# Investigação técnica: Amberol Deskband

Registro histórico da análise inicial; a implementação posterior está na seção 7.

Data: 16/10/2026. Escopo: rastreamento do fluxo de integração do player até as duas barras, identificação da origem da dock e revisão dos quatro pontos do plano. A única alteração persistente desta tarefa é documental. O plugin ainda não foi implementado, instalado ou publicado.

## 1. Origem e ambiente confirmado

A dock incorporada ao WinDoc é o **Omarchy Dock**, de **rosakodu**, publicado em https://github.com/rosakodu/omarchy-dock. O README, LICENSE e manifest.json locais confirmam essa origem. O manifesto declara `rosakodu.dock`, versão `1.8.32`, licença MIT. Essa versão não identifica o conjunto das customizações locais nem permite atribuir um commit exato do código original.

O código em uso fica em `dock/`. Os caminhos `~/.config/omarchy/plugins/rosakodu.dock` e `~/.config/omarchy/plugins/brunoma.windoc` são symlinks para essa mesma pasta. A configuração `shell/shell.json` habilita `rosakodu.dock`. Não são duas implementações separadas.

Versões instaladas observadas: Omarchy `4.0.4-1`, Quickshell `0.3.1-1`, Amberol `2026.1-1`. Esta é a primeira combinação candidata a suporte; a compatibilidade integral do futuro plugin ainda depende de validação. O formato de manifesto é `schemaVersion: 1`.

A barra superior está desativada pelo estado `~/.local/state/omarchy/toggles/bar-off`; seu layout está vazio. Uma demonstração no topo precisará habilitá-la temporariamente e restaurar o estado anterior, ou usar um host isolado. A dock atual opera em `windowsTaskbarMode`, horizontal, com slots de 42 px e janela de aproximadamente 50 px de altura.

## 2. Ponto 1: renderização da cápsula e popup no WinDoc

### Fluxo encontrado, em ordem

1. `shell/shell.json` habilita o plugin da dock. O shell lê `dock/manifest.json` e carrega o serviço `dock/DockPanel.qml`; `dock/BarWidget.qml` é o botão de ajustes, não o conteúdo da barra inferior.
2. `shell/dock-settings.json` fornece `dockWidgets`, posições e opções. `dock/DockWidgets.js`, encaminhado por `DockModel.js`, organiza as listas esquerda/direita. O estado atual contém os dois menus; bandeja, relógio e mostrar área de trabalho são acrescentados por lógica da taskbar.
3. O Omarchy registra componentes dos plugins habilitados em `BarWidgetRegistry`. `DockPanel.qml:getWidgetComponent()` consulta o catálogo injetado, que permite encontrar componentes externos. `getWidgetSource()` é uma alternativa, mas a visão restrita do registro de plugins não garante consultar o manifesto de outro plugin.
4. Os Repeaters de widgets à esquerda e à direita criam slots. Os Loaders instanciam o componente externo com `opacity: 0.0`, em wrappers normalmente limitados ao tamanho de ícone. `DockGlyph` desenha o ícone substituto; uma `MouseArea` do host cobre o slot e encaminha a ação para `activateWidget()`.
5. `configureHostedWidget()` injeta `dockBarContext`, ID, shell e âncora, além de percorrer painéis para adaptar sua posição. `dockBarContext` já informa a posição inferior e oferece funções de tooltip e popup.
6. As funções de dimensão e offsets somam slots fixos, com exceções para relógio, bandeja e mostrar área de trabalho. Não consultam a largura da cápsula nem recolhem o espaço quando ela fica invisível.
7. O seletor `components/WidgetPickerPopup.qml` contém uma lista fixa. Não inclui o novo plugin nem o widget nativo `omarchy.media`, embora exista resolução de componente para este último.
8. `DockWidgets.js:addWidgetToDockList()` preserva os menus e apenas um widget adicional. `dock/BarWidget.qml:saveSettings()` também limita a lista a três entradas. Não existe, hoje, uma lista geral de widgets livremente reordenáveis pelo usuário.
9. `checkWidgetPanelsOpen()` considera `opened` no widget e `panel.open` no painel. Esse contrato mantém a dock aberta enquanto o popup é usado; expor apenas uma variável com outro nome não basta.

