/* Renderização comum a Claude, Codex e Kani. Conteúdo recebido nunca vira HTML executável. */
window.KCResposta = (() => {
  const esc = t => String(t).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const absoluto = t => /^(?:[a-z]:[\\/]|\\\\[^\\/]+[\\/]|file:\/\/)/i.test(t);
  const web = t => { try { const u = new URL(t); return /^https?:$/.test(u.protocol) && !u.username && !u.password; } catch (_) { return false; } };
  const local = t => absoluto(t) || (!!t && !/^(?:[\w+.-]+:|\/\/|#)/.test(t));
  const formato = t => esc(t).replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>');
  const abrir = (alvo, rotulo) => `<span class="caminho-resposta"><code>${esc(rotulo)}</code><button type="button" class="abrir-caminho" data-abrir-caminho="${esc(alvo)}" title="Abrir caminho no Explorer" aria-label="Abrir caminho: ${esc(alvo)}">↗<span> Abrir</span></button></span>`;
  const link = (alvo, rotulo) => `<a href="${esc(alvo)}" data-link-externo target="_blank" rel="noopener noreferrer" title="Abrir no navegador externo">${esc(rotulo)}<small aria-hidden="true"> ↗</small></a>`;
  function imagem(alvo, rotulo) {
    const remoto = web(alvo), data = /^data:image\/(?:png|jpeg|webp|gif|bmp);base64,[a-z0-9+/=]+$/i.test(alvo);
    if (!remoto && !data && !local(alvo)) return esc(rotulo);
    return `<span class="resposta-imagem"><button type="button" class="imagem-abrir" data-imagem="${esc(alvo)}" title="Ampliar imagem" aria-label="Ampliar imagem: ${esc(rotulo || 'Imagem')}"><img ${remoto || data ? `src="${esc(alvo)}"` : `data-imagem-local="${esc(alvo)}"`} alt="${esc(rotulo || 'Imagem')}" loading="lazy" referrerpolicy="no-referrer"></button>${rotulo ? `<span class="imagem-legenda">${esc(rotulo)}</span>` : ''}</span>`;
  }
  function texto(t) {
    // Caminhos com espaços devem preferir crases ou links Markdown para delimitar o fim exato.
    const re = /https?:\/\/[^\s<>"`]+|www\.[^\s<>"`]+|(?:[a-z]:[\\/]|\\\\[^\\/\s]+[\\/])[^<>"'\r\n`|,;!?]+/gi;
    let html = '', inicio = 0;
    for (const m of t.matchAll(re)) {
      let alvo = m[0].replace(/[.,;!]+$/, '').trimEnd();
      if (/^(https?:|www\.)/i.test(alvo)) {
        while (alvo.endsWith(')') && (alvo.match(/\)/g) || []).length > (alvo.match(/\(/g) || []).length) alvo = alvo.slice(0, -1);
      }
      html += formato(t.slice(inicio, m.index));
      const url = alvo.startsWith('www.') ? 'https://' + alvo : alvo;
      html += web(url) ? link(url, alvo) : absoluto(alvo) ? abrir(alvo, alvo) : esc(alvo);
      html += formato(m[0].slice(alvo.length));
      inicio = m.index + m[0].length;
    }
    return html + formato(t.slice(inicio));
  }
  function lerLink(t, i) {
    const foto = t[i] === '!', inicio = i + (foto ? 2 : 1);
    if (foto && t[i + 1] !== '[' || !foto && t[i] !== '[') return null;
    const meio = t.indexOf('](', inicio);
    if (meio < 0) return null;
    let fim = meio + 2, nivel = 1, angulo = t[fim] === '<';
    for (; fim < t.length; fim++) {
      if (t[fim] === '\\' && /[()]/.test(t[fim + 1] || '')) { fim++; continue; }
      if (!angulo && t[fim] === '(') nivel++;
      if (t[fim] === '>' && angulo) angulo = false;
      if (!angulo && t[fim] === ')' && --nivel === 0) break;
    }
    if (fim >= t.length) return null;
    let alvo = t.slice(meio + 2, fim).trim();
    if (alvo.startsWith('<') && alvo.endsWith('>')) alvo = alvo.slice(1, -1);
    else alvo = alvo.replace(/\s+["'][^"']*["']$/, '');
    return {fim: fim + 1, foto, alvo, rotulo: t.slice(inicio, meio)};
  }
  function linha(t) {
    let html = '', inicio = 0, i = 0;
    while (i < t.length) {
      if (t[i] === '`') {
        const m = t.slice(i).match(/^(`+)/), marca = m[0], fim = t.indexOf(marca, i + marca.length);
        if (fim >= 0) {
          const codigo = t.slice(i + marca.length, fim);
          html += texto(t.slice(inicio, i));
          html += absoluto(codigo) ? abrir(codigo, codigo) : `<span class="codigo-inline"><code>${esc(codigo)}</code><button type="button" data-copiar-inline title="Copiar código" aria-label="Copiar código">⧉</button></span>`;
          i = fim + marca.length; inicio = i; continue;
        }
      }
      if (t[i] === '[' || t[i] === '!') {
        const l = lerLink(t, i);
        if (l) {
          html += texto(t.slice(inicio, i));
          const foto = l.foto || /\.(?:png|jpe?g|webp|gif|bmp)(?:[?#].*)?$/i.test(l.alvo);
          html += foto ? imagem(l.alvo, l.rotulo) : web(l.alvo) ? link(l.alvo, l.rotulo)
            : local(l.alvo) ? abrir(l.alvo, l.rotulo) : esc(l.rotulo);
          i = l.fim; inicio = i; continue;
        }
      }
      i++;
    }
    return html + texto(t.slice(inicio));
  }
  function md(src) {
    const out = [], L = String(src || '').replace(/\r\n?/g, '\n').split('\n');
    let i = 0;
    const comeco = l => /^\s{0,3}(?:`{3,}|~{3,})/.test(l);
    const bloco = (codigo, idioma = 'código') => `<section class="codigo"><div class="codigo-topo"><span>${esc(idioma)}</span><button type="button" data-copiar-codigo aria-label="Copiar código">⧉ Copiar</button></div><pre><code>${esc(codigo)}</code></pre></section>`;
    while (i < L.length) {
      const l = L[i], cerca = l.match(/^\s{0,3}(`{3,}|~{3,})(.*)$/);
      if (cerca) {
        const cod = [], fechar = new RegExp('^\\s{0,3}' + cerca[1][0] + '{' + cerca[1].length + ',}\\s*$');
        const idioma = cerca[2].trim().split(/\s/)[0] || 'código'; i++;
        while (i < L.length && !fechar.test(L[i])) cod.push(L[i++]);
        i++;
        out.push(bloco(cod.join('\n'), idioma));
        continue;
      }
      if (/^(?: {4}|\t)/.test(l)) {
        const cod = [];
        while (i < L.length && (/^(?: {4}|\t)/.test(L[i]) || !L[i].trim())) cod.push(L[i++].replace(/^(?: {4}|\t)/, ''));
        while (cod.length && !cod.at(-1)) cod.pop();
        out.push(bloco(cod.join('\n'))); continue;
      }
      if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < L.length && /^\s*\|[\s:|-]+\|\s*$/.test(L[i + 1])) {
        const cel = r => r.trim().replace(/^\||\|$/g, '').split('|').map(c => linha(c.trim()));
        let h = '<table><tr>' + cel(l).map(c => '<th>' + c + '</th>').join('') + '</tr>'; i += 2;
        while (i < L.length && /^\s*\|.*\|\s*$/.test(L[i])) h += '<tr>' + cel(L[i++]).map(c => '<td>' + c + '</td>').join('') + '</tr>';
        out.push(h + '</table>'); continue;
      }
      const tit = l.match(/^(#{1,3})\s+(.*)/);
      if (tit) { out.push(`<h${tit[1].length}>${linha(tit[2])}</h${tit[1].length}>`); i++; continue; }
      if (/^\s*([-*]|\d+[.)])\s+/.test(l)) {
        const num = /^\s*\d/.test(l), it = [];
        while (i < L.length && /^\s*([-*]|\d+[.)])\s+/.test(L[i])) it.push('<li>' + linha(L[i++].replace(/^\s*([-*]|\d+[.)])\s+/, '')) + '</li>');
        out.push((num ? '<ol>' : '<ul>') + it.join('') + (num ? '</ol>' : '</ul>')); continue;
      }
      if (!l.trim()) { i++; continue; }
      const p = [];
      while (i < L.length && L[i].trim() && !comeco(L[i]) && !/^(#{1,3}\s|\s*([-*]|\d+[.)])\s+)/.test(L[i])) p.push(linha(L[i++]));
      out.push('<p>' + p.join('<br>') + '</p>');
    }
    return out.join('');
  }
  return {md, linha, web, esc};
})();
