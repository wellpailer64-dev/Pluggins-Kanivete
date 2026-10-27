# Plano de construção anti-regressão do KaniCode

Status: núcleo implementado e inventário das suítes antigas revisado. A bateria completa simulada agora
abrange 80 módulos; 5 integrações reais e 1 manual ficam explicitamente separadas. Bateria essencial,
seleção por impacto, relatórios, carga Python e reinício validado estão disponíveis em `ANTIRREGRESSAO.md`.
As metas e ampliações abaixo continuam sendo o plano, sem pressupor cobertura total já concluída.
Objetivo: detectar rapidamente quando uma feature quebra um comportamento que já funcionava,
antes de aplicar a atualização no KaniCode em uso. Os testes devem usar modelos e serviços simulados.
Nenhuma bateria garante ausência de defeitos; a entrega precisa informar exatamente o que foi coberto.

## 1. Aproveitar a base existente

- `verificar.py`: sintaxe Python/JS/HTML e execução por área; hoje executa módulos em sequência,
  captura a saída até o processo acabar e usa prazo de 180 s por comando filho.
- `teste_isolado.py` e `dados_app.py`: dados separados no D, proteção dos diretórios reais e da porta 9222.
- `tests/test_verificar.py` e `tests/test_ambiente_isolado.py`: cobertura do próprio verificador e isolamento.
- `tests/test_abas_ui.py`, `tests/test_board_ui.py`, `tests/test_colab.py`, `tests/test_colab_ui.py`:
  histórico, eventos, Board e acordo entre chats.
- `tests/test_ponte_nativa.py` e `tests/apoio_ponte_nativa.py`: ponte WebView2 real com motor simulado.
- `tests/test_codex_eventos.py`, `tests/test_codex_processo.py`, `tests/test_mensagens.py` e
  `tests/test_passagem.py`: eventos, processos, fila e continuidade entre modelos.

O benchmark `benchmark_kani_orquestracao.py` usa um modelo local real: serve como avaliação separada,
não como teste simulado rápido nem como requisito de toda edição.

## 2. Contrato de compatibilidade por comportamento

Criar um catálogo que ligue comportamento, arquivos envolvidos, teste e criticidade.
Registrar tanto a feature nova quanto os comportamentos antigos que ela deve preservar.
As expectativas vêm do comportamento aprovado do produto, não de copiar a implementação atual.
Uma mudança intencional de UX atualiza o contrato e o teste correspondente; não elimina a cobertura.

| Comportamento preservado | Cenário mínimo de regressão |
| --- | --- |
| Conversar em qualquer modelo | Enviar, transmitir progresso, terminar, recuperar histórico e apresentar erro útil |
| Isolar abas | Intercalar eventos de duas abas, trocar a ativa e conferir que mensagens, tokens e logs não se misturam |
| Preservar mensagens | Enfileirar durante execução, cancelar, retomar e garantir que não há envio perdido ou duplicado |
| Parar e reiniciar | Cancelar um motor travado; reinício solicitado espera tarefas; histórico permanece recuperável |
| Trocar de modelo | Entregar o contexto pendente uma vez, manter a conversa e não perder contexto se o envio falhar |
| Board e Colab | Ler logs sem ativar aba; preservar rolagem; aprovar a mesma revisão; rejeitar arquivos sobrepostos; integrar após ambas as entregas |
| Persistir estado | Gravações concorrentes preservam campos alheios; estado antigo abre; falha de escrita não produz sucesso falso |
| Respeitar projeto | Cada aba usa sua pasta; mudar projeto não continua um Colab no destino errado |
| Renderizar respostas | Markdown, código, imagens e textos grandes não quebram layout ou executam conteúdo como instrução |
| Falhar sem afetar outras tarefas | Erro, timeout ou serviço ausente numa aba não paralisa as demais |

Voz, celular, conexões, tarefas e demais recursos entram no catálogo com seus próprios testes.
Serviços externos devem ser simulados; a seleção fixa essencial não precisa iniciar todos os recursos do produto.

## 3. Baterias por custo e risco

Metas abaixo são iniciais, não resultados medidos. Calibrar no PC do Pailer na primeira etapa,
separando execução fria, execução aquecida e tempo de preparação. Não reduzir cobertura para caber no prazo.

| Bateria | Quando executar | Conteúdo | Meta inicial de duração total |
| --- | --- | --- | --- |
| Rápida | Durante a construção da feature | Sintaxe e contratos puros dos arquivos tocados | Até 10 s, aquecida |
| Essencial + impacto | Antes de considerar uma feature pronta | Fluxos essenciais fixos, áreas afetadas e suas integrações | Até 60 s, aquecida |
| Completa simulada | Antes de aplicar uma versão que reúna features | Todos os testes simulados elegíveis, incluindo interface e ponte nativa | Até 5 min |
| Carga e resiliência | Mudanças em eventos, filas, persistência, renderização ou Colab | Rajadas, concorrência controlada, falhas e métricas | Orçamento definido após a medição inicial |

