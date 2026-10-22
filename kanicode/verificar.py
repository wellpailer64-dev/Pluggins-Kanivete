"""Verificação local por área; logs, scripts extraídos e caches ficam no D."""
import argparse
from html.parser import HTMLParser
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile

RAIZ = Path(__file__).resolve().parent
AREAS = {
    "kani": ("kani_modo.py", "ajudantes.py", "tests/test_kani_*.py", "tests/test_modelo_ferramenta.py"),
    "pickle": ("bigpickle_modo.py", "pickle_agente.py", "codigo_agente.py", "ui/codigo_agente.js", "pickle_controle.py", "opencode_mvp.py", "kani_modo.py", "kanicode.py", "bolinha.py", "ui/janela.html", "ui/movel.js", "tests/test_bigpickle_*.py", "tests/test_pickle_agente.py", "tests/test_opencode_mvp.py", "tests/test_kani_historico.py"),
    "codex": ("ajudantes.py", "codex_contexto.py", "codex_processo.py", "codex_conta.py", "codex_alteracoes.py", "ui/alteracoes.js", "ui/codex_uso.js", "ui/janela.html", "tests/test_codex_*.py"),
    "codigo": ("codigo_agente.py", "codigo_testes.py", "kani_modo.py", "bigpickle_modo.py", "kanicode.py", "ui/codigo_agente.js", "tests/test_codigo_*.py"),
    "interface": ("ui/janela.html", "ui/organizacao.js", "ui/kani_gpu.js", "tests/test_layout.py"),
    "respostas": ("recursos_resposta.py", "ui/respostas.js", "ui/respostas_render.js", "tests/test_*respostas*.py", "tests/test_recursos_resposta.py"),
    "gpu": ("gpu.py", "ui/kani_gpu.js", "tests/test_gpu.py"),
    "contas": ("contas.py", "avatares.py", "tests/test_avatares.py"),
    "infra": ("verificar.py", "modelo_ferramenta.py", "tests/test_modelo_ferramenta.py", "tests/test_verificar.py"),
}


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.atuais = None
        self.modulo = False
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag != "script":
            return
        attrs = dict(attrs)
        tipo = attrs.get("type", "").lower()
        self.modulo = tipo == "module"
        self.atuais = [] if "src" not in attrs and tipo in ("", "module", "text/javascript", "application/javascript") else None

    def handle_data(self, data):
        if self.atuais is not None:
            self.atuais.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.atuais is not None:
            self.scripts.append(("".join(self.atuais), self.modulo))
            self.atuais = None


def selecionar(area, nomes):
    padroes = ("*.py", "ui/*.js", "ui/*.html", "tests/test_*.py") if area == "todas" else AREAS[area]
    encontrados = set()
    for padrao in padroes:
        arquivos = list(RAIZ.glob(padrao))
        if not arquivos:
            raise ValueError("nenhum arquivo para " + padrao)
        encontrados.update(arquivos)
    for nome in nomes:
        caminho = (RAIZ / nome).resolve()
        if not caminho.is_relative_to(RAIZ) or not caminho.is_file():
            raise ValueError("arquivo inexistente ou fora do plugin: " + nome)
        encontrados.add(caminho)
    return sorted(encontrados)


def ambiente():
    base = Path(r"D:\kanivete_testes")
    os.environ["KANICODE_TESTE"] = "1"
    for nome, pasta in (("TEMP", "tmp"), ("TMP", "tmp"), ("APPDATA", "appdata"),
                        ("LOCALAPPDATA", "localappdata"), ("PYTHONPYCACHEPREFIX", "pycache")):
        destino = base / pasta
        destino.mkdir(parents=True, exist_ok=True)
        os.environ[nome] = str(destino)
    return Path(tempfile.mkdtemp(prefix="verificar_", dir=base))


def verificar(arquivos, saida):
    falhas = []
    ignorados = []
    testes = [p for p in arquivos if p.parent == RAIZ / "tests" and p.name.startswith("test_")]
    log = saida / "resultado.txt"
    with log.open("w", encoding="utf-8") as registro:
        def rodar(comando, nome):
            try:
                r = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=180)
                registro.write("\n" + nome + "\n" + r.stdout + r.stderr)
                if "skipped=" in r.stdout + r.stderr:
                    ignorados.append(nome)
                if r.returncode:
                    falhas.append(nome)
            except (OSError, subprocess.TimeoutExpired) as e:
                falhas.append(nome)
                registro.write("\n" + nome + ": " + str(e) + "\n")
        for i, p in enumerate(arquivos):
            nome = str(p.relative_to(RAIZ))
            if p.suffix == ".py":
                try:
                    py_compile.compile(str(p), cfile=str(saida / (str(i) + ".pyc")), doraise=True)
                except py_compile.PyCompileError as e:
                    falhas.append(nome)
                    registro.write(str(e) + "\n")
            elif p.suffix == ".js":
                rodar(["node", "--check", str(p)], nome)
            elif p.suffix == ".html":
                parser = Scripts()
                parser.feed(p.read_text(encoding="utf-8"))
                for n, (texto, modulo) in enumerate(parser.scripts):
                    script = saida / (str(i) + "_" + str(n) + (".mjs" if modulo else ".js"))
                    script.write_text(texto, encoding="utf-8")
                    rodar(["node", "--check", str(script)], nome + " script " + str(n + 1))
        if not falhas:
            for p in testes:
                rodar([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", p.name, "-v"], p.name)
    print(f"{'FALHOU' if falhas else 'OK'}: {len(arquivos)} arquivos; {len(testes)} módulos de teste selecionados.")
    if falhas:
        print("Falhas: " + ", ".join(falhas))
    if ignorados:
        print("Cobertura parcial: houve testes ignorados em " + ", ".join(ignorados) + ". Motivos no relatório.")
    print("Relatório: " + str(log))
    return 1 if falhas else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", choices=[*AREAS, "todas"], required=True)
    parser.add_argument("--arquivos", nargs="*", default=[], help="arquivos adicionais alterados, relativos ao plugin")
    parser.add_argument("--listar", action="store_true", help="só mostra a seleção, sem testar nem criar saídas")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 13):
        parser.error("use py -3.13 verificar.py")
    try:
        arquivos = selecionar(args.area, args.arquivos)
    except ValueError as e:
        parser.error(str(e))
    if args.listar:
        print("\n".join(str(p.relative_to(RAIZ)) for p in arquivos))
        return 0
    return verificar(arquivos, ambiente())


if __name__ == "__main__":
    raise SystemExit(main())
