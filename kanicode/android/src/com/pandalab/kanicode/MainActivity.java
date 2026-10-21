package com.pandalab.kanicode;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
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
            public void onPermissionRequest(PermissionRequest r) {
                r.grant(r.getResources());   // microfone para o 🎤 (só a página do KaniCode abre aqui)
            }
        });
        web.addJavascriptInterface(new Ponte(), "KCApp");
        setContentView(web);
        web.loadUrl(Config.URL);
        pedirPermissoes();
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
        ligarBolinha();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (BolinhaService.eu == null && Settings.canDrawOverlays(this)
                && checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) ligarBolinha();
    }

    void ligarBolinha() {
        if (!Settings.canDrawOverlays(this)) {   // "aparecer sobre outros apps": o Android só deixa a pessoa ligar nas configurações
            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())));
            return;
        }
        if (BolinhaService.eu == null) startForegroundService(new Intent(this, BolinhaService.class));
    }

    /** a bolinha pede: 1 toque = abrir; 2 toques = ouvir (o 🎤 da página) */
    void ouvir() {
        runOnUiThread(() -> web.evaluateJavascript("(function(){var m=document.getElementById('mic');if(m&&!m.classList.contains('on'))m.click();})()", null));
    }

    @Override
    public void onBackPressed() {
        moveTaskToBack(true);   // voltar só esconde: a conversa (e a rádio) continuam
    }

    // NÃO chama web.onPause()/pauseTimers(): a página segue viva com o app minimizado

    class Ponte {
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
    }
}
