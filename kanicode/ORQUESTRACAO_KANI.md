# Orquestração incremental da Kani local

## Diagnóstico e escopo

A Kani do KaniCode já executava ferramentas em sequência por `kani_modo.py`, com JSON,
receitas, compactação, cancelamento e travas para algumas repetições. O motor integrado
é llama.cpp (`ajudantes.py`, Qwen3.5-4B quantizado), não Ollama. Não foi instalado outro
motor nem criada uma segunda assistente. O caminho do Big Pickle permanece no executor
anterior; `_rodar_pedido` também permite comparar o fluxo anterior no benchmark.

O plano antigo era uma lista textual, com progresso recebido no campo `feitas` da LLM.
O histórico não era um checkpoint transacional. O Cérebro fornece preferências/contexto;
`tarefas_agente.py` acompanha pedidos e pendências, mas não substitui o estado de operações.
Reutilizamos as ferramentas e contratos de código, a ponte da janela, `dados_app.py`,
os eventos `ferr`, `ferr_fim`, `kani_plano`, `agente_uso` e o modelo local existente.

## Componentes

| Arquivo | Responsabilidade |
|---|---|
| `kani_orquestracao.py` | Análise determinística, plano tipado, contexto por etapa, execução, limites, recuperação e replanejamento |
| `kani_estado.py` | SQLite transacional por execução, evidências, eventos, assinatura das operações e bloqueio contra execução concorrente |
| `kani_etapas.py` | Adaptadores das consultas existentes, escopo de caminhos, verificadores e rascunho do Gmail |
| `kani_codigo_etapas.py` | Contratos, edição somente na cópia, diff, sintaxe e testes do `codigo_agente.py` existente |
| `kani_modo.py` | Entrada da Kani integrada ao novo fluxo; JSON estrito e uso detalhado no caminho novo |
| `kanicode.py` | Aprovação humana e retomada pela ponte; continuidade para especialista com evidências e políticas |
| `ui/kani_execucoes.js` | Cartões de checkpoint, argumentos da ação, aprovação/negação e esclarecimentos |
| `benchmark_kani_orquestracao.py` | Comparação reproduzível com inferência real e ferramentas simuladas |

## Decisões de execução

- **DIRECT:** comandos inequívocos, como listar tarefas ou ler um caminho explícito,
  não carregam o modelo. Perguntas simples usam uma decisão com poucas ferramentas.
- **SEQUENTIAL:** sequências explícitas conhecidas são montadas pelo programa;
  as demais podem receber propostas da LLM.
- **ADAPTIVE:** propõe a próxima operação, executa e confere antes de planejar novamente.

Para reduzir a carga do modelo de 4B, o planejador propõe apenas objetivo, ação e
argumentos. O programa atribui identificadores, dependências sequenciais, entradas,
saída, critério e política de tentativa. O plano resultante tem validação estrita.
Respostas inválidas, campos desconhecidos e ferramentas ausentes não são executados.
`feitas` do modelo não participa do progresso; só evidências aceitas pelos verificadores.

O contexto leva pedido, etapa, entradas das dependências, referências de evidências e
resumos limitados. Não retransmite a conversa inteira. O Cérebro continua fornecendo
contexto pertinente, separado das evidências de ferramentas. Conteúdo recuperado é dado
não confiável: nunca concede permissão, não registra conclusão e não substitui políticas.

## Persistência e interrupções

Dados em `<dados>/kani_execucoes/estado.sqlite3`; testes usam dados no D.
`tarefas` contém pedido original, versões do plano, etapa ativa, estados, tentativas,
erros, recursos, autorizações e contadores. `evidencias` conserva resultados externos
separados; `eventos` registra modelo, duração, tokens quando disponíveis e validações.
Conteúdos extensos não são reinjetados integralmente nos prompts.

A intenção é salva antes da chamada com efeito. A assinatura inclui ação e argumentos.
Ao retomar, operações concluídas não são executadas novamente. Se um comprovante conferido
foi persistido antes de uma queda, ele permite reconciliar o checkpoint. Sem comprovante,
uma escrita com resultado incerto fica bloqueada: exige conferência no serviço.
Não existe retry automático de envio, exclusão ou outra escrita possivelmente realizada.

Leituras transitórias admitem até duas tentativas, com pequeno backoff. Entradas inválidas
não são repetidas sem mudança. O replanejamento preserva etapas válidas e possui limite.
Arquivos das dependências têm existência/propriedades reavaliadas antes do próximo uso.
Cache evita I/O duplicado; repetições sem informação nova são interrompidas.

Limites são configuráveis pelo parâmetro `limites=Limites(...)` do `Orquestrador`:
12 passos, 16 inferências, 180 s, dois replanejamentos, contexto de 11.000 caracteres e
resultado externo de até 1 MB por padrão. O orçamento de trabalho persiste na retomada.
O botão Parar impede novas ações. Chamadas HTTP/ferramentas já em curso respeitam seus
timeouts; o cancelamento não desfaz um efeito externo nem garante interrupção instantânea
de uma inferência bloqueante.

O prazo do **Codex**, separado desse orçamento local, passou de 1.200 para 3.600 segundos
em `ajudantes.py` e `codex_processo.py`. Parar continua disponível. Processos já iniciados
conservam o prazo com que foram lançados; recarregar o KaniCode aplica o novo padrão.

