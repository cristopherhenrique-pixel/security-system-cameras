import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import json
import os
import subprocess
import threading
import sys

# Importa utilitários centralizados
from utils import carregar_config, salvar_config, carregar_status, salvar_status, CONFIG_PATH, STATUS_PATH, logger, get_resource_path
SCRIPT_PRINCIPAL = os.path.join(os.path.dirname(__file__), "sistema-seguranca-v7.py")

class ConfigApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Configurações do Sistema de Segurança")
        self.processo_sistema = None
        self.config = carregar_config()
        self.status = carregar_status() # Carrega o status para a GUI
        self.root.geometry(self.config.get("gui_geometry", "600x900"))
        
        # Garante que a seção telegram_bot2 exista para evitar KeyError
        if "telegram_bot2" not in self.config:
            self.config["telegram_bot2"] = {
                "token": "",
                "chat_id": "",
                "ativo": False,
                "alertar_risco": True,
                "alertar_geral": True,
                "intervalo_envio": 60,
                "enviar_crop_roi": True
            }

        # Garante valores padrão para novos campos
        det = self.config.get("deteccao", {})
        for key, val in {
            "detection_cooldown_seconds": 2, 
            "yolo_allowed_classes": [],
            "risco_px_gatilho": 400,
            "risco_tempo_gatilho": 0.5
        }.items():
            if key not in det: det[key] = val
        if "video_output_format" not in self.config.get("arquivos", {}):
            self.config.setdefault("arquivos", {})["video_output_format"] = "mp4"
        if "video_codec" not in self.config.get("arquivos", {}):
            self.config.setdefault("arquivos", {})["video_codec"] = "avc1"
        
        self.create_widgets()
        self.atualizar_status_rec()
        self.iniciar_sistema()
        self.verificar_processo()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def salvar_config(self):
        try:
            # LÊ: Busca a configuração mais recente do disco (com os desenhos novos)
            config_recente = carregar_config()

            # MODIFICA: Atualiza apenas o que a GUI controla
            config_recente["deteccao"]["threshold"] = int(self.sld_thresh.get())
            config_recente["deteccao"]["fps_limit"] = int(self.sld_fps.get())
            config_recente["deteccao"]["geral_px_gatilho"] = int(self.sld_area.get())
            config_recente["deteccao"]["risco_px_gatilho"] = int(self.sld_risco.get())
            config_recente["deteccao"]["geral_tempo_gatilho"] = round(float(self.sld_tempo_grav.get()), 1)
            config_recente["deteccao"]["risco_tempo_gatilho"] = round(float(self.sld_risco_tempo.get()), 1)
            config_recente["deteccao"]["tempo_sem_movimento"] = int(self.sld_pos_grav.get())
            config_recente["deteccao"]["min_contour_area"] = int(self.sld_min_area.get())
            config_recente["deteccao"]["dilate_iterations"] = int(self.sld_dilate.get())
            config_recente["deteccao"]["max_video_duration"] = int(self.sld_max_video.get())
            config_recente["deteccao"]["detection_cooldown_seconds"] = int(self.sld_cooldown.get())
            
            config_recente["ia"]["url"] = self.entry_ia_url.get()
            config_recente["ia"]["ativo"] = self.var_ia.get()
            config_recente["ia"]["model_name"] = self.entry_ia_model.get()
            config_recente["ia"]["system_prompt"] = self.txt_prompt.get("1.0", tk.END).strip()
            config_recente["ia"]["temperature"] = round(float(self.sld_ia_temp.get()), 2)
            
            # Bot 1 (Mestre)
            config_recente["telegram"]["ativo"] = self.var_tg1.get()
            config_recente["telegram"]["token"] = self.entry_tg1_token.get()
            config_recente["telegram"]["chat_id"] = self.entry_tg1_chatid.get()
            config_recente["telegram"]["alertar_risco"] = self.var_tg1_risco.get()
            config_recente["telegram"]["alertar_geral"] = self.var_tg1_geral.get()
            config_recente["telegram"]["intervalo_envio"] = int(self.sld_tg1_interval.get())
            config_recente["telegram"]["enviar_crop_roi"] = self.var_tg1_crop.get()
            config_recente["telegram"]["slot"] = int(self.combo_tg1_slot.get())
            config_recente["telegram"]["silent_mode"] = self.var_tg1_silent.get()

            # Bot 2 (Secundário)
            config_recente["telegram_bot2"]["ativo"] = self.var_tg2.get()
            config_recente["telegram_bot2"]["token"] = self.entry_tg2_token.get()
            config_recente["telegram_bot2"]["chat_id"] = self.entry_tg2_chatid.get()
            config_recente["telegram_bot2"]["alertar_risco"] = self.var_tg2_risco.get()
            config_recente["telegram_bot2"]["alertar_geral"] = self.var_tg2_geral.get()
            config_recente["telegram_bot2"]["intervalo_envio"] = int(self.sld_tg2_interval.get())
            config_recente["telegram_bot2"]["enviar_crop_roi"] = self.var_tg2_crop.get()
            config_recente["telegram_bot2"]["slot"] = int(self.combo_tg2_slot.get())
            config_recente["telegram_bot2"]["silent_mode"] = self.var_tg2_silent.get()

            config_recente["deteccao"]["usar_yolo"] = self.var_yolo.get()
            config_recente["deteccao"]["yolo_confidence_threshold"] = round(float(self.sld_yolo_conf.get()), 2)
            config_recente["deteccao"]["skip_yolo"] = int(self.sld_yolo_skip.get())
            config_recente["deteccao"]["resize_scale_yolo"] = round(float(self.sld_yolo_scale.get()), 2)
            
            config_recente["deteccao"]["usar_fogo_fumaca"] = self.var_fogo.get()
            
            config_recente["deteccao"]["modo_teste"] = self.var_modo_teste.get()
            config_recente["deteccao"]["usar_areas_risco"] = self.var_usar_risco.get()
            config_recente["deteccao"]["desenhar_overlays_video"] = self.var_overlays_vid.get()
            config_recente["deteccao"]["display_resize_scale"] = round(float(self.sld_display_scale.get()), 2)
            config_recente["deteccao"]["titulo_janela"] = self.entry_win_title.get()

            config_recente["arquivos"]["salvar_imagem"] = self.var_img.get()
            config_recente["arquivos"]["salvar_video"] = self.var_vid.get()
            config_recente["arquivos"]["video_output_format"] = self.combo_video_format.get()
            config_recente["arquivos"]["video_codec"] = self.combo_video_codec.get()
            config_recente["deteccao"]["gravar_geral"] = self.var_gravar_geral.get()
            config_recente["deteccao"]["gravar_risco"] = self.var_gravar_risco.get()

            config_recente["arquivos"]["pasta_gravacoes"] = self.entry_path.get()
            config_recente["arquivos"]["limpeza_dias"] = int(self.sld_cleanup.get())

            # GRAVA: Salva o objeto mesclado de volta no disco
            self.config = config_recente
            
            if salvar_config(config_recente):
                messagebox.showinfo("Sucesso", "Configurações salvas com sucesso!")
        except Exception as e:
            logger.error(f"Erro ao salvar configurações: {e}", exc_info=True)
            messagebox.showerror("Erro", f"Erro ao salvar configurações: {e}")

    def atualizar_status_rec(self):
        """Verifica no JSON se o sistema está gravando e lê a telemetria."""
        try:
            self.status = carregar_status() # Recarrega o status para a GUI
            if self.status.get("gravando_atualmente", False):
                self.lbl_rec.config(text="● GRAVANDO", foreground="red")
            else:
                self.lbl_rec.config(text="○ STANDBY", foreground="gray")

            # Atualiza Telemetria
            tel = self.status.get("telemetria", {})
            self.prog_px_geral['value'] = tel.get("px_fora", 0)
            self.lbl_px_geral.config(text=f"Mov. Geral: {tel.get('px_fora', 0)} px")
            
            self.prog_px_risco['value'] = tel.get("px_risco", 0)
            self.lbl_px_risco.config(text=f"Invasão Risco: {tel.get('px_risco', 0)} px")
            
            # Atualiza Timers de Gatilho (Persistência)
            tm_g = tel.get("tm_geral", 0)
            lim_g = self.config["deteccao"].get("geral_tempo_gatilho", 5)
            self.prog_tm_geral['maximum'] = lim_g if lim_g > 0 else 1
            self.prog_tm_geral['value'] = tm_g
            self.lbl_tm_geral.config(text=f"Tempo p/ Gravar: {tm_g:.1f} / {lim_g}s")

            tm_r = tel.get("tm_risco", 0)
            lim_r = self.config["deteccao"].get("risco_tempo_gatilho", 2)
            self.prog_tm_risco['maximum'] = lim_r if lim_r > 0 else 1
            self.prog_tm_risco['value'] = tm_r
            self.lbl_tm_risco.config(text=f"Tempo p/ Alerta Risco: {tm_r:.1f} / {lim_r}s")

            self.lbl_sys_info.config(text=f"CPU: {tel.get('cpu', 0)}% | RAM: {tel.get('ram', 0)}% | FPS: {tel.get('fps', 0)}")

            # Mostra o último alerta enviado
            alerta = self.status.get("ultimo_alerta")
            if alerta:
                self.lbl_alerta.config(text=f"Último Alerta: {alerta['tipo']} às {alerta['timestamp']}", foreground="#0055ff")
        except Exception as e:
            logger.debug(f"Erro ao atualizar status na GUI: {e}") # Debug level, pois é esperado que o status.json possa estar vazio no início
        self.root.after(1000, self.atualizar_status_rec)

    def iniciar_sistema(self):
        """Inicia o sistema principal em segundo plano capturando o terminal."""
        if self.processo_sistema and self.processo_sistema.poll() is None:
            messagebox.showwarning("Aviso", "O sistema já está em execução!")
            return

        try:
            self.processo_sistema = subprocess.Popen(
                [sys.executable, SCRIPT_PRINCIPAL, "--child"],
                cwd=os.path.dirname(SCRIPT_PRINCIPAL),
            )
            logger.info("Sistema principal iniciado com sucesso.")
        except Exception as e:
            logger.critical(f"Falha ao iniciar sistema principal: {e}", exc_info=True)
            messagebox.showerror("Erro", f"Falha ao iniciar sistema principal: {e}")

    def parar_sistema(self):
        """Finaliza o processo do sistema de monitoramento."""
        if self.processo_sistema:
            self.processo_sistema.terminate()
        self.root.destroy()
        os._exit(0) # Encerra completamente o processo Python

    def verificar_processo(self):
        """Monitora se o processo principal ainda está rodando."""
        if self.processo_sistema and self.processo_sistema.poll() is not None:
            self.processo_sistema = None
            logger.warning("Sistema principal foi encerrado inesperadamente.")
        self.root.after(1000, self.verificar_processo)

    def on_closing(self):
        """Salva a geometria da janela antes de fechar."""
        self.config["gui_geometry"] = self.root.geometry()
        salvar_config(self.config)
        self.root.destroy()

    def abrir_selecao_risco(self):
        # Recarrega para garantir que não estamos enviando flags antigas
        self.config = carregar_config()
        self.config["deteccao"]["solicitar_reconfiguracao_risco"] = True
        salvar_config(self.config)
        
        messagebox.showinfo("Ação Necessária", "A janela de seleção de áreas de risco será aberta no monitoramento agora.")

    def abrir_selecao_window(self):
        """Solicita ao processo principal que abra a seleção de janela/ROI."""
        self.config = carregar_config()
        self.config["deteccao"]["solicitar_reconfiguracao_window"] = True
        salvar_config(self.config)
        
        messagebox.showinfo("Ação Necessária", "A interface de seleção de janela e ROI será aberta agora.")

    def verificar_modelos_yolo(self):
        """Verifica se os arquivos .pt do YOLO existem no disco para carregamento."""
        main_model = get_resource_path(self.config["deteccao"].get("yolo_main_model_path", "yolov8n.pt"))
        smoke_dir = get_resource_path("YOLOv8-Fire-and-Smoke-Detection")
        
        msg = "Verificação de Modelos:\n"
        msg += f"- Principal ({os.path.basename(main_model)}): {'✅ Disponível' if os.path.exists(main_model) else '❌ Arquivo ausente'}\n"
        msg += f"- Fogo/Fumaça (Pasta): {'✅ Disponível' if os.path.exists(smoke_dir) else '❌ Pasta ausente'}\n"
        
        if os.path.exists(main_model):
            messagebox.showinfo("Status dos Modelos", msg)
        else:
            messagebox.showwarning("Atenção", msg)

    def selecionar_pasta(self):
        diretorio = filedialog.askdirectory()
        if diretorio:
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, diretorio)

    def create_widgets(self):
        style = ttk.Style()
        style.configure("Help.TLabel", foreground="gray", font=('Helvetica', 8))
        style.configure("Header.TLabel", font=('Helvetica', 10, 'bold'))
        style.configure("Rec.TLabel", font=('Helvetica', 12, 'bold'))
        style.configure("Tel.TLabel", font=('Helvetica', 9))

        # Status REC no topo
        self.lbl_rec = ttk.Label(self.root, text="○ STANDBY", style="Rec.TLabel")
        self.lbl_rec.pack(pady=5)

        # Status do Último Alerta
        self.lbl_alerta = ttk.Label(self.root, text="Nenhum alerta enviado nesta sessão", font=('Helvetica', 9, 'italic'))
        self.lbl_alerta.pack(pady=2)

        # Rodapé (Botões Salvar/Fechar) - Empacotado primeiro no fundo para garantir visibilidade
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(side='bottom', fill='x', pady=10)

        ttk.Button(btn_frame, text="💾 SALVAR CONFIGURAÇÕES", command=self.salvar_config).pack(side='left', expand=True, padx=5)
        ttk.Button(btn_frame, text="FECHAR", command=self.root.destroy).pack(side='right', expand=True, padx=5)

        # Conteúdo Central (Abas) - Expandirá no espaço que sobrar entre o topo e o fundo
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=5, pady=5)

        # --- ABAS ---
        tab_det = ttk.Frame(notebook)
        tab_rec = ttk.Frame(notebook)
        tab_ia_vision = ttk.Frame(notebook)
        tab_tg_all = ttk.Frame(notebook)
        tab_sys = ttk.Frame(notebook)

        notebook.add(tab_det, text="Detecção")
        notebook.add(tab_rec, text="Gravação")
        notebook.add(tab_ia_vision, text="IA & Visão")
        notebook.add(tab_tg_all, text="Telegram (Bots)")
        notebook.add(tab_sys, text="Zonas & Sistema")

        def create_scale(parent, label, from_, to, var_key, help_text="", resolution=1):
            frame = ttk.Frame(parent)
            frame.pack(fill='x', padx=10, pady=2)
            ttk.Label(frame, text=label, style="Header.TLabel").pack(anchor='w')
            scale = tk.Scale(frame, from_=from_, to=to, resolution=resolution, orient="horizontal")
            scale.set(self.config["deteccao"].get(var_key, from_))
            scale.pack(fill='x')
            if help_text: ttk.Label(frame, text=help_text, style="Help.TLabel").pack(anchor='w')
            return scale

        # Threshold
        self.sld_thresh = create_scale(tab_det, "Sensibilidade de Luz (Threshold):", 0, 255, "threshold", "Quanto menor, mais sensível a mudanças. Ideal: 25-45.")
        self.sld_fps = create_scale(tab_det, "Fluidez da Análise (FPS):", 1, 60, "fps_limit", "Quantidade de quadros por segundo. Ideal: 15-20.")
        
        cv_frame = ttk.LabelFrame(tab_det, text=" Refinamento OpenCV ", padding=5)
        cv_frame.pack(fill='x', padx=10, pady=5)
        self.sld_min_area = tk.Scale(cv_frame, from_=10, to=1000, orient="horizontal", label="Tamanho Mínimo do Movimento")
        self.sld_min_area.set(self.config["deteccao"].get("min_contour_area", 150)); self.sld_min_area.pack(fill='x')
        ttk.Label(cv_frame, text="Ignora objetos menores que este valor. Ideal: 150.", style="Help.TLabel").pack(anchor='w')
        self.sld_dilate = tk.Scale(cv_frame, from_=0, to=10, orient="horizontal", label="Filtro de Ruído (Dilação - Aumente para unir movimentos)")
        self.sld_dilate.set(self.config["deteccao"].get("dilate_iterations", 2)); self.sld_dilate.pack(fill='x')
        ttk.Label(cv_frame, text="Une partes do movimento para formar um único objeto. Ideal: 2.", style="Help.TLabel").pack(anchor='w')

        self.sld_area = create_scale(tab_det, "Volume de Movimento p/ Gravar:", 100, 15000, "geral_px_gatilho", "Quantidade de pixels necessária. Ideal: 3000-5000.", resolution=100)
        self.sld_risco = create_scale(tab_det, "Volume de Movimento em Risco:", 100, 5000, "risco_px_gatilho", "Sensibilidade em áreas críticas. Ideal: 300-600 para alta sensibilidade.", resolution=50)
        self.sld_cooldown = create_scale(tab_det, "Espera Pós-Detecção (seg):", 0, 10, "detection_cooldown_seconds", "Tempo para resetar a detecção após parar. Ideal: 2s.") # type: ignore

        # --- TELEMETRIA NO RODAPÉ DA ABA DETECÇÃO ---
        tel_frame = ttk.LabelFrame(tab_det, text=" Telemetria ", padding=5)
        tel_frame.pack(fill='x', padx=10, pady=5, side='bottom')
        
        tel_grid = ttk.Frame(tel_frame)
        tel_grid.pack(fill='x')
        
        self.lbl_px_geral = ttk.Label(tel_grid, text="Mov: 0 px", style="Tel.TLabel")
        self.lbl_px_geral.grid(row=0, column=0, sticky='w')
        self.prog_px_geral = ttk.Progressbar(tel_grid, maximum=10000, length=120)
        self.prog_px_geral.grid(row=0, column=1, padx=5, sticky='ew')

        self.lbl_tm_geral = ttk.Label(tel_grid, text="Rec: 0s", style="Tel.TLabel")
        self.lbl_tm_geral.grid(row=0, column=2, sticky='w')
        self.prog_tm_geral = ttk.Progressbar(tel_grid, maximum=10, length=120)
        self.prog_tm_geral.grid(row=0, column=3, padx=5, sticky='ew')
        
        self.lbl_px_risco = ttk.Label(tel_grid, text="Risco: 0 px", style="Tel.TLabel")
        self.lbl_px_risco.grid(row=1, column=0, sticky='w')
        self.prog_px_risco = ttk.Progressbar(tel_grid, maximum=5000, length=120)
        self.prog_px_risco.grid(row=1, column=1, padx=5, sticky='ew')

        self.lbl_tm_risco = ttk.Label(tel_grid, text="Alt: 0s", style="Tel.TLabel")
        self.lbl_tm_risco.grid(row=1, column=2, sticky='w')
        self.prog_tm_risco = ttk.Progressbar(tel_grid, maximum=10, length=120)
        self.prog_tm_risco.grid(row=1, column=3, padx=5, sticky='ew')

        tel_grid.columnconfigure((1,3), weight=1)

        self.lbl_sys_info = ttk.Label(tel_frame, text="CPU: 0% | RAM: 0% | FPS: 0", foreground="gray")
        self.lbl_sys_info.pack(anchor='e')

        # --- TAB GRAVAÇÃO ---
        self.sld_tempo_grav = create_scale(tab_rec, "Persistência p/ Gravar (seg):", 0.1, 30.0, "geral_tempo_gatilho", "Tempo de movimento necessário para iniciar o vídeo. Ideal: 3-5s.", resolution=0.1)
        self.sld_risco_tempo = create_scale(tab_rec, "Persistência em Risco (seg):", 0.1, 30.0, "risco_tempo_gatilho", "Tempo em área de risco para disparar alerta. Ideal: 0.5-1s para alertas rápidos.", resolution=0.1)
        self.sld_pos_grav = create_scale(tab_rec, "Gravação Extra pós-Movimento:", 1, 60, "tempo_sem_movimento", "Tempo que o vídeo continua após o fim do movimento. Ideal: 10s.")
        self.sld_max_video = create_scale(tab_rec, "Duração Máxima de Vídeo:", 30, 1800, "max_video_duration", "Limite de tempo para cada arquivo de vídeo. Ideal: 300s.", resolution=30)

        def add_module_option(parent, var, title, description):
            frame = ttk.Frame(parent)
            frame.pack(fill='x', padx=10, pady=2)
            ttk.Checkbutton(frame, text=title, variable=var).pack(anchor='w')
            if description: ttk.Label(frame, text=description, style="Help.TLabel").pack(anchor='w', padx=20)
            return frame

        file_opt = ttk.LabelFrame(tab_rec, text=" Opções de Arquivo ", padding=5)
        file_opt.pack(fill='x', padx=10, pady=5)
        self.var_img = tk.BooleanVar(value=self.config["arquivos"].get("salvar_imagem"))
        add_module_option(file_opt, self.var_img, "Salvar Fotos", "")
        self.var_vid = tk.BooleanVar(value=self.config["arquivos"].get("salvar_video"))
        add_module_option(file_opt, self.var_vid, "Gravar Vídeos", "")
        self.var_gravar_geral = tk.BooleanVar(value=self.config["deteccao"].get("gravar_geral", True))
        add_module_option(file_opt, self.var_gravar_geral, "Gatilho Geral", "")
        self.var_gravar_risco = tk.BooleanVar(value=self.config["deteccao"].get("gravar_risco", True))
        add_module_option(file_opt, self.var_gravar_risco, "Gatilho Risco", "")
        self.var_overlays_vid = tk.BooleanVar(value=self.config["deteccao"].get("desenhar_overlays_video", True))
        add_module_option(file_opt, self.var_overlays_vid, "Overlays no Vídeo", "")
        
        ttk.Label(file_opt, text="Formato de Vídeo:").pack(anchor='w', padx=10)
        self.combo_video_format = ttk.Combobox(file_opt, values=["mp4", "avi"], state="readonly", width=5)
        self.combo_video_format.set(self.config["arquivos"].get("video_output_format", "mp4")); self.combo_video_format.pack(anchor='w', padx=10)

        ttk.Label(file_opt, text="Codec (avc1 = H.264 padrão web):").pack(anchor='w', padx=10)
        self.combo_video_codec = ttk.Combobox(file_opt, values=["avc1", "mp4v", "X264", "H264"], state="readonly", width=8)
        self.combo_video_codec.set(self.config["arquivos"].get("video_codec", "avc1")); self.combo_video_codec.pack(anchor='w', padx=10)

        # --- TAB IA & VISÃO ---
        llm_frame = ttk.LabelFrame(tab_ia_vision, text=" Análise LLM (LM Studio) ", padding=5)
        llm_frame.pack(fill='x', padx=10, pady=5)
        self.var_ia = tk.BooleanVar(value=self.config["ia"].get("ativo"))
        
        ttk.Label(llm_frame, text="URL do Servidor Local (Ex: http://IP:PORTA/v1/...):").pack(anchor='w', padx=10)
        self.entry_ia_url = ttk.Entry(llm_frame)
        self.entry_ia_url.insert(0, self.config["ia"].get("url", "")); self.entry_ia_url.pack(fill='x', padx=10)

        add_module_option(llm_frame, self.var_ia, "Ativar Análise IA", "")
        ttk.Label(llm_frame, text="Nome do Modelo:").pack(anchor='w', padx=10)
        self.entry_ia_model = ttk.Entry(llm_frame)
        self.entry_ia_model.insert(0, self.config["ia"].get("model_name", "")); self.entry_ia_model.pack(fill='x', padx=10)
        ttk.Label(llm_frame, text="System Prompt:").pack(anchor='w', padx=10)
        self.txt_prompt = scrolledtext.ScrolledText(llm_frame, height=3, font=("Helvetica", 9))
        self.txt_prompt.insert(tk.END, self.config["ia"].get("system_prompt", "")); self.txt_prompt.pack(fill='x', padx=10)
        self.sld_ia_temp = tk.Scale(llm_frame, from_=0, to=1, resolution=0.1, orient="horizontal", label="Criatividade da IA")
        self.sld_ia_temp.set(self.config["ia"].get("temperature", 0.2)); self.sld_ia_temp.pack(fill='x', padx=10)
        ttk.Label(llm_frame, text="Controla a variedade da resposta. Ideal: 0.2", style="Help.TLabel").pack(anchor='w', padx=10)

        yolo_frame = ttk.LabelFrame(tab_ia_vision, text=" Detecção YOLO ", padding=5)
        yolo_frame.pack(fill='x', padx=10, pady=5)
        self.var_yolo = tk.BooleanVar(value=self.config["deteccao"].get("usar_yolo"))
        add_module_option(yolo_frame, self.var_yolo, "Ativar YOLO (Humanos/Veículos)", "")
        self.var_fogo = tk.BooleanVar(value=self.config["deteccao"].get("usar_fogo_fumaca"))
        add_module_option(yolo_frame, self.var_fogo, "Ativar Fogo e Fumaça", "")
        self.sld_yolo_conf = tk.Scale(yolo_frame, from_=0.1, to=0.9, resolution=0.05, orient="horizontal", label="Certeza da Detecção")
        self.sld_yolo_conf.set(self.config["deteccao"].get("yolo_confidence_threshold", 0.6)); self.sld_yolo_conf.pack(fill='x', padx=10)
        ttk.Label(yolo_frame, text="Nível de certeza para identificar objetos. Ideal: 0.60", style="Help.TLabel").pack(anchor='w', padx=10)
        self.sld_yolo_skip = tk.Scale(yolo_frame, from_=1, to=20, orient="horizontal", label="Intervalo de Quadros (Skip)")
        self.sld_yolo_skip.set(self.config["deteccao"].get("skip_yolo", 5)); self.sld_yolo_skip.pack(fill='x', padx=10)
        ttk.Label(yolo_frame, text="Processa a cada X quadros para economizar CPU. Ideal: 5", style="Help.TLabel").pack(anchor='w', padx=10)
        self.sld_yolo_scale = tk.Scale(yolo_frame, from_=0.1, to=1.0, resolution=0.1, orient="horizontal", label="Escala da Imagem p/ IA")
        self.sld_yolo_scale.set(self.config["deteccao"].get("resize_scale_yolo", 0.5)); self.sld_yolo_scale.pack(fill='x', padx=10)
        ttk.Label(yolo_frame, text="Tamanho da imagem enviada para análise. Ideal: 0.5", style="Help.TLabel").pack(anchor='w', padx=10)

        # Checkboxes para filtro de classes YOLO
        class_filter_frame = ttk.LabelFrame(yolo_frame, text=" Filtrar Classes YOLO ", padding=5)
        class_filter_frame.pack(fill='x', padx=5, pady=5)
        
        common_yolo_classes = ["person", "car", "truck", "motorcycle", "dog", "cat", "bird", "bicycle", "bus"]
        self.yolo_class_vars = {}
        for i, cls in enumerate(common_yolo_classes):
            var = tk.BooleanVar(value=(cls in self.config["deteccao"].get("yolo_allowed_classes", [])))
            cb = ttk.Checkbutton(class_filter_frame, text=cls.capitalize(), variable=var)
            cb.grid(row=i // 3, column=i % 3, sticky='w', padx=5, pady=2)
            self.yolo_class_vars[cls] = var

        # --- TAB TELEGRAM (BOTS UNIFICADOS) ---
        canvas = tk.Canvas(tab_tg_all)
        scrollbar = ttk.Scrollbar(tab_tg_all, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_frame = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_frame, width=e.width))
        canvas.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")

        def create_bot_settings(parent, bot_key, title, bot_vars):
            frame = ttk.LabelFrame(parent, text=title, padding=5)
            frame.pack(fill='x', padx=5, pady=5)
            add_module_option(frame, bot_vars['active'], "Ativar este Bot", "")
            ttk.Label(frame, text="Token:").pack(anchor='w', padx=10)
            et = ttk.Entry(frame); et.insert(0, self.config[bot_key].get("token", "")); et.pack(fill='x', padx=10)
            ttk.Label(frame, text="Chat ID:").pack(anchor='w', padx=10)
            ec = ttk.Entry(frame); ec.insert(0, self.config[bot_key].get("chat_id", "")); ec.pack(fill='x', padx=10)
            add_module_option(frame, bot_vars['risco'], "Alertar Risco", "")
            add_module_option(frame, bot_vars['geral'], "Alertar Geral", "")
            add_module_option(frame, bot_vars['crop'], "Enviar Crop", "")
            add_module_option(frame, bot_vars['silent'], "Modo Silencioso", "")
            ttk.Label(frame, text="Slot:").pack(anchor='w', padx=10)
            cs = ttk.Combobox(frame, values=["1", "2", "3", "4"], state="readonly", width=5)
            cs.set(str(self.config[bot_key].get("slot", 1))); cs.pack(anchor='w', padx=10)
            si = tk.Scale(frame, from_=5, to=1800, orient="horizontal", label="Intervalo Mínimo de Envio (s)")
            si.set(self.config[bot_key].get("intervalo_envio", 60)); si.pack(fill='x', padx=10)
            ttk.Label(frame, text="Tempo mínimo entre envios de alertas para este bot. Ideal: 60s para evitar spam.", style="Help.TLabel").pack(anchor='w', padx=10)
            return et, ec, cs, si

        self.var_tg1 = tk.BooleanVar(value=self.config["telegram"].get("ativo"))
        self.var_tg1_risco = tk.BooleanVar(value=self.config["telegram"].get("alertar_risco", True))
        self.var_tg1_geral = tk.BooleanVar(value=self.config["telegram"].get("alertar_geral", True))
        self.var_tg1_crop = tk.BooleanVar(value=self.config["telegram"].get("enviar_crop_roi", True))
        self.var_tg1_silent = tk.BooleanVar(value=self.config["telegram"].get("silent_mode", False))
        self.entry_tg1_token, self.entry_tg1_chatid, self.combo_tg1_slot, self.sld_tg1_interval = create_bot_settings(
            self.scrollable_frame, "telegram", "BOT MESTRE", 
            {'active': self.var_tg1, 'risco': self.var_tg1_risco, 'geral': self.var_tg1_geral, 'crop': self.var_tg1_crop, 'silent': self.var_tg1_silent}
        )

        self.var_tg2 = tk.BooleanVar(value=self.config["telegram_bot2"].get("ativo"))
        self.var_tg2_risco = tk.BooleanVar(value=self.config["telegram_bot2"].get("alertar_risco", True))
        self.var_tg2_geral = tk.BooleanVar(value=self.config["telegram_bot2"].get("alertar_geral", True))
        self.var_tg2_crop = tk.BooleanVar(value=self.config["telegram_bot2"].get("enviar_crop_roi", True))
        self.var_tg2_silent = tk.BooleanVar(value=self.config["telegram_bot2"].get("silent_mode", False))
        self.entry_tg2_token, self.entry_tg2_chatid, self.combo_tg2_slot, self.sld_tg2_interval = create_bot_settings(
            self.scrollable_frame, "telegram_bot2", "BOT AUXILIAR", 
            {'active': self.var_tg2, 'risco': self.var_tg2_risco, 'geral': self.var_tg2_geral, 'crop': self.var_tg2_crop, 'silent': self.var_tg2_silent}
        )

        # --- TAB ZONAS & SISTEMA ---
        win_frame = ttk.LabelFrame(tab_sys, text=" Janela & Foco ", padding=5)
        win_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(win_frame, text="Título da Janela:").pack(anchor='w', padx=10)
        self.entry_win_title = ttk.Entry(win_frame)
        self.entry_win_title.insert(0, self.config["deteccao"].get("titulo_janela", "")); self.entry_win_title.pack(fill='x', padx=10, pady=2)
        ttk.Button(win_frame, text="📺 SELECIONAR JANELA E ROI", command=self.abrir_selecao_window).pack(fill='x', padx=10, pady=5)
        ttk.Button(win_frame, text="📐 DESENHAR ÁREAS DE RISCO", command=self.abrir_selecao_risco).pack(fill='x', padx=10, pady=5)
        self.sld_display_scale = tk.Scale(win_frame, from_=0.1, to=1.5, resolution=0.05, orient="horizontal", label="Escala Preview")
        self.sld_display_scale.set(self.config["deteccao"].get("display_resize_scale", 0.7)); self.sld_display_scale.pack(fill='x', padx=10)
        ttk.Label(win_frame, text="Tamanho da janela de pré-visualização. Ideal: 0.7", style="Help.TLabel").pack(anchor='w', padx=10)

        storage_frame = ttk.LabelFrame(tab_sys, text=" Armazenamento ", padding=5)
        storage_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(storage_frame, text="Pasta de Gravações:").pack(anchor='w', padx=10)
        pf = ttk.Frame(storage_frame); pf.pack(fill='x', padx=10)
        self.entry_path = ttk.Entry(pf); self.entry_path.insert(0, self.config["arquivos"].get("pasta_gravacoes", "")); self.entry_path.pack(side='left', fill='x', expand=True)
        ttk.Button(pf, text="...", width=3, command=self.selecionar_pasta).pack(side='right', padx=2)
        self.sld_cleanup = tk.Scale(storage_frame, from_=0, to=90, orient="horizontal", label="Limpeza (Dias - 0 desativa)")
        self.sld_cleanup.set(self.config["arquivos"].get("limpeza_dias", 0)); self.sld_cleanup.pack(fill='x', padx=10)
        ttk.Label(storage_frame, text="Apaga vídeos antigos após X dias. 0 desativa.", style="Help.TLabel").pack(anchor='w', padx=10)

        sys_frame = ttk.LabelFrame(tab_sys, text=" Sistema ", padding=5)
        sys_frame.pack(fill='x', padx=10, pady=5)
        self.var_usar_risco = tk.BooleanVar(value=self.config["deteccao"].get("usar_areas_risco", True))
        add_module_option(sys_frame, self.var_usar_risco, "Monitorar Áreas de Risco", "")
        self.var_modo_teste = tk.BooleanVar(value=self.config["deteccao"].get("modo_teste", False))
        add_module_option(sys_frame, self.var_modo_teste, "Modo Teste (Captura Full)", "")

if __name__ == "__main__":
    root = tk.Tk()
    app = ConfigApp(root)
    root.mainloop()