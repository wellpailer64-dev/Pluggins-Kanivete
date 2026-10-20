"""Linha de comando do plugin Pandalab (para o Claude e para o Pailer). Só leitura nesta etapa.

  py -3.13 panda.py login                 (abre janelinha: e-mail ou @usuario + senha)
  py -3.13 panda.py quem | sair
  py -3.13 panda.py demandas [--status abertas|todo|in_progress|adjustment|done] [--cliente X] [--busca X] [--json]
  py -3.13 panda.py demanda <id ou começo do id> [--json]
  py -3.13 panda.py baixar <id> [--pasta P]
  py -3.13 panda.py clientes
  py -3.13 panda.py status <id> --status todo|in_progress|adjustment [--sim]   comentar <id> --descricao "texto" [--sim]
  py -3.13 panda.py finais <id>   (o que vai na entrega)
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandalab as pl

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _janela_login():
    import tkinter as tk
    r = {}
    w = tk.Tk(); w.title("Pandalab — login"); w.attributes("-topmost", True); w.resizable(False, False)
    tk.Label(w, text="E-mail ou @usuário").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
    e1 = tk.Entry(w, width=34); e1.grid(row=1, column=0, padx=10)
    tk.Label(w, text="Senha").grid(row=2, column=0, sticky="w", padx=10, pady=(8, 0))
    e2 = tk.Entry(w, width=34, show="•"); e2.grid(row=3, column=0, padx=10)

    def ok(*_):
        r["u"], r["s"] = e1.get(), e2.get(); w.destroy()
    tk.Button(w, text="Entrar", command=ok, width=12).grid(row=4, column=0, pady=10)
    w.bind("<Return>", ok); e1.focus_set(); w.mainloop()
    return r.get("u"), r.get("s")


def _linha(d):
    tipo = d.get("custom_creative_type_name") or pl.TIPOS.get(d["content_type"], d["content_type"])
    marcas = ("🔥" if d.get("is_urgent") else "") + ("↺" if d.get("needs_revision") else "")
    cli = (d.get("client") or {}).get("name") or "—"
    resp = (d.get("resp") or {}).get("name") or ""
    return f"{d['id'][:8]}  {pl.STATUS.get(d['status'], d['status']):<12} {tipo:<11} {cli[:22]:<22} {d['title'][:60]} {marcas} {resp}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("ref", nargs="?")
    ap.add_argument("--status"); ap.add_argument("--cliente"); ap.add_argument("--busca")
    ap.add_argument("--pasta"); ap.add_argument("--json", action="store_true")
    ap.add_argument("--mes", help="AAAA-MM do mês da pauta (padrão: mês de hoje)")
    ap.add_argument("--tipo", default="estatico"); ap.add_argument("--descricao")
    ap.add_argument("--sim", action="store_true", help="confirma a escrita no Pandalab")
    a = ap.parse_args()
    try:
        if a.cmd == "login":
            u, s = _janela_login()
            if not u or not s:
                print("Login cancelado."); return 1
            print("Entrou como", pl.login(u, s))
        elif a.cmd == "sair":
            pl.sair(); print("Sessão apagada.")
        elif a.cmd == "quem":
            print(json.dumps(pl.quem(), ensure_ascii=False))
        elif a.cmd == "demandas":
            rows = pl.demandas(a.status, a.cliente, a.busca)
            if a.json:
                print(json.dumps(rows, ensure_ascii=False)); return 0
            for d in rows:
                print(_linha(d))
            print(f"— {len(rows)} demanda(s)")
        elif a.cmd == "demanda":
            d = pl.demanda(a.ref)
            if a.json:
                print(json.dumps(d, ensure_ascii=False, indent=1)); return 0
            print(_linha(d))
            print("Criada:", d["created_at"][:16], "| Atualizada:", (d.get("updated_at") or "")[:16])
            if d.get("delivery_link"): print("Entrega:", d["delivery_link"])
            print("\nDescrição:\n" + (d.get("description") or "(vazia)"))
            print(f"\nArquivos ({len(d['arquivos'])}):")
            for f in d["arquivos"]:
                print(f"  - {f['file_name']} ({(f.get('file_size') or 0) // 1024} KB)")
            print(f"\nComentários ({len(d['comentarios'])}):")
            for c in d["comentarios"]:
                quem = (c.get("cliente") or {}).get("name") or (c.get("equipe") or {}).get("name") or "?"
                print(f"  [{c['created_at'][:16]}] {quem}: {c['comment_text']}")
        elif a.cmd == "baixar":
            pasta, feitos = pl.baixar(a.ref, a.pasta, a.mes)
            print(f"{len(feitos)} arquivo(s); pasta da demanda: {pasta}")
            for f in feitos:
                print("  -", f)
        elif a.cmd == "onde":
            d, p = pl.onde(a.ref, a.mes)
            print(_linha(d)); print("→", p or "(cliente sem pasta no mapa_clientes.json)")
        elif a.cmd == "pastas":
            import pastas
            m = pastas.mapa()
            for c in pl.clientes():
                base, e = pastas.pasta_cliente(c["id"])
                if not e:
                    print(f"  FALTA NO MAPA   {c['name']} ({c['id'][:8]})"); continue
                if not base:
                    print(f"  sem pasta       {c['name']}"); continue
                prod = os.path.join(base, e.get("producao", ""))
                st = "ok" if os.path.isdir(prod) else ("criar produção" if os.path.isdir(base) else "PASTA NÃO EXISTE")
                print(f"  {st:<15} {c['name']:<28} {prod}")
        elif a.cmd == "criar":
            if not a.ref or not a.cliente:
                print('Uso: panda.py criar "Título" --cliente Nome [--tipo carrossel] [--descricao "..."] [--sim]'); return 1
            c = pl.achar_cliente(a.cliente)
            print(f"Nova demanda: '{a.ref}' | {c['name']} | {a.tipo} | {len(a.descricao or '')} letras de descrição")
            if not a.sim:
                print("(prévia: nada foi criado. Repita com --sim para criar no Pandalab.)"); return 0
            r = pl.criar(a.ref, c["id"], a.tipo, a.descricao or "")
            print("Criada:", json.dumps(r, ensure_ascii=False))
        elif a.cmd in ("status", "comentar"):
            d = pl.demanda(a.ref)
            alvo = a.status if a.cmd == "status" else a.descricao
            print(f"{a.cmd}: '{d['title']}' ({(d.get('client') or {}).get('name')}) → {alvo}")
            if not a.sim:
                print("(prévia: nada mudou. Repita com --sim para gravar no Pandalab.)"); return 0
            print(pl.mudar_status(a.ref, a.status) if a.cmd == "status" else pl.comentar(a.ref, a.descricao))
        elif a.cmd == "finais":
            r = pl.finais(a.ref)
            print(r["pasta"]); [print("  -", os.path.basename(f)) for f in r["arquivos"]]
        elif a.cmd == "clientes":
            for c in pl.clientes():
                print(c["id"][:8], c["name"])
        else:
            print(__doc__); return 1
    except pl.ErroPanda as e:
        print("ERRO:", e); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
