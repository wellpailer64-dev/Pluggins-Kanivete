# MVP OpenCode no KaniCode

O Big Pickle também está no seletor principal **Quem responde**, com ferramentas do
KaniCode, histórico por pasta e cancelamento: veja `BIGPICKLE.md`. Este guia descreve
o painel separado de teste, que continua sendo apenas uma pergunta independente.

Estado: resposta real validada em 21/10/2026 com OpenCode 1.19.3 e Big Pickle:
o modelo respondeu `teste OK`. Também foi observada a rejeição automática de um pedido
de ferramenta (`auto-rejecting`). Registro: `D:\kanivete_testes\opencode_bloqueio.json`.
Cliente instalado em `D:\Kanivete\Ferramentas\OpenCode\v1.19.3\opencode.exe`;
variável de usuário `KANICODE_OPENCODE_EXE` configurada. Não exige estar no PATH.

O teste direto sem chave na API oficial retornou HTTP 403 / FreeTierError:
`OpenCode's free tier can only be used from within OpenCode.`
A configuração que removia todas as ferramentas também provocou esse erro no cliente
oficial. A versão atual usa permissões `ask` e `run --pure --no-auto`: no modo não
interativo, o cliente rejeita automaticamente os pedidos de ação. Não usa aprovação
automática, não imita ferramentas/cabeçalhos e não modifica o cliente oficial.
Não instala programas, não modifica dependências do projeto e não troca o agente principal.

## Como testar

1. O cliente oficial OpenCode já está instalado no D neste computador.
2. Deixe `opencode.exe` no PATH ou configure a variável de ambiente
   `KANICODE_OPENCODE_EXE` com o caminho absoluto do executável antes de abrir o KaniCode.
   Wrappers `.cmd` não são aceitos; use o executável oficial para evitar passar perguntas pelo shell.
3. Na próxima abertura do KaniCode: Ferramentas → OpenCode · teste Big Pickle.
4. Digite uma pergunta sem dados confidenciais e clique Testar. O painel mostra o resultado.
   Cada pergunta inicia uma conversa independente, com prazo de 60 segundos.

Diagnóstico sem iniciar o cliente: `py -3.13 opencode_mvp.py`.
Teste real opcional: `py -3.13 opencode_mvp.py --pergunta "Responda apenas: teste OK"`.
Os arquivos desta integração não contêm chaves e não pedem uma chave no painel.
O único modelo solicitado é `opencode/big-pickle`, sem fallback para modelo pago.
Disponibilidade, acesso e continuidade da gratuidade dependem do OpenCode.

## Alcance deste MVP

Somente conversa, sem histórico anterior, anexos, arquivos do projeto ou ferramentas do
Kanivete. As ferramentas do cliente exigem permissão, e o modo não interativo rejeita
esses pedidos. `--no-auto` é obrigatório. `--pure` desativa plugins externos.
Se o serviço recusar o pedido, o teste falha sem trocar de modelo nem aprovar ações.
O modelo pode usar o texto enviado para melhoria do serviço. Não envie dados confidenciais.

Execuções, configuração, dados e caches do cliente ficam em
`D:\kanivete_testes\opencode_mvp`. A pasta de trabalho é nova e isolada a cada pedido.
As configurações são passadas só ao processo filho. Não reutiliza a configuração nem as
credenciais de uma instalação pessoal do OpenCode. Não publica sessões automaticamente.
Fechar o painel não cancela a requisição; aguarde a resposta ou o prazo de 60 segundos.
O MVP não oferece streaming nem botão Parar; isso fica para uma integração posterior.

Verificação: `py -3.13 verificar.py --area todas` ou
`py -3.13 verificar.py --area infra --arquivos opencode_mvp.py kanicode.py ui/opencode_mvp.js ui/janela.html tests/test_opencode_mvp.py`.
Os testes simulam o cliente, validam isolamento, modelo fixo, erros, prazo e concorrência.
Eles não substituem os testes reais descritos no início. A versão 1.19.3 foi conferida:
`permission.asked` recebe `reply: reject` em `run` não interativo sem `--auto`.
Referência: https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/cli/cmd/run.ts
Problema do provedor: https://github.com/anomalyco/opencode/issues/50627

Documentação oficial consultada:
- https://opencode.ai/v2/docs/console/api/inference
- https://opencode.ai/docs/cli/
- https://opencode.ai/docs/config/
- https://opencode.ai/docs/permissions/
