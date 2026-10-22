"""Bateria da Kani: pedidos do jeito que o Pailer fala → a habilidade certa (bateria_kani.json: [pedido, regex do id]).

  py -3.13 bateria_kani.py            só a BUSCA (instantâneo): a certa veio em 1º? entre as 5 que vão no pedido?
  py -3.13 bateria_kani.py --modelo   a Kani de verdade escolhe (modelo local), sem executar nada no app
  [--so photo] filtra pelos ids esperados; [-v] mostra o que veio nos erros
Saída: acertos por ferramenta e a lista do que errou (para ensinar com frases em habilidades_extra.json)."""
import json
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import habilidades  # noqa: E402

CASOS = os.path.join(AQUI, "bateria_kani.json")


def _ferr(esperado):
    return esperado.replace("(?i)", "").split(":", 1)[0].split("|")[0]


def busca(casos, v=False):
    tot, erros = {}, []
    for pedido, esperado in casos:
        ids = [h["id"] for h in habilidades.buscar(pedido, 5)]
        r = re.compile(esperado)
        pos = next((i for i, x in enumerate(ids) if r.match(x)), None)
        f = _ferr(esperado)
        t = tot.setdefault(f, [0, 0, 0])
        t[0] += 1
        t[1] += pos == 0
        t[2] += pos is not None
        if pos != 0:
            erros.append((pedido, esperado, pos, ids))
    return tot, erros


def modelo(casos, v=False):
    """a Kani escolhe a 1ª ação; nada roda no app (cada ação vira 'FEITO (simulado)' e a rodada para)"""
    import kani_modo
    tot, erros = {}, []
    for pedido, esperado in casos:
        escolha = {}

        def falso(acao, a, pasta, _e=escolha):
            if acao in ("usar_habilidade", "photo_novo_documento", "photo_escrever", "abrir_ferramenta"):
                _e.setdefault("acoes", []).append((acao, a))
            if acao == "buscar_habilidade":
                return "Habilidades (use usar_habilidade com o id):\n" + "\n".join(
                    habilidades.resumo(h) for h in habilidades.buscar(str(a.get("busca") or pedido), 8))
            if acao == "ver_kanivete":
                return "Ferramenta aberta: home. Abas: nenhuma. Tela inicial."
            if acao == "usar_habilidade":
                if not habilidades.achar(str(a.get("id") or "")):
                    return "NÃO FEITO: não achei a habilidade \"" + str(a.get("id")) + "\". Use buscar_habilidade."
                return "FEITO (simulado). Agora: ok."
            return "FEITO (simulado)."
        orig, orig_pedir = kani_modo._executar, kani_modo.pedir_ao_kanivete
        kani_modo._executar = falso
        kani_modo.pedir_ao_kanivete = lambda p, *x, **y: (escolha.setdefault("acoes", []).append(("pedir_ao_kanivete", {"pedido": p})), "FEITO (simulado).")[1]
        t0 = time.time()
        try:
            res = kani_modo._rodar_pedido(pedido, AQUI, lambda ev: None)
        finally:
            kani_modo._executar, kani_modo.pedir_ao_kanivete = orig, orig_pedir   # nada vai para o app de verdade
        usadas = [a.get("id", "") for acao, a in escolha.get("acoes", []) if acao == "usar_habilidade"]
        r = re.compile(esperado)
        ok = any(r.match(str(x)) for x in usadas) or (
            esperado.startswith("photo:documento novo") and any(acao == "photo_novo_documento" for acao, _ in escolha.get("acoes", []))) or (
            esperado.startswith("photo:escrever") and any(acao == "photo_escrever" for acao, _ in escolha.get("acoes", [])))
        f = _ferr(esperado)
        t = tot.setdefault(f, [0, 0, 0])
        t[0] += 1
        t[1] += ok
        t[2] += ok
        print(("OK  " if ok else "ERRO") + f" {time.time() - t0:4.1f}s  {pedido}" + ("" if ok else f"  → {escolha.get('acoes')} | {res.get('texto', '')[:80]}"), flush=True)
        if not ok:
            erros.append((pedido, esperado, None, usadas))
    return tot, erros


if __name__ == "__main__":
    with open(CASOS, encoding="utf-8") as f:
        casos = json.load(f)
    if "--so" in sys.argv:
        so = sys.argv[sys.argv.index("--so") + 1]
        casos = [c for c in casos if c[1].startswith(so)]
    v = "-v" in sys.argv
    tot, erros = (modelo if "--modelo" in sys.argv else busca)(casos, v)
    n = sum(t[0] for t in tot.values())
    print(f"\n{len(casos)} pedidos — em 1º: {sum(t[1] for t in tot.values())}/{n}, entre as 5: {sum(t[2] for t in tot.values())}/{n}")
    for f, t in sorted(tot.items()):
        print(f"  {f:7s} {t[1]}/{t[0]} em 1º, {t[2]}/{t[0]} entre as 5")
    if erros:
        print("\nerrou:")
        for pedido, esp, pos, ids in erros:
            print(f"  - {pedido}  (esperado {esp}; {'posição ' + str(pos + 1) if pos is not None else 'fora'})" + (f"\n      veio: {ids}" if v else ""))
