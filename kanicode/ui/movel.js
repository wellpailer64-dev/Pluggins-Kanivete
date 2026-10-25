// KaniCode no celular (movel.py): imita o window.pywebview.api da janela do PC por HTTP e recebe os eventos por SSE.
// Carregado ANTES do script da janela; só existe na página servida pelo movel.py (na janela do PC não entra).
(() => {
  window.KC_MOVEL = true;
  window.KC_DE = 'movel-' + Math.random().toString(36).slice(2, 8);
  document.documentElement.classList.add('movel');

  async function chamar(nome, args) {
    const r = await fetch('/api/' + nome, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-KC-De': KC_DE, 'X-KC-Aba': window.KC_ABAS?.ativa || '' },
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
      if (caiu && window.KC_ABAS?.reconectou) KC_ABAS.reconectou();   // abas criadas/fechadas enquanto estava fora
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
      // reaberto sozinho (conversa): para com 1,4 s de silêncio depois de falar. No toque no 🎤: pausa para pensar não
      // corta — só o 2º toque, 20 s sem falar nada ou 3 min (antes cortava na 1ª pausa e o resto da fala se perdia)
      if ((g.auto && g.falou > 0.3 && g.silencio > 1.4) || (!g.falou && Date.now() - g.inicio > (g.auto ? 3000 : 20000))
          || Date.now() - g.inicio > (g.auto ? 60000 : 180000)) micParar();
    };
    fonte.connect(proc); proc.connect(ctx.destination);
    V.gravando = g; micVisual(true); vozEv({ fase: 'ouvindo' });
    if (navigator.vibrate) navigator.vibrate(30);
  }
  // 2 toques na bolinha do app: liga o microfone; outros 2 toques com ele ligado descartam a gravação
  window.kcBolaOuvir = () => V.gravando ? micParar(true) : micLigar();
  async function micParar(cancelar) {
    const g = V.gravando; if (!g) return;
    V.gravando = null; micVisual(false);
    setTimeout(fundoLigar, 300);   // o silêncio volta depois do microfone (com a tela aberta ele não atrapalha)
    g.proc.disconnect(); g.fonte.disconnect(); g.fluxo.getTracks().forEach(t => t.stop()); g.ctx.close();
    if (navigator.vibrate) navigator.vibrate([20, 40, 20]);
    if (cancelar === true) { atividade('Gravação descartada'); return; }
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
    const nativo = window.KCApp && typeof KCApp.avisosEstado === 'function';
    const sub = !nativo && swReg?.pushManager && await swReg.pushManager.getSubscription();
    const on = nativo ? KCApp.avisosEstado() === 'ligados' : !!sub && window.Notification?.permission === 'granted';
    b.classList.toggle('on', on); b.textContent = on ? '🔔' : '🔕';
    b.title = on ? 'Avisos ligados: chega notificação quando eu terminar ou precisar de você' : 'Ligar avisos no celular';
  }
  async function avisoAlternar() {
    if (window.KCApp && typeof KCApp.avisosAlternar === 'function') {
      KCApp.avisosAlternar(); setTimeout(avisoBotao, 300); return;
    }
    if (!swReg?.pushManager || !('PushManager' in window)) { bolha('sis', 'Para receber avisos, use o app Android atualizado ou abra o KaniCode no Chrome.'); return; }
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
  document.addEventListener('visibilitychange', () => { visto(); if (!document.hidden) avisoBotao(); });
  window.kcAvisosAtualizar = avisoBotao;
  window.addEventListener('pagehide', () => navigator.sendBeacon && navigator.sendBeacon('/push/visto', new Blob([JSON.stringify({ de: KC_DE, on: false })], { type: 'application/json' })));

  window.addEventListener('DOMContentLoaded', () => {
    ligar();
    visto();
    // A mesma prévia e o mesmo envio de imagens da conversa do PC.
    const entrada = document.querySelector('.entrada');
    const fotos = document.createElement('div');
    fotos.className = 'movel-fotos';
    for (const [nome, icone, camera] of [['Câmera', '◎', true], ['Galeria', '▧', false]]) {
      const arquivo = document.createElement('input');
      arquivo.type = 'file'; arquivo.accept = 'image/*'; arquivo.hidden = true;
      if (camera) arquivo.setAttribute('capture', 'environment');
      else arquivo.multiple = true;
      const botao = document.createElement('button');
      botao.type = 'button'; botao.className = 'movel-foto';
      botao.textContent = icone; botao.title = nome; botao.setAttribute('aria-label', nome);
      botao.onclick = () => arquivo.click();
      arquivo.onchange = async () => {
        await anexar(Array.from(arquivo.files || [])); arquivo.value = '';
      };
      fotos.append(botao, arquivo);
    }
    entrada.append(fotos);
    // O teclado reduz a área útil também nos navegadores que não redimensionam o body.
    const tamanho = () => document.documentElement.style.setProperty('--movel-altura',
      (window.visualViewport ? window.visualViewport.height : window.innerHeight) + 'px');
    if (window.visualViewport) window.visualViewport.addEventListener('resize', tamanho);
    window.addEventListener('resize', tamanho); tamanho();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(r => { swReg = r; avisoBotao(); }).catch(() => {});
    // 🎤 e 🎙 do celular no lugar dos do PC (que usam o microfone do PC); 👤 abre as contas
    document.addEventListener('click', e => {
      const b = e.target.closest('#mic, #mic-x, #voz, #contas-bt, #aviso-bt'); if (!b) return;
      e.preventDefault(); e.stopImmediatePropagation();
      if (!V.tocando && !V.fundo) { V.audio.play().catch(() => {}); V.audio.pause(); }   // libera o som neste toque (o celular exige um toque antes)
      if (b.id === 'mic') micLigar();
      else if (b.id === 'mic-x') micParar(true);
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
      const outra = ev.aba != null && window.KC_ABAS?.ativa && String(ev.aba) !== KC_ABAS.ativa;
      if (window.KCApp && typeof KCApp.notificar === 'function') {
        if (ev.t === 'permissao' || ev.t === 'pergunta') KCApp.notificar('Preciso de você', 'Abra o KaniCode para responder.', !!outra);
        else if (ev.t === 'fim' || ev.t === 'ajudante_resposta' || (ev.t === 'saiu' && ev.erro)) {
          KCApp.notificar(ev.erro || ev.ok === false ? 'A tarefa precisa de atenção' : 'Tarefa concluída', 'Abra o KaniCode para ver a resposta.', !!outra);
        }
      }
      if (outra) { ev0(ev); return; }   // voz e rosto acompanham a conversa selecionada
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
    topo.insertAdjacentHTML('beforeend', '<button class="bt" id="kv-bt" title="Tela do PC ao vivo">📺</button><button class="bt" id="menu-bt" title="Menu">☰</button>');
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
      ['todo-trilho', '☑', 'Tarefas e agenda', ''],
      ['consumo-trilho', '📊', 'Consumo de tokens', ''],
      ['mapa-d-bt', '▤', 'Mapa do disco D', ''],
      ['casa-trilho', '🏠', 'Casa', ''],
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
  let kvFonte = 'pc', kvMonitor = '', kvZoom = 1, kvPan = {x:0,y:0}, kvPinca = null;
  const kvDedos = new Map();
  let kvResolucao=1280,kvZoomTimer=null;
  let kvNativa = false, kvGesto = null, kvUltToque = 0, kvMoveTimer = 0, kvEnviando = false, kvGer = 0, kvAbort = null;
  const kvMouse = { x: .5, y: .5, largura: 0, ligado: true, fila: [] };
  function telaMontar() {
    document.querySelector('.topo').insertAdjacentHTML('afterend', `<div class="kv" id="kv" hidden>
      <div class="kv-area controle" id="kv-area"><img id="kv-img" alt="Tela do PC" draggable="false">
        <svg id="kv-cursor" viewBox="0 0 16 22" aria-hidden="true" hidden><path d="M1 1v17l4-4 4 7 3-2-4-7h6Z" fill="white" stroke="black" stroke-width="1.5"/></svg></div>
      <div class="kv-msg" id="kv-msg" hidden><span id="kv-txt"></span><button id="kv-abrir">Abrir o KANIVETE</button></div>
      <div class="kv-bts"><select id="kv-fonte" aria-label="Tela transmitida"><option value="pc">PC · principal</option><option value="kanivete">KANIVETE</option></select><button id="kv-mouse" title="Arraste para mover o mouse; toque para clicar; dois toques para duplo clique" aria-label="Controle do mouse" aria-pressed="true">↖</button><button id="kv-menos" aria-label="Diminuir zoom">−</button><button id="kv-mais" aria-label="Aumentar zoom">+</button><button id="kv-cheia" title="Tela cheia" aria-label="Tela cheia" aria-pressed="false">⛶</button><button id="kv-fechar" title="Fechar" aria-label="Fechar transmissão">✕</button></div>
      <span id="kv-mouse-status" class="kv-mouse-status" role="status">Arraste: mover · toque: clicar · dois toques: duplo clique</span></div>`);
    const img = $$('kv-img');
    img.onload = () => { $$('kv-msg').hidden = true; mouseDesenhar(); };
    img.onerror = () => { if (!$$('kv').hidden) telaConferir(); };
    $$('kv-cheia').onclick = telaCheia;
    $$('kv-mais').onclick = () => zoomAplicar(kvZoom * 1.5);
    $$('kv-menos').onclick = () => zoomAplicar(kvZoom / 1.5);
    $$('kv-fonte').onchange = () => {
      mouseCancelar(); kvDedos.clear(); kvPinca=null;
      const valor=$$('kv-fonte').value;
      kvFonte=valor==='kanivete'?'kanivete':'pc';kvMonitor=valor.startsWith('pc:')?valor.slice(3):'';
      kvMouse.x=kvMouse.y=.5;kvMouse.largura=0;kvPan={x:0,y:0};zoomAplicar(1);
      $$('kv-img').alt=kvFonte==='pc'?'Tela do PC':'Tela do KANIVETE';
      $$('kv-msg').hidden=true;telaLigar();
    };
    $$('kv-fechar').onclick = telaFechar;
    $$('kv-mouse').onclick = () => {
      kvMouse.ligado = !kvMouse.ligado; mouseCancelar();
      $$('kv-area').classList.toggle('controle', kvMouse.ligado);
      $$('kv-mouse').setAttribute('aria-pressed', String(kvMouse.ligado));
      $$('kv-mouse-status').textContent = kvMouse.ligado ? 'Arraste: mover · toque: clicar · dois toques: duplo clique' : 'Só assistir';
      mouseDesenhar();
    };
    mouseMontar();
    $$('kv-abrir').onclick = async () => {
      $$('kv-abrir').disabled = true; $$('kv-txt').textContent = 'Abrindo o KANIVETE no PC…';
      await post('/tela/abrir');
      for (let i = 0; i < 45 && !$$('kv').hidden; i++) {
        await new Promise(r => setTimeout(r, 2000));
        if ((await (await fetch('/tela/estado')).json()).aberto) { $$('kv-abrir').disabled = false; return telaLigar(); }
      }
      $$('kv-abrir').disabled = false; $$('kv-txt').textContent = 'O KANIVETE não abriu a tempo.';
    };
    const mudouTela = () => {
      if (!(document.fullscreenElement || document.webkitFullscreenElement) && kvNativa) telaNormal();
      mouseDesenhar();
    };
    document.addEventListener('fullscreenchange', mudouTela);
    document.addEventListener('webkitfullscreenchange', mudouTela);
    window.addEventListener('resize', mouseDesenhar);
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && $$('kv').classList.contains('kv-grande')) telaNormal(); });
    document.addEventListener('visibilitychange', () => { if (document.hidden) mouseCancelar(); });
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && !$$('kv').hidden) telaLigar(); });
  }
  function telaParametros() { return new URLSearchParams({fonte:kvFonte,monitor:kvMonitor,largura:kvResolucao}); }
  function telaLigar() { $$('kv-img').src = '/tela?' + telaParametros() + '&t=' + Date.now(); }
  async function telaMonitores() {
    try {
      const r=await fetch('/tela/monitores'), itens=await r.json();
      if(!r.ok||!Array.isArray(itens))return;
      const seletor=$$('kv-fonte'), valor=seletor.value;seletor.replaceChildren();
      for(const m of itens){const o=document.createElement('option');o.value='pc:'+m.id;o.textContent=m.nome;seletor.append(o);}
      if(!itens.length){const o=document.createElement('option');o.value='pc';o.textContent='PC · principal';seletor.append(o);}
      const app=document.createElement('option');app.value='kanivete';app.textContent='KANIVETE';seletor.append(app);
      if(Array.from(seletor.options).some(o=>o.value===valor))seletor.value=valor;
      else if(kvFonte==='pc'&&!kvMonitor){seletor.selectedIndex=0;}
      else {seletor.selectedIndex=0;seletor.onchange();}
    } catch (_) {}
  }
  function zoomAplicar(valor) {
    kvZoom=Math.max(1,Math.min(4,valor));
    if(kvZoom===1)kvPan={x:0,y:0};
    const area=$$('kv-area').getBoundingClientRect();
    const img=$$('kv-img'), proporcao=img.naturalWidth/img.naturalHeight;
    const w=Math.min(img.clientWidth,img.clientHeight*proporcao)||area.width;
    const h=w/proporcao||area.height;
    const maxX=Math.max(0,(w*kvZoom-area.width)/2),maxY=Math.max(0,(h*kvZoom-area.height)/2);
    kvPan.x=Math.max(-maxX,Math.min(maxX,kvPan.x));
    kvPan.y=Math.max(-maxY,Math.min(maxY,kvPan.y));
    $$('kv-img').style.transform=`translate(${kvPan.x}px,${kvPan.y}px) scale(${kvZoom})`;
    $$('kv-mais').title=$$('kv-menos').title='Zoom: '+Math.round(kvZoom*100)+'% · dois dedos para ampliar e deslocar';
    const resolucao=kvZoom>1.1?2560:1280;
    if(resolucao!==kvResolucao){
      kvResolucao=resolucao;clearTimeout(kvZoomTimer);
      kvZoomTimer=setTimeout(()=>{if(!$$('kv').hidden&&kvFonte==='pc')telaLigar();},300);
    }
    mouseDesenhar();
  }
  async function telaConferir() {
    telaMonitores();
    let aberto = false;
    try { aberto = (await (await fetch('/tela/estado?' + telaParametros())).json()).aberto; } catch (e) {}
    if (aberto) { if (!$$('kv-img').complete || !$$('kv-img').naturalWidth) setTimeout(telaLigar, 1500); return; }
    $$('kv-txt').textContent = kvFonte==='pc'?'Monitor indisponível. Escolha outra tela.':'O KANIVETE está fechado (ou fora do modo agente).';
    $$('kv-abrir').hidden=kvFonte==='pc';
    $$('kv-msg').hidden = false;
  }
  function telaAbrir() {
    $$('kv').hidden = false; $$('kv-bt').classList.add('on'); telaLigar();
    telaMonitores();
    clearInterval(kvVigia); kvVigia = setInterval(telaConferir, 10000);   // o app fechou no meio: avisa
    requestAnimationFrame(mouseDesenhar);
  }
  function telaFechar() {
    mouseCancelar(); telaNormal();
    const img = $$('kv-img'); img.removeAttribute('src'); img.src = '';   // fecha a conexão: o PC para de mandar quadros
    $$('kv').hidden = true; $$('kv-bt').classList.remove('on'); clearInterval(kvVigia);
  }
  async function telaCheia() {
    const kv = $$('kv');
    if (kv.classList.contains('kv-grande')) return telaNormal();
    kv.classList.add('kv-grande'); document.documentElement.classList.add('kv-ampliada');
    $$('kv-cheia').setAttribute('aria-pressed', 'true');
    $$('kv-cheia').setAttribute('aria-label', 'Sair da tela cheia');
    mouseCancelar(); requestAnimationFrame(mouseDesenhar);
    try {
      const pedir = kv.requestFullscreen || kv.webkitRequestFullscreen;
      if (pedir) { await pedir.call(kv); kvNativa = true; }
    } catch (e) {}   // navegador sem Fullscreen API: a classe mantém a tela ampliada
    if (!kv.classList.contains('kv-grande')) return telaNormal();
    try { await screen.orientation.lock('landscape'); } catch (e) {}
  }
  function telaNormal() {
    kvNativa = false;
    $$('kv').classList.remove('kv-grande'); document.documentElement.classList.remove('kv-ampliada');
    $$('kv-cheia').setAttribute('aria-pressed', 'false');
    $$('kv-cheia').setAttribute('aria-label', 'Tela cheia');
    const sair = document.exitFullscreen || document.webkitExitFullscreen;
    if ((document.fullscreenElement || document.webkitFullscreenElement) && sair) {
      try { const p = sair.call(document); if (p?.catch) p.catch(() => {}); } catch (e) {}
    }
    try { screen.orientation.unlock(); } catch (e) {}
    mouseCancelar(); requestAnimationFrame(mouseDesenhar);
  }
  function mouseCancelar() {
    clearTimeout(kvMoveTimer); kvMoveTimer = 0; kvGesto = null; kvUltToque = 0;
    kvMouse.fila.length = 0; kvGer++; kvAbort?.abort();
    kvDedos.clear();kvPinca=null;
  }
  function quadroVisivel() {
    const img = $$('kv-img'), r = img.getBoundingClientRect(), proporcao = img.naturalWidth / img.naturalHeight;
    if (!Number.isFinite(proporcao) || !r.width || !r.height) return null;
    const w = Math.min(r.width, r.height * proporcao), h = w / proporcao;
    return { x: r.left + (r.width - w) / 2, y: r.top + (r.height - h) / 2, w, h };
  }
  function mouseDesenhar() {
    const q = quadroVisivel(), cursor = $$('kv-cursor');
    if (!cursor) return;
    cursor.toggleAttribute('hidden', !q || !kvMouse.ligado || !$$('kv-msg').hidden);
    if (!q) return;
    const r = $$('kv-area').getBoundingClientRect();
    cursor.style.left = (q.x - r.left + Math.min(q.w - 1, kvMouse.x * q.w)) + 'px';
    cursor.style.top = (q.y - r.top + Math.min(q.h - 1, kvMouse.y * q.h)) + 'px';
    cursor.style.width = Math.max(6, 16 * q.w / (kvMouse.largura || $$('kv-img').naturalWidth)) + 'px';
  }
  function mouseEnfileirar(acao, cliques = 1) {
    const d = { acao, x: kvMouse.x, y: kvMouse.y, cliques:kvFonte==='pc'?1:cliques, fonte:kvFonte, monitor:kvMonitor };
    const fila = kvMouse.fila;
    // O clique já leva a posição final; movimentos pendentes não devem atrasá-lo.
    if(acao==='clicar'&&kvFonte==='pc')for(let i=fila.length-1;i>=0;i--)if(fila[i].acao==='mover')fila.splice(i,1);
    if (acao === 'mover' && fila.at(-1)?.acao === 'mover') fila[fila.length - 1] = d;
    else fila.push(d);
    mouseEnviar();
  }
  async function mouseEnviar() {
    if (kvEnviando || !kvMouse.fila.length || $$('kv').hidden) return;
    kvEnviando = true;
    const ger = kvGer;
    try {
      while (kvMouse.fila.length && ger === kvGer && !$$('kv').hidden) {
        const dados = kvMouse.fila.shift(), abort = new AbortController(); kvAbort = abort;
        const prazo = setTimeout(() => abort.abort(), 3000);
        try {
          const r = await fetch('/tela/mouse', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(dados), signal:abort.signal});
          const j = await r.json();
          if (!r.ok || j.erro) throw Error(j.erro || 'Mouse indisponível');
          if (ger === kvGer) {
            kvMouse.largura = j.largura;
            $$('kv-mouse-status').textContent = 'Arraste: mover · toque: clicar · dois toques: duplo clique';
            mouseDesenhar();
          }
        } finally { clearTimeout(prazo); }
      }
    } catch (e) {
      if (ger === kvGer) { kvMouse.fila.length = 0; $$('kv-mouse-status').textContent = 'Mouse indisponível — tente novamente'; }
    } finally {
      kvEnviando = false; kvAbort = null;
      if (kvMouse.fila.length && !$$('kv').hidden) mouseEnviar();
    }
  }
  function mouseMontar() {
    const area = $$('kv-area');
    area.addEventListener('contextmenu', e => { if (kvMouse.ligado) e.preventDefault(); });
    area.addEventListener('pointerdown', e => {
      if (!$$('kv-msg').hidden || !quadroVisivel() || e.button !== 0) return;
      e.preventDefault();
      kvDedos.set(e.pointerId,{x:e.clientX,y:e.clientY});
      try { area.setPointerCapture(e.pointerId); } catch (_) {}
      if(kvDedos.size>=2){
        const [a,b]=Array.from(kvDedos.values());
        kvPinca={dist:Math.max(1,Math.hypot(a.x-b.x,a.y-b.y)),x:(a.x+b.x)/2,y:(a.y+b.y)/2,zoom:kvZoom,pan:{...kvPan}};
        kvGesto=null;kvUltToque=0;clearTimeout(kvMoveTimer);kvMoveTimer=0;return;
      }
      if(!kvMouse.ligado)return;
      if (kvGesto) { kvGesto = null; kvUltToque = 0; return; }
      kvGesto = { id:e.pointerId, x:e.clientX, y:e.clientY, inicioX:e.clientX, inicioY:e.clientY, t:performance.now(), moveu:false };
      try { area.setPointerCapture(e.pointerId); } catch (e) {}
    });
    area.addEventListener('pointermove', e => {
      if(kvDedos.has(e.pointerId))kvDedos.set(e.pointerId,{x:e.clientX,y:e.clientY});
      if(kvPinca){
        e.preventDefault();
        if(kvDedos.size>=2){
          const [a,b]=Array.from(kvDedos.values());
          kvPan={x:kvPinca.pan.x+(a.x+b.x)/2-kvPinca.x,y:kvPinca.pan.y+(a.y+b.y)/2-kvPinca.y};
          zoomAplicar(kvPinca.zoom*Math.hypot(a.x-b.x,a.y-b.y)/kvPinca.dist);
        }
        return;
      }
      const g = kvGesto, q = quadroVisivel();
      if (!g || g.id !== e.pointerId || !q) return;
      e.preventDefault();
      if (!g.moveu && Math.hypot(e.clientX - g.inicioX, e.clientY - g.inicioY) < 5) return;
      g.moveu = true; kvUltToque = 0;
      kvMouse.x = Math.max(0, Math.min(1, kvMouse.x + (e.clientX - g.x) / q.w));
      kvMouse.y = Math.max(0, Math.min(1, kvMouse.y + (e.clientY - g.y) / q.h));
      g.x = e.clientX; g.y = e.clientY; mouseDesenhar();
      if (!kvMoveTimer) kvMoveTimer = setTimeout(() => { kvMoveTimer = 0; mouseEnfileirar('mover'); }, 50);
    });
    area.addEventListener('pointerup', e => {
      kvDedos.delete(e.pointerId);
      if(kvPinca){if(!kvDedos.size)kvPinca=null;kvGesto=null;kvUltToque=0;return;}
      const g = kvGesto;
      if (!g || g.id !== e.pointerId) return;
      kvGesto = null;
      if (g.moveu) { clearTimeout(kvMoveTimer); kvMoveTimer = 0; mouseEnfileirar('mover'); return; }
      if (performance.now() - g.t > 500 || Math.hypot(e.clientX - g.inicioX, e.clientY - g.inicioY) >= 5) return;
      const agora = performance.now(), duplo = kvUltToque && agora - kvUltToque < 450;
      kvUltToque = duplo ? 0 : agora;
      mouseEnfileirar('clicar', duplo ? 2 : 1);
    });
    area.addEventListener('pointercancel', mouseCancelar);
    area.addEventListener('lostpointercapture', () => { if (kvGesto) mouseCancelar(); });
  }
})();
