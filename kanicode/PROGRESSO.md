# Render e downloads

Faixa acima da entrada da conversa, compartilhada entre abas, PC e celular.
Consulta local a cada segundo, somente com a página visível; não usa IA nem contexto.
Porcentagem só aparece quando informada pela operação. Finais ficam dez segundos;
sem sinal por 25 segundos, informa “Sem atualização”, sem concluir por conta própria.
Até 64 operações em memória; nenhum histórico adicional em disco.

Fontes atuais:
- Kanivete: exportação de vídeo, pré-render e composição; download de vídeo/áudio.
  O plugin observa os callbacks já existentes e repassa os dados em lotes de 500 ms
  pelo canal local do KaniCode, sem CDP e sem mudar o resultado das funções originais.
- Drive: download/exportação pelos controles do KaniCode ou Kani, com bytes recebidos.
  Exportações sem tamanho conhecido usam barra de atividade.

O observador do Kanivete carrega junto do plugin (`painel.js` e `ponte.py`).
Depois de atualizar, precisa recarregar o plugin no Kanivete; reiniciar somente
o KaniCode não troca o código já carregado no outro processo. Não captura operações
anteriores ao carregamento nem downloads de navegadores/programas externos.

Verificar: `py -3.13 verificar.py --area progresso`.
Testes usam callbacks, rede e API simulados, Chromium isolado e socket local;
nunca conectam ao Kanivete em uso.
