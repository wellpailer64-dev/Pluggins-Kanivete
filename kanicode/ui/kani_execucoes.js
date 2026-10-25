/* Checkpoints da Kani: retomar e aprovar a ação concreta, sem expor raciocínio. */
window.KaniExecucoes = (() => {
  const dados = new Map();
  const receber = (ev, conversa) => {
    if (!/^[a-f0-9]{32}$/.test(ev.execucao || '')) return;
    const d = Object.assign(dados.get(ev.execucao) || {}, ev); dados.set(ev.execucao, d);
    let el = document.getElementById('kani-exec-' + ev.execucao);
    if (!el) { el = document.createElement('div'); el.id = 'kani-exec-' + ev.execucao; el.className = 'msg sis'; conversa.appendChild(el); }
    el.replaceChildren();
    const titulo = document.createElement('b'); titulo.textContent = 'Kani — ' + String(d.status).replaceAll('_', ' '); el.appendChild(titulo);
    if (d.status === 'concluida' || d.status === 'incerta' || d.status === 'negada' || d.status === 'aguardando_especialista') return;
    const texto = document.createElement('pre'); texto.style.whiteSpace = 'pre-wrap';
    texto.textContent = d.aprovacao ? JSON.stringify(d.aprovacao.args, null, 2) : d.pergunta || d.pedido || 'Checkpoint preservado.';
    el.appendChild(texto);
    let entrada;
    if (d.status === 'aguardando_informacao') { entrada = document.createElement('textarea'); entrada.placeholder = 'Informação necessária para continuar'; el.appendChild(entrada); }
    const botao = (rotulo, acao, concedida) => {
      const b = document.createElement('button'); b.textContent = rotulo;
      b.onclick = async () => {
        b.disabled = true;
        try { await pywebview.api.kani_execucao(acao, d.execucao, d.aprovacao?.chave || '', concedida, entrada?.value || ''); }
        catch (e) { texto.textContent = String(e); }
        finally { b.disabled = false; }
      };
      el.appendChild(b);
    };
    if (d.status === 'aguardando_aprovacao') {
      const acao = document.createElement('p'); acao.textContent = 'Aprovar operação: ' + (d.aprovacao?.acao || ''); el.appendChild(acao);
      botao('Aprovar esta ação', 'aprovar', true); botao('Negar', 'aprovar', false);
    } else botao('Retomar', 'retomar', false);
  };
  window.addEventListener('pywebviewready', async () => {
    try {
      const itens = await pywebview.api.kani_execucao('listar', '', '', false, '');
      const conversa = document.getElementById('conversa');
      if (conversa) for (const ev of itens || []) receber(ev, conversa);
    } catch (_) { /* A ponte pode ainda estar abrindo. Os próximos checkpoints aparecem ao vivo. */ }
  });
  return { receber };
})();

