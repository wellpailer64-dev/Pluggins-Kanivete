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
| Dados isolados e Chromium automático na verificação | `dados_app.py`, `teste_isolado.py`, `verificar.py`; `KANICODE_TESTE=1` usa `KANICODE_DADOS_TESTE` dentro de `D:/kanivete_testes`. Auditoria recusa gravações nos dados reais. `tests/test_ambiente_isolado.py` |
| Markdown, copiar código, Explorer, links externos e visualizador de imagens | `ui/respostas_render.js`, `ui/respostas.js`, `ui/respostas.css`, `recursos_resposta.py`, `App.resposta_*` |
| Painel Ferramentas (largura por arraste, espaço inicial, ações de trabalho e atividade recolhível), Configurações separadas na engrenagem, seletores e pastas em uso | `ui/paineis.js`, `ui/organizacao.js`, `ui/organizacao.css`; grupos em `ui/janela.html`; aba Código em `ui/alteracoes.js` |
| Abas (várias conversas/tarefas ao mesmo tempo; Ctrl+N/W/Tab; aba de trás guarda eventos e avisa) | `ui/abas.js`, `kanicode.py` (`_Aba`, `_ctx`, `_na_aba`; eventos com `aba`; aba 1 = chaves antigas), `tests/test_abas*.py` |
| Enter enfileira durante o trabalho; duplo clique na pendente interrompe o turno para entregar com urgência | `mensagens.py`, `App.mensagem_enviar/mensagem_urgente/_fila_tentar`, `ui/mensagens.js`; guia `MENSAGENS.md`; verificar `--area mensagens` |
| Kani ilimitada, uso real da GPU e VRAM (NVML, sob demanda) | `gpu.py`, `App.gpu_info`, `ui/kani_gpu.js` |
| Contas, fotos locais por e-mail e miniaturas | `contas.py`, `avatares.py`, `App._contas_com_fotos`; Codex na lateral: `App.codex_identidade`, `codex_conta.identidade`, `ui/codex_uso.js/css` |
| API da janela, estado, pastas, sessões e cancelamento | `kanicode.py` → `App`; falhas de envio/histórico: `ui/diagnostico.js`, `janela_diagnostico.jsonl` na pasta de dados. Teste WebView2 real (janela invisível, motor simulado): `tests/test_ponte_nativa.py` |
| Execução do Codex, JSONL, progresso e tokens | `ajudantes.py` → `codex` |
| Pipes, prazos, cancelamento e processos filhos | `codex_processo.py` |
| Limites, redefinições, tokens e comentários de andamento do Codex | `codex_conta.py`, `ui/codex_uso.js/css`; guia e pendências: `CODEX_PARIDADE.md` |
| Diffs expansíveis por arquivo na conversa | `codex_alteracoes.py`, `ui/alteracoes.js/css` |
| Código de Kani/Big Pickle na cópia, sintaxe/testes e revisão humana | `codigo_agente.py`, `codigo_testes.py`, `ui/codigo_agente.js/css`, `tests/test_codigo_agente.py`; área `codigo` |
| Contexto inicial, ferramentas e esforço do Codex | `codex_contexto.py` |
| Claude (conversa contínua e permissões) | `sessao.py` → `Sessao` |
| Missões longas do Claude, pontos de retomada e erros completos em disco | `continuidade.py`, `Sessao.registro`, ferramenta `mcp__equipe__missao`; guia `CONTINUIDADE.md`; teste `tests/test_continuidade.py`; verificar `--area claude` |
| Contratos do modo Equipe e revisão automática | `mcp_equipe.py`; regressões: `tests/test_equipe_revisao.py`; verificar `--area claude`. Evidências JSON (resultado/duração, sem conteúdo dos arquivos) em `D:/kanivete_testes/revisoes_kanicode`. |
| Regras e lições por projeto | `licoes.py` |
| Meu perfil: exportação portátil e restauração com prévia, conflitos e cópia anterior (login/nuvem ainda não implementados) | `perfil_portatil.py`, `ui/perfil_portatil.js/css`, `App.perfil_*`; guia `PERFIL_PORTATIL.md`; testes `tests/test_perfil_portatil.py`; rotinas personalizadas em `D:/Kanivete/KaniCode/perfil/rotinas.json` |
| Preferências curadas de organização dos clientes, aplicadas apenas em pedidos pertinentes | `organizacao_pailer.py`, `licoes.py`, `codex_contexto.py`, `kani_modo.py`; perfil e evidências em `D:/Kanivete/KaniCode/preferencias/organizacao_clientes.json` e `.md`; teste `tests/test_organizacao_pailer.py` |
| Kani local e ferramentas dela | `ajudantes.py`, `kani_modo.py` |
| Mapa vivo do disco D (menu de ferramentas e mobile): índice SQLite, busca, navegação e monitor de mudanças | `mapa_d.py`, `mapa_d_monitor.py`, `ui/mapa_d.js/css`; guia `MAPA_DISCO.md`; teste `tests/test_mapa_d.py`; MCP `mapa_d` |
| Consultas da Kani: busca local por cliente/documento, leitura de PDF, previsão do tempo, Gmail e Drive | `kani_consultas.py`, `kani_modo.py`; Gmail/Drive precisam de conta conectada em Conexões. Teste: `tests/test_kani_consultas.py` |
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
| Google Calendar: Configurações → Conexões, OAuth desktop/DPAPI, agendas, consulta da Kani e avisos falados | `google_calendar.py`, `App.google_*`, `ui/conexoes.js/css`, `compromissos.py`, `kani_modo.agenda_google`; guia `CONEXOES.md`; testes `test_google_calendar.py`, `test_conexoes_ui.py` |
| Google Drive: OAuth independente, busca/navegação, upload, download/exportação, criar pasta, mover, renomear, lixeira/restaurar; Kani `drive_*` | `google_drive.py`, `google_drive_arquivos.py`, `App.drive_*`, `ui/conexoes_drive.js`; guia `CONEXOES.md`; testes `test_google_drive.py`, `test_google_drive_arquivos.py`, `test_conexoes_ui.py` |
| Voz, fala e áudio | `voz.py`, `fala.py` (`TOM_SEMITONS = 3`, fala e prontidão), `radio.py`; prontidão nos quatro motores em `App._prontidao_agendar`; verificar `--area voz` |
| Vinhetas vocais de 8 bits da bolinha (entrada, conclusão e saída) | `sons_bolinha.py`, `ui/sons_bolinha/*.wav`, `App.sons_acoes`, `Bolinha._som` |
| Painel Projeto (como o do Codex): árvore de arquivos ao vivo com marcas do git, busca, Alterações (+/−, diff colorido), ver arquivo, citar na conversa; só lê | `projeto.py`, `ui/projeto.js/css`, `App.projeto(acao, arq)`; teste `tests/test_projeto_ui.py` |
| Tarefas pessoais, To-do e agenda no painel direito | `tarefas.py`, `ui/tarefas.js/css`, `ui/paineis.js`, `App.todo_*`, `kani_modo.todo_*`; guia `TAREFAS.md`; testes `test_tarefas*.py` |
| Arrastar anexos locais e imagens | `anexos_locais.py`, `ui/anexos.js/css`, `ui/janela.html` (`ANX`, `mandar`); testes `test_anexos*.py`. Arquivos por caminho original; imagens mantêm prévia. |
| Aba Consumo: tokens de hoje/semana/mês/tudo por motor e modelo (Claude sdk-cli, Codex codex_exec, Big Pickle; sem a Kani local), retroativo pelos registros de cada motor | `consumo.py` (cache `consumo_cache.json`), `App.consumo`, `ui/consumo.js/css` |
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
- WhatsApp pelo agente (2026-10-22): `wa.py foto --conversa X --saida F` (foto de perfil 640 px: Dados do contato → visualizador
  → canvas) e `wa.py enviar --arquivo F [--texto legenda]` (documento colado na caixa: ClipboardEvent paste → prévia → "Enviar 1 item").
