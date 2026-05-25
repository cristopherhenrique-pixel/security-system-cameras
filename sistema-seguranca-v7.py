import time
import os
import base64
import json
import threading
import re
from collections import deque
import subprocess
import sys

# --- Dependency Check ---
# Mapeamento do nome do pacote (instalação) para o nome do módulo (importação)
REQUIRED_PACKAGES = {
    "opencv-python": "cv2",
    "numpy": "numpy",
    "pygetwindow": "pygetwindow",
    "Pillow": "PIL",
    "requests": "requests",
    "ultralytics": "ultralytics",
    "psutil": "psutil",
    "pywin32": "win32gui"
}

def verify_environment():
    """Verifica se o ambiente tem o básico para rodar sem travar."""
    for package, module in REQUIRED_PACKAGES.items():
        try:
            __import__(module if module != "win32gui" else "win32gui")
        except ImportError as e:
            print(f"FATAL: Biblioteca {package} nao encontrada. Erro: {e}")
            if not getattr(sys, 'frozen', False):
                print("DICA: Rode 'pip install -r requirements.txt'")
            time.sleep(5)
            sys.exit(1)

# Verifica ambiente antes de importar o grosso do sistema
verify_environment()

# Agora importamos as bibliotecas externas após garantir que existem
import cv2
import numpy as np
import pygetwindow as gw
import win32gui
import win32ui
import win32con
import requests
import psutil

# Importação dos módulos customizados
from yolo_handler import YoloManager
from risk_handler import gerar_mascaras_risco, processar_movimento_risco, selecionar_areas_de_risco, desenhar_areas_no_frame
from window_selector import selecionar_janela_e_roi
from comms_handler import processar_alerta_background, enviar_telegram, analisar_imagem
# Importa utilitários
from utils import carregar_config, salvar_config, CONFIG_PATH, carregar_status, salvar_status, STATUS_PATH, capturar_janela, logger, get_resource_path

def abrir_interface_config():
    """Abre a interface grafica. Em EXE, chama o proprio executavel."""
    cmd = [sys.executable]
    if not getattr(sys, 'frozen', False):
        cmd.append(os.path.join(os.path.dirname(__file__), "config_gui.py"))
    subprocess.Popen(cmd, close_fds=True)

# VERIFICAÇÃO DE ENTRADA: Abre a GUI se iniciado diretamente
if "--child" not in sys.argv:
    resposta = input("Deseja abrir as janelas (Interface e Preview)? [s/n]: ").strip().lower()
    if resposta == 's':
        abrir_interface_config()
        sys.exit(0)
    else:
        print("🚀 Iniciando monitoramento em modo segundo plano (apenas terminal)...")
        os.environ["HEADLESS_MODE"] = "1"

cfg = carregar_config()
last_config_mod_time = os.path.getmtime(CONFIG_PATH) # Marca o tempo da última alteração
status_data = carregar_status() # Carrega o status inicial
yolo_manager = YoloManager()

logger.info("Engine de Monitoramento Iniciada.")

# Atalhos baseados no Config
RESIZE_SCALE = cfg["deteccao"].get("resize_scale_yolo", 0.5)
DISPLAY_RESIZE_SCALE = cfg["deteccao"].get("display_resize_scale", 0.7) # Escala para a janela de pré-visualização (X% do tamanho original)
SKIP_YOLO = cfg["deteccao"].get("skip_yolo", 5)
YOLO_CONF_THRESHOLD = cfg["deteccao"].get("yolo_confidence_threshold", 0.6)
ULTIMO_ALERTA_IA = 0
ia_em_andamento = False

# =========================
# CONFIG DETECÇÃO
# =========================
FRAME_TIME = 1 / cfg["deteccao"]["fps_limit"]
SPINNER = ["◐", "◓", "◑", "◒"]

