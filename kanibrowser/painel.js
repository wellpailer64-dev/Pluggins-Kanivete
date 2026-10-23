// Painel do KaniBrowser (roda dentro do KANIVETE; recebe KPLUG e PLUGIN_ID). Tudo DENTRO do app: o Chrome roda escondido
// e cada lado é uma transmissão ao vivo (MJPEG local, visao.py) com mouse e teclado de volta pelo canal privado.
// Esquerda = o SEU navegador (abas, endereço, pegar imagens → pasta da demanda); direita = a KANI trabalhando.
const KB = { abas: [], ordem: [], sel: null, kani: null, aberto: false, base: '', destinos: [], dest: null, imgs: [], marcadas: new Set() };
const kbEsc = t => _escHtml(t == null ? '' : String(t));
const kbCall = (f, a) => KPLUG.chamar(PLUGIN_ID, f, a);
const kbPg = () => KPLUG.pagina(PLUGIN_ID);
const kb$ = s => kbPg().querySelector(s);
const kbGuarda = (k, v) => { try { v === undefined ? (v = localStorage.getItem(k)) : localStorage.setItem(k, v); } catch (e) { v = null; } return v; };
window.KB_API = { KB, atualizar: () => kbEstado() };

function kbMontar() {
    const info = KPLUG.info(PLUGIN_ID) || {};
    const kw = +kbGuarda('kb-kani-w2') ? kbGuarda('kb-kani-w2') + 'px' : 'minmax(0, 1fr)';   // meio a meio até arrastar
    kbPg().innerHTML = `
      <div class="kb-app${kbGuarda('kb-kani-off') === '1' ? ' sem-kani' : ''}" style="--kb-kw:${kw}">
        <div class="kb-barra">
          ${info.logo ? `<img class="kb-logo" src="${info.logo}" alt="KaniBrowser">` : '<b>KaniBrowser</b>'}
          <span class="kb-status" id="kb-status">fechado</span>
          <span class="kb-dica" title="O navegador roda escondido; só o Kanivete comanda ele. Os logins ficam guardados.">🔒 canal privado</span>
          <span class="kb-esp"></span>
          <span class="kb-kpilula" id="kb-kpilula" hidden></span>
          <button class="btn-secondary kb-mini" id="kb-baixados" title="Pasta dos downloads do navegador">⬇ Downloads</button>
          <button class="btn-secondary kb-mini" id="kb-kbot" title="Mostrar/esconder a visão da Kani">◨ Kani</button>
          <button class="btn-secondary kb-mini" id="kb-fechar" title="Fechar o navegador">✕</button>
        </div>
        <div class="kb-corpo">
          <section class="kb-nav">
            <div class="kb-faixa"><div class="kb-tabs" id="kb-tabs"></div><button class="kb-tab-mais" id="kb-mais" title="Nova aba (Ctrl+T)">+</button></div>
            <div class="kb-ferr">
              <button class="kb-ico" data-n="voltar" title="Voltar (Alt+←)">←</button>
              <button class="kb-ico" data-n="avancar" title="Avançar (Alt+→)">→</button>
              <button class="kb-ico" data-n="recarregar" id="kb-rec" title="Recarregar (F5)">⟳</button>
              <form class="kb-end" id="kb-end"><span class="kb-cad">🔒</span><input id="kb-url" placeholder="Pesquise ou digite um endereço" autocomplete="off" spellcheck="false">
                <button type="button" class="kb-estrela" id="kb-estrela" title="Favoritar esta página (Ctrl+D)">☆</button></form>
            </div>
            <div class="kb-favs" id="kb-favs"></div>
            <div class="kb-tela kb-tela-voce" id="kb-tv"></div>
            <div class="kb-pe">
              <button class="btn-primary kb-mini" id="kb-pegar">🖼 Pegar imagens</button>
              <button class="btn-secondary kb-mini" id="kb-print">📷 Print</button>
              <button class="btn-secondary kb-mini" id="kb-texto">Copiar texto</button>
              <span class="kb-esp"></span>
              <label class="kb-destino" title="Para onde vão as imagens, prints e materiais"><span>Mandar para</span><select id="kb-dest"></select></label>
            </div>
            <aside class="kb-gaveta" id="kb-gaveta" hidden></aside>
          </section>
          <div class="kb-div" id="kb-div" title="Arraste para mudar o tamanho"></div>
          <section class="kb-kani">
            <header class="kb-cab"><img class="kb-av" src="identidade/kani.webp" alt=""><b>Kani</b>
              <span class="kb-faz" id="kb-faz">parada</span></header>
            <div class="kb-kurl" id="kb-kurl"></div>
            <div class="kb-tela kb-tela-kani" id="kb-tk"></div>
            <div class="kb-hist" id="kb-hist"></div>
            <div class="kb-tarefas">
              <form id="kb-kir"><input placeholder="Mandar a Kani abrir…" id="kb-kir-u"><button class="btn-secondary kb-mini">Abrir</button></form>
              <form id="kb-ig"><input placeholder="@perfil do Instagram" id="kb-ig-u"><button class="btn-secondary kb-mini">Ver posts</button></form>
              <form id="kb-ln"><input placeholder="Link de material (Drive, WeTransfer…)" id="kb-ln-u"><button class="btn-secondary kb-mini">Baixar</button></form>
            </div>
          </section>
        </div>
      </div>`;
    KB.tv = kbTela(kb$('#kb-tv'), false);
    KB.tk = kbTela(kb$('#kb-tk'), true);
    kb$('#kb-end').onsubmit = e => { e.preventDefault(); const u = kb$('#kb-url').value.trim(); if (u) kbIr(u); kb$('#kb-url').blur(); };
    kb$('#kb-url').onfocus = e => e.target.select();
    kb$('#kb-estrela').onclick = () => kbFavoritar();
    kbPg().querySelectorAll('.kb-ico').forEach(b => b.onclick = () => KB.sel && kbCall('navegar', { aba: KB.sel, acao: b.dataset.n === 'recarregar' && b.classList.contains('parar') ? 'parar' : b.dataset.n }).catch(() => 0));
    kb$('#kb-mais').onclick = () => kbNovaAba();
    kb$('#kb-fechar').onclick = async () => { await kbTenta(() => kbCall('fechar_navegador')); kbEstado(); };
    kb$('#kb-baixados').onclick = () => kbCall('abrir_downloads').catch(() => 0);
    kb$('#kb-kbot').onclick = () => kbKani(!kb$('.kb-app').classList.contains('sem-kani') ? false : true);
    kb$('#kb-kpilula').onclick = () => kbKani(true);
    kb$('#kb-pegar').onclick = () => kbPegar();
    kb$('#kb-print').onclick = () => kbPrint();
    kb$('#kb-texto').onclick = async e => {
        const t = await kbTenta(() => kbCall('texto', { aba: KB.sel }));
        if (t) { navigator.clipboard.writeText(t); kbAviso('✓ Texto da página copiado'); }
    };
    kb$('#kb-dest').onchange = async e => {
        const s = e.target;
        if (s.value !== 'escolher') { KB.dest = s.value; return; }
        const r = await window.pywebview.api.select_folder('kanibrowser').catch(() => null);
        if (r && r.success) KB.dest = 'p:' + r.path;
        kbDestinos();
    };
    kb$('#kb-kir').onsubmit = e => {
        e.preventDefault();
        const u = kb$('#kb-kir-u').value.trim(); if (u) { kbKani(true); kbTenta(() => kbCall('kani_ir', { url: u })); }
    };
    kb$('#kb-ig').onsubmit = async e => {
        e.preventDefault();
        const u = kb$('#kb-ig-u').value.trim(); if (!u) return;
        kbKani(true);
        kbGaveta('Posts de ' + u, '<div class="kb-vazio">A Kani está abrindo o perfil… acompanhe à direita.</div>');
        const r = await kbTenta(() => kbCall('instagram', { usuario: u }));
        if (!r) return kbGavetaFechar();
        if (!r.logado) kbAviso('Entre no Instagram pela tela da Kani (clique nela e digite) e tente de novo.');
        kbGrade(r.posts.filter(p => p.imagem).map(p => ({ url: p.imagem, w: 0, h: 0, link: p.link })));
    };
    kb$('#kb-ln').onsubmit = async e => {
        e.preventDefault();
        const u = kb$('#kb-ln-u').value.trim(); if (!u) return;
        kbKani(true);
        const r = await kbTenta(() => kbCall('baixar_link', { url: u, ...kbDestino() }));
        if (r) kbAviso(`✓ ${r.arquivos.length} arquivo(s) baixado(s)`, r.pasta);
    };
    kbDivisoria();
    kbDestinos();
}

