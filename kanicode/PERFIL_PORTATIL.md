# Perfil portátil do KaniCode — etapa 1

Esta etapa cria o pacote de dados que depois poderá ser associado a uma conta. **Não há login próprio, upload nem sincronização automática nesta versão.** A exportação e a restauração são locais, no PC.

## O que já pode ser levado

- Preferências de estado explicitamente portáteis: agente padrão (`quem`), janela fixada (`fixa`) e sons da bolinha (`sons_bolinha`).
- Caderno da Kani (`kani_notas.md`), se existir.
- Regras por projeto (`regras/*.md`) e lições (`licoes/*.jsonl`).
- Preferências curadas (`preferencias/*.json` e `.md`), incluindo o método de organização dos clientes e suas evidências.
- Modelos reutilizáveis de contratos guardados em `contratos/` (`.json` e `.md`), quando existirem. Não são as tarefas/conversas em andamento.
- Definições de rotinas personalizadas. O pacote inclui a combinação das rotinas instaladas com as personalizações do usuário. Ao restaurar, ficam em `perfil/rotinas.json`, sem editar o código instalado.

O pacote não leva as credenciais Claude/Codex/Google, autorizações DPAPI, sessões, conversas, mapa do disco, caches, pesos dos modelos, dispositivos, posições de janela, pastas de projetos nem a autorização permanente de ações (`sempre.json`). As preferências podem conter nomes e caminhos antigos como evidência histórica, sem transformá-los em configuração ativa da nova máquina.

As ferramentas integradas e as instruções embutidas no código pertencem à versão do KaniCode. O perfil registra uma assinatura dessa instalação e avisa se o destino for diferente; ele não transfere nem instala o código dessas ferramentas. Dependências e plugins que uma rotina chamar precisam existir no computador de destino.

## Uso na interface do PC

1. Abra o menu de ferramentas e escolha **Meu perfil**.
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

Os arquivos exportados ficam em `<DADOS>/perfil/exportacoes/`. Uma identidade de perfil local é criada com UUID; ela ainda não é uma conta autenticada. `revisao` é o hash estável dos conteúdos portáteis, preparado para controle de versões e conflitos da sincronização futura. `perfil/identidade.json` nunca armazena login nem senha.

## Próximas etapas

1. Definir e implementar a conta do KaniCode, com recuperação de acesso e vínculo entre perfil e dispositivos.
2. Armazenar remotamente o perfil privado, autenticado e versionado, sem credenciais de outros serviços.
3. Sincronizar alterações entre computadores com revisão-base, conflitos explícitos e recuperação de versões anteriores.
4. Distribuir versões compatíveis das ferramentas/contratos integrados e adaptar caminhos/dependências por dispositivo.

## Verificação

```powershell
py -3.13 -m unittest discover -s tests -p test_perfil_portatil.py -v
py -3.13 verificar.py --area infra --arquivos perfil_portatil.py ui/perfil_portatil.js kanicode.py mcp_equipe.py ui/janela.html tests/test_perfil_portatil.py
```

Os testes usam dados sintéticos em `D:/kanivete_testes` e não restauram perfis nos dados reais do usuário.
