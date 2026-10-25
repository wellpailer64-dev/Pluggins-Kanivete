"""Telinha do KANIVETE no celular: a página do app ao vivo, só ela (nada da área de trabalho), pelo modo agente.

O KANIVETE em modo agente (CDP em 127.0.0.1:9222; 9333 = app de teste) manda quadros JPEG da própria página
(Page.startScreencast) só quando algo muda; aqui eles viram um MJPEG (multipart/x-mixed-replace) que o <img> do
celular mostra. Uma conexão por telinha aberta; fechou a telinha, o pedido de quadros para. O mouse remoto atua
somente nessa página, em coordenadas proporcionais ao quadro, sem controlar outras janelas do computador.
"""
import json, math, os, subprocess, threading, time, urllib.request

PORTAS = (9222, 9333)
LIMITE = "kcquadro"
_MOUSE_TRAVA = threading.Lock()


def mouse(dados):
    """Touchpad do celular: mover ou clicar no ponto normalizado da página transmitida."""
    if not isinstance(dados, dict) or dados.get("acao") not in ("mover", "clicar"):
        raise ValueError("Ação de mouse inválida.")
    for eixo in ("x", "y"):
        v = dados.get(eixo)
        if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1:
            raise ValueError("Coordenada de mouse inválida.")
    cliques = dados.get("cliques", 1)
    if type(cliques) is not int or cliques not in (1, 2):
        raise ValueError("Quantidade de cliques inválida.")
    from websockets.sync.client import connect
    with _MOUSE_TRAVA:
        a = alvo()
        if not a:
            raise LookupError("KANIVETE fechado ou fora do modo agente")
        with connect(a[1], max_size=2 ** 20, open_timeout=3) as ws:
            numero = 0

            def comando(metodo, params=None):
                nonlocal numero
                numero += 1
                ws.send(json.dumps({"id": numero, "method": metodo, "params": params or {}}))
                fim = time.monotonic() + 3
                while True:
                    restante = fim - time.monotonic()
                    if restante <= 0:
                        raise TimeoutError("O KANIVETE não respondeu ao mouse.")
                    r = json.loads(ws.recv(timeout=restante))
                    if r.get("id") == numero:
                        if r.get("error"):
                            raise RuntimeError("O KANIVETE recusou o evento de mouse.")
                        return r.get("result", {})

            medidas = comando("Page.getLayoutMetrics")
            vista = medidas.get("cssVisualViewport") or medidas.get("cssLayoutViewport") or medidas["layoutViewport"]
            largura, altura = float(vista["clientWidth"]), float(vista["clientHeight"])
            x = min(largura - 1, dados["x"] * largura)
            y = min(altura - 1, dados["y"] * altura)
            params = {"x": x, "y": y, "pointerType": "mouse"}
            comando("Input.dispatchMouseEvent", dict(params, type="mouseMoved", buttons=0))
            if dados["acao"] == "clicar":
                try:
                    comando("Input.dispatchMouseEvent", dict(params, type="mousePressed", button="left", buttons=1, clickCount=cliques))
                finally:
                    comando("Input.dispatchMouseEvent", dict(params, type="mouseReleased", button="left", buttons=0, clickCount=cliques))
    return {"ok": True, "largura": largura, "altura": altura}


def alvo():
    """(porta, websocket) da janela principal do KANIVETE em modo agente, ou None"""
    for p in PORTAS:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{p}/json", timeout=1.5) as r:
                ts = json.loads(r.read())
        except Exception:
            continue
        for t in ts:
            if t.get("type") == "page" and "index.html" in t.get("url", "") and t.get("webSocketDebuggerUrl"):
                return p, t["webSocketDebuggerUrl"]
    return None


def transmitir(wfile, largura=1280):
    """escreve os quadros em wfile até o celular fechar (OSError) ou o app sair"""
    import base64
    from websockets.sync.client import connect
    a = alvo()
    if not a:
        raise LookupError("KANIVETE fechado ou fora do modo agente")

    def parte(jpg):
        wfile.write(b"--" + LIMITE.encode() + b"\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() +
                    b"\r\n\r\n" + jpg + b"\r\n")
        wfile.flush()

    with connect(a[1], max_size=None, open_timeout=5) as ws:
        n = [0]

        def cmd(metodo, params=None):
            n[0] += 1
            ws.send(json.dumps({"id": n[0], "method": metodo, "params": params or {}}))
            return n[0]

        # 1º quadro na hora (o screencast só manda quando a tela muda)
        i = cmd("Page.captureScreenshot", {"format": "jpeg", "quality": 55})
        cmd("Page.startScreencast", {"format": "jpeg", "quality": 55, "maxWidth": largura, "maxHeight": largura})
        try:
            while True:
                try:
                    m = json.loads(ws.recv(timeout=25))
                except TimeoutError:
                    i = cmd("Page.captureScreenshot", {"format": "jpeg", "quality": 55})   # parado: um quadro de vida
                    continue
                if m.get("id") == i and "result" in m:
                    parte(base64.b64decode(m["result"]["data"]))
                elif m.get("method") == "Page.screencastFrame":
                    pr = m["params"]
                    parte(base64.b64decode(pr["data"]))   # escreve antes de confirmar: celular lento = menos quadros
                    cmd("Page.screencastFrameAck", {"sessionId": pr["sessionId"]})
        finally:
            try:
                cmd("Page.stopScreencast")
            except Exception:
                pass


def abrir_kanivete(projeto):
    """abre o KANIVETE em modo agente (o exe do dist; sem ele, pelo código)"""
    if alvo():
        return "aberto"
    exe = os.path.join(projeto, "dist", "CaniveteDoPailer", "CaniveteDoPailer.exe")
    if os.path.isfile(exe):
        subprocess.Popen([exe, "--agente"], cwd=os.path.dirname(exe), close_fds=True, creationflags=0x00000008 | 0x00000200)
    else:
        subprocess.Popen(["py", "-3.13", "main.py", "--agente"], cwd=projeto, close_fds=True, creationflags=0x00000008 | 0x00000200)
    return "abrindo"
