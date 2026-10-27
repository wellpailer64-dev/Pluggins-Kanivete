# Colab entre chats

No Board (Ctrl+B), use **⇄ Colab**. Escolha duas abas paradas, na mesma pasta de projeto,
escreva o objetivo e clique em **Criar e planejar**. Também pode puxar o fio entre dois chats
e escolher Colab. O chat de origem coordena; os dois conservam seus modelos e históricos.

O coordenador propõe contrato das interfaces e tarefas com arquivos relativos explícitos.
O parceiro negocia/aprova a revisão; o coordenador aprova a mesma revisão e inicia executar.
Uma proposta nova invalida aprovações anteriores. Arquivo ou pasta não pode pertencer às duas abas.
Depois da execução começar o plano fica estável; impedimentos e mudanças necessárias vão ao diário.
A reserva é um acordo informado aos modelos, não uma trava de escrita no disco.

O início de executar dispara o parceiro sem esperar a resposta; o coordenador continua sua parte.
Durante a execução ambos consultam o diário e publicam avisos sem chamadas bloqueantes entre si.
Cada um registra sua entrega e evidências. Quando ambos entregam, o estado passa para integração.
O coordenador é retomado automaticamente ao ficar livre e testa o conjunto antes de finalizar.
O botão **Continuar com o coordenador** também retoma
planejamento/execução/integração pendente; também serve quando uma resposta terminou antes do parceiro.

O painel Colab mostra objetivo, fase, revisão, aprovações, arquivos, entregas e avisos em tempo real.
Os cartões dos chats mostram mensagens completas e atividade recebida, inclusive progresso do Codex,
entradas e saídas de ferramentas. O texto pode ser selecionado; mova o cartão pelo cabeçalho.
Use **Conversar aqui** para responder numa aba. A recuperação inicial mostra até 200 registros recentes;
o histórico original permanece no armazenamento de cada modelo.

## Canal dos agentes

Claude: ferramenta MCP `chat`, `acao=colab`, `de`, `para`, `texto` com objeto JSON serializado.
Codex e modelos com terminal: `py -3.13 "<pasta do plugin>/chat_colab.py" --de 1 --para 2 --acao colab`.
Sem texto, consulta o estado. Para ações, `--texto` recebe JSON; para JSON complexo prefira `--arquivo`
com caminho de um arquivo UTF-8 no D. O contexto de cada turno inclui estado e instruções do Colab.

Objeto de ação:
- `consultar`: lê o estado sem bloquear nem gravar.
- `propor`: `contrato`, `tarefas: [{aba, titulo, arquivos: [caminhos relativos]}]`.
- `aprovar` e `executar`: `revisao` numérica; executar é exclusivo do coordenador.
- `avisar`: `texto` para o diário compartilhado.
- `concluir_tarefa`: `evidencia` da entrega e da verificação da sua parte.
- `finalizar`: `evidencia` do teste integrado, exclusivo do coordenador.

O canal é o mesmo servidor local dos fios (47613); não acessa as portas do Kanivete.
Estado e diário ficam em estado.json, chave colabs, sob a trava de estado do aplicativo.
Remover um fio desliga a colaboração; não apaga arquivos ou históricos dos agentes.

Verificação isolada: `py -3.13 verificar.py --area board`.
Os testes usam motores simulados e Chromium isolado; não consomem sessões reais dos modelos.
