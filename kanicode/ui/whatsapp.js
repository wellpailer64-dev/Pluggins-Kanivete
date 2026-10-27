/* Avisos falados do WhatsApp: o monitor continua ligado quando este painel é recolhido. */
(() => {
  const el = id => document.getElementById(id), api = () => window.pywebview.api;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const trilho = document.createElement('button');
  trilho.id = 'whatsapp-trilho'; trilho.className = 'trilho'; trilho.title = 'WhatsApp: avisos falados e ignorados';
  trilho.setAttribute('aria-label', 'WhatsApp'); trilho.setAttribute('aria-expanded', 'false'); trilho.setAttribute('aria-controls', 'whatsapp-painel');
  trilho.innerHTML = '<span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11.5a8 8 0 0 1-12 7L3 20l1.5-5A8 8 0 1 1 20 11.5Z"/><path d="M8 7c0 5 3 8 8 8l1-3-3-1-1 1-2-2 1-1-1-3Z"/></svg></span><span class="vert">WHATSAPP</span>';
  (el('trilhos-dir') || el('atv-trilho').parentElement).append(trilho);
  const painel = document.createElement('section'); painel.id = 'whatsapp-painel'; painel.className = 'det'; painel.inert = true;
  painel.innerHTML = `<div class="cab"><b>WhatsApp</b><span class="esp"></span><button class="bt" id="wa-fechar" aria-label="Recolher WhatsApp">»</button></div>
    <div class="wa-corpo"><button class="wa-acao" id="wa-ligar" aria-pressed="false">Ligar avisos</button>
    <p id="wa-estado" role="status">Desligado</p><p id="wa-erro" role="alert"></p>
    <p class="wa-nota">Abra o WhatsApp Web no navegador 🌐 do KaniCode e faça login. Com o monitor ligado, a Kani anuncia o remetente e lê o texto disponível. Não precisa treinar um modelo.</p>
    <p class="wa-nota">Acompanha novas mensagens visíveis e prévias de conversas não lidas na lista. Conversas fora da tela podem não ser detectadas; prévias podem estar cortadas e não identificar o remetente do grupo. Não abre conversas automaticamente. Ao ligar ou abrir uma conversa, o conteúdo existente serve de referência e não é anunciado.</p>
    <label><input type="checkbox" id="wa-audios"> Transcrever e resumir áudios com IA local</label>
    <p class="wa-nota">Áudios novos da conversa aberta: pode marcar como ouvido ao carregar o áudio em mudo. Em conversas fechadas, avisa apenas que chegou áudio. Voz, transcrição e resumo usam os modelos locais já instalados.</p>
    <label for="wa-ignorados">Ignorar conversas, grupos ou remetentes</label><textarea id="wa-ignorados" rows="4" placeholder="Um nome exato por linha"></textarea>
    <label for="wa-palavras">Ignorar mensagens que contenham</label><textarea id="wa-palavras" rows="3" placeholder="Uma palavra ou expressão por linha"></textarea>
    <p class="wa-nota">Sem diferenciar maiúsculas. O filtro de palavras também confere a transcrição do áudio.</p>
    <button class="wa-acao" id="wa-salvar">Salvar filtros</button>
    <h4>Últimos avisos desta sessão</h4><p class="wa-nota">Textos ficam só na memória; apenas os filtros são salvos.</p><div id="wa-historico"></div></div>`;
  el('atv').append(painel);
  let estado = null, ocupado = false, edicao = false, historico = '';
  function desenhar(d) {
    estado = d; trilho.classList.toggle('ligado', d.ligado);
    el('wa-ligar').textContent = d.ligado ? 'Desligar avisos' : 'Ligar avisos'; el('wa-ligar').setAttribute('aria-pressed', String(d.ligado));
    el('wa-estado').textContent = d.situacao + (d.pendentes ? ` · ${d.pendentes} na fila` : '');
    if (!edicao) {
      el('wa-ignorados').value = (d.ignorados || []).join('\n'); el('wa-palavras').value = (d.palavras || []).join('\n'); el('wa-audios').checked = d.audios;
    }
    const html = (d.historico || []).map(m => `<article><b>${esc(m.pessoa || m.conversa)}</b>${m.pessoa && m.pessoa !== m.conversa ? ` · ${esc(m.conversa)}` : ''}
      <p>${m.previa ? 'Prévia: ' : ''}${esc(m.resumo || m.texto)}</p><button class="wa-acao" data-ignorar="${esc(m.conversa)}">Ignorar conversa</button></article>`).join('');
    if (html !== historico) { el('wa-historico').innerHTML = html || '<p class="wa-nota">Nenhum aviso ainda.</p>'; historico = html; }
  }
  async function consultar() {
    if (ocupado || !window.pywebview?.api) return;
    try { desenhar(await api().whatsapp_estado()); } catch (e) { el('wa-erro').textContent = String(e.message || e); }
  }
  async function acao(fn) {
    if (ocupado) return;
    ocupado = true; el('wa-erro').textContent = ''; el('wa-ligar').disabled = true; el('wa-salvar').disabled = true;
    try { const d = await fn(); if (!d.ok) throw new Error(d.erro || 'Não foi possível concluir.'); desenhar(d); }
    catch (e) { el('wa-erro').textContent = String(e.message || e); }
    finally { ocupado = false; el('wa-ligar').disabled = false; el('wa-salvar').disabled = false; }
  }
  const linhas = id => el(id).value.split('\n').map(s => s.trim()).filter(Boolean);
  trilho.onclick = () => window.kaniPainelDireito(trilho.getAttribute('aria-expanded') !== 'true', 'whatsapp');
  el('wa-fechar').onclick = () => window.kaniPainelDireito(false, 'whatsapp');
  el('wa-ligar').onclick = () => acao(() => api().whatsapp_ligar(!estado?.ligado));
  el('wa-salvar').onclick = () => acao(async () => {
    const d = await api().whatsapp_configurar({ignorados: linhas('wa-ignorados'), palavras: linhas('wa-palavras'), audios: el('wa-audios').checked});
    if (d.ok) edicao = false; return d;
  });
  painel.addEventListener('input', () => { edicao = true; });
  painel.addEventListener('click', e => {
    const bt = e.target.closest('[data-ignorar]'); if (!bt) return;
    const nomes = new Set(linhas('wa-ignorados')); nomes.add(bt.dataset.ignorar); el('wa-ignorados').value = [...nomes].join('\n'); edicao = true; el('wa-salvar').click();
  });
  painel.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); window.kaniPainelDireito(false, 'whatsapp'); trilho.focus(); } });
  new MutationObserver(() => {
    const aberto = trilho.getAttribute('aria-expanded') === 'true'; painel.inert = !aberto;
    if (aberto) { api().painel_espaco(360).catch(() => {}); consultar(); }
  }).observe(trilho, {attributes: true, attributeFilter: ['aria-expanded']});
  setInterval(() => { if (!document.hidden && trilho.getAttribute('aria-expanded') === 'true') consultar(); }, 1500);
})();
