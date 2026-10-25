/* Perfil portátil e sincronização pelo Drive autenticado. */
(() => {
  // Acesso único pelo Meu perfil da lateral.
  const p=document.createElement('section');p.className='perfil-portatil';p.hidden=true;p.setAttribute('aria-label','Meu perfil KaniCode');
  p.innerHTML='<header><strong>Meu perfil KaniCode</strong><button aria-label="Fechar perfil">×</button></header>'+
    '<p>Seu perfil reúne preferências, cadastro, memórias e cérebro. Entre com a mesma conta Google em outro computador para encontrar seu perfil no Drive.</p>'+
    '<div class="perfil-nuvem"><strong>Google Drive · pasta KaniCode</strong><p class="perfil-nuvem-status" role="status"></p>'+
    '<div class="perfil-botoes"><button data-nuvem="login">Entrar com Google</button><button data-nuvem="oauth">Importar configuração OAuth</button>'+
    '<button data-nuvem="ativar">Ativar sincronização</button><button data-nuvem="sincronizar">Sincronizar agora</button><button data-nuvem="pausar">Pausar</button></div>'+
    '<section class="perfil-acesso"><strong>Seu acesso KaniCode</strong><p>Primeiro autorize o Google no botão acima. Depois entre ou cadastre uma senha própria do KaniCode.</p>'+
    '<form class="perfil-acesso-form"><label>E-mail<input class="perfil-acesso-email" type="email" autocomplete="username" maxlength="200" required></label>'+
    '<label>Senha do KaniCode<input class="perfil-acesso-senha" type="password" autocomplete="current-password" maxlength="1024" required></label>'+
    '<label class="perfil-acesso-confirmar" hidden>Repita a senha<input type="password" autocomplete="new-password" maxlength="1024"></label>'+
    '<p class="perfil-acesso-dica" hidden>Crie uma senha de pelo menos 12 caracteres. Guarde-a: esta versão ainda não tem recuperação de senha.</p>'+
    '<label class="perfil-acesso-lembrar"><input type="checkbox" checked> Lembrar acesso neste PC</label>'+
    '<div class="perfil-botoes"><button type="submit">Entrar no meu perfil</button><button type="button" class="perfil-acesso-modo">Primeira vez? Cadastrar acesso</button></div></form>'+
    '<p class="perfil-acesso-status" role="status"></p><button class="perfil-acesso-sair" hidden>Sair do acesso neste PC</button></section>'+
    '<p>No primeiro acesso em outro PC, confira o perfil encontrado antes de restaurar. Após entrar, o app confere o Drive a cada minuto enquanto estiver aberto.</p>'+
    '<div class="perfil-botoes"><select class="perfil-nuvem-versoes" aria-label="Versão do perfil no Drive"></select><button data-nuvem="conferir">Conferir versão do Drive</button>'+
    '<button data-nuvem="publicar">Usar perfil deste PC no Drive</button></div><p>Usar este PC cria uma versão com os dados locais. As versões anteriores continuam guardadas.</p></div>'+
    '<div class="perfil-resumo" aria-live="polite"></div><div class="perfil-botoes"><button class="perfil-exportar">Exportar meu perfil</button>'+
    '<label>Conferir perfil de outro PC<input type="file" accept=".json,application/json"></label></div>'+
    '<input class="perfil-caminho" readonly hidden aria-label="Caminho do perfil exportado">'+
    '<p class="perfil-mensagem" aria-live="polite"></p><div class="perfil-previa"></div>'+
    '<footer hidden><label>Quando houver diferenças<select><option value="manter">Manter o que já existe neste PC</option><option value="substituir">Usar os valores do perfil importado</option></select></label>'+
    '<p>Uma cópia dos valores anteriores será salva neste PC antes de restaurar. A restauração não executa as rotinas importadas.</p><button class="perfil-aplicar">Restaurar este perfil</button></footer>';
  document.body.appendChild(p);
  const apiP=()=>window.pywebview.api,msg=p.querySelector('.perfil-mensagem'),prev=p.querySelector('.perfil-previa');
  const rodape=p.querySelector('footer'),aplicar=p.querySelector('.perfil-aplicar');
  let texto='',conferencia='',geracao=0,origemDrive='',conferenciaNuvem='',ocupado=false,autenticado=false,cadastrar=false;
  const dizer=t=>{msg.textContent=t;};
  const resumo=async()=>{const r=await apiP().perfil_resumo();p.querySelector('.perfil-resumo').textContent=r.arquivos+' arquivos de preferências, memórias, regras, contratos e rotinas disponíveis. Credenciais, sessões e dados do disco ficam neste PC.';};
  window.perfilPortatilAbrir=async()=>{p.hidden=!p.hidden;if(!p.hidden)try{await resumo();await acessoStatus();await nuvem('status');}catch(e){dizer(e.message||String(e));}};
  p.querySelector('header button').onclick=()=>{p.hidden=true;};
  p.querySelector('.perfil-exportar').onclick=async e=>{
    e.target.disabled=true;dizer('Preparando o perfil…');
    try{const r=await apiP().perfil_exportar();const campo=p.querySelector('.perfil-caminho');campo.hidden=false;campo.value=r.caminho;campo.onclick=()=>campo.select();dizer('Perfil exportado: '+r.arquivos+' arquivos. Copie o arquivo indicado para o outro computador.');}
    catch(erro){dizer(erro.message||String(erro));}finally{e.target.disabled=false;}
  };
  p.querySelector('[type=file]').onchange=async e=>{
    const arquivo=e.target.files[0],minha=++geracao;rodape.hidden=true;prev.replaceChildren();texto='';conferencia='';
    origemDrive='';if(!arquivo)return;
    if(arquivo.size>40*1024*1024){dizer('Arquivo de perfil grande demais.');return;}
    dizer('Conferindo conteúdo e diferenças…');
    try{
      const conteudo=await arquivo.text();const r=await apiP().perfil_conferir(conteudo);if(minha!==geracao)return;
      mostrarPrevia(conteudo,r);
    }catch(erro){if(minha===geracao)dizer(erro.message||String(erro));}
  };
  aplicar.onclick=async()=>{
    if(!texto||!conferencia)return;aplicar.disabled=true;
    try{
      const politica=p.querySelector('footer select').value;
      const r=origemDrive ? await apiP().perfil_nuvem('restaurar',origemDrive,conferencia,politica) : await apiP().perfil_restaurar(texto,conferencia,politica);
      dizer(`Perfil restaurado: ${r.restaurados} arquivos. ${r.conflitos_mantidos} diferenças mantidas neste PC. Cópia anterior: ${r.backup}. Reinicie o KaniCode pelo botão do topo para aplicar as preferências.`);
      conferencia='';rodape.hidden=true;await resumo();
    }catch(erro){dizer(erro.message||String(erro));aplicar.disabled=false;}
  };
  function mostrarPrevia(conteudo,r){
    texto=conteudo;conferencia=r.conferencia;prev.replaceChildren();
    dizer(`${r.perfil.nome}: ${r.resumo.novo} novos, ${r.resumo.conflito} com diferenças, ${r.resumo.igual} iguais.`);
    for(const aviso of r.avisos){const a=document.createElement('p');a.textContent=aviso;prev.appendChild(a);}
    for(const item of r.arquivos){const d=document.createElement('details'),s=document.createElement('summary');s.textContent=item.arquivo+' · '+item.estado;d.appendChild(s);
      if(item.diff){const code=document.createElement('pre');code.textContent=item.diff;d.appendChild(code);}prev.appendChild(d);}
    rodape.hidden=false;aplicar.disabled=false;
  }
  async function nuvem(acao){
    if(ocupado)return;ocupado=true;
    const status=p.querySelector('.perfil-nuvem-status'),seletor=p.querySelector('.perfil-nuvem-versoes');
    const botoes=[...p.querySelectorAll('[data-nuvem]')];botoes.forEach(b=>b.disabled=true);
    try{
      if(acao==='login'){
        let d=await apiP().drive_status();
        if(!d.configurado && d.reutilizavel)d=await apiP().drive_usar_calendar();
        if(!d.configurado){status.textContent='Importe a configuração OAuth Desktop do Google Drive para entrar. A ajuda está em Configurações → Conexões → Google Drive.';return;}
        const r=await apiP().drive_conectar();status.textContent=r.mensagem||'Conclua o login no navegador e clique em Ativar sincronização.';return;
      }
      if(acao==='oauth'){await apiP().drive_importar();status.textContent='Configuração importada. Clique em Entrar com Google.';return;}
      if(acao==='conferir'){
        const minha=++geracao;conferencia='';rodape.hidden=true;
        const r=await apiP().perfil_nuvem('conferir',seletor.value);
        const previa=await apiP().perfil_conferir(r.texto);if(minha!==geracao)return;
        origemDrive=r.id;mostrarPrevia(r.texto,previa);return;
      }
      const r=await apiP().perfil_nuvem(acao,'',acao==='publicar'?conferenciaNuvem:'');
      pintarAcesso(r);status.textContent=(r.conta?r.conta+' · ':'')+r.mensagem;
      if(r.conferencia)conferenciaNuvem=r.conferencia;
      if(r.versoes){const anterior=seletor.value;seletor.replaceChildren();
        for(const v of r.versoes){const o=document.createElement('option');o.value=v.id;o.textContent='Perfil · '+v.revisao.slice(0,12);seletor.appendChild(o);}
        if([...seletor.options].some(o=>o.value===anterior))seletor.value=anterior;
      }
      p.querySelector('[data-nuvem="pausar"]').hidden=!r.ativo;
    }catch(e){status.textContent=e.message||String(e);}
    finally{ocupado=false;ajustarBotoes();}
  }
  p.querySelectorAll('[data-nuvem]').forEach(b=>b.onclick=()=>nuvem(b.dataset.nuvem));
  const formulario=p.querySelector('.perfil-acesso-form'),emailAcesso=p.querySelector('.perfil-acesso-email');
  const senhaAcesso=p.querySelector('.perfil-acesso-senha'),confirmarAcesso=p.querySelector('.perfil-acesso-confirmar');
  const statusAcesso=p.querySelector('.perfil-acesso-status'),sairAcesso=p.querySelector('.perfil-acesso-sair');
  function ajustarBotoes(){
    p.querySelectorAll('[data-nuvem]').forEach(b=>{b.disabled=ocupado||(!autenticado&&['ativar','sincronizar','conferir','publicar'].includes(b.dataset.nuvem));});
  }
  function pintarAcesso(r){
    if(!r||typeof r!=='object'||!('autenticado' in r))return;
    autenticado=!!r.autenticado;formulario.hidden=autenticado;sairAcesso.hidden=!autenticado;
    if(r.email&&!emailAcesso.matches(':focus'))emailAcesso.value=r.email;
    if(r.mensagem)statusAcesso.textContent=r.mensagem;
    else statusAcesso.textContent=autenticado?'Acesso lembrado neste PC.':'Entre no perfil ou cadastre seu acesso na primeira vez.';
    ajustarBotoes();
  }
  async function acessoStatus(abrir=false){
    try{const r=await apiP().perfil_acesso('status');pintarAcesso(r);
      if(abrir&&r?.requer_acesso){p.hidden=false;await resumo();}
    }catch(e){statusAcesso.textContent=e.message||String(e);}
  }
  p.querySelector('.perfil-acesso-modo').onclick=()=>{
    cadastrar=!cadastrar;confirmarAcesso.hidden=!cadastrar;confirmarAcesso.querySelector('input').required=cadastrar;
    senhaAcesso.autocomplete=cadastrar?'new-password':'current-password';senhaAcesso.minLength=cadastrar?12:1;
    p.querySelector('.perfil-acesso-dica').hidden=!cadastrar;
    formulario.querySelector('[type="submit"]').textContent=cadastrar?'Salvar meu acesso':'Entrar no meu perfil';
    p.querySelector('.perfil-acesso-modo').textContent=cadastrar?'Já tenho acesso':'Primeira vez? Cadastrar acesso';
  };
  formulario.onsubmit=async e=>{
    e.preventDefault();if(ocupado)return;ocupado=true;ajustarBotoes();
    formulario.querySelectorAll('button').forEach(b=>b.disabled=true);statusAcesso.textContent='Conferindo seu acesso…';
    try{
      const r=await apiP().perfil_acesso(cadastrar?'cadastrar':'entrar',{email:emailAcesso.value,senha:senhaAcesso.value,
        confirmacao:confirmarAcesso.querySelector('input').value,lembrar:p.querySelector('.perfil-acesso-lembrar input').checked});
      pintarAcesso(r);
    }catch(erro){statusAcesso.textContent=erro.message||String(erro);}
    finally{senhaAcesso.value='';confirmarAcesso.querySelector('input').value='';ocupado=false;
      formulario.querySelectorAll('button').forEach(b=>b.disabled=false);ajustarBotoes();}
    if(autenticado)await nuvem('ativar');
  };
  sairAcesso.onclick=async()=>{
    if(ocupado)return;ocupado=true;sairAcesso.disabled=true;
    try{pintarAcesso(await apiP().perfil_acesso('sair'));texto='';conferencia='';origemDrive='';conferenciaNuvem='';
      rodape.hidden=true;prev.replaceChildren();p.querySelector('.perfil-nuvem-versoes').replaceChildren();
    }catch(e){statusAcesso.textContent=e.message||String(e);}
    finally{ocupado=false;sairAcesso.disabled=false;ajustarBotoes();}
  };
  const iniciar=async()=>{await acessoStatus(true);if(autenticado)await nuvem('sincronizar');
    setInterval(()=>{if(autenticado&&!conferencia)nuvem('sincronizar');},60000);};
  if(window.pywebview?.api)iniciar();else window.addEventListener('pywebviewready',iniciar,{once:true});
})();