async function kbTenta(f) {
    try { return await f(); }
    catch (e) { appConfirm({ titulo: 'KaniBrowser', texto: e.message, botoes: [{ rotulo: 'Ok', valor: 1, tipo: 'primario' }] }); }
}

function kbAviso(texto, pasta) {
    const d = document.createElement('div'); d.className = 'kb-aviso';
    d.innerHTML = kbEsc(texto) + (pasta ? ' · <a href="#">abrir pasta</a>' : '');
    if (pasta) d.querySelector('a').onclick = ev => { ev.preventDefault(); pasta === 'downloads' ? kbCall('abrir_downloads') : kbCall('abrir_pasta', { pasta }); };
    kb$('.kb-app').appendChild(d); setTimeout(() => d.remove(), 8000);
}

function kbKani(ligar) {
    kb$('.kb-app').classList.toggle('sem-kani', !ligar);
    kbGuarda('kb-kani-off', ligar ? '0' : '1');
    kbLigarTelas();
}

function kbDivisoria() {
    const div = kb$('#kb-div'), app = kb$('.kb-app');
    div.onpointerdown = e => {
        div.setPointerCapture(e.pointerId);
        const x0 = e.clientX, w0 = kb$('.kb-kani').getBoundingClientRect().width || 420;
        div.onpointermove = ev => {
            const w = Math.max(300, Math.min(app.clientWidth * 0.7, w0 - (ev.clientX - x0)));
            app.style.setProperty('--kb-kw', w + 'px');
        };
        div.onpointerup = () => { div.onpointermove = null; const w = parseInt(app.style.getPropertyValue('--kb-kw')); if (w) kbGuarda('kb-kani-w2', w); };
        div.ondblclick = () => { app.style.setProperty('--kb-kw', 'minmax(0, 1fr)'); kbGuarda('kb-kani-w2', ''); };   // duplo clique: volta ao meio
    };
}

