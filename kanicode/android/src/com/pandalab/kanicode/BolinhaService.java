package com.pandalab.kanicode;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.DisplayMetrics;
import android.view.GestureDetector;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.TextView;

/**
 * A bolinha por cima de qualquer app: arrasta; 1 toque abre o KaniCode; 2 toques começa a ouvir; arrastar até o ✕ fecha.
 * Anel verde pulsando = ouvindo; laranja batendo com a voz = falando. Serviço em primeiro plano (microfone + mídia) para o
 * Android não matar a conversa com o app minimizado.
 */
public class BolinhaService extends Service {
    static BolinhaService eu;
    WindowManager wm;
    FrameLayout bola;
    View anel;
    BolaView rosto;
    TextView xis;
    WindowManager.LayoutParams lp, lpx;
    Handler h = new Handler(Looper.getMainLooper());
    int tam;

    @Override
    public IBinder onBind(Intent i) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        eu = this;
        primeiroPlano();
        wm = (WindowManager) getSystemService(Context.WINDOW_SERVICE);
        float d = getResources().getDisplayMetrics().density;
        tam = (int) (68 * d);

        bola = new FrameLayout(this);
        rosto = new BolaView(this);
        bola.addView(rosto, new FrameLayout.LayoutParams(tam, tam));
        anel = rosto;

        SharedPreferences p = getSharedPreferences("bolinha", MODE_PRIVATE);
        lp = new WindowManager.LayoutParams(tam, tam, WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.x = p.getInt("x", 20);
        lp.y = p.getInt("y", 400);
        wm.addView(bola, lp);
        som(R.raw.swoosh); som(R.raw.hello);   // sons da KaniBall (ui/sons_bolinha, como no PC)

        // o ✕ de fechar (só aparece arrastando)
        xis = new TextView(this);
        xis.setText("✕");
        xis.setTextColor(Color.WHITE);
        xis.setTextSize(26);
        xis.setGravity(Gravity.CENTER);
        GradientDrawable gx = new GradientDrawable();
        gx.setShape(GradientDrawable.OVAL);
        gx.setColor(Color.parseColor("#CC222222"));
        gx.setStroke((int) (2 * d), Color.WHITE);
        xis.setBackground(gx);
        lpx = new WindowManager.LayoutParams(tam, tam, WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
                PixelFormat.TRANSLUCENT);
        lpx.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        lpx.y = (int) (60 * d);
        xis.setVisibility(View.GONE);
        wm.addView(xis, lpx);

        final GestureDetector gd = new GestureDetector(this, new GestureDetector.SimpleOnGestureListener() {
            @Override
            public boolean onSingleTapConfirmed(MotionEvent e) { abrir(); return true; }

            @Override
            public boolean onDoubleTap(MotionEvent e) { ouvir(); return true; }
        });
        final int toque = (int) (10 * d);
        bola.setOnTouchListener(new View.OnTouchListener() {
            int x0, y0; float rx, ry; boolean arrastando;

            @Override
            public boolean onTouch(View v, MotionEvent e) {
                gd.onTouchEvent(e);
                switch (e.getActionMasked()) {
                    case MotionEvent.ACTION_DOWN:
                        x0 = lp.x; y0 = lp.y; rx = e.getRawX(); ry = e.getRawY(); arrastando = false;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        float dx = e.getRawX() - rx, dy = e.getRawY() - ry;
                        if (!arrastando && Math.hypot(dx, dy) > toque) { arrastando = true; xis.setVisibility(View.VISIBLE); }
                        if (arrastando) {
                            lp.x = x0 + (int) dx; lp.y = y0 + (int) dy;
                            wm.updateViewLayout(bola, lp);
                            xis.setAlpha(perto() ? 1f : 0.6f);
                        }
                        return true;
                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        if (arrastando) {
                            xis.setVisibility(View.GONE);
                            if (perto()) { fechar(); return true; }
                            getSharedPreferences("bolinha", MODE_PRIVATE).edit().putInt("x", lp.x).putInt("y", lp.y).apply();
                        }
                        return true;
                }
                return false;
            }
        });
        h.post(animar);
    }

