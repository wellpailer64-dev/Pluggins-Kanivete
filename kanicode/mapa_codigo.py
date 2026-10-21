"""Busca e trechos pequenos do KaniCode, com linhas atuais, sem importar o app."""
import argparse
import ast
import os
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parent
EXTENSOES = {".py", ".js", ".html", ".css", ".json", ".md", ".java"}
IGNORAR = {".git", "__pycache__", "modelos", "node_modules"}


def arquivo(nome):
    p = (RAIZ / nome).resolve()
    if not p.is_relative_to(RAIZ) or not p.is_file() or p.suffix not in EXTENSOES:
        raise ValueError("use um arquivo de código/documentação dentro do KaniCode")
    return p


def trecho(p, inicio, fim):
    linhas = p.read_text(encoding="utf-8").splitlines()
    fim = min(fim, inicio + 79, len(linhas))
    return "\n".join(f"{p.relative_to(RAIZ).as_posix()}:{i}: {linhas[i - 1]}"
                     for i in range(max(1, inicio), fim + 1))


def buscar(termo, p=None):
    caminhos = [p] if p else []
    if not p:
        for raiz, pastas, nomes in os.walk(RAIZ):
            pastas[:] = [d for d in pastas if d not in IGNORAR]
            caminhos.extend(Path(raiz) / n for n in nomes if Path(n).suffix in EXTENSOES)
        caminhos.sort(key=lambda f: ("tests" in f.parts, f.suffix == ".md", str(f)))
    saida = []
    for f in caminhos:
        for i, linha in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if termo.casefold() in linha.casefold():
                saida.append(f"{f.relative_to(RAIZ).as_posix()}:{i}: {linha.strip()[:240]}")
                if len(saida) == 25:
                    return "\n".join(saida) + "\n(limite de 25; refine --busca ou indique --arquivo)"
    return "\n".join(saida) or "Nenhuma ocorrência."


def simbolo(p, nome):
    def visitar(no, prefixo=""):
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                completo = prefixo + filho.name
                if completo == nome:
                    return filho
                encontrado = visitar(filho, completo + ".")
                if encontrado:
                    return encontrado
    no = visitar(ast.parse(p.read_text(encoding="utf-8")))
    if no is None:
        raise ValueError("símbolo não encontrado; use NomeDaClasse.metodo ou --busca")
    return trecho(p, no.lineno, no.end_lineno)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquivo")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--busca")
    grupo.add_argument("--simbolo")
    grupo.add_argument("--trecho", help="início:fim; até 80 linhas")
    args = parser.parse_args()
    try:
        p = arquivo(args.arquivo) if args.arquivo else None
        if args.busca:
            saida = buscar(args.busca, p)
        elif args.simbolo and p:
            saida = simbolo(p, args.simbolo)
        elif args.trecho and p:
            inicio, fim = map(int, args.trecho.split(":"))
            if inicio < 1 or fim < inicio:
                raise ValueError("intervalo inválido")
            saida = trecho(p, inicio, fim)
        elif args.simbolo or args.trecho:
            raise ValueError("informe --arquivo")
        elif p:
            saida = trecho(p, 1, 80)
        else:
            saida = (RAIZ / "MAPA.md").read_text(encoding="utf-8")
        print(saida)
    except (OSError, ValueError, SyntaxError) as e:
        parser.error(str(e))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