// ---------- uma tela ao vivo (a sua ou a da Kani) ----------
function kbTela(raiz, kani) {
    raiz.innerHTML = `<img class="kb-vid" draggable="false" alt=""><textarea class="kb-tec" aria-label="teclado da página"></textarea>
        <div class="kb-carga"></div><div class="kb-sobre"></div><div class="kb-tela-vazia"></div>`;
    const im = raiz.querySelector('.kb-vid'), tec = raiz.querySelector('.kb-tec'), sobre = raiz.querySelector('.kb-sobre');
    const T = { tid: null, fila: [], enviando: false, raiz, kani };
    T.vazio = html => { raiz.querySelector('.kb-tela-vazia').innerHTML = html; raiz.classList.toggle('vazia', !!html); };
    T.ligar = tid => {
        if (!tid || !KB.base) return T.desligar();
        if (T.tid === tid && im.getAttribute('src')) return;
        T.tid = tid; T.tam = null; sobre.innerHTML = '';
        T.ajustar();
        im.src = KB.base + tid + '.mjpg?k=' + Date.now();
    };
    T.desligar = () => { T.tid = null; im.removeAttribute('src'); };
    T.ajustar = () => {
        if (!T.tid) return;
        const r = raiz.getBoundingClientRect(); if (r.width < 50 || r.height < 50) return;
        const dpr = window.devicePixelRatio || 1;
        // a Kani trabalha num tamanho de computador (1280 de largura) e a tela mostra reduzido
        const w = kani ? 1280 : Math.round(r.width), h = kani ? Math.round(1280 * r.height / r.width) : Math.round(r.height);
        const k = `${w}x${h}`; if (T.tam === k) return; T.tam = k;
        kbCall('ajustar', { aba: T.tid, w, h, dpr: kani ? 1 : dpr }).catch(() => 0);
    };
    let rt; new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(T.ajustar, 200); }).observe(raiz);
    const pos = e => {   // fração (0..1) dentro da imagem (object-fit: contain deixa faixas)
        const r = im.getBoundingClientRect(), w = im.naturalWidth, h = im.naturalHeight;
        if (!w) return null;
        const k = Math.min(r.width / w, r.height / h), x0 = r.left + (r.width - w * k) / 2, y0 = r.top + (r.height - h * k) / 2;
        return { x: Math.max(0, Math.min(1, (e.clientX - x0) / (w * k))), y: Math.max(0, Math.min(1, (e.clientY - y0) / (h * k))) };
    };
    const mods = e => (e.altKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.metaKey ? 4 : 0) | (e.shiftKey ? 8 : 0);
    T.manda = ev => {
        if (!T.tid) return;
        const ult = T.fila[T.fila.length - 1];   // junta movimentos e rodinha seguidos (um pedido por vez)
        if (ev.t === 'move' && ult && ult.t === 'move' && ult.bs === ev.bs) T.fila[T.fila.length - 1] = ev;
        else if (ev.t === 'wheel' && ult && ult.t === 'wheel') { ult.dx += ev.dx; ult.dy += ev.dy; ult.x = ev.x; ult.y = ev.y; }
        else T.fila.push(ev);
        T.esvaziar();
    };
    T.esvaziar = async () => {
        if (T.enviando || !T.fila.length) return;
        T.enviando = true;
        const lote = T.fila.splice(0);
        try {
            const r = await kbCall('entrada', { aba: T.tid, eventos: lote });
            if (r) {
                im.style.cursor = r.cursor || 'default';
                if (r.select) kbLista(T, r.select);
            }
        } catch (e) { }
        T.enviando = false;
        if (T.fila.length) T.esvaziar();
    };
    im.addEventListener('pointerdown', e => {
        if (!T.tid) return;
        e.preventDefault();
        tec.focus({ preventScroll: true });
        sobre.querySelectorAll('.kb-menu,.kb-lista').forEach(x => x.remove());
        if (e.button === 2) return;
        im.setPointerCapture(e.pointerId);
        T.manda({ t: 'down', ...pos(e), b: e.button, bs: e.buttons, c: e.detail || 1, m: mods(e) });
    });
    im.addEventListener('pointerup', e => { if (T.tid && e.button !== 2) T.manda({ t: 'up', ...pos(e), b: e.button, bs: e.buttons, c: e.detail || 1, m: mods(e) }); });
    im.addEventListener('pointermove', e => { if (T.tid && pos(e)) T.manda({ t: 'move', ...pos(e), bs: e.buttons, m: mods(e) }); });
    im.addEventListener('wheel', e => {
        if (!T.tid) return;
        e.preventDefault();
        const k = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 800 : 1;
        T.manda({ t: 'wheel', ...pos(e), dx: e.deltaX * k, dy: e.deltaY * k, m: mods(e) });
    }, { passive: false });
    im.addEventListener('contextmenu', e => { e.preventDefault(); if (T.tid) kbMenu(T, e, pos(e)); });
    const atalho = e => {   // atalhos de navegador na sua tela
        if (kani) return false;
        const c = e.ctrlKey && !e.altKey, k = e.key.toLowerCase();
        if (c && k === 't') kbNovaAba();
        else if (c && k === 'w') { if (KB.sel) kbCall('fechar', { aba: KB.sel }).then(kbEstado).catch(() => 0); }
        else if (c && k === 'l') kb$('#kb-url').focus();
        else if (c && k === 'd') kbFavoritar();
        else if (e.key === 'F5' || (c && k === 'r')) kbCall('navegar', { aba: KB.sel, acao: 'recarregar' }).catch(() => 0);
        else if (e.altKey && e.key === 'ArrowLeft') kbCall('navegar', { aba: KB.sel, acao: 'voltar' }).catch(() => 0);
        else if (e.altKey && e.key === 'ArrowRight') kbCall('navegar', { aba: KB.sel, acao: 'avancar' }).catch(() => 0);
        else return false;
        return true;
    };
    tec.addEventListener('keydown', e => {
        e.stopPropagation();
        if (e.key === 'Dead') { T.morto = true; return; }   // acento: a letra composta chega pelo "input"
        if (e.isComposing || e.key === 'Process' || (T.morto && e.key.length === 1)) { T.morto = false; return; }
        T.morto = false;
        if (e.key === 'Escape' && sobre.firstChild) { sobre.innerHTML = ''; e.preventDefault(); return; }
        e.preventDefault();
        if (atalho(e)) return;
        const txt = e.key.length === 1 ? e.key : e.key === 'Enter' ? '\r' : '';
        T.manda({ t: 'kd', key: e.key, code: e.code, vk: e.keyCode, m: mods(e), txt, rep: e.repeat });
    });
    tec.addEventListener('keyup', e => {
        e.stopPropagation();
        if (e.key === 'Dead' || e.key === 'Process') return;
        e.preventDefault();
        T.manda({ t: 'ku', key: e.key, code: e.code, vk: e.keyCode, m: mods(e) });
    });
    tec.addEventListener('compositionend', e => { if (e.data) T.manda({ t: 'txt', txt: e.data }); tec.value = ''; });
    tec.addEventListener('input', e => {   // texto que não veio por tecla (acento composto, colar do sistema, ditado)
        if (e.data && !e.isComposing && e.inputType !== 'insertCompositionText') T.manda({ t: 'txt', txt: e.data });
        tec.value = '';
    });
    tec.addEventListener('focus', () => raiz.classList.add('foco'));
    tec.addEventListener('blur', () => raiz.classList.remove('foco'));
    return T;
}

