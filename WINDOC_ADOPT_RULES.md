# WinDocAdoptRule

Protocolo obrigatório para agentes que personalizam este Linux/Omarchy. O gatilho
é uma solicitação autorizada de customização do usuário: Hyprland, comportamento
de janelas, interface, temas, terminais, aplicativos, plugins, serviços ou outras
configurações persistentes do sistema. Aplica-se em qualquer diretório de trabalho.
Pedidos apenas de análise, diagnóstico ou parecer permitem leitura e testes
isolados; não autorizam incorporar arquivos nem alterar configurações reais.

## Antes da edição: verificar e incorporar

1. Ler este arquivo e o `AGENTS.md` do WinDoc, localizar os arquivos persistentes
   afetados e verificar seus caminhos reais e vínculos existentes.
2. Se o caminho do sistema já resolver para um arquivo no WinDoc, validar esse
   vínculo e editar o arquivo real dentro do projeto. `windoc adopt CAMINHO`
   reconhece esse caso e retorna sucesso sem mover novamente nem duplicar entradas.
   Um arquivo acessado diretamente no projeto não exige um symlink de volta para
   si mesmo; conferir o caminho de uso no sistema quando aplicável.
3. Se o arquivo estiver fora do WinDoc, incorporá-lo ANTES da customização com
   `windoc adopt CAMINHO`. O comando aceita arquivos/diretórios existentes em HOME,
   move o conteúdo para `adotados/`, cria o symlink na origem e registra o par em
   `symlinks.tsv`. Validar o arquivo, o link e o registro antes de editar.
4. Se o arquivo ainda não existir, criar um arquivo vazio no caminho de origem,
   adotar e validar esse arquivo e só então escrever a configuração solicitada.
   Não mover uma pasta inteira quando a customização requer apenas um arquivo.
5. Symlinks para fora do projeto, destinos conflitantes ou falhas do comando
   exigem examinar a causa e resolver o vínculo antes da edição. Não contornar a
   regra editando a origem e deixando sua incorporação para depois.

O padrão é único: **arquivo real no WinDoc; symlink no caminho esperado pelo
sistema apontando para esse arquivo**. Não criar duas cópias independentes nem
um symlink no WinDoc apontando para um original externo: isso não versiona o conteúdo.
`sync-symlinks.sh` já lê o manifesto; uma adoção não exige acrescentar comandos
manuais de link nesse script.

## Arquivos de sistema e exceções técnicas

Para caminhos fora de HOME, como `/etc`, o comando recusa a movimentação automática.
O agente continua obrigado a avaliar a incorporação: determinar permissões,
proprietário e modo, verificar se o serviço aceita symlinks e registrar o método
reproduzível antes de aplicar a alteração. Usar privilégios somente quando
necessário. Se o componente exigir arquivo físico, versionar uma configuração
sanitizada e o procedimento/script de aplicação em vez de forçar um symlink.
Não editar arquivos empacotados em `/usr/share/omarchy`; usar overrides do usuário.
Não incorporar credenciais, chaves, tokens, caches ou dados temporários no Git.

## Depois da edição: validar e versionar

Validar o componente afetado, conferir que os arquivos novos não são ignorados
pelo Git, registrar a mudança em `config-sistema.txt`, revisar o diff, fazer
commit e push segundo o `AGENTS.md`. A adoção prepara o vínculo; o agente conclui
o versionamento após terminar a customização, sem nova solicitação do usuário.
Dependências adicionadas nessa tarefa devem ter instalação reproduzível registrada
conforme forem identificadas; não é necessário inventariar o sistema inteiro.

## Ativação global

A seção `WinDocAdoptRule` do `~/.codex/AGENTS.md` obriga o agente a consultar este
protocolo mesmo fora do repositório. O arquivo global mantém suas demais regras;
somente essa orientação é documentada aqui, sem copiar suas informações pessoais.
Essa ativação é uma instrução ao agente, não um monitor de alterações no disco:
edições feitas por outros programas ou manualmente não são adotadas automaticamente.