def detect_motion(frame_gray, prev_gray):
    """Detecta movimento comparando o frame atual com o anterior (Mais leve)."""
    if prev_gray is None or prev_gray.shape != frame_gray.shape:
        return False, 0, None

    frame_delta = cv2.absdiff(prev_gray, frame_gray)
    thresh = cv2.threshold(frame_delta, cfg["deteccao"]["threshold"], 255, cv2.THRESH_BINARY)[1]
    dilations = cfg["deteccao"].get("dilate_iterations", 2)
    thresh = cv2.dilate(thresh, None, iterations=dilations)
    thresh_copy = thresh.copy()
    cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    movimento_real = False
    area_total = 0
    
    for c in cnts: # Itera sobre os contornos encontrados
        area = cv2.contourArea(c)
        min_area = cfg["deteccao"].get("min_contour_area", 150)
        if area < min_area: 
            continue
        movimento_real = True
        area_total += int(area)
    
    return movimento_real, area_total, thresh_copy

prev_frame = None
frame_count = 0
cooldown = 0
ULTIMA_ATT_LOG = 0
tempo_inicio_video = 0
tempo_movimento_continuo_geral = 0
tempo_movimento_continuo_risco = 0
ultimo_detect_geral = 0
ultimo_detect_risco = 0
videos_salvos = 0
alertas_enviados = 0
boxes_to_draw = [] # Lista global para persistir os indicadores na tela

# =========================
# GRAVAÇÃO (VÍDEO)
# =========================
gravando_video = False
video_writer = None
ultimo_movimento_tempo = 0
exibir_preview = os.environ.get("HEADLESS_MODE") != "1" # Flag para controlar a visibilidade da janela

def criar_writer(nome, largura, altura, fps): # Função auxiliar para criar o VideoWriter
    output_format = cfg["arquivos"].get("video_output_format", "mp4").lower()
    codec = cfg["arquivos"].get("video_codec", "mp4v")
    if output_format == "mp4":
        # Se o codec for H264 ou avc1, costuma dar erro de DLL no Windows
        if codec.lower() in ["h264", "avc1"]:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        else:
            fourcc = cv2.VideoWriter_fourcc(*codec) 
    else: # Default para AVI
        fourcc = cv2.VideoWriter_fourcc(*"XVID") 

    # Garante que o diretório de destino existe antes de criar o arquivo
    os.makedirs(os.path.dirname(nome), exist_ok=True)

    # Tenta abrir forçando o backend FFMPEG
    writer = cv2.VideoWriter(nome, cv2.CAP_FFMPEG, fourcc, fps, (largura, altura))
    
    # Se falhar, tenta forçar o backend MSMF (Microsoft Media Foundation), nativo do Windows
    if not writer.isOpened():
        logger.warning(f"FFMPEG falhou para {nome}. Tentando backend nativo MSMF...")
        writer = cv2.VideoWriter(nome, cv2.CAP_MSMF, fourcc, fps, (largura, altura))
        
    return writer

# =========================
# WORKER (PARA NÃO TRAVAR)
# =========================
# =========================
# LOOP
# =========================
def realizar_limpeza_arquivos(cfg):
    dias = cfg["arquivos"].get("limpeza_dias", 0)
    pasta = cfg["arquivos"].get("pasta_gravacoes", "gravacoes")
    
    # Validação de Drive: Verifica se o drive (ex: E:/) está montado
    drive = os.path.splitdrive(pasta)[0]
    if drive and not os.path.exists(drive):
        logger.error(f"Drive {drive} não encontrado! O caminho '{pasta}' é inválido após a formatação.")
        # Fallback para pasta local do script
        pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gravacoes")
        cfg["arquivos"]["pasta_gravacoes"] = pasta
        logger.info(f"Redirecionando gravações para: {pasta}")
        salvar_config(cfg)

    if not os.path.exists(pasta):
        try: os.makedirs(pasta, exist_ok=True)
        except Exception as e: logger.error(f"Não foi possível criar a pasta {pasta}: {e}")

    if dias <= 0: return
    if not os.path.exists(pasta): return
    limite = time.time() - (dias * 86400)
    removidos = 0
    for f in os.listdir(pasta):
        path = os.path.join(pasta, f)
        if os.path.isfile(path) and os.path.getmtime(path) < limite:
            try: 
                os.remove(path)
                removidos += 1
            except: pass
    if removidos > 0:
        print(f"🧹 Limpeza Automática: {removidos} arquivos removidos.")

realizar_limpeza_arquivos(cfg)

