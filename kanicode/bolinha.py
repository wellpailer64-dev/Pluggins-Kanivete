"""A bolinha do KaniCode: janela NATIVA do Windows (WinForms + janela em camadas com transparência por pixel).

Sem navegador dentro: o WebView2 desenha por uma camada de vídeo que ignora o recorte da janela (sobrava um quadrado
escuro em volta), e cada janela com navegador é um processo a mais. Aqui a imagem é desenhada com GDI+ num bitmap com
alfa e entregue ao Windows (UpdateLayeredWindow): borda lisa, sem quadrado, quase nada de memória.
Posições e tamanhos em pixels reais (o processo é "DPI aware"). Criar SEMPRE na thread da interface (Invoke).
"""
import ctypes, math, time
from ctypes import wintypes

import clr  # noqa: F401  (pythonnet, que o pywebview já carrega)
from System import Action
from System.Drawing import Bitmap, Color, Font, FontStyle, Graphics, Pen, Point, PointF, RectangleF, Size, SolidBrush
from System.Drawing.Drawing2D import GraphicsPath, LineCap, PathGradientBrush, SmoothingMode
from System.Drawing.Imaging import PixelFormat
from System.Drawing.Text import TextRenderingHint
from System.Windows.Forms import Form, FormBorderStyle, FormStartPosition, MouseButtons, Screen, Timer

LIMA, LIMA_CLARO, LIMA_ESC, FUNDO, ALERTA = (0xB6, 0xF2, 0x3A), (0xD8, 0xFF, 0x7A), (0x7F, 0xB5, 0x1A), (0x0E, 0x11, 0x10), (0xFF, 0x5A, 0x5F)
u32, gdi = ctypes.windll.user32, ctypes.windll.gdi32
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_TOPMOST = -20, 0x80000, 0x80, 0x40000, 0x8


class _BLEND(ctypes.Structure):
    _fields_ = [("op", ctypes.c_byte), ("flags", ctypes.c_byte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_byte)]


u32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
                                    wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF, ctypes.POINTER(_BLEND), wintypes.DWORD]
u32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi.SelectObject.restype = wintypes.HGDIOBJ
gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi.DeleteDC.argtypes = [wintypes.HDC]
gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi.CreateCompatibleDC.restype = wintypes.HDC
u32.GetDC.restype = wintypes.HDC
u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]


def _cor(rgb, a=255):
    return Color.FromArgb(a, *rgb)


