/* Aba Saúde do PC no painel da direita (2026-10-24): nota geral, alertas em linguagem simples e um cartão por peça
   (CPU, placa de vídeo, discos com SMART, RAM, placa-mãe, sistema) — saude_pc.py. Botão Manutenção abre o
   manutencao.py elevado (UAC) e a aba acompanha estado.json: a KaniBall sai da faixa do chat e trabalha numa cena
   (vassoura no lixo, lupa nos vírus, chave nos drivers/discos). No fim, o relatório pede as decisões: ameaças
   (remover/restaurar/ignorar) e duplicados (vão para a Lixeira). */
(() => {
  const el = id => document.getElementById(id), api = () => window.pywebview.api;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const tam = n => { n = +n || 0; const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return (i < 2 ? n.toFixed(0) : n.toFixed(1)).replace('.', ',') + ' ' + u[i]; };
  const LARG = 400;
  const ETAPAS = [['preparar', 'Ponto de restauração'], ['sensores', 'Sensores dos discos'], ['limpeza', 'Lixo do Windows'],
    ['navegadores', 'Cache dos navegadores e apps'], ['kanivete', 'Resíduos do Kanivete/KaniCode'], ['duplicados', 'Arquivos duplicados'],
    ['virus', 'Vírus e ameaças'], ['drivers', 'Drivers'], ['reparo', 'Reparar o Windows (DISM + SFC)'], ['discos', 'Desfragmentar / otimizar']];
  const IC = {
    cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    gpu: '<rect x="2" y="7" width="20" height="10" rx="2"/><circle cx="9" cy="12" r="2.6"/><circle cx="16" cy="12" r="2.6"/><path d="M4 17v3"/>',
    disco: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="12" cy="11" r="4"/><path d="M12 11l5 6"/>',
    ram: '<rect x="2" y="7" width="20" height="9" rx="1"/><path d="M6 16v3M10 16v3M14 16v3M18 16v3M6 10h2M11 10h2M16 10h2"/>',
    placa: '<rect x="3" y="3" width="18" height="18" rx="2"/><rect x="7" y="7" width="6" height="6"/><path d="M16 7h2M16 11h2M7 17h11"/>',
    so: '<path d="M3 5l8-1v7H3zM13 4l8-1v8h-8zM3 13h8v7l-8-1zM13 13h8v8l-8-1z"/>',
  };
  const svg = p => `<svg viewBox="0 0 24 24" aria-hidden="true">${p}</svg>`;

  // ── trilho + painel (mesmo encaixe da aba Casa) ──
  const trilho = document.createElement('button'); trilho.id = 'saude-trilho'; trilho.className = 'trilho';
  trilho.title = 'Saúde do PC: hardware e manutenção'; trilho.setAttribute('aria-label', 'Saúde do PC');
  trilho.setAttribute('aria-expanded', 'false'); trilho.setAttribute('aria-controls', 'saude-painel');
  trilho.innerHTML = '<span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h4l2-5 4 10 2-5h6"/></svg></span><span class="cont" id="saude-cont" hidden></span><span class="vert">SAÚDE DO PC</span>';
  (el('casa-trilho') || el('consumo-trilho') || el('atv-trilho')).after(trilho);
  const painel = document.createElement('section'); painel.id = 'saude-painel'; painel.className = 'det';
  painel.setAttribute('aria-label', 'Saúde do PC');
  painel.innerHTML = `<div class="cab"><b>Saúde do PC</b><span class="esp"></span><button class="bt" id="sd-atualizar" title="Ler de novo">↻</button><button class="bt" id="sd-fechar" aria-label="Recolher">»</button></div>
    <div class="sd-rolo" id="sd-rolo"><div id="sd-man"></div><div id="sd-corpo"><p class="sd-nota">Lendo o hardware…</p></div></div>`;
  el('atv').append(painel); painel.inert = true;
  let dados = null, est = null, timerH = 0, timerM = 0, decidido = {}, dupMarc = {}, opcoesAbertas = false, ultimoHTML = '', offline = false, rodAntes = false;
  let opcoes = { etapas: ETAPAS.map(e => e[0]), completa: false, seco: false };
  try { Object.assign(opcoes, JSON.parse(localStorage.getItem('kanicode-saude-opcoes') || '{}')); } catch (_) {}

  // ── hardware ──
  const cor = n => n >= 80 ? 'var(--lima)' : n >= 55 ? 'var(--aviso)' : 'var(--erro)';
  const barra = (pct, c) => `<div class="sd-barra"><i style="width:${Math.max(1, Math.min(100, pct || 0)).toFixed(1)}%;background:${c || 'var(--lima)'}"></i></div>`;
  const anel = (n, r = 34) => {
    const C = 2 * Math.PI * r, c = cor(n);
    return `<svg class="sd-anel" viewBox="0 0 ${2 * r + 12} ${2 * r + 12}"><circle cx="${r + 6}" cy="${r + 6}" r="${r}" class="fundo"/>
      <circle cx="${r + 6}" cy="${r + 6}" r="${r}" style="stroke:${c};stroke-dasharray:${C};stroke-dashoffset:${C * (1 - n / 100)}"/></svg>`;
  };
  const temp = t => t == null ? '' : `<span class="sd-temp ${t >= 80 ? 'q' : t >= 65 ? 'm' : ''}">${t} °C</span>`;
  const quando = s => { if (!s || typeof s !== 'string') return 'nunca'; const d = (Date.now() - new Date(s)) / 864e5; return d < 1 ? 'hoje' : d < 2 ? 'ontem' : `há ${Math.floor(d)} dias`; };

  function cartao(p) {
    let corpo = '';
    if (p.tipo === 'cpu') corpo = `<div class="sd-l"><span>Uso</span><b>${Math.round(p.uso)}%</b></div>${barra(p.uso)}
        <div class="sd-l"><span>Frequência</span><b>${p.mhz || '—'} MHz</b></div>
        <div class="sd-l"><span>Temperatura</span><b>${p.temp != null ? temp(p.temp) : '<small title="O Windows só entrega a temperatura dos núcleos com um driver de sensores (LibreHardwareMonitor).">sem sensor de núcleo</small>'}</b></div>`;
    else if (p.tipo === 'gpu') corpo = (p.uso != null ? `<div class="sd-l"><span>Uso</span><b>${p.uso}%</b></div>${barra(p.uso)}` : '') +
        (p.vram && p.vram[1] ? `<div class="sd-l"><span>Memória de vídeo</span><b>${tam(p.vram[0])} / ${tam(p.vram[1])}</b></div>${barra(p.vram[0] / p.vram[1] * 100, '#7FD3FF')}` : '') +
        (p.temp != null ? `<div class="sd-l"><span>Temperatura</span><b>${temp(p.temp)}</b></div>` : '');
    else if (p.tipo === 'ram') corpo = `<div class="sd-l"><span>Em uso</span><b>${tam(p.usada)} de ${tam(p.total)}</b></div>${barra(p.pct, p.pct > 85 ? 'var(--aviso)' : 'var(--lima)')}
        <div class="sd-pentes">${(p.pentes || []).map(m => `<span title="${esc(m.modelo)}">${m.gb} GB · ${esc((m.slot || '').replace('Channel', 'Canal ').replace('-DIMM', ' · slot '))}</span>`).join('')}</div>`;
    else if (p.tipo === 'disco') corpo = `<div class="sd-chips"><span class="${p.saude === 'Healthy' ? 'ok' : 'ruim'}">${p.saude === 'Healthy' ? 'saudável' : esc(p.saude)}</span>
        ${p.crystal ? `<span title="CrystalDiskInfo">${esc(p.crystal)}</span>` : ''}${p.temp != null ? `<span>${p.temp} °C</span>` : ''}
        ${p.desgaste != null ? `<span title="desgaste do SSD">${p.desgaste}% gasto</span>` : ''}${p.horas ? `<span>${Math.round(p.horas / 24)} dias ligado</span>` : ''}</div>` +
        (p.volumes || []).map(v => `<div class="sd-l"><span><b class="sd-letra">${v.l}:</b> ${esc(v.nome)}</span><b>${tam(v.livre)} livres</b></div>${barra(100 - v.pct, v.pct < 5 ? 'var(--erro)' : v.pct < 10 ? 'var(--aviso)' : 'var(--lima)')}`).join('');
    else if (p.tipo === 'placa' && p.temp != null) corpo = `<div class="sd-l"><span>Zona térmica (ACPI)</span><b>${temp(p.temp)}</b></div>`;
    return `<article class="sd-card ${p.estado === 'bom' ? '' : p.estado === 'ruim' ? 'ruim' : 'atn'}">
      <header><span class="sd-ic">${svg(IC[p.tipo] || IC.so)}</span><div><b>${esc(p.nome)}</b><small>${esc(p.sub)}</small></div>
      <span class="sd-pt" style="color:${cor(p.nota)}">${p.nota}</span></header>${corpo}</article>`;
  }

  function desenharHW() {
    const c = el('sd-corpo');
    if (!dados) return;
    if (!dados.ok) { c.innerHTML = `<p class="sd-nota erro">${esc(dados.erro)}</p>`; return; }
    const s = dados.sistema || {}, df = s.defender || {}, m = dados.manutencao;
    const rodando = est && ['rodando', 'decidir'].includes(est.situacao);
    c.innerHTML = `<div class="sd-hero">${anel(dados.geral)}<div class="sd-hero-n"><b style="color:${cor(dados.geral)}">${dados.geral}</b><small>de 100</small></div>
        <div class="sd-hero-t"><b>${dados.estado === 'bom' ? 'PC em boa forma' : dados.estado === 'ruim' ? 'O PC precisa de cuidado' : 'Alguns pontos de atenção'}</b>
        <small>${m && m.fim ? `última manutenção ${quando(new Date(m.fim * 1000).toISOString())}${m.seco ? ' (simulação)' : ` · ${tam(m.liberado)} liberados`}` : 'nenhuma manutenção ainda'}</small>
        ${rodando ? '' : `<button class="sd-man-bt" id="sd-iniciar">${svg('<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>')}Manutenção</button>
        <button class="sd-link" id="sd-op">${opcoesAbertas ? 'fechar opções' : 'opções'}</button>`}</div></div>
      ${opcoesAbertas && !rodando ? opcoesHTML() : ''}
      ${dados.alertas.length ? `<div class="sd-alertas">${dados.alertas.map(a => `<p>${esc(a)}</p>`).join('')}</div>` : ''}
      <div class="sd-grade">${dados.pecas.map(cartao).join('')}
      <article class="sd-card"><header><span class="sd-ic">${svg(IC.so)}</span><div><b>${esc((s.so || {}).nome || 'Windows')}</b><small>build ${esc((s.so || {}).build)} · ${s.processos} processos</small></div></header>
        <div class="sd-l"><span>Ligado há</span><b>${s.dias_boot < 1 ? Math.round(s.dias_boot * 24) + ' h' : s.dias_boot + ' dias'}</b></div>
        <div class="sd-l"><span>Defender</span><b class="${df.ligado ? 'ok' : 'ruim'}">${df.ligado ? 'protegendo' : 'desligado'}</b></div>
        <div class="sd-l"><span>Definições de vírus</span><b>${quando(df.assinatura)}</b></div>
        <div class="sd-l"><span>Última verificação</span><b>${quando(df.rapida)}${typeof df.completa === 'string' ? ' · completa ' + quando(df.completa) : ''}</b></div>
        <div class="sd-l"><span>Sensores SMART</span><b>${s.sensores_quando ? quando(new Date(s.sensores_quando * 1000).toISOString()) : 'na 1ª manutenção'}</b></div></article></div>`;
    const cont = el('saude-cont');
    const n = dados.alertas.length;
    cont.hidden = !n && !rodando; cont.textContent = rodando ? '…' : n;
  }

  function opcoesHTML() {
    return `<div class="sd-opcoes">${ETAPAS.map(([id, nome]) => `<label><input type="checkbox" data-et="${id}" ${opcoes.etapas.includes(id) ? 'checked' : ''}> ${nome}</label>`).join('')}
      <hr><label><input type="checkbox" data-op="completa" ${opcoes.completa ? 'checked' : ''}> Verificação de vírus completa (pode levar horas)</label>
      <label><input type="checkbox" data-op="seco" ${opcoes.seco ? 'checked' : ''}> Só simular (mede o que sairia, não apaga nada)</label>
      <p class="sd-nota">Nunca apaga: logins, cookies, senhas, favoritos e sessões dos navegadores; seus arquivos (duplicados só vão para a Lixeira se você marcar).</p></div>`;
  }

  async function lerHW() {
    try { dados = await api().saude_ler(); } catch (e) { dados = { ok: false, erro: e.message || String(e) }; }
    desenharHW();
  }

  // ── manutenção ──
  async function lerEstado() {
    try { est = await api().saude_estado(); } catch (_) { return; }
    desenharMan();
    const rod = ['rodando', 'decidir'].includes(est.situacao);
    if (rod !== rodAntes) { rodAntes = rod; if (rod) opcoesAbertas = false; desenharHW(); }
    if (rod) kaniVem(); else kaniVolta();
    if (!rod && timerM && est.situacao !== 'nada') { clearInterval(timerM); timerM = 0; lerHW(); }
  }

  function desenharMan() {
    const c = el('sd-man');
    if (!est || est.situacao === 'nada') { c.innerHTML = ''; return; }
    const ets = (est.etapas || []).filter(e => e.estado !== 'pulada');
    const tot = ets.length ? ets.reduce((s, e) => s + (e.estado === 'ok' || e.estado === 'erro' ? 100 : e.estado === 'rodando' ? e.progresso : 0), 0) / ets.length : 0;
    const rod = est.situacao === 'rodando';
    const atual = ets.find(e => e.estado === 'rodando');
    let h = `<section class="sd-mbox ${rod ? 'on' : ''}">
      <div class="sd-cena" id="sd-cena-casa">${rod ? '' : ''}</div>
      <div class="sd-mtopo"><b>${rod ? (atual ? esc(atual.nome) : 'Começando…') : est.situacao === 'decidir' ? 'Falta você decidir' : est.situacao === 'interrompida' ? 'Manutenção interrompida' : 'Manutenção concluída'}${est.seco ? ' <small>(simulação)</small>' : ''}</b>
        <span class="sd-lib">${tam(est.liberado)} ${est.seco ? 'sairiam' : 'liberados'}</span></div>
      ${barra(tot)}<p class="sd-det">${esc(atual ? atual.detalhe : '')}</p>
      <ol class="sd-etapas">${ets.map(e => `<li class="${e.estado}"><i></i><span>${esc(e.nome)}</span><small>${e.estado === 'rodando' ? e.progresso + '%' : esc(e.detalhe)}</small></li>`).join('')}</ol>
      ${rod ? '<button class="sd-link" id="sd-parar">parar depois da etapa atual</button>' : ''}`;
    if (!rod) h += relatorio();
    h += '</section>';
    if (h === ultimoHTML && (!rod || el('sd-cena-casa')?.firstChild)) return;   // a cada 1 s: só redesenha se mudou (não perde cliques)
    ultimoHTML = h; c.innerHTML = h;
    if (el('sd-offline')) { el('sd-offline').checked = offline; el('sd-offline').onchange = e => { offline = e.target.checked; }; }
    if (rod) montarCena();
  }

  function relatorio() {
    let h = '';
    const a = est.discos_antes || {}, d = est.discos_depois || {};
    const ls = Object.keys(d).filter(l => a[l]);
    if (ls.length) h += `<h4>Espaço nos discos</h4><div class="sd-disc">${ls.map(l => { const g = d[l].livre - a[l].livre; return `<span><b>${l}:</b> ${tam(d[l].livre)} livres <em class="${g > 0 ? 'ok' : ''}">${g > 0 ? '+' + tam(g) : '='}</em></span>`; }).join('')}</div>`;
    if (est.reiniciar) h += '<p class="sd-aviso">Reinicie o PC para terminar a instalação dos drivers/reparos.</p>';
    (est.avisos || []).forEach(x => { h += `<p class="sd-aviso">${esc(x)}</p>`; });
    // ameaças
    const am = est.ameacas || [];
    if (am.length) {
      h += `<h4>Ameaças isoladas pelo Defender <small>${am.length}</small></h4>` + am.map(t => {
        const v = decidido[t.id] || t.decisao || (t.recomendo === 'remover' ? 'remover' : 'ignorar');
        decidido[t.id] = v;
        return `<div class="sd-amea g${esc(t.nivel)}"><b>${esc(t.nome || 'Ameaça ' + t.id)}</b><small>gravidade ${esc(t.nivel)}${t.nova ? ' · achada agora' : ''} · ${esc((t.recursos || '').slice(0, 140))}</small>
          ${t.decisao ? `<em>${esc(t.decisao)}</em>` : `<div class="sd-esc" data-id="${esc(t.id)}">${[['remover', 'Eliminar'], ['restaurar', 'É seguro: restaurar'], ['ignorar', 'Deixar isolada']].map(([k, n]) =>
            `<button data-v="${k}" class="${v === k ? 'sel' : ''}">${n}${k === t.recomendo || (t.recomendo === 'avaliar' && k === 'ignorar') ? ' ★' : ''}</button>`).join('')}</div>`}</div>`;
      }).join('') + (est.situacao === 'decidir' ? `<div class="sd-bts"><label><input type="checkbox" id="sd-offline"> verificação offline (reinicia o PC)</label><button class="sim" id="sd-aplicar">Aplicar</button></div>` : '');
    } else if ((est.etapas || []).some(e => e.id === 'virus' && e.estado === 'ok')) h += '<h4>Vírus e ameaças</h4><p class="sd-nota ok">Nada encontrado. ✓</p>';
    // drivers
    const dr = est.drivers || [];
    if ((est.etapas || []).some(e => e.id === 'drivers' && e.estado === 'ok'))
      h += `<h4>Drivers <small>${dr.length}</small></h4>` + (dr.length ? dr.map(x => `<p class="sd-drv ${x.ok ? 'ok' : x.ok === false ? 'ruim' : ''}">${x.ok ? '✓' : x.ok === false ? '✗' : '•'} ${esc(x.nome)} <small>${esc(x.data || '')}</small></p>`).join('') : '<p class="sd-nota ok">Todos em dia pelo Windows Update. ✓</p>');
    // duplicados
    const dp = est.duplicados || [];
    if (dp.length) {
      const tot = dp.reduce((s, g, i) => s + (dupMarc[i] !== false ? g.tamanho * g.copias.length : 0), 0);
      h += `<h4>Arquivos duplicados <small>${dp.length} grupos</small></h4><p class="sd-nota">Fica o original (◆); as cópias marcadas vão para a Lixeira.</p><div class="sd-dups">` +
        dp.slice(0, 80).map((g, i) => `<label class="sd-dup"><input type="checkbox" data-dup="${i}" ${dupMarc[i] !== false ? 'checked' : ''}>
          <span><b>${esc(g.manter.split('\\').pop())}</b> <small>${tam(g.tamanho)} × ${g.copias.length}</small><small class="cam">◆ ${esc(g.manter)}</small>${g.copias.map(c => `<small class="cam">✕ ${esc(c)}</small>`).join('')}</span></label>`).join('') +
        `</div><div class="sd-bts"><span>${tam(tot)}</span><button class="sim" id="sd-dup-ir">Mandar cópias para a Lixeira</button></div><p class="sd-nota" id="sd-dup-msg"></p>`;
    }
    return h;
  }

  // ── a cena: KaniBall trabalhando ──
  let cena = null, rosto = {};
  ['trabalhando', 'feliz'].forEach(e => window.addEventListener('pywebviewready', () => api().rosto_quadros(e).then(r => { rosto[e] = r; }).catch(() => {})));
  function montarCena() {
    const casa = el('sd-cena-casa');
    if (!casa) return;
    if (!cena) {
      const cv = document.createElement('canvas'); cv.width = 360; cv.height = 120;
      cena = { cv, g: cv.getContext('2d'), t0: performance.now(), raf: 0, poeira: [] };
      const passo = () => { cena.raf = requestAnimationFrame(passo); if (!document.hidden && cena.cv.isConnected) desenharCena((performance.now() - cena.t0) / 1000); };
      passo();
    }
    casa.append(cena.cv);
  }
  function desenharCena(t) {
    const { g, cv } = cena, k = window.devicePixelRatio || 1, W = cv.clientWidth || 360, H = 120;
    if (cv.width !== Math.round(W * k)) { cv.width = Math.round(W * k); cv.height = Math.round(H * k); }
    g.setTransform(k, 0, 0, k, 0, 0); g.clearRect(0, 0, W, H);
    const id = (est && est.agora) || 'limpeza', cx = W / 2;
    // chão
    g.fillStyle = '#1A201D'; g.fillRect(0, H - 14, W, 14);
    // o PC (gabinete) com LED pulsando
    const px = cx + 34, py = H - 14 - 78;
    g.fillStyle = '#222A26'; g.strokeStyle = '#3A4740'; g.lineWidth = 1.5; rr(g, px, py, 50, 78, 6); g.fill(); g.stroke();
    g.fillStyle = '#0E1110'; rr(g, px + 8, py + 10, 34, 34, 4); g.fill();
    for (let i = 0; i < 3; i++) { g.fillStyle = `rgba(182,242,58,${.25 + .6 * Math.max(0, Math.sin(t * 6 + i * 1.7))})`; g.fillRect(px + 12 + i * 10, py + 54, 6, 3); }
    g.strokeStyle = 'rgba(182,242,58,.5)'; g.beginPath(); g.arc(px + 25, py + 27, 10, t * 4, t * 4 + 4); g.stroke();   // ventoinha
    // KaniBall: pula de leve e trabalha no PC
    const bx = cx - 26, by = H - 14 - 30 - Math.abs(Math.sin(t * 4)) * 8, R = 26;
    const gr = g.createRadialGradient(bx - R * .36, by - R * .44, 0, bx - R * .36, by - R * .44, R * 1.56);
    gr.addColorStop(0, '#D8FF7A'); gr.addColorStop(.35, '#C4F64E'); gr.addColorStop(1, '#7FB51A');
    g.fillStyle = 'rgba(0,0,0,.35)'; g.beginPath(); g.ellipse(bx, H - 13, R * .8, 3, 0, 0, 7); g.fill();
    g.fillStyle = gr; g.beginPath(); g.arc(bx, by, R, 0, 7); g.fill();
    const q = rosto.trabalhando;
    if (q && q.quadros && q.quadros.length) {
      const L = q.quadros[Math.floor(t * q.fps) % q.quadros.length], cel = 2.6, x0 = bx - 8 * cel, y0 = by - 8 * cel + cel * .5;
      const CO = { '#': '#0E1110', w: '#FFFFFF', p: '#FF8FA3', r: '#FF5A5F' };
      L.forEach((l, y) => { for (let x = 0; x < 16; x++) { const c = CO[l[x]]; if (c) { g.fillStyle = c; g.fillRect(x0 + x * cel, y0 + y * cel, cel, cel); } } });
    }
    // a ferramenta da etapa, na mão (lado direito da bola)
    g.save(); g.translate(bx + R * .9, by + 4);
    const bate = Math.sin(t * 9);
    g.lineCap = 'round'; g.lineJoin = 'round';
    if (['limpeza', 'navegadores', 'kanivete'].includes(id)) {   // vassoura varrendo + poeira
      g.rotate(.5 + bate * .35);
      g.strokeStyle = '#C89B5B'; g.lineWidth = 3; g.beginPath(); g.moveTo(0, -18); g.lineTo(0, 22); g.stroke();
      g.fillStyle = '#F0C04A'; g.beginPath(); g.moveTo(-7, 22); g.lineTo(7, 22); g.lineTo(10, 34); g.lineTo(-10, 34); g.fill();
      if (Math.random() < .5) cena.poeira.push({ x: bx + R + 18, y: H - 18, vx: 30 + Math.random() * 50, vy: -20 - Math.random() * 30, v: 1 });
    } else if (id === 'virus' || id === 'duplicados') {   // lupa procurando
      g.rotate(-.3 + Math.sin(t * 2.5) * .4);
      g.strokeStyle = '#E6EDE8'; g.lineWidth = 3; g.beginPath(); g.arc(14, -10, 9, 0, 7); g.stroke();
      g.fillStyle = 'rgba(127,211,255,.25)'; g.beginPath(); g.arc(14, -10, 8, 0, 7); g.fill();
      g.strokeStyle = '#C89B5B'; g.lineWidth = 4; g.beginPath(); g.moveTo(7, -3); g.lineTo(-2, 8); g.stroke();
      if (id === 'virus' && Math.sin(t * 1.3) > .7) { g.fillStyle = '#FF5A5F'; g.font = '14px sans-serif'; g.fillText('🦠', 40, -20 + Math.sin(t * 5) * 3); }
    } else if (id === 'drivers') {   // seta baixando no PC
      g.restore(); g.save();
      const yy = py - 20 + ((t * 30) % 26);
      g.strokeStyle = '#7FD3FF'; g.lineWidth = 3; g.beginPath(); g.moveTo(px + 25, yy - 12); g.lineTo(px + 25, yy); g.moveTo(px + 19, yy - 6); g.lineTo(px + 25, yy); g.lineTo(px + 31, yy - 6); g.stroke();
      g.translate(bx + R * .9, by + 4); g.rotate(-.6 + bate * .2);
      chave(g);
    } else {   // chave inglesa / martelinho batendo no gabinete + faíscas
      g.rotate(-.9 + Math.max(0, bate) * 1.1);
      chave(g);
      if (bate > .92) for (let i = 0; i < 4; i++) cena.poeira.push({ x: px - 2, y: by - 6, vx: -20 + Math.random() * 40, vy: -40 - Math.random() * 40, v: 1, faisca: true });
    }
    g.restore();
    // poeira/faíscas
    cena.poeira = cena.poeira.filter(p => (p.v -= .02) > 0).slice(-80);
    for (const p of cena.poeira) {
      p.x += p.vx / 60; p.y += p.vy / 60; p.vy += 2;
      g.fillStyle = p.faisca ? `rgba(255,226,122,${p.v})` : `rgba(138,152,143,${p.v * .6})`;
      g.fillRect(p.x, p.y, p.faisca ? 2 : 3, p.faisca ? 2 : 3);
    }
  }
  function chave(g) {
    g.strokeStyle = '#B8C4BD'; g.lineWidth = 4; g.beginPath(); g.moveTo(0, 0); g.lineTo(0, -26); g.stroke();
    g.lineWidth = 3; g.beginPath(); g.arc(0, -30, 6, Math.PI * .25, Math.PI * 1.75); g.stroke();
  }
  function rr(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }

  // a KaniBall da faixa do chat "sai" e vai para a cena; no fim volta
  let kaniFora = false;
  function kaniVem() {
    const d = el('kb-doca');
    if (kaniFora || !d || d.hidden || trilho.getAttribute('aria-expanded') !== 'true') return;
    const casa = el('sd-cena-casa'); if (!casa) return;
    kaniFora = true;
    voo(d.getBoundingClientRect(), casa.getBoundingClientRect(), () => {});
    d.style.visibility = 'hidden';
  }
  function kaniVolta() {
    const d = el('kb-doca');
    if (!kaniFora || !d) return;
    kaniFora = false;
    const casa = el('sd-cena-casa');
    if (casa && !d.hidden) voo(casa.getBoundingClientRect(), d.getBoundingClientRect(), () => { d.style.visibility = ''; });
    else d.style.visibility = '';
  }
  function voo(de, para, fim) {
    const b = document.createElement('div'); b.className = 'sd-voo';
    const x0 = de.left + de.width / 2 - 26, y0 = de.top + 4, x1 = para.left + para.width / 2 - 52, y1 = para.top + para.height - 70;
    b.style.transform = `translate(${x0}px,${y0}px)`; document.body.append(b);
    b.animate([{ transform: `translate(${x0}px,${y0}px) scale(.9)` }, { transform: `translate(${(x0 + x1) / 2}px,${Math.min(y0, y1) - 80}px) scale(1.1) rotate(180deg)` },
      { transform: `translate(${x1}px,${y1}px) scale(1) rotate(360deg)` }], { duration: 700, easing: 'cubic-bezier(.3,.6,.4,1)' }).onfinish = () => { b.remove(); fim(); };
  }

  // ── cliques ──
  painel.addEventListener('click', async e => {
    const t = e.target;
    if (t.closest('#sd-op')) { opcoesAbertas = !opcoesAbertas; desenharHW(); return; }
    if (t.closest('#sd-iniciar')) {
      const b = t.closest('#sd-iniciar'); b.disabled = true; b.lastChild.textContent = 'Pedindo permissão…';
      decidido = {}; dupMarc = {};
      const r = await api().saude_iniciar(opcoes);
      if (!r.ok) { b.disabled = false; b.lastChild.textContent = 'Manutenção'; alerta(r.erro); return; }
      setTimeout(lerEstado, 1500); clearInterval(timerM); timerM = setInterval(lerEstado, 1000);
      el('sd-rolo').scrollTop = 0; return;
    }
    if (t.closest('#sd-parar')) { await api().saude_parar(); t.closest('#sd-parar').textContent = 'vai parar depois desta etapa…'; return; }
    const esc_ = t.closest('.sd-esc button');
    if (esc_) { decidido[esc_.parentNode.dataset.id] = esc_.dataset.v; esc_.parentNode.querySelectorAll('button').forEach(x => x.classList.toggle('sel', x === esc_)); return; }
    if (t.closest('#sd-aplicar')) {
      await api().saude_decidir(decidido, offline); t.closest('#sd-aplicar').disabled = true; t.closest('#sd-aplicar').textContent = 'Aplicando…';
      clearInterval(timerM); timerM = setInterval(lerEstado, 1000); return;
    }
    if (t.closest('#sd-dup-ir')) {
      const lista = []; (est.duplicados || []).forEach((g, i) => { if (dupMarc[i] !== false && i < 80) lista.push(...g.copias); });
      if (!lista.length) return;
      const b = t.closest('#sd-dup-ir'); b.disabled = true; b.textContent = 'Movendo…';
      const r = await api().saude_lixeira(lista);
      el('sd-dup-msg').textContent = `${r.movidos} cópia(s) na Lixeira · ${tam(r.bytes)} (dá para desfazer pela Lixeira).`;
      b.textContent = 'Feito'; return;
    }
  });
  painel.addEventListener('change', e => {
    const t = e.target;
    if (t.dataset.et) { opcoes.etapas = ETAPAS.map(x => x[0]).filter(id => painel.querySelector(`[data-et="${id}"]`)?.checked); }
    else if (t.dataset.op) opcoes[t.dataset.op] = t.checked;
    else if (t.dataset.dup != null) { dupMarc[+t.dataset.dup] = t.checked; desenharMan(); return; }
    try { localStorage.setItem('kanicode-saude-opcoes', JSON.stringify(opcoes)); } catch (_) {}
  });
  function alerta(txt) { const p = document.createElement('p'); p.className = 'sd-aviso'; p.textContent = txt; el('sd-corpo').prepend(p); setTimeout(() => p.remove(), 6000); }

  trilho.addEventListener('click', () => window.kaniPainelDireito(trilho.getAttribute('aria-expanded') !== 'true', 'saude'));
  el('sd-fechar').addEventListener('click', () => window.kaniPainelDireito(false, 'saude'));
  el('sd-atualizar').addEventListener('click', () => { el('sd-corpo').insertAdjacentHTML('afterbegin', '<p class="sd-nota">Lendo…</p>'); lerHW(); lerEstado(); });
  painel.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); window.kaniPainelDireito(false, 'saude'); trilho.focus(); } });
  new MutationObserver(() => {
    const aberto = trilho.getAttribute('aria-expanded') === 'true'; painel.inert = !aberto; clearInterval(timerH);
    if (aberto) {
      api().painel_espaco(LARG).catch(() => {});
      lerHW(); lerEstado(); timerH = setInterval(() => { if (!document.hidden) lerHW(); }, 5000);
      clearInterval(timerM); timerM = setInterval(lerEstado, 1000);
    } else { clearInterval(timerM); timerM = 0; kaniVolta(); }
  }).observe(trilho, { attributes: true, attributeFilter: ['aria-expanded'] });
  // fora da aba: de vez em quando confere se a manutenção ainda roda (o contador do trilho mostra "…")
  setInterval(async () => {
    if (trilho.getAttribute('aria-expanded') === 'true') return;
    try { est = await api().saude_estado(); } catch (_) { return; }
    const rod = ['rodando', 'decidir'].includes(est.situacao), cont = el('saude-cont');
    if (rod) { cont.hidden = false; cont.textContent = est.situacao === 'decidir' ? '!' : '…'; }
  }, 10000);
})();
