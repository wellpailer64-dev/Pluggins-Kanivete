/* KaniCode — painel direito regulável, com espaço inicial na janela; contas à esquerda por cima da conversa:
   • direita: Ferramentas e atividade da conversa — o que roda em segundo plano (shell, monitor, agente) com a última
     linha da saída ao vivo, e tudo o que já foi feito nesta conversa (clique leva ao passo na conversa);
   • esquerda: Contas do Claude em detalhe (e-mail, plano, cotas 5h/semana) no lugar do popup;
   • diferenças de código (verde = entrou, vermelho = saiu) nos passos Edit/Write e nos cartões de permissão.
   Carregado depois do script principal: troca passo/passoFim/cartao/carregar/contasAbrir e embrulha kcEv. */
(() => {
  const PAINEL = { esq: false, dir: false, dirAuto: false, secao: "atividades" };

  // A largura escolhida é da divisória; a janela continua livre para esticar pelas bordas.
  window.kcExtra = () => 0;
  let larguraPreferida = 270;
  try { larguraPreferida = Math.max(270, Math.min(1600, Number(localStorage.getItem('kanicode-painel-largura')) || 270)); } catch (_) {}

  async function abrirDir(on, auto = false, secao = 'atividades') {
    PAINEL.secao = secao;
    $('atv').classList.toggle('todo-visivel', secao === 'todo');
    const ferramentasVisiveis = on && secao === 'atividades';
    $('atv-trilho').setAttribute('aria-expanded', String(ferramentasVisiveis));
    $('ferramentas-menu').hidden = !ferramentasVisiveis;
    $('painel-ajuste').hidden = !ferramentasVisiveis;
    $('todo-trilho')?.setAttribute('aria-expanded', String(on && secao === 'todo'));
    $('atv').classList.toggle('consumo-visivel', secao === 'consumo');
    $('consumo-trilho')?.setAttribute('aria-expanded', String(on && secao === 'consumo'));
    $('atv').classList.toggle('casa-visivel', secao === 'casa');
    $('atv').classList.toggle('projeto-visivel', secao === 'projeto');
    $('proj-trilho')?.setAttribute('aria-expanded', String(on && secao === 'projeto'));
    $('casa-trilho')?.setAttribute('aria-expanded', String(on && secao === 'casa'));
    $('atv').classList.toggle('saude-visivel', secao === 'saude');
    $('saude-trilho')?.setAttribute('aria-expanded', String(on && secao === 'saude'));
    $('atv').classList.toggle('whatsapp-visivel', secao === 'whatsapp');
    $('whatsapp-trilho')?.setAttribute('aria-expanded', String(on && secao === 'whatsapp'));
    // Trocar de seção também confere o espaço das ferramentas.
    PAINEL.dir = on; PAINEL.dirAuto = on && auto;
    if (on) {
      $('atv').classList.add('aberto'); desenhar(); ajustarLargura();
      if (!document.documentElement.classList.contains('movel')) {
        try { await api().painel_espaco(larguraPreferida); ajustarLargura(); }
        catch (e) { console.warn('Não foi possível abrir espaço para o painel:', e); }
      }
    }
    else $('atv').classList.remove('aberto');
  }
  async function abrirEsq(on) {
    if (on === PAINEL.esq) return;
    PAINEL.esq = on;
    const lado = $('lado'), p = $('contas');
    if (on) {
      $('dica-ct')?.remove();
      lado.classList.add('aberto'); lado.appendChild(p); p.hidden = false;
      CT.dados = await api().contas_listar(); contasDesenhar();
      CT.dados = await api().conta_atualizar(); contasDesenhar(); contaBotao(); cotasDaConta();
    } else {
      p.hidden = true; lado.classList.remove('aberto'); document.body.appendChild(p);
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
  document.addEventListener('mousedown', ev => {
    if (!PAINEL.esq) return;
    if (!$('lado').contains(ev.target) && !ev.target.closest('.caixa, #contas-bt')) { abrirEsq(false); return; }   // por cima: clicar fora recolhe
    setTimeout(() => { $('contas').hidden = false; });
  });

  // ── coluna das Ferramentas ──
  const corpo = document.querySelector('.corpo');
  corpo.insertAdjacentHTML('beforeend', `<div class="atv" id="atv">
    <div id="painel-ajuste" class="painel-ajuste" role="separator" tabindex="0" aria-label="Largura do painel Ferramentas" aria-orientation="vertical" aria-controls="ferramentas-painel" aria-valuemin="270" aria-valuemax="270" aria-valuenow="270" title="Arraste para dividir o espaço · duplo clique: largura inicial" hidden></div>
    <div class="trilho-coluna">
      <button class="ferramentas-bt" id="ferramentas-bt" title="Configurações" aria-label="Configurações" aria-expanded="false" aria-controls="config-menu"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10 3-1 3-3 1-3-1-1 4 3 2v2l-2 2 2 3 3-1 3 1 1 3 4-1v-3l2-2 3-1-1-4-3 1-2-2V3z"/><circle cx="12" cy="12" r="3"/></svg></button>
      <button class="trilho" id="atv-trilho" title="Ferramentas do KaniCode" aria-label="Ferramentas" aria-expanded="false" aria-controls="ferramentas-conteudo">
        <span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m13 2-8 11h6l-1 9 9-13h-6z"/></svg></span><span class="cont" id="atv-cont" hidden></span><span class="vert">FERRAMENTAS</span></button>
    </div>
    <div class="det" id="ferramentas-painel"><div class="cab"><b>Ferramentas</b><span class="esp"></span><button class="bt" id="atv-fechar" title="Recolher">»</button></div>
      <div class="ferramentas-conteudo" id="ferramentas-conteudo">
        <details class="ferramentas-historico"><summary>Atividade da conversa</summary><div class="rolo" id="atv-lista"></div></details>
      </div></div></div>`);
  $('ferramentas-conteudo').prepend($('ferramentas-menu'));
  // o painel da direita desce até o fim da janela, ao lado da barra de digitar: corpo + status/anexos/entrada/rodapé
  // numa coluna (.principal) e o painel ao lado dela; aberto, empurra o chat inteiro, a entrada junto (no celular o
  // painel é gaveta por cima: fica como está)
  if (!document.documentElement.classList.contains('movel')) {
    const linha = document.createElement('div'), principal = document.createElement('div');
    linha.className = 'area-linha'; principal.className = 'principal';
    corpo.before(linha); linha.append(principal, $('atv'));
    principal.append(corpo);
    for (const s of ['#planoFixo', '#status', '#anexos', 'body > .entrada', 'body > .rodape']) { const n = document.querySelector(s); if (n) principal.append(n); }
  }
  window.kaniPainelDireito = (on, secao = 'atividades') => abrirDir(on, false, secao);
  $('atv-trilho').addEventListener('click', () => abrirDir(!PAINEL.dir || PAINEL.secao !== 'atividades'));
  $('atv-fechar').addEventListener('click', () => abrirDir(false));

  const ajuste = $('painel-ajuste');
  function larguraMaxima() { return Math.max(270, (corpo.closest('.area-linha') || corpo).clientWidth - 420); }
  function ajustarLargura(valor = larguraPreferida, guardar = false) {
    const largura = Math.round(Math.max(270, Math.min(larguraMaxima(), valor)));
    $('atv').style.setProperty('--painel-largura', largura + 'px');
    ajuste.setAttribute('aria-valuemax', String(larguraMaxima()));
    ajuste.setAttribute('aria-valuenow', String(largura));
    if (guardar) {
      larguraPreferida = largura;
      try { localStorage.setItem('kanicode-painel-largura', String(largura)); } catch (_) {}
    }
  }
  let arraste = null;
  ajuste.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    e.preventDefault(); ajuste.focus(); ajuste.setPointerCapture(e.pointerId);
    arraste = { x: e.clientX, largura: Number(ajuste.getAttribute('aria-valuenow')) };
    $('atv').classList.add('ajustando');
  });
  ajuste.addEventListener('pointermove', e => {
    if (arraste) ajustarLargura(arraste.largura + arraste.x - e.clientX);
  });
  const soltarPainel = () => {
    if (!arraste) return;
    arraste = null; $('atv').classList.remove('ajustando');
    ajustarLargura(Number(ajuste.getAttribute('aria-valuenow')), true);
  };
  ajuste.addEventListener('pointerup', soltarPainel);
  ajuste.addEventListener('pointercancel', soltarPainel);
  ajuste.addEventListener('lostpointercapture', soltarPainel);
  ajuste.addEventListener('dblclick', () => ajustarLargura(270, true));
  ajuste.addEventListener('keydown', e => {
    const atual = Number(ajuste.getAttribute('aria-valuenow'));
    const valores = { ArrowLeft: atual + 20, ArrowRight: atual - 20, Home: 270, End: larguraMaxima() };
    if (e.key in valores) { e.preventDefault(); ajustarLargura(valores[e.key], true); }
  });
  addEventListener('resize', () => ajustarLargura());
  ajustarLargura();

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
    // O trilho sinaliza trabalho em segundo plano; expandir só por clique.
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
    if (ev.t === 'ajudante' && ev.quem === 'codex') {
      const id = 'codex:' + ev.id;
      if (ev.operacao === 'inicio' && (ev.entrada?.command || ev.entrada?.changes?.length))
        inicio(id, 'Codex', {command: ev.entrada.command, description: ev.texto}, true);
      if (ev.operacao === 'fim') termino(id, ev.ok !== false, '');
      if (ev.fase === 'fim') for (const it of A.itens.values()) {
        if (it.id.startsWith('codex:') && !it.t1) { it.t1 = Date.now(); it.ok = !!ev.ok; }
      }
      desenhar();
    }
    if (ev.t === 'tarefa') tarefa(ev);
    if (ev.t === 'ferr' || ev.t === 'ferr_fim' || ev.t === 'fim') desenhar();
  };
  aoVivo = true;
})();
