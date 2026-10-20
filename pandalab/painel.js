// Painel do plugin Pandalab (roda dentro do KANIVETE; recebe KPLUG e PLUGIN_ID). Leitura livre; criar pede confirmação.
const PL = { status: 'abertas', busca: '', cliente: '', lista: [], sel: null, tipos: {}, clientes: [] };
const plSt = { todo: 'A fazer', in_progress: 'Em andamento', adjustment: 'Ajuste', done: 'Feita' };
const plEsc = t => _escHtml(t == null ? '' : String(t));
const plCall = (f, a) => KPLUG.chamar(PLUGIN_ID, f, a);
const plPg = () => document.getElementById('pl-painel');
const PL_SITE = (() => { try { return localStorage.getItem('pl-site') || 'https://laboratoriopanda.com'; } catch (e) { return 'https://laboratoriopanda.com'; } })();   // pl-site: só para testar uma cópia local do sistema

// Casca da aba: "Sistema" = o próprio site do Pandalab (espelho, com login e tudo) | "Pastas" = painel do Kanivete
function plCasca() {
    const raiz = KPLUG.pagina(PLUGIN_ID);
    const logo = KPLUG.info(PLUGIN_ID).logo;
    raiz.innerHTML = `
      <div class="pl-casca">
        <div class="pl-barra">
          ${logo ? `<img class="pl-logo" src="${logo}" alt="Pandalab">` : '<b>Pandalab</b>'}
          <div class="pl-modos">
            <button class="pl-modo on" data-m="sistema">Sistema</button>
            <button class="pl-modo" data-m="pastas">Pastas e material</button>
          </div>
          <button class="btn-secondary pl-mini" id="pl-site-recarregar" title="Recarregar o sistema">↻</button>
        </div>
        <div class="pl-corpo">
          <iframe id="pl-site" src="${PL_SITE}" allow="clipboard-read; clipboard-write; microphone; camera; fullscreen; autoplay"></iframe>
          <div id="pl-painel" hidden></div>
        </div>
      </div>`;
    const modo = m => {
        raiz.querySelectorAll('.pl-modo').forEach(b => b.classList.toggle('on', b.dataset.m === m));
        raiz.querySelector('#pl-site').hidden = m !== 'sistema';
        raiz.querySelector('#pl-painel').hidden = m !== 'pastas';
        raiz.querySelectorAll('.pl-mini').forEach(b => b.hidden = m !== 'sistema');
        if (m === 'pastas' && !PL.iniciado) { PL.iniciado = true; plIniciar(); }
    };
    raiz.querySelectorAll('.pl-modo').forEach(b => b.onclick = () => modo(b.dataset.m));
    raiz.querySelector('#pl-site-recarregar').onclick = () => { raiz.querySelector('#pl-site').src = raiz.querySelector('#pl-site').src; };
    PL.modo = modo;
}
window.PL_API = { PL, listar: () => plListar(), abrir: id => plAbrir(id), modo: m => PL.modo(m) };

