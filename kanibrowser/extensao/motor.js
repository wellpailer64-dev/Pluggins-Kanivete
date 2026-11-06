// A ponte privada chama este motor; sites não têm canal de mensagens nem acesso ao sistema.
let abaComandada = null;
globalThis.kbMotorVersao = '0.2.0';
chrome.action.onClicked.addListener(aba => { abaComandada = aba.id; });
globalThis.kbPronto = async url => {
  const abas = (await chrome.tabs.query({})).filter(a => a.url === url);
  return {versao: kbMotorVersao, pronta: abas.length === 1 && abas[0].id === abaComandada};
};

globalThis.kbExecutar = async (url, acao, dados = {}) => {
  const abas = (await chrome.tabs.query({})).filter(a => a.url === url);
  if (abas.length !== 1) throw new Error('A página precisa ter uma única aba com esse endereço.');
  if (!/^https?:\/\//.test(url)) throw new Error('A extensão atua somente em páginas HTTP/HTTPS.');
  const tabId = abas[0].id;
  if (tabId !== abaComandada) throw new Error('A aba comandada mudou; tente novamente após conferir a página.');
  if (acao === 'pronto') return kbPronto(url);
  const espera = acao === 'aguardar' ? dados : dados.aguardar;
  if (espera && !espera.seletor && !espera.url && !espera.texto) throw new Error('Informe seletor, url ou texto para aguardar.');
  if (acao === 'baixar') {
    const origem = new URL(dados.url);
    if (!['http:', 'https:'].includes(origem.protocol)) throw new Error('Download exige URL HTTP/HTTPS direta; blob e DRM não são suportados.');
    const id = await chrome.downloads.download({url: origem.href, saveAs: false});
    return {id, estado: 'iniciado'};
  }
  if (acao === 'download') {
    const [item] = await chrome.downloads.search({id: dados.id});
    if (!item) throw new Error('Download não encontrado.');
    return {id: item.id, estado: item.state, arquivo: item.filename, erro: item.error, recebido: item.bytesReceived};
  }
  if (!['ler', 'mapa', 'panorama', 'midias', 'digitar', 'copiar', 'api', 'selecionar', 'marcar', 'clicar', 'focar', 'aguardar'].includes(acao)) throw new Error('Ação desconhecida.');
  const executar = async (a, d) => {
  await chrome.scripting.executeScript({target: {tabId}, files: ['olhos.js']});
  const [r] = await chrome.scripting.executeScript({target: {tabId},
    func: async (a, d) => {
      try { return {ok: true, resultado: await globalThis.kbOlhos(a, d)}; }
      catch (e) { return {ok: false, erro: e.message}; }
    }, args: [a, d]});
  if (!r?.result?.ok) throw new Error(r?.result?.erro || 'A página não respondeu.');
  return r.result.resultado;
  };
  if (espera) await executar('condicao', espera);
  const resultado = acao === 'aguardar' ? {} : await executar(acao, dados);
  if (!espera) return resultado;
  const inicio = Date.now(), prazo = Math.min(15000, Math.max(100, Number(espera.prazo_ms) || 5000));
  let ultimoErro;
  do {
    try {
      const atual = await chrome.tabs.get(tabId);
      if (!/^https?:\/\//.test(atual.url)) throw new Error('Destino não é HTTP/HTTPS.');
      const condicao = await executar('condicao', espera);
      if (condicao.satisfeito) return {...resultado, confirmado: true, resultado: condicao, espera_ms: Date.now() - inicio};
    } catch (e) { ultimoErro = e.message; }
    await new Promise(r => setTimeout(r, 100));
  } while (Date.now() - inicio < prazo);
  return {...resultado, confirmado: false, motivo: 'Prazo esgotado; ação não foi repetida.', erro: ultimoErro};
};
