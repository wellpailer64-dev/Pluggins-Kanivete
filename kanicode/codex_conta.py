"""Limites e redefinições pelo protocolo oficial do Codex; nenhuma inferência nem compra."""
import atexit
from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import uuid

BASE = Path(r"D:\kanivete_testes\codex_conta")
_TRAVA = threading.RLock()
_CACHE = {"quando": 0, "valor": None}
_TENTATIVAS = set()
_CLIENTE = None


def fechar():
    global _CLIENTE
    with _TRAVA:
        if _CLIENTE is not None:
            cliente, _CLIENTE = _CLIENTE, None
            cliente.__exit__(None, None, None)
        _CACHE.update(quando=0, valor=None)


@contextmanager
def conexao():
    global _CLIENTE
    if _CLIENTE is None:
        _CLIENTE = Cliente().__enter__()
    try:
        yield _CLIENTE
    except (OSError, ValueError, TimeoutError):
        fechar()
        raise


atexit.register(fechar)


class Cliente:
    def __enter__(self):
        exe = shutil.which("codex")
        if not exe:
            raise ValueError("Cliente Codex não encontrado.")
        BASE.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        for nome, pasta in (("TEMP", "tmp"), ("TMP", "tmp")):
            destino = BASE / pasta
            destino.mkdir(exist_ok=True)
            env[nome] = str(destino)
        cmd = [exe, "-c", "log_dir=" + json.dumps(str(BASE / "logs")),
               "-c", "sqlite_home=" + json.dumps(str(BASE / "estado")), "app-server"]
        self.processo = subprocess.Popen(cmd, cwd=BASE, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                         creationflags=0x08000000 if os.name == "nt" else 0)
        self.fila = queue.Queue()
        self.numero = 0
        self.atualizado_em = 0
        def ler():
            for linha in self.processo.stdout:
                try:
                    mensagem = json.loads(linha)
                    if mensagem.get("method") == "account/rateLimits/updated":
                        self.atualizado_em = time.monotonic()
                    if "id" in mensagem:
                        self.fila.put(mensagem)
                except ValueError:
                    pass
            self.fila.put(None)
        threading.Thread(target=ler, daemon=True).start()
        try:
            self.pedir("initialize", {"clientInfo": {"name": "kanicode", "title": "KaniCode", "version": "1"},
                                      "capabilities": {"experimentalApi": True}})
            self.enviar({"method": "initialized", "params": {}})
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def enviar(self, valor):
        self.processo.stdin.write(json.dumps(valor) + "\n")
        self.processo.stdin.flush()

    def pedir(self, metodo, params=None):
        self.numero += 1
        numero = self.numero
        mensagem = {"id": numero, "method": metodo}
        if params is not None:
            mensagem["params"] = params
        self.enviar(mensagem)
        limite = time.monotonic() + 15
        while True:
            try:
                r = self.fila.get(timeout=max(0.01, limite - time.monotonic()))
            except queue.Empty:
                raise TimeoutError("O Codex não respondeu à consulta da conta em 15 segundos.") from None
            if r is None:
                raise ValueError("O cliente Codex encerrou a consulta da conta.")
            if isinstance(r, dict) and r.get("id") == numero:
                if r.get("error"):
                    raise ValueError("O cliente não disponibilizou esta operação da conta: " + str(r["error"].get("message", "erro"))[:350])
                return r.get("result") or {}
            if time.monotonic() >= limite:
                raise TimeoutError("Prazo da consulta da conta excedido.")

    def __exit__(self, *args):
        try:
            self.processo.stdin.close()
            self.processo.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            self.processo.kill()
            self.processo.wait(timeout=2)


def normalizar(resultado):
    rl = (resultado.get("rateLimitsByLimitId") or {}).get("codex") or resultado.get("rateLimits") or {}
    p, s = rl.get("primary") or {}, rl.get("secondary") or {}
    def valor(janela, novo, antigo):
        return janela.get(novo, janela.get(antigo))
    def fracao(janela):
        v = valor(janela, "usedPercent", "used_percent")
        return None if v is None else min(1, max(0, float(v) / 100))
    redefinicoes = resultado.get("rateLimitResetCredits") or {}
    return {"h5": fracao(p), "h5_zera": valor(p, "resetsAt", "resets_at"),
            "sem": fracao(s), "sem_zera": valor(s, "resetsAt", "resets_at"),
            "primaria_minutos": valor(p, "windowDurationMins", "window_minutes"),
            "secundaria_minutos": valor(s, "windowDurationMins", "window_minutes"),
            "atingido": bool(rl.get("rateLimitReachedType")) or any(fracao(x) == 1 for x in (p, s)),
            "redefinicoes": redefinicoes.get("availableCount"),
            "creditos_redefinicao": redefinicoes.get("credits"), "medido_em": time.time()}