// a lista de opções que o Chrome desenharia fora da página
function kbLista(T, s) {
    const sobre = T.raiz.querySelector('.kb-sobre');
    sobre.querySelectorAll('.kb-lista').forEach(x => x.remove());
    const im = T.raiz.querySelector('.kb-vid'), r = im.getBoundingClientRect(), rr = T.raiz.getBoundingClientRect();
    const w = im.naturalWidth, h = im.naturalHeight, k = Math.min(r.width / w, r.height / h);
    const x0 = r.left - rr.left + (r.width - w * k) / 2, y0 = r.top - rr.top + (r.height - h * k) / 2;
    const L = document.createElement('div'); L.className = 'kb-lista';
    L.style.left = (x0 + s.x * w * k) + 'px'; L.style.top = (y0 + s.y * h * k) + 'px'; L.style.minWidth = Math.max(140, s.w * w * k) + 'px';
    let grupo = null;
    L.innerHTML = s.o.map(([t, off, g], i) => {
        const cab = g && g !== grupo ? `<div class="kb-lg">${kbEsc(g)}</div>` : '';
        grupo = g;
        return cab + `<button class="${i === s.i ? 'sel' : ''}" data-i="${i}" ${off ? 'disabled' : ''}>${kbEsc(t)}</button>`;
    }).join('');
    L.onclick = e => {
        const b = e.target.closest('button[data-i]'); if (!b) return;
        kbCall('escolher', { aba: T.tid, indice: +b.dataset.i }).catch(() => 0);
        L.remove(); T.raiz.querySelector('.kb-tec').focus();
    };
    sobre.appendChild(L);
    const b = L.getBoundingClientRect();
    if (b.bottom > rr.bottom) L.style.top = Math.max(4, rr.height - b.height - 4) + 'px';
    (L.querySelector('.sel') || L).scrollIntoView({ block: 'nearest' });
}

// botão direito: o menu do Chrome não aparece, então o nosso, com o que é útil
async function kbMenu(T, e, p) {
    const sobre = T.raiz.querySelector('.kb-sobre');
    sobre.querySelectorAll('.kb-menu').forEach(x => x.remove());
    const o = (await kbCall('ponto', { aba: T.tid, x: p.x, y: p.y }).catch(() => null)) || {};
    const it = [];
    if (o.link) it.push(['Abrir link em nova aba', () => kbNovaAba(o.link, true)], ['Copiar endereço do link', () => navigator.clipboard.writeText(o.link)]);
    if (o.img) it.push(['Salvar imagem em “' + kbDestinoNome() + '”', async () => {
        const r = await kbTenta(() => kbCall('baixar_imagens', { urls: [o.img], aba: T.tid, ...kbDestino() }));
        if (r) kbAviso(r.arquivos.length ? '✓ Imagem salva' : 'Não consegui baixar essa imagem', r.pasta);
    }], ['Copiar endereço da imagem', () => navigator.clipboard.writeText(o.img)]);
    if (o.sel) it.push(['Copiar', () => navigator.clipboard.writeText(o.sel)],
        ['Pesquisar “' + o.sel.slice(0, 24) + (o.sel.length > 24 ? '…' : '') + '”', () => kbNovaAba('https://www.google.com/search?q=' + encodeURIComponent(o.sel), true)]);
    if (it.length) it.push(null);
    it.push(['Voltar', () => kbCall('navegar', { aba: T.tid, acao: 'voltar' })], ['Avançar', () => kbCall('navegar', { aba: T.tid, acao: 'avancar' })],
        ['Recarregar', () => kbCall('navegar', { aba: T.tid, acao: 'recarregar' })]);
    if (!T.kani) it.push(null, ['Pegar imagens da página', () => kbPegar()], ['Print da página', () => kbPrint()]);
    const rr = T.raiz.getBoundingClientRect();
    const M = document.createElement('div'); M.className = 'kb-menu';
    M.style.left = (e.clientX - rr.left) + 'px'; M.style.top = (e.clientY - rr.top) + 'px';
    M.innerHTML = it.map((x, i) => x ? `<button data-i="${i}">${kbEsc(x[0])}</button>` : '<hr>').join('');
    M.onclick = ev => { const b = ev.target.closest('button'); if (!b) return; M.remove(); it[+b.dataset.i][1](); };
    sobre.appendChild(M);
    const b = M.getBoundingClientRect();
    if (b.right > rr.right) M.style.left = (rr.width - b.width - 4) + 'px';
    if (b.bottom > rr.bottom) M.style.top = (rr.height - b.height - 4) + 'px';
}

