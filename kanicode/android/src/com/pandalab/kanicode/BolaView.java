package com.pandalab.kanicode;

import android.content.Context;
import android.graphics.Canvas;
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
    String voz = "", tarefa = "";
    float nivel = 0;
    final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG), px = new Paint();
    final long t0 = System.currentTimeMillis();

    BolaView(Context c) { super(c); }

    String expressao() {
        if (!voz.isEmpty()) return voz;            // ouvindo | pensando | falando
        if (!tarefa.isEmpty()) return tarefa;      // trabalhando | pergunta
        return "neutro";
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
        c.restore();
    }
}
