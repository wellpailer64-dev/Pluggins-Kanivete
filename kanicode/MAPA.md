# Mapa do KaniCode

Plugin do Kanivete, em processo independente. A janela usa pywebview e uma API Python;
a bolinha é nativa do Windows. Não confundir o código deste plugin com o frontend do Kanivete.

| Assunto | Código de entrada |
| --- | --- |
| Layout, CSS, botões, conversa, seleção de agente, painel de uso | `ui/janela.html` |
| Menu de ferramentas, seletores junto da entrada e faixa de pastas em uso | `ui/organizacao.js`, `ui/organizacao.css` |
| Kani ilimitada, uso real da GPU e VRAM (NVML, sob demanda) | `gpu.py`, `App.gpu_info`, `ui/kani_gpu.js` |
| Contas, fotos locais por e-mail e miniaturas | `contas.py`, `avatares.py`, `App._contas_com_fotos` |
| API da janela, estado, pastas, sessões e cancelamento | `kanicode.py` → `App` |
| Execução do Codex, JSONL, progresso e tokens | `ajudantes.py` → `codex` |
| Pipes, prazos, cancelamento e processos filhos | `codex_processo.py` |
| Contexto inicial, ferramentas e esforço do Codex | `codex_contexto.py` |
| Claude (conversa contínua e permissões) | `sessao.py` → `Sessao` |
| Contratos do modo Equipe e revisão automática | `mcp_equipe.py` |
| Regras e lições por projeto | `licoes.py` |
| Kani local e ferramentas dela | `ajudantes.py`, `kani_modo.py` |
| Bolinha e rosto | `bolinha.py`, `rosto.py`, `icone_oculos.py` |
| Selo do Codex (terminal >_) | `ui/codex.svg`, `Bolinha._selo` |
| Selo circular do Claude (asterisco) | `ui/claude.svg`, `Bolinha._selo` |
| Voz, fala e áudio | `voz.py`, `fala.py`, `radio.py` |
| Celular, HTTP e notificações | `movel.py`, `ui/movel.js`, `ui/movel.css`, `aviso_movel.py` |
| Plugin dentro do Kanivete | `ponte.py`, `painel.js`, `painel.css`, `kanivete.json` |
| Testes do Codex | `tests/test_codex_*.py` |

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
