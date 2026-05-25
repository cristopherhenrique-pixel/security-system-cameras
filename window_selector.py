import cv2
import pygetwindow as gw
import tkinter as tk
from tkinter import ttk
import time
from utils import capturar_janela, salvar_config, logger # Importa o logger

def selecionar_janela_e_roi(cfg):
    """Abre uma interface para escolher a janela e depois o ROI das câmeras."""
    # 1. Mini Interface para escolher o título da janela
    root = tk.Tk()
    root.title("Selecionar Janela das Câmeras")
    root.attributes("-topmost", True)
    root.geometry("450x350")

    selected_title = tk.StringVar()
    
    ttk.Label(root, text="Selecione a janela do software de monitoramento:", font=("Arial", 10, "bold")).pack(pady=10)
    
    # Filtra janelas que possuem título
    titles = sorted([w.title for w in gw.getAllWindows() if w.title.strip()])
    
    frame_list = ttk.Frame(root)
    frame_list.pack(fill='both', expand=True, padx=10)
    
    scrollbar = ttk.Scrollbar(frame_list)
    scrollbar.pack(side='right', fill='y')
    
    listbox = tk.Listbox(frame_list, yscrollcommand=scrollbar.set, font=("Consolas", 9))
    for t in titles: listbox.insert(tk.END, t)
    listbox.pack(side='left', fill='both', expand=True)
    scrollbar.config(command=listbox.yview)

    def confirmar():
        if listbox.curselection():
            selected_title.set(listbox.get(listbox.curselection()))
            root.destroy()

    ttk.Button(root, text="PRÓXIMO: SELECIONAR ÁREA (ROI)", command=confirmar).pack(pady=15)
    root.mainloop()

    if not selected_title.get():
        return

    # 2. Atualiza o título e busca o frame para selecionar ROI
    cfg["deteccao"]["titulo_janela"] = selected_title.get()
    
    logger.info(f"Janela selecionada: {cfg['deteccao']['titulo_janela']}. Aguardando captura...")
    
    static_frame = None
    while static_frame is None or isinstance(static_frame, str):
        static_frame = capturar_janela(cfg["deteccao"]["titulo_janela"], cfg, ignorar_roi=True)
        time.sleep(0.5)

    # 3. OpenCV Select ROI
    win_roi = "Arraste o mouse sobre os 4 slots e pressione ENTER"
    cv2.namedWindow(win_roi, cv2.WINDOW_NORMAL)
    roi = cv2.selectROI(win_roi, static_frame, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow(win_roi)

    if roi[2] > 0 and roi[3] > 0:
        cfg["deteccao"]["roi"] = {"x": int(roi[0]), "y": int(roi[1]), "w": int(roi[2]), "h": int(roi[3])}
        salvar_config(cfg)
        logger.info(f"ROI configurado com sucesso: {cfg['deteccao']['roi']}")