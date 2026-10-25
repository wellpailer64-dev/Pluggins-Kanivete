/* KaniCode — KaniBall no Board (2026-10-25, pedido do Pailer). No quadro a bolinha sai da faixa de status e passeia pelos
   chats: anda (pulinhos ou rolando) no topo dos cartões, pula de um para outro, espia pela borda (e às vezes escorrega e
   cai no "chão", reclama e pula de volta), faz as palhaçadas da kaniball.js, corre para o chat que espera você e fica
   assistindo o que está trabalhando, atravessa os fios andando em cima deles (a corda cede com o peso) e empurra
   qualquer corda que encostar (as penduradas balançam). Clique = palhaçada; arrastar = pega e arremessa.
   Cara e truques: window.KB_ROSTO (kaniball.js); cordas e cartões: window.KC_BOARD (board.js). */
(() => {
  if (window.KC_MOVEL) return;
  const BD = window.KC_BOARD, KR = window.KB_ROSTO, A = window.KC_ABAS;
  if (!BD || !KR || !A) return;
  const R = 26, G = 1500, DORME_S = 120, PASSO = 120;
  const cv = document.createElement('canvas'); cv.className = 'bd-bola'; cv.title = 'KaniBall · clique: palhaçada · arraste para arremessar';
  const sombra = document.createElement('div'); sombra.className = 'bd-bola-sombra';
  const g = cv.getContext('2d');
  const Q = { x: 0, y: -600, vx: 0, vy: 0, modo: 'ar', sobre: null, dx: 0, plano: [], passo: null, truque: null, rot: 0, sq: 1,
              olho: [0, 0], expr: '', corda: null, s: 0, dorme: false, dormeT: 0, zzz: 0, mouse: null, pego: null, ligada: false, salto: 0 };
  const agora = () => performance.now() / 1000;

  // ── o cenário ──
  const cards = () => A.lista.map(a => BD.estado.cards[a.id] && Object.assign({ id: a.id }, BD.estado.cards[a.id])).filter(Boolean);
  const card = id => A.lista.some(a => a.id === id) ? BD.estado.cards[id] : null;
  const chao = () => { const cs = cards(); return cs.length ? Math.max(...cs.map(c => c.y + c.h)) + 140 : 400; };
  function estadoAba(id) {
    const on = id === A.ativa, e = A.estDe(id) || {};
    return { trab: on ? !!(window.K && K.ocupada) : !!e.ocupada, espera: on ? !!(window.K && K.espera) : e.aviso === 'pergunta' };
  }
  const sorteia = l => l[Math.floor(Math.random() * l.length)];
  function pesado(opcoes) {   // [[peso, fn], ...]
    const tot = opcoes.reduce((s, o) => s + o[0], 0);
    let r = Math.random() * tot;
    for (const o of opcoes) { if ((r -= o[0]) <= 0) return o[1]; }
    return opcoes[opcoes.length - 1][1];
  }

  // ── efeitos: texto que sobe e some; o cartão afunda um pouquinho quando ela cai em cima ──
  let ultFx = 0;
  function fx(txt, cor = '#E9F5D0', dx = 0) {
    const t = performance.now();
    if (t - ultFx < 180) return;
    ultFx = t;
    const e = document.createElement('span');
    e.className = 'bd-bola-fx'; e.textContent = txt; e.style.color = cor;
    e.style.left = (Q.x - 10 + dx + (Math.random() * 20 - 10)).toFixed(0) + 'px'; e.style.top = (Q.y - R - 18).toFixed(0) + 'px';
    BD.mundo.appendChild(e);
    e.animate([{ transform: 'translate(0,0) scale(.6)', opacity: 0 }, { transform: 'translate(0,-12px) scale(1)', opacity: 1, offset: .2 },
               { transform: `translate(${(Math.random() * 24 - 12).toFixed(0)}px,-56px) scale(.9)`, opacity: 0 }],
              { duration: 1200, easing: 'ease-out' }).onfinish = () => e.remove();
  }
  function amassarCartao(id, forca) {
    const el = BD.cardEl(id);
    if (el) el.animate([{ transform: 'translateY(0)' }, { transform: `translateY(${Math.min(6, forca).toFixed(1)}px)` }, { transform: 'translateY(0)' }],
                       { duration: 220, easing: 'ease-out' });
  }

  // ── movimento ──
  function lancar(tx, ty, T) {
    const dy = ty - Q.y;
    if (dy < 0) T = Math.max(T, Math.sqrt(-2 * dy / G) * 1.18 + .08);   // chega já descendo (senão passa por cima)
    Q.vx = (tx - Q.x) / T; Q.vy = (dy - .5 * G * T * T) / T;
    Q.modo = 'ar'; Q.sobre = null; Q.sq = .8;
    return T;
  }
  function pousar(c, vy) {
    Q.modo = 'chao'; Q.sobre = c ? c.id : null; Q.vx = Q.vy = 0;
    Q.y = (c ? c.y : chao()) - R; Q.dx = c ? Q.x - c.x : 0;
    Q.sq = 1 + Math.min(.35, vy / 2600);
    if (c && vy > 450) amassarCartao(c.id, vy / 180);
    if (!c && vy > 700) { fx(sorteia(['ai!', 'ui!', 'ops']), '#FF8FA3'); Q.plano = [{ tipo: 'esperar', s: .9, olho: [0, -1] }, { tipo: 'voltar' }]; Q.passo = null; }
  }
  function irPara(id, frac) {   // pulo até o topo de outro chat
    const c = card(id);
    if (!c) return;
    const tx = c.x + Math.max(R, Math.min(c.w - R, c.w * (frac == null ? .2 + Math.random() * .6 : frac)));
    lancar(tx, c.y - R, Math.min(1.25, Math.max(.5, .45 + Math.hypot(tx - Q.x, c.y - Q.y) / 1600)));
  }

  // ── o que fazer agora (só parada no topo de um chat) ──
  function decidir(t) {
    const c = Q.sobre && card(Q.sobre), outros = cards().filter(x => x.id !== Q.sobre);
    if (!c) { Q.plano = [{ tipo: 'voltar' }]; return; }
    const espera = outros.find(x => estadoAba(x.id).espera), trab = outros.filter(x => estadoAba(x.id).trab);
    if (espera && Math.random() < .7) { Q.plano = [{ tipo: 'pular', id: espera.id, frac: .5 }, { tipo: 'truque', n: 'pulo' }, { tipo: 'fx', txt: '!', cor: '#FF5A5F' }, { tipo: 'esperar', s: 2.5, olho: [0, 1] }]; return; }
    if (estadoAba(Q.sobre).trab && Math.random() < .45) { Q.plano = [{ tipo: 'andar', dx: c.w * (.3 + Math.random() * .4) }, { tipo: 'esperar', s: 3 + Math.random() * 3, olho: [0, 1], expr: 'trabalhando' }]; return; }
    const fio = BD.estado.fios.find(f => f.de === Q.sobre && card(f.para) && BD.cordas.get('f:' + f.id));
    const truques = Object.keys(KR.TRUQUES).filter(n => !['afunda', 'espia'].includes(n));
    const lado = Math.random() < .5 ? -1 : 1;
    Q.plano = pesado([
      [3, () => [{ tipo: 'andar', dx: c.w * (.08 + Math.random() * .84) }]],
      [1, () => [{ tipo: 'andar', dx: c.w * (.1 + Math.random() * .8), rolar: true }]],
      [2.2, () => [{ tipo: 'truque', n: sorteia(truques) }]],
      [trab.length ? 1.5 : 0, () => [{ tipo: 'pular', id: sorteia(trab).id }]],
      [outros.length ? 1.5 : 0, () => [{ tipo: 'pular', id: sorteia(outros).id }]],
      [1.2, () => {   // espia pela borda; às vezes escorrega
        const borda = lado < 0 ? R * .55 : c.w - R * .55, l = [{ tipo: 'andar', dx: borda }, { tipo: 'esperar', s: 1.6, olho: [lado * 2, 1], rot: lado * 24 }];
        if (Math.random() < .3) l.push({ tipo: 'fx', txt: 'opa', cor: '#FFE27A' }, { tipo: 'saltar', vx: lado * 90, vy: -120 });
        else l.push({ tipo: 'truque', n: 'balanca' });
        return l;
      }],
      [1, () => [{ tipo: 'andar', dx: c.w - R * .7 }, { tipo: 'esperar', s: .7, olho: [2, 1] }, { tipo: 'cordinha', id: c.id }]],   // pula na cordinha pendurada
      [fio ? 2 : 0, () => [{ tipo: 'andar', dx: c.w - R * .6 }, { tipo: 'esperar', s: .5, olho: [2, 1] }, { tipo: 'corda', fio: fio.id }]],
      [.6, () => [{ tipo: 'esperar', s: 2.5, olho: [0, -1], expr: 'feliz' }]],
    ])();
  }

  function proximoPasso(t) {
    if (!Q.plano.length) {
      if (t < Q.salto) return null;
      if (t - (KR.estado().ativa || t) > DORME_S && Q.sobre) { Q.dorme = true; Q.dormeT = KR.estado().ativa; Q.truque = { n: 'boceja', t0: t }; return null; }
      decidir(t); Q.salto = t + 1.2 + Math.random() * 2.5;
    }
    const p = Q.plano.shift();
    if (!p) return null;
    p.t0 = t;
    if (p.tipo === 'pular') { irPara(p.id, p.frac); return null; }
    if (p.tipo === 'voltar') {   // do chão (ou de onde caiu) volta ao chat mais perto
      const cs = cards();
      if (!cs.length) return null;
      const perto = cs.reduce((a, c) => Math.abs(c.x + c.w / 2 - Q.x) < Math.abs(a.x + a.w / 2 - Q.x) ? c : a);
      fx('hup', '#C4F64E'); irPara(perto.id); return null;
    }
    if (p.tipo === 'saltar') { Q.vx = p.vx; Q.vy = p.vy; Q.modo = 'ar'; Q.sobre = null; return null; }
    if (p.tipo === 'truque') { Q.truque = { n: p.n, t0: t }; return p; }
    if (p.tipo === 'cordinha') {   // salta da borda e cai em cima da cordinha pendurada (ela balança), depois volta
      const pend = BD.cordas.get('p:' + p.id), alvo = pend && pend.pts[Math.floor(pend.pts.length * .6)];
      const vy0 = -260, ty = alvo ? alvo.y : Q.y + 300, tq = (-vy0 + Math.sqrt(vy0 * vy0 + 2 * G * Math.max(0, ty - Q.y))) / G;
      Q.vx = ((alvo ? alvo.x : Q.x + 40) + 6 - Q.x) / tq; Q.vy = vy0; Q.modo = 'ar'; Q.sobre = null; fx('uhu', '#C4F64E');
      return null;
    }
    if (p.tipo === 'fx') { fx(p.txt, p.cor); return null; }
    if (p.tipo === 'corda') {
      const c = BD.cordas.get('f:' + p.fio);
      if (!c) return null;
      const alvo = c.pts[2];
      const T = lancar(alvo.x, alvo.y - R, .45);
      Q.corda = { fio: p.fio, ate: t + T };
      return null;
    }
    return p;
  }

  // ── encostar nas cordas: empurra os pontos para fora da bola (o Verlet do board.js vira o balanço) ──
  function empurrarCordas() {
    let mexeu = false;
    BD.cordas.forEach((c, chave) => {
      if (!c.pts || (Q.modo === 'corda' && chave === 'f:' + Q.corda.fio)) return;
      const n = c.pts.length, ult = c.solta ? n : n - 1;
      for (let i = 1; i < ult; i++) {
        const p = c.pts[i], dx = p.x - Q.x, dy = p.y - Q.y, d = Math.hypot(dx, dy);
        if (d >= R + 3 || d < .01) continue;
        p.x = Q.x + dx / d * (R + 3); p.y = Q.y + dy / d * (R + 3); mexeu = true;
      }
    });
    if (mexeu) BD.animar();
    return mexeu;
  }

  // ── um quadro ──
  let ult = 0;
  function passo(t) {
    const dt = Math.min(.05, t - (ult || t)); ult = t;
    const st = KR.estado();
    if (Q.dorme && st.ativa !== Q.dormeT) { Q.dorme = false; Q.truque = { n: 'acorda', t0: t }; Q.salto = t + 1.5; }
    let o = { y: 0, rot: 0, sx: 1, sy: 1, olho: null, expr: null, lingua: false, pisca: false, fx: null };
    if (Q.truque) {
      const T = KR.TODOS[Q.truque.n], p = T ? (t - Q.truque.t0) / T.dur : 1;
      if (p >= 1) Q.truque = null; else Object.assign(o, T.f(p));
    }
    let rotAlvo = 0, olho = null, expr = '';
    if (Q.pego) { /* a posição vem do mouse */ }
    else if (Q.modo === 'ar') {
      const y0 = Q.y;
      Q.vy += G * dt; Q.x += Q.vx * dt; Q.y += Q.vy * dt;
      Q.rot += Q.vx * dt * .9;
      if (Q.corda && t >= Q.corda.ate) {
        const c = BD.cordas.get('f:' + Q.corda.fio);
        if (c) { Q.modo = 'corda'; Q.s = 2; Q.vx = Q.vy = 0; fx('♪', '#C4F64E'); } else Q.corda = null;
      } else if (Q.vy > 0 && !Q.corda) {
        const c = cards().find(c => Q.x > c.x - R * .4 && Q.x < c.x + c.w + R * .4 && y0 + R <= c.y + 1 && Q.y + R >= c.y);
        if (c) pousar(c, Q.vy);
        else if (Q.y + R >= chao()) pousar(null, Q.vy);
      }
      olho = [Q.vx > 60 ? 1 : Q.vx < -60 ? -1 : 0, Q.vy > 200 ? 1 : -1];
    } else if (Q.modo === 'corda') {   // em cima do fio: cede com o peso; no fim, pulo para o chat da outra ponta
      const c = BD.cordas.get('f:' + Q.corda.fio), f = BD.estado.fios.find(x => x.id === Q.corda.fio);
      if (!c || !f) { Q.modo = 'ar'; Q.corda = null; Q.vy = 0; fx('ei!', '#FF8FA3'); }
      else {
        const n = c.pts.length, i = Math.min(n - 2, Math.floor(Q.s)), u = Q.s - i, a = c.pts[i], b = c.pts[i + 1];
        Q.x = a.x + (b.x - a.x) * u; Q.y = a.y + (b.y - a.y) * u - R + 2;
        a.y += 2.4 * (1 - u); b.y += 2.4 * u; BD.animar();
        const seg = Math.hypot(b.x - a.x, b.y - a.y) || 1;
        Q.s += dt * 95 / seg;
        rotAlvo = 8 * Math.sin(t * 6); olho = [1, 1];
        if (Q.s >= n - 3) { Q.modo = 'ar'; Q.corda = null; Q.plano = [{ tipo: 'pular', id: f.para, frac: .15 }]; Q.passo = null; Q.vx = 0; Q.vy = 0; Q.salto = 0; }
      }
    } else {   // no chão: em cima de um chat (segue o chat se ele for arrastado) ou no "chão" do quadro
      const c = Q.sobre && card(Q.sobre);
      if (Q.sobre && !c) { Q.modo = 'ar'; Q.sobre = null; }
      else {
        if (c) { Q.dx = Math.max(R * .4, Math.min(c.w - R * .4, Q.dx)); Q.x = c.x + Q.dx; Q.y = c.y - R; }
        else Q.y = chao() - R;
        if (!Q.passo && !Q.truque && !Q.dorme) Q.passo = proximoPasso(t);
        const p = Q.passo;
        if (p && p.tipo === 'andar' && c) {
          const dir = Math.sign(p.dx - Q.dx), v = p.rolar ? 150 : PASSO;
          Q.dx += dir * Math.min(Math.abs(p.dx - Q.dx), v * dt);
          if (p.rolar) { Q.rot += dir * v * dt / R * 57.3; olho = [0, 0]; }
          else { o.y += -Math.abs(Math.sin((t - p.t0) * 9)) * 7; rotAlvo = dir * 7; olho = [dir * 2, 0]; }
          if (Math.abs(p.dx - Q.dx) < 1.5) Q.passo = null;
        } else if (p && p.tipo === 'esperar') {
          olho = p.olho || null; expr = p.expr || ''; rotAlvo = p.rot || 0;
          if (t - p.t0 > p.s) Q.passo = null;
        } else if (p && p.tipo === 'truque') { if (!Q.truque) Q.passo = null; }
        else if (p) Q.passo = null;
      }
    }
    if (Q.modo !== 'ar' && !(Q.passo && Q.passo.rolar)) {   // assenta o giro no múltiplo de 360 mais perto
      const base = Math.round(Q.rot / 360) * 360;
      Q.rot += (base + rotAlvo - Q.rot) * .2;
    }
    Q.sq += (1 - Q.sq) * .18;
    if (!Q.pego && Q.modo !== 'corda') empurrarCordas(); else if (Q.pego) empurrarCordas();
    // olhos: o mouse quando parada
    if (!olho && Q.mouse && !Q.dorme) {
      const dx = Q.mouse.x - Q.x, dy = Q.mouse.y - Q.y;
      olho = [Math.abs(dx) < 40 ? 0 : dx > 0 ? (dx > 260 ? 2 : 1) : (dx < -260 ? -2 : -1), dy < -60 ? -1 : dy > 80 ? 1 : 0];
    }
    if (Q.dorme && t > Q.zzz) { Q.zzz = t + 1.8; fx('z', '#E9F5D0', 8); setTimeout(() => Q.dorme && fx('Z', '#E9F5D0', 16), 500); }
    if (o.fx) fx(o.fx[0], o.fx[1]);
    // cara: o estado do app manda (trabalhando/pergunta/feliz); depois o truque; depois o passo
    let cara = st.expr && st.expr !== 'neutro' ? st.expr : o.expr || expr || (Q.dorme ? 'dormindo' : 'neutro');
    if (cara === 'concluido') cara = 'feliz';
    desenhar(t, { expr: cara, olho: o.olho || olho || [0, 0], lingua: o.lingua, pisca: o.pisca, trab: st.estado === 'trabalhando',
                  ouvindo: st.voz === 'ouvindo', pergunta: st.estado === 'pergunta' || cara === 'pergunta' }, o);
  }

  function desenhar(t, f, o) {
    const z = BD.estado.vista.z, k = window.devicePixelRatio || 1, P = Math.max(16, Math.min(512, Math.round(2 * R * z * k)));
    if (cv.width !== P) { cv.width = cv.height = P; cv.style.width = cv.style.height = 2 * R + 'px'; }
    KR.quadros(f.expr);
    KR.pintar(g, P, t, Object.assign({ k }, f));
    const esc = R / 32, sx = (o.sx || 1) * (2 - Q.sq), sy = (o.sy || 1) * Q.sq;
    cv.style.left = (Q.x - R).toFixed(1) + 'px'; cv.style.top = (Q.y - R).toFixed(1) + 'px';
    cv.style.transform = `translateY(${((o.y || 0) * esc).toFixed(1)}px) rotate(${(Q.rot + (o.rot || 0)).toFixed(1)}deg) scale(${sx.toFixed(3)}, ${sy.toFixed(3)})`;
    // sombra no que estiver embaixo
    const baixo = cards().filter(c => Q.x > c.x && Q.x < c.x + c.w && c.y >= Q.y + R - 2).reduce((m, c) => Math.min(m, c.y), chao());
    const alt = Math.max(0, baixo - (Q.y + R) - (o.y || 0) * esc), s = Math.max(.25, 1 - alt / 500);
    sombra.style.left = (Q.x - R * .8).toFixed(1) + 'px'; sombra.style.top = (baixo - 5).toFixed(1) + 'px';
    sombra.style.transform = `scale(${s.toFixed(2)})`; sombra.style.opacity = Q.modo === 'corda' ? '0' : (s * .55).toFixed(2);
  }

  // ── pegar e arremessar; clique = palhaçada ──
  cv.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    e.stopPropagation(); e.preventDefault();
    cv.setPointerCapture(e.pointerId);
    const m = BD.mundoDe(e.clientX, e.clientY);
    Q.pego = { ox: Q.x - m.x, oy: Q.y - m.y, x0: e.clientX, y0: e.clientY, mexeu: false, hist: [[performance.now(), Q.x, Q.y]] };
    Q.dorme = false; Q.plano = []; Q.passo = null; Q.corda = null;
  });
  cv.addEventListener('pointermove', e => {
    if (!Q.pego) return;
    if (Math.hypot(e.clientX - Q.pego.x0, e.clientY - Q.pego.y0) > 4) Q.pego.mexeu = true;
    if (!Q.pego.mexeu) return;
    const m = BD.mundoDe(e.clientX, e.clientY);
    Q.x = m.x + Q.pego.ox; Q.y = m.y + Q.pego.oy; Q.modo = 'ar'; Q.sobre = null; Q.vx = Q.vy = 0;
    Q.pego.hist.push([performance.now(), Q.x, Q.y]); if (Q.pego.hist.length > 6) Q.pego.hist.shift();
  });
  cv.addEventListener('pointerup', () => {
    const p = Q.pego; Q.pego = null;
    if (!p) return;
    if (!p.mexeu) { Q.truque = { n: sorteia(['cocegas', 'giro', 'carinho', 'danca']), t0: agora() }; Q.salto = agora() + 2; return; }
    const h = p.hist, a = h[0], b = h[h.length - 1], dt = Math.max(.016, (b[0] - a[0]) / 1000);
    Q.vx = Math.max(-2400, Math.min(2400, (b[1] - a[1]) / dt)); Q.vy = Math.max(-2400, Math.min(2400, (b[2] - a[2]) / dt));
    Q.modo = 'ar'; fx(Math.hypot(Q.vx, Q.vy) > 900 ? 'uiii' : 'ei', '#FFE27A');
  });
  cv.addEventListener('dblclick', e => e.stopPropagation());
  document.addEventListener('pointermove', e => { if (Q.ligada) Q.mouse = BD.mundoDe(e.clientX, e.clientY); }, { passive: true });

  // ── liga com o Board; rAF só com o quadro à vista; dormindo, ~8 quadros por segundo ──
  let raf = 0, tmo = 0;
  function laco() {
    raf = tmo = 0;
    if (!Q.ligada || document.hidden) return;
    passo(agora());
    if (Q.dorme && !Q.truque) tmo = setTimeout(laco, 120); else raf = requestAnimationFrame(laco);
  }
  function conferir() {
    const on = document.body.classList.contains('board');
    if (on === Q.ligada) { if (on && !raf && !tmo && !document.hidden) laco(); return; }
    Q.ligada = on;
    if (on) {
      BD.mundo.appendChild(sombra); BD.mundo.appendChild(cv);
      const c = card(A.ativa) || cards()[0];   // entra caindo do alto em cima do chat aberto
      if (c) { Q.x = c.x + c.w * .75; Q.y = c.y - 520; } else { Q.x = 200; Q.y = -400; }
      Object.assign(Q, { vx: 0, vy: 0, modo: 'ar', sobre: null, plano: [], passo: null, corda: null, dorme: false, salto: 0 });
      ult = 0; laco();
    } else { cancelAnimationFrame(raf); clearTimeout(tmo); raf = tmo = 0; cv.remove(); sombra.remove(); }
  }
  setInterval(conferir, 400);
  document.addEventListener('visibilitychange', conferir);
  window.KC_BOLA = { estado: Q, passo: t => passo(t), fazer: n => { Q.truque = { n, t0: agora() }; } };
})();
