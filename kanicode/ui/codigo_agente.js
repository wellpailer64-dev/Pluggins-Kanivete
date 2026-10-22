// Revisão humana da cópia: o modelo não dispõe de ferramenta para aplicar na origem.
(() => {
  const menu = document.getElementById('ferramentas-menu');
  if (!menu) return;
  const abrir = document.createElement('button');
  abrir.className = 'bt';
  abrir.textContent = 'Revisar código isolado';
  menu.appendChild(abrir);
  const painel = document.createElement('dialog');
  painel.className = 'codigo-revisao';
  painel.setAttribute('aria-label', 'Revisão de código isolado');
  painel.innerHTML = '<h2>Código na cópia isolada</h2><p>Confira as alterações e os testes antes de aplicar nos arquivos originais. Uma pasta separada não é uma máquina virtual: testes executam código local.</p><p class="codigo-estado" role="status"></p><pre class="codigo-info"></pre><pre class="codigo-diff"></pre><div class="codigo-acoes"><button type="button" class="codigo-atualizar">Atualizar revisão</button><button type="button" class="codigo-aplicar" disabled>Aplicar arquivos revisados</button><button type="button" class="codigo-fechar">Fechar</button></div>';
  document.body.appendChild(painel);
  const estado = painel.querySelector('.codigo-estado');
  const info = painel.querySelector('.codigo-info');
  const diff = painel.querySelector('.codigo-diff');
  const aplicar = painel.querySelector('.codigo-aplicar');
  const atualizar = painel.querySelector('.codigo-atualizar');
  let revisao = null;
  let ocupado = false;
  async function carregar() {
    if (ocupado) return;
    ocupado = true;
    revisao = null;
    aplicar.disabled = true;
    atualizar.disabled = true;
    estado.textContent = 'Carregando revisão…';
    info.textContent = ''; diff.textContent = '';
    try {
      const r = await window.pywebview.api.codigo_revisar();
      if (!r.ok) { estado.textContent = r.mensagem; return; }
      revisao = r;
      estado.textContent = r.aplicada ? 'Esta sessão já foi aplicada.' : (r.arquivos.length ? 'Mudanças disponíveis somente na cópia.' : 'Nenhum arquivo alterado.');
      const teste = r.testes ? (r.testes.ok ? 'Testes passaram: ' : 'Testes falharam: ') + r.testes.arquivo + '\n' + r.testes.saida : 'Testes de comportamento não executados.';
      info.textContent = 'Agente: ' + r.agente + '\nCópia: ' + r.copia + '\nArquivos: ' + r.arquivos.join(', ') + '\nSintaxe: ' + (r.verificacao.ok ? 'sem erros detectados' : 'falhou') + '\n' + teste;
      diff.textContent = r.diff || 'Sem diff.';
      aplicar.disabled = !r.pode_aplicar;
    } catch (_) {
      estado.textContent = 'Não foi possível carregar. Reabra o KaniCode se acabou de receber a atualização.';
    } finally {
      ocupado = false;
      atualizar.disabled = false;
    }
  }
  abrir.onclick = () => { menu.hidden = true; painel.showModal(); carregar(); };
  // Big Pickle nativo (pickle_agente.py) terminou com mudanças na cópia: botão na conversa, depois da resposta
  const anterior = window.kcEv;
  let pronto = null;
  window.kcEv = ev => {
    if (ev.t === 'codigo_pronto') { pronto = ev; return; }
    const r = anterior(ev);
    if (ev.t === 'ajudante_resposta' && pronto) {   // o botão vem logo abaixo da resposta
      const n = (pronto.arquivos || []).length; pronto = null;
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'bt codigo-pronto';
      b.textContent = 'Revisar e aplicar (' + n + ' arquivo' + (n > 1 ? 's' : '') + ')';
      b.onclick = () => { painel.showModal(); carregar(); };
      conversa.appendChild(b);
      b.scrollIntoView({ block: 'nearest' });
    }
    return r;
  };
  atualizar.onclick = carregar;
  painel.querySelector('.codigo-fechar').onclick = () => painel.close();
  aplicar.onclick = async () => {
    if (!revisao || ocupado) return;
    ocupado = true; aplicar.disabled = true; atualizar.disabled = true;
    try {
      const r = await window.pywebview.api.codigo_aplicar(revisao.agente, revisao.revisao);
      estado.textContent = r.ok ? 'Aplicado na origem: ' + r.arquivos.join(', ') + '. Cópia inicial preservada em ' + r.backup : r.mensagem;
      revisao = null;
    } catch (_) { estado.textContent = 'A aplicação não foi confirmada. Atualize a revisão antes de continuar.'; }
    finally { ocupado = false; atualizar.disabled = false; }
  };
})();
