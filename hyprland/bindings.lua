-- Keep only your personal keybinding overrides here. Add new bindings or
-- unbind defaults before replacing them.

-- See current bindings and descriptions:
--   omarchy menu keybindings --print

-- To disable every Omarchy default binding, set this in
-- ~/.config/hypr/hyprland.lua before require("default.hypr.omarchy"), then add
-- only the bindings you want below:
--   omarchy_default_bindings = false

-- To disable all preinstalled app/webapp bindings, set:
--   omarchy_preinstalled_bindings = false

-- Add a new binding.
-- o.bind("SUPER + SHIFT + R", "SSH", "alacritty -e ssh your-server")

-- Change an existing binding by unbinding it first, then binding the key again.
-- This example changes SUPER+SPACE from the launcher to the Omarchy root menu.
-- hl.unbind("SUPER + SPACE")
-- o.bind("SUPER + SPACE", "Omarchy menu", "omarchy-menu toggle root")

-- Disable a default binding without replacing it.
-- hl.unbind("SUPER + SHIFT + B")

-- Logitech MX Keys examples:
-- o.bind("SUPER + SHIFT + S", nil, "omarchy-capture-screenshot")
-- o.bind("SUPER + H", nil, "voxtype record toggle")
o.bind("SCROLL_LOCK", "Voxtype: start/stop recording", "voxtype record toggle")
o.bind("PAUSE", "WinDoc TTS: Ler seleção / Interromper", "windoc-tts")

-- Gerenciador de tarefas / Processos (equivalente ao Ctrl+Shift+Esc do Windows)
o.bind("CTRL + SHIFT + Escape", "Gerenciador de Tarefas", { tui = "btop" })

-- Amberol media controls and system-wide audio volume.
o.bind("SUPER + F1", "Amberol: play/pause", "gdbus call --session --dest org.mpris.MediaPlayer2.io.bassi.Amberol --object-path /org/mpris/MediaPlayer2 --method org.mpris.MediaPlayer2.Player.PlayPause")
o.bind("SUPER + F2", "Diminuir volume", "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-")
o.bind("SUPER + F3", "Aumentar volume", "wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+")
o.bind("SUPER + F4", "Alternar mudo", "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")
o.bind("SUPER + F6", "Amberol: faixa anterior", "gdbus call --session --dest org.mpris.MediaPlayer2.io.bassi.Amberol --object-path /org/mpris/MediaPlayer2 --method org.mpris.MediaPlayer2.Player.Previous")
o.bind("SUPER + F8", "Amberol: próxima faixa", "gdbus call --session --dest org.mpris.MediaPlayer2.io.bassi.Amberol --object-path /org/mpris/MediaPlayer2 --method org.mpris.MediaPlayer2.Player.Next")
-- o.bind("SUPER + PERIOD", nil, "omarchy-shell shell toggle omarchy.emojis")

-- Use Dolphin instead of the default Nautilus file manager.
hl.unbind("SUPER + SHIFT + F")
hl.unbind("SUPER + ALT + SHIFT + F")
o.bind("SUPER + SHIFT + F", "File manager (Dolphin)", "setsid uwsm-app -- dolphin")
o.bind("SUPER + ALT + SHIFT + F", "File manager (Dolphin, cwd)", "setsid uwsm-app -- dolphin \"$(omarchy-cmd-terminal-cwd)\"")
o.bind("SUPER + V", "Pre-select Vertical Split (Side-by-side)", "hyprctl dispatch layoutmsg preselect r")
o.bind("SUPER + H", "Pre-select Horizontal Split (Top/Bottom)", "hyprctl dispatch layoutmsg preselect d")

-- Ciclo de três estágios: Grade (0) -> Maximizado (1) -> Fullscreen total (2) -> Grade (0)
-- Maximizado preserva as barras/dock inferior e as abas de grupo do Hyprland.
local function cycle_fullscreen()
  local w = hl.get_active_window()
  if not w then
    return
  end
  local fs = w.fullscreen
  if fs == 0 then
    hl.dispatch(hl.dsp.window.fullscreen({ mode = "maximized" }))
  elseif fs == 1 then
    hl.dispatch(hl.dsp.window.fullscreen({ mode = "fullscreen" }))
  else
    hl.dispatch(hl.dsp.window.fullscreen({ mode = "fullscreen" }))
  end
end

hl.unbind("SUPER + F")
o.bind("SUPER + F", "Alternar janela: Grade / Maximizar / Fullscreen", cycle_fullscreen)

-- Group tabs: replace workspace cycling and group focus shortcuts.
-- Workspace cycling remains available on SUPER + mouse wheel / number keys.
hl.unbind("SUPER + TAB")
hl.unbind("SUPER + SHIFT + TAB")
hl.unbind("SUPER + CTRL + LEFT")
hl.unbind("SUPER + CTRL + RIGHT")
o.bind("SUPER + TAB", "Proxima aba do grupo", hl.dsp.group.next())
o.bind("SUPER + SHIFT + TAB", "Aba anterior do grupo", hl.dsp.group.prev())
o.bind("SUPER + CTRL + LEFT", "Mover aba para esquerda no grupo", hl.dsp.group.move_window({ forward = false }))
o.bind("SUPER + CTRL + RIGHT", "Mover aba para direita no grupo", hl.dsp.group.move_window({ forward = true }))
-- Keep native shortcuts: SUPER+G toggles grouping, SUPER+ALT+G detaches,
-- SUPER+ALT+arrows moves into a neighboring group, SUPER+W closes one window.
-- SUPER+RETURN opens a terminal in the focused unlocked group (auto_group).
