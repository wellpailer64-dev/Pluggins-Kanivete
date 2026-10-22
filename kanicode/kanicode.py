"""KaniCode: conversar com o Claude (e depois Codex/Kani) numa janelinha na área de trabalho.

Processo PRÓPRIO, aberto pelo plugin do KANIVETE (ponte.py) mas independente dele: fechar ou reiniciar o KANIVETE não
fecha o KaniCode. A bolinha verde-limão é nativa do Windows (bolinha.py: sem navegador, sempre por cima, arrastável);
a janela da conversa é uma janela do pywebview (ui/janela.html) que aparece/some com o clique na bolinha.
Uma instância só: o canal de controle (127.0.0.1:PORTA, só aceita "ping", "mostrar" e "sair") avisa a que já está aberta.

Rodar à mão: pyw -3.13 kanicode.py   (ferramentas do navegador: --console; testes por CDP: --agente[=9350])
"""
import json, os, re, socket, sys, threading, time
from collections import deque

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
_ESTADO_TRAVA = threading.RLock()


def _ler_estado():
    try:
        with open(ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _gravar_estado(**kw):
    with _ESTADO_TRAVA:
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
        self._ajudante_trava = threading.Lock()
        self._ajudante_ativo = None
        self._codex_parar = None
        self._comandos = []
        self._pendente = None      # "recarregar"/"reiniciar" pedido no meio de uma resposta: roda quando ela terminar
        self._carregado = time.time()   # para o "atualizar" saber o que mudou depois de aberto
        self._voz = None           # voz.py: "Ei Kani" + fala para texto
        self._fala = None          # fala.py: resposta lida em voz alta (pedido por voz com a janela fechada)
        self._por_voz = False
        self._estado_voz = ""
        self._sons_ativos = bool(_ler_estado().get("sons_bolinha", True))
        self._codex_comentario = ""
        self._codex_lidos = set()
        self._codex_falando = False
        self._prontidao_pendente = None
        self._respondendo = False  # resposta do Claude chegando (para falar o resto se a janela for minimizada)
        self._resposta = ""        # o texto da mensagem atual da resposta, desde o último "texto_novo"
        self._pend = {}            # permissões/perguntas abertas, por id (para o celular, movel.py)

    # ── js_api ──
    def mostrar(self):
        if not self._janela:
            return
        self._janela.move(*self._perto_da_bola())
        self._janela.show()
        self._janela.restore()
        self._aberta = True
        ocupada = self._ocupada()
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

    # ── voz (voz.py): "Ei Kani" acorda, a fala vai para a conversa ──
    def voz(self, on=None):
        """liga/desliga o Ei Kani (None = só diz o estado). Fica gravado: abre ligado da próxima vez."""
        if on is None:
            return {"on": bool(self._voz and self._voz.ligada)}
        if on:
            try:
                if not self._voz:
                    from voz import Voz
                    self._voz = Voz(self._voz_acordou, self._voz_texto, self._voz_estado)
                self._voz.ligar()
                threading.Thread(target=self._fala_obj().carregar, daemon=True).start()   # 1ª resposta sem espera
            except Exception as e:
                return {"on": False, "erro": str(e)}
        elif self._voz:
            self._voz.desligar()
            if self._fala:
                self._fala.soltar()
            self._na_ui(lambda: self._bola and self._bola.definir(voz=""))
        _gravar_estado(voz=bool(on))
        return {"on": bool(on)}

    def ouvir(self, fim=False):
        """botão do microfone na caixa de texto: ouve um pedido sem "Ei Kani" (fim=True: terminou de falar)"""
        try:
            if fim:
                if self._voz:
                    self._voz.terminar()
                return {"ok": True}
            if not self._voz:
                from voz import Voz
                self._voz = Voz(self._voz_acordou, self._voz_texto, self._voz_estado)
            self._voz.escutar()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    def _voz_acordou(self):
        # a janela fica como está: fechada, a conversa é toda por voz (a bolinha mostra o rosto ouvindo)
        if self._fala:
            self._fala.parar()   # "Ei Kani" no meio da fala = interromper

    def _voz_estado(self, e):
        self._estado_voz = e
        if e in ("ouvindo", "transcrevendo"):
            from sons_bolinha import parar
            parar()
        b = {"escutando": "escutando", "ouvindo": "ouvindo", "transcrevendo": "pensando"}.get(e, "")
        self._na_ui(lambda: self._bola and self._bola.definir(voz=b))
        self._para_janela({"t": "voz", "fase": e})

    def _voz_texto(self, texto):
        # pedido por voz com a janela fechada: a resposta volta falada (fala.py), frase a frase enquanto é escrita
        self._por_voz = not self._aberta
        self._para_janela({"t": "voz", "fase": "texto", "texto": texto})

    def _fala_obj(self):
        if not self._fala:
            from fala import Fala
            self._fala = Fala(self._fala_estado)
        return self._fala

    def _fala_estado(self, e):
        if e == "falando":
            from sons_bolinha import parar
            parar()
        if e == "fim":   # terminou de falar a resposta: ouve o próximo pedido sem "Ei Kani" (janela fechada)
            if not self._aberta and not self._ocupada():   # chat minimizado = conversa por voz, mesmo com o Ei Kani desligado
                try:
                    if not self._voz:
                        from voz import Voz
                        self._voz = Voz(self._voz_acordou, self._voz_texto, self._voz_estado)
                    from voz import SEGUIR_S
                    self._voz.escutar(SEGUIR_S)
                except Exception:
                    pass
            return
        b = "falando" if e == "falando" else ("escutando" if self._voz and self._voz.ligada else "")
        self._na_ui(lambda: self._bola and self._bola.definir(voz=b))

    def esconder(self):
        if self._janela:
            self._janela.hide()
        self._aberta = False
        self._na_ui(lambda: self._bola and self._bola.definir(aberta=False))
        if self._ajudante_ativo == "codex":
            self._codex_ler(self._codex_comentario)
        # minimizou com a resposta ainda chegando (pedido escrito): o resto vira voz, a partir da mensagem atual
        if self._respondendo and not self._por_voz:
            try:
                f = self._fala_obj()
                self._por_voz = True
                f.novo()
                if self._resposta:
                    f.pedaco(self._resposta)
            except Exception:
                self._por_voz = False

    def sons_acoes(self, on=None):
        if on is not None:
            self._sons_ativos = bool(on)
            _gravar_estado(sons_bolinha=self._sons_ativos)
            if not self._sons_ativos:
                from sons_bolinha import parar
                parar()
        return self._sons_ativos

    def _som_bolinha(self, acao):
        if not self._sons_ativos or self._estado_voz in ("ouvindo", "transcrevendo"):
            return False
        if self._fala and self._fala.falando:
            return False
        from sons_bolinha import tocar
        return tocar(acao)

    def fixar(self, on):
        """janela sempre por cima (alfinete)"""
        if self._janela:
            self._janela.on_top = bool(on)
        _gravar_estado(fixa=bool(on))
        return bool(on)

    def info(self):
        e = _ler_estado()
        return {"versao": VERSAO, "pasta": self._pasta(), "fixa": bool(e.get("fixa", True)), "limite": self._limite,
                "ocupada": self._ocupada(), "comandos": self._comandos,
                "modelo": e.get("modelo") or "", "cota_codex": e.get("cota_codex"), "quem": e.get("quem") or "claude",
                "modo": getattr(self, "_modo", "auto")}

    def codex_limites(self, forcar=False):
        import codex_conta
        r = codex_conta.consultar(bool(forcar))
        if r.get("ok"):
            _gravar_estado(cota_codex=r["cota"])
        return r

    def codex_redefinir(self, tentativa, credito=""):
        import codex_conta
        r = codex_conta.redefinir(tentativa, credito)
        if r.get("cota"):
            _gravar_estado(cota_codex=r["cota"])
        return r

    def codigo_revisar(self):
        import codigo_agente
        if self._ocupada():
            return {"ok": False, "mensagem": "Acompanhe os passos na conversa; espere a tarefa terminar para revisar o diff."}
        agente = _ler_estado().get("quem")
        try:
            with codigo_agente.TRAVA:
                ctx = codigo_agente.Contexto(self._pasta(), agente).carregar()
                r = ctx.revisar()
                r["verificacao"] = ctx.verificar()
                r["ok"] = True
                r["pode_aplicar"] = bool(r["arquivos"]) and not r["aplicada"] and r["verificacao"]["ok"] and getattr(self, "_modo", "auto") != "plan"
                if r.get("testes") and not r["testes"]["ok"]:
                    r["pode_aplicar"] = False
                return r
        except (ValueError, OSError) as e:
            return {"ok": False, "mensagem": str(e)}

    def codigo_aplicar(self, agente, revisao):
        import codigo_agente
        if self._ocupada() or getattr(self, "_modo", "auto") == "plan":
            return {"ok": False, "mensagem": "Termine a tarefa e saia de Planejar antes de aplicar."}
        if agente != _ler_estado().get("quem"):
            return {"ok": False, "mensagem": "O agente selecionado mudou; abra a revisão novamente."}
        try:
            with codigo_agente.TRAVA:
                return codigo_agente.Contexto(self._pasta(), agente).carregar().aplicar(str(revisao))
        except (ValueError, OSError) as e:
            return {"ok": False, "mensagem": str(e)}

    def opencode_info(self):
        import opencode_mvp
        return opencode_mvp.info()

    def opencode_testar(self, texto):
        import opencode_mvp
        return opencode_mvp.testar(texto)

    def gpu_info(self):
        """Telemetria do PC, solicitada pela interface apenas no modo Kani visível."""
        import gpu
        return gpu.info()

    # ── contas do Claude (contas.py): salvas, com apelido e e-mail; troca MANUAL ──
    def _contas(self):
        e = _ler_estado()
        lista = e.get("contas") or []
        if not any(c["id"] == "principal" for c in lista):
            lista.insert(0, {"id": "principal", "apelido": "Principal"})
        return lista, e.get("conta") or "principal"

    def contas_listar(self):
        lista, ativa = self._contas()
        return self._contas_com_fotos(lista, ativa)

    def _contas_com_fotos(self, lista, ativa):
        import avatares
        fotos = avatares.fotos(c.get("email") for c in lista)
        # Fotos só na resposta da API; não duplicar base64 no estado nem nas credenciais.
        return {"lista": [dict(c, foto=fotos.get((c.get("email") or "").strip().casefold())) for c in lista], "ativa": ativa}

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
        return self._contas_com_fotos(lista, ativa)

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
        return self._contas_com_fotos(lista, ativa)

    def conta_remover(self, conta_id):
        import contas
        lista, ativa = self._contas()
        if conta_id == "principal":
            return self._contas_com_fotos(lista, ativa)
        contas.remover(conta_id)
        lista = [c for c in lista if c["id"] != conta_id]
        if ativa == conta_id:
            ativa = "principal"
            self._encerrar()
        _gravar_estado(contas=lista, conta=ativa)
        return self._contas_com_fotos(lista, ativa)

    def conta_usar(self, conta_id):
        """troca manual: a próxima mensagem já vai pela conta escolhida, na MESMA conversa"""
        lista, ativa = self._contas()
        if conta_id == ativa or not any(c["id"] == conta_id for c in lista):
            return self._contas_com_fotos(lista, ativa)
        if self._sessao and self._sessao.ocupada:
            raise RuntimeError("espere a resposta terminar para trocar de conta")
        self._encerrar()
        c = next(c for c in lista if c["id"] == conta_id)
        self._limite = c.get("cotas")
        _gravar_estado(conta=conta_id, limite=self._limite)
        return self._contas_com_fotos(lista, conta_id)

    # ── falar direto com um ajudante ("Quem responde": Codex ou Kani) ──
    def quem(self, nome):
        _gravar_estado(quem=nome if nome in ("claude", "codex", "kani", "pickle") else "claude")
        self.bola_quem(nome)
        return True

    def bola_quem(self, nome):
        """selo do agente selecionado, junto do rosto animado"""
        self._na_ui(lambda: self._bola and self._bola.definir(quem=nome if nome in ("claude", "codex", "kani", "pickle") else "claude"))
        return True

    # ── conversa da Kani: vai para a mesma conversa da janela (trocar Kani ⇄ Claude não apaga) e o Claude lê depois ──
    def _kani_arquivo(self, pasta, so_previa=False):
        """antes de existir conversa do Claude nesta pasta, a da Kani fica à parte (entra na dele na 1ª mensagem)"""
        sid = None if so_previa else (_ler_estado().get("sessoes") or {}).get(pasta)
        if sid:
            return os.path.join(DADOS, "conversas", sid + ".jsonl")
        import hashlib
        return os.path.join(DADOS, "conversas_kani", hashlib.md5(os.path.normcase(pasta).encode()).hexdigest()[:12] + ".jsonl")

    def _kani_guardar(self, pasta, eventos, pedido, resposta):
        try:
            with _ESTADO_TRAVA:
                a = self._kani_arquivo(pasta)
                os.makedirs(os.path.dirname(a), exist_ok=True)
                with open(a, "a", encoding="utf-8") as f:
                    for ev in eventos:
                        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                nv = _ler_estado().get("kani_nao_visto") or {}
                nv[pasta] = ((nv.get(pasta) or []) + [{"pedido": pedido, "resposta": resposta}])[-8:]
                _gravar_estado(kani_nao_visto=nv)
        except OSError:
            pass

    def _kani_previa(self, pasta, tirar=False):
        a = self._kani_arquivo(pasta, so_previa=True)
        try:
            with open(a, encoding="utf-8") as f:
                evs = [json.loads(l) for l in f if l.strip()]
        except (OSError, ValueError):
            return []
        if tirar:
            try:
                os.remove(a)
            except OSError:
                pass
        return evs

    def _kani_para_claude(self, pasta):
        """trocas com a Kani que o Claude ainda não viu: vão junto da próxima mensagem (o Pailer não vê o bloco)"""
        with _ESTADO_TRAVA:
            nv = _ler_estado().get("kani_nao_visto") or {}
            trocas = nv.pop(pasta, None)
            if not trocas:
                return ""
            _gravar_estado(kani_nao_visto=nv)
        linhas = "\n".join(f"Pailer: {t['pedido']}\nKani: {t['resposta']}" for t in trocas)
        return ("[Contexto do KaniCode, o Pailer não vê este bloco: antes desta mensagem ele conversou com a Kani (modo Kani, "
                "modelo local). Últimas trocas:\n" + linhas + "\nPassos/ferramentas de cada pedido: "
                + os.path.join(DADOS, "kani_modo.jsonl") + "]\n\n")

    def _comando_conclusao(self, texto, de="pc"):
        import unicodedata
        t = re.sub(r"\s*\(por voz\)\s*$", "", texto or "", flags=re.I)
        t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if not unicodedata.combining(c))
        t = re.sub(r"[.!?,;:]", "", t)
        t = " ".join(t.split())
        if t not in ("/concluir", "tarefa concluida", "concluir tarefa", "concluir a tarefa",
                     "pode concluir a tarefa", "finalizamos a tarefa", "tarefa finalizada") or self._ocupada():
            return False
        self._para_janela({"t": "eco_eu", "texto": texto, "de": de, "minis": []})
        self._na_ui(lambda: self._bola and self._bola.definir(humor="concluido", segundos=2.8))
        self._para_janela({"t": "local", "acao": "aviso", "texto": "Tarefa concluída! 👍"})
        return True

    def ajudante(self, quem, texto, _de="pc"):
        import ajudantes
        if quem not in ("codex", "kani", "pickle"):
            raise ValueError("ajudante desconhecido")
        if not texto or not texto.strip():
            return False
        if self._comando_conclusao(texto, _de):
            return True
        if self._ocupada() or not self._ajudante_trava.acquire(blocking=False):
            raise RuntimeError("Espere a resposta terminar ou use Parar antes de enviar outra demanda.")
        # a mensagem aparece também nos outros aparelhos (pedido por voz no celular aparecia só a resposta)
        self._para_janela({"t": "eco_eu", "texto": texto, "de": _de, "minis": []})
        self._ajudante_ativo = quem
        pasta = self._pasta()   # não deixar uma troca de pasta mudar o destino no meio da tarefa
        editar = getattr(self, "_modo", "auto") != "plan"
        if quem == "codex":
            self._codex_parar = threading.Event()
            self._prontidao_agendar()

        def evento_codex(ev):
            if ev.get("sessao"):
                self._codex_guardar(pasta, ev["sessao"])
            self._evento(ev)

        def rodar():
            por_voz = self._por_voz
            resposta = None
            try:
                self._bola_estado("trabalhando")
                if quem == "codex":
                    r = ajudantes.codex(texto, pasta, editar=editar, ao_evento=evento_codex,
                                        retomar=self._codex_id(pasta), parar=self._codex_parar)
                    if r.get("sessao"):
                        self._codex_guardar(pasta, r["sessao"])
                    self._codex_registrar(pasta, texto, r)
                elif quem == "pickle":
                    r = self._pickle_rodar(texto, pasta, por_voz, editar)
                else:   # modo Kani: em etapas (kani_modo.py), com a conversa recente como contexto
                    import kani_modo
                    self._kani_parar = threading.Event()
                    passos, vistos = [], []

                    def ev(e):   # guarda os passos para o registro (D:/Kanivete/KaniCode/kani_modo.jsonl)
                        if e.get("t") in ("ferr", "ferr_fim"):
                            passos.append({k: e.get(k) for k in ("t", "nome", "entrada", "ok", "saida") if e.get(k) is not None})
                            vistos.append(dict(e))
                        self._evento(e)
                    r = kani_modo.rodar(texto, pasta, ev, getattr(self, "_kani_hist", []), por_voz, self._kani_parar, editar=editar)
                    try:   # registro de cada pedido do modo Kani: o Claude lê depois para achar limitações
                        with open(os.path.join(DADOS, "kani_modo.jsonl"), "a", encoding="utf-8") as f:
                            f.write(json.dumps({"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "pedido": texto, "voz": por_voz,
                                                "passos": passos, "resposta": r.get("texto"), "claude": r.get("claude"),
                                                "ok": r.get("ok"), "ms": r.get("ms"), "tokens": r.get("tokens")}, ensure_ascii=False) + chr(10))
                    except Exception:
                        pass
                    if r.get("claude"):   # pedido difícil: vai para o Claude, com a mesma pergunta
                        self._kani_hist = []
                        self._para_janela({"t": "ajudante_resposta", "quem": "kani", "ok": True, "tokens": r["tokens"],
                                           "texto": "Isso é com o Claude, passei para ele." + (f" ({r['texto']})" if r["texto"] else "")})
                        self._bola_atividade("")
                        self._para_janela({"t": "local", "acao": "quem", "quem": "claude"})
                        self.enviar(texto)
                        return
                    self._kani_hist = (getattr(self, "_kani_hist", []) + [{"role": "user", "content": texto},
                                                                          {"role": "assistant", "content": r["texto"]}])[-20:]
                    self._kani_guardar(pasta, [{"t": "eu", "texto": texto}] + vistos +
                                       [{"t": "ajudante_resposta", "quem": "kani", "texto": r["texto"], "ok": r["ok"]}],
                                       texto, r["texto"])
                    self._bola_atividade("")
                    if por_voz:   # pedido por voz: a resposta volta falada
                        f = self._fala_obj()
                        f.novo()
                        f.pedaco(r["texto"])
                        f.terminar()
                        self._por_voz = False
                resposta = {"t": "ajudante_resposta", "quem": quem, "texto": r["texto"], "ok": r["ok"],
                            "tokens": r["tokens"], "uso": r.get("uso")}
                self._na_ui(lambda: self._bola and self._bola.definir(humor="feliz" if r["ok"] else "erro", segundos=3))
            except Exception as e:
                resposta = {"t": "ajudante_resposta", "quem": quem, "texto": str(e), "ok": False, "tokens": 0}
            finally:
                if quem == "codex" and resposta is not None:
                    resposta["cancelado"] = bool(self._codex_parar and self._codex_parar.is_set())
                self._ajudante_ativo = None
                self._codex_parar = None
                if resposta:
                    self._codex_voz(resposta)
                self._ajudante_trava.release()
                if resposta:
                    self._para_janela(resposta)   # só liberar a caixa da janela depois de liberar o motor
                self._bola_atividade("")
                self._bola_estado("" if self._aberta else "pergunta")
                if self._pendente:
                    acao, self._pendente = self._pendente, None
                    threading.Timer(1.5, self._atualizar, args=(acao,)).start()
        try:
            threading.Thread(target=rodar, daemon=True).start()
        except Exception:
            self._prontidao_cancelar()
            self._ajudante_ativo = None
            self._codex_parar = None
            self._ajudante_trava.release()
            raise
        return True

    def _ocupada(self):
        return bool(self._ajudante_ativo or (self._sessao and self._sessao.ocupada))

    def _pickle_arquivo(self, pasta, nova=False):
        import uuid
        chave = os.path.normcase(os.path.realpath(pasta))
        with _ESTADO_TRAVA:
            sessoes = _ler_estado().get("pickle_sessoes") or {}
            sid = sessoes.get(chave, "")
            if nova or not re.fullmatch(r"[a-f0-9]{32}", sid):
                sid = uuid.uuid4().hex
                sessoes[chave] = sid
                _gravar_estado(pickle_sessoes=sessoes)
        return os.path.join(DADOS, "conversas_pickle", sid + ".jsonl")

    def _pickle_historico(self, pasta):
        try:
            with open(self._pickle_arquivo(pasta), encoding="utf-8") as f:
                eventos = []
                for linha in deque(f, maxlen=400):
                    try:
                        ev = json.loads(linha)
                        if isinstance(ev, dict):
                            eventos.append(ev)
                    except ValueError:
                        continue
                return eventos
        except OSError:
            return []

    def _pickle_rodar(self, texto, pasta, por_voz, editar):
        import bigpickle_modo
        self._kani_parar = threading.Event()
        vistos = []
        historico = []
        for ev in self._pickle_historico(pasta):
            if ev.get("t") == "eu":
                historico.append({"role": "user", "content": ev.get("texto", "")})
            elif ev.get("t") == "ajudante_resposta":
                historico.append({"role": "assistant", "content": ev.get("texto", "")})

        def evento(ev):
            if ev.get("t") in ("ferr", "ferr_fim", "pickle_progresso", "codigo_alteracao", "codigo_pronto"):
                vistos.append(dict(ev))
            self._evento(ev)

        import pickle_agente
        if pickle_agente.para_ponte(texto):   # mexer no KANIVETE, sites, disco: a ponte em etapas
            r = bigpickle_modo.rodar(texto, pasta, evento, historico[-16:], por_voz, self._kani_parar, editar)
        else:   # código e conversa: o OpenCode nativo, numa cópia isolada (pickle_agente.py)
            r = pickle_agente.rodar(texto, pasta, evento, historico[-16:], por_voz, self._kani_parar,
                                    editar and getattr(self, "_modo", "auto") != "plan")
        eventos = [{"t": "eu", "texto": texto}] + vistos + [
            {"t": "ajudante_resposta", "quem": "pickle", "texto": r["texto"], "ok": r["ok"], "tokens": r["tokens"],
             "orcamento":r.get("orcamento"), "etapas_concluidas":r.get("etapas_concluidas")}]
        with _ESTADO_TRAVA:
            arquivo = self._pickle_arquivo(pasta)
            os.makedirs(os.path.dirname(arquivo), exist_ok=True)
            with open(arquivo, "a", encoding="utf-8") as f:
                for ev in eventos:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if por_voz:
            fala = self._fala_obj()
            fala.novo()
            fala.pedaco(r["texto"])
            fala.terminar()
            self._por_voz = False
        return r

    def _codex_id(self, pasta):
        chave = os.path.normcase(os.path.realpath(pasta))
        return (_ler_estado().get("codex_sessoes") or {}).get(chave)

    def _codex_guardar(self, pasta, sessao):
        chave = os.path.normcase(os.path.realpath(pasta))
        with _ESTADO_TRAVA:
            sessoes = _ler_estado().get("codex_sessoes") or {}
            if sessoes.get(chave) != sessao:
                sessoes[chave] = sessao
                _gravar_estado(codex_sessoes=sessoes)

    def _codex_registrar(self, pasta, texto, r):
        """Histórico para a janela; medidas separadas sem copiar prompts para a telemetria."""
        try:
            with _ESTADO_TRAVA:
                os.makedirs(DADOS, exist_ok=True)
                medida = {k: r.get(k) for k in ("sessao", "ok", "uso", "tokens", "ms", "primeiro_evento_ms",
                                               "esforco", "cancelado", "estourou")}
                medida.update(quando=time.strftime("%Y-%m-%d %H:%M:%S"), pasta=pasta,
                              comandos=len(r.get("comandos") or []))
                with open(os.path.join(DADOS, "codex_uso.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(medida, ensure_ascii=False) + "\n")
                sid = r.get("sessao")
                if not sid or not re.fullmatch(r"[a-fA-F0-9-]{36}", sid):
                    return
                diretorio = os.path.join(DADOS, "conversas_codex")
                os.makedirs(diretorio, exist_ok=True)
                with open(os.path.join(diretorio, sid + ".jsonl"), "a", encoding="utf-8") as f:
                    progresso = [{"t": "codex_progresso", "texto": t, "reiniciar": i == 0}
                                 for i, t in enumerate(r.get("progresso") or [])]
                    for ev in [{"t": "eu", "texto": texto}, *progresso, *(r.get("alteracoes") or []),
                               {"t": "ajudante_resposta", "quem": "codex", "texto": r["texto"], "ok": r["ok"]}]:
                        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except OSError:
            pass   # falha de registro não deve esconder uma resposta que já terminou

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
    def enviar(self, texto, imagens=None, _de="pc"):
        texto = (texto or "").strip()
        if not texto and not imagens:
            return False
        if not imagens and self._comando_conclusao(texto, _de):
            return True
        # a mensagem aparece também nos outros aparelhos abertos (janela do PC × celular, movel.py)
        self._para_janela({"t": "eco_eu", "texto": texto, "de": _de, "minis": [i.get("mini") for i in imagens or [] if i.get("mini")]})
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
        if not self._respondendo:
            self._respondendo, self._resposta = True, ""
        pasta = self._pasta()
        if not self._sessao.sessao_id:   # conversa nova: o que a Kani falou antes entra no começo dela
            self._sessao._pendentes = self._kani_previa(pasta, tirar=True) + (getattr(self._sessao, "_pendentes", None) or [])
        contexto = "" if texto.startswith("/") else self._kani_para_claude(pasta)
        try:
            self._sessao.enviar(texto, imagens, contexto=contexto)
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
        self._prontidao_cancelar()
        parar = self._codex_parar
        if parar:
            parar.set()
            if self._fala:
                self._fala.parar()
        if getattr(self, "_kani_parar", None):
            self._kani_parar.set()
        if self._sessao:
            self._sessao.parar()
        return True

    _IMG = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

    def miniatura(self, caminho, lado=900):
        """print na conversa: a imagem reduzida como dataURL (None se não for imagem ou não existir)"""
        try:
            from recursos_resposta import caminho as resolver
            caminho = resolver(caminho, self._pasta())
            lado = max(64, min(1200, int(lado)))
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

    def resposta_abrir_caminho(self, caminho):
        import recursos_resposta as recursos
        return recursos.abrir_caminho(caminho, self._pasta())

    def resposta_navegador(self, navegador=None):
        if navegador is not None:
            if navegador not in ('chrome', 'padrao'):
                raise ValueError('Navegador inválido.')
            _gravar_estado(navegador_links=navegador)
        return {'navegador': _ler_estado().get('navegador_links') or 'chrome'}

    def resposta_abrir_link(self, url):
        import recursos_resposta as recursos
        return recursos.abrir_link(url, self.resposta_navegador()['navegador'])

    def resposta_copiar_texto(self, texto):
        import recursos_resposta as recursos
        return recursos.copiar_texto(texto)

    def resposta_imagem(self, origem):
        import recursos_resposta as recursos
        return recursos.imagem_dados(origem, self._pasta())

    def resposta_tela_cheia(self, on):
        on = bool(on)
        if self._janela and on != getattr(self, '_imagem_tela_cheia', False):
            self._janela.toggle_fullscreen()
            self._imagem_tela_cheia = on
        return bool(getattr(self, '_imagem_tela_cheia', False))

    def resposta_copiar_imagem(self, origem):
        import recursos_resposta as recursos
        return recursos.copiar_imagem(origem, self._pasta())

    def resposta_salvar_imagem(self, origem):
        import recursos_resposta as recursos
        dados, info = recursos.imagem(origem, self._pasta())
        ext = os.path.splitext(info['nome'])[1]
        destino = self._janela.create_file_dialog(webview.FileDialog.SAVE, save_filename=info['nome'],
                                                 file_types=(f'Imagem (*{ext})', 'Todas as imagens (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp)'))
        if not destino:
            return False
        if not isinstance(destino, str):
            destino = destino[0]
        return recursos.salvar_imagem(dados, info, destino)

    def modo(self, modo):
        """botão Planejar: 'plan' = o Claude só planeja e pede aprovação; 'auto' = trabalha normal"""
        modo = "plan" if modo == "plan" else "auto"
        self._modo = modo
        if self._sessao:
            self._sessao.definir_modo(modo)
        return modo

    def nova(self):
        """conversa nova nesta pasta (a anterior continua guardada)"""
        if self._ocupada():
            raise RuntimeError("Espere a resposta terminar ou use Parar antes de abrir outra conversa.")
        if _ler_estado().get("quem") == "pickle":
            self._pickle_arquivo(self._pasta(), nova=True)
            return True
        if _ler_estado().get("quem") == "codex":
            with _ESTADO_TRAVA:
                sessoes = _ler_estado().get("codex_sessoes") or {}
                sessoes.pop(os.path.normcase(os.path.realpath(self._pasta())), None)
                _gravar_estado(codex_sessoes=sessoes)
            return True
        self._encerrar()
        e = _ler_estado()
        ss = e.get("sessoes") or {}
        ss.pop(self._pasta(), None)
        nv = e.get("kani_nao_visto") or {}
        nv.pop(self._pasta(), None)
        _gravar_estado(sessoes=ss, kani_nao_visto=nv)
        self._kani_previa(self._pasta(), tirar=True)
        self._kani_hist = []
        return True

    def historico(self):
        if _ler_estado().get("quem") == "pickle":
            return self._pickle_historico(self._pasta())
        if _ler_estado().get("quem") == "codex":
            sid = self._codex_id(self._pasta())
            if not sid or not re.fullmatch(r"[a-fA-F0-9-]{36}", sid):
                return []
            try:
                with open(os.path.join(DADOS, "conversas_codex", sid + ".jsonl"), encoding="utf-8") as f:
                    eventos = []
                    for linha in deque(f, maxlen=400):
                        try:
                            eventos.append(json.loads(linha))
                        except ValueError:
                            continue
                    return eventos
            except OSError:
                return []
        previa = self._kani_previa(self._pasta())   # conversa com a Kani antes de haver uma do Claude
        sid = (_ler_estado().get("sessoes") or {}).get(self._pasta())
        if not sid:
            return previa
        from sessao import Sessao
        return previa + Sessao(self._pasta(), DADOS, None, sessao_id=sid).historico()

    def escolher_pasta(self):
        if self._ocupada():
            return None
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
        try:   # o chat some na hora; só a KaniBall faz a despedida (2026-10-21, pedido do Pailer)
            self._janela.hide()
            self._aberta = False
        except Exception:
            pass
        self._encerrar()
        try:   # a Kani direta roda neste processo: sai da placa de vídeo junto
            import ajudantes
            ajudantes.kani_parar()
        except Exception:
            pass
        terminou = threading.Event()
        self._na_ui(lambda: self._bola.sair(terminou.set) if self._bola else terminou.set())
        terminou.wait(self._bola.duracao_saida + 0.7 if self._bola else 0)
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
        parar = self._codex_parar
        if parar:
            parar.set()
        if self._sessao:
            s, self._sessao = self._sessao, None
            threading.Thread(target=s.fechar, daemon=True).start()
        self._bola_estado("")

    def _prontidao_cancelar(self):
        pendente, self._prontidao_pendente = self._prontidao_pendente, None
        if pendente:
            pendente[0].set()
            pendente[1].cancel()

    def _prontidao_agendar(self):
        self._prontidao_cancelar()
        if self._aberta and not self._por_voz:
            return
        cancelado = threading.Event()
        def valido():
            return not cancelado.is_set() and self._ajudante_ativo == "codex" and (not self._aberta or self._por_voz)
        def confirmar():
            if valido():
                try:
                    self._fala_obj().prontidao(valido)
                except Exception:
                    pass  # mensagem opcional; o Codex continua normalmente
        temporizador = threading.Timer(1.0, confirmar)
        temporizador.daemon = True
        self._prontidao_pendente = (cancelado, temporizador)
        temporizador.start()

    def _codex_ler(self, texto):
        texto = (texto or "").strip()
        if (self._aberta and not self._por_voz) or not texto or texto in self._codex_lidos:
            return
        if self._codex_parar and self._codex_parar.is_set():
            return
        try:
            fala = self._fala_obj()
            if not self._codex_falando:
                fala.novo()
                self._codex_falando = True
            fala.dizer(texto)
            self._codex_lidos.add(texto)
        except Exception as erro:
            self._para_janela({"t": "voz", "fase": "erro:" + str(erro)})

    def _codex_voz(self, ev):
        t = ev.get("t")
        if (t == "codex_progresso" and ev.get("texto")) or (t == "ajudante_resposta" and ev.get("quem") == "codex"):
            self._prontidao_cancelar()
        if t == "ajudante" and ev.get("quem") == "codex" and ev.get("fase") == "inicio":
            self._codex_comentario = ""
            self._codex_lidos = set()
            self._codex_falando = False
        elif t == "codex_progresso" and ev.get("concluido"):
            self._codex_comentario = ev.get("texto") or ""
            self._codex_ler(self._codex_comentario)
        elif t == "ajudante_resposta" and ev.get("quem") == "codex":
            try:
                if not ev.get("cancelado"):
                    self._codex_ler(ev.get("texto"))
                if self._codex_falando and self._fala and not ev.get("cancelado"):
                    self._fala.terminar()
            except Exception as erro:
                self._para_janela({"t": "voz", "fase": "erro:" + str(erro)})
            finally:
                self._codex_falando = False
                self._codex_comentario = ""
                self._por_voz = False

    def _evento(self, ev):
        self._codex_voz(ev)
        t = ev.get("t")
        if t == "inicio":
            self._respondendo, self._resposta = True, ""
        elif t == "texto_novo":
            self._resposta = ""
        elif t == "texto":
            self._resposta += ev.get("d") or ""
        elif t in ("fim", "saiu"):
            self._respondendo, self._resposta = False, ""
        if t == "ferr":
            self._bola_atividade(self._ATIV.get(ev.get("nome"), ""))
        elif t in ("pensando", "kani_pensando"):
            self._bola_atividade("pensando")
        elif t in ("texto_novo", "fim", "saiu"):
            self._bola_atividade("")
        if self._por_voz and self._fala:
            if t == "texto_novo":
                self._fala.novo()
            elif t == "texto":
                self._fala.pedaco(ev.get("d") or "")
            elif t in ("permissao", "pergunta"):
                self._fala.dizer("Preciso da sua decisão na janela.")
            elif t in ("fim", "saiu"):
                self._fala.terminar()
                self._por_voz = False
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
            if t == "fim" or ev.get("erro"):   # carinha feliz/triste por 3 s (sair sem erro não entristece)
                ok = t == "fim" and not ev.get("erro")
                self._na_ui(lambda: self._bola and self._bola.definir(humor="feliz" if ok else "erro", segundos=3))
            if t == "saiu":
                self._sessao = None
        self._para_janela(ev)
        if t in ("fim", "saiu") and self._pendente:
            acao, self._pendente = self._pendente, None
            threading.Timer(1.5, self._atualizar, args=(acao,)).start()   # a última bolha chega à tela antes

    def pendentes(self):
        """cartões de permissão/pergunta ainda sem resposta (o celular que abre agora mostra eles vivos)"""
        return list(self._pend.values())

    def _para_janela(self, ev):
        if ev.get("t") in ("permissao", "pergunta") and ev.get("id"):
            self._pend[ev["id"]] = ev
        elif ev.get("t") == "eco_resp":
            self._pend.pop(ev.get("id"), None)
        elif ev.get("t") in ("fim", "saiu"):
            self._pend.clear()
        try:
            import movel
            movel.publicar(ev)
        except Exception:
            pass
        try:
            self._janela.evaluate_js("window.kcEv && kcEv(%s)" % json.dumps(ev, ensure_ascii=False))
        except Exception:
            pass

    def _bola_estado(self, estado):
        self._na_ui(lambda: self._bola and self._bola.definir(estado=estado))

    # o que está fazendo agora → rosto da bolinha (lendo, digitando, procurando, pensando)
    _ATIV = {"Read": "lendo", "Grep": "procurando", "Glob": "procurando", "WebSearch": "procurando", "WebFetch": "lendo",
             "ToolSearch": "procurando", "Edit": "digitando", "MultiEdit": "digitando", "Write": "digitando",
             "NotebookEdit": "digitando", "Bash": "digitando", "PowerShell": "digitando",
             "kani_ler_arquivo": "lendo", "kani_listar_pasta": "procurando", "kani_procurar_no_codigo": "procurando",
             "kani_buscar_no_mapa": "procurando", "kani_demandas_panda": "lendo", "kani_git_resumo": "lendo",
             "kani_espaco_disco": "procurando", "kani_abrir": "digitando", "kani_ver_kanivete": "procurando",
             "kani_abrir_ferramenta": "digitando", "kani_pedir_ao_kanivete": "digitando",
             "kani_abrir_no_kanibrowser": "digitando", "kani_fechar_aba": "digitando", "kani_salvar_texto": "digitando",
             "kani_salvar_conversa": "digitando", "kani_lembrar": "digitando", "kani_responder_janela": "digitando",
             "kani_ver_kanibrowser": "procurando", "kani_fechar_aba_kanibrowser": "digitando", "kani_ler_site": "lendo",
             "kani_clicar_no_site": "digitando",
             "kani_navegar_kani": "procurando", "kani_ler_kani": "lendo", "kani_clicar_kani": "digitando"}

    def _bola_atividade(self, a):
        self._na_ui(lambda: self._bola and self._bola.definir(atividade=a))

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
            b = Bolinha(-10000, -10000, BOLA, self._clique, self._movida, ao_direito=self._clique, ao_som=self._som_bolinha)
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
            b.quem = e.get("quem") if e.get("quem") in ("kani", "pickle") else "claude"
            b.entrar(px, py_)
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
        if self._ocupada():
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

    def _kb(self, c, linha):
        with c:
            try:
                import navegador
                r = navegador.chamar(linha, DADOS, self._pasta())
                c.settimeout(30)
                c.sendall(json.dumps(r, ensure_ascii=False, default=str).encode("utf-8") + b"\n")
            except OSError:
                pass

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
                if cmd.startswith("kb "):   # KaniBrowser hospedado aqui (navegador.py; kb.py manda): numa thread, pode demorar
                    threading.Thread(target=self._kb, args=(c.dup(), cmd[3:]), daemon=True).start()
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
    if e.get("movel", True):   # KaniCode no celular (movel.py): só em 127.0.0.1; de fora, pelo Tailscale
        try:
            import movel
            movel.iniciar(app, DADOS)
        except Exception:
            pass

    def comecar():
        app._criar_bola()
        if e.get("encaixe", True):   # Win + setas encaixam a janela (encaixe.py); "encaixe": false no estado desliga
            def encaixar():
                try:
                    import encaixe
                    encaixe.ligar(app._hwnd())
                except Exception:
                    pass
            app._na_ui(encaixar)
        if e.get("voz"):   # o Ei Kani estava ligado: volta ligado
            threading.Timer(1.5, app.voz, args=(True,)).start()
        # ao iniciar vem só a KaniBall, sempre (2026-10-21, pedido do Pailer): o chat abre no clique
    webview.start(comecar, debug="--console" in sys.argv, storage_path=os.path.join(DADOS, "webview"))


if __name__ == "__main__":
    main()
