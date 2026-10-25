# Cérebro do Pailer — método

Ferramenta do Claude em primeiro lugar (consulta rápida do que sei sobre o Pailer); para o Pailer, a vitrine de como
o cérebro está evoluindo (Perfil › Cérebro). Código: `perfil_cerebro.py`; interface: `ui/cerebro.js`; ferramenta
`cerebro` em `mcp_equipe.py`. Dados em `<DADOS>/cerebro/` (neuronios.json, vida.json, arquivo.json, atividade.jsonl,
historico.jsonl).

## Kani
A área **Kani** reúne registros de assunto `kani_local` e de autoria comprovada da Kani.
O grupo **Aprendizados** contém lições; falar da Kani não prova autoria. Regras e projetos
continuam nos respectivos grupos. **Ferramentas** mostra o catálogo atual de `FERRAMENTAS`
de `kani_modo.py` e `codigo_agente.py`, lido sem executar o motor. Cadastro não comprova uso
bem-sucedido nem disponibilidade de conexão/permissão. É referência do código, não aprendizado.

## De onde vêm os neurônios
- Memórias do Claude (todas as contas e projetos), lições do Codex, preferências curadas, o perfil e os
  neurônios PRÓPRIOS (`guardar`). Organização: lobo (área) › grupo (jeito de trabalhar / projetos / saber) › neurônio.
- Ligações: `[[links]]` e `ligar` (fortes) + os 3 de assunto mais parecido (TF-IDF). Consultar acende o assunto e
  espalha por até 2 passos, sempre mais fraco que quem puxou.

## Quando CONSULTAR (só quando falta)
### PC e mapa vivo
Área/assunto **PC** › **Caminhos do PC**: o mapa vivo e até 24 referências às pastas principais já indexadas no
disco D. Cada referência abre o mapa completo na pasta correspondente; o cartão mostra cobertura parcial e
saúde do monitor. São referências de navegação, não memórias copiadas da árvore inteira nem preferências.

A raiz é consultada no índice existente com limite de resultados e cache de 15 s, sem percorrer o disco ou
iniciar outro indexador. Com PC em uso no painel, as referências se atualizam a cada 20 s; a topologia do cérebro
só é recalculada quando a lista muda. Subpastas e arquivos ficam no mapa completo, consultados ao navegar.

**Organização e aprendizados** reúne regras/procedimentos/lições já registrados sobre pastas e materiais.
A classificação automática usa indicações claras do título/descrição; pode ser confirmada com
`classificar(..., ambitos=['pc'], ...)`. As observações curadas de organização de clientes continuam identificadas
como observações ainda não validadas individualmente. Não aprender padrões de caches, temporários ou arquivos
gerados e não reorganizar materiais por iniciativa própria.

Conexões: referências de pastas → mapa; organização → mapa; projeto com pasta existente → referência da pasta
principal que a contém. A conexão de projeto é estrutural, com caminho conferido; não deduz equivalência entre
pastas renomeadas nem reescreve sua ficha. Referências vivas não entram na faxina por idade/semelhança.
Para os agentes: `mapa(ambito='pc')` → ferramenta `mapa_d` (buscar/listar/status) quando precisar do caminho atual.
Só resultado com fonte pode virar aprendizado; a lista de pastas não é contexto fixo de nenhuma IA.

Antes da área visual, cada neurônio distingue **assunto** (KANIVETE, KaniCode, Kani local, Pailer/geral),
**finalidade** (orientar o trabalho, acompanhar projeto, evitar repetir erro, como executar, consultar informação)
e **quem registrou** (só com evidência; desconhecido continua "não registrado"). Falar da Kani não prova que ela
aprendeu/escreveu aquilo. Conhecimento é compartilhado pelos agentes; a autoria não restringe quem pode usá-lo.

Os filtros Assunto, Finalidade e Registrado por estão no painel e combinam entre si. Um neurônio pode tratar de
dois sistemas quando for uma integração real. Os rótulos antigos são sugestões **automáticas**, por nomes
explícitos no conteúdo, sem modelo ou chamada adicional. Caminho de arquivo não prova assunto. Sem indicação
segura: **A classificar**. Essa organização automática não confirma fatos nem autoria.

`classificar(ref, ambitos, finalidade, origem, certeza, agente opcional)` confirma a organização em
`cerebro/classificacao.json`, sem reescrever memórias importadas. Exemplo: `{"acao":"classificar","ref":"pro:…",
"ambitos":["kani_local"],"finalidade":"aprendizado","agente":"kani","certeza":"verificado",
"origem":"registro da execução da Kani que produziu a lição"}`. Não inventar o agente; omita se não souber.

`mapa` e `consultar` aceitam `ambito`: use o sistema pertinente para reduzir o resultado e evitar misturas.
O filtro também limita os vizinhos puxados pela consulta. Ligações por semelhança e sugestões de juntar não
cruzam sistemas distintos; `ligar` explícito pode registrar integrações reais. Uma classificação duvidosa não
gera ligação automática. Classificar aos poucos conforme usar; não varrer nem reinterpretar tudo com IA.

