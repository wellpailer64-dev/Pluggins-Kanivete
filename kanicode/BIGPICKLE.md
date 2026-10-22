# Big Pickle como agente do KaniCode

Na próxima abertura do KaniCode, escolha **Big Pickle** no seletor **Quem responde**.
O painel Ferramentas → OpenCode · teste Big Pickle permanece como diagnóstico separado.
Não é necessário mudar o modelo do Claude nem cadastrar uma chave para o Big Pickle.
Cliente validado: OpenCode 1.19.3 no caminho configurado em `KANICODE_OPENCODE_EXE`.
Também lê essa variável do perfil do usuário no Windows, sem exigir reiniciar o Windows.

## Modo nativo para código (2026-10-21) — `pickle_agente.py`

Código e conversa vão para o OpenCode com as ferramentas PRÓPRIAS dele (ler, procurar, editar, conferir), como o Codex.
Pedidos sobre o app (KANIVETE, KaniBrowser, disco, demandas) continuam na ponte em etapas abaixo (`para_ponte`).
Segurança, em camadas:
- Sempre numa CÓPIA: git worktree em `D:\kanivete_testes\codigo_agentes\sessao_*\arvore` (~0,6 s), com as mudanças não
  commitadas da origem copiadas por cima. Arquivos ignorados pelo git (segredos, credenciais) nunca entram na cópia.
- `--dir` + `PWD` apontando a cópia: sem isso o OpenCode herdava o PWD do Git Bash e editou a ORIGEM no teste.
- Permissões: `external_directory` negado; bash só `py_compile`, `node --check`, `unittest` e git de leitura; sem web.
- Trava do KaniCode: qualquer ferramenta com arquivo fora da cópia encerra a tarefa na hora.
- A revisão é a de sempre (`codigo_agente.Contexto`, botão "Revisar e aplicar" na conversa): só .py/.js/.html/.css/.json/
  .md/.txt, nada de AGENTS.md/CLAUDE.md/dependências; o Aplicar recusa se a origem mudou enquanto ele trabalhava.
- Sem commit/push/instalar/apagar (as exclusões não são levadas para a origem).
Medidas: bug simples 13 s; pergunta no CANIVETE (624 arquivos) ~2 min. Teste: `tests/test_pickle_agente.py`.
Falha na ponte: uma frase ao Pailer; detalhes técnicos no andamento (`pickle_progresso`).

## O que ele aprendeu a fazer

- Consultar discos, pastas, arquivos de texto, resumo Git e mapa do projeto.
- Consultar programas abertos e o resumo textual do Kanivete e das abas do KaniBrowser.
- Abrir o app Kanivete por pedido explícito, conferindo primeiro as janelas para evitar outra instância.
- Abrir ferramentas, clicar nos itens visíveis do Kanivete e abrir um site no KaniBrowser.
- Consultar as receitas da Kani e trabalhar em até dez consultas ao modelo por tarefa: observar, agir, conferir.
- Editar código em uma cópia separada: preparar contrato, ler, substituir trecho único, criar arquivo declarado,
  conferir sintaxe, executar unittest declarado e mostrar diff. A Kani usa a mesma ponte.
- Mostrar uma barra expansível com as mudanças na cópia. Aplicação na origem só pelo botão de revisão humana.
- Reconhecer limites e indicar a seleção de Claude/Codex quando faltar uma capacidade.

Não recebe execução livre de Python, shell ou JavaScript. Não tem ferramentas para
apagar arquivos, fechar programas, reiniciar apps ou editar vídeo/imagem. Código é editado somente na cópia.
N?o h? visão por imagem nem anexos nesta integra??o. `/clear`, `/nova` e `/new`
começam outra conversa, como o bot?o Nova conversa, preservando o histórico anterior.
Os demais comandos `/` são recusados. Em Planejar, somente as ferramentas de leitura ficam
disponíveis, e ações fora da lista são recusadas antes de executar.
Estas instruções orientam o modelo a cada pedido; não alteram seus pesos nem treinamento.

## Conversa, dados e cancelamento

