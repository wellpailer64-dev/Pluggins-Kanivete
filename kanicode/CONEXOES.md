# Google Calendar no KaniCode

Abra a **engrenagem à direita → Conexões**. Os aplicativos aparecem em cards: coloridos quando conectados, cinza quando desconectados. Clique no Google Calendar para configurar a conta, agendas e avisos. Google Drive já permite conexão e busca de arquivos. Gmail e GitHub continuam como sugestões para próximas integrações.
A conexão concede apenas leitura de calendários e eventos; não cria, edita nem envia convites.

## Configuração inicial (uma vez por aplicativo Google)

1. No [Google Cloud Console](https://console.cloud.google.com/), crie ou selecione um projeto.
2. Em APIs e serviços, ative **Google Calendar API**.
3. Em Google Auth Platform, configure identificação, público e tela de consentimento. Solicite os escopos
   `https://www.googleapis.com/auth/calendar.calendarlist.readonly` e
   `https://www.googleapis.com/auth/calendar.events.readonly`.
4. Se o público for externo e o aplicativo estiver em teste, adicione seu e-mail aos usuários de teste.
5. Crie um cliente OAuth do tipo **Aplicativo para computador / Desktop app** e baixe o JSON.
6. No KaniCode, clique **Importar JSON OAuth** e selecione esse arquivo. Depois, **Conectar conta Google**.
7. Entre no navegador e autorize as duas permissões de leitura. Volte à janela para conferir o resultado.

O login usa navegador externo, retorno local em `127.0.0.1` com porta temporária, state e PKCE.
Documentação: [OAuth para aplicativos desktop](https://developers.google.com/identity/protocols/oauth2/native-app),
[lista de calendários](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/list),
[consulta de eventos](https://developers.google.com/workspace/calendar/api/v3/reference/events/list).
Aplicativos externos em teste podem ter a autorização offline expirada pelo Google em sete dias: desconecte e reconecte.
Não são necessárias novas bibliotecas Python.

## Agenda e lembretes

- A primeira sincronização seleciona o calendário principal. Marque os demais e salve as preferências.
- A antecedência é configurável entre 1 e 1440 minutos; padrão de 10 minutos.
- A tela e a ferramenta `agenda_google` da Kani consultam os próximos sete dias, incluindo ocorrências de eventos recorrentes.
- Eventos de dia inteiro aparecem na agenda, sem aviso falado. Horários com fuso são convertidos para a hora local do Windows.
- `compromissos.py preparar`, na tarefa Windows existente `\Kani\Preparar avisos`, sincroniza a cada 30 minutos e agenda as próximas 36 horas junto dos compromissos próprios e do Pandalab.
- Login, sincronização manual e mudanças de seleção solicitam a preparação imediata em segundo plano.
- O PC precisa estar ligado, com a sessão do usuário disponível. Não há serviço na nuvem nem garantia de tocar com o computador suspenso/desligado.
- Os áudios usam o comportamento existente: saída Edifier quando disponível, som ativado, volume do Windows em 50%.
- Sem rede, a tela mantém a última leitura e informa a falha. Avisos Google só aceitam cache sincronizado há até duas horas.
- Desconectar esquece a autorização local, preserva a configuração do aplicativo OAuth e bloqueia os avisos Google já agendados. Também é possível revogar o acesso pela Conta Google.

Credenciais e tokens ficam protegidos com DPAPI, vinculados ao usuário Windows, em
`D:/Kanivete/KaniCode/conexoes/google.dpapi.json`. Eventos e preferências ficam em `google.json` nessa pasta.
A interface e a ferramenta da Kani nunca recebem os tokens. O JSON original baixado do Google não é alterado.

Logs: `D:/Kanivete/KaniCode/avisos/preparar.log` (ações da janela) e `agendador.log` (execução via pythonw).
A preparação falha se o Windows recusar criar uma tarefa; não registra isso como sucesso.

## Código e validação

Entradas: `google_calendar.py`, `App.google_*`, `ui/conexoes.js/css`, `compromissos.py` e `kani_modo.agenda_google`.
Testes não usam contas reais, não tocam áudio e simulam o Agendador de Tarefas.

```powershell
py -3.13 verificar.py --area interface --arquivos google_calendar.py compromissos.py kanicode.py kani_modo.py ui/conexoes.js tests/test_google_calendar.py tests/test_conexoes_ui.py
```

Mudanças Python exigem reabrir o KaniCode; não reiniciar o processo do usuário durante uma tarefa.
O fluxo com uma conta real depende do projeto OAuth e da autorização do usuário no navegador.

## Google Drive

Abra **engrenagem à direita → Conexões → Google Drive**. Ative a Google Drive API no projeto Google.
Use **Usar configuração do Calendar** para reaproveitar somente o cadastro OAuth (ID/segredo do aplicativo),
ou importe um JSON OAuth Desktop. Depois clique **Conectar Google Drive** e autorize no navegador.
O Drive solicita `https://www.googleapis.com/auth/drive`. A autorização é independente do Calendar;
nenhum token do Calendar é copiado. As contas podem ser diferentes.

Contas conectadas com a permissão antiga continuam consultando. Clique **Autorizar controle total** para
ampliar a permissão no Google, sem desconectar o Calendar. Até concluir, a API recusa alterações e a UI
mantém escrita desabilitada. Cancelar essa autorização preserva a conexão anterior.

A busca é pelo nome, 50 itens por página, com filtro de pasta ou lixeira. **Entrar** navega nas pastas;
**Meu Drive**, **Todos os arquivos** e **Lixeira** mudam a consulta. **Abrir** usa o navegador configurado.
**Enviar arquivo** cria um novo arquivo no destino aberto (ou Meu Drive); **Nova pasta** cria uma pasta ali.
O menu **⋯** de cada item permite baixar, renomear, mover, enviar à lixeira ou restaurar.
Para mover, cole o link ou ID da pasta destino; vazio significa Meu Drive. Não existe exclusão definitiva.

Downloads binários são gravados em arquivo temporário na pasta escolhida e publicados ao terminar,
sem sobrescrever arquivos locais existentes. Google Docs/Sheets/Slides exportam para DOCX/XLSX/PPTX,
com PDF opcional; desenho Google exporta para PDF. Outros formatos são aceitos pela API conforme o tipo.
A API do Google limita a exportação de documentos; erros são informados sem publicar download parcial.
Pastas não são baixadas como ZIP: os arquivos são baixados individualmente. Atalhos não são exportados.
Uploads usam sessão retomável e blocos de 4 MiB, sem carregar todo o arquivo em memória. Nesta versão,
se o envio falhar, não há retomada automática; confira o destino antes de repetir para evitar duplicatas.

Ferramentas da Kani, somente quando solicitadas pelo usuário:
- `drive_buscar {busca, proxima, pasta, lixeira}`: nomes, IDs, links e metadados.
- `drive_criar_pasta {nome, pasta}`: `pasta` é ID do destino ou `root`.
- `drive_enviar {caminho, pasta}`: arquivo local completo; cria um arquivo novo.
- `drive_baixar {id, destino, formato}`: pasta local completa; formato opcional.
- `drive_renomear {id, nome}` e `drive_mover {id, pasta}`.
- `drive_lixeira {id, restaurar}`: `false` move à lixeira; `true` restaura.

Confira IDs e destino antes de alterar. Não há edição do conteúdo dos arquivos nem compartilhamento
pela integração. As APIs `App.drive_enviar(caminho, pasta)` e `App.drive_baixar(id, destino, formato)`
aceitam caminhos explícitos para testes/agentes, sem abrir diálogos nativos. A UI abre seletores apenas
quando o usuário pede envio/download. Testes não usam credenciais reais nem alteram o Drive do usuário.

Segredos protegidos por DPAPI e cache próprios ficam em `D:/Kanivete/KaniCode/conexoes/drive/`.
Desconectar limpa token e cache do Drive sem afetar o Calendar. Sem rede, uma falha na sincronização
mantém a última listagem e mostra o erro. Não existe sincronização periódica do Drive.

Código: `google_drive.py`, `google_drive_arquivos.py`, `App.drive_*`, `ui/conexoes_drive.js`; OAuth/PKCE compartilhado com `google_calendar.py`.
Testes isolados: `tests/test_google_drive.py`, `tests/test_google_drive_arquivos.py` e `tests/test_conexoes_ui.py`. Verificar:

```powershell
py -3.13 verificar.py --area interface --arquivos google_drive.py google_drive_arquivos.py google_calendar.py kanicode.py kani_modo.py ui/conexoes.js ui/conexoes_drive.js tests/test_google_drive.py tests/test_google_drive_arquivos.py tests/test_google_calendar.py tests/test_conexoes_ui.py
```

Referências: [files.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list),
[permissões](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).