Não é contexto fixo: nada do cérebro entra sozinho no prompt do Claude (só uma linha avisando que ele existe).
Quando faltar uma informação do Pailer que a tarefa precisa ("como ele quer isso?", "qual cliente/pasta/padrão?"):
`mapa` (títulos, barato) → `consultar` ou `ler`. Consulta só devolve acerto FORTE (força ≥ 0,15 e metade do peso da
pergunta presente no neurônio; palavra desconhecida pesa contra); sem acerto volta "nada" → siga sem ele ou pergunte.
Codex/Kani/Pickle (sem a ferramenta) recebem no máximo 2 neurônios com acerto ≥ 0,22 para a tarefa; sem acerto, nada.
Usou e serviu → `reforcar`; atrapalhou → `enfraquecer`.

## Quando GUARDAR (neurônio próprio) — só certeza
`guardar` exige `certeza='pailer'` (ele disse/confirmou) ou `'verificado'` (conferi na fonte) + `origem`. Palpite,
dedução ou "acho que" não entra.
- Ele corrigiu ou aprovou algo (o porquê junto).
- Fato estável sobre ele, cliente, contato, ferramenta ou processo que vai valer de novo.
- Busca em tempo real (web, Drive, Pandalab) que trouxe algo reutilizável — com `origem`.
- Habilidade/conhecimento dele percebido no trabalho.
Não guardar: o que está no código, no git ou no CLAUDE.md; o que só vale para esta conversa; palpite não confirmado.
Se `guardar` devolver um parecido, ATUALIZE esse em vez de duplicar. Regra de ouro: memória do Claude (arquivo .md) =
regra durável de comportamento; neurônio próprio = conhecimento e contexto que se consulta.

## Projetos em andamento (sem chamada extra de IA)
Ao trabalhar num projeto, aproveite as informações já confirmadas na conversa ou na fonte e chame
`projeto` com `projeto` (nome específico do trabalho, não só o cliente), `ficha`, `certeza` e `origem`.
Ficha: cliente, formato (vídeo/flyer/carrossel/animação etc.), tema, ferramentas (texto curto), resumo (até 700
caracteres), etapa, pasta e status. Não precisa completar tudo: desconhecido se omite, não se adivinha nem se
investiga só para preencher. Não guardar transcrições, código ou histórico de cada ação.

Uma ficha = um neurônio. Nome igual atualiza o mesmo; use a `ref` devolvida para evitar ambiguidade. Mande só
campos que mudaram; os outros ficam. Campo vazio remove informação corrigida; status só muda com confirmação.
Cada campo mantém sua origem/certeza. Repetir a mesma ficha não grava nem cria atividade. `ligar` acrescenta
ligações explícitas; a afinidade já existente cria as demais conexões sem modelo adicional.

Exemplo: `{"acao":"projeto","projeto":"Cliente — campanha outubro — reels",
"ficha":{"cliente":"Cliente","formato":"vídeo","tema":"campanha outubro","ferramentas":"Kanivete",
"resumo":"Reels da campanha de outubro.","etapa":"montagem"},"certeza":"pailer","origem":"conversa atual"}`.
Depois: mesma ação, mesma ref e `ficha={"etapa":"ajuste das legendas"}` com certeza/origem.

Em andamento e pausado aparecem em **Projetos em andamento** na área correspondente. Concluído/cancelado sai
desse grupo e fica em **Projetos**, sem apagar. A consulta continua seletiva; não injeta lista de projetos nos
prompts. Agentes sem a ferramenta podem usar `perfil_cerebro.acao({...})` pelo Python do plugin, com o mesmo
formato. Atualizar ao receber mudança relevante confirmada, sem varrer conversas antigas ou rodar um extrator.

## Quando DESCARTAR
Contradito por informação nova (descartar o velho, guardar o novo), caminho/ferramenta que não existe mais, projeto
encerrado sem uso, duplicata depois de juntar. Descartar arquiva com o motivo (dá para voltar); memória .md errada se
corrige ou apaga no arquivo dela também.

## Vida (nunca parado)
Vida 0–1 = uso recente (meia-vida ~60 dias) + quantidade de usos + novidade + nota (reforçar/enfraquecer). Abaixo de
0,15 = "apagando" (aparece fraco no mapa). `revisar` lista: juntar (semelhança ≥ 0,6), caminhos quebrados, apagando e
projetos parados > 45 dias — rodar no fim de missão longa e cuidar de 2–3 itens por vez.
Uma fotografia por dia vai para historico.jsonl (o gráfico de evolução no painel).

## Faxina (o cérebro se cuida sozinho)
Uma vez por dia, 10 min depois de abrir o KaniCode (processo à parte, prioridade baixa; log em `<DADOS>/cerebro_faxina.log`),
`perfil_cerebro.py faxina --diaria` junta os candidatos: todos os caminhos citados sumiram, projeto sem uso > 60 dias,
apagado > 90 dias (nunca o "jeito de trabalhar": regra não vence por tempo) e o mais velho de um par muito parecido.
A Kani (local, grátis) julga cada um ("na dúvida, fica"); o que ela manda sair vai para o arquivo com o motivo. Memória
.md do Claude que sair vira PENDÊNCIA: o Claude vê no ponto de partida, corrige/apaga o arquivo e marca `resolvida`.
Mantido pelo juiz não volta a ser julgado por 30 dias. Botão "Faxina agora" no painel; `restaurar` volta um descartado.

## Ponto de partida comum (todas as IAs partem do mesmo cérebro, sem peso)
`ponto_de_partida(tarefa, quem)`: Claude = 1 linha de aviso (+ pendências da faxina); Codex (licoes.anexo), Kani e
Pickle (kani_modo) = só acertos fortes da tarefa (máx. 2) ou nada. Agente novo no portal = chamar `ponto_de_partida`.
