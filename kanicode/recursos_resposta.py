"""Ações explícitas da conversa: Explorer, navegador e imagens, sem executar código recebido."""
import base64
import ctypes as C
from ctypes import wintypes as W
import io
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.parse
import urllib.request

MAX_IMAGEM = 32 * 1024 * 1024
FORMATOS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif", "BMP": "image/bmp"}


def caminho(valor, pasta):
    valor = str(valor).strip()
    if valor.startswith('file:'):
        u = urllib.parse.urlsplit(valor)
        valor = urllib.request.url2pathname(u.path)
        if u.netloc:
            valor = '\\\\' + u.netloc + valor
    if not valor or re.search(r'[\x00-\x1f]', valor) or (re.match(r'^\w+:', valor) and not re.match(r'^[A-Za-z]:[\\/]', valor)):
        raise ValueError('Caminho inválido.')
    valor = os.path.normpath(valor if os.path.isabs(valor) else os.path.join(pasta, valor))
    if not os.path.exists(valor):
        sem_linha = re.sub(r':\d+(?::\d+)?$', '', valor)
        if not os.path.exists(sem_linha):
            raise ValueError('Este caminho não existe no computador.')
        valor = sem_linha
    return valor


def abrir_caminho(valor, pasta):
    alvo = caminho(valor, pasta)
    explorer = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'explorer.exe')
    args = [explorer, alvo] if os.path.isdir(alvo) else [explorer, '/select,', alvo]
    subprocess.Popen(args)  # Explorer seleciona arquivos; nunca os executa.
    return True


def url_web(valor):
    valor = str(valor).strip()
    if re.search(r'[\x00-\x20]', valor):
        raise ValueError('Link inválido.')
    u = urllib.parse.urlsplit(valor)
    if u.scheme.lower() not in ('https', 'http') or not u.hostname or u.username or u.password:
        raise ValueError('Use um link http ou https válido.')
    return valor


def _chrome():
    candidatos = []
    try:
        import winreg
        for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(raiz, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe') as chave:
                    candidatos.append(winreg.QueryValue(chave, None).strip('"'))
            except OSError:
                pass
    except ImportError:
        pass
    for env in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
        if os.environ.get(env):
            candidatos.append(os.path.join(os.environ[env], 'Google', 'Chrome', 'Application', 'chrome.exe'))
    return next((p for p in candidatos if os.path.isfile(p)), None)


def abrir_link(valor, navegador='chrome'):
    url = url_web(valor)
    chrome = _chrome() if navegador == 'chrome' else None
    if chrome:
        subprocess.Popen([chrome, url])
    else:
        os.startfile(url)  # associação de http/https escolhida pelo usuário no Windows
    return True


class _Redirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, url_web(newurl))


def imagem(origem, pasta):
    """Bytes originais completos, limitados e validados; rede só na abertura/cópia/salvamento."""
    from PIL import Image
    origem = str(origem)
    if origem.startswith('data:'):
        if len(origem) > MAX_IMAGEM * 4 // 3 + 256:
            raise ValueError('Imagem maior que 32 MB.')
        cab, dados = origem.split(',', 1)
        if not re.fullmatch(r'data:image/(?:png|jpeg|webp|gif|bmp);base64', cab):
            raise ValueError('Formato de imagem não suportado.')
        dados = base64.b64decode(dados, validate=True)
        nome = 'imagem'
    elif re.match(r'^https?://', origem, re.I):
        req = urllib.request.Request(url_web(origem), headers={'User-Agent': 'KaniCode/1.0'})
        with urllib.request.build_opener(_Redirecionamento()).open(req, timeout=12) as resposta:
            dados = resposta.read(MAX_IMAGEM + 1)
        nome = Path(urllib.parse.unquote(urllib.parse.urlsplit(origem).path)).name or 'imagem'
    else:
        alvo = caminho(origem, pasta)
        with open(alvo, 'rb') as arquivo:
            dados = arquivo.read(MAX_IMAGEM + 1)
        nome = Path(alvo).name
    if len(dados) > MAX_IMAGEM:
        raise ValueError('Imagem maior que 32 MB.')
    with Image.open(io.BytesIO(dados)) as im:
        if im.format not in FORMATOS:
            raise ValueError('Formato de imagem não suportado.')
        tipo, largura, altura = FORMATOS[im.format], im.width, im.height
        if largura * altura > 60_000_000:
            raise ValueError('Imagem grande demais para o visualizador (60 megapixels).')
        im.verify()
    extensao = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif', 'image/bmp': '.bmp'}[tipo]
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(nome).stem)[:100] + extensao
    return dados, {'nome': nome, 'tipo': tipo, 'largura': largura, 'altura': altura}


