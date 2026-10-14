# System Icon Tray — base minimalista

Atualizado em 14/10/2026. Estado: escopo revisado; implementação pendente.

## Entrega única

Implementar o ícone da System Icon Tray em uma versão minimalista, como base
para evoluções posteriores. O ícone deve ocupar exatamente a posição atual do
ícone de previsão do tempo na barra inferior.

Essa posição existente é a referência de layout. Não criar outra posição nem
um espaço adicional para a bandeja. A futura implementação deve resolver a
substituição visual do ícone nessa posição, sem presumir novos comportamentos
para o clima.

## Base conhecida

- `shell/dock-settings.json` configura `omarchy.apps` e `omarchy.weather` como
  widgets da dock e mantém o modo Windows ativo.
- `dock/DockPanel.qml` contém o layout e a infraestrutura de widgets existente.
- Reaproveitar essa infraestrutura para integrar o ícone com o mínimo de mudanças.

## Limites da entrega

O escopo atual termina no ícone e em sua integração visual à dock. Pop-up, grid,
PIN, migração de outros widgets, painel de configurações, checkboxes e novas
preferências não integram esta entrega. Não implementar ações de clique ainda
não definidas. Funcionalidades adicionais exigem uma nova definição de escopo.

## Sequência mínima

1. Localizar no layout o espaço atualmente ocupado pelo ícone do clima.
2. Integrar o ícone base da System Icon Tray nesse mesmo espaço.
3. Verificar posição, aparência e carregamento da dock; registrar e versionar.

São passos de uma única entrega, não um plano de múltiplas camadas funcionais.
Esta revisão atualiza apenas a documentação. Nenhuma implementação foi iniciada.

## Referência para próximas interações

Este documento substitui o plano anterior. Seguir o escopo aqui descrito e as
regras gerais de `AGENTS.md`, sem recuperar funcionalidades de versões anteriores
como requisitos ativos. A validação da futura implementação deve corresponder
às mudanças efetivas; a revisão documental não exige recarregar a interface.
