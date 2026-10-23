/* Configurações > Conexões. Nenhum token OAuth atravessa a ponte da interface. */
(() => {
  const dialog = document.getElementById('configuracoes');
  const el = id => document.getElementById(id);
  const apiGoogle = () => window.pywebview.api;
  let ocupado = false, timer = null, configurado = false, selecionado = null;
  const icones = {
    calendar: '<rect x="4" y="5" width="24" height="23" rx="5"/><path d="M4 12h24M11 3v5M21 3v5"/><text x="16" y="23" text-anchor="middle" stroke="none" fill="currentColor" font-size="10" font-weight="700">31</text>',
    drive: '<path d="m13 4 7 0 12 21-7 0z"/><path d="m13 4-12 21 7 0 12-21M1 25l4 6h20l7-6z"/>',
    gmail: '<rect x="3" y="6" width="26" height="21" rx="4"/><path d="m4 8 12 10L28 8M8 13v12M24 13v12"/>',
    github: '<circle cx="8" cy="8" r="4"/><circle cx="24" cy="10" r="4"/><circle cx="8" cy="25" r="4"/><path d="M8 12v9M24 14v2q0 5-12 5"/>'
  };
  const apps = [
    { id: 'calendar', nome: 'Google Calendar', descricao: 'Agenda e lembretes falados.', cor: '#71a7ff' },
    { id: 'drive', nome: 'Google Drive', descricao: 'Arquivos e materiais dos projetos.', cor: '#72c99a',
      usos: ['Localizar arquivos e pastas de trabalho.', 'Consultar materiais e documentos dos projetos.'] },
    { id: 'gmail', nome: 'Gmail', descricao: 'Mensagens e informações dos clientes.', cor: '#ed9289',
      usos: ['Localizar mensagens e conversas importantes.', 'Consultar informações e anexos dos clientes.'] },
    { id: 'github', nome: 'GitHub', descricao: 'Repositórios, tarefas e revisões.', cor: '#c4abff',
      usos: ['Consultar issues e acompanhar pendências.', 'Ver pull requests e informações dos repositórios.'] }
  ];
  const svg = id => `<svg viewBox="0 0 34 34" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icones[id]}</svg>`;
  const cards = new Map(), estados = new Map();
  window.kaniConexoesEstado = (id, s) => {
    estados.set(id, s);
    const card = cards.get(id);
    card.classList.toggle('conectado', !!s?.conectado);
    card.querySelector('.conexao-situacao').textContent = !s ? 'Verificação indisponível' : s.conectando ? 'Conectando…' : s.conectado ? 'Conectado' : 'Não conectado';
    const ativos = [...estados.values()].filter(e => e?.conectado).length;
    const falhas = [...estados.values()].filter(e => !e).length;
    el('conexoes-resumo').textContent = (ativos ? `${ativos} ${ativos === 1 ? 'conexão ativa' : 'conexões ativas'}` : 'Nenhuma conexão ativa') + (falhas ? ' · verificação parcial' : '');
  };
  for (const app of apps) {
    const card = document.createElement('button');
    card.type = 'button'; card.className = 'conexao-card'; card.dataset.conexao = app.id;
    card.style.setProperty('--conexao-cor', app.cor);
    card.innerHTML = `<span class="conexao-card-topo"><span class="conexao-icone">${svg(app.id)}</span><span class="conexao-seta" aria-hidden="true">↗</span></span><strong>${app.nome}</strong><span class="conexao-descricao">${app.descricao}</span><span class="conexao-situacao">${['calendar', 'drive', 'gmail'].includes(app.id) ? 'Verificando…' : 'Sugestão · em breve'}</span>`;
    card.addEventListener('click', () => abrirApp(app.id));
    cards.set(app.id, card); el('conexoes-grade').append(card);
  }
  function abrirApp(id) {
    selecionado = id;
    el('conexoes-catalogo').hidden = !!id;
    el('conexoes-nav').hidden = !id;
    el('conexao-google').hidden = id !== 'calendar';
    el('conexao-drive').hidden = id !== 'drive';
    el('conexao-gmail').hidden = id !== 'gmail';
    el('conexao-sugestao').hidden = !id || ['calendar', 'drive', 'gmail'].includes(id);
    if (id && !['calendar', 'drive', 'gmail'].includes(id)) {
      const app = apps.find(a => a.id === id);
      el('sugestao-titulo').textContent = app.nome;
      el('sugestao-descricao').textContent = app.descricao;
      el('sugestao-icone').innerHTML = svg(id);
      el('sugestao-usos').replaceChildren(...app.usos.map(texto => {
        const item = document.createElement('li'); item.textContent = texto; return item;
      }));
    }
    dialog.scrollTop = 0;
    if (id) el(id === 'calendar' ? 'google-titulo' : id === 'drive' ? 'drive-titulo' : id === 'gmail' ? 'gmail-titulo' : 'sugestao-titulo').focus();
  }
  el('conexoes-voltar').addEventListener('click', () => {
    const anterior = selecionado; abrirApp(null); cards.get(anterior)?.focus();
  });
  el('conexoes-repetir').addEventListener('click', atualizar);
  const botoes = ['google-importar', 'google-conectar', 'google-sync', 'google-desconectar'];
  function mensagem(texto, erro = false) {
    el('google-status').textContent = texto;
    el('google-status').classList.toggle('erro', erro);
  }
  function render(s) {
    configurado = s.configurado;
    window.kaniConexoesEstado('calendar', s);
    el('conexoes-erro').hidden = true; el('conexoes-repetir').hidden = true;
    el('google-importar').hidden = s.conectado || s.conectando;
    el('google-conectar').hidden = s.conectado || s.conectando;
    el('google-conectar').disabled = !s.configurado || ocupado;
    el('google-sync').hidden = !s.conectado;
    el('google-desconectar').hidden = !s.conectado && !s.conectando;
    el('google-preferencias').hidden = !s.conectado;
    el('google-ajuda').open = !s.configurado;
    const atualizado = s.ultima_sync ? new Date(s.ultima_sync).toLocaleString('pt-BR') : 'ainda não realizada';
    mensagem(s.mensagem || (s.conectado ? `${s.conta} · Somente leitura\nÚltima sincronização: ${atualizado}` :
      s.configurado ? 'Aplicativo configurado. Conecte sua conta Google.' : 'Configure o aplicativo Google uma vez para conectar sua conta.'));
    const lista = el('google-calendarios');
    lista.replaceChildren();
    for (const c of s.calendarios) {
      const label = document.createElement('label'), input = document.createElement('input');
      input.type = 'checkbox'; input.value = c.id; input.checked = s.selecionados.includes(c.id);
      label.append(input, document.createTextNode(c.nome + (c.principal ? ' · principal' : '')));
      lista.append(label);
    }
    el('google-antes').value = s.antes;
    const eventos = el('google-eventos'); eventos.replaceChildren();
    if (!s.eventos.length) eventos.textContent = 'Nenhum evento nos calendários selecionados nos próximos 7 dias.';
    for (const e of s.eventos.slice(0, 40)) {
      const article = document.createElement('article'), titulo = document.createElement('b');
      const horario = document.createElement('time'), calendario = document.createElement('small');
      titulo.textContent = e.titulo;
      horario.dateTime = e.inicio;
      horario.textContent = e.dia_inteiro ? new Date(e.inicio + 'T12:00:00').toLocaleDateString('pt-BR') + ' · dia inteiro' : new Date(e.inicio).toLocaleString('pt-BR');
      calendario.textContent = e.calendario;
      article.append(titulo, horario, calendario); eventos.append(article);
    }
    if (s.avisos?.estado === 'erro') mensagem(el('google-status').textContent + '\nFalha ao preparar os avisos. Consulte avisos/preparar.log.', true);
    if (s.avisos?.estado === 'preparando') mensagem(el('google-status').textContent + '\nPreparando os avisos falados…');
    clearTimeout(timer);
    if ((s.conectando || s.avisos?.estado === 'preparando') && dialog.open) timer = setTimeout(atualizar, 1500);
  }
  async function atualizar() {
    try { render(await apiGoogle().google_status()); }
    catch (e) {
      mensagem(String(e.message || e), true);
      window.kaniConexoesEstado('calendar', null);
      el('conexoes-erro').textContent = String(e.message || e);
      el('conexoes-erro').hidden = false; el('conexoes-repetir').hidden = false;
    }
    await window.kaniDriveAtualizar?.();
    await window.kaniGmailAtualizar?.();
  }
  async function executar(nome, args = []) {
    if (ocupado) return;
    ocupado = true;
    botoes.forEach(id => { el(id).disabled = true; });
    el('google-preferencias').querySelectorAll('input, button').forEach(e => { e.disabled = true; });
    mensagem(nome === 'google_importar' ? 'Selecione o JSON OAuth do Google…' : 'Aguarde…');
    try { render(await apiGoogle()[nome](...args)); }
    catch (e) { mensagem(String(e.message || e), true); }
    finally {
      ocupado = false;
      botoes.forEach(id => { el(id).disabled = false; });
      el('google-conectar').disabled = !configurado;
      el('google-preferencias').querySelectorAll('input, button').forEach(e => { e.disabled = false; });
    }
  }
  window.kaniConfiguracoesAbrir = async () => {
    abrirApp(null);
    window.kaniConfiguracoesMenu?.(false);
    if (!dialog.open) dialog.showModal();
    await atualizar();
  };
  el('config-fechar').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => clearTimeout(timer));
  dialog.addEventListener('click', e => { if (e.target === dialog && e.offsetX < 0) dialog.close(); });
  el('config-conexoes').addEventListener('click', () => window.kaniConfiguracoesAbrir());
  el('google-importar').addEventListener('click', () => executar('google_importar'));
  el('google-conectar').addEventListener('click', () => executar('google_conectar'));
  el('google-sync').addEventListener('click', () => executar('google_sincronizar'));
  el('google-desconectar').addEventListener('click', () => executar('google_desconectar'));
  el('google-preferencias').addEventListener('submit', e => {
    e.preventDefault();
    const ids = [...el('google-calendarios').querySelectorAll('input:checked')].map(i => i.value);
    executar('google_selecionar', [ids, Number(el('google-antes').value)]);
  });
})();