async function plIniciar() {
    const e = await plCall('estado').catch(() => ({ logado: false }));
    if (!e.logado) return plTelaLogin();
    PL.quem = e.nome;
    [PL.tipos, PL.clientes] = await Promise.all([plCall('tipos'), plCall('clientes')]);
    plPg().innerHTML = `
      <div class="pl-app">
        <div class="pl-col">
          <div class="pl-topo"><h2>Demandas<span class="pl-sub">baixar para a pasta do cliente</span></h2>
            <span class="pl-quem">${plEsc(PL.quem)}</span>
            <button class="btn-secondary" id="pl-nova">+ Nova</button>
            <button class="btn-secondary" id="pl-atualizar" title="Atualizar">↻</button></div>
          <div class="pl-filtros">
            ${['abertas', 'todo', 'in_progress', 'adjustment', 'done', ''].map(s =>
                `<button class="pl-chip${s === PL.status ? ' on' : ''}" data-s="${s}">${s === 'abertas' ? 'Abertas' : s ? plSt[s] : 'Todas'}</button>`).join('')}
            <select id="pl-cli"><option value="">Todos os clientes</option>${PL.clientes.map(c =>
                `<option value="${plEsc(c.name)}">${plEsc(c.name)}</option>`).join('')}</select>
            <input id="pl-busca" placeholder="Buscar título…">
          </div>
          <div class="pl-lista" id="pl-lista"></div>
        </div>
        <div class="pl-col"><div class="pl-det" id="pl-det"><div class="pl-vazio">Escolha uma demanda</div></div></div>
      </div>`;
    const pg = plPg();
    pg.querySelectorAll('.pl-chip').forEach(b => b.onclick = () => {
        PL.status = b.dataset.s; pg.querySelectorAll('.pl-chip').forEach(x => x.classList.toggle('on', x === b)); plListar(); });
    pg.querySelector('#pl-cli').onchange = e => { PL.cliente = e.target.value; plListar(); };
    let t; pg.querySelector('#pl-busca').oninput = e => { clearTimeout(t); t = setTimeout(() => { PL.busca = e.target.value; plListar(); }, 300); };
    pg.querySelector('#pl-atualizar').onclick = () => plListar();
    pg.querySelector('#pl-nova').onclick = () => plTelaNova();
    plListar();
}

function plTelaLogin(msg) {
    plPg().innerHTML = `<div class="pl-login">
        ${KPLUG.info(PLUGIN_ID).logo ? `<img class="pl-logo" src="${KPLUG.info(PLUGIN_ID).logo}" alt="Pandalab">` : '<h2 style="margin:0">Pandalab</h2>'}<div class="pl-quem">Entrar com o seu usuário do sistema (a senha não fica guardada).</div>
        <input id="pl-u" placeholder="usuário ou e-mail"><input id="pl-s" type="password" placeholder="senha">
        <button class="btn-primary" id="pl-entrar">Entrar</button><div class="pl-msg">${plEsc(msg || '')}</div></div>`;
    const ir = async () => {
        try { await plCall('entrar', { usuario: plPg().querySelector('#pl-u').value, senha: plPg().querySelector('#pl-s').value }); plIniciar(); }
        catch (e) { plTelaLogin(e.message); }
    };
    plPg().querySelector('#pl-entrar').onclick = ir;
    plPg().querySelector('#pl-s').onkeydown = e => { if (e.key === 'Enter') ir(); };
}

async function plListar() {
    const box = plPg().querySelector('#pl-lista');
    if (!box) return;
    box.innerHTML = '<div class="pl-vazio">Carregando…</div>';
    try { PL.lista = await plCall('listar', { status: PL.status, cliente: PL.cliente, busca: PL.busca }); }
    catch (e) { box.innerHTML = `<div class="pl-vazio">${plEsc(e.message)}</div>`; return; }
    box.innerHTML = PL.lista.length ? PL.lista.map(d => `
        <div class="pl-card${d.id === PL.sel ? ' sel' : ''}" data-id="${d.id}">
          <b>${d.is_urgent ? '🔥 ' : ''}${plEsc(d.title)}</b>
          <div class="pl-meta"><span class="pl-tag">${plEsc(d.custom_creative_type_name || PL.tipos[d.content_type] || d.content_type)}</span>
            <span class="pl-st ${d.status}">${plSt[d.status] || d.status}</span>
            <span>${plEsc(d.client?.name || '—')}</span><span>${(d.created_at || '').slice(0, 10)}</span></div>
        </div>`).join('') : '<div class="pl-vazio">Nenhuma demanda</div>';
    box.querySelectorAll('.pl-card').forEach(c => c.onclick = () => plAbrir(c.dataset.id));
}

