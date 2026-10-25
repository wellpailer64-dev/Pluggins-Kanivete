/* Mapa do disco: busca e navegação locais; nenhum arquivo é aberto automaticamente. */
(() => {
  const botao = document.createElement('button');
  botao.id = 'mapa-d-bt'; botao.className = 'bt'; botao.textContent = '▤ Mapa do disco D';
  document.getElementById('ferramentas-arquivos').appendChild(botao);
  const painel = document.createElement('section');
  painel.className = 'mapa-d-painel'; painel.hidden = true;
  painel.setAttribute('aria-label', 'Mapa do disco D');
  painel.innerHTML = '<header><strong>Mapa do disco D</strong><button type="button" aria-label="Fechar mapa">×</button></header>' +
    '<p class="mapa-d-estado" aria-live="polite"></p><form><input type="search" placeholder="Cliente, arquivo ou pasta…" aria-label="Buscar no disco D"><button>Buscar</button></form>' +
    '<nav><button type="button">↑ Subir</button><input readonly aria-label="Pasta consultada"></nav>' +
    '<div class="mapa-d-itens"></div><p class="mapa-d-nota">Busca por nomes e caminhos. O conteúdo dos arquivos não é lido pelo mapa.</p>';
  document.body.appendChild(painel);
  const busca = painel.querySelector('[type=search]'), caminho = painel.querySelector('nav input');
  const estado = painel.querySelector('.mapa-d-estado'), itens = painel.querySelector('.mapa-d-itens');
  let pasta = 'D:\\', versao = 0;
  const apiMapa = () => window.pywebview.api;
  function mostrarEstado(s) {
    const n = s.total || s.progresso || 0;
    estado.textContent = `${s.estado === 'construindo' ? 'Construindo o mapa' : s.estado === 'pronto' ? 'Mapa atualizado' : 'Cobertura parcial'} · ${n.toLocaleString('pt-BR')} itens` +
      (s.monitor_ativo && s.monitor === 'windows' ? ' · monitor ativo' : ' · atualização a conferir');
  }
  async function carregarMapa() {
    const minha = ++versao; itens.textContent = 'Consultando…'; caminho.value = pasta;
    try {
      const termo = busca.value.trim();
      const r = termo ? await apiMapa().mapa_d_buscar(termo) : await apiMapa().mapa_d_listar(pasta);
      if (minha !== versao) return;
      mostrarEstado(r.mapa || {}); itens.replaceChildren();
      const lista = r.arquivos || r.itens || [];
      if (!lista.length) itens.textContent = r.mapa?.parcial ? 'Nenhum resultado nesta parte do mapa. A indexação ainda não está completa.' : 'Nenhum resultado.';
      for (const item of lista) {
        const linha = document.createElement('div'); linha.className = 'mapa-d-item';
        const nome = document.createElement(item.pasta ? 'button' : 'strong');
        nome.textContent = (item.pasta ? '▸ ' : '') + item.nome;
        if (item.pasta) { nome.type = 'button'; nome.onclick = () => { pasta = item.caminho; busca.value = ''; carregarMapa(); }; }
        const local = document.createElement('input'); local.readOnly = true; local.value = item.caminho;
        local.setAttribute('aria-label', 'Caminho de ' + item.nome); local.onclick = () => local.select();
        linha.append(nome, local); itens.appendChild(linha);
      }
      if (r.parcial && lista.length) {
        const nota = document.createElement('p'); nota.textContent = 'Resultado parcial ou limitado. Refine a busca para encontrar mais itens.'; itens.appendChild(nota);
      }
    } catch (e) { if (minha === versao) itens.textContent = 'Não foi possível consultar o mapa: ' + (e.message || e); }
  }
  botao.onclick = () => { painel.hidden = !painel.hidden; if (!painel.hidden) carregarMapa(); };
  window.KCMapaD = { abrir: (local = 'D:/') => {
    pasta = local; busca.value = ''; painel.hidden = false; carregarMapa();
  } };
  painel.querySelector('header button').onclick = () => { painel.hidden = true; versao++; };
  painel.querySelector('form').onsubmit = e => { e.preventDefault(); carregarMapa(); };
  painel.querySelector('nav button').onclick = () => {
    const partes = pasta.split(/[\\/]+/).filter(Boolean);
    pasta = partes.length > 1 ? partes.slice(0, -1).join('\\') + '\\' : 'D:\\'; busca.value = ''; carregarMapa();
  };
  setInterval(async () => {
    if (!painel.hidden) try { mostrarEstado(await apiMapa().mapa_d_status()); } catch (e) {}
  }, 5000);
})();
