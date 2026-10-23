/* Perfil portátil: exportar e conferir antes de restaurar; nenhuma conexão em nuvem nesta etapa. */
(() => {
  const bt=document.createElement('button');bt.id='perfil-portatil-bt';bt.className='bt';bt.textContent='◉ Meu perfil';
  document.getElementById('config-perfil').appendChild(bt);
  const p=document.createElement('section');p.className='perfil-portatil';p.hidden=true;p.setAttribute('aria-label','Meu perfil KaniCode');
  p.innerHTML='<header><strong>Meu perfil KaniCode</strong><button aria-label="Fechar perfil">×</button></header>'+
    '<p>Etapa 1 · Perfil portátil. Login e sincronização entre computadores serão a próxima etapa.</p>'+
    '<div class="perfil-resumo" aria-live="polite"></div><div class="perfil-botoes"><button class="perfil-exportar">Exportar meu perfil</button>'+
    '<label>Conferir perfil de outro PC<input type="file" accept=".json,application/json"></label></div>'+
    '<input class="perfil-caminho" readonly hidden aria-label="Caminho do perfil exportado">'+
    '<p class="perfil-mensagem" aria-live="polite"></p><div class="perfil-previa"></div>'+
    '<footer hidden><label>Quando houver diferenças<select><option value="manter">Manter o que já existe neste PC</option><option value="substituir">Usar os valores do perfil importado</option></select></label>'+
    '<p>Uma cópia dos valores anteriores será salva neste PC antes de restaurar. A restauração não executa as rotinas importadas.</p><button class="perfil-aplicar">Restaurar este perfil</button></footer>';
  document.body.appendChild(p);
  const apiP=()=>window.pywebview.api,msg=p.querySelector('.perfil-mensagem'),prev=p.querySelector('.perfil-previa');
  const rodape=p.querySelector('footer'),aplicar=p.querySelector('.perfil-aplicar');
  let texto='',conferencia='',geracao=0;
  const dizer=t=>{msg.textContent=t;};
  const resumo=async()=>{const r=await apiP().perfil_resumo();p.querySelector('.perfil-resumo').textContent=r.arquivos+' arquivos de preferências, memórias, regras, contratos e rotinas disponíveis. Credenciais, sessões e dados do disco ficam neste PC.';};
  bt.onclick=async()=>{p.hidden=!p.hidden;if(!p.hidden)try{await resumo();}catch(e){dizer(e.message||String(e));}};
  p.querySelector('header button').onclick=()=>{p.hidden=true;};
  p.querySelector('.perfil-exportar').onclick=async e=>{
    e.target.disabled=true;dizer('Preparando o perfil…');
    try{const r=await apiP().perfil_exportar();const campo=p.querySelector('.perfil-caminho');campo.hidden=false;campo.value=r.caminho;campo.onclick=()=>campo.select();dizer('Perfil exportado: '+r.arquivos+' arquivos. Copie o arquivo indicado para o outro computador.');}
    catch(erro){dizer(erro.message||String(erro));}finally{e.target.disabled=false;}
  };
  p.querySelector('[type=file]').onchange=async e=>{
    const arquivo=e.target.files[0],minha=++geracao;rodape.hidden=true;prev.replaceChildren();texto='';conferencia='';
    if(!arquivo)return;
    if(arquivo.size>40*1024*1024){dizer('Arquivo de perfil grande demais.');return;}
    dizer('Conferindo conteúdo e diferenças…');
    try{
      const conteudo=await arquivo.text();const r=await apiP().perfil_conferir(conteudo);if(minha!==geracao)return;
      texto=conteudo;conferencia=r.conferencia;
      dizer(`${r.perfil.nome}: ${r.resumo.novo} novos, ${r.resumo.conflito} com diferenças, ${r.resumo.igual} iguais.`);
      for(const aviso of r.avisos){const a=document.createElement('p');a.textContent=aviso;prev.appendChild(a);}
      for(const item of r.arquivos){const d=document.createElement('details'),s=document.createElement('summary');s.textContent=item.arquivo+' · '+item.estado;d.appendChild(s);
        if(item.diff){const code=document.createElement('pre');code.textContent=item.diff;d.appendChild(code);}prev.appendChild(d);}
      rodape.hidden=false;aplicar.disabled=false;
    }catch(erro){if(minha===geracao)dizer(erro.message||String(erro));}
  };
  aplicar.onclick=async()=>{
    if(!texto||!conferencia)return;aplicar.disabled=true;
    try{
      const r=await apiP().perfil_restaurar(texto,conferencia,p.querySelector('select').value);
      dizer(`Perfil restaurado: ${r.restaurados} arquivos. ${r.conflitos_mantidos} diferenças mantidas neste PC. Cópia anterior: ${r.backup}. Reinicie o KaniCode pelo botão do topo para aplicar as preferências.`);
      conferencia='';rodape.hidden=true;await resumo();
    }catch(erro){dizer(erro.message||String(erro));aplicar.disabled=false;}
  };
})();