O comando atual `py -3.13 verificar.py --area <area>` continua funcionando durante a migração.
`--area todas` é o inventário amplo atual, não deve ser rebatizado como bateria totalmente simulada:
primeiro classificar testes manuais, dependências locais e eventuais efeitos externos.

## 4. Seleção por impacto sem esquecer o que já funciona

Criar um manifesto declarativo, por exemplo `tests/contratos_regressao.json` (arquivo futuro), com:
id do comportamento, área, arquivos/recursos envolvidos, testes, criticidade, tipo de ambiente,
prazo, dependências de execução e motivo de eventual exclusividade.

A seleção será a união, sem duplicações, de:
1. Bateria essencial fixa, independente da feature alterada.
2. Testes dos arquivos e comportamentos alterados.
3. Testes de integração dos componentes que recebem esses eventos, dados ou chamadas.

Mudanças em `kanicode.py`, `ui/janela.html`, `ui/abas.js`, passagem entre modelos ou protocolo de eventos
exigem a bateria transversal de conversa, fila, troca de abas, renderização e ponte.
Mudanças em CSS, ordem dos scripts ou nomes/classes usados por outros módulos também têm impacto.
Imports ajudam a localizar relações, mas não substituem o manifesto: há wrappers JS e chamadas dinâmicas.

Arquivo de produção sem classificação torna a seleção incompleta e exige classificar ou rodar a bateria ampla pertinente.
Mostrar antes de executar quais testes foram selecionados e por quê. Não depender de commit, push ou reset:
aceitar uma lista explícita de arquivos; diff local é um auxílio opcional.

## 5. Simulador determinístico de modelos e serviços

Construir um motor de teste reutilizável para Claude, Codex, Kani e Big Pickle,
preservando os formatos reais de entrada/saída e os adaptadores existentes.
Simular a fronteira com o modelo ou serviço; manter reais a lógica da App, fila, persistência,
roteamento por aba e renderização que o cenário pretende verificar.
Um teste que substitui justamente a lógica que pode quebrar não comprova a integração.

Roteiros sintéticos de eventos devem cobrir:
- Resposta curta, transmissão em vários blocos, ferramentas com entrada/saída e resposta final.
- Erro antes/depois de um bloco parcial; cancelamento no meio de uma ferramenta; conclusão atrasada.
- JSONL fragmentado, Unicode, linha inválida e eventos desconhecidos, sem derrubar a sessão inteira.
- Eventos duplicados ou atrasados: rejeitar quando o contrato exigir; nunca gerar duplicação silenciosa de efeito.
- Duas ou mais abas trabalhando; plano Colab revisado enquanto existe uma aprovação antiga.
- Timeout, serviço indisponível, arquivo de estado incompleto e falha de gravação.

Usar relógio controlável, barreiras e eventos de sincronização para testes de lógica.
Evitar sleeps fixos e dependência do escalonamento do Windows.
Variantes aleatórias precisam de semente registrada e roteiro reproduzível.
Fixtures devem ser sintéticas, pequenas e sem conversas, tokens ou arquivos reais de clientes.
Adicionar testes de contrato que detectem quando um adaptador muda e o simulador fica desatualizado.

## 6. Desempenho sem sacrificar isolamento

- Reutilizar um Chromium por grupo de testes compatíveis; criar contexto/página separados por cenário.
- Paralelizar apenas suítes independentes, em processos limitados; nunca compartilhar App, estado,
  porta, perfil de navegador ou diretório de dados entre workers.
- Medir execução sequencial e comparar antes de ativar paralelismo; mais processos podem piorar a latência.
- Usar portas locais efêmeras do próprio harness. A porta real 47613 dos chats não deve ser usada por testes.
  Tornar o transporte configurável em modo teste e comprovar que a configuração de teste não vaza para produção.
- Nenhuma bateria rápida chama API paga, modelo real, GPU, microfone, fala, e-mail ou outras integrações reais.
- Registrar a impressão dos arquivos, testes, fixtures e configuração que produziram cada resultado.
  Alteração posterior invalida a evidência correspondente; não reaproveitar um resultado antigo como aprovação atual.
- Cachear preparação cara somente quando a identidade dos insumos e o isolamento forem verificáveis;
  não pular uma execução de comportamento apenas porque o nome do teste não mudou.

Toda saída, cache e dado temporário fica em `D:/kanivete_testes`, com pasta exclusiva por execução/worker.
Python é `py -3.13`; não instalar dependências nesta construção sem autorização específica.
Proibir acesso aos dados reais, porta 9222, diálogos nativos e automação do app do usuário.
Quando um cenário exigir o Kanivete, usar somente a instância isolada de teste na 9333.
O teste WebView2 do KaniCode deve continuar independente do Kanivete em uso.

## 7. Carga e oráculos de desempenho

Começar com 1, 2 e 8 abas simuladas; transmitir lotes de 1.000 e 10.000 eventos,
incluindo mensagens grandes e saídas de ferramentas. Registrar número de mensagens,
eventos e bytes: apenas contar eventos não caracteriza a carga.