async function plAbrir(id) {
    PL.sel = id;
    plPg().querySelectorAll('.pl-card').forEach(c => c.classList.toggle('sel', c.dataset.id === id));
    const det = plPg().querySelector('#pl-det');
    det.innerHTML = '<div class="pl-vazio">Carregando…</div>';
    let d;
    try { d = await plCall('detalhe', { id }); } catch (e) { det.innerHTML = `<div class="pl-vazio">${plEsc(e.message)}</div>`; return; }
    det.innerHTML = `
      <h3>${plEsc(d.title)}</h3>
      <div class="pl-meta"><span class="pl-tag">${plEsc(d.custom_creative_type_name || PL.tipos[d.content_type] || d.content_type)}</span>
        <span class="pl-st ${d.status}">${plSt[d.status] || d.status}</span><span>${plEsc(d.client?.name || '—')}</span>
        <span>criada ${(d.created_at || '').slice(0, 16).replace('T', ' ')}</span></div>
      <div class="pl-acoes">
        <button class="btn-primary" id="pl-baixar">⬇ Baixar para a pasta do cliente</button>
        <button class="btn-secondary" id="pl-abrir" ${d.pasta_existe ? '' : 'disabled'}>📁 Abrir pasta</button>
        <button class="btn-secondary" id="pl-copiar">Copiar briefing</button>
        <select id="pl-st" title="Mudar o status no Pandalab">${['todo', 'in_progress', 'adjustment'].map(s =>
            `<option value="${s}"${s === d.status ? ' selected' : ''}>${plSt[s]}</option>`).join('')}${d.status === 'done' ? '<option selected>Feita</option>' : ''}</select>
      </div>
      <div class="pl-pasta" id="pl-pasta">${d.pasta ? (d.pasta_existe ? 'Pasta: ' : 'Vai para: ') + plEsc(d.pasta) : 'Cliente sem pasta no mapa (mapa_clientes.json)'}</div>
      <h4>Descrição</h4><div class="pl-desc">${plEsc(d.description || '(vazia)')}</div>
      <h4>Material (${d.arquivos.length})</h4>${d.arquivos.map(a => `<div class="pl-com">${plEsc(a.file_name)} <small>${Math.round((a.file_size || 0) / 1024)} KB</small></div>`).join('') || '<div class="pl-quem">Nenhum arquivo</div>'}
      <h4>Comentários (${d.comentarios.length})</h4>${d.comentarios.map(c => `<div class="pl-com"><small>${(c.created_at || '').slice(0, 16).replace('T', ' ')} · ${plEsc(c.cliente?.name || c.equipe?.name || '')}</small><br>${plEsc(c.comment_text)}</div>`).join('') || '<div class="pl-quem">Nenhum comentário</div>'}
      <form class="pl-comentar" id="pl-cf"><input id="pl-ct" placeholder="Escrever um comentário (a equipe vê)…"><button class="btn-secondary">Enviar</button></form>`;
    const confirma = (titulo, texto) => appConfirm({ titulo, texto, botoes: [{ rotulo: 'Cancelar', valor: 0, tipo: 'secundario' }, { rotulo: 'Confirmar', valor: 1, tipo: 'primario' }] });
    det.querySelector('#pl-st').onchange = async e => {
        const st = e.target.value;
        if (!(await confirma('Mudar status no Pandalab?', `"${d.title}" → ${plSt[st]}. A equipe vê na hora.`))) { e.target.value = d.status; return; }
        try { await plCall('mudar_status', { id, status: st }); d.status = st; plListar(); } catch (err) { alertaKplug(err.message); e.target.value = d.status; }
    };
    det.querySelector('#pl-cf').onsubmit = async e => {
        e.preventDefault();
        const t = det.querySelector('#pl-ct').value.trim(); if (!t) return;
        if (!(await confirma('Enviar comentário?', t))) return;
        try { await plCall('comentar', { id, texto: t }); plAbrir(id); } catch (err) { alertaKplug(err.message); }
    };
    det.querySelector('#pl-baixar').onclick = async e => {
        e.target.disabled = true; e.target.textContent = 'Baixando…';
        try {
            const r = await plCall('baixar', { id });
            det.querySelector('#pl-pasta').textContent = `Pasta: ${r.pasta} — ${r.arquivos.length} arquivo(s) + BRIEFING.txt`;
            det.querySelector('#pl-abrir').disabled = false; e.target.textContent = '✓ Baixado';
        } catch (err) { e.target.textContent = 'Falhou: ' + err.message; e.target.disabled = false; }
    };
    det.querySelector('#pl-abrir').onclick = () => plCall('abrir_pasta', { id }).catch(err => alertaKplug(err.message));
    det.querySelector('#pl-copiar').onclick = e => {
        navigator.clipboard.writeText(`${d.title}\n${d.client?.name || ''}\n\n${d.description || ''}`);
        e.target.textContent = '✓ Copiado';
    };
}

