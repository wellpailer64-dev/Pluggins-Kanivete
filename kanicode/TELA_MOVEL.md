# Tela do PC no celular

O botão 📺 abre o monitor principal. O seletor mostra os monitores conectados, com resolução,
e mantém KANIVETE como alternativa. O modo PC mostra e controla a área de trabalho inteira,
incluindo outras janelas. Não depende do Kanivete aberto nem do modo agente.

Um dedo arrasta o cursor como um touchpad; um toque clica e dois toques dão duplo clique.
O Windows recebe os cliques individuais e faz o duplo clique normalmente. Movimentos pendentes
saem da fila quando chega um clique, que já contém a posição final. No modo KANIVETE, mantém
o protocolo anterior da página. Desligar o mouse permite só assistir.

Zoom entre 1× e 4× com +/− ou pinça; dois dedos também deslocam a imagem ampliada sem clicar.
O modo PC usa JPEG de até 1280 pixels, ou 2560 durante zoom, até oito quadros/segundo.
A redução ocorre no GDI antes da cópia de pixels. Quadros iguais não são retransmitidos,
exceto a confirmação de vida a cada dois segundos. Cada conexão captura o monitor selecionado;
ao fechar ou trocar a tela, a desconexão encerra a captura anterior, sem fila de quadros.
Só captura enquanto a transmissão está aberta. Não instala programa no Android.

Monitores e mouse usam pixels físicos com consciência de DPI por thread, incluindo origens
negativas e escalas diferentes. A enumeração tem cache de dois segundos. O seletor é atualizado
ao abrir e durante a verificação periódica. O principal vem primeiro.

Rotas autenticadas existentes: `/tela?fonte=pc&monitor=...&largura=1280`, `/tela/estado`,
`/tela/monitores`, `/tela/mouse`. A chave de pareamento e a proteção de origem do mouse continuam
obrigatórias. Sem `fonte=pc`, as rotas antigas continuam atendendo ao KANIVETE.

Validação: `py -3.13 verificar.py --area movel`. Entrada nativa é simulada nos testes;
não move nem clica no computador em uso e nunca acessa a porta 9222. Captura e enumeração
podem ser conferidas separadamente, sem enviar entrada. A latência completa depende também
da rede e do aparelho; a medição da captura não representa o tempo de ida e volta do celular.
