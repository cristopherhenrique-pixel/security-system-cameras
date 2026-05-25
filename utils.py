import json
import os
import time
import cv2
import numpy as np
import pygetwindow as gw
import win32gui
import win32ui
import win32con
import logging
from logging.handlers import RotatingFileHandler
import sys

def get_resource_path(relative_path):
    """Obtém o caminho absoluto para recursos (modelos, ícones).
    Funciona para dev e para PyInstaller (_MEIPASS)."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

def get_data_path(filename):
    """Obtém o caminho para arquivos de dados graváveis (config, logs).
    Estes devem ficar na pasta do executável, não na temporária do bundle."""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    path = os.path.join(base_path, filename)
    # Garante que o diretório base existe
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

CONFIG_PATH = get_data_path("config_geral.json")
STATUS_PATH = get_data_path("status.json")
LOG_PATH = get_data_path("system.log")

# Setup Logging
def setup_logging():
    logger = logging.getLogger('SistemaSeguranca')
    logger.setLevel(logging.INFO)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File Handler (Rotating)
    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8') # 10MB per file, 5 backups
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logging()

def carregar_config():
    """Lê o arquivo JSON com sistema de retentativas para evitar conflitos de I/O."""
    # Determine o diretório base para o caminho padrão da pasta de gravações
    default_gravacoes_path = os.path.join(os.path.dirname(CONFIG_PATH), "gravacoes")
    default_config = {
        "deteccao": {"fps_limit": 15, "threshold": 35, "titulo_janela": "Yoosee", "roi": {"x":0,"y":0,"w":640,"h":480}},
        "arquivos": {"pasta_gravacoes": default_gravacoes_path, "salvar_video": True, "video_output_format": "mp4", "video_codec": "mp4v"},
        "ia": {"ativo": False},
        "telegram": {"ativo": False}
    }
    for _ in range(5):
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            return default_config
        except (json.JSONDecodeError, PermissionError):
            time.sleep(0.1)
    return default_config

def salvar_config(config_data):
    """Salva as configurações de forma atômica usando um arquivo temporário."""
    temp_path = CONFIG_PATH + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        
        for _ in range(5):
            try:
                os.replace(temp_path, CONFIG_PATH)
                return True
            except PermissionError:
                time.sleep(0.1)
        
        raise PermissionError(f"Acesso negado ao salvar {CONFIG_PATH} após retentativas.")
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        logger.error(f"Erro ao salvar configuração: {e}")
        return False

def carregar_status():
    """Lê o arquivo de status em tempo real."""
    for _ in range(5):
        try:
            if os.path.exists(STATUS_PATH):
                with open(STATUS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            break
        except (json.JSONDecodeError, PermissionError, FileNotFoundError):
            time.sleep(0.05)
    else:
        logger.debug(f"Não foi possível carregar o arquivo de status em {STATUS_PATH} após retentativas.")

    return {"gravando_atualmente": False, "ultimo_alerta": None}

def salvar_status(status_data):
    """Salva o status de forma rápida com retentativas para evitar conflitos no Windows."""
    temp_path = STATUS_PATH + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(status_data, f, indent=4, ensure_ascii=False)
        
        for _ in range(10):
            try:
                os.replace(temp_path, STATUS_PATH)
                return True
            except PermissionError:
                time.sleep(0.05)
        
        raise PermissionError(f"Acesso negado ao substituir {STATUS_PATH} após retentativas.")
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        logger.error(f"Erro ao salvar status: {e}", exc_info=True)
        return False

def capturar_janela(titulo, cfg, ignorar_roi=False):
    """Captura a janela específica pelo título e aplica o ROI se configurado."""
    try:
        janelas = [j for j in gw.getAllWindows() if titulo.lower() in j.title.lower()]
        if not janelas:
            return None
        logger.debug(f"Janela '{titulo}' encontrada.")
        
        janela = janelas[0]
        if janela.isMinimized:
            return "MINIMIZED"

        hwnd = janela._hWnd
        left, top, right, bot = win32gui.GetWindowRect(hwnd)
        w, h = right - left, bot - top
        
        if w <= 0 or h <= 0:
            return None

        hwndDC = None
        mfcDC = None
        saveDC = None
        saveBitMap = None
        try:
            if cfg["deteccao"].get("modo_teste", False):
                hwndDC = win32gui.GetDC(0)
            else:
                hwndDC = win32gui.GetWindowDC(hwnd)

            mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
            saveDC.SelectObject(saveBitMap)
            saveDC.BitBlt((0, 0), (w, h), mfcDC, (0, 0), win32con.SRCCOPY)

            signedIntsArray = saveBitMap.GetBitmapBits(True)
            img = np.frombuffer(signedIntsArray, dtype='uint8')
            img.shape = (h, w, 4)
        finally:
            if saveBitMap: win32gui.DeleteObject(saveBitMap.GetHandle())
            if saveDC: saveDC.DeleteDC()
            if mfcDC: mfcDC.DeleteDC()
            if hwndDC: win32gui.ReleaseDC(hwnd, hwndDC)

        if 'img' not in locals():
            return "SESSION_LOCKED"

        frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        if frame is None or frame.size == 0:
            return None

        roi = cfg["deteccao"].get("roi")
        if roi and not ignorar_roi:
            max_h, max_w = frame.shape[:2]
            if roi['y'] >= max_h or roi['x'] >= max_w:
                return "ROI_ERROR"

            frame = frame[roi['y']:min(roi['y']+roi['h'], max_h), 
                          roi['x']:min(roi['x']+roi['w'], max_w)]
        
        return frame if frame.size > 0 else None
    except Exception:
        logger.error(f"Erro na captura de janela para '{titulo}'", exc_info=True)
        return None