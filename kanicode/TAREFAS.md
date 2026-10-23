# Tarefas e agenda

O botão To-do fica abaixo de Atividades, no trilho direito. Os dois compartilham a coluna:
trocar entre eles não aumenta a janela novamente. No celular, abra pelo menu Tarefas e agenda.

**Tarefas**: adicionar título e prazo opcional, editar, concluir e reabrir. A lista é pessoal,
compartilhada por todas as conversas. Fica em `D:/Kanivete/KaniCode/tarefas.json`, com gravação
atômica e bloqueio entre processos. Erro de leitura não sobrescreve a lista. Concluídas ficam
recolhidas; não há exclusão permanente. O painel aberto atualiza a cada 15 segundos.

**Agenda**: próximos sete dias dos lembretes locais, calendários Google selecionados e cache
dos compromissos Pandalab. Atualizar sincroniza o Google; abrir usa a última sincronização.
Eventos Google são somente leitura. Novo lembrete usa `compromissos.py`, avisos falados locais
e o Agendador existente. O PC precisa estar ligado, com sessão Windows e áudio disponíveis.
Lembretes futuros entram no horizonte de 36 horas do preparador periódico existente.
Se a preparação falhar depois de gravar, a tela pede para conferir a agenda antes de repetir.

A Kani dispõe de `todo_listar`, `todo_salvar`, `todo_concluir`, `todo_agenda` e `todo_lembrar`.
Essas ferramentas registram demandas pessoais pedidas/combinadas; não etapas internas do agente.
Os métodos `App.todo_*` usam o mesmo armazenamento; estão liberados na ponte móvel autenticada.

Código: `tarefas.py`, `ui/tarefas.js/css`, `ui/paineis.js`, `kanicode.py`, `kani_modo.py`.
Testes isolam rede, contas e agendador; não disparam avisos reais:

```powershell
py -3.13 verificar.py --area interface --arquivos tarefas.py compromissos.py kanicode.py kani_modo.py movel.py ui/paineis.js ui/tarefas.js ui/movel.js tests/test_tarefas.py tests/test_tarefas_ui.py tests/test_conexoes_ui.py
```
