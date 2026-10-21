"""KaniCode: conversar com o Claude (e depois Codex/Kani) numa janelinha na área de trabalho.

Processo PRÓPRIO, aberto pelo plugin do KANIVETE (ponte.py) mas independente dele: fechar ou reiniciar o KANIVETE não
fecha o KaniCode. A bolinha verde-limão é nativa do Windows (bolinha.py: sem navegador, sempre por cima, arrastável);
a janela da conversa é uma janela do pywebview (ui/janela.html) que aparece/some com o clique na bolinha.
Uma instância só: o canal de controle (127.0.0.1:PORTA, só aceita "ping", "mostrar" e "sair") avisa a que já está aberta.

Rodar à mão: pyw -3.13 kanicode.py   (ferramentas do navegador: --console; testes por CDP: --agente[=9350])
"""
import json, os, re, socket, sys, threading, time

import webview

PASTA = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(os.path.splitdrive(PASTA)[0] + os.sep, "Kanivete", "KaniCode")   # nada no C:
ESTADO = os.path.join(DADOS, "estado.json")
PORTA = 47613
BOLA = 64                 # tamanho da bolinha em pixels da interface (o Windows aplica o zoom do monitor)
JW, JH = 550, 660         # janela da conversa, idem (+50 do painel das contas, à esquerda); o Pailer estica pelas bordas
MIN_W, MIN_H = 340, 420
VERSAO = 3
AUMID = "Pandalab.KaniCode"   # o mesmo dos atalhos (atalhos.py): ícone fixado na barra = esta janela
# pasta padrão das conversas: o KANIVETE (ao lado da pasta dos plugins)
# (realpath: aberto pela junção D:\Kanivete\Plugins, o "ao lado" seria D:\Kanivete — pasta que não existe, WinError 267)
PROJETO_PADRAO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), "CANIVETE DO PAILER")


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


