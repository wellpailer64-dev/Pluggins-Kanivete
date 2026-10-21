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
- `kanicode.py`: o app à parte (pywebview). Instância única pela porta 127.0.0.1:47613 (aceita `ping`, `mostrar`,
  `sair`, `atualizar`/`recarregar`/`reiniciar` e `evento <json>`). Estado em `D:\Kanivete\KaniCode\estado.json` (posição da bolinha em pixels reais, alfinete).
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
- Etapa 4 (equipe): `ajudantes.py` roda o Codex (`codex exec --json -m gpt-6.1-sol`, conta Plus; cotas lidas do
  arquivo da sessão dele em `~/.codex/sessions`, `rate_limits.primary/secondary`) e a Kani (llama-server do KANIVETE,
  `dist/CaniveteDoPailer/modelos_ia/kani`, sai da placa após 3 min parada). `mcp_equipe.py` = servidor MCP (stdio) que o
  Claude Code abre (`--mcp-config` + `--allowedTools`): ferramentas `codex(contrato, editar)` e `kani(pedido, contexto)`;
  o andamento vai para a janela pelo canal de controle (linha `evento <json>`) → avatar animado no canto (anel girando,
  o que faz, tempo, tokens). "Quem responde" (rodapé): Claude (com a equipe), Codex direto ou Kani direta. Painel 🧰:
  ferramentas, guias (resumo + seções na busca) e scripts do `Instructions/mapa.json`, comandos/skills do Claude, equipe.
- Etapas: 1 esqueleto · 2 conversa · 3 permissões, status, cotas, comandos, sons · 4 equipe Codex/Kani, habilidades (feitas) (`claude -p --input-format stream-json --output-format
  stream-json --include-partial-messages --resume`) · 5 modo Equipe completo
  (contratos com as lições guardadas, revisão automática).
- Melhorias "melhor que o cmd" (2026-10-20; medições em `D:\kanivete_testes\kc\exp_*.py`):
  - Custo: o prompt extra (`sessao.PROMPT_KANICODE`) ficou só no essencial; o como-usar dos ajudantes mora na descrição da
    ferramenta `codex` (ferramentas MCP entram adiadas). Medido por passo: cmd 57.612 × KaniCode 57.932 tokens (+0,5%;
    antes +1,5%). Aviso "Conversa longa" (> 120 mil de contexto, de novo a cada +60 mil) com botão Nova conversa — o
    `/usage` aponta "não limpar ao trocar de assunto" como o maior gasto.
  - "Mandar agora": com texto escrito no meio da tarefa o botão manda o recado (`user` no stream-json entra na MESMA
    volta, no próximo passo); campo vazio = Parar (`exp_meio.py`).
  - 📝 Planejar (rodapé): `control_request set_permission_mode` plan/auto (e `--permission-mode` ao abrir); o
    `ExitPlanMode` chega como `can_use_tool` e vira cartão com o plano em markdown (Aprovar e executar / Ajustar);
    aprovar volta a auto (`exp_plano.py`). 🔍 no topo = `/code-review`.
  - Prints na conversa: `Read` de .png/.jpg/.webp ou caminho de imagem na saída do Bash/PowerShell vira miniatura abaixo
    do passo (`App.miniatura`, PIL, ≤ 900 px; clique = `App.abrir_imagem`).
  - Diff colorido por linha e resumo dos arquivos mudados; ⤢ janela grande; painéis laterais para fora (`ui/paineis.js`:
    Atividades à direita, Contas à esquerda).
  - Contas: a mesma conta (mesmo e-mail) aparece uma vez só (`oculta`: fica a em uso, senão uma salva; nada é apagado),
    a em uso primeiro, e a vaga "Principal" (login do PC, muda por fora com `/login`) mostra o e-mail. Contas salvas têm
    login próprio em `D:\Kanivete\KaniCode\contas\<id>` e não somem quando o login do PC muda.
  - Aplicar ajuste sem fechar: `py -3.13 recarregar.py [--recarregar|--reiniciar]` manda `atualizar` pelo canal de
    controle; só ui/css/js mudou = recarrega a página; algum .py = abre um KaniCode novo (`--reaberto` espera a porta,
    `--abrir` volta com a janela aberta, `--resume` mantém a conversa) e este sai. No meio de uma resposta, espera o `fim`.
