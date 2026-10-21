// KaniCode no celular (movel.py): imita o window.pywebview.api da janela do PC por HTTP e recebe os eventos por SSE.
// Carregado ANTES do script da janela; só existe na página servida pelo movel.py (na janela do PC não entra).
(() => {
  window.KC_MOVEL = true;
  window.KC_DE = 'movel-' + Math.random().toString(36).slice(2, 8);
  document.documentElement.classList.add('movel');

  async function chamar(nome, args) {
    const r = await fetch('/api/' + nome, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-KC-De': KC_DE },
                                           body: JSON.stringify(args) });
    if (r.status === 403) { location.reload(); throw new Error('sem chave'); }
    const j = await r.json();
    if (j.erro) throw new Error(j.erro);
    return j.r;
  }
  const base = new Proxy({}, { get: (_, nome) => (...args) => chamar(nome, args) });

  // historico: os cartões ainda sem resposta voltam VIVOS (no PC eles ficariam como "recusado" ao recarregar)
  const api = new Proxy({}, { get: (_, nome) => nome !== 'historico' ? base[nome] : async () => {
    const [h, pend] = await Promise.all([base.historico(), base.pendentes().catch(() => [])]);
    const ids = new Set((pend || []).map(e => e.id));
    if (ids.size) setTimeout(() => pend.forEach(ev => window.kcEv && kcEv(ev)), 0);
    return (h || []).filter(e => !((e.t === 'permissao' || e.t === 'pergunta') && ids.has(e.id)));
  } });
  window.pywebview = { api };

  // eventos ao vivo; caiu (celular dormiu, trocou de rede): reconecta e recarrega a conversa do arquivo
  let fonte, caiu = false;
  function ligar() {
    fonte = new EventSource('/eventos');
    fonte.onopen = () => {
      document.documentElement.classList.remove('sem-pc');
      if (caiu && typeof carregar === 'function') carregar();
      caiu = false;
    };
    fonte.onmessage = m => { try { window.kcEv && kcEv(JSON.parse(m.data)); } catch (e) { console.error(e); } };
    fonte.onerror = () => { caiu = true; document.documentElement.classList.add('sem-pc'); };
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && fonte && fonte.readyState === 2) { fonte.close(); ligar(); }
  });
  // ── voz no celular: 🎤 grava aqui e o PC transcreve (Parakeet); a resposta volta falada (Kokoro no PC, toca aqui) ──
  const V = { gravando: null, ler: false, conversa: localStorage.getItem('kc-conversa') === '1', buf: '', codigo: false,
              fila: [], tocando: false, fimResposta: false, audio: new Audio() };
  V.audio.setAttribute('playsinline', '');
  function micVisual(on) { document.getElementById('mic').classList.toggle('on', on); }
  async function micLigar() {
    if (V.gravando) return micParar();
    pararFala();
    let fluxo;
    try { fluxo = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
    catch (e) { bolha('erro', 'Microfone: o celular não deixou usar (' + (e.message || e) + ').'); return; }
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const fonte = ctx.createMediaStreamSource(fluxo), proc = ctx.createScriptProcessor(4096, 1, 1);
    const g = { ctx, fluxo, fonte, proc, partes: [], sr: ctx.sampleRate, inicio: Date.now(), falou: 0, silencio: 0 };
    proc.onaudioprocess = e => {
      if (V.gravando !== g) return;
      const x = e.inputBuffer.getChannelData(0);
      g.partes.push(new Float32Array(x));
      let s = 0; for (let i = 0; i < x.length; i += 4) s += x[i] * x[i];
      const alto = Math.sqrt(s / (x.length / 4)) > 0.02, dt = x.length / g.sr;
      if (alto) { g.falou += dt; g.silencio = 0; } else g.silencio += dt;
      // para sozinho: 1,4 s de silêncio depois de falar; 8 s sem falar nada; 60 s no máximo
      if ((g.falou > 0.3 && g.silencio > 1.4) || (!g.falou && Date.now() - g.inicio > 8000) || Date.now() - g.inicio > 60000) micParar();
    };
    fonte.connect(proc); proc.connect(ctx.destination);
    V.gravando = g; micVisual(true); vozEv({ fase: 'ouvindo' });
    if (navigator.vibrate) navigator.vibrate(30);
  }
  async function micParar() {
    const g = V.gravando; if (!g) return;
    V.gravando = null; micVisual(false);
    g.proc.disconnect(); g.fonte.disconnect(); g.fluxo.getTracks().forEach(t => t.stop()); g.ctx.close();
    if (navigator.vibrate) navigator.vibrate([20, 40, 20]);
    if (g.falou < 0.3) { atividade('Pronto'); return; }
    // 16 kHz, 16 bits
    const total = g.partes.reduce((n, p) => n + p.length, 0), passo = g.sr / 16000, n = Math.floor(total / passo);
    const tudo = new Float32Array(total); let o = 0; for (const p of g.partes) { tudo.set(p, o); o += p.length; }
    const pcm = new Int16Array(n);
    for (let i = 0; i < n; i++) pcm[i] = Math.max(-1, Math.min(1, tudo[Math.floor(i * passo)])) * 32767;
    vozEv({ fase: 'transcrevendo' });
    try {
      const r = await (await fetch('/voz/ouvir', { method: 'POST', body: pcm.buffer })).json();
      if (r.erro) throw new Error(r.erro);
      if (!r.texto) { atividade('Não entendi; toque no 🎤 e fale de novo'); return; }
      V.ler = true;   // pediu por voz: a resposta volta falada
      vozEv({ fase: 'texto', texto: r.texto });
    } catch (e) { bolha('erro', 'Transcrever: ' + (e.message || e)); atividade('Pronto'); }
  }
  // leitura: frase a frase enquanto a resposta chega (blocos de código não são lidos)
  function falarPedaco(d) {
    V.buf += d;
    for (;;) {
      if (V.codigo) { const i = V.buf.indexOf('```'); if (i < 0) return; V.buf = V.buf.slice(i + 3); V.codigo = false; continue; }
      const i = V.buf.indexOf('```'), m = V.buf.match(/^([\s\S]*?[.!?…:;])(\s+)|^([^\n]*)\n/);
      if (i >= 0 && (!m || i < m[0].length)) { falarFrase(V.buf.slice(0, i)); V.buf = V.buf.slice(i + 3); V.codigo = true; continue; }
      if (!m) return;
      falarFrase(m[1] || m[3] || ''); V.buf = V.buf.slice(m[0].length);
    }
  }
  function falarFrase(f) {
    if ((f || '').replace(/\W/g, '').length < 2) return;
    V.fila.push(fetch('/voz/falar', { method: 'POST', body: JSON.stringify({ texto: f }) })
      .then(r => r.status === 200 ? r.blob() : null).catch(() => null));
    if (!V.tocando) tocar();
  }
  async function tocar() {
    V.tocando = true;
    while (V.fila.length) {
      const blob = await V.fila.shift();
      if (!blob || !V.tocando) continue;
      const url = URL.createObjectURL(blob);
      V.audio.src = url;
      try {
        await V.audio.play();
        await new Promise(r => { V.audio.onended = V.audio.onpause = r; });
      } catch (e) { /* bloqueado: segue */ }
      URL.revokeObjectURL(url);
    }
    V.tocando = false;
    if (V.fimResposta) { V.fimResposta = false; depoisDeFalar(); }
  }
  function pararFala() { V.fila = []; V.buf = ''; V.codigo = false; V.fimResposta = false; try { V.audio.pause(); } catch (e) {} }
  function depoisDeFalar() {
    // modo conversa: terminou de falar → já ouve o próximo pedido (só com a tela aberta: o celular não libera o microfone em segundo plano)
    if (V.conversa && document.visibilityState === 'visible' && !V.gravando) micLigar();
  }
  function conversaBotao() {
    const b = document.getElementById('voz');
    b.classList.toggle('on', V.conversa);
    b.title = V.conversa ? 'Modo conversa ligado: leio as respostas em voz alta e já ouço o próximo pedido' : 'Modo conversa';
  }
  if ('mediaSession' in navigator) navigator.mediaSession.metadata = new MediaMetadata({ title: 'KaniCode', artist: 'Claude',
    artwork: [{ src: '/icone-512.png', sizes: '512x512', type: 'image/png' }] });

  window.addEventListener('DOMContentLoaded', () => {
    ligar();
    // 🎤 e 🎙 do celular no lugar dos do PC (que usam o microfone do PC); 👤 abre as contas
    document.addEventListener('click', e => {
      const b = e.target.closest('#mic, #voz, #contas-bt'); if (!b) return;
      e.preventDefault(); e.stopImmediatePropagation();
      if (!V.tocando) { V.audio.play().catch(() => {}); V.audio.pause(); }   // libera o som neste toque (o celular exige um toque antes)
      if (b.id === 'mic') micLigar();
      else if (b.id === 'voz') {
        V.conversa = !V.conversa; localStorage.setItem('kc-conversa', V.conversa ? '1' : '0'); conversaBotao();
        bolha('sis', V.conversa ? '🎙 Modo conversa: leio as respostas em voz alta e depois já ouço você.' : 'Modo conversa desligado.');
        if (V.conversa && !K.ocupada) micLigar(); else if (!V.conversa) pararFala();
      } else contasAbrir();
    }, true);
    const voz = document.getElementById('voz'); conversaBotao();
    const ct = document.createElement('button'); ct.className = 'bt'; ct.id = 'contas-bt'; ct.title = 'Contas do Claude: trocar'; ct.textContent = '👤';
    voz.after(ct);
    // eventos da conversa → leitura em voz alta
    const ev0 = window.kcEv;
    window.kcEv = ev => {
      if (ev.t === 'inicio' || ev.t === 'texto_novo') { V.buf = ''; V.codigo = false; }
      else if (ev.t === 'texto' && (V.ler || V.conversa)) falarPedaco(ev.d || '');
      else if ((ev.t === 'permissao' || ev.t === 'pergunta') && (V.ler || V.conversa)) falarFrase('Preciso da sua decisão na tela.');
      else if (ev.t === 'fim' || ev.t === 'saiu') {
        if (V.ler || V.conversa) { if (!V.codigo) falarFrase(V.buf); V.buf = ''; V.fimResposta = true; if (!V.tocando) tocar(); }
        V.ler = false;
      }
      ev0(ev);
    };
    // Enter no celular = nova linha (o teclado não tem Shift); envia pelo botão
    const t = document.getElementById('texto');
    t.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) e.stopImmediatePropagation(); }, true);
    t.placeholder = 'Fale com o Claude…';
    setTimeout(() => window.dispatchEvent(new Event('pywebviewready')), 0);
  });
})();
