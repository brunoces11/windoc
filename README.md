# WinDoc: The Windows Experience for Omarchy Linux

O **WinDoc** é um projeto de personalização que transforma o **Omarchy Linux** (Arch Linux + Hyprland + Quickshell) em um ambiente com a usabilidade, atalhos e ergonomia do Windows — mantendo toda a velocidade, fluidez e poder do ecossistema Arch/Wayland.

Um "Windows slim e turbinado", construído sobre o Omarchy.

---

## 🚀 O que está incluído

* **`dock/`**: Plugin de barra de tarefas / dock nativo do Omarchy em Quickshell (QML + JavaScript), com suporte a:
  * Agrupamento e alternância de janelas
  * Aplicativos fixados
  * Pop-up integrado de calendário e relógio estilo Windows
* **`hyprland/`**: Configurações de compositor Hyprland:
  * Atalhos universais familiares (`bindings.lua` — Win+V, Win+H, Win+Tab, atalhos de gerenciamento de janelas)
  * Visual e ergonomia de janelas (`looknfeel.lua` — cantos, gaps, comportamento de divisão)
  * Configuração de monitores (`monitors.lua`), teclado ABNT2 (`input.lua`) e ociosidade (`hypridle.conf`)
* **`shell/`**: Definições da barra e widgets do Omarchy (`shell.json`, `dock-settings.json`, `dock-pinned.json`)
* **`terminal/`**: Configurações do emulador Kitty (`kitty.conf`) com atalhos de área de transferência (Ctrl+C / Ctrl+V nativos)
* **`config-sistema.txt`**: Inventário e histórico contínuo de todas as modificações realizadas no sistema

---

## Próxima evolução: System Icon Tray

Planejamento consolidado em 14/10/2026; implementação pendente. Consulte o
[plano de implementação](system_icon_tray_plan.md), referência única de escopo,
estado atual e divisão proposta.

A bandeja reunirá os widgets escolhidos junto ao relógio: checkbox marcado fixa
na barra, desmarcado mantém no pop-up de até cinco ícones por linha. Uma engrenagem
abrirá as preferências. A migração será gradual; mostrar a área de trabalho será
uma entrega adicional com mecanismo próprio a validar.

A sequência proposta é **base e preferências → bandeja com piloto → painel de
configuração → migração dos demais widgets → mostrar área de trabalho**. Cada
entrega será verificável sem depender da próxima para funcionar. O detalhamento
das etapas fica para a próxima interação.

---

## 🛠️ Arquitetura por Links Simbólicos (Symlinks)

Para que a edição centralizada nesta pasta reflita instantaneamente no sistema operacional sem necessidade de cópias manuais, os arquivos originais em `~/.config/` apontam para este repositório através de symlinks.

Para verificar ou restaurar todos os links a qualquer momento:
```bash
./sync-symlinks.sh
```

---

## 🤖 Diretrizes para Agentes de IA

Consulte o arquivo [`AGENTS.md`](AGENTS.md) para as regras de negócio mandatórias sobre adição de novos arquivos ao projeto, criação prévia de symlinks e registro incremental em `config-sistema.txt`.