## Permissões e capacidades

Caminhos ficam no projeto, nos caminhos explicitamente informados pelo usuário ou em
recursos conferidos. Pedidos de busca no PC autorizam o mapa do D. Caminhos de
credenciais são bloqueados e valores reconhecidos como segredos são redigidos antes
de persistir ou retornar aos prompts. Isso não transforma texto externo em fonte confiável.

O rascunho do Gmail exige endereço confirmado pelo usuário, assunto, texto e aprovação
dos argumentos concretos. O retorno precisa conter o identificador do serviço. A ponte
de aprovação não é uma ferramenta disponível à LLM. Aprovação não vale para argumentos
diferentes. Código permanece na cópia do contrato e usa os verificadores existentes;
testes executáveis exigem aprovação, e a aplicação na origem continua na revisão da interface.

Ferramentas legadas sem adaptador verificável não são executadas livremente pelo novo
fluxo. O encaminhamento já existente ao Claude permanece disponível, com os checkpoints
e a política de aprovação; o encaminhamento não marca a tarefa local como concluída.
Não foram adicionados comandos de shell, execução arbitrária, novos conectores ou dependências.

**Limitações:** Gmail atual não oferece envio com anexo pela Kani. O exemplo de contrato
enviado por e-mail não está implementado ponta a ponta; o fluxo informa a limitação ou
encaminha para ferramenta disponível. Não foi criado um cadastro novo de contatos:
endereços ausentes devem ser fornecidos/confirmados, sem inventar o Pedro correto.
Consulta e seleção de arquivos ambíguos pedem esclarecimento; índice parcial não prova ausência.

## Verificação e benchmark

`py -3.13 verificar.py --area kani` cobre núcleo, ponte, cópia de código e interface
headless. Testes simulam envio, rascunho, falhas e operações sensíveis. Há casos de JSON
inválido, dependências, retomada, crash, comprovante salvo, negação, cancelamento,
limites, loop, arquivo inexistente/modificado, contatos ambíguos e conteúdo malicioso.
Compatibilidade adicional: `test_bigpickle_controle.py`, `test_bigpickle_modo.py`,
`test_bigpickle_ui.py` e `test_opencode_mvp.py`. A suíte do Codex verifica o transporte.

Reproduzir o benchmark sem conectar ao app em uso:

```powershell
$env:PYTHONPYCACHEPREFIX='D:\kanivete_testes\pycache'
py -3.13 benchmark_kani_orquestracao.py --executar --repeticoes 2
```

`--casos adaptativo` restringe a medição ao caso que usa planejamento. O script copia
os binários para o D, lê o mesmo GGUF da instalação e abre seu próprio servidor em porta
livre, fora de 9222/9333. Alterna a ordem dos fluxos entre repetições e encerra somente
seu processo. Nenhum e-mail, arquivo real do usuário ou ação destrutiva é executado.

Sucesso é conferido no simulador, não no `ok` textual. O adaptativo exige leitura do
briefing correto e a data correta; uma busca explícita é opcional quando existe um caminho
válido. Essa correção evita medir uma sequência particular de ferramentas como se fosse
o objetivo. Resultados incluem latência, tokens, erros, recuperação e ações fora do objetivo.
O benchmark usa inferência real, mas não comprova todas as integrações externas ou
generaliza para qualquer tarefa complexa. Relatórios e resultados brutos ficam no D.


## Ajustes de 2026-10-24 (a Kani só perguntava)

Registro real: "pegue o último conteúdo do Alessandro e envie no grupo" virava 6 perguntas seguidas. Causas e correções:
- **Catálogo**: só leituras + perguntar/responder. Agora as ferramentas antigas entram por adaptador (`catalogo`):
  leituras conferem pelo resultado; ações confirmam pelo retorno (`NÃO FEITO` = `NaoFeito`, replaneja sem "incerto");
  `sensiveis` (WhatsApp, apagar, fechar, Drive mover/lixeira) pedem aprovação. Nova `arquivos_recentes` (último conteúdo).
- **Escopo**: o disco D inteiro está liberado (credenciais continuam bloqueadas); `mapa_d`/`buscar_arquivos` partem do D.
- **Contexto**: ferramentas filtradas por assunto (`relevantes`, o 4B tem 8k), memória com Cérebro + pasta do cliente
  (`pastas_de_cliente`, mapa do Pandalab) + caderno, conversa recente (6 falas).
- **Perguntar** só depois de tentar uma ferramenta; resposta curta logo após pergunta/aprovação continua a MESMA tarefa
  (`_ULTIMA`); "pode"/"não" no chat = botão do cartão.
- **Responder** pode dizer "encontrei/enviei" quando há etapa conferida; a resposta final é a fala dela, não o despejo das evidências.
- **DIRECT**: pergunta geral = 1 inferência; consulta = 2 (ferramenta + resposta); falhou → vira ADAPTIVE.
Medido com o modelo real: foto do cliente 25 s/5k tokens; pedido do WhatsApp até a aprovação 26 s/4k; disco 7 s; geral 6 s.
Pendente: "último conteúdo" de carrossel manda 1 slide (devia ser a pasta da peça); datas no `buscar_arquivos`.
