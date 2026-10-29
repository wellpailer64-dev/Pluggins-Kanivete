// KaniADB: tela ao vivo + controle. Fala só com o servidor local do plugin (127.0.0.1:47615).
const tela = document.getElementById('tela');
const palco = document.getElementById('palco');
const mudo = document.getElementById('mudo');
const sinal = document.getElementById('sinal');
const aparelho = document.getElementById('aparelho');
const fps = document.getElementById('fps');
const recado = document.getElementById('recado');
const campo = document.getElementById('campo');

let inicio = null;
let tentativas = 0;
let disponivel = false;
let fluxo = false;
let reconexao = null;
let modoVideo = 'ao vivo';
let controleDireto = false;
let envioPonteiro = Promise.resolve();
let ultimoMovimento = 0;

function disponibilidade(pronto) {
  disponivel = pronto;
  document.querySelectorAll('button, #campo').forEach(b => { b.disabled = !pronto; });
  if (!pronto) {
    clearTimeout(reconexao);
    reconexao = null;
    fluxo = false;
    inicio = null;
    if (tela.hasAttribute('src')) tela.removeAttribute('src');
    tela.classList.remove('viva');
    mudo.hidden = false;
    mudo.textContent = 'aguardando celular conectado e autorizado';
    fps.textContent = 'sem transmissão';
  }
}

function mostrarRecado(texto) {
  recado.textContent = texto;
  recado.classList.toggle('erro', !!texto);
}

async function pedir(rota, corpo) {
  const r = await fetch(rota, {
    method: corpo ? 'POST' : 'GET',
    headers: corpo ? { 'Content-Type': 'application/json' } : {},
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  const dados = await r.json().catch(() => ({}));
  if (!r.ok || (dados.erro && rota !== '/estado')) throw new Error(dados.erro || ('falhou: ' + r.status));
  return dados;
}

async function atualizarEstado() {
  try {
    const e = await pedir('/estado');
    const a = e.aparelho || {};
    disponibilidade(!!e.pronto);
    if (e.video) {
      controleDireto = e.video.motor === 'scrcpy';
      modoVideo = e.video.erro ? 'vídeo interrompido' : !e.video.quadros ? 'iniciando vídeo' :
        e.video.idade_ms > 2000 ? 'imagem estática' : 'vídeo contínuo';
    }
    if (e.pronto) {
      const tam = a.tela || {};
      sinal.className = 'sinal ok';
      aparelho.textContent = [a.modelo || a.serial, a.android ? 'Android ' + a.android : '',
        tam.largura ? tam.largura + 'x' + tam.altura : ''].filter(Boolean).join(' · ');
      if (!tela.classList.contains('viva')) mostrarRecado('Tela do celular carregando…');
      if (!fluxo && !reconexao) ligarFluxo();
      if (e.video && e.video.erro) mostrarRecado(e.video.erro);
    } else {
      sinal.className = 'sinal ruim';
      aparelho.textContent = e.adb ? 'nenhum celular' : 'adb não encontrado';
      mostrarRecado(e.erro || 'Celular não encontrado.');
    }
  } catch (erro) {
    disponibilidade(false);
    sinal.className = 'sinal ruim';
    mostrarRecado('Servidor do KaniADB fora do ar: ' + erro.message);
  }
}

function ligarFluxo() {
  reconexao = null;
  if (!disponivel || fluxo) return;
  fluxo = true;
  fps.textContent = 'conectando';
  mudo.hidden = false;
  mudo.textContent = 'carregando o primeiro quadro…';
  tela.src = '/fluxo?t=' + Date.now();
}

function confirmarQuadro() {
  if (!disponivel || !fluxo || !tela.naturalWidth) return;
  if (!tela.classList.contains('viva') && recado.textContent === 'Tela do celular carregando…') mostrarRecado('');
  tentativas = 0;
  tela.classList.add('viva');
  mudo.hidden = true;
  fps.textContent = modoVideo;
}
tela.addEventListener('load', confirmarQuadro);
setInterval(confirmarQuadro, 500);
tela.addEventListener('error', () => {
  fluxo = false;
  if (!disponivel) return;
  tela.classList.remove('viva');
  mudo.hidden = false;
  mudo.textContent = 'tela parou; tentando de novo…';
  fps.textContent = 'reconectando';
  clearTimeout(reconexao);
  reconexao = setTimeout(ligarFluxo, Math.min(8000, 800 * ++tentativas));
});

// coordenada do ponteiro em fração da tela do celular (0..1)
function fracao(valor, eixo) {
  const r = tela.getBoundingClientRect();
  const f = eixo === 'x' ? (valor - r.left) / r.width : (valor - r.top) / r.height;
  return Math.max(0, Math.min(0.999, f));
}

function enviarPonteiro(tipo, ev) {
  const dados = { tipo, x: fracao(ev.clientX, 'x'), y: fracao(ev.clientY, 'y') };
  envioPonteiro = envioPonteiro.then(() => pedir('/ponteiro', dados)).catch(erro => mostrarRecado(erro.message));
}

palco.addEventListener('pointerdown', (ev) => {
  if (!tela.classList.contains('viva')) return;
  const r = tela.getBoundingClientRect();
  if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) return;
  if (ev.button !== 0) return;
  inicio = { x: ev.clientX, y: ev.clientY, t: Date.now(), direto: controleDireto };
  palco.setPointerCapture(ev.pointerId);
  if (inicio.direto) enviarPonteiro('down', ev);
  ev.preventDefault();
});

palco.addEventListener('pointermove', ev => {
  if (!inicio || !inicio.direto || Date.now() - ultimoMovimento < 16) return;
  ultimoMovimento = Date.now();
  enviarPonteiro('move', ev);
});

palco.addEventListener('pointercancel', ev => {
  if (inicio && inicio.direto) enviarPonteiro('cancel', ev);
  inicio = null;
});

palco.addEventListener('pointerup', async (ev) => {
  if (!inicio || !tela.classList.contains('viva')) return;
  if (inicio.direto) {
    enviarPonteiro('up', ev);
    inicio = null;
    return;
  }
  const dx = ev.clientX - inicio.x;
  const dy = ev.clientY - inicio.y;
  const distancia = Math.hypot(dx, dy);
  try {
    if (distancia < 12) {
      await pedir('/tocar', { x: fracao(ev.clientX, 'x'), y: fracao(ev.clientY, 'y') });
    } else {
      const ms = Math.max(120, Math.min(1500, Date.now() - inicio.t));
      await pedir('/deslizar', {
        de: [fracao(inicio.x, 'x'), fracao(inicio.y, 'y')],
        ate: [fracao(ev.clientX, 'x'), fracao(ev.clientY, 'y')],
        ms,
      });
    }
    mostrarRecado('');
  } catch (erro) {
    mostrarRecado(erro.message);
  } finally {
    inicio = null;
  }
});

document.querySelectorAll('[data-tecla]').forEach((b) => {
  b.addEventListener('click', async () => {
    try {
      await pedir('/tecla', { tecla: b.dataset.tecla });
      mostrarRecado('');
    } catch (erro) {
      mostrarRecado(erro.message);
    }
  });
});

document.getElementById('digitar').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const texto = campo.value;
  if (!texto.trim()) return;
  try {
    const r = await pedir('/texto', { texto });
    if (r.aviso) mostrarRecado(r.aviso);
    campo.value = '';
  } catch (erro) {
    mostrarRecado(erro.message);
  }
});

disponibilidade(false);
atualizarEstado();
setInterval(atualizarEstado, 6000);
