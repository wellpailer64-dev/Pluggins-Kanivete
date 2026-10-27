async mensagem => {
  // Captura só o áudio solicitado e restaura o player mesmo em caso de erro.
  const cabecalho = () => document.querySelector('#main header span[title]')?.getAttribute('title');
  if (cabecalho() !== mensagem.conversa) return {erro: 'a conversa mudou; abra o áudio para ouvi-lo depois'};
  const caixa = [...document.querySelectorAll('#main [data-id]')].find(e => e.getAttribute('data-id') === mensagem.id);
  if (!caixa) return {erro: 'áudio saiu da tela'};
  let media = caixa.querySelector('audio'), mudo = media?.muted;
  if (media && !media.paused) return {erro: 'este áudio já está sendo ouvido'};
  const original = HTMLMediaElement.prototype.play;
  let instalado = false;
  try {
    if (!media?.src) {
      if ([...document.querySelectorAll('audio,video')].some(m => !m.paused)) return {erro: 'outro áudio está tocando'};
      const botao = caixa.querySelector('button[aria-label="Reproduzir mensagem de voz"], button[aria-label="Play voice message"], [data-icon="audio-play"]');
      if (!botao) return {erro: 'WhatsApp ainda não disponibilizou o áudio'};
      HTMLMediaElement.prototype.play = function () {
        if (!media) { media = this; mudo = this.muted; this.muted = true; }
        return original.apply(this, arguments);
      };
      instalado = true;
      (botao.closest('button,[role="button"]') || botao).click();
      for (let i = 0; i < 40 && !media?.src; i++) {
        await new Promise(r => setTimeout(r, 150));
        if (cabecalho() !== mensagem.conversa) return {erro: 'a conversa mudou'};
      }
    }
    if (!media?.src) return {erro: 'o arquivo de áudio não carregou'};
    media.pause();
    const resposta = await fetch(media.src, {signal: AbortSignal.timeout(10000)});
    if (!resposta.ok) return {erro: 'falha ao carregar o áudio'};
    const blob = await resposta.blob();
    if (blob.size > 20 * 1024 * 1024) return {erro: 'áudio acima do limite de 20 MB'};
    const b64 = await new Promise((resolve, reject) => {
      const leitor = new FileReader(); leitor.onload = () => resolve(leitor.result.split(',')[1]); leitor.onerror = reject; leitor.readAsDataURL(blob);
    });
    return {b64};
  } catch (e) { return {erro: String(e.message || e)}; }
  finally {
    if (instalado) { HTMLMediaElement.prototype.play = original; if (media) media.pause(); }
    if (media && mudo !== undefined) media.muted = mudo;
  }
}