// avisos do site (alerta, confirmar, pergunta) e "escolher arquivo": no Kanivete, sobre a tela
function kbAvisosDaTela(T, v) {
    const sobre = T.raiz.querySelector('.kb-sobre');
    let d = sobre.querySelector('.kb-dlg');
    if (v && v.dialogo) {
        if (d) return;
        const g = v.dialogo;
        d = document.createElement('div'); d.className = 'kb-dlg';
        d.innerHTML = `<div class="kb-dlg-caixa"><small>${kbEsc((v.url.match(/^https?:\/\/([^/]+)/) || [])[1] || 'A página')} diz</small>
            <p>${kbEsc(g.texto)}</p>${g.tipo === 'prompt' ? `<input value="${kbEsc(g.padrao)}">` : ''}
            <div>${g.tipo === 'alert' ? '' : '<button class="btn-secondary kb-mini" data-r="0">Cancelar</button>'}<button class="btn-primary kb-mini" data-r="1">Ok</button></div></div>`;
        d.onclick = e => {
            const b = e.target.closest('button[data-r]'); if (!b) return;
            const inp = d.querySelector('input');
            kbCall('dialogo', { aba: T.tid, aceitar: b.dataset.r === '1', texto: inp ? inp.value : null }).catch(() => 0);
            d.remove();
        };
        sobre.appendChild(d);
    } else if (d) d.remove();
    if (v && v.arquivo && !T.escolhendo) {
        T.escolhendo = true;
        window.pywebview.api.select_file('kanibrowser').then(r =>
            kbCall('arquivo', { aba: T.tid, caminhos: r && r.success ? [r.path] : [] })).catch(() => 0).finally(() => { T.escolhendo = false; });
    }
}

// ---------- estado (2×/s com o painel à vista) ----------
async function kbEstado() {
    let e;
    try { e = await kbCall('estado', { vistas: [KB.sel, KB.kani].filter(Boolean) }); } catch (err) { return; }
    const eraAberto = KB.aberto;
    KB.aberto = e.aberto;
    kb$('#kb-status').textContent = e.aberto ? 'aberto' : 'fechado';
    kb$('#kb-status').classList.toggle('on', e.aberto);
    kb$('.kb-app').classList.toggle('fechado', !e.aberto);
    if (e.base) KB.base = e.base;
    if (!e.aberto) {
        KB.urlAtual = ''; if (KB.favs) kbEstrela();
        KB.abas = []; KB.sel = KB.kani = null; KB.tv.desligar(); KB.tk.desligar();
        KB.tv.vazio(`<img src="${(KPLUG.info(PLUGIN_ID) || {}).icone || ''}" alt=""><b>Seu navegador, dentro do Kanivete</b>
            <span>Logins guardados, nada de janela pulando na tela. A Kani trabalha ao lado, e você acompanha ao vivo.</span>
            <button class="btn-primary" id="kb-abrir">Abrir navegador</button>`);
        kb$('#kb-abrir').onclick = async () => { await kbTenta(() => kbCall('abrir', {})); kbEstado(); };
        KB.tk.vazio('');
        kbTabs(); kbKaniStatus(e);
        return;
    }
    KB.base = e.base;
    // abas na ordem em que apareceram; aba aberta pelo site (popup, link em nova aba) entra ao lado e fica à vista
    const ids = e.abas.map(a => a.id);
    KB.ordem = KB.ordem.filter(i => ids.includes(i));
    for (const a of e.abas) if (!KB.ordem.includes(a.id)) {
        const j = KB.ordem.indexOf(a.abriu);
        j >= 0 ? KB.ordem.splice(j + 1, 0, a.id) : KB.ordem.push(a.id);
        if (eraAberto && (a.abriu === KB.sel || KB.abrindo)) { KB.sel = a.id; KB.abrindo = false; kbCall('frente', { aba: a.id }).catch(() => 0); }
    }
    KB.abas = KB.ordem.map(i => e.abas.find(a => a.id === i));
    if (!KB.abas.some(a => a.id === KB.sel)) { KB.sel = KB.abas.length ? KB.abas[0].id : null; if (KB.sel) kbCall('frente', { aba: KB.sel }).catch(() => 0); }
    KB.kani = e.kani;
    kbTabs();
    const v = e.vistas[KB.sel];
    if (v) {
        const u = kb$('#kb-url');
        if (document.activeElement !== u) u.value = /^(about:blank|chrome:\/\/newtab)/.test(v.url) ? '' : v.url;
        kb$('.kb-cad').textContent = v.url.startsWith('https:') ? '🔒' : 'ⓘ';
        kb$('#kb-tv').classList.toggle('carregando', v.carregando);
        kb$('#kb-rec').classList.toggle('parar', v.carregando);
        kb$('#kb-rec').textContent = v.carregando ? '✕' : '⟳';
        KB.urlAtual = /^(about:blank|chrome:\/\/newtab)/.test(v.url) ? '' : v.url; KB.tituloAtual = v.titulo;
        kbEstrela();
    }
    KB.tv.vazio(KB.sel ? '' : `<b>Nenhuma aba aberta</b><button class="btn-primary" id="kb-nova0">+ Nova aba</button>`);
    if (!KB.sel) kb$('#kb-nova0').onclick = () => kbNovaAba();
    kbAvisosDaTela(KB.tv, v);
    kbAvisosDaTela(KB.tk, e.vistas[KB.kani]);
    kbKaniStatus(e);
    kbLigarTelas();
    for (const d of e.baixados || []) if (d.estado !== 'baixando' && !(KB.avisados || (KB.avisados = new Set())).has(d.id)) {
        KB.avisados.add(d.id);
        if (d.estado === 'pronto') kbAviso('⬇ Baixado: ' + d.nome, 'downloads');
    }
}

