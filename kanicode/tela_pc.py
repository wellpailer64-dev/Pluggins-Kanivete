"""Monitores e mouse do PC para o celular pareado, sem CDP ou dependências novas."""
import contextlib
import ctypes
from ctypes import wintypes as w
import io
import math
import threading
import time

_trava = threading.Lock()
_cache = (0, [])


@contextlib.contextmanager
def _pixels():
    u = ctypes.WinDLL('user32', use_last_error=True)
    u.SetThreadDpiAwarenessContext.argtypes = [w.HANDLE]
    u.SetThreadDpiAwarenessContext.restype = w.HANDLE
    anterior = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        yield u
    finally:
        if anterior:
            u.SetThreadDpiAwarenessContext(anterior)


def _enumerar():
    class Info(ctypes.Structure):
        _fields_ = [('cbSize', w.DWORD), ('rcMonitor', w.RECT), ('rcWork', w.RECT),
                    ('dwFlags', w.DWORD), ('szDevice', w.WCHAR * 32)]
    itens = []
    with _pixels() as u:
        u.GetMonitorInfoW.argtypes = [w.HANDLE, ctypes.POINTER(Info)]
        callback = ctypes.WINFUNCTYPE(w.BOOL, w.HANDLE, w.HDC, ctypes.POINTER(w.RECT), w.LPARAM)

        def receber(handle, dc, rect, extra):
            info = Info(); info.cbSize = ctypes.sizeof(info)
            if u.GetMonitorInfoW(handle, ctypes.byref(info)):
                r = info.rcMonitor
                itens.append({'id': info.szDevice, 'principal': bool(info.dwFlags & 1),
                              'x': r.left, 'y': r.top, 'largura': r.right-r.left, 'altura': r.bottom-r.top})
            return True
        u.EnumDisplayMonitors.argtypes = [w.HDC, ctypes.POINTER(w.RECT), callback, w.LPARAM]
        if not u.EnumDisplayMonitors(None, None, callback(receber), 0):
            raise OSError('Não foi possível listar os monitores.')
    itens.sort(key=lambda m: (not m['principal'], m['id']))
    for n, m in enumerate(itens, 1):
        m['nome'] = ('Principal' if m['principal'] else f'Monitor {n}') + f" · {m['largura']}×{m['altura']}"
    return itens


def monitores():
    global _cache
    with _trava:
        agora = time.monotonic()
        if agora - _cache[0] > 2 or not _cache[1]:
            _cache = (agora, _enumerar())
        return [dict(m) for m in _cache[1]]


def monitor(id=''):
    itens = monitores()
    if not itens:
        raise LookupError('Nenhum monitor disponível.')
    if not id:
        return itens[0]
    for m in itens:
        if m['id'] == id:
            return m
    raise LookupError('O monitor foi desconectado. Escolha outro monitor.')


def _entrada(x, y, cliques):
    with _pixels() as u:
        u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        if not u.SetCursorPos(x, y):
            raise OSError('O Windows não permitiu mover o mouse.')
        u.mouse_event.argtypes = [w.DWORD, w.DWORD, w.DWORD, w.DWORD, ctypes.c_size_t]
        for _ in range(cliques):
            u.mouse_event(0x0002, 0, 0, 0, 0)
            u.mouse_event(0x0004, 0, 0, 0, 0)


def mouse(dados):
    if not isinstance(dados, dict) or dados.get('acao') not in ('mover', 'clicar'):
        raise ValueError('Ação de mouse inválida.')
    for eixo in ('x', 'y'):
        v = dados.get(eixo)
        if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1:
            raise ValueError('Coordenada de mouse inválida.')
    cliques = dados.get('cliques', 1)
    if type(cliques) is not int or cliques not in (1, 2):
        raise ValueError('Quantidade de cliques inválida.')
    m = monitor(dados.get('monitor', ''))
    x = m['x'] + min(m['largura']-1, int(dados['x'] * m['largura']))
    y = m['y'] + min(m['altura']-1, int(dados['y'] * m['altura']))
    with _trava:
        _entrada(x, y, cliques if dados['acao'] == 'clicar' else 0)
    return {'ok': True, 'largura': m['largura'], 'altura': m['altura']}


