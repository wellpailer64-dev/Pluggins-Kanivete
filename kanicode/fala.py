"""Fala do KaniCode: a resposta do Claude lida em voz alta enquanto ainda está sendo escrita (pedido feito por voz).

Kokoro 82M (Apache-2.0, kokoro-onnx), voz feminina pt-BR "pf_dora", só no processador: ~0,5 s por frase curta. Cada frase
é preparada enquanto a anterior toca, então só a 1ª espera. Bancada (Piper × Kokoro): D:/kanivete_testes/voz_rapida.
Modelos (~350 MB) baixados no 1º uso para D:/Kanivete/KaniCode/modelos_voz (fora do git).
Texto: tira markdown, blocos de código, caminhos e links (não se lê "D barra Kanivete…").
"""
import os, queue, re, subprocess, threading, urllib.request

import numpy as np

PASTA = os.path.dirname(os.path.abspath(__file__))
MODELOS = os.path.join(os.path.splitdrive(PASTA)[0] + os.sep, "Kanivete", "KaniCode", "modelos_voz")
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
ARQUIVOS = ("kokoro-v1.0.onnx", "voices-v1.0.bin")
VOZ, VELOCIDADE = "pf_dora", 1.08
TOM_SEMITONS = 2
PRONTIDAO = ("Recebi. Já vou analisar.", "Certo, estou verificando.", "Recebi seu pedido. Só um instante.")
CACHE_PRONTIDAO = os.path.join(MODELOS, f"prontidao-v2-{VOZ}-{VELOCIDADE}-tom{TOM_SEMITONS}.npz")
FIM_FRASE = re.compile(r"(.+?[.!?…:;])(\s+|$)|(.+?)\n", re.S)


def baixar(progresso=None):
    os.makedirs(MODELOS, exist_ok=True)
    for a in ARQUIVOS:
        dst = os.path.join(MODELOS, a)
        if not os.path.isfile(dst):
            urllib.request.urlretrieve(BASE + a, dst + ".parte")
            os.replace(dst + ".parte", dst)


def limpar(t):
    """texto da tela → texto para ouvir"""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)                 # [rótulo](link) → rótulo
    t = re.sub(r"https?://\S+", "o link", t)                         # antes do caminho ("s://" parecia D:/)
    t = re.sub(r"`[^`]*[/\\][^`]*`", "o arquivo", t)                # `caminho/arquivo` → o arquivo
    t = re.sub(r"[A-Za-z]:[/\\][^\s,;)]*", "o arquivo", t)          # D:/... solto
    t = re.sub(r"[`*_#>|]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = t.replace("→", ", ").replace("×", " contra ").replace("~", "cerca de ")
    return re.sub(r"\s+", " ", t).strip()


def ajustar_tom(audio, taxa):
    """Sobe poucos semitons e compensa o tempo; processa em memória, sem arquivos temporários."""
    a = np.asarray(audio, dtype=np.float32)
    if not TOM_SEMITONS or not a.size:
        return a, taxa
    from voz import _app
    ffmpeg = os.path.join(_app(), "modelos_ia", "ffmpeg.exe")
    if not os.path.isfile(ffmpeg):
        ffmpeg = "ffmpeg"
    fator = 2 ** (TOM_SEMITONS / 12)
    nova_taxa = round(taxa * fator)
    filtro = f"asetrate={nova_taxa},aresample={taxa},atempo={taxa / nova_taxa:.10f}"
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(taxa),
                            "-ac", "1", "-i", "pipe:0", "-af", filtro, "-f", "f32le", "-ar", str(taxa),
                            "-ac", "1", "pipe:1"], input=a.astype('<f4').tobytes(), capture_output=True,
                           timeout=10, creationflags=0x08000000)
        if r.returncode == 0 and r.stdout:
            saida = np.frombuffer(r.stdout, dtype='<f4').copy()
            if np.isfinite(saida).all():
                return saida, taxa
    except (OSError, subprocess.SubprocessError):
        pass  # se o processamento falhar, mantém a fala original em vez de ficar muda
    return a, taxa


def sintetizar(modelo, texto):
    return ajustar_tom(*modelo.create(texto, voice=VOZ, speed=VELOCIDADE, lang="pt-br"))