O histórico pertence ao Big Pickle e à pasta ativa. Trocar para a Kani ou Claude não
envia suas conversas ao provedor. Trocar de pasta muda o contexto; reabrir mantém a
conversa. Nova conversa começa outra sem apagar o arquivo anterior.
Registros: `D:\Kanivete\KaniCode\conversas_pickle\<id>.jsonl`; IDs por pasta em
`estado.json` (`pickle_sessoes`). O histórico mostrado tem até 400 eventos; contexto
do modelo usa as últimas 16 mensagens, com o mesmo limite de tamanho usado pela Kani.

O provedor recebe o pedido, instruções, caminho da pasta, histórico desta conversa
e os resultados das ferramentas chamadas. Não recebe automaticamente o caderno privado
da Kani. Conteúdo consultado pode incluir dados pessoais: não use para dados confidenciais.
Somente o modelo gratuito `opencode/big-pickle` é selecionado, sem fallback pago.
A gratuidade e a disponibilidade dependem do OpenCode. O programa não presume uso ilimitado.

Parar interrompe a consulta ao cliente e impede a próxima ação. Uma ferramenta que já
começou pode terminar; Parar não desfaz ações feitas. Cada chamada ao modelo tem prazo
de 60 segundos. A Kani local não é carregada para atender ao Big Pickle.

## Implementação e validação

`bigpickle_modo.Motor` pede uma decisão JSON ao cliente oficial pelo stdin.
O agente tem instrução própria (`Motor.sistema`), contendo apenas as ferramentas
liberadas. O processo usa `ambiente(agente=True)`; a instrução "somente conversa"
fica restrita ao painel de diagnóstico. Nunca reutilize essa instrução no agente.
Pedido para abrir o Kanivete não pode ser concluído sem uma observação/ação da rodada:
uma resposta sem evidência recebe uma correção e, se persistir, falha sem inventar sucesso.
O estado dito em conversas antigas não serve de comprovação do estado atual.
`kani_modo.rodar` valida a ação contra uma lista explícita e usa o executor local já
existente. O OpenCode nativo roda isolado, com `--pure --no-auto`, recusando execução
de ferramentas próprias; a ponte do KaniCode executa só as ações da lista liberada.
Não passa pedidos do usuário pelo shell. Resposta inválida falha sem executar a etapa.

`App._pickle_rodar` faz a ponte com eventos, voz, histórico e cancelamento da janela.
Não encaminha automaticamente pedidos ao Claude. A bolinha usa o selo BP.
Verificar: `py -3.13 verificar.py --area pickle`.
Testes: `tests/test_bigpickle_modo.py`, `tests/test_bigpickle_ui.py` e regressões da Kani/MVP.
Teste real documentado: consulta de espaço no D chamou `espaco_disco` e respondeu com o
valor observado (`D:\kanivete_testes\pickle_agente_real.json`). Nenhuma conexão à porta 9222
foi feita para esse teste. Testes de interface usam página isolada e API simulada.
Correção validada com pedidos naturais, sem o usuário citar nomes técnicos de ferramentas:
"Pode abrir o KANIVETE para mim?" chamou `abrir_kanivete`; "Que programas estão abertos?"
chamou `programas_abertos`. Modelo real, ambiente simulado sem tocar no app em uso:
`D:\kanivete_testes\pickle_pedidos_naturais.json`. Abertura efetiva e não duplicação são
verificadas separadamente com funções simuladas nos testes automáticos.

## Código na cópia

Arquivos ficam em `D:\kanivete_testes\codigo_agentes\sessao_*\trabalho`; originais da sessão ficam em `base`.
O contrato lista caminhos relativos, até 80 arquivos/20 MB; arquivos precisam ser texto UTF-8, até 2 MB cada.
Regras do projeto, dependências, links, travessia de diretórios e exclusões são bloqueados pela ponte.
Testes têm prazo de 30 segundos e bloqueio da porta 9222. Uma pasta separada não é uma VM: unittest executa código local.
Não há shell livre para o modelo. Aplique somente depois de revisar em **Ferramentas → Revisar código isolado**.
O botão confere revisão, conflito na origem, sintaxe e falha conhecida de testes antes de gravar. Planejar não libera escrita.
Não aplica silenciosamente nem transfere a tarefa automaticamente para outro modelo.
Verificar a ponte: `py -3.13 verificar.py --area codigo`.

