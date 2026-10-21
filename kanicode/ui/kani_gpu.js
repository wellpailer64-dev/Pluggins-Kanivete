/* Telemetria local: só na Kani, visível, sem sobrepor chamadas ou consumir tokens. */
(() => {
  let timer = null, pendente = false, geracao = 0;
  const amostras = [], ativo = () => K.quem === 'kani' && !document.hidden;
  const numero = n => typeof n === 'number' && Number.isFinite(n);
  function desenhar(d) {
    const uso = d?.disponivel && numero(d.uso) ? Math.max(0, Math.min(100, d.uso)) : null;
    $('gpu').classList.toggle('sem-dados', uso === null);
    $('gpu-uso').textContent = uso === null ? 'GPU · indisponível' : `GPU ${Math.round(uso)}%`;
    if (uso === null) amostras.length = 0;
    else { amostras.push(uso); if (amostras.length > 30) amostras.shift(); }
    $('gpu-linha').setAttribute('points', amostras.map((v, i) => `${80 - (amostras.length - 1 - i) * 80 / 29},${19 - v * .18}`).join(' '));
    const memoria = d?.disponivel && numero(d.memoria_usada) && numero(d.memoria_total) && d.memoria_total > 0
      ? `${(d.memoria_usada / 1024 ** 3).toFixed(1)} / ${(d.memoria_total / 1024 ** 3).toFixed(1)} GB` : '';
    $('gpu-memoria').textContent = memoria;
    $('gpu').title = d?.disponivel
      ? `${d.nome} · uso total da GPU do computador${memoria ? ' · VRAM ' + memoria : ''}${numero(d.temperatura) ? ' · ' + d.temperatura + ' °C' : ''}`
      : 'Leitura da GPU indisponível neste computador';
  }
  async function atualizar() {
    if (!ativo() || pendente || !api()) return;
    const versao = geracao;
    pendente = true;
    try {
      const d = await api().gpu_info();
      if (versao === geracao && ativo()) desenhar(d);
    } catch (_) { if (versao === geracao && ativo()) desenhar(null); }
    finally {
      pendente = false;
      if (ativo()) timer = setTimeout(atualizar, 1500);
    }
  }
  function sincronizar() {
    clearTimeout(timer); timer = null; geracao++;
    amostras.length = 0;
    $('gpu-linha').setAttribute('points', '');
    if (ativo()) {
      $('gpu-uso').textContent = 'GPU · consultando…';
      $('gpu-memoria').textContent = '';
      atualizar();
    }
  }
  window.addEventListener('kc-agente', sincronizar);
  document.addEventListener('visibilitychange', sincronizar);
})();
