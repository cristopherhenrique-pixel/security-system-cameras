import cv2
import requests
import base64
import time
import os
import re
import threading
from utils import logger # Importa o logger

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def analisar_imagem(cfg, image_path):
    base64_image = encode_image(image_path)
    payload = {
        "model": cfg["ia"]["model_name"],
        "messages": [
            {"role": "system", "content": cfg["ia"]["system_prompt"]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analise a imagem"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ],
        "temperature": cfg["ia"].get("temperature", 0.2)
    }
    try:
        # Timeout de 5s para conectar e 25s para processar a resposta
        r = requests.post(cfg["ia"]["url"], json=payload, timeout=(5, 25))
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.ConnectTimeout:
        logger.warning("IA: Tempo de conexão esgotado. Verifique se o servidor LM Studio está ativo.")
        return "Erro IA: Servidor offline"
    except requests.exceptions.ReadTimeout:
        logger.warning("IA: O servidor demorou muito para processar a imagem.")
        return "Erro IA: Resposta lenta"
    except Exception as e:
        logger.error(f"Erro na análise da IA: {e}")
        return f"Erro IA: {e}"

def recortar_slot(frame, slot):
    """Divide o frame em 4 quadrantes e retorna o slot solicitado (1-4)."""
    h, w = frame.shape[:2]
    if slot == 1: # Superior Esquerdo
        return frame[0:h//2, 0:w//2]
    elif slot == 2: # Superior Direito
        return frame[0:h//2, w//2:w]
    elif slot == 3: # Inferior Esquerdo
        return frame[h//2:h, 0:w//2]
    elif slot == 4: # Inferior Direito
        return frame[h//2:h, w//2:w]
    return frame

def enviar_telegram(bot_config, imagem_path, legenda, bot_name="Bot"): # imagem_path é o caminho para a imagem já salva
    if not bot_config["ativo"]:
        return
    try:
        url = f"https://api.telegram.org/bot{bot_config['token']}/sendPhoto"
        legenda_formatada = re.sub(r"(Setor \d:)", r"*\1*", legenda)
        with open(imagem_path, "rb") as img:
            requests.post(url, data={
                "chat_id": bot_config["chat_id"],
                "caption": legenda_formatada,
                "parse_mode": "Markdown",
                "disable_notification": bot_config.get("silent_mode", False)
            }, files={"photo": img})
        logger.info(f"Telegram: Foto enviada com sucesso ({os.path.basename(imagem_path)}) para {bot_name}")
    except Exception as e:
        logger.error(f"Erro Crítico Telegram ({bot_name}): {e}")

def processar_alerta_background(cfg, frame_full_copy, tipo_alerta="Movimento", alerta_por_risco=False, alerta_por_geral=False):
    def worker():
        try:
            legenda_final = f"🚨 *{tipo_alerta}* detectado às {time.strftime('%H:%M:%S')}"
            img_path_full = f"{cfg['arquivos']['pasta_gravacoes']}/img_full_{int(time.time())}.jpg"

            cv2.imwrite(img_path_full, frame_full_copy)

            if cfg["ia"].get("ativo"):
                logger.info(f"IA: Analisando evento de {tipo_alerta}...")
                descricao_bruta = analisar_imagem(cfg, img_path_full)
                if "Erro" not in descricao_bruta:
                    linhas_breves = [l.split('|')[1].strip() if '|' in l else l.strip() for l in descricao_bruta.split('\n')]
                    legenda_final = f"🚨 *{tipo_alerta}* - Análise IA:\n" + "\n".join(linhas_breves)
                else:
                    logger.warning(f"IA falhou, enviando apenas foto. Erro: {descricao_bruta}")
                
                if cfg["arquivos"]["salvar_texto"]:
                    nome_relatorio = os.path.join(cfg["arquivos"]["pasta_gravacoes"], f"relatorio_{time.strftime('%Y-%m-%d')}.txt")
                    with open(nome_relatorio, "a", encoding="utf-8") as f:
                        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {descricao_bruta}\n")
            
            # Enviar para os bots do Telegram
            bots_configs = [
                {"config": cfg["telegram"], "name": "Bot Principal"},
                {"config": cfg.get("telegram_bot2", {}), "name": "Bot Secundário"}
            ]

            current_time = time.time()
            for bot_info in bots_configs:
                bot_cfg = bot_info["config"]
                bot_name = bot_info["name"]
                
                if not bot_cfg.get("ativo", False):
                    continue

                should_alert_this_bot = False
                if alerta_por_risco and bot_cfg.get("alertar_risco", True):
                    should_alert_this_bot = True
                if alerta_por_geral and bot_cfg.get("alertar_geral", True):
                    should_alert_this_bot = True
                
                if should_alert_this_bot:
                    last_sent_key = f"last_sent_{bot_name.replace(' ', '_').lower()}"
                    if current_time - bot_cfg.get(last_sent_key, 0) < bot_cfg.get("intervalo_envio", 10):
                        logger.info(f"Telegram ({bot_name}): Ignorando envio devido ao intervalo.")
                        continue
                    
                    # Lógica de Imagem (Full ou Cropped por Bot)
                    if bot_cfg.get("enviar_crop_roi", False):
                        slot = bot_cfg.get("slot", 1)
                        img_slot = recortar_slot(frame_full_copy, slot)
                        bot_id = "1" if "Principal" in bot_name else "2" # Identificador para o nome do arquivo temporário
                        temp_crop_path = img_path_full.replace(".jpg", f"_bot{bot_id}_crop.jpg")
                        cv2.imwrite(temp_crop_path, img_slot)
                        enviar_telegram(bot_cfg, temp_crop_path, legenda_final, bot_name)
                        if os.path.exists(temp_crop_path): os.remove(temp_crop_path)
                    else:
                        enviar_telegram(bot_cfg, img_path_full, legenda_final, bot_name)
                    
                    bot_cfg[last_sent_key] = current_time # Update last sent time in config (in-memory)
        except Exception as e:
            logger.error(f"Erro no worker de alerta em background: {e}", exc_info=True)
        finally:
            if not cfg["arquivos"]["salvar_imagem"]:
                if os.path.exists(img_path_full):
                    os.remove(img_path_full)

    threading.Thread(target=worker, daemon=True).start()