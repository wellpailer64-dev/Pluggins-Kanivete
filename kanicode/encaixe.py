"""Encaixe do Windows (Win + setas, arrastar para a borda) na janela SEM moldura do KaniCode.

O Windows só encaixa janela com borda redimensionável: liga WS_THICKFRAME/WS_CAPTION/maximizar/minimizar e esconde a
moldura respondendo WM_NCCALCSIZE com 0 (a área da página ocupa a janela toda; o mesmo truque de VS Code e Electron).
Maximizada, o Windows põe a janela um pouco além da tela: aí a área é recolhida pela espessura da borda.
Chamar `ligar(hwnd)` NA thread da interface (a dona da janela).
"""
import ctypes
from ctypes import wintypes

u32, comctl = ctypes.windll.user32, ctypes.windll.comctl32
GWL_STYLE = -16
WS_CAPTION, WS_THICKFRAME, WS_SYSMENU, WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0xC00000, 0x40000, 0x80000, 0x20000, 0x10000
WM_NCCALCSIZE = 0x0083
LRESULT = ctypes.c_ssize_t
SUBCLASSPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                  ctypes.c_size_t, ctypes.c_size_t)
comctl.SetWindowSubclass.argtypes = [wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t]
comctl.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
comctl.DefSubclassProc.restype = LRESULT
u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
u32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_vivos = []   # o Python não pode recolher a função enquanto a janela existir


class _NCPARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


def _proc(hwnd, msg, wp, lp, _id, _ref):
    if msg == WM_NCCALCSIZE and wp:
        if u32.IsZoomed(hwnd):
            p = ctypes.cast(lp, ctypes.POINTER(_NCPARAMS)).contents
            dpi = u32.GetDpiForWindow(hwnd) or 96
            b = u32.GetSystemMetricsForDpi(32, dpi) + u32.GetSystemMetricsForDpi(92, dpi)   # SM_CXFRAME + PADDEDBORDER
            r = p.rgrc[0]
            r.left += b; r.top += b; r.right -= b; r.bottom -= b
        return 0
    return comctl.DefSubclassProc(hwnd, msg, wp, lp)


def ligar(hwnd):
    f = SUBCLASSPROC(_proc)
    _vivos.append(f)
    comctl.SetWindowSubclass(hwnd, f, 0x4B43, 0)   # "KC"
    st = u32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    u32.SetWindowLongPtrW(hwnd, GWL_STYLE, st | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
    u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)   # FRAMECHANGED, sem mover
    return True
