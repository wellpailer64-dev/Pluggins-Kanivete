# Missões longas do Claude

O KaniCode usa o Claude Code instalado e conserva o ID para `--resume`. Não repete
pedidos automaticamente quando o processo cai: uma edição ou exportação pode ter
terminado mesmo sem resposta. Ao enviar a próxima mensagem, a reabertura recebe o
registro anterior e a orientação de conferir o estado real antes de agir.

## Ponto de retomada

O Claude tem a ferramenta `mcp__equipe__missao`: sem argumentos lê; com campos
atualiza objetivo, concluido, proximo, referencias e observacoes. As listas são
fotografias completas, substituem as anteriores. Deve atualizar no início de uma
missão longa, após cada etapa relevante e antes de encerrar. Após compactação,
deve consultar a ferramenta novamente. É orientação ao agente, não uma garantia
de que todo trabalho será registrado nem uma verificação automática da edição.

Em vídeo, registrar IDs de timelines/clipes, faixas, tempos, arquivos, parâmetros
de exportação e como conferir o resultado. Coordenadas de mouse são secundárias:
a posição e o tamanho dos painéis podem mudar. Um retorno de ferramenta só indica
que ela respondeu; validar o resultado no projeto ou arquivo antes de anotar como concluído.
O registro não salva o projeto do Kanivete nem concede autorização para salvá-lo.

## Disco e diagnóstico

Cada sessão tem sua pasta em `D:/Kanivete/KaniCode/continuidade/` (a raiz acompanha
DADOS). `estado.json` acompanha pedidos, ferramentas ainda sem resposta, tarefas em segundo plano e término;
`missao.json` guarda o resumo do agente; `eventos.jsonl` conserva stderr, erros de
ferramentas sem o corte visual de 3 mil caracteres, resultados e eventos inválidos.
O vínculo pelo projeto e ID da sessão permite reencontrar os arquivos após reiniciar.
Abas com sessões distintas têm registros separados. Fechar o processo sem resultado
marca a execução como interrompida; um processo encerrado abruptamente junto do
KaniCode pode deixar o estado em execução, também sujeito à conferência na retomada.

Os registros ficam locais e podem conter texto e caminhos da tarefa. Falha de gravação
é avisada no chat; arquivo corrompido não é substituído silenciosamente por um vazio.
A leitura do contexto de reabertura é limitada; a ferramenta permite ler o registro completo.
Não existe reinício em loop, repetição automática de comandos ou compra de cota.

## Verificar

`py -3.13 verificar.py --area claude`

Os testes usam processos e protocolo simulados, sem consumir tokens do Claude,
sem abrir aplicativos nem se conectar ao Kanivete do usuário.
