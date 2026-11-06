# Extensão e scripts do KaniBrowser

`mapa` e `panorama` aceitam `{"cobertura":true}`. Cada controle recebe `cobertura` com estado
`livre`, `parcial`, `bloqueado` ou `fora_tela`, pontos testados/livres e primeiro bloqueador (seletor/tipo).
Usa nove pontos da área recortada e elementFromPoint: filhos contam como o próprio controle;
camadas com pointer-events:none não bloqueiam. É diagnóstico de ponteiro por amostragem,
não prova de visibilidade visual nem de clique bem-sucedido. Formas irregulares, transforms,
iframes e shadow DOM podem limitar a precisão. Não altera cliques nem tenta remover sobreposições.

O mapa informa `na_tela` por controle; `{"na_tela":true}` filtra pela interseção geométrica
com a janela e ancestrais que recortam conteúdo. Não detecta sobreposição por outros elementos.
Panorama informa `foco` (seletor, nome e tipo), sem ler o valor do campo; fora da região retorna null.
Esses dados são uma fotografia do momento e não garantem que um clique será recebido.

Leitura por região: `ler`, `mapa`, `midias` e `panorama` aceitam `{"regiao":"#main"}`.
O seletor deve encontrar exatamente um elemento visível; ausência ou ambiguidade gera erro,
sem ampliar silenciosamente para a página inteira. `seletor` continua sendo filtro de controles no mapa.
Panorama retorna `paineis` (até 20) e `total_paineis`: menus, listboxes, diálogos e popovers
visíveis dentro da região. Cada painel informa tipo, nome, seletor e estado modal.
O mapa inclui menuitem/option e estados `expandido`/`selecionado` quando declarados por ARIA.
Detecção depende de marcação semântica do site; menus implementados só com divs podem não aparecer.

O mapa prefere seletores únicos por ID, data-testid, aria-label, name, placeholder ou title,
antes do caminho por posição. A unicidade vale no DOM atual; refaça o mapa após mudanças.
Nomes reconhecem aria-labelledby. Estado desabilitado considera fieldset, inert e aria-disabled
nos ancestrais; ações recusam esses controles. Isso não implementa toda a árvore de acessibilidade.

## WhatsApp: contexto compacto

`scripts rodar --nome whatsapp_eventos` instala um MutationObserver restrito ao grupo KaniCode.
Entrega mensagens por ID em uma fila na página, sem clicar, rolar ou tocar áudio.
Eventos só saem da fila ao receber `{"confirmados":["ID"]}`; `{"conferir":true}` refaz a varredura.
O observador sinaliza `reiniciado` quando é reinstalado: essa fotografia inicial serve de histórico,
não de pedido novo. IDs simples usam a mesma heurística geométrica de autoria do leitor wa.py.
Depende do DOM carregado e da aba da Kani no grupo; não é integração oficial com o servidor do WhatsApp.

`wa_comando.py ouvir` mantém uma espera assíncrona pela ponte privada existente. O observador
resolve essa espera quando há eventos pendentes, sem consulta periódica de 2 segundos nem
servidor/porta adicional. A espera não segura a trava de trabalho da Kani. A cada 60 segundos
sem eventos, confere o estado e refaz a varredura; usa leitura tradicional se o script falhar.
Essa conferência periódica é silenciosa no painel; `--a-cada` ajusta o prazo entre 1 e 60 segundos.
Reconexão ou falha do observador pode levar esse prazo de segurança.
O filtro ignora também `KANI:` sem emoji (o DOM pode omiti-lo); avisos deste processo são
serializados para não digitarem simultaneamente no mesmo editor.
Recepção, avisos e preparo/encaminhamento têm trabalhadores separados; áudio demorado não bloqueia
a detecção nem a confirmação de novos pedidos. O primeiro aviso é "Estou ouvindo seu áudio!"
ou "Recebi seu pedido.". Envio pelo browser ainda tem seu próprio tempo e pode falhar.
Não promete execução antes da gerente começar; a orientação de início acompanha o pedido.
`wa_comando.py estado` mostra as últimas 20 etapas persistidas no SQLite e o log registra tempos.
Trabalhos recebidos aguardando preparo sobrevivem à reinicialização; encaminhamento interrompido
fica `incerto`, sem repetição automática. Toda partida marca o DOM atual como histórico; não importa
pedidos antigos não recebidos. Um único ouvinte é permitido por pasta. A tarefa solta dura 120 minutos
por padrão; não é serviço permanente. Limites na página: até 400 eventos e 2000 IDs recentes.

