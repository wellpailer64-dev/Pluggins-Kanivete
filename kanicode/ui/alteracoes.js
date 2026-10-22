// Barras recolhidas: texto do código nunca é interpretado como HTML.
(() => {
  const cards = new Map();
  function mostrar(ev) {
    const chave = ev.arquivo || ev.id || 'copia';
    let card = cards.get(chave);
    const acompanhar = perto();
    if (!card?.isConnected) {
      card = document.createElement('details'); card.className = 'codigo-alteracao';
      card.append(document.createElement('summary'), document.createElement('p'), document.createElement('pre'));
      conversa.appendChild(card); cards.set(chave, card);
    }
    card.querySelector('summary').textContent = 'Ver alterações · ' + chave;
    card.querySelector('p').textContent = ev.rotulo || 'Alterações somente na cópia isolada; a origem aguarda sua revisão.';
    card.querySelector('pre').textContent = ev.diff || 'Nenhuma diferença de texto registrada.';
    if (acompanhar) conversa.scrollTop = conversa.scrollHeight;
  }
  const anterior = window.kcEv;
  window.kcEv = ev => {
    if (ev.t === 'codex_alteracao' || ev.t === 'codigo_alteracao') { mostrar(ev); return; }
    if (ev.t === 'eu' || ev.t === 'ajudante_resposta' || ev.t === 'historico_turno' || (ev.t === 'ajudante' && ev.fase === 'inicio')) cards.clear();
    return anterior(ev);
  };
})();
