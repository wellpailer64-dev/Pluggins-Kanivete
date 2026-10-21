"""Rosto 8-bit da bolinha do KaniCode: grade de 16 × 16 "pixels grandes", uma expressão por situação.

Sem .NET aqui (a bolinha desenha; a folha de prévia usa o PIL): `quadro(expressao, t)` devolve as 16 linhas da grade em
texto — "#" = traço escuro, "w" = brilho do olho, "p" = bochecha, "r" = alerta. Animação pelo relógio (t em segundos):
piscar, olhos que procuram enquanto trabalha, boca que mexe ouvindo, "z" dormindo.
Prévia: py -3.13 rosto.py [saida.png]
"""

VAZIO = "." * 16

# olhos (3 linhas, a partir da linha 5) e bocas (3 linhas, a partir da linha 10); cada um em 16 colunas
OLHOS = {
    "abertos": ["....w#....w#....",
                "....##....##....",
                "....##....##...."],
    "fechados": [VAZIO,
                 VAZIO,
                 "....##....##...."],
    "grandes": ["...w##...w##....",
                "...###...###....",
                "...###...###...."],
    "felizes": [".....#....#.....",
                "....#.#..#.#....",
                VAZIO],
    "x": ["....#.#..#.#....",
          ".....#....#.....",
          "....#.#..#.#...."],
    "cima": ["....w#....w#....",
             "....##....##....",
             VAZIO],
}
BOCAS = {
    "sorriso": ["......#..#......",
                ".......##.......",
                VAZIO],
    "reta": [VAZIO,
             "......####......",
             VAZIO],
    "lado": [VAZIO,
             "........###.....",
             VAZIO],
    "o": [".......##.......",
          "......#..#......",
          ".......##......."],
    "o_peq": [VAZIO,
              ".......##.......",
              VAZIO],
    "riso": ["....#......#....",
             ".....#....#.....",
             "......####......"],
    "triste": [VAZIO,
               "......####......",
               ".....#....#....."],
    "til": [VAZIO,
            "......#.#.#.....",
            ".......#.#......"],
}

EXPRESSOES = ("neutro", "trabalhando", "pensando", "ouvindo", "falando", "pergunta", "feliz", "erro", "dormindo",
              "lendo", "digitando", "procurando")


def _desloca(linha, d):
    """move a linha d colunas (olhos que procuram)"""
    if d > 0:
        return "." * d + linha[:-d]
    if d < 0:
        return linha[-d:] + "." * (-d)
    return linha


def _pisca(t, cada=4.2, dura=0.16):
    return (t % cada) < dura


