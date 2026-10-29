# Plugins pessoais do KANIVETE

Ferramentas que moram só no PC do Pailer, fora do app e do release. O KANIVETE lê `D:\Kanivete\Plugins`, que é uma
junção (atalho de pasta) para esta pasta: `mklink /J "D:\Kanivete\Plugins" "<esta pasta>"`.

Cada plugin é uma pasta com um `kanivete.json` (nome, ícone, js/css do painel e o módulo Python). Formato e carregador:
`Functions/plugins_pessoais.py` e `Instructions/agente/plugins.md` › Plugins pessoais, no repositório do KANIVETE.

| Plugin | O que faz |
|---|---|
| `pandalab` | Demandas do Laboratório Panda: listar, baixar na pasta certa do cliente, status, comentários, entrega |
| `kanibrowser` | Chrome do KANIVETE por canal privado (pipe, sem porta), com os logins guardados; funciona também só com o KaniCode aberto |
| `kaniadb` | Celular Android no KaniCode pelo cabo USB (depuração ativa): tela ao vivo e controle. Som: pendente |
| `kanicode` | **Software independente desde 2026-10-28**, com repositório próprio (github.com/wellpailer64-dev/KaniCode, privado). A pasta continua aqui, fora deste git; não é mais plugin do KANIVETE (o KaniCode é que comanda o KANIVETE, pelo plugin `kanicode/plugins/kanivete`) |

## Não vão para o git (`.gitignore`)
- `pandalab/config.json`: endereço e chave do sistema. Copie `config.exemplo.json` e preencha.
- `pandalab/sessao.bin`: sessão cifrada pelo Windows (só este usuário neste PC abre).
- `pandalab/vinculos.json` e `pandalab/mapa_clientes.json`: dados de clientes e das pastas deste PC.

## KaniCode (`kanicode/`, repositório próprio — notas abaixo são históricas; ver README do KaniCode)
Plugins do KaniCode: `kanicode.json` ao lado do `kanivete.json` (Pandalab e KaniBrowser servem aos dois).

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
  regras "ask" do KaniCode (`sessao.REGRAS_PERGUNTAR`, mandadas por `--settings`) — VAZIA desde 2026-10-20: o Pailer quis
  as mesmas permissões do cmd (antes: git push/commit/reset…, gh, apagar, matar processo, desligar, POST); o pedido chega no canal da conversa com `--permission-prompt-tool stdio` + um
  `control_request initialize` no início (sem isso o "ask" é recusado sozinho). Apagar com todos os alvos dentro da pasta
  do projeto é liberado em `_apagar_dentro`, sem cartão. "Permitir sempre: git push" no cartão (`sessao.risco`/`sempre`,
  lista em `dados/sempre.json`) libera aquele item de `_RISCO` só com o comando sozinho (com `&&`, `;`, `|`, crase ou
  `$(` volta a perguntar); passou sozinho = linha "✓ … liberado sempre · não liberar mais". O `initialize` devolve a lista dos comandos "/" (com descrição).
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
- **Ei Kani** (voz, 2026-10-20, `kanicode/voz.py`, botão 🎙): microfone → openWakeWord com modelo próprio
  (`modelos/hey_kani.onnx`, treinado em `D:\kanivete_testes\hey_kani`: Piper + OmniVoice, 2000 h de negativos do ACAV;
  ~78% em voz sintética nunca vista, 1,8 falsos/h) → no disparo o Parakeet confere se ouviu "Kani" → bipe, grava até a pausa
  (Silero VAD) → Parakeet pt-BR do KANIVETE transcreve → vai para a conversa com "(por voz)". "Para" interrompe a tarefa,
  "cancela/esquece" descarta. Bolinha: pontinho = escutando, anel pulsando = ouvindo. Liga sozinho se estava ligado.

## KaniCode no celular (2026-10-21)
A MESMA conversa no celular, de qualquer lugar; o PC faz tudo, o celular é tela, microfone e alto-falante.
- **Acesso**: `movel.py` serve `ui/janela.html` (+ `ui/movel.js`/`movel.css`) em **127.0.0.1:47614 apenas**. De fora, só
  pelo Tailscale (conta well.pailer64; PC `pcpailer`, celular Motorola Edge 40): `tailscale serve --bg 47614` →
  `https://pcpailer.taile07425.ts.net` (HTTPS só dentro da rede particular). Chave de pareamento em
  `D:\Kanivete\KaniCode\movel.json` (fora do git), vira cookie (`SameSite=Lax`: com `Strict` o link vindo da câmera não
  guardava). Link + QR na tela: `py -3.13 kanicode/movel.py`. Liga sozinho (`estado.json` › `movel`: false desliga).