def imagem_dados(origem, pasta):
    dados, info = imagem(origem, pasta)
    return dict(info, url='data:' + info['tipo'] + ';base64,' + base64.b64encode(dados).decode('ascii'))


def _clipboard(formato, dados):
    if os.name != 'nt':
        raise RuntimeError('Área de transferência nativa disponível no Windows.')
    user, kernel = C.WinDLL('user32', use_last_error=True), C.WinDLL('kernel32', use_last_error=True)
    user.OpenClipboard.argtypes = [W.HWND]; user.OpenClipboard.restype = W.BOOL
    user.GetForegroundWindow.argtypes = []; user.GetForegroundWindow.restype = W.HWND
    user.GetDesktopWindow.argtypes = []; user.GetDesktopWindow.restype = W.HWND
    user.EmptyClipboard.argtypes = []; user.EmptyClipboard.restype = W.BOOL
    user.CloseClipboard.argtypes = []; user.CloseClipboard.restype = W.BOOL
    user.SetClipboardData.argtypes = [W.UINT, W.HANDLE]; user.SetClipboardData.restype = W.HANDLE
    kernel.GlobalAlloc.argtypes = [W.UINT, C.c_size_t]; kernel.GlobalAlloc.restype = W.HGLOBAL
    kernel.GlobalLock.argtypes = [W.HGLOBAL]; kernel.GlobalLock.restype = C.c_void_p
    kernel.GlobalUnlock.argtypes = [W.HGLOBAL]; kernel.GlobalUnlock.restype = W.BOOL
    kernel.GlobalFree.argtypes = [W.HGLOBAL]; kernel.GlobalFree.restype = W.HGLOBAL
    memoria = kernel.GlobalAlloc(0x0002, len(dados))
    if not memoria:
        raise MemoryError('Não foi possível copiar.')
    aberta = False
    try:
        ptr = kernel.GlobalLock(memoria)
        if not ptr:
            raise C.WinError(C.get_last_error())
        C.memmove(ptr, dados, len(dados)); kernel.GlobalUnlock(memoria)
        for _ in range(10):
            if user.OpenClipboard(user.GetForegroundWindow() or user.GetDesktopWindow()):
                aberta = True; break
            time.sleep(.02)
        if not aberta or not user.EmptyClipboard() or not user.SetClipboardData(formato, memoria):
            raise RuntimeError('A área de transferência está ocupada. Tente novamente.')
        memoria = None  # a propriedade passou para o Windows
    finally:
        if aberta:
            user.CloseClipboard()
        if memoria:
            kernel.GlobalFree(memoria)
    return True


def copiar_texto(texto):
    return _clipboard(13, (str(texto) + '\0').encode('utf-16-le'))


def copiar_imagem(origem, pasta):
    from PIL import Image, ImageOps
    dados, _ = imagem(origem, pasta)
    with Image.open(io.BytesIO(dados)) as im:
        im = ImageOps.exif_transpose(im).convert('RGBA')
        fundo = Image.new('RGB', im.size, 'white')
        fundo.paste(im, mask=im.getchannel('A'))
        buf = io.BytesIO(); fundo.save(buf, 'BMP')
    return _clipboard(8, buf.getvalue()[14:])  # CF_DIB: cabeçalho BMP de arquivo não faz parte do bitmap


def salvar_imagem(dados, info, destino):
    """Mantém bytes originais; converte só se o usuário escolher outra extensão."""
    from PIL import Image, ImageOps
    formatos = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.webp': 'WEBP', '.gif': 'GIF', '.bmp': 'BMP'}
    ext = Path(destino).suffix.lower()
    if ext not in formatos:
        destino += Path(info['nome']).suffix
        ext = Path(destino).suffix.lower()
    if FORMATOS[formatos[ext]] == info['tipo']:
        with open(destino, 'wb') as arquivo:
            arquivo.write(dados)
    else:
        with Image.open(io.BytesIO(dados)) as im:
            im = ImageOps.exif_transpose(im)
            if formatos[ext] in ('JPEG', 'BMP'):
                fundo = Image.new('RGB', im.size, 'white')
                if 'A' in im.getbands():
                    fundo.paste(im, mask=im.getchannel('A'))
                else:
                    fundo.paste(im.convert('RGB'))
                im = fundo
            im.save(destino, format=formatos[ext])
    return True
