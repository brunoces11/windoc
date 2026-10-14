# System Icon Tray — plano de implementação do WinDoc

Atualizado em 14/10/2026. Estado: planejamento consolidado; implementação pendente.

Este documento é a referência única para a feature. Consolida as decisões da
conversa e substitui suas propostas técnicas preliminares. Define uma divisão
macro; o detalhamento de cada etapa será feito em uma próxima interação.
A atualização documental não autoriza iniciar a implementação.

## Objetivo e comportamento acordado

Reunir os indicadores escolhidos na barra inferior, à esquerda do relógio,
com experiência inspirada na área de notificação do Windows.

- A seleção é nominal, por identificador, sem limite arbitrário de ícones fixados.
- Checkbox marcado significa fixado e visível na barra; desmarcado significa
  disponível no pop-up da setinha. Não significa desativar o widget.
- O pop-up tem até cinco ícones por linha; o sexto inicia a segunda linha.
  Cresce conforme o conteúdo. A referência inicial de quatro linhas não obriga
  a reservar vinte células vazias; o tratamento de excedentes será detalhado depois.
- A engrenagem abre uma janela flutuante centralizada com a lista e os checkboxes.
- As escolhas devem atualizar a interface e persistir após reiniciar a sessão.
- Os widgets migrados deixam sua posição anterior após a nova integração funcionar.
- A faixa fina após o relógio deve mostrar a área de trabalho e, em novo clique,
  restaurar a situação anterior. Seu mecanismo será investigado separadamente.

Diretriz proposta para manter o acesso à edição: engrenagem sempre disponível no
pop-up e setinha acessível mesmo com todos os widgets fixados.
Os ícones inicialmente fixados ainda não foram escolhidos pelo usuário; áudio e
rede apareceram apenas como sugestão nas respostas anteriores.

## Base atual conferida

Inspeção de arquivos e resolução de caminhos em 14/10/2026; não equivale a uma
validação visual ou funcional de todos os plugins instalados.

| Área | Evidência atual | Consequência para o plano |
| --- | --- | --- |
| Dock | `shell/dock-settings.json`: modo Windows ativo, widgets `omarchy.apps` e `omarchy.weather` | O clima já está na dock; será integrado à bandeja sem duplicação final. |
| Relógio | `dock/DockPanel.qml` acrescenta `taskbar.clock` ao modo horizontal Windows | Integrar a bandeja ao layout existente. |
| Hospedagem | `DockPanel.qml` possui carregamento por registro e fontes específicas de painéis | Reaproveitar a infraestrutura, verificando as necessidades de cada widget. |
| Limite atual | Leitura e gravação de `dockWidgets` usam `slice(0, 2)` | Não aumentar o limite automaticamente; propor coleção própria para a bandeja. |
| Preferências | `saveSettings()` reconstrói o JSON com campos explícitos | Integrar leitura e gravação das novas preferências; apenas acrescentar campos ao arquivo não basta. |
| Barra superior | `shell/shell.json` lista tray de apps, floating mode, agentes, Bluetooth, rede, áudio, monitor e energia à direita | Migrar somente os itens do escopo confirmado. |
| Minimização | `DockPanel.qml` chama `dock/scripts/dock-minimize.py` | Investigar reaproveitamento antes de criar outro mecanismo para mostrar a área de trabalho. |
| Centralização | Os caminhos de shell.json, dock-settings.json e rosakodu.dock resolvem para o repositório | As futuras mudanças nesses alvos já têm base centralizada. |

O inventário histórico registra situações anteriores, inclusive dock desabilitada
e OmaPanel na barra. Esses registros permanecem como histórico. A configuração
atual lista `rosakodu.dock` em `plugins`, com `dockEnabled: true`, e não inclui
OmaPanel no layout; isso não comprova por si só o estado do processo em execução.

## Escopo e pontos a confirmar

| Função solicitada | Referência disponível | Situação |
| --- | --- | --- |
| Volume | `omarchy.audio` | Candidato identificado; validar integração. |
| Consumo de agentes | `brunoma.agents` | Candidato identificado; preservar o widget personalizado. |
| Previsão do tempo | `omarchy.weather` | Já configurado na dock; consolidar na bandeja. |
| Rede / configuração DNS | `omarchy.network` | Confirmar que corresponde à ação de DNS mencionada pelo usuário. |
| Desktop | `io.github.rawritude.floating-mode` foi sugerido anteriormente | Identidade e funcionamento ainda precisam ser confirmados; não assumir equivalência com monitor, workspaces ou mostrar área de trabalho. |

