# Anti-regressão em funcionamento

O KaniCode agora tem uma bateria essencial simulada, seleção por impacto e relatório estruturado.
A proposta completa continua em `PLANO_ANTIRREGRESSAO.md`; este guia descreve o que já está implementado.

## Uso

Na pasta do plugin, com Python 3.13:

```powershell
py -3.13 verificar.py --inventario
py -3.13 verificar.py --bateria rapida --workers 2
py -3.13 verificar.py --impacto ui/board.js colab.py --listar
py -3.13 verificar.py --impacto ui/board.js colab.py --workers 2
py -3.13 verificar.py --bateria essencial --workers 2
py -3.13 verificar.py --bateria completa --workers 2
py -3.13 verificar.py --bateria carga --repeticoes 5
```

`--impacto` executa a essencial e acrescenta os contratos afetados e integrações cadastradas nas áreas.
Arquivos centrais exigem os grupos transversais. `--listar` explica a seleção sem rodar testes.
`--arquivos` acrescenta caminhos; o nome de cada arquivo precisa existir dentro do plugin.
Os comandos antigos com `--area` continuam funcionando com o comportamento anterior.

O inventário usa AST e nomes de arquivos; não importa testes desconhecidos.
O catálogo revisado está em `tests/contratos_regressao.json`.
O inventário atual tem 86 módulos classificados: 80 simulados, 5 integrações reais e 1 manual.
A completa seleciona todos os grupos simulados, inclusive os não essenciais. A essencial mantém suas 22 suítes;
as áreas adicionais entram conforme o impacto. Mudanças centrais também selecionam os grupos marcados como transversais.
As 5 integrações reais e o teste manual são listados como fora da bateria, com motivo, e não contam como aprovados.
Eles abrangem modelo semântico real, parser do CLI instalado, três integrações Git com commits de fixture e voz manual.
Os testes Git não são executados no fluxo sem commits. Mudança que exija uma dessas integrações continua incompleta
na seleção por impacto, em vez de receber aprovação apenas pelos testes simulados.
Testes ainda não revisados aparecem como pendentes. Eles não são declarados simulados por inferência.
`--bateria completa` recusa aprovação enquanto houver módulos pendentes de classificação.
Arquivo afetado sem contrato, ou integração exigida com teste pendente, gera resultado incompleto.
Não remover a exigência apenas para fazer a bateria passar: revisar o cenário e cadastrar sua cobertura.

## Evidência e liberação

Cada execução grava `resultado.json` em `D:/kanivete_testes/verificar_*`.
O relatório identifica seleção, motivos, lacunas, tempos, repetições, impressão dos insumos e cada caso executado.
Cada suíte tem dados, configurações, cache Python, temporários, `saida.log` e `casos.jsonl` próprios.
O log é atualizado durante a execução; timeout captura stack e preserva o último caso iniciado.

Uma suíte só fica aprovada se houver fechamento normal, evidência final de todos os casos e nenhum skip/falha.
Saída zero prematura, caso indisponível, falha esperada e relatório incompleto não liberam atualização.
Repetições não escondem falhas anteriores. Arquivos alterados durante ou depois dos testes invalidam a evidência.
Não editar o catálogo ou um teste e reutilizar um relatório da versão anterior.

Para executar a verificação e solicitar o reinício somente se a versão atual for aprovada:

```powershell
py -3.13 verificar.py --impacto ui/board.js colab.py --workers 2 --reiniciar
```

Este é o novo fluxo automatizado de reinício validado. O comando só chama o canal de reinício após aprovação
da essencial + impacto e conferência da impressão atual do projeto. Falha ou evidência incompleta impede a chamada.
O reinício manual existente não foi bloqueado, e o verificador não publica, aplica patches ou reinicia o Kanivete.
O reinício do KaniCode mantém o fluxo que aguarda as tarefas terminarem.

## Isolamento e desempenho

As baterias novas proíbem escritas Python fora de `D:/kanivete_testes` e conexões a serviços reais.
O dispositivo nulo do sistema (`NUL`/`os.devnull`) é permitido porque descarta dados sem criar arquivo.
O cache de modelos do cérebro aponta para uma pasta própria e vazia por suíte; não compartilha o modelo instalado.
Quando o contexto RAG não faz parte do cenário, a fonte é substituída no teste, mantendo real a lógica verificada.
Apenas comunicação de loopback em porta efêmera aberta pelo próprio processo é permitida,
para o asyncio/Playwright. As portas 9222, 9333 e 47613 continuam proibidas aos testes.
Esta auditoria é uma proteção do processo Python, não um firewall do Windows para todos os executáveis filhos.
Os cenários revisados usam motores/serviços simulados; processos locais e renderizadores continuam reais.

`--workers` aceita 1 a 4 processos de suíte independentes; o padrão é 1. Não compartilha instância de App entre workers.
`--repeticoes` aceita 1 a 5 rodadas, preservando todas as evidências. Compare tempos na mesma máquina e carga.
O catálogo aplica prazos menores por grupo; um teste travado encerra somente a árvore criada para aquela suíte.

A carga usa semente fixa e 1, 2 e 8 abas com até 10.000 blocos de texto, passando pelo roteamento real da App.
`dados/carga.json` da suíte registra volume, bytes, eventos/s, p50/p95 do despacho Python e memória rastreada.
O destino da janela é simulado: essas latências não medem atualização do DOM nem o tempo de resposta de um modelo.
Nenhuma meta de desempenho foi transformada em limite universal antes da calibração.

## Próximas ampliações do plano

- Manter o inventário sem módulos pendentes e ampliar os contratos quando surgirem novos comportamentos.
- Separar cenários simulados dos módulos mistos de integração real, preservando também a cobertura externa explícita.
- Unificar roteiros específicos de todos os modelos e serviços; hoje eles também usam mocks já existentes.
- Medir carga até o DOM, cancelamento sob carga e memória após liberação dos objetos.
- Calibrar limiares com várias execuções comparáveis antes de bloquear por desempenho.
- Integrar a evidência a outros fluxos de aplicação que venham a existir; o bloqueio atual vale para o novo reinício validado.

Essas lacunas são explícitas: aprovação da essencial ou da completa simulada não equivale à aprovação das integrações reais.

## O que a revisão das suítes antigas encontrou

- `cenas.py` tipava funções do `kernel32` compartilhado; passou a usar uma DLL própria. O teste nativo usa mocks,
  confere o argumento do temporizador e não agenda eventos no sistema.
- Anexos de contexto sem conteúdo produziam separadores em branco; `licoes.anexo` agora omite as partes vazias.
- Testes de preferências e do Big Pickle consultavam contexto fora do cenário; a fonte RAG desses casos ficou controlada.
- O teste de layout esperava um botão de perfil já removido; passou a verificar o contrato atual de acesso pela lateral.
- O cenário de código usava o protocolo anterior da Kani; agora verifica plano tipado, contrato explícito,
  aprovação antes de rodar testes, encerramento e preservação do arquivo original.
- Temporários de avatares foram movidos para a área de testes no D.

As falhas anteriores permanecem nos relatórios no D; as correções não usam skip nem alteram o resultado reprovado.
