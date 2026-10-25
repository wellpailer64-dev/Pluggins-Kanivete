# Perfil portátil e Google Drive do KaniCode

O perfil pode ser exportado localmente ou sincronizado com o Google Drive. O acesso usa OAuth do Google Drive já integrado ao KaniCode, com autorização persistente protegida por DPAPI em cada PC. O e-mail do cadastro precisa corresponder ao e-mail retornado pelo Google autenticado; preencher o cadastro não autentica ninguém.

## E-mail e senha do KaniCode

O painel **Meu perfil → Backup e sincronização do perfil** contém **Seu acesso KaniCode**. Na primeira abertura sem uma sessão lembrada, esse painel aparece para pedir o acesso. A senha é adicional à autorização Google; ela libera o sincronizador do perfil no aplicativo, não bloqueia o uso local do KaniCode nem criptografa os arquivos JSON já existentes no Drive.

- **Cadastrar:** autorize o Google, preencha e-mail e uma senha própria do KaniCode com pelo menos 12 caracteres, repita a senha e clique **Salvar meu acesso**. O e-mail informado deve corresponder à conta confirmada pelo Google. Ao concluir, a sincronização é ativada automaticamente.
- **Outro PC:** autorize o mesmo Google Drive, informe o mesmo e-mail e senha e clique **Entrar no meu perfil**. O perfil remoto é localizado e pode ser conferido/restaurado. Não cadastre uma segunda senha.
- **Lembrar acesso neste PC:** guarda somente uma sessão vinculada ao cadastro remoto, cifrada com DPAPI do usuário Windows. A senha não é guardada. Sem a opção, o acesso dura até o processo fechar.
- **Sair do acesso neste PC:** invalida a sessão local e interrompe o automático até novo login, preservando arquivos locais, autorização Google e dados remotos. Não encerra os outros PCs.
- **Senha esquecida:** esta versão não tem recuperação ou troca de senha. Guarde a senha ao cadastrar. Cadastrar novamente não substitui a senha existente.

Em `KaniCode/acesso-kanicode.json`, o Drive guarda e-mail, sal aleatório de 16 bytes e hash PBKDF2-HMAC-SHA256 com 600 mil iterações. Nunca guarda a senha legível. O registro de acesso e `perfil/acesso.dpapi` ficam fora do pacote portátil. Cada operação de sincronização verifica a autorização Google, o cadastro remoto e a sessão; senha errada ou cadastro remoto alterado não libera baixar, restaurar ou publicar pelo sincronizador. O Google continua sendo a proteção efetiva do Drive privado, inclusive se a pasta for acessada fora do KaniCode.

## Entrar e sincronizar

1. No avatar **Meu perfil** da lateral, salve seu e-mail em **Informações básicas**.
2. Abra **Backup e sincronização do perfil**, clique **Entrar com Google** e autorize a conta no navegador. Se preciso, importe a configuração OAuth Desktop; a ajuda está em Configurações → Conexões → Google Drive. Cada novo computador precisa dessa configuração e da autorização própria; tokens não viajam no perfil.
3. Cadastre ou entre com sua senha própria no bloco **Seu acesso KaniCode**. Ao concluir, a sincronização é ativada; você também pode usar **Ativar sincronização** depois de uma pausa. O app cria/localiza a pasta **KaniCode** na raiz do Meu Drive e salva versões JSON do perfil. Ao reabrir o app, a autorização e a opção de sincronizar são mantidas neste PC. A conferência automática ocorre a cada minuto enquanto a janela do app estiver carregada.
4. Em outro computador, autorize o Google e entre com o mesmo e-mail e senha do KaniCode. O perfil é localizado automaticamente. No primeiro acesso, use **Conferir versão do Drive**, revise e restaure. Essa conferência evita substituir preferências existentes no novo PC sem revisão.
5. Após estabelecer a primeira versão em comum, mudanças locais são enviadas automaticamente. Mudanças do Drive são restauradas com backup se o conteúdo local não mudou; tarefas em execução impedem restauração e o app tenta novamente depois. Rotinas novas/alteradas sempre exigem conferência.
6. Se os dois PCs mudarem, confira uma versão do Drive ou escolha **Usar perfil deste PC no Drive**. Esse botão exige uma conferência atual das revisões e cria uma nova versão. Edições simultâneas são preservadas como ramos; escolha a versão desejada e publique o perfil resultante para reunir os ramos.
7. **Pausar** interrompe o automático neste PC. Desconectar o Drive também impede acesso. Nenhuma versão remota é apagada.

As versões são imutáveis, identificadas por arquivo e revisão; os pais registram a linhagem. Se duas máquinas enviarem juntas, ambas permanecem no Drive. Falhas de rede não substituem versões. Duas pastas KaniCode na raiz são tratadas como ambiguidade, exigindo organização no Drive antes de continuar. O pacote continua JSON legível e privado à conta Drive conforme as permissões da pasta; não há criptografia adicional do conteúdo.

