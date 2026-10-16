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

## System Icon Tray

A bandeja fica na barra inferior, no espaço reservado à direita junto ao relógio.
Ela também reúne Screen Recording, lembretes, Dictation/Voxtype, Stay Awake,
Allow Notifications e Daylight/Night Light. Esses seis controles deixam a barra
superior e aparecem fixados inicialmente na barra inferior; cada ação preserva
o comportamento do indicador original. O modal de configurações permite
fixar/desafixar qualquer um, e os desfixados ficam no overflow (^).
Ela agrupa os widgets de áudio, rede, consumo de agentes, modo de janela, clima e
display. Os itens fixados aparecem na barra; os demais ficam no overflow em grade,
com configurações acessíveis pelo ícone de engrenagem. Os painéis nativos são
abertos a partir da bandeja com sua borda mais próxima alinhada à linha do tooltip
(12 px a partir do topo da dock), como uma expansão visual do próprio tooltip.

O ícone `omarchy.monitor` não deve permanecer na barra superior. A bandeja de
aplicativos de terceiros (`omarchy.tray`) permanece independente. Consulte o
[plano central](system_icon_tray_plan.md) para o estado atualizado e as decisões
de integração.

---

## 🛠️ Arquitetura por Links Simbólicos (Symlinks)

Para que a edição centralizada nesta pasta reflita instantaneamente no sistema operacional sem necessidade de cópias manuais, os arquivos originais em `~/.config/` apontam para este repositório através de symlinks.

Para verificar ou restaurar todos os links a qualquer momento:
```bash
./sync-symlinks.sh
```

### Provisionamento e adoção de novas configurações

`./install.sh` sincroniza os links declarados e instala o comando `windoc` em
`~/.local/bin/`. Para incluir pacotes, declare um pacote Arch por linha em
`pacotes-sistema.txt` e execute `./install.sh --install-packages`.

`windoc adopt CAMINHO` incorpora um arquivo ou diretório que esteja dentro da
pasta pessoal: move-o para `adotados/`, cria o symlink no local original e
registra a relação em `symlinks.tsv`, usada por `sync-symlinks.sh`. A adoção
reconhece arquivos já incorporados sem movê-los novamente. Para arquivos novos,
crie um arquivo vazio e adote antes de escrever sua configuração. A movimentação
automática aceita apenas HOME e não substitui um item já existente no WinDoc.
Plugins e extensões de terceiros ainda precisam ter origem e versão declaradas;
não são baixados automaticamente.

A seção global `WinDocAdoptRule` em `~/.codex/AGENTS.md` instrui o agente a consultar
[WINDOC_ADOPT_RULES.md](WINDOC_ADOPT_RULES.md) e o `AGENTS.md` do projeto antes de
customizar o Linux/Omarchy, mesmo trabalhando fora deste repositório. O agente
verifica/adota os arquivos antes da edição e conclui registro, commit e push após
validar a customização. A regra é acionada pela solicitação ao agente; não há
monitor de arquivos adotando alterações feitas manualmente por outros programas.

---

## 🤖 Diretrizes para Agentes de IA

Consulte o arquivo [`AGENTS.md`](AGENTS.md) para as regras de negócio mandatórias sobre adição de novos arquivos ao projeto, criação prévia de symlinks e registro incremental em `config-sistema.txt`.
