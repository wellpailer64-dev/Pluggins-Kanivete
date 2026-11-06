// Fotografia do DOM carregado: não clica, não rola, não toca áudio e não envia.
const main = document.querySelector('#main');
const titulo = (main?.querySelector('header')?.innerText || '').split('\n')[0].trim();
const norm = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
const visivel = e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
const busca = document.querySelector('#side input[role="textbox"]');
const editor = main?.querySelector('footer [contenteditable="true"][role="textbox"]');
const esperado = dados.conversa;
if (esperado !== undefined && (!String(esperado).trim() || norm(esperado) !== norm(titulo)))
  throw new Error('Conversa aberta diferente da esperada; nenhuma mensagem lida.');
const n = Math.min(30, Math.max(0, Math.floor(Number(dados.n) || 0)));
if (n && !esperado) throw new Error('Informe conversa com o nome completo antes de ler mensagens.');
const linhas = [...(main?.querySelectorAll('[role="row"]') || [])].filter(e => e.querySelector('[data-id]'));
const resultado = {
  conversa: titulo || null,
  conversa_conferida: !!esperado,
  busca: {disponivel: !!busca, preenchida: !!busca?.value, seletor: '#side input[role="textbox"]'},
  editor: {disponivel: !!editor, tem_rascunho: !!editor?.innerText.trim(), seletor: '#main footer [contenteditable="true"][role="textbox"]'},
  mensagens_carregadas: linhas.length,
  historico_completo: false,
  aviso: 'Somente DOM carregado; não recupera histórico nem confirma recebimento/envio.',
  mensagens: []
};
if (n) resultado.mensagens = linhas.slice(-n).map(r => {
  const pre = r.querySelector('[data-pre-plain-text]')?.getAttribute('data-pre-plain-text') || '';
  const textos = [...r.querySelectorAll('span.selectable-text')].filter(e => !e.parentElement.closest('span.selectable-text'));
  const texto = textos.map(e => e.innerText).join(' ').trim();
  return {referencia: pre.slice(0, 250), texto: texto.slice(0, 2000), truncado: texto.length > 2000,
    imagem: !!r.querySelector('img'), video: !!r.querySelector('video,[data-icon*="video"]'),
    audio: !!r.querySelector('audio,button[aria-label*="mensagem de voz"]'),
    documento: !!r.querySelector('[data-icon^="document"]')};
});
return resultado;