### Solução concreta proposta

Adaptar os slots existentes com um modo explícito de conteúdo completo para o Deskband. Nesse modo, o Loader deve ficar visível, seus botões devem receber eventos e sua largura deve vir do componente. A mesma medida deve alimentar soma de larguras, offsets, limites de aplicativos, separadores e recolhimento. O modo atual dos demais widgets deve continuar disponível.

O componente deve expor `implicitWidth`, `implicitHeight`, `opened`, `close()` e uma referência `panel` compatível com o host. O popup deve usar a janela e a tela da instância da cápsula como âncora. Fechar o player ou recolher o componente deve fechar o popup. Ao destruir/recarregar uma instância, remover sua referência de `loadedWidgetItems` e evitar conexões duplicadas.

Acrescentar a entrada do Deskband ao seletor e validar persistência. Para o escopo inicial, ele pode ocupar o terceiro lugar disponível após os dois menus; não é preciso transformar o gerenciador inteiro de widgets. A promessa de reordenação livre de vários widgets exige trabalho adicional e deve ficar fora da primeira entrega.

Arquivos previstos para a integração: `dock/DockPanel.qml`, `dock/components/WidgetPickerPopup.qml` e, conforme o contrato final de posicionamento, `dock/DockWidgets.js` e `dock/BarWidget.qml`. Os arquivos de configuração só serão alterados na ativação.

**Estado:** limitação e locais de alteração identificados por leitura do código. A renderização da futura cápsula ainda não foi implementada nem validada visualmente.

## 3. Ponto 2: versões, manifesto e independência

No topo, `plugins/bar/Bar.qml:ModuleSlot` respeita `visible` e `implicitWidth` do componente. O host injeta `bar`, `moduleName` e `settings`; o plugin deve aceitar esse contrato e oferecer apresentação compacta compatível com a altura disponível. O estilo do shell tem altura horizontal padrão de 26 px, sujeita ao tema: capa de 28 px e duas linhas não devem ser impostas a toda barra. No dock, há espaço para a apresentação de duas linhas; no topo, usar medidas adaptadas ou modo compacto.

Há um serviço nativo de mídia em `plugins/services/media/`, com Service.qml, BarWidget.qml e MediaModel.js. Porém, `shell.qml:pluginServiceFor()` permite acesso ao serviço do próprio plugin; `firstPartyServiceFor()` depende das capacidades concedidas pelo host. Copiar o widget nativo e presumir que todo plugin terá o mesmo acesso é incorreto.

A solução mais simples para um produto independente é acessar `Quickshell.Services.Mpris` diretamente. Começar com manifesto de tipo `bar-widget` e sem serviço próprio. Um componente `AmberolController.qml` por instância consome o singleton nativo `Mpris`, sem processo auxiliar. O código do controlador é reutilizado nas duas barras. Um serviço separado só se justificará se aparecer uma necessidade real de estado global adicional.

Nome proposto: Amberol Deskband. ID proposto: `amberol-deskband`, válido pelo formato de IDs aceito pelo shell local; mantê-lo idêntico entre manifesto, configuração e instalação. O nome não implica API oficial de plugins do Amberol: trata-se de um controlador MPRIS externo.

Restringir a primeira compatibilidade declarada ao Omarchy Quattro e ao WinDoc customizado aqui inspecionado. Outros hosts Quickshell podem reutilizar componentes, mas exigem adaptação. Imports `qs.Ui`/`qs.Commons` pertencem ao shell Omarchy, portanto não são dependências universais de qualquer instalação Quickshell. Manter o núcleo visual e MPRIS com imports QtQuick/Quickshell quando possível.

**Estado:** versões instaladas, contratos de entrada e restrições de acesso conferidos. A versão do manifesto da dock não substitui fixar uma revisão do WinDoc na documentação de compatibilidade.

## 4. Ponto 3: controlador, estados e desempenho

