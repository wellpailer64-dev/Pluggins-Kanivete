"""Busca e baixa trilhas do Epidemic Sound pela conta logada no navegador interno.
    py -3.13 epidemic.py buscar "lofi hip hop" ["chillhop" ...] [--min 140]   → id | título | artista | bpm | segundos | gêneros (sem voz)
    py -3.13 epidemic.py baixar <id> --pasta "<02 - ASSETS do card>"           → caminho do MP3
Leva a aba da Kani para o site antes (kb.py js só roda nela; na aba do WhatsApp a busca dá 404).
"""
import argparse, json, os, re, subprocess, sys, urllib.parse, urllib.request, uuid
sys.stdout.reconfigure(encoding="utf-8")
KB = ["py", "-3.13", os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb.py")]


def _kb(*args):
    return subprocess.run(KB + list(args) + ["--sem-foto"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120).stdout


def _no_site():
    """leva a aba da Kani ao site e devolve o endereço de antes (a aba da Kani é a do WhatsApp da gerente)"""
    antes = (_kb("js", "location.href").strip().splitlines() or [""])[-1]
    if "epidemicsound.com" not in antes:
        _kb("ir", "https://www.epidemicsound.com/music/search/")
        return antes if antes.startswith("http") else ""
    return ""


def _busca_json(caminho):
    saida = _kb("js", "(async()=>{const r=await fetch('" + caminho + "',{credentials:'include'});return await r.json()})()")
    return json.loads(saida.strip().splitlines()[-1])


def buscar(termo, minimo):
    d = _busca_json("/json/search/tracks/?term=" + urllib.parse.quote(termo) + "&page=1")
    for t in ((d.get("entities") or {}).get("tracks") or {}).values():
        if t.get("hasVocals") or t.get("isSfx") or (t.get("length") or 0) < minimo:
            continue
        artista = ", ".join(a.get("name", "") for a in (t.get("creatives") or {}).get("mainArtists") or [])
        generos = "/".join(g.get("displayTag") or "" for g in t.get("genres") or [])
        print(f"{t.get('kosmosId')} | {t.get('title')} | {artista} | {t.get('bpm')} bpm | {round(t.get('length') or 0)} s | {generos}")


def baixar(kid, pasta):
    # 2026-11-06: o site passou a exigir uiOrigin (valor do botão da lista) e um downloadId novo por download
    d = _busca_json("/download/?bundle=false&context=MODAL_MUSIC_DOWNLOAD&downloadId=" + str(uuid.uuid4()) + "&is_sfx=false&qualityType=hq&sound_id=" + kid
                    + "&stemType=full&uiOrigin=tracklist_button")
    url = d.get("assetUrl")
    if not url:
        raise SystemExit(f"o Epidemic não liberou: {d}")
    nome = re.search(r"filename%3D%22(.+?)%22", url)
    nome = urllib.parse.unquote(nome.group(1)) if nome else kid + ".mp3"
    os.makedirs(pasta, exist_ok=True)
    arq = os.path.join(pasta, re.sub(r'[<>:"/\\|?*]', "_", nome))
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=180) as r, open(arq, "wb") as f:
        f.write(r.read())
    print(arq)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["buscar", "baixar"])
    ap.add_argument("termos", nargs="+")
    ap.add_argument("--min", type=int, default=0)
    ap.add_argument("--pasta", default="D:/Kanivete/Músicas/Epidemic")
    a = ap.parse_args()
    volta = _no_site()
    try:
        for x in a.termos:
            buscar(x, a.min) if a.acao == "buscar" else baixar(x, a.pasta)
    finally:
        if volta:
            _kb("ir", volta)
