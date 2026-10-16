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
├── DIRETRIZES_DE_DESIGN.txt              <-- CATÁLOGO E PADRÕES DE DESIGN, ESTILOS E ESPAÇAMENTOS
├── sync-symlinks.sh                      <-- Script utilitário para validar e restaurar links
├── AGENTS.md                             <-- Este arquivo de regras obrigatórias para agentes
├── README.md                             <-- Documentação do projeto
└── .gitignore                            <-- Filtros para manter o repositório limpo
```

### 2.1. Origem do código da dock e identidade do WinDoc

- **Projeto original:** Omarchy Dock, de **rosakodu**.
- **Repositório de origem:** https://github.com/rosakodu/omarchy-dock
- **Identificador canônico do plugin:** `rosakodu.dock`; o manifesto local declara versão `1.8.32` e licença MIT.
- **Código customizado usado nesta máquina:** `~/Desktop/windoc/dock/`. O WinDoc incorpora e modifica esse código; não se deve presumir que ele permaneça idêntico ao projeto original ou que a versão do manifesto identifique todas as alterações locais.
- **Vínculos locais:** `~/.config/omarchy/plugins/rosakodu.dock` e `~/.config/omarchy/plugins/brunoma.windoc` resolvem para a mesma pasta `dock/`. `brunoma.windoc` é um caminho alternativo local; o manifesto continua declarando `rosakodu.dock`. Não habilitar os dois caminhos como se fossem implementações independentes.
- **Pontos de entrada:** `dock/DockPanel.qml` implementa o serviço e a barra inferior; `dock/BarWidget.qml` implementa o botão de configuração da dock na barra superior.
- **Preservação da origem:** manter o crédito e a licença MIT de rosakodu ao redistribuir o código derivado. Atualizações do projeto original exigem revisão das customizações locais.
- **Limite atual para novas integrações:** o carregamento genérico de widgets existe, mas os slots comuns escondem o componente original e exibem um ícone de tamanho fixo. Uma cápsula interativa de largura variável exige adaptação do host; um symlink sozinho não implementa esse suporte.
- **Investigação Amberol Deskband:** consultar `RELATORIO_AMBEROL_DESKBAND.md` para o fluxo de integração, versões observadas, correções propostas e verificações ainda pendentes.

---

## 3. Regras Mandatórias para Agentes de IA

Todo agente de IA (Antigravity, Codex ou similar) que atue neste repositório **DEVE** seguir rigorosamente as seguintes diretivas antes de executar qualquer intervenção:

### REGRA 1: WinDocAdoptRule — incorporação antes de customizar (OBRIGATÓRIO)
> **Em toda solicitação autorizada de customização do Linux, Omarchy, Hyprland,
> interface, terminal, aplicativos, plugins ou serviços, consultar primeiro
> [`WINDOC_ADOPT_RULES.md`](WINDOC_ADOPT_RULES.md).**
1. Verificar se cada arquivo afetado já está no WinDoc ou se o caminho do sistema
   resolve para ele. Se já estiver incorporado, validar o vínculo existente e
   editar no projeto, sem mover novamente nem criar outro link/registro.
2. Caso contrário, executar `windoc adopt CAMINHO` antes de editar. O arquivo real
   fica em `adotados/`, o symlink fica no sistema e o vínculo entra em `symlinks.tsv`,
   que já é lido por `sync-symlinks.sh`. Para arquivos novos, criar um arquivo vazio,
   adotar e validar antes de escrever a configuração.
3. Para arquivos fora de HOME, arquivos com segredos ou componentes incompatíveis
   com symlinks, seguir o tratamento específico do protocolo. Não forçar vínculos.
4. Após a customização, validar, registrar, commitar e enviar conforme as regras
   seguintes. Não exigir que o usuário peça a adoção ou o versionamento novamente.
Pedidos somente de análise ou parecer não acionam mudanças reais.

### REGRA 2: Registro Incremental em `config-sistema.txt` (OBRIGATÓRIO)
> **Toda nova solicitação, modificação, ajuste ou adição realizada a pedido do usuário DEVE ser registrada de forma incremental no arquivo `config-sistema.txt`, localizado na raiz deste projeto.**
* O registro deve conter:
  * Data e identificação da mudança.
  * O arquivo afetado.
  * O comportamento anterior vs. o novo comportamento implementado.
  * O estado atual (validado, funcional ou pendente).
* Não registrar senhas, tokens ou segredos.

### REGRA 3: Auto-Commit & Auto-Push Obrigatório ao Final de Cada Tarefa (Trigger Automático)
> **MUITO IMPORTANTE:** Toda vez que o agente realizar qualquer modificação, ajuste ou adição de arquivos na estrutura deste projeto (`~/Desktop/windoc/`), o agente DEVE, AUTOMATICAMENTE e OBRIGATORIAMENTE antes de finalizar a resposta ao usuário:
1. Validar a integridade técnica da alteração (sintaxe, `hyprctl reload`, etc.).
2. Registrar a mudança no histórico incremental do `config-sistema.txt`.
3. Adicionar as alterações ao stage (`git add .`).
4. Criar um commit com uma mensagem personalizada, clara e informativa, preferencialmente em português e sem jargão técnico. A mensagem deve caber em duas linhas: a primeira resume a mudança percebida pelo usuário; a segunda descreve, de forma direta, as funcionalidades ou comportamentos modificados. Evitar mensagens genéricas e incluir todas as mudanças funcionais relevantes daquela edição.
5. Executar imediatamente o envio ao GitHub (`git push origin main`).
6. Na resposta final, informar o identificador do commit e, logo em seguida, reproduzir exatamente a mensagem personalizada criada para ele, nas mesmas duas linhas. A mensagem deve deixar claro o que foi alterado sem depender de detalhes técnicos. Depois, confirmar se o push foi concluído.
*O usuário NÃO precisa pedir para commitar nem para dar push: isso é um trigger automático mandatório ao final de qualquer modificação.*

### REGRA 4: Hot-Reload e Validação no Omarchy/Hyprland
* Ao alterar configurações do Hyprland: validar sempre com `hyprctl reload` e verificar se há erros com `hyprctl configerrors`.
* Ao alterar componentes QML/JS da Dock ou `shell.json`: verificar o carregamento e os logs do Quickshell/Omarchy Shell; o shell suporta atualização em tempo real. Se necessário, reiniciar com `omarchy restart shell`.
* `omarchy refresh shell` restaura configurações padrão e NÃO deve ser usado como simples recarregamento.
* Alterações exclusivamente documentais exigem revisão de conteúdo, referências e diff; não exigem reiniciar o shell nem recarregar o Hyprland.

### REGRA 5: Não Duplicação de Pastas e Diretórios (OBRIGATÓRIO)
> **MUITO IMPORTANTE:** Antes de criar qualquer pasta ou diretório, verifique sempre se já existe uma pasta igual ou equivalente (inclusive variações de maiúsculas/minúsculas) para jamais criar pastas duplicadas ou redundantes.

### REGRA 6: Observância e Registro em `DIRETRIZES_DE_DESIGN.txt` (OBRIGATÓRIO)
> **MUITO IMPORTANTE:** O projeto mantém um catálogo autoritativo de design tokens, medidas, estilos visuais e arquétipos de componentes no arquivo `DIRETRIZES_DE_DESIGN.txt`, localizado na raiz deste projeto.
* **Consulta Obrigatória**: Toda vez que o usuário solicitar uma alteração visual, de layout, de espaçamento ou fizer referência a um padrão registrado (ex: "espaçamento padrão", "janela X", "janela Y"), o agente DEVE consultar `DIRETRIZES_DE_DESIGN.txt` e aplicar rigorosamente os valores e convenções ali estabelecidos.
* **Registro de Novos Padrões e Variantes**: Toda vez que o usuário solicitar uma modificação de design e pedir para registrá-la ou acordar um novo padrão (ex: novas dimensões, regras de janela com cores/outlines/paddings específicos, novas variantes), o agente DEVE documentar e atualizar imediatamente o arquivo `DIRETRIZES_DE_DESIGN.txt`.

### REGRA 7: Padrão Mandatório de Criação e Nomenclatura de Novos Arquivos (OBRIGATÓRIO)
> **MUITO IMPORTANTE:** Toda vez que o usuário solicitar a criação de um novo arquivo, ou o agente identificar a necessidade de criá-lo, devem ser observadas rigorosamente as seguintes diretivas:
1. **Local Padrão (Raiz)**: Caso o usuário não indique expressamente o diretório de destino, o arquivo DEVE ser criado diretamente na raiz do projeto (`~/Desktop/windoc/`).
2. **Nomenclatura em Caixa Alta**: O nome do arquivo deve ser redigido inteiramente em letras MAIÚSCULAS (UPPERCASE).
3. **Separador Obrigatório**: Utilizar exclusivamente o caractere underline (`_`) como separador entre palavras. É proibido o uso de espaços em branco ou hífens (`-`).
4. **Extensão Padrão**: O formato e extensão padrão oficial é `.txt`. Caso aplicável ou justificado pelo contexto, poderá ser `.md`, ou qualquer outra extensão técnica expressamente requisitada pelo usuário (ex: `.json`, `.qml`, `.sh`).
*(Exemplos de conformidade: `DIRETRIZES_DE_DESIGN.txt`, `MAPA_DE_ENTIDADES.txt`, `REGRAS_DE_ESTILO.md`).*

### REGRA 8: Exclusão Mútua e Não Duplicação de Ícones da System Tray (OBRIGATÓRIO)
> **MUITO IMPORTANTE:** É terminantemente proibida a duplicação de ícones na interface: qualquer ícone fixado ou exposto na barra de tarefas (taskbar) deve ser automaticamente omitido do pop-up de overflow (^), exibindo na pop-up exclusivamente os ícones não visíveis na barra, mantendo unicidade funcional e visual absoluta no sistema.

## 4. Status vigente: System Icon Tray

A feature **System Icon Tray** foi planejada, implementada e validada em tempo real com máxima precisão:
- **Cápsula na barra**: Chevron expansível (`^`) + ícones fixados nominais (Network, Audio, etc.).
- **Pop-up em Grid**: Abre acima da bandeja exibindo estritamente os ícones ocultos (não visíveis na barra) + botão de configurações (`⚙`), sem qualquer duplicação.
- **Modal de Configurações**: Janela centralizada com switches/checkboxes reativos para gerenciar os 5 widgets da bandeja (Áudio, Rede, Agentes IA, Clima, Telas/Display) em tempo real.
- **Show Desktop**: Botão retangular no extremo direito acionando alternância limpa no Hyprland (`hl.dsp.workspace.toggle_special`).
- **Estado atual**: Implementado, operacional e validado em runtime. Consulte [`system_icon_tray_plan.md`](system_icon_tray_plan.md) para o histórico das etapas.
