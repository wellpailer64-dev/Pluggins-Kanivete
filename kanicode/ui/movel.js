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
    fonte = new EventSource('/eventos?de=' + KC_DE);
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
  function micVisual(on) { document.getElementById('mic').classList.toggle('on', on); if (window.KCApp) KCApp.estado(on ? 'ouvindo' : 'parado'); }
  // app do celular: selo de quem responde, rosto da atividade e carinha do fim (APK antigo não tem: ignora)
  function appBola(f, v) { try { if (window.KCApp && typeof KCApp[f] === 'function') KCApp[f](v); } catch (e) {} }
  const ATIV = n => /^(Read|WebFetch|kani_(ler|demandas|git))/.test(n) ? 'lendo'
    : /^(Grep|Glob|WebSearch|ToolSearch|kani_(listar|procurar|buscar|espaco|ver|navegar))/.test(n) ? 'procurando'
    : n ? 'digitando' : '';
  function quemVigiar() {   // o seletor de modelo da janela (quemDefinir) troca o nome no botão
    const s = document.querySelector('#quem-bt span'); if (!s) return;
    const mandar = () => appBola('quem', ({ Kani: 'kani', Codex: 'codex', 'Big Pickle': 'pickle' })[s.textContent.trim()] || 'claude');
    new MutationObserver(mandar).observe(s, { childList: true, characterData: true, subtree: true }); mandar();
  }
  // app do celular (APK com a bolinha): mede o volume da voz que está tocando para a bolinha pulsar junto
  function bolinhaMedir() {
    if (!window.KCApp || V.medidor) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)(), an = ctx.createAnalyser();
      ctx.createMediaElementSource(V.audio).connect(an); an.connect(ctx.destination); an.fftSize = 512;
      const x = new Float32Array(an.fftSize); let falando = false;
      V.medidor = setInterval(() => {
        if (ctx.state === 'suspended') ctx.resume();
        an.getFloatTimeDomainData(x); let s = 0; for (let i = 0; i < x.length; i++) s += x[i] * x[i];
        const r = Math.sqrt(s / x.length);
        if (r > 0.015) { if (!falando) { falando = true; KCApp.estado('falando'); } KCApp.nivel(Math.min(1, r * 6)); }
        else if (falando) { falando = false; if (!V.gravando) KCApp.estado('parado'); }
      }, 100);
    } catch (e) { console.warn('medidor', e); }
  }
  async function micLigar(auto) {
    if (V.gravando) return micParar();
    pararFala();
    let fluxo;
    try { fluxo = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
    catch (e) { bolha('erro', 'Microfone: o celular não deixou usar (' + (e.message || e) + ').'); return; }
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const fonte = ctx.createMediaStreamSource(fluxo), proc = ctx.createScriptProcessor(4096, 1, 1);
    const g = { auto: auto === true, ctx, fluxo, fonte, proc, partes: [], sr: ctx.sampleRate, inicio: Date.now(), falou: 0, silencio: 0 };
    proc.onaudioprocess = e => {
      if (V.gravando !== g) return;
      const x = e.inputBuffer.getChannelData(0);
      g.partes.push(new Float32Array(x));
      let s = 0; for (let i = 0; i < x.length; i += 4) s += x[i] * x[i];
      const alto = Math.sqrt(s / (x.length / 4)) > 0.02, dt = x.length / g.sr;
      if (alto) { g.falou += dt; g.silencio = 0; } else g.silencio += dt;
      // para sozinho: 1,4 s de silêncio depois de falar; sem falar nada: 3 s quando reabriu sozinho, 8 s no toque; 60 s no máximo
      if ((g.falou > 0.3 && g.silencio > 1.4) || (!g.falou && Date.now() - g.inicio > (g.auto ? 3000 : 8000)) || Date.now() - g.inicio > 60000) micParar();
    };
    fonte.connect(proc); proc.connect(ctx.destination);
    V.gravando = g; micVisual(true); vozEv({ fase: 'ouvindo' });
    if (navigator.vibrate) navigator.vibrate(30);
  }
  async function micParar() {
    const g = V.gravando; if (!g) return;
    V.gravando = null; micVisual(false);
    setTimeout(fundoLigar, 300);   // o silêncio volta depois do microfone (com a tela aberta ele não atrapalha)
    g.proc.disconnect(); g.fonte.disconnect(); g.fluxo.getTracks().forEach(t => t.stop()); g.ctx.close();
    if (navigator.vibrate) navigator.vibrate([20, 40, 20]);
    if (g.falou < 0.3) { atividade('Pronto'); return; }
    // 16 kHz, 16 bits
    const total = g.partes.reduce((n, p) => n + p.length, 0), passo = g.sr / 16000, n = Math.floor(total / passo);
    const tudo = new Float32Array(total); let o = 0; for (const p of g.partes) { tudo.set(p, o); o += p.length; }
    const pcm = new Int16Array(n);
    for (let i = 0; i < n; i++) pcm[i] = Math.max(-1, Math.min(1, tudo[Math.floor(i * passo)])) * 32767;
    vozEv({ fase: 'transcrevendo' }); if (window.KCApp) KCApp.estado('pensando');
    try {
      const r = await (await fetch('/voz/ouvir', { method: 'POST', body: pcm.buffer })).json();
      if (r.erro) throw new Error(r.erro);
      if (window.KCApp) KCApp.estado('parado');
      if (!r.texto) { atividade('Não entendi; toque no 🎤 e fale de novo'); return; }
      V.ler = true; V.porVoz = true;   // pediu por voz: a resposta volta falada (e no app, depois, ouve de novo)
      fundoLigar();
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
    if (V.fundo) return;   // a rádio do PC já está lendo
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
      bolinhaMedir();
      V.audio.src = url;
      try {
        await V.audio.play();
        await new Promise(r => { V.audio.onended = V.audio.onpause = r; });
      } catch (e) { /* bloqueado: segue */ }
      URL.revokeObjectURL(url);
    }
    V.tocando = false;
    if (V.fimResposta) { V.fimResposta = false; depoisDeFalar(); }
    fundoLigar();
  }
  // rádio: com o modo conversa (ou um pedido por voz) o player toca /voz/radio, um fluxo contínuo que vem do PC; quem lê
  // a resposta é o PC (radio.py). Rádio o celular deixa tocando com o app minimizado ou a tela apagada (a página congela,
  // a rádio não). Fica ligada até desligar o 🎙 ou pausar na tela de bloqueio.
  V.fundo = false;
  function fundoLigar() {
    if (window.KCApp) return;   // no app do celular a página não congela: a voz vem direto, frase a frase (sem o atraso da rádio)
    if (!(V.conversa || V.ler) || V.gravando) return;
    if (V.fundo && !V.audio.paused) return;
    V.fila = []; V.fundo = true; V.audio.onended = V.audio.onpause = null; V.audio.loop = false;
    V.audio.src = '/voz/radio?t=' + Date.now();
    V.audio.play().catch(() => { V.fundo = false; });
    if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'playing';
    // ao vivo: o player junta segundos de folga antes de tocar; se ficou mais de 1 s atrás do que já chegou, pula para perto do fim
    V.audio.ontimeupdate = () => {
      const b = V.audio.buffered; if (!V.fundo || !b.length) return;
      const fim = b.end(b.length - 1);
      if (fim - V.audio.currentTime > 1) V.audio.currentTime = fim - 0.25;
    };
  }
  function fundoDesligar() {
    if (!V.fundo) return;
    V.fundo = false;
    try { V.audio.pause(); V.audio.removeAttribute('src'); V.audio.load(); } catch (e) {}
  }
  function pararFala() { V.fila = []; V.buf = ''; V.codigo = false; V.fimResposta = false; try { V.audio.pause(); } catch (e) {} }
  function depoisDeFalar() {
    // modo conversa: terminou de falar → já ouve o próximo pedido (só com a tela aberta: o celular não libera o microfone em segundo plano)
    // no app (KCApp) o microfone segue com a tela apagada e o pedido feito pela bolinha também continua a conversa
    const seguir = V.conversa || (window.KCApp && V.porVoz);
    V.porVoz = false;
    if (seguir && (document.visibilityState === 'visible' || window.KCApp) && !V.gravando) micLigar(true);
  }
  function conversaBotao() {
    const b = document.getElementById('voz');
    b.classList.toggle('on', V.conversa);
    b.title = V.conversa ? 'Modo conversa ligado: leio as respostas em voz alta e já ouço o próximo pedido' : 'Modo conversa';
  }
  // modo conversa já ligado ao abrir: o 1º toque na tela libera o som de fundo (o celular exige um toque)
  document.addEventListener('pointerdown', () => { if (V.conversa) fundoLigar(); }, { once: true, capture: true });
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({ title: 'KaniCode', artist: 'Claude',
      artwork: [{ src: '/icone-512.png', sizes: '512x512', type: 'image/png' }] });
    // pausar na tela de bloqueio = desligar o modo conversa (e o som de fundo); tocar = ligar de novo
    navigator.mediaSession.setActionHandler('pause', () => {
      V.conversa = false; V.ler = false; localStorage.setItem('kc-conversa', '0'); conversaBotao(); pararFala(); fundoDesligar();
      navigator.mediaSession.playbackState = 'paused';
    });
    navigator.mediaSession.setActionHandler('play', () => { V.conversa = true; localStorage.setItem('kc-conversa', '1'); conversaBotao(); fundoLigar(); });
  }

  // ── aviso no celular (aviso_movel.py): 🔔 liga/desliga; chega quando termino ou preciso de você e o KaniCode não está à vista ──
  const post = (u, d) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d || {}) }).then(r => r.json());
  const b64 = s => { const p = (s + '='.repeat((4 - s.length % 4) % 4)).replace(/-/g, '+').replace(/_/g, '/');
                     return Uint8Array.from(atob(p), c => c.charCodeAt(0)); };
  let swReg = null;
  async function avisoBotao() {
    const b = document.getElementById('aviso-bt'); if (!b) return;
    const sub = swReg && await swReg.pushManager.getSubscription();
    const on = !!sub && Notification.permission === 'granted';
    b.classList.toggle('on', on); b.textContent = on ? '🔔' : '🔕';
    b.title = on ? 'Avisos ligados: chega notificação quando eu terminar ou precisar de você' : 'Ligar avisos no celular';
  }
  async function avisoAlternar() {
    if (!swReg || !('PushManager' in window)) { bolha('erro', 'Este navegador não aceita avisos.'); return; }
    const sub = await swReg.pushManager.getSubscription();
    if (sub && Notification.permission === 'granted') {
      await post('/push/sair', { endpoint: sub.endpoint }); await sub.unsubscribe();
      bolha('sis', '🔕 Avisos desligados neste celular.');
    } else {
      if (await Notification.requestPermission() !== 'granted') { bolha('erro', 'Avisos bloqueados: libere as notificações do KaniCode nas configurações do Android.'); return; }
      const chave = (await post('/push/chave')).r;
      const nova = sub || await swReg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(chave) });
      await post('/push/assinar', { sub: nova.toJSON() });
      await post('/push/teste');
      bolha('sis', '🔔 Avisos ligados. Mandei um de teste agora. Daqui em diante: quando você pedir algo pelo celular e sair do KaniCode, eu aviso ao terminar ou se precisar de você.');
    }
    avisoBotao();
  }
  const visto = () => post('/push/visto', { de: KC_DE, on: document.visibilityState === 'visible' }).catch(() => {});
  document.addEventListener('visibilitychange', visto);
  window.addEventListener('pagehide', () => navigator.sendBeacon && navigator.sendBeacon('/push/visto', new Blob([JSON.stringify({ de: KC_DE, on: false })], { type: 'application/json' })));

  window.addEventListener('DOMContentLoaded', () => {
    ligar();
    visto();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(r => { swReg = r; avisoBotao(); }).catch(() => {});
    // 🎤 e 🎙 do celular no lugar dos do PC (que usam o microfone do PC); 👤 abre as contas
    document.addEventListener('click', e => {
      const b = e.target.closest('#mic, #voz, #contas-bt, #aviso-bt'); if (!b) return;
      e.preventDefault(); e.stopImmediatePropagation();
      if (!V.tocando && !V.fundo) { V.audio.play().catch(() => {}); V.audio.pause(); }   // libera o som neste toque (o celular exige um toque antes)
      if (b.id === 'mic') micLigar();
      else if (b.id === 'voz') {
        V.conversa = !V.conversa; localStorage.setItem('kc-conversa', V.conversa ? '1' : '0'); conversaBotao();
        bolha('sis', V.conversa ? '🎙 Modo conversa: leio as respostas em voz alta e depois já ouço você.' : 'Modo conversa desligado.');
        if (V.conversa && !K.ocupada) micLigar(); else if (!V.conversa) pararFala();
        if (V.conversa) fundoLigar(); else fundoDesligar();
      } else if (b.id === 'aviso-bt') avisoAlternar();
      else contasAbrir();
    }, true);
    const voz = document.getElementById('voz'); conversaBotao();
    const ct = document.createElement('button'); ct.className = 'bt'; ct.id = 'contas-bt'; ct.title = 'Contas do Claude: trocar'; ct.textContent = '👤';
    voz.after(ct);
    const av = document.createElement('button'); av.className = 'bt'; av.id = 'aviso-bt'; av.textContent = '🔕';
    ct.after(av); avisoBotao();
    // eventos da conversa → leitura em voz alta
    const ev0 = window.kcEv;
    window.kcEv = ev => {
      if (window.KCApp) {   // a cara da bolinha do app acompanha a conversa (trabalhando / pergunta / parada)
        if (ev.t === 'inicio' || ev.t === 'texto' || ev.t === 'passo' || ev.t === 'ferr' || ev.t === 'kani_pensando') KCApp.tarefa('trabalhando');
        else if (ev.t === 'permissao' || ev.t === 'pergunta') KCApp.tarefa('pergunta');
        else if (ev.t === 'fim' || ev.t === 'saiu' || ev.t === 'ajudante_resposta') KCApp.tarefa('parado');
        // o rosto enquanto trabalha (lendo / procurando / digitando / pensando) e a carinha do fim, como no PC
        if (ev.t === 'ferr') appBola('atividade', ATIV(ev.nome || ''));
        else if (ev.t === 'pensando' || ev.t === 'kani_pensando') appBola('atividade', 'pensando');
        else if (ev.t === 'texto_novo' || ev.t === 'fim' || ev.t === 'saiu' || ev.t === 'ajudante_resposta') appBola('atividade', '');
        if (ev.t === 'fim' || (ev.t === 'saiu' && ev.erro)) appBola('humor', ev.t === 'fim' && !ev.erro ? 'feliz' : 'erro');
        else if (ev.t === 'ajudante_resposta') appBola('humor', ev.ok ? 'feliz' : 'erro');
      }
      // resposta da Kani/Codex (vem inteira, sem 'texto'/'fim'): também é lida em voz alta
      if (ev.t === 'ajudante_resposta' && (V.ler || V.conversa) && ev.texto) {
        fundoDesligar(); V.buf = ''; V.codigo = false;
        falarPedaco(ev.texto + '\n'); if (!V.codigo) falarFrase(V.buf); V.buf = '';
        V.fimResposta = true; V.ler = false; if (!V.tocando) tocar();
      }
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
    menuMontar();
    telaMontar();
    quemVigiar();
    setTimeout(() => window.dispatchEvent(new Event('pywebviewready')), 0);
  });

  // ── menu ☰: os botões do topo moram aqui (o topo fica só com a marca, 📺 e ☰) ──
  const $$ = id => document.getElementById(id);
  function menuMontar() {
    const topo = document.querySelector('.topo');
    topo.insertAdjacentHTML('beforeend', '<button class="bt" id="kv-bt" title="KANIVETE ao vivo">📺</button><button class="bt" id="menu-bt" title="Menu">☰</button>');
    document.body.insertAdjacentHTML('beforeend', '<div class="menu-m" id="menu-m" hidden></div>');
    $$('menu-bt').onclick = e => { e.stopPropagation(); const m = $$('menu-m'); m.hidden ? menuAbrir() : (m.hidden = true); };
    $$('kv-bt').onclick = () => ($$('kv').hidden ? telaAbrir() : telaFechar());
    document.addEventListener('click', e => { if (!e.target.closest('#menu-m, #menu-bt')) $$('menu-m').hidden = true; });
  }
  function menuAbrir() {
    const n = ($$('atv-cont') && !$$('atv-cont').hidden) ? $$('atv-cont').textContent : '';
    const itens = [
      ['nova', '＋', 'Conversa nova', ''],
      ['habil', '🧰', 'Habilidades', ''],
      ['voz', '🎙', 'Modo conversa', V.conversa ? 'ligado' : 'desligado'],
      ['aviso-bt', '🔔', 'Avisos no celular', $$('aviso-bt')?.classList.contains('on') ? 'ligados' : 'desligados'],
      ['contas-bt', '👤', 'Contas do Claude', ''],
      ['atv-trilho', '⚡', 'Atividades', n ? n + ' rodando' : ''],
      ['recarregar', '⟳', 'Recarregar a tela', ''],
    ];
    const m = $$('menu-m');
    m.innerHTML = itens.map(([id, ic, nome, est]) => `<button data-id="${id}"><i>${ic}</i><span>${nome}</span>${est ? `<small class="${/ligad/.test(est) && !/des/.test(est) ? 'on' : ''}">${est}</small>` : ''}</button>`).join('');
    m.hidden = false;
    m.onclick = e => {
      const b = e.target.closest('button'); if (!b) return;
      m.hidden = true;
      if (b.dataset.id === 'recarregar') location.reload(); else $$(b.dataset.id).click();
    };
  }

  // ── 📺 KANIVETE ao vivo (tela_movel.py): telinha horizontal em cima da conversa; ⛶ tela cheia deitada; ✕ fecha e para ──
  let kvVigia = null;
  function telaMontar() {
    document.querySelector('.topo').insertAdjacentHTML('afterend', `<div class="kv" id="kv" hidden>
      <img id="kv-img" alt="">
      <div class="kv-msg" id="kv-msg" hidden><span id="kv-txt"></span><button id="kv-abrir">Abrir o KANIVETE</button></div>
      <div class="kv-bts"><button id="kv-cheia" title="Tela cheia">⛶</button><button id="kv-fechar" title="Fechar">✕</button></div></div>`);
    const img = $$('kv-img');
    img.onload = () => $$('kv-msg').hidden = true;
    img.onerror = () => { if (!$$('kv').hidden) telaConferir(); };
    img.ondblclick = telaCheia;
    $$('kv-cheia').onclick = telaCheia;
    $$('kv-fechar').onclick = telaFechar;
    $$('kv-abrir').onclick = async () => {
      $$('kv-abrir').disabled = true; $$('kv-txt').textContent = 'Abrindo o KANIVETE no PC…';
      await post('/tela/abrir');
      for (let i = 0; i < 45 && !$$('kv').hidden; i++) {
        await new Promise(r => setTimeout(r, 2000));
        if ((await (await fetch('/tela/estado')).json()).aberto) { $$('kv-abrir').disabled = false; return telaLigar(); }
      }
      $$('kv-abrir').disabled = false; $$('kv-txt').textContent = 'O KANIVETE não abriu a tempo.';
    };
    document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement) try { screen.orientation.unlock(); } catch (e) {} });
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && !$$('kv').hidden) telaLigar(); });
  }
  function telaLigar() { $$('kv-img').src = '/tela?t=' + Date.now(); }
  async function telaConferir() {
    let aberto = false;
    try { aberto = (await (await fetch('/tela/estado')).json()).aberto; } catch (e) {}
    if (aberto) { if (!$$('kv-img').complete || !$$('kv-img').naturalWidth) setTimeout(telaLigar, 1500); return; }
    $$('kv-txt').textContent = 'O KANIVETE está fechado (ou fora do modo agente).';
    $$('kv-msg').hidden = false;
  }
  function telaAbrir() {
    $$('kv').hidden = false; $$('kv-bt').classList.add('on'); telaLigar();
    clearInterval(kvVigia); kvVigia = setInterval(telaConferir, 10000);   // o app fechou no meio: avisa
  }
  function telaFechar() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    const img = $$('kv-img'); img.removeAttribute('src'); img.src = '';   // fecha a conexão: o PC para de mandar quadros
    $$('kv').hidden = true; $$('kv-bt').classList.remove('on'); clearInterval(kvVigia);
  }
  async function telaCheia() {
    const kv = $$('kv');
    if (document.fullscreenElement) return document.exitFullscreen().catch(() => {});
    try { await kv.requestFullscreen(); await screen.orientation.lock('landscape'); } catch (e) {}
  }
})();