- **Ponte**: `movel.js` imita o `window.pywebview.api` (POST `/api/<método>`, só os de `LIBERADOS`; os de janela do PC
  ficam em `NADA`) e recebe os eventos por SSE (`/eventos?de=<id>`). `App._para_janela` → `movel.publicar`. Mensagens e
  respostas de cartões ecoam entre aparelhos (`eco_eu`, `eco_resp`); cartões abertos voltam vivos ao abrir (`App.pendentes`).
- **Voz**: 🎤 grava no celular (16 kHz, para sozinho no silêncio) → `/voz/ouvir` (Parakeet do `voz.py`) → vai com "(por voz)".
  Resposta falada: frases → `/voz/falar` (Kokoro do `fala.py`, WAV) → toca no celular (continua com a aba minimizada).
  🎙 Modo conversa = lê todas as respostas e reabre o microfone (no navegador só com a tela à vista; no app sempre).
- **Rádio** (`radio.py`, navegador): página parada não fala (o celular congela o JS minimizado/tela apagada; "silêncio em
  laço" no próprio celular NÃO resolveu). Com o 🎙, o player toca `GET /voz/radio` (MP3 32 kb/s contínuo, ≈ 14 MB/h); o
  PC lê a resposta de pedido feito pelo celular (`X-KC-De` ≠ "pc" → `radio.marcar`), frase a frase (corta na vírgula se
  passar de 70 letras), e mistura no fluxo; o resto é silêncio. Player pula para perto do fim se ficar > 1 s atrás.
  Pausar na tela de bloqueio desliga.
- **Avisos** 🔔 (`aviso_movel.py` + `ui/movel-sw.js`, Web Push com `pywebpush`; chaves VAPID e assinaturas em
  `D:\Kanivete\KaniCode\movel_push.json`): "terminei" / "preciso de você" só quando o pedido saiu do celular e nenhuma tela
  do KaniCode está à vista lá (`/push/visto`).
- **📺 KANIVETE ao vivo** (`tela_movel.py`): `Page.startScreencast` do KANIVETE em modo agente (9222; 9333 = teste) →
  MJPEG em `/tela`; só a página do app, só manda quadro quando muda; ✕ fecha a conexão e para. ⛶ tela cheia deitada.
  Fechado: "Abrir o KANIVETE" (`/tela/abrir` → exe do `dist` com `--agente`). Só assistir (clicar = próxima etapa).
- **Tela**: topo só marca + 📺 + ☰ (menu: conversa nova, habilidades, modo conversa, avisos, contas, atividades,
  recarregar); sem zoom e sem arrastar para o lado (`.meio` com `min-width: 0`); contas = painel por cima, só trocar.
- **Ícone**: carinha 8-bit de óculos escuros — `py -3.13 kanicode/icone_oculos.py` gera `icone*.png` (192/512/máscara/
  notificação) e o `kanicode.ico` do atalho. Trocou: apagar e reinstalar o app no celular.
- O PC nunca dorme (energia) e KaniCode + Tailscale iniciam com o Windows; se o Windows reiniciar, fica na senha até o
  Pailer entrar (entrada automática recusada por segurança).
- Testes (servidor com app de mentira, Playwright com tela de celular): `D:\kanivete_testes\kanicode_movel\*.py`.

## App do celular (Android, 2026-10-21) — `kanicode/android`
Java puro, sem Android Studio/Gradle: `py -3.13 kanicode/android/montar.py [--sem-instalar]` (aapt2 + javac + d8 +
zipalign + apksigner; SDK em `D:/dev/android`: cmdline-tools, build-tools 34, android-34, platform-tools) monta
`KaniCode.apk` e instala pelo cabo (`adb install -r`, depuração USB ligada). O endereço com a chave vai num `Config.java`
gerado em `build/`; APK e build fora do git; assinatura em `D:/dev/android\kanicode.jks`.
- `MainActivity`: a página do KaniCode num WebView que NÃO pausa (sem `onPause`/`pauseTimers`): conversa e voz seguem
  minimizado, por isso no app a voz vem direto (`/voz/falar`), sem a rádio (menos atraso). Voltar = só esconde.
- `BolinhaService` (serviço em primeiro plano microfone + mídia): bolinha por cima de tudo (`TYPE_APPLICATION_OVERLAY`);
  arrastar (lembra a posição), soltar no ✕ embaixo fecha, 1 toque abre o app, 2 toques aperta o 🎤 da página.
  `BolaView` + `Rosto` = a bolinha e o rosto 8-bit do PC (`bolinha.py`/`rosto.py`): neutro, trabalhando (arco),
  ouvindo (anel), pensando, falando (boca + pulso pelo volume), pergunta (ponto vermelho).
- Página ↔ app: `window.KCApp.estado(ouvindo|pensando|falando|parado)`, `.tarefa(trabalhando|pergunta|parado)`,
  `.nivel(0..1)` (volume medido por um AnalyserNode no player). Pedido pela bolinha continua a conversa (ouve de novo
  depois de falar; 8 s sem fala encerra).
- Permissões (sobrepor apps, microfone, notificações): o app pede; pelo cabo `adb shell appops set com.pandalab.kanicode
  SYSTEM_ALERT_WINDOW allow` + `pm grant … RECORD_AUDIO / POST_NOTIFICATIONS`.

## KaniADB — o celular no KaniCode pelo cabo USB (vídeo contínuo, 2026-10-29) — `kaniadb/`
`py -3.13 kaniadb/kaniadb.py estado` · `dispositivos` · `tamanho` · `tela --salvar tela.png` · `tocar X Y` ·
`deslizar X1 Y1 X2 Y2` · `texto "..."` · `tecla voltar|home|recentes|ligar|volume+` · `audio` ·
`servir [--porta 47615]` (página do celular, só em 127.0.0.1).
- Usa o adb que já existe no PC (`D:\dev\android\platform-tools`, ou `KANIADB_ADB`); não instala nada e não abre porta
  para fora deste PC. Aparelho sem autorização/offline aparece no `estado` com o motivo.
- Motor rápido (padrão quando existe): o scrcpy 4.x já baixado (`~/Downloads/scrcpy-win64-v4.1` ou `KANIADB_SCRCPY`),
  vídeo e toque por sockets persistentes (`scrcpy_backend.py`), atraso perto do scrcpy. Sem ele, cai no caminho abaixo.
- `servir` captura H264 contínuo pelo `screenrecord` do Android e converte com o FFmpeg já instalado (`KANIADB_FFMPEG`
  pode indicar o executável). `/fluxo` envia MJPEG local, limitado a 30 quadros/s, guardando somente a imagem mais recente.
  Uma captura PNG inicial permite exibir a tela antes do primeiro quadro do vídeo. Telas estáticas podem não produzir novos
  quadros: a última imagem é preservada enquanto o processo permanece saudável, e `/estado.video` informa a idade do quadro.
  Não instala pacotes nem grava vídeo. O FFmpeg e o adb próprios da captura são encerrados quando a última página sai.
- Aceita `/tocar`, `/deslizar`, `/texto` e `/tecla`; usa o serial e a resolução da conexão ativa para evitar consultas ADB
  redundantes em cada comando. Capturas avulsas continuam em PNG. Não promete equivalência de latência com o scrcpy nativo.
- **Som: ainda não sai.** O adb sozinho não captura áudio do Android; `audio` explica o que falta (auxiliar rodando pelo
  shell no Android 11+, SDK 30+, ou o app do KaniCode no celular). Etapa seguinte.
- Testes (adb falso, sem celular e sem rede): `py -3.13 -m unittest discover -s kaniadb/tests -v`.

## KaniBrowser sem o KANIVETE (2026-10-21)
`kb.py` usa o KANIVETE (modo agente) se ele já está com o navegador aberto; senão o **KaniCode hospeda** o navegador
(`kanicode/navegador.py`: linha `kb <chave> {"f", "a"}` no canal 47613, chave em `D:\Kanivete\KaniCode\kb_chave.txt`;
roda numa thread). `--onde kanivete|kanicode` força. O mesmo perfil não abre nos dois ao mesmo tempo. Depois de
ir/abrir/nova/js/instagram/chatgpt/link sai `tela: <jpg>` (`ponte.vista`, prints em `D:\Kanivete\KaniBrowser\prints`,
40 últimos) e o KaniCode mostra a miniatura na conversa (PC e celular). `--sem-foto` não tira.

## WhatsApp em um comando (`kanibrowser/wa.py`, 2026-10-21)
`py -3.13 kanibrowser/wa.py ler --conversa "camila studio" [--n 30] [--transcrever]` · `arquivo --conversa X --nome parte`
· `conversas [--busca termo]` · `enviar --conversa X --texto "…"` (só com o ok do Pailer). Nome sem acento/emoji; se não
está na lista, usa a busca do WhatsApp; confere o cabeçalho antes de ler/colar. A lista do WhatsApp só guarda na tela um
pedaço: `ler` junta rolando para cima um passo por chamada (o navegador corta comando longo) e lê só o que está visível
(fora da tela vem vazio). Áudio: toca mudo, pega o arquivo (blob do player), Parakeet pt-BR local em pedaços de ~18 s
cortados no ponto mais quieto; cache por mensagem em `D:\Kanivete\KaniBrowser\wa_audios` (8 min ≈ 44 s). Marca o áudio
como ouvido. `arquivo`: abre o documento, aperta Baixar com o download desviado (createObjectURL / clique do link) para
`D:\Kanivete\KaniBrowser\wa_arquivos`.
**Regra (Pailer):** com o KANIVETE aberto, `kb.py` leva o navegador para ELE (fecha o do KaniCode, abre lá) e traz a aba
do KaniBrowser para a frente (`mostrar_aba`): ele acompanha ao vivo.
