-- Extra autostart processes.
-- o.launch_on_start("my-service")

-- Salva e restaura localmente as janelas e sessões do Workspace 1.
o.launch_on_start("sh -lc 'sleep 4; exec python3 \"$HOME/Desktop/windoc/PERSISTIR_WORKSPACE/WORKSPACE1.py\" login'")
