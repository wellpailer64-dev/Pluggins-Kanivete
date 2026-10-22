"""Código de Kani/Big Pickle em cópias por contrato. A aplicação na origem pertence à interface."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import py_compile
import re
import subprocess
import tempfile
import threading
import time

BASE = Path(r"D:\kanivete_testes\codigo_agentes")
TRAVA = threading.RLock()
EXTENSOES = {".py", ".js", ".mjs", ".html", ".css", ".json", ".md", ".txt"}
BLOQUEADOS = {".git", ".env", "node_modules", "dist", "build", "__pycache__", "modelos", "venv", ".venv"}
DEPENDENCIAS = {"package.json", "package-lock.json", "yarn.lock", "requirements.txt", "requirements-dev.txt", "agents.md", "claude.md"}
FERRAMENTAS = {
    "codigo_preparar": "Inicia uma CÓPIA isolada dos arquivos do contrato. Origem não é editada. args: {arquivos: caminhos relativos separados por ponto e vírgula, objetivo}",
    "codigo_incluir": "Copia dependências locais/testes adicionais para a sessão atual, sem sobrescrever trabalho. args: {arquivos: caminhos relativos separados por ponto e vírgula}",
    "codigo_ler": "Lê até 100 linhas de arquivo da cópia. args: {caminho, inicio: número em texto; opcional}",
    "codigo_substituir": "Substitui trecho EXATO e ÚNICO apenas na cópia. args: {caminho, antes, depois}",
    "codigo_criar": "Cria arquivo novo da lista do contrato, só na cópia. args: {caminho, conteudo}",
    "codigo_verificar": "Confere sintaxe dos arquivos da cópia. Não executa o app. args: {}",
    "codigo_testar": "Roda unittest de UM arquivo test_*.py/teste_*.py do contrato na cópia (30s). Testes executam código local; sem shell livre. args: {caminho}",
    "codigo_revisar": "Mostra diff, alterações e resultados para revisão. NÃO aplica na origem. args: {}",
}


def hash_bytes(dados):
    return hashlib.sha256(dados).hexdigest()


def relativo(nome):
    nome = str(nome).strip().replace("\\", "/")
    p = Path(nome)
    if not nome or p.is_absolute() or p.drive or any(x in ("..", ".") for x in p.parts) or ':' in nome:
        raise ValueError("use caminho relativo dentro do contrato")
    if any(x.lower() in BLOQUEADOS for x in p.parts) or p.name.lower() in DEPENDENCIAS or p.name.lower().startswith("requirements"):
        raise ValueError("arquivo de regras, dependências ou pasta reservada não pode ser editado")
    if p.suffix.lower() not in EXTENSOES:
        raise ValueError("extensão não suportada para edição de texto")
    return p.as_posix()


def caminho(raiz, nome):
    p = raiz / relativo(nome)
    if not p.resolve().is_relative_to(raiz.resolve()):
        raise ValueError("caminho sai da pasta autorizada")
    atual = raiz
    for parte in Path(relativo(nome)).parts:
        atual = atual / parte
        if atual.is_symlink() or (hasattr(atual, "is_junction") and atual.is_junction()):
            raise ValueError("links e junções não são aceitos no contrato")
    return p


class Contexto:
    def __init__(self, origem, agente):
        self.origem = Path(origem).resolve()
        if agente not in ("kani", "pickle"):
            raise ValueError("agente de código desconhecido")
        self.agente = agente
        self.chave = hash_bytes((os.path.normcase(str(self.origem)) + agente).encode())[:24]

    def carregar(self):
        indice = BASE / (self.chave + ".json")
        if not indice.exists():
            raise ValueError("inicie a cópia com codigo_preparar")
        sid = json.loads(indice.read_text(encoding="utf-8"))["sessao"]
        if not re.fullmatch(r"sessao_[a-zA-Z0-9_-]+", sid):
            raise ValueError("sessão inválida")
        self.pasta = BASE / sid
        if not self.pasta.resolve().is_relative_to(BASE.resolve()):
            raise ValueError("sessão fora da pasta de trabalho")
        self.meta = json.loads((self.pasta / "contrato.json").read_text(encoding="utf-8"))
        if self.meta["origem"] != str(self.origem) or self.meta["agente"] != self.agente:
            raise ValueError("a sessão não pertence a esta pasta/agente")
        self.trabalho = self.pasta / "trabalho"
        if self.meta.get("trabalho"):   # Big Pickle nativo (pickle_agente.py): a cópia é um git worktree dentro da sessão
            self.trabalho = Path(self.meta["trabalho"])
            if not self.trabalho.resolve().is_relative_to(self.pasta.resolve()):
                raise ValueError("cópia fora da sessão")
        return self

    def salvar(self):
        (self.pasta / "contrato.json").write_text(json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def preparar(self, arquivos, objetivo="", incluir=False):
        nomes = list(dict.fromkeys(relativo(n) for n in re.split(r"[;\n]", arquivos) if n.strip()))
        if not nomes:
            raise ValueError("informe os arquivos do contrato")
        if len({n.casefold() for n in nomes}) != len(nomes):
            raise ValueError("não use nomes que diferem apenas por maiúsculas/minúsculas")
        if incluir:
            self.carregar()
            self.editavel()
        else:
            BASE.mkdir(parents=True, exist_ok=True)
            self.pasta = Path(tempfile.mkdtemp(prefix="sessao_", dir=BASE))
            self.trabalho = self.pasta / "trabalho"
            self.trabalho.mkdir()
            (self.pasta / "base").mkdir()
            self.meta = {"origem": str(self.origem), "agente": self.agente, "objetivo": objetivo[:3000],
                         "arquivos": {}, "aplicada": False, "testes": None}
        existentes = {n.casefold(): n for n in self.meta["arquivos"]}
        if any(n.casefold() in existentes and existentes[n.casefold()] != n for n in nomes):
            raise ValueError("o contrato já contém esse arquivo com outra capitalização")
        novos = {}
        total = sum(v.get("tamanho", 0) for v in self.meta["arquivos"].values())
        for nome in nomes:
            if nome in self.meta["arquivos"]:
                continue
            p = caminho(self.origem, nome)
            if p.is_file() and p.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("arquivo maior que 2 MB; delimite um contrato menor")
            dados = p.read_bytes() if p.is_file() else None
            if p.exists() and not p.is_file():
                raise ValueError("o contrato deve listar arquivos, não pastas")
            if dados is not None:
                dados.decode("utf-8-sig")
                total += len(dados)
                if len(dados) > 2 * 1024 * 1024:
                    raise ValueError("arquivo maior que 2 MB; delimite um contrato menor")
            novos[nome] = dados
        if len(self.meta["arquivos"]) + len(novos) > 80 or total > 20 * 1024 * 1024:
            raise ValueError("contrato excede 80 arquivos/20 MB")
        for nome, dados in novos.items():
            self.meta["arquivos"][nome] = {"hash": hash_bytes(dados) if dados is not None else None, "tamanho": len(dados or b"")}
            if dados is not None:
                for raiz in (self.trabalho, self.pasta / "base"):
                    destino = caminho(raiz, nome)
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(dados)
        self.salvar()
        (BASE / (self.chave + ".json")).write_text(json.dumps({"sessao": self.pasta.name}), encoding="utf-8")
        return {"sessao": self.pasta.name, "copia": str(self.trabalho), "arquivos": list(self.meta["arquivos"]),
                "aviso": "Edite somente a cópia. Use codigo_revisar; a origem só muda pelo botão de aplicar da interface."}

    def editavel(self):
        if self.meta["aplicada"]:
            raise ValueError("sessão já aplicada; prepare outra cópia")

    def arquivo(self, nome):
        nome = relativo(nome)
        if nome not in self.meta["arquivos"]:
            raise ValueError("arquivo não liberado; use codigo_incluir para copiar uma dependência local")
        return caminho(self.trabalho, nome)

    def ler(self, nome, inicio=1):
        p = self.arquivo(nome)
        ls = p.read_text(encoding="utf-8-sig").splitlines()
        inicio = max(1, int(inicio))
        return "\n".join(f"{i}: {ls[i-1]}" for i in range(inicio, min(len(ls) + 1, inicio + 100)))

    def escrever(self, nome, conteudo, antes=None):
        self.editavel()
        p = self.arquivo(nome)
        if len(conteudo) > 200000:
            raise ValueError("trecho muito grande; divida a edição")
        antigo = p.read_bytes() if p.exists() else None
        if antes is None and antigo is not None:
            raise ValueError("arquivo já existe; use codigo_substituir")
        if antes is not None:
            if not antes:
                raise ValueError("o trecho anterior não pode ser vazio")
            texto = antigo.decode("utf-8-sig").replace("\r\n", "\n") if antigo is not None else ""
            antes = antes.replace("\r\n", "\n")
            if texto.count(antes) != 1:
                raise ValueError("o trecho anterior deve existir exatamente uma vez")
            conteudo = texto.replace(antes, conteudo.replace("\r\n", "\n"), 1)
        dados = conteudo.replace("\r\n", "\n")
        if antigo and b"\r\n" in antigo:
            dados = dados.replace("\n", "\r\n")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((b"\xef\xbb\xbf" if antigo and antigo.startswith(b"\xef\xbb\xbf") else b"") + dados.encode("utf-8"))
        self.meta["testes"] = None
        self.salvar()
        return "Alteração gravada SOMENTE na cópia: " + str(p)

    def ambiente(self):
        env = dict(os.environ)
        env["KANICODE_TESTE"] = "1"
        for nome, pasta in (("TEMP", "tmp"), ("TMP", "tmp"), ("APPDATA", "appdata"),
                            ("LOCALAPPDATA", "localappdata"), ("PYTHONPYCACHEPREFIX", "pycache")):
            destino = self.pasta / pasta
            destino.mkdir(exist_ok=True)
            env[nome] = str(destino)
        return env

    def rodar(self, cmd, parar=None):
        p = subprocess.Popen(cmd, cwd=self.trabalho, env=self.ambiente(), stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                             creationflags=0x08000000 if os.name == "nt" else 0)
        inicio = time.monotonic()
        try:
            while True:
                if parar and parar.is_set():
                    raise InterruptedError("teste cancelado")
                if time.monotonic() - inicio > 30:
                    raise TimeoutError("teste excedeu 30 segundos")
                try:
                    out, err = p.communicate(timeout=0.25)
                    return {"ok": p.returncode == 0, "saida": (out + err)[-12000:]}
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if p.poll() is None:
                p.kill()
                p.communicate()

    def verificar(self):
        resultados = []
        for nome in self.meta["arquivos"]:
            p = self.arquivo(nome)
            if not p.exists():
                continue
            try:
                if p.suffix == ".py":
                    cache = self.pasta / "pycache"
                    cache.mkdir(exist_ok=True)
                    py_compile.compile(str(p), cfile=str(cache / (hash_bytes(nome.encode()) + ".pyc")), doraise=True)
                elif p.suffix in (".js", ".mjs"):
                    r = self.rodar(["node", "--check", str(p)])
                    if not r["ok"]:
                        raise ValueError(r["saida"])
                elif p.suffix == ".json":
                    json.loads(p.read_text(encoding="utf-8-sig"))
                elif p.suffix == ".html":
                    from verificar import Scripts
                    scripts = Scripts()
                    scripts.feed(p.read_text(encoding="utf-8-sig"))
                    for i, (texto, modulo) in enumerate(scripts.scripts):
                        extraido = self.pasta / (hash_bytes(nome.encode())[:12] + str(i) + (".mjs" if modulo else ".js"))
                        extraido.write_text(texto, encoding="utf-8")
                        r = self.rodar(["node", "--check", str(extraido)])
                        if not r["ok"]:
                            raise ValueError(r["saida"])
                else:
                    resultados.append({"arquivo": nome, "ok": True, "tipo": "sem verificador de sintaxe"})
                    continue
                resultados.append({"arquivo": nome, "ok": True, "tipo": "sintaxe"})
            except (ValueError, OSError, py_compile.PyCompileError) as e:
                resultados.append({"arquivo": nome, "ok": False, "erro": str(e)[:1500]})
        return {"ok": all(r["ok"] for r in resultados), "arquivos": sorted(resultados, key=lambda r: r["ok"])}

    def testar(self, nome, parar=None):
        p = self.arquivo(nome)
        if p.suffix != ".py" or not p.name.startswith(("test_", "teste_")) or not p.is_file():
            raise ValueError("escolha um arquivo de teste Python do contrato (test_*.py ou teste_*.py)")
        sintaxe = self.verificar()
        if not sintaxe["ok"]:
            return sintaxe
        runner = Path(__file__).with_name("codigo_testes.py")
        cache_teste = tempfile.mkdtemp(prefix="pycache_teste_", dir=self.pasta)
        r = self.rodar(["py", "-3.13", "-I", "-X", "pycache_prefix=" + cache_teste,
                        str(runner), str(self.trabalho), str(p)], parar)
        self.meta["testes"] = {"arquivo": nome, **r}
        self.salvar()
        return r

    def revisar(self):
        diffs, alterados, hashes = [], [], {}
        for nome, base in self.meta["arquivos"].items():
            p = self.arquivo(nome)
            dados = p.read_bytes() if p.exists() else None
            hashes[nome] = hash_bytes(dados) if dados is not None else None
            if hashes[nome] == base["hash"]:
                continue
            if dados is None:
                raise ValueError("exclusão não é permitida")
            anterior = (self.pasta / "base" / nome).read_text(encoding="utf-8-sig") if base["hash"] is not None else ""
            diffs.extend(difflib.unified_diff(anterior.splitlines(True), dados.decode("utf-8-sig").replace("\r\n", "\n").splitlines(True), fromfile="antes/" + nome, tofile="copia/" + nome))
            alterados.append(nome)
        revisao = hash_bytes(json.dumps({"sessao": self.pasta.name, "base": self.meta["arquivos"], "copia": hashes}, sort_keys=True).encode())
        return {"sessao": self.pasta.name, "copia": str(self.trabalho), "agente": self.agente,
                "arquivos": alterados, "diff": "".join(diffs), "revisao": revisao,
                "aplicada": self.meta["aplicada"], "testes": self.meta["testes"]}

    def aplicar(self, revisao):
        self.editavel()
        atual = self.revisar()
        if atual["revisao"] != revisao:
            raise ValueError("a cópia mudou desde a revisão; abra o diff novamente")
        if not atual["arquivos"]:
            raise ValueError("não há alterações para aplicar")
        for nome in atual["arquivos"]:
            p = caminho(self.origem, nome)
            if p.exists() and not p.is_file():
                raise ValueError("o destino agora é uma pasta: " + nome)
            original = hash_bytes(p.read_bytes()) if p.is_file() else None
            if original != self.meta["arquivos"][nome]["hash"]:
                raise ValueError("a origem mudou desde a cópia: " + nome + "; nada foi aplicado")
        if self.meta.get("testes") and not self.meta["testes"]["ok"]:
            raise ValueError("há testes falhando nesta cópia; corrija e rode novamente antes de aplicar")
        resultado = self.verificar()
        if not resultado["ok"]:
            raise ValueError("corrija a sintaxe antes de aplicar")
        aplicados = []
        try:
            for nome in atual["arquivos"]:
                destino = caminho(self.origem, nome)
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(self.arquivo(nome).read_bytes())
                aplicados.append(nome)
        except OSError as e:
            raise ValueError("falha ao aplicar; arquivos já gravados: " + ", ".join(aplicados)) from e
        self.meta["aplicada"] = True
        self.salvar()
        return {"ok": True, "arquivos": aplicados, "backup": str(self.pasta / "base")}


def executar(acao, args, origem, agente, parar=None):
    with TRAVA:
        ctx = Contexto(origem, agente)
        if acao in ("codigo_preparar", "codigo_incluir"):
            r = ctx.preparar(str(args.get("arquivos") or ""), str(args.get("objetivo") or ""), acao == "codigo_incluir")
        else:
            ctx.carregar()
            if acao == "codigo_ler":
                return ctx.ler(args.get("caminho"), args.get("inicio") or 1)
            if acao == "codigo_substituir":
                return ctx.escrever(args.get("caminho"), str(args.get("depois") or ""), str(args.get("antes") or ""))
            if acao == "codigo_criar":
                return ctx.escrever(args.get("caminho"), str(args.get("conteudo") or ""))
            if acao == "codigo_verificar":
                r = ctx.verificar()
            elif acao == "codigo_testar":
                r = ctx.testar(args.get("caminho"), parar)
            elif acao == "codigo_revisar":
                r = ctx.revisar()
            else:
                raise ValueError("ferramenta de código desconhecida")
        return ("NÃO FEITO: " if r.get("ok") is False else "") + json.dumps(r, ensure_ascii=False)
