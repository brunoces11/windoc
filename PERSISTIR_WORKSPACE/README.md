# Persistência gradual do Workspace 1

O serviço `windoc-workspace1.service` registra as janelas do Workspace 1 a cada
oito segundos e tenta reabri-las no próximo login, depois de um novo boot.
O mecanismo restaura o que conseguiu identificar: uma aba sem ID ou uma aplicação
não reconhecida não impede a abertura das outras janelas.

## Camadas e dados

1. **Hyprland:** IPC identifica janela, classe, workspace, posição, tamanho,
   monitor, foco e membros do grupo. Cada janela recebe uma identidade estável
   para associar captura e restauração, sem depender do novo PID/endereço.
2. **Kitty:** `save_as_session --save-only --use-foreground-process` fornece o
   arquivo nativo com abas, painéis, layouts, diretórios, foco e comandos. O código
   personaliza os comandos dos agentes, conservando a estrutura gerada pelo Kitty.
   Todos os painéis, inclusive terminais vazios, entram no manifesto de verificação.
3. **Conversas:** agente e ID pertencem ao painel exato, identificado por
   `KITTY_PID` + `KITTY_WINDOW_ID` e início do processo. Títulos e recência global
   não escolhem conversas. A retomada usa `codex resume ID`, `agy --conversation ID`
   ou `claude --resume ID`.
4. **Aplicativos:** Chromium, Sublime Text, Nautilus e Amberol possuem comandos
   conhecidos, usados quando instalados. Aplicações desconhecidas ficam registradas
   como pendentes. Páginas, arquivos e posição de reprodução dependem da restauração
   própria de cada aplicativo; este mecanismo não os extrai.
5. **Login:** o autostart do Hyprland importa seu ambiente IPC e inicia o serviço
   do usuário. O systemd supervisiona falhas; locks impedem dois monitores ou duas
   restaurações simultâneas. Não são necessários privilégios administrativos.

## Identificação das conversas

- **Codex:** hooks oficiais `SessionStart`/`UserPromptSubmit`; retomada explícita
  por ID é uma alternativa quando o hook ainda não chegou. Uma sessão antiga sem
  registro foi associada nesta máquina pelo `/status` nativo. Essa consulta foi
  manual e não é injetada automaticamente em terminais pelo monitor.
- **Antigravity:** eventos `SessionStart`/`PreInvocation`, callback nativo de título
  com `conversation_id` e arquivo de presença/conversa aberto pelo processo.
  O parser reconhece `USER_INPUT` no transcript e reavalia registros antigos que
  haviam sido marcados incorretamente como vazios.
- **Claude Code:** hooks `SessionStart`/`UserPromptSubmit` e transcript aberto pelo
  processo. O adaptador foi testado isoladamente; não havia Claude aberto para um
  teste real de retomada nesta validação.

Um chat comprovadamente vazio volta como shell na mesma aba. Falta de ID, arquivo
inacessível ou formato desconhecido **não provam que o chat está vazio**. Um chat
sem ID também volta como shell, com pendência explícita, sem selecionar a conversa
mais recente. Um registro de hook atualizado tem prioridade sobre argumentos
antigos do processo, pois o usuário pode trocar de conversa dentro do agente.

A verificação distingue o ID pedido no comando do ID confirmado pelo agente.
Durante o teste desta versão, uma retomada Codex carregou a conversa correta, mas
não emitiu o hook de sessão no intervalo observado antes de uma nova interação.
Nesse caso a abertura continua funcionando, porém a verificação permanece pendente
até haver evidência nativa. O monitor não envia mensagens para provocar o hook.

## Estado privado e recuperação

`ESTADO_LOCAL/` é privado e ignorado pelo Git. Contém:

- `WORKSPACE1.json`: estado atual, inclusive parcial, usado no próximo boot.
- `LATEST_CAPTURE.json`: última leitura do desktop, inclusive durante verificações.
- `PREVIOUS_WORKSPACE1.json` e `LAST_COMPLETE.json`: alternativas se o manifesto
  principal estiver corrompido. “Completo” se refere à detecção, não a um reboot testado.
