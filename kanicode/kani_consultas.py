"""Consultas da Kani: documentos do PC e previsão com fonte e data, sem alterar os arquivos."""
from collections import deque
from pathlib import Path
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request


def normal(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(texto).lower()) if not unicodedata.combining(c))


def fonte_pedido(pedido):
    texto = normal(pedido)
    if re.search(r'\b(abr[ae]|abrir|acesse|acessar|entre)\b', texto) and not re.search(r'\b(bus\w*|procur\w*|che\w*|arquivos?|documentos?|pdf|orcamento|e-?mails?|mensagens?|caixa)\b', texto):
        return ''
    if re.search(r'\b(gmail|e-?mails?|caixa de entrada)\b', texto):
        return 'gmail'
    if re.search(r'\b(drive|google docs)\b', texto):
        return 'drive'
    if re.search(r'previsao do tempo|\b(clima|chover|chuva|temperatura)\b', texto):
        return 'clima'
    documento = re.search(r'\b(pdf|documentos?|arquivos?|orcamento|contrato)\b', texto)
    criar = re.search(r'\b(cri\w*|ger\w*|mont\w*|faca|fazer|escrev\w*)\b', texto)
    web = re.search(r'https?://|\b(site|internet|google|online|baixar)\b', texto)
    return 'pc' if documento and not criar and not web else ''


def buscar_arquivos(busca, pasta, raiz='', extensao='', prazo=6, limite=40):
    if not raiz and os.environ.get('KANICODE_TESTE') != '1':
        import mapa_d
        mapa_d.iniciar()
        indexado = mapa_d.buscar(busca, extensao=extensao, limite=limite)
        if indexado['arquivos'] or not indexado['parcial']:
            return indexado
    termos = normal(busca).split()
    if not termos or len(str(busca)) > 200:
        raise ValueError('Informe o nome do cliente ou parte do nome do arquivo.')
    extensao = str(extensao or '').lower().lstrip('.')
    if raiz:
        raizes = [Path(raiz).expanduser()]
    else:
        nuvem = Path(__file__).resolve().parents[3]
        raizes = [Path(pasta), Path.home() / 'Documents', Path.home() / 'Downloads', Path.home() / 'Desktop']
        if 'ALL IN CLOUD' in nuvem.name.upper():
            raizes.append(nuvem)
    if raiz and not Path(raiz).expanduser().is_dir():
        raise ValueError('A pasta informada não existe ou não está acessível.')
    fila = deque((r, r.name) for r in raizes if r.is_dir())
    visitados, arquivos, erros = set(), [], 0
    inicio = time.monotonic()
    ignorar = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'appdata', '$recycle.bin', 'system volume information', 'modelos_ia'}
    while fila and len(arquivos) < limite and time.monotonic() - inicio < prazo:
        diretorio, relativo = fila.popleft()
        chave = os.path.normcase(os.path.abspath(diretorio))
        if chave in visitados:
            continue
        visitados.add(chave)
        try:
            with os.scandir(diretorio) as itens:
                for item in itens:
                    if time.monotonic() - inicio >= prazo:
                        fila.append((diretorio, relativo)); break
                    caminho = relativo + '/' + item.name
                    if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
                        continue
                    if item.is_dir(follow_symlinks=False):
                        if item.name.lower() not in ignorar:
                            fila.append((Path(item.path), caminho))
                    elif item.is_file(follow_symlinks=False) and all(t in normal(caminho) for t in termos):
                        if not extensao or Path(item.name).suffix.lower() == '.' + extensao:
                            arquivos.append({'nome': item.name, 'caminho': item.path})
                            if len(arquivos) >= limite: break
        except OSError:
            erros += 1
    return {'arquivos': arquivos, 'parcial': bool(fila) or len(arquivos) >= limite, 'pastas_consultadas': len(visitados),
            'sem_acesso': erros, 'raizes': [str(r) for r in raizes if r.is_dir()],
            'aviso': 'Busca limitada ao nome e caminho; não pesquisou o conteúdo nem todo o PC. Se parcial, refine a pasta ou o nome.'}


def _json(url, parametros):
    pedido = urllib.request.Request(url + '?' + urllib.parse.urlencode(parametros), headers={'User-Agent': 'KaniCode/1'})
    with urllib.request.urlopen(pedido, timeout=15) as resposta:
        return json.load(resposta)


def previsao_tempo(cidade, dias=3):
    if not str(cidade or '').strip():
        raise ValueError('Pergunte ao Pailer a cidade; não presuma a localização.')
    locais = _json('https://geocoding-api.open-meteo.com/v1/search', {'name': cidade, 'count': 5, 'language': 'pt'}).get('results', [])
    # O geocodificador também retorna aeroportos e nomes parecidos com o da cidade.
    cidades = [l for l in locais if not l.get('feature_code') or l['feature_code'].startswith('PPL')]
    exatas = [l for l in cidades if normal(l['name']) == normal(str(cidade).split(',')[0].strip())]
    locais = exatas or cidades
    if not locais:
        raise ValueError('Cidade não encontrada. Peça cidade e estado ou país.')
    if len(locais) > 1:
        return {'escolher_local': [{'cidade': l['name'], 'estado': l.get('admin1'), 'pais': l.get('country')} for l in locais],
                'aviso': 'Mais de uma cidade encontrada. Pergunte qual estado/país e consulte novamente com cidade, estado ou país.'}
    local = locais[0]
    dados = _json('https://api.open-meteo.com/v1/forecast', {'latitude': local['latitude'], 'longitude': local['longitude'],
        'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max', 'timezone': 'auto',
        'forecast_days': max(1, min(7, int(dias)))})
    return {'local': {'cidade': local['name'], 'estado': local.get('admin1'), 'pais': local.get('country')},
            'previsao': dados.get('daily'), 'unidades': dados.get('daily_units'), 'fuso': dados.get('timezone'),
            'consultado_em': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'fonte': 'https://open-meteo.com/',
            'aviso': 'Previsão, não certeza. Use as datas e unidades retornadas.'}