Foi executado um diagnóstico QML temporário em um processo Quickshell separado, sem janelas. O binding para `Mpris.players.values` foi inicializado antes da leitura; após descoberta assíncrona, encontrou o Amberol. Arquivos temporários foram removidos. Não houve comando de reprodução ou alteração do estado do player.

Resultado: `desktopEntry = io.bassi.Amberol`; D-Bus `org.mpris.MediaPlayer2.io.bassi.Amberol`; suporte confirmado pela API a play/pause, anterior/próxima, seek, posição, duração, volume e shuffle. Havia título, artista e capa. O estado observado era pausado, posição de 40 segundos e duração de 210 segundos.

Mapeamento da API Quickshell instalada:

| Recurso | API | Condição para usar |
| --- | --- | --- |
| Play/pause | `togglePlaying()` ou `play()`/`pause()` | capacidades correspondentes |
| Anterior/próxima | `previous()`/`next()` | `canGoPrevious`/`canGoNext` |
| Aleatório | propriedade gravável `shuffle` | `canControl` e `shuffleSupported` |
| Volume por player | propriedade gravável `volume` | `canControl` e `volumeSupported` |
| Buscar posição absoluta | propriedade gravável `position` | `canSeek` e `positionSupported` |
| Duração | `length` | `lengthSupported` e valor positivo |
| Metadados | `trackTitle`, `trackArtist`, `trackArtUrl` | aceitar valores ausentes e falha da imagem |

Posição e duração são expressas em segundos na API Quickshell. Os valores brutos MPRIS usam microssegundos; não misturar unidades. `playPause` é o nome de uma operação MPRIS, não o método fornecido por esse wrapper QML.

A documentação oficial explica que ler `position` obtém a posição atual, mas sua progressão normal não dispara continuamente o sinal. Usar Timer local de aproximadamente 250–1000 ms somente com popup aberto e player reproduzindo, atualizando a leitura exibida; não criar chamadas D-Bus recorrentes por shell. Parar ao fechar ou pausar. Seek deve ser enviado ao soltar o arraste, preservando a prévia visual e o vínculo com a faixa/player iniciados no gesto.

Prioridade proposta: selecionar Amberol quando estiver presente; manter a seleção ao pausar. Se estiver aberto sem faixa, recolher. Somente na ausência do Amberol, selecionar um player MPRIS controlável com faixa, preferindo um que esteja tocando; usar desempate estável. Cada ação usa o mesmo objeto mostrado na cápsula. Evitar que o popup troque silenciosamente o alvo durante um arraste.

Manter a cápsula visível quando houver faixa pausada para permitir retomar. Ocultar quando não houver player/faixa, liberando também o espaço reservado pelo host. Metadados incompletos devem ter texto e arte substitutos; ausência de artista isoladamente não pode descartar uma faixa válida.

Substituir a exigência de CPU literalmente zero por ausência de polling contínuo e de animações quando oculto. Marquee, animações e blur têm custo: limitar marquee a interação e largura excedida, ou começar com reticências e tooltip. O blur deve ser opcional, sem exigir mudanças globais no compositor para o MVP.

**Estado:** leitura real da API concluída; comandos graváveis e reações à mudança de estado ainda precisam ser exercitados durante a implementação.

## 5. Ponto 4: instalação, remoção e aceitação

O Omarchy já fornece `omarchy plugin add`, enable/disable, catálogo e remoção; os scripts instalados foram lidos. A remoção distingue symlink de diretório e não precisa apagar o destino de um symlink. Reutilizar esses mecanismos quando compatíveis com o modo de distribuição, em vez de inventar um registro paralelo.

O instalador deve verificar Quickshell e a presença das APIs/host compatíveis, aceitar Amberol nativo ou Flatpak e permitir fallback sem Amberol instalado. Não exigir sudo nem modificar `/usr/share/omarchy`. Validar caminhos existentes antes de criar links; não substituir diretórios ou links de terceiros.

Na máquina Brunoma, obedecer ao WinDoc: arquivos reais dentro do projeto, links nos caminhos do sistema, restauração registrada. Para manter um repositório independente sem duplicar o código, um submódulo Git dentro do WinDoc é uma possibilidade coerente; isso requer registrar também sua revisão e inicialização na restauração. A instalação local deve seguir o protocolo de adoção antes de customizar caminhos ainda externos.

