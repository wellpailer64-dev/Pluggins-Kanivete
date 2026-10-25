/* KaniCode — visão Board (2026-10-25). Os chats (abas) viram telas soltas num quadro quadriculado: arrastar pelo
   cabeçalho, mudar o tamanho no canto, rodinha = zoom (sobre a conversa, rola; com Ctrl, zoom), arrastar o fundo = mover a vista.
   O cartão da aba aberta recebe o chat DE VERDADE (os mesmos nós da janela, movidos para dentro dele); os outros mostram a
   prévia das últimas falas (api aba_previa) e, ao clicar, viram o aberto. Fios: puxe da bolinha da direita de um chat e solte
   noutro — quem puxa MANDA (comando) ou OBSERVA (leitura); servidor em fios.py / kanicode.py fio_*. Posições em localStorage. */
(() => {
  if (window.KC_MOVEL) return;
  const A = window.KC_ABAS;
  const B = { on: false, vista: { x: 40, y: 30, z: 0.8 }, cards: {}, fios: [], vivos: new Set(), sujos: new Set(), previas: {} };
  const SALVO = 'kc-board';
  try { Object.assign(B, JSON.parse(localStorage.getItem(SALVO) || '{}'), { fios: [], vivos: new Set(), sujos: new Set(), previas: {} }); } catch (e) {}
  const gravar = () => localStorage.setItem(SALVO, JSON.stringify({ on: B.on, vista: B.vista, cards: B.cards }));

  const board = document.createElement('div');
  board.className = 'board'; board.id = 'board'; board.hidden = true;
  board.innerHTML = `<div class="bd-pan"><div class="bd-mundo"><svg class="bd-fios"><defs><marker id="bd-seta" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="context-stroke"/></marker></defs><g class="fios"></g><g class="cortes"></g><path class="temp" style="display:none"/></svg></div></div>
    <div class="bd-dica">Arraste o fundo para mover · rodinha = zoom · puxe a bolinha da direita de um chat até outro para ligar</div>
    <div class="bd-barra"><button data-z="-" title="Afastar">−</button><button class="zoom" data-z="100" title="Zoom 100%">80%</button><button data-z="+" title="Aproximar">＋</button>
      <span class="div"></span><button data-acao="ajustar" title="Mostrar todos os chats">Ajustar</button><button data-acao="arrumar" title="Pôr os chats em grade">Arrumar</button>
      <span class="div"></span><button data-acao="nova" title="Novo chat (Ctrl+N)">＋ Chat</button><button data-acao="sair" title="Voltar às abas (Ctrl+B)">Abas</button></div>`;
  document.querySelector('.corpo').appendChild(board);   // ao lado da barra lateral (.lado), que continua no Board
  const pan = board.querySelector('.bd-pan'), mundo = board.querySelector('.bd-mundo'), svg = board.querySelector('.bd-fios'), gFios = svg.querySelector('.fios'), gCortes = svg.querySelector('.cortes'), temp = svg.querySelector('.temp');

  // ── o chat de verdade: os nós da janela vão para dentro do cartão aberto e voltam ao sair do Board ──
  const NOS = () => [document.querySelector('.meio'), $('planoFixo'), $('status'), $('anexos'), document.querySelector('.entrada')].filter(Boolean);
  const vivo = document.createElement('div'); vivo.className = 'bd-vivo';
  let lugares = null;
  function prenderVivo() {
    if (lugares) return;
    lugares = NOS().map(n => { const m = document.createComment('board'); n.before(m); return [n, m]; });
    lugares.forEach(([n]) => vivo.appendChild(n));
  }
  function soltarVivo() {
    if (!lugares) return;
    lugares.forEach(([n, m]) => { m.replaceWith(n); });
    lugares = null; vivo.remove();
  }

  // mover os nós zera a rolagem: o chat abre sempre na mensagem mais recente (de novo quando o histórico termina de chegar)
  function rolarFim() {
    const ir = () => { const c = $('conversa'); if (c) c.scrollTop = c.scrollHeight; };
    ir(); requestAnimationFrame(ir); setTimeout(ir, 250); setTimeout(ir, 700);
  }
  // ── vista (pan/zoom) ──
  function aplicarVista() {
    const { x, y, z } = B.vista;
    // zoom de CSS (não scale): o texto é redesenhado no tamanho final, nítido; o deslocamento em pixel inteiro
    pan.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    mundo.style.zoom = z;
    const g = 24 * z, G = 120 * z;
    board.style.backgroundSize = `${G}px ${G}px, ${G}px ${G}px, ${g}px ${g}px, ${g}px ${g}px`;
    board.style.backgroundPosition = `${x}px ${y}px, ${x}px ${y}px, ${x}px ${y}px, ${x}px ${y}px`;
    board.querySelector('.zoom').textContent = Math.round(z * 100) + '%';
  }
  function zoomEm(px, py, z) {   // px,py = ponto da tela que fica parado
    z = Math.min(1.6, Math.max(0.2, z));
    const v = B.vista, wx = (px - v.x) / v.z, wy = (py - v.y) / v.z;
    B.vista = { z, x: px - wx * z, y: py - wy * z };
    aplicarVista(); gravar();
  }
  const mundoDe = (cx, cy) => { const r = board.getBoundingClientRect(), v = B.vista; return { x: (cx - r.left - v.x) / v.z, y: (cy - r.top - v.y) / v.z }; };

  // ── cartões ──
  const LARG = 1000, ALT = 860, VAO = 90;
  Object.values(B.cards).forEach(c => { if ([460, 680, 800].includes(c.w)) c.w = LARG; if ([600, 700].includes(c.h)) c.h = ALT; });   // os do tamanho antigo crescem
  function lugarNovo(i) {
    const usados = Object.values(B.cards);
    if (!usados.length) return { x: 0, y: 0, w: LARG, h: ALT };
    const dir = usados.reduce((a, c) => (c.x + c.w > a.x + a.w ? c : a));
    return { x: dir.x + dir.w + VAO, y: dir.y, w: LARG, h: ALT };
  }
  const cardEl = id => mundo.querySelector(`.bd-card[data-aba="${id}"]`);
  function cabecalho(a) {
    const on = a.id === A.ativa, e = A.estDe(a.id);
    const trab = on ? K.ocupada : e.ocupada, espera = on ? K.espera : e.aviso === 'pergunta';
    const marca = espera ? 'pergunta' : trab ? 'trab' : e.aviso || '';
    const icone = marca === 'trab' ? '<span class="aba-trab"><i></i><i></i><i></i></span>' : `<span class="aba-ponto ${marca}"></span>`;
    return `${icone}<span class="bd-tit"><b>${esc(A.titulo(a))}</b><small>${esc(A.modeloCurto(a))}${espera ? ' · esperando você' : trab ? ' · trabalhando' : ''}</small></span>
      <button data-bt="abrir" title="Abrir nas abas (sai do Board)">⤢</button>`;
  }
  function previa(id) {
    const falas = B.previas[id];
    if (!falas) return '<div class="vazio">carregando…</div>';
    if (!falas.length) return '<div class="vazio">conversa vazia</div>';
    const rot = { pailer: 'Pailer', fio: 'outro chat', claude: 'Claude', kani: 'Kani', codex: 'Codex', pickle: 'Big Pickle' };
    return falas.map(f => `<div class="bd-fala ${esc(f.quem)}"><i>${esc(rot[f.quem] || f.quem)}</i>${esc(f.texto.length > 320 ? f.texto.slice(0, 320) + '…' : f.texto)}</div>`).join('');
  }
  function desenharCards() {
    if (!B.on) return;
    const ids = A.lista.map(a => a.id);
    mundo.querySelectorAll('.bd-card').forEach(c => { if (!ids.includes(c.dataset.aba)) c.remove(); });
    A.lista.forEach((a, i) => {
      if (!B.cards[a.id]) { B.cards[a.id] = lugarNovo(i); gravar(); }
      const p = B.cards[a.id], q = EQUIPE[a.quem] || EQUIPE.claude, on = a.id === A.ativa;
      let c = cardEl(a.id);
      if (!c) {
        c = document.createElement('div'); c.className = 'bd-card'; c.dataset.aba = a.id;
        c.innerHTML = '<div class="bd-cab"></div><div class="bd-corpo"></div><span class="bd-porta entrada"></span><span class="bd-porta saida" title="Puxe até outro chat para ligar (este chat manda/observa)"></span><span class="bd-tam" title="Mudar o tamanho"></span>';
        mundo.appendChild(c);
        if (!B.previas[a.id]) B.sujos.add(a.id);
      }
      c.style.cssText = `left:${p.x}px;top:${p.y}px;width:${p.w}px;height:${p.h}px;--cor:${q.cor}`;
      c.classList.toggle('on', on);
      c.querySelector('.bd-cab').innerHTML = cabecalho(a);
      const corpo = c.querySelector('.bd-corpo');
      if (on) { if (vivo.parentNode !== corpo) { corpo.innerHTML = ''; corpo.appendChild(vivo); rolarFim(); } }
      else if (corpo.contains(vivo) || !corpo.querySelector('.bd-previa') || c.dataset.previa !== JSON.stringify(B.previas[a.id] || null)) {
        if (corpo.contains(vivo)) vivo.remove();
        c.dataset.previa = JSON.stringify(B.previas[a.id] || null);
        corpo.innerHTML = `<div class="bd-previa" title="Clique para abrir este chat aqui">${previa(a.id)}</div><div class="bd-previa-dica">clique para conversar aqui · duplo clique no topo abre nas abas</div>`;
        const pv = corpo.querySelector('.bd-previa'); pv.scrollTop = pv.scrollHeight;
      }
      if (!on) aoVivo(a.id);
    });
    desenharFios();
    buscarPrevias();
  }
  let buscando = false;
  async function buscarPrevias() {
    if (buscando || !B.sujos.size || !api().aba_previa) return;
    buscando = true;
    try {
      for (const id of [...B.sujos]) {
        B.sujos.delete(id);
        if (id === A.ativa || !A.lista.some(a => a.id === id)) continue;
        try { B.previas[id] = await api().aba_previa(id, 8); } catch (e) { B.previas[id] = []; }
      }
    } finally { buscando = false; }
    desenharCards();
  }
  // ── ao vivo: os chats de trás mostram o texto chegando e a ferramenta em uso (dos eventos, sem esperar o fim) ──
  const AO = {}, aoTimers = {};
  function aoVivo(id) {
    const c = cardEl(id), pv = c && c.querySelector('.bd-previa');
    if (!pv) return;
    const v = AO[id];
    let el = pv.querySelector('.bd-aovivo');
    if (!v || (!v.texto && !v.ferr)) { if (el) el.remove(); return; }
    if (!el) { el = document.createElement('div'); pv.querySelector('.vazio')?.remove(); pv.appendChild(el); }
    const a = A.lista.find(x => x.id === id), quem = (a && a.quem) || 'claude', rot = { claude: 'Claude', kani: 'Kani', codex: 'Codex', pickle: 'Big Pickle' };
    const t = v.texto.length > 900 ? '…' + v.texto.slice(-900) : v.texto;
    el.className = 'bd-fala bd-aovivo ' + quem;
    el.innerHTML = `<i>${esc(rot[quem] || quem)} · ao vivo</i>${esc(t)}${v.ferr ? `<span class="bd-ferr">⚙ ${esc(v.ferr)}</span>` : ''}`;
    const perto = pv.scrollHeight - pv.scrollTop - pv.clientHeight < 80;
    if (perto) pv.scrollTop = pv.scrollHeight;
  }
  function aoEv(ev) {
    const id = String(ev.aba), v = AO[id] || (AO[id] = { texto: '', ferr: '' });
    if (ev.t === 'inicio') { v.texto = ''; v.ferr = ''; sujo(id); }
    else if (ev.t === 'texto_novo') { if (v.texto) sujo(id); v.texto = ''; v.ferr = ''; }
    else if (ev.t === 'texto') { v.texto += ev.d || ''; v.ferr = ''; }
    else if (ev.t === 'ferr') v.ferr = ev.nome || 'ferramenta';
    else if (ev.t === 'ferr_fim') v.ferr = '';
    else if (ev.t === 'pensando' || ev.t === 'kani_pensando') { if (!v.texto) v.ferr = 'pensando…'; }
    else if (['fim', 'saiu', 'ajudante_resposta'].includes(ev.t)) { delete AO[id]; }
    else return;
    if (!aoTimers[id]) aoTimers[id] = setTimeout(() => { aoTimers[id] = 0; aoVivo(id); }, 150);
  }
  let sujoTimer = 0;
  function sujo(id) { B.sujos.add(String(id)); clearTimeout(sujoTimer); sujoTimer = setTimeout(() => B.on && buscarPrevias(), 1200); }

  // ── fios ──
  const ponto = (id, lado) => { const p = B.cards[id]; return p && { x: lado === 'saida' ? p.x + p.w : p.x, y: p.y + p.h / 2 }; };
  // Cordas com física (Verlet): pontas presas, o meio com gravidade e amortecimento; a folga dá a barriga. Cada chat tem
  // uma cordinha pendurada na bolinha da direita (ponta solta com o pino): puxar o pino estica a corda até outro chat.
  const N = 18, GRAV = 0.55, AMORT = 0.975;
  const cordas = new Map();   // 'f:<id>' fio ligado · 'p:<aba>' cordinha pendurada · 'temp' a que está sendo puxada
  function corda(chave, a, b, comp, solta) {
    let c = cordas.get(chave);
    if (!c) {
      const bb = b || { x: a.x + 4, y: a.y + comp };
      c = { pts: Array.from({ length: N }, (_, i) => { const t = i / (N - 1), x = a.x + (bb.x - a.x) * t, y = a.y + (bb.y - a.y) * t; return { x, y, px: x, py: y }; }) };
      cordas.set(chave, c);
    }
    Object.assign(c, { a, b, solta: !!solta, L: comp / (N - 1) });
    return c;
  }
  function passo(c) {
    const p = c.pts, ult = c.solta ? N : N - 1;
    let mov = 0;
    for (let i = 1; i < ult; i++) {
      const q = p[i], vx = (q.x - q.px) * AMORT, vy = (q.y - q.py) * AMORT;
      q.px = q.x; q.py = q.y; q.x += vx; q.y += vy + GRAV; mov += Math.abs(vx) + Math.abs(vy);
    }
    for (let k = 0; k < 14; k++) {
      Object.assign(p[0], { x: c.a.x, y: c.a.y });
      if (!c.solta) Object.assign(p[N - 1], { x: c.b.x, y: c.b.y });
      for (let i = 0; i < N - 1; i++) {
        const u = p[i], v = p[i + 1], dx = v.x - u.x, dy = v.y - u.y, d = Math.hypot(dx, dy) || 1e-6, dif = (d - c.L) / d;
        const fu = i === 0 ? 0 : (i + 1 === N - 1 && !c.solta ? 1 : 0.5), fv = i + 1 === N - 1 && !c.solta ? 0 : (i === 0 ? 1 : 0.5);
        u.x += dx * dif * fu; u.y += dy * dif * fu; v.x -= dx * dif * fv; v.y -= dy * dif * fv;
      }
    }
    return mov;
  }
  function caminho(c) {
    const p = c.pts; let d = `M${p[0].x.toFixed(1)} ${p[0].y.toFixed(1)}`;
    for (let i = 1; i < N - 1; i++) d += ` Q${p[i].x.toFixed(1)} ${p[i].y.toFixed(1)} ${((p[i].x + p[i + 1].x) / 2).toFixed(1)} ${((p[i].y + p[i + 1].y) / 2).toFixed(1)}`;
    return d + ` L${p[N - 1].x.toFixed(1)} ${p[N - 1].y.toFixed(1)}`;
  }
  const comprimento = (a, b, folga) => Math.hypot(b.x - a.x, b.y - a.y) * folga + 24;
  function desenharFios() {   // estrutura (um <g> por corda); a posição de cada quadro vem de quadro()
    if (!B.on) return;
    const ligados = new Set(B.fios.map(f => f.de));
    gFios.innerHTML = B.fios.map(f => `<g data-fio="${f.id}"><path class="toque"/><path class="linha ${f.modo}${B.vivos.has(f.id) ? ' vivo' : ''}"/>
        <text text-anchor="middle">${f.modo === 'comando' ? '⚡ manda' : '👁 lê'}</text></g>`).join('') +
      A.lista.filter(a => B.cards[a.id] && !(arr && arr.tipo === 'fio' && arr.de === a.id)).map(a =>
        `<g class="pendurada${ligados.has(a.id) ? ' tem' : ''}" data-pino="${a.id}"><path class="linha"/><circle class="pino" r="7" data-pino="${a.id}"/></g>`).join('');
    [...cordas.keys()].forEach(k => {
      if ((k.startsWith('f:') && !B.fios.some(f => 'f:' + f.id === k)) || (k.startsWith('p:') && !B.cards[k.slice(2)])) cordas.delete(k);
    });
    animar();
  }
  let rodando = 0, calmo = 0;
  function animar() { calmo = 0; if (!rodando) rodando = requestAnimationFrame(quadro); }
  function quadro() {
    rodando = 0;
    if (!B.on) return;
    let mov = 0;
    B.fios.forEach(f => {
      const a = ponto(f.de, 'saida'), b = ponto(f.para, 'entrada'), g = gFios.querySelector(`[data-fio="${f.id}"]`);
      if (!a || !b || !g) return;
      const c = corda('f:' + f.id, a, b, comprimento(a, b, 1.08));
      mov += passo(c);
      const d = caminho(c), m = c.pts[N >> 1];
      g.querySelectorAll('path').forEach(p => p.setAttribute('d', d));
      const t = g.querySelector('text'); t.setAttribute('x', m.x); t.setAttribute('y', m.y - 10);
    });
    gFios.querySelectorAll('g.pendurada').forEach(g => {
      const id = g.dataset.pino, a = ponto(id, 'saida');
      if (!a) return;
      const c = corda('p:' + id, a, null, 46, true);
      mov += passo(c);
      const e = c.pts[N - 1];
      g.querySelector('path').setAttribute('d', caminho(c));
      const pino = g.querySelector('circle'); pino.setAttribute('cx', e.x); pino.setAttribute('cy', e.y);
    });
    if (arr && arr.tipo === 'fio' && arr.fim) {
      const a = ponto(arr.de, 'saida'), c = corda('temp', a, arr.fim, comprimento(a, arr.fim, 1.12));
      mov += passo(c);
      temp.setAttribute('d', caminho(c));
    }
    calmo = mov < 0.02 * N ? calmo + 1 : 0;
    mov += quadroCortes();
    if (calmo < 30 || cortes.length || (arr && (arr.tipo === 'fio' || arr.tipo === 'card' || arr.tipo === 'tam'))) rodando = requestAnimationFrame(quadro);
  }
  // ── cortar a corda: clique com a lâmina divide no ponto, as duas metades caem presas nos chats e somem ──
  const cortes = [];
  function reamostrar(pts) {   // metade da corda → N pontos igualmente espaçados (a física usa N fixo)
    const acum = [0];
    for (let i = 1; i < pts.length; i++) acum.push(acum[i - 1] + Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y));
    const total = acum[acum.length - 1] || 1, out = [];
    for (let k = 0, j = 0; k < N; k++) {
      const alvo = total * k / (N - 1);
      while (j < pts.length - 2 && acum[j + 1] < alvo) j++;
      const t = (alvo - acum[j]) / ((acum[j + 1] - acum[j]) || 1), x = pts[j].x + (pts[j + 1].x - pts[j].x) * t, y = pts[j].y + (pts[j + 1].y - pts[j].y) * t;
      out.push({ x, y, px: x - (Math.random() - 0.5) * 3, py: y - 2.5 });   // empurrãozinho para baixo: cai
    }
    return { pts: out, L: total / (N - 1), solta: true };
  }
  function cortar(f, e) {
    const c = cordas.get('f:' + f.id);
    if (c) {
      const m = mundoDe(e.clientX, e.clientY);
      let k = 1, melhor = Infinity;
      c.pts.forEach((q, i) => { const d = Math.hypot(q.x - m.x, q.y - m.y); if (i > 0 && i < N - 1 && d < melhor) { melhor = d; k = i; } });
      const metade = (pts, id, lado) => {
        const r = reamostrar(pts), el = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        el.setAttribute('class', 'linha corte ' + f.modo); gCortes.appendChild(el);
        return Object.assign(r, { id, lado, el });
      };
      cortes.push({ t0: performance.now(), partes: [metade(c.pts.slice(0, k + 1), f.de, 'saida'), metade(c.pts.slice(k).reverse(), f.para, 'entrada')] });
    }
    cordas.delete('f:' + f.id);
    som('corte');
    B.fios = B.fios.filter(x => x.id !== f.id);
    desenharFios(); A.desenhar();
    api().fio_apagar(f.id).catch(err => { erro && erro(err); carregarFios(); });
  }
  function quadroCortes() {
    let mov = 0;
    const agora = performance.now();
    for (let i = cortes.length - 1; i >= 0; i--) {
      const ct = cortes[i], idade = agora - ct.t0;
      ct.partes.forEach(c => {
        c.a = ponto(c.id, c.lado) || c.pts[0];
        mov += passo(c);
        c.el.setAttribute('d', caminho(c));
        c.el.style.opacity = String(Math.max(0, 1 - Math.max(0, idade - 700) / 600));
      });
      if (idade > 1300) { ct.partes.forEach(c => c.el.remove()); cortes.splice(i, 1); }
    }
    return mov;
  }
  // sons sintetizados (sem arquivo): 'clique' ao encaixar, 'corte' = lâmina passando (chiado agudo + "tchin")
  function som(tipo) {
    try {
      const ac = clique.ac || (clique.ac = new AudioContext()), t = ac.currentTime;
      if (tipo !== 'corte') return clique();
      const dur = 0.22, buf = ac.createBuffer(1, Math.round(ac.sampleRate * dur), ac.sampleRate), d = buf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / d.length, 2);
      const ruido = ac.createBufferSource(); ruido.buffer = buf;
      const bp = ac.createBiquadFilter(); bp.type = 'bandpass'; bp.Q.value = 1.4;
      bp.frequency.setValueAtTime(2500, t); bp.frequency.exponentialRampToValueAtTime(7500, t + 0.16);
      const g1 = ac.createGain(); g1.gain.setValueAtTime(0.0001, t); g1.gain.exponentialRampToValueAtTime(0.55, t + 0.02); g1.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      ruido.connect(bp).connect(g1).connect(ac.destination); ruido.start(t);
      const o = ac.createOscillator(), g2 = ac.createGain();
      o.type = 'sine'; o.frequency.setValueAtTime(5200, t + 0.05); o.frequency.exponentialRampToValueAtTime(4300, t + 0.4);
      g2.gain.setValueAtTime(0.0001, t + 0.05); g2.gain.exponentialRampToValueAtTime(0.12, t + 0.06); g2.gain.exponentialRampToValueAtTime(0.0001, t + 0.42);
      o.connect(g2).connect(ac.destination); o.start(t + 0.05); o.stop(t + 0.45);
    } catch (e) {}
  }
  function clique() {   // estalo curto ao encaixar a corda (sintetizado, sem arquivo)
    try {
      const ac = clique.ac || (clique.ac = new AudioContext()), t = ac.currentTime;
      const o = ac.createOscillator(), g = ac.createGain();
      o.type = 'triangle'; o.frequency.setValueAtTime(1900, t); o.frequency.exponentialRampToValueAtTime(700, t + 0.05);
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.35, t + 0.004); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);
      o.connect(g).connect(ac.destination); o.start(t); o.stop(t + 0.1);
    } catch (e) {}
  }
  async function carregarFios() { try { const l = await api().fios(); B.fios = Array.isArray(l) ? l : []; } catch (e) { B.fios = []; } desenharFios(); A.desenhar(); }

  function menu(x, y, html, aoEscolher) {
    fecharMenu();
    const m = document.createElement('div'); m.className = 'bd-menu'; m.innerHTML = html;
    document.body.appendChild(m);
    const r = m.getBoundingClientRect();
    m.style.left = Math.min(x, innerWidth - r.width - 8) + 'px'; m.style.top = Math.min(y, innerHeight - r.height - 8) + 'px';
    m.addEventListener('click', e => { const b = e.target.closest('button[data-v]'); if (b) { fecharMenu(); aoEscolher(b.dataset.v); } });
    setTimeout(() => document.addEventListener('pointerdown', fora, true), 0);
  }
  const fora = e => { if (!e.target.closest('.bd-menu')) fecharMenu(); };
  function fecharMenu() { document.querySelectorAll('.bd-menu').forEach(m => m.remove()); document.removeEventListener('pointerdown', fora, true); }
  const nomeAba = id => { const a = A.lista.find(x => x.id === id); return a ? A.titulo(a) : 'Aba ' + id; };
  const MODOS = f => `<button data-v="leitura" class="${f && f.modo === 'leitura' ? 'on' : ''}">👁 Leitura<small>o chat de origem pode ler este</small></button>
      <button data-v="comando" class="${f && f.modo === 'comando' ? 'on' : ''}">⚡ Comando<small>o de origem manda pedidos e recebe a resposta</small></button>`;
  function menuNovoFio(de, para, x, y) {
    menu(x, y, `<h4>${esc(nomeAba(de))} → ${esc(nomeAba(para))}</h4>${MODOS(null)}`, async modo => {
      try { await api().fio_criar(de, para, modo); } catch (e) { erro && erro(e); }
    });
  }
  function menuFio(f, x, y) {
    gFios.querySelector(`[data-fio="${f.id}"] .linha`)?.classList.add('sel');
    menu(x, y, `<h4>${esc(nomeAba(f.de))} → ${esc(nomeAba(f.para))}</h4>${MODOS(f)}
      <button data-v="parar">■ Parar o chat ${esc(nomeAba(f.para))}<small>interrompe o que ele estiver fazendo</small></button>
      <button data-v="apagar" class="perigo">✕ Apagar fio</button>`, async v => {
      try {
        if (v === 'apagar') await api().fio_apagar(f.id);
        else if (v === 'parar') await api().aba_parar(f.para);
        else if (v !== f.modo) await api().fio_mudar(f.id, v);
      } catch (e) { erro && erro(e); }
    });
    setTimeout(() => gFios.querySelectorAll('.sel').forEach(p => p.classList.remove('sel')), 50);
  }

  // ── mouse: mover a vista, mover/redimensionar cartão, puxar fio, abrir chat ──
  let arr = null;
  board.addEventListener('pointerdown', e => {
    if (e.button !== 0 && e.button !== 1) return;
    if (e.target.closest('.bd-barra, .bd-menu')) return;
    const pino = e.target.closest('[data-pino]');
    if (pino && e.button === 0) { puxar(pino.dataset.pino, e); return; }
    const g = e.target.closest('[data-fio]');
    if (g) { const f = B.fios.find(x => x.id === g.dataset.fio); if (f && e.button === 0) { cortar(f, e); animar(); } return; }   // botão direito = menu
    const c = e.target.closest('.bd-card');
    if (!c || e.button === 1) {   // fundo (ou botão do meio em qualquer lugar): move a vista
      arr = { tipo: 'vista', x0: e.clientX, y0: e.clientY, v: Object.assign({}, B.vista) };
      board.classList.add('panando'); board.setPointerCapture(e.pointerId); e.preventDefault(); return;
    }
    const id = c.dataset.aba, p = B.cards[id];
    if (e.target.closest('.bd-porta.saida')) { puxar(id, e); return; }
    if (e.target.closest('.bd-tam')) { arr = { tipo: 'tam', id, x0: e.clientX, y0: e.clientY, p: Object.assign({}, p) }; board.setPointerCapture(e.pointerId); e.preventDefault(); animar(); return; }
    // move pelo topo, pela prévia (clique sem arrastar abre) e, no chat aberto, pelo vazio da conversa ou pela borda
    const vazio = e.target === c || e.target.matches('.bd-corpo, .bd-vivo, .conversa, .meio, .status');
    if ((e.target.closest('.bd-cab') && !e.target.closest('button')) || e.target.closest('.bd-previa, .bd-previa-dica') || vazio) {
      arr = { tipo: 'card', id, x0: e.clientX, y0: e.clientY, p: Object.assign({}, p), mexeu: false };
      board.setPointerCapture(e.pointerId); e.preventDefault(); animar(); return;
    }
  });
  function puxar(id, e) {
    arr = { tipo: 'fio', de: id, fim: mundoDe(e.clientX, e.clientY) };
    cordas.delete('temp');
    const pend = cordas.get('p:' + id);   // a corda puxada nasce da pendurada (continua no mesmo lugar, sem pulo)
    if (pend) cordas.set('temp', { pts: pend.pts.map(q => Object.assign({}, q)) });
    temp.style.display = '';
    board.classList.add('puxando');
    board.setPointerCapture(e.pointerId); e.preventDefault();
    desenharFios();
  }
  board.addEventListener('pointermove', e => {
    if (!arr) return;
    const z = B.vista.z;
    if (arr.tipo === 'vista') { B.vista = { z: arr.v.z, x: arr.v.x + e.clientX - arr.x0, y: arr.v.y + e.clientY - arr.y0 }; aplicarVista(); return; }
    if (arr.tipo === 'card' || arr.tipo === 'tam') {
      const dx = (e.clientX - arr.x0) / z, dy = (e.clientY - arr.y0) / z;
      if (Math.abs(dx) + Math.abs(dy) > 3) arr.mexeu = true;
      const p = B.cards[arr.id];
      if (arr.tipo === 'card') { p.x = Math.round(arr.p.x + dx); p.y = Math.round(arr.p.y + dy); }
      else { p.w = Math.max(360, Math.round(arr.p.w + dx)); p.h = Math.max(260, Math.round(arr.p.h + dy)); }
      const c = cardEl(arr.id); c.style.left = p.x + 'px'; c.style.top = p.y + 'px'; c.style.width = p.w + 'px'; c.style.height = p.h + 'px';
      animar(); return;
    }
    if (arr.tipo === 'fio') {
      arr.fim = mundoDe(e.clientX, e.clientY); animar();
      mundo.querySelectorAll('.bd-card.alvo').forEach(c => c.classList.remove('alvo'));
      const sob = document.elementFromPoint(e.clientX, e.clientY)?.closest('.bd-card');
      if (sob && sob.dataset.aba !== arr.de) sob.classList.add('alvo');
    }
  });
  board.addEventListener('pointerup', e => {
    if (!arr) return;
    const a = arr; arr = null; board.classList.remove('panando');
    if (a.tipo === 'vista') { gravar(); return; }
    if (a.tipo === 'card' || a.tipo === 'tam') { gravar(); if (a.tipo === 'card' && !a.mexeu) abrirAqui(a.id); return; }
    if (a.tipo === 'fio') {
      temp.style.display = 'none'; temp.removeAttribute('d'); cordas.delete('temp');
      board.classList.remove('puxando');
      mundo.querySelectorAll('.bd-card.alvo').forEach(c => c.classList.remove('alvo'));
      const sob = document.elementFromPoint(e.clientX, e.clientY)?.closest('.bd-card');
      if (sob && sob.dataset.aba !== a.de) { clique(); menuNovoFio(a.de, sob.dataset.aba, e.clientX, e.clientY); }
      desenharFios();   // a cordinha volta a ficar pendurada (e balança)
    }
  });
  board.addEventListener('contextmenu', e => {   // botão direito na corda: modo, parar, apagar
    const g = e.target.closest('[data-fio]'), f = g && B.fios.find(x => x.id === g.dataset.fio);
    if (f) { e.preventDefault(); menuFio(f, e.clientX, e.clientY); }
  });
  board.addEventListener('dblclick', e => {
    const c = e.target.closest('.bd-card');
    if (c && e.target.closest('.bd-cab')) { e.preventDefault(); abrirNasAbas(c.dataset.aba); }
  });
  board.addEventListener('click', e => {
    const b = e.target.closest('[data-bt="abrir"]');
    if (b) { abrirNasAbas(b.closest('.bd-card').dataset.aba); return; }
    const z = e.target.closest('[data-z]');
    if (z) { const r = board.getBoundingClientRect(), v = z.dataset.z; zoomEm(r.width / 2, r.height / 2, v === '+' ? B.vista.z * 1.2 : v === '-' ? B.vista.z / 1.2 : 1); return; }
    const ac = e.target.closest('[data-acao]')?.dataset.acao;
    if (ac === 'ajustar') ajustar(); else if (ac === 'arrumar') arrumar(); else if (ac === 'nova') A.nova(); else if (ac === 'sair') alternar(false);
  });
  board.addEventListener('wheel', e => {
    const rolavel = e.target.closest('.bd-card .conversa, .bd-previa, .bd-card textarea, .bd-card .cmds');
    if (rolavel && !e.ctrlKey) return;   // sobre a conversa a rodinha rola; com Ctrl, zoom
    e.preventDefault();
    const r = board.getBoundingClientRect();
    zoomEm(e.clientX - r.left, e.clientY - r.top, B.vista.z * Math.exp(-e.deltaY * 0.0015));
  }, { passive: false });

  async function abrirAqui(id) {
    if (id === A.ativa || A.mudando) return;
    await A.trocar(id);
    desenharCards(); rolarFim();
  }
  async function abrirNasAbas(id) {
    if (id !== A.ativa) await A.trocar(id);
    alternar(false);
  }
  function ajustar() {
    const cs = A.lista.map(a => B.cards[a.id]).filter(Boolean);
    if (!cs.length) return;
    const x0 = Math.min(...cs.map(c => c.x)), y0 = Math.min(...cs.map(c => c.y));
    const x1 = Math.max(...cs.map(c => c.x + c.w)), y1 = Math.max(...cs.map(c => c.y + c.h));
    const r = board.getBoundingClientRect(), m = 40;
    const z = Math.min(1, Math.max(0.2, Math.min((r.width - 2 * m) / (x1 - x0), (r.height - 2 * m - 50) / (y1 - y0))));
    B.vista = { z, x: (r.width - (x1 - x0) * z) / 2 - x0 * z, y: m - y0 * z };
    aplicarVista(); gravar();
  }
  function arrumar() {
    const n = A.lista.length, col = Math.ceil(Math.sqrt(n));
    A.lista.forEach((a, i) => { B.cards[a.id] = { x: (i % col) * (LARG + VAO), y: Math.floor(i / col) * (ALT + VAO), w: LARG, h: ALT }; });
    gravar(); desenharCards(); ajustar();
  }

  function alternar(on = !B.on) {
    B.on = !!on;
    document.body.classList.toggle('board', B.on);
    board.hidden = !B.on;
    if (B.on) {
      prenderVivo();
      A.lista.forEach(a => { if (a.id !== A.ativa) B.sujos.add(a.id); });
      aplicarVista(); carregarFios(); desenharCards();
    } else {
      soltarVivo();
      mundo.querySelectorAll('.bd-card').forEach(c => c.remove());
      rolarFim();
      if (window.KC_MOVEL) return;
      texto.focus();
    }
    gravar(); A.desenhar();
  }

  // eventos do servidor: fios mudaram, fio trabalhando, conversa de outra aba andou
  const evAntes = window.kcEv;
  window.kcEv = ev => {
    if (ev && ev.t === 'fios') { B.fios = Array.isArray(ev.lista) ? ev.lista : []; desenharFios(); A.desenhar(); return; }
    if (ev && ev.t === 'fio_ativo') { if (ev.on) B.vivos.add(ev.id); else B.vivos.delete(ev.id); desenharFios(); return; }
    evAntes(ev);
    if (B.on && ev && ev.aba != null && String(ev.aba) !== A.ativa) aoEv(ev);
    if (B.on && ev && ev.aba != null && String(ev.aba) !== A.ativa && ['fim', 'saiu', 'ajudante_resposta', 'eco_eu', 'ajudante'].includes(ev.t)) sujo(ev.aba);
  };
  document.addEventListener('keydown', e => {
    if (e.ctrlKey && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'b' && !document.querySelector('dialog[open]')) { e.preventDefault(); alternar(); }
  }, true);

  // nas abas normais: quem está ligado a quem (abas.js desenha a marca com fiosDa)
  const fiosDa = id => B.fios.filter(f => f.de === String(id) || f.para === String(id));
  window.KC_BOARD = { alternar, abasMudaram: () => B.on && desenharCards(), estado: B, ajustar, arrumar, fiosDa, nomeAba: id => nomeAba(id),
    cordas, animar, mundo, cardEl, N, mundoDe };   // cordas/animar/mundo: a KaniBall do quadro (board-bola.js) mexe nas cordas
  window.addEventListener('pywebviewready', () => setTimeout(() => { if (B.on && A.ativa) alternar(true); else carregarFios(); }, 600));
})();
