// KaniCode no celular (movel.py): imita o window.pywebview.api da janela do PC por HTTP e recebe os eventos por SSE.
// Carregado ANTES do script da janela; só existe na página servida pelo movel.py (na janela do PC não entra).
(() => {
  window.KC_MOVEL = true;
  window.KC_DE = 'movel-' + Math.random().toString(36).slice(2, 8);
  document.documentElement.classList.add('movel');

  async function chamar(nome, args) {
    const r = await fetch('/api/' + nome, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-KC-De': KC_DE },
                                           body: JSON.stringify(args) });
    if (r.status === 403) { location.reload(); throw new Error('sem chave'); }
    const j = await r.json();
    if (j.erro) throw new Error(j.erro);
    return j.r;
  }
  const base = new Proxy({}, { get: (_, nome) => (...args) => chamar(nome, args) });

  // historico: os cartões ainda sem resposta voltam VIVOS (no PC eles ficariam como "recusado" ao recarregar)
  const api = new Proxy({}, { get: (_, nome) => nome !== 'historico' ? base[nome] : async () => {
    const [h, pend] = await Promise.all([base.historico(), base.pendentes().catch(() => [])]);
    const ids = new Set((pend || []).map(e => e.id));
    if (ids.size) setTimeout(() => pend.forEach(ev => window.kcEv && kcEv(ev)), 0);
    return (h || []).filter(e => !((e.t === 'permissao' || e.t === 'pergunta') && ids.has(e.id)));
  } });
  window.pywebview = { api };

  // eventos ao vivo; caiu (celular dormiu, trocou de rede): reconecta e recarrega a conversa do arquivo
  let fonte, caiu = false;
  function ligar() {
    fonte = new EventSource('/eventos');
    fonte.onopen = () => {
      document.documentElement.classList.remove('sem-pc');
      if (caiu && typeof carregar === 'function') carregar();
      caiu = false;
    };
    fonte.onmessage = m => { try { window.kcEv && kcEv(JSON.parse(m.data)); } catch (e) { console.error(e); } };
    fonte.onerror = () => { caiu = true; document.documentElement.classList.add('sem-pc'); };
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && fonte && fonte.readyState === 2) { fonte.close(); ligar(); }
  });
  window.addEventListener('DOMContentLoaded', () => {
    ligar();
    // Enter no celular = nova linha (o teclado não tem Shift); envia pelo botão
    const t = document.getElementById('texto');
    t.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) e.stopImmediatePropagation(); }, true);
    t.placeholder = 'Fale com o Claude…';
    setTimeout(() => window.dispatchEvent(new Event('pywebviewready')), 0);
  });
})();