Aplicar configuração por estrutura JSON, preservando campos e posições alheias. Registrar o estado anterior das entradas pertencentes ao Deskband. A desinstalação remove apenas as entradas/links do plugin e deve preservar alterações posteriores do usuário; não restaurar um backup integral antigo por cima de configurações novas. Tornar instalar/desinstalar repetidamente uma operação previsível.

Manter ativação do topo e do dock como destinos explícitos. Para o uso atual, priorizar o dock: o topo está desligado. Reinício do shell não deve ser parte obrigatória de cada instalação; usar recarga/rescan suportado e verificar o componente. Reservar reinício para quando necessário.

Aceitação necessária, com registro de resultados:

1. Sintaxe QML, carregamento e logs sem novos erros relevantes.
2. Player ausente, aberto sem faixa, faixa pausada e faixa tocando; metadados/capa ausentes.
3. Play/pause, anterior/próxima, shuffle, volume específico e seek com verificação do estado resultante.
4. Fechamento e reabertura do Amberol, troca de faixa e mudança de player enquanto o popup está aberto.
5. Cápsula completa nos dois hosts, cliques internos, recolhimento sem espaço residual e popup ancorado à tela correta.
6. Dock com popup aberto, autohide e modo de edição; verificar ausência de conflito com menus, workspaces, apps, bandeja e relógio.
7. Instalação repetida, desinstalação repetida, restauração e reabertura de sessão. Testar instalador em ambiente isolado antes de ativá-lo na sessão real.
8. Segunda tela/orientação vertical somente se declaradas suportadas. Para a primeira versão, declarar suporte horizontal; não prometer todos os cenários sem validá-los.

**Estado:** procedimento e verificações definidos, com leitura dos mecanismos existentes. Não há instalador do Deskband escrito para testar nesta tarefa.

## 6. Plano revisado e confiança

Ordem proposta: criar o componente MPRIS e a cápsula/popup em ambiente isolado; adicionar o modo de conteúdo completo ao host da dock; integrar o seletor e a persistência; validar no dock atual; conferir a apresentação compacta no topo; concluir instalador, remoção e documentação de compatibilidade.

Estimativa subjetiva após a investigação: **95% de confiança na viabilidade da implementação neste computador** e **85% na entrega replicável para as versões explicitamente suportadas**. Esses números não são taxa de testes aprovados nem probabilidade medida. A comunicação foi observada em execução; a adaptação visual, as ações graváveis e o ciclo de instalação ainda têm trabalho e validação pendentes.

O risco de alterar a integridade do Linux é baixo no escopo de configurações do usuário. Existe risco concreto de uma regressão na dock ou de erro QML afetar o shell compartilhado durante desenvolvimento. Reduzir esse risco com execução isolada antes de ativar o plugin e com alteração pequena e reversível no host. Não tratar plugin como isolamento de processo: a UI ativa roda dentro do processo do shell.

## Fontes e limites

- Código local: `dock/DockPanel.qml`, `dock/DockWidgets.js`, `dock/DockModel.js`, `dock/BarWidget.qml`, `dock/components/WidgetPickerPopup.qml`, manifesto, README, licença, configurações e protocolo WinDoc.
- Host instalado: `/usr/share/omarchy/shell/shell.qml`, `services/PluginRegistry.qml`, `services/BarWidgetRegistry.qml`, APIs restritas de plugins, `plugins/bar/Bar.qml`, `Ui/BarWidget.qml`, `Ui/PopupCard.qml`, serviço/widget de mídia e comandos de instalação/remoção.
- API instalada: `/usr/lib/qt6/qml/Quickshell/Services/Mpris/quickshell-service-mpris.qmltypes` e introspecção D-Bus do Amberol.
- Origem pública: https://github.com/rosakodu/omarchy-dock e seu manifesto público.
- Documentação MPRIS Quickshell: https://quickshell.org/docs/v0.3.0/types/Quickshell.Services.Mpris/MprisPlayer/ (referência da série 0.3, cruzada com a API instalada 0.3.1).

