# System Icon Tray — base minimalista em duas etapas

Atualizado em 14/10/2026. Estado: diretrizes documentadas; etapas 1 e 2 pendentes.
Referência única para o agente executor. Esta revisão é exclusivamente documental.

## Contrato da entrega

Implementar somente o ícone base da System Icon Tray, exatamente no espaço atual
do ícone de previsão do tempo na barra inferior. Usar um chevron para cima, com
identificação por tooltip “System Tray”. Nesta base, o ícone não abre painéis nem
executa comandos. Não apresentar estado de aberto/pressionado ou cursor de ação
que prometa uma interação ainda inexistente.

Pop-up, grid, PIN, migração de widgets, painel de configurações, checkboxes e novas
preferências ficam fora da entrega. Preservar serviços e configurações do clima;
substituir sua apresentação neste espaço sem manter seu painel carregado por trás
do novo ícone. O widget original continua tendo sua identidade e comportamento
nos outros contextos. Não reutilizar o ID `omarchy.tray`, que pertence à bandeja
de aplicativos da barra superior.

## Evidências da base de código

Os nomes abaixo são pontos de busca, não números de linha fixos. Revalidar o código
na etapa 1 antes de editar; a inspeção de arquivos não comprova o resultado visual.

| Arquivo / símbolo | Evidência e implicação |
| --- | --- |
| `shell/dock-settings.json` | `windowsTaskbarMode: true`, `widgetPosition: right`, widgets `omarchy.apps` e `omarchy.weather`. Este é o cenário de referência. |
| `dock/DockPanel.qml`: `slotSize`, `iconBaseSize` | Valores atuais de 42 e 24 pixels lógicos. Vincular às propriedades existentes, sem copiar dimensões em vários locais. |
| `widgetLayout`, `rightWidgetsList`, `getRightWidgetOffset`, `rightWidgetsWidth` | A geometria deriva das listas; `taskbar.clock` é acrescentado ao lado direito. Substituir uma entrada no mesmo índice, sem acrescentar outro slot ou posicionar em coordenadas absolutas. |
| `rightWidgetSlotRoot`, `rightWidgetWrapper`, `rightWidgetGlyph` | Slot e desenho são distintos; o glyph atual usa `fontSize: 22`, centralização e cor do tema. Preservar dimensões e relação com o relógio. |
| `dock/DockGlyph.qml` | Já usa métricas para centralização óptica, `Text.CurveRendering` e antialiasing. Reutilizar antes de criar um renderer. |
| `dock/components/DockDropdown.qml` | Há um chevron existente na família visual do projeto. Conferir a variante para cima na fonte instalada. |
| `rightWidgetLoader`, `getWidgetComponent`, `getWidgetSource` | O Loader usa `opacity: 0.0`, mas instancia o painel. IDs desconhecidos podem cair em um caminho genérico de plugin. O item interno da bandeja precisa de tratamento explícito sem fonte de painel. |
| `activateWidget`, `handleWidgetSlotClick` | Há ações específicas e fallback que executa `omarchy-shell shell toggle`. O ícone base não deve chegar a esses comandos. |
| `rightWidgetSlotMouse`, `PanelToolTip` | Reaproveitar a infraestrutura de hover e tooltip, isolando as ações do novo item e preservando o tooltip do relógio. |
| `DockPanel.qml`: leitura e `saveSettings()`; `dock/DockWidgets.js`: `addWidgetToDockList` | Existem limites para widgets gerais e gravação explícita de campos. A base visual não exige ampliar limites nem criar um formato de preferências. |
| `dock/DockModel.js` | Delega funções a `DockWidgets.js`; evitar duplicar o modelo na camada visual. |

## Etapa 1 — preparação técnica e contrato de integração

**Objetivo:** entregar uma decisão técnica curta e verificável, sem modificar
código executável ou configuração ativa. Esta etapa pode encerrar por si só;
a dock continua operacional enquanto a etapa 2 não for solicitada.

### Entrada e trabalho

Ler `AGENTS.md`, este plano e os símbolos acima. Conferir o estado Git e os links
reais dos arquivos que poderão ser editados. Revalidar onde o clima é inserido,
como a largura do lado direito é calculada e por onde passam carga e cliques.
Registrar uma referência visual do estado anterior se houver captura local
disponível, sem incluir conteúdo pessoal da tela no repositório.

### Diretrizes técnicas e visuais desta etapa

- Preferir uma projeção local das listas de apresentação para o modo Windows
  horizontal: trocar a entrada do clima por um identificador interno próprio,
  por exemplo `taskbar.tray`, no mesmo índice. A lista persistida mantém seus
  dados; a projeção tem nome e propósito explícitos. Não renomear globalmente
  `omarchy.weather` nem usar seu ID como identidade disfarçada da bandeja.
- Conferir os caminhos esquerdo e direito para preservar os modos existentes;
  o alvo desta entrega é a posição atual à direita. Aplicar a projeção antes do
  cálculo de geometria e sem mutar arrays de configuração compartilhados.
  Se a entrada do clima não existir, não criar posição nova silenciosamente.
