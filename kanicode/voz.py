"""Voz do KaniCode: "Ei Kani" acorda, a fala vira texto e vai para a conversa. Tudo local, nada sai do PC.

Microfone (16 kHz) → openWakeWord com o modelo próprio modelos/hey_kani.onnx (~1–2% de um núcleo) → bipe → grava até
uma pausa (Silero VAD) → Parakeet pt-BR (o mesmo da Ata/legendas do KANIVETE, int8, no processador) → ao_texto(texto).
O reconhecimento só carrega no primeiro "Ei Kani" e sai da memória depois de LIBERAR_S parado.
Bancada do modelo (gerar vozes, treinar, medir disparos falsos): D:/kanivete_testes/hey_kani.
"""
import os, queue, re, threading, time, wave
from collections import deque

import numpy as np

PASTA = os.path.dirname(os.path.abspath(__file__))
MODELO = os.path.join(PASTA, "modelos", "hey_kani.onnx")
SR, BLOCO = 16000, 1280              # 80 ms: o passo do openWakeWord
LIMIAR = 0.5
SILENCIO_S, ESPERA_S, MAX_S = 0.9, 5.0, 30.0
LIBERAR_S = 600
# 2ª checagem: no disparo, o Parakeet relê os últimos 2,5 s; sem algo como "Kani" é alarme falso (vídeo falando, música)
CONFERIR = re.compile(r"[kcq][aâáeê]+n|hani|kenn|conn|kahn|ikan", re.I)
TIRAR = re.compile(r"^\W*(?:(?:e|ei|hey|hei|ê|rei|oi)\W+)?(?:kani|kane|cani|kanye|kenny|connie|conny|câni)\b\W*", re.I)


def _app():
    """pasta do KANIVETE (modelos de fala já baixados por ele)"""
    real = os.path.realpath(PASTA)
    return os.path.join(os.path.dirname(os.path.dirname(real)), "CANIVETE DO PAILER")


def _asr_pasta():
    return os.path.join(_app(), "modelos_ia", "asr")


def disponivel():
    """o que falta para ligar a voz (lista vazia = pronto)"""
    falta = []
    if not os.path.isfile(MODELO):
        falta.append("modelo do Ei Kani")
    p = os.path.join(_asr_pasta(), "pt")
    if not os.path.isfile(os.path.join(p, "encoder-model.int8.onnx")):
        falta.append("reconhecimento de fala em português (baixe pelas Legendas do KANIVETE)")
    return falta


class _Vad:
    """Silero VAD em pedaços de 512 amostras (com os 64 de contexto, como o original)."""

    def __init__(self):
        import onnxruntime as ort
        op = ort.SessionOptions()
        op.intra_op_num_threads = op.inter_op_num_threads = 1
        self.s = ort.InferenceSession(os.path.join(_asr_pasta(), "silero_vad.onnx"), op, providers=["CPUExecutionProvider"])
        self.zerar()

    def zerar(self):
        self.estado = np.zeros((2, 1, 128), np.float32)
        self.ctx = np.zeros(64, np.float32)

    def fala(self, x16):
        """probabilidade de fala no bloco de 1280 (máximo dos pedaços de 512)"""
        x = x16.astype(np.float32) / 32768
        p = 0.0
        for i in range(0, len(x) - 511, 512):
            pedaco = np.concatenate([self.ctx, x[i:i + 512]])[None]
            out, self.estado = self.s.run(None, {"input": pedaco, "state": self.estado, "sr": np.array(SR, np.int64)})
            self.ctx = x[i + 448:i + 512]
            p = max(p, float(out[0, 0]))
        return p


