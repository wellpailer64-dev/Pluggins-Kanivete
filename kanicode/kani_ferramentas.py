"""Ferramentas "de uma tacada" para a Kani (4B): o que ela fazia em 5–10 passos e se perdia vira UMA chamada.
Cada uma devolve JSON curto e já mastigado (nomes, datas legíveis, contagens), pronto para ela contar ao Pailer."""
RECARREGAVEL = True
import json
import os
from pathlib import Path
import re
import time
import unicodedata

RAIZ_CLIENTES = Path(r'D:\01 - ALL IN CLOUD - HD PAILER\01 - PANDA LAB\01 - CLIENTES')
MAPA_CLIENTES = Path(__file__).resolve().parent.parent / 'pandalab' / 'mapa_clientes.json'
# lixo de programa (cache do Premiere/Audition, temporários) não é "conteúdo"
_LIXO_EXT = {'.pek', '.cfa', '.tmp', '.ini', '.db', '.lnk', '.log', '.bak', '.lock'}
_LIXO_PASTA = {'comprimidas', 'convertidas', 'favicon_gerados', '__pycache__', 'node_modules', 'cache', 'adobe premiere pro auto-save',
               'adobe premiere pro video previews', 'adobe premiere pro audio previews', 'auto-save'}
_MESES = 'janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro'
# pastas que só ORGANIZAM (ano, mês, pacote, "02 - PRODUÇÕES", "03 - PAUTAS ...") — a peça é a pasta logo abaixo delas
_ORGANIZA = re.compile(r'^(?:\d{4}|\d{1,2}\s*-\s*(?:' + _MESES + r')\b.*|.*\bpacote\b.*|\d{1,2}\s*-\s*(?:pautas?|produc\w*|conteudos?|posts?)\b.*|pautas?\b.*|produc\w*)$')


def sem_acento(s):
    return unicodedata.normalize('NFD', str(s).lower()).encode('ascii', 'ignore').decode()


def _data(ns):
    return time.strftime('%d/%m/%Y %H:%M', time.localtime(ns / 1e9))


def achar_cliente(nome):
    """nome/apelido do cliente → pasta dele. Prefere a mais específica (Oficina Produtiva dentro de Alessandro Barbosa)."""
    alvo = sem_acento(nome)
    palavras = [p for p in re.findall(r'[a-z0-9]+', alvo) if len(p) > 2 and p not in ('cliente', 'pasta', 'conteudo', 'ultimo', 'para', 'dele', 'dela', 'pro')]
    candidatos = {}
    try:
        d = json.loads(MAPA_CLIENTES.read_text(encoding='utf-8'))
        raiz = Path(d.get('raiz') or RAIZ_CLIENTES)
        for c in (d.get('clientes') or {}).values():
            if c.get('pasta'):
                candidatos[str(raiz / c['pasta'])] = {c.get('nome', ''), c['pasta'].split('\\')[-1]}
    except (OSError, ValueError):
        pass
    try:
        for p in RAIZ_CLIENTES.iterdir():
            if p.is_dir():
                candidatos.setdefault(str(p), set()).add(p.name)
                for q in p.iterdir():   # subcliente (ALESSANDRO BARBOSA\OFICINA PRODUTIVA)
                    if q.is_dir() and not re.match(r'^\d', q.name):
                        candidatos.setdefault(str(q), set()).add(q.name)
    except OSError:
        pass
    pontos = []
    for caminho, nomes in candidatos.items():
        if not Path(caminho).is_dir():
            continue
        melhor = 0
        for n in nomes:
            n = sem_acento(n)
            if n and len(n) > 2 and re.search(r'\b' + re.escape(n) + r'\b', alvo):
                melhor = max(melhor, 100 + len(n))   # nome inteiro citado
            else:
                toks = [t for t in re.findall(r'[a-z0-9]+', n) if len(t) > 2]
                if toks:
                    acertos = sum(t in palavras for t in toks)
                    if acertos: melhor = max(melhor, int(60 * acertos / len(toks)) + acertos)
        if melhor:
            pontos.append((melhor, len(Path(caminho).parts), caminho))
    if not pontos:
        return []
    pontos.sort(reverse=True)
    topo = pontos[0][0]
    bons = [p for p in pontos if p[0] >= topo * 0.6]
    # mais específica: se uma está dentro da outra, fica a de dentro
    caminhos = [Path(p[2]) for p in bons]
    finos = [c for c in caminhos if not any(o != c and o.is_relative_to(c) for o in caminhos)]
    return [str(c) for c in finos][:3]


