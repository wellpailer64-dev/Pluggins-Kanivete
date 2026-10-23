/* KaniCode — navegador dentro da janela (🌐 / Ctrl+B). O Chrome do KaniBrowser (logins guardados) entra como janela
   filha por cima de #nav-area (navegador_painel.py); aqui ficam as abas, o endereço e os botões, na cor do KaniCode.
   localhost:5173, 127.0.0.1:8000 ou ":3000" abrem direto (sites e landing pages em teste). Quando o Claude/Kani usa o
   KaniBrowser, a vista vai para a aba dela e aparece a faixa "Kani navegando…" (se o Pailer não mexeu há 2 s), com um
   brilho verde-limão em volta da página (.trab: a página recua 3 px; só opacidade animada, leve). */
(() => {
  const $ = id => document.getElementById(id), api = () => window.pywebview && window.pywebview.api;
  const esc = s => String(s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const NAV = { on: false, w: 760, cresceu: 0, est: null, digitando: false, timer: null };
  try { NAV.w = Math.max(360, Math.min(2400, Number(localStorage.getItem('kc-nav-w')) || 760)); } catch (_) {}
  if (document.documentElement.classList.contains('movel')) return;   // no celular não há janela para encaixar

  const svg = d => `<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
  const bt = document.createElement('button');
  bt.id = 'nav-bt'; bt.title = 'Navegador (Ctrl+B)'; bt.setAttribute('aria-label', 'Navegador'); bt.setAttribute('aria-pressed', 'false');
  bt.innerHTML = svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>');
  const bolas = document.querySelector('.janela-bolas');
  bolas.parentNode.insertBefore(bt, bolas);

  document.body.insertAdjacentHTML('beforeend', `<section id="nav" aria-label="Navegador">
    <div id="nav-div" role="separator" aria-orientation="vertical" title="Arraste para dividir · duplo clique: meio a meio"></div>
    <div class="nav-abas pywebview-drag-region" id="nav-abas"></div>
    <div class="nav-barra">
      <button id="nav-voltar" title="Voltar (Alt+←)">${svg('<path d="M15 6l-6 6 6 6"/>')}</button>
      <button id="nav-avancar" title="Avançar (Alt+→)">${svg('<path d="M9 6l6 6-6 6"/>')}</button>
      <button id="nav-rec" title="Recarregar (F5)">${svg('<path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/>')}</button>
      <div class="nav-end-caixa"><input id="nav-end" spellcheck="false" autocomplete="off" placeholder="Pesquise ou digite um endereço (localhost:5173 também)">
        <button id="nav-estrela" title="Favoritar esta página (de novo: tira)">${svg('<path d="M12 3.5l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"/>')}</button></div>
      <div class="nav-ap" id="nav-ap" role="radiogroup" aria-label="Aparelho">
        <button data-m="auto" title="Auto: a página segue a largura do painel">${svg('<path d="M4 12h16M4 12l4-4M4 12l4 4M20 12l-4-4M20 12l-4 4"/>')}</button>
        <button data-m="computador" title="Computador: versão desktop (encolhe para caber)">${svg('<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M9 20h6M12 16v4"/>')}</button>
        <button data-m="tablet" title="Tablet (820 px, toque)">${svg('<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M11 18h2"/>')}</button>
        <button data-m="celular" title="Celular (390 px, toque, navegador de celular)">${svg('<rect x="7.5" y="3" width="9" height="18" rx="2"/><path d="M11 18h2"/>')}</button>
        <span class="nav-faixa" id="nav-faixa" title="Faixa em que um site responsivo põe esta largura"></span>
      </div>
      <button class="lima" id="nav-anexar" title="Mandar esta página para a conversa (print + endereço)">${svg('<path d="M21 11.5l-8.6 8.6a5 5 0 0 1-7-7l8.6-8.6a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4L15.5 7.6"/>')}</button>
      <i class="nav-carga" id="nav-carga" aria-hidden="true"></i>
      <button id="nav-fora" title="Abrir no Chrome normal">${svg('<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>')}</button>
    </div>
    <div class="nav-fav" id="nav-fav"></div>
    <div class="nav-kani" id="nav-kani"><i></i><span id="nav-kani-txt">Kani navegando…</span></div>
    <div id="nav-area"><div class="nav-msg" id="nav-msg">Abrindo o navegador…</div></div>
  </section>`);
  const nav = $('nav'), area = $('nav-area'), end = $('nav-end');

  function largura(w) {
    NAV.w = Math.round(Math.max(360, Math.min(window.innerWidth - 380, w)));
    document.documentElement.style.setProperty('--navw', NAV.w + 'px');
    nav.classList.toggle('estreito', NAV.w < 720); nav.classList.toggle('mini', NAV.w < 520); apertar();
  }
  function informarArea() {
    if (!NAV.on || !api()) return;
    const r = area.getBoundingClientRect(), k = window.devicePixelRatio || 1;
    const m = area.classList.contains('trab') ? 3 : 0;   // Kani trabalhando: a página recua 3 px e o brilho aparece em volta
    api().nav_area((r.left + m) * k, (r.top + m) * k, (r.width - 2 * m) * k, (r.height - 2 * m) * k, document.documentElement.clientWidth * k);
  }
  new ResizeObserver(informarArea).observe(area);
  window.addEventListener('resize', () => { if (NAV.on) { largura(NAV.w); informarArea(); apertar(); } });

  async function abrir() {
    if (NAV.on) return;
    NAV.on = true; bt.setAttribute('aria-pressed', 'true');
    // janela estreita: cresce para a direita; já larga (≥ 1000): divide o que tem
    const cresce = window.innerWidth < 1000 ? NAV.w : 0;
    NAV.cresceu = cresce; try { sessionStorage.setItem('kc-nav-cresceu', String(cresce)); } catch (_) {}
    if (cresce) await api().crescer(0, cresce);
    largura(cresce ? NAV.w : Math.max(NAV.w, window.innerWidth / 2));
    document.documentElement.classList.add('com-nav');
    $('nav-abas').appendChild(bolas);   // botões da janela no canto de cima, como num navegador
    $('nav-msg').hidden = false; $('nav-msg').textContent = 'Abrindo o navegador…';
    informarArea();
    await ligar();
  }
  async function ligar() {
    if (!NAV.on) return;
    const e = await api().nav_abrir(0);
    clearInterval(NAV.timer);
    if (e && e.erro) {   // ex.: o KANIVETE ainda segura o navegador: tenta de novo sozinho
      $('nav-msg').innerHTML = 'Não abriu: ' + esc(e.erro) + '<br><small>Tentando de novo…</small>';
      NAV.timer = setTimeout(ligar, 3000);
      return;
    }
    $('nav-msg').hidden = true;
    favCarregar();
    desenhar(e); informarArea();
    NAV.timer = setInterval(atualizar, 1000);
  }
  async function fechar() {
    if (!NAV.on) return;
    NAV.on = false; bt.setAttribute('aria-pressed', 'false'); clearInterval(NAV.timer); clearTimeout(NAV.timer);
    try { localStorage.setItem('kc-nav-w', String(NAV.w)); } catch (_) {}
    document.querySelector('.topo').appendChild(bolas);
    document.documentElement.classList.remove('com-nav');
    await api().nav_fechar(NAV.cresceu ? NAV.w : 0);
    NAV.cresceu = 0;
  }
  // a página recarregou (atualização a quente) com o painel aberto no Python: volta a mostrar a barra, sem crescer a janela
  async function restaurar() {
    let e; try { e = await api().nav_estado(); } catch (_) { return; }
    if (!e || !e.aberto || NAV.on) return;
    NAV.on = true; NAV.cresceu = Number(sessionStorage.getItem('kc-nav-cresceu')) || 0;
    bt.setAttribute('aria-pressed', 'true');
    largura(NAV.w);
    document.documentElement.classList.add('com-nav');
    $('nav-abas').appendChild(bolas);
    $('nav-msg').hidden = true;
    favCarregar(); desenhar(e); informarArea();
    clearInterval(NAV.timer); NAV.timer = setInterval(atualizar, 1000);
  }
  if (window.pywebview && window.pywebview.api) setTimeout(restaurar, 300);
  else window.addEventListener('pywebviewready', () => setTimeout(restaurar, 300));
  window.kcNavegador = { abrir, fechar, alternar: () => (NAV.on ? fechar() : abrir()), estado: () => NAV.est };
  bt.addEventListener('click', () => window.kcNavegador.alternar());

  const local = u => /^https?:\/\/(localhost|127\.|0\.0\.0\.0|\[::1\]|192\.168\.|10\.)/i.test(u || '');
  function desenhar(e) {
    if (!e || e.erro) return;
    NAV.est = e;
    const abas = $('nav-abas');
    // as abas só são refeitas quando mudam (antes: 1×/s, e o ícone recarregava/falhava a cada segundo)
    // a aba da Kani só aparece com algo nela (vazia, "about:blank", era só ruído na barra)
    const vis = (e.abas || []).filter(a => !(a.kani && a.id !== e.aba && !e.trabalhando && (!a.url || a.url === 'about:blank')));
    // ordem estável (o Chrome devolve a última usada primeiro: as abas pulavam de lugar); nova = no fim
    NAV.ordem = NAV.ordem.filter(id => vis.some(a => a.id === id));
    for (const a of vis) if (!NAV.ordem.includes(a.id)) NAV.ordem.push(a.id);
    try { sessionStorage.setItem('kc-nav-ordem', JSON.stringify(NAV.ordem)); } catch (_) {}
    vis.sort((x, y) => NAV.ordem.indexOf(x.id) - NAV.ordem.indexOf(y.id));
    const assin = JSON.stringify([e.aba, vis.map(a => [a.id, a.titulo, a.url, a.kani, a.icone])]);
    if (assin !== NAV.assin) { NAV.assin = assin; abasDesenhar({ ...e, abas: vis }, abas); }
    restoDesenhar(e);
  }
  try { NAV.ordem = JSON.parse(sessionStorage.getItem('kc-nav-ordem')) || []; } catch (_) { NAV.ordem = []; }
  // muitas abas: as de fundo ficam só com o ícone (o título vai no balão), a ativa mantém o nome
  function apertar() {
    const abas = $('nav-abas'), n = abas.querySelectorAll('.nav-aba').length;
    abas.classList.toggle('apertado', n * 96 > abas.clientWidth - 150);
  }
  const ICONES = {};   // host → 'ok' | 'erro': o ícone que falhou vira a inicial, sem tentar de novo
  function abasDesenhar(e, abas) {
    abas.querySelectorAll('.nav-aba, .nav-mais').forEach(n => n.remove());
    const ref = abas.querySelector('.janela-bolas');
    for (const a of e.abas || []) {
      const d = document.createElement('div');
      d.className = 'nav-aba' + (a.id === e.aba ? ' ativa' : '') + (a.kani ? ' kani' : '');
      d.title = (a.titulo || '') + '\n' + (a.url || '');
      let h = ''; try { h = new URL(a.url).hostname; } catch (_) {}
      const letra = `<i class="nav-ic">${esc(((a.titulo || h || '•').trim()[0] || '•').toUpperCase())}</i>`;
      // ícone: o da própria página (estado → a.icone); falhou → o do serviço do Google; falhou → a inicial
      const fontes = [a.icone, h && `https://www.google.com/s2/favicons?sz=32&domain=${encodeURIComponent(h)}`].filter(f => f && ICONES[f] !== 'erro');
      d.innerHTML = `${fontes.length ? '<img alt="">' : letra}<span>${esc(a.titulo || a.url || 'Nova aba')}</span><button class="x" title="Fechar aba">×</button>`;
      const img = d.querySelector('img');
      if (img) {
        let i = 0;
        img.onerror = () => { ICONES[fontes[i]] = 'erro'; i++; if (fontes[i]) img.src = fontes[i]; else img.outerHTML = letra; };
        img.src = fontes[0];
      }
      d.addEventListener('mousedown', ev => { if (ev.button === 1) { ev.preventDefault(); cmd('fechar_aba', a.id); } });
      d.addEventListener('click', ev => { if (ev.target.closest('.x')) cmd('fechar_aba', a.id); else if (a.id !== e.aba) cmd('mostrar', a.id); });
      abas.insertBefore(d, ref);
    }
    const mais = document.createElement('button');
    mais.className = 'nav-mais'; mais.title = 'Nova aba (Ctrl+T)'; mais.textContent = '+';
    mais.onclick = () => cmd('nova');
    abas.insertBefore(mais, ref);
    apertar();
  }
  function restoDesenhar(e) {
    // endereço legível (Wikipédia, não Wikip%C3%A9dia); no meio da navegação o url vem vazio: mantém o anterior
    if (!NAV.digitando && document.activeElement !== end && (e.url || e.aba !== NAV.abaEnd)) {
      let u = e.url && e.url !== 'about:blank' ? e.url : '';
      try { u = decodeURI(u); } catch (_) {}
      end.value = u; NAV.abaEnd = e.aba;
    }
    end.classList.toggle('local', local(e.url));
    $('nav-carga').classList.toggle('on', !!e.carregando);   // barrinha de carregando sob o endereço
    document.querySelectorAll('#nav-ap button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.m === (e.modo || 'auto'))));
    const NOME = { celular: 'Celular', tablet: 'Tablet', computador: 'Desktop' };
    if (e.faixa) $('nav-faixa').textContent = NOME[e.faixa] + ' · ' + e.tam[0] + 'px';
    $('nav-estrela').classList.toggle('on', FAV.lista.some(f => f.url === e.url));
    const faz = (e.fazendo || [])[0] || (e.trabalhando && e.log && e.log[0] && e.log[0].o);
    $('nav-kani').classList.toggle('on', !!faz);
    if (faz) $('nav-kani-txt').textContent = 'Kani: ' + faz;
    const trab = !!e.trabalhando;
    if (trab !== area.classList.contains('trab')) area.classList.toggle('trab', trab);
    requestAnimationFrame(informarArea);   // a faixa da Kani muda a altura da área
  }
  async function atualizar() {
    if (!NAV.on || document.hidden) return;
    try {
      const e = await api().nav_estado();
      if (e && !e.aberto) { $('nav-msg').hidden = false; $('nav-msg').textContent = 'Reabrindo o navegador…'; clearInterval(NAV.timer); ligar(); return; }
      desenhar(e);
    } catch (_) {}
  }
  async function cmd(o, a) {
    const e = await api().nav_cmd(o, a === undefined ? null : a);
    if (e && e.erro) console.warn('navegador:', e.erro); else if (e && e.abas) desenhar(e);
    return e;
  }

  end.addEventListener('focus', () => { NAV.digitando = true; end.select(); });
  end.addEventListener('blur', () => { NAV.digitando = false; });
  end.addEventListener('keydown', async ev => {
    ev.stopPropagation();
    if (ev.key === 'Enter') { ev.preventDefault(); const v = end.value; end.blur(); await cmd('ir', v); cmd('foco'); }
    if (ev.key === 'Escape') { ev.preventDefault(); end.value = NAV.est ? NAV.est.url : ''; end.blur(); cmd('foco'); }
  });
  document.querySelectorAll('#nav-ap button').forEach(b => b.onclick = () => cmd('aparelho', b.dataset.m));
  $('nav-voltar').onclick = () => cmd('acao', 'voltar');
  $('nav-avancar').onclick = () => cmd('acao', 'avancar');
  $('nav-rec').onclick = () => cmd('acao', 'recarregar');
  $('nav-fora').onclick = () => NAV.est && NAV.est.url && api().resposta_abrir_link(NAV.est.url);
  $('nav-anexar').onclick = async () => {
    const r = await cmd('print');
    if (!r || !r.caminho) return;
    if (window.kaniAnexosLocais) window.kaniAnexosLocais({ arquivos: [{ nome: 'página.png', caminho: r.caminho }] });
    const tx = $('texto'), u = NAV.est && NAV.est.url;
    if (tx && u && !tx.value.includes(u)) { tx.value = (tx.value ? tx.value.trimEnd() + '\n' : '') + 'Página: ' + u + '\n'; tx.dispatchEvent(new Event('input')); }
    tx && tx.focus();
  };

  // ── barra de favoritos (a mesma do KaniBrowser): clique abre, botão do meio = aba nova, arrastar organiza,
  //    botão direito = Excluir (confirma no próprio favorito; menus HTML não aparecem por cima da página do Chrome) ──
  const FAV = { lista: [], arrastando: null, excluir: null };
  async function favCarregar(op, a) {
    const r = await api().nav_favoritos(op || 'listar', a || null);
    if (Array.isArray(r)) { FAV.lista = r; favDesenhar(); }
    if (NAV.est) $('nav-estrela').classList.toggle('on', FAV.lista.some(f => f.url === NAV.est.url));
    if (!op && FAV.lista.some(f => !f.ic)) setTimeout(() => NAV.on && favCarregar(), 4000);   // ícones chegando
  }
  function favDesenhar() {
    const bar = $('nav-fav');
    bar.innerHTML = '';
    if (!FAV.lista.length) { bar.innerHTML = '<span class="nav-fav-vazio">Clique na ☆ da barra para guardar uma página aqui.</span>'; return; }
    for (const f of FAV.lista) {
      const b = document.createElement('button');
      b.className = 'nav-fv' + (FAV.excluir === f.url ? ' excluir' : '');
      b.draggable = true; b.title = f.nome + '\n' + f.url + '\n(botão direito: excluir · arraste para organizar)';
      b.innerHTML = FAV.excluir === f.url ? '<span>✕ Excluir?</span>'
        : (f.ic ? `<img src="${f.ic}" alt="">` : `<i>${esc((f.nome || '?')[0].toUpperCase())}</i>`) + `<span>${esc(f.nome)}</span>`;
      b.addEventListener('click', () => {
        if (FAV.excluir === f.url) { FAV.excluir = null; favCarregar('remover', { url: f.url }); return; }
        if (FAV.excluir) { FAV.excluir = null; favDesenhar(); }
        cmd('ir', f.url).then(() => cmd('foco'));
      });
      b.addEventListener('auxclick', ev => { if (ev.button === 1) { ev.preventDefault(); cmd('nova', f.url); } });
      b.addEventListener('contextmenu', ev => {
        ev.preventDefault(); FAV.excluir = f.url; favDesenhar();
        clearTimeout(FAV.t); FAV.t = setTimeout(() => { if (FAV.excluir === f.url) { FAV.excluir = null; favDesenhar(); } }, 3500);
      });
      b.addEventListener('dragstart', ev => { FAV.arrastando = f.url; b.classList.add('arrastando'); ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData('text/plain', f.url); });
      b.addEventListener('dragend', () => { FAV.arrastando = null; b.classList.remove('arrastando'); bar.querySelectorAll('.alvo-e,.alvo-d').forEach(n => n.classList.remove('alvo-e', 'alvo-d')); });
      b.addEventListener('dragover', ev => {
        if (!FAV.arrastando || FAV.arrastando === f.url) return;
        ev.preventDefault();
        const r = b.getBoundingClientRect(), dir = ev.clientX > r.left + r.width / 2;
        b.classList.toggle('alvo-d', dir); b.classList.toggle('alvo-e', !dir);
      });
      b.addEventListener('dragleave', () => b.classList.remove('alvo-e', 'alvo-d'));
      b.addEventListener('drop', ev => {
        ev.preventDefault();
        const de = FAV.arrastando; if (!de || de === f.url) return;
        const dir = b.classList.contains('alvo-d');
        const urls = FAV.lista.map(x => x.url).filter(u => u !== de);
        urls.splice(urls.indexOf(f.url) + (dir ? 1 : 0), 0, de);
        FAV.lista.sort((x, y) => urls.indexOf(x.url) - urls.indexOf(y.url)); favDesenhar();
        favCarregar('ordenar', { urls });
      });
      bar.appendChild(b);
    }
  }
  $('nav-fav').addEventListener('wheel', ev => { if (ev.deltaY) { ev.preventDefault(); $('nav-fav').scrollLeft += ev.deltaY; } }, { passive: false });
  $('nav-estrela').onclick = () => {
    const e = NAV.est; if (!e || !e.url || e.url === 'about:blank') return;
    let nome = (e.titulo || '').split(/ [-–|•·] /)[0].trim() || e.url;
    favCarregar('salvar', { url: e.url, nome: nome.slice(0, 40) });
  };

  // divisória: arrastar muda a divisão (a janela não muda de tamanho); duplo clique = meio a meio
  const div = $('nav-div');
  div.addEventListener('pointerdown', ev => {
    ev.preventDefault(); div.setPointerCapture(ev.pointerId); div.classList.add('arrastando');
    const mover = e2 => largura(window.innerWidth - e2.clientX);
    const soltar = () => { div.classList.remove('arrastando'); div.removeEventListener('pointermove', mover); informarArea();
      try { localStorage.setItem('kc-nav-w', String(NAV.w)); } catch (_) {} };
    div.addEventListener('pointermove', mover);
    div.addEventListener('pointerup', soltar, { once: true });
  });
  div.addEventListener('dblclick', () => { largura(window.innerWidth / 2); informarArea(); });

  // atalhos (com o foco no KaniCode; com o foco na página quem responde é o Chrome)
  document.addEventListener('keydown', ev => {
    const k = ev.key.toLowerCase();
    if (ev.ctrlKey && !ev.shiftKey && !ev.altKey && k === 'b') { ev.preventDefault(); window.kcNavegador.alternar(); return; }
    if (!NAV.on) return;
    if (ev.ctrlKey && k === 'l') { ev.preventDefault(); end.focus(); }
    else if (ev.ctrlKey && k === 't') { ev.preventDefault(); cmd('nova').then(() => end.focus()); }
    else if (ev.altKey && ev.key === 'ArrowLeft') { ev.preventDefault(); cmd('acao', 'voltar'); }
    else if (ev.altKey && ev.key === 'ArrowRight') { ev.preventDefault(); cmd('acao', 'avancar'); }
  }, true);
})();
