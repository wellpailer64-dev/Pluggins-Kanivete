"""Restrições e dependências de consulta derivadas do pedido e de fontes verificadas."""
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import unicodedata


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFD',str(texto).casefold()) if not unicodedata.combining(c))


_FIM = r'(?=[.!?](?:\s|$)|;|\n|$|\s+mas\s+|\s+e\s+(?:leia|consulte|salve|envie)\b)'
_NEGACAO = re.compile(r'(?i)\b(?:n[aã]o|nunca)\s+(?:consulte|consultar|busque|buscar|procure|leia|ler|acesse|acessar|salve|salvar|grave|gravar|envie|enviar|apague|apagar|exclua|excluir|liste|listar|mostre|mostrar|anote|anotar|crie|criar|escreva|escrever|adicione|adicionar)\b.*?'+_FIM)
_ARQUIVO = r'(?:[A-Za-z]:[/\\])?(?:[\w.-]+[/\\])*[\w.-]+\.(?:txt|md|csv|json|pdf|docx|py|js|html|log|srt)'
_ACOES_NEGADAS = {
    'salvar_texto':r'\b(?:salve|salvar|grave|gravar|escreva|escrever)\b|\b(?:crie|criar)\b.*\b(?:arquivos?|textos?|txt)\b',
    'salvar_conversa':r'\b(?:salve|salvar|grave|gravar|escreva|escrever)\b|\b(?:crie|criar)\b.*\b(?:arquivos?|textos?|txt)\b',
    'escrever_arquivo':r'\b(?:salve|salvar|grave|gravar|escreva|escrever)\b|\b(?:crie|criar)\b.*\b(?:arquivos?|textos?|txt)\b',
    'todo_salvar':r'\b(?:anote|anotar|crie|criar|adicione|adicionar)\b.*\b(?:tarefas?|lembretes?)\b',
    'todo_listar':r'\b(?:consulte|consultar|liste|listar|mostre|mostrar)\b.*\b(?:tarefas?|pendencias?)\b',
    'ler_arquivo':r'\b(?:leia|ler|consulte|consultar)\b.*(?:\b(?:arquivos?|documentos?)\b|\.[a-z]{2,5}\b)',
    'whatsapp_enviar':r'\b(?:envie|enviar)\b',
    'drive_enviar':r'\b(?:envie|enviar)\b',
    'gmail_rascunho':r'\b(?:envie|enviar)\b',
    'apagar_arquivo':r'\b(?:apague|apagar|exclua|excluir)\b',
}


def pedido_positivo(pedido):
    return _NEGACAO.sub('',pedido)


def proibida(pedido, acao, args=None):
    regra=_ACOES_NEGADAS.get(acao)
    if not regra: return False
    positivo=normalizar(pedido_positivo(pedido))
    # A consulta do ramo verdadeiro não é proibida pela instrução do ramo contrário.
    if acao=='todo_listar' and re.search(regra,positivo) and condicional(pedido): return False
    for m in _NEGACAO.finditer(pedido):
        if not re.search(regra,normalizar(m[0])): continue
        alvos=re.findall(_ARQUIVO,m[0],re.I)
        if alvos and re.search(regra,positivo):
            if args is None: continue
            valores=' '.join(str(v) for v in args.values()).casefold()
            if not any(nome.casefold() in valores for nome in alvos): continue
        return True
    return False


def condicional(pedido):
    return bool(re.search(r'\b(?:somente se|apenas se|se\b.{0,50}\b(?:for|seja|estiver))',normalizar(pedido)))


def condicao(t):
    pedido=normalizar(pedido_positivo(t['pedido']))
    m=re.search(r'\bse\b.{0,50}?\b(?:for|seja|igual a)\s+(\d{2}/\d{2}/\d{4})',pedido)
    if m:
        datas=t.get('datas_consultadas',[])
        return m[1] in datas if datas else None
    m=re.search(r'\bse\b.{0,35}?\bstatus\s+(?:for|seja|estiver|igual a)\s+["\']?([\w-]+)',pedido)
    if m:
        estados=set()
        for fonte in t.get('fontes_lidas',{}).values():
            dados=interpretar(fonte['conteudo'])
            if isinstance(dados,dict) and isinstance(dados.get('status'),str): estados.add(normalizar(dados['status']))
        return m[1] in estados if len(estados)==1 else None
    return None if condicional(pedido) else True


def interpretar(bruto):
    if isinstance(bruto,(dict,list)): return bruto
    try: return json.loads(bruto)
    except (ValueError,TypeError): return None


