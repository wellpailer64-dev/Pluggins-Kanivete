"""Base opcional para novas ferramentas; não registra ações nem dá permissões à Kani."""


def executar(argumentos, campos, observar, agir, conferir):
    """campos = {nome: tipo}; callbacks recebem somente argumentos validados.

    observar(args) lê o estado; agir(args) executa uma vez; conferir(antes, depois, args)
    deve devolver True somente quando o objetivo foi observado. A autorização pertence
    à ferramenta concreta, antes de chamar esta base. Não passe comandos livres do modelo.
    """
    resultado = {"ok": False, "etapa": "validar", "mensagem": "", "antes": None, "depois": None}
    try:
        if not isinstance(argumentos, dict) or set(argumentos) != set(campos):
            raise ValueError("argumentos ausentes ou desconhecidos: esperados " + ", ".join(campos))
        for nome, tipo in campos.items():
            valor = argumentos[nome]
            if type(valor) is not tipo or (tipo is str and not valor.strip()):
                raise ValueError("argumento inválido: " + nome)
        args = dict(argumentos)
        resultado["etapa"] = "observar"
        resultado["antes"] = observar(args)
        resultado["etapa"] = "agir"
        agir(args)
        resultado["etapa"] = "conferir"
        resultado["depois"] = observar(args)
        resultado["ok"] = conferir(resultado["antes"], resultado["depois"], args) is True
        resultado["mensagem"] = "CONFIRMADO: objetivo observado." if resultado["ok"] else "NÃO FEITO: objetivo não confirmado; confira o estado antes de tentar novamente."
    except Exception as e:
        resultado["mensagem"] = "NÃO FEITO em " + resultado["etapa"] + ": " + str(e)
    return resultado


def para_kani(resultado):
    """O executor atual da Kani recebe texto e reconhece o prefixo NÃO FEITO."""
    import json
    return resultado["mensagem"] + "\n" + json.dumps(resultado, ensure_ascii=False, default=str)
