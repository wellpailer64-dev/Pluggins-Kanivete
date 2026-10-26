/* Tarefas pessoais e agenda compartilhadas entre o painel e a Kani. */
(() => {
  const el = id => document.getElementById(id), api = () => window.pywebview.api;
  const trilho = document.createElement('button'); trilho.id = 'todo-trilho'; trilho.className = 'trilho';
  trilho.title = 'Tarefas e agenda'; trilho.setAttribute('aria-label', 'Tarefas e agenda');
  trilho.setAttribute('aria-expanded', 'false'); trilho.setAttribute('aria-controls', 'todo-painel');
  trilho.innerHTML = '<span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="3"/><path d="m8 10 2 2 5-5M8 16h8"/></svg></span><span class="vert">TO-DO</span>';
  el('atv-trilho').after(trilho);
  const painel = document.createElement('section'); painel.id = 'todo-painel'; painel.className = 'det';
  painel.setAttribute('aria-label', 'Tarefas e agenda');
  painel.innerHTML = `<div class="cab"><b>Seu dia</b><span class="esp"></span><button class="bt" id="todo-fechar" aria-label="Recolher tarefas">»</button></div>
    <div class="todo-rolo"><p class="todo-intro">Um lugar para tirar as coisas da cabeça.</p>
      <div class="todo-nav" role="tablist" aria-label="Organização pessoal"><button id="todo-tab-tarefas" role="tab" aria-selected="true" aria-controls="todo-tarefas">Tarefas</button><button id="todo-tab-agenda" role="tab" aria-selected="false" aria-controls="todo-agenda" tabindex="-1">Agenda</button><button id="todo-tab-alarmes" role="tab" aria-selected="false" aria-controls="todo-alarmes" tabindex="-1">Alarmes</button></div>
      <section id="todo-tarefas" role="tabpanel" aria-labelledby="todo-tab-tarefas">
        
        <div id="todo-lista"></div><details id="todo-concluidas" hidden><summary id="todo-total-concluidas"></summary><div id="todo-feitas"></div></details>
      </section>
      <section id="todo-agenda" role="tabpanel" aria-labelledby="todo-tab-agenda" hidden>
        <div class="todo-agenda-topo"><div class="todo-vista" role="group" aria-label="Ver agenda como"><button type="button" data-v="lista">Lista</button><button type="button" data-v="semana">Semana</button></div><button class="todo-editar" id="todo-sync">↻ Atualizar</button></div>
        <div id="todo-eventos"></div><p class="todo-intro" id="todo-agenda-nota"></p>
      </section>
      <section id="todo-alarmes" role="tabpanel" aria-labelledby="todo-tab-alarmes" hidden>
        <div id="todo-alarmes-lista"></div>
        <details id="todo-lembrete"><summary id="todo-lembrete-cab">＋ Novo alarme</summary><form id="todo-lembrete-form">
          <label>Título<input id="todo-lembrete-titulo" required maxlength="300" placeholder="Ex.: consulta médica"></label>
          <label>Data e hora<input id="todo-inicio" type="datetime-local" required></label>
          <div class="todo-dias" role="group" aria-label="Repetir nos dias">${['seg','ter','qua','qui','sex','sab','dom'].map(d => `<button type="button" data-d="${d}" aria-pressed="false">${d}</button>`).join('')}</div>
          <label>Avisar antes<select id="todo-antes"><option value="5">5 minutos</option><option value="10" selected>10 minutos</option><option value="30">30 minutos</option><option value="60">1 hora</option></select></label>
          <p class="todo-intro">Aviso falado da Kani. O PC precisa estar ligado. Marque dias para repetir toda semana.</p>
          <div class="todo-campos"><button class="todo-botao" id="todo-lembrete-salvar">Salvar alarme</button><button type="button" class="todo-editar" id="todo-lembrete-cancelar" hidden>Cancelar</button></div>
        </form></details>
      </section><p id="todo-status" role="status" aria-live="polite"></p>
    </div>
    <div class="todo-pe" id="todo-pe"><form id="todo-form"><label for="todo-titulo" id="todo-form-titulo">O que precisa ser feito?</label><input id="todo-titulo" required maxlength="300" placeholder="Adicionar uma tarefa…" autocomplete="off">   <div class="todo-campos"><label>Prazo · opcional<input type="date" id="todo-prazo"></label><button class="todo-botao" id="todo-salvar">Adicionar</button><button type="button" class="todo-editar" id="todo-cancelar" hidden>Cancelar</button></div></form></div>`;
  el('atv').append(painel); painel.inert = true; painel.setAttribute('aria-hidden', 'true');
  let aberto = false, aba = 'tarefas', editando = '', ocupado = false, timer = null, itens = [], rodada = 0;
  const agenteTab=document.createElement('button'); agenteTab.id='todo-tab-agente'; agenteTab.textContent='Agente';
  agenteTab.setAttribute('role','tab'); agenteTab.setAttribute('aria-selected','false'); agenteTab.setAttribute('aria-controls','todo-agente'); agenteTab.tabIndex=-1;
  el('todo-tab-tarefas').after(agenteTab);
  const agenteSec=document.createElement('section'); agenteSec.id='todo-agente'; agenteSec.hidden=true;
  agenteSec.setAttribute('role','tabpanel'); agenteSec.setAttribute('aria-labelledby','todo-tab-agente');
  agenteSec.innerHTML='<p class="todo-intro">Pedidos da fila e pendências combinadas com os agentes, ligados à mensagem original.</p><div id="todo-agente-lista"></div><details id="todo-agente-concluidas" hidden><summary id="todo-agente-total"></summary><div id="todo-agente-feitas"></div></details><div id="todo-agente-contexto" hidden></div>';
  el('todo-tarefas').after(agenteSec);
  let agenteContexto='';
  const espelho=document.createElement('nav');espelho.id='todo-agente-espelho';espelho.hidden=true;
  espelho.setAttribute('aria-label','Tarefas abertas do agente');el('status').before(espelho);
  let agenteRodada=0;
  async function agenteAbrir(id='') {
    await window.kaniPainelDireito(true,'todo');navegar('agente',true);
    if(id)agentePedido(id);
  }
  function agenteEspelhar(lista) {
    el('status').before(espelho);
    let abertas=lista.filter(i=>!i.concluida&&i.estado!=='cancelada');
    // Na barra só o que pede ação: "a conferir" (resposta já entregue) fica no painel; de falhas, só a última de cada conversa.
    const ultFalha={};
    for(const i of abertas)if(i.estado==='falha'&&String(i.criado||'')>=String((ultFalha[i.aba]||{}).criado||''))ultFalha[i.aba]=i;
    abertas=abertas.filter(i=>i.estado!=='a_conferir'&&(i.estado!=='falha'||ultFalha[i.aba]===i));
    espelho.replaceChildren();espelho.hidden=false;espelho.removeAttribute('title');
    const total=document.createElement('button');total.className='todo-agente-contagem';
    total.textContent='Agente · '+abertas.length;total.title='Abrir To-do do agente';total.onclick=()=>agenteAbrir();
    const tags=document.createElement('div');tags.className='todo-agente-tags';
    for(const i of abertas){
      const tag=document.createElement('button');tag.className='todo-agente-tag';tag.dataset.tarefaAgente=i.id;
      const titulo=String(i.titulo||'Tarefa').replace(/\s+/g,' ').trim();
      tag.textContent=titulo.length>48?titulo.slice(0,47)+'…':titulo;tag.title=titulo;
      tag.onclick=()=>agenteAbrir(i.id);tags.append(tag);
    }
    espelho.append(total,tags);
  }
  async function agenteCarregar() {
    const numero=++agenteRodada;
    try {
      const lista=await api().todo_agente_listar();
      if(numero!==agenteRodada||!Array.isArray(lista))return;
      agenteEspelhar(lista);
      if(aberto&&aba==='agente')agenteDesenhar(lista);
    } catch(e) {espelho.title='Não foi possível atualizar as tarefas do agente.';}
  }
  async function agentePedido(id) {
    agenteContexto=id;
    try {
      const i=await api().todo_agente_contexto(id);
      if(agenteContexto!==id) return;
      const caixa=el('todo-agente-contexto');caixa.replaceChildren();caixa.hidden=false;
      const cab=document.createElement('b');cab.textContent='Pedido original · conversa '+i.aba;
      const texto=document.createElement('pre');texto.textContent=i.texto;
      const ir=document.createElement('button');ir.className='todo-editar';ir.textContent='Localizar na conversa';
      ir.onclick=async()=>{const ok=await window.mensagemLocalizar?.(i);if(!ok)status('O pedido original está preservado acima. A mensagem não está carregada nesta conversa.');};
      caixa.append(cab,texto,ir);
    } catch(e) {status(String(e.message||e),true);}
  }
  function agenteDesenhar(lista) {
    el('todo-agente-lista').replaceChildren();el('todo-agente-feitas').replaceChildren();
    const estados={pendente:'Na fila',em_andamento:'Em andamento',a_conferir:'Conclusão a confirmar',adiada:'Para depois',falha:'Precisa retomar',concluida:'Concluída',cancelada:'Cancelada'};
    const abertas=lista.filter(i=>!i.concluida&&i.estado!=='cancelada');
    if(!abertas.length){const p=document.createElement('p');p.className='todo-vazio';p.textContent='Nenhuma pendência do agente.';el('todo-agente-lista').append(p);}
    for(const i of lista){
      const linha=document.createElement('div');linha.className='todo-linha'+(i.concluida?' feita':'');linha.dataset.tarefaAgente=i.id;
      const check=document.createElement('input');check.type='checkbox';check.className='todo-check';check.checked=i.concluida;
      check.setAttribute('aria-label',(i.concluida?'Reabrir ':'Concluir ')+i.titulo);
      check.onchange=()=>executar(async()=>{await api().todo_agente_concluir(i.id,check.checked);await atualizar();});
      const corpo=document.createElement('div');corpo.className='todo-textos';
      const titulo=document.createElement('b');titulo.textContent=i.titulo;
      const nota=document.createElement('small');nota.textContent=(estados[i.estado]||i.estado)+' · '+(i.agente||'agente')+' · conversa '+i.aba;
      const origem=document.createElement('button');origem.className='todo-editar';origem.textContent='Ver pedido';origem.onclick=()=>agentePedido(i.id);
      corpo.append(titulo,nota,origem);if(i.motivo&&!i.concluida){const motivo=document.createElement('small');motivo.textContent=i.motivo;corpo.append(motivo);}
      linha.append(check,corpo);(i.concluida||i.estado==='cancelada'?el('todo-agente-feitas'):el('todo-agente-lista')).append(linha);
    }
    const feitas=lista.filter(i=>i.concluida||i.estado==='cancelada');
    el('todo-agente-concluidas').hidden=!feitas.length;el('todo-agente-total').textContent='Finalizadas · '+feitas.length;
  }
  const hoje = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
  const dataCurta = data => new Date(data + 'T12:00:00').toLocaleDateString('pt-BR', {day:'numeric', month:'short'});
  function status(texto = '', erro = false) { el('todo-status').textContent = texto; el('todo-status').classList.toggle('erro', erro); }
  function cancelar() { editando = ''; el('todo-form').reset(); el('todo-salvar').textContent = 'Adicionar'; el('todo-cancelar').hidden = true; el('todo-form-titulo').textContent = 'O que precisa ser feito?'; }
  function linha(item) {
    const r = document.createElement('div'); r.className = 'todo-linha' + (item.concluida ? ' feita' : '');
    const check = document.createElement('input'); check.type = 'checkbox'; check.className = 'todo-check'; check.checked = item.concluida;
    check.setAttribute('aria-label', (item.concluida ? 'Reabrir ' : 'Concluir ') + item.titulo);
    check.addEventListener('change', () => executar(async () => { await api().todo_concluir(item.id, check.checked); await atualizar(); }));
    const texto = document.createElement('div'); texto.className = 'todo-textos';
    const titulo = document.createElement('b'); titulo.textContent = item.titulo;
    const meta = document.createElement('small'); meta.textContent = [item.prazo ? dataCurta(item.prazo) : '', item.origem === 'kani' ? 'Adicionada pela Kani' : ''].filter(Boolean).join(' · ');
    if (!item.concluida && item.prazo && item.prazo < hoje()) meta.className = 'todo-atrasada';
    texto.append(titulo, meta);
    const editar = document.createElement('button'); editar.className = 'todo-editar'; editar.textContent = 'Editar'; editar.setAttribute('aria-label', 'Editar ' + item.titulo);
    editar.addEventListener('click', () => { editando = item.id; el('todo-titulo').value = item.titulo; el('todo-prazo').value = item.prazo || ''; el('todo-salvar').textContent = 'Salvar'; el('todo-cancelar').hidden = false; el('todo-form-titulo').textContent = 'Editar tarefa'; el('todo-titulo').focus(); });
    r.append(check, texto, editar); return r;
  }
  function desenhar() {
    const lista = el('todo-lista'); lista.replaceChildren(); el('todo-feitas').replaceChildren();
    // grupos na ordem Pendentes · Hoje · Próximas · Sem prazo; dentro de cada um, as mais novas em cima
    const ordem = i => !i.prazo ? 3 : i.prazo < hoje() ? 0 : i.prazo === hoje() ? 1 : 2;
    const abertas = itens.filter(i => !i.concluida).sort((a,b) => ordem(a) - ordem(b) || String(b.criado).localeCompare(String(a.criado)));
    if (!abertas.length) { const p = document.createElement('p'); p.className = 'todo-vazio'; p.textContent = 'Tudo em dia. Adicione uma tarefa abaixo ou peça para a Kani anotar.'; lista.append(p); }
    let grupo = '';
    for (const item of abertas) {
      const nome = !item.prazo ? 'Sem prazo' : item.prazo < hoje() ? 'Pendentes' : item.prazo === hoje() ? 'Hoje' : 'Próximas';
      if (nome !== grupo) { const h = document.createElement('h4'); h.className = 'todo-grupo'; h.textContent = nome; lista.append(h); grupo = nome; }
      lista.append(linha(item));
    }
    const feitas = itens.filter(i => i.concluida).reverse();
    el('todo-concluidas').hidden = !feitas.length; el('todo-total-concluidas').textContent = `Concluídas · ${feitas.length}`;
    feitas.forEach(i => el('todo-feitas').append(linha(i)));
  }
  // agenda: lista dos próximos 7 dias ou semana (faixa de 7 dias a partir de hoje + os compromissos do dia escolhido)
  let vista = 'lista', diaSel = '', ultimaAgenda = null;
  try { vista = localStorage.getItem('kc-todo-vista') === 'semana' ? 'semana' : 'lista'; } catch (_) {}
  const quando = item => new Date(item.dia_inteiro ? item.inicio.slice(0, 10) + 'T12:00:00' : item.inicio);
  const chaveDia = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  function evento(item) {
    const data = quando(item);
    const linha = document.createElement('div'); linha.className = 'todo-linha';
    const texto = document.createElement('div'); texto.className = 'todo-textos';
    const titulo = document.createElement('b'); titulo.textContent = item.titulo;
    const meta = document.createElement('small'); meta.textContent = `${item.dia_inteiro ? 'Dia inteiro' : data.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})} · ${item.origem === 'google' ? item.calendario || 'Google Calendar' : item.origem === 'pandalab' ? 'Pandalab' : 'Lembrete da Kani'}`;
    texto.append(titulo, meta); linha.append(texto);
    if (item.origem === 'kani') {   // alarme da Kani: abre na aba Alarmes para mudar/excluir
      const b = document.createElement('button'); b.className = 'todo-editar'; b.textContent = 'Editar'; b.setAttribute('aria-label', 'Editar alarme ' + item.titulo);
      b.addEventListener('click', () => { alarmeAbrir = item.id; navegar('alarmes'); }); linha.append(b);
    }
    return linha;
  }
  // alarmes: os lembretes da Kani (compromissos.json), com editar e excluir
  let alarmeEd = '', alarmeAbrir = '', alarmesItens = [], excluir = '';
  const NOMES_DIA = {seg:'seg', ter:'ter', qua:'qua', qui:'qui', sex:'sex', sab:'sáb', dom:'dom'};
  const diasSel = () => [...painel.querySelectorAll('.todo-dias button[aria-pressed=true]')].map(b => b.dataset.d);
  function alarmeCancelar() {
    alarmeEd = ''; el('todo-lembrete-form').reset(); painel.querySelectorAll('.todo-dias button').forEach(b => b.setAttribute('aria-pressed', 'false'));
    el('todo-inicio').type = 'datetime-local'; el('todo-lembrete-cab').textContent = '＋ Novo alarme'; el('todo-lembrete-cancelar').hidden = true;
  }
  function alarmeEditar(a) {
    alarmeEd = a.id; el('todo-lembrete').open = true; el('todo-lembrete-cab').textContent = 'Editar alarme'; el('todo-lembrete-cancelar').hidden = false;
    painel.querySelectorAll('.todo-dias button').forEach(b => b.setAttribute('aria-pressed', String((a.dias || []).includes(b.dataset.d))));
    el('todo-inicio').type = a.dias?.length ? 'time' : 'datetime-local';
    el('todo-inicio').value = a.dias?.length ? a.hora : `${a.data}T${a.hora}`;
    el('todo-lembrete-titulo').value = a.titulo; el('todo-antes').value = String(a.antes || 10);
    if (!el('todo-antes').value) { el('todo-antes').add(new Option(`${a.antes} minutos`, a.antes)); el('todo-antes').value = String(a.antes); }
    el('todo-lembrete-titulo').focus(); el('todo-lembrete').scrollIntoView({block: 'nearest'});
  }
  function alarmesDesenhar() {
    const lista = el('todo-alarmes-lista'); lista.replaceChildren(); let grupo = '';
    if (!alarmesItens.length) { const p = document.createElement('p'); p.className = 'todo-vazio'; p.textContent = 'Nenhum alarme. Crie um abaixo ou peça à Kani.'; lista.append(p); }
    for (const a of alarmesItens) {
      const nome = a.passado ? 'Já passaram' : a.dias?.length ? 'Toda semana' : 'Próximos';
      if (nome !== grupo) { const h = document.createElement('h4'); h.className = 'todo-grupo'; h.textContent = nome; lista.append(h); grupo = nome; }
      const r = document.createElement('div'); r.className = 'todo-linha' + (a.passado ? ' feita' : '');
      const texto = document.createElement('div'); texto.className = 'todo-textos';
      const b = document.createElement('b'); b.textContent = a.titulo;
      const quando = a.dias?.length ? a.dias.map(d => NOMES_DIA[d] || d).join(', ') : dataCurta(a.data);
      const m = document.createElement('small'); m.textContent = `${quando} · ${a.hora} · avisa ${a.antes} min antes`;
      texto.append(b, m);
      const ed = document.createElement('button'); ed.className = 'todo-editar'; ed.textContent = 'Editar'; ed.setAttribute('aria-label', 'Editar ' + a.titulo);
      ed.addEventListener('click', () => alarmeEditar(a));
      const ex = document.createElement('button'); ex.className = 'todo-editar todo-excluir'; ex.textContent = excluir === a.id ? 'Excluir?' : '✕';
      ex.setAttribute('aria-label', 'Excluir ' + a.titulo); ex.title = 'Excluir';
      ex.addEventListener('click', () => {
        if (excluir !== a.id) { excluir = a.id; alarmesDesenhar(); painel.querySelector('.todo-excluir.confirmar')?.focus(); return; }
        executar(async () => { await api().todo_alarme_apagar(a.id); excluir = ''; if (alarmeEd === a.id) alarmeCancelar(); await atualizar(); status('Alarme excluído.'); });
      });
      if (excluir === a.id) ex.classList.add('confirmar');
      r.append(texto, ed, ex); lista.append(r);
    }
    if (alarmeAbrir) { const a = alarmesItens.find(i => i.id === alarmeAbrir); alarmeAbrir = ''; if (a) alarmeEditar(a); }
  }
  function semana(r, lista) {
    const porDia = {};
    for (const item of r.itens) (porDia[chaveDia(quando(item))] ||= []).push(item);
    const dias = Array.from({length: 7}, (_, n) => { const d = new Date(); d.setHours(12, 0, 0, 0); d.setDate(d.getDate() + n); return d; });
    if (!dias.some(d => chaveDia(d) === diaSel)) diaSel = chaveDia(dias[0]);
    const faixa = document.createElement('div'); faixa.className = 'todo-semana'; faixa.setAttribute('role', 'tablist'); faixa.setAttribute('aria-label', 'Dias da semana');
    for (const d of dias) {
      const k = chaveDia(d), n = (porDia[k] || []).length;
      const b = document.createElement('button'); b.type = 'button'; b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', String(k === diaSel)); b.className = k === chaveDia(dias[0]) ? 'hoje' : '';
      b.setAttribute('aria-label', d.toLocaleDateString('pt-BR', {weekday:'long', day:'numeric', month:'long'}) + (n ? `, ${n} compromisso${n > 1 ? 's' : ''}` : ''));
      b.innerHTML = `<small>${d.toLocaleDateString('pt-BR', {weekday:'short'}).replace('.', '').slice(0, 3)}</small><b>${d.getDate()}</b><i>${'<span></span>'.repeat(Math.min(n, 3))}</i>`;
      b.addEventListener('click', () => { diaSel = k; agenda(ultimaAgenda); lista.querySelector('.todo-semana [aria-selected=true]')?.focus(); });
      faixa.append(b);
    }
    lista.append(faixa);
    const sel = dias.find(d => chaveDia(d) === diaSel);
    const h = document.createElement('h4'); h.className = 'todo-grupo'; h.textContent = sel.toLocaleDateString('pt-BR', {weekday:'long', day:'numeric', month:'short'}); lista.append(h);
    const doDia = porDia[diaSel] || [];
    doDia.forEach(item => lista.append(evento(item)));
    if (!doDia.length) { const p = document.createElement('p'); p.className = 'todo-vazio'; p.textContent = 'Nada marcado neste dia.'; lista.append(p); }
  }
  function agenda(r) {
    if (!r) return;
    ultimaAgenda = r;
    painel.querySelectorAll('.todo-vista button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.v === vista)));
    const lista = el('todo-eventos'); lista.replaceChildren(); let grupo = '';
    if (vista === 'semana') semana(r, lista);
    else for (const item of r.itens) {
      const dia = quando(item).toLocaleDateString('pt-BR', {weekday:'short',day:'numeric',month:'short'});
      if (dia !== grupo) { const h = document.createElement('h4'); h.className = 'todo-grupo'; h.textContent = dia; lista.append(h); grupo = dia; }
      lista.append(evento(item));
    }
    if (!r.itens.length && vista === 'lista') { const p = document.createElement('p'); p.className = 'todo-vazio'; p.textContent = 'Nenhum compromisso nos próximos dias.'; lista.append(p); }
    el('todo-agenda-nota').textContent = r.google_conectado ? 'Calendários conectados · somente leitura' + (r.ultima_sync ? ' · atualizados em ' + new Date(r.ultima_sync).toLocaleString('pt-BR') : '') : 'Conecte o Google Calendar em Conexões para ver seus calendários aqui.';
    if (r.mensagem) status(r.mensagem, true);
    else if (r.avisos?.estado === 'erro') status('Há uma falha na preparação dos avisos falados. Confira Conexões.', true);
  }
  async function atualizar(sync = false) {
    const numero = ++rodada;
    try {
      if (aba === 'tarefas') { const r = await api().todo_listar(); if (numero === rodada) { itens = r; desenhar(); } }
      else if (aba === 'agente') { await agenteCarregar(); }
      else if (aba === 'alarmes') { const r = await api().todo_alarmes(); if (numero === rodada) { alarmesItens = r; alarmesDesenhar(); } }
      else { const r = await api().todo_agenda(sync); if (numero === rodada) agenda(r); }
    } catch (e) { status(String(e.message || e), true); }
  }
  async function executar(fn) {
    if (ocupado) return;
    ocupado = true; painel.querySelectorAll('button, input, select').forEach(e => { e.disabled = true; }); status();
    try { await fn(); } catch (e) { status(String(e.message || e), true); await atualizar(); }
    finally { ocupado = false; painel.querySelectorAll('button, input, select').forEach(e => { e.disabled = false; }); }
  }
  function navegar(nome, foco = false) {
    aba = nome; status();
    for (const id of ['tarefas','agente','agenda','alarmes']) { const b = el('todo-tab-' + id); b.setAttribute('aria-selected', String(id === nome)); b.tabIndex = id === nome ? 0 : -1; el('todo-' + id).hidden = id !== nome; } el('todo-pe').hidden = nome !== 'tarefas'; excluir = '';
    if (foco) el('todo-tab-' + nome).focus(); atualizar();
  }
  painel.querySelectorAll('.todo-vista button').forEach(b => b.addEventListener('click', () => {
    vista = b.dataset.v; try { localStorage.setItem('kc-todo-vista', vista); } catch (_) {}
    agenda(ultimaAgenda);
  }));
  trilho.addEventListener('click', async () => { await window.kaniPainelDireito(trilho.getAttribute('aria-expanded') !== 'true', 'todo'); if (trilho.getAttribute('aria-expanded') === 'true') { atualizar(); el('todo-tab-' + aba).focus(); } });
  el('todo-fechar').addEventListener('click', () => { window.kaniPainelDireito(false, 'todo'); trilho.focus(); });
  new MutationObserver(() => {
    aberto = trilho.getAttribute('aria-expanded') === 'true'; painel.inert = !aberto; painel.setAttribute('aria-hidden', String(!aberto)); clearInterval(timer);
    if (aberto) timer = setInterval(() => { if (!ocupado && !document.hidden) atualizar(); }, 15000);
  }).observe(trilho, {attributes:true, attributeFilter:['aria-expanded']});
  el('todo-tab-tarefas').addEventListener('click', () => navegar('tarefas'));
  agenteTab.addEventListener('click',()=>navegar('agente'));
  el('todo-tab-agenda').addEventListener('click', () => navegar('agenda'));
  el('todo-tab-alarmes').addEventListener('click', () => navegar('alarmes'));
  painel.querySelectorAll('.todo-dias button').forEach(b => b.addEventListener('click', () => {
    b.setAttribute('aria-pressed', String(b.getAttribute('aria-pressed') !== 'true'));
    const semana = diasSel().length > 0, campo = el('todo-inicio'), v = campo.value;
    if (semana && campo.type !== 'time') { campo.type = 'time'; campo.value = v.slice(11, 16); }
    else if (!semana && campo.type !== 'datetime-local') { campo.type = 'datetime-local'; campo.value = v ? `${hoje()}T${v}` : ''; }
  }));
  el('todo-lembrete-cancelar').addEventListener('click', alarmeCancelar);
  painel.querySelector('.todo-nav').addEventListener('keydown', e => {
    const abas = ['tarefas','agente','agenda','alarmes'], i = abas.indexOf(aba);
    if (['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) { e.preventDefault(); navegar(e.key === 'Home' ? abas[0] : e.key === 'End' ? abas.at(-1) : abas[(i + (e.key === 'ArrowRight' ? 1 : abas.length-1)) % abas.length], true); }
  });
  el('todo-form').addEventListener('submit', e => { e.preventDefault(); executar(async () => { await api().todo_salvar(el('todo-titulo').value, el('todo-prazo').value, editando); cancelar(); await atualizar(); el('todo-titulo').focus(); }); });
  el('todo-cancelar').addEventListener('click', cancelar);
  el('todo-sync').addEventListener('click', () => executar(() => atualizar(true)));
  el('todo-lembrete-form').addEventListener('submit', e => { e.preventDefault(); executar(async () => {
    const titulo = el('todo-lembrete-titulo').value, inicio = el('todo-inicio').value, antes = Number(el('todo-antes').value), dias = diasSel(), ed = alarmeEd;
    if (ed || dias.length) await api().todo_alarme_salvar(ed, titulo, inicio, antes, dias);
    else await api().todo_lembrar(titulo, inicio, antes);
    alarmeCancelar(); el('todo-lembrete').open = false; await atualizar(); status(ed ? 'Alarme alterado.' : 'Lembrete salvo. Avisos pelo agendador da Kani.');
  }); });
  painel.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); window.kaniPainelDireito(false, 'todo'); trilho.focus(); } });
  const eventoAntes=window.kcEv;
  window.kcEv=ev=>{if(ev?.t==='todo_agente'){agenteCarregar();return;}return eventoAntes(ev);};
  setInterval(()=>{if(!document.hidden&&!(aberto&&aba==='agente'))agenteCarregar();},15000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)agenteCarregar();});
  window.addEventListener('pywebviewready',agenteCarregar);
  if(window.pywebview?.api)agenteCarregar();
})();