class Voz:
    def __init__(self, ao_acordar=None, ao_texto=None, ao_estado=None):
        self.ao_acordar, self.ao_texto, self.ao_estado = ao_acordar, ao_texto, ao_estado
        self._fila = queue.Queue(maxsize=200)
        self._ligada = False
        self._th = None
        self._asr = None
        self._asr_uso = 0
        self.ultimo = {}

    # ── ligar/desligar ──
    def ligar(self):
        if self._ligada:
            return True
        falta = disponivel()
        if falta:
            raise RuntimeError("Falta: " + "; ".join(falta))
        self._ligada = True
        self._th = threading.Thread(target=self._rodar, daemon=True, name="kc-voz")
        self._th.start()
        threading.Thread(target=self._carregar_asr, daemon=True).start()   # o 1º pedido não espera o carregamento
        return True

    def desligar(self):
        self._ligada = False

    @property
    def ligada(self):
        return self._ligada

    def _estado(self, e):
        if self.ao_estado:
            try:
                self.ao_estado(e)
            except Exception:
                pass

    # ── laço do microfone ──
    def _rodar(self):
        import sounddevice as sd
        from openwakeword.model import Model
        ww = Model(wakeword_models=[MODELO], inference_framework="onnx",
                   melspec_model_path=os.path.join(PASTA, "modelos", "melspectrogram.onnx"),
                   embedding_model_path=os.path.join(PASTA, "modelos", "embedding_model.onnx"))
        vad = _Vad()
        recente = deque(maxlen=int(2.5 * SR / BLOCO))

        def cb(dados, _n, _t, _s):
            try:
                self._fila.put_nowait(dados[:, 0].copy())
            except queue.Full:
                pass

        try:
            with sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=BLOCO, callback=cb):
                self._estado("escutando")
                while self._ligada:
                    try:
                        x = self._fila.get(timeout=0.5)
                    except queue.Empty:
                        self._talvez_liberar()
                        continue
                    recente.append(x)
                    sc = float(ww.predict(x)[os.path.splitext(os.path.basename(MODELO))[0]])
                    if sc >= LIMIAR:
                        ouvido = self._transcrever(np.concatenate(recente).astype(np.float32) / 32768)
                        self.ultimo = {"nota": round(sc, 3), "quando": time.time(), "ouvido": ouvido,
                                       "ok": bool(CONFERIR.search(ouvido.replace(" ", "")))}
                        recente.clear()
                        if self.ultimo["ok"]:
                            self._pedido(vad)
                        ww.reset()
                        self._esvaziar()
        except Exception as e:
            self._estado("erro:" + str(e))
        finally:
            self._ligada = False
            self._estado("desligada")

    def _esvaziar(self):
        while not self._fila.empty():
            self._fila.get_nowait()

    def _pedido(self, vad):
        """depois do Ei Kani: grava até a pausa e transcreve"""
        self._bipe(True)
        self._estado("ouvindo")
        if self.ao_acordar:
            try:
                self.ao_acordar()
            except Exception:
                pass
        vad.zerar()
        blocos, falou, quieto, t0 = [], False, 0.0, time.time()
        while self._ligada:
            try:
                x = self._fila.get(timeout=0.5)
            except queue.Empty:
                continue
            blocos.append(x)
            if vad.fala(x) > 0.5:
                falou, quieto = True, 0.0
            else:
                quieto += BLOCO / SR
            dur = time.time() - t0
            if (falou and quieto >= SILENCIO_S) or (not falou and dur >= ESPERA_S) or dur >= MAX_S:
                break
        self._bipe(False)
        if not falou:
            self._estado("escutando")
            return
        self._estado("transcrevendo")
        audio = np.concatenate(blocos).astype(np.float32) / 32768
        try:
            texto = self._transcrever(audio)
        except Exception as e:
            self._estado("erro:" + str(e))
            return
        texto = TIRAR.sub("", texto).strip()   # "Ei Kani, abre…" → "abre…"
        texto = texto[:1].upper() + texto[1:]
        self._estado("escutando")
        if texto and self.ao_texto:
            self.ao_texto(texto)

    # ── reconhecimento ──
    def _carregar_asr(self):
        if self._asr is None:
            import onnx_asr
            self._asr = onnx_asr.load_model("nemo-conformer-tdt", os.path.join(_asr_pasta(), "pt"), quantization="int8")
        self._asr_uso = time.time()
        return self._asr

    def _transcrever(self, audio):
        t = self._carregar_asr().recognize(audio, sample_rate=SR)
        self._asr_uso = time.time()
        return (t or "").strip()

    def _talvez_liberar(self):
        if self._asr is not None and time.time() - self._asr_uso > LIBERAR_S:
            self._asr = None

    # ── bipe (dois tons curtos: subindo = ouvindo, descendo = terminou) ──
    def _bipe(self, subindo):
        try:
            import winsound
            f = os.path.join(os.environ.get("TEMP", PASTA), f"kc_bipe_{int(subindo)}.wav")
            if not os.path.isfile(f):
                t = np.arange(int(SR * 0.07)) / SR
                tons = (880, 1320) if subindo else (1320, 880)
                s = np.concatenate([np.sin(2 * np.pi * h * t) * np.hanning(len(t)) for h in tons]) * 0.25
                with wave.open(f, "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                    w.writeframes((s * 32767).astype(np.int16).tobytes())
            winsound.PlaySound(f, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass
