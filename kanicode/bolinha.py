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

import rosto

LIMA, LIMA_CLARO, LIMA_ESC, FUNDO, ALERTA = (0xB6, 0xF2, 0x3A), (0xD8, 0xFF, 0x7A), (0x7F, 0xB5, 0x1A), (0x0E, 0x11, 0x10), (0xFF, 0x5A, 0x5F)
BOCHECHA = (0xFF, 0x8F, 0xA3)
u32, gdi = ctypes.windll.user32, ctypes.windll.gdi32
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_TOPMOST = -20, 0x80000, 0x80, 0x40000, 0x8


class _BLEND(ctypes.Structure):
    _fields_ = [("op", ctypes.c_byte), ("flags", ctypes.c_byte), ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_byte)]


u32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
                                    wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF, ctypes.POINTER(_BLEND), wintypes.DWORD]
u32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u32.CreateWindowExW.restype = wintypes.HWND
u32.DestroyWindow.argtypes = [wintypes.HWND]
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

    duracao_saida = 2.8

    def __init__(self, x, y, lado_ui, ao_clicar, ao_mover, ao_direito=None, ao_som=None):
        self.ao_clicar, self.ao_mover, self.ao_direito = ao_clicar, ao_mover, ao_direito
        self.ao_som = ao_som
        self.estado = ""          # "" | "trabalhando" | "pergunta"
        self.aberta = False
        self.voz = ""             # "" | "escutando" (Ei Kani ligado) | "ouvindo" (gravando o pedido) | "pensando"
        self.humor, self._humor_ate = "", 0.0   # "feliz"/"erro" por alguns segundos (fim da tarefa)
        self._mexeu = time.time()                # parada há muito tempo = dorme
        self._fase = 0.0
        self.quem = "claude"      # selo no canto: "claude" | "codex" | "kani"
        self.atividade = ""       # "" | "lendo" | "digitando" | "procurando" | "pensando" (rosto enquanto trabalha)
        self._selos = {}
        self._voo = None
        self._rastro_hwnd = None
        self._deformacao = (1.0, 1.0)
        self._opacidade = 255
        self._humor_inicio = 0.0
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
        self._t.Interval = 120
        self._t.Tick += self._tique
        # Só aparece depois de preparar o primeiro quadro do voo, ainda na origem.

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

    def entrar(self, x, y):
        a = Screen.FromPoint(Point(int(x + self.total / 2), int(y + self.total / 2))).WorkingArea
        self._area_voo = (a.Left, a.Top, a.Width, a.Height)
        origem = (a.Left - self.total, a.Top + self.total)
        self._animar(origem, (int(x), int(y)), False)

    def _animar(self, origem, destino, saindo, ao_terminar=None):
        self._som_voo_tocado = False
        self._duracao_voo = self.duracao_saida if saindo else 3.4
        self._voo = (time.perf_counter(), origem, destino, saindo, ao_terminar)
        self._abrir_rastro()
        self._t.Interval = 16
        self._avancar_voo()
        if not self.form.Visible:
            self.form.Show()
        self._t.Start()

    def _ponto_entrada(self, p, origem, destino):
        if p <= 0:
            return origem
        if p >= 1:
            return destino
        ax, ay, largura, altura = self._area_voo
        raio = min(largura * 0.115, altura * 0.18, 170 * self.escala)
        cx, cy = ax + (largura - self.total) / 2, ay + (altura - self.total) / 2
        topo = (cx, cy - raio)
        # A curva começa e termina devagar; as tangentes coincidem nas junções da volta.
        t = p * p * p * (10 + p * (-15 + 6 * p))
        omega = 2 * math.pi / 0.7
        if 0.15 <= t <= 0.85:
            volta = (t - 0.15) / 0.7
            # Desce ganhando velocidade; na subida, a esfera parece vencer a gravidade.
            volta += 0.4 * (1 - math.cos(2 * math.pi * volta)) / (2 * math.pi)
            angulo = -math.pi / 2 + volta * 2 * math.pi
            return cx + raio * math.cos(angulo), cy + raio * math.sin(angulo)
        tangente = (raio * omega * 0.15, 0)
        curvatura = (raio * 0.4 * omega ** 2 * 0.15 ** 2, raio * omega ** 2 * 0.15 ** 2)
        if t < 0.15:
            return self._curva_voo(t / 0.15, origem, topo, fim_v=tangente, fim_a=curvatura)
        return self._curva_voo((t - 0.85) / 0.15, topo, destino, inicio_v=tangente, inicio_a=curvatura)

    @staticmethod
    def _curva_voo(u, origem, destino, inicio_v=(0, 0), fim_v=(0, 0), inicio_a=(0, 0), fim_a=(0, 0)):
        # Controles de posição, velocidade e curvatura: continuidade também na aceleração.
        ponto = []
        for eixo in (0, 1):
            d = destino[eixo] - origem[eixo]
            v0, v1, a0, a1 = inicio_v[eixo], fim_v[eixo], inicio_a[eixo], fim_a[eixo]
            c3 = 10 * d - 6 * v0 - 4 * v1 - 1.5 * a0 + 0.5 * a1
            c4 = -15 * d + 8 * v0 + 7 * v1 + 1.5 * a0 - a1
            c5 = 6 * d - 3 * v0 - 3 * v1 - 0.5 * a0 + 0.5 * a1
            ponto.append(origem[eixo] + u * (v0 + u * (a0 / 2 + u * (c3 + u * (c4 + u * c5)))))
        return tuple(ponto)

    def _ponto_saida(self, p, origem, destino):
        # A despedida passa pela mesma volta luminosa antes de escapar pelo canto.
        return self._ponto_entrada(p, origem, destino)

    def _avancar_voo(self):
        inicio, origem, destino, saindo, terminou = self._voo
        p = min(1.0, (time.perf_counter() - inicio) / self._duracao_voo)
        if p >= 0.12 and not self._som_voo_tocado:
            self._som_voo_tocado = True
            self._som("saida" if saindo else "entrada")
        caminho = self._ponto_saida if saindo else self._ponto_entrada
        x, y = caminho(p, origem, destino)
        antes = caminho(max(0.0, p - 0.002), origem, destino)
        depois = caminho(min(1.0, p + 0.002), origem, destino)
        dx, dy = depois[0] - antes[0], depois[1] - antes[1]
        velocidade = math.hypot(dx, dy)
        forca = min(1.0, velocidade * 3.4 / self._duracao_voo / max(1, self.lado * 0.16))
        # A compressão acompanha a direção do movimento, inclusive durante a volta.
        if velocidade > 0.001:
            self._deformacao = (1 - 0.34 * forca * (dy / velocidade) ** 2,
                                1 - 0.34 * forca * (dx / velocidade) ** 2)
        else:
            self._deformacao = (1.0, 1.0)
        if not saindo and p > 0.86:
            q = (p - 0.86) / 0.14
            mola = 0.07 * math.sin(q * math.pi * 4) * math.sin(q * math.pi) * (1 - q)
            self._deformacao = (self._deformacao[0] + mola, self._deformacao[1] - mola)
        self.form.Location = Point(round(x), round(y))
        if saindo:
            sumir = max(0.0, min(1.0, (p - 0.8) / 0.2))
            self._opacidade = round(255 * (1 - sumir * sumir * (3 - 2 * sumir)))
        else:
            self._opacidade = round(255 * min(1, p * 5))
        if p >= 1:
            self._fechar_rastro()
            self._voo = None
            self._deformacao = (1.0, 1.0)
            self._opacidade = 255
            self._t.Interval = 40 if self.estado == "trabalhando" or self.voz == "ouvindo" else 120
            if saindo:
                self.fechar()
                if terminou:
                    terminou()
                return
        if self._voo:
            self._desenhar_rastro(p)
        self.desenhar()

    def sair(self, ao_terminar):
        if self._voo and self._voo[3]:
            return
        a = Screen.FromHandle(self.form.Handle).WorkingArea
        self._area_voo = (a.Left, a.Top, a.Width, a.Height)
        self._animar((self.x, self.y), (a.Right + self.total, a.Top - self.total), True, ao_terminar)

    def _som(self, acao):
        try:
            if self.ao_som:
                self.ao_som(acao)
        except Exception:
            pass   # uma falha no dispositivo de áudio não interrompe a animação

    # ── eventos ──
    def _apertou(self, _s, e):
        if self._voo:
            return
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
        if self._voo:
            self._avancar_voo()
            return
        if self.estado == "trabalhando" or self.voz == "ouvindo":
            self._fase = (self._fase + 0.12) % 1.0
        self.desenhar()

    def definir(self, estado=None, aberta=None, voz=None, humor=None, segundos=2.5, quem=None, atividade=None):
        if quem is not None:
            self.quem = quem
        if atividade is not None:
            self.atividade = atividade
        if estado is not None:
            self.estado = estado
        if voz is not None:
            self.voz = voz
        if humor is not None:
            self._humor_inicio = time.time()
            self.humor, self._humor_ate = humor, self._humor_inicio + segundos
            if humor == "concluido":
                self._som("conclusao")
            elif humor == "erro":
                self._som("erro")
        elif estado == "trabalhando" and self.humor == "concluido":
            self.humor = ""
        if (estado is not None or voz is not None) and not self._voo:
            # rápido só com animação contínua (arco/anel); parado, 120 ms basta para piscar
            self._t.Interval = 40 if self.estado == "trabalhando" or self.voz == "ouvindo" else 120
        if aberta is not None:
            self.aberta = aberta
        self._mexeu = time.time()
        self.desenhar()

    def expressao(self):
        """qual cara mostrar agora (rosto.py)"""
        if self.humor and time.time() < self._humor_ate:
            return self.humor
        if self.voz == "ouvindo":
            return "ouvindo"
        if self.voz == "pensando":
            return "pensando"
        if self.voz == "falando":
            return "falando"
        if self.estado == "pergunta":
            return "pergunta"
        if self.estado == "trabalhando":
            return self.atividade or "trabalhando"
        if not self.aberta and time.time() - self._mexeu > 600:
            return "dormindo"
        return "neutro"

    # ── desenho ──
    def desenhar(self):
        T, L, m = self.total, self.lado, self.margem
        bmp = Bitmap(T, T, PixelFormat.Format32bppArgb)
        g = Graphics.FromImage(bmp)
        g.SmoothingMode = SmoothingMode.AntiAlias
        g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit
        g.Clear(Color.Transparent)
        sx, sy = self._deformacao
        g.TranslateTransform(float(T * (1 - sx) / 2), float(T * (1 - sy) / 2))
        g.ScaleTransform(float(sx), float(sy))
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
        if self._voo:
            br.CenterColor = _cor((0xF0, 0xFF, 0xCA))
            br.SurroundColors = [_cor(LIMA)]
        g.FillPath(br, p)
        br.Dispose()
        p.Dispose()
        if self._voo:   # em trânsito é só energia; o rosto e o selo aparecem ao pousar
            g.Dispose()
            self._entregar(bmp)
            bmp.Dispose()
            return
        if self.estado == "trabalhando":
            pen = Pen(_cor(FUNDO, 230), max(2.0, L * 0.06))
            pen.StartCap = pen.EndCap = LineCap.Round
            d = L * 0.07
            g.DrawArc(pen, float(m + d), float(m + d), float(L - 2 * d), float(L - 2 * d), float(self._fase * 360), 90.0)
        # rosto 8-bit (rosto.py): grade 16 × 16 de pixels grandes, sem suavizar
        cel = max(2, int(L * 0.8 / 16))
        x0 = int(m + L / 2 - 8 * cel)
        y0 = int(m + L / 2 - 8 * cel + cel * 0.5)
        g.SmoothingMode = getattr(SmoothingMode, "None")   # "None" é palavra reservada no Python
        pinceis = {"#": SolidBrush(_cor(FUNDO)), "w": SolidBrush(Color.White), "p": SolidBrush(_cor(BOCHECHA)),
                   "r": SolidBrush(_cor(ALERTA))}
        expressao = self.expressao()
        tempo = time.time() - self._humor_inicio if expressao == "concluido" else time.time()
        for y, linha in enumerate(rosto.quadro(expressao, tempo)):
            for x, c in enumerate(linha):
                if c in pinceis:
                    g.FillRectangle(pinceis[c], x0 + x * cel, y0 + y * cel, cel, cel)
        g.SmoothingMode = SmoothingMode.AntiAlias
        if self.voz == "ouvindo":   # ouvindo o pedido: anel que pulsa por fora
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
        self._selo(g, T, L, m)
        if expressao == "concluido":
            self._joinha(g, tempo)
        g.Dispose()
        self._entregar(bmp)
        bmp.Dispose()

    def _joinha(self, g, tempo):
        # Mão em pixels no canto esquerdo: sobe, segura o gesto e recolhe antes de voltar ao rosto normal.
        desenho = ("...##...", "..#ww#..", "..#ww#..", "..#ww###", ".##wwww#",
                   "#w#wwww#", "#w#wwww#", "#w#wwww#", ".######.")
        cel = max(1.5, self.lado * 0.039)
        subida = min(1.0, tempo / 0.3, max(0.0, (2.8 - tempo) / 0.3))
        x0 = self.margem + self.lado * 0.05
        y0 = self.margem + self.lado * 0.54 + (1 - subida) * self.lado * 0.1
        g.SmoothingMode = getattr(SmoothingMode, "None")
        escuro = SolidBrush(_cor(FUNDO, round(255 * subida)))
        claro = SolidBrush(_cor((0xF5, 0xF0, 0xD0), round(255 * subida)))
        try:
            for y, linha in enumerate(desenho):
                for x, c in enumerate(linha):
                    if c != ".":
                        g.FillRectangle(escuro if c == "#" else claro, float(x0 + x * cel), float(y0 + y * cel), float(cel), float(cel))
        finally:
            escuro.Dispose()
            claro.Dispose()
            g.SmoothingMode = SmoothingMode.AntiAlias

    def _selo_kani(self, lado, arq="kani.webp"):
        """logo da Kani (ui/kani.webp) ou do Big Pickle (ui/pickle.webp) redondo, guardado por tamanho"""
        if (arq, lado) not in self._selos:
            import io, os
            from PIL import Image, ImageDraw
            from System.IO import MemoryStream
            im = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", arq)).convert("RGBA")
            w, h = im.size
            q = min(w, h)
            im = im.crop(((w - q) // 2, (h - q) // 2, (w + q) // 2, (h + q) // 2)).resize((lado * 4, lado * 4), Image.LANCZOS)
            masc = Image.new("L", im.size, 0)
            ImageDraw.Draw(masc).ellipse((0, 0, im.size[0] - 1, im.size[1] - 1), fill=255)
            im.putalpha(masc)
            im = im.resize((lado, lado), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            self._selos[(arq, lado)] = Bitmap(Bitmap(MemoryStream(buf.getvalue())))   # cópia: o GDI+ prende o stream do original
        return self._selos[(arq, lado)]

    def _selo(self, g, T, L, m):
        """quem responde, no canto de baixo à direita; Codex usa o mesmo desenho de ui/codex.svg"""
        r = int(L * 0.36)
        x, y = float(m + L - r * 0.92), float(m + L - r * 0.92)
        g.FillEllipse(SolidBrush(_cor(FUNDO)), x - 2, y - 2, float(r + 4), float(r + 4))
        if self.quem in ("kani", "pickle"):
            g.DrawImage(self._selo_kani(r, "pickle.webp" if self.quem == "pickle" else "kani.webp"), x, y, float(r), float(r))
            return
        g.FillEllipse(SolidBrush(_cor((0xF5, 0xF0, 0xE6))), x, y, float(r), float(r))
        if self.quem == "pickle":
            fonte = Font("Segoe UI", max(6.0, r * 0.32), FontStyle.Bold)
            pincel = SolidBrush(_cor((0x25, 0x45, 0x20)))
            g.DrawString("BP", fonte, pincel, float(x + r * 0.08), float(y + r * 0.16))
            fonte.Dispose()
            pincel.Dispose()
            return
        if self.quem == "codex":
            pen = Pen(_cor((0x15, 0x20, 0x1B)), max(1.2, r * 2.5 / 32))
            pen.StartCap = pen.EndCap = LineCap.Round
            for a, b, c, d in ((8, 10, 14, 16), (14, 16, 8, 22), (18, 22, 25, 22)):
                g.DrawLine(pen, x + r * a / 32, y + r * b / 32, x + r * c / 32, y + r * d / 32)
            pen.Dispose()
            return
        cx, cy = x + r / 2, y + r / 2
        pen = Pen(_cor((0xD9, 0x77, 0x57)), max(1.2, r * 0.075))
        pen.StartCap = pen.EndCap = LineCap.Round
        for k in range(12):   # asterisco de raios desiguais, como o logo do Claude
            a = k * math.pi / 6 + 0.2
            c = r * (0.40 if k % 2 else 0.31)
            g.DrawLine(pen, float(cx + math.cos(a) * r * 0.07), float(cy + math.sin(a) * r * 0.07),
                       float(cx + math.cos(a) * c), float(cy + math.sin(a) * c))

    def _abrir_rastro(self):
        if self._rastro_hwnd is not None:
            return
        # Janela visual nativa, desabilitada para entrada: nunca toma foco nem captura cliques.
        estilo = WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | 0x20 | 0x8000000
        h = u32.CreateWindowExW(estilo, "STATIC", "KaniCode — luz do voo", 0x88000000,
                                0, 0, 1, 1, None, None, None, None)   # WS_POPUP | WS_DISABLED
        if not h:
            raise ctypes.WinError()
        self._rastro_hwnd = h
        u32.ShowWindow(h, 4)   # SW_SHOWNOACTIVATE
        u32.SetWindowPos(h, self.hwnd, 0, 0, 0, 0, 0x13)   # atrás da esfera, sem mover nem ativar

    def _fechar_rastro(self):
        if self._rastro_hwnd is not None:
            u32.DestroyWindow(self._rastro_hwnd)
            self._rastro_hwnd = None

    def _desenhar_rastro(self, p):
        _, origem, destino, saindo, _ = self._voo
        duracao = self._duracao_voo
        caminho = self._ponto_saida if saindo else self._ponto_entrada
        pontos = []
        for i in range(32):
            passado = max(0.0, p - (1 - i / 31) * 0.48 / duracao)
            x, y = caminho(passado, origem, destino)
            pontos.append((x + self.total / 2, y + self.total / 2))
        margem = self.lado * 1.15
        x0 = math.floor(min(x for x, y in pontos) - margem)
        y0 = math.floor(min(y for x, y in pontos) - margem)
        largura = math.ceil(max(x for x, y in pontos) + margem - x0)
        altura = math.ceil(max(y for x, y in pontos) + margem - y0)
        bmp = Bitmap(largura, altura, PixelFormat.Format32bppArgb)
        g = Graphics.FromImage(bmp)
        g.SmoothingMode = SmoothingMode.AntiAlias
        g.Clear(Color.Transparent)
        energia = min(1.0, p / 0.07, (1 - p) / 0.12)
        try:
            # Três espessuras formam um rastro contínuo: halo verde, luz e filamento claro.
            for espessura, alfa, cor in ((0.64, 25, LIMA), (0.28, 80, LIMA), (0.055, 210, LIMA_CLARO)):
                for i in range(1, len(pontos)):
                    a, b = pontos[i - 1], pontos[i]
                    pen = Pen(_cor(cor, round(alfa * energia * (i / 31) ** 1.7)), max(1.0, self.lado * espessura * (0.25 + 0.75 * i / 31)))
                    pen.StartCap = pen.EndCap = LineCap.Round
                    try:
                        g.DrawLine(pen, float(a[0] - x0), float(a[1] - y0), float(b[0] - x0), float(b[1] - y0))
                    finally:
                        pen.Dispose()
            # Fragmentos digitais se desprendem da cauda e apagam, sem sorteio a cada quadro.
            for i in range(2, 30):
                x, y = pontos[i]
                idade = 1 - i / 31
                fase = i * 2.399 + p * duracao * 4
                x += math.sin(fase) * self.lado * idade * 0.7
                y += math.cos(fase * 1.3) * self.lado * idade * 0.7
                tamanho = self.escala * (1.5 + (i % 4) * 0.65)
                alfa = round(220 * energia * (1 - idade) * (0.55 + 0.45 * math.sin(fase) ** 2))
                pincel = SolidBrush(_cor(LIMA_CLARO if i % 3 else (0xF0, 0xFF, 0xE4), alfa))
                try:
                    g.FillRectangle(pincel, float(x - x0), float(y - y0), float(tamanho), float(tamanho))
                finally:
                    pincel.Dispose()
            x, y = pontos[-1]
            for i in range(10, 0, -1):
                raio = self.lado * (0.40 + i * 0.045)
                pincel = SolidBrush(_cor(LIMA, round((5 + (10 - i) * 0.8) * energia)))
                try:
                    g.FillEllipse(pincel, float(x - x0 - raio), float(y - y0 - raio), float(raio * 2), float(raio * 2))
                finally:
                    pincel.Dispose()
            self._entregar(bmp, self._rastro_hwnd, (x0, y0), 255)
        finally:
            g.Dispose()
            bmp.Dispose()

    def _entregar(self, bmp, hwnd=None, posicao=None, opacidade=None):
        tela = u32.GetDC(None)
        mem = gdi.CreateCompatibleDC(tela)
        hb = wintypes.HGDIOBJ(int(str(bmp.GetHbitmap(Color.FromArgb(0)))))
        velho = gdi.SelectObject(mem, hb)
        tam, org = wintypes.SIZE(bmp.Width, bmp.Height), wintypes.POINT(0, 0)
        pos = wintypes.POINT(*(posicao if posicao is not None else (self.x, self.y)))
        u32.UpdateLayeredWindow(self.hwnd if hwnd is None else hwnd, tela, ctypes.byref(pos), ctypes.byref(tam), mem, ctypes.byref(org), 0,
                                ctypes.byref(_BLEND(0, 0, self._opacidade if opacidade is None else opacidade, 1)), 2)   # ULW_ALPHA, AC_SRC_ALPHA
        gdi.SelectObject(mem, velho)
        gdi.DeleteObject(hb)
        gdi.DeleteDC(mem)
        u32.ReleaseDC(None, tela)

    def fechar(self):
        try:
            self._t.Stop()
            self._fechar_rastro()
            self.form.Close()
        except Exception:
            pass