function kbLigarTelas() {
    const vis = kbPg().classList.contains('active') && !document.hidden && KB.aberto;
    vis && KB.sel ? KB.tv.ligar(KB.sel) : KB.tv.desligar();
    vis && KB.kani && !kb$('.kb-app').classList.contains('sem-kani') ? KB.tk.ligar(KB.kani) : KB.tk.desligar();
}

function kbTabs() {
    const t = kb$('#kb-tabs');
    const html = KB.abas.map(a => {
        const tit = a.titulo || a.url.replace(/^https?:\/\/(www\.)?/, '') || 'Nova aba';
        const dom = (a.url.match(/^https?:\/\/(?:www\.)?([^/])/) || [])[1] || '•';
        return `<div class="kb-tab${a.id === KB.sel ? ' sel' : ''}" data-id="${a.id}" title="${kbEsc(a.titulo)}\n${kbEsc(a.url)}">
            <i>${kbEsc(dom.toUpperCase())}</i><span>${kbEsc(tit)}</span><button data-x="${a.id}" title="Fechar (Ctrl+W)">✕</button></div>`;
    }).join('');
    if (t.dataset.h === html) return;
    t.dataset.h = html; t.innerHTML = html;
    t.querySelectorAll('.kb-tab').forEach(el => el.onpointerdown = ev => {
        if (ev.target.dataset.x) { kbCall('fechar', { aba: ev.target.dataset.x }).then(kbEstado).catch(() => 0); return; }
        if (ev.button === 1) { kbCall('fechar', { aba: el.dataset.id }).then(kbEstado).catch(() => 0); return; }
        KB.sel = el.dataset.id; kbCall('frente', { aba: KB.sel }).catch(() => 0);
        t.querySelectorAll('.kb-tab').forEach(x => x.classList.toggle('sel', x === el));
        kbLigarTelas(); kbEstado();
    });
}

function kbKaniStatus(e) {
    const faz = kb$('#kb-faz'), on = !!e.fazendo;
    faz.textContent = !e.aberto ? 'navegador fechado' : on ? e.fazendo + '…' : e.kani ? 'esperando' : 'parada';
    faz.classList.toggle('on', on);
    const vk = (e.vistas || {})[e.kani];
    kb$('#kb-kurl').textContent = vk ? (vk.titulo ? vk.titulo + ' — ' : '') + vk.url : '';
    KB.tk.vazio(e.aberto && !e.kani ? `<img src="identidade/kani.webp" alt=""><b>A Kani ainda não abriu nada</b>
        <span>Quando ela (ou o Claude) pesquisar, ler um site ou baixar material, aparece aqui ao vivo, sem mexer no seu navegador.</span>` : '');
    const p = kb$('#kb-kpilula');
    p.hidden = !(on && kb$('.kb-app').classList.contains('sem-kani'));
    p.textContent = 'Kani: ' + e.fazendo + '…';
    const h = (e.log || []).slice().reverse(), sig = h.map(x => x.t).join();
    if (sig !== KB.histSig) {
        KB.histSig = sig;
        kb$('#kb-hist').innerHTML = h.map(x => `<span class="kb-h"><i>${new Date(x.t * 1000).toTimeString().slice(0, 5)}</i>${kbEsc(x.o)}</span>`).join('');
    }
}

async function kbIr(url) {
    if (!KB.aberto || !KB.sel) return kbNovaAba(url);
    const id = await kbTenta(() => kbCall('visitar', { url, aba: KB.sel, mesma_aba: true }));
    if (id) KB.sel = id;
    kbEstado();
}