function alertaKplug(t) { appConfirm({ titulo: 'Pandalab', texto: t, botoes: [{ rotulo: 'Ok', valor: 1, tipo: 'primario' }] }); }

function plTelaNova() {
    const det = plPg().querySelector('#pl-det');
    det.innerHTML = `<h3>Nova demanda</h3><div class="pl-form">
        <input id="pl-n-tit" placeholder="Título">
        <select id="pl-n-cli">${PL.clientes.map(c => `<option value="${c.id}">${plEsc(c.name)}</option>`).join('')}</select>
        <select id="pl-n-tipo">${Object.entries(PL.tipos).map(([k, v]) => `<option value="${k}">${plEsc(v)}</option>`).join('')}</select>
        <textarea id="pl-n-desc" placeholder="Descrição / briefing (texto das páginas, referências…)"></textarea>
        <div class="pl-quem">Arquivos: anexe pelo site depois (lá eles sobem para o Drive do cliente).</div>
        <button class="btn-primary" id="pl-n-ok">Criar no Pandalab</button><div class="pl-msg" id="pl-n-msg"></div></div>`;
    det.querySelector('#pl-n-ok').onclick = async () => {
        const v = s => det.querySelector(s).value.trim();
        const tit = v('#pl-n-tit'), cli = det.querySelector('#pl-n-cli');
        if (!tit) { det.querySelector('#pl-n-msg').textContent = 'Falta o título.'; return; }
        const ok = await appConfirm({ titulo: 'Criar demanda no Pandalab?',
            texto: `"${tit}" para ${cli.options[cli.selectedIndex].text}. A equipe vê na hora.`,
            botoes: [{ rotulo: 'Cancelar', valor: 0, tipo: 'secundario' }, { rotulo: 'Criar', valor: 1, tipo: 'primario' }] });
        if (!ok) return;
        try {
            await plCall('criar', { titulo: tit, cliente_id: cli.value, tipo: v('#pl-n-tipo'), descricao: v('#pl-n-desc') });
            plListar(); det.innerHTML = '<div class="pl-vazio">✓ Demanda criada</div>';
        } catch (e) { det.querySelector('#pl-n-msg').textContent = e.message; }
    };
}

plCasca();

// Pedidos do próprio site (botão "Baixar no Kanivete" na demanda, src/lib/kanivete.ts do sistema): só aceita do site.
window.addEventListener('message', async e => {
    if (e.origin !== PL_SITE || !e.data || !/^kanivete-(baixar|abrir|arquivos)$/.test(e.data.tipo || '')) return;
    const responder = r => e.source && e.source.postMessage({ tipo: 'kanivete-resposta', pedido: e.data.pedido, ...r }, e.origin);
    try {
        if (e.data.tipo === 'kanivete-arquivos') {   // finais para a janela de entrega do site
            const r = await plCall('finais', { id: String(e.data.id), conteudo: true });
            responder({ ok: true, pasta: r.pasta, dados: r.dados });
        } else if (e.data.tipo === 'kanivete-baixar') {
            const r = await plCall('baixar', { id: String(e.data.id) });
            responder({ ok: true, pasta: r.pasta, arquivos: r.arquivos.length });
        } else {
            responder({ ok: true, pasta: await plCall('abrir_pasta', { id: String(e.data.id) }) });
        }
    } catch (err) { responder({ ok: false, erro: err.message }); }
});