`scripts rodar --nome whatsapp_contexto` informa conversa aberta, disponibilidade da busca/editor,
presença de rascunho (sem expor conteúdo) e quantidade de mensagens carregadas.
Para ler: `--dados @arquivo.json` com `{"conversa":"KaniCode","n":3}`.
Exige nome completo da conversa aberta; recusa divergência antes de ler mensagens. Limite: 30 mensagens,
2000 caracteres por mensagem. Só lê o DOM carregado, sem rolar ou recuperar histórico; referências são
metadados do WhatsApp, não interpretação de autoria. Indicadores de mídia são heurísticos.
Não toca áudio, não clica e não envia. Restrito à origem `https://web.whatsapp.com`.
Para abrir/localizar conversas, histórico e mídia original, reutilize `wa.py --porta 9333`.
O panorama genérico pode misturar a lista lateral com a conversa; prefira este script no WhatsApp.

## Novidades 0.2.0

`extensao estado` verifica `pronta` e a versão do motor, além de `carregada`.
A ponte valida versão e prontidão antes de agir; motor antigo pede `extensao instalar`.
A recarga pode exigir o reinício normal do KaniCode quando a ponte Python mudou.

Novas ações (sempre com `--dados @arquivo.json`):

| Ação | Dados de exemplo |
| --- | --- |
| `selecionar` | `{"seletor":"#idioma","valor":"pt"}`; select múltiplo aceita lista de valores |
| `marcar` | `{"seletor":"#aceite","marcado":true}`; para trocar radio marque outra opção |
| `clicar` | `{"seletor":"#buscar","aguardar":{"seletor":"#resultado","prazo_ms":5000}}` |
| `tecla` | `{"seletor":"#busca","tecla":"Enter","aguardar":{"url":"/resultado"}}` |
| `aguardar` | `{"texto":"Concluído","prazo_ms":5000}` |

As condições `seletor`, `texto` e `url` combinam entre si; URL/texto buscam um trecho.
`ausente:true` com seletor espera desaparecer. Prazo máximo: 15 segundos.
`confirmado:true` significa que a condição foi observada, não que um envio foi aceito pelo servidor.
Sem condição, clique/tecla retornam execução sem confirmação; prazo esgotado retorna `confirmado:false`.
Ações não são repetidas automaticamente. Erro durante navegação exige conferir a página antes de tentar de novo.
Clique exige elemento único e disponível; controles especiais podem exigir adaptação.
Clique DOM não equivale a gesto físico confiável para recursos protegidos do navegador.
Teclas usam CDP real: Enter, Tab, Escape, ArrowDown, ArrowUp e Backspace.
Enviar/publicar em terceiros continua exigindo pedido explícito; uma espera não concede autorização.

`ler` e `panorama` aceitam `principal:true`: procuram main/article e ignoram navegação,
cabeçalhos, rodapés e laterais; sem região semântica, usam o corpo filtrado. É uma heurística.
O mapa informa estados de radio/checkbox e até 100 opções por select, sem valores de senhas.
`digitar` recusa checkbox/radio/botões; use as ações específicas.

