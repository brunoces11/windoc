# AGENTS.md - Diretrizes e Regras de Negócio do Projeto WinDoc

## 1. Visão e Motivação do Projeto

O **WinDoc** nasce da jornada de personalização do **Omarchy Linux** (Arch Linux + Hyprland + Quickshell) com um objetivo audacioso e claro:
> **Criar uma experiência com cara de Windows, jeito de Windows e comportamento de Windows, construída sobre a base do Omarchy — um "Windows slim e turbinado".**

Esta iniciativa visa permitir que o usuário desfrute do ecossistema leve, rápido e moderno do Omarchy sem abrir mão dos paradigmas de usabilidade, produtividade e ergonomia consagrados do Windows (barra de tarefas na base, atalhos universais, gestão de janelas, popups de calendário/relógio e fluxo intuitivo).

O objetivo final é **encapsular essa jornada em um projeto coeso, versionado e distribuível**, para que no futuro qualquer membro da comunidade possa transformar sua instalação do Omarchy em uma experiência Windows com facilidade e confiabilidade.

---

## 2. Estrutura Centralizada de Arquivos e Symlinks

O projeto adota uma arquitetura onde **todos os arquivos de configuração do sistema são centralizados nesta pasta única** (`~/Desktop/windoc/`) e vinculados aos seus destinos reais no sistema através de **Links Simbólicos nativos do Linux (*Symlinks*)**:

```text
~/Desktop/windoc/                         <-- RAIZ DO REPOSITÓRIO GIT
├── dock/                                 <-- Plugin Quickshell da Dock (QML, JS, manifest)
│                                             Symlink em: ~/.config/omarchy/plugins/rosakodu.dock
│                                             Symlink em: ~/.config/omarchy/plugins/brunoma.windoc
├── hyprland/                             <-- Janelas, atalhos, monitores e comportamento
│                                             Symlink em: ~/.config/hypr/
├── shell/                                <-- Configurações da barra superior e da dock
│                                             Symlink em: ~/.config/omarchy/
├── terminal/                             <-- Configurações do emulador de terminal Kitty
│                                             Symlink em: ~/.config/kitty/
├── config-sistema.txt                    <-- LOG HISTÓRICO E INCREMENTAL DE MODIFICAÇÕES
├── sync-symlinks.sh                      <-- Script utilitário para validar e restaurar links
├── Agents.md                             <-- Este arquivo de regras obrigatórias para agentes
├── README.md                             <-- Documentação do projeto
└── .gitignore                            <-- Filtros para manter o repositório limpo
```

---

## 3. Regras Mandatórias para Agentes de IA

Todo agente de IA (Antigravity, Codex ou similar) que atue neste repositório **DEVE** seguir rigorosamente as seguintes diretivas antes de executar qualquer intervenção:

### REGRA 1: Verificação Prévia de Symlink (OBRIGATÓRIO)
> **Toda vez que o usuário solicitar qualquer customização de interface, terminal, tema ou sistema cujo arquivo alvo ainda NÃO resida dentro da estrutura deste projeto (`~/Desktop/windoc/`), o agente DEVE, ANTES DE EDITAR O ARQUIVO:**
1. Mover o arquivo de configuração original para a subpasta temática correspondente dentro de `~/Desktop/windoc/` (ex: `hyprland/`, `shell/`, `dock/`, `terminal/`, etc.).
2. Criar imediatamente o link simbólico (`ln -sfn`) apontando do caminho esperado pelo sistema (ex: `~/.config/...`) para o arquivo dentro do projeto.
3. Adicionar o novo link ao script `sync-symlinks.sh`.
4. Somente após a criação e validação do symlink, realizar a edição solicitada diretamente no arquivo dentro do projeto.

### REGRA 2: Registro Incremental em `config-sistema.txt` (OBRIGATÓRIO)
> **Toda nova solicitação, modificação, ajuste ou adição realizada a pedido do usuário DEVE ser registrada de forma incremental no arquivo `config-sistema.txt`, localizado na raiz deste projeto.**
* O registro deve conter:
  * Data e identificação da mudança.
  * O arquivo afetado.
  * O comportamento anterior vs. o novo comportamento implementado.
  * O estado atual (validado, funcional ou pendente).
* Não registrar senhas, tokens ou segredos.

### REGRA 3: Versionamento Ativo e Commits Semânticos
* Todas as edições feitas na pasta são detectadas pelo Git instantaneamente.
* Concluída e testada uma alteração solicitada pelo usuário, o agente deve propor/efetuar o commit semântico (ex: `feat: ...`, `fix: ...`, `style: ...`) e o push para o repositório remoto oficial `brunoces11/windoc`.

### REGRA 4: Hot-Reload e Validação no Omarchy/Hyprland
* Ao alterar configurações do Hyprland: validar sempre com `hyprctl reload` e verificar se há erros com `hyprctl configerrors`.
* Ao alterar componentes QML/JS da Dock ou `shell.json`: o Quickshell atualiza em tempo real; caso necessário, forçar atualização com `omarchy restart shell` ou `omarchy refresh shell`.
