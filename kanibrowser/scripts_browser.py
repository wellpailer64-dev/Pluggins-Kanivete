"""Biblioteca de scripts locais confiáveis, limitada por origem e executada na aba da Kani."""
import fnmatch
import hashlib
import json
from pathlib import Path
import re

import kanibrowser as kb

PASTA = Path(__file__).resolve().parent / "scripts"


def _ler(nome):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", nome or ""):
        raise ValueError("Nome de script inválido.")
    arquivos = [PASTA / (nome + ext) for ext in (".json", ".js")]
    if any(p.resolve().parent != PASTA.resolve() for p in arquivos):
        raise ValueError("Script fora da biblioteca.")
    meta = json.loads(arquivos[0].read_text(encoding="utf-8"))
    origens = meta.get("origens")
    if not isinstance(origens, list) or not origens or not all(isinstance(o, str) and re.fullmatch(r"https?://[^/\s]+", o) for o in origens):
        raise ValueError("Informe as origens HTTP/HTTPS autorizadas no JSON do script.")
    if type(meta.get("altera_pagina")) is not bool:
        raise ValueError("Declare altera_pagina como true ou false.")
    codigo = arquivos[1].read_text(encoding="utf-8")
    return {**meta, "nome": nome, "sha256": hashlib.sha256(codigo.encode()).hexdigest()}, codigo


def comando(acao="listar", nome=None, dados=None, permitir_alteracao=False):
    if acao == "listar":
        return [_ler(p.stem)[0] for p in sorted(PASTA.glob("*.json"))]
    if acao != "rodar":
        raise ValueError("Use listar ou rodar.")
    meta, codigo = _ler(nome)
    if meta["altera_pagina"] and not permitir_alteracao:
        raise ValueError("Script altera a página; execução exige permitir_alteracao explícito.")
    # O monitor roda periodicamente em segundo plano; não deve acender o painel a cada conferência.
    with kb.trabalho("Script: " + nome, registrar=nome != "whatsapp_eventos") as aba:
        origem = kb.js("location.origin", aba)
        if not any(fnmatch.fnmatchcase(origem, p) for p in meta["origens"]):
            raise ValueError("Origem não autorizada para este script: " + str(origem))
        # Confere de novo dentro da mesma execução para evitar mudança de site entre chamadas.
        expressao = "(async () => { if (location.origin !== " + json.dumps(origem) + ") throw new Error('A página mudou.');\n"
        expressao += "return await (async (dados) => {\n" + codigo + "\n})(" + json.dumps(dados or {}, ensure_ascii=False) + "); })()"
        return {"nome": nome, "origem": origem, "sha256": meta["sha256"], "resultado": kb.js(expressao, aba)}
