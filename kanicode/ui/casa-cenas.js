/* Aba Casa › Cenas (cenas.py): automações = gatilhos (horário, frase de voz, ao abrir) + ações em ordem
   (aparelho, gatos, esperar, PC, alerta, som, abrir). Lista com ▶ e liga/desliga; editor dentro da própria aba. */
(() => {
  const el = id => document.getElementById(id), api = () => window.pywebview.api;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const DIAS = ['S', 'T', 'Q', 'Q', 'S', 'S', 'D'];   // weekday() do Python: 0 = segunda
  const ACOES = {
    aparelho: '💡 Aparelho', alimentar: '🐱 Alimentar gatos', esperar: '⏳ Esperar', pc: '🖥 PC',
    alerta: '🔔 Alerta', falar: '🗣 Falar (voz da Kani)', som: '🔊 Som', abrir: '📂 Abrir programa/site',
  };
  const OPS = {
    aparelho: { ligar: 'ligar', desligar: 'desligar', alternar: 'alternar', brilho: 'brilho %' },
    pc: { acordar: 'acordar (acender a tela)', bloquear: 'bloquear', tela_off: 'apagar a tela', suspender: 'suspender', desligar: 'desligar (60 s)', reiniciar: 'reiniciar (60 s)' },
    som: { volume: 'volume %', mudo: 'sem som', som: 'tirar do mudo', tocar_pausar: 'tocar/pausar', proxima: 'próxima faixa', anterior: 'faixa anterior' },
  };
  const MODELOS = [
    { nome: 'Bom dia', gatilhos: [{ tipo: 'horario', hora: '07:30', dias: [0, 1, 2, 3, 4] }, { tipo: 'voz', frase: 'bom dia' }],
      acoes: [{ tipo: 'aparelho', alvo: 'cozinha', op: 'ligar' }, { tipo: 'som', op: 'volume', valor: 30 }, { tipo: 'falar', texto: 'Bom dia, Pailer!' }] },
    { nome: 'Modo cinema', gatilhos: [{ tipo: 'voz', frase: 'modo cinema' }],
      acoes: [{ tipo: 'aparelho', alvo: 'luzes', op: 'desligar' }, { tipo: 'som', op: 'volume', valor: 60 }] },
    { nome: 'Ração dos gatos', gatilhos: [{ tipo: 'horario', hora: '08:00', dias: [] }, { tipo: 'horario', hora: '19:00', dias: [] }],
      acoes: [{ tipo: 'alimentar', porcoes: 1 }, { tipo: 'alerta', texto: 'Servi a ração dos gatos.', falar: false }] },
    { nome: 'Começar o trabalho', gatilhos: [{ tipo: 'voz', frase: 'hora de trabalhar' }],
      acoes: [{ tipo: 'aparelho', alvo: 'escritorio', op: 'ligar' }, { tipo: 'abrir', alvo: 'https://laboratoriopanda.com' }, { tipo: 'som', op: 'volume', valor: 25 }] },
  ];

  const painel = el('casa-painel'), corpo = el('casa-corpo');
  if (!painel || !corpo) return;
  const abas = document.createElement('div'); abas.className = 'ca-abas';
  abas.innerHTML = '<button data-v="ap" class="sel">Aparelhos</button><button data-v="cn">Cenas</button>';
  const vista = document.createElement('div'); vista.id = 'casa-cenas'; vista.hidden = true;
  corpo.before(abas); corpo.after(vista);
  let dados = { cenas: [], aparelhos: [], comodos: [] }, ed = null;

  abas.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    abas.querySelectorAll('button').forEach(x => x.classList.toggle('sel', x === b));
    const cn = b.dataset.v === 'cn';
    corpo.hidden = cn; vista.hidden = !cn;
    if (cn) carregar();
  };

  async function carregar() {
    const r = await api().cenas_listar();
    if (!r || !r.ok) { vista.innerHTML = `<p class="ca-nota erro">${esc(r?.erro || 'Não consegui ler as cenas.')}</p>`; return; }
    dados = r; if (!ed) lista();
  }

  const resumoGat = g => g.tipo === 'horario' ? `⏰ ${g.hora}${g.dias?.length && g.dias.length < 7 ? ' ' + g.dias.map(d => DIAS[d]).join('') : ''}`
    : g.tipo === 'voz' ? `🎙 “${g.frase}”` : '▶ ao abrir';

  function lista() {
    ed = null;
    const cs = dados.cenas;
    vista.innerHTML = (cs.length ? cs.map(c => `<div class="cn-card${c.ativa === false ? ' off' : ''}" data-id="${c.id}">
        <div class="cn-l1"><b>${esc(c.nome)}</b><span class="esp"></span>
          <label class="cn-sw" title="Ligada"><input type="checkbox" data-a="ativa" ${c.ativa === false ? '' : 'checked'}><i></i></label></div>
        <small>${esc((c.gatilhos || []).map(resumoGat).join(' · ') || 'só manual')} — ${(c.acoes || []).length} ação(ões)</small>
        <div class="cn-l2"><button data-a="rodar">▶ Rodar</button><button data-a="editar">✎ Editar</button><span class="cn-msg"></span></div>
      </div>`).join('') : '<p class="ca-nota">Nenhuma cena ainda. Comece por um modelo:</p>') +
      `<div class="cn-mod">${cs.length ? '' : MODELOS.map((m, k) => `<button data-m="${k}">${esc(m.nome)}</button>`).join('')}</div>
       <button class="cn-nova" data-a="nova">+ Nova cena</button>
       <p class="ca-nota">Horários rodam com o KaniCode aberto; com o PC hibernado ou suspenso, ele acorda 2 min antes. A frase de voz vale no Ei Kani e no chat.</p>`;
  }

  vista.addEventListener('click', async e => {
    if (ed) return;
    const m = e.target.closest('[data-m]'); if (m) return editar(JSON.parse(JSON.stringify(MODELOS[+m.dataset.m])));
    const b = e.target.closest('button[data-a]'); if (!b) return;
    if (b.dataset.a === 'nova') return editar({ nome: '', ativa: true, gatilhos: [], acoes: [] });
    const c = dados.cenas.find(x => x.id === b.closest('.cn-card')?.dataset.id); if (!c) return;
    if (b.dataset.a === 'editar') return editar(JSON.parse(JSON.stringify(c)));
    if (b.dataset.a === 'rodar') {
      const msg = b.parentElement.querySelector('.cn-msg'); b.disabled = true; msg.textContent = 'rodando…';
      const r = await api().cenas_rodar(c.id);
      b.disabled = false; msg.textContent = r.ok ? 'feito ✓' : 'com erro';
      msg.title = (r.linhas || []).join('\n');
    }
  });
  vista.addEventListener('change', async e => {
    if (ed || e.target.dataset.a !== 'ativa') return;
    const c = dados.cenas.find(x => x.id === e.target.closest('.cn-card').dataset.id);
    c.ativa = e.target.checked; e.target.closest('.cn-card').classList.toggle('off', !c.ativa);
    await api().cenas_salvar(c);
  });

  // ── editor ──
  const opcoes = (obj, v) => Object.entries(obj).map(([k, t]) => `<option value="${k}"${k === v ? ' selected' : ''}>${esc(t)}</option>`).join('');
  function alvos(v) {
    const xs = [['luzes', 'todas as luzes'], ...dados.comodos.map(c => [c, 'cômodo: ' + c]),
      ...dados.aparelhos.filter(a => a.cat !== 'cwwsq').map(a => [a.nome, a.nome])];
    if (v && !xs.some(x => x[0] === v)) xs.push([v, v]);
    return xs.map(([k, t]) => `<option value="${esc(k)}"${k === v ? ' selected' : ''}>${esc(t)}</option>`).join('');
  }
  function campoGat(g, i) {
    const x = g.tipo === 'horario' ? `<input type="time" data-f="hora" value="${esc(g.hora || '08:00')}">
        <span class="cn-dias">${DIAS.map((d, k) => `<button data-dia="${k}" class="${(g.dias || []).includes(k) ? 'sel' : ''}" title="${['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'][k]}">${d}</button>`).join('')}</span>`
      : g.tipo === 'voz' ? `<input data-f="frase" placeholder="ex.: modo cinema" value="${esc(g.frase || '')}">` : '<span class="cn-fixo">quando o KaniCode abrir</span>';
    return `<div class="cn-item" data-g="${i}"><span class="cn-t">${{ horario: '⏰', voz: '🎙', inicio: '▶' }[g.tipo]}</span>${x}<button class="cn-x" data-x title="Tirar">×</button></div>`;
  }
  function campoAcao(a, i, n) {
    let x = '';
    if (a.tipo === 'aparelho') x = `<select data-f="alvo">${alvos(a.alvo)}</select><select data-f="op">${opcoes(OPS.aparelho, a.op)}</select>` +
      (a.op === 'brilho' ? `<input type="number" min="1" max="100" data-f="valor" value="${a.valor ?? 100}">` : '');
    else if (a.tipo === 'alimentar') x = `<input type="number" min="1" max="10" data-f="porcoes" value="${a.porcoes || 1}"><span class="cn-fixo">porção(ões)</span>`;
    else if (a.tipo === 'esperar') x = `<input type="number" min="0" max="3600" data-f="seg" value="${a.seg ?? 5}"><span class="cn-fixo">segundos</span>`;
    else if (a.tipo === 'pc') x = `<select data-f="op">${opcoes(OPS.pc, a.op)}</select>`;
    else if (a.tipo === 'som') x = `<select data-f="op">${opcoes(OPS.som, a.op)}</select>` +
      (a.op === 'volume' || !a.op ? `<input type="number" min="0" max="100" data-f="valor" value="${a.valor ?? 30}">` : '');
    else if (a.tipo === 'falar') x = `<input data-f="texto" placeholder="o que a Kani vai falar" value="${esc(a.texto || '')}">`;
    else if (a.tipo === 'alerta') x = `<input data-f="texto" placeholder="texto do aviso" value="${esc(a.texto || '')}">
        <label class="cn-ck"><input type="checkbox" data-f="falar" ${a.falar === false ? '' : 'checked'}> falar</label>`;
    else if (a.tipo === 'abrir') x = `<input data-f="alvo" placeholder="programa, C:\\…\\arquivo ou site" value="${esc(a.alvo || '')}">`;
    return `<div class="cn-item" data-ac="${i}"><span class="cn-t" title="${esc(ACOES[a.tipo])}">${ACOES[a.tipo].split(' ')[0]}</span>${x}
      <span class="cn-ord"><button data-up ${i ? '' : 'disabled'}>↑</button><button data-dn ${i < n - 1 ? '' : 'disabled'}>↓</button></span><button class="cn-x" data-x title="Tirar">×</button></div>`;
  }
  function desenharEd() {
    const c = ed;
    vista.innerHTML = `<div class="cn-ed">
      <input class="cn-nome" data-f="nome" placeholder="Nome da cena" value="${esc(c.nome)}">
      <h4>Quando</h4><div id="cn-gats">${c.gatilhos.map(campoGat).join('') || '<p class="ca-nota">Sem gatilho: só pelo ▶ Rodar.</p>'}</div>
      <div class="cn-add"><button data-ng="horario">+ Horário</button><button data-ng="voz">+ Frase de voz</button><button data-ng="inicio">+ Ao abrir</button></div>
      <h4>Fazer (em ordem)</h4><div id="cn-acs">${c.acoes.map((a, i) => campoAcao(a, i, c.acoes.length)).join('') || '<p class="ca-nota">Nenhuma ação.</p>'}</div>
      <select class="cn-addac"><option value="">+ Adicionar ação…</option>${opcoes(ACOES)}</select>
      <div class="ca-bts">${c.id ? '<button data-e="apagar" class="cn-apagar">Apagar</button>' : ''}<span class="esp"></span>
        <button data-e="cancelar">Cancelar</button><button data-e="testar">Testar</button><button data-e="salvar" class="sim">Salvar</button></div>
      <p class="ca-msg cn-res"></p></div>`;
  }
  function editar(c) { ed = c; desenharEd(); }

  const novaAcao = t => ({ aparelho: { alvo: 'luzes', op: 'ligar' }, alimentar: { porcoes: 1 }, esperar: { seg: 5 }, pc: { op: 'acordar' },
    som: { op: 'volume', valor: 30 }, alerta: { texto: '', falar: true }, falar: { texto: '' }, abrir: { alvo: '' } })[t];

  vista.addEventListener('input', e => {
    if (!ed) return;
    const f = e.target.dataset.f; if (!f) return;
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.type === 'number' ? +e.target.value : e.target.value;
    if (f === 'nome') { ed.nome = v; return; }
    const g = e.target.closest('[data-g]'), a = e.target.closest('[data-ac]');
    const obj = g ? ed.gatilhos[+g.dataset.g] : a ? ed.acoes[+a.dataset.ac] : null; if (!obj) return;
    obj[f] = v;
    if (a && f === 'op') desenharEd();   // brilho/volume mostram o campo de valor
  });
  vista.addEventListener('change', e => {
    if (!ed || !e.target.classList.contains('cn-addac') || !e.target.value) return;
    ed.acoes.push({ tipo: e.target.value, ...novaAcao(e.target.value) }); desenharEd();
  });
  vista.addEventListener('click', async e => {
    if (!ed) return;
    const b = e.target.closest('button'); if (!b || !vista.contains(b)) return;
    const g = b.closest('[data-g]'), a = b.closest('[data-ac]');
    if (b.dataset.ng) { ed.gatilhos.push(b.dataset.ng === 'horario' ? { tipo: 'horario', hora: '08:00', dias: [] } : b.dataset.ng === 'voz' ? { tipo: 'voz', frase: '' } : { tipo: 'inicio' }); return desenharEd(); }
    if (b.dataset.dia !== undefined && g) {
      const gt = ed.gatilhos[+g.dataset.g], k = +b.dataset.dia; gt.dias = gt.dias || [];
      gt.dias = gt.dias.includes(k) ? gt.dias.filter(d => d !== k) : [...gt.dias, k].sort();
      b.classList.toggle('sel'); return;
    }
    if (b.hasAttribute('data-x')) { if (g) ed.gatilhos.splice(+g.dataset.g, 1); else if (a) ed.acoes.splice(+a.dataset.ac, 1); return desenharEd(); }
    if ((b.hasAttribute('data-up') || b.hasAttribute('data-dn')) && a) {
      const i = +a.dataset.ac, j = i + (b.hasAttribute('data-up') ? -1 : 1);
      [ed.acoes[i], ed.acoes[j]] = [ed.acoes[j], ed.acoes[i]]; return desenharEd();
    }
    const res = vista.querySelector('.cn-res');
    if (b.dataset.e === 'cancelar') { ed = null; return carregar().then(lista); }
    if (b.dataset.e === 'apagar') {
      if (b.dataset.certo !== '1') { b.dataset.certo = '1'; b.textContent = 'Apagar mesmo?'; return; }
      await api().cenas_apagar(ed.id); ed = null; return carregar().then(lista);
    }
    if (!ed.nome.trim()) { res.textContent = 'Dê um nome à cena.'; return vista.querySelector('.cn-nome').focus(); }
    const r = await api().cenas_salvar(ed);
    if (!r.ok) { res.textContent = r.erro || 'Não consegui salvar.'; return; }
    ed = r.cena;
    if (b.dataset.e === 'testar') {
      res.textContent = 'rodando…';
      const x = await api().cenas_rodar(ed.id);
      res.textContent = (x.ok ? '✓ ' : '⚠ ') + (x.linhas || []).join(' · ');
      return;
    }
    ed = null; carregar().then(lista);
  });
})();
