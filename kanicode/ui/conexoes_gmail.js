/* Gmail: mensagens são exibidas como texto; credenciais ficam no Python. */
(() => {
  const el = id => document.getElementById(id), api = () => window.pywebview.api;
  let ocupado = false, estado = null, timer = null, proxima = '', busca = '';
  const mensagem = texto => { el('gmail-status').textContent = texto; };
  function controles() {
    el('conexao-gmail').querySelectorAll('button, input, textarea').forEach(e => { e.disabled = ocupado; });
    el('gmail-conectar').disabled = ocupado || !estado?.configurado || estado?.conectando;
  }
  function limpar() {
    el('gmail-lista').replaceChildren(); el('gmail-leitura').hidden = true;
    el('gmail-corpo').textContent = ''; el('gmail-assunto').textContent = ''; el('gmail-cabecalho').textContent = '';
    el('gmail-resultados').textContent = ''; el('gmail-rascunho').reset(); proxima = ''; el('gmail-mais').hidden = true;
  }
  function render(s) {
    estado = s; window.kaniConexoesEstado('gmail', s);
    el('gmail-reutilizar').hidden = !s.reutilizavel || s.conectado || s.conectando;
    el('gmail-importar').hidden = s.conectado || s.conectando;
    el('gmail-conectar').hidden = s.conectado || s.conectando;
    el('gmail-desconectar').hidden = !s.conectado && !s.conectando;
    el('gmail-consulta').hidden = !s.conectado;
    if (!s.conectado) limpar();
    mensagem(s.mensagem || (s.conectado ? 'Gmail conectado.' : 'Conecte sua conta Gmail.'));
    clearTimeout(timer);
    if (s.conectando && el('configuracoes').open) timer = setTimeout(atualizar, 1200);
    controles();
  }
  async function atualizar() {
    try { render(await api().gmail_status()); }
    catch (e) { mensagem(String(e.message || e)); window.kaniConexoesEstado('gmail', null); }
  }
  async function executar(fn) {
    if (ocupado) return;
    ocupado = true; controles();
    try { await fn(); } catch (e) { mensagem(String(e.message || e)); }
    finally { ocupado = false; controles(); }
  }
  async function buscar(mais = false) {
    await executar(async () => {
      const termo = mais ? busca : el('gmail-termo').value;
      const r = await api().gmail_buscar(termo, mais ? proxima : ''); busca = termo;
      if (!mais) el('gmail-lista').replaceChildren();
      for (const m of r.mensagens) {
        const linha = document.createElement('p'), abrir = document.createElement('button');
        abrir.type = 'button'; abrir.textContent = `${m.assunto} · ${m.de} · ${m.data}`;
        abrir.addEventListener('click', () => executar(async () => {
          const l = await api().gmail_ler(m.id);
          el('gmail-assunto').textContent = l.assunto;
          el('gmail-cabecalho').textContent = `${l.de} → ${l.para} · ${l.data}`;
          el('gmail-corpo').textContent = l.texto || l.resumo;
          el('gmail-leitura').hidden = false;
        }));
        linha.append(abrir); el('gmail-lista').append(linha);
      }
      proxima = r.proxima || ''; el('gmail-mais').hidden = !proxima;
      el('gmail-resultados').textContent = `${el('gmail-lista').children.length} mensagens carregadas.`;
    });
  }
  for (const [id, metodo] of Object.entries({reutilizar:'usar_calendar', importar:'importar', conectar:'conectar', desconectar:'desconectar'})) {
    el('gmail-' + id).addEventListener('click', () => executar(async () => render(await api()['gmail_' + metodo]())));
  }
  el('gmail-busca').addEventListener('submit', e => { e.preventDefault(); buscar(); });
  el('gmail-mais').addEventListener('click', () => buscar(true));
  el('gmail-rascunho').addEventListener('submit', e => {
    e.preventDefault(); executar(async () => {
      const r = await api().gmail_rascunho(el('gmail-para').value, el('gmail-novo-assunto').value, el('gmail-texto').value);
      mensagem(r.mensagem); el('gmail-rascunho').reset();
    });
  });
  el('configuracoes').addEventListener('close', () => { clearTimeout(timer); limpar(); });
  window.kaniGmailAtualizar = atualizar;
})();
