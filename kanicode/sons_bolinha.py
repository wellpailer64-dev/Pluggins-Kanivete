"""Vinhetas da bolinha: voz local com bitcrusher, preparada uma vez e tocada sem carregar TTS na animação."""
import os, threading, time, wave

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "sons_bolinha")
FRASES = {"entrada": "Uhuu!", "conclusao": "Iupi!", "saida": "Fui!",
          "risada": "He-he!", "surpresa": "Oh!", "pensando": "Hum!"}
_trava = threading.Lock()
_ultimo = 0.0


def oito_bits(audio, taxa):
    """Voz mais aguda, amostragem retida em 5,5 kHz e quantização de 8 bits; volume baixo e bordas sem estalos."""
    import numpy as np
    a = np.asarray(audio, dtype=np.float32)
    if a.ndim != 1 or not a.size or not np.isfinite(a).all() or taxa < 8000:
        raise ValueError("áudio mono válido e taxa de pelo menos 8 kHz são necessários")
    a = a - np.mean(a)
    pico = float(np.max(np.abs(a)))
    if pico < 1e-6:
        return np.zeros(round(taxa * 0.05), dtype=np.float32)
    ativos = np.flatnonzero(np.abs(a) > pico * 0.018)
    a = a[max(0, ativos[0] - round(taxa * 0.015)):min(a.size, ativos[-1] + round(taxa * 0.04))]
    a = np.interp(np.arange(0, a.size, 1.16), np.arange(a.size), a)
    a = a / max(1e-6, float(np.max(np.abs(a)))) * 0.45
    passo = taxa / 5500
    indices = np.minimum((np.floor(np.arange(a.size) / passo) * passo).astype(int), a.size - 1)
    a = 0.9 * a[indices] + 0.1 * a
    atraso = round(taxa * 0.045)
    eco = np.zeros(a.size + atraso * 2)
    eco[:a.size] += a
    eco[atraso:atraso + a.size] += a * 0.12
    eco[atraso * 2:atraso * 2 + a.size] += a * 0.06
    entrada, saida = min(round(taxa * 0.008), eco.size), min(round(taxa * 0.035), eco.size)
    eco[:entrada] *= np.linspace(0, 1, entrada)
    eco[-saida:] *= np.linspace(1, 0, saida)
    return (np.round(np.clip(eco, -0.55, 0.55) * 127) / 127).astype(np.float32)


def gerar(destino):
    """Usa os modelos já presentes; não baixa nada nem roda durante a abertura do app."""
    import numpy as np
    from kokoro_onnx import Kokoro
    from fala import MODELOS, ARQUIVOS, VOZ
    arquivos = [os.path.join(MODELOS, nome) for nome in ARQUIVOS]
    if not all(os.path.isfile(a) for a in arquivos):
        raise FileNotFoundError("os modelos locais da voz precisam estar disponíveis")
    os.makedirs(destino, exist_ok=True)
    modelo = Kokoro(*arquivos)
    for nome, frase in FRASES.items():
        audio, taxa = modelo.create(frase, voice=VOZ, speed=1.12, lang="pt-br")
        audio = oito_bits(audio, taxa)
        if audio.size > taxa * 1.8:
            raise ValueError(f"vinheta longa demais: {nome}")
        with wave.open(os.path.join(destino, nome + ".wav"), "wb") as arq:
            arq.setnchannels(1)
            arq.setsampwidth(2)   # PCM 16 para reprodução; o sinal já foi quantizado em 8 bits
            arq.setframerate(taxa)
            arq.writeframes((audio * 32767).astype("<i2").tobytes())
        print(f"{nome}: {frase} ({audio.size / taxa:.2f} s)", flush=True)


# sons da KaniBall gravados pelo Pailer (2026-10-21): ação → arquivos tocados juntos (o swoosh acompanha o voo)
SONS = {"entrada": ("Swoosh intro e outro.mp3", "Hello.mp3"), "saida": ("Swoosh intro e outro.mp3", "Bye.mp3"),
        "erro": ("Ops.mp3",), "entrada_chat": ("inter chat.wav",), "saida_chat": ("out chat.wav",)}
_abertos = []   # apelidos do MCI tocando agora


def _mci(cmd):
    import ctypes
    return ctypes.windll.winmm.mciSendStringW(cmd, None, 0, None)


def _soltar():
    for a in _abertos:
        _mci(f"close {a}")
    _abertos.clear()


def tocar(acao):
    """toca pelo MCI do Windows (lê MP3 e WAV, vários ao mesmo tempo); sem arquivo do Pailer, a vinheta gerada <acao>.wav"""
    global _ultimo
    nomes = [n for n in SONS.get(acao, ()) if os.path.isfile(os.path.join(PASTA, n))]
    if not nomes and acao in FRASES and os.path.isfile(os.path.join(PASTA, acao + ".wav")):
        nomes = [acao + ".wav"]
    if not nomes:
        return False
    with _trava:
        agora = time.monotonic()
        if agora - _ultimo < 0.8 and acao not in ("entrada_chat", "saida_chat"):
            return False
        _soltar()
        tocou = False
        for i, n in enumerate(nomes):
            apelido = f"kcbola{i}"
            # mpegvideo (DirectShow) abre MP3 e qualquer WAV; o waveaudio recusa WAV de 24 bits/float
            if _mci(f'open "{os.path.join(PASTA, n)}" type mpegvideo alias {apelido}') == 0:
                _abertos.append(apelido)
                tocou = _mci(f"play {apelido}") == 0 or tocou
        if tocou:
            _ultimo = agora
        return tocou


def parar():
    with _trava:
        _soltar()
