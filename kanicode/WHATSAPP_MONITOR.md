# Avisos falados do WhatsApp

Abra o navegador 🌐 do KaniCode, entre em `https://web.whatsapp.com` e faça login.
No botão WhatsApp da lateral direita, clique em **Ligar avisos**. Recolher o painel
não desliga o monitor; **Desligar avisos** interrompe a fila e a fala dele.
O aviso falado é “Mensagem de Nome”, seguido do conteúdo, sem dizer “prévia”.
Mensagens seguidas da mesma origem são lidas sem repetir o nome. Ao mudar de
remetente ou conversa, ou religar o monitor, o nome volta a ser anunciado.
O monitor começa desligado após cada reinício. Não precisa abrir PowerShell/CMD.

São observadas apenas as abas do navegador hospedado no processo do KaniCode.
Não conecta a portas do Chrome ou do Kanivete e não abre, fecha ou troca abas.
Não envia mensagens e não abre conversas para buscar conteúdo.

- Na conversa aberta: lê mensagens recebidas novas que aparecem depois da referência inicial.
- Na lista lateral: anuncia mudanças nas prévias de conversas não lidas visíveis.
  Prévia pode estar cortada e não identificar o remetente de um grupo.
- Ao ligar, abrir uma conversa ou perder a referência visível, o conteúdo serve como
  referência; não faz leitura retroativa. Conversas fora da lista renderizada, mudanças
  entre duas observações e mensagens que saem da tela podem não ser capturadas.
- Áudio novo da conversa aberta: carrega em mudo, transcreve com o Parakeet já
  instalado e resume com a Kani local. Isso pode marcar o áudio como ouvido.
  Se o arquivo não estiver acessível, registra e fala a limitação; não inventa a transcrição.
  Se faltar o modelo de resumo, lê a transcrição. O resumo é gerado, não é uma citação literal.
- Áudio de conversa fechada: anuncia a chegada; precisa abrir a conversa para acessar
  o áudio. Áudios já presentes ao abrir não são transcritos retroativamente pelo monitor.
- Pode desligar a transcrição. O carregamento de um modelo já em andamento pode
  terminar após desligar; o resultado não será falado. Para religar, aguarde essa tarefa terminar.

Em **Ignorar conversas, grupos ou remetentes**, use o nome exato, um por linha.
Em **Ignorar mensagens que contenham**, use palavras ou expressões, uma por linha.
Os filtros não diferenciam maiúsculas e são conferidos de novo antes de falar;
o texto transcrito também passa pelo filtro de palavras. Clique em **Salvar filtros**.
As preferências ficam em `whatsapp_monitor.json` na pasta de dados do KaniCode.
O histórico limitado a 40 avisos e a fila de até 50 mensagens ficam na memória.
Espera o microfone, a fala e os agentes ficarem livres antes de iniciar um aviso.

Implementação: `whatsapp_monitor.py`, `App.whatsapp_*`, `ui/whatsapp.*`,
`ui/whatsapp_observar.js` e `ui/whatsapp_audio.js`.
Os seletores dependem da interface do WhatsApp Web; não é uma integração oficial.
Testes `tests/test_whatsapp_monitor.py` e `tests/test_whatsapp_ui.py` usam dados
sintéticos, modelos simulados e Chromium isolado, sem acessar uma conta real.
