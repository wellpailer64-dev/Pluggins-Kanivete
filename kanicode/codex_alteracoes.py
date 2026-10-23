"""Fotografia limitada antes do turno para mostrar diffs sem misturar edições anteriores."""
import difflib
import os
import time
from pathlib import Path

EXTENSOES = {".py", ".js", ".mjs", ".html", ".css", ".json", ".md", ".txt", ".ts", ".tsx", ".jsx"}
IGNORAR = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv", "modelos", "modelos_ia"}


class Captura:
    def __init__(self, pasta):
        self.raiz = Path(pasta).resolve()
        self.antes = {}
        self.completa = True
        self.total = 0
        self.alteracoes = {}
        limite = time.monotonic() + 1.5
        try:
            for raiz, dirs, arquivos in os.walk(self.raiz, onerror=self.erro):
                if time.monotonic() > limite:
                    self.completa = False
                    return
                dirs[:] = [n for n in dirs if n.lower() not in IGNORAR and not (Path(raiz) / n).is_symlink()
                           and not (hasattr(Path(raiz) / n, "is_junction") and (Path(raiz) / n).is_junction())]
                for nome in arquivos:
                    p = Path(raiz) / nome
                    if p.suffix.lower() not in EXTENSOES or p.is_symlink():
                        continue
                    if len(self.antes) >= 300 or self.total >= 8 * 1024 * 1024 or time.monotonic() > limite:
                        self.completa = False
                        return
                    if p.stat().st_size > 512 * 1024:
                        self.antes[os.path.normcase(str(p.resolve()))] = None
                        continue
                    dados = p.read_bytes()
                    self.total += len(dados)
                    try:
                        self.antes[os.path.normcase(str(p.resolve()))] = dados.decode("utf-8-sig").replace("\r\n", "\n")
                    except UnicodeError:
                        self.antes[os.path.normcase(str(p.resolve()))] = None
        except OSError:
            self.completa = False

    def erro(self, _erro):
        self.completa = False

    def registrar(self, mudanca):
        nome = str(mudanca.get("path") or "")
        try:
            p = (self.raiz / nome).resolve()
        except (OSError, ValueError):
            return None
        if not nome or not p.is_relative_to(self.raiz) or p.suffix.lower() not in EXTENSOES:
            return None
        relativo = p.relative_to(self.raiz)
        if any(n.lower() in IGNORAR for n in relativo.parts):
            return None
        try:
            if p.exists() and (not p.is_file() or p.stat().st_size > 512 * 1024):
                return None
            depois = p.read_text(encoding="utf-8-sig") if p.is_file() else ""
            antes = self.antes.get(os.path.normcase(str(p)), "" if self.completa else None)
            if antes is not None:
                diff = "".join(difflib.unified_diff(antes.splitlines(True), depois.splitlines(True),
                                                  fromfile="antes/" + relativo.as_posix(), tofile="depois/" + relativo.as_posix()))
                rotulo = "Alterações desde o início desta tarefa."
            elif mudanca.get("diff"):
                diff = str(mudanca["diff"])
                rotulo = "Diff informado pelo Codex nesta operação."
            else:
                diff = depois
                rotulo = "Sem fotografia anterior: mostrando o conteúdo atual, não um diff da tarefa."
            if not diff:
                return None
            adicionadas = removidas = None
            if antes is not None:
                operacoes = difflib.SequenceMatcher(None, antes.splitlines(), depois.splitlines()).get_opcodes()
                adicionadas = sum(j2 - j1 for op, i1, i2, j1, j2 in operacoes if op in ("insert", "replace"))
                removidas = sum(i2 - i1 for op, i1, i2, j1, j2 in operacoes if op in ("delete", "replace"))
            if len(diff) > 60000:
                diff = diff[:60000] + "\n… visualização limitada a 60 mil caracteres."
            ev = {"t":"codex_alteracao", "arquivo":relativo.as_posix(), "diff":diff, "rotulo":rotulo,
                  "conteudo": depois, "adicionadas": adicionadas, "removidas": removidas}
            self.alteracoes[relativo.as_posix()] = ev
            return ev
        except (OSError, UnicodeError):
            return None
