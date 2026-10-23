// Barras recolhidas: texto do código nunca é interpretado como HTML.
(() => {
  const cards = new Map();
  const lateral = document.querySelector('#atv .det');
  lateral.querySelector('.cab b').innerHTML = '<button type="button" id="codigo-atividades" aria-pressed="true">Ferramentas</button><button type="button" id="codigo-aba" aria-pressed="false">Código</button>';
  const painel = document.createElement('div'); painel.className = 'codigo-painel'; painel.hidden = true;
  painel.innerHTML = '<label>Arquivo <select aria-label="Arquivo alterado"></select></label><p class="codigo-resumo"></p><p class="codigo-nota"></p><pre><code></code></pre>';
  lateral.appendChild(painel);
  const seletor = painel.querySelector('select');
  function arquivos() {
    const mapa = new Map();
    conversa.querySelectorAll('.codigo-alteracao').forEach(c => { if (c.codigoEvento) mapa.set(c.codigoEvento.arquivo || c.codigoEvento.id || 'copia', c.codigoEvento); });
    return mapa;
  }
  function desenharCodigo(preferido) {
    const mapa = arquivos(), selecionado = preferido || seletor.value;
    seletor.replaceChildren(...[...mapa.keys()].map(nome => { const o = document.createElement('option'); o.value = nome; o.textContent = nome; return o; }));
    if (mapa.has(selecionado)) seletor.value = selecionado;
    const ev = mapa.get(seletor.value);
    painel.querySelector('.codigo-resumo').textContent = ev ? (ev.adicionadas != null ? `+${ev.adicionadas} / −${ev.removidas ?? '?'} linhas` : 'Contagem indisponível') : 'Nenhum arquivo alterado nesta conversa.';
    painel.querySelector('.codigo-nota').textContent = ev ? (ev.rotulo || '') + (ev.conteudo == null ? ' Exibindo o diff recebido.' : ' Conteúdo após a última edição informada.') : 'Os arquivos aparecem quando o agente informa uma edição.';
    const idioma = (seletor.value.split('.').pop() || '').toLowerCase();
    painel.querySelector('code').innerHTML = KCResposta.colorir(ev ? ev.conteudo ?? ev.diff ?? '' : '', idioma);
  }
  function alternar(codigo) {
    painel.hidden = !codigo; $('ferramentas-conteudo').hidden = codigo;
    $('codigo-aba').setAttribute('aria-pressed', String(codigo));
    $('codigo-atividades').setAttribute('aria-pressed', String(!codigo));
    if (codigo) desenharCodigo();
  }
  $('codigo-aba').onclick = () => alternar(true);
  $('codigo-atividades').onclick = () => alternar(false);
  seletor.onchange = () => desenharCodigo();
  new MutationObserver(() => { if (!painel.hidden) desenharCodigo(); }).observe(conversa, {childList: true});
  function mostrar(ev) {
    const chave = ev.arquivo || ev.id || 'copia';
    let card = cards.get(chave);
    const acompanhar = perto();
    if (!card?.isConnected) {
      card = document.createElement('details'); card.className = 'codigo-alteracao';
      card.append(document.createElement('summary'), document.createElement('p'), document.createElement('pre'));
      conversa.appendChild(card); cards.set(chave, card);
    }
    card.codigoEvento = ev;
    desenharCodigo(chave);
    card.querySelector('summary').textContent = 'Ver alterações · ' + chave;
    card.querySelector('p').textContent = ev.rotulo || 'Alterações somente na cópia isolada; a origem aguarda sua revisão.';
    card.querySelector('pre').textContent = ev.diff || 'Nenhuma diferença de texto registrada.';
    if (acompanhar) conversa.scrollTop = conversa.scrollHeight;
  }
  // Edit/Write do Claude: só registrar depois da confirmação de sucesso.
  const edicoes = new Map(), passoAntes = window.passo, fimAntes = window.passoFim;
  window.passo = (id, nome, entrada) => {
    const d = passoAntes(id, nome, entrada);
    if (['Edit', 'Write', 'MultiEdit'].includes(nome)) edicoes.set(id, {nome, entrada});
    return d;
  };
  window.passoFim = (id, ok, saida) => {
    fimAntes(id, ok, saida);
    const edicao = edicoes.get(id); edicoes.delete(id);
    if (!ok || !edicao) return;
    const {nome, entrada: e} = edicao, partes = e.edits || [e];
    const novo = nome === 'Write' ? e.content || '' : partes.map(p => p.new_string || '').join('\n');
    const velho = partes.map(p => p.old_string || '').join('\n');
    const n = t => t ? t.replace(/\n$/, '').split('\n').length : 0;
    mostrar({arquivo: e.file_path || e.path || 'arquivo', conteudo: novo,
      adicionadas: n(novo), removidas: nome === 'Write' ? null : n(velho),
      rotulo: nome === 'Write' ? 'Conteúdo enviado na operação Write; base anterior indisponível.' : 'Trecho da última edição confirmada; contagem do trecho substituído.'});
  };
  const anterior = window.kcEv;
  window.kcEv = ev => {
    if (ev.t === 'codex_alteracao' || ev.t === 'codigo_alteracao') { mostrar(ev); return; }
    if (ev.t === 'eu' || ev.t === 'ajudante_resposta' || ev.t === 'historico_turno' || (ev.t === 'ajudante' && ev.fase === 'inicio')) cards.clear();
    return anterior(ev);
  };
})();