- `KITTY-<hash>.session`: sessões nativas imutáveis por conteúdo, com hash verificado.
- `AGENT_IDS.json`: associação local entre painel e conversa.
- `RECOVERY.json` e `RECOVERY-<hash>.json`: captura preservada antes de cada tentativa.
- `RESTORE_STATUS.json`: resultado individual de cada janela e da verificação.

Gravações usam arquivo temporário, troca atômica e sincronização em disco. A redução
da quantidade de janelas/abas/painéis aguarda 30 segundos; workspace vazio aguarda
60 segundos. No desligamento, o monitor evita substituir o estado por um desktop
em encerramento. Falhas de uma janela não interrompem a tentativa das demais.

Os arquivos de sessão são imutáveis e mantidos localmente; esta versão ainda não
remove automaticamente versões antigas. Eles não incluem um backup do histórico
dos agentes: os dados originais de cada agente também precisam continuar disponíveis.

## Comandos

Executar no diretório `PERSISTIR_WORKSPACE`:

- `python3 WORKSPACE1.py status`: contagens, pendências e último resultado, sem IDs.
- `python3 WORKSPACE1.py plan`: mostra os comandos gerados, sem executá-los. Pode
  exibir caminhos privados; não publicar a saída sem revisão.
- `python3 WORKSPACE1.py snapshot`: salva a configuração observada manualmente.
- `python3 WORKSPACE1.py restore`: abre itens ausentes e confere os existentes.
- `python3 WORKSPACE1.py restore --recovery`: usa a captura preservada da tentativa.
- `python3 WORKSPACE1.py login`: entrada do serviço; restaura após novo boot e monitora.

`RESTORE_STATUS.json` distingue janelas iniciadas de janelas apenas conferidas.
“Conferida” com zero iniciadas não é um teste de reboot. Os resultados podem ser
parciais mesmo quando algumas janelas abriram corretamente. A conferência compara
abas, painéis, diretórios, programas, IDs e associação aos grupos.

## Validação e limites atuais

Em 17/10/2026 passaram 25 testes automatizados. Um ciclo real em workspace isolado
abriu um Kitty com duas abas e três painéis, capturou pelo recurso nativo, fechou
somente essa janela, restaurou e conferiu diretórios, layout e grupo individual.
Repetir a restauração não duplicou a janela. As janelas originais foram preservadas.
O serviço foi ativado e sua atualização automática de estado foi confirmada.

Durante a validação, a tela mudou de seis para nove abas Kitty. As nove foram
registradas: oito conversas com IDs distintos (duas Codex e seis Antigravity) e
um terminal vazio. Amberol e Sublime também entraram no inventário restaurável.
Essas contagens são uma observação datada, não uma configuração fixa.

Limites relevantes:

- **Reboot completo ainda não testado.** A captura, os comandos, o serviço e o ciclo
  nativo isolado foram verificados; isso não garante sucesso de todas as conversas
  depois de reiniciar a máquina.
- Grupos com uma janela são recriados. **Grupos Hyprland com várias janelas ainda
  não são recompostos**: cada janela abre separadamente e a conferência informa
  `grupo_pendente`. Isso inclui o grupo Kitty + Amberol observado nesta validação.
- A posição e o tamanho exatos dos tiles, monitor e foco global são registrados,
  mas não reaplicados. As janelas seguem o layout atual do compositor.
- Várias janelas externas compartilhando o mesmo processo Kitty ainda não têm
  associação individual; a captura faz uma restauração reduzida e registra aviso.
- Se a exportação nativa falhar, recria as abas/painéis conhecidos e preserva os
  comandos de agentes com ID. Demais programas desse fallback voltam como shell.
- Um agente iniciado sem emitir hook e sem outro identificador observável pode
  continuar sem ID. Esse caso fica pendente e não bloqueia o restante do workspace.

Referências: [dispatchers Lua do Hyprland](https://wiki.hypr.land/configuring/core/dispatchers/),
[hooks do Codex](https://learn.chatgpt.com/docs/hooks) e
[sessões nativas do Kitty](https://sw.kovidgoyal.net/kitty/sessions/).
