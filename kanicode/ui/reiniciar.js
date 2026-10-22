/* Usa o reinício existente: aguarda todas as abas terminarem antes de reabrir. */
(() => {
  const botao = document.getElementById('reiniciar');
  botao.addEventListener('click', async () => {
    if (botao.disabled) return;
    botao.disabled = true;
    try {
      const resultado = await window.pywebview.api.reiniciar();
      if (String(resultado).startsWith('depois:')) {
        botao.title = 'Reinício agendado para quando as tarefas terminarem';
        botao.setAttribute('aria-label', botao.title);
        bolha('sis', 'O KaniCode vai reiniciar quando as tarefas em andamento terminarem.');
      }
    } catch (e) {
      botao.disabled = false;
      bolha('erro', 'Não foi possível reiniciar o KaniCode: ' + String(e.message || e));
    }
  });
})();
