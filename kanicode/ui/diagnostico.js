/* Falhas de inicialização e da ponte ficam consultáveis, sem registrar o texto enviado. */
(() => {
  const fila = [];
  function entregar() {
    const ponte = window.pywebview?.api;
    if (typeof ponte?.janela_diagnostico !== 'function') return;
    for (const item of fila.splice(0)) {
      try { Promise.resolve(ponte.janela_diagnostico(item.etapa, item.mensagem)).catch(() => {}); } catch (_) {}
    }
  }
  window.kaniRegistrarErro = (etapa, erro) => {
    const mensagem = String(erro?.stack || erro?.message || erro || 'Erro sem detalhe').slice(0, 1500);
    fila.push({etapa, mensagem});
    if (fila.length > 30) fila.shift();
    entregar();
  };
  addEventListener('error', e => {
    const recurso = e.target?.src || e.target?.href;
    window.kaniRegistrarErro(recurso ? 'recurso' : 'javascript', e.error || e.message || recurso);
  }, true);
  addEventListener('unhandledrejection', e => window.kaniRegistrarErro('promessa', e.reason));
  addEventListener('pywebviewready', entregar);
})();
