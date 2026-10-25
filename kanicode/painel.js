// Lobby do KaniCode no KANIVETE (recebe KPLUG e PLUGIN_ID), no padrão dos lobbys das ferramentas (lobby.js: cartão com
// arte + logo + ações, seções embaixo, fundo = vídeo do Início tingido na cor). O KaniCode em si roda à parte
// (kanicode.py): aqui só abre/fecha, mostra se está rodando, cria os atalhos do Windows e guarda "abrir junto".
const KC = { timer: 0, on: null };
const kcCall = (f, a) => KPLUG.chamar(PLUGIN_ID, f, a);
const kcPg = () => KPLUG.pagina(PLUGIN_ID);
const kcEl = s => kcPg().querySelector(s);
const kcGuarda = (k, v) => { try { v === undefined ? (v = localStorage.getItem(k)) : localStorage.setItem(k, v); } catch (e) { v = null; } return v; };
const KC_OPCOES = [
    ['desktop', 'Atalho na área de trabalho', 'Abre o KaniCode sem o KANIVETE. Para fixar na barra de tarefas: botão direito no atalho › Fixar na barra de tarefas.'],
    ['menu', 'No menu Iniciar', 'Aparece ao buscar "KaniCode" no Iniciar (dá para fixar por lá também).'],
    ['inicio', 'Iniciar com o Windows', 'Ao ligar o PC, só a bolinha aparece; a conversa abre no clique.'],
    ['auto', 'Abrir junto com o KANIVETE', 'Ao abrir o KANIVETE, a bolinha aparece se estiver fechada.'],
];
const KC_DICAS = [
    ['Clique na bolinha', 'abre e recolhe a conversa'], ['Arraste', 'muda a bolinha de lugar'],
    ['📌 na janela', 'fica sempre por cima'], ['Esc', 'recolhe a conversa'],
    ['📝 Planejar', 'o Claude mostra o plano antes de mexer'], ['Mandar agora', 'recado no meio da tarefa'],
];

function kcMontar() {
    const info = KPLUG.info(PLUGIN_ID) || {};
    const pg = kcPg();
    pg.innerHTML = `
      <section class="kl kl-com-fundo kc-lobby" style="--kl-cor:#B6F23A;--kl-top:0px">
        <div class="kl-fundo" aria-hidden="true"><video muted loop playsinline tabindex="-1"></video><i class="kl-veu"></i></div>
        <div class="kl-inner">
          <div class="kl-hero kc-hero">
            <div class="kc-arte" aria-hidden="true"><span>&gt;<i></i></span></div>
            <div class="kl-hero-txt">
              ${info.logo ? `<img class="kc-logo" src="${info.logo}" alt="KaniCode">` : '<span class="app-logo app-logo-grande" style="background:#B6F23A;color:#0E1110">Kc</span>'}
              <h2>Converse com o Claude</h2>
              <p>Uma bolinha verde na área de trabalho, por cima de tudo. Funciona sozinha: não precisa do KANIVETE aberto
                e continua aberta se ele fechar ou reiniciar.</p>
              <div class="kc-linha"><span class="kc-ponto" id="kc-ponto"></span><span id="kc-status">verificando…</span></div>
            </div>
            <div class="kl-acoes">
              <button class="ie-btn ie-btn-primario kl-novo" id="kc-abrir">Abrir KaniCode</button>
              <div class="kl-mais"><button class="ie-btn" id="kc-fechar">Fechar</button></div>
            </div>
          </div>
          <div class="ie-recentes kc-sec">
            <div class="ie-recentes-tit">Atalhos e início</div>
            <div class="kc-opcoes">${KC_OPCOES.map(([k, t, d]) => `
              <label class="kc-op"><span class="kc-chave"><input type="checkbox" data-kc="${k}"><i></i></span>
                <span><b>${t}</b><small>${d}</small></span></label>`).join('')}</div>
          </div>
          <div class="ie-recentes kc-sec">
            <div class="ie-recentes-tit">Como usar</div>
            <div class="kc-dicas">${KC_DICAS.map(([a, b]) => `<div><b>${a}</b><small>${b}</small></div>`).join('')}</div>
          </div>
        </div>
      </section>`;
    kcEl('#kc-abrir').onclick = async () => { await kcCall('abrir').catch(e => toast(e.message, 'erro')); kcEstado(); setTimeout(kcEstado, 2500); };
    kcEl('#kc-fechar').onclick = async () => { await kcCall('fechar').catch(() => {}); setTimeout(kcEstado, 600); };
    pg.querySelectorAll('[data-kc]').forEach(c => c.onchange = async () => {
        const k = c.dataset.kc;
        if (k === 'auto') { kcGuarda('kc-auto', c.checked ? '1' : '0'); return; }
        c.disabled = true;
        try { kcAtalhos(await kcCall('atalho', { lugar: k, ligar: c.checked })); toast(c.checked ? 'Atalho criado' : 'Atalho removido'); }
        catch (e) { c.checked = !c.checked; toast('Atalho: ' + e.message, 'erro'); }
        c.disabled = false;
    });
    kcEl('[data-kc="auto"]').checked = kcGuarda('kc-auto') === '1';
    kcCall('atalhos').then(kcAtalhos).catch(() => {});
    // fundo: só toca com a aba à vista (mesma regra dos outros lobbys)
    const v = kcEl('.kl-fundo video');
    kcCall('fundo').then(u => { v.src = u; if (pg.classList.contains('active')) v.play().catch(() => {}); }).catch(() => {});
    new IntersectionObserver(es => es.forEach(e => e.isIntersecting && !document.hidden ? v.play().catch(() => {}) : v.pause())).observe(v);
}

function kcAtalhos(e) {
    for (const k of ['desktop', 'menu', 'inicio']) { const c = kcEl(`[data-kc="${k}"]`); if (c && e) c.checked = !!e[k]; }
}

async function kcEstado() {
    let e = null;
    try { e = await kcCall('estado'); } catch (x) { /* plugin sem Python */ }
    const on = !!(e && e.rodando);
    if (on === KC.on) return;   // nada mudou: não mexe no DOM
    KC.on = on;
    kcEl('#kc-status').textContent = on ? 'Aberto na área de trabalho' : 'Fechado';
    kcEl('#kc-ponto').classList.toggle('on', on);
    kcEl('#kc-abrir').textContent = on ? 'Mostrar a conversa' : 'Abrir KaniCode';
    kcEl('#kc-fechar').disabled = !on;
}

kcMontar();
// A observação continua mesmo quando o lobby não está à vista; não consulta o CDP do app.
kcCall('progresso_observador').then(codigo => new Function('KPLUG', 'PLUGIN_ID', codigo)(KPLUG, PLUGIN_ID)).catch(() => {});
kcEstado();
// o painel só pergunta o estado com a aba à vista (nada rodando com o app parado)
KC.timer = setInterval(() => { if (kcPg() && kcPg().classList.contains('active') && !document.hidden) kcEstado(); }, 3000);
// "Abrir junto com o KANIVETE": só a bolinha, sem puxar a janela da conversa se ela já estava aberta
if (kcGuarda('kc-auto') === '1') kcCall('garantir').then(kcEstado).catch(() => {});
