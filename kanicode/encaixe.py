"""Encaixe do Windows (Win + setas, arrastar para a borda) na janela SEM moldura do KaniCode.

O Windows só encaixa janela com borda redimensionável: liga WS_THICKFRAME/WS_CAPTION/maximizar/minimizar e esconde a
moldura respondendo WM_NCCALCSIZE com 0 (a área da página ocupa a janela toda; o mesmo truque de VS Code e Electron).
Maximizada, o Windows põe a janela um pouco além da tela: aí a área é recolhida pela espessura da borda.
O WinForms reaplica o estilo dele ao restaurar/mostrar a janela (2026-10-22: Win+←/→ pararam depois de reabrir): o
WM_STYLECHANGING devolve as nossas bordas toda vez. `ligar` pode ser chamado de novo (não duplica).
Chamar `ligar(hwnd)` NA thread da interface (a dona da janela).
"""
import ctypes
from ctypes import wintypes

# cópias próprias das DLLs: argtypes em ctypes.windll vale para o processo todo e quebra o pywebview (2026-10-23)
u32, comctl = ctypes.WinDLL("user32"), ctypes.WinDLL("comctl32")
GWL_STYLE = -16
WS_CAPTION, WS_THICKFRAME, WS_SYSMENU, WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0xC00000, 0x40000, 0x80000, 0x20000, 0x10000
WM_NCCALCSIZE, WM_STYLECHANGING = 0x0083, 0x007C
BORDAS = WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
LRESULT = ctypes.c_ssize_t
SUBCLASSPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                  ctypes.c_size_t, ctypes.c_size_t)
comctl.SetWindowSubclass.argtypes = [wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t]
comctl.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
comctl.DefSubclassProc.restype = LRESULT
u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
u32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_ligadas = set()


class _NCPARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


class _STYLESTRUCT(ctypes.Structure):
    _fields_ = [("velho", wintypes.DWORD), ("novo", wintypes.DWORD)]


def _proc(hwnd, msg, wp, lp, _id, _ref):
    if msg == WM_STYLECHANGING and ctypes.c_int(wp).value == GWL_STYLE:
        s = ctypes.cast(lp, ctypes.POINTER(_STYLESTRUCT)).contents
        s.novo |= BORDAS
    elif msg == WM_NCCALCSIZE and wp:
        if u32.IsZoomed(hwnd):
            p = ctypes.cast(lp, ctypes.POINTER(_NCPARAMS)).contents
            dpi = u32.GetDpiForWindow(hwnd) or 96
            b = u32.GetSystemMetricsForDpi(32, dpi) + u32.GetSystemMetricsForDpi(92, dpi)   # SM_CXFRAME + PADDEDBORDER
            r = p.rgrc[0]
            r.left += b; r.top += b; r.right -= b; r.bottom -= b
        return 0
    return comctl.DefSubclassProc(hwnd, msg, wp, lp)


_PROC = SUBCLASSPROC(_proc)   # uma só, viva enquanto o módulo existir


def ligar(hwnd):
    if hwnd not in _ligadas:
        comctl.SetWindowSubclass(hwnd, _PROC, 0x4B43, 0)   # "KC"
        _ligadas.add(hwnd)
    st = u32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    if st & BORDAS == BORDAS:
        return True
    u32.SetWindowLongPtrW(hwnd, GWL_STYLE, st | BORDAS)
    u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)   # FRAMECHANGED, sem mover
    return True
