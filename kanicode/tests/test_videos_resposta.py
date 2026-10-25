"""Vídeo na conversa: link (como o da Runway) é baixado para o disco e tocado por 127.0.0.1 com Range; o chat mostra o player."""
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import videos_resposta as videos  # noqa: E402
import test_layout as layout  # noqa: E402

PASTA = Path(os.environ.get('KC_TESTE_PASTA', 'D:/kanivete_testes/kanicode'))


def _video(destino):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=640x360:r=24:d=3', '-pix_fmt', 'yuv420p', str(destino)], check=True)


class VideosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        PASTA.mkdir(parents=True, exist_ok=True)
        cls.tmp = Path(tempfile.mkdtemp(dir=PASTA))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        (cls.tmp / 'web').mkdir()
        _video(cls.tmp / 'web' / 'gen-abc.mp4')
        raiz = str(cls.tmp / 'web')

        class H(http.server.SimpleHTTPRequestHandler):
            def __init__(s, *a, **k): super().__init__(*a, directory=raiz, **k)
            def log_message(s, *a): pass
        cls.srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.srv.shutdown)
        cls.link = f'http://127.0.0.1:{cls.srv.server_address[1]}/gen-abc.mp4?X-Amz-Signature=abc&Expires=1'

    def test_baixa_uma_vez_e_toca_com_range(self):
        dest = self.tmp / 'videos'
        d = videos.preparar(self.link, str(self.tmp), str(dest))
        self.assertTrue(d['baixado'])
        self.assertTrue(Path(d['caminho']).is_file())
        self.assertEqual(Path(d['caminho']).stat().st_size, (self.tmp / 'web' / 'gen-abc.mp4').stat().st_size)
        # outro link assinado do mesmo vídeo: não baixa de novo
        d2 = videos.preparar(self.link.replace('abc&', 'xyz&'), str(self.tmp), str(dest))
        self.assertEqual(d2['caminho'], d['caminho'])
        self.assertEqual(len(list(dest.iterdir())), 1)
        req = urllib.request.Request(d['url'], headers={'Range': 'bytes=100-199'})
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.status, 206)
            self.assertEqual(len(r.read()), 100)
            self.assertEqual(r.headers['Content-Type'], 'video/mp4')
        # token errado / arquivo não registrado: 404
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(d['url'].rsplit('/', 2)[0] + '/errado/' + d['url'].rsplit('/', 1)[1])

    def test_arquivo_local_e_recusa_o_que_nao_e_video(self):
        local = self.tmp / 'web' / 'gen-abc.mp4'
        d = videos.preparar(str(local), str(self.tmp), str(self.tmp / 'v2'))
        self.assertFalse(d['baixado'])
        self.assertEqual(Path(d['caminho']), local)
        (self.tmp / 'nota.txt').write_text('x')
        with self.assertRaises(ValueError):
            videos.preparar(str(self.tmp / 'nota.txt'), str(self.tmp), str(self.tmp / 'v2'))

    @unittest.skipUnless(layout.sync_playwright, 'Playwright opcional não instalado')
    def test_player_no_chat(self):
        d = videos.preparar(self.link, str(self.tmp), str(self.tmp / 'videos'))
        layout.LayoutTest.setUpClass()
        self.addCleanup(layout.LayoutTest.doClassCleanups)
        fx = layout.LayoutTest('test_controles_nas_posicoes_pedidas_e_fotos'); fx.setUp(); self.addCleanup(fx.doCleanups)
        p = fx.page
        p.evaluate('''d => { window.acoes = []; const ant = pywebview.api;
          pywebview.api = new Proxy(ant, {get: (a, nome) => nome.startsWith('resposta_') ? async (...args) => { acoes.push({nome, args}); return nome === 'resposta_video' ? d : true; } : a[nome]}); }''', d)
        # chega pelo Claude em pedaços, como link Markdown
        p.evaluate('conversa.innerHTML="";K.bolha=null;K.bruto=""')
        for pedaco in ('Pronto! Seu vídeo: [cena da praia](', self.link + ')'):
            fx.evento({'t': 'texto', 'd': pedaco})
        p.wait_for_function("(v => v && !v.hidden && v.readyState >= 1)(document.querySelector('.resposta-video video'))", timeout=8000)
        self.assertAlmostEqual(p.evaluate("document.querySelector('.resposta-video video').duration"), 3, delta=0.2)
        self.assertEqual(p.evaluate("acoes.filter(a => a.nome === 'resposta_video').length"), 1)
        p.evaluate("document.querySelector('.resposta-video video').currentTime = 2")
        p.wait_for_function("document.querySelector('.resposta-video video').currentTime >= 1.9")
        p.click('[data-video-acao="repetir"]')
        self.assertTrue(p.evaluate("document.querySelector('.resposta-video video').loop"))
        p.click('[data-video-acao="pasta"]')
        self.assertEqual(p.evaluate("acoes.at(-1)"), {'nome': 'resposta_abrir_caminho', 'args': [d['caminho']]})
        p.screenshot(path=str(PASTA / 'video_chat.png'))
        # caminho solto do disco também vira player
        p.evaluate('d => {conversa.innerHTML="";bolhaAjudante("codex", "Salvei em " + d, true)}', d['caminho'])
        p.wait_for_selector('.resposta-video video:not([hidden])')
        self.assertEqual(fx.erros, [])


if __name__ == '__main__':
    unittest.main()
