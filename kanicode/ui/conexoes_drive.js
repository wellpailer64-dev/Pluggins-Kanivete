/* Drive: autorização independente, navegação e operações por item. Tokens ficam no Python. */
(() => {
  const el = id => document.getElementById(id), dialog = el('configuracoes');
  const api = () => window.pywebview.api;
  const botoes = ['drive-reutilizar', 'drive-importar', 'drive-conectar', 'drive-sync', 'drive-desconectar'];
  let estado = null, ocupado = false, timer = null, proxima = '', buscaAtual = '', pastaAtual = '', naLixeira = false;
  let trilha = [], selecionado = null, criando = false;
  function mensagem(texto, erro = false) {
    el('drive-status').textContent = texto; el('drive-status').classList.toggle('erro', erro);
  }
  function controles() {
    botoes.forEach(id => { el(id).disabled = ocupado || !estado; });
    el('drive-conectar').disabled = ocupado || !estado?.configurado || estado?.conectando;
    el('drive-consulta').querySelectorAll('input, button, select').forEach(e => { e.disabled = ocupado; });
    el('drive-enviar').disabled = el('drive-criar').disabled = ocupado || !estado?.controle_total || naLixeira;
  }
  function local() {
    el('drive-local').textContent = naLixeira ? 'Lixeira' : trilha.length ? trilha.map(p => p.nome).join(' / ') : pastaAtual === 'root' ? 'Meu Drive' : 'Todos os arquivos · novos itens em Meu Drive';
    el('drive-voltar').hidden = !trilha.length;
    el('drive-visao').value = naLixeira ? 'lixeira' : pastaAtual === 'root' || trilha.length ? 'root' : '';
  }
  function fecharOperacao() { selecionado = null; criando = false; el('drive-operacao').hidden = true; }
  function listar(r, anexar = false) {
    proxima = r.proxima || '';
    const lista = el('drive-arquivos');
    if (!anexar) { lista.replaceChildren(); fecharOperacao(); }
    for (const arquivo of r.arquivos) {
      const linha = document.createElement('article'), icone = document.createElement('span');
      const nome = document.createElement('b'), tipo = document.createElement('small'), abrir = document.createElement('button');
      icone.textContent = arquivo.pasta ? '▱' : '▤'; icone.setAttribute('aria-hidden', 'true');
      const texto = document.createElement('div');
      nome.textContent = arquivo.nome; tipo.textContent = arquivo.lixeira ? 'Na lixeira' : arquivo.pasta ? 'Pasta' : 'Arquivo';
      texto.append(nome, tipo); abrir.type = 'button'; abrir.textContent = 'Abrir';
      abrir.setAttribute('aria-label', 'Abrir ' + arquivo.nome);
      abrir.addEventListener('click', async () => {
        try {
          const url = new URL(arquivo.url);
          if (url.protocol !== 'https:' || url.hostname !== 'drive.google.com') throw new Error('Link do Drive inválido.');
          await api().resposta_abrir_link(url.href);
        } catch (e) { mensagem(String(e.message || e), true); }
      });
      const acoes = document.createElement('div'); acoes.className = 'drive-item-acoes'; acoes.append(abrir);
      if (arquivo.pasta && !arquivo.lixeira) {
        const entrar = document.createElement('button'); entrar.type = 'button'; entrar.textContent = 'Entrar';
        entrar.setAttribute('aria-label', 'Entrar na pasta ' + arquivo.nome);
        entrar.addEventListener('click', () => navegar(arquivo.id, false, [...trilha, {id: arquivo.id, nome: arquivo.nome}]));
        acoes.append(entrar);
      }
      if (estado?.controle_total || (!arquivo.pasta && !arquivo.lixeira)) {
        const mais = document.createElement('button'); mais.type = 'button'; mais.textContent = '⋯';
        mais.setAttribute('aria-label', 'Ações de ' + arquivo.nome);
        mais.addEventListener('click', () => operacao(arquivo)); acoes.append(mais);
      }
      linha.append(icone, texto, acoes); lista.append(linha);
    }
    el('drive-mais').hidden = !proxima;
    const total = lista.children.length;
    el('drive-resultado-status').textContent = !total ? 'Nenhum arquivo encontrado.' : `${total} ${total === 1 ? 'resultado' : 'resultados'}${proxima ? ' · há mais arquivos' : ''}${r.incompleta ? ' · busca parcial do Google' : ''}`;
    controles();
  }
  function render(s) {
    estado = s; window.kaniConexoesEstado('drive', s);
    el('drive-reutilizar').hidden = !s.reutilizavel || s.conectado || s.conectando;
    el('drive-importar').hidden = s.conectado || s.conectando;
    el('drive-conectar').hidden = (s.conectado && s.controle_total) || s.conectando;
    el('drive-conectar').textContent = s.conectado ? 'Autorizar controle total' : 'Conectar Google Drive';
    el('drive-sync').hidden = !s.conectado;
    el('drive-desconectar').hidden = !s.conectado && !s.conectando;
    el('drive-consulta').hidden = !s.conectado;
    el('drive-ajuda').open = !s.conectado;
    el('drive-permissao').textContent = s.controle_total ? 'Controle total' : s.conectado ? 'Somente leitura' : 'Controle de arquivos';
    const quando = s.ultima_sync ? new Date(s.ultima_sync).toLocaleString('pt-BR') : 'ainda não realizada';
    mensagem(s.mensagem || (s.conectado ? `${s.conta} · ${s.controle_total ? 'Controle total' : 'Somente leitura · autorize o controle total para alterar arquivos'}\nÚltima sincronização: ${quando}` :
      s.configurado ? 'Aplicativo configurado. Conecte sua conta Google Drive.' : 'Use a configuração do Calendar ou importe o JSON OAuth.'));
    buscaAtual = pastaAtual = ''; naLixeira = false; trilha = []; el('drive-termo').value = ''; local();
    listar({arquivos: s.arquivos || [], proxima: s.proxima});
    controles(); clearTimeout(timer);
    if (s.conectando && dialog.open) timer = setTimeout(atualizar, 1500);
  }
  async function atualizar() {
    if (ocupado) return;
    try { render(await api().drive_status()); }
    catch (e) {
      estado = null; controles(); window.kaniConexoesEstado('drive', null);
      mensagem(String(e.message || e), true);
    }
  }
  async function executar(nome) {
    if (ocupado) return;
    ocupado = true; clearTimeout(timer); controles(); mensagem('Aguarde…');
    try { render(await api()[nome]()); }
    catch (e) { mensagem(String(e.message || e), true); }
    finally { ocupado = false; controles(); }
  }
  async function buscar(anexar = false) {
    if (ocupado || !estado?.conectado) return;
    ocupado = true; controles(); el('drive-resultado-status').textContent = 'Buscando…';
    const termo = anexar ? buscaAtual : el('drive-termo').value.trim();
    try {
      const r = await api().drive_buscar(termo, anexar ? proxima : '', pastaAtual, naLixeira);
      buscaAtual = termo; listar(r, anexar);
    } catch (e) { el('drive-resultado-status').textContent = String(e.message || e); }
    finally { ocupado = false; controles(); }
  }
  async function navegar(pasta, lixeira, caminho = []) {
    if (ocupado) return;
    ocupado = true; controles();
    try {
      const r = await api().drive_buscar('', '', pasta, lixeira);
      pastaAtual = pasta; naLixeira = lixeira; trilha = caminho; buscaAtual = ''; el('drive-termo').value = '';
      local(); listar(r);
    } catch (e) { mensagem(String(e.message || e), true); local(); }
    finally { ocupado = false; controles(); }
  }
  function operacao(arquivo = null) {
    selecionado = arquivo; criando = !arquivo;
    el('drive-op-titulo').textContent = criando ? 'Nova pasta' : arquivo.nome;
    el('drive-op-escolha').hidden = criando;
    el('drive-op-acao').replaceChildren();
    const opcoes = [];
    if (arquivo && !arquivo.pasta && !arquivo.lixeira) opcoes.push(['baixar', 'Baixar arquivo']);
    if (arquivo && estado.controle_total) {
      if (arquivo.lixeira) opcoes.push(['restaurar', 'Restaurar da lixeira']);
      else opcoes.push(['renomear', 'Renomear'], ['mover', 'Mover para outra pasta'], ['lixeira', 'Mover para a lixeira']);
    }
    for (const [valor, texto] of opcoes) {
      const option = document.createElement('option'); option.value = valor; option.textContent = texto; el('drive-op-acao').append(option);
    }
    el('drive-operacao').hidden = false; camposOperacao();
    el('drive-operacao').scrollIntoView({block: 'nearest'});
  }
  function camposOperacao() {
    const acao = criando ? 'criar' : el('drive-op-acao').value;
    el('drive-op-campo').hidden = !['criar', 'renomear', 'mover'].includes(acao);
    el('drive-op-valor').value = acao === 'renomear' ? selecionado.nome : '';
    el('drive-op-valor').placeholder = acao === 'mover' ? 'Link ou ID da pasta destino (vazio = Meu Drive)' : 'Nome da pasta ou arquivo';
    el('drive-op-valor').required = ['criar', 'renomear'].includes(acao);
    el('drive-op-campo').firstChild.textContent = acao === 'mover' ? 'Pasta destino ' : 'Nome ';
    el('drive-op-exportacao').hidden = acao !== 'baixar' || !selecionado?.tipo?.startsWith('application/vnd.google-apps.');
    el('drive-op-formato').value = '';
    el('drive-op-ajuda').textContent = acao === 'lixeira' ? 'O item será movido para a lixeira. Pastas levam seus arquivos junto. Você poderá restaurar enquanto o Google mantiver o item na lixeira.' : acao === 'baixar' ? 'Escolha a pasta local na próxima janela. Arquivos existentes não serão sobrescritos.' : acao === 'criar' ? 'A nova pasta será criada na pasta aberta, ou em Meu Drive.' : acao === 'mover' ? 'Cole o link da pasta destino no Google Drive, ou o ID dela.' : '';
    el('drive-op-confirmar').textContent = {criar:'Criar pasta', renomear:'Salvar nome', mover:'Mover', lixeira:'Mover para lixeira', restaurar:'Restaurar', baixar:'Escolher pasta e baixar'}[acao];
  }
  function pastaDestino(valor) {
    const texto = valor.trim();
    if (!texto) return 'root';
    if (/^[\w-]+$/.test(texto)) return texto;
    const url = new URL(texto);
    if (url.protocol !== 'https:' || url.hostname !== 'drive.google.com') throw new Error('Use um link de pasta do Google Drive.');
    const id = url.pathname.match(/\/folders\/([\w-]+)/)?.[1];
    if (!id) throw new Error('O link precisa apontar para uma pasta do Drive.');
    return id;
  }
  async function alterar(nome, args, sucesso) {
    if (ocupado) return;
    ocupado = true; controles(); mensagem('Aguarde…');
    try {
      const r = await api()[nome](...args);
      if (r.cancelado) { mensagem('Operação cancelada.'); return; }
      if (nome !== 'drive_baixar') {
        const lista = await api().drive_buscar(buscaAtual, '', pastaAtual, naLixeira);
        listar(lista);
      }
      fecharOperacao(); mensagem(nome === 'drive_baixar' ? 'Arquivo salvo em: ' + r.caminho : sucesso);
    } catch (e) { mensagem(String(e.message || e), true); }
    finally { ocupado = false; controles(); }
  }
  el('drive-operacao').addEventListener('submit', e => {
    e.preventDefault();
    const acao = criando ? 'criar' : el('drive-op-acao').value, valor = el('drive-op-valor').value.trim();
    try {
      if (acao === 'criar') alterar('drive_criar_pasta', [valor, pastaAtual || 'root'], 'Pasta criada.');
      else if (acao === 'renomear') alterar('drive_renomear', [selecionado.id, valor], 'Nome atualizado.');
      else if (acao === 'mover') alterar('drive_mover', [selecionado.id, pastaDestino(valor)], 'Item movido para a pasta destino.');
      else if (acao === 'lixeira' || acao === 'restaurar') alterar('drive_lixeira', [selecionado.id, acao === 'restaurar'], acao === 'restaurar' ? 'Item restaurado.' : 'Item movido para a lixeira.');
      else if (acao === 'baixar') alterar('drive_baixar', [selecionado.id, null, el('drive-op-formato').value], 'Arquivo baixado.');
    } catch (e) { mensagem(String(e.message || e), true); }
  });
  el('drive-op-acao').addEventListener('change', camposOperacao);
  el('drive-op-cancelar').addEventListener('click', fecharOperacao);
  el('drive-criar').addEventListener('click', () => operacao());
  el('drive-enviar').addEventListener('click', () => alterar('drive_enviar', [null, pastaAtual || 'root'], 'Arquivo enviado.'));
  el('drive-visao').addEventListener('change', () => navegar(el('drive-visao').value === 'lixeira' ? '' : el('drive-visao').value, el('drive-visao').value === 'lixeira'));
  el('drive-voltar').addEventListener('click', () => {
    const anterior = trilha.slice(0, -1); navegar(anterior.at(-1)?.id || 'root', false, anterior);
  });
  el('drive-reutilizar').addEventListener('click', () => executar('drive_usar_calendar'));
  el('drive-importar').addEventListener('click', () => executar('drive_importar'));
  el('drive-conectar').addEventListener('click', () => executar('drive_conectar'));
  el('drive-sync').addEventListener('click', () => executar('drive_sincronizar'));
  el('drive-desconectar').addEventListener('click', () => executar('drive_desconectar'));
  el('drive-busca').addEventListener('submit', e => { e.preventDefault(); buscar(); });
  el('drive-mais').addEventListener('click', () => buscar(true));
  dialog.addEventListener('close', () => clearTimeout(timer));
  window.kaniDriveAtualizar = atualizar;
})();