Verificar primeiro a correção: nada perdido ou duplicado, isolamento entre abas, ordem contratada,
estado final correto, cancelamento atendido e fila esvaziada.
Depois medir com relógio real: duração total, eventos/s, p50/p95 de entrega até atualização do DOM,
tempo de cancelamento e memória antes/durante/depois. Relógio falso não mede desempenho.
Medir separadamente estado em memória, persistência e UI; evitar que o custo de avaliar JS por evento
domine o benchmark. Enviar lotes e usar marcadores no próprio fluxo.

Criar a referência com pelo menos cinco execuções comparáveis. Medir execução fria à parte.
Como hipótese inicial, investigar piora repetida de p95 acima de 20%, usando também um limite absoluto
calibrado para não reprovar oscilações de poucos milissegundos. Não aceitar degradação progressiva
de memória apenas porque a máquina ainda tem RAM disponível.
Esses limiares só viram bloqueio depois de validar variabilidade e carga de fundo no PC.

O Board pode futuramente limitar os nós DOM visíveis e manter histórico recuperável,
caso a medição mostre necessidade; isso não autoriza descartar mensagens ou logs.

## 8. Diagnóstico e critérios para aplicar uma atualização

Estender o relatório atual com resultado estruturado por caso e saída incremental.
Informar: aprovado, falhou, ignorado, indisponível ou timeout, com motivo, duração,
seleção por impacto, semente e comando para reproduzir.
Guardar falha esperada/observada, eventos relevantes, captura de tela e erro JS quando aplicável.
Em timeout, capturar a última etapa e diagnóstico antes de encerrar somente os processos criados pelo teste.
Uma ponte simulada que devolve objeto tratado como Promise precisa falhar por prazo, não travar toda a bateria.

Condições de liberação:
- Sintaxe válida e nenhum erro inesperado de console/ponte.
- Todos os casos críticos essenciais e de impacto aprovados; cenário crítico indisponível/ignorado não conta como aprovação.
- Nenhuma escrita ou chamada externa fora do isolamento.
- Desempenho dentro dos limites já calibrados quando a mudança afetar caminho medido.
- Contrato e teste atualizados para mudanças intencionais de comportamento.

Falha intermitente continua sendo falha: uma repetição serve ao diagnóstico e deve preservar o primeiro resultado.
Testes não críticos temporariamente separados da liberação precisam de responsável, motivo e prazo de correção.
Uma execução simulada aprovada não comprova qualidade das respostas reais de um modelo nem integração real com serviços.
Avaliações reais ficam identificadas, separadas e só são executadas quando pertinentes e autorizadas.

O verificador deve retornar código de falha e impedir o fluxo automatizado de aplicar/reiniciar quando não aprovado.
A implementação deve ligar essa decisão ao ponto concreto de aplicação; gerar um relatório sozinho não cria bloqueio.
Preservar o reinício autorizado que aguarda tarefas, sem interferir no Kanivete ou em outros programas.

## 9. Ordem de construção e entregas revisáveis

| Etapa | Entrega | Critério de pronto |
| --- | --- | --- |
| 1 — Inventário e referência | Classificar testes existentes; catálogo inicial; tempos frios/aquecidos e lacunas | Cada comportamento crítico tem cenário nomeado ou lacuna explícita; relatório reproduzível no D |
| 2 — Simulação comum | Roteiros de motores, relógio, falhas e transporte isolado | Mesma semente repete o resultado; nenhuma conta, serviço ou dado real é acessado |
| 3 — Essencial + impacto | Manifesto validado, seleção explicada e grupo transversal | Mudar arquivo central seleciona integrações; arquivo desconhecido não produz aprovação incompleta silenciosa |
| 4 — Velocidade e diagnóstico | Reuso seguro de navegador, paralelismo limitado e relatório incremental | Isolamento comprovado; ganho medido; timeout localiza cenário e deixa recursos de teste encerrados |
| 5 — Carga e bloqueio de aplicação | Baseline calibrada, carga determinística e ligação com aplicar/reiniciar | Falha deliberada em comportamento essencial bloqueia a aplicação; versão corrigida passa |

Em cada etapa usar contrato próprio com lista explícita de arquivos liberados e preservar alterações locais existentes.
Começar estendendo `verificar.py`, `teste_isolado.py` e os testes atuais; novos auxiliares só quando reduzirem duplicação.
Não reconstruir toda a infraestrutura de uma vez e não adicionar framework novo por padrão.

## 10. Regra operacional para toda feature

1. Identificar o comportamento novo e os antigos expostos à mudança.
2. Para bug: reproduzir com teste que falha antes da correção. Para feature: escrever cenários de aceitação
   e preservação proporcionais ao risco; evitar testes triviais que apenas repetem o código.
3. Implementar dentro do contrato e conferir sintaxe.
4. Executar bateria essencial + impacto; usar completa/carga conforme o escopo.
5. Registrar evidências e limitações. Aplicar somente a versão efetivamente verificada.

Próxima ampliação recomendada: medir carga até o DOM e memória após liberação, calibrar limites de desempenho
e separar os cenários simulados que ainda dividem módulo com uma integração real.
O inventário das suítes existentes, a essencial e a seleção por impacto já estão implementados.
