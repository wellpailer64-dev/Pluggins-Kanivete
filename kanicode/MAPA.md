# Mapa do KaniCode

Plugin do Kanivete, em processo independente. A janela usa pywebview e uma API Python;
a bolinha é nativa do Windows. Não confundir o código deste plugin com o frontend do Kanivete.

Fluxo de trabalho por área, comandos e modelo de ferramenta: `ROTEIRO.md`.
Verificação local: `py -3.13 verificar.py --area <area> --listar` para consultar;
retire `--listar` para verificar. Áreas: kani, codex, interface, respostas, gpu, contas,
infra ou todas. Saídas e caches no D. Modelo opcional: `modelo_ferramenta.py`;
testes simulados: `tests/test_modelo_ferramenta.py`.

| Assunto | Código de entrada |
| --- | --- |
| Layout, CSS, botões, conversa, seleção de agente, painel de uso | `ui/janela.html` |
| Markdown, copiar código, Explorer, links externos e visualizador de imagens | `ui/respostas_render.js`, `ui/respostas.js`, `ui/respostas.css`, `recursos_resposta.py`, `App.resposta_*` |
| Menu de ferramentas, seletores junto da entrada e faixa de pastas em uso | `ui/organizacao.js`, `ui/organizacao.css` |
| Abas (várias conversas/tarefas ao mesmo tempo; Ctrl+N/W/Tab; aba de trás guarda eventos e avisa) | `ui/abas.js`, `kanicode.py` (`_Aba`, `_ctx`, `_na_aba`; eventos com `aba`; aba 1 = chaves antigas), `tests/test_abas*.py` |
| Enter enfileira durante o trabalho; duplo clique na pendente interrompe o turno para entregar com urgência | `mensagens.py`, `App.mensagem_enviar/mensagem_urgente/_fila_tentar`, `ui/mensagens.js`; guia `MENSAGENS.md`; verificar `--area mensagens` |
| Kani ilimitada, uso real da GPU e VRAM (NVML, sob demanda) | `gpu.py`, `App.gpu_info`, `ui/kani_gpu.js` |
| Contas, fotos locais por e-mail e miniaturas | `contas.py`, `avatares.py`, `App._contas_com_fotos`; Codex na lateral: `App.codex_identidade`, `codex_conta.identidade`, `ui/codex_uso.js/css` |
| API da janela, estado, pastas, sessões e cancelamento | `kanicode.py` → `App` |
| Execução do Codex, JSONL, progresso e tokens | `ajudantes.py` → `codex` |
| Pipes, prazos, cancelamento e processos filhos | `codex_processo.py` |
| Limites, redefinições, tokens e comentários de andamento do Codex | `codex_conta.py`, `ui/codex_uso.js/css`; guia e pendências: `CODEX_PARIDADE.md` |
| Diffs expansíveis por arquivo na conversa | `codex_alteracoes.py`, `ui/alteracoes.js/css` |
| Código de Kani/Big Pickle na cópia, sintaxe/testes e revisão humana | `codigo_agente.py`, `codigo_testes.py`, `ui/codigo_agente.js/css`, `tests/test_codigo_agente.py`; área `codigo` |
| Contexto inicial, ferramentas e esforço do Codex | `codex_contexto.py` |
| Claude (conversa contínua e permissões) | `sessao.py` → `Sessao` |
| Missões longas do Claude, pontos de retomada e erros completos em disco | `continuidade.py`, `Sessao.registro`, ferramenta `mcp__equipe__missao`; guia `CONTINUIDADE.md`; teste `tests/test_continuidade.py`; verificar `--area claude` |
| Contratos do modo Equipe e revisão automática | `mcp_equipe.py` |
| Regras e lições por projeto | `licoes.py` |
| Kani local e ferramentas dela | `ajudantes.py`, `kani_modo.py` |
| MVP de conversa Big Pickle pelo cliente oficial OpenCode | `opencode_mvp.py`, `App.opencode_info`, `App.opencode_testar`, `ui/opencode_mvp.js`, `ui/opencode_mvp.css`; guia: `OPENCODE_MVP.md`; teste: `tests/test_opencode_mvp.py` |
| Big Pickle no seletor, ferramentas, histórico por pasta e Parar | `bigpickle_modo.py`, `opencode_mvp.conversar`, `kani_modo.rodar` (motor opcional), `App._pickle_*`, `ui/janela.html`; guia: `BIGPICKLE.md`; verificar: `py -3.13 verificar.py --area pickle` |
| Big Pickle NATIVO para código (OpenCode com ferramentas próprias numa cópia git worktree; revisão e Aplicar) | `pickle_agente.py` (`rodar`, `Sessao`, `para_ponte`), `codigo_agente.Contexto` (`trabalho` do worktree), botão em `ui/codigo_agente.js`; guia: `BIGPICKLE.md` › Modo nativo; teste: `tests/test_pickle_agente.py` |
| Contexto, orçamento e recuperação única do Big Pickle | `pickle_controle.py`, `Motor.validar_resposta`, `opencode_mvp.FalhaOpenCode`; testes: `tests/test_bigpickle_controle.py` |
| Receitas por tarefa, abrir ferramenta com conferência da aba ativa e encaminhar tentativas | `kani_modo.py`: `_RECEITAS`, `consultar_receita`, `_JS_ABRIR_CONFERIR`, `rodar` (até 8 etapas); teste isolado: `D:\kanivete_testes\test_kani_receitas.py` |
| Conversa da Kani na mesma conversa do Claude (trocar não apaga; o Claude recebe as trocas não vistas) | `App._kani_guardar`, `_kani_para_claude`, `tests/test_kani_historico.py` |
| Programas abertos no PC e fechar o KANIVETE sem a porta | `kani_modo._programas_abertos`, `_fechar_sem_porta` |
| Bolinha e rosto | `bolinha.py`, `rosto.py`, `icone_oculos.py` |
| KaniBall dentro do chat (pula para cima da faixa de status e espia; palhaçadas, olha o mouse; volta ao lugar ao recolher) e Ctrl+Q (recolhe; de novo na bolinha fecha) | `ui/kaniball.js`, `App._encaixar/_desencaixar/_doca_sync/rosto_quadros`, `Bolinha.voar/esconder/mostrar_em/focar`; estado `"doca": false` desliga |
| Abas com assunto (1ª frase do último pedido) + modelo, barrinhas = trabalhando, vermelho = esperando você | `ui/abas.js` (`resumo`, `modeloCurto`), `App.aba_assunto` |
| Ctrl+Shift+K abre o KaniCode (tecla do atalho do menu Iniciar) | `atalhos.py` (`TECLA`; recriar: `py -3.13 atalhos.py criar menu`) |
| Selo do Codex (terminal >_) | `ui/codex.svg`, `Bolinha._selo` |
| Selo circular do Claude (asterisco) | `ui/claude.svg`, `Bolinha._selo` |
| Voz, fala e áudio | `voz.py`, `fala.py` (`TOM_SEMITONS = 2`, fala e prontidão), `radio.py`; prontidão nos quatro motores em `App._prontidao_agendar`; verificar `--area voz` |
| Vinhetas vocais de 8 bits da bolinha (entrada, conclusão e saída) | `sons_bolinha.py`, `ui/sons_bolinha/*.wav`, `App.sons_acoes`, `Bolinha._som` |
| Celular, HTTP e notificações | `movel.py`, `ui/movel.js`, `ui/movel.css`, `aviso_movel.py` |
| Plugin dentro do Kanivete | `ponte.py`, `painel.js`, `painel.css`, `kanivete.json` |
| Testes do Codex | `tests/test_codex_*.py` |
| Ações das respostas e imagens, com efeitos externos simulados | `tests/test_recursos_resposta.py`, `tests/test_respostas_ui.py` |