# Usamos round() para garantir compatibilidade exata com o redimensionamento do OpenCV
h_ref, w_ref = round(cfg["deteccao"]["roi"]["h"] * RESIZE_SCALE), round(cfg["deteccao"]["roi"]["w"] * RESIZE_SCALE)
risk_masks = gerar_mascaras_risco(cfg, (h_ref, w_ref), RESIZE_SCALE)
window_name = "Monitoramento de Seguranca"
window_initialized = False
window_found = True

# Variáveis para controlar o log de estado da sessão (evitar spam no log)
last_session_state_logged = None
last_session_state = None

print("\n🚀 Sistema monitorando... Pressione Ctrl+C para encerrar.\n")
try:
    while True:
        inicio_loop = time.time()
        agora = inicio_loop
        DISPLAY_RESIZE_SCALE = cfg["deteccao"].get("display_resize_scale", 0.7)

        frame_count += 1
        heartbeat = SPINNER[frame_count % len(SPINNER)]

        frame_full = capturar_janela(cfg["deteccao"]["titulo_janela"], cfg)
        
        # VERIFICAÇÃO DE ATUALIZAÇÃO DE CONFIGURAÇÃO EM TEMPO REAL
        try:
            mtime = os.path.getmtime(CONFIG_PATH)
            if mtime > last_config_mod_time:
                cfg = carregar_config()
                last_config_mod_time = mtime
                # Atualiza as variáveis que dependem do config
                FRAME_TIME = 1 / cfg["deteccao"]["fps_limit"]
                RESIZE_SCALE = cfg["deteccao"].get("resize_scale_yolo", 0.5)
                SKIP_YOLO = cfg["deteccao"].get("skip_yolo", 5)
                YOLO_CONF_THRESHOLD = cfg["deteccao"].get("yolo_confidence_threshold", 0.6)
                # Regenera as máscaras caso a escala ou áreas tenham mudado
                h_ref, w_ref = round(cfg["deteccao"]["roi"]["h"] * RESIZE_SCALE), round(cfg["deteccao"]["roi"]["w"] * RESIZE_SCALE)
                risk_masks = gerar_mascaras_risco(cfg, (h_ref, w_ref), RESIZE_SCALE)

                prev_frame = None # Reset prev_frame, pois as dimensões do frame podem ter mudado
                # Verifica se solicitou reconfiguração de Janela/ROI
                if cfg["deteccao"].get("solicitar_reconfiguracao_window", False):
                    cfg["deteccao"]["solicitar_reconfiguracao_window"] = False
                    salvar_config(cfg)
                    selecionar_janela_e_roi(cfg)
                    # Recarrega tudo após a mudança de janela/ROI
                    cfg = carregar_config()
                    last_config_mod_time = os.path.getmtime(CONFIG_PATH)
                    h_ref, w_ref = round(cfg["deteccao"]["roi"]["h"] * RESIZE_SCALE), round(cfg["deteccao"]["roi"]["w"] * RESIZE_SCALE)
                    risk_masks = gerar_mascaras_risco(cfg, (h_ref, w_ref), RESIZE_SCALE)
                    prev_frame = None # Reset prev_frame novamente após reconfiguração de janela/ROI

                # Verifica se a GUI solicitou a abertura da seleção de áreas de risco
                if cfg["deteccao"].get("solicitar_reconfiguracao_risco", False): # Flag para reconfigurar áreas de risco
                    cfg["deteccao"]["solicitar_reconfiguracao_risco"] = False
                    salvar_config(cfg)
                    # Atualiza o tempo para não detectar a própria mudança de flag
                    last_config_mod_time = os.path.getmtime(CONFIG_PATH)
                    
                    selecionar_areas_de_risco(cfg)
                    
                    # Recarrega e atualiza após o desenho para sincronizar com o que foi salvo no seletor
                    cfg = carregar_config()
                    last_config_mod_time = os.path.getmtime(CONFIG_PATH) # Atualiza o timestamp da config
                    risk_masks = gerar_mascaras_risco(cfg, (h_ref, w_ref), RESIZE_SCALE)
                    prev_frame = None # Reset prev_frame novamente após reconfiguração de áreas de risco
                
                logger.info("Configurações atualizadas em tempo real!")
        except Exception as e: pass
        
        if frame_full is None:
            if window_found:
                logger.warning(f"Janela '{cfg['deteccao']['titulo_janela']}' não encontrada!")
                window_found = False
            if gravando_video:
                # Fecha o vídeo atual para não corromper se a janela sumir (garante integridade do arquivo)
                status_data["gravando_atualmente"] = False
                gravando_video = False # Reset the flag
                if video_writer: video_writer.release(); video_writer = None
            time.sleep(2)
            continue
        
        if not window_found:
            logger.info(f"Janela '{cfg['deteccao']['titulo_janela']}' recuperada.")
            window_found = True
        
        if isinstance(frame_full, str) and frame_full in ["MINIMIZED", "SESSION_LOCKED", "ROI_ERROR"]:
            if last_session_state_logged != frame_full:
                logger.warning(f"Captura suspensa: {frame_full}")
                last_session_state_logged = frame_full
            time.sleep(1)
            continue
        last_session_state_logged = "OK" # Resetar o estado logado quando a captura volta ao normal

        # Validação final antes do resize para evitar o erro !ssize.empty()
        if frame_full is None or frame_full.size == 0:
            continue

        frame_small = cv2.resize(frame_full, (0, 0), fx=RESIZE_SCALE, fy=RESIZE_SCALE)
        gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        # Detecção de Movimento com check de tamanho para evitar erro absdiff
        movimento_detectado = False
        pixels_movimento = 0
        thresh_img = None
        
        movimento_detectado, pixels_movimento, thresh_img = detect_motion(gray, prev_frame)
        prev_frame = gray # Atualiza para a próxima comparação

        # Cálculo de movimento fora das áreas de risco (Geral)
        px_fora_risco = int(pixels_movimento / (RESIZE_SCALE**2)) # Valor base
        if risk_masks and thresh_img is not None:
            # Verificação de segurança: Se o tamanho do frame mudar, regenera as máscaras para evitar crash (robustez)
            if thresh_img.shape != risk_masks[0].shape:
                risk_masks = gerar_mascaras_risco(cfg, thresh_img.shape, RESIZE_SCALE)
            
            try:
                # Combina todas as máscaras de risco para subtrair do geral
                mask_todas_areas = cv2.bitwise_or.reduce(risk_masks) if len(risk_masks) > 1 else risk_masks[0]
                mask_fora = cv2.bitwise_not(mask_todas_areas)
                res_fora = cv2.bitwise_and(thresh_img, mask_fora) # Movimento fora das áreas de risco
                px_fora_risco = int(cv2.countNonZero(res_fora) / (RESIZE_SCALE**2))
            except Exception:
                pass

        # Lógica de persistência do movimento Geral (para gatilho de gravação)
        if px_fora_risco > cfg["deteccao"].get("geral_px_gatilho", 3000):
            if tempo_movimento_continuo_geral == 0:
                tempo_movimento_continuo_geral = agora
            ultimo_detect_geral = agora
        elif agora - ultimo_detect_geral > 0.5: # 500ms de tolerância para manter o acúmulo de tempo
            tempo_movimento_continuo_geral = 0

        # Gatilho de Gravação baseada na persistência (configurado via GUI) para movimento geral
        alerta_por_geral = tempo_movimento_continuo_geral > 0 and \
                           (agora - tempo_movimento_continuo_geral >= cfg["deteccao"].get("geral_tempo_gatilho", 5))

        pessoa_detectada_yolo = False
        fumaca_detectada_yolo = False
        fogo_detectado_yolo = False
        veiculo_detectado = False
        objeto_detectado = False
        person_in_risk_area = False
        movimento_na_area_risco = False
        
        detalhes_areas = []
        # Lógica de YOLO (Otimizada: só roda se houver movimento e respeitar o skip)
        yolo_status = {"pessoa": False, "veiculo": False, "fogo": False, "fumaca": False}
        if (cfg["deteccao"].get("usar_yolo") or cfg["deteccao"].get("usar_fogo_fumaca")):
            if (frame_count % SKIP_YOLO == 0) and (movimento_detectado or gravando_video): # Só roda YOLO se houver movimento ou já estiver gravando
                boxes_to_draw, yolo_status = yolo_manager.detectar(frame_small, cfg, RESIZE_SCALE)
                pessoa_detectada_yolo = yolo_status["pessoa"]
                veiculo_detectado = yolo_status["veiculo"]
                fogo_detectado_yolo = yolo_status["fogo"]
                fumaca_detectada_yolo = yolo_status["fumaca"]
            else:
                # Persiste os estados de detecção entre os frames pulados para evitar oscilação nos gatilhos
                pessoa_detectada_yolo = any(d[2] == "person" for d in boxes_to_draw)
                veiculo_detectado = any(d[2] in ["car", "truck", "motorcycle"] for d in boxes_to_draw)
                fogo_detectado_yolo = any("fire" in d[2] or "fogo" in d[2] for d in boxes_to_draw)
                fumaca_detectada_yolo = any("smoke" in d[2] or "fumaça" in d[2] for d in boxes_to_draw)
        else:
            # Se desativado, limpa os desenhos imediatamente
            boxes_to_draw = []
        
        # Análise e Desenho das Áreas de Risco com Contador de Movimento Interno (se ativado)
        if cfg["deteccao"].get("usar_areas_risco"):
            movimento_na_area_risco, detalhes_areas = processar_movimento_risco(thresh_img, risk_masks, cfg, RESIZE_SCALE)

        # Gatilho de Tempo - Risco (Global para todas as áreas)
        if movimento_na_area_risco and cfg["deteccao"].get("usar_areas_risco", True):
            if tempo_movimento_continuo_risco == 0:
                tempo_movimento_continuo_risco = agora
            ultimo_detect_risco = agora
        elif agora - ultimo_detect_risco > 0.5: # 500ms de tolerância
            tempo_movimento_continuo_risco = 0

        # Definição dos gatilhos de alerta antes do uso na gravação
        alerta_por_risco = tempo_movimento_continuo_risco > 0 and \
                           (agora - tempo_movimento_continuo_risco >= cfg["deteccao"].get("risco_tempo_gatilho", 0.5))
        alerta_por_fogo_fumaca = fogo_detectado_yolo or fumaca_detectada_yolo
        
        # --- Algoritmo de Manutenção de Gravação (Keep-Alive) ---
        # Definimos 'atividade_presente' como qualquer movimento que supere os limites de sensibilidade,
        # sem exigir a persistência (segundos contínuos) necessária para o disparo inicial.
        atividade_presente = (px_fora_risco > cfg["deteccao"].get("geral_px_gatilho", 3000)) or \
                             movimento_na_area_risco or \
                             pessoa_detectada_yolo or veiculo_detectado or \
                             fogo_detectado_yolo or fumaca_detectada_yolo
        
        # HISTERESE: Mantém o estado de movimento por alguns frames para evitar cortes
        # Adiciona fogo e fumaça para manter a gravação ativa (importante para detecções críticas)
        if atividade_presente or person_in_risk_area:
            cooldown = int(cfg["deteccao"].get("fps_limit", 20) * 2) # Mantém ativo por 2 segundos após detecção

        # Estado final para gravação: Movimento real OU ainda está no tempo de cooldown
        movimento_ativo = (cooldown > 0)

        # Cooldown de detecção para evitar múltiplos alertas/gravações em sequência rápida
        detection_cooldown = cfg["deteccao"].get("detection_cooldown_seconds", 2)

        # --- Lógica de Gravação de Vídeo (Definição de Gatilho) ---
        # O vídeo agora começa por qualquer detecção válida
        trigger_inicio = (alerta_por_geral and cfg["deteccao"].get("gravar_geral", True)) or \
                         (alerta_por_risco and cfg["deteccao"].get("gravar_risco", True)) or \
                         alerta_por_fogo_fumaca or pessoa_detectada_yolo or veiculo_detectado

        # Se houver atividade atual, resetamos o cronômetro de 'último movimento'.
        # Isso evita que o vídeo seja cortado se o movimento for intermitente.
        if atividade_presente:
            ultimo_movimento_tempo = agora
        gravar_agora = (trigger_inicio or gravando_video) and cfg["arquivos"].get("salvar_video", True) and (agora - ULTIMO_ALERTA_IA > detection_cooldown)
        desenhar_no_video = cfg["deteccao"].get("desenhar_overlays_video", True)

        # --- INICIALIZAÇÃO DA GRAVAÇÃO (Common) ---
        if gravar_agora and not gravando_video:
            timestamp = int(agora)
            ext = cfg["arquivos"].get("video_output_format", "mp4").lower()
            nome_video = f"{cfg['arquivos']['pasta_gravacoes']}/video_{timestamp}.{ext}"
            video_writer = criar_writer(nome_video, frame_full.shape[1], frame_full.shape[0], cfg["deteccao"]["fps_limit"])
            gravando_video = True
            status_data["gravando_atualmente"] = True
            salvar_status(status_data)
            tempo_inicio_video = agora # Reset video start time
            videos_salvos += 1
            mode_log = "com overlay" if desenhar_no_video else "limpa"
            logger.info(f"🔴 Gravação Iniciada ({mode_log}): {os.path.basename(nome_video)}")

        # --- Parte 1: Gravação de Frame Limpo ---
        if gravando_video and not desenhar_no_video and video_writer:
            video_writer.write(frame_full)

        # --- DESENHO DOS INDICADORES E OVERLAYS ---
        # Desenha áreas de risco aqui para respeitar a opção de vídeo limpo
        if cfg["deteccao"].get("usar_areas_risco"):
            desenhar_areas_no_frame(frame_full, detalhes_areas)

        yolo_manager.desenhar_deteccoes(frame_full, boxes_to_draw)

        # Limpeza de memória do tracking
        if frame_count % 100 == 0:
            yolo_manager.limpar_tracking(frame_count)

        # --- Lógica de Gravação de Vídeo (Parte 2: Frame com Desenhos) ---
        # Se o usuário QUER as linhas no vídeo, gravamos APÓS os desenhos acima.
        if gravando_video and desenhar_no_video and video_writer:
            video_writer.write(frame_full)

        # Lógica de Parada da Gravação
        if gravando_video:
            tempo_atual_gravacao = agora - tempo_inicio_video
            tempo_desde_ultimo_mov = agora - ultimo_movimento_tempo
            limite_video = cfg["deteccao"].get("max_video_duration", 300)

            if (tempo_desde_ultimo_mov > cfg["deteccao"].get("tempo_sem_movimento", 10)) or (tempo_atual_gravacao >= limite_video):
                gravando_video = False
                status_data["gravando_atualmente"] = False # Atualiza status_data
                salvar_status(status_data) # Salva status_data
                logger.info("⚪ Gravação Finalizada (Tempo Esgotado/Sem Movimento).")
                if video_writer:
                    video_writer.release()
                    video_writer = None

        # Disparo de Alerta (Telegram + IA)
        # Lógica de filtragem de alertas Telegram
        
        # Verifica se algum bot está ativo e configurado para alertar para este tipo de movimento
        any_bot_active = cfg["telegram"].get("ativo", False) or cfg.get("telegram_bot2", {}).get("ativo", False)
        
        alerta_por_risco_cond = (alerta_por_risco and cfg["telegram"].get("alertar_risco", True)) or \
                                (alerta_por_risco and cfg.get("telegram_bot2", {}).get("alertar_risco", False))
        alerta_por_geral_cond = ((alerta_por_geral or alerta_por_fogo_fumaca) and cfg["telegram"].get("alertar_geral", True)) or \
                                ((alerta_por_geral or alerta_por_fogo_fumaca) and cfg.get("telegram_bot2", {}).get("alertar_geral", False))

        pode_enviar_alerta = (alerta_por_risco_cond or alerta_por_geral_cond) and any_bot_active
        
        # Aplica um intervalo global mínimo de 5s para evitar sobrecarga, mas respeita o config individual depois
        if pode_enviar_alerta and (agora - ULTIMO_ALERTA_IA < 5):
            pode_enviar_alerta = False

        if pode_enviar_alerta:
            ULTIMO_ALERTA_IA = agora
            alertas_enviados += 1

            # Atualiza o JSON com a info do último alerta para a GUI
            status_data["ultimo_alerta"] = {
                "timestamp": time.strftime('%H:%M:%S'),
                "tipo": "Área de Risco" if alerta_por_risco else "Movimento Geral"
            }
            salvar_status(status_data) # Salva status_data

            # Passa apenas o frame original, a thread cuida dos recortes específicos de cada bot
            processar_alerta_background(cfg, frame_full.copy(), 
                                        tipo_alerta="Área de Risco" if alerta_por_risco else "Movimento Geral",
                                        alerta_por_risco=alerta_por_risco, alerta_por_geral=alerta_por_geral or alerta_por_fogo_fumaca)

        # Decrementa cooldown frame a frame
        if cooldown > 0: cooldown -= 1

        # =========================
        # STATUS NO TERMINAL
        # =========================
        # Prepara o frame para exibição
        frame_display = cv2.resize(frame_full, (0, 0), fx=DISPLAY_RESIZE_SCALE, fy=DISPLAY_RESIZE_SCALE)

        # --- ENVIO DE TELEMETRIA PARA O STATUS.JSON ---
        if agora - ULTIMA_ATT_LOG >= 0.5:
            fps_real = 1.0 / (time.time() - inicio_loop) if (time.time() - inicio_loop) > 0 else 0
            px_risco_max = max([a['pixels'] for a in detalhes_areas]) if detalhes_areas else 0
            
            # Cálculo dos tempos atuais de persistência para telemetria na GUI
            tm_geral = (agora - tempo_movimento_continuo_geral) if tempo_movimento_continuo_geral > 0 else 0
            tm_risco = (agora - tempo_movimento_continuo_risco) if tempo_movimento_continuo_risco > 0 else 0

            status_data["telemetria"] = {
                "px_fora": px_fora_risco,
                "px_risco": px_risco_max,
                "tm_geral": round(tm_geral, 1),
                "tm_risco": round(tm_risco, 1),
                "fps": f"{fps_real:.1f}",
                "cpu": psutil.cpu_percent(),
                "ram": psutil.virtual_memory().percent,
                "vids": videos_salvos,
                "alertas": alertas_enviados
            }
            salvar_status(status_data)

            ULTIMA_ATT_LOG = agora

        if exibir_preview:
            try:
                # Verifica se o usuário fechou a janela pelo 'X' do Windows
                if window_initialized and cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    exibir_preview = False
                    cv2.destroyWindow(window_name)
                    logger.info("Janela de preview fechada. O sistema continua rodando no terminal.")
                
                # Só tenta renderizar se o preview ainda estiver ativo
                if exibir_preview:
                    cv2.imshow(window_name, frame_display)
                    if not window_initialized:
                        pos = cfg["deteccao"].get("window_pos")
                        if pos:
                            try: cv2.moveWindow(window_name, pos[0], pos[1])
                            except: pass
                        window_initialized = True
            except Exception:
                # Se houver erro ao acessar a janela (já fechada), desativa o preview e continua no terminal
                if window_initialized:
                    exibir_preview = False
                    logger.info("Janela de preview encerrada. Continuando monitoramento apenas via terminal.")

        # Controle de FPS para não fritar o processador
        tempo_gasto = time.time() - inicio_loop
        if tempo_gasto < FRAME_TIME:
            time.sleep(FRAME_TIME - tempo_gasto)
        
        cv2.waitKey(1)

except KeyboardInterrupt:
    logger.info("👋 Sistema encerrado pelo usuário (KeyboardInterrupt).")
finally:
    # Garante que o status de gravação seja resetado ao fechar
    status_data = carregar_status() # Recarrega para garantir que não sobrescreva algo
    status_data["gravando_atualmente"] = False
    salvar_status(status_data)

    try:
        # Salva a posição da janela de vídeo antes de fechar
        rect = cv2.getWindowImageRect(window_name)
        if rect[2] > 0: # Garante que a janela estava aberta
            cfg = carregar_config()
            cfg["deteccao"]["window_pos"] = [rect[0], rect[1]]
            salvar_config(cfg)
    except Exception as e: 
        logger.warning(f"Não foi possível salvar a posição da janela: {e}")
        pass

    if video_writer:
        video_writer.release()
    cv2.destroyAllWindows()