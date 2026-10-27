/* Mensagens pendentes ficam visíveis sem tocar no fluxo da resposta em andamento. */
(() => {
  const nomes = {pendente:'Na fila · duplo clique para enviar agora', urgente:'Urgente · aguardando interrupção',
    enviando:'Entregando ao agente…', falha:'Não entregue · veja o aviso'};
  function desenhar(ev) {
    let b = conversa.querySelector('[data-mensagem-id="' + CSS.escape(ev.id) + '"]');
    if (!b) {
      b = bolha('eu', ''); b.dataset.mensagemId = ev.id;
      const conteudo = document.createElement('span'); conteudo.className = 'mensagem-texto'; b.appendChild(conteudo);
      const m = minis(ev.minis); if (m) b.prepend(m);
    }
    if (ev.estado === 'cancelada') { b.remove(); return; }
    b.dataset.mensagemEstado = ev.estado;
    b.dataset.mensagemTexto = ev.texto || '';
    b.querySelector('.mensagem-texto').textContent = ev.texto || '';
    let x = b.querySelector('.mensagem-cancelar');
    const cancelavel = ['pendente','urgente','falha'].includes(ev.estado);
    if (cancelavel && !x) {
      x = document.createElement('button'); x.type = 'button'; x.className = 'mensagem-cancelar'; x.textContent = '✕';
      x.title = 'Cancelar esta mensagem (não envia)'; x.setAttribute('aria-label', x.title); b.appendChild(x);
    } else if (!cancelavel) x?.remove();
    let editar = b.querySelector('.mensagem-editar');
    if (cancelavel && !editar) {
      editar = document.createElement('button'); editar.type = 'button'; editar.className = 'mensagem-editar';
      editar.textContent = '✎'; editar.title = 'Editar mensagem na fila'; editar.setAttribute('aria-label', editar.title);
      b.appendChild(editar);
    } else if (!cancelavel) editar?.remove();
    const editor = b.querySelector('.mensagem-editor');
    if (editor && !cancelavel) {
      editor.querySelector('.mensagem-salvar').disabled = true;
      editor.querySelector('.mensagem-edicao-erro').textContent = 'A mensagem já saiu da fila. Seu rascunho está aqui para copiar.';
    }
    b.classList.toggle('mensagem-pendente', ['pendente','urgente'].includes(ev.estado));
    b.classList.toggle('mensagem-urgente', ev.estado === 'urgente');
    let nota = b.querySelector('.mensagem-fila-nota');
    if (ev.estado === 'enviada') { nota?.remove(); b.title = ''; return; }
    if (!nota) { nota = document.createElement('small'); nota.className = 'mensagem-fila-nota'; b.appendChild(nota); }
    nota.textContent = ev.erro || nomes[ev.estado] || '';
    b.title = nomes[ev.estado] || '';
    if (ev.estado === 'enviando') {
      K.bolha = null;
      if (ev.quem && K.quem !== ev.quem) quemDefinir(ev.quem, false);
      ocupada(true); atividade('Enviando mensagem da fila');
    }
    if (ev.estado === 'falha') bolha('erro', ev.erro || 'A mensagem não foi entregue. A fila ficou pausada.');
  }
  window.mensagemEnfileirar = async (t, imgs) => {
    const id = crypto.randomUUID();
    const ev = {id, texto:t, minis:imgs.map(i => i.mini).filter(Boolean), quem:K.quem, estado:'pendente'};
    desenhar(ev); fim(); som('enviar');
    texto.value = ''; ajustar();
    try {
      const r = await api().mensagem_enviar(id, t, imgs, K.quem);
      if (!r) throw new Error('A fila não confirmou o recebimento.');
      // As mudanças chegam por evento; a resposta da API pode ser anterior ao último evento recebido.
    } catch (erro) {
      desenhar({...ev, estado:'falha', erro:String(erro.message || erro)});
    }
  };
  function abrirEditor(b) {
    if (b.querySelector('.mensagem-editor')) { b.querySelector('textarea').focus(); return; }
    const editor = document.createElement('form'); editor.className = 'mensagem-editor';
    const campo = document.createElement('textarea'); campo.value = b.dataset.mensagemTexto;
    campo.setAttribute('aria-label', 'Editar texto da mensagem'); campo.rows = 4;
    const salvar = document.createElement('button'); salvar.type = 'submit'; salvar.className = 'mensagem-salvar'; salvar.textContent = 'Salvar';
    const cancelar = document.createElement('button'); cancelar.type = 'button'; cancelar.textContent = 'Cancelar';
    const erro = document.createElement('small'); erro.className = 'mensagem-edicao-erro'; erro.setAttribute('role', 'status');
    const fechar = () => { editor.remove(); b.querySelector('.mensagem-texto').hidden = false; };
    cancelar.onclick = fechar;
    editor.append(campo, salvar, cancelar, erro); b.appendChild(editor);
    b.querySelector('.mensagem-texto').hidden = true;
    editor.addEventListener('keydown', e => {
      e.stopPropagation();
      if (e.key === 'Escape') { e.preventDefault(); fechar(); }
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); editor.requestSubmit(); }
    });
    editor.addEventListener('submit', async e => {
      e.preventDefault(); e.stopPropagation();
      if (salvar.disabled) return;
      salvar.disabled = true; erro.textContent = '';
      try {
        const ok = await api().mensagem_editar(b.dataset.mensagemId, campo.value);
        if (!ok) throw new Error('A mensagem já saiu da fila ou não está mais disponível.');
        fechar();
      } catch (x) {
        erro.textContent = String(x.message || x);
        salvar.disabled = !['pendente','urgente','falha'].includes(b.dataset.mensagemEstado);
      }
    });
    campo.focus();
  }
  conversa.addEventListener('click', async e => {
    const editar = e.target.closest('.mensagem-editar');
    if (editar) {
      e.preventDefault(); e.stopPropagation(); abrirEditor(editar.closest('[data-mensagem-id]')); return;
    }
    if (e.target.closest('.mensagem-editor')) { e.stopPropagation(); return; }
    const x = e.target.closest('.mensagem-cancelar'); if (!x) return;
    e.preventDefault(); e.stopPropagation();
    const b = x.closest('[data-mensagem-id]'); if (!b) return;
    let r = false;
    try { r = await api().mensagem_cancelar(b.dataset.mensagemId); } catch (erro) { /* ok */ }
    // falha local (a fila nem recebeu): some daqui mesmo; senão o evento 'cancelada' já tirou a bolha
    if (r || b.dataset.mensagemEstado === 'falha') { b.remove(); atividade('Mensagem cancelada'); }
  });
  conversa.addEventListener('dblclick', async e => {
    if (e.target.closest('.mensagem-cancelar, .mensagem-editar, .mensagem-editor')) return;
    const b = e.target.closest('.mensagem-pendente[data-mensagem-id]');
    if (!b) return;
    e.preventDefault();
    try { await api().mensagem_urgente(b.dataset.mensagemId); }
    catch (erro) { bolha('erro', String(erro.message || erro)); }
  });
  const eventoAntes = window.kcEv;
  window.mensagemLocalizar=async ref=>{
    const seletor='[data-mensagem-id="'+CSS.escape(ref.mensagem_id)+'"]';
    if(!conversa.querySelector(seletor)&&window.KC_ABAS?.ativa&&window.KC_ABAS.ativa!==String(ref.aba)){
      const aba=document.querySelector('.aba-chat[data-aba="'+CSS.escape(String(ref.aba))+'"]');
      if(!aba)return false;
      aba.click();
      for(let i=0;i<50&&window.KC_ABAS?.ativa!==String(ref.aba);i++)await new Promise(r=>setTimeout(r,40));
    }
    let alvo=conversa.querySelector(seletor);
    if(!alvo&&ref.texto){
      const normalizar=t=>String(t).replace(/\s+/g,' ').trim();
      const encontrados=[...conversa.querySelectorAll('.msg.eu')].filter(e=>normalizar(e.textContent).includes(normalizar(ref.texto)));
      if(encontrados.length===1)alvo=encontrados[0];
    }
    if(!alvo)return false;
    alvo.scrollIntoView({block:'center',behavior:'smooth'});
    alvo.animate([{outline:'2px solid #B6F23A'},{outline:'2px solid transparent'}],{duration:2200});
    return true;
  };
  window.kcEv = ev => {
    if (ev?.t === 'fila_mensagem') { desenhar(ev); return; }
    if (ev?.t === 'fila_livre') { ocupada(false); return; }
    if (ev?.t === 'eco_eu' && ev.de === 'fila') return;   // a bolha pendente já representa este envio
    return eventoAntes(ev);
  };
  const carregarAntes = window.carregar;
  window.carregar = async () => {
    const r = await carregarAntes();
    const pendentes = await api().mensagens_fila();
    if (Array.isArray(pendentes)) pendentes.forEach(desenhar);
    return r;
  };
})();