def _capturar(m, largura):
    """Reduz no GDI antes de copiar pixels; não captura o desktop inteiro para recortar depois."""
    from PIL import Image
    class Cabecalho(ctypes.Structure):
        _fields_ = [('size',w.DWORD),('width',w.LONG),('height',w.LONG),('planes',w.WORD),
                    ('bits',w.WORD),('compression',w.DWORD),('imageSize',w.DWORD),
                    ('xppm',w.LONG),('yppm',w.LONG),('used',w.DWORD),('important',w.DWORD)]
    escala=min(1,largura/max(m['largura'],m['altura']))
    largura,altura=max(1,round(m['largura']*escala)),max(1,round(m['altura']*escala))
    with _pixels() as u:
        g=ctypes.WinDLL('gdi32',use_last_error=True)
        u.GetDC.argtypes=[w.HWND];u.GetDC.restype=w.HDC
        u.ReleaseDC.argtypes=[w.HWND,w.HDC]
        g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
        g.CreateDIBSection.argtypes=[w.HDC,ctypes.POINTER(Cabecalho),w.UINT,ctypes.POINTER(ctypes.c_void_p),w.HANDLE,w.DWORD]
        g.CreateDIBSection.restype=w.HANDLE
        g.SelectObject.argtypes=[w.HDC,w.HANDLE];g.SelectObject.restype=w.HANDLE
        g.DeleteObject.argtypes=[w.HANDLE];g.DeleteDC.argtypes=[w.HDC]
        g.SetStretchBltMode.argtypes=[w.HDC,ctypes.c_int]
        g.StretchBlt.argtypes=[w.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,
                              w.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.DWORD]
        tela=u.GetDC(None);dc=None;bitmap=None;anterior=None
        try:
            if not tela:raise OSError('Tela indisponível.')
            dc=g.CreateCompatibleDC(tela)
            if not dc:raise OSError('Captura indisponível.')
            info=Cabecalho();info.size=ctypes.sizeof(info);info.width=largura;info.height=-altura;info.planes=1;info.bits=32
            pixels=ctypes.c_void_p()
            bitmap=g.CreateDIBSection(tela,ctypes.byref(info),0,ctypes.byref(pixels),None,0)
            if not bitmap or not pixels:raise OSError('Não foi possível preparar a captura.')
            anterior=g.SelectObject(dc,bitmap);g.SetStretchBltMode(dc,3)
            if not g.StretchBlt(dc,0,0,largura,altura,tela,m['x'],m['y'],m['largura'],m['altura'],0x40CC0020):
                raise OSError('Não foi possível capturar o monitor.')
            g.GdiFlush()
            return Image.frombytes('RGB',(largura,altura),ctypes.string_at(pixels,largura*altura*4),'raw','BGRX')
        finally:
            if anterior and dc:g.SelectObject(dc,anterior)
            if bitmap:g.DeleteObject(bitmap)
            if dc:g.DeleteDC(dc)
            if tela:u.ReleaseDC(None,tela)


def quadro(m, largura=1280):
    imagem = _capturar(m, largura)
    try:
        saida = io.BytesIO(); imagem.save(saida, format='JPEG', quality=55)
        return saida.getvalue()
    finally:
        imagem.close()


def transmitir(wfile, id='', largura=1280):
    from tela_movel import LIMITE
    ultimo=None;enviado=0
    while True:
        inicio = time.monotonic()
        jpg = quadro(monitor(id), largura)
        if jpg!=ultimo or inicio-enviado>=2:
            wfile.write(b'--' + LIMITE.encode() + b'\r\nContent-Type: image/jpeg\r\nContent-Length: ' +
                        str(len(jpg)).encode() + b'\r\n\r\n' + jpg + b'\r\n')
            wfile.flush();ultimo=jpg;enviado=inicio
        # No máximo oito quadros por segundo; não enfileira quadros antigos.
        time.sleep(max(0, .125 - (time.monotonic()-inicio)))
