"""Monitor nativo de pastas do Windows; não altera os arquivos observados."""
import ctypes
from ctypes import wintypes
import os
import struct


def monitorar(raiz, receber, parar, pronto, erro):
    if os.name != 'nt':
        erro('Monitor nativo disponível apenas no Windows.'); pronto.set(); return
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    class Sobreposta(ctypes.Structure):
        _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                    ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k.CreateFileW.restype = wintypes.HANDLE
    k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateEventW.restype = wintypes.HANDLE
    k.ReadDirectoryChangesW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
                                       ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(Sobreposta), ctypes.c_void_p]
    k.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(Sobreposta), ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(Sobreposta)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.ResetEvent.argtypes = [wintypes.HANDLE]
    pasta = k.CreateFileW(str(raiz), 1, 7, None, 3, 0x02000000 | 0x40000000, None)
    if pasta == ctypes.c_void_p(-1).value:
        erro(str(ctypes.WinError(ctypes.get_last_error()))); pronto.set(); return
    evento = k.CreateEventW(None, True, False, None)
    if not evento:
        k.CloseHandle(pasta); erro(str(ctypes.WinError(ctypes.get_last_error()))); pronto.set(); return
    ov = Sobreposta(); ov.hEvent = evento
    # Local: 64 KiB. Zero bytes recebidos significa perda de eventos e exige nova varredura.
    buffer = (wintypes.DWORD * 16384)()
    try:
        while not parar.is_set():
            k.ResetEvent(evento)
            ok = k.ReadDirectoryChangesW(pasta, buffer, ctypes.sizeof(buffer), True, 1 | 2 | 8 | 16, None, ctypes.byref(ov), None)
            if not ok and ctypes.get_last_error() != 997:
                raise ctypes.WinError(ctypes.get_last_error())
            pronto.set()
            while k.WaitForSingleObject(evento, 500) == 258:
                if parar.is_set():
                    k.CancelIoEx(pasta, ctypes.byref(ov))
                    k.WaitForSingleObject(evento, 3000)
                    return
            tamanho = wintypes.DWORD()
            if not k.GetOverlappedResult(pasta, ctypes.byref(ov), ctypes.byref(tamanho), False):
                raise ctypes.WinError(ctypes.get_last_error())
            if tamanho.value == 0:
                receber(None); continue
            dados = bytes(buffer)[:tamanho.value]
            pos = 0
            while pos + 12 <= len(dados):
                proximo, acao, comprimento = struct.unpack_from('<III', dados, pos)
                nome = dados[pos + 12:pos + 12 + comprimento].decode('utf-16-le')
                receber((os.path.join(raiz, nome), acao))
                if not proximo: break
                pos += proximo
    except Exception as e:
        erro(str(e))
    finally:
        pronto.set()
        k.CancelIoEx(pasta, ctypes.byref(ov))
        k.CloseHandle(evento)
        k.CloseHandle(pasta)
