"""Vídeos na conversa (2026-10-25): link de vídeo (ex.: o que a Runway devolve) ou arquivo do disco vira um player no chat.

Link da web é BAIXADO para <dados>/videos (o link da Runway expira; o arquivo fica). O chat toca o arquivo por um servidor
HTTP só em 127.0.0.1, com token, que entrega apenas os arquivos registrados aqui e responde Range (avançar/voltar).
"""
import hashlib
import http.server
import mimetypes
import os
import re
import secrets
import shutil
import threading
import urllib.parse
import urllib.request
from pathlib import Path

EXT = {'.mp4': 'video/mp4', '.m4v': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime'}
MAX = 2 * 1024 ** 3   # 2 GB
_REG, _TRAVA = {}, threading.Lock()
_SRV = {'porta': 0, 'token': secrets.token_urlsafe(16)}


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        partes = self.path.split('?')[0].strip('/').split('/')
        if len(partes) != 3 or partes[0] != 'v' or partes[1] != _SRV['token'] or partes[2] not in _REG:
            self.send_error(404); return
        alvo = _REG[partes[2]]
        try:
            tam = os.path.getsize(alvo)
        except OSError:
            self.send_error(404); return
        ini, fim, cod = 0, tam - 1, 200
        m = re.match(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
        if m and tam:
            if m.group(1):
                ini = int(m.group(1)); fim = int(m.group(2)) if m.group(2) else tam - 1
            else:
                ini = max(0, tam - int(m.group(2) or 0))
            fim = min(fim, tam - 1)
            if ini > fim:
                self.send_response(416); self.send_header('Content-Range', f'bytes */{tam}'); self.end_headers(); return
            cod = 206
        self.send_response(cod)
        self.send_header('Content-Type', EXT.get(Path(alvo).suffix.lower(), 'application/octet-stream'))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(fim - ini + 1))
        self.send_header('Access-Control-Allow-Origin', '*')
        if cod == 206:
            self.send_header('Content-Range', f'bytes {ini}-{fim}/{tam}')
        self.end_headers()
        try:
            with open(alvo, 'rb') as f:
                f.seek(ini); falta = fim - ini + 1
                while falta > 0:
                    bloco = f.read(min(falta, 256 * 1024))
                    if not bloco:
                        break
                    self.wfile.write(bloco); falta -= len(bloco)
        except (ConnectionError, OSError):
            pass


def _servidor():
    with _TRAVA:
        if not _SRV['porta']:
            srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
            srv.daemon_threads = True
            _SRV['porta'] = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True, name='kc-videos').start()
    return _SRV['porta']


def _registrar(alvo):
    vid = hashlib.sha1(os.path.abspath(alvo).lower().encode()).hexdigest()[:16]
    _REG[vid] = alvo
    return f"http://127.0.0.1:{_servidor()}/v/{_SRV['token']}/{vid}"


def _baixar(url, pasta_videos):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ('http', 'https') or u.username or u.password:
        raise ValueError('Link inválido.')
    nome = Path(urllib.parse.unquote(u.path)).name or 'video.mp4'
    ext = Path(nome).suffix.lower()
    if ext not in EXT:
        ext = '.mp4'
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(nome).stem)[:60] or 'video'
    chave = hashlib.sha1((u.netloc + u.path).encode()).hexdigest()[:10]   # o link assinado muda a cada vez; o caminho não
    os.makedirs(pasta_videos, exist_ok=True)
    destino = os.path.join(pasta_videos, f'{base}_{chave}{ext}')
    if os.path.exists(destino) and os.path.getsize(destino) > 0:
        return destino
    tmp = destino + '.parcial'
    try:
        _gravar(url, tmp)
    except BaseException:
        try: os.remove(tmp)
        except OSError: pass
        raise
    os.replace(tmp, destino)
    return destino


def _gravar(url, tmp):
    req = urllib.request.Request(url, headers={'User-Agent': 'KaniCode/1.0'})
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, 'wb') as f:
        tipo = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        if tipo and not (tipo.startswith('video/') or tipo in ('application/octet-stream', 'binary/octet-stream')):
            raise ValueError(f'O link não é um vídeo ({tipo}).')
        total = 0
        while True:
            bloco = r.read(1024 * 1024)
            if not bloco:
                break
            total += len(bloco)
            if total > MAX:
                raise ValueError('Vídeo maior que 2 GB.')
            f.write(bloco)


def preparar(origem, pasta, pasta_videos):
    """origem = link http(s) ou caminho no disco → {url (player), caminho, nome, baixado}."""
    import recursos_resposta as recursos
    origem = str(origem).strip()
    baixado = False
    if re.match(r'^https?://', origem, re.I):
        alvo = _baixar(origem, pasta_videos)
        baixado = True
    else:
        alvo = recursos.caminho(origem, pasta)
        if os.path.isdir(alvo) or Path(alvo).suffix.lower() not in EXT:
            raise ValueError('Não é um arquivo de vídeo (mp4, webm, mov).')
    return {'url': _registrar(alvo), 'caminho': alvo, 'nome': Path(alvo).name, 'baixado': baixado}


def salvar_como(alvo, destino):
    shutil.copyfile(alvo, destino)
    return destino