    boolean perto() {
        DisplayMetrics dm = getResources().getDisplayMetrics();
        float cx = lp.x + tam / 2f, cy = lp.y + tam / 2f;
        float xx = dm.widthPixels / 2f, xy = dm.heightPixels - lpx.y - tam / 2f;
        return Math.hypot(cx - xx, cy - xy) < tam * 1.2;
    }

    void abrir() {
        Intent i = new Intent(this, MainActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        startActivity(i);
    }

    void ouvir() {
        if (MainActivity.eu == null) { abrir(); return; }
        estado("ouvindo");
        MainActivity.eu.ouvir();
    }

    void fechar() {   // a despedida toca inteira antes de sumir
        som(R.raw.swoosh); som(R.raw.bye);
        bola.animate().alpha(0f).scaleX(0.3f).scaleY(0.3f).setDuration(600).start();
        h.postDelayed(this::stopSelf, 1300);
    }

    /** toca um som curto da KaniBall; o MediaPlayer se solta sozinho no fim */
    void som(int id) {
        try {
            android.media.MediaPlayer mp = android.media.MediaPlayer.create(this, id);
            if (mp == null) return;
            mp.setOnCompletionListener(android.media.MediaPlayer::release);
            mp.start();
        } catch (Exception ignored) { }
    }

    /** chamado pela página (KCApp.estado): ouvindo | pensando | falando | parado */
    void estado(String e) { rosto.voz = e == null || e.equals("parado") ? "" : e; rosto.mexeu = System.currentTimeMillis(); }

    /** chamado pela página (KCApp.tarefa): trabalhando | pergunta | parado */
    void tarefa(String e) { rosto.tarefa = e == null || e.equals("parado") ? "" : e; rosto.mexeu = System.currentTimeMillis(); }

    void nivel(float n) { rosto.nivel = Math.max(0, Math.min(1, n)); }

    /** chamado pela página (KCApp.quem): claude | codex | kani | pickle (o selo no canto) */
    void quem(String q) { rosto.quem = q == null ? "claude" : q; rosto.mexeu = System.currentTimeMillis(); }

    /** chamado pela página (KCApp.atividade): lendo | digitando | procurando | pensando | "" (rosto enquanto trabalha) */
    void atividade(String a) { rosto.atividade = a == null ? "" : a; rosto.mexeu = System.currentTimeMillis(); }

    /** chamado pela página (KCApp.humor): feliz | erro por alguns segundos (fim da tarefa) */
    void humor(String hm) { if ("erro".equals(hm)) som(R.raw.ops); rosto.humor = hm == null ? "" : hm; rosto.humorAte = System.currentTimeMillis() + 3000; rosto.mexeu = rosto.humorAte; }

    final Runnable animar = new Runnable() {
        @Override
        public void run() {
            rosto.nivel *= 0.85f;
            rosto.invalidate();
            boolean rapido = !rosto.voz.isEmpty() || !"neutro".equals(rosto.expressao());
            h.postDelayed(this, rapido ? 40 : 120);
        }
    };

    void primeiroPlano() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel("bolinha", "Bolinha do KaniCode", NotificationManager.IMPORTANCE_MIN));
        PendingIntent abre = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        Notification n = new Notification.Builder(this, "bolinha")
                .setSmallIcon(R.drawable.kani)
                .setContentTitle("KaniCode")
                .setContentText("A bolinha está ativa")
                .setContentIntent(abre)
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= 30)
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE | ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        else startForeground(1, n);
    }

    @Override
    public void onDestroy() {
        h.removeCallbacks(animar);
        try { wm.removeView(bola); } catch (Exception ignored) { }
        try { wm.removeView(xis); } catch (Exception ignored) { }
        eu = null;
        super.onDestroy();
    }
}
