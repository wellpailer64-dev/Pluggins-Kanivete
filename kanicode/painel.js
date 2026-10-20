// Painel do KaniCode no KANIVETE (recebe KPLUG e PLUGIN_ID). O KaniCode em si roda à parte (kanicode.py): aqui só
// abre/fecha, mostra se está rodando e guarda "abrir junto com o KANIVETE".
const KC = { timer: 0 };
const kcCall = (f, a) => KPLUG.chamar(PLUGIN_ID, f, a);
const kcPg = () => KPLUG.pagina(PLUGIN_ID);
const kcGuarda = (k, v) => { try { v === undefined ? (v = localStorage.getItem(k)) : localStorage.setItem(k, v); } catch (e) { v = null; } return v; };

function kcMontar() {
    const info = KPLUG.info(PLUGIN_ID) || {};
    kcPg().innerHTML = `
      <div class="kc-app">
        ${info.logo ? `<img class="kc-logo" src="${info.logo}" alt="KaniCode">` : '<h2>KaniCode</h2>'}
        <p class="kc-desc">Converse com o Claude numa bolinha verde na área de trabalho. Ela fica por cima de tudo e
          continua aberta mesmo se o KANIVETE fechar ou reiniciar.</p>
        <div class="kc-linha"><span class="kc-ponto" id="kc-ponto"></span><span id="kc-status">verificando…</span></div>
        <div class="kc-botoes">
          <button class="btn-primary" id="kc-abrir">Abrir KaniCode</button>
          <button class="btn-secondary" id="kc-fechar">Fechar</button>
        </div>
        <label class="kc-op"><input type="checkbox" id="kc-auto"> Abrir junto com o KANIVETE</label>
        <ul class="kc-dicas">
          <li>Clique na bolinha: abre e recolhe a conversa. Arraste: muda de lugar.</li>
          <li>📌 na janela: sempre por cima. Esc: recolhe.</li>
          <li>Etapa 1 (esqueleto): a conversa com o Claude chega na etapa 2.</li>
        </ul>
      </div>`;
    kcPg().querySelector('#kc-abrir').onclick = async () => { await kcCall('abrir').catch(e => toast(e.message, 'erro')); kcEstado(); setTimeout(kcEstado, 2500); };
    kcPg().querySelector('#kc-fechar').onclick = async () => { await kcCall('fechar').catch(() => {}); setTimeout(kcEstado, 600); };
    const auto = kcPg().querySelector('#kc-auto');
    auto.checked = kcGuarda('kc-auto') === '1';
    auto.onchange = () => kcGuarda('kc-auto', auto.checked ? '1' : '0');
}

async function kcEstado() {
    let e = null;
    try { e = await kcCall('estado'); } catch (x) { /* plugin sem Python */ }
    const on = !!(e && e.rodando);
    const st = kcPg().querySelector('#kc-status'), pt = kcPg().querySelector('#kc-ponto');
    if (st) st.textContent = on ? 'aberto na área de trabalho' : 'fechado';
    if (pt) pt.classList.toggle('on', on);
}

kcMontar();
kcEstado();
// o painel só pergunta o estado com a aba à vista (nada rodando com o app parado)
KC.timer = setInterval(() => { if (kcPg() && kcPg().classList.contains('active')) kcEstado(); }, 3000);
if (kcGuarda('kc-auto') === '1') kcCall('abrir').then(kcEstado).catch(() => {});
