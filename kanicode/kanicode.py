"""KaniCode: conversar com o Claude (e depois Codex/Kani) numa janelinha na área de trabalho.

Processo PRÓPRIO, aberto pelo plugin do KANIVETE (ponte.py) mas independente dele: fechar ou reiniciar o KANIVETE não
fecha o KaniCode. A bolinha verde-limão é nativa do Windows (bolinha.py: sem navegador, sempre por cima, arrastável);
a janela da conversa é uma janela do pywebview (ui/janela.html) que aparece/some com o clique na bolinha.
Uma instância só: o canal de controle (127.0.0.1:PORTA, só aceita "ping", "mostrar" e "sair") avisa a que já está aberta.

Rodar à mão: pyw -3.13 kanicode.py   (com as ferramentas do navegador: py -3.13 kanicode.py --console)
"""
import json, os, socket, sys, threading, time

import webview

PASTA = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(os.path.splitdrive(PASTA)[0] + os.sep, "Kanivete", "KaniCode")   # nada no C:
ESTADO = os.path.join(DADOS, "estado.json")
PORTA = 47613
BOLA = 64                 # tamanho da bolinha em pixels da interface (o Windows aplica o zoom do monitor)
JW, JH = 440, 640         # janela da conversa, idem
VERSAO = 1


def _ler_estado():
    try:
        with open(ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _gravar_estado(**kw):
    os.makedirs(DADOS, exist_ok=True)
    e = _ler_estado()
    e.update(kw)
    tmp = ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ESTADO)


def avisar(cmd):
    """manda um comando à instância aberta; devolve a resposta ou None se não houver nenhuma"""
    try:
        with socket.create_connection(("127.0.0.1", PORTA), timeout=1.5) as s:
            s.sendall(cmd.encode() + b"\n")
            return s.recv(64).decode().strip()
    except OSError:
        return None


class App:
    """o que a página da conversa pode chamar (js_api): só os métodos sem _ na frente"""

    def __init__(self):
        self._bola = None
        self._janela = None
        self._aberta = False
        self._saindo = False

    # ── js_api ──
    def mostrar(self):
        if not self._janela:
            return
        self._janela.move(*self._perto_da_bola())
        self._janela.show()
        self._janela.restore()
        self._aberta = True
        self._na_ui(lambda: self._bola and self._bola.definir(aberta=True))

    def esconder(self):
        if self._janela:
            self._janela.hide()
        self._aberta = False
        self._na_ui(lambda: self._bola and self._bola.definir(aberta=False))

    def fixar(self, on):
        """janela sempre por cima (alfinete)"""
        if self._janela:
            self._janela.on_top = bool(on)
        _gravar_estado(fixa=bool(on))
        return bool(on)

    def info(self):
        e = _ler_estado()
        return {"versao": VERSAO, "pasta": e.get("projeto") or "", "fixa": bool(e.get("fixa", True))}

    def sair(self):
        self._saindo = True
        self._na_ui(lambda: self._bola and self._bola.fechar())
        try:
            self._janela.destroy()
        except Exception:
            pass

    # ── internos ──
    def _na_ui(self, fn):
        """roda fn na thread da interface do Windows (a bolinha só pode ser mexida lá)"""
        try:
            from System import Action
            self._janela.native.Invoke(Action(fn))
        except Exception:
            pass

    def _clique(self):
        # chamado na thread da interface: abrir/esconder a janela do pywebview sai dela (senão trava esperando)
        threading.Thread(target=self.esconder if self._aberta else self.mostrar, daemon=True).start()

    def _movida(self, x, y):
        _gravar_estado(bola_px=[int(x), int(y)])
        if self._aberta:
            threading.Thread(target=lambda: self._janela.move(*self._perto_da_bola()), daemon=True).start()

    def _perto_da_bola(self):
        """posição da janela ao lado da bolinha, inteira na tela (em pixels da interface, como o pywebview quer)"""
        b = self._bola
        k = b.escala
        ax, ay, aw, ah = (v / k for v in b.area_util())
        bx, by, bl = b.x / k, b.y / k, b.total / k
        x = bx - JW - 10 if bx - JW - 10 >= ax else bx + bl + 10
        y = by + bl - JH
        x = max(ax + 8, min(x, ax + aw - JW - 8))
        y = max(ay + 8, min(y, ay + ah - JH - 8))
        return int(x), int(y)

    def _criar_bola(self):
        from bolinha import Bolinha
        e = _ler_estado()
        x, y = e.get("bola_px") or (None, None)

        def criar():
            b = Bolinha(-10000, -10000, BOLA, self._clique, self._movida, ao_direito=self._clique)
            ax, ay, aw, ah = b.area_util()
            if x is None:
                px, py_ = ax + aw - b.total - round(24 * b.escala), ay + ah - b.total - round(24 * b.escala)
            else:   # a posição guardada pode ser de um monitor que saiu: traz para dentro da área útil
                px, py_ = x, y
            from System.Drawing import Point
            from System.Windows.Forms import Screen
            dentro = any(s.WorkingArea.Contains(Point(int(px + b.total / 2), int(py_ + b.total / 2))) for s in Screen.AllScreens)
            if not dentro:
                px, py_ = ax + aw - b.total - 24, ay + ah - b.total - 24
            b.form.Location = Point(int(px), int(py_))
            b.desenhar()
            self._bola = b
        for _ in range(100):   # a janela da conversa (escondida) precisa existir para dar a thread da interface
            try:
                self._janela.native.Handle
                break
            except Exception:
                time.sleep(0.05)
        self._na_ui(criar)

    def _fechando(self):
        # Alt+F4 / fechar na janela da conversa: só esconde (a bolinha continua); sair de verdade = botão Sair
        if self._saindo:
            return True
        threading.Thread(target=self.esconder, daemon=True).start()
        return False

    def _servir(self, srv):
        while not self._saindo:
            try:
                c, _ = srv.accept()
            except OSError:
                break
            with c:
                try:
                    cmd = c.recv(64).decode().strip()
                except OSError:
                    continue
                c.sendall(b"ok\n" if cmd in ("ping", "mostrar", "sair") else b"?\n")
                if cmd == "mostrar":
                    self.mostrar()
                elif cmd == "sair":
                    self.sair()
                    break
        srv.close()


def main():
    if avisar("mostrar"):   # já existe uma aberta: ela aparece e esta sai
        return
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", PORTA))   # a porta é a trava de instância única
        srv.listen(4)
    except OSError:
        return
    app = App()
    e = _ler_estado()
    app._janela = webview.create_window("KaniCode", os.path.join(PASTA, "ui", "janela.html"), js_api=app, width=JW, height=JH,
                                        hidden=True, frameless=True, easy_drag=False, on_top=bool(e.get("fixa", True)),
                                        resizable=True, min_size=(340, 420), background_color="#0E1110")
    app._janela.events.closing += app._fechando
    threading.Thread(target=app._servir, args=(srv,), daemon=True).start()
    os.makedirs(DADOS, exist_ok=True)
    webview.start(app._criar_bola, debug="--console" in sys.argv, storage_path=os.path.join(DADOS, "webview"))


if __name__ == "__main__":
    main()
