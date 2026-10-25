/* Eventos delegados sobrevivem ao streaming e à recuperação do histórico. */
(() => {
  const aviso = document.createElement('div');
  aviso.className = 'recursos-aviso'; aviso.hidden = true; aviso.setAttribute('role', 'status');
  document.body.append(aviso);
  let avisoTimer;
  function avisar(t) { aviso.textContent = String(t); aviso.hidden = false; clearTimeout(avisoTimer); avisoTimer = setTimeout(() => aviso.hidden = true, 6000); }
  const erro = e => avisar(e?.message || e || 'Não foi possível concluir esta ação.');
  async function copiarTexto(t) {
    if (!window.KC_MOVEL) return api().resposta_copiar_texto(t);
    try { await navigator.clipboard.writeText(t); }
    catch (_) {
      const antes = document.activeElement, area = document.createElement('textarea');
      area.value = t; area.style.cssText = 'position:fixed;left:-9999px;top:0'; document.body.append(area); area.select();
      const ok = document.execCommand('copy'); area.remove(); antes?.focus();
      if (!ok) throw Error('Seu navegador não permitiu copiar.');
    }
    return true;
  }
  async function copiar(botao, codigo) {
    try {
      await copiarTexto(codigo.textContent);
      const antes = botao.textContent; botao.textContent = '✓ Copiado';
      setTimeout(() => { if (botao.isConnected) botao.textContent = antes; }, 1800);
    } catch (e) { erro(e); }
  }

  const cache = new Map();
  const eventoAntes = window.kcEv;
  window.kcEv = ev => {
    if (['inicio','texto_novo','ajudante_resposta','ferr_fim'].includes(ev.t)) cache.clear();
    return eventoAntes(ev);
  };
  function miniatura(alvo) {
    if (!cache.has(alvo)) {
      const p = api().miniatura(alvo).catch(() => null);
      cache.set(alvo, p);
      if (cache.size > 32) cache.delete(cache.keys().next().value);
    }
    return cache.get(alvo);
  }
  function imagensNo(no) {
    if (no.nodeType !== 1) return;
    const imagens = [...no.querySelectorAll('img[data-imagem-local]')];
    if (no.matches('img[data-imagem-local]')) imagens.push(no);
    for (const img of imagens) {
      if (img.dataset.carregada) continue;
      img.dataset.carregada = '1';
      miniatura(img.dataset.imagemLocal).then(url => {
        if (url && img.isConnected) img.src = url;
        else if (img.isConnected) img.alt = 'Imagem indisponível · clique para tentar abrir';
      });
    }
  }
  // vídeos: o Python baixa o link (Runway) para o disco D e entrega por 127.0.0.1; o mesmo vídeo não baixa duas vezes
  const videosProntos = new Map();
  function videosNo(no) {
    if (no.nodeType !== 1) return;
    const lista = [...no.querySelectorAll('.resposta-video')];
    if (no.matches('.resposta-video')) lista.push(no);
    for (const el of lista) {
      if (el.dataset.carregado) continue;
      el.dataset.carregado = '1';
      const alvo = el.dataset.video, v = el.querySelector('video'), estado = el.querySelector('.video-estado');
      if (window.KC_MOVEL) { v.src = alvo; v.hidden = false; estado.remove(); continue; }
      if (!videosProntos.has(alvo)) videosProntos.set(alvo, api().resposta_video(alvo));
      videosProntos.get(alvo).then(d => {
        if (!el.isConnected) return;
        el.dataset.caminho = d.caminho;
        v.src = d.url; v.hidden = false; estado.remove();
        el.querySelectorAll('[data-video-acao="pasta"], [data-video-acao="salvar"]').forEach(b => { b.disabled = false; });
        if (d.baixado) el.querySelector('[data-video-acao="pasta"]').title = 'Salvo em ' + d.caminho;
      }).catch(e => {
        videosProntos.delete(alvo);
        if (!el.isConnected) return;
        estado.textContent = 'Não deu para abrir o vídeo: ' + ((e && e.message) || e);
        el.classList.add('erro');
      });
    }
  }
  conversa.addEventListener('click', e => {
    const b = e.target.closest('[data-video-acao]');
    if (!b) return;
    e.preventDefault();
    const el = b.closest('.resposta-video'), v = el.querySelector('video'), acao = b.dataset.videoAcao;
    if (acao === 'repetir') { v.loop = !v.loop; b.setAttribute('aria-pressed', String(v.loop)); b.classList.toggle('on', v.loop); }
    else if (acao === 'pasta' && el.dataset.caminho) api().resposta_abrir_caminho(el.dataset.caminho).catch(erro);
    else if (acao === 'salvar' && el.dataset.caminho) api().resposta_salvar_video(el.dataset.caminho).catch(erro);
  });
  const novos = no => { imagensNo(no); videosNo(no); };
  new MutationObserver(rs => rs.forEach(r => r.addedNodes.forEach(novos))).observe(conversa, {childList:true,subtree:true});
  novos(conversa);

  const dialog = document.createElement('dialog');
  dialog.className = 'imagem-visor'; dialog.setAttribute('aria-label', 'Visualizador de imagem');
  dialog.innerHTML = `<div class="visor-barra"><span class="visor-nome"></span>
    <button type="button" data-visor="menos" title="Diminuir zoom" aria-label="Diminuir zoom">−</button><output class="visor-zoom">100%</output>
    <button type="button" data-visor="mais" title="Aumentar zoom" aria-label="Aumentar zoom">＋</button>
    <button type="button" data-visor="ajustar" title="Ajustar à tela (0)">Ajustar</button>
    <button type="button" data-visor="tela" title="Tela cheia" aria-label="Tela cheia">⛶</button>
    <button type="button" data-visor="copiar" disabled>⧉ Copiar</button><button type="button" data-visor="salvar" disabled>↓ Salvar</button>
    <button type="button" data-visor="fechar" title="Fechar (Esc)" aria-label="Fechar imagem">×</button></div>
    <div class="visor-palco"><div class="visor-conteudo"><img alt="" draggable="false" hidden></div></div>
    <div class="visor-estado" role="status"></div>`;
  document.body.append(dialog);
  const palco = dialog.querySelector('.visor-palco'), conteudo = dialog.querySelector('.visor-conteudo'), img = conteudo.querySelector('img');
  const estado = dialog.querySelector('.visor-estado'), botao = acao => dialog.querySelector(`[data-visor="${acao}"]`);
  const V = {geracao:0, escala:1, pronto:false, url:'', nome:'imagem.png', foco:null, telaNativa:false, telaBrowser:false};
  function desenhar(escala, centro = false) {
    if (!V.pronto) return;
    const anterior = V.escala, x = (palco.scrollLeft + palco.clientWidth / 2) / anterior, y = (palco.scrollTop + palco.clientHeight / 2) / anterior;
    V.escala = Math.max(.02, Math.min(16, escala));
    const w = img.naturalWidth * V.escala, h = img.naturalHeight * V.escala;
    const cw = Math.max(palco.clientWidth, w + 32), ch = Math.max(palco.clientHeight, h + 32);
    conteudo.style.width = cw + 'px'; conteudo.style.height = ch + 'px';
    img.style.width = w + 'px'; img.style.height = h + 'px'; img.style.left = (cw - w) / 2 + 'px'; img.style.top = (ch - h) / 2 + 'px';
    dialog.querySelector('.visor-zoom').textContent = Math.round(V.escala * 100) + '%';
    palco.scrollLeft = centro ? (cw - palco.clientWidth) / 2 : x * V.escala - palco.clientWidth / 2;
    palco.scrollTop = centro ? (ch - palco.clientHeight) / 2 : y * V.escala - palco.clientHeight / 2;
  }
  function ajustar() { desenhar(Math.min(1, (palco.clientWidth - 32) / img.naturalWidth, (palco.clientHeight - 32) / img.naturalHeight), true); }
  async function abrir(origem, foco) {
    const versao = ++V.geracao;
    V.foco = foco; V.pronto = false; V.url = ''; img.hidden = true; img.removeAttribute('src');
    botao('copiar').disabled = botao('salvar').disabled = true;
    estado.textContent = 'Carregando imagem completa…';
    dialog.querySelector('.visor-nome').textContent = 'Imagem';
    if (!dialog.open) dialog.showModal();
    // No desktop, expande a janela nativa; no navegador, o botão ⛶ usa Fullscreen API.
    if (!window.KC_MOVEL && !V.telaNativa) {
      V.telaNativa = true;
      api().resposta_tela_cheia(true).then(() => {
        if (!dialog.open) return api().resposta_tela_cheia(false);
        if (V.pronto) ajustar();
      }).catch(e => { V.telaNativa = false; estado.textContent = e?.message || String(e); });
    }
    try {
      const d = origem.startsWith('data:image/') ? {url:origem,nome:'imagem.png'} : await api().resposta_imagem(origem);
      if (versao !== V.geracao || !dialog.open) return;
      if (!d?.url || !/^data:image\/(png|jpeg|webp|gif|bmp);base64,/i.test(d.url)) throw Error('Imagem indisponível.');
      img.onload = () => {
        if (versao !== V.geracao || !dialog.open) return;
        V.pronto = true; V.url = d.url; V.nome = d.nome || 'imagem.png'; img.hidden = false;
        dialog.querySelector('.visor-nome').textContent = V.nome;
        botao('copiar').disabled = botao('salvar').disabled = false;
        estado.textContent = `${img.naturalWidth} × ${img.naturalHeight} · arraste para mover · use +/− ou a roda para zoom`;
        ajustar();
      };
      img.onerror = () => { estado.textContent = 'Não foi possível carregar esta imagem.'; };
      img.src = d.url;
    } catch (e) { if (versao === V.geracao) estado.textContent = e?.message || String(e); }
  }
  function fechar() {
    V.geracao++; V.pronto = false; V.url = ''; img.removeAttribute('src'); img.onload = img.onerror = null;
    if (V.telaBrowser && document.fullscreenElement) document.exitFullscreen().catch(() => {});
    V.telaBrowser = false;
    if (V.telaNativa) { V.telaNativa = false; api().resposta_tela_cheia(false).catch(erro); }
    dialog.close(); if (V.foco?.isConnected) V.foco.focus();
  }
  async function copiarImagem() {
    if (!window.KC_MOVEL) return api().resposta_copiar_imagem(V.url);
    if (!window.ClipboardItem || !navigator.clipboard?.write) throw Error('Este navegador não permite copiar imagens. Use Salvar.');
    const canvas = document.createElement('canvas'); canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
    canvas.getContext('2d').drawImage(img, 0, 0);
    const png = new Promise((resolve, reject) => canvas.toBlob(b => b ? resolve(b) : reject(Error('Falha ao copiar imagem.')), 'image/png'));
    return navigator.clipboard.write([new ClipboardItem({'image/png':png})]);
  }
  dialog.addEventListener('click', async e => {
    const bt = e.target.closest('[data-visor]'); if (!bt) return;
    const acao = bt.dataset.visor;
    if (acao === 'fechar') return fechar();
    if (acao === 'mais') return desenhar(V.escala * 1.25);
    if (acao === 'menos') return desenhar(V.escala / 1.25);
    if (acao === 'ajustar') return ajustar();
    if (acao === 'tela') {
      bt.disabled = true;
      try {
        if (!window.KC_MOVEL) V.telaNativa = await api().resposta_tela_cheia(!V.telaNativa);
        else if (V.telaBrowser && document.fullscreenElement) { await document.exitFullscreen(); V.telaBrowser = false; }
        else { await document.documentElement.requestFullscreen(); V.telaBrowser = true; }
        ajustar();
      } catch (_) { estado.textContent = 'Tela cheia indisponível neste ambiente. O visualizador continua aberto.'; }
      finally { bt.disabled = false; }
      return;
    }
    if (!V.pronto) return;
    const versao = V.geracao;
    bt.disabled = true;
    try {
      if (acao === 'copiar') { await copiarImagem(); if (versao === V.geracao) estado.textContent = 'Imagem copiada.'; }
      if (acao === 'salvar') {
        let salvo = true;
        if (window.KC_MOVEL) {
          const a = document.createElement('a'); a.href = V.url; a.download = V.nome; document.body.append(a); a.click(); a.remove();
        } else salvo = await api().resposta_salvar_imagem(V.url);
        if (versao === V.geracao) estado.textContent = salvo ? 'Imagem salva.' : 'Salvamento cancelado.';
      }
    } catch (e) { if (versao === V.geracao) estado.textContent = e?.message || String(e); }
    finally { if (versao === V.geracao && V.pronto) bt.disabled = false; }
  });
  dialog.addEventListener('cancel', e => { e.preventDefault(); fechar(); });
  document.addEventListener('keydown', e => {
    if (!dialog.open) return;
    if (['Escape','+','=','-','0'].includes(e.key)) {
      e.preventDefault(); e.stopImmediatePropagation();
      if (e.key === 'Escape') fechar(); else if (e.key === '0') ajustar(); else desenhar(V.escala * (e.key === '-' ? .8 : 1.25));
    }
  }, true);
  palco.addEventListener('wheel', e => { e.preventDefault(); desenhar(V.escala * (e.deltaY < 0 ? 1.15 : 1 / 1.15)); }, {passive:false});
  const ponteiros = new Map(); let gesto = null;
  const distancia = () => { const [a,b] = [...ponteiros.values()]; return b ? Math.hypot(a.x-b.x,a.y-b.y) : 0; };
  palco.addEventListener('pointerdown', e => {
    if (e.button > 0) return;
    palco.setPointerCapture(e.pointerId); ponteiros.set(e.pointerId,{x:e.clientX,y:e.clientY});
    gesto = {x:e.clientX,y:e.clientY,left:palco.scrollLeft,top:palco.scrollTop,dist:distancia(),escala:V.escala};
  });
  palco.addEventListener('pointermove', e => {
    if (!ponteiros.has(e.pointerId) || !gesto) return;
    ponteiros.set(e.pointerId,{x:e.clientX,y:e.clientY});
    if (ponteiros.size > 1 && gesto.dist) desenhar(gesto.escala * distancia() / gesto.dist);
    else { palco.scrollLeft = gesto.left + gesto.x - e.clientX; palco.scrollTop = gesto.top + gesto.y - e.clientY; }
  });
  for (const evento of ['pointerup','pointercancel','lostpointercapture']) palco.addEventListener(evento, e => { ponteiros.delete(e.pointerId); gesto = null; });
  window.addEventListener('resize', () => { if (dialog.open) desenhar(V.escala, true); });

  // Captura permite abrir links mesmo com a prevenção antiga de navegação da conversa.
  document.addEventListener('click', e => {
    const bloco = e.target.closest('[data-copiar-codigo]'), inline = e.target.closest('[data-copiar-inline]');
    if (bloco || inline) {
      e.preventDefault(); const bt = bloco || inline;
      copiar(bt, bt.closest(bloco ? '.codigo' : '.codigo-inline').querySelector('code')); return;
    }
    const pasta = e.target.closest('[data-abrir-caminho]');
    if (pasta) { e.preventDefault(); api().resposta_abrir_caminho(pasta.dataset.abrirCaminho).catch(erro); return; }
    const a = e.target.closest('a[data-link-externo]');
    if (a) {
      e.preventDefault();
      if (window.KC_MOVEL) window.open(a.href, '_blank', 'noopener,noreferrer');
      else api().resposta_abrir_link(a.href).catch(erro);
      return;
    }
    const foto = e.target.closest('[data-imagem]'), mini = e.target.closest('.minis img');
    if (foto || mini) { e.preventDefault(); abrir(foto ? foto.dataset.imagem : mini.src, foto || mini); }
  }, true);
  conversa.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('.print[data-imagem]')) { e.preventDefault(); abrir(e.target.dataset.imagem, e.target); }
  });
  const seletor = $('navegador-links');
  window.addEventListener('pywebviewready', async () => {
    if (window.KC_MOVEL) return;
    try { const d = await api().resposta_navegador(); if (d?.navegador) seletor.value = d.navegador; } catch (e) { erro(e); }
  });
  seletor.addEventListener('change', async () => {
    try { await api().resposta_navegador(seletor.value); } catch (e) { erro(e); }
  });
})();