def _tamanho():
    """tamanho guardado da janela (pixels da interface) ou o de fábrica"""
    t = _ler_estado().get("tamanho")
    return (max(MIN_W, int(t[0])), max(MIN_H, int(t[1]))) if t else (JW, JH)


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
        self._pendente = None      # "recarregar"/"reiniciar" pedido no meio de uma resposta: roda quando ela terminar
        self._carregado = time.time()   # para o "atualizar" saber o que mudou depois de aberto

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

    # ── tamanho: a janela é sem moldura, então as bordas são desenhadas no HTML e o redimensionar vem por aqui ──
    def _hwnd(self):
        return int(self._janela.native.Handle.ToInt64())

    def tam_inicio(self):
        """retângulo atual da janela em pixels físicos [x, y, w, h]"""
        import ctypes
        from ctypes import wintypes
        r = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(self._hwnd(), ctypes.byref(r))
        return [r.left, r.top, r.right - r.left, r.bottom - r.top]

    def tam_mudar(self, x, y, w, h):
        import ctypes
        k = self._bola.escala if self._bola else 1
        w, h = max(int(w), int(MIN_W * k)), max(int(h), int(MIN_H * k))
        ctypes.windll.user32.SetWindowPos(self._hwnd(), 0, int(x), int(y), w, h, 0x0004 | 0x0010)   # NOZORDER | NOACTIVATE

    def tam_fim(self, extra=0):
        """guarda o tamanho sem as colunas laterais abertas (extra = quanto elas somam agora)"""
        k = self._bola.escala if self._bola else 1
        _, _, w, h = self.tam_inicio()
        _gravar_estado(tamanho=[round(w / k - float(extra or 0)), round(h / k)])

    def _area(self):
        """área útil do monitor da janela (pixels físicos): esquerda, direita"""
        import ctypes
        from ctypes import wintypes

        class MI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        mi = MI(); mi.cbSize = ctypes.sizeof(MI)
        mon = ctypes.windll.user32.MonitorFromWindow(self._hwnd(), 2)
        ctypes.windll.user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        return mi.rcWork.left, mi.rcWork.right

    def crescer(self, esq, dir):
        """abre/fecha uma coluna lateral PARA FORA: a janela ganha (ou perde) esq px à esquerda e dir px à direita,
        num deslize curto, sem sair da tela"""
        import ctypes
        k = self._bola.escala if self._bola else 1
        x, y, w, h = self.tam_inicio()
        de, dd = int(float(esq) * k), int(float(dir) * k)
        nx, nw = x - de, max(int(MIN_W * k), w + de + dd)
        try:
            l, r = self._area()
            if nx + nw > r:
                nx = r - nw
            nx = max(l, nx)
        except Exception:
            pass
        for i in range(1, 8):
            t = i / 7
            t = 1 - (1 - t) ** 3
            ctypes.windll.user32.SetWindowPos(self._hwnd(), 0, int(x + (nx - x) * t), y, int(w + (nw - w) * t), h, 0x0004 | 0x0010)
            time.sleep(0.012)
        return True

    def tarefas_ler(self, arquivos):
        """andamento das tarefas em segundo plano do Claude Code: última linha da saída e o código de saída quando acaba"""
        r = {}
        for a in (arquivos or [])[:20]:
            if not str(a).lower().endswith(".output"):
                continue
            try:
                tam = os.path.getsize(a)
                with open(a, "rb") as f:
                    f.seek(max(0, tam - 8192))
                    fim = f.read().decode("utf-8", "replace")
            except OSError:
                r[a] = {"falta": True}
                continue
            m = re.search(r"\[exited with code (-?\d+)\]\s*$", fim)
            linhas = [l.strip() for l in re.sub(r"\[exited with code -?\d+\]\s*$", "", fim).replace("\r", "\n").split("\n") if l.strip()]
            r[a] = {"tail": "\n".join(linhas[-3:])[-400:], "fim": int(m.group(1)) if m else None, "kb": round(tam / 1024)}
        return r

    def expandir(self, on):
        """⤢ janela grande (diffs e saídas inteiros): ocupa quase o monitor inteiro; de novo = volta ao retângulo de antes"""
        import ctypes
        from ctypes import wintypes

        class MI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        if on:
            self._antes = self.tam_inicio()
            mi = MI(); mi.cbSize = ctypes.sizeof(MI)
            ctypes.windll.user32.GetMonitorInfoW(ctypes.windll.user32.MonitorFromWindow(self._hwnd(), 2), ctypes.byref(mi))
            a = mi.rcWork
            k = self._bola.escala if self._bola else 1
            m = int(24 * k)
            w = min(int(1280 * k), a.right - a.left - 2 * m)
            r = [a.left + (a.right - a.left - w) // 2, a.top + m, w, a.bottom - a.top - 2 * m]
        else:
            r = getattr(self, "_antes", None)
            if not r:
                return False
            self._antes = None
        ctypes.windll.user32.SetWindowPos(self._hwnd(), 0, *map(int, r), 0x0004 | 0x0010)
        return bool(on)

    def tam_padrao(self):
        """duplo clique no canto: volta ao tamanho de fábrica, ao lado da bolinha"""
        _gravar_estado(tamanho=None)
        self._janela.resize(JW, JH)
        self._janela.move(*self._perto_da_bola())

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
                "modelo": e.get("modelo") or "", "cota_codex": e.get("cota_codex"), "quem": e.get("quem") or "claude",
                "modo": getattr(self, "_modo", "auto")}

    # ── contas do Claude (contas.py): salvas, com apelido e e-mail; troca MANUAL ──
    def _contas(self):
        e = _ler_estado()
        lista = e.get("contas") or []
        if not any(c["id"] == "principal" for c in lista):
            lista.insert(0, {"id": "principal", "apelido": "Principal"})
        return lista, e.get("conta") or "principal"

    def contas_listar(self):
        lista, ativa = self._contas()
        return {"lista": lista, "ativa": ativa}

    def conta_atualizar(self, conta_id=None):
        """lê e-mail, plano e cotas (sem gastar tokens) de uma conta ou de todas; guarda no estado"""
        import contas
        lista, ativa = self._contas()
        for c in lista:
            if conta_id and c["id"] != conta_id:
                continue
            st = contas.status(c["id"])
            c.update(email=st.get("email", ""), plano=st.get("plano", ""), logado=st.get("logado", False))
            if c["logado"]:
                c["cotas"] = contas.cotas(c["id"])
        # a mesma conta duas vezes (mesmo e-mail): mostra uma só — a em uso; senão uma salva (a "Principal" segue o
        # login do PC e pode mudar por fora; as salvas têm login próprio e ficam). Nada é apagado: as outras só somem.
        por = {}
        for c in lista:
            c.pop("igual", None)
            c.pop("oculta", None)
            if c.get("logado") and c.get("email"):
                por.setdefault(c["email"].lower(), []).append(c)
        for grupo in por.values():
            if len(grupo) > 1:
                fica = next((x for x in grupo if x["id"] == ativa), None) \
                    or next((x for x in grupo if x["id"] != "principal"), grupo[0])
                fica["cotas"] = max(grupo, key=lambda x: (x.get("cotas") or {}).get("lido") or 0).get("cotas")
                for c in grupo:
                    if c is not fica:
                        c["oculta"] = True
        _gravar_estado(contas=lista)
        return {"lista": lista, "ativa": ativa}

    def conta_adicionar(self, apelido):
        import contas, re as _re
        apelido = (apelido or "").strip() or "Conta"
        lista, ativa = self._contas()
        base = _re.sub(r"[^a-z0-9]+", "-", apelido.lower()).strip("-") or "conta"
        cid, n = base, 2
        while any(c["id"] == cid for c in lista) or cid == "principal":
            cid, n = f"{base}-{n}", n + 1
        lista.append({"id": cid, "apelido": apelido})
        _gravar_estado(contas=lista)
        contas.abrir_login(cid, apelido)
        return {"id": cid, "lista": lista, "ativa": ativa}

    def conta_entrar_de_novo(self, conta_id):
        import contas
        lista, _ = self._contas()
        c = next((x for x in lista if x["id"] == conta_id), None)
        return bool(c) and contas.abrir_login(conta_id, c["apelido"])

    def conta_renomear(self, conta_id, apelido):
        lista, ativa = self._contas()
        for c in lista:
            if c["id"] == conta_id and (apelido or "").strip():
                c["apelido"] = apelido.strip()[:40]
        _gravar_estado(contas=lista)
        return {"lista": lista, "ativa": ativa}

    def conta_remover(self, conta_id):
        import contas
        lista, ativa = self._contas()
        if conta_id == "principal":
            return {"lista": lista, "ativa": ativa}
        contas.remover(conta_id)
        lista = [c for c in lista if c["id"] != conta_id]
        if ativa == conta_id:
            ativa = "principal"
            self._encerrar()
        _gravar_estado(contas=lista, conta=ativa)
        return {"lista": lista, "ativa": ativa}

    def conta_usar(self, conta_id):
        """troca manual: a próxima mensagem já vai pela conta escolhida, na MESMA conversa"""
        lista, ativa = self._contas()
        if conta_id == ativa or not any(c["id"] == conta_id for c in lista):
            return {"lista": lista, "ativa": ativa}
        if self._sessao and self._sessao.ocupada:
            raise RuntimeError("espere a resposta terminar para trocar de conta")
        self._encerrar()
        c = next(c for c in lista if c["id"] == conta_id)
        self._limite = c.get("cotas")
        _gravar_estado(conta=conta_id, limite=self._limite)
        return {"lista": lista, "ativa": conta_id}

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
    def enviar(self, texto, imagens=None):
        texto = (texto or "").strip()
        if not texto and not imagens:
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
            self._sessao.conta = _ler_estado().get("conta") or None
            self._sessao.modo = getattr(self, "_modo", "auto")
        self._bola_estado("trabalhando")
        try:
            self._sessao.enviar(texto, imagens)
        except Exception as e:
            self._bola_estado("")
            self._para_janela({"t": "saiu", "erro": str(e)})
            return False
        return True

    def responder_pergunta(self, pedido_id, entrada, respostas):
        """múltipla escolha: {texto da pergunta: rótulo escolhido (vários = separados por vírgula)}"""
        ok = bool(self._sessao and self._sessao.responder_pergunta(pedido_id, entrada, respostas))
        self._bola_estado("trabalhando")
        return ok

    def responder(self, pedido_id, permitir, entrada=None):
        """cartão de permissão: Permitir / Recusar"""
        ok = bool(self._sessao and self._sessao.responder(pedido_id, permitir, entrada))
        self._bola_estado("trabalhando")
        return ok

    def sempre(self, add=None, tirar=None):
        """"Permitir sempre" do cartão (git push, git commit…): lista guardada em DADOS/sempre.json"""
        import sessao
        return sessao.sempre(DADOS, add, tirar)

    def preparar(self):
        """abre o Claude Code já ao mostrar a janela (a lista de comandos "/" e a 1ª resposta chegam mais rápido)"""
        if not self._sessao:
            from sessao import Sessao
            sid = (_ler_estado().get("sessoes") or {}).get(self._pasta())
            self._sessao = Sessao(self._pasta(), DADOS, self._evento, sessao_id=sid)
            self._sessao.modelo = _ler_estado().get("modelo") or None
            self._sessao.conta = _ler_estado().get("conta") or None
            self._sessao.modo = getattr(self, "_modo", "auto")
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

    _IMG = (".png", ".jpg", ".jpeg", ".webp")

    def miniatura(self, caminho, lado=900):
        """print na conversa: a imagem reduzida como dataURL (None se não for imagem ou não existir)"""
        try:
            if not caminho.lower().endswith(self._IMG) or not os.path.isfile(caminho):
                return None
            import base64, io
            from PIL import Image
            with Image.open(caminho) as im:
                im.thumbnail((lado, lado))
                buf = io.BytesIO()
                if im.mode in ("RGBA", "LA", "P"):
                    im.convert("RGBA").save(buf, "PNG", optimize=True)
                    tipo = "png"
                else:
                    im.convert("RGB").save(buf, "JPEG", quality=85)
                    tipo = "jpeg"
            return f"data:image/{tipo};base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None

    def abrir_imagem(self, caminho):
        if caminho.lower().endswith(self._IMG) and os.path.isfile(caminho):
            os.startfile(caminho)
        return True

    def modo(self, modo):
        """botão Planejar: 'plan' = o Claude só planeja e pede aprovação; 'auto' = trabalha normal"""
        modo = "plan" if modo == "plan" else "auto"
        self._modo = modo
        if self._sessao:
            self._sessao.definir_modo(modo)
        return modo

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
        try:   # a Kani direta roda neste processo: sai da placa de vídeo junto
            import ajudantes
            ajudantes.kani_parar()
        except Exception:
            pass
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
            # a cota ao vivo também vai para a conta em uso (o painel de contas mostra sem consultar)
            lista, ativa = self._contas()
            for c in lista:
                if c["id"] == ativa:
                    c["cotas"] = dict(self._limite, lido=int(time.time()))
            _gravar_estado(limite=self._limite, contas=lista)
        elif t == "comandos":
            self._comandos = ev.get("lista") or []
        elif t == "ajudante" and ev.get("fase") == "fim" and ev.get("cota") and ev.get("quem") == "codex":
            _gravar_estado(cota_codex=ev["cota"])   # a cota do Codex aparece de novo ao reabrir
        elif t in ("permissao", "pergunta"):
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
        if t in ("fim", "saiu") and self._pendente:
            acao, self._pendente = self._pendente, None
            threading.Timer(1.5, self._atualizar, args=(acao,)).start()   # a última bolha chega à tela antes

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
        try:   # o tamanho de agora (com as colunas laterais abertas a janela é mais larga)
            _, _, fw, fh = self.tam_inicio()
            JW, JH = fw / k, fh / k
        except Exception:
            JW, JH = _tamanho()
        JW, JH = min(JW, aw - 16), min(JH, ah - 16)
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

    # ── atualizar depois de um ajuste no código do KaniCode (recarregar.py) ──
    def _o_que_mudou(self):
        """'reiniciar' se algum .py mudou depois de aberto; 'recarregar' se só a janela (ui/, .css/.js); senão None"""
        py = ui = False
        for raiz, _, nomes in os.walk(PASTA):
            if "__pycache__" in raiz:
                continue
            for n in nomes:
                try:
                    novo = os.path.getmtime(os.path.join(raiz, n)) > self._carregado
                except OSError:
                    continue
                if novo and n.endswith(".py"):
                    py = True
                elif novo and n.endswith((".html", ".css", ".js")):
                    ui = True
        return "reiniciar" if py else "recarregar" if ui else None

    def _pedir(self, acao):
        """acao: atualizar (decide sozinho) | recarregar | reiniciar. No meio de uma resposta, espera ela terminar."""
        if acao == "atualizar":
            acao = self._o_que_mudou()
            if not acao:
                return "nada"
        if self._sessao and self._sessao.ocupada:
            if self._pendente != "reiniciar":
                self._pendente = acao
            return "depois:" + acao
        threading.Thread(target=self._atualizar, args=(acao,), daemon=True).start()
        return acao

    def _atualizar(self, acao):
        if acao == "recarregar":
            self._carregado = time.time()
            try:
                self._janela.evaluate_js("setTimeout(() => location.reload(), 50)")
            except Exception:
                pass
            return
        # reiniciar: abre um KaniCode novo (que espera este soltar a porta) e este sai; a conversa continua (--resume)
        import subprocess
        args = [a for a in sys.argv[1:] if a not in ("--reaberto", "--abrir")] + ["--reaberto"] + (["--abrir"] if self._aberta else [])
        subprocess.Popen([sys.executable, os.path.abspath(__file__), *args], cwd=PASTA, close_fds=True,
                         creationflags=0x00000008 | 0x00000200)
        self.sair()

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
                if cmd in ("atualizar", "recarregar", "reiniciar"):
                    c.sendall(self._pedir(cmd).encode() + b"\n")
                    if self._saindo:
                        break
                    continue
                c.sendall(b"ok\n" if cmd in ("ping", "mostrar", "sair") else b"?\n")
                if cmd == "mostrar":
                    self.mostrar()
                elif cmd == "sair":
                    self.sair()
                    break
        srv.close()


