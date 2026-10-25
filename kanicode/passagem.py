"""Passagem de bastão entre agentes na mesma aba (2026-10-24).

Cada aba+pasta tem um diário curto dos turnos (quem, pedido, resposta). Quando o Pailer troca de agente
(Claude ⇄ Codex ⇄ Big Pickle ⇄ Kani), o próximo pedido leva, num bloco que ele não vê, as trocas que esse
agente ainda não viu — o novo agente continua a demanda sem recomeçar. Cada agente tem um cursor (`vistos`).
Kani → Claude já vai por `kani_nao_visto` (kanicode.py), então aqui é pulado.
"""
import hashlib
import json
import os
import threading
import time

NOMES = {"claude": "Claude", "codex": "Codex", "kani": "Kani", "pickle": "Big Pickle"}
GUARDAR = 30            # turnos no diário
PRIMEIRA_VEZ = 6        # agente que nunca participou recebe só os últimos turnos
LIMITE = {"kani": 1500}  # caracteres do bloco (a Kani local tem pouca memória)
LIMITE_PADRAO = 8000
POR_RESPOSTA = 2000

_trava = threading.Lock()


def _arquivo(dados, chave):
    h = hashlib.md5(os.path.normcase(chave).encode("utf-8")).hexdigest()[:16]
    return os.path.join(dados, "passagem", h + ".json")


def _ler(arq):
    try:
        with open(arq, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            return {"turnos": list(d.get("turnos") or []), "vistos": dict(d.get("vistos") or {}), "seq": int(d.get("seq") or 0)}
    except (OSError, ValueError, TypeError):
        pass
    return {"turnos": [], "vistos": {}, "seq": 0}


def _gravar(arq, d):
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    tmp = arq + ".parte"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, arq)


def _encurtar(t, n):
    t = str(t or "").strip()
    if len(t) <= n:
        return t
    cabeca = n * 3 // 10
    return t[:cabeca].rstrip() + " […] " + t[-(n - cabeca):].lstrip()


def registrar(dados, chave, quem, pedido, resposta):
    """turno concluído: entra no diário; quem respondeu já viu tudo até aqui"""
    pedido, resposta = str(pedido or "").strip(), str(resposta or "").strip()
    if quem not in NOMES or not (pedido or resposta):
        return
    try:
        with _trava:
            arq = _arquivo(dados, chave)
            d = _ler(arq)
            d["seq"] += 1
            d["turnos"] = (d["turnos"] + [{"n": d["seq"], "quem": quem, "pedido": _encurtar(pedido, POR_RESPOSTA),
                                           "resposta": _encurtar(resposta, POR_RESPOSTA), "quando": int(time.time())}])[-GUARDAR:]
            d["vistos"][quem] = d["seq"]
            _gravar(arq, d)
    except OSError:
        pass   # o diário é ajuda; nunca impede a resposta


def pendente(dados, chave, destino, marcar=True):
    """bloco de contexto com o que `destino` ainda não viu de outros agentes ("" = nada a passar)"""
    try:
        with _trava:
            arq = _arquivo(dados, chave)
            d = _ler(arq)
            visto = d["vistos"].get(destino)
            novos = [t for t in d["turnos"] if (visto is None or t["n"] > visto) and t["quem"] != destino
                     and not (destino == "claude" and t["quem"] == "kani")]
            if visto is None:
                novos = novos[-PRIMEIRA_VEZ:]
            if marcar and d["seq"] and d["vistos"].get(destino) != d["seq"]:
                d["vistos"][destino] = d["seq"]
                _gravar(arq, d)
    except OSError:
        return ""
    if not novos:
        return ""
    limite = LIMITE.get(destino, LIMITE_PADRAO)
    linhas, total = [], 0
    for t in reversed(novos):   # do mais recente para trás, até caber
        r = _encurtar(t["resposta"], min(POR_RESPOSTA, limite // 2))
        bloco = f"Pailer: {_encurtar(t['pedido'], 600)}\n{NOMES.get(t['quem'], t['quem'])}: {r}"
        if linhas and total + len(bloco) > limite:
            break
        linhas.insert(0, bloco)
        total += len(bloco)
    quem = sorted({NOMES.get(t["quem"], t["quem"]) for t in novos})
    return ("[Contexto do KaniCode, o Pailer não vê este bloco: nesta mesma aba ele vinha trabalhando com "
            + ", ".join(quem) + " e agora passou a demanda para você. Continue de onde pararam, sem refazer o que já "
            "foi feito; confira o estado real dos arquivos antes de agir. Últimas trocas:\n"
            + "\n\n".join(linhas) + "]\n\n")
