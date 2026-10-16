# Persistência do Workspace 1

`WORKSPACE1.py` acompanha somente o Workspace 1. Ele usa o IPC do Hyprland para
localizar as janelas e a sessão nativa do Kitty para registrar abas, divisões,
diretórios, foco e programas em primeiro plano. O estado e os arquivos `.session`
ficam em `ESTADO_LOCAL/`, com permissão privada e exclusão explícita do Git.

## IDs de sessão dos agentes

O estado guarda o identificador único da conversa por painel, sem depender do
título visível:

- Codex: correlaciona o evento de inicialização do processo TUI ao `thread_id`
  registrado pelo app-server local. A correlação só é aceita se houver um único
  ID no intervalo estreito de 250 ms; mudanças de esquema ou ambiguidade deixam
  o painel em shell, em vez de retomar outra conversa. O protocolo oficial do
  app-server usa o ID da thread para retomar uma conversa.
- Antigravity: lê o ID do arquivo de presença/conversa ou o ID recebido pelo
  callback nativo do título. Para sessões antigas que ainda não acionaram esse
  callback, aceita somente um título exato que corresponda a um único ID no
  banco local; essa associação é usada apenas para obter e guardar o ID. O
  registro é vinculado ao PID e ao horário de início do processo, e nunca usa
  o título como chave de restauração. Se não houver ID comprovado, a retomada
  fica em shell até que o callback ou outro canal nativo o forneça.
- Claude Code: lê o ID do transcript JSONL aberto pelo processo.

Na restauração, o Kitty mantém o layout nativo e o comando do agente é trocado
por uma retomada explícita pelo ID (`codex resume`, `agy --conversation` ou
`claude --resume`). Flags que desativam confirmações de segurança não são
reaplicadas automaticamente. Se um ID não puder ser identificado, o agente não
é iniciado numa conversa arbitrária; a aba volta ao shell e o estado indica a
lacuna.

Para integrar outro agente, adicione ao registro de adaptadores em
`WORKSPACE1.py` a identificação do processo, a leitura do ID ativo e o comando
oficial para retomar por ID. O adaptador precisa falhar fechado quando não puder
provar a associação entre processo e sessão.

## Comandos

- `python3 WORKSPACE1.py status`: mostra contagens sem imprimir títulos ou IDs.
- `python3 WORKSPACE1.py snapshot`: atualiza o estado manualmente.
- `python3 WORKSPACE1.py restore`: restaura uma captura local.
- `python3 WORKSPACE1.py login`: restaura uma captura de um boot anterior e
  continua monitorando o workspace a cada oito segundos.

O monitor preserva o último estado não vazio por 60 segundos após o workspace
ficar vazio, evitando que o encerramento da sessão substitua a captura por uma
lista vazia. Aplicações gráficas fora do Kitty são inventariadas; a restauração
automática inicial cobre Chromium, Sublime Text e Nautilus quando instalados.
O conteúdo interno de cada aplicativo depende da API própria dele.
