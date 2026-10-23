/* Consumo de tokens no painel da direita: hoje, semana, mês e desde o início, por motor e modelo (consumo.py).
   A Kani local não entra. Lido dos registros de cada motor, então já mostra o passado. */
(() => {
  const el = id => document.getElementById(id), api = () => window.pywebview.api;
  const MOTOR = { claude: ['Claude', '#E08A5B'], codex: ['Codex', '#C9D1CC'], pickle: ['Big Pickle', '#9BCB5E'] };
  const PER = [['hoje', 'Hoje'], ['semana', 'Semana'], ['mes', 'Mês'], ['tudo', 'Tudo']];
  // o que somar de [entrada, cache_lido, cache_criado, saida]
  const TIPO = { tudo: ['Tudo', v => v[0] + v[1] + v[2] + v[3]], saida: ['Saída', v => v[3]],
                 entrada: ['Entrada nova', v => v[0] + v[2]], cache: ['Cache', v => v[1]] };
  const fmt = n => n >= 1e9 ? (n / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + ' bi'
    : n >= 1e6 ? (n / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi'
    : n >= 1e3 ? (n / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mil' : String(n);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const trilho = document.createElement('button'); trilho.id = 'consumo-trilho'; trilho.className = 'trilho';
  trilho.title = 'Consumo de tokens'; trilho.setAttribute('aria-label', 'Consumo de tokens');
  trilho.setAttribute('aria-expanded', 'false'); trilho.setAttribute('aria-controls', 'consumo-painel');
  trilho.innerHTML = '<span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M21 20H3"/></svg></span><span class="vert">CONSUMO</span>';
  (el('todo-trilho') || el('atv-trilho')).after(trilho);
  const painel = document.createElement('section'); painel.id = 'consumo-painel'; painel.className = 'det';
  painel.setAttribute('aria-label', 'Consumo de tokens');
  painel.innerHTML = `<div class="cab"><b>Consumo</b><span class="esp"></span><button class="bt" id="consumo-atualizar" title="Atualizar">↻</button><button class="bt" id="consumo-fechar" aria-label="Recolher consumo">»</button></div>
    <div class="cs-rolo"><div class="cs-nav" role="tablist">${PER.map(([id, nome], i) => `<button data-p="${id}" role="tab" aria-selected="${i === 0}">${nome}</button>`).join('')}</div>
      <div class="cs-tipo" role="radiogroup" aria-label="O que contar">${Object.entries(TIPO).map(([id, [nome]]) => `<button data-t="${id}" role="radio" aria-checked="${id === 'saida'}">${nome}</button>`).join('')}</div>
      <div id="consumo-corpo"><p class="cs-nota">Calculando…</p></div></div>`;
  el('atv').append(painel); painel.inert = true;
  let per = 'hoje', tipo = localStorage.getItem('kc-consumo-tipo') || 'saida', dados = null, timer = null;
  painel.querySelectorAll('.cs-tipo button').forEach(x => x.setAttribute('aria-checked', String(x.dataset.t === tipo)));

  function desenhar() {
    const c = el('consumo-corpo');
    if (!dados) return;
    const p = dados.periodos[per], f = p.campos, conta = TIPO[tipo][1];
    const lista = g => Object.entries(g).map(([k, v]) => [k, conta(v)]).filter(x => x[1]).sort((a, b) => b[1] - a[1]);
    const motores = lista(p.motores), modelos = lista(p.modelos);
    const total = conta([f.entrada, f.cache_lido, f.cache_criado, f.saida]);
    const novos = f.entrada + f.cache_criado + f.saida;
    const dia = d => Object.fromEntries(Object.entries(d.motores).map(([m, v]) => [m, conta(v)]));
    const pico = Math.max(1, ...dados.dias.map(d => Object.values(dia(d)).reduce((a, b) => a + b, 0)));
    const barras = dados.dias.map(d0 => {
      const d = { dia: d0.dia, motores: dia(d0) };
      const tot = Object.values(d.motores).reduce((a, b) => a + b, 0);
      const tit = `${d.dia.split('-').reverse().slice(0, 2).join('/')}: ${fmt(tot)}`;
      return `<i title="${tit}">${Object.keys(MOTOR).filter(m => d.motores[m]).map(m =>
        `<s style="height:${(d.motores[m] / pico * 100).toFixed(1)}%;background:${MOTOR[m][1]}"></s>`).join('')}</i>`;
    }).join('');
    c.innerHTML = `<div class="cs-total">${fmt(total)}<small>tokens${tipo === 'tudo' ? '' : ' de ' + TIPO[tipo][0].toLowerCase()}</small></div>
      <p class="cs-det">${total.toLocaleString('pt-BR')} exatos</p>
      <div class="cs-campos"><span><b>${fmt(f.cache_lido)}</b>cache lido</span><span><b>${fmt(f.entrada + f.cache_criado)}</b>entrada nova</span><span><b>${fmt(f.saida)}</b>saída</span></div>
      <h4 class="cs-sec">Por motor</h4>
      ${motores.length ? motores.map(([m, n]) => `<div class="cs-linha"><span><i style="background:${(MOTOR[m] || [, '#888'])[1]}"></i>${esc((MOTOR[m] || [m])[0])}</span><b>${fmt(n)}</b>
        <div class="cs-barra"><s style="width:${(n / total * 100).toFixed(1)}%;background:${(MOTOR[m] || [, '#888'])[1]}"></s></div></div>`).join('') : '<p class="cs-nota">Nada neste período.</p>'}
      ${modelos.length ? `<h4 class="cs-sec">Por modelo</h4>${modelos.map(([m, n]) => `<div class="cs-mod"><span>${esc(m)}</span><b>${fmt(n)}</b></div>`).join('')}` : ''}
      <h4 class="cs-sec">Últimos 30 dias</h4><div class="cs-graf">${barras}</div>
      <p class="cs-nota">Sem a Kani local. ${novos ? `Tokens novos (sem o cache): ${fmt(novos)}. ` : ''}Contando desde ${dados.desde ? dados.desde.split('-').reverse().join('/') : '—'} · atualizado ${dados.atualizado}.</p>`;
  }
  async function atualizar() {
    try { dados = await api().consumo(); desenhar(); }
    catch (e) { el('consumo-corpo').innerHTML = `<p class="cs-nota erro">Não consegui ler o consumo: ${esc(e.message || e)}</p>`; }
  }
  painel.querySelector('.cs-nav').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    per = b.dataset.p; painel.querySelectorAll('.cs-nav button').forEach(x => x.setAttribute('aria-selected', String(x === b))); desenhar();
  });
  painel.querySelector('.cs-tipo').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    tipo = b.dataset.t; localStorage.setItem('kc-consumo-tipo', tipo);
    painel.querySelectorAll('.cs-tipo button').forEach(x => x.setAttribute('aria-checked', String(x === b))); desenhar();
  });
  trilho.addEventListener('click', () => window.kaniPainelDireito(trilho.getAttribute('aria-expanded') !== 'true', 'consumo'));
  el('consumo-fechar').addEventListener('click', () => window.kaniPainelDireito(false, 'consumo'));
  el('consumo-atualizar').addEventListener('click', atualizar);
  painel.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); window.kaniPainelDireito(false, 'consumo'); trilho.focus(); } });
  new MutationObserver(() => {
    const aberto = trilho.getAttribute('aria-expanded') === 'true'; painel.inert = !aberto; clearInterval(timer);
    if (aberto) { atualizar(); timer = setInterval(() => { if (!document.hidden) atualizar(); }, 60000); }
  }).observe(trilho, { attributes: true, attributeFilter: ['aria-expanded'] });
})();
