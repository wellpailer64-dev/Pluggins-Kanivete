(() => {
  // Só consulta o DOM; não abre conversas, não rola e não marca mensagens como lidas.
  const principal = document.querySelector('#main');
  const conversa = principal?.querySelector('header span[title]')?.getAttribute('title') || '';
  const pronto = !!document.querySelector('#pane-side');
  const mensagens = [];
  for (const caixa of principal?.querySelectorAll('[data-id]') || []) {
    const id = caixa.getAttribute('data-id');
    if (!id || id.startsWith('true_') || !caixa.closest('.message-in') && !caixa.querySelector('.message-in')) continue;
    const meta = caixa.querySelector('[data-pre-plain-text]')?.getAttribute('data-pre-plain-text') || '';
    const pessoa = meta.replace(/^\[[^\]]*\]\s*/, '').replace(/:\s*$/, '').trim() || conversa;
    // Texto selecionável exclui citações, reações e botões do balão.
    const texto = [...caixa.querySelectorAll('.selectable-text.copyable-text')]
      .filter(e => !e.closest('[data-testid="quoted-message"], [data-testid="quoted-message-container"]'))
      .map(e => e.innerText).join('\n').trim().slice(0, 16000);
    const audio = !!caixa.querySelector('[data-icon="audio-play"], [data-icon="ptt"], [data-icon="ptt-in"], audio, button[aria-label*="mensagem de voz"]');
    mensagens.push({id, conversa, pessoa, texto: texto || (audio ? '' : 'Mensagem sem texto (mídia ou anexo).'), audio});
  }
  const previas = [];
  for (const linha of document.querySelectorAll('#pane-side [role="row"]')) {
    const nome = linha.querySelector('span[title]')?.getAttribute('title');
    if (!nome) continue;
    const selo = [...linha.querySelectorAll('[aria-label]')].find(e => /\d+\s+(mensage(ns|m)\s+não\s+lida|unread message)/i.test(e.getAttribute('aria-label') || ''));
    const nao_lidas = selo?.getAttribute('aria-label') || '';
    const titulos = [...linha.querySelectorAll('span[title]')].map(e => e.getAttribute('title'));
    const texto = titulos.slice(1).filter(t => t !== nome).join(' ').slice(0, 4000) || linha.innerText.split('\n').slice(1).join(' ').slice(0, 4000);
    const audio = !!linha.querySelector('[data-icon="ptt"], [data-icon="ptt-in"], [data-icon="audio-play"]');
    previas.push({id: 'previa:' + nome + ':' + texto + ':' + nao_lidas, conversa: nome, pessoa: '', texto, audio, previa: true, nao_lidas});
  }
  return {pronto, conversa, mensagens, previas};
})()
