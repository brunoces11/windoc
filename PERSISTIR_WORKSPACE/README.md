# Persistência do Workspace 1 por grupo

Um único serviço de usuário, `windoc-workspace1.service`, mantém o mapa estrutural
do Workspace 1 e restaura janelas, grupos, geometria e terminais no próximo login.
O estado local permanece em `ESTADO_LOCAL/`, privado e ignorado pelo Git.

## Atualização leve: 30 segundos e um minuto

- Eventos do socket nativo do Hyprland sinalizam abertura, fechamento, foco,
  agrupamento, tela cheia e outras mudanças disponíveis. Inotify acompanha as
  alterações semânticas dos IDs de conversa registrados pelos hooks.
- O monitor espera **30 segundos de estabilidade observada** antes de consolidar
  uma alteração. Novas mudanças reiniciam a espera; dados ainda diferentes na
  conferência adiam a consolidação por mais 30 segundos.
- Uma reconciliação leve ocorre **a cada 60 segundos**. Ela cobre mudanças sem
  evento completo, incluindo redimensionamentos e alterações internas do Kitty.
  Uma mudança descoberta nessa conferência ainda aguarda 30 segundos: o atraso
  normal nesses casos pode chegar a aproximadamente 90 segundos.
- A consolidação e a reconciliação se aproveitam quando coincidem. Eventos não
  disparam subprocessos imediatamente: o serviço dorme esperando notificações ou
  o próximo prazo. Títulos animados e spinners não reiniciam o relógio.
- Sem alteração real, não regrava o manifesto, os backups ou as sessões nativas.
  A idade mostrada no status indica a última mudança salva, não um heartbeat.

A espera escolhida é intencional: desligar ou sofrer uma falha antes da
consolidação conserva a captura anterior. O monitor não grava o desktop em
encerramento como se todas as janelas tivessem sido fechadas pelo usuário.

## Granularidade

Mudanças externas de posição, tamanho, grupo ou monitor atualizam o mapa Hyprland
sem exportar novamente os terminais. A conferência de um minuto consulta a
estrutura de cada Kitty, mas compara seus dados antes de gerar outro arquivo de
sessão. Só exporta a janela Kitty cuja estrutura, foco interno, diretório,
programa ou conversa realmente mudou. Colunas/linhas causadas pelo tamanho externo
e títulos automáticos não provocam uma exportação nativa por si sós.

A unidade de exportação nativa é uma janela Kitty: o próprio Kitty escreve suas
abas, painéis, layouts e comandos em `.session`. As alterações dos grupos ficam
num manifesto pequeno, gravado atomicamente. Os arquivos de sessão são imutáveis
por conteúdo e compartilhados quando o conteúdo continua igual.

## O que é registrado

- **Janela:** identidade estável, classe, workspace, PID e início do processo,
  coordenadas e tamanho lógicos, flutuação, tela cheia, monitor e foco.
- **Grupo Hyprland:** identidades dos membros em ordem, aba ativa, trava, geometria,
  nome do monitor e algoritmo do layout. Um grupo ocupa uma folha da árvore de tiles.
- **Layout Dwindle:** árvore reconstruída das divisões observadas, orientações e
  proporções horizontais/verticais; geometria normal conhecida antes da tela cheia.
- **Monitor:** nome, descrição, escala, resolução, rotação, posição e área reservada.
  A restauração procura a saída pelo nome e adapta coordenadas à área disponível
  quando o monitor muda. Não força um novo modo de vídeo global.
- **Kitty:** todas as abas e painéis, inclusive shells vazios, layout nativo,
  seleção, diretórios e processos. A sessão original do Kitty preserva os detalhes
  internos; o manifesto permite conferir a estrutura depois de restaurá-la.
- **Agente:** tipo e ID da conversa associados ao painel, com origem da evidência.
  Títulos e recência global não escolhem qual conversa será retomada.

## Sequência de restauração

1. O autostart do Hyprland importa o ambiente IPC e inicia o serviço systemd.
2. Ao detectar um boot novo, preserva uma captura de recuperação e abre os itens
   ausentes de forma independente. Um item desconhecido não bloqueia os demais.
3. As novas janelas começam isoladas e flutuantes, evitando agrupamento automático.
4. A API nativa `Group:add` recompõe cada grupo pelas identidades exatas dos membros,
   na ordem registrada. Não usa aproximação por título ou janela vizinha.
5. Recria as divisões do Dwindle usando preseleção, retorno ao modo tiled e razões
   de divisão nativas. Janelas flutuantes recebem posição e tamanho explícitos.
6. Recupera a aba ativa de cada grupo, trava, tela cheia e foco. Se o layout já
   coincide, uma nova chamada não o desmonta nem duplica janelas.
7. Confere separadamente abertura, terminais, grupos e geometria. A comparação de
   geometria aceita quatro pixels lógicos de tolerância para arredondamento.

Uma falha permanece explícita por item. `RESTORE_GUARD.json` conserva o estado
desejado e a primeira observação após a tentativa. A disposição incorreta inicial
não substitui silenciosamente esse estado. Uma mudança real posterior na camada
correspondente pode estabelecer um novo estado desejado; uma confirmação válida
também encerra a pendência. Janelas que não abriram continuam recuperáveis.