async function kbNovaAba(url, fundo) {
    if (!KB.aberto) { await kbTenta(() => kbCall('abrir', { url: url || 'https://www.google.com/' })); return kbEstado(); }
    const r = await kbTenta(() => kbCall('nova', { url: url || 'https://www.google.com/' }));
    if (r && !fundo) { KB.sel = r.id; kbCall('frente', { aba: r.id }).catch(() => 0); }
    await kbEstado();
    if (!url && !fundo) kb$('#kb-url').focus();
}

// ---------- destino, imagens, print ----------
async function kbDestinos() {
    KB.destinos = await kbCall('destinos').catch(() => KB.destinos) || [];
    const s = kb$('#kb-dest');
    s.innerHTML = KB.destinos.map(d => `<option value="d:${d.id}">${kbEsc(d.cliente)} · ${kbEsc(d.nome)}</option>`).join('') +
        (KB.dest && KB.dest.startsWith('p:') ? `<option value="${kbEsc(KB.dest)}">${kbEsc(KB.dest.slice(2))}</option>` : '') +
        '<option value="kb">Downloads do KaniBrowser</option><option value="escolher">Escolher pasta…</option>';
    if (KB.dest) s.value = KB.dest;
    KB.dest = s.value;
}

function kbDestino() {
    const v = KB.dest || 'kb';
    return v.startsWith('d:') ? { demanda: v.slice(2) } : v.startsWith('p:') ? { pasta: v.slice(2) } : {};
}

function kbDestinoNome() { const s = kb$('#kb-dest'); return s && s.selectedOptions[0] ? s.selectedOptions[0].textContent.split(' · ').pop() : 'Downloads'; }

function kbGaveta(titulo, html) {
    const g = kb$('#kb-gaveta');
    g.hidden = false;
    g.innerHTML = `<div class="kb-gv-topo"><b>${kbEsc(titulo)}</b><button class="kb-ico" id="kb-gv-x" title="Fechar">✕</button></div>
      <div class="kb-grade" id="kb-grade">${html}</div>
      <div class="kb-rodape" id="kb-rodape" hidden><span id="kb-cont"></span>
        <button class="btn-secondary kb-mini" id="kb-todas">Marcar todas</button>
        <button class="btn-primary kb-mini" id="kb-baixar">⬇ Baixar</button></div>`;
    g.querySelector('#kb-gv-x').onclick = kbGavetaFechar;
}

function kbGavetaFechar() { const g = kb$('#kb-gaveta'); g.hidden = true; g.innerHTML = ''; }

async function kbPegar() {
    if (!KB.sel) return;
    const a = KB.abas.find(x => x.id === KB.sel) || {};
    kbGaveta(a.titulo || 'Imagens', '<div class="kb-vazio">Procurando imagens…</div>');
    kbGrade((await kbTenta(() => kbCall('imagens', { aba: KB.sel }))) || []);
}

function kbGrade(lista) {
    const g = kb$('#kb-grade'); if (!g) return;
    KB.imgs = lista; KB.marcadas.clear();
    g.innerHTML = KB.imgs.map((im, i) => `
        <label class="kb-img"><input type="checkbox" data-i="${i}"><img src="${kbEsc(im.url)}" loading="lazy" referrerpolicy="no-referrer">
          <small>${im.link ? 'post' : im.w + '×' + im.h}</small></label>`).join('') || '<div class="kb-vazio">Nenhuma imagem grande nesta página.</div>';
    g.querySelectorAll('input').forEach(c => c.onchange = () => { c.checked ? KB.marcadas.add(+c.dataset.i) : KB.marcadas.delete(+c.dataset.i); kbConta(); });
    const rod = kb$('#kb-rodape'); rod.hidden = !KB.imgs.length;
    rod.querySelector('#kb-todas').onclick = () => { g.querySelectorAll('input').forEach(c => { c.checked = true; KB.marcadas.add(+c.dataset.i); }); kbConta(); };
    rod.querySelector('#kb-baixar').onclick = () => kbBaixar();
    kbConta();
}

function kbConta() { const c = kb$('#kb-cont'); if (c) c.textContent = `${KB.marcadas.size} de ${KB.imgs.length} → ${kbDestinoNome()}`; }

async function kbBaixar() {
    if (!KB.marcadas.size) return;
    const b = kb$('#kb-baixar'); b.disabled = true; b.textContent = 'Baixando…';
    const urls = [...KB.marcadas].map(i => KB.imgs[i].url);
    const r = await kbTenta(() => kbCall('baixar_imagens', { urls, aba: KB.sel, ...kbDestino() }));
    b.disabled = false; b.textContent = '⬇ Baixar';
    if (r) kbAviso(`✓ ${r.arquivos.length} salva(s)${r.falhas.length ? `, ${r.falhas.length} falharam` : ''}`, r.pasta);
}

async function kbPrint() {
    if (!KB.sel) return;
    const d = kbDestino();
    let pasta = d.pasta;
    if (d.demanda) pasta = (KB.destinos.find(x => x.id === d.demanda) || {}).pasta + '\\02 - ASSETS\\REFERENCIAS';
    const nome = `print_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.png`;
    const r = await kbTenta(() => kbCall('foto', { aba: KB.sel, caminho: (pasta || 'D:\\Kanivete\\KaniBrowser\\downloads') + '\\' + nome, inteira: true }));
    if (r) kbAviso('✓ Print salvo', r.replace(/\\[^\\]+$/, ''));
}