Localizar sem ler arquivos inteiros (os números de linha vêm do código atual):

```powershell
py -3.13 mapa_codigo.py --busca codex
py -3.13 mapa_codigo.py --arquivo kanicode.py --simbolo App.ajudante
py -3.13 mapa_codigo.py --arquivo ui/janela.html --busca 'function ajudante'
py -3.13 mapa_codigo.py --arquivo ajudantes.py --trecho 60:120
```

`--busca` procura texto literal, até 25 resultados; `--simbolo` extrai uma classe/função
Python, até 80 linhas. Use `--trecho início:fim` para continuar. Nenhum comando importa
o app, altera arquivos ou abre uma janela.

Contrato eficiente: objetivo + arquivos liberados + restrições + critério de pronto +
comando de teste. Exemplo: “Corrija a retomada em ajudantes.py. Preserve o Claude e o
modelo. Pronto quando primeira mensagem e continuação passarem. Teste: py -3.13 -m
unittest discover -s tests -v”. Não anexar o mapa inteiro a cada mensagem.

Dados ficam em `D:\Kanivete\KaniCode` (ou na unidade do plugin): estado em `estado.json`,
regras/lições em `regras/` e `licoes/`. Sessões do Codex ficam no `CODEX_HOME` configurado
(padrão `~/.codex/sessions`); o KaniCode guarda o ID por pasta para retomar após reiniciar.
Histórico visível do Codex: `conversas_codex/<id>.jsonl`. Medidas de cada chamada
(tempo, entrada/cache/saída, esforço e comandos): `codex_uso.jsonl`, sem os prompts.

