"""KaniCode: conversar com o Claude (e depois Codex/Kani) numa janelinha na área de trabalho.

Processo PRÓPRIO, aberto pelo plugin do KANIVETE (ponte.py) mas independente dele: fechar ou reiniciar o KANIVETE não
fecha o KaniCode. A bolinha verde-limão é nativa do Windows (bolinha.py: sem navegador, sempre por cima, arrastável);
a janela da conversa é uma janela do pywebview (ui/janela.html) que aparece/some com o clique na bolinha.
Uma instância só: o canal de controle (127.0.0.1:PORTA, só aceita "ping", "mostrar" e "sair") avisa a que já está aberta.

Rodar à mão: pyw -3.13 kanicode.py   (ferramentas do navegador: --console; testes por CDP: --agente[=9350])
"""
import json, os, socket, sys, threading, time

import webview

PASTA = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(os.path.splitdrive(PASTA)[0] + os.sep, "Kanivete", "KaniCode")   # nada no C:
ESTADO = os.path.join(DADOS, "estado.json")
PORTA = 47613
BOLA = 64                 # tamanho da bolinha em pixels da interface (o Windows aplica o zoom do monitor)
JW, JH = 500, 660         # janela da conversa, idem
VERSAO = 3
# pasta padrão das conversas: o KANIVETE (ao lado da pasta dos plugins)
PROJETO_PADRAO = os.path.join(os.path.dirname(os.path.dirname(PASTA)), "CANIVETE DO PAILER")


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
        self._limite = _ler_estado().get("limite")   # o último visto (a cota aparece antes da 1ª resposta)
        self._sessao = None
        self._comandos = []

    # ── js_api ──
    def mostrar(self):
        if not self._janela:
            return
        self._janela.move(*self._perto_da_bola())
        self._janela.show()
        self._janela.restore()
        self._aberta = True
        ocupada = bool(self._sessao and self._sessao.ocupada)
        self._na_ui(lambda: self._bola and self._bola.definir(aberta=True, estado="trabalhando" if ocupada else ""))

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
        return {"versao": VERSAO, "pasta": self._pasta(), "fixa": bool(e.get("fixa", True)), "limite": self._limite,
                "ocupada": bool(self._sessao and self._sessao.ocupada), "comandos": self._comandos,
                "modelo": e.get("modelo") or "", "cota_codex": e.get("cota_codex"), "quem": e.get("quem") or "claude"}

    # ── falar direto com um ajudante ("Quem responde": Codex ou Kani) ──
    def quem(self, nome):
        _gravar_estado(quem=nome if nome in ("claude", "codex", "kani") else "claude")
        return True

    def ajudante(self, quem, texto):
        import ajudantes

        def rodar():
            self._bola_estado("trabalhando")
            try:
                if quem == "codex":
                    r = ajudantes.codex(texto, self._pasta(), editar=True, ao_evento=self._evento)
                else:
                    r = ajudantes.kani(texto, ao_evento=self._evento)
                self._para_janela({"t": "ajudante_resposta", "quem": quem, "texto": r["texto"], "ok": r["ok"], "tokens": r["tokens"]})
            except Exception as e:
                self._para_janela({"t": "ajudante_resposta", "quem": quem, "texto": str(e), "ok": False, "tokens": 0})
            self._bola_estado("" if self._aberta else "pergunta")
        threading.Thread(target=rodar, daemon=True).start()
        return True

    def habilidades(self):
        """o que sabemos fazer, para o painel 🧰: guias e ferramentas do KANIVETE (Instructions/mapa.json) + skills"""
        out = {"kanivete": [], "ferramentas": [], "scripts": []}
        try:
            with open(os.path.join(PROJETO_PADRAO, "Instructions", "mapa.json"), encoding="utf-8") as f:
                m = json.load(f)
            out["kanivete"] = []
            for k, v in (m.get("guias") or {}).items():
                # o 1º parágrafo vira o resumo e os títulos das seções entram na busca (achar "legenda" na Legenda Premium)
                g = {"caminho": k, "titulo": v}
                try:
                    with open(os.path.join(PROJETO_PADRAO, k), encoding="utf-8") as f:
                        txt = f.read(60000)
                    linhas = txt.splitlines()
                    g["secoes"] = " ".join(l.lstrip("#").strip() for l in linhas if l.startswith("#"))[:3000]
                    corpo = [l.strip() for l in linhas[1:40] if l.strip() and not l.startswith(("#", "|", "-", "`", ">"))]
                    g["resumo"] = (corpo[0] if corpo else "")[:220]
                except OSError:
                    pass
                out["kanivete"].append(g)
            out["ferramentas"] = [{"id": x.get("id"), "nome": x.get("nome"), "grupo": x.get("grupo"),
                                   "guias": x.get("guias") or [], "testes": x.get("testes") or []} for x in m.get("ferramentas") or []]
            out["scripts"] = [{"caminho": k, "titulo": v} for k, v in (m.get("tools") or {}).items()]
        except Exception as e:
            out["erro"] = str(e)
        return out

    # ── conversa (sessao.py) ──
    def enviar(self, texto):
        texto = (texto or "").strip()
        if not texto:
            return False
        # comandos que o próprio KaniCode resolve (os outros "/" vão para o Claude Code como no terminal)
        cmd, _, arg = texto.partition(" ")
        if cmd in ("/clear", "/nova", "/new"):
            self.nova()
            self._para_janela({"t": "local", "acao": "recarregar"})
            return True
        if cmd == "/pasta":
            self._para_janela({"t": "local", "acao": "pasta"})
            return True
        if cmd == "/model" and arg.strip():
            _gravar_estado(modelo=arg.strip())
            self._encerrar()   # a próxima mensagem abre o Claude Code com o modelo novo (a conversa continua)
            self._para_janela({"t": "local", "acao": "aviso", "texto": f"Modelo trocado para {arg.strip()}."})
            return True
        if not self._sessao:
            from sessao import Sessao
            sid = (_ler_estado().get("sessoes") or {}).get(self._pasta())
            self._sessao = Sessao(self._pasta(), DADOS, self._evento, sessao_id=sid)
            self._sessao.modelo = _ler_estado().get("modelo") or None
        self._bola_estado("trabalhando")
        try:
            self._sessao.enviar(texto)
        except Exception as e:
            self._bola_estado("")
            self._para_janela({"t": "saiu", "erro": str(e)})
            return False
        return True

    def responder(self, pedido_id, permitir, entrada=None):
        """cartão de permissão: Permitir / Recusar"""
        ok = bool(self._sessao and self._sessao.responder(pedido_id, permitir, entrada))
        self._bola_estado("trabalhando")
        return ok

    def preparar(self):
        """abre o Claude Code já ao mostrar a janela (a lista de comandos "/" e a 1ª resposta chegam mais rápido)"""
        if not self._sessao:
            from sessao import Sessao
            sid = (_ler_estado().get("sessoes") or {}).get(self._pasta())
            self._sessao = Sessao(self._pasta(), DADOS, self._evento, sessao_id=sid)
            self._sessao.modelo = _ler_estado().get("modelo") or None
        if not self._sessao.vivo():
            try:
                self._sessao._abrir()
            except Exception as e:
                self._para_janela({"t": "saiu", "erro": str(e)})
        return self._comandos

    def parar(self):
        if self._sessao:
            self._sessao.parar()
        return True

    def nova(self):
        """conversa nova nesta pasta (a anterior continua guardada)"""
        self._encerrar()
        e = _ler_estado()
        ss = e.get("sessoes") or {}
        ss.pop(self._pasta(), None)
        _gravar_estado(sessoes=ss)
        return True

    def historico(self):
        sid = (_ler_estado().get("sessoes") or {}).get(self._pasta())
        if not sid:
            return []
        from sessao import Sessao
        return Sessao(self._pasta(), DADOS, None, sessao_id=sid).historico()

    def escolher_pasta(self):
        r = self._janela.create_file_dialog(webview.FOLDER_DIALOG, directory=self._pasta())
        if not r:
            return None
        nova = r[0] if isinstance(r, (list, tuple)) else r
        if os.path.normcase(nova) != os.path.normcase(self._pasta()):
            self._encerrar()
            _gravar_estado(projeto=nova)
        return nova

    def sair(self):
        self._saindo = True
        self._encerrar()
        self._na_ui(lambda: self._bola and self._bola.fechar())
        try:
            self._janela.destroy()
        except Exception:
            pass

    # ── internos ──
    def _pasta(self):
        p = _ler_estado().get("projeto")
        return p if p and os.path.isdir(p) else PROJETO_PADRAO

    def _encerrar(self):
        if self._sessao:
            s, self._sessao = self._sessao, None
            threading.Thread(target=s.fechar, daemon=True).start()
        self._bola_estado("")

    def _evento(self, ev):
        t = ev.get("t")
        if t == "inicio" and ev.get("sessao"):
            ss = _ler_estado().get("sessoes") or {}
            if ss.get(self._pasta()) != ev["sessao"]:
                ss[self._pasta()] = ev["sessao"]
                _gravar_estado(sessoes=ss)
        elif t == "limite":
            self._limite = {k: ev.get(k) for k in ("h5", "h5_zera", "sem", "sem_zera")}
            _gravar_estado(limite=self._limite)
        elif t == "comandos":
            self._comandos = ev.get("lista") or []
        elif t == "ajudante" and ev.get("fase") == "fim" and ev.get("cota") and ev.get("quem") == "codex":
            _gravar_estado(cota_codex=ev["cota"])   # a cota do Codex aparece de novo ao reabrir
        elif t == "permissao":
            # pergunta para o Pailer: a janela aparece e a bolinha fica com a marca
            self._bola_estado("pergunta")
            if not self._aberta:
                threading.Thread(target=self.mostrar, daemon=True).start()
        elif t in ("fim", "saiu"):
            # terminou: com a janela recolhida, a bolinha fica com a marca de "tem resposta"
            self._bola_estado("" if self._aberta else "pergunta")
            if t == "saiu":
                self._sessao = None
        self._para_janela(ev)

    def _para_janela(self, ev):
        try:
            self._janela.evaluate_js("window.kcEv && kcEv(%s)" % json.dumps(ev, ensure_ascii=False))
        except Exception:
            pass

    def _bola_estado(self, estado):
        self._na_ui(lambda: self._bola and self._bola.definir(estado=estado))

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
                    c.settimeout(3)
                    buf = b""
                    while not buf.endswith(b"\n") and len(buf) < 1_000_000:   # evento pode ser maior que um pacote
                        pedaco = c.recv(65536)
                        if not pedaco:
                            break
                        buf += pedaco
                    cmd = buf.decode("utf-8", "replace").strip()
                except OSError:
                    continue
                if cmd.startswith("evento "):   # andamento dos ajudantes (mcp_equipe.py, aberto pelo Claude Code)
                    c.sendall(b"ok\n")
                    try:
                        self._evento(json.loads(cmd[7:]))
                    except ValueError:
                        pass
                    continue
                c.sendall(b"ok\n" if cmd in ("ping", "mostrar", "sair") else b"?\n")
                if cmd == "mostrar":
                    self.mostrar()
                elif cmd == "sair":
                    self.sair()
                    break
        srv.close()


def main():
    # --agente[=porta]: a janela da conversa aceita CDP em 127.0.0.1 (testes e o agente lendo a tela); nunca por padrão
    ag = next((a for a in sys.argv if a.startswith("--agente")), None)
    if ag:
        porta = ag.split("=", 1)[1] if "=" in ag else "9350"
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={porta} --remote-allow-origins=http://127.0.0.1:{porta}"
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
