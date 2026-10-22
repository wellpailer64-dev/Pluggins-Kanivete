"""Rádio do celular: a voz da resposta vem do PC num fluxo de áudio contínuo (GET /voz/radio, MP3), como uma rádio.

Página parada não fala (o celular congela o JS com o app minimizado ou a tela apagada), mas áudio de rádio o celular deixa
tocando. Então quem lê a resposta é o PC: movel.publicar() passa cada evento por evento(); as frases viram voz (Kokoro, o
mesmo da janela) e entram no fluxo de quem está ouvindo; sem fala, o fluxo leva silêncio (MP3 32 kb/s ≈ 14 MB por hora).
Só lê a resposta de um pedido feito PELO CELULAR (marcar("movel") no /api/enviar); pedido do PC não sai no celular.
"""
import os, queue, re, subprocess, threading, time

SR = 24000                 # o Kokoro devolve 24 kHz
PASSO = 0.1                # s de áudio por escrita (ritmo de tempo real: a fala entra sem esperar o silêncio já mandado)
_ouvintes = []             # uma fila de PCM por celular ouvindo
_trava = threading.Lock()
_frases = queue.Queue()
_e = {"ler": False, "buf": "", "codigo": False}
_app = None
_tts = None


def iniciar(app, trava_tts):
    global _app, _tts
    _app, _tts = app, trava_tts
    threading.Thread(target=_falador, daemon=True).start()


def marcar(de):
    """o próximo pedido veio do celular (lê a resposta) ou não"""
    _e["ler"] = bool(de) and de != "pc"   # o celular manda um id próprio por aparelho


def evento(ev):
    if not _ouvintes:
        return
    t = ev.get("t")
    if t in ("inicio", "texto_novo"):
        _e["buf"], _e["codigo"] = "", False
    elif t == "texto" and _e["ler"]:
        _pedaco(ev.get("d") or "")
    elif t in ("permissao", "pergunta") and _e["ler"]:
        _frases.put("Preciso da sua decisão na tela.")
    elif t in ("fim", "saiu"):
        if _e["ler"] and not _e["codigo"]:
            _frases.put(_e["buf"])
        _e["buf"], _e["ler"] = "", False


def _pedaco(d):
    """frase a frase enquanto a resposta chega; blocos de código não são lidos (igual ao movel.js)"""
    _e["buf"] += d
    while True:
        b = _e["buf"]
        if _e["codigo"]:
            i = b.find("```")
            if i < 0:
                return
            _e["buf"], _e["codigo"] = b[i + 3:], False
            continue
        i = b.find("```")
        m = re.match(r"^([\s\S]*?[.!?…:;])(\s+)|^([^\n]*)\n", b)
        if not m and i < 0 and len(b) > 70:    # frase comprida: começa a falar na vírgula (a 1ª voz sai antes)
            m = re.match(r"^([\s\S]{30,}?,)(\s+)", b)
        if i >= 0 and (not m or i < len(m.group(0))):
            _frases.put(b[:i])
            _e["buf"], _e["codigo"] = b[i + 3:], True
            continue
        if not m:
            return
        _frases.put(m.group(1) or m.group(3) or "")
        _e["buf"] = b[len(m.group(0)):]


def _falador():
    import numpy as np
    from fala import limpar, sintetizar
    while True:
        frase = limpar(_frases.get() or "")
        if len(re.sub(r"\W", "", frase)) < 2 or not _ouvintes:
            continue
        try:
            with _tts:
                a, sr = sintetizar(_app._fala_obj().carregar(), frase)
            a = np.asarray(a, np.float32)
            if sr != SR:
                a = np.interp(np.arange(0, len(a), sr / SR), np.arange(len(a)), a).astype(np.float32)
            pcm = (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes() + bytes(int(SR * 0.25) * 2)   # respiro entre frases
            with _trava:
                for q in _ouvintes:
                    q.put(pcm)
        except Exception:
            pass


def _ffmpeg():
    from voz import _app as pasta_app
    ff = os.path.join(pasta_app(), "modelos_ia", "ffmpeg.exe")
    return ff if os.path.isfile(ff) else "ffmpeg"


def servir(saida):
    """manda o fluxo MP3 para um celular até ele desligar (chamado pelo handler HTTP, já com os cabeçalhos enviados)"""
    q = queue.Queue()
    p = subprocess.Popen([_ffmpeg(), "-loglevel", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "pipe:0",
                          "-b:a", "32k", "-f", "mp3", "-flush_packets", "1", "pipe:1"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    vivo = [True]

    def copiar():
        try:
            while vivo[0]:
                b = p.stdout.read1(4096)
                if not b:
                    break
                saida.write(b)
                saida.flush()
        except Exception:
            pass
        vivo[0] = False

    threading.Thread(target=copiar, daemon=True).start()
    with _trava:
        _ouvintes.append(q)
    n = int(SR * PASSO) * 2
    fala, t0, k = b"", time.monotonic(), 0
    try:
        while vivo[0]:
            while len(fala) < n:
                try:
                    fala += q.get_nowait()
                except queue.Empty:
                    break
            pedaco, fala = (fala[:n], fala[n:]) if fala else (bytes(n), b"")
            pedaco += bytes(n - len(pedaco))
            p.stdin.write(pedaco)
            p.stdin.flush()
            k += 1
            espera = t0 + k * PASSO - time.monotonic()
            if espera > 0:
                time.sleep(espera)
    except Exception:
        pass
    finally:
        vivo[0] = False
        with _trava:
            if q in _ouvintes:
                _ouvintes.remove(q)
        try:
            p.kill()
        except Exception:
            pass