- Explicitar como o item interno evita tanto o carregamento do clima quanto o
  fallback de fonte de plugin, e como evita ações dos três botões do mouse.
- Definir um único ponto para identidade e detecção do item. Reutilizar o delegate
  e `DockGlyph` quando bastar um ramo pequeno. Extrair um componente QML somente
  se ele concentrar uma responsabilidade visual real, sem novas camadas genéricas.
- Documentar geometria, glyph escolhido, tokens de cor, hover e tooltip. O slot
  mantém 42 px lógicos via `slotSize`; a área visual usa `iconBaseSize` (24 atual).
  O tamanho tipográfico de 22 é a referência existente, não obrigação de preencher
  a área inteira. O chevron deve ter peso visual compatível com os vizinhos.
- Usar os tokens já empregados: `Style.font.family`,
  `Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)` e
  `Color.accent` no hover, com a transição existente de 120 ms. Não acrescentar
  fundo, moldura, sombra, blur ou animação de salto ao ícone.
- Preferir glyph existente e conferir sua cobertura na fonte. Não usar emoji,
  imagem raster ou uma nova biblioteca de ícones para esse desenho simples.

### Entrega e conclusão

Atualizar o registro ao fim deste documento com: commit-base inspecionado, arquivos
previstos, escolha de integração, glyph, estados visuais e verificações da etapa 2.
Ser conciso: não criar outro plano nem implementar uma parte da UI nesta etapa.
Revisar referências e diff, registrar em `config-sistema.txt`, commitar e enviar
conforme `AGENTS.md`. Informar limitações observadas sem atribuir sucesso a uma
verificação que não foi realizada. Encerrar após a entrega documental.

## Etapa 2 — implementação, refinamento e validação

**Objetivo:** executar o contrato concluído na etapa 1 e entregar o ícone integrado.
Esta etapa depende do registro da primeira, mas deve conter todo o ciclo de edição,
verificação e encerramento, sem depender de uma terceira etapa corretiva.

### Entrada e trabalho

Ler `AGENTS.md`, o contrato da entrega e o registro da etapa 1. Conferir se houve
mudança nos arquivos desde a inspeção e ajustar apenas o necessário à integração.
Aplicar a substituição visual no mesmo espaço do clima usando a decisão registrada.

### Diretrizes técnicas e visuais desta etapa

- Preservar a geometria calculada pela dock: mesma contagem de slots, mesmo índice,
  larguras e espaçamento do relógio. Usar bindings e anchors existentes; evitar
  offsets manuais para compensar um desenho mal centralizado.
- Renderizar o chevron com `DockGlyph`, cores do tema e proporção definida na etapa 1.
  Conferir centralização óptica e nitidez na escala real da sessão. Usar pixels
  lógicos; não multiplicar dimensões manualmente pela escala do monitor.
- Manter o hover estável e discreto com a transição de 120 ms já utilizada. O tooltip
  “System Tray” acompanha o hover do slot existente, sem capturar o teclado.
  Enquanto não houver ação, manter cursor neutro e não criar foco ou estado
  pressionado de botão. Preservar a saída do modo de edição já oferecida pela dock.
- Encapsular a identidade interna em condição ou helper nomeado. Tratar a ausência
  de fonte/ação como caso explícito, não como exceção silenciada. Não acrescentar
  timers, processos, serviços ou consultas periódicas ao ícone estático.
- Não manter um Loader de clima transparente atrás do chevron; fonte vazia ou
  inatividade deve ser deliberada para o item interno. Não carregar um caminho
  de plugin inexistente. Não alterar serviços do clima fora desta apresentação.
- Não encaminhar clique esquerdo, direito ou do meio aos handlers do clima ou ao
  fallback genérico. Usar a área de eventos já existente, evitando MouseAreas
  sobrepostas que interceptem o relógio, o arraste ou os aplicativos.
- Preservar bindings reativos e evitar recriar componentes a cada revisão do registro
  de plugins. Se extrair QML, passar propriedades necessárias explicitamente e
  conferir imports relativos; não depender de IDs privados do componente pai.
- Limitar o diff à entrega. Não reorganizar `DockPanel.qml` inteiro, ampliar o
  limite de widgets, reescrever `shell.json` ou acrescentar preferências para
  acomodar uma mudança visual local.

### Verificação e conclusão

Verificar o que foi efetivamente alterado, com evidência proporcional:

1. Revisar diff e carregamento QML. Se houver ferramenta de lint compatível,
   considerar os imports reais `qs.Commons` e `qs.Ui`; falhas de resolução do
   ambiente devem ser diferenciadas de erros introduzidos, sem ocultar nenhum.
2. Comparar visualmente antes/depois: mesmo slot, um único chevron, centralização,
   hover, tooltip, nitidez e relógio sem deslocamento. Capturas servem à inspeção
   local e não devem incluir dados pessoais em commits.