Validar: `py -3.13 -m unittest discover -s tests -v`; JS: `node --check arquivo.js`.
O HTML contém JavaScript inline: extraia os scripts para checar a sintaxe. Não controle
o app em uso para testar. `recarregar.py` aplica mudanças no plugin aberto; Python
exige reiniciar o processo, então só aplique quando a resposta tiver terminado.

## Habilidades da Kani (livro do KANIVETE, 2026-10-21)
- `habilidades.py`: lê do app (só leitura) os menus de Photo (IE_MENUS), Vídeo (VE_CMDS + painéis VED), Vetor (VK_MENUS +
  VK_CMDS), Slider (SD_CMDS), Lux (luxItensMenu) e os botões com nome de cada página → `D:\Kanivete\KaniCode\habilidades.json`
  (~1300). Coletar tudo (abre cada ferramenta): `KANI_PORTA_KANIVETE=9333 py -3.13 habilidades.py --coletar --visitar` no app
  de teste; sozinho ele recoleta a cada 3 dias no app aberto (sem visitar). Buscar: `py -3.13 habilidades.py <pedido>`.
- Modo Kani: as 5 que parecem servir vão junto do pedido (`_dica_habilidades`); ferramentas `buscar_habilidade` e
  `usar_habilidade {id, args}`. Fechar/apagar só com pedido explícito (`PERIGO`). Diz que fez sem usar nenhuma = cobrança.
- Ensinar: frases do jeito do Pailer em `habilidades_extra.json` › `frases` (id → frases); habilidade com parâmetro e
  conferência = `habilidades` (tipo js, `async a => ...` que devolve CONFIRMADO/NÃO FEITO).
- Bateria: `bateria_kani.json` ([pedido, regex do id]); `py -3.13 bateria_kani.py` (busca, instantâneo) e `--modelo` (a Kani
  escolhe, nada roda no app; ~5 s/pedido). Erro novo → frase nova ou caso novo.
- Navegador e WhatsApp da Kani (2026-10-21): `whatsapp_conversas/ler/enviar` chamam `kanibrowser/wa.py` (confere o cabeçalho;
  enviar só com verbo de mandar no pedido, `_PODE_ENVIAR`); `escrever_kani` (campo por nome/placeholder, setter nativo, enter),
  `imagens_kani` (imagens ≥ 250 px da aba dela), `baixar_arquivo` (ponte `baixar_link`); `clicar_kani` clica também linhas de lista/títulos.
- Etapas: pedido com 3+ verbos (ou 2 + "depois/também…") → `_planejar` (1 chamada, `_SCHEMA_PLANO`) → evento `kani_plano`
  {itens, feitas, fim} → lista no chat (janela.html `plano()`), riscando pelo campo `feitas` do esquema. Teste simulado:
  `D:/kanivete_testes/scripts/teste_plano_kani.py "<pedido>"`. Falta: a lista no celular (movel.js).
- `foto_do_google {busca}`: Google Imagens na aba dela → clica a miniatura → foto grande do painel → `_baixar_direto` (pasta
  `D:\Kanivete\KaniBrowser\downloads`; tenta até 4 resultados). Memória curta: `compactar()` antes de cada chamada (resultados
  antigos resumidos; o motor tem 8 mil tokens) e, se ainda der HTTP 400, resume tudo e tenta de novo.
- Lista de etapas FIXA acima do status (`#planoFixo`), plim `som('etapa')` a cada etapa riscada; no fim vai para a conversa.
- KaniBrowser meio a meio por padrão (`--kb-kw: minmax(0,1fr)`; arrastar guarda em `kb-kani-w2`; duplo clique na divisória volta ao meio).
