// Observa os callbacks existentes; preserva o resultado e os efeitos da interface original.
(() => {
  if (window.__kcProgressoObservador) return;
  window.__kcProgressoObservador = true;
  const fontes = {veOnExport:['render','Exportação de vídeo'], veOnRender:['render','Pré-render'],
    veOnComp:['render','Composição'], updateVideoDownloaderProgress:['download','Download de vídeo']};
  const pendentes = new Map();
  let enviando = false;
  function observar(nome, dados) {
    try {
      const d = typeof dados === 'string' ? JSON.parse(dados) : dados;
      if (!d || typeof d !== 'object') return;
      if (d.log && d.pct == null && d.percent == null && !d.complete && !d.done && !d.error) return;
      const [tipo, titulo] = fontes[nome], id = 'kanivete:' + nome + ':' + (d.hash || d.job || 'principal');
      const fim = !!(d.done || d.complete);
      const item = {id, tipo, titulo, pct:d.pct ?? d.percent ?? null,
        estado: d.error || (fim && d.success === false) ? 'erro' : fim ? (d.cancelado || d.cancelled ? 'cancelado' : 'concluido') : 'ativo',
        detalhe: d.error || d.message || d.status || ''};
      pendentes.set(id,item);
    } catch (_) { /* telemetria não interrompe o render */ }
  }
  for (const nome of Object.keys(fontes)) {
    const original = window[nome];
    if (typeof original !== 'function' || original.__kcProgresso) continue;
    const novo = function (...args) { observar(nome,args[0]); return original.apply(this,args); };
    novo.__kcProgresso = true; window[nome] = novo;
  }
  setInterval(async () => {
    if (enviando || !pendentes.size) return;
    enviando = true;
    const lote = Array.from(pendentes.values()); pendentes.clear();
    try { await KPLUG.chamar(PLUGIN_ID,'progresso',{itens:lote}); }
    catch (_) { /* o próximo sinal tenta novamente */ }
    finally { enviando = false; }
  }, 500);
})();
