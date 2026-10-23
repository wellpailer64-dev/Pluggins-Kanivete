/* Controles recolhidos e pastas observadas nos passos dos agentes. Sem sondagem do disco. */
(() => {
  // Projeto e consumo ficam junto do estado da conversa; o topo fica livre para as abas.
  $('status').prepend($('pastas-nav'));
  $('status').appendChild(document.querySelector('.rodape'));
  const saudacao = () => { $('saudacao').hidden = K.ocupada || !!conversa.children.length; };
  new MutationObserver(saudacao).observe(conversa, {childList: true});
  const menu = $('config-menu'), botao = $('ferramentas-bt');
  function configuracoes(on, foco = false) {
    menu.hidden = !on; botao.setAttribute('aria-expanded', String(on));
    if (on) {
      const r = botao.getBoundingClientRect();
      menu.style.right = Math.max(8, innerWidth - r.right) + 'px';
      menu.style.top = r.bottom + 4 + 'px';
      menu.style.maxHeight = Math.max(100, innerHeight - r.bottom - 14) + 'px';
      $('menu-quem').hidden = true;
      if (foco) menu.querySelector('button').focus();
    }
  }
  window.kaniConfiguracoesMenu = configuracoes;
  botao.addEventListener('click', () => configuracoes(menu.hidden));
  botao.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); configuracoes(true, true); }
  });
  menu.addEventListener('keydown', e => {
    if (e.target.matches('select')) return;
    const bts = [...menu.querySelectorAll('button')].filter(b => b.getClientRects().length);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); bts[(bts.indexOf(document.activeElement) + (e.key === 'ArrowDown' ? 1 : bts.length - 1)) % bts.length]?.focus();
    }
  });
  document.addEventListener('mousedown', e => {
    if (!e.target.closest('#config-menu, #ferramentas-bt')) configuracoes(false);
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !menu.hidden && !document.querySelector('dialog[open]')) {
      e.preventDefault(); e.stopImmediatePropagation(); configuracoes(false); botao.focus();
    }
  }, true);
  document.addEventListener('error', e => {
    if (e.target.matches?.('.foto-ct img')) e.target.remove();
  }, true);

  // O seletor de agente usa o mesmo popover, agora ancorado à esquerda da mensagem.
  const seletor = $('quem-bt'), modelos = $('menu-quem');
  new MutationObserver(() => seletor.setAttribute('aria-expanded', String(!modelos.hidden))).observe(modelos, {attributes: true, attributeFilter: ['hidden']});
  seletor.addEventListener('click', () => {
    configuracoes(false);
    modelos.querySelectorAll('[data-q]').forEach(el => { el.tabIndex = 0; el.setAttribute('role', 'button'); });
  });
  modelos.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.target.closest('[data-q]')?.click(); }
    if (e.key === 'Escape') { e.stopPropagation(); modelos.hidden = true; seletor.focus(); }
  });

  const operacoes = new Map();
  let ultimaLista = '';
  const normal = p => String(p || '').replace(/\\/g, '/').replace(/\/{2,}/g, '/').replace(/\/$/, '');
  const chave = p => normal(p).toLowerCase();
  const absoluto = p => /^[a-z]:\//i.test(p) || p.startsWith('/');
  function resolver(p) {
    p = normal(p);
    if (!p || /^(?:https?:|data:)/i.test(p)) return '';
    if (!absoluto(p)) p = normal(K.pasta) + '/' + p.replace(/^\.\//, '');
    const partes = [];
    for (const parte of p.split('/')) {
      if (parte === '..') { if (partes.length > 1) partes.pop(); }
      else if (parte !== '.') partes.push(parte);
    }
    return partes.join('/');
  }
  function caminhos(entrada) {
    const pastas = new Set();
    const por = (p, arquivo = false) => {
      if (typeof p !== 'string' || !p) return;
      p = resolver(p);
      if (arquivo) p = p.slice(0, p.lastIndexOf('/'));
      if (p && chave(p) !== chave(K.pasta)) pastas.add(p);
    };
    for (const k of ['cwd', 'workdir', 'pasta', 'directory']) por(entrada[k]);
    for (const k of ['file_path', 'notebook_path', 'caminho', 'path']) {
      const p = entrada[k];
      if (typeof p === 'string') por(p, k.endsWith('_path') || /\.[\w-]+$/.test(p));
    }
    for (const mudanca of entrada.changes || []) por(mudanca.path, true);
    const cmd = String(entrada.command || '');
    for (const m of cmd.matchAll(/(?:\b(?:cd|pushd|Set-Location|Push-Location)\s+(?:-LiteralPath\s+|-Path\s+)?)(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))/gi)) por(m[1] || m[2] || m[3]);
    for (const m of cmd.matchAll(/["']([a-z]:[\\/][^"'\r\n]+)["']/gi)) {
      if (!/\.(?:exe|dll|bat|cmd)$/i.test(m[1])) por(m[1], /\.[\w-]+$/.test(m[1]));
    }
    return [...pastas];
  }
  function desenharPastas() {
    const pastas = new Map();
    for (const grupo of operacoes.values()) for (const p of grupo) pastas.set(chave(p), p);
    const lista = [...pastas.values()].filter(p => !(K.pastasInternas || []).some(interna => chave(interna) === chave(p))), raiz = normal(K.pasta);
    const assinatura = [raiz, ...lista].join('\n');
    if (assinatura === ultimaLista) return;
    ultimaLista = assinatura;
    const nome = p => chave(p).startsWith(chave(raiz) + '/') ? p.slice(raiz.length + 1) : p.split('/').slice(-2).join('/');
    $('pastas-ativas').innerHTML = lista.slice(0, 5).map(p => `<span class="pasta-ativa" title="${esc(p)} · em uso"><span>${esc(nome(p))}</span></span>`).join('')
      + (lista.length > 5 ? `<span class="pasta-ativa mais" title="${esc(lista.slice(5).join('\n'))}">+${lista.length - 5}</span>` : '');
  }
  const antes = window.kcEv;
  window.kcEv = ev => {
    antes(ev);
    if (ev.t === 'ferr' && ev.id) operacoes.set(ev.id, caminhos(ev.entrada || {}));
    if (ev.t === 'ferr_fim') operacoes.delete(ev.id);
    if (ev.t === 'ajudante' && ev.operacao && ev.id) {
      if (ev.operacao === 'inicio') operacoes.set(ev.quem + ':' + ev.id, caminhos(ev.entrada || {}));
      else operacoes.delete(ev.quem + ':' + ev.id);
    }
    if (ev.t === 'ajudante' && ev.fase === 'fim') {
      for (const id of operacoes.keys()) if (id.startsWith(ev.quem + ':')) operacoes.delete(id);
    }
    if (['fim', 'saiu', 'ajudante_resposta'].includes(ev.t)) operacoes.clear();
    desenharPastas();
  };
  const carregarAntes = window.carregar;
  window.carregar = async () => {
    operacoes.clear();
    const r = await carregarAntes();
    desenharPastas();
    return r;
  };
})();
