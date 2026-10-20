# Plugins pessoais do KANIVETE

Ferramentas que moram só no PC do Pailer, fora do app e do release. O KANIVETE lê `D:\Kanivete\Plugins`, que é uma
junção (atalho de pasta) para esta pasta: `mklink /J "D:\Kanivete\Plugins" "<esta pasta>"`.

Cada plugin é uma pasta com um `kanivete.json` (nome, ícone, js/css do painel e o módulo Python). Formato e carregador:
`Functions/plugins_pessoais.py` e `Instructions/agente/plugins.md` › Plugins pessoais, no repositório do KANIVETE.

| Plugin | O que faz |
|---|---|
| `pandalab` | Demandas do Laboratório Panda: listar, baixar na pasta certa do cliente, status, comentários, entrega |
| `kanibrowser` | Chrome do KANIVETE por canal privado (pipe, sem porta), com os logins guardados |
| `kanicode` | Conversa com o Claude (depois Codex e Kani) numa bolinha na área de trabalho; processo à parte, sobrevive ao KANIVETE fechar |

## Não vão para o git (`.gitignore`)
- `pandalab/config.json`: endereço e chave do sistema. Copie `config.exemplo.json` e preencha.
- `pandalab/sessao.bin`: sessão cifrada pelo Windows (só este usuário neste PC abre).
- `pandalab/vinculos.json` e `pandalab/mapa_clientes.json`: dados de clientes e das pastas deste PC.

## KaniCode (`kanicode/`)
- `kanicode.py`: o app à parte (pywebview). Instância única pela porta 127.0.0.1:47613 (só aceita `ping`, `mostrar`,
  `sair`). Estado em `D:\Kanivete\KaniCode\estado.json` (posição da bolinha em pixels reais, alfinete).
- `bolinha.py`: a bolinha NATIVA (WinForms + janela em camadas com alfa por pixel, GDI+). Não usar WebView para ela: o
  WebView2 desenha por DirectComposition e ignora o recorte da janela (sobrava um quadrado escuro) e a transparência
  do pywebview não desenha nada. Criar e mexer nela só na thread da interface (`App._na_ui`).
- `ui/janela.html`: a conversa. `ponte.py`: o KANIVETE abre (`pythonw`/`pyw -3.13`, processo solto, fora do job do app),
  mostra e fecha. `painel.js`: aba com status e "Abrir junto com o KANIVETE".
- Medidas: o pywebview recebe pixels da INTERFACE (ele aplica o zoom do monitor); a bolinha nativa trabalha em pixels
  REAIS (`Bolinha.escala`). Nunca chamar SetProcessDpiAwareness à mão (dobra a escala).
- `sessao.py` (etapa 2): uma conversa = um `claude -p --input-format stream-json --output-format stream-json
  --include-partial-messages --verbose --permission-mode acceptEdits --permission-prompts none` aberto na pasta do
  projeto, que fica vivo entre as mensagens; eventos simples para a janela (texto aos pedaços, ferr/ferr_fim, limite =
  % da cota de 5 h, fim). Parar = `control_request interrupt` (3 s depois, mata). Sessão por pasta em `estado.json`
  (`sessoes`), conversa da janela em `D:\Kanivete\KaniCode\conversas\<sessão>.jsonl`; reabrir = `--resume`.
- Testar a janela: `py -3.13 kanicode.py --agente[=9350]` (CDP só nesse modo) — scripts em `D:\kanivete_testes\scripts\kc_*.py`.
- Etapa 3 (permissões, status e cotas): `--permission-mode auto` (o classificador do Claude Code libera o seguro) +
  regras "ask" do KaniCode (`sessao.REGRAS_PERGUNTAR`: git push/commit/reset…, gh, apagar, matar processo, desligar,
  POST) mandadas por `--settings`; o pedido chega no canal da conversa com `--permission-prompt-tool stdio` + um
  `control_request initialize` no início (sem isso o "ask" é recusado sozinho). Apagar com todos os alvos dentro da pasta
  do projeto é liberado em `_apagar_dentro`, sem cartão. O `initialize` devolve a lista dos comandos "/" (com descrição).
  Comandos internos ("/context", "/usage") voltam como resposta "<synthetic>" inteira, sem pedaços.
  Status ao vivo: tokens (`message_start/delta.usage`), contexto, tempo, ação atual; cotas de 5 h e semana do
  `rate_limit_event.unifiedWindows` (`five_hour`, `seven_day`), com contagem regressiva. Sons sintetizados (Web Audio).
- Etapas: 1 esqueleto (feita) · 2 conversa com o Claude Code (feita) · 3 permissões, status, cotas, comandos, sons (feita) (`claude -p --input-format stream-json --output-format
  stream-json --include-partial-messages --resume`) · 4 Codex e
  Kani · 5 modo Equipe.
