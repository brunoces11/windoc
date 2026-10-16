# Persistência do Workspace 1

`WORKSPACE1.py` acompanha somente o Workspace 1. Ele usa o IPC do Hyprland para
localizar as janelas e a sessão nativa do Kitty para salvar abas, divisões,
diretórios, foco e programas em primeiro plano. O estado e os arquivos `.session`
ficam em `ESTADO_LOCAL/`, com permissão privada e exclusão explícita do Git.

## IDs de sessão dos agentes

O manifesto registra, por janela Hyprland, o processo Kitty e, por aba/painel,
índice, título, ID do painel, diretório, agente, ID da conversa e origem do ID.
Os hooks associam o evento ao painel por `KITTY_PID` e `KITTY_WINDOW_ID`; títulos
não são usados para adivinhar conversas.

- Codex: usa `session_id` do hook oficial `SessionStart`; `UserPromptSubmit`
  marca que houve mensagem do usuário. A leitura dos logs locais continua como
  compatibilidade para sessões que já estavam abertas antes da integração.
- Antigravity: usa `conversationId` de `SessionStart`/`PreInvocation` e o
  `conversation_id` do callback nativo de título; a leitura de arquivos de
  conversa é compatibilidade para sessões antigas.
- Claude Code: usa `session_id` dos hooks oficiais `SessionStart` e
  `UserPromptSubmit`; o transcript aberto é compatibilidade para sessões antigas.

Uma sessão comprovadamente vazia conserva a aba Kitty, mas volta a shell sem
reabrir o agente. Um painel ativo sem ID não é tratado como vazio nem inicia uma
conversa arbitrária. IDs são validados conforme o agente: Codex e Antigravity
usam UUID; Claude Code aceita um identificador opaco seguro.

Na restauração, Kitty mantém a topologia nativa e troca o comando do agente por
uma retomada explícita pelo ID (`codex resume`, `agy --conversation` ou
`claude --resume`). Flags que desativam confirmações de segurança não são
reaplicadas automaticamente.

Para integrar outro agente, adicione a identificação do processo, a leitura do
ID ativo e o comando oficial para retomar por ID. O adaptador precisa falhar
fechado quando não puder provar a associação entre processo e sessão.

## Comandos

- `python3 WORKSPACE1.py status`: mostra contagens sem imprimir títulos ou IDs.
- `python3 WORKSPACE1.py snapshot`: atualiza o estado manualmente.
- `python3 WORKSPACE1.py restore`: restaura uma captura local.
- `python3 WORKSPACE1.py login`: restaura uma captura de um boot anterior e
  continua monitorando o workspace a cada oito segundos.

O monitor preserva o último estado não vazio por 60 segundos após o workspace
ficar vazio. Capturas incompletas são mantidas como diagnóstico separado e não
substituem a última captura completa. Após um boot, a restauração espera pelas
janelas esperadas e IDs de agentes antes de promover uma nova captura. Aplicações
gráficas fora do Kitty são inventariadas; a restauração inicial cobre Chromium,
Sublime Text e Nautilus quando instalados. O conteúdo interno de cada aplicativo
depende da API própria dele.
