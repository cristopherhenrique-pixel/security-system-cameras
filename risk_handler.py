import cv2
import numpy as np
import time
import pygetwindow as gw
from utils import capturar_janela, salvar_config
from utils import logger # Importa o logger
DRAWING_MODE = 0
DRAGGING_MODE = 1

state = {
    "drawing_polygon": False,
    "current_polygon": [],
    "polygons_to_save": [],
    "current_mode": DRAWING_MODE,
    "selected_polygon_index": -1,
    "drag_start_point": None
}

def mouse_callback_polygon(event, x, y, flags, param):
    global state
    close_dist = 15 

    if state["current_mode"] == DRAGGING_MODE:
        if event == cv2.EVENT_LBUTTONDOWN:
            state["selected_polygon_index"] = -1
            for i, poly in enumerate(state["polygons_to_save"]):
                if cv2.pointPolygonTest(poly, (x, y), False) >= 0:
                    state["selected_polygon_index"] = i
                    state["drag_start_point"] = (x, y)
                    break
        elif event == cv2.EVENT_MOUSEMOVE and state["selected_polygon_index"] != -1 and (flags & cv2.EVENT_FLAG_LBUTTON):
            if state["drag_start_point"] is not None:
                dx, dy = x - state["drag_start_point"][0], y - state["drag_start_point"][1]
                state["polygons_to_save"][state["selected_polygon_index"]] = (state["polygons_to_save"][state["selected_polygon_index"]] + (dx, dy)).astype(np.int32)
                state["drag_start_point"] = (x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            state["selected_polygon_index"] = -1
        elif event == cv2.EVENT_RBUTTONDOWN and state["selected_polygon_index"] != -1:
            state["polygons_to_save"].pop(state["selected_polygon_index"])
            state["selected_polygon_index"] = -1
        return

    if event == cv2.EVENT_LBUTTONDOWN:
        if not state["drawing_polygon"]:
            state["drawing_polygon"] = True
            state["current_polygon"] = [(x, y)]
        else:
            dist = np.sqrt((x - state["current_polygon"][0][0])**2 + (y - state["current_polygon"][0][1])**2)
            if dist < close_dist and len(state["current_polygon"]) > 2:
                state["polygons_to_save"].append(np.array(state["current_polygon"], np.int32))
                state["drawing_polygon"] = False
                state["current_polygon"] = []
            else:
                state["current_polygon"].append((x, y))
    elif event == cv2.EVENT_RBUTTONDOWN and state["drawing_polygon"]:
        if len(state["current_polygon"]) > 2:
            state["polygons_to_save"].append(np.array(state["current_polygon"], np.int32))
        state["drawing_polygon"] = False
        state["current_polygon"] = []

def selecionar_areas_de_risco(cfg):
    titulo = cfg["deteccao"]["titulo_janela"]
    janelas = [j for j in gw.getAllWindows() if titulo.lower() in j.title.lower()]
    if janelas:
        try: janelas[0].activate(); time.sleep(1)
        except: pass

    state["polygons_to_save"] = [np.array(p, np.int32) for p in cfg["deteccao"].get("risk_areas", [])]
    static_frame = None
    while static_frame is None or isinstance(static_frame, str):
        static_frame = capturar_janela(titulo, cfg, ignorar_roi=False)
        if static_frame is None or isinstance(static_frame, str):
            time.sleep(1)

    win_title = "Selecione Areas de Risco (Pressione 'q' para sair)"
    cv2.namedWindow(win_title, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win_title, mouse_callback_polygon)

    while True:
        display_frame = static_frame.copy()
        h, w = display_frame.shape[:2]
        cv2.rectangle(display_frame, (0, 0), (w, 45), (40, 40, 40), -1)
        cv2.putText(display_frame, "[D] Desenhar [G] Arrastar [C] Limpar [Q] Sair", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        mode_text = "DESENHO" if state["current_mode"] == DRAWING_MODE else "ARRASTAR"
        cv2.putText(display_frame, f"MODO: {mode_text}", (w-150, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        for i, poly in enumerate(state["polygons_to_save"]):
            color = (0, 0, 255) if (state["current_mode"] == DRAGGING_MODE and i == state["selected_polygon_index"]) else (0, 255, 0)
            cv2.polylines(display_frame, [poly], True, color, 2)
        
        if state["drawing_polygon"] and len(state["current_polygon"]) > 0:
            cv2.polylines(display_frame, [np.array(state["current_polygon"], np.int32)], False, (0, 255, 255), 2)

        cv2.imshow(win_title, display_frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'): break
        elif key == ord('c'): state["polygons_to_save"] = []
        elif key == ord('d'): state["current_mode"] = DRAWING_MODE
        elif key == ord('r'): state["current_mode"] = DRAWING_MODE # 'r' para resetar/desenhar
        elif key == ord('g'): state["current_mode"] = DRAGGING_MODE
    
    cv2.destroyWindow(win_title)
    cfg["deteccao"]["risk_areas"] = [poly.tolist() for poly in state["polygons_to_save"]]
    salvar_config(cfg)

def desenhar_areas_no_frame(frame, detalhes_areas):
    for area in detalhes_areas:
        cor = (0, 0, 255) if area["ativo"] else (0, 255, 255)
        cv2.polylines(frame, [area["poly"]], True, cor, 2)
        cv2.putText(frame, f"Risco: {area['pixels']}", (area["poly"][0][0], area["poly"][0][1]-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 1)

def gerar_mascaras_risco(cfg, frame_shape_small, resize_scale):
    masks = []
    for poly_coords in cfg["deteccao"].get("risk_areas", []):
        mask = np.zeros(frame_shape_small, dtype=np.uint8)
        poly_small = (np.array(poly_coords) * resize_scale).astype(np.int32)
        cv2.fillPoly(mask, [poly_small], 255)
        masks.append(mask)
    return masks

def processar_movimento_risco(thresh_img, risk_masks, cfg, resize_scale):
    movimento_na_area = False
    detalhes_areas = []
    
    if not risk_masks or thresh_img is None:
        return False, []

    for i, mask in enumerate(risk_masks):
        res = cv2.bitwise_and(thresh_img, mask)
        px_count = int(cv2.countNonZero(res) / (resize_scale**2))
        
        ativo = px_count > cfg["deteccao"].get("risco_px_gatilho", 1000)
        if ativo: movimento_na_area = True
        
        detalhes_areas.append({
            "pixels": px_count,
            "ativo": ativo,
            "poly": np.array(cfg["deteccao"]["risk_areas"][i], np.int32)
        })
    
    return movimento_na_area, detalhes_areas