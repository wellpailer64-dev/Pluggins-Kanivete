/* Aba Casa no painel da direita: os aparelhos da casa (casa.py, Tuya pela rede local), cada um com ícone e nome.
   Conectado = aceso; fora da rede = apagado. Clique liga/desliga; o alimentador dos gatos pede confirmação. */
(() => {
  const el = id => document.getElementById(id), api = () => window.pywebview.api;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const IC = {
    luz: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.6 1 2.5h6c0-.9.2-1.7 1-2.5A6 6 0 0 0 12 3z"/>',
    tomada: '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M9.5 9v3M14.5 9v3M10 16h4"/>',
    gato: '<path d="M4 15h16l-1.5 5h-13zM7 15c0-3 2-5 5-5s5 2 5 5"/><path d="M8 6l1.5 3M16 6l-1.5 3"/>',
    cafe: '<path d="M5 9h11v5a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5zM16 10h2a2 2 0 0 1 0 4h-2M8 3v3M11 3v3"/>',
    chapa: '<rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 13h10M6 17v2M18 17v2"/>',
  };
  const icone = it => {
    const n = it.nome.toLowerCase();
    if (it.cat === 'cwwsq') return IC.gato;
    if (it.cat === 'dj' || /luz|lumin|l[âa]mp|abajur/.test(n)) return IC.luz;
    if (/caf[ée]/.test(n)) return IC.cafe;
    if (/chapa|grill|forno/.test(n)) return IC.chapa;
    return IC.tomada;
  };

  const trilho = document.createElement('button'); trilho.id = 'casa-trilho'; trilho.className = 'trilho';
  trilho.title = 'Casa: aparelhos da casa'; trilho.setAttribute('aria-label', 'Casa');
  trilho.setAttribute('aria-expanded', 'false'); trilho.setAttribute('aria-controls', 'casa-painel');
  trilho.innerHTML = '<span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11 12 4l9 7M5 10v10h14V10M10 20v-6h4v6"/></svg></span><span class="vert">CASA</span>';
  (el('consumo-trilho') || el('todo-trilho') || el('atv-trilho')).after(trilho);
  const painel = document.createElement('section'); painel.id = 'casa-painel'; painel.className = 'det';
  painel.setAttribute('aria-label', 'Casa');
  painel.innerHTML = `<div class="cab"><b>Casa</b><span class="esp"></span><button class="bt" id="casa-atualizar" title="Atualizar">↻</button><button class="bt" id="casa-fechar" aria-label="Recolher casa">»</button></div>
    <div class="ca-rolo"><div id="casa-corpo"><p class="ca-nota">Procurando os aparelhos…</p></div></div>`;
  el('atv').append(painel); painel.inert = true;
  let itens = [], timer = null, ocupado = false;

  function desenhar() {
    const c = el('casa-corpo');
    if (!itens.length) { c.innerHTML = '<p class="ca-nota">Nenhum aparelho.</p>'; return; }
    const on = itens.filter(i => i.online).length;
    c.innerHTML = `<p class="ca-resumo">${on} de ${itens.length} conectados</p><div class="ca-grade">` + itens.map((it, k) => {
      const est = !it.online ? 'fora da rede' : it.cat === 'cwwsq' ? (it.info || 'pronto') : it.ligado ? 'ligado' : 'desligado';
      const cls = ['ca-ap', it.online ? 'on' : 'off', it.ligado ? 'lig' : '', it.cat === 'cwwsq' ? 'gato' : ''].join(' ');
      return `<button class="${cls}" data-k="${k}" ${it.online ? '' : 'disabled'} title="${esc(it.tipo + (it.comodo ? ' · ' + it.comodo : ''))}">
        <span class="ca-ic"><svg viewBox="0 0 24 24" aria-hidden="true">${icone(it)}</svg></span>
        <b>${esc(it.nome)}</b><small>${esc(est)}</small></button>`;
    }).join('') + '</div><p class="ca-nota">Toque para ligar/desligar. O alimentador pede confirmação antes de servir.</p>';
  }

  async function atualizar() {
    if (ocupado) return;
    try {
      const r = await api().casa_estado();
      if (r && r.ok) { itens = r.itens; desenhar(); }
      else el('casa-corpo').innerHTML = `<p class="ca-nota erro">${esc((r && r.erro) || 'Não consegui ler a casa.')}</p>`;
    } catch (e) { el('casa-corpo').innerHTML = `<p class="ca-nota erro">${esc(e.message || e)}</p>`; }
  }

  el('casa-corpo').addEventListener('click', async e => {
    const b = e.target.closest('.ca-ap'); if (!b || b.disabled || ocupado) return;
    const it = itens[+b.dataset.k];
    if (it.cat === 'cwwsq') return confirmar(b);
    ocupado = true; b.classList.add('esp');
    const r = await api().casa_alternar(it.nome);
    ocupado = false; b.classList.remove('esp');
    if (r && r.ok) { it.ligado = r.ligado; desenhar(); } else atualizar();
  });

  // alimentador: confirmação dentro da aba (prompt/alert não aparecem no WebView do celular)
  function confirmar(b) {
    el('casa-conf')?.remove();
    let n = 1;
    const d = document.createElement('div'); d.id = 'casa-conf'; d.className = 'ca-conf';
    d.innerHTML = `<p>Servir ração para os gatos?</p><div class="ca-qtd"><button data-a="-">−</button><b>1</b><button data-a="+">+</button><small>porção</small></div>
      <div class="ca-bts"><button data-a="nao">Cancelar</button><button data-a="sim" class="sim">Servir</button></div><p class="ca-msg"></p>`;
    el('casa-corpo').prepend(d);
    d.onclick = async e => {
      const a = e.target.closest('button')?.dataset.a; if (!a) return;
      if (a === '-' || a === '+') { n = Math.max(1, Math.min(40, n + (a === '+' ? 1 : -1))); d.querySelector('b').textContent = n; d.querySelector('small').textContent = n > 1 ? 'porções' : 'porção'; return; }
      if (a === 'nao') return d.remove();
      ocupado = true; d.querySelectorAll('button').forEach(x => x.disabled = true); b.classList.add('esp');
      const r = await api().casa_alimentar(n);
      ocupado = false; b.classList.remove('esp');
      d.querySelector('.ca-msg').textContent = r.ok ? 'Pedido enviado. 🐱' : (r.texto || 'Não consegui servir.');
      setTimeout(() => { d.remove(); atualizar(); }, 2500);
    };
  }

  trilho.addEventListener('click', () => window.kaniPainelDireito(trilho.getAttribute('aria-expanded') !== 'true', 'casa'));
  el('casa-fechar').addEventListener('click', () => window.kaniPainelDireito(false, 'casa'));
  el('casa-atualizar').addEventListener('click', atualizar);
  painel.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); window.kaniPainelDireito(false, 'casa'); trilho.focus(); } });
  new MutationObserver(() => {
    const aberto = trilho.getAttribute('aria-expanded') === 'true'; painel.inert = !aberto; clearInterval(timer);
    if (aberto) { atualizar(); timer = setInterval(() => { if (!document.hidden) atualizar(); }, 15000); }
  }).observe(trilho, { attributes: true, attributeFilter: ['aria-expanded'] });
})();
