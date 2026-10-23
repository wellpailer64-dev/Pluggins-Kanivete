// Teste opcional e separado da conversa principal.
(() => {
  const menu = document.getElementById('ferramentas-codigo');
  if (!menu) return;
  const abrir = document.createElement('button');
  abrir.className = 'bt';
  abrir.textContent = 'OpenCode · teste Big Pickle';
  menu.appendChild(abrir);
  const painel = document.createElement('dialog');
  painel.className = 'oc-mvp';
  painel.setAttribute('aria-label', 'Teste OpenCode Big Pickle');
  painel.innerHTML = '<h2>Big Pickle · experimental</h2><p>Uma pergunta por teste, pelo cliente oficial OpenCode. O texto será enviado pela internet e poderá ser usado para melhorar o modelo. Use texto sem dados confidenciais.</p><p>Este teste é só de conversa. Não recebe os arquivos nem o histórico do seu projeto.</p><p class="oc-estado" role="status"></p><label>Pergunta<textarea maxlength="4000" rows="4" placeholder="Por exemplo: explique o que é uma função em Python."></textarea></label><div class="oc-acoes"><button type="button" class="oc-enviar">Testar</button><button type="button" class="oc-fechar">Fechar</button></div><pre class="oc-resposta" aria-live="polite"></pre>';
  document.body.appendChild(painel);
  const estado = painel.querySelector('.oc-estado');
  const texto = painel.querySelector('textarea');
  const enviar = painel.querySelector('.oc-enviar');
  const resposta = painel.querySelector('.oc-resposta');
  painel.querySelector('.oc-fechar').onclick = () => painel.close();
  let pronto = false;
  abrir.onclick = async () => {
    menu.hidden = true;
    painel.showModal();
    enviar.disabled = true;
    try {
      const r = await window.pywebview.api.opencode_info();
      pronto = r.disponivel;
      estado.textContent = r.mensagem;
    } catch (_) {
      pronto = false;
      estado.textContent = 'Reabra o KaniCode para carregar a integração OpenCode.';
    }
    enviar.disabled = !pronto;
    texto.focus();
  };
  enviar.onclick = async () => {
    if (!pronto || !texto.value.trim()) return;
    enviar.disabled = true;
    texto.disabled = true;
    resposta.textContent = 'Consultando Big Pickle… prazo de até 60 segundos.';
    try {
      const r = await window.pywebview.api.opencode_testar(texto.value);
      resposta.textContent = r.texto;
      estado.textContent = r.ok ? 'Resposta recebida · tokens informados: ' + r.tokens : 'Teste não concluído';
    } catch (_) {
      resposta.textContent = 'Falha na comunicação com o KaniCode.';
    } finally {
      enviar.disabled = !pronto;
      texto.disabled = false;
    }
  };
})();
