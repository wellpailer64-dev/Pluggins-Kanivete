/* Mensagens pendentes ficam visíveis sem tocar no fluxo da resposta em andamento. */
(() => {
  const nomes = {pendente:'Na fila · duplo clique para enviar agora', urgente:'Urgente · aguardando interrupção',
    enviando:'Entregando ao agente…', falha:'Não entregue · veja o aviso'};
  function desenhar(ev) {
    let b = conversa.querySelector('[data-mensagem-id="' + CSS.escape(ev.id) + '"]');
    if (!b) {
      b = bolha('eu', ev.texto || ''); b.dataset.mensagemId = ev.id;
      const m = minis(ev.minis); if (m) b.prepend(m);
    }
    b.dataset.mensagemEstado = ev.estado;
    b.classList.toggle('mensagem-pendente', ['pendente','urgente'].includes(ev.estado));
    b.classList.toggle('mensagem-urgente', ev.estado === 'urgente');
    let nota = b.querySelector('.mensagem-fila-nota');
    if (ev.estado === 'enviada') { nota?.remove(); b.title = ''; return; }
    if (!nota) { nota = document.createElement('small'); nota.className = 'mensagem-fila-nota'; b.appendChild(nota); }
    nota.textContent = ev.erro || nomes[ev.estado] || '';
    b.title = nomes[ev.estado] || '';
    if (ev.estado === 'enviando') {
      K.bolha = null;
      if (ev.quem && K.quem !== ev.quem) quemDefinir(ev.quem, false);
      ocupada(true); atividade('Enviando mensagem da fila');
    }
    if (ev.estado === 'falha') bolha('erro', ev.erro || 'A mensagem não foi entregue. A fila ficou pausada.');
  }
  window.mensagemEnfileirar = async (t, imgs) => {
    const id = crypto.randomUUID();
    const ev = {id, texto:t, minis:imgs.map(i => i.mini).filter(Boolean), quem:K.quem, estado:'pendente'};
    desenhar(ev); fim(); som('enviar');
    texto.value = ''; ajustar();
    try {
      const r = await api().mensagem_enviar(id, t, imgs, K.quem);
      if (!r) throw new Error('A fila não confirmou o recebimento.');
      // As mudanças chegam por evento; a resposta da API pode ser anterior ao último evento recebido.
    } catch (erro) {
      desenhar({...ev, estado:'falha', erro:String(erro.message || erro)});
    }
  };
  conversa.addEventListener('dblclick', async e => {
    const b = e.target.closest('.mensagem-pendente[data-mensagem-id]');
    if (!b) return;
    e.preventDefault();
    try { await api().mensagem_urgente(b.dataset.mensagemId); }
    catch (erro) { bolha('erro', String(erro.message || erro)); }
  });
  const eventoAntes = window.kcEv;
  window.kcEv = ev => {
    if (ev?.t === 'fila_mensagem') { desenhar(ev); return; }
    if (ev?.t === 'fila_livre') { ocupada(false); return; }
    if (ev?.t === 'eco_eu' && ev.de === 'fila') return;   // a bolha pendente já representa este envio
    return eventoAntes(ev);
  };
  const carregarAntes = window.carregar;
  window.carregar = async () => {
    const r = await carregarAntes();
    const pendentes = await api().mensagens_fila();
    if (Array.isArray(pendentes)) pendentes.forEach(desenhar);
    return r;
  };
})();
