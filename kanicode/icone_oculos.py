"""Ícone do KaniCode: o rosto 8-bit da bolinha (rosto.py) de óculos escuros pixelados ("deal with it") e sorriso de canto.

Gera icone.png (KANIVETE/atalho), icone-192/512.png (celular, movel.py), icone-mascara-512.png (Android recorta em
círculo/gota: o rosto fica na zona segura) e refaz DADOS/kanicode.ico (atalhos.py).
Rodar: py -3.13 icone_oculos.py [--previa saida.png]
"""
import os, sys

from PIL import Image, ImageDraw, ImageFilter

PASTA = os.path.dirname(os.path.abspath(__file__))
LIMA_CLARO, LIMA_ESC, FUNDO = (0xD8, 0xFF, 0x7A), (0x7F, 0xB5, 0x1A), (0x0E, 0x11, 0x10)

GRADE = ["................",
         "................",
         "................",
         "................",
         "................",
         "..############..",
         "..#ww###.#ww##..",
         "..##ww##.##ww#..",
         "...####...###...",
         "................",
         "..........#.....",
         ".....######.....",
         "................",
         "................",
         "................",
         "................"]
CORES = {"#": FUNDO, "w": (255, 255, 255)}


def desenhar(lado, mascara=False):
    """mascara=True: quadrado cheio (fundo escuro) com a bola dentro da zona segura de 80%"""
    k = 4   # desenha grande e reduz: borda do círculo lisa, pixels do rosto nítidos
    L = lado * k
    im = Image.new("RGBA", (L, L), FUNDO + (255,) if mascara else (0, 0, 0, 0))
    m = L * (0.14 if mascara else 0.03)
    d = L - 2 * m
    # bola com luz em cima à esquerda (como a bolinha: centro claro, borda escura)
    bola = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    g = ImageDraw.Draw(bola)
    passos = 60
    for i in range(passos):
        t = i / (passos - 1)
        r = d / 2 * (1 - t * 0.98)
        cx, cy = m + d / 2 - d * 0.10 * t, m + d / 2 - d * 0.12 * t
        cor = tuple(int(LIMA_ESC[c] + (LIMA_CLARO[c] - LIMA_ESC[c]) * t ** 0.8) for c in range(3))
        g.ellipse((cx - r, cy - r, cx + r, cy + r), fill=cor + (255,))
    alfa = Image.new("L", (L, L), 0)
    ImageDraw.Draw(alfa).ellipse((m, m, m + d, m + d), fill=255)
    bola.putalpha(alfa)
    if not mascara:   # sombra suave embaixo
        sombra = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        ImageDraw.Draw(sombra).ellipse((m, m + L * 0.02, m + d, m + d + L * 0.02), fill=(0, 0, 0, 90))
        im = Image.alpha_composite(im, sombra.filter(ImageFilter.GaussianBlur(L * 0.012)))
    im = Image.alpha_composite(im, bola)
    # rosto: grade 16 × 16 centrada na bola
    p = d * 0.82 / 16
    x0, y0 = m + (d - 16 * p) / 2, m + (d - 16 * p) / 2 + p * 0.3
    g = ImageDraw.Draw(im)
    for y, linha in enumerate(GRADE):
        for x, c in enumerate(linha):
            if c in CORES:
                g.rectangle((round(x0 + x * p), round(y0 + y * p), round(x0 + (x + 1) * p) - 1, round(y0 + (y + 1) * p) - 1), fill=CORES[c])
    return im.resize((lado, lado), Image.LANCZOS)


def gerar():
    desenhar(256).save(os.path.join(PASTA, "icone.png"))
    desenhar(192).save(os.path.join(PASTA, "icone-192.png"))
    desenhar(512).save(os.path.join(PASTA, "icone-512.png"))
    desenhar(512, mascara=True).save(os.path.join(PASTA, "icone-mascara-512.png"))
    sys.path.insert(0, PASTA)
    import kanicode as kc
    ico = os.path.join(kc.DADOS, "kanicode.ico")
    os.makedirs(kc.DADOS, exist_ok=True)
    desenhar(256).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    if "--previa" in sys.argv:
        saida = sys.argv[sys.argv.index("--previa") + 1]
        folha = Image.new("RGBA", (1000, 300), (30, 34, 32, 255))
        x = 10
        for lado, masc in ((256, False), (256, True), (128, False), (64, False), (32, False)):
            folha.alpha_composite(desenhar(lado, masc), (x, 20))
            x += lado + 20
        folha.save(saida)
        print(saida)
    else:
        gerar()
        print("ok")
