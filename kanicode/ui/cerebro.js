/* Cérebro do perfil: neurônios (memórias) em 3D leve num canvas 2D — cada área é um lobo em volta de você (centro).
   Gira devagar, arrasta para girar, rodinha aproxima, clique mostra o neurônio. Só anima com o painel à vista. */
(() => {
  const COR = { kani: '#C692FF', pc: '#74C7EC', eu: '#B6F23A', design: '#F29A3A', video: '#B48CF2', audio: '#7FD3E8', ia: '#F25CC0', dev: '#3AD29F', clientes: '#F2D23A' };
  const C = { d: null, pts: [], ligas: [], el: null, cv: null, ctx: null, rx: -0.25, ry: 0, zoom: 1, auto: true, raf: 0, sel: null,
              hover: null, foco: null, ambito: '', finalidade: '', agente: '', pcTimer: 0, pcAtualizando: false, areasVisiveis: new Set(), gruposVisiveis: new Set(), luz: null, viz: null, base: 0, pulsos: [], arr: null, ultimo: 0 };

  // ── som: cada área uma nota da mesma escala pentatônica (nunca desafina junto), seno macio com eco leve;
  //    todos com a MESMA duração e volume baixo. Web Audio, sem arquivos. Silenciar: botão ♪ (lembra a escolha).
  const NOTA = { kani: 698.46, pc: 293.66, eu: 392.0, design: 440.0, video: 523.25, audio: 587.33, ia: 659.25, dev: 783.99, clientes: 880.0 };
  const SOM = { ctx: null, saida: null, notas: null, ambiente: null, ambienteLigado: false, ultimo: 0, ligado: localStorage.getItem('cerebro-som') !== '0' };
  const DUR = 1.6;
  function somPreparar() {
    if (SOM.ctx) return SOM.ctx;
    const ctx = SOM.ctx = new (window.AudioContext || window.webkitAudioContext)();
    const filtro = ctx.createBiquadFilter(); filtro.type = 'lowpass'; filtro.frequency.value = 2200;
    const eco = ctx.createDelay(); eco.delayTime.value = .27;
    const volta = ctx.createGain(); volta.gain.value = .32;
    const molhado = ctx.createGain(); molhado.gain.value = .28;
    const mestre = ctx.createGain(); mestre.gain.value = window.KC_MICROFONE_ATIVO ? 0 : .9;
    filtro.connect(mestre); filtro.connect(eco); eco.connect(volta); volta.connect(eco); eco.connect(molhado); molhado.connect(mestre);
    mestre.connect(ctx.destination);
    SOM.saida = filtro;
    SOM.notas = mestre;
    return ctx;
  }
  function tocarSom(p, forte) {
    if (window.KC_MICROFONE_ATIVO || !SOM.ligado || !p || !p.area || !NOTA[p.area]) return;
    const agora = performance.now(); if (agora - SOM.ultimo < 140) return; SOM.ultimo = agora;
    const ctx = somPreparar(); if (ctx.state === 'suspended') ctx.resume();
    const t = ctx.currentTime, f = NOTA[p.area];
    // lobo e grupo: nota + quinta; neurônio: nota só (o tipo muda só o brilho, nunca o tamanho)
    const vozes = p.tipo === 'area' || p.tipo === 'grupo' ? [[f, 1], [f * 1.5, .45]] : [[f, 1], [f * 2.003, p.no && p.no.grupo === 'saber' ? .18 : .1]];
    const pico = (forte ? .055 : .032);
    const env = ctx.createGain();
    env.gain.setValueAtTime(0, t);
    env.gain.linearRampToValueAtTime(pico, t + .09);              // entrada macia, sem estalo
    env.gain.exponentialRampToValueAtTime(.0001, t + DUR);        // a mesma duração para todos
    env.connect(SOM.saida);
    for (const [fr, g] of vozes) {
      const o = ctx.createOscillator(), gg = ctx.createGain();
      o.type = 'sine'; o.frequency.value = fr; o.detune.value = (Math.random() - .5) * 6;
      gg.gain.value = g; o.connect(gg); gg.connect(env); o.start(t); o.stop(t + DUR + .05);
    }
  }

  // Fundo grave só na tela cheia; transições suaves e o mesmo botão de silêncio das notas.
  function somAmbiente() {
    const ligado = !!(!window.KC_MICROFONE_ATIVO && SOM.ligado && C.el?.isConnected && C.el.classList.contains('grande') &&
      !C.el.closest('[hidden]') && !document.hidden);
    if (ligado === SOM.ambienteLigado) return;
    if (ligado && !SOM.ambiente) {
      const ctx = somPreparar(), tamanho = ctx.sampleRate * 6;
      const buffer = ctx.createBuffer(1, tamanho, ctx.sampleRate), dados = buffer.getChannelData(0);
      let anterior = 0;
      for (let i = 0; i < tamanho; i++) {
        anterior = (anterior + .02 * (Math.random() * 2 - 1)) / 1.02;
        dados[i] = anterior * 3.5;
      }
      // Fecha o ciclo sem salto na emenda do ruído.
      const salto = dados[tamanho - 1] - dados[0];
      for (let i = 0; i < tamanho; i++) dados[i] -= salto * i / (tamanho - 1);
      const fonte = ctx.createBufferSource(); fonte.buffer = buffer; fonte.loop = true;
      const grave = ctx.createBiquadFilter(); grave.type = 'lowpass'; grave.frequency.value = 220; grave.Q.value = .5;
      const corte = ctx.createBiquadFilter(); corte.type = 'highpass'; corte.frequency.value = 30; corte.Q.value = .5;
      const volume = ctx.createGain(); volume.gain.value = 0;
      fonte.connect(grave); grave.connect(corte); corte.connect(volume); volume.connect(ctx.destination);
      fonte.start(); SOM.ambiente = volume;
    }
    SOM.ambienteLigado = ligado;
    if (!SOM.ambiente) return;
    const ctx = SOM.ctx, ganho = SOM.ambiente.gain;
    if (ligado && ctx.state === 'suspended') ctx.resume();
    ganho.cancelScheduledValues(ctx.currentTime);
    ganho.setTargetAtTime(ligado ? .55 : 0, ctx.currentTime, window.KC_MICROFONE_ATIVO ? .015 : .3);
  }

  // posição estável: o mesmo neurônio fica no mesmo lugar a cada abertura
  const semente = s => { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return () => ((h = Math.imul(h ^ (h >>> 15), 2246822507) ^ Math.imul(h ^ (h >>> 13), 3266489909)) >>> 0) / 4294967296; };
  function esfera(i, n) { const y = 1 - (i + .5) / n * 2, r = Math.sqrt(1 - y * y), t = i * 2.39996; return [Math.cos(t) * r, y, Math.sin(t) * r]; }

  // lobo (área) › grupo (jeito de trabalhar / projetos / saber) › neurônio
  function montarPontos(d, perfil) {
    const areas = d.areas.filter(a => d.nos.some(n => n.area === a.id));
    const centro = { x: 0, y: 0, z: 0, r: 9, cor: '#B6F23A', tipo: 'voce', titulo: perfil?.nome || 'Você', desc: 'Você, no centro. Cada lobo em volta é uma área do que eu sei sobre você.' };
    const pts = [centro], hubs = {}, subs = {}, ligas = [];
    areas.forEach((a, i) => {
      const [x, y, z] = esfera(i, areas.length), R = 150;
      const n = d.nos.filter(o => o.area === a.id).length;
      const h = hubs[a.id] = { x: x * R, y: y * R * .8, z: z * R, r: 6 + Math.min(5, n / 10), cor: COR[a.id], tipo: 'area', area: a.id,
                               titulo: a.nome, desc: `${n} neurônio${n === 1 ? '' : 's'} nesta área.` };
      pts.push(h); ligas.push([0, pts.length - 1, 2]);
      const grupos = Object.keys(d.grupos).filter(g => d.nos.some(o => o.area === a.id && o.grupo === g));
      grupos.forEach((g, k) => {
        const ang = k / grupos.length * Math.PI * 2 + i, dist = grupos.length > 1 ? 30 : 0;
        const m = d.nos.filter(o => o.area === a.id && o.grupo === g).length;
        const sh = subs[a.id + g] = { x: h.x * 1.12 + Math.cos(ang) * dist, y: h.y * 1.12 + Math.sin(ang) * dist * .8, z: h.z * 1.12 + Math.sin(ang * 1.7) * dist * .5,
                                      r: 3.6 + Math.min(3, m / 12), cor: COR[a.id], tipo: 'grupo', area: a.id, grupo: g, titulo: d.grupos[g],
                                      desc: `${a.nome} › ${d.grupos[g]}: ${m} neurônio${m === 1 ? '' : 's'}.` };
        pts.push(sh); ligas.push([pts.indexOf(h), pts.length - 1, 2]);
      });
    });
    const base = pts.length;
    d.nos.forEach(n => {
      const h = subs[n.area + n.grupo] || hubs[n.area], rnd = semente(n.chave);
      const cont = d.nos.filter(o => o.area === n.area && o.grupo === n.grupo).length;
      const raio = 14 + Math.sqrt(cont) * 6 * Math.cbrt(rnd());
      const u = rnd() * 2 - 1, t = rnd() * Math.PI * 2, s = Math.sqrt(1 - u * u);
      pts.push({ x: h.x + Math.cos(t) * s * raio, y: h.y + u * raio, z: h.z + Math.sin(t) * s * raio, r: 1.8 + n.vida * 1.6,
                 cor: COR[n.area] || '#9AA', tipo: n.tipo, area: n.area, titulo: n.titulo, desc: n.desc, texto: n.texto, projeto: n.projeto, no: n });
      ligas.push([pts.indexOf(h), pts.length - 1, 3]);
    });
    d.ligas.forEach(([a, b, forte]) => ligas.push([base + a, base + b, forte]));
    pts.forEach((p, i) => { p.i = i; }); C.pts = pts; C.ligas = ligas; C.base = base;
    C.viz = pts.map(() => []);
    for (const [a, b, k, w] of ligas) { const p = k === 2 || k === 3 ? .35 : (w || .5); C.viz[a].push([b, p]); C.viz[b].push([a, p]); }
  }

  function projetar() {
    const w = C.cv.width, h = C.cv.height, dpr = devicePixelRatio || 1, cx = Math.cos(C.rx), sx = Math.sin(C.rx), cy = Math.cos(C.ry), sy = Math.sin(C.ry);
    const esc = Math.min(w, h) / 330 * C.zoom;
    const unica = C.foco || (C.areasVisiveis.size === 1 ? [...C.areasVisiveis][0] : null);
    const alvo = unica ? C.pts.find(p => p.tipo === 'area' && p.area === unica) : null;
    for (const p of C.pts) {
      const x = p.x - (alvo?.x || 0) / 2, y = p.y - (alvo?.y || 0) / 2, z = p.z - (alvo?.z || 0) / 2;
      const x1 = x * cy - z * sy, z1 = x * sy + z * cy, y1 = y * cx - z1 * sx, z2 = y * sx + z1 * cx;
      const f = 420 / (420 + z2);
      p.sx = w / 2 + x1 * f * esc; p.sy = h / 2 + y1 * f * esc; p.sz = z2; p.sr = Math.max(1, p.r * f * esc * (p.tipo === 'area' || p.tipo === 'voce' ? 1 : 1.1)) * dpr / dpr;
    }
  }
  const corresponde = n => (!C.ambito || (n.ambitos || ['revisar']).includes(C.ambito)) && (!C.finalidade || n.finalidade === C.finalidade) && (!C.agente || n.agente === C.agente);
  const visivel = p => p.tipo === 'voce' || ((!C.foco || p.area === C.foco) &&
    (p.no ? corresponde(p.no) : p.tipo === 'grupo' ? C.gruposVisiveis.has(p.area + ':' + p.grupo) : C.areasVisiveis.has(p.area)));
  const luz = p => C.luz ? (C.luz.get(p.i) || 0) : 0;
  const achado = p => luz(p) > .25;
  // acender: o neurônio puxa os ligados (1 e 2 passos), cada vez mais fraco — como uma lembrança puxando outra
  function espalhar(sementes) {
    const m = new Map(sementes);
    for (const decai of [.6, .3]) {
      for (const [i, v] of [...m]) for (const [j, w] of C.viz[i]) {
        if (!visivel(C.pts[j])) continue;
        const g = v * Math.min(1, w * 2) * decai; if (g > .15 && g > (m.get(j) || 0)) m.set(j, g);
      }
    }
    C.luz = m;
  }

  function desenhar(t) {
    const g = C.ctx, w = C.cv.width, h = C.cv.height;
    g.clearRect(0, 0, w, h);
    projetar();
    // ligações (de trás para a frente, as de trás mais apagadas)
    g.lineWidth = devicePixelRatio || 1;
    for (const [a, b, k] of C.ligas) {
      const p = C.pts[a], q = C.pts[b];
      if (!visivel(p) || !visivel(q)) continue;
      const prof = Math.max(.08, Math.min(1, .55 - (p.sz + q.sz) / 520));
      const ativo = C.luz ? luz(p) > .2 && luz(q) > .2 : C.sel && (C.sel === p || C.sel === q);
      g.globalAlpha = ativo ? Math.min(.9, .3 + Math.min(luz(p), luz(q))) : C.luz ? .04 * prof : (k === 2 ? .35 : k === 1 ? .32 : k === 3 ? .12 : .18) * prof;
      g.strokeStyle = ativo ? (C.luz ? p.cor : '#fff') : (k === 2 ? q.cor : p.cor);
      g.beginPath(); g.moveTo(p.sx, p.sy); g.lineTo(q.sx, q.sy); g.stroke();
    }
    // impulsos correndo nas ligações
    if (C.pulsos.length < 14 && Math.random() < .25) { let l = C.ligas[(Math.random() * C.ligas.length) | 0]; if (C.luz) for (let t = 0; t < 30 && !(luz(C.pts[l[0]]) > .2 && luz(C.pts[l[1]]) > .2); t++) l = C.ligas[(Math.random() * C.ligas.length) | 0]; if (l) C.pulsos.push({ l, t: 0, v: .012 + Math.random() * .02 }); }
    C.pulsos = C.pulsos.filter(u => (u.t += u.v) < 1);
    for (const u of C.pulsos) {
      const p = C.pts[u.l[0]], q = C.pts[u.l[1]]; if (!visivel(p) || !visivel(q)) continue;
      g.globalAlpha = Math.sin(u.t * Math.PI) * .9; g.fillStyle = q.cor;
      g.beginPath(); g.arc(p.sx + (q.sx - p.sx) * u.t, p.sy + (q.sy - p.sy) * u.t, 1.6 * (devicePixelRatio || 1), 0, 7); g.fill();
    }
    // neurônios, do fundo para a frente
    const ordem = C.pts.filter(visivel).sort((a, b) => b.sz - a.sz);
    for (const p of ordem) {
      const prof = Math.max(.25, Math.min(1, .75 - p.sz / 300)), dpr = devicePixelRatio || 1, r = p.sr * dpr;
      const marcado = p === C.sel || p === C.hover || achado(p);
      const lz = luz(p), vida = p.no ? .3 + .7 * p.no.vida : 1;
      g.globalAlpha = C.luz && p.no ? (lz > .08 ? Math.min(1, .35 + lz) : .12) : prof * vida;
      if (p.tipo === 'area' || p.tipo === 'voce' || p.tipo === 'grupo' || marcado) {
        g.globalAlpha *= .25; g.fillStyle = p.cor; g.beginPath(); g.arc(p.sx, p.sy, r * 2.4, 0, 7); g.fill();
        g.globalAlpha = Math.min(1, prof * 1.3);
      }
      g.fillStyle = p === C.sel || p === C.hover ? '#fff' : p.no && p.no.vida < .15 ? '#5A635E' : p.cor;
      g.beginPath(); g.arc(p.sx, p.sy, marcado ? r * (1.2 + lz) : r, 0, 7); g.fill();
      if (p.no && p.no.fonte === 'cérebro') { g.strokeStyle = '#fff'; g.lineWidth = dpr; g.beginPath(); g.arc(p.sx, p.sy, r + 2 * dpr, 0, 7); g.stroke(); }
      if (p.no && p.no.ultimo && Date.now() / 1000 - p.no.ultimo < 2 * 86400) {   // usado nos últimos 2 dias: anel pulsando
        const f = (t / 1200 + p.i * .37) % 1; g.globalAlpha = (1 - f) * .7; g.strokeStyle = p.cor; g.lineWidth = dpr;
        g.beginPath(); g.arc(p.sx, p.sy, r + f * 9 * dpr, 0, 7); g.stroke();
      }
      if (p.tipo === 'area' || p.tipo === 'voce' || (p.tipo === 'grupo' && (C.foco === p.area || C.zoom > 1.6))) {
        g.globalAlpha = Math.min(1, prof * (p.tipo === 'grupo' ? 1 : 1.4)); g.fillStyle = '#E8ECEA';
        g.font = `${p.tipo === 'voce' ? 600 : p.tipo === 'grupo' ? 400 : 500} ${(p.tipo === 'grupo' ? 9.5 : 11) * dpr}px system-ui, sans-serif`; g.textAlign = 'center';
        g.fillText(p.titulo, p.sx, p.sy - r - 5 * dpr);
      }
    }
    if (C.luz) {
      const dpr = devicePixelRatio || 1; g.font = `${10 * dpr}px system-ui, sans-serif`; g.textAlign = 'center';
      [...C.luz].filter(([i]) => C.pts[i].no).sort((a, b) => b[1] - a[1]).slice(0, 5).forEach(([i, v]) => {
        const p = C.pts[i]; g.globalAlpha = Math.min(1, .5 + v); g.fillStyle = '#E8ECEA';
        g.fillText(p.titulo.length > 26 ? p.titulo.slice(0, 25) + '…' : p.titulo, p.sx, p.sy + p.sr * dpr + 12 * dpr);
      });
    }
    // nome do neurônio sob o mouse
    const rot = C.hover && C.hover.no ? C.hover : null;
    if (rot) {
      const dpr = devicePixelRatio || 1; g.globalAlpha = 1; g.font = `${11 * dpr}px system-ui, sans-serif`;
      const tx = rot.titulo.length > 38 ? rot.titulo.slice(0, 37) + '…' : rot.titulo, lw = g.measureText(tx).width + 12 * dpr;
      const x = Math.min(w - lw - 4, Math.max(4, rot.sx - lw / 2)), y = Math.max(4, rot.sy - 26 * dpr);
      g.fillStyle = 'rgba(10,13,12,.9)'; g.fillRect(x, y, lw, 18 * dpr); g.fillStyle = '#E8ECEA'; g.textAlign = 'left'; g.fillText(tx, x + 6 * dpr, y + 13 * dpr);
    }
    g.globalAlpha = 1;
  }

  function quadro(t) {
    C.raf = 0;
    somAmbiente();
    if (!C.el || !C.el.isConnected || C.el.closest('[hidden]') || document.hidden) return;
    if (t - C.ultimo > 32) {   // ~30 qps basta
      if (C.auto && !C.arr) C.ry += .0035;
      C.ultimo = t; desenhar(t);
    }
    C.raf = requestAnimationFrame(quadro);
  }
  function tocar() { if (!C.raf) C.raf = requestAnimationFrame(quadro); }
  function medir() {
    const dpr = devicePixelRatio || 1, r = C.cv.getBoundingClientRect();
    C.cv.width = Math.max(10, r.width * dpr); C.cv.height = Math.max(10, r.height * dpr);
  }
  function perto(ev) {
    const r = C.cv.getBoundingClientRect(), dpr = devicePixelRatio || 1, x = (ev.clientX - r.left) * dpr, y = (ev.clientY - r.top) * dpr;
    let melhor = null, dmin = 14 * dpr;
    for (const p of C.pts) { if (!visivel(p)) continue; const d = Math.hypot(p.sx - x, p.sy - y) - p.sr * dpr; if (d < dmin) { dmin = d; melhor = p; } }
    return melhor;
  }
  function cartao(p) {
    const k = C.el.querySelector('.cer-cartao');
    if (!p) { k.hidden = true; return; }
    const area = C.d.areas.find(a => a.id === p.area);
    k.hidden = false;
    const n = p.no, dias = s => s ? Math.max(0, Math.round((Date.now() / 1000 - s) / 86400)) : null;
    const quando = s => { const x = dias(s); return x == null ? 'nunca' : x === 0 ? 'hoje' : x === 1 ? 'ontem' : `há ${x} dias`; };
    k.innerHTML = `<b style="color:${p.cor}">${esc(p.titulo)}</b>
      <small>${esc([n ? (C.d.tipos[p.tipo] || p.tipo) : null, area?.nome, n ? n.fonte : null, p.projeto].filter(Boolean).join(' · '))}</small>
      ${n ? `<small>Assunto: ${esc((n.ambitos || ['revisar']).map(a => C.d.ambitos?.[a] || a).join(' + '))} · Finalidade: ${esc(C.d.finalidades?.[n.finalidade] || n.finalidade || 'não registrada')}</small>
        <small>Registrado por: ${esc(n.agente || 'não registrado')} · Classificação ${esc(n.classificacao || 'não registrada')}</small>` : ''}
      ${n?.certeza?.startsWith('observação') ? `<small>${esc(n.certeza)}</small>` : ''}
      ${n && !n.pc ? `<div class="cer-vida"><i><b style="width:${Math.round(n.vida * 100)}%;background:${n.vida < .15 ? '#5A635E' : p.cor}"></b></i>
        <span>vida ${Math.round(n.vida * 100)}% · ${n.usos} uso${n.usos === 1 ? '' : 's'} · último ${quando(n.ultimo)} · nasceu ${quando(n.criado)}${n.atualizado ? ' · atualizado ' + quando(n.atualizado) : ''}</span></div>` : ''}
      <p>${esc(p.desc || '')}</p>${p.texto ? `<pre>${esc(p.texto)}</pre>` : ''}
      ${n?.pc ? `<div class="cer-pc"><small class="cer-pc-estado">Conferindo o mapa…</small><button data-c="pc-mapa">${n.pc.mapa ? 'Explorar o mapa do PC' : 'Ver esta pasta no mapa'}</button><small>Referência viva · as pastas seguem o índice. A organização é consultada separadamente.</small></div>` : ''}
      ${n && !n.pc ? `<div class="cer-acoes"><button data-c="descartar" title="Tirar do cérebro (vai para o arquivo, dá para voltar)">Descartar</button></div>` : ''}`;
    if (n?.pc) {
      const estado = k.querySelector('.cer-pc-estado');
      api().mapa_d_status().then(s => {
        if (!estado.isConnected) return;
        estado.textContent = `${(s.total || s.progresso || 0).toLocaleString('pt-BR')} itens no índice · ` +
          (s.parcial || !s.monitor_ativo || s.monitor !== 'windows' ? 'cobertura parcial ou atualização a conferir' : 'monitor ativo') +
          '. Referências às pastas principais; explore o mapa para ver todas.';
      }).catch(() => { if (estado.isConnected) estado.textContent = 'Mapa indisponível no momento. Tente novamente pelo mapa do PC.'; });
    }
  }
  async function pcAtualizar() {
    if (C.pcAtualizando || !C.el?.isConnected || C.el.closest('[hidden]') || document.hidden) return;
    if (C.foco !== 'pc' && C.ambito !== 'pc' && !C.sel?.no?.pc) return;
    C.pcAtualizando = true;
    const el = C.el, chave = C.sel?.no?.chave, nome = C.pts[0]?.titulo;
    try {
      const dados = await api().cerebro_ler();
      if (C.el !== el || !el.isConnected) return;
      C.d = dados; C.luz = null; C.hover = null; C.pulsos = [];
      montarPontos(dados, {nome}); legenda();
      C.sel = chave ? C.pts.find(p => p.no?.chave === chave) || null : null;
      cartao(C.sel);
    } finally { C.pcAtualizando = false; }
  }
  function legenda() {
    const nos = C.d.nos.filter(corresponde), cont = {};
    C.areasVisiveis = new Set(nos.map(n => n.area)); C.gruposVisiveis = new Set(nos.map(n => n.area + ':' + n.grupo));
    nos.forEach(n => cont[n.area] = (cont[n.area] || 0) + 1);
    const opcoes = (itens, atual) => Object.entries(itens || {}).map(([id, nome]) => `<option value="${esc(id)}" ${atual === id ? 'selected' : ''}>${esc(nome)}</option>`).join('');
    C.el.querySelector('.cer-areas').innerHTML = `<div class="cer-filtros"><label>Assunto <select data-cer-filtro="ambito"><option value="">Todos</option>${opcoes(C.d.ambitos, C.ambito)}</select></label>
      <label>Finalidade <select data-cer-filtro="finalidade"><option value="">Todas</option>${opcoes(C.d.finalidades, C.finalidade)}</select></label>
      <label>Registrado por <select data-cer-filtro="agente"><option value="">Todos</option>${opcoes({pailer:'Pailer',claude:'Claude',codex:'Codex',kani:'Kani local',pickle:'Big Pickle','não registrado':'Não registrado'}, C.agente)}</select></label>
      <small>${nos.length} de ${C.d.nos.length} neurônios</small></div>` + C.d.areas.filter(a => cont[a.id]).map(a =>
      `<button data-area="${a.id}" class="${C.foco === a.id ? 'on' : ''}"><i style="background:${COR[a.id]}"></i>${esc(a.nome)} <small>${cont[a.id]}</small></button>`).join('');
  }

  // evolução: números de hoje, gráfico dos dias e o que o Claude fez no cérebro
  async function evolucao() {
    const r = C.d.resumo, h = C.d.historico || [];
    const ev = C.el.querySelector('.cer-evo');
    ev.innerHTML = `<b class="tit">Evolução</b>
      <div class="cer-num"><span><b>${r.neuronios}</b>neurônios</span><span><b>${r.ligacoes}</b>ligações</span>
        <span><b>+${r.novos_semana}</b>na semana</span><span><b>${r.usados_semana}</b>usados</span>
        <span title="sem uso há muito tempo"><b>${r.apagando}</b>apagando</span><span title="escritos pelo próprio cérebro"><b>${r.proprios}</b>próprios</span></div>
      <canvas class="cer-graf" title="neurônios por dia"></canvas>
      <small class="cer-fontes">${Object.entries(r.fontes).map(([f, n]) => `${esc(f)} ${n}`).join(' · ')}${r.descartados ? ` · ${r.descartados} arquivados` : ''}</small>`;
    const cv = ev.querySelector('.cer-graf'), dpr = devicePixelRatio || 1;
    requestAnimationFrame(() => {
      const w = cv.clientWidth * dpr, hh = cv.clientHeight * dpr; cv.width = w; cv.height = hh;
      const g = cv.getContext('2d'), v = h.map(x => x.neuronios);
      if (v.length < 2) { g.fillStyle = '#8A958F'; g.font = `${10.5 * dpr}px system-ui`; g.fillText('o gráfico ganha um ponto por dia', 4 * dpr, hh / 2 + 4 * dpr); return; }
      const mn = Math.min(...v) * .95, mx = Math.max(...v) * 1.02 || 1, X = i => i / (v.length - 1) * (w - 4 * dpr) + 2 * dpr, Y = x => hh - 3 * dpr - (x - mn) / (mx - mn || 1) * (hh - 8 * dpr);
      g.beginPath(); v.forEach((x, i) => i ? g.lineTo(X(i), Y(x)) : g.moveTo(X(i), Y(x)));
      g.strokeStyle = '#B6F23A'; g.lineWidth = 1.5 * dpr; g.stroke();
      g.lineTo(X(v.length - 1), hh); g.lineTo(X(0), hh); g.closePath(); g.globalAlpha = .12; g.fillStyle = '#B6F23A'; g.fill();
    });
    try {
      const p = await api().cerebro_painel(), rv = p.revisar;
      const ICO = { consultou: '🔎', guardou: '✚', atualizou: '✎', 'reforçou': '▲', enfraqueceu: '▼', descartou: '✕', faxina: '🧹', restaurou: '↺' };
      const fx = p.faxina || {}, dfx = fx.quando ? Math.round((Date.now() / 1000 - fx.quando) / 86400) : null;
      const pend = [rv.juntar.length && rv.juntar.length + ' para juntar', rv.caminhos_quebrados.length && rv.caminhos_quebrados.length + ' com caminho quebrado',
                    rv.apagando.length && rv.apagando.length + ' apagando', rv.projetos_parados.length && rv.projetos_parados.length + ' projetos parados'].filter(Boolean);
      C.el.querySelector('.cer-ativ').innerHTML = `<b class="tit">Atividade do cérebro</b>
        ${p.atividade.length ? p.atividade.slice(0, 8).map(a => `<div class="cer-at"><span>${ICO[a.acao] || '•'}</span><span>${esc(a.acao)}: ${esc(a.texto)}</span>
          <small>${new Date(a.t * 1000).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}</small></div>`).join('') : '<div class="cer-at"><span></span><span>Nada ainda: começa quando eu consultar ou guardar.</span></div>'}
        <div class="cer-pend">${pend.length ? 'Para cuidar: ' + pend.join(' · ') : 'Nada para cuidar agora.'}</div>
        <div class="cer-pend" title="Mesma busca para Kani, Claude, Codex e qualquer IA (MCP, HTTP 127.0.0.1:47620 e Python)">🧠 Motor universal: ${p.motor && p.motor.motor === 'v2'
          ? `${p.motor.trechos} trechos · ${p.motor.semantica ? 'palavra + sentido' : 'só palavra (sentido preparando)'}${p.motor.propostas ? ` · ${p.motor.propostas} proposta(s) na fila` : ''}`
          : 'busca antiga (v1)'}</div>
        <div class="cer-fax"><span>🧹 Faxina ${dfx == null ? 'ainda não rodou' : dfx === 0 ? 'hoje' : dfx === 1 ? 'ontem' : `há ${dfx} dias`}${fx.quando
          ? `: ${fx.analisados} julgados, ${fx.descartados.length} descartados` : ''}${p.pendencias ? ` · ${p.pendencias} memória(s) para o Claude corrigir` : ''}</span>
          <button data-c="faxina" title="A Kani julga o que está velho e descarta o obsoleto (roda sozinha 1× por dia)">Faxina agora</button></div>
        ${(fx.descartados || []).slice(0, 4).map(x => `<div class="cer-at"><span>✕</span><span>${esc(x.titulo)} — ${esc(x.motivo)}</span><small></small></div>`).join('')}`;
    } catch (e) { console.warn('cérebro painel:', e); }
  }
  async function faxinaAgora(bt) {
    bt.disabled = true; bt.textContent = 'A Kani está julgando…';
    try {
      const r = await api().cerebro_faxina();
      bolha('sis', `Faxina do cérebro: ${r.analisados} julgados, ${r.descartados.length} descartados${r.descartados.length ? ' (' + r.descartados.map(x => esc(x.titulo)).join(', ') + ')' : ''}.`);
      C.d = await api().cerebro_ler(); montarPontos(C.d, { nome: C.pts[0].titulo }); legenda();
    } catch (e) { bolha('erro', 'Faxina: ' + esc(e.message || e)); }
    evolucao();
  }
  async function descartar(p) {
    const motivo = await perguntar(`Tirar "${p.titulo}" do cérebro? Fica no arquivo e dá para voltar. Motivo:`, '', 'Descartar');
    if (motivo == null) return;
    const r = await api().cerebro_descartar(p.no.chave, motivo);
    if (r.aviso) bolha('sis', esc(r.aviso));
    C.d = await api().cerebro_ler(); C.sel = null; C.luz = null; cartao(null); montarPontos(C.d, { nome: C.pts[0].titulo }); legenda(); evolucao();
  }

  async function montar(el, perfil) {
    C.el = el;
    el.innerHTML = `<div class="cer-topo"><input class="cer-busca" placeholder="Buscar no cérebro…" spellcheck="false">
        <button class="cer-bt" data-c="som" title="Som dos neurônios (ligar/desligar)">${SOM.ligado ? '♪' : '♪̸'}</button><button class="cer-bt" data-c="girar" title="Parar/girar">⟳</button><button class="cer-bt" data-c="tela" title="Ver grande">⤢</button></div>
      <div class="cer-palco"><canvas></canvas><div class="cer-carregando">Ligando os neurônios…</div></div>
      <div class="cer-areas"></div><div class="cer-cartao" hidden></div>
      <div class="cer-evo"></div><div class="cer-ativ"></div>`;
    C.cv = el.querySelector('canvas'); C.ctx = C.cv.getContext('2d');
    try { C.d = await api().cerebro_ler(); } catch (e) { el.querySelector('.cer-carregando').textContent = 'Não deu para ler: ' + (e.message || e); return; }
    el.querySelector('.cer-carregando').remove();
    montarPontos(C.d, perfil); legenda(); evolucao(); medir(); tocar();
    clearInterval(C.pcTimer);
    C.pcTimer = setInterval(() => pcAtualizar().catch(() => {}), 20000);
    el.querySelector('.cer-sub')?.remove();
    const cv = C.cv;
    cv.addEventListener('pointerdown', ev => { C.arr = { x: ev.clientX, y: ev.clientY, rx: C.rx, ry: C.ry, mov: 0 }; cv.setPointerCapture(ev.pointerId); });
    cv.addEventListener('pointermove', ev => {
      if (C.arr) {
        const dx = ev.clientX - C.arr.x, dy = ev.clientY - C.arr.y; C.arr.mov = Math.max(C.arr.mov, Math.abs(dx) + Math.abs(dy));
        C.ry = C.arr.ry + dx * .008; C.rx = Math.max(-1.4, Math.min(1.4, C.arr.rx + dy * .008));
      } else { const h = perto(ev); if (h && h !== C.hover) tocarSom(h, false); C.hover = h; cv.style.cursor = C.hover ? 'pointer' : 'grab'; }
    });
    cv.addEventListener('pointerup', ev => {
      const clique = C.arr && C.arr.mov < 4; C.arr = null;
      if (clique) { C.sel = perto(ev); SOM.ultimo = 0; tocarSom(C.sel, true); cartao(C.sel); if (C.sel && C.sel.no) espalhar([[C.pts.indexOf(C.sel), 1]]); else if (!C.sel || C.sel.tipo === 'voce') C.luz = null; if (C.sel?.tipo === 'area') { C.foco = C.foco === C.sel.area ? null : C.sel.area; legenda(); } }
    });
    cv.addEventListener('pointerleave', () => { C.hover = null; });
    cv.addEventListener('wheel', ev => { ev.preventDefault(); C.zoom = Math.max(.5, Math.min(4, C.zoom * (ev.deltaY < 0 ? 1.12 : .89))); }, { passive: false });
    let espera = 0;
    el.querySelector('.cer-busca').addEventListener('input', e => {
      clearTimeout(espera); const q = e.target.value.trim();
      if (!q) { C.luz = null; return; }
      espera = setTimeout(async () => {
        const ambito = C.ambito;
        const r = await api().cerebro_consultar(q, ambito || null); if (e.target.value.trim() !== q || ambito !== C.ambito) return;
        if (!r.length) { C.luz = new Map(); return; }
        const filtrados = r.filter(x => C.d.nos[x.id] && corresponde(C.d.nos[x.id]));
        if (!filtrados.length) { C.luz = new Map(); return; }
        const max = filtrados[0].forca || 1; espalhar(filtrados.map(x => [C.base + x.id, x.forca / max]));
        C.sel = C.pts[C.base + filtrados[0].id]; cartao(C.sel);
      }, 300);
    });
    el.addEventListener('change', e => {
      const filtro = e.target.dataset.cerFiltro;
      if (!['ambito', 'finalidade', 'agente'].includes(filtro)) return;
      C[filtro] = e.target.value; C.foco = null; C.sel = null; C.hover = null; C.luz = null; C.pulsos = [];
      cartao(null); legenda();
      if (C.ambito === 'pc') pcAtualizar().catch(() => {});
    });
    el.addEventListener('click', e => {
      const a = e.target.closest('[data-area]'); if (a) { C.foco = C.foco === a.dataset.area ? null : a.dataset.area; legenda(); return; }
      const c = e.target.closest('[data-c]')?.dataset.c;
      if (c === 'pc-mapa' && C.sel?.no?.pc) {
        if (window.KCMapaD) window.KCMapaD.abrir(C.sel.no.pc.pasta);
        else bolha('erro', 'O mapa do PC ainda não está disponível nesta tela.');
      }
      if (c === 'girar') C.auto = !C.auto;
      if (c === 'som') { SOM.ligado = !SOM.ligado; localStorage.setItem('cerebro-som', SOM.ligado ? '1' : '0'); e.target.closest('button').textContent = SOM.ligado ? '♪' : '♪̸'; if (SOM.ligado) { SOM.ultimo = 0; tocarSom(C.pts[1], true); } somAmbiente(); }
      if (c === 'descartar' && C.sel?.no) descartar(C.sel);
      if (c === 'faxina') faxinaAgora(e.target.closest('button'));
      if (c === 'tela') { el.classList.toggle('grande'); somAmbiente(); requestAnimationFrame(medir); }
    });
    el.addEventListener('keydown', e => { if (e.key === 'Escape' && el.classList.contains('grande')) { e.stopPropagation(); el.classList.remove('grande'); somAmbiente(); requestAnimationFrame(medir); } });
    new ResizeObserver(() => medir()).observe(el.querySelector('.cer-palco'));
  }
  window.Cerebro = { montar, tocar };
  window.addEventListener('kc-microfone', () => {
    somAmbiente();
    if (!SOM.notas) return;
    const t = SOM.ctx.currentTime, ganho = SOM.notas.gain;
    ganho.cancelScheduledValues(t);
    ganho.setTargetAtTime(window.KC_MICROFONE_ATIVO ? 0 : .9, t, .015);
  });
  document.addEventListener('visibilitychange', () => { somAmbiente(); if (!document.hidden && C.el) tocar(); });
})();
