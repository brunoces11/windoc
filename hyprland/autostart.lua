-- Extra autostart processes.
-- o.launch_on_start("my-service")

-- Importa o IPC da sessao atual antes de iniciar o monitor supervisionado.
o.launch_on_start("sh -lc 'systemctl --user import-environment HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY XDG_RUNTIME_DIR && systemctl --user start windoc-workspace1.service'")

-- Inicia apenas o serviço do Amberol; o build customizado carrega a fila sem apresentar a janela.
o.launch_on_start("amberol --gapplication-service")
