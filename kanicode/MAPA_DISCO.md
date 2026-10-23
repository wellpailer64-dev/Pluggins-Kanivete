# Mapa vivo do disco D

O **Mapa do disco D**, no menu de ferramentas do KaniCode e no menu do celular, permite procurar clientes, arquivos e pastas e navegar pela estrutura do disco. A Kani usa o mesmo índice em `buscar_arquivos` e na ferramenta `mapa_d`. Os agentes têm acesso pelo MCP `mapa_d` e pela linha de comando.

## O que fica guardado

Banco local em `D:/Kanivete/KaniCode/mapa_d/indice.sqlite3`, com SQLite FTS5: nome, caminho, pasta de origem, extensão, tamanho e data de alteração. Não guarda o conteúdo, não manda o inventário para a internet e não abre os documentos durante a indexação. Busca por palavras no nome e no caminho, com prefixos e sem exigir os acentos; não faz análise semântica do conteúdo.

A primeira varredura percorre o D acessível ao usuário. Ficam fora a Lixeira, System Volume Information, a própria pasta do índice e `D:/kanivete_testes`; links simbólicos e junções não são seguidos para evitar ciclos e sair do disco. Permissões negadas são informadas, sem elevar privilégios.

## Atualização e limites

- Um processo próprio observa o disco com `ReadDirectoryChangesW` e atualiza criações, alterações, exclusões e renomeações; mover uma pasta atualiza os caminhos dos descendentes.
- O monitor começa antes da varredura para guardar as mudanças que chegarem durante a construção. A primeira varredura e as reconferências podem levar vários minutos em um disco grande.
- O monitor é registrado no início de sessão do usuário atual no Windows (HKCU Run, `KaniCodeMapaDiscoD`), sem administrador. O KaniCode também o inicia e a busca o religa se necessário. Ele continua durante o reinício do KaniCode e não executa com o Windows desligado. Ao iniciar de novo, reconfere o inventário inteiro para recuperar mudanças desse intervalo.
- A cada seis horas há nova conferência. Se o Windows informar perda de eventos, o serviço reconfere o disco. Se o monitor nativo falhar, o estado indica modo periódico, com conferência a cada cinco minutos.
- `parcial=true` significa construção em andamento, acesso incompleto, limite de resultados ou monitor a conferir. Nenhum resultado nessa situação prova que o arquivo não existe.
- Cada resultado é conferido no disco antes de retornar: caminhos já inexistentes são omitidos. Ainda assim, um arquivo pode mudar depois da consulta; confira-o novamente antes de abrir ou executar qualquer ação.
- `status` informa progresso, última conferência, atividade do monitor e pastas sem acesso. O mapa não altera, move nem apaga arquivos do usuário.

## Linha de comando (na pasta do plugin)

```powershell
py -3.13 mapa_d.py instalar  # registra início no logon do usuário atual
py -3.13 mapa_d.py iniciar
py -3.13 mapa_d.py status
py -3.13 mapa_d.py buscar "Camila" --ext pdf --limite 20
py -3.13 mapa_d.py buscar "Camila" --pastas
py -3.13 mapa_d.py listar --pasta "D:/01 - ALL IN CLOUD - HD PAILER"
```

`construir` permite construir um banco de teste isolado com `--raiz` e `--banco`; não execute uma segunda construção manual no banco de produção enquanto o monitor estiver ativo. O serviço usa trava de instância para evitar dois monitores no mesmo banco.

## Verificação

```powershell
py -3.13 -m unittest discover -s tests -p test_mapa_d.py -v
py -3.13 verificar.py --area kani --arquivos mapa_d.py mapa_d_monitor.py ui/mapa_d.js kanicode.py movel.py mcp_equipe.py codex_contexto.py tests/test_mapa_d.py
```

Os testes criam dados sintéticos apenas em `D:/kanivete_testes`, incluindo um teste com notificações reais do Windows e encerramento controlado do monitor de teste.