def pendente():
    try:
        r = json.loads((BASE / "reset_pendente.json").read_text(encoding="utf-8"))
        return r if r.get("pendente") else None
    except (OSError, ValueError):
        return None


def guardar_tentativa(tentativa, credito, ativa):
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "reset_pendente.json").write_text(json.dumps({"tentativa": tentativa, "credito": credito, "pendente": ativa}), encoding="utf-8")


def identidade():
    """Identificação pública da conta atual; nunca devolve tokens nem credenciais."""
    with _TRAVA:
        try:
            with conexao() as cliente:
                conta = cliente.pedir("account/read", {"refreshToken": False}).get("account") or {}
            return {"ok": True, "email": conta.get("email") or "", "plano": conta.get("planType") or "",
                    "tipo": conta.get("type") or "", "logado": bool(conta)}
        except Exception:
            return {"ok": False, "mensagem": "Não foi possível identificar a conta do Codex agora."}


def consultar(forcar=False):
    with _TRAVA:
        if (not forcar and _CACHE["valor"] is not None and time.monotonic() - _CACHE["quando"] < 5
                and (not _CLIENTE or _CLIENTE.atualizado_em <= _CACHE["quando"])):
            return {**_CACHE["valor"], "redefinicao_pendente": pendente()}
        try:
            with conexao() as cliente:
                valor = {"ok": True, "cota": normalizar(cliente.pedir("account/rateLimits/read"))}
            _CACHE.update(quando=time.monotonic(), valor=valor)
            return {**valor, "redefinicao_pendente": pendente()}
        except (OSError, ValueError, TimeoutError) as e:
            return {"ok": False, "mensagem": str(e)}


def redefinir(tentativa, credito=""):
    try:
        tentativa = str(uuid.UUID(str(tentativa)))
    except ValueError:
        return {"ok": False, "mensagem": "Identificador de tentativa inválido."}
    with _TRAVA:
        anterior = pendente()
        if anterior:
            if anterior["tentativa"] != tentativa:
                return {"ok": False, "mensagem": "Há uma redefinição pendente; verifique a tentativa anterior.", **anterior}
            _TENTATIVAS.add(tentativa)
            credito = anterior.get("credito") or credito
        try:
            with conexao() as cliente:
                dados = cliente.pedir("account/rateLimits/read")
                cota = normalizar(dados)
                if tentativa not in _TENTATIVAS and not (cota.get("redefinicoes") or 0) > 0:
                    return {"ok": False, "mensagem": "A conta não informou redefinições disponíveis.", "cota": cota}
                if credito:
                    disponiveis = cota.get("creditos_redefinicao") or []
                    if tentativa not in _TENTATIVAS and not any(c.get("id") == credito and c.get("status") == "available" for c in disponiveis):
                        return {"ok": False, "mensagem": "Essa redefinição não está mais disponível. Atualize o painel."}
                params = {"idempotencyKey": tentativa}
                if credito:
                    params["creditId"] = credito
                _TENTATIVAS.add(tentativa)
                guardar_tentativa(tentativa, credito, True)
                r = cliente.pedir("account/rateLimitResetCredit/consume", params)
                resultado = r.get("outcome")
                mensagens = {"reset": "Redefinição usada. Limites atualizados.", "alreadyRedeemed": "Esta redefinição já foi confirmada.",
                             "nothingToReset": "Não há uma janela elegível para redefinir agora.", "noCredit": "Não há redefinições disponíveis nesta conta."}
                if resultado in mensagens:
                    guardar_tentativa(tentativa, credito, False)
                try:
                    cota = normalizar(cliente.pedir("account/rateLimits/read"))
                    _CACHE.update(quando=time.monotonic(), valor={"ok": True, "cota": cota})
                except (OSError, ValueError, TimeoutError):
                    cota = None
                    _CACHE.update(quando=0, valor=None)
                return {"ok": resultado in ("reset", "alreadyRedeemed"), "resultado": resultado,
                        "mensagem": mensagens.get(resultado, "O Codex não confirmou uma redefinição."), "cota": cota,
                        "pendente": resultado not in mensagens}
        except (OSError, ValueError, TimeoutError) as e:
            return {"ok": False, "mensagem": str(e) + " Não tente com outro identificador: use a mesma tentativa para evitar consumo duplicado.", "pendente": True}
