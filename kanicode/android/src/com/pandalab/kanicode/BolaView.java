package com.pandalab.kanicode;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.BitmapShader;
import android.graphics.Canvas;
import android.graphics.Matrix;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.view.View;

/** A bolinha desenhada como a do PC (bolinha.py): bola verde-limão com luz, rosto 8-bit, anel ouvindo, arco trabalhando. */
class BolaView extends View {
    static final int LIMA_CLARO = Color.rgb(0xD8, 0xFF, 0x7A), LIMA_ESC = Color.rgb(0x7F, 0xB5, 0x1A),
            FUNDO = Color.rgb(0x0E, 0x11, 0x10), BOCHECHA = Color.rgb(0xFF, 0x8F, 0xA3), ALERTA = Color.rgb(0xFF, 0x5A, 0x5F);
    String voz = "", tarefa = "", quem = "claude", atividade = "", humor = "";
    long humorAte = 0, mexeu = System.currentTimeMillis();
    float nivel = 0;
    Bitmap kani, pickle;
    final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG), px = new Paint();
    final long t0 = System.currentTimeMillis();

    BolaView(Context c) { super(c); }

    /** a mesma escolha da bolinha do PC (bolinha.py expressao) */
    String expressao() {
        if (!humor.isEmpty() && System.currentTimeMillis() < humorAte) return humor;   // feliz | erro por 3 s
        if (!voz.isEmpty()) return voz;            // ouvindo | pensando | falando
        if ("pergunta".equals(tarefa)) return tarefa;
        if ("trabalhando".equals(tarefa)) return atividade.isEmpty() ? tarefa : atividade;   // lendo | digitando | procurando | pensando
        if (System.currentTimeMillis() - mexeu > 600_000) return "dormindo";
        return "neutro";
    }

    /** quem responde, no canto de baixo à direita (bolinha.py _selo) */
    void selo(Canvas c, float m, float L) {
        float r = L * 0.36f, x = m + L - r * 0.92f, y = m + L - r * 0.92f;
        p.setColor(FUNDO);
        c.drawOval(new RectF(x - 2, y - 2, x + r + 2, y + r + 2), p);
        if ("kani".equals(quem) || "pickle".equals(quem)) {   // logo redondo (Kani ou Big Pickle)
            if (kani == null) kani = BitmapFactory.decodeResource(getResources(), R.drawable.kani);
            if (pickle == null) pickle = BitmapFactory.decodeResource(getResources(), R.drawable.pickle);
            Bitmap logo = "pickle".equals(quem) ? pickle : kani;
            if (logo != null) {
                BitmapShader sh = new BitmapShader(logo, Shader.TileMode.CLAMP, Shader.TileMode.CLAMP);
                Matrix mt = new Matrix();
                float s = r / Math.min(logo.getWidth(), logo.getHeight());
                mt.setScale(s, s);
                mt.postTranslate(x, y);
                sh.setLocalMatrix(mt);
                p.setColor(Color.WHITE);
                p.setShader(sh);
                c.drawOval(new RectF(x, y, x + r, y + r), p);
                p.setShader(null);
            }
            return;
        }
        p.setColor(Color.rgb(0xF5, 0xF0, 0xE6));
        c.drawOval(new RectF(x, y, x + r, y + r), p);
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeCap(Paint.Cap.ROUND);
        if ("codex".equals(quem)) {   // o desenho de ui/codex.svg
            p.setColor(Color.rgb(0x15, 0x20, 0x1B));
            p.setStrokeWidth(Math.max(1.2f, r * 2.5f / 32));
            float[][] ls = {{8, 10, 14, 16}, {14, 16, 8, 22}, {18, 22, 25, 22}};
            for (float[] l : ls) c.drawLine(x + r * l[0] / 32, y + r * l[1] / 32, x + r * l[2] / 32, y + r * l[3] / 32, p);
        } else {   // asterisco de raios desiguais, como o logo do Claude
            p.setColor(Color.rgb(0xD9, 0x77, 0x57));
            p.setStrokeWidth(Math.max(1.2f, r * 0.075f));
            float cx = x + r / 2, cy = y + r / 2;
            for (int k = 0; k < 12; k++) {
                double a = k * Math.PI / 6 + 0.2, cc = r * (k % 2 == 1 ? 0.40 : 0.31);
                c.drawLine((float) (cx + Math.cos(a) * r * 0.07), (float) (cy + Math.sin(a) * r * 0.07),
                        (float) (cx + Math.cos(a) * cc), (float) (cy + Math.sin(a) * cc), p);
            }
        }
        p.setStyle(Paint.Style.FILL);
    }

    @Override
    protected void onDraw(Canvas c) {
        float W = getWidth(), m = W * 0.08f, L = W - 2 * m;
        double t = (System.currentTimeMillis() - t0) / 1000.0;
        float esc = "falando".equals(voz) ? 1f + 0.08f * nivel : 1f;
        c.save();
        c.scale(esc, esc, W / 2, W / 2);
        // sombra
        p.setShader(null);
        for (int k = (int) m; k > 0; k -= 2) {
            p.setColor(Color.argb((int) (10 + 30 * (1 - k / m)), 0, 0, 0));
            c.drawOval(new RectF(m - k * 0.5f, m - k * 0.5f + m * 0.5f, m + L + k * 0.5f, m + L + k * 0.5f + m * 0.5f), p);
        }
        // bola com luz no alto à esquerda
        p.setColor(Color.WHITE);   // o shader herda a transparência da cor (a sombra deixava a bola apagada)
        p.setShader(new RadialGradient(m + L * 0.32f, m + L * 0.28f, L * 0.85f, LIMA_CLARO, LIMA_ESC, Shader.TileMode.CLAMP));
        c.drawOval(new RectF(m, m, m + L, m + L), p);
        p.setShader(null);
        if ("trabalhando".equals(tarefa) && voz.isEmpty()) {   // arco que gira
            p.setStyle(Paint.Style.STROKE);
            p.setStrokeWidth(Math.max(3, L * 0.06f));
            p.setStrokeCap(Paint.Cap.ROUND);
            p.setColor(Color.argb(230, 0x0E, 0x11, 0x10));
            float d = L * 0.07f;
            c.drawArc(new RectF(m + d, m + d, m + L - d, m + L - d), (float) ((t * 0.9 % 1) * 360), 90, false, p);
            p.setStyle(Paint.Style.FILL);
        }
        // rosto 8-bit
        int cel = Math.max(2, (int) (L * 0.8f / 16));
        float x0 = (int) (m + L / 2 - 8 * cel), y0 = (int) (m + L / 2 - 8 * cel + cel * 0.5f);
        char[][] g = Rosto.quadro(expressao(), t);
        for (int y = 0; y < 16; y++)
            for (int x = 0; x < 16; x++) {
                char ch = g[y][x];
                if (ch == '.') continue;
                px.setColor(ch == 'w' ? Color.WHITE : ch == 'p' ? BOCHECHA : ch == 'r' ? ALERTA : FUNDO);
                c.drawRect(x0 + x * cel, y0 + y * cel, x0 + (x + 1) * cel, y0 + (y + 1) * cel, px);
            }
        if ("ouvindo".equals(voz)) {   // anel que pulsa por fora
            double k = 0.5 + 0.5 * Math.sin(t * 2 * Math.PI);
            p.setStyle(Paint.Style.STROKE);
            p.setStrokeWidth((float) Math.max(3, L * (0.05 + 0.04 * k)));
            p.setColor(Color.argb((int) (120 + 110 * k), 0x0E, 0x11, 0x10));
            c.drawOval(new RectF(m + L * 0.04f, m + L * 0.04f, m + L * 0.96f, m + L * 0.96f), p);
            p.setStyle(Paint.Style.FILL);
        }
        if ("pergunta".equals(tarefa)) {   // pontinho de alerta
            float r = L * 0.22f;
            p.setColor(FUNDO);
            c.drawOval(new RectF(m + L - r * 1.05f, m - r * 0.05f, m + L - r * 1.05f + r + 2, m - r * 0.05f + r + 2), p);
            p.setColor(ALERTA);
            c.drawOval(new RectF(m + L - r * 0.95f, m + r * 0.05f, m + L - r * 0.95f + r - 2, m + r * 0.05f + r - 2), p);
        }
        selo(c, m, L);
        c.restore();
    }
}