Na validação real de código em 21/10/2026, o modelo preparou a cópia e leu o arquivo, mas uma etapa
terminou sem texto confirmado pelo OpenCode. O original permaneceu intacto. O fluxo completo da ponte,
para Kani e Big Pickle, passou com decisões simuladas e unittest real na cópia; isso não garante que
o provedor gratuito conclua toda tarefa. Não houve fallback pago nem aplicação parcial na origem.

## Balanceamento e diagnóstico (21/10/2026)

- `pickle_controle.py` seleciona ferramentas por intenção: código, navegação ou consulta. Pedidos mistos mantêm os grupos necessários.
- O contexto preserva o pedido, correções e os dois resultados mais recentes; resultados antigos são abreviados e os argumentos
  de ações já solicitadas não são reenviados integralmente. Não use um resumo abreviado como trecho exato de substituição: releia.
- Contexto máximo de 24 mil caracteres, sem apresentar caracteres como tokens. O OpenCode também acrescenta sua orientação interna.
- No agente, ferramentas nativas ficam em `deny`, com apenas `read: ask` anunciado. `--no-auto` recusa o pedido de leitura:
  a ponte continua responsável pelas ações. Esse anúncio mínimo atende ao provedor sem expor todas as ferramentas nativas.
  O painel de diagnóstico de conversa mantém configuração própria.
- Orçamento padrão: **10 consultas, 180 segundos e 60 mil tokens informados pelo cliente**. Recuperação também conta como consulta.
  Antes da próxima consulta considera-se o último consumo medido; ao receber uma resposta que excedeu o orçamento, nenhuma nova
  ação dessa resposta é executada. Uma requisição em voo pode ultrapassar o teto de tokens; falhas sem medição podem ter consumo desconhecido.
  Consultas respeitam o tempo restante; testes da cópia recebem o cancelador do orçamento. Outras ações já iniciadas podem terminar.
- `rodar(..., limites={"etapas":5,"segundos":90,"tokens":30000})` permite limites menores; não muda as permissões nem habilita modelo pago.
- Uma única correção automática por tarefa: resposta vazia, JSON/decisão inválidos, ferramenta nativa comprovadamente recusada ou
  resposta prematura sem a observação exigida. A ação ainda não foi entregue ao executor. Ações concluídas não são repetidas.
  Cota do provedor, falha de transporte, prazo, cancelamento e ferramenta nativa com resultado incerto não provocam repetição automática.
- Progresso, falhas, resultados parciais e diffs ficam na conversa. Ao continuar uma tarefa parcial, revise a cópia existente antes de preparar outra.
- Medidas sem prompts/código: `D:\kanivete_testes\opencode_mvp\diagnostico_agente.jsonl` (tipo da falha, consultas, caracteres, tokens e tempo).
  Os registros de conversa mantêm orçamento e etapas concluídas. A medição inclui também consultas que falharam, quando o cliente informou uso.
- Cache Python distinto em cada execução de unittest impede reaproveitar código antigo quando uma correção mantém o tamanho do arquivo.

Após essas mudanças, o teste real de soma.py completou preparação, leitura, substituição, unittest e revisão em **6 consultas,
16.285 tokens e 34,82 s**, sem recuperação e com a origem intacta. Esses números são deste teste, não uma garantia por tarefa.
Testes simulados cobrem falhas, limites, cancelamento e a proibição de executar duas vezes uma ação concluída.

Configuração conferida na [documentação oficial de permissões do OpenCode](https://docs.opencode.ai/docs/permissions/).
Verificar: `py -3.13 verificar.py --area pickle --arquivos tests/test_codigo_agente.py codigo_agente.py tests/test_layout.py`.
