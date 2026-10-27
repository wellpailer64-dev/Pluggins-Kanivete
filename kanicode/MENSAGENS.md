# Fila e mensagens urgentes

Na conversa, Enter ou Enfileirar com o agente trabalhando guarda o recado sem
mandá-lo ao motor e sem cortar a resposta em andamento. Cada aba tem sua fila.
Quando o turno termina, a próxima mensagem é entregue; anexos seguem com ela.
O pedido captura o agente e a pasta da aba no momento do envio.

Duplo clique em uma mensagem marcada Na fila prioriza esse recado e solicita
interrupção do turno atual. A entrega aguarda o motor liberar a execução; não
começa um segundo trabalho simultâneo na mesma aba. As demais mensagens ficam
aguardando, na ordem. Uma mensagem já entregue não é reenviada pelo duplo clique.
O prazo de interrupção do Claude identifica o turno, evitando encerrar por engano
o turno novo. Isso interrompe o agente; um render já iniciado no Kanivete pode
continuar e deve ser conferido antes de repetir a exportação.

Parar com o campo vazio pausa a fila. Um novo envio ou uma urgência explícita a
retoma. Falha de entrega também pausa; o chat conserva o texto e mostra o motivo.
Não se entrega um pedido em outra pasta caso o projeto tenha sido trocado.

As pendentes reaparecem ao recarregar a interface ou alternar abas e ficam também
em disco (`fila/aba<N>.json` na pasta de dados): ao reiniciar o KaniCode elas voltam
PAUSADAS — nada é entregue sozinho; um novo envio ou o duplo clique retoma. A que
estava sendo entregue na hora volta como falha (pode ter chegado ao agente).
Anexos de imagem não vão para o disco. Fechar a aba descarta a fila dela.
As APIs diretas enviar/ajudante continuam disponíveis para integrações; a fila da
interface usa mensagem_enviar, mensagem_urgente e mensagens_fila.

O lápis na mensagem pendente abre a edição no próprio balão. Salvar (ou Ctrl+Enter)
altera só o texto, mantendo a posição, agente, pasta e anexos. Cancelar ou Esc descarta
a edição. O campo de nova mensagem não é usado. A alteração também atualiza o pedido
no painel Agente e persiste ao reiniciar. Editar não retoma uma fila pausada.
Se a mensagem já começou a ser entregue, a edição é recusada e o rascunho continua
no editor para copiar; nenhuma segunda entrega é criada.

Verificação: `py -3.13 verificar.py --area mensagens`. Interface: teste de Enter,
duplo clique, recarga e bolha única em `tests/test_layout.py`. Motores simulados,
sem gastar tokens nem controlar o app do usuário.