`midias` e `panorama` aceitam `max_imagens`, `max_videos` (inclusive zero) e `carregadas:true`.
Panorama usa por padrão até 10 imagens carregadas e 5 fontes de áudio/vídeo; informe
`carregadas:false` para incluir imagens ainda não carregadas. Totais e `truncado` indicam cortes.
`scripts rodar --nome extrair_links` aceita `visiveis:true` e `com_nome:true` para filtrar links.

Primeira versão local: Manifest V3 em `extensao/`. O Chrome do KaniBrowser carrega a extensão
ao abrir, por `Extensions.loadUnpacked` no pipe privado, com `--enable-unsafe-extension-debugging`.
Não usa porta de depuração, loja ou servidor HTTP de comandos. O navegador continua abrindo se a
extensão falhar; `extensao estado` mostra o erro. A flag é restrita ao processo do KaniBrowser.

Após atualizar o código, reiniciar **o KaniCode** pelo fluxo normal (espera as tarefas).
A primeira ativação no processo já aberto não acontece por editar arquivos no disco.
Os testes usam Chrome real, perfil sem conta e HTTP local em `D:/kanivete_testes`.

## CLI e API Python

Sempre usar `py -3.13 D:/Kanivete/Plugins/kanibrowser/kb.py --onde kanicode` como prefixo.
Os exemplos abaixo mostram os argumentos depois desse prefixo:

| Comando | Resultado |
| --- | --- |
| `extensao estado` | Versão do Chrome, ID, estado e erro da extensão |
| `extensao instalar` | Carrega/recarrega somente a extensão própria desta pasta |
| `extensao gerenciar` | Abre `chrome://extensions/` no navegador interno |
| `extensao ler` | Texto, seleção, título e URL |
| `extensao mapa` | Até 300 campos, botões e links visíveis, com nome e seletor CSS |
| `extensao panorama` | Uma chamada com texto, seleção, mapa e fontes de mídias |
| `extensao midias` | URLs atuais, src/srcset e dimensões das imagens; fontes de áudio/vídeo |
| `extensao digitar --dados '@D:/kanivete_testes/entrada.json'` | Preenche um campo único, dispara input/change, sem enviar formulário |
| `extensao copiar --dados '@D:/kanivete_testes/entrada.json'` | Copia texto ou a seleção para o clipboard do Windows |
| `extensao api --dados '@D:/kanivete_testes/entrada.json'` | GET/HEAD na origem da página, com a sessão logada, resposta limitada e prazo de 15 s |
| `extensao baixar --dados '@D:/kanivete_testes/entrada.json'` | Inicia download HTTP/HTTPS direto; retorna ID, não confirmação de arquivo salvo |
| `extensao download --dados '@D:/kanivete_testes/entrada.json'` | Consulta o ID: só `complete` confirma conclusão; `interrupted` indica falha |
| `scripts listar` | Scripts locais, origens, declaração de alteração e SHA-256 |
| `scripts rodar --nome extrair_links` | Executa script na origem autorizada, sem duplicar links |

Dados são objetos JSON. Arquivos UTF-8 com ou sem BOM (inclusive os gerados pelo PowerShell) são aceitos.
Para filtrar `mapa` ou o mapa de `panorama`, use `{"tipo":"campos","texto":"busca","maximo":10}`.
`tipo` aceita `campos`, `botoes` ou `links`; `texto` busca no nome sem distinguir acentos/maiúsculas.
`seletor` restringe por CSS. Os filtros combinam entre si; `maximo` limita de 1 a 300 resultados.
O retorno distingue `total` visível, `encontrados` após filtros e `truncado` quando há mais resultados.
Em `panorama`, `limite` controla o tamanho do texto; os filtros atingem somente o mapa.
Exemplos de conteúdo de `entrada.json`:

```json
{"seletor":"#nome","texto":"Olá, Pailer!"}
```