`omarchy.tray` é um widget da barra superior que reúne ícones de aplicativos;
não é uma terceira barra. Sua migração está fora desta entrega. Bluetooth,
monitor e energia também não entram automaticamente na lista por estarem próximos.
A retirada completa da barra superior fica para uma evolução posterior.

## Organização modular

Separar responsabilidades de dados e persistência, apresentação da bandeja,
edição das preferências, integração dos widgets e controle de janelas.
A quantidade de arquivos QML será consequência dessas responsabilidades, sem
exigir antecipadamente dois ou quatro arquivos.

A lista de participantes pertence à feature; a lista de fixados é preferência do
usuário. Reutilizar metadados existentes quando disponíveis, sem criar agora uma
segunda configuração de ativar/desativar widgets. Preservar as ações nativas e
verificar posicionamento e foco dos painéis antes de adicionar adaptações de mouse.
Blur, animações extras, arraste e novos controles não são requisitos desta entrega.

## Proposta de divisão sequencial

As etapas são separáveis para implementação, validação e versionamento. Possuem
dependências explícitas: a independência significa que uma entrega não exige a
próxima para permanecer coerente e utilizável, e não ausência de dependências.

| Etapa | Camada e entrega | Dependência | Resultado ao encerrar |
| --- | --- | --- | --- |
| 1 | Base: consolidar catálogo de participantes, contrato de integração e persistência dos IDs fixados | Nenhuma etapa de implementação anterior | Base compatível com a dock atual; dúvidas de identidade resolvidas antes de incluir cada widget. |
| 2 | Bandeja: posição junto ao relógio, fixados, setinha e grid com um widget piloto | 1 | Estrutura visual e abertura do painel do piloto verificadas; hospedagem do piloto coordenada com sua origem. |
| 3 | Configuração: engrenagem, janela central, checkboxes e atualização persistente | 2 | Usuário alterna o piloto entre barra e pop-up; acesso às configurações permanece disponível. |
| 4 | Consolidação: integrar os demais widgets confirmados, incluindo clima, e retirar suas apresentações anteriores | 3 | Bandeja completa no escopo escolhido, com ações preservadas e migração verificável por widget. |
| 5 | Mostrar área de trabalho: implementar a faixa após o relógio e a restauração das janelas | Layout estabilizado na 4; mecanismo de janelas validado separadamente | Recurso adicional funcional; sua eventual pendência não bloqueia o uso da bandeja concluída na 4. |

Nenhuma etapa foi iniciada. Esta tabela é a proposta de divisão, ainda sem tarefas,
interfaces de código ou listas detalhadas de testes por etapa.

## Critérios comuns para a próxima fase

Cada etapa deve preservar o que já funciona e ter uma verificação correspondente
à mudança antes de incorporar a seguinte. A migração deve manter acesso às funções,
coordenar a substituição de cada widget e evitar duplicação final entre barra,
pop-up e posição anterior. O campo `allowMultiple` isoladamente não prova falha de
execução; conferir o comportamento e o contexto reais de cada componente.

A verificação futura cobrirá carregamento QML, ações dos widgets, abertura e foco
dos painéis, persistência e layout no ambiente utilizado. Foco, fechamento,
limites da tela e comportamento entre monitores entram no detalhamento da etapa
correspondente. Mostrar área de trabalho exige conferir a restauração das janelas,
inclusive interação com a minimização que a dock já utiliza.

Mudanças de QML e shell são verificadas no Omarchy Shell/Quickshell. Reiniciar o
shell só quando necessário. `omarchy refresh shell` restaura padrões e não serve
como recarregamento comum. Alterações de configuração do Hyprland exigem
`hyprctl reload` e consulta a `hyprctl configerrors`. Revisões somente documentais
não exigem recarregar a interface.

A confiança na viabilidade da bandeja é alta; a compatibilidade de cada widget
precisa de validação. O principal risco é regressão da interface ou das preferências.
O controle coletivo de janelas tem incerteza própria. Git permite recuperar arquivos
versionados, sem garantir restauração do estado da sessão. Não há promessa de risco
zero ou percentuais de assertividade sem evidência.

Seguir `AGENTS.md` em cada entrega: centralização prévia quando necessária,
verificação proporcional, registro incremental, commit e push. Na próxima
interação, detalhar as etapas a partir desta divisão, sem recriar planos concorrentes.