def _arquivos(raiz, limite=60000):
    vistos, pilha = 0, [Path(raiz)]
    while pilha and vistos < limite:
        try:
            itens = list(os.scandir(pilha.pop()))
        except OSError:
            continue
        for d in itens:
            vistos += 1
            nome = d.name
            if nome.startswith(('.', '~$')):
                continue
            try:
                if d.is_dir(follow_symlinks=False):
                    if sem_acento(nome) not in _LIXO_PASTA: pilha.append(d.path)
                    continue
                if Path(nome).suffix.lower() in _LIXO_EXT:
                    continue
                st = d.stat()
                yield Path(d.path), st.st_mtime_ns, st.st_size
            except OSError:
                continue


def _peca(raiz, arquivo):
    """pasta da peça a que o arquivo pertence: a logo abaixo da última pasta organizadora (ano/mês/pautas)."""
    partes = arquivo.relative_to(raiz).parts[:-1]
    ultimo_org = -1
    for i, p in enumerate(partes):
        if _ORGANIZA.match(sem_acento(p).strip()):
            ultimo_org = i
    if ultimo_org + 1 < len(partes):
        return Path(raiz, *partes[:ultimo_org + 2])
    return arquivo   # arquivo solto: ele mesmo é a peça


def ultimos_conteudos(cliente='', pasta='', n=1):
    """Últimas peças (pastas de conteúdo) de um cliente, mais nova primeiro, com data, quantidade e arquivos."""
    n = max(1, min(int(n or 1), 8))
    raizes = [pasta] if pasta else achar_cliente(cliente)
    if not raizes:
        return {'ok': False, 'erro': f'Não achei pasta de cliente para "{cliente}". Clientes ficam em {RAIZ_CLIENTES}.'}
    raiz = Path(raizes[0])
    pecas = {}
    for arq, ns, tam in _arquivos(raiz):
        p = _peca(raiz, arq)
        info = pecas.setdefault(str(p), {'ns': 0, 'qtd': 0, 'bytes': 0, 'tipos': {}, 'pasta': p.is_dir()})
        info['ns'] = max(info['ns'], ns)
        info['qtd'] += 1
        info['bytes'] += tam
        ext = arq.suffix.lower().lstrip('.') or '?'
        info['tipos'][ext] = info['tipos'].get(ext, 0) + 1
    ordem = sorted(pecas.items(), key=lambda kv: kv[1]['ns'], reverse=True)[:n]
    saida = []
    for caminho, info in ordem:
        p = Path(caminho)
        arquivos = sorted(x.name for x in p.iterdir() if x.is_file() and x.suffix.lower() not in _LIXO_EXT)[:15] if info['pasta'] else [p.name]
        saida.append({'nome': p.name, 'caminho': caminho, 'e_pasta': info['pasta'], 'data': _data(info['ns']),
                      'arquivos': info['qtd'], 'tamanho_mb': round(info['bytes'] / 1e6, 1),
                      'tipos': info['tipos'], 'lista': arquivos,
                      'imagens': [str(p / a) for a in arquivos if a.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))][:10] if info['pasta'] else []})
    return {'ok': True, 'cliente': raiz.name, 'pasta_cliente': str(raiz), 'outras_pastas_possiveis': raizes[1:], 'ultimos': saida}


def resolver_caminho(caminho, pasta=None):
    """O 4B chuta caminhos ("D:\\08 - CARROSSEL...", "...\\ALESSANDRO BARBOSA\\Mini Bio.txt"). Se não existe, procura o NOME
    no mapa do disco D e devolve o caminho real quando o nome bate exatamente (sem acento/caixa). Senão devolve o original."""
    caminho = str(caminho).strip().rstrip('?!.,;:"\'').strip()   # "08 - CARROSSEL ...?" (o 4B copia a pontuação da frase)
    p = Path(caminho)
    if not caminho or p.exists():
        return caminho
    nome = sem_acento(p.name).strip()
    if len(nome) < 3:
        return str(caminho)
    try:
        import mapa_d
        r = mapa_d.buscar(p.name, '', '', limite=40, pastas=True)
    except Exception:
        return str(caminho)
    achados = [a for a in r.get('arquivos', []) if sem_acento(Path(a['caminho']).name).strip() == nome
               and (pasta is None or bool(a.get('pasta')) == pasta) and Path(a['caminho']).exists()]
    if not achados:
        return str(caminho)
    # vários com o mesmo nome: o que mais se parece com o caminho chutado (pastas em comum), depois o mais novo
    pedacos = {sem_acento(x) for x in p.parts[:-1]}
    achados.sort(key=lambda a: (len(pedacos & {sem_acento(x) for x in Path(a['caminho']).parts}), a.get('modificado_ns') or 0), reverse=True)
    return achados[0]['caminho']


