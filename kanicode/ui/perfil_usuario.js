/* Perfil do usuário: avatar no alto da coluna das contas; clique abre a seção por cima (foto, nome, informações, parâmetros).
   Dados em <DADOS>/perfil/usuario.json + foto.png (perfil_usuario.py). */
(() => {
  const P = { d: null };
  const ini = n => String(n || '?').trim().split(/\s+/).slice(0, 2).map(p => p[0]).join('').toUpperCase() || '?';
  const fotoHtml = d => d.foto && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(d.foto) ? `<img src="${d.foto}" alt="">` : `<span>${esc(ini(d.nome))}</span>`;
  const CAMPOS = [['nome', 'Nome'], ['apelido', 'Me chamar de'], ['email', 'E-mail'], ['telefone', 'Telefone'],
                  ['empresa', 'Empresa'], ['funcao', 'Função'], ['cidade', 'Cidade'], ['site', 'Site']];

  const sec = document.createElement('aside');
  sec.className = 'perfil-sec'; sec.id = 'perfil-sec'; sec.hidden = true; sec.setAttribute('aria-label', 'Meu perfil');
  document.querySelector('.corpo').appendChild(sec);
  const arquivo = document.createElement('input');
  arquivo.type = 'file'; arquivo.accept = 'image/*'; arquivo.hidden = true; document.body.appendChild(arquivo);

  function botao() {
    const d = P.d; if (!d) return;
    $('perfil-bt').innerHTML = fotoHtml(d);
    $('perfil-bt').title = `${d.nome || 'Meu perfil'} · abrir perfil`;
    const s = $('saudacao'); if (s) s.textContent = `Olá, ${d.apelido || d.nome || 'Pailer'}.`;
  }
  function contaEmUso() {
    const c = window.CT && CT.dados && CT.dados.lista.find(x => x.id === CT.dados.ativa);
    if (!c) return '<div class="perfil-linha"><span>Conta do Claude</span><span>—</span></div>';
    return `<div class="perfil-linha"><span>Conta do Claude</span><span>${esc(c.email || c.apelido || '—')}</span></div>
      ${c.plano ? `<div class="perfil-linha"><span>Plano</span><span>${esc(String(c.plano).toUpperCase())}</span></div>` : ''}`;
  }
  function desenhar() {
    const d = P.d; if (!d) return;
    sec.innerHTML = `<h4>MEU PERFIL<button class="bt" data-a="fechar" title="Recolher">«</button></h4>
      <div class="perfil-topo">
        <button class="perfil-foto" data-a="foto" title="Trocar a foto">${fotoHtml(d)}<i>trocar foto</i></button>
        <div class="perfil-nome">${esc(d.nome || 'Sem nome')}</div>
        <div class="perfil-sub">${esc([d.funcao, d.empresa].filter(Boolean).join(' · ') || d.email || '')}</div>
      </div>
      <details class="perfil-det"><summary>Informações básicas</summary>
        ${CAMPOS.map(([k, r]) => `<label class="perfil-campo"><span>${r}</span><input data-k="${k}" value="${esc(d[k] || '')}" spellcheck="false"></label>`).join('')}
        <div class="perfil-ok" id="perfil-ok"></div>
      </details>
      <div class="perfil-bloco perfil-cerebro"><b class="tit">🧠 Cérebro</b><div class="cerebro" id="cerebro"></div></div>
      <div class="perfil-acoes"><button data-a="portatil">Backup e sincronização do perfil</button></div>
      <details class="perfil-det"><summary>Parâmetros</summary>
        ${contaEmUso()}
        <div class="perfil-acoes" style="margin-top:8px">
          <button data-a="contas">Contas do Claude</button><button data-a="config">Configurações</button>
          ${d.foto ? '<button data-a="semfoto">Tirar foto</button>' : ''}
        </div>
      </details>`;
    window.Cerebro?.montar($('cerebro'), d);
  }
  async function carregar() {
    try { P.d = await api().usuario_ler(); botao(); if (!sec.hidden) desenhar(); } catch (e) { console.warn('perfil:', e); }
  }
  function abrir(on) {
    if (on && $('lado').classList.contains('aberto')) window.contasAbrir();   // a coluna das contas recolhe
    sec.hidden = !on;
    if (on) { desenhar(); carregar(); }
  }
  window.perfilAbrir = abrir;

  $('perfil-bt').addEventListener('click', e => { e.stopPropagation(); abrir(sec.hidden); });
  document.addEventListener('mousedown', e => {
    if (!sec.hidden && !sec.contains(e.target) && !e.target.closest('#perfil-bt, .caixa')) abrir(false);
  });
  sec.addEventListener('keydown', e => { if (e.key === 'Escape') abrir(false); });
  sec.addEventListener('click', async e => {
    const a = e.target.closest('[data-a]')?.dataset.a; if (!a) return;
    if (a === 'fechar') abrir(false);
    else if (a === 'foto') arquivo.click();
    else if (a === 'semfoto') { P.d = await api().usuario_foto(''); botao(); desenhar(); }
    else if (a === 'contas') { abrir(false); window.contasAbrir(); }
    else if (a === 'config') { abrir(false); $('ferramentas-bt')?.click(); }
    else if (a === 'portatil') { abrir(false); window.perfilPortatilAbrir?.(); }
  });
  sec.addEventListener('change', async e => {
    const k = e.target.dataset.k; if (!k) return;
    try {
      P.d = await api().usuario_salvar({ [k]: e.target.value }); botao();
      sec.querySelector('.perfil-nome').textContent = P.d.nome || 'Sem nome';
      sec.querySelector('.perfil-sub').textContent = [P.d.funcao, P.d.empresa].filter(Boolean).join(' · ') || P.d.email || '';
      if (k === 'nome' && !P.d.foto) sec.querySelector('.perfil-foto').innerHTML = fotoHtml(P.d) + '<i>trocar foto</i>';
      $('perfil-ok').textContent = 'Salvo.'; setTimeout(() => { const o = $('perfil-ok'); if (o) o.textContent = ''; }, 1500);
    } catch (x) { $('perfil-ok').textContent = String(x.message || x); }
  });
  arquivo.addEventListener('change', () => {
    const f = arquivo.files[0]; arquivo.value = ''; if (!f) return;
    const r = new FileReader();
    r.onload = async () => {
      try { P.d = await api().usuario_foto(r.result); botao(); desenhar(); }
      catch (x) { bolha('erro', 'Não deu para usar essa foto: ' + (x.message || x)); }
    };
    r.readAsDataURL(f);
  });

  if (window.pywebview && pywebview.api) carregar(); else window.addEventListener('pywebviewready', carregar);
})();
