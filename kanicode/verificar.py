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
    "progresso": ("progresso.py", "progresso_kanivete.js", "ponte.py", "painel.js", "google_drive_arquivos.py", "kanicode.py", "movel.py", "ui/progresso.js", "ui/janela.html", "tests/test_progresso.py", "tests/test_google_drive_arquivos.py"),
    "tarefas": ("tarefas.py", "tarefas_agente.py", "kanicode.py", "kani_modo.py", "licoes.py", "codex_contexto.py", "sessao.py", "mcp_equipe.py", "movel.py", "ui/tarefas.js", "ui/mensagens.js", "ui/abas.js", "tests/test_tarefas*.py", "tests/test_mensagens.py", "tests/test_fila_disco.py", "tests/test_codex_eventos.py"),
    "cerebro": ("perfil_cerebro.py", "mcp_equipe.py", "ui/cerebro.js", "ui/mapa_d.js", "tests/test_cerebro_*.py"),
    "movel": ("movel.py", "tela_pc.py", "tela_movel.py", "tests/test_tela_pc.py", "ui/movel.js", "tests/test_tela_movel.py", "tests/test_tela_movel_ui.py"),
    "mensagens": ("mensagens.py", "kanicode.py", "sessao.py", "ui/mensagens.js", "ui/janela.html", "tests/test_mensagens.py"),
    "voz": ("fala.py", "voz.py", "radio.py", "kanicode.py", "ui/abas.js", "ui/cerebro.js", "ui/janela.html", "tests/test_fala_tom.py", "tests/test_fala_microfone.py", "tests/test_codex_prontidao.py", "tests/test_codex_voz.py", "tests/test_cerebro_classificacao_ui.py"),
    "claude": ("sessao.py", "continuidade.py", "mcp_equipe.py", "ui/janela.html", "tests/test_continuidade.py", "tests/test_equipe_revisao.py"),
    "kani": ("kani_modo.py", "kani_estado.py", "kani_orquestracao.py", "kani_etapas.py", "kani_codigo_etapas.py", "benchmark_kani_orquestracao.py", "kanicode.py", "ajudantes.py", "ui/kani_execucoes.js", "ui/janela.html", "tests/test_kani_*.py", "tests/test_modelo_ferramenta.py"),
    "pickle": ("bigpickle_modo.py", "pickle_agente.py", "codigo_agente.py", "ui/codigo_agente.js", "pickle_controle.py", "opencode_mvp.py", "kani_modo.py", "kanicode.py", "bolinha.py", "ui/janela.html", "ui/movel.js", "tests/test_bigpickle_*.py", "tests/test_pickle_agente.py", "tests/test_opencode_mvp.py", "tests/test_kani_historico.py"),
    "codex": ("ajudantes.py", "codex_contexto.py", "codex_processo.py", "codex_conta.py", "codex_alteracoes.py", "ui/alteracoes.js", "ui/codex_uso.js", "ui/janela.html", "tests/test_codex_*.py"),
    "codigo": ("codigo_agente.py", "codigo_testes.py", "kani_modo.py", "bigpickle_modo.py", "kanicode.py", "ui/codigo_agente.js", "tests/test_codigo_*.py"),
    "interface": ("kanicode.py", "ui/janela.html", "ui/paineis.js", "ui/organizacao.js", "ui/diagnostico.js", "ui/kani_gpu.js", "tests/test_layout.py", "tests/test_janela_painel.py", "tests/test_ponte_nativa.py", "tests/apoio_ponte_nativa.py", "tests/test_dll_isoladas.py"),
    "respostas": ("recursos_resposta.py", "ui/respostas.js", "ui/respostas_render.js", "tests/test_*respostas*.py", "tests/test_recursos_resposta.py"),
    "gpu": ("gpu.py", "ui/kani_gpu.js", "tests/test_gpu.py"),
    "contas": ("contas.py", "avatares.py", "tests/test_avatares.py"),
    "infra": ("verificar.py", "dados_app.py", "teste_isolado.py", "modelo_ferramenta.py", "tests/test_modelo_ferramenta.py", "tests/test_verificar.py", "tests/test_ambiente_isolado.py"),
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
    base.mkdir(parents=True, exist_ok=True)
    saida = Path(tempfile.mkdtemp(prefix="verificar_", dir=base))
    os.environ["KANICODE_TESTE"] = "1"
    os.environ["KANICODE_DADOS_TESTE"] = str(saida / "dados")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(base / "playwright"))
    os.environ["CODEX_HOME"] = str(saida / "codex")
    os.environ["CLAUDE_CONFIG_DIR"] = str(saida / "claude")
    for nome, pasta in (("TEMP", "tmp"), ("TMP", "tmp"), ("APPDATA", "appdata"),
                        ("LOCALAPPDATA", "localappdata"), ("PYTHONPYCACHEPREFIX", "pycache")):
        destino = base / pasta
        destino.mkdir(parents=True, exist_ok=True)
        os.environ[nome] = str(destino)
    return saida


def verificar(arquivos, saida):
    falhas = []
    ignorados = []
    testes = [p for p in arquivos if p.parent == RAIZ / "tests" and p.name.startswith("test_")]
    log = saida / "resultado.txt"
    with log.open("w", encoding="utf-8") as registro:
        def rodar(comando, nome, dados=None):
            env = os.environ.copy()
            if dados is not None:
                dados.mkdir(parents=True, exist_ok=True)
                env.update(KANICODE_DADOS_TESTE=str(dados), CODEX_HOME=str(dados / "codex"), CLAUDE_CONFIG_DIR=str(dados / "claude"))
            try:
                r = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=180, env=env)
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
                rodar([sys.executable, str(RAIZ / "teste_isolado.py"), p.name], p.name, saida / "dados" / p.stem)
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
