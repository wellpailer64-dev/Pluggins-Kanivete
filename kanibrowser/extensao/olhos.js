// Executa no mundo isolado da extensão. Nunca lê valores de senhas.
globalThis.kbOlhos = async (acao, dados = {}) => {
  const visivel = e => !!e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
  const areaNaTela = e => {
    const r = e.getBoundingClientRect();
    let esquerda = Math.max(0, r.left), topo = Math.max(0, r.top);
    let direita = Math.min(innerWidth, r.right), baixo = Math.min(innerHeight, r.bottom);
    for (let p = e.parentElement; p; p = p.parentElement) {
      const estilo = getComputedStyle(p), b = p.getBoundingClientRect();
      if (/(auto|scroll|hidden|clip)/.test(estilo.overflowX)) { esquerda = Math.max(esquerda, b.left); direita = Math.min(direita, b.right); }
      if (/(auto|scroll|hidden|clip)/.test(estilo.overflowY)) { topo = Math.max(topo, b.top); baixo = Math.min(baixo, b.bottom); }
    }
    return visivel(e) && direita > esquerda && baixo > topo ? {esquerda, topo, direita, baixo} : null;
  };
  const naTela = e => !!areaNaTela(e);
  const nome = e => {
    const rotulos = (e.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
    return (rotulos || e.getAttribute('aria-label') || e.labels?.[0]?.innerText || e.innerText || e.getAttribute('placeholder') || e.getAttribute('name') || e.title || '').trim().slice(0, 240);
  };
  const desabilitado = e => e.matches(':disabled') || !!e.closest('[inert],[aria-disabled="true"]');
  const seletor = e => {
    const unico = s => { const encontrados = document.querySelectorAll(s); return encontrados.length === 1 && encontrados[0] === e; };
    if (e.id && unico('#' + CSS.escape(e.id))) return '#' + CSS.escape(e.id);
    for (const atributo of ['data-testid', 'aria-label', 'name', 'placeholder', 'title']) {
      const valor = e.getAttribute(atributo);
      if (!valor) continue;
      const s = e.localName + '[' + atributo + '="' + CSS.escape(valor) + '"]';
      if (unico(s)) return s;
    }
    const partes = [];
    for (let n = e; n && n.nodeType === 1; n = n.parentElement) {
      const irmaos = n.parentElement ? [...n.parentElement.children].filter(i => i.tagName === n.tagName) : [];
      partes.unshift(n.localName + (irmaos.length > 1 ? ':nth-of-type(' + (irmaos.indexOf(n) + 1) + ')' : ''));
    }
    return partes.join(' > ');
  };
  const base = {titulo: document.title, url: location.href};
  const cobertura = e => {
    const area = areaNaTela(e);
    if (!area) return {estado: 'fora_tela', pontos_testados: 0, pontos_livres: 0};
    let livres = 0, bloqueador = null;
    for (const fx of [0.2, 0.5, 0.8]) for (const fy of [0.2, 0.5, 0.8]) {
      const x = area.esquerda + (area.direita - area.esquerda) * fx;
      const y = area.topo + (area.baixo - area.topo) * fy;
      const topo = document.elementFromPoint(x, y);
      if (topo && (topo === e || e.contains(topo))) livres++;
      else if (!bloqueador && topo) bloqueador = {seletor: seletor(topo), tipo: topo.localName};
    }
    return {estado: livres === 9 ? 'livre' : livres ? 'parcial' : 'bloqueado',
      pontos_testados: 9, pontos_livres: livres, bloqueador};
  };
  let regiao = document.body;
  if (dados.regiao && ['ler', 'mapa', 'midias', 'panorama'].includes(acao)) {
    const regioes = [...document.querySelectorAll(dados.regiao)];
    if (regioes.length !== 1 || !visivel(regioes[0])) throw new Error('Região deve encontrar exatamente um elemento visível.');
    regiao = regioes[0];
  }
  const limite = Math.min(60000, Math.max(1, Number(dados.limite) || 12000));
  const unico = () => {
    const els = [...document.querySelectorAll(dados.seletor)];
    if (els.length !== 1) throw new Error('O seletor deve encontrar exatamente um elemento.');
    const e = els[0];
    if (!visivel(e) || desabilitado(e) || e.readOnly) throw new Error('Elemento indisponível.');
    return e;
  };
  if (acao === 'condicao') {
    if (!dados.seletor && !dados.url && !dados.texto) throw new Error('Informe seletor, url ou texto para aguardar.');
    const e = dados.seletor ? document.querySelector(dados.seletor) : null;
    return {...base, satisfeito: (!dados.url || location.href.includes(dados.url)) &&
      (!dados.texto || (document.body?.innerText || '').includes(dados.texto)) &&
      (!dados.seletor || (dados.ausente ? !e || !visivel(e) : !!e && visivel(e)))};
  }
  if (['selecionar', 'marcar', 'clicar', 'focar'].includes(acao)) {
    const e = unico();
    if (acao === 'selecionar') {
      if (!e.matches('select')) throw new Error('Escolha um select.');
      const valores = Array.isArray(dados.valor) ? dados.valor.map(String) : [String(dados.valor)];
      if ((!e.multiple && valores.length !== 1) || valores.some(v => ![...e.options].some(o => o.value === v && !o.disabled && !o.closest('optgroup[disabled]')))) throw new Error('Opção indisponível.');
      [...e.options].forEach(o => { o.selected = valores.includes(o.value); });
      e.dispatchEvent(new Event('input', {bubbles: true}));
      e.dispatchEvent(new Event('change', {bubbles: true}));
      return {selecionado: [...e.selectedOptions].map(o => o.value)};
    }
    if (acao === 'marcar') {
      if (!e.matches('input[type=checkbox],input[type=radio]') || typeof dados.marcado !== 'boolean') throw new Error('Informe checkbox/radio e marcado booleano.');
      if (e.type === 'radio' && !dados.marcado) throw new Error('Para trocar radio, marque outra opção.');
      if (e.checked !== dados.marcado) e.click();
      return {marcado: e.checked, confirmado: e.checked === dados.marcado};
    }
    e.scrollIntoView({block: 'center'});
    e.focus();
    if (acao === 'clicar') e.click();
    return {executado: true, confirmado: false};
  }
  if (acao === 'panorama') {
    const leitura = await globalThis.kbOlhos('ler', dados);
    const mapa = await globalThis.kbOlhos('mapa', dados);
    const midias = await globalThis.kbOlhos('midias', {max_imagens: 10, max_videos: 5, carregadas: true, ...dados});
    const paineis = [...regiao.querySelectorAll('dialog[open],[role=dialog],[role=alertdialog],[role=menu],[role=listbox],[popover]:popover-open')].filter(visivel);
    if (regiao.matches('dialog[open],[role=dialog],[role=alertdialog],[role=menu],[role=listbox]') && visivel(regiao)) paineis.unshift(regiao);
    const ativo = document.activeElement;
    const foco = ativo && ativo !== document.body && regiao.contains(ativo) ? {seletor: seletor(ativo), tipo: ativo.getAttribute('type') || ativo.localName, nome: nome(ativo)} : null;
    return {...base, texto: leitura.texto, selecao: leitura.selecao, foco,
      paineis: paineis.slice(0, 20).map(e => ({tipo: e.getAttribute('role') || e.localName, nome: nome(e), seletor: seletor(e), modal: e.getAttribute('aria-modal') === 'true' || e.matches(':modal')})),
      total_paineis: paineis.length,
      mapa: {total: mapa.total, encontrados: mapa.encontrados, truncado: mapa.truncado, elementos: mapa.elementos},
      leitura: {principal: leitura.principal, truncado: leitura.truncado}, midias};
  }
  if (acao === 'api') {
    const url = new URL(dados.url, location.href);
    if (url.origin !== location.origin) throw new Error('API deve pertencer à mesma origem da página.');
    const metodo = String(dados.metodo || 'GET').toUpperCase();
    if (!['GET', 'HEAD'].includes(metodo)) throw new Error('A API de leitura aceita GET ou HEAD.');
    const controle = new AbortController();
    const tempo = setTimeout(() => controle.abort(), 15000);
    try {
      const r = await fetch(url.href, {method: metodo, credentials: 'same-origin', redirect: 'manual', signal: controle.signal});
      if (r.type === 'opaqueredirect') throw new Error('A API retornou redirecionamento; navegue até a URL final e consulte sua origem diretamente.');
      const leitor = r.body?.getReader();
      const decoder = new TextDecoder();
      let texto = '', truncado = false;
      if (leitor) {
        try {
          while (true) {
            const parte = await leitor.read();
            if (parte.done) { texto += decoder.decode(); break; }
            texto += decoder.decode(parte.value, {stream: true});
            if (texto.length > limite) { truncado = true; texto = texto.slice(0, limite); await leitor.cancel(); break; }
          }
        } finally { leitor.releaseLock(); }
      }
      let json;
      if (!truncado && (r.headers.get('content-type') || '').includes('json')) {
        try { json = JSON.parse(texto); } catch (_) { /* retorna o texto quando a resposta não é JSON válido */ }
      }
      return {url: r.url, status: r.status, ok: r.ok, tipo: r.headers.get('content-type'), texto, json, truncado};
    } finally { clearTimeout(tempo); }
  }
  if (acao === 'ler') {
    const raiz = dados.principal ? (regiao.matches('main,[role=main],article') ? regiao : regiao.querySelector('main,[role=main],article')) || regiao : regiao;
    let texto = raiz?.innerText || '';
    if (dados.principal && raiz) {
      const textos = [], walker = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const p = walker.currentNode.parentElement;
        if (p && visivel(p) && !p.closest('nav,header,footer,aside,[role=navigation],script,style')) {
          const t = walker.currentNode.textContent.trim();
          if (t) textos.push(t);
        }
      }
      texto = textos.join('\n');
    }
    const selecao = getSelection();
    return {...base, texto: texto.slice(0, limite), selecao: (!dados.regiao || regiao.contains(selecao.anchorNode) && regiao.contains(selecao.focusNode)) ? String(selecao).slice(0, limite) : '',
      principal: !!dados.principal && raiz !== document.body, truncado: texto.length > limite};
  }
  if (acao === 'mapa') {
    const controles = 'a[href],button,input,textarea,select,[contenteditable=true],[role=button],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio],[role=option]';
    const itens = [...regiao.querySelectorAll(controles)].filter(visivel);
    if (regiao.matches(controles) && visivel(regiao)) itens.unshift(regiao);
    const normalizar = s => String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const texto = normalizar(dados.texto || '');
    const tipos = {campos: 'input,textarea,select,[contenteditable=true]', botoes: 'button,[role=button],input[type=submit],input[type=button]', links: 'a[href]'};
    if (dados.tipo && !Object.hasOwn(tipos, dados.tipo)) throw new Error('Tipo deve ser campos, botoes ou links.');
    const filtrados = itens.filter(e => (!dados.tipo || e.matches(tipos[dados.tipo])) &&
      (!texto || normalizar(nome(e)).includes(texto)) && (!dados.seletor || e.matches(dados.seletor)) && (!dados.na_tela || naTela(e)));
    const maximo = Math.min(300, Math.max(1, Math.floor(Number(dados.maximo) || 300)));
    return {...base, total: itens.length, encontrados: filtrados.length, truncado: filtrados.length > maximo,
      elementos: filtrados.slice(0, maximo).map(e => ({
      seletor: seletor(e), tipo: e.getAttribute('type') || e.getAttribute('role') || e.localName, nome: nome(e), na_tela: naTela(e),
      cobertura: dados.cobertura ? cobertura(e) : undefined,
      expandido: e.hasAttribute('aria-expanded') ? e.getAttribute('aria-expanded') === 'true' : undefined,
      selecionado: e.hasAttribute('aria-selected') ? e.getAttribute('aria-selected') === 'true' : undefined,
      url: e.localName === 'a' ? e.href : undefined, desabilitado: desabilitado(e),
      marcado: e.matches('input[type=checkbox],input[type=radio]') ? e.checked : undefined,
      opcoes: e.matches('select') ? [...e.options].slice(0, 100).map(o => ({texto: o.text, valor: o.value, selecionada: o.selected, desabilitada: o.disabled})) : undefined
    }))};
  }
  if (acao === 'midias') {
    const buscar = s => [...(regiao.matches(s) ? [regiao] : []), ...regiao.querySelectorAll(s)];
    const imagens = buscar('img').filter(e => !dados.carregadas || e.complete && e.naturalWidth > 0).map(e => ({url: e.currentSrc || e.src, fonte: e.src, srcset: e.srcset, largura: e.naturalWidth, altura: e.naturalHeight, descricao: e.alt}));
    const videos = buscar('video,audio,video source,audio source').map(e => ({url: e.currentSrc || e.src, tipo: e.type || e.localName}));
    const mi = Math.min(300, Math.max(0, Math.floor(Number(dados.max_imagens ?? 300)) || 0));
    const mv = Math.min(100, Math.max(0, Math.floor(Number(dados.max_videos ?? 100)) || 0));
    return {...base, total_imagens: imagens.length, total_videos: videos.length,
      truncado: imagens.length > mi || videos.length > mv, imagens: imagens.slice(0, mi), videos: videos.slice(0, mv)};
  }
  if (acao === 'copiar') {
    const texto = dados.texto ?? String(getSelection());
    await navigator.clipboard.writeText(String(texto));
    return {copiado: true, caracteres: String(texto).length};
  }
  if (acao === 'digitar') {
    const els = [...document.querySelectorAll(dados.seletor)];
    if (els.length !== 1) throw new Error('O seletor deve encontrar exatamente um campo.');
    const e = els[0];
    if (!visivel(e) || desabilitado(e) || e.readOnly || e.getAttribute('aria-readonly') === 'true') throw new Error('Campo indisponível para digitação.');
    if (e.matches('input') && !['text', 'search', 'email', 'url', 'tel', 'number', 'date', 'time', 'datetime-local', 'month', 'week'].includes(e.type)) throw new Error('Tipo de campo não permitido; use marcar ou selecionar para opções.');
    if (!e.matches('input,textarea,[contenteditable=true]')) throw new Error('Escolha um campo de texto.');
    e.focus();
    const texto = String(dados.texto ?? '');
    if (e.isContentEditable) e.textContent = texto;
    else {
      const proto = e.localName === 'textarea' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(e, texto);
    }
    e.dispatchEvent(new Event('input', {bubbles: true}));
    e.dispatchEvent(new Event('change', {bubbles: true}));
    return {digitado: true, caracteres: texto.length, confirmado: (e.isContentEditable ? e.textContent : e.value) === texto};
  }
  throw new Error('Ação desconhecida.');
};
