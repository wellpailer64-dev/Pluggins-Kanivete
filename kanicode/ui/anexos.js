/* Arquivos do PC são referências locais; imagens mantêm a prévia e o envio próprios. */
(() => {
  const imagens = new Set(['image/png','image/jpeg','image/gif','image/webp','image/bmp','image/svg+xml']);
  window.kaniImagemAnexo = tipo => imagens.has(tipo);
  window.kaniAnexosLocais = ({arquivos = [], erros = []}) => {
    for (const arquivo of arquivos) {
      if (ANX.some(a => a.arquivo && a.caminho === arquivo.caminho)) continue;
      if (ANX.length >= 8) { bolha('sis', 'No máximo 8 anexos por mensagem.'); break; }
      ANX.push({arquivo:true, nome:arquivo.nome, caminho:arquivo.caminho});
    }
    erros.forEach(erro => bolha('erro', erro));
    anexosDesenhar(); texto.focus();
  };
  window.kaniTextoComAnexos = pedido => {
    const arquivos = ANX.filter(a => a.arquivo);
    if (!arquivos.length) return pedido;
    const caminhos = arquivos.map(a => '- ' + JSON.stringify(a.caminho)).join('\n');
    return (pedido ? pedido + '\n\n' : '') + 'Arquivos anexados (caminhos locais no PC; abra os arquivos conforme necessário):\n' + caminhos;
  };
})();