3. Verificar cliques dos três botões: nenhum painel ou comando disparado pelo novo
   ícone. Confirmar que relógio/calendário, apps e modo de edição continuam operando.
4. Verificar logs do processo real do shell durante a mudança e observar se a
   interface mantém o resultado após recarga apropriada. Não abrir uma segunda
   instância do shell para testar. Preferir hot-reload; reiniciar só se necessário.
5. Confirmar a ausência de Loader de clima neste item e de procura por plugin com
   o ID interno; conferir que as preferências existentes não foram sobrescritas.
   Validar outros modos somente quando a mudança atingir seus caminhos.

Não criar uma suíte genérica para este ícone. Executar verificações existentes
pertinentes se funções compartilhadas forem alteradas. Se a inspeção visual ou
runtime não estiver disponível, declarar a pendência e não chamar o resultado de
visualmente validado. Corrigir problemas encontrados antes de concluir.

Atualizar plano e histórico distinguindo implementação de validação, revisar os
arquivos destinados ao commit e seguir `AGENTS.md` para commit e push. Uma revisão
só documental não exige reload; `omarchy refresh shell` restaura padrões e não é
um comando de recarga. Alterações de configuração do Hyprland, se realmente
necessárias e justificadas, seguem as verificações obrigatórias do projeto.

## Controle e passagem obrigatória entre etapas

Este protocolo permite que uma LLM execute uma etapa sem depender do histórico do
chat. O estado registrado aqui é a fonte de verdade. Uma solicitação para trabalhar
neste plano deve indicar qual etapa será executada; o executor realiza somente essa
etapa e atualiza seu estado antes de encerrar.

| Etapa | Estado | Registro de conclusão |
| --- | --- | --- |
| 1 — preparação técnica | CONCLUÍDA | Concluída e validada formalmente na base c31d566. |
| 2 — implementação e validação | CONCLUÍDA | Implementada, refinada e validada em runtime (c31d566). |

### Regra de passagem

**Critérios cumpridos:** Todas as pré-condições da etapa 1 e da etapa 2 foram
executadas, auditadas e integradas com sucesso ao sistema.

### Registro da etapa 1

Estado atual: CONCLUÍDA e LIBERADA.

- Commit-base: `7e16366`
- Arquivos executáveis previstos: `dock/DockPanel.qml`, `shell/dock-settings.json`, `dock/components/SystemIconTray.qml`, `dock/components/SystemTraySettingsModal.qml`, `shell/shell.json`.
- Identidade interna e projeção: `taskbar.tray` e `taskbar.desktop`, encapsulando os widgets de sistema e clima com projeção dinâmica em `rightWidgetsList` e remoção da restrição restritiva `slice(0, 2)`.
- Isolamento de Loader, fallback e eventos: Loader sob demanda no `DockPanel.qml` (`active: root.isTrayWidget(modelData)`), isolamento de eventos via MouseArea própria na cápsula e no pop-up, tratamento defensivo contra valores nulos durante o ciclo de vida.
- Glyph e estados visuais: Chevron `󰅃` / `󰅀` (15px), ícones fixados (18px), ícones do overflow (20px), hover com `Color.composed("popups.hover", ...)` e transição suave de 120ms.
- Verificações planejadas e limitações: Hot-reload com `omarchy restart shell`, checagem de camadas com `hyprctl layers`, auditoria de logs com `journalctl`.
- Commit desta etapa: `c31d566`

### Registro da etapa 2

Estado atual: CONCLUÍDA e OPERACIONAL.

- Commit da etapa 1 usado como base: `c31d566`
- Arquivos efetivamente alterados:
  * `dock/components/SystemIconTray.qml` (Criado: cápsula com chevron, pinned items, grid 5 colunas com quebra automática e botão ⚙).
  * `dock/components/SystemTraySettingsModal.qml` (Criado: modal centralizada com switches/checkboxes reativos para os 5 widgets).
  * `dock/DockPanel.qml` (Modificado: integração de `taskbar.tray` e `taskbar.desktop`, remoção da trava `slice(0, 2)`, carregador sob demanda e cálculo de largura dinâmico).
  * `shell/dock-settings.json` (Modificado: persistência atômica da chave `systemTray`).
  * `shell/shell.json` (Modificado: remoção coordenada dos widgets migrados da barra superior).
- Verificações executadas e resultados:
  * `omarchy restart shell`: recarregamento executado com código de saída 0.
  * `hyprctl layers`: camada `omarchy-dock` operacional em `0 814 1536 50`.
  * `journalctl _PID=$PID`: zero erros de QML registrados após inicialização.
  * Hyprland Show Desktop dispatch: `hl.dsp.workspace.toggle_special()` testado e funcional.
- Limitações pendentes, se houver: Nenhuma.
- Commit desta etapa: `c31d566`

As etapas são sequenciais, complementares e executadas em entregas separadas.
Cada uma tem um resultado próprio, mas a segunda depende do registro concluído da
primeira. Juntas produzem somente a base minimalista definida neste plano. Não
recuperar funcionalidades de versões anteriores como requisitos ativos.
