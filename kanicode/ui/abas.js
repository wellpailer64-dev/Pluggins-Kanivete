/* KaniCode — abas (2026-10-21): várias conversas na mesma janela, cada uma com o seu agente e a sua tarefa,
   rodando ao mesmo tempo. O servidor guarda o estado por aba (kanicode.py _Aba) e marca cada evento com ev.aba.
   Aqui: a aba aberta desenha normal; as outras guardam os eventos numa fila (repassados ao voltar para ela) e só
   avisam na faixa (bolinha girando = trabalhando, verde = terminou, amarela = espera você). Carregado por último:
   embrulha o kcEv de todos os outros scripts. */
(() => {
  // No celular, a aba selecionada segue no cabeçalho HTTP; o PC conserva a seleção dele.
  const A = { ativa: null, lista: [], est: {}, repetindo: false, mudando: false };
  const faixa = document.createElement('div');
  faixa.className = 'abas-chat'; faixa.id = 'abas-chat'; faixa.setAttribute('role', 'tablist');
  document.querySelector('.corpo').before(faixa);

  const LIMPO = () => ({ ocupada: false, bolha: null, bruto: '', ferr: {}, mud: {}, t0: 0, tokFeitos: 0, tokMsg: 0,
    contexto: 0, faz: 'Pronto', espera: false, totTok: 0, totTarefas: 0, totSeg: 0, avisouEm: 0, planoFeitas: 0 });
  const est = id => A.est[id] || (A.est[id] = { fila: [], visto: false, aviso: '', ocupada: false });
  const nome = a => a.nome || `Aba ${a.id}`;
  // linha de cima: o assunto atual (ou o nome dado à mão); de baixo: o modelo em uso
  const titulo = a => (a.manual && a.nome) || a.assunto || nome(a);
  function modeloCurto(a) {
    const q = a.quem || 'claude';
    if (q === 'kani') return 'Kani · local';
    if (q === 'pickle') return 'Big Pickle';
    const m = String((a.id === A.ativa ? K.modelo : '') || a.modelo || (q === 'claude' ? A.modeloPadrao : '') || '');
    if (q === 'codex') return m && /gpt|codex/i.test(m) ? m.replace(/^gpt-/i, 'GPT-') : 'Codex';
    const r = m.match(/(opus|sonnet|haiku|fable)[-_ ]?(\d+)(?:[-.](\d+))?/i);
    if (r) return r[1][0].toUpperCase() + r[1].slice(1).toLowerCase() + ' ' + r[2] + (r[3] && r[3].length < 3 ? '.' + r[3] : '');
    return m ? m.replace(/^claude-/i, '').slice(0, 18) : 'Claude';
  }
  // o assunto: a 1ª frase do último pedido, sem as palavras de enchimento
  function resumo(t) {
    t = t.replace(/\s*\(por voz\)\s*$/i, '').replace(/```[\s\S]*?```/g, ' ').replace(/\s+/g, ' ').trim();
    t = t.replace(/^((ok|beleza|blz|show|certo|agora|então|entao|e|ei|oi|olá|ola|kani|claude|codex|bom|tá|ta|perfeito|legal|ótimo|otimo)[,.!]?\s+)+/i, '');
    t = (t.split(/(?<=[.?!])\s|\n/)[0] || t).replace(/[.!]+$/, '');
    if (t.length > 48) t = t.slice(0, 48).replace(/\s+\S*$/, '') + '…';
    return t ? t[0].toUpperCase() + t.slice(1) : '';
  }

  function desenhar() {
    faixa.innerHTML = A.lista.map(a => {
      const e = est(a.id), on = a.id === A.ativa;
      const trab = on ? K.ocupada : e.ocupada;
      const espera = on ? K.espera : e.aviso === 'pergunta';
      const marca = espera ? 'pergunta' : trab ? 'trab' : on ? '' : e.aviso;
      const q = EQUIPE[a.quem] || EQUIPE.claude, mod = modeloCurto(a);
      const icone = marca === 'trab' ? '<span class="aba-trab" aria-label="trabalhando"><i></i><i></i><i></i></span>' : `<span class="aba-ponto ${marca}"></span>`;
      const dica = `${titulo(a)} · ${mod}${espera ? ' · esperando você' : trab ? ' · trabalhando' : ''} (duplo clique renomeia)`;
      return `<div class="aba-chat${on ? ' on' : ''}" role="tab" aria-selected="${on}" data-aba="${a.id}" title="${esc(dica)}" style="--cor:${q.cor}">
        ${icone}<span class="aba-txt"><span class="aba-nome">${esc(titulo(a))}</span><span class="aba-mod">${esc(mod)}</span></span>
        ${A.lista.length > 1 ? '<button class="aba-x" title="Fechar aba (Ctrl+W)" aria-label="Fechar aba">×</button>' : ''}</div>`;
    }).join('') + '<button class="aba-mais" title="Nova aba (Ctrl+N)" aria-label="Nova aba">＋</button>';
  }

  function guardar() {   // a aba que sai: conversa, estado e plano fixo ficam guardados
    const e = est(A.ativa), frag = document.createDocumentFragment();
    while (conversa.firstChild) frag.appendChild(conversa.firstChild);
    e.frag = frag; e.K = Object.assign({}, K); e.ocupada = K.ocupada;
    e.plano = { html: $('planoFixo').innerHTML, hidden: $('planoFixo').hidden };
    rascunho(A.ativa, texto.value);
  }
  // texto ainda não enviado: cada aba com o seu (fica guardado até reabrir a janela)
  function rascunho(id, v) {
    const k = 'kc-rascunho-' + id;
    if (v === undefined) return localStorage.getItem(k) || '';
    if (v) localStorage.setItem(k, v); else localStorage.removeItem(k);
  }
  texto.addEventListener('input', () => { if (A.ativa) rascunho(A.ativa, texto.value); });

  async function entrar(id, r) {   // r = resposta do servidor (lista e aba ativa)
    A.lista = r.lista; A.ativa = String(r.ativa);
    const e = est(A.ativa);
    e.aviso = '';
    if (!e.visto || !e.frag) {   // 1ª vez nesta janela: a conversa vem do disco
      e.visto = true; e.fila = []; e.frag = null;
      Object.assign(K, LIMPO());
      $('planoFixo').hidden = true; $('planoFixo').innerHTML = '';
      await carregar();
    } else {
      conversa.innerHTML = ''; conversa.appendChild(e.frag); e.frag = null;
      Object.assign(K, e.K);
      $('planoFixo').innerHTML = e.plano.html; $('planoFixo').hidden = e.plano.hidden;
      quemDefinir(K.quem, false); modoMostrar(K.modo || 'auto');
      const fila = e.fila.splice(0);
      A.repetindo = true;
      try { fila.forEach(ev => evAntes(ev)); } finally { A.repetindo = false; }
      ocupada(K.ocupada); fim();
    }
    desenhar();
    texto.value = rascunho(A.ativa); texto.dispatchEvent(new Event('input'));
    if (!window.KC_MOVEL) texto.focus();
  }

  async function trocar(id) {
    id = String(id);
    if (id === A.ativa) return;
    guardar(); A.mudando = true;
    try { await entrar(id, await api().aba_ativar(id)); } finally { A.mudando = false; }
  }
  async function nova() {
    guardar(); A.mudando = true;
    try { const r = await api().aba_nova(); est(String(r.ativa)).visto = false; await entrar(r.ativa, r); } finally { A.mudando = false; }
  }
  async function fechar(id) {
    id = String(id);
    const a = A.lista.find(x => x.id === id);
    const trab = id === A.ativa ? K.ocupada : est(id).ocupada;
    if (trab && !await perguntar(`"${nome(a)}" ainda está trabalhando. Fechar para a tarefa dela?`, null, 'Fechar e parar')) return;
    const r = await api().aba_fechar(id);
    delete A.est[id]; rascunho(id, '');
    if (String(r.ativa) !== A.ativa) {
      if (id !== A.ativa) guardar();
      await entrar(r.ativa, r);
    } else { A.lista = r.lista; desenhar(); }
  }
  async function renomear(id) {
    const a = A.lista.find(x => x.id === id);
    const n = await perguntar('Nome da aba (vazio = volta a mostrar o assunto)', titulo(a), 'Renomear');
    if (n == null) return;
    a.nome = n.trim(); a.manual = !!a.nome; await api().aba_renomear(id, a.nome); desenhar();
  }

  faixa.addEventListener('click', e => {
    if (e.target.closest('.aba-mais')) return nova();
    const d = e.target.closest('[data-aba]');
    if (!d) return;
    if (e.target.closest('.aba-x')) return fechar(d.dataset.aba);
    trocar(d.dataset.aba);
  });
  faixa.addEventListener('auxclick', e => { const d = e.target.closest('[data-aba]'); if (d && e.button === 1 && A.lista.length > 1) fechar(d.dataset.aba); });
  faixa.addEventListener('dblclick', e => { const d = e.target.closest('[data-aba]'); if (d && !e.target.closest('.aba-x')) renomear(d.dataset.aba); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Tab' && !e.altKey && !e.metaKey && A.lista.length > 1 && !document.querySelector('.caixa')) {
      e.preventDefault();
      e.stopImmediatePropagation();
      if (A.mudando) return;
      const i = A.lista.findIndex(a => a.id === A.ativa), n = A.lista.length;
      trocar(A.lista[(i + (e.shiftKey ? n - 1 : 1)) % n].id);
      return;
    }
    if (!e.ctrlKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === 'n') { e.preventDefault(); nova(); }
    else if (k === 'w' && A.lista.length > 1) { e.preventDefault(); fechar(A.ativa); }
    else if (k === 'tab' && A.lista.length > 1) {
      e.preventDefault();
      const i = A.lista.findIndex(a => a.id === A.ativa), n = A.lista.length;
      trocar(A.lista[(i + (e.shiftKey ? n - 1 : 1)) % n].id);
    }
  }, true);

  // cada pedido atualiza o assunto da aba (o nome dado à mão continua por cima)
  const nomear = () => {
    const a = A.lista.find(x => x.id === A.ativa), t = resumo(texto.value.trim());
    if (!a || !t || texto.value.trim().startsWith('/')) return;
    a.assunto = t;
    api().aba_assunto && api().aba_assunto(a.id, t, null); desenhar();
  };
  texto.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !K.ocupada) nomear(); }, true);
  enviar.addEventListener('click', () => { if (!K.ocupada) nomear(); }, true);
  const quemAntes = window.quemDefinir;
  window.quemDefinir = (q, gravar = true) => {
    quemAntes(q, gravar);
    const a = A.lista.find(x => x.id === A.ativa);
    if (a && a.quem !== K.quem) { a.quem = K.quem; desenhar(); }
  };

  // som da aba de trás: na hora (o repasse ao voltar fica mudo)
  const somAntes = window.som;
  window.som = q => { if (!A.repetindo) somAntes(q); };

  const TRAB = ['inicio', 'texto_novo', 'texto', 'pensando', 'ferr', 'ferr_fim', 'kani_pensando', 'kani_estado', 'ajudante', 'pickle_progresso'];
  const evAntes = window.kcEv;
  window.kcEv = ev => {
    if (ev && ev.aba != null && A.mudando) { est(String(ev.aba)).fila.push(ev); return; }   // trocando de aba: chega depois
    if (ev && ev.aba != null && A.ativa && String(ev.aba) !== A.ativa) {
      const e = est(String(ev.aba));
      // Mesmo sem histórico aberto, o indicador acompanha a tarefa desta aba.
      e.fila.push(ev);
      if (TRAB.includes(ev.t) && !(ev.t === 'ajudante' && ev.fase === 'fim')) e.ocupada = true;
      if (ev.t === 'inicio' && ev.modelo) guardarModelo(String(ev.aba), ev.modelo);
      if (ev.t === 'permissao' || ev.t === 'pergunta') { e.aviso = 'pergunta'; somAntes('pergunta'); }
      if (['fim', 'saiu', 'ajudante_resposta'].includes(ev.t)) {
        const ok = !ev.erro && ev.ok !== false;
        e.ocupada = false; e.aviso = ok ? 'pronto' : 'erro'; somAntes(ok ? 'pronto' : 'erro');
      }
      desenhar();
      return;
    }
    evAntes(ev);
    if (ev && ev.t === 'inicio' && ev.modelo && A.ativa) { guardarModelo(A.ativa, ev.modelo); desenhar(); }
    if (ev && ['fim', 'saiu', 'ajudante_resposta', 'local', 'ajudante'].includes(ev.t)) desenhar();
  };
  function guardarModelo(id, m) {
    const a = A.lista.find(x => x.id === id);
    if (!a || a.modelo === m) return;
    a.modelo = m; api().aba_assunto && api().aba_assunto(id, null, m);
  }
  let marcaVista = '';
  setInterval(() => {   // a aba aberta acompanha o trabalhando/esperando sem esperar um evento
    const m = `${!!K.ocupada}${!!K.espera}${K.modelo}${K.quem}`;
    if (m !== marcaVista) { marcaVista = m; desenhar(); }
  }, 700);

  window.addEventListener('pywebviewready', async () => {
    if (!api().abas) return;
    const r = await api().abas();
    if (!r || !Array.isArray(r.lista)) return;
    A.lista = r.lista; A.ativa = String(r.ativa);
    A.modeloPadrao = K.modelo || '';
    est(A.ativa).visto = true;
    r.lista.forEach(a => { if (a.ocupada && a.id !== A.ativa) est(a.id).ocupada = true; });
    desenhar();
  });
  if (window.KC_MOVEL) setInterval(async () => {
    if (!A.ativa || A.mudando || document.hidden) return;
    try {
      const r = await api().abas();
      if (!Array.isArray(r?.lista)) return;
      if (!r.lista.some(a => String(a.id) === A.ativa)) {
        guardar(); await entrar(r.ativa, r);
      } else { A.lista = r.lista; desenhar(); }
    } catch (e) { /* a conexão SSE já sinaliza quando o PC está desconectado */ }
  }, 3000);
  window.KC_ABAS = A;
})();