Para copiar: `{"texto":"Texto escolhido"}`. Para API: `{"url":"/api/itens","limite":12000}`.
Para baixar: `{"url":"https://site.exemplo/arquivo.mp4"}`. Para consultar: `{"id":1}`.
A API autenticada da ponte expõe `extensao(acao, dados)` e
`scripts_browser(acao, nome, dados, permitir_alteracao)`; não existe endpoint aberto a sites.

## Biblioteca reutilizável

Um par `scripts/nome.js` + `scripts/nome.json` por automação, em UTF-8. Nome: letras minúsculas,
números, `_` ou `-`. JS é o corpo de uma função async que recebe `dados` e aceita `return`.
O script `extrair_links` é o primeiro exemplo. Metadados obrigatórios:

```json
{
  "descricao": "Extrai dados do painel autorizado",
  "origens": ["https://painel.exemplo.com"],
  "altera_pagina": false
}
```

As origens são conferidas antes e dentro da execução. `http://*` e `https://*` são curingas explícitos
para leitores universais. Scripts com `altera_pagina: true` exigem `--permitir-alteracao`.
Essa declaração não analisa nem torna confiável um script: o código da biblioteca é código local
do operador, com acesso ao DOM da página. Não copiar scripts de um site para a biblioteca e rodar
automaticamente. Automações novas continuam sujeitas ao catálogo/RAG e aos pedidos do Pailer.

## Limites desta versão

- Opera na aba da Kani. Primeiro navegar com `kb.py --onde kanicode ir URL`. `--aba` é recusado.
- Duas abas com URL idêntica são recusadas para não atuar na aba errada.
- Lê o documento principal; iframe de outra origem, shadow DOM fechado e canvas precisam de tratamento específico.
- Digitação não preenche senha, arquivo ou campo oculto e não clica em enviar. Editores especiais podem exigir adaptação.
- Clipboard depende de contexto permitido e foco da página; ainda sem teste de clipboard nesta entrega,
  para preservar o conteúdo atual do usuário.
- Downloads usam a pasta configurada no navegador. URLs blob, DRM, manifests HLS/DASH e mídias sem fonte direta
  não viram arquivos de vídeo por este comando. Para plataformas, reutilizar `video_download.py`.
- API de leitura aceita somente mesma origem, sem redirecionar; POST/PUT/DELETE ficam para automação específica autorizada.
- Não há execução de shell a partir da página, `externally_connectable` ou receptor de `postMessage`.
- Nenhuma integração já existente do `kb.py`, WhatsApp ou ChatGPT foi substituída.

## Verificar

```powershell
$env:PYTHONPYCACHEPREFIX = 'D:/kanivete_testes/pycache'
py -3.13 -m py_compile D:/Kanivete/Plugins/kanibrowser/extensoes.py D:/Kanivete/Plugins/kanibrowser/scripts_browser.py
node --check D:/Kanivete/Plugins/kanibrowser/extensao/motor.js
node --check D:/Kanivete/Plugins/kanibrowser/extensao/olhos.js
py -3.13 D:/Kanivete/Plugins/kanibrowser/tests/test_extensao_real.py
```

O teste requer o Chrome e o FFmpeg já instalados. Gera PNG e MP4 local, baixa e compara os bytes;
confere leitura, campos, API, biblioteca, recusas, suspensão do motor e reabertura do perfil.
Não instala dependências, não usa 9222 e não acessa contas reais. As evidências ficam no D.

Referência da API: https://chromedevtools.github.io/devtools-protocol/tot/Extensions/
# Descoberta pelos agentes

`kb.py --onde kanicode estado` anuncia a extensão, se está carregada, seus comandos e este guia.
O manifesto do plugin também apresenta os comandos nas instruções do KaniCode. Codex, Claude e
Pickle recebem a orientação de consultar o estado, preferir os recursos disponíveis e listar a
biblioteca antes de criar outra automação. Sessões antigas mostram que precisam de atualização;
instalação no disco não é confirmação de carregamento no navegador aberto.

