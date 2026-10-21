/* KaniCode — painéis laterais que se abrem PARA FORA da janela (ela cresce, a conversa não aperta):
   • direita: Atividades — o que está rodando agora, o que roda em segundo plano (shell, monitor, agente) com a última
     linha da saída ao vivo, e tudo o que já foi feito nesta conversa (clique leva ao passo na conversa);
   • esquerda: Contas do Claude em detalhe (e-mail, plano, cotas 5h/semana) no lugar do popup;
   • diferenças de código (verde = entrou, vermelho = saiu) nos passos Edit/Write e nos cartões de permissão.
   Carregado depois do script principal: troca passo/passoFim/cartao/carregar/contasAbrir e embrulha kcEv. */
(() => {
  const LADO_EXTRA = 200, ATV_EXTRA = 270;   // quanto a janela cresce ao abrir cada coluna (pixels da interface)
  const PAINEL = { esq: false, dir: false, dirAuto: false };

  // ── janela cresce/encolhe para fora ──
  async function crescer(esq, dir) { try { await api().crescer(esq, dir); } catch (e) { /* janela antiga: só a coluna */ } }
  window.kcExtra = () => (PAINEL.esq ? LADO_EXTRA : 0) + (PAINEL.dir ? ATV_EXTRA : 0);

  async function abrirDir(on, auto = false) {
    if (on === PAINEL.dir) return;
    PAINEL.dir = on; PAINEL.dirAuto = on && auto;
    if (on) { await crescer(0, ATV_EXTRA); $('atv').classList.add('aberto'); desenhar(); }
    else { $('atv').classList.remove('aberto'); await crescer(0, -ATV_EXTRA); }
  }
  async function abrirEsq(on) {
    if (on === PAINEL.esq) return;
    PAINEL.esq = on;
    const lado = $('lado'), p = $('contas');
    if (on) {
      $('dica-ct')?.remove();
      await crescer(LADO_EXTRA, 0);
      lado.classList.add('aberto'); lado.appendChild(p); p.hidden = false;
      CT.dados = await api().contas_listar(); contasDesenhar();
      CT.dados = await api().conta_atualizar(); contasDesenhar(); contaBotao(); cotasDaConta();
    } else {
      p.hidden = true; lado.classList.remove('aberto'); document.body.appendChild(p);
      await crescer(-LADO_EXTRA, 0);
    }
  }
  window.contasAbrir = () => abrirEsq(!PAINEL.esq);
  const contasDesenhar0 = window.contasDesenhar;
  window.contasDesenhar = () => {   // na coluna aberta: botão « para recolher, no título
    contasDesenhar0();
    const h = $('contas').querySelector('h4');
    if (PAINEL.esq && h) {
      h.insertAdjacentHTML('beforeend', '<button class="bt" title="Recolher as contas">«</button>');
      h.querySelector('.bt').onclick = ev => { ev.stopPropagation(); abrirEsq(false); };
    }
  };
  // com a coluna aberta, clicar fora não fecha as contas (o popup antigo fechava)
  document.addEventListener('mousedown', () => { if (PAINEL.esq) setTimeout(() => { $('contas').hidden = false; }); });

  // ── coluna das Atividades ──
  const corpo = document.querySelector('.corpo');
  corpo.insertAdjacentHTML('beforeend', `<div class="atv" id="atv">
    <div class="trilho" id="atv-trilho" title="Atividades: o que está rodando e o que já foi feito">
      <span class="ic">⚡</span><span class="cont" id="atv-cont" hidden></span><span class="vert">ATIVIDADES</span></div>
    <div class="det"><div class="cab"><b>Atividades</b><span class="esp"></span><button class="bt" id="atv-fechar" title="Recolher">»</button></div>
      <div class="rolo" id="atv-lista"></div></div></div>`);
  $('atv-trilho').addEventListener('click', () => abrirDir(!PAINEL.dir));
  $('atv-fechar').addEventListener('click', () => abrirDir(false));

  const A = { itens: new Map(), ordem: [] };   // id → {id, nome, tit, cmd, t0, t1, ok, bg, arq, tarefa, tail, cod}
  const ehBg = (nome, e) => !!(e && e.run_in_background) || nome === 'Monitor';
  const titulo = (nome, e) => {
    const a = ACOES[nome] || ['⚙', nome, nome];
    const t = (e && e.description) || (a[1] + ' ' + (alvo(nome, e) || '')).trim();
    return { ic: a[0], tit: t.charAt(0).toUpperCase() + t.slice(1) };
  };
  function inicio(id, nome, e, vivo) {
    if (!id || A.itens.has(id)) return;
    const { ic, tit } = titulo(nome, e);
    const it = { id, nome, ic, tit, cmd: e.command || e.prompt || '', t0: vivo ? Date.now() : 0, t1: 0, ok: null, bg: ehBg(nome, e) };
    A.itens.set(id, it); A.ordem.push(id);
    if (it.bg && vivo) abrirDir(true, true);
    desenhar();
  }
  function termino(id, ok, saida) {
    const it = A.itens.get(id); if (!it) return;
    saida = String(saida || '');
    if (it.bg) {   // o resultado só diz que COMEÇOU: o fim vem pela saída gravada ou pelo aviso do Claude Code
      const arq = saida.match(/written to:\s*(\S.*?\.output)/i), tid = saida.match(/\bID:\s*([\w-]+)/i);
      if (arq) it.arq = arq[1].trim();
      if (tid) it.tarefa = tid[1];
      if (!ok) { it.ok = false; it.t1 = Date.now(); }
      if (!arq && !tid && ok) { it.ok = true; it.t1 = it.t1 || Date.now(); }
    } else { it.ok = ok; it.t1 = Date.now(); }
    desenhar(); vigiar();
  }
  // aviso de tarefa do Claude Code (system task_*): marca o fim do que roda em segundo plano
  function tarefa(ev) {
    for (const it of A.itens.values()) {
      if (!it.bg || it.t1 || !(ev.id && (it.tarefa === ev.id || (it.arq && ev.arquivo && it.arq === ev.arquivo)))) continue;
      if (/complet|fail|kill|stop|error|done/i.test(ev.status || ev.sub || '')) {
        it.t1 = Date.now(); it.ok = !/fail|error|kill/i.test(ev.status || '');
        if (ev.resumo) it.tail = ev.resumo;
      }
    }
    desenhar(); fecharSozinho();
  }

  // a saída dos comandos em segundo plano: última linha ao vivo e o fim ("[exited with code N]")
  let vigiando = null;
  function vigiar() {
    if (vigiando) return;
    const passo = async () => {
      const vivos = [...A.itens.values()].filter(i => i.bg && !i.t1 && i.arq);
      if (!vivos.length) { vigiando = null; fecharSozinho(); return; }
      try {
        const r = await api().tarefas_ler(vivos.map(i => i.arq));
        for (const it of vivos) {
          const x = r[it.arq]; if (!x) continue;
          if (x.falta) { it.t1 = Date.now(); it.ok = null; it.tail = 'encerrada (a saída não existe mais)'; continue; }
          it.tail = x.tail; it.kb = x.kb;
          if (x.fim != null) { it.t1 = Date.now(); it.cod = x.fim; it.ok = x.fim === 0; }
        }
        desenhar();
      } catch (e) { /* janela antiga sem tarefas_ler */ }
      vigiando = setTimeout(passo, 1500);
    };
    vigiando = setTimeout(passo, 300);
  }
  let fechaT = null;
  function fecharSozinho() {   // abriu sozinha por uma tarefa de fundo: recolhe 10 s depois que tudo acabar
    clearTimeout(fechaT);
    if (!PAINEL.dirAuto || [...A.itens.values()].some(i => i.bg && !i.t1)) return;
    fechaT = setTimeout(() => { if (PAINEL.dirAuto && ![...A.itens.values()].some(i => i.bg && !i.t1)) abrirDir(false); }, 10000);
  }

  const dur = it => { if (!it.t0) return ''; const s = ((it.t1 || Date.now()) - it.t0) / 1000; return s < 60 ? s.toFixed(s < 10 ? 1 : 0).replace('.', ',') + ' s' : relogio(s); };
  function cartaoAtv(it) {
    const est = !it.t1 ? 'vivo' : it.ok === false ? 'falhou' : 'ok';
    const chip = !it.t1 ? (it.bg ? 'em segundo plano' : 'rodando') : it.ok === false ? (it.cod != null ? `saiu com ${it.cod}` : 'falhou') : it.ok == null ? 'encerrada' : 'concluído';
    return `<div class="ta ${est}${it.bg ? ' bg' : ''}" data-id="${esc(it.id)}">
      <div class="l1"><span class="anel"></span><span class="tic">${it.ic}</span><b>${esc(it.tit)}</b></div>
      ${it.cmd && it.cmd !== it.tit ? `<code>${esc(String(it.cmd).replace(/\s+/g, ' ').slice(0, 160))}</code>` : ''}
      ${it.bg && it.tail ? `<pre>${esc(it.tail)}</pre>` : ''}
      <div class="l2"><span class="chip">${chip}</span><span>${dur(it)}${it.kb ? ' · ' + mil(it.kb) + ' KB de saída' : ''}</span></div></div>`;
  }
  function desenhar() {
    const tudo = A.ordem.map(id => A.itens.get(id));
    const fundo = tudo.filter(i => i.bg && !i.t1), agora = tudo.filter(i => !i.bg && !i.t1 && i.t0), feito = tudo.filter(i => i.t1 || (!i.t0 && !i.bg) || (i.bg && !i.t0 && !i.arq)).reverse().slice(0, 60);
    const n = fundo.length + agora.length;
    $('atv-cont').hidden = !n; $('atv-cont').textContent = n;
    $('atv').classList.toggle('tem', n > 0);
    if (!PAINEL.dir) return;
    const sec = (t, l, vazio) => `<div class="sec">${t}${l.length ? ` <small>${l.length}</small>` : ''}</div>` + (l.length ? l.map(cartaoAtv).join('') : `<div class="vazio">${vazio}</div>`);
    $('atv-lista').innerHTML = sec('EM SEGUNDO PLANO', fundo, 'Nada rodando por baixo.') + sec('AGORA', agora, K.ocupada ? 'Pensando…' : 'Parado.')
      + sec('FEITO NESTA CONVERSA', feito, 'Ainda nada.');
  }
  setInterval(() => { if (PAINEL.dir && [...A.itens.values()].some(i => !i.t1 && i.t0)) desenhar(); }, 1000);
  $('atv-lista').addEventListener('click', e => {
    const c = e.target.closest('.ta'); if (!c) return;
    const d = K.ferr[c.dataset.id]; if (!d) return;
    d.open = true; d.scrollIntoView({ block: 'center', behavior: 'smooth' });
    d.classList.add('piscar'); setTimeout(() => d.classList.remove('piscar'), 1200);
  });

  // ── diferenças de código: linhas que saíram (vermelho) e entraram (verde) ──
  function difLinhas(a, b) {
    const n = a.length, m = b.length;
    if (n * m > 360000) return [...a.map(s => ['-', s]), ...b.map(s => ['+', s])];
    const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = a[i] === b[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    const out = []; let i = 0, j = 0;
    while (i < n && j < m) {
      if (a[i] === b[j]) { out.push([' ', a[i]]); i++; j++; }
      else if (L[i + 1][j] >= L[i][j + 1]) out.push(['-', a[i++]]); else out.push(['+', b[j++]]);
    }
    while (i < n) out.push(['-', a[i++]]); while (j < m) out.push(['+', b[j++]]);
    return out;
  }
  function difBloco(ops, nome) {
    let h = nome ? `<div class="dh">${esc(nome)}</div>` : '', igual = [], houve = false;
    const ig = s => `<div class="dl"><i> </i>${esc(s) || ' '}</div>`;
    const solta = fimBloco => {   // linhas iguais: 2 de contexto em volta da mudança, o meio dobrado
      const ini = houve ? 2 : 0, fimN = fimBloco ? 0 : 2;
      if (igual.length > ini + fimN + 1) h += igual.slice(0, ini).map(ig).join('') + `<div class="dz">⋯ ${igual.length - ini - fimN} linhas iguais</div>` + igual.slice(igual.length - fimN).map(ig).join('');
      else h += igual.map(ig).join('');
      igual = [];
    };
    for (const [t, s] of ops) {
      if (t === ' ') { igual.push(s); continue; }
      solta(false); houve = true;
      h += `<div class="dl ${t === '+' ? 'add' : 'del'}"><i>${t === '+' ? '+' : '−'}</i>${esc(s) || ' '}</div>`;
    }
    solta(true);
    return h;
  }
  const conta = ops => [ops.filter(o => o[0] === '+').length, ops.filter(o => o[0] === '-').length];
  function difDe(nome, e) {
    e = e || {};
    let blocos = [];
    if (nome === 'Edit' || nome === 'MultiEdit') blocos = (e.edits || [e]).map(x => [difLinhas(String(x.old_string || '').split('\n'), String(x.new_string || '').split('\n')), '']);
    else if (nome === 'Write' && /\.patch$/i.test(e.file_path || '')) {   // tools/patch.py: @@ arquivo / <<< velho === novo >>>
      const re = /^@@ (.+?)\s*\n<<<\n([\s\S]*?)\n?===\n([\s\S]*?)\n?>>>/gm; let m;
      while ((m = re.exec(String(e.content || '').replace(/\r/g, '')))) blocos.push([difLinhas(m[2] ? m[2].split('\n') : [], m[3].split('\n')), base(m[1].replace(/\s+(\*|\+fim)$/, ''))]);
    } else if (nome === 'Write') {
      const l = String(e.content || '').split('\n');
      blocos = [[l.slice(0, 400).map(s => ['+', s]).concat(l.length > 400 ? [[' ', `… mais ${l.length - 400} linhas`]] : []), '']];
    } else return null;
    if (!blocos.length) return null;
    let mais = 0, menos = 0;
    blocos.forEach(([ops]) => { const [a, b] = conta(ops); mais += a; menos += b; });
    return { html: `<div class="dif">${blocos.map(([ops, nm]) => difBloco(ops, nm)).join('<div class="dsep"></div>')}</div>`, mais, menos };
  }
  const placar = d => ` <span class="pl"><span class="add">+${d.mais}</span> <span class="del">−${d.menos}</span></span>`;

  // ── trocas no script principal ──
  const passo0 = window.passo, passoFim0 = window.passoFim, cartao0 = window.cartao, carregar0 = window.carregar;
  let aoVivo = false;   // false enquanto o histórico é montado (carregar)
  window.passo = (id, nome, entrada) => {
    const d = passo0(id, nome, entrada);
    const dif = difDe(nome, entrada);
    if (dif) { d.querySelector('pre.ent').outerHTML = dif.html; d.querySelector('summary').insertAdjacentHTML('beforeend', placar(dif)); }
    inicio(id, nome, entrada || {}, aoVivo);
    return d;
  };
  window.passoFim = (id, ok, saida) => { passoFim0(id, ok, saida); termino(id, ok, saida); };
  window.cartao = (ev, respondido) => {
    const d = cartao0(ev, respondido);
    const dif = difDe(ev.ferr, ev.entrada);
    if (dif) { d.querySelector('pre').outerHTML = dif.html; d.querySelector('.t').insertAdjacentHTML('beforeend', placar(dif)); }
    return d;
  };
  window.carregar = async () => {
    aoVivo = false; A.itens.clear(); A.ordem = [];
    try { await carregar0(); } finally { aoVivo = true; desenhar(); vigiar(); }
  };
  const kcEv0 = window.kcEv;
  window.kcEv = ev => {
    aoVivo = true;
    kcEv0(ev);
    if (ev.t === 'tarefa') tarefa(ev);
    if (ev.t === 'ferr' || ev.t === 'ferr_fim' || ev.t === 'fim') desenhar();
  };
  aoVivo = true;
})();