def quadro(expressao, t=0.0):
    g = [list(VAZIO) for _ in range(16)]

    def por(linhas, y0, d=0):
        for i, l in enumerate(linhas):
            for x, c in enumerate(_desloca(l, d)):
                if c != ".":
                    g[y0 + i][x] = c

    e = expressao if expressao in EXPRESSOES else "neutro"
    if e == "neutro":
        por(OLHOS["fechados" if _pisca(t) else "abertos"], 5)
        por(BOCAS["sorriso"], 10)
        g[9][3] = g[9][12] = "p"
    elif e == "trabalhando":   # concentrado: olhos vão de um lado ao outro, boca reta
        d = (-1, 0, 1, 0)[int(t * 1.6) % 4]
        por(OLHOS["fechados" if _pisca(t, 3.1) else "abertos"], 5, d)
        por(BOCAS["reta"], 10)
    elif e == "pensando":      # entendendo a fala / esperando: olha para cima, boca de lado
        por(OLHOS["cima"], 4, 1)
        por(BOCAS["lado"], 10)
    elif e == "ouvindo":       # olhos grandes, boca abre e fecha devagar
        por(OLHOS["fechados" if _pisca(t, 5.0) else "grandes"], 5)
        por(BOCAS["o" if int(t * 2.5) % 2 else "o_peq"], 10)
    elif e == "falando":       # respondendo em voz alta: boca mexe rápido
        por(OLHOS["fechados" if _pisca(t, 3.6) else "abertos"], 5)
        por(BOCAS[("o", "o_peq", "sorriso", "o_peq")[int(t * 7) % 4]], 10)
        g[9][3] = g[9][12] = "p"
    elif e == "pergunta":      # uma sobrancelha levantada
        por(["...###.........."], 3)
        por(["..........###..."], 4)
        por(OLHOS["abertos"], 5)
        por(BOCAS["til"], 10)
    elif e == "feliz":
        por(OLHOS["felizes"], 5)
        por(BOCAS["riso"], 9)
        g[8][3] = g[8][12] = "p"
    elif e == "erro":
        por(OLHOS["x"], 5)
        por(BOCAS["triste"], 10)
    elif e == "lendo":         # lendo arquivo: olhos baixos que correm a linha, livro aberto, página que vira
        d = (-1, 0, 1, 1)[int(t * 2.2) % 4]
        por(["....##....##....", "....##....##...."], 6, d)
        por(["..############..",
             "..#wwwwwwwwww#..",
             "..#wwwwwwwwww#..",
             "..############.."], 11)
        lin = int(t * 2.2) % 4 < 2
        por(["...#.##.##.#...." if lin else "....##.#.##.#..."], 12)
        if int(t * 0.7) % 3 == 0:     # página virando
            por(["........#......."], 10)
        g[11][7] = g[11][8] = "#"
    elif e == "digitando":     # editando/rodando: olhos no teclado, mãozinhas batendo alternadas
        por(["....##....##....", "....##....##...."], 6)
        por(BOCAS["o_peq"], 9)
        sobe = int(t * 7) % 2
        por(["..##............"], 12 if sobe else 13)
        por(["...........##..."], 13 if sobe else 12)
        por(["..############.."], 14)
        if int(t * 7) % 4 == 0:
            por([".....w..w..w...."], 14)
    elif e == "procurando":    # procurando: lupa (com o olho grande dentro) que passa de um lado ao outro
        d = (-4, -2, 0, 0, -2, -4)[int(t * 1.8) % 6]
        por(["....w#..........", "....##..........", "....##.........."], 5)
        por(BOCAS["o_peq"], 10)
        por(["........####....",
             ".......#wwww#...",
             ".......#w##w#...",
             ".......#w##w#...",
             ".......#wwww#...",
             "........####....",
             "............#...",
             ".............#.."], 3, d)
    elif e == "dormindo":
        por(OLHOS["fechados"], 5)
        por(BOCAS["o_peq"], 10)
        if int(t * 0.8) % 3 < 2:        # "z" que sobe e some
            por(["..........####..", "............#...", "...........#....", "..........####.."], 2 - int(t * 0.8) % 3)
    return ["".join(l) for l in g]


def folha(caminho, lado=12, quadros=4):
    """prévia: uma linha por expressão, alguns quadros da animação, sobre o verde da bolinha"""
    from PIL import Image, ImageDraw
    cores = {"#": (14, 17, 16), "w": (255, 255, 255), "p": (255, 143, 163), "r": (255, 90, 95)}
    passo = 16 * lado + 24
    im = Image.new("RGB", (passo * quadros + 160, passo * len(EXPRESSOES)), (30, 34, 32))
    d = ImageDraw.Draw(im)
    for j, e in enumerate(EXPRESSOES):
        d.text((8, j * passo + passo // 2 - 6), e, fill=(220, 230, 220))
        for k in range(quadros):
            t = (0.0, 0.7, 1.3, 2.1)[k] if e != "neutro" else (0.0, 0.05, 1.0, 2.0)[k]
            x0, y0 = 150 + k * passo, j * passo + 12
            d.ellipse((x0 - 6, y0 - 6, x0 + 16 * lado + 6, y0 + 16 * lado + 6), fill=(182, 242, 58))
            for y, l in enumerate(quadro(e, t)):
                for x, c in enumerate(l):
                    if c in cores:
                        d.rectangle((x0 + x * lado, y0 + y * lado, x0 + (x + 1) * lado - 1, y0 + (y + 1) * lado - 1), fill=cores[c])
    im.save(caminho)
    return caminho


if __name__ == "__main__":
    import sys
    print(folha(sys.argv[1] if len(sys.argv) > 1 else "D:/kanivete_testes/scripts/rosto_folha.png"))