class Fala:
    def __init__(self, ao_estado=None):
        self.ao_estado = ao_estado
        self._k = None
        self._modelo_lock = threading.RLock()
        self._preparo_lock = threading.Lock()
        self._prontidas = None
        self._prontidao_indice = 0
        self._frases = queue.Queue()
        self._audios = queue.Queue(maxsize=3)
        self._buf = ""
        self._codigo = False
        self._ger = 0              # geração: parar() invalida o que já estava na fila
        self._pend = 0             # frases ainda não tocadas (inclusive a que está sendo preparada)
        self._acabou = False       # a resposta inteira já chegou (terminar())
        self._lock = threading.Lock()
        threading.Thread(target=self._sintetizar, daemon=True, name="kc-fala-s").start()
        threading.Thread(target=self._tocar, daemon=True, name="kc-fala-t").start()

    @property
    def falando(self):
        return not (self._frases.empty() and self._audios.empty()) or getattr(self, "_tocando", False)

    def carregar(self):
        with self._modelo_lock:
            if self._k is None:
                baixar()
                from kokoro_onnx import Kokoro
                self._k = Kokoro(os.path.join(MODELOS, ARQUIVOS[0]), os.path.join(MODELOS, ARQUIVOS[1]))
                self._k.create("Oi.", voice=VOZ, speed=VELOCIDADE, lang="pt-br")   # aquece (a 1ª chamada é lenta)
            return self._k

    def _carregar_prontidao(self):
        try:
            with np.load(CACHE_PRONTIDAO, allow_pickle=False) as dados:
                taxa = int(dados["taxa"])
                audios = [np.asarray(dados[f"audio_{i}"], dtype=np.float32) for i in range(len(PRONTIDAO))]
                if not 8000 <= taxa <= 96000 or any(a.ndim != 1 or not 0 < a.size <= taxa * 10 for a in audios):
                    return False
                self._prontidas = [(a, taxa) for a in audios]
                return True
        except (OSError, ValueError, KeyError):
            return False

    def preparar_prontidao(self):
        if not self._preparo_lock.acquire(blocking=False):
            return
        try:
            if self._carregar_prontidao():
                return
            audios = []
            for texto in PRONTIDAO:
                with self._modelo_lock:
                    a, taxa = sintetizar(self.carregar(), texto)
                audios.append(np.asarray(a, dtype=np.float32))
            os.makedirs(MODELOS, exist_ok=True)
            temporario = CACHE_PRONTIDAO + ".parte.npz"
            np.savez(temporario, taxa=taxa, **{f"audio_{i}": a for i, a in enumerate(audios)})
            os.replace(temporario, CACHE_PRONTIDAO)
            self._prontidas = [(a, taxa) for a in audios]
        except Exception:
            pass  # a falta da mensagem pronta nunca impede a resposta real
        finally:
            self._preparo_lock.release()

    def prontidao(self, ainda_valido):
        if self._prontidas is None and not self._carregar_prontidao():
            def preparar_e_confirmar():
                self.preparar_prontidao()
                if self._prontidas is None:
                    # Outra solicitação pode já estar preparando o mesmo cache.
                    with self._preparo_lock:
                        pass
                if self._prontidas is not None and ainda_valido():
                    self.prontidao(ainda_valido)
            threading.Thread(target=preparar_e_confirmar, daemon=True).start()
            return False
        if not ainda_valido():
            return False
        a, taxa = self._prontidas[self._prontidao_indice % len(self._prontidas)]
        self._prontidao_indice += 1
        self._pend += 1
        try:
            self._audios.put_nowait((self._ger, a, taxa, ainda_valido))
            return True
        except queue.Full:
            self._pend = max(0, self._pend - 1)
            return False

    def soltar(self):
        self.parar()
        self._k = None

    # ── entrada: pedaços de texto chegando (stream) ──
    def novo(self):
        self._buf, self._codigo, self._acabou = "", False, False

    def pedaco(self, d):
        self._buf += d
        while True:
            # bloco de código: não se lê; espera fechar
            if self._codigo:
                i = self._buf.find("```")
                if i < 0:
                    return
                self._buf, self._codigo = self._buf[i + 3:], False
                continue
            i = self._buf.find("```")
            m = FIM_FRASE.match(self._buf)
            if i >= 0 and (not m or i < m.end()):
                self._dizer(self._buf[:i])
                self._buf, self._codigo = self._buf[i + 3:], True
                continue
            if not m:
                return
            self._dizer(m.group(1) or m.group(3) or "")
            self._buf = self._buf[m.end():]

    def terminar(self):
        if not self._codigo:
            self._dizer(self._buf)
        self.novo()
        self._acabou = True
        if self._pend == 0:
            self._estado("fim")

    def dizer(self, texto):
        self.pedaco(texto + "\n")

    def _dizer(self, frase):
        f = limpar(frase)
        if len(re.sub(r"\W", "", f)) >= 2:
            self._pend += 1
            self._frases.put((self._ger, f))

    def parar(self):
        with self._lock:
            self._ger += 1
        self.novo()
        self._pend = 0
        for q in (self._frases, self._audios):
            while not q.empty():
                q.get_nowait()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    # ── trabalhadores: um prepara a próxima frase enquanto o outro toca a atual ──
    def _sintetizar(self):
        while True:
            ger, f = self._frases.get()
            if ger != self._ger:
                continue
            try:
                with self._modelo_lock:
                    a, sr = sintetizar(self.carregar(), f)
            except Exception:
                self._tocou(ger)
                continue
            if ger == self._ger:
                self._audios.put((ger, a, sr, None))

    def _tocar(self):
        import sounddevice as sd
        self._tocando = False
        while True:
            ger, a, sr, ainda_valido = self._audios.get()
            if ger != self._ger:
                continue
            if ainda_valido is not None and not ainda_valido():
                self._tocou(ger)
                continue
            self._tocando = True
            self._estado("falando")
            try:
                sd.play(np.asarray(a, np.float32), sr)
                sd.wait()
            except Exception:
                pass
            self._tocando = False
            self._tocou(ger)
            if self._frases.empty() and self._audios.empty():
                self._estado("")

    def _tocou(self, ger):
        """uma frase a menos; a última da resposta avisa "fim" (a conversa contínua começa a ouvir)"""
        if ger != self._ger:
            return
        self._pend = max(0, self._pend - 1)
        if self._pend == 0 and self._acabou:
            self._acabou = False
            self._estado("fim")

    def _estado(self, e):
        if self.ao_estado:
            try:
                self.ao_estado(e)
            except Exception:
                pass
