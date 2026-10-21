package com.pandalab.kanicode;

/** Rosto 8-bit da bolinha: a mesma grade 16 × 16 de rosto.py (PC). "#" traço, "w" brilho, "p" bochecha. */
final class Rosto {
    static final String V = "................";
    static final String[] AB = {"....w#....w#....", "....##....##....", "....##....##...."};
    static final String[] FE = {V, V, "....##....##...."};
    static final String[] GR = {"...w##...w##....", "...###...###....", "...###...###...."};
    static final String[] FZ = {".....#....#.....", "....#.#..#.#....", V};
    static final String[] CI = {"....w#....w#....", "....##....##....", V};
    static final String[] SORRISO = {"......#..#......", ".......##.......", V};
    static final String[] RETA = {V, "......####......", V};
    static final String[] LADO = {V, "........###.....", V};
    static final String[] O = {".......##.......", "......#..#......", ".......##......."};
    static final String[] OP = {V, ".......##.......", V};
    static final String[] TIL = {V, "......#.#.#.....", ".......#.#......"};
    static final String[] RISO = {"....#......#....", ".....#....#.....", "......####......"};

    static boolean pisca(double t, double cada) { return (t % cada) < 0.16; }

    static String desloca(String l, int d) {
        if (d > 0) return ".".repeat(d) + l.substring(0, 16 - d);
        if (d < 0) return l.substring(-d) + ".".repeat(-d);
        return l;
    }

    static char[][] quadro(String e, double t) {
        char[][] g = new char[16][16];
        for (char[] l : g) java.util.Arrays.fill(l, '.');
        switch (e) {
            case "trabalhando": {
                int d = new int[]{-1, 0, 1, 0}[(int) (t * 1.6) % 4];
                por(g, pisca(t, 3.1) ? FE : AB, 5, d);
                por(g, RETA, 10, 0);
                break;
            }
            case "pensando":
                por(g, CI, 4, 1);
                por(g, LADO, 10, 0);
                break;
            case "ouvindo":
                por(g, pisca(t, 5.0) ? FE : GR, 5, 0);
                por(g, ((int) (t * 2.5)) % 2 == 1 ? O : OP, 10, 0);
                break;
            case "falando": {
                por(g, pisca(t, 3.6) ? FE : AB, 5, 0);
                String[][] b = {O, OP, SORRISO, OP};
                por(g, b[(int) (t * 7) % 4], 10, 0);
                g[9][3] = g[9][12] = 'p';
                break;
            }
            case "pergunta":
                por(g, new String[]{"...###.........."}, 3, 0);
                por(g, new String[]{"..........###..."}, 4, 0);
                por(g, AB, 5, 0);
                por(g, TIL, 10, 0);
                break;
            case "feliz":
                por(g, FZ, 5, 0);
                por(g, RISO, 9, 0);
                g[8][3] = g[8][12] = 'p';
                break;
            default:
                por(g, pisca(t, 4.2) ? FE : AB, 5, 0);
                por(g, SORRISO, 10, 0);
                g[9][3] = g[9][12] = 'p';
        }
        return g;
    }

    static void por(char[][] g, String[] linhas, int y0, int d) {
        for (int i = 0; i < linhas.length; i++) {
            String l = desloca(linhas[i], d);
            for (int x = 0; x < 16; x++) if (l.charAt(x) != '.') g[y0 + i][x] = l.charAt(x);
        }
    }
}
