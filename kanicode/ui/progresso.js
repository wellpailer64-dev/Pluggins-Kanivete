// Faixa compartilhada no PC e no celular; consulta leve, sem entrar no contexto dos agentes.
(() => {
  const faixa = document.createElement('section');
  faixa.id = 'kc-progresso'; faixa.hidden = true; faixa.setAttribute('aria-label', 'Render e downloads');
  const referencia = document.querySelector('#status');
  if (referencia) referencia.after(faixa); else document.body.prepend(faixa);
  let ocupado = false;
  function mostrar(itens) {
    if (!Array.isArray(itens)) return;
    faixa.replaceChildren(); faixa.hidden = !itens.length;
    for (const item of itens) {
      const linha = document.createElement('div'), titulo = document.createElement('span');
      const valor = document.createElement('small'), barra = document.createElement('progress');
      linha.className = 'kc-progresso-item';
      titulo.textContent = item.titulo; titulo.title = item.detalhe || item.titulo;
      const estados = {concluido:'Concluído', erro:'Falhou', cancelado:'Cancelado'};
      valor.textContent = estados[item.estado] || (item.sem_sinal ? 'Sem atualização' : item.pct == null ? 'Em andamento' : Math.round(item.pct) + '%');
      barra.max = 100;
      if (item.pct != null) barra.value = item.pct;
      barra.setAttribute('aria-label', item.titulo);
      linha.dataset.estado = item.estado; linha.append(titulo, valor, barra); faixa.append(linha);
    }
  }
  async function consultar() {
    if (ocupado || document.hidden || !window.pywebview?.api?.progresso_listar) return;
    ocupado = true;
    try { mostrar(await pywebview.api.progresso_listar()); }
    catch (_) { for (const el of faixa.querySelectorAll('small')) el.textContent = 'Sem conexão'; }
    finally { ocupado = false; }
  }
  window.KCProgresso = {mostrar};
  setInterval(consultar, 1000);
  document.addEventListener('visibilitychange', consultar);
  window.addEventListener('pywebviewready', consultar);
  consultar();
})();