// ---------- barra de favoritos (favoritos.json: fica salva entre aberturas) ----------
async function kbFavs(lista) {
    if (lista) KB.favs = lista;
    else KB.favs = await kbCall('favoritos').catch(() => KB.favs || []) || [];
    const bar = kb$('#kb-favs'), ib = (KB.base || '').replace(/\/v\/$/, '/i/');
    bar.innerHTML = KB.favs.map((f, i) => `<button class="kb-fav" draggable="true" data-i="${i}" title="${kbEsc(f.nome)}
${kbEsc(f.url)}">
        ${f.icone && ib ? `<img src="${ib}${kbEsc(f.icone)}.png" alt="">` : `<i>${kbEsc((f.nome || '?')[0].toUpperCase())}</i>`}<span>${kbEsc(f.nome)}</span></button>`).join('')
        || '<span class="kb-fav-dica">☆ no endereço guarda a página aqui</span>';
    if (KB.favs.some(f => !f.icone) && !KB.favTenta) { KB.favTenta = 1; setTimeout(() => kbFavs(), 4000); }   // ícones baixando
    bar.querySelectorAll('.kb-fav').forEach(b => {
        const f = KB.favs[+b.dataset.i];
        b.onclick = e => (e.ctrlKey || e.shiftKey) ? kbNovaAba(f.url, e.ctrlKey) : kbIr(f.url);
        b.onauxclick = e => { if (e.button === 1) { e.preventDefault(); kbNovaAba(f.url, true); } };
        b.oncontextmenu = e => { e.preventDefault(); kbFavMenu(b, f, e); };
        b.ondragstart = e => { KB.arrasta = +b.dataset.i; e.dataTransfer.effectAllowed = 'move'; };
        b.ondragover = e => { e.preventDefault(); b.classList.add('alvo'); };
        b.ondragleave = () => b.classList.remove('alvo');
        b.ondrop = async e => {
            e.preventDefault(); b.classList.remove('alvo');
            const de = KB.arrasta, para = +b.dataset.i; if (de == null || de === para) return;
            const l = KB.favs.slice(); const [x] = l.splice(de, 1); l.splice(para, 0, x);
            kbFavs(await kbCall('favoritos_ordem', { urls: l.map(f => f.url) }).catch(() => null));
        };
    });
    kbEstrela();
}

function kbEstrela() {
    const st = kb$('#kb-estrela'), on = !!KB.urlAtual && (KB.favs || []).some(f => f.url === KB.urlAtual);
    st.textContent = on ? '★' : '☆'; st.classList.toggle('on', on); st.hidden = !KB.urlAtual;
    st.title = on ? 'Tirar dos favoritos (Ctrl+D)' : 'Favoritar esta página (Ctrl+D)';
}

async function kbFavoritar() {
    if (!KB.urlAtual) return;
    const nome = (KB.tituloAtual || '').split(/ [-|–·] /)[0].trim().slice(0, 30);
    kbFavs(await kbCall('favorito', { url: KB.urlAtual, nome: nome || null }).catch(() => null));
}

function kbFavMenu(b, f, e) {
    kbPg().querySelectorAll('.kb-favmenu').forEach(x => x.remove());
    const M = document.createElement('div'); M.className = 'kb-menu kb-favmenu';
    const ra = kb$('.kb-app').getBoundingClientRect();
    M.style.left = (e.clientX - ra.left) + 'px'; M.style.top = (e.clientY - ra.top) + 'px';
    M.innerHTML = '<button data-a="nova">Abrir em nova aba</button><button data-a="ren">Renomear</button><hr><button data-a="rem">Remover</button>';
    M.onclick = async ev => {
        const a = (ev.target.closest('button') || {}).dataset?.a; if (!a) return;
        M.remove();
        if (a === 'nova') kbNovaAba(f.url);
        else if (a === 'rem') kbFavs(await kbCall('favorito_remover', { url: f.url }).catch(() => null));
        else if (a === 'ren') {
            const sp = b.querySelector('span'), inp = document.createElement('input');
            inp.className = 'kb-fav-ren'; inp.value = f.nome; sp.replaceWith(inp); inp.focus(); inp.select();
            let feito = false;
            const fim = async ok => {
                if (feito) return; feito = true;
                kbFavs(ok && inp.value.trim() ? await kbCall('favorito_renomear', { url: f.url, nome: inp.value }).catch(() => null) : null);
            };
            inp.onkeydown = ev2 => { ev2.stopPropagation(); if (ev2.key === 'Enter') fim(true); if (ev2.key === 'Escape') fim(false); };
            inp.onblur = () => fim(true);
            inp.onclick = ev2 => ev2.stopPropagation();
        }
    };
    kb$('.kb-app').appendChild(M);
    setTimeout(() => document.addEventListener('pointerdown', function fora(ev) { if (!M.contains(ev.target)) { M.remove(); document.removeEventListener('pointerdown', fora, true); } }, true), 0);
}

kbMontar();
kbEstado().then(() => kbFavs());
(function kbLaco() {   // 2×/s com o painel à vista; parado (e sem transmissão) fora dele
    const vis = kbPg().classList.contains('active') && !document.hidden;
    if (vis) kbEstado(); else kbLigarTelas();
    setTimeout(kbLaco, vis ? 500 : 1500);
})();