- Rotinas (2026-10-22): `rotinas.json` → cada rotina vira ferramenta `mcp__equipe__<name>` (`_ferramentas`/`_rodar_rotina` em
  mcp_equipe.py: '{arg}' troca, vazio derruba o par '--flag {arg}', `flags` booleanas). Filho com stdin=DEVNULL (herdar o stdin do MCP travava).
  Tarefa metódica nova = acrescentar rotina (vale na próxima sessão).
- Cliente novo (2026-10-22): `pandalab/panda.py novo-cliente "Nome" --whatsapp "conversa" [--cor #hex] [--pasta P] --sim` = tag no
  sistema (client_tags: nome, cor, foto em meeting-files/client-profiles) + CLIENTES/<P> com 00 ORCAMENTO…04 NOTAS FISCAIS + foto
  como ícone (.ico + desktop.ini UTF-16) + ligação id[:8] → pasta no `mapa_clientes.json`. `ligar-pasta` (cliente que já existe), `editar-cliente`.
  Estudado no site (assets BoardLayout/HomeCreateMeetingDialog): `--drive` = função create-client-drive-folder; Área do Cliente =
  client_areas {tag_id, login, pin_hash: btoa(PIN)}; `reuniao` = create-meet-link (Meet + Agenda) + meeting_columns + meeting_reminders.
- Etapas: pedido com 3+ verbos (ou 2 + "depois/também…") → `_planejar` (1 chamada, `_SCHEMA_PLANO`) → evento `kani_plano`
  {itens, feitas, fim} → lista no chat (janela.html `plano()`), riscando pelo campo `feitas` do esquema. Teste simulado:
  `D:/kanivete_testes/scripts/teste_plano_kani.py "<pedido>"`. Falta: a lista no celular (movel.js).
- `foto_do_google {busca}`: Google Imagens na aba dela → clica a miniatura → foto grande do painel → `_baixar_direto` (pasta
  `D:\Kanivete\KaniBrowser\downloads`; tenta até 4 resultados). Memória curta: `compactar()` antes de cada chamada (resultados
  antigos resumidos; o motor tem 8 mil tokens) e, se ainda der HTTP 400, resume tudo e tenta de novo.
- Lista de etapas FIXA acima do status (`#planoFixo`), plim `som('etapa')` a cada etapa riscada; no fim vai para a conversa.
- KaniBrowser meio a meio por padrão (`--kb-kw: minmax(0,1fr)`; arrastar guarda em `kb-kani-w2`; duplo clique na divisória volta ao meio).
- Navegador 🌐 encaixado (2026-10-23, `navegador_painel.py` + `ui/navegador.js/css`): o agente usa ele primeiro (`kb.py` → KaniCode,
  abre o painel sozinho); brilho verde-limão (`.trab`) com a Kani trabalhando; `kb.py painel estado|mostrar ID|nova URL|ir URL|
  fechar_aba ID|acao voltar|aparelho celular` comanda as abas do Pailer (`navegador.painel_cmd`). Abas em ordem estável
  (`NAV.ordem`), aba da Kani vazia escondida, compactas (só ícone) quando são muitas, endereço legível (decodeURI), reajuste
  quando a borda do Chrome muda (`_reajustar`). Barrinha de carregando e ícone tirado da própria página (`_pagina`: readyState + link rel=icon, 1×/s na aba
  mostrada; reserva: serviço do Google → inicial). Reinício pelo botão: o encaixe da bolinha espera a entrada (3,4 s) e a página. Bateria com prints: `D:/kanivete_testes/scripts/kc_nav_bateria.py`.
