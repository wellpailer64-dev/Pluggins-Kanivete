package com.pandalab.kanicode;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.ContentValues;
import android.provider.MediaStore;
import android.webkit.ValueCallback;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/** A casca: a mesma página do KaniCode (Tailscale) num WebView que NÃO pausa em segundo plano, mais a bolinha. */
public class MainActivity extends Activity {
    static MainActivity eu;
    WebView web;
    boolean visivel;
    ValueCallback<Uri[]> anexos;
    Uri foto;
    static final int ESCOLHER_IMAGEM = 42;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        eu = this;
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setUserAgentString(s.getUserAgentString() + " KaniCodeApp/1");
        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView vista, ValueCallback<Uri[]> retorno, FileChooserParams parametros) {
                if (anexos != null) anexos.onReceiveValue(null);
                anexos = retorno;
                try {
                    Intent pedido;
                    if (parametros.isCaptureEnabled()) {
                        ContentValues valores = new ContentValues();
                        valores.put(MediaStore.Images.Media.DISPLAY_NAME, "KaniCode-" + System.currentTimeMillis() + ".jpg");
                        valores.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                        valores.put(MediaStore.Images.Media.IS_PENDING, 1);
                        foto = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, valores);
                        if (foto == null) throw new IllegalStateException("Não foi possível preparar a foto");
                        pedido = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                        pedido.putExtra(MediaStore.EXTRA_OUTPUT, foto);
                        pedido.setClipData(android.content.ClipData.newRawUri("Foto", foto));
                        pedido.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    } else {
                        pedido = parametros.createIntent();
                        pedido.setType("image/*");
                        pedido.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, parametros.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                    }
                    startActivityForResult(pedido, ESCOLHER_IMAGEM);
                } catch (Exception erro) {
                    concluirAnexo(null);
                    android.widget.Toast.makeText(MainActivity.this, "Não foi possível abrir. Tente a Galeria.", android.widget.Toast.LENGTH_LONG).show();
                }
                return true;
            }

            @Override
            public void onPermissionRequest(PermissionRequest r) {
                r.grant(r.getResources());   // microfone para o 🎤 (só a página do KaniCode abre aqui)
            }
        });
        web.addJavascriptInterface(new Ponte(), "KCApp");
        setContentView(web);
        web.loadUrl(Config.URL);
        pedirPermissoes();
    }

    void concluirAnexo(Uri[] imagens) {
        if (foto != null) {
            try {
                if (imagens == null) getContentResolver().delete(foto, null, null);
                else {
                    ContentValues valores = new ContentValues();
                    valores.put(MediaStore.Images.Media.IS_PENDING, 0);
                    getContentResolver().update(foto, valores, null, null);
                }
            } catch (Exception erro) { /* o retorno ao chat continua mesmo se a galeria falhar */ }
            foto = null;
        }
        ValueCallback<Uri[]> retorno = anexos;
        anexos = null;
        if (retorno != null) retorno.onReceiveValue(imagens);
    }

    @Override
    protected void onActivityResult(int codigo, int resultado, Intent dados) {
        super.onActivityResult(codigo, resultado, dados);
        if (codigo != ESCOLHER_IMAGEM) return;
        Uri[] imagens = null;
        if (resultado == RESULT_OK) {
            if (foto != null) imagens = new Uri[]{foto};
            else if (dados != null && dados.getClipData() != null) {
                int n = dados.getClipData().getItemCount();
                imagens = new Uri[n];
                for (int i = 0; i < n; i++) imagens[i] = dados.getClipData().getItemAt(i).getUri();
            } else imagens = WebChromeClient.FileChooserParams.parseResult(resultado, dados);
        }
        concluirAnexo(imagens);
    }

    void pedirPermissoes() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED
                || (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)) {
            requestPermissions(Build.VERSION.SDK_INT >= 33
                    ? new String[]{Manifest.permission.RECORD_AUDIO, Manifest.permission.POST_NOTIFICATIONS}
                    : new String[]{Manifest.permission.RECORD_AUDIO}, 1);
            return;
        }
        ligarBolinha();
    }

    @Override
    public void onRequestPermissionsResult(int c, String[] p, int[] r) {
        if (web != null) web.evaluateJavascript("window.kcAvisosAtualizar && kcAvisosAtualizar()", null);
        ligarBolinha();
    }

    @Override
    protected void onResume() {
        super.onResume();
        visivel = true;
        if (web != null) web.evaluateJavascript("window.kcAvisosAtualizar && kcAvisosAtualizar()", null);
        if (BolinhaService.eu == null && Settings.canDrawOverlays(this)
                && checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) ligarBolinha();
    }

    @Override
    protected void onPause() {
        visivel = false;
        super.onPause();
    }

    boolean avisosPermitidos() {
        return getSystemService(android.app.NotificationManager.class).areNotificationsEnabled()
            && (Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED);
    }

    void ligarBolinha() {
        if (!Settings.canDrawOverlays(this)) {   // "aparecer sobre outros apps": o Android só deixa a pessoa ligar nas configurações
            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())));
            return;
        }
        if (BolinhaService.eu == null) startForegroundService(new Intent(this, BolinhaService.class));
    }

    /** a bolinha pede: 1 toque = abrir; 2 toques = ouvir (o 🎤 da página); ouvindo, 2 toques cancelam */
    void ouvir() {
        runOnUiThread(() -> web.evaluateJavascript("(function(){if(window.kcBolaOuvir)return kcBolaOuvir();var m=document.getElementById('mic');if(m&&!m.classList.contains('on'))m.click();})()", null));
    }

    @Override
    public void onBackPressed() {
        moveTaskToBack(true);   // voltar só esconde: a conversa (e a rádio) continuam
    }

    // NÃO chama web.onPause()/pauseTimers(): a página segue viva com o app minimizado

    class Ponte {
        @JavascriptInterface
        public String avisosEstado() {
            if (!avisosPermitidos()) return "bloqueados";
            return getSharedPreferences("avisos", MODE_PRIVATE).getBoolean("ligados", false) ? "ligados" : "desligados";
        }

        @JavascriptInterface
        public void avisosAlternar() {
            runOnUiThread(() -> {
                android.content.SharedPreferences p = getSharedPreferences("avisos", MODE_PRIVATE);
                boolean ligar = !"ligados".equals(avisosEstado());
                p.edit().putBoolean("ligados", ligar).apply();
                if (ligar && !avisosPermitidos()) {
                    if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
                        requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 2);
                    else startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName()));
                } else if (ligar) notificar("Avisos ligados", "Vou avisar quando terminar ou precisar de você.", true);
                if (web != null) web.evaluateJavascript("window.kcAvisosAtualizar && kcAvisosAtualizar()", null);
            });
        }

        @JavascriptInterface
        public void notificar(String titulo, String texto, boolean outraAba) {
            if (!"ligados".equals(avisosEstado()) || (visivel && !outraAba)) return;
            android.app.NotificationManager nm = getSystemService(android.app.NotificationManager.class);
            nm.createNotificationChannel(new android.app.NotificationChannel("conversas", "Respostas e perguntas", android.app.NotificationManager.IMPORTANCE_DEFAULT));
            Intent abrir = new Intent(MainActivity.this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            android.app.PendingIntent toque = android.app.PendingIntent.getActivity(MainActivity.this, 2, abrir,
                android.app.PendingIntent.FLAG_UPDATE_CURRENT | android.app.PendingIntent.FLAG_IMMUTABLE);
            android.app.Notification aviso = new android.app.Notification.Builder(MainActivity.this, "conversas")
                .setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle(titulo).setContentText(texto)
                .setContentIntent(toque).setAutoCancel(true).build();
            nm.notify(2, aviso);
        }

        @JavascriptInterface
        public void estado(String e) {
            if (BolinhaService.eu != null) BolinhaService.eu.estado(e);
        }

        @JavascriptInterface
        public void tarefa(String e) {
            if (BolinhaService.eu != null) BolinhaService.eu.tarefa(e);
        }

        @JavascriptInterface
        public void nivel(float n) {
            if (BolinhaService.eu != null) BolinhaService.eu.nivel(n);
        }

        @JavascriptInterface
        public void quem(String q) {
            if (BolinhaService.eu != null) BolinhaService.eu.quem(q);
        }

        @JavascriptInterface
        public void atividade(String a) {
            if (BolinhaService.eu != null) BolinhaService.eu.atividade(a);
        }

        @JavascriptInterface
        public void humor(String hm) {
            if (BolinhaService.eu != null) BolinhaService.eu.humor(hm);
        }
    }
}