def main():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(AUMID)
    except Exception:
        pass
    # --agente[=porta]: a janela da conversa aceita CDP em 127.0.0.1 (testes e o agente lendo a tela); nunca por padrão
    ag = next((a for a in sys.argv if a.startswith("--agente")), None)
    if ag:
        porta = ag.split("=", 1)[1] if "=" in ag else "9350"
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={porta} --remote-allow-origins=http://127.0.0.1:{porta}"
    reaberto = "--reaberto" in sys.argv   # reiniciado pelo _atualizar: espera o anterior soltar a porta
    if not reaberto and avisar("mostrar"):   # já existe uma aberta: ela aparece e esta sai
        return
    srv = None
    for _ in range(100 if reaberto else 1):
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.bind(("127.0.0.1", PORTA))   # a porta é a trava de instância única
            srv.listen(4)
            break
        except OSError:
            srv.close()
            srv = None
            time.sleep(0.15)
    if not srv:
        return
    app = App()
    e = _ler_estado()
    w, h = _tamanho()
    app._janela = webview.create_window("KaniCode", os.path.join(PASTA, "ui", "janela.html"), js_api=app, width=w, height=h,
                                        hidden=True, frameless=True, easy_drag=False, on_top=bool(e.get("fixa", True)),
                                        resizable=True, min_size=(MIN_W, MIN_H), background_color="#0E1110")
    app._janela.events.closing += app._fechando
    threading.Thread(target=app._servir, args=(srv,), daemon=True).start()
    os.makedirs(DADOS, exist_ok=True)

    def comecar():
        app._criar_bola()
        if "--abrir" in sys.argv:   # reiniciado com a janela aberta: volta aberta
            threading.Timer(0.8, app.mostrar).start()
    webview.start(comecar, debug="--console" in sys.argv, storage_path=os.path.join(DADOS, "webview"))


if __name__ == "__main__":
    main()
