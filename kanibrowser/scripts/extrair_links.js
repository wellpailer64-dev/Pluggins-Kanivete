// O motor fornece dados e aceita return; não posta, não clica e não envia formulários.
const limite = Math.min(500, Math.max(1, Number(dados.limite) || 100));
const vistos = new Set();
return [...document.querySelectorAll('a[href]')].filter(a => {
  if (!/^https?:/.test(a.href) || vistos.has(a.href)) return false;
  if (dados.visiveis && (!a.getClientRects().length || getComputedStyle(a).visibility === 'hidden')) return false;
  if (dados.com_nome && !(a.innerText || a.getAttribute('aria-label') || a.title).trim()) return false;
  vistos.add(a.href);
  return true;
}).slice(0, limite).map(a => ({texto: (a.innerText || a.getAttribute('aria-label') || a.title).trim().slice(0, 240), url: a.href}));
