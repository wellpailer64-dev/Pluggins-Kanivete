// Eventos ficam na página entre consultas; leitura restrita ao grupo de comandos.
const titulo = () => (document.querySelector('#main header')?.innerText || '').split('\n')[0].trim();
if (titulo() !== 'KaniCode') throw new Error('Abra o grupo KaniCode para observar mensagens.');
const reiniciado = !globalThis.__kbWaEventos || globalThis.__kbWaEventos.versao !== 3;
if (reiniciado) {
  globalThis.__kbWaEventos?.observador?.disconnect();
  for (const acordar of (globalThis.__kbWaEventos?.esperas || [])) acordar('reiniciado');
  const estado = {versao: 3, pendentes: new Map(), vistos: new Set(), varreduras: 0, esperas: new Set()};
  const ler = () => {
    if (titulo() !== 'KaniCode') return;
    estado.varreduras++;
    for (const d of document.querySelectorAll('#main [data-id]')) {
      const id = d.getAttribute('data-id');
      if (!id || estado.vistos.has(id)) continue;
      const r = d.closest('[role=row]') || d;
      const txt = [...r.querySelectorAll('span.selectable-text')]
        .filter(e => !e.parentElement.closest('span.selectable-text')).map(e => e.innerText).join(' ').trim();
      const audio = !!r.querySelector('audio,button[aria-label="Reproduzir mensagem de voz"],button[aria-label="Pausar mensagem de voz"]');
      // Aguarda a montagem da mensagem: não consome um ID vazio/incompleto.
      if (!txt && !audio) continue;
      // Versões recentes usam ID simples: mantém a geometria do leitor wa.py.
      const main = document.querySelector('#main').getBoundingClientRect();
      const bolha = [...d.querySelectorAll('div')].map(e => e.getBoundingClientRect())
        .filter(b => b.width > 60 && b.width < main.width * .8).sort((a, b) => b.width - a.width)[0] || d.getBoundingClientRect();
      const eu = /^(true|false)_/.test(id) ? id.startsWith('true_') : bolha.x + bolha.width / 2 > main.x + main.width / 2;
      estado.vistos.add(id);
      estado.pendentes.set(id, {id, quem: eu ? 'Eu' : 'Outro', txt, audio,
        detectado: new Date().toISOString()});
    }
    while (estado.vistos.size > 2000) estado.vistos.delete(estado.vistos.values().next().value);
    while (estado.pendentes.size > 400) estado.pendentes.delete(estado.pendentes.keys().next().value);
    if (estado.pendentes.size) for (const acordar of [...estado.esperas]) acordar('mensagem');
  };
  let agendado = false;
  estado.observador = new MutationObserver(() => {
    if (agendado) return;
    agendado = true;
    setTimeout(() => { agendado = false; ler(); }, 80);
  });
  estado.observador.observe(document.body, {subtree: true, childList: true, characterData: true});
  estado.ler = ler;
  globalThis.__kbWaEventos = estado;
  ler();
}
const estado = globalThis.__kbWaEventos;
// Atualiza a espera sem reinstalar o observador nem descartar eventos pendentes.
estado.esperar = (confirmados, ms) => {
  for (const id of confirmados) estado.pendentes.delete(id);
  if (estado.pendentes.size) return Promise.resolve('mensagem');
  return new Promise(resolve => {
    const acordar = motivo => { clearTimeout(tempo); estado.esperas.delete(acordar); resolve(motivo); };
    const tempo = setTimeout(() => acordar('conferencia'), Math.min(60000, Math.max(100, ms)));
    estado.esperas.add(acordar);
  });
};
// IDs confirmados pelo receptor só são removidos depois de persistidos no disco.
for (const id of (dados.confirmados || [])) estado.pendentes.delete(id);
if (dados.conferir) estado.ler();
return {conversa: titulo(), mensagens: [...estado.pendentes.values()], fonte: 'eventos', reiniciado, varreduras: estado.varreduras};
