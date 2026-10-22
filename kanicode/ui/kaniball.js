/* KaniBall dentro do chat (2026-10-22, pedido do Pailer): ao abrir, a bolinha nativa (bolinha.py) pula até aqui, em
   cima da faixa de status, à direita; esta cópia em canvas assume e afunda até só o alto da cabeça ficar para fora (o
   resto atrás da faixa). Parada, ela olha o mouse e faz palhaçada de vez em quando; trabalhando, mostra o arco; com
   pergunta, sobe e mostra o ponto vermelho. Ao recolher, sobe inteira, a nativa aparece no mesmo lugar e volta para casa.
   Cara: os mesmos quadros do rosto.py (App.rosto_quadros). Python chama kbDocaAlvo/kbDoca/kbDocaEstado.
   Ctrl+Q aqui recolhe o chat e deixa a bolinha com o teclado (Ctrl+Q de novo nela fecha o KaniCode). */
(() => {
  if (window.KC_MOVEL) return;
  const L = 64, ESPIA = 30, SOBE_MS = 200;
  const doca = document.createElement('div');
  doca.className = 'kb-doca'; doca.id = 'kb-doca'; doca.hidden = true;
  doca.innerHTML = '<div class="kb-clip"><div class="kb-caixa" id="kb-caixa" title="KaniBall · clique ou Ctrl+Q recolhe"><canvas width="64" height="64"></canvas></div></div>';
  $('status').before(doca);   // o recorte (.kb-clip) termina na borda de cima da faixa: o que afunda some "atrás" dela
  const caixa = doca.firstChild.firstChild, cv = caixa.firstChild, g = cv.getContext('2d');
  const B = { on: false, expr: 'neutro', estado: '', voz: '', humorAte: 0, y: 0, rot: 0, sx: 1, sy: 1, olho: [0, 0],
              truque: null, proximo: 0, mouse: null, perto: false, quadros: {}, timer: 0 };
  const CORES = { '#': '#0E1110', w: '#FFFFFF', p: '#FF8FA3', r: '#FF5A5F' };

  function quadros(expr) {
    if (!B.quadros[expr]) {
      B.quadros[expr] = { fps: 10, quadros: null };
      api() && api().rosto_quadros(expr).then(r => { B.quadros[expr] = r; }).catch(() => {});
    }
    return B.quadros[expr];
  }
  ['neutro', 'feliz', 'trabalhando', 'pergunta'].forEach(e => window.addEventListener('pywebviewready', () => quadros(e)));

  // ── palhaçadas: cada uma é uma função do tempo (0..1) que mexe em y/rot/escala/olho/cara ──
  const ease = p => p * p * (3 - 2 * p);
  const TRUQUES = {
    pulo: { dur: 1.1, f: p => { const s = Math.sin(p * Math.PI); return { y: -ESPIA * 1.15 * s, sy: p > .85 ? 1 - .12 * Math.sin((p - .85) / .15 * Math.PI) : 1, expr: 'feliz' }; } },
    afunda: { dur: 1.8, f: p => ({ y: 20 * Math.sin(Math.min(1, p * 1.25) * Math.PI) ** .6, olho: [0, -1] }) },
    balanca: { dur: 1.4, f: p => ({ rot: 14 * Math.sin(p * Math.PI * 4) * (1 - p), y: -4 * Math.sin(p * Math.PI) }) },
    olha: { dur: 2.2, f: p => ({ olho: [p < .45 ? -2 : p < .9 ? 2 : 0, 0], y: -3 * Math.sin(p * Math.PI) }) },
    lingua: { dur: 1.6, f: p => ({ y: -ESPIA * .8 * Math.min(1, Math.sin(p * Math.PI) * 1.6), lingua: p > .15 && p < .85 }) },
    espia: { dur: 2.0, f: p => ({ y: 14 * Math.sin(p * Math.PI), rot: -22 * Math.sin(p * Math.PI), olho: [-1, -1] }) },
  };
  function sortear(t) {
    const nomes = Object.keys(TRUQUES), n = nomes[Math.floor(Math.random() * nomes.length)];
    B.truque = { n, t0: t };
    B.proximo = t + TRUQUES[n].dur + 5 + Math.random() * 7;
  }

  function grade(expr, t, olho, lingua) {
    const q = quadros(expr);
    let linhas = q.quadros && q.quadros.length ? q.quadros[Math.floor(t * q.fps) % q.quadros.length] : null;
    if (!linhas) return null;
    linhas = linhas.slice();
    const [dx, dy] = olho;
    if ((dx || dy) && ['neutro', 'feliz', 'pergunta', 'dormindo'].includes(expr)) {   // os olhos seguem o mouse
      const olhos = linhas.slice(3, 9).map(l => dx > 0 ? '.'.repeat(dx) + l.slice(0, 16 - dx) : dx < 0 ? l.slice(-dx) + '.'.repeat(-dx) : l);
      for (let i = 0; i < 6; i++) linhas[3 + i] = linhas[3 + i].split('').map((c, x) => '#w'.includes(c) ? '.' : c).join('');
      olhos.forEach((l, i) => {
        const y = 3 + i + dy;
        if (y < 0 || y > 15) return;
        linhas[y] = linhas[y].split('').map((c, x) => '#w'.includes(l[x]) ? l[x] : c).join('');
      });
    }
    if (lingua) {   // boca aberta com a língua de fora
      linhas[10] = '......####......'; linhas[11] = '......#pp#......'; linhas[12] = '.......pp.......';
    }
    return linhas;
  }

  function desenhar(t) {
    const k = window.devicePixelRatio || 1, P = Math.round(L * k);
    if (cv.width !== P) { cv.width = cv.height = P; cv.style.width = cv.style.height = L + 'px'; }
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, P, P);
    const gr = g.createRadialGradient(P * .32, P * .28, 0, P * .32, P * .28, P * .78);
    gr.addColorStop(0, '#D8FF7A'); gr.addColorStop(.35, '#C4F64E'); gr.addColorStop(1, '#7FB51A');
    g.fillStyle = gr; g.beginPath(); g.arc(P / 2, P / 2, P / 2 - .5, 0, Math.PI * 2); g.fill();
    let o = { y: 0, rot: 0, sx: 1, sy: 1, olho: B.olho, expr: null, lingua: false };
    const trab = B.estado === 'trabalhando';
    if (B.truque) {
      const T = TRUQUES[B.truque.n], p = (t - B.truque.t0) / T.dur;
      if (p >= 1) B.truque = null; else Object.assign(o, T.f(p));
    }
    let expr = B.expr;
    if (o.expr && expr === 'neutro') expr = o.expr;
    const linhas = grade(expr, t, o.olho || [0, 0], o.lingua);
    if (linhas) {
      const cel = Math.max(2, Math.floor(P * .8 / 16)), x0 = Math.floor(P / 2 - 8 * cel), y0 = Math.floor(P / 2 - 8 * cel + cel * .5);
      linhas.forEach((l, y) => { for (let x = 0; x < 16; x++) { const c = CORES[l[x]]; if (c) { g.fillStyle = c; g.fillRect(x0 + x * cel, y0 + y * cel, cel, cel); } } });
    }
    if (trab) {   // o arco que gira, como na bolinha nativa
      const d = P * .07;
      g.strokeStyle = 'rgba(14,17,16,.9)'; g.lineWidth = Math.max(2, P * .06); g.lineCap = 'round';
      const a = (t * 3 % 1) * Math.PI * 2;
      g.beginPath(); g.arc(P / 2, P / 2, P / 2 - d, a, a + Math.PI / 2); g.stroke();
    }
    if (B.voz === 'ouvindo') {
      const s = .5 + .5 * Math.sin(t * 8);
      g.strokeStyle = `rgba(14,17,16,${(.47 + .43 * s).toFixed(2)})`; g.lineWidth = P * (.05 + .04 * s);
      g.beginPath(); g.arc(P / 2, P / 2, P * .46, 0, Math.PI * 2); g.stroke();
    }
    if (B.estado === 'pergunta' || expr === 'pergunta') {
      const r = P * .11;
      g.fillStyle = '#0E1110'; g.beginPath(); g.arc(P - r * 1.2, r * 1.2, r + 1.5 * k, 0, Math.PI * 2); g.fill();
      g.fillStyle = '#FF5A5F'; g.beginPath(); g.arc(P - r * 1.2, r * 1.2, r - k, 0, Math.PI * 2); g.fill();
    }
    return o;
  }

  function quadro() {
    const t = performance.now() / 1000;
    if (B.humorAte && t > B.humorAte) B.humorAte = 0;
    const parada = B.expr === 'neutro' && !B.estado;
    if (parada && !B.truque && t > B.proximo) sortear(t);
    if (!parada && B.truque && TRUQUES[B.truque.n].f(0).expr) B.truque = null;
    // olhar o mouse
    if (B.mouse && !B.truque) {
      const r = caixa.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const dx = B.mouse[0] - cx, dy = B.mouse[1] - cy;
      B.olho = [Math.abs(dx) < 40 ? 0 : dx > 0 ? (dx > 220 ? 2 : 1) : (dx < -220 ? -2 : -1), dy < -60 ? -1 : 0];
    }
    const o = desenhar(t);
    // altura: pergunta sobe mais; trabalhando um pouco; mouse perto = curiosa
    let base = ESPIA;
    if (B.estado === 'pergunta' || B.expr === 'pergunta') base = 6 + 3 * Math.sin(t * 4);
    else if (B.estado === 'trabalhando') base = ESPIA - 8;
    else if (B.perto) base = ESPIA - 12;
    if (B.expr === 'feliz' || B.expr === 'concluido') base = 4 + 4 * Math.abs(Math.sin(t * 5));
    B.y += (base - B.y) * .25;
    caixa.style.transform = `translateY(${(B.y + (o.y || 0)).toFixed(1)}px) rotate(${(o.rot || 0).toFixed(1)}deg) scale(${o.sx || 1}, ${o.sy || 1})`;
  }

  function ligar(on) {
    clearInterval(B.timer);
    if (on && !document.hidden) B.timer = setInterval(quadro, 50);   // 20 por segundo basta (leve com o app parado)
  }
  document.addEventListener('visibilitychange', () => ligar(B.on));
  document.addEventListener('mousemove', e => { B.mouse = [e.clientX, e.clientY]; }, { passive: true });
  document.addEventListener('mouseleave', () => { B.mouse = null; B.olho = [0, 0]; });
  caixa.addEventListener('mouseenter', () => { B.perto = true; });
  caixa.addEventListener('mouseleave', () => { B.perto = false; });
  caixa.addEventListener('click', () => { if (B.on && api() && api().bola_clique) api().bola_clique(); });

  // ── chamado pelo kanicode.py ──
  window.kbDocaAlvo = () => {   // onde a bola fica inteira, logo acima da faixa (antes de afundar)
    const r = $('status').getBoundingClientRect();   // a doca tem a largura da faixa; .kb-caixa fica a 22 px da direita
    return { x: r.right - 22 - L, y: r.top - L, dpr: window.devicePixelRatio || 1 };
  };
  window.kbDoca = on => {
    if (on === true) {
      B.on = true; doca.hidden = false; B.y = 0; B.truque = null;
      B.proximo = performance.now() / 1000 + 2.5;
      caixa.style.transition = 'none';
      caixa.animate([{ transform: 'translateY(0) scale(1.14, .84)' }, { transform: 'translateY(0) scale(.94, 1.06)' }, { transform: 'translateY(0)' }],
                    { duration: 260, easing: 'ease-out' });
      setTimeout(() => ligar(true), 240);   // depois do quique, afunda até espiar
      quadro();
    } else if (on === false) {   // sobe inteira para a nativa aparecer no mesmo lugar
      ligar(false);
      caixa.style.transition = `transform ${SOBE_MS}ms ease-out`;
      caixa.style.transform = 'translateY(0)';
      B.y = 0;
    } else {   // 'fora': a nativa já está no lugar
      B.on = false; doca.hidden = true; caixa.style.transition = 'none';
    }
    return true;
  };
  window.kbDocaEstado = d => {
    B.expr = d.expr || 'neutro'; B.estado = d.estado || ''; B.voz = d.voz || '';
    if (d.humor_ate) B.humorAte = performance.now() / 1000 + d.humor_ate;
    if (B.expr !== 'neutro') B.truque = null;
    quadros(B.expr);
    return true;
  };

  // Ctrl+Q: recolhe o chat; a bolinha fica com o teclado (outro Ctrl+Q nela fecha tudo)
  document.addEventListener('keydown', e => {
    if (e.ctrlKey && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'q') {
      e.preventDefault(); e.stopPropagation();
      api() && api().esconder(true);
    }
  }, true);
  window.KC_BOLA = B;
})();
