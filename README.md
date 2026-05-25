# security-system-cameras
security system for 4 cameras
()
<!-- CONFIGURAÇÃO -->
<!-- 
cols = quantidade de colunas
size = largura das imagens
gap = espaçamento
-->

<div align="center">
<img src="imagens/Sem título.png" width="220">
<table>
<tr>

<td><img src="imagens/Sem título.png" width="220"></td>
<td><img src="imagens/Captura de tela 2026-05-25 120035.png" width="220"></td>
<td><img src="imagens/Captura de tela 2026-05-25 120045.png" width="220"></td>
<td><img src="imagens/Captura de tela 2026-05-25 120056.png" width="220"></td>

</tr>

<tr>

<td><img src="imagens/Captura de tela 2026-05-25 120104.png" width="220"></td>
<td><img src="imagens/Captura de tela 2026-05-25 120112.png" width="220"></td>

</tr>
</table>

</div>
=========================================================
SISTEMA DE SEGURANÇA V7 - DOCUMENTAÇÃO TÉCNICA
=========================================================

RESUMO DO APLICATIVO:
Este sistema é uma suíte avançada de monitoramento de vídeo baseada em Visão Computacional e Inteligência Artificial. Ele foi projetado para capturar janelas específicas de softwares de câmeras (como Yoosee, NVRs, etc.), processar o movimento em tempo real, identificar objetos críticos e enviar alertas inteligentes.

PRINCIPAIS FUNCIONALIDADES:

1. Captura Inteligente de Janela:
   - Monitora janelas específicas pelo título, permitindo que o sistema funcione sem depender de uma webcam física, capturando diretamente a interface de outros softwares.
   - Suporte a ROI (Region of Interest): Permite focar a análise apenas em uma área específica da imagem.

2. Detecção de Movimento Evoluída:
   - Algoritmo de subtração de fundo para detectar mudanças de pixels.
   - Filtros de ruído (dilação e área mínima) para evitar alarmes falsos com pequenos animais ou chuva.
   - Configuração de sensibilidade (Threshold) ajustável via interface.

3. Zonas de Risco (Polígonos):
   - Permite ao usuário desenhar áreas personalizadas na tela.
   - Detecção diferenciada: O sistema diferencia movimento "geral" de invasões em "áreas de risco".

4. Inteligência Artificial (YOLOv8):
   - Reconhecimento de Objetos: Identifica pessoas, carros, motos e outros.
   - Detecção de Fogo e Fumaça: Módulo especializado para identificar princípios de incêndio.
   - Tracking: Acompanha os objetos detectados entre os quadros.

5. Integração com LLM (IA de Visão Local):
   - Conexão com servidores locais (como LM Studio).
   - Ao detectar um evento, o sistema envia a imagem para uma IA que descreve detalhadamente o que está acontecendo (Ex: "Um homem de camisa azul está tentando abrir o portão").

6. Sistema de Gravação Automatizado:
   - Gravação disparada por movimento com tempo de persistência configurável.
   - Suporte a formatos MP4 e AVI com escolha de codecs (H.264/AVC1).
   - Opção de gravar o vídeo "limpo" ou com os desenhos da IA (overlays).

7. Alertas via Telegram:
   - Suporte a múltiplos Bots (Principal e Auxiliar).
   - Envio de fotos com legendas geradas pela IA.
   - Função "Crop": Envia apenas o quadrante onde o movimento foi detectado para facilitar a visualização rápida no celular.

8. Interface de Configuração (GUI):
   - Painel completo em Tkinter para ajuste de todos os parâmetros sem precisar editar o código.
   - Telemetria em tempo real: Monitoramento de uso de CPU, RAM, FPS e contagem de pixels de movimento.

9. Manutenção Automática:
   - Limpeza automática de arquivos antigos (vídeos e logs) após um número de dias definido pelo usuário.

COMO USAR:
1. Execute o 'config_gui.py' para ajustar as configurações e selecionar a janela da câmera.
2. Desenhe as áreas de risco se necessário.
3. Ative o monitoramento.
4. Os vídeos serão salvos na pasta 'gravacoes' e os alertas enviados para os Chat IDs configurados.

=========================================================
Desenvolvido com Python, OpenCV e Ultralytics.
=========================================================





=========================================================================
V7 SECURITY SYSTEM - TECHNICAL DOCUMENTATION
=========================================================================

APP SUMMARY:
This system is an advanced video monitoring suite based on Computer Vision and Artificial Intelligence. It is designed to capture specific windows from camera software (such as Yoosee, NVRs, etc.), process movement in real time, identify critical objects, and send smart alerts.

MAIN FEATURES:

1. Smart Window Capture: 
- Monitors specific windows by title, allowing the system to work without relying on a physical webcam, directly capturing the interface of other software. 
- ROI (Region of Interest) support: Allows you to focus the analysis only on a specific area of ​​the image.

2. Evolved Motion Detection: 
- Background subtraction algorithm to detect pixel changes. 
- Noise filters (dilation and minimum area) to avoid false alarms with small animals or rain. 
- Sensitivity setting (Threshold) adjustable via interface.

3. Risk Zones (Polygons): 
- Allows the user to draw custom areas on the screen. 
- Differentiated detection: The system differentiates between "general" movement and invasions in "risk areas".

4. Artificial Intelligence (YOLOv8): 
- Object Recognition: Identifies people, cars, motorcycles and others. 
- Fire and Smoke Detection: Specialized module to identify fire principles. 
- Tracking: Tracks detected objects between frames.

5. Integration with LLM (Local Vision AI): 
- Connection to local servers (such as LM Studio). 
- When detecting an event, the system sends the image to an AI that describes in detail what is happening (Ex: "A man in a blue shirt is trying to open the gate").

6. Automated Recording System: 
- Motion-triggered recording with configurable persistence time. 
- Support for MP4 and AVI formats with choice of codecs (H.264/AVC1). 
- Option to record the video "clean" or with AI drawings (overlays).

7. Alerts via Telegram: 
- Support for multiple Bots (Main and Auxiliary). 
- Sending photos with AI-generated captions. 
- "Crop" function: Sends only the quadrant where the movement was detected to facilitate quick viewing on the cell phone.

8. Configuration Interface (GUI): 
- Complete panel in Tkinter to adjust all parameters without having to edit the code. 
- Real-time telemetry: Monitoring CPU usage, RAM, FPS and motion pixel count.

9. Automatic Maintenance: 
- Automatic cleaning of old files (videos and logs) after a user-defined number of days.

HOW TO USE:
1. Run 'config_gui.py' to adjust settings and select the camera window.
2. Draw risk areas if necessary.
3. Enable monitoring.
4. The videos will be saved in the 'recordings' folder and alerts sent to the configured Chat IDs.

=========================================================================
Developed with Python, OpenCV and Ultralytics.
=========================================================================