A revisão rastreou os caminhos que conectam player, host, configuração e widgets; não representa auditoria linha a linha de todos os módulos não relacionados do WinDoc. Nenhuma funcionalidade do futuro Deskband pode ser declarada concluída a partir desta investigação.


## 7. Implementação posterior: versão 0.1.0

O plugin foi implementado em repositório independente, dentro do WinDoc como submódulo, e ativado na dock. O host agora permite a cápsula visível com largura reativa, botões internos e popup; o alinhamento central dos aplicativos respeita o espaço ocupado à direita. A entrada foi acrescentada ao seletor de widgets. A ativação na barra superior foi verificada no host real com o topo ainda oculto, e a apresentação compacta também foi exercitada isoladamente. Ao terminar, o plugin permaneceu somente no dock e o topo continuou desligado.

As verificações funcionais corrigiram uma premissa da análise inicial: embora o D-Bus anuncie propriedades graváveis, **Amberol 2026.1 ignora Volume e Shuffle e não implementa SetPosition**. Isso foi observado no player e confirmado no código oficial de `src/audio/mpris_controller.rs`, referência `2026.1`:
https://gitlab.gnome.org/World/amberol/-/blob/2026.1/src/audio/mpris_controller.rs

Volume passou a usar exclusivamente os streams PipeWire identificados como Amberol; o volume do dispositivo principal foi comparado antes/depois e permaneceu intacto. Seek usa a operação MPRIS relativa. Quando uma troca de faixa pausada ainda não criou stream/decoder, os controles dependentes aguardam sua inicialização. O aleatório está desativado no Amberol original; foi apresentada ao usuário a alternativa de ampliar o escopo para alterar o próprio player. Outros players continuam usando suas capacidades MPRIS.

Verificações concluídas: sete cenários de instalação/remoção isolados; seleção e formatação em QML; ciclo MPRIS real em barramento isolado (ausência, player vazio, faixa, pausa, desaparecimento e reconexão); regressões existentes da dock; instalação, remoção e reinstalação reais; play/pause, próxima/anterior, seek e volume no Amberol. Cliques reais na cápsula, chevron, área externa, slider de progresso e volume foram exercitados por ponteiro Wayland temporário. Capturas foram inspecionadas para confirmar a ausência de sobreposição entre aplicativos e player.

A música original foi restaurada, pausada perto de 0:40, com volume individual em 100%. A preferência de bandeja preexistente com Rede foi preservada. O futuro suporte a aleatório no Amberol exige uma decisão de ampliação de escopo; não é anunciado como funcional nesta versão. Múltiplos monitores e orientação vertical continuam fora do escopo validado.

## 8. Ajustes da cápsula, progresso e playlist (16/10/2026)

- O fundo neutro foi clareado em 15% sobre o fator visual anterior; mantém tom cinza e contraste com a dock.
- A cápsula da dock ganhou seek arrastável logo abaixo dos controles, com trilho de 3px, knob de 8px e área interativa de 10px. Continua usando `Seek` relativo no Amberol, aplicando o comando ao soltar e bloqueando seek quando o stream/decoder não está disponível. O timer de 500ms só roda durante reprodução e com a cápsula visível. A barra superior preserva 24px e oculta o seek.
- O popup agora mostra a lista rolável da playlist PLS que o Amberol salva em cache. Recarrega ao abrir e observa alterações do arquivo. O texto identifica a origem como playlist salva: o Amberol não publica TrackList nem atualiza essa ordem ao alternar shuffle. As entradas são informativas e não prometem salto direto para uma faixa.
- O shuffle segue desativado para Amberol 2026.1, cujo comando não funciona via MPRIS. Assim não se exibe um controle que aparenta funcionar sem realmente alterar a reprodução.
- Validações desta versão: parser PLS testado para Unicode, ordenação e entradas ausentes; sete testes do instalador; 26 testes do host; nove verificações QML; preflight de instalação; shell reiniciado e ping confirmado. O popup real leu as 41 faixas do cache e foi inspecionado visualmente; não surgiram novos erros QML. O estado do Amberol permaneceu pausado e o popup foi fechado após a inspeção.
