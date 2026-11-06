"""Extensão própria pelo pipe privado do Chrome; sem servidor aberto para páginas web."""
import json
from pathlib import Path
import threading
import time

import kanibrowser as kb

PASTA = Path(__file__).resolve().parent / "extensao"
VERSAO = "0.2.0"
_trava = threading.RLock()


def instalar():
    with _trava:
        try:
            r = kb._cmd("Extensions.loadUnpacked", {"path": str(PASTA)})
        except kb.ErroKB as e:
            raise kb.ErroKB("Extensão não carregada. O Chrome precisa iniciar com "
                            "--enable-unsafe-extension-debugging pelo pipe privado. "
                            "Reinicie o KaniCode para aplicar a preparação. Detalhe: " + str(e)) from e
        kb._c["extensao_id"] = r["id"]
        kb._c.pop("extensao_erro", None)
        return {"id": r["id"], "pasta": str(PASTA), "carregada": True}


def descoberta():
    """Resumo local para o estado e os agentes, sem abrir navegador nem chamar CDP."""
    return {"nome": "KaniCode · Olhos do navegador",
            "carregada": bool(kb.ativo() and kb._c.get("extensao_id")),
            "erro": kb._c.get("extensao_erro"),
            "comandos": "extensao estado|ler|mapa|panorama|midias|api|digitar|selecionar|marcar|clicar|tecla|aguardar|copiar|baixar|download; scripts listar|rodar",
            "guia": str(PASTA.parent / "EXTENSAO.md")}


def estado():
    if not kb.ativo():
        return {"aberto": False, "carregada": False, "pasta": str(PASTA)}
    pronto = {"pronta": False}
    if kb._c.get("extensao_id"):
        try:
            pronto = executar("pronto")
        except kb.ErroKB as e:
            pronto["erro_prontidao"] = str(e)
    return {"aberto": True, "id": kb._c.get("extensao_id"), **pronto,
            "carregada": bool(kb._c.get("extensao_id")), "erro": kb._c.get("extensao_erro"),
            "pasta": str(PASTA), "versao_navegador": kb._cmd("Browser.getVersion")["product"]}


def executar(acao, dados=None):
    """O alvo é sempre a aba da Kani; URLs duplicadas são recusadas pelo motor."""
    with _trava, kb.trabalho("Extensão: " + acao) as aba:
        eid = kb._c.get("extensao_id")
        if not eid:
            raise kb.ErroKB("Extensão ainda não carregada: use `kb.py extensao instalar` ou reinicie o KaniCode.")
        url = kb.js("location.href", aba)
        # A ação acorda o service worker, inclusive depois da suspensão por inatividade.
        alvos = kb._cmd("Target.getTargets", {"filter": [{"type": "tab", "exclude": False}]})["targetInfos"]
        tabs = [x for x in alvos if x.get("type") == "tab" and x.get("url") == url]
        if len(tabs) != 1:
            raise kb.ErroKB("A página precisa ter uma única aba com esse endereço.")
        kb._cmd("Extensions.triggerAction", {"id": eid, "targetId": tabs[0]["targetId"]})
        motor = f"chrome-extension://{eid}/motor.js"
        alvo = None
        for _ in range(40):
            alvo = next((x for x in kb._cmd("Target.getTargets")["targetInfos"]
                         if x.get("type") == "service_worker" and x.get("url") == motor), None)
            if alvo:
                break
            time.sleep(.1)
        if not alvo:
            raise kb.ErroKB("O motor da extensão não iniciou.")
        sessao = kb._cmd("Target.attachToTarget", {"targetId": alvo["targetId"], "flatten": True})["sessionId"]
        try:
            pronto = None
            for _ in range(40):
                r = kb._cmd("Runtime.evaluate", {"expression":
                            "typeof kbPronto === 'function' ? kbPronto(" + json.dumps(url) + ") : null",
                            "awaitPromise": True, "returnByValue": True}, sessao)
                pronto = r.get("result", {}).get("value")
                if pronto:
                    if pronto.get("versao") != VERSAO:
                        raise kb.ErroKB("Motor desatualizado; use extensao instalar e confira extensao estado.")
                    if pronto.get("pronta"):
                        break
                # Após recarga, o evento inicial pode chegar antes do listener do motor.
                kb._cmd("Extensions.triggerAction", {"id": eid, "targetId": tabs[0]["targetId"]})
                time.sleep(.1)
            else:
                raise kb.ErroKB("Motor não está pronto ou é antigo; use extensao instalar. Nenhuma ação foi executada.")
            if acao == "pronto":
                return pronto
            if acao == "tecla":
                teclas = {"Enter": ("Enter", 13), "Tab": ("Tab", 9), "Escape": ("Escape", 27),
                          "ArrowDown": ("ArrowDown", 40), "ArrowUp": ("ArrowUp", 38), "Backspace": ("Backspace", 8)}
                dados = dados or {}
                if dados.get("tecla") not in teclas:
                    raise ValueError("Tecla permitida: " + ", ".join(teclas))
                if dados.get("aguardar") and not any(dados["aguardar"].get(k) for k in ("url", "texto", "seletor")):
                    raise ValueError("Informe condição para aguardar antes de pressionar tecla.")
                if dados.get("seletor"):
                    executar("focar", {"seletor": dados["seletor"]})
                tecla, codigo = teclas[dados["tecla"]]
                kb._cdp(aba, "Input.dispatchKeyEvent", {"type": "keyDown", "key": tecla, "code": tecla,
                        "windowsVirtualKeyCode": codigo, **({"text": "\r"} if tecla == "Enter" else {})})
                kb._cdp(aba, "Input.dispatchKeyEvent", {"type": "keyUp", "key": tecla, "code": tecla, "windowsVirtualKeyCode": codigo})
                if dados.get("aguardar"):
                    return executar("aguardar", dados["aguardar"])
                return {"executado": True, "confirmado": False}
            argumentos = json.dumps([url, acao, dados or {}], ensure_ascii=False)
            r = kb._cmd("Runtime.evaluate", {"expression": f"kbExecutar(...{argumentos})",
                        "awaitPromise": True, "returnByValue": True}, sessao)
            if r.get("exceptionDetails"):
                erro = r["exceptionDetails"].get("exception", {}).get("description") or r["exceptionDetails"].get("text")
                raise kb.ErroKB(str(erro)[:1000])
            return r.get("result", {}).get("value")
        finally:
            try:
                kb._cmd("Target.detachFromTarget", {"sessionId": sessao})
            except kb.ErroKB:
                pass


def comando(acao="estado", dados=None):
    if acao == "estado":
        return estado()
    if acao == "instalar":
        return instalar()
    if acao == "gerenciar":
        return kb.nova("chrome://extensions/")
    if acao not in ("ler", "mapa", "panorama", "midias", "digitar", "copiar", "baixar", "download", "api", "selecionar", "marcar", "clicar", "tecla", "aguardar"):
        raise ValueError("Ação da extensão desconhecida.")
    return executar(acao, dados)