class Bolinha:
    """bolinha arrastável, sempre por cima. ao_clicar() = clique; ao_mover(x, y) = soltou em outro lugar (pixels reais)"""

    def __init__(self, x, y, lado_ui, ao_clicar, ao_mover, ao_direito=None):
        self.ao_clicar, self.ao_mover, self.ao_direito = ao_clicar, ao_mover, ao_direito
        self.estado = ""          # "" | "trabalhando" | "pergunta"
        self.aberta = False
        self.voz = ""             # "" | "escutando" (Ei Kani ligado) | "ouvindo" (gravando o pedido)
        self._fase = 0.0
        self._cursor = True
        f = self.form = Form()
        f.FormBorderStyle = getattr(FormBorderStyle, "None")   # "None" é palavra reservada no Python
        f.ShowInTaskbar = False
        f.TopMost = True
        f.StartPosition = FormStartPosition.Manual
        f.Text = "KaniCode"
        f.Location = Point(int(x), int(y))
        h = int(str(f.Handle))
        self.hwnd = h
        self.escala = u32.GetDpiForWindow(h) / 96 or 1
        self.lado = round(lado_ui * self.escala)
        self.margem = round(4 * self.escala)          # espaço para a sombra
        self.total = self.lado + 2 * self.margem
        f.Size = Size(self.total, self.total)
        u32.SetWindowLongW(h, GWL_EXSTYLE, (u32.GetWindowLongW(h, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
        f.MouseDown += self._apertou
        self._t = Timer()
        self._t.Interval = 550
        self._t.Tick += self._tique
        self._t.Start()
        f.Show()
        self.desenhar()

    # ── posição ──
    @property
    def x(self):
        return self.form.Location.X

    @property
    def y(self):
        return self.form.Location.Y

    def area_util(self):
        """área útil (sem a barra de tarefas) do monitor onde a bolinha está, em pixels reais: x, y, w, h"""
        a = Screen.FromHandle(self.form.Handle).WorkingArea
        return a.X, a.Y, a.Width, a.Height

    # ── eventos ──
    def _apertou(self, _s, e):
        if e.Button == MouseButtons.Right:
            if self.ao_direito:
                self.ao_direito()
            return
        if e.Button != MouseButtons.Left:
            return
        x0, y0 = self.x, self.y
        u32.ReleaseCapture()
        u32.SendMessageW(self.hwnd, 0xA1, 2, 0)   # WM_NCLBUTTONDOWN no "título": o Windows arrasta (volta ao soltar)
        if abs(self.x - x0) + abs(self.y - y0) <= 3:
            self.ao_clicar()
        else:
            self.ao_mover(self.x, self.y)

    def _tique(self, _s, _e):
        if self.estado == "trabalhando" or self.voz == "ouvindo":
            self._fase = (self._fase + 0.12) % 1.0
        else:
            self._cursor = not self._cursor
        self.desenhar()

    def definir(self, estado=None, aberta=None, voz=None):
        if estado is not None:
            self.estado = estado
        if voz is not None:
            self.voz = voz
        if estado is not None or voz is not None:
            self._t.Interval = 40 if self.estado == "trabalhando" or self.voz == "ouvindo" else 550
        if aberta is not None:
            self.aberta = aberta
        self.desenhar()

    # ── desenho ──
    def desenhar(self):
        T, L, m = self.total, self.lado, self.margem
        bmp = Bitmap(T, T, PixelFormat.Format32bppArgb)
        g = Graphics.FromImage(bmp)
        g.SmoothingMode = SmoothingMode.AntiAlias
        g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit
        g.Clear(Color.Transparent)
        # sombra suave embaixo: círculos cada vez maiores e mais fracos
        for k in range(m, 0, -1):
            a = int(16 + 40 * (1 - k / m))
            g.FillEllipse(SolidBrush(Color.FromArgb(a, 0, 0, 0)), float(m - k * 0.5), float(m - k * 0.5 + m * 0.5), float(L + k), float(L + k))
        # bola com luz no alto à esquerda
        p = GraphicsPath()
        p.AddEllipse(float(m), float(m), float(L), float(L))
        br = PathGradientBrush(p)
        br.CenterPoint = PointF(m + L * 0.32, m + L * 0.28)
        br.CenterColor = _cor(LIMA_CLARO)
        br.SurroundColors = [_cor(LIMA_ESC)]
        br.FocusScales = PointF(0.35, 0.35)
        g.FillPath(br, p)
        if self.estado == "trabalhando":
            pen = Pen(_cor(FUNDO, 230), max(2.0, L * 0.06))
            pen.StartCap = pen.EndCap = LineCap.Round
            d = L * 0.07
            g.DrawArc(pen, float(m + d), float(m + d), float(L - 2 * d), float(L - 2 * d), float(self._fase * 360), 90.0)
        # ">" e o cursor (pisca quando a conversa está fechada)
        fonte = Font("Cascadia Mono", float(L * 0.27), FontStyle.Bold)
        tam = g.MeasureString(">", fonte)
        cx, cy = m + L / 2, m + L / 2
        g.DrawString(">", fonte, SolidBrush(_cor(FUNDO)), float(cx - tam.Width * 0.62), float(cy - tam.Height / 2))
        if self.aberta or self._cursor or self.estado == "trabalhando":
            g.FillRectangle(SolidBrush(_cor(FUNDO)), RectangleF(float(cx + L * 0.02), float(cy + L * 0.08), float(L * 0.13), float(L * 0.05)))
        if self.voz == "ouvindo":   # ouvindo o pedido: anel que pulsa por fora
            import math
            k = 0.5 + 0.5 * math.sin(self._fase * 2 * math.pi)
            pen = Pen(_cor(FUNDO, int(120 + 110 * k)), max(2.0, L * (0.05 + 0.04 * k)))
            g.DrawEllipse(pen, float(m + L * 0.04), float(m + L * 0.04), float(L * 0.92), float(L * 0.92))
        elif self.voz == "escutando":   # Ei Kani ligado: pontinho embaixo à esquerda
            r = L * 0.16
            g.FillEllipse(SolidBrush(_cor(FUNDO)), float(m + L * 0.06), float(m + L - r * 1.25), float(r), float(r))
        if self.estado == "pergunta":
            r = L * 0.22
            g.FillEllipse(SolidBrush(_cor(FUNDO)), float(m + L - r * 1.05), float(m - r * 0.05), float(r + 2), float(r + 2))
            g.FillEllipse(SolidBrush(_cor(ALERTA)), float(m + L - r * 0.95), float(m + r * 0.05), float(r - 2), float(r - 2))
        g.Dispose()
        self._entregar(bmp)
        bmp.Dispose()

    def _entregar(self, bmp):
        tela = u32.GetDC(None)
        mem = gdi.CreateCompatibleDC(tela)
        hb = wintypes.HGDIOBJ(int(str(bmp.GetHbitmap(Color.FromArgb(0)))))
        velho = gdi.SelectObject(mem, hb)
        tam, org = wintypes.SIZE(self.total, self.total), wintypes.POINT(0, 0)
        pos = wintypes.POINT(self.x, self.y)
        u32.UpdateLayeredWindow(self.hwnd, tela, ctypes.byref(pos), ctypes.byref(tam), mem, ctypes.byref(org), 0,
                                ctypes.byref(_BLEND(0, 0, 255, 1)), 2)   # ULW_ALPHA, AC_SRC_ALPHA
        gdi.SelectObject(mem, velho)
        gdi.DeleteObject(hb)
        gdi.DeleteDC(mem)
        u32.ReleaseDC(None, tela)

    def fechar(self):
        try:
            self._t.Stop()
            self.form.Close()
        except Exception:
            pass