def arquivos_pedidos(t):
    pedido=pedido_positivo(t['pedido'])
    nomes=[]
    verbos=r'\b(?:leia|ler|compare|comparar|encontre|encontrar|descubra|descobrir|procure|procurar|informe|informar|calcule|calcular|consulte|consultar|resuma|resumir|salve|salvar|crie|criar|escreva|escrever|edite|editar|altere|alterar)\b'
    escrita={'salve','salvar','crie','criar','escreva','escrever','edite','editar','altere','alterar'}
    ocorrencias=[]; citados=[]
    for m in re.finditer(r'["\']([^"\'\n]+\.(?:txt|md|csv|json|pdf|docx|py|js|html|log|srt))["\']',pedido,re.I):
        citados.append(m.span()); ocorrencias.append((m.start(),m[1]))
    for m in re.finditer(r'[A-Za-z]:[/\\][^"\n<>|]*?\.(?:txt|md|csv|json|pdf|docx|py|js|html|log|srt)(?![\w/\\])',pedido,re.I):
        if any(a<=m.start()<b for a,b in citados): continue
        citados.append(m.span()); ocorrencias.append((m.start(),m[0]))
    conhecidos=[Path(p).name for p in t.get('fontes_lidas',{})]
    for m in re.finditer(_ARQUIVO,pedido,re.I):
        if any(a<=m.start()<b for a,b in citados): continue
        inicio=m.start(); nome=m[0]
        for conhecido in conhecidos:
            a=m.end()-len(conhecido)
            if a>=0 and pedido[a:m.end()].casefold()==conhecido.casefold() and len(conhecido)>len(nome):
                inicio=a; nome=conhecido
        ocorrencias.append((inicio,nome))
    for inicio,nome in sorted(ocorrencias):
        anteriores=list(re.finditer(verbos,normalizar(pedido[:inicio])))
        if anteriores:
            ultimo=anteriores[-1]
            contexto=normalizar(pedido[:inicio])[ultimo.end():]
            if ultimo[0] in escrita and not re.search(r'\b(?:conteudo|resumo|dados) de\b',contexto): continue
        elif not re.search(r'(?i)\b(?:qual|quais|onde|resuma)\b',pedido[:inicio]):
            continue
        nomes.append(nome)
    # Só seguir referências quando o usuário pediu explicitamente essa navegação.
    if re.search(r'(?i)\b(?:apontad\w*|referenciad\w*|documento dos detalhes)\b',pedido):
        for caminho,fonte in t.get('fontes_lidas',{}).items():
            dados=interpretar(fonte['conteudo'])
            if not isinstance(dados,dict): continue
            for campo in ('documento','arquivo','caminho'):
                ref=dados.get(campo)
                if isinstance(ref,str) and re.fullmatch(_ARQUIVO,ref,re.I):
                    nomes.append(str(Path(caminho).parent/ref))
    return list(dict.fromkeys(nomes))


def fontes_faltantes(t):
    feitas=t.get('fontes_lidas',{})
    # Também aceita as etapas de execuções antigas, que não tinham o cache de fontes.
    caminhos=[str(Path(e.get('decisao',{}).get('args',{}).get('caminho','')).resolve()).casefold() for e in t['etapas']
              if e.get('status')=='concluida' and e.get('decisao',{}).get('acao')=='ler_arquivo' and e.get('decisao',{}).get('args',{}).get('caminho')]
    caminhos += [str(Path(p).resolve()).casefold() for p in feitas]
    faltam=[]
    for nome in arquivos_pedidos(t):
        alvo=Path(nome)
        completo=alvo.is_absolute() or alvo.parent!=Path('.')
        if not alvo.is_absolute(): alvo=Path(t.get('pasta','.'))/alvo
        if any(p==str(alvo.resolve()).casefold() if completo else Path(p).name.casefold()==Path(nome).name.casefold() for p in caminhos): continue
        faltam.append(nome)
    return faltam


def pede_tarefas(t):
    pedido=pedido_positivo(t['pedido'])
    return bool(re.search(r'(?i)\b(?:consulte|consultar|liste|listar|mostre|quais|verifique)\b[^.!?\n]{0,90}\b(?:tarefas?|pend[eê]ncias?|pendencias?)\b',pedido))


def pede_escolha(pedido):
    p=normalizar(pedido)
    return bool(re.search(r'\b(?:peca|pergunte|pedir)\b.{0,60}\b(?:escolh|qual|campanha)|\bnao escolha\b',p))


