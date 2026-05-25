from ultralytics import YOLO
import os
import cv2
import numpy as np
from utils import logger, get_resource_path

class YoloManager:
    def __init__(self):
        self.model_main = None
        self.model_smoke = None
        self.tracking_history = {}
        self.last_seen_tracking = {}

    def carregar_modelos(self, cfg):
        if cfg["deteccao"].get("usar_yolo") and self.model_main is None:
            model_path = get_resource_path(cfg["deteccao"].get("yolo_main_model_path", "yolov8n.pt"))
            self.model_main = YOLO(model_path)
            logger.info("YOLOv8 Principal carregado em memória.")
        elif not cfg["deteccao"].get("usar_yolo") and self.model_main is not None:
            del self.model_main
            self.model_main = None
            logger.info("YOLOv8 Principal descarregado da memória.")

        if cfg["deteccao"].get("usar_fogo_fumaca") and self.model_smoke is None:
            # Ajustado para procurar dentro do bundle do EXE
            caminho_repo = get_resource_path("YOLOv8-Fire-and-Smoke-Detection")
            # Verifica se o diretório existe antes de tentar carregar
            if not os.path.exists(caminho_repo): logger.warning(f"Diretório do modelo de Fogo/Fumaça não encontrado: {caminho_repo}"); return
            for peso in ["best.pt", "fire_smoke.pt", "runs/detect/train/weights/best.pt"]:
                path_pt = os.path.join(caminho_repo, peso)
                if os.path.exists(path_pt):
                    self.model_smoke = YOLO(path_pt) # type: ignore
                    logger.info(f"Modelo Fogo/Fumaça carregado: {peso}")
                    break

    def detectar(self, frame_small, cfg, resize_scale):
        # Recarrega/descarrega modelos se as configurações mudaram
        self.carregar_modelos(cfg)

        deteccoes = []
        status = {"pessoa": False, "veiculo": False, "fogo": False, "fumaca": False}
        
        # Obtém as classes permitidas do config, se a lista estiver vazia, todas são permitidas
        allowed_classes = cfg["deteccao"].get("yolo_allowed_classes", [])
        if not allowed_classes: # Se a lista estiver vazia, permite todas as classes conhecidas
            allowed_classes = ["person", "car", "truck", "motorcycle", "bus", "dog", "cat", "bird"]
        
        # Garante que classes de fogo/fumaça estejam na lista se o módulo estiver ativo
        if cfg["deteccao"].get("usar_fogo_fumaca"):
            allowed_classes += ["fire", "fogo", "smoke", "fumaça"]
        
        modelos_ativos = []
        if cfg["deteccao"].get("usar_yolo"): modelos_ativos.append(self.model_main)
        if cfg["deteccao"].get("usar_fogo_fumaca"): modelos_ativos.append(self.model_smoke)

        for m in [m for m in modelos_ativos if m]:
            if m == self.model_smoke:
                # Fogo/Fumaça costuma funcionar melhor com predict e confiança um pouco menor (0.4)
                results = m.predict(frame_small, verbose=False, conf=min(0.4, cfg["deteccao"].get("yolo_confidence_threshold", 0.6)))
            else:
                results = m.track(frame_small, persist=True, verbose=False, conf=cfg["deteccao"].get("yolo_confidence_threshold", 0.6))
            for r in results:
                if r.boxes:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        class_name = r.names[cls_id].lower()
                        
                        if class_name not in allowed_classes: continue # Filtra classes não permitidas

                        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy() / resize_scale)
                        
                        color = (255, 255, 255)
                        if class_name == "person":
                            color = (0, 255, 255); status["pessoa"] = True
                        elif class_name in ["car", "truck", "motorcycle"]:
                            color = (255, 128, 0); status["veiculo"] = True
                        elif "fire" in class_name or "fogo" in class_name: color = (0, 0, 255); status["fogo"] = True
                        elif "smoke" in class_name or "fumaça" in class_name: color = (0, 165, 255); status["fumaca"] = True
                        
                        deteccoes.append(((x1, y1), (x2, y2), class_name, color))
        return deteccoes, status

    def desenhar_deteccoes(self, frame, deteccoes):
        for (pt1, pt2, label, color) in deteccoes:
            cv2.rectangle(frame, pt1, pt2, color, 1)
            cv2.putText(frame, label, (pt1[0], pt1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    def limpar_tracking(self, frame_count):
        for tid in list(self.tracking_history.keys()):
            if frame_count - self.last_seen_tracking.get(tid, 0) > 100:
                del self.tracking_history[tid]
                if tid in self.last_seen_tracking: del self.last_seen_tracking[tid]