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
| Kani ilimitada, uso real da GPU e VRAM (NVML, sob demanda) | `gpu.py`, `App.gpu_info`, `ui/kani_gpu.js` |
| Contas, fotos locais por e-mail e miniaturas | `contas.py`, `avatares.py`, `App._contas_com_fotos` |
| API da janela, estado, pastas, sessões e cancelamento | `kanicode.py` → `App` |
| Execução do Codex, JSONL, progresso e tokens | `ajudantes.py` → `codex` |
| Pipes, prazos, cancelamento e processos filhos | `codex_processo.py` |
| Limites, redefinições, tokens e comentários de andamento do Codex | `codex_conta.py`, `ui/codex_uso.js/css`; guia e pendências: `CODEX_PARIDADE.md` |
| Diffs expansíveis por arquivo na conversa | `codex_alteracoes.py`, `ui/alteracoes.js/css` |
| Código de Kani/Big Pickle na cópia, sintaxe/testes e revisão humana | `codigo_agente.py`, `codigo_testes.py`, `ui/codigo_agente.js/css`, `tests/test_codigo_agente.py`; área `codigo` |
| Contexto inicial, ferramentas e esforço do Codex | `codex_contexto.py` |
| Claude (conversa contínua e permissões) | `sessao.py` → `Sessao` |
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
| Selo do Codex (terminal >_) | `ui/codex.svg`, `Bolinha._selo` |
| Selo circular do Claude (asterisco) | `ui/claude.svg`, `Bolinha._selo` |
| Voz, fala e áudio | `voz.py`, `fala.py`, `radio.py` |
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