## Identificação das conversas

Codex usa os hooks `SessionStart`/`UserPromptSubmit`; Antigravity usa seus eventos,
callback nativo com `conversation_id` e arquivos de presença/conversa; Claude Code
usa hooks e transcript aberto. O cache por PID não prova uma conversa atual.
Sem hook válido, os arquivos nativos disponíveis são consultados novamente.

A retomada usa ID explícito: `codex resume ID`, `agy --conversation ID` ou
`claude --resume ID`. Um chat comprovadamente vazio conserva seu painel como shell.
Um ID desconhecido também deixa a aba como terminal e gera pendência, sem escolher
uma conversa por adivinhação. Os históricos originais dos agentes precisam continuar
disponíveis; o manifesto não é um backup desses históricos.

O ID pedido nos argumentos é distinguido do ID confirmado pelo agente. Um Codex
pode carregar a conversa antes de emitir o hook; a abertura ocorre, mas a conferência
permanece pendente até haver evidência nativa. O monitor não envia mensagens para
provocar hooks. Claude foi testado isoladamente, sem uma sessão real aberta nesta
validação. Algumas sessões Codex antigas foram associadas manualmente por `/status`;
essa consulta não é injetada automaticamente nos terminais.

## Estado e recuperação

- `WORKSPACE1.json`: manifesto atual, com grupos, árvore, monitores e janelas.
- `LATEST_CAPTURE.json`: última observação diferente da interface, antes das proteções.
- `PREVIOUS_WORKSPACE1.json` e `LAST_COMPLETE.json`: alternativas locais se o
  manifesto principal estiver corrompido. Detecção completa não significa reboot verificado.
- `KITTY-<hash>.session`: arquivos nativos com hash conferido na leitura.
- `AGENT_IDS.json`: associação local entre painel e conversa.
- `RECOVERY.json` e `RECOVERY-<hash>.json`: estado preservado antes de restaurar.
- `RESTORE_GUARD.json`: pendências e referência para evitar aprender um layout falho.
- `RESTORE_STATUS.json`: resultados individuais, incluindo conferências por camada.

Gravações usam arquivo temporário, fsync e troca atômica. Locks impedem monitores
ou restaurações concorrentes. Se um Kitty ficar inacessível, conserva sua última
sessão nativa somente para a mesma janela, boot, PID e início do processo, marcada
como antiga e pendente. A observação bruta mantém o diagnóstico da falha.

O serviço é iniciado pelo autostart e reiniciado pelo systemd em caso de falha.
Não requer root, processo por grupo ou dependências extras. Os arquivos imutáveis
antigos ainda não são removidos automaticamente.

## Comandos

No diretório `PERSISTIR_WORKSPACE`:

- `python3 WORKSPACE1.py status`: contagens e última mudança salva, sem IDs privados.
- `python3 WORKSPACE1.py plan`: comandos de abertura, sem executá-los; pode imprimir
  caminhos e IDs privados, portanto a saída deve ser revisada antes de compartilhada.
- `python3 WORKSPACE1.py snapshot`: captura manual explícita, que dispensa a espera
  do monitor. A atualização automática sempre segue a espera configurada.
- `python3 WORKSPACE1.py restore`: restaura o manifesto e confere por camada.
- `python3 WORKSPACE1.py restore --recovery`: usa a captura anterior preservada.
- `python3 WORKSPACE1.py login`: entrada do serviço, restauração no boot e monitoramento.
- `python3 TEST_WORKSPACE1.py`: testes isolados, sem mover as janelas do desktop.
- `python3 TEST_LAYOUT_LIVE.py`: teste real no workspace 85, que deve estar vazio.
  Abre apenas shells temporários e fecha somente as identidades criadas pelo teste.

## Validação e limites

Em 17/10/2026 passaram 38 testes automatizados. O ciclo nativo isolado capturou,
fechou e restaurou quatro janelas, três grupos e cinco abas, com divisões horizontal
e vertical, geometria, ordem dos grupos e seleção conferidas. Outro ciclo validou
uma janela flutuante e dois grupos. As janelas originais foram preservadas.

O monitor ativo foi observado por 65 segundos sem mudanças: não regravou o manifesto
nem os arquivos Kitty; seu processo consumiu 0,12 segundo de CPU nesse intervalo.
Esse número é uma medição local do processo principal, não uma garantia para todas
as cargas. A captura automática do formato novo foi confirmada depois da espera.

O usuário já confirmou a reabertura de chats em um reboot real da versão anterior.
A restauração geométrica desta versão passou no ciclo real isolado, mas ainda não
foi testada em outro reboot completo. Layouts tiled diferentes do Dwindle e
arranjos que não possam ser reconstruídos como suas divisões ficam pendentes,
sem declarar sucesso. Janelas externas compartilhando o mesmo processo Kitty
continuam sem associação individual completa e usam restauração reduzida.

Referências: [API Lua do Hyprland](https://wiki.hypr.land/configuring/core/advanced-configuration/lua-utilities/),
[dispatchers](https://wiki.hypr.land/configuring/core/dispatchers/),
[IPC](https://wiki.hypr.land/ipc/) e
[sessões nativas do Kitty](https://sw.kovidgoyal.net/kitty/sessions/).
