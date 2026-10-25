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

**Agente**: pedidos enviados pela fila e pendências combinadas para depois. Lista compartilhada entre agentes e
conversas, separada da pessoal em `tarefas_agente.json`, com o mesmo bloqueio entre processos e gravação atômica.
Cada pedido mantém ID da mensagem, conversa, pasta, agente e cópia do texto original. `Ver pedido` recupera esse
texto mesmo após reinício; `Localizar na conversa` destaca a mensagem carregada (sem adivinhar entre duplicatas).
O snapshot é do texto: anexos continuam no histórico/fluxo original da conversa.

Entregar a mensagem não conclui a tarefa. A fila indica em andamento; o agente registra conclusão com resultado
conferido usando `tarefa_agente` (Claude/Kani/Pickle) ou a CLI abaixo (Codex). Ao concluir, a linha fica riscada em
**Finalizadas** e sai da lista aberta. O checkbox permite concluir/reabrir manualmente. Falha, interrupção,
reinício e planejamento sem execução não viram conclusão. Resposta encerrada sem confirmação fica aberta como
**Conclusão a confirmar**. Pendência explicitamente adiada não é sobrescrita pelo encerramento do turno.

Ao combinar algo para depois, `anotar(ref,titulo)` cria uma pendência com o mesmo pedido de origem. Concluir o
pedido principal não conclui suas pendências. `adiar(ref,motivo)` mantém o próprio pedido aberto. Os agentes recebem
somente a ref atual e até três títulos de pendências da mesma pasta; texto completo vem só ao consultar `ler`.
Não há execução automática de pendências após reiniciar. A captura vale para novos envios e a fila pendente já
persistida; não interpreta retroativamente conversas antigas nem usa uma chamada extra de IA para extrair tarefas.

```powershell
py -3.13 tarefas_agente.py listar
py -3.13 tarefas_agente.py ler --ref ID
py -3.13 tarefas_agente.py anotar --ref ID --titulo "Conferir no celular"
py -3.13 tarefas_agente.py adiar --ref ID --motivo "Falta o teste no aparelho"
py -3.13 tarefas_agente.py concluir --ref ID --motivo "Implementado e conferido"
```

Verificação da lista pessoal, agentes, UI e integração da fila: `py -3.13 verificar.py --area tarefas`.

Acima do “Pronto”, uma faixa estreita espelha a quantidade de tarefas abertas do agente e seus títulos
resumidos, com rolagem horizontal no celular. Clicar abre a aba Agente; uma tag também mostra o pedido
original. Usa a mesma consulta e o mesmo filtro da lista, atualiza nos eventos e a cada 15 segundos
com a tela visível. Não cria outra lista nem chama IA. Concluídas e canceladas deixam o espelho.

Código: `tarefas.py`, `ui/tarefas.js/css`, `ui/paineis.js`, `kanicode.py`, `kani_modo.py`.
Testes isolam rede, contas e agendador; não disparam avisos reais:

```powershell
py -3.13 verificar.py --area interface --arquivos tarefas.py compromissos.py kanicode.py kani_modo.py movel.py ui/paineis.js ui/tarefas.js ui/movel.js tests/test_tarefas.py tests/test_tarefas_ui.py tests/test_conexoes_ui.py
```
