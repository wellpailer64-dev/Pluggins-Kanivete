// Uso medido pelo cliente e redefinições oficiais, consumidas somente pelo clique do usuário.
(() => {
  const painel = document.createElement('details');
  painel.className = 'codex-conta';
  painel.hidden = true;
  painel.innerHTML = '<summary>Uso e limites do Codex</summary><p class="codex-conta-estado" role="status">Consultando limites…</p><div class="codex-janelas"></div><p class="codex-reset-info"></p><button type="button" class="codex-atualizar">Atualizar limites</button> <button type="button" class="codex-redefinir" hidden>Usar 1 redefinição disponível</button><p class="codex-nota">A redefinição usa um benefício informado pela conta; não compra créditos. Tokens são atualizados quando o Codex registra uma medição.</p>';
  const ancora = document.querySelector('.rodape');
  if (!ancora) return;
  ancora.before(painel);
  const estado = painel.querySelector('.codex-conta-estado');
  const janelas = painel.querySelector('.codex-janelas');
  const info = painel.querySelector('.codex-reset-info');
  const portal = document.createElement('button');
  portal.type = 'button';
  portal.textContent = 'Abrir painel oficial de uso';
  portal.onclick = async () => {
    try { await api().resposta_abrir_link('https://chatgpt.com/codex/settings/usage'); }
    catch (_) { estado.textContent = 'Não foi possível abrir o painel oficial de uso.'; }
  };
  painel.querySelector('.codex-nota').before(portal);
  const atualizarBt = painel.querySelector('.codex-atualizar');
  const redefinirBt = painel.querySelector('.codex-redefinir');
  let consultando = false, limiteInformado = false, tentativa = null, credito = '', cota = null, tentarApos = 0;
  const horario = v => v ? new Date(v * 1000).toLocaleString('pt-BR', {dateStyle:'short', timeStyle:'short'}) : 'horário não informado';
  function desenhar() {
    painel.hidden = K.quem !== 'codex';
    if (painel.hidden || !cota) return;
    const esgotado = cota.atingido || limiteInformado || cota.h5 >= 1 || cota.sem >= 1;
    estado.textContent = esgotado ? 'O Codex informou limite de uso atingido.' : 'Limites consultados na conta do Codex.';
    if (esgotado) painel.open = true;
    janelas.replaceChildren();
    for (const [chave, zera, minutos, padrao] of [['h5','h5_zera','primaria_minutos','Janela principal'], ['sem','sem_zera','secundaria_minutos','Janela secundária']]) {
      if (cota[chave] == null) continue;
      const p = document.createElement('p');
      const duracao = cota[minutos] ? ' (' + cota[minutos] + ' min)' : '';
      p.textContent = padrao + duracao + ': ' + Math.round(cota[chave] * 100) + '% usado · redefine em ' + horario(cota[zera]) + ' (horário local).';
      janelas.appendChild(p);
    }
    info.textContent = cota.redefinicoes == null ? 'A conta não informou a quantidade de redefinições disponíveis.' : 'Redefinições disponíveis: ' + cota.redefinicoes + '.';
    redefinirBt.hidden = !(tentativa || (esgotado && cota.redefinicoes > 0));
    redefinirBt.textContent = tentativa ? 'Conferir redefinição pendente' : 'Usar 1 redefinição disponível';
  }
  function receberCota(valor) {
    if (!valor || (cota?.medido_em && !valor.medido_em)) return;
    cota = {...cota, ...valor};
    K.cotaCodex = {...K.cotaCodex, ...valor};
    cotas(); desenhar();
  }
  async function atualizar(forcar = false) {
    if (consultando || K.quem !== 'codex' || document.hidden || (!forcar && Date.now() < tentarApos)) return;
    tentarApos = Date.now() + 30000;
    consultando = true; atualizarBt.disabled = true;
    try {
      const r = await api().codex_limites(forcar);
      if (!r?.ok) { estado.textContent = r?.mensagem || 'O cliente não informou os limites.'; return; }
      tentarApos = 0;
      limiteInformado = !!r.cota.atingido;
      if (r.redefinicao_pendente) {
        tentativa = r.redefinicao_pendente.tentativa;
        credito = r.redefinicao_pendente.credito || '';
      }
      receberCota(r.cota);
    } catch (_) { estado.textContent = 'Não foi possível consultar os limites agora. Atualize para tentar novamente.'; }
    finally { consultando = false; atualizarBt.disabled = false; }
  }
  atualizarBt.onclick = () => atualizar(true);
  redefinirBt.onclick = async () => {
    if (consultando) return;
    tentativa = tentativa || crypto.randomUUID();
    if (!credito) credito = (cota.creditos_redefinicao || []).find(c => c.status === 'available')?.id || '';
    consultando = true; redefinirBt.disabled = true; atualizarBt.disabled = true;
    try {
      const r = await api().codex_redefinir(tentativa, credito);
      if (r.pendente) { tentativa = r.tentativa || tentativa; credito = r.credito || credito; }
      else { tentativa = null; credito = ''; }
      if (r.cota) { limiteInformado = !!r.cota.atingido; receberCota(r.cota); }
      estado.textContent = r.mensagem || 'Redefinição não confirmada.';
      if (!r.pendente && r.ok) redefinirBt.hidden = true;
    } catch (_) { estado.textContent = 'Resposta não recebida. Use Conferir redefinição pendente para verificar a mesma tentativa.'; }
    finally { consultando = false; redefinirBt.disabled = false; atualizarBt.disabled = false; if (tentativa) redefinirBt.textContent = 'Conferir redefinição pendente'; }
  };
  let andamento = null;
  const mensagens = new Map();
  const etapas = new Map();
  const comentarios = new Map();
  function registrarComentario(ev) {
    if (ev.reiniciar) { andamento = null; mensagens.clear(); comentarios.clear(); }
    const texto = String(ev.texto || '').trim();
    if (!texto) return;
    const chave = ev.id || texto;
    let comentario = comentarios.get(chave);
    if (!comentario?.isConnected) {
      comentario = bolhaAjudante('codex', texto, true);
      comentario.classList.add('codex-comentario');
      comentarios.set(chave, comentario);
      andamento = null; mensagens.clear();
    } else if (comentario.dataset.texto !== texto) {
      const nova = bolhaAjudante('codex', texto, true);
      nova.classList.add('codex-comentario');
      comentario.replaceWith(nova);
      comentario = nova;
      comentarios.set(chave, comentario);
    }
    comentario.dataset.texto = texto;
    fim();
  }
  function registrarProgresso(ev) {
    const texto = String(ev.texto || '').trim();
    if (!texto) return;
    if (ev.reiniciar) { andamento = null; mensagens.clear(); }
    if (!andamento?.isConnected || andamento !== conversa.lastElementChild) {
      mensagens.clear();
      andamento = document.createElement('details');
      andamento.className = 'codex-andamento';
      andamento.open = true;
      const titulo = document.createElement('summary');
      titulo.textContent = 'Andamento do Codex';
      andamento.appendChild(titulo);
      conversa.appendChild(andamento);
    }
    const chave = ev.id || texto;
    let p = mensagens.get(chave);
    if (!p) { p = document.createElement('p'); mensagens.set(chave, p); andamento.appendChild(p); }
    p.textContent = texto;
  }
  const anterior = window.kcEv;
  window.kcEv = ev => {
    if (ev.t === 'codex_progresso') { registrarComentario(ev); return; }
    if (ev.t === 'ajudante_resposta' && ev.quem === 'codex') {
      for (const comentario of comentarios.values()) {
        if (comentario.dataset.texto === String(ev.texto || '').trim()) comentario.remove();
      }
      comentarios.clear(); andamento = null; mensagens.clear();
    }
    if (ev.t === 'ajudante' && ev.quem === 'codex' && ev.fase === 'inicio') {
      andamento = null; mensagens.clear(); etapas.clear(); comentarios.clear();
    }
    if (ev.t === 'ajudante' && ev.quem === 'codex' && ev.fase === 'passo' && ev.operacao) {
      if (ev.operacao === 'inicio') etapas.set(ev.id, ev.texto);
      const etapa = etapas.get(ev.id) || ev.texto;
      if (etapa !== 'pensando') registrarProgresso({id: 'etapa-' + ev.id, texto: (ev.operacao === 'fim' ? (ev.ok ? '✓ Concluído: ' : '⚠ Falhou: ') : 'Em andamento: ') + etapa});
    }
    if (ev.t === 'ajudante' && ev.quem === 'codex' && ev.fase === 'passo' && ev.texto?.startsWith('editou ')) {
      registrarProgresso({texto: ev.texto});
    }
    if (ev.t === 'agente_uso') {
      if (ev.quem === K.quem && K.ocupada) { K.tokMsg = ev.tokens || 0; status(); }
      return;
    }
    if (ev.t === 'codex_uso') {
      if (K.quem === 'codex' && K.ocupada) {
        K.codexMedido = true; K.tokMsg = ev.uso?.saida || 0; K.contexto = ev.uso?.entrada || 0;
        if (AJ.codex) { AJ.codex.tokens = ev.tokens || 0; desenharAj('codex'); }
        status();
      }
      receberCota(ev.cota);
      return;
    }
    if (ev.t === 'codex_limite') {
      limiteInformado = true;
      if (!cota) cota = {};
      receberCota(ev.cota);
      desenhar(); painel.open = true;
      atualizar(true);
      return;
    }
    if (ev.t === 'ajudante' && ev.quem === 'codex' && ev.fase === 'inicio') {
      K.codexMedido = false; K.contexto = 0;
    }
    if (ev.t === 'ajudante' && ev.quem === 'codex' && ev.cota && cota?.medido_em && !ev.cota.medido_em) ev = {...ev, cota};
    const r = anterior(ev);
    if (ev.t === 'ajudante' && ev.quem === 'codex' && ev.cota) receberCota(ev.cota);
    if (ev.t === 'ajudante_resposta' && ev.quem === 'codex') atualizar(true);
    return r;
  };
  window.addEventListener('kc-agente', () => { desenhar(); atualizar(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) atualizar(); });
  window.addEventListener('focus', () => atualizar(true));
  setInterval(() => atualizar(), 5000);
})();