def resumo_pasta(caminho, extensao=''):
    """Uma pasta inteira de uma vez: quantos arquivos, tipos, tamanho, mais novo/mais velho, subpastas."""
    p = Path(resolver_caminho(caminho, pasta=True))
    if not p.is_dir():
        return {'ok': False, 'erro': 'Pasta não existe: ' + str(p) + '. Procure o nome com mapa_d.'}
    qtd, total, tipos, novo, velho, novo_tipo = 0, 0, {}, None, None, {}
    ext_pedida, da_ext = str(extensao or '').lower().lstrip('.'), []
    for arq, ns, tam in _arquivos(p):
        qtd += 1
        total += tam
        ext = arq.suffix.lower().lstrip('.') or '?'
        tipos[ext] = tipos.get(ext, 0) + 1
        if ext not in novo_tipo or ns > novo_tipo[ext][1]: novo_tipo[ext] = (arq, ns)
        if ext_pedida and ext == ext_pedida: da_ext.append((ns, arq))
        if not novo or ns > novo[1]: novo = (arq, ns)
        if not velho or ns < velho[1]: velho = (arq, ns)
    try:
        subs = sorted(x.name for x in p.iterdir() if x.is_dir())
        soltos = sorted(x.name for x in p.iterdir() if x.is_file())
    except OSError:
        subs, soltos = [], []
    rel = lambda a: str(Path(a).relative_to(p)) if Path(a).is_relative_to(p) else str(a)   # caminhos curtos: cabem no contexto do 4B
    r = {'ok': True, 'pasta': str(p)}
    if ext_pedida:   # primeiro: é o que foi perguntado ("o PDF mais recente") e não pode sumir num corte do resumo
        r['extensao_pedida'] = {'extensao': ext_pedida, 'quantidade': len(da_ext),
                                'mais_novos': [{'arquivo': rel(a), 'data': _data(n)} for n, a in sorted(da_ext, reverse=True)[:5]]}
    r.update({'arquivos_total': qtd, 'tamanho_mb': round(total / 1e6, 1), 'tamanho_gb': round(total / 1e9, 2),
              'tipos': dict(sorted(tipos.items(), key=lambda kv: -kv[1])[:10]),
              'mais_novo': {'arquivo': rel(novo[0]), 'data': _data(novo[1])} if novo else None,
              'mais_velho': {'arquivo': rel(velho[0]), 'data': _data(velho[1])} if velho else None,
              'mais_novo_por_tipo': {e: {'arquivo': rel(novo_tipo[e][0]), 'data': _data(novo_tipo[e][1])}
                                     for e in list(dict(sorted(tipos.items(), key=lambda kv: -kv[1])))[:6]},
              'subpastas': subs[:30], 'arquivos_soltos': soltos[:20]})
    return r


PANDA = Path(__file__).resolve().parent.parent / 'pandalab' / 'panda.py'


def demandas(cliente='', status='abertas', tipo=''):
    """Demandas do Laboratório Panda já separadas em campos (o 4B lia a tabela de texto e inventava). Filtra pelo cliente."""
    import subprocess, sys
    exe = sys.executable.replace('pythonw', 'python')
    r = subprocess.run([exe, str(PANDA), 'demandas', '--status', status or 'abertas'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=90, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    itens = []
    for linha in r.stdout.splitlines():
        partes = re.split(r'\s{2,}', linha.strip())
        if len(partes) >= 5 and re.fullmatch(r'[0-9a-f]{8}', partes[0]):
            itens.append({'id': partes[0], 'status': partes[1], 'tipo': partes[2], 'cliente': partes[3], 'titulo': ' '.join(partes[4:])})
    if not itens and r.returncode:
        return {'ok': False, 'erro': (r.stderr or r.stdout)[-300:]}
    todos = len(itens)
    if cliente:
        alvo = [t for t in re.findall(r'[a-z0-9]+', sem_acento(cliente)) if len(t) > 2]
        itens = [i for i in itens if any(t in sem_acento(i['cliente']) for t in alvo)]
    if tipo:   # carrossel, reels, estático... (aceita plural e sem acento)
        alvo_t = sem_acento(tipo).rstrip('s')[:6]
        itens = [i for i in itens if sem_acento(i['tipo']).startswith(alvo_t)]
    por_cliente, por_tipo = {}, {}
    for i in itens:
        por_cliente[i['cliente']] = por_cliente.get(i['cliente'], 0) + 1
        por_tipo[i['tipo']] = por_tipo.get(i['tipo'], 0) + 1
    return {'ok': True, 'filtro_cliente': cliente or None, 'filtro_tipo': tipo or None, 'quantidade': len(itens),
            'total_abertas_sem_filtro': todos, 'por_cliente': por_cliente, 'por_tipo': por_tipo, 'demandas': itens}


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(ultimos_conteudos(' '.join(sys.argv[1:]) or 'Alessandro da Oficina Produtiva', n=3), ensure_ascii=False, indent=1)[:3000])