`perfil/nuvem.json` guarda ativação e revisão-base somente no PC; não é exportado. A foto do avatar, sessões, credenciais e caches continuam locais.

## O que já pode ser levado

- Preferências de estado explicitamente portáteis: agente padrão (`quem`), janela fixada (`fixa`) e sons da bolinha (`sons_bolinha`).
- Caderno da Kani (`kani_notas.md`), se existir.
- Cadastro (`perfil/usuario.json`), dados próprios e históricos do cérebro (`cerebro/*.json`, `.jsonl` e `.md`).
- Memórias Markdown consultadas pelo cérebro nas contas do Claude, sem credenciais: são copiadas para `cerebro/memorias/<projeto>/` e lidas pelo cérebro no destino. O índice MEMORY.md e a estrutura das contas não são transferidos; nomes/caminhos citados no texto permanecem referências.
- Regras por projeto (`regras/*.md`) e lições (`licoes/*.jsonl`).
- Preferências curadas (`preferencias/*.json` e `.md`), incluindo o método de organização dos clientes e suas evidências.
- Modelos reutilizáveis de contratos guardados em `contratos/` (`.json` e `.md`), quando existirem. Não são as tarefas/conversas em andamento.
- Definições de rotinas personalizadas. O pacote inclui a combinação das rotinas instaladas com as personalizações do usuário. Ao restaurar, ficam em `perfil/rotinas.json`, sem editar o código instalado.

O pacote não leva as credenciais Claude/Codex/Google, autorizações DPAPI, sessões, conversas, mapa do disco, caches, pesos dos modelos, dispositivos, posições de janela, pastas de projetos nem a autorização permanente de ações (`sempre.json`). As preferências podem conter nomes e caminhos antigos como evidência histórica, sem transformá-los em configuração ativa da nova máquina.

As ferramentas integradas e as instruções embutidas no código pertencem à versão do KaniCode. O perfil registra uma assinatura dessa instalação e avisa se o destino for diferente; ele não transfere nem instala o código dessas ferramentas. Dependências e plugins que uma rotina chamar precisam existir no computador de destino.

## Uso na interface do PC

1. Abra **Meu perfil** na lateral e escolha **Backup e sincronização do perfil**.
2. Clique **Exportar meu perfil**. O caminho do JSON aparecerá para selecionar/copiar.
3. Leve esse arquivo ao notebook. Com uma instalação compatível do KaniCode, abra **Meu perfil** e selecione o arquivo em **Conferir perfil de outro PC**.
4. Confira os itens novos, iguais, conflitantes e os diffs. Escolha se as diferenças devem manter o conteúdo local ou usar o conteúdo do perfil importado. A escolha vale para os arquivos conflitantes inteiros; esta etapa não faz fusão semântica de textos.
5. Clique **Restaurar este perfil** com todas as tarefas paradas. Uma cópia dos valores anteriores é salva em `perfil/restauracoes/` antes das alterações.
6. Reinicie pelo botão do topo para aplicar as preferências. Nenhuma rotina é executada pela importação.

A prévia não altera os dados. Se as preferências locais mudarem entre a conferência e o clique de restaurar, a restauração é recusada até nova conferência. Erros durante a gravação tentam reverter os arquivos já gravados. Uma interrupção abrupta do processo/energia pode exigir recuperação pela cópia anterior indicada; não há transação distribuída nesta etapa.

O pacote é JSON legível e pode conter informações pessoais nas memórias e regras. A verificação de hashes detecta corrupção, não comprova a identidade de quem criou o arquivo. Confira a origem e os comandos das rotinas antes de restaurar um perfil de terceiros.

## Linha de comando (somente exportação e conferência)

```powershell
py -3.13 perfil_portatil.py resumo
py -3.13 perfil_portatil.py exportar
py -3.13 perfil_portatil.py conferir "D:/caminho/perfil.json"
```

Os arquivos exportados ficam em `<DADOS>/perfil/exportacoes/`. Uma identidade de perfil local é criada com UUID; a autenticação remota é feita separadamente pelo Google Drive. `revisao` é o hash estável dos conteúdos portáteis, preparado para controle de versões e conflitos da sincronização futura. `perfil/identidade.json` nunca armazena login nem senha.

## Limites atuais

O código das ferramentas e dependências não é transferido. Caminhos citados nas memórias não são adaptados automaticamente. A restauração mantém arquivos locais ausentes no pacote remoto; exclusões não são propagadas. Novos PCs e conflitos exigem revisão. Reinicie pelo botão do topo para aplicar preferências de interface restauradas.

## Verificação

```powershell
py -3.13 -m unittest discover -s tests -p test_perfil_portatil.py -v
py -3.13 verificar.py --area infra --arquivos perfil_portatil.py ui/perfil_portatil.js kanicode.py mcp_equipe.py ui/janela.html tests/test_perfil_portatil.py
```

Os testes usam dados sintéticos em `D:/kanivete_testes` e não restauram perfis nos dados reais do usuário.