def escolhida(t):
    candidatos=t.get('candidatos_consulta',[])
    for info in reversed(t.get('informacoes',[])):
        texto=normalizar(info).strip(' .')
        if texto.isdigit() and 1<=int(texto)<=len(candidatos): return candidatos[int(texto)-1]
        if re.search(r'\b(?:nao sei|nao tenho certeza|nao escolhi|nenhum)\b',texto): return None
        nomes=[]
        for p in candidatos:
            pasta=normalizar(Path(p).parent.name)
            if normalizar(p) in texto or texto==pasta or (len(pasta)>=3 and re.search(r'(?<!\w)'+re.escape(pasta)+r'(?!\w)',texto)):
                nomes.append(p)
        if len(nomes)==1: return nomes[0]
    return candidatos[0] if len(candidatos)==1 and not t.get('busca_parcial') else None


def decimal(valor):
    if isinstance(valor,bool): raise ValueError('Booleano não é valor monetário.')
    try: numero=Decimal(str(valor))
    except InvalidOperation: raise ValueError('Valor numérico inválido.') from None
    if not numero.is_finite(): raise ValueError('Valor numérico não finito.')
    return numero


def total_itens(bruto):
    dados=interpretar(bruto)
    itens=dados.get('itens') if isinstance(dados,dict) else None
    if not isinstance(itens,list) or not itens: return None
    total=Decimal(0)
    try:
        for item in itens:
            if not isinstance(item,dict) or 'quantidade' not in item or 'valor_unitario' not in item: return None
            total+=decimal(item['quantidade'])*decimal(item['valor_unitario'])
    except (ValueError,TypeError): return None
    return format(total,'f')


def filtrar_tarefas(pedido, bruto):
    dados=interpretar(bruto)
    lista=dados.get('tarefas') if isinstance(dados,dict) else dados
    if not isinstance(lista,list) or not all(isinstance(x,dict) for x in lista): return bruto
    texto=normalizar(pedido_positivo(pedido))
    clientes={str(x['cliente']) for x in lista if isinstance(x.get('cliente'),str) and x['cliente'].strip()}
    pedidos=[c for c in clientes if re.search(r'\b'+re.escape(normalizar(c))+r'\b',texto)]
    if len(pedidos)==1: lista=[x for x in lista if normalizar(x.get('cliente',''))==normalizar(pedidos[0])]
    if re.search(r'\bpenden\w*|\bem aberto\b',texto): lista=[x for x in lista if x.get('concluida') is not True]
    return dict(dados,tarefas=lista) if isinstance(dados,dict) else lista


def atualizar(t,acao,args,bruto):
    if acao=='ler_arquivo':
        t.setdefault('fontes_lidas',{})[str(Path(args['caminho']).resolve())]={'conteudo':bruto}
    if acao in ('buscar_arquivos','mapa_d'):
        dados=interpretar(bruto)
        if isinstance(dados,dict):
            t['candidatos_consulta']=[a['caminho'] for a in dados.get('arquivos',[]) if isinstance(a,dict) and isinstance(a.get('caminho'),str) and Path(a['caminho']).is_file()]
            t['busca_parcial']=bool(dados.get('parcial'))


def caminho_pendente(t):
    for nome in fontes_faltantes(t):
        local=Path(nome) if Path(nome).is_absolute() else Path(t['pasta'])/nome
        if local.is_file(): return str(local.resolve())
        candidatos=[p for p in t.get('candidatos_consulta',[]) if Path(p).name.casefold()==Path(nome).name.casefold()]
        if len(candidatos)==1: return candidatos[0]
    return escolhida(t) if pede_escolha(t['pedido']) and not t.get('fontes_lidas') else None


def conferir_total(t,texto):
    if not re.search(r'(?i)\b(?:calcul\w*|total|som\w*)\b',t['pedido']): return True
    totais=[total_itens(f['conteudo']) for f in t.get('fontes_lidas',{}).values()]
    totais=[decimal(x) for x in totais if x is not None]
    if len(totais)!=1: return True
    m=re.search(r'(?i)\btotal\b[^\d\n]{0,45}(-?\d[\d.,]*)',texto)
    numeros=[m[1]] if m else re.findall(r'(?<![\w])\d[\d.,]*',texto)
    for numero in numeros:
        numero=numero.rstrip('.,')
        if ',' in numero: numero=numero.replace('.','').replace(',','.')
        try:
            if decimal(numero)==totais[0]: return True
        except ValueError: pass
    return False
