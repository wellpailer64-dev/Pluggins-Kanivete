"""Bateria simulada: catálogo explícito, seleção por impacto, evidências e liberação verificável."""
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import py_compile
import statistics
import subprocess
import sys
import threading
import time

CATALOGO = 'tests/contratos_regressao.json'


def relativo(raiz, nome):
    raiz = Path(raiz).resolve()
    p = (raiz / nome).resolve()
    if not p.is_relative_to(raiz) or not p.is_file():
        raise ValueError('arquivo inexistente ou fora do plugin: ' + str(nome))
    return p.relative_to(raiz).as_posix()


def carregar(raiz):
    raiz = Path(raiz).resolve()
    try:
        m = json.loads((raiz / CATALOGO).read_text(encoding='utf-8'))
        if m.get('versao') != 1 or not isinstance(m.get('grupos'), list) or not m['grupos']:
            raise ValueError('catálogo inválido')
        vistos, revisados = set(), set()
        for g in m['grupos']:
            if not isinstance(g['id'], str) or g['id'] in vistos or not g['testes'] or not isinstance(g['prazo_s'], int) or not 1 <= g['prazo_s'] <= 180:
                raise ValueError('grupo repetido, vazio ou com prazo inválido')
            if not isinstance(g['arquivos'], list) or not isinstance(g['testes'], list) or len(set(g['testes'])) != len(g['testes']):
                raise ValueError('listas de arquivos/testes inválidas ou repetidas')
            if not isinstance(g['essencial'], bool) or not isinstance(g['rapido'], bool):
                raise ValueError('essencial e rapido precisam ser booleanos')
            vistos.add(g['id'])
            for t in g['testes']:
                nome = relativo(raiz, t)
                if not nome.startswith('tests/test_') or not nome.endswith('.py'):
                    raise ValueError('teste fora do catálogo de suítes: ' + nome)
                revisados.add(nome)
            for padrao in g['arquivos']:
                encontrados = list(raiz.glob(padrao))
                if Path(padrao).is_absolute() or '..' in Path(padrao).parts or not encontrados or any(not p.resolve().is_relative_to(raiz) for p in encontrados):
                    raise ValueError('padrão sem arquivo ou fora do projeto: ' + padrao)
        for nome in m['centrais']:
            relativo(raiz, nome)
        for nome, classificacao in m.get('classificacoes', {}).items():
            relativo(raiz, nome)
            if nome in revisados or classificacao['tipo'] not in ('manual', 'real', 'pendente') or not classificacao['motivo']:
                raise ValueError('classificação sem motivo ou simulada fora de grupo: ' + nome)
        return m
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError('estrutura do catálogo inválida: ' + str(e)) from e

def inventario(raiz, m=None):
    raiz = Path(raiz)
    m = m or carregar(raiz)
    revisados = {t for g in m['grupos'] for t in g['testes']}
    saida = []
    for p in sorted((raiz / 'tests').glob('test_*.py')):
        nome = p.relative_to(raiz).as_posix()
        info = dict(m.get('classificacoes', {}).get(nome, {}))
        if nome in revisados:
            info = {'tipo': 'simulado', 'motivo': 'Cenários catalogados; motores e serviços substituídos ou processos locais isolados.'}
        info.setdefault('tipo', 'pendente')
        info.setdefault('motivo', 'Revisar efeitos externos e isolamento antes de incluir na bateria simulada.')
        try:
            arvore = ast.parse(p.read_text(encoding='utf-8-sig'))
            info['casos_declarados'] = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(arvore))
        except (SyntaxError, UnicodeError) as e:
            info.update(tipo='invalido', motivo=str(e), casos_declarados=0)
        saida.append(dict(info, arquivo=nome))
    return saida


def selecionar(raiz, bateria='essencial', alterados=(), areas=None):
    raiz = Path(raiz).resolve()
    m = carregar(raiz)
    nomes = [relativo(raiz, n) for n in alterados]
    if bateria not in ('essencial', 'rapida', 'completa', 'carga'):
        raise ValueError('bateria desconhecida')
    grupos, motivos, lacunas = {}, {}, []
    def incluir(g, motivo):
        grupos[g['id']] = g
        if motivo not in motivos.setdefault(g['id'], []):
            motivos[g['id']].append(motivo)
    for g in m['grupos']:
        if bateria == 'completa' or (bateria == 'essencial' and g.get('essencial')) or (bateria == 'rapida' and g.get('rapido')) or (bateria == 'carga' and g['id'] == 'carga'):
            incluir(g, 'bateria ' + bateria)
    for nome in nomes:
        if nome in m['centrais']:
            for g in m['grupos']:
                if g.get('essencial') or g.get('transversal'):
                    incluir(g, 'arquivo transversal: ' + nome)
            continue
        encontrados = [g for g in m['grupos'] if nome in g['testes'] or any(fnmatch.fnmatchcase(nome, p) for p in g['arquivos'])]
        for g in encontrados:
            incluir(g, 'impacto de ' + nome)
        if not encontrados and Path(nome).suffix.lower() not in ('.md', '.txt'):
            lacunas.append('Sem contrato de impacto: ' + nome)
    if areas and nomes:
        revisados = {t for g in m['grupos'] for t in g['testes']}
        for area, padroes in areas.items():
            atingidos = [n for n in nomes if n not in m['centrais'] and any(fnmatch.fnmatchcase(n, p.replace('\\', '/')) for p in padroes if not p.startswith('tests/'))]
            if not atingidos:
                continue
            for padrao in padroes:
                if padrao.startswith('tests/test_'):
                    for p in raiz.glob(padrao):
                        t = p.relative_to(raiz).as_posix()
                        if t not in revisados:
                            tipo = m.get('classificacoes', {}).get(t, {}).get('tipo')
                            motivo = ' exige integração fora da bateria simulada: ' if tipo in ('real', 'manual') else ' exige classificar: '
                            lacunas.append('Impacto na área ' + area + motivo + t)
                        else:
                            for g in m['grupos']:
                                if t in g['testes']:
                                    incluir(g, 'integração da área ' + area)
    inv = inventario(raiz, m)
    if bateria == 'completa':
        lacunas.extend('Inventário ainda não classificado: ' + x['arquivo'] for x in inv if x['tipo'] in ('pendente', 'invalido'))
    arquivos, testes = set(nomes), {}
    arquivos.update([CATALOGO, 'regressao.py', 'teste_isolado.py', 'verificar.py'])
    for g in grupos.values():
        for padrao in g['arquivos']:
            arquivos.update(p.relative_to(raiz).as_posix() for p in raiz.glob(padrao) if p.is_file())
        for t in g['testes']:
            arquivos.add(t)
            testes[t] = max(testes.get(t, 0), g['prazo_s'])
    return {'bateria': bateria, 'alterados': nomes, 'arquivos': sorted(arquivos), 'testes': testes,
            'motivos': motivos, 'lacunas': sorted(set(lacunas)), 'inventario': inv,
            'excluidos': [i for i in inv if i['tipo'] in ('real', 'manual')]}


def impressao(raiz):
    """Inclui código, testes, assets e catálogo; exclui saídas e metadados git."""
    raiz = Path(raiz).resolve()
    extensoes = {'.py', '.js', '.html', '.css', '.json'}
    arquivos = set()
    for pasta in (raiz, raiz / 'ui', raiz / 'tests'):
        for p in pasta.rglob('*') if pasta != raiz else pasta.iterdir():
            if p.is_file() and p.suffix.lower() in extensoes and '__pycache__' not in p.parts:
                arquivos.add(p)
    h = hashlib.sha256()
    for p in sorted(arquivos):
        h.update(p.relative_to(raiz).as_posix().encode('utf-8') + b'\0')
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def ambiente_suite(saida, nome):
    base = Path(saida) / 'suites' / nome
    base.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, KANICODE_TESTE='1', KANICODE_REGRESSAO='1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    for chave, pasta in {'KANICODE_DADOS_TESTE': 'dados', 'CODEX_HOME': 'codex', 'CLAUDE_CONFIG_DIR': 'claude',
                         'APPDATA': 'appdata', 'LOCALAPPDATA': 'localappdata', 'TEMP': 'tmp', 'TMP': 'tmp',
                         'CEREBRO_PASTA_MODELO': 'modelos',
                         'PYTHONPYCACHEPREFIX': 'pycache'}.items():
        destino = base / pasta
        destino.mkdir(exist_ok=True)
        env[chave] = str(destino)
    env['KANICODE_RESULTADO_TESTE'] = str(base / 'casos.jsonl')
    return base, env


def rodar_suite(raiz, saida, teste, prazo, repeticao):
    from codex_processo import _job, _encerrar, _SEM_JANELA
    base, env = ambiente_suite(saida, Path(teste).stem + '_' + str(repeticao))
    env['KANICODE_TESTE_PRAZO'] = str(prazo)
    inicio = time.perf_counter()
    print(f'EM ANDAMENTO: {teste} (repetição {repeticao}, prazo {prazo}s)', flush=True)
    comando = [sys.executable, '-u', str(Path(raiz) / 'teste_isolado.py'), Path(teste).name]
    status, erro = 'falhou', ''
    with (base / 'saida.log').open('w', encoding='utf-8') as log:
        try:
            p = subprocess.Popen(comando, cwd=raiz, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace', creationflags=_SEM_JANELA)
            job = _job(p)
            def ler():
                for linha in p.stdout:
                    log.write(linha); log.flush()
            leitor = threading.Thread(target=ler, daemon=True)
            leitor.start()
            try:
                codigo = p.wait(timeout=prazo)
                status = 'aprovado' if codigo == 0 else 'falhou'
            except subprocess.TimeoutExpired:
                status, erro = 'timeout', 'Prazo da suíte excedido; consulte a última etapa e o stack em saida.log'
                _encerrar(p, job)
                p.wait(timeout=5)
            finally:
                if job:
                    job[0].CloseHandle(job[1])
                leitor.join(timeout=3)
                if leitor.is_alive():
                    status, erro = 'falhou', 'O leitor de saída não terminou'
        except OSError as e:
            erro = str(e)
    eventos = []
    caso = base / 'casos.jsonl'
    if caso.exists():
        for linha in caso.read_text(encoding='utf-8').splitlines():
            try:
                eventos.append(json.loads(linha))
            except ValueError:
                status, erro = 'falhou', 'Registro de caso inválido'
    finais = [e for e in eventos if e.get('evento') == 'fim']
    inicios = [e for e in eventos if e.get('evento') == 'inicio']
    fechamentos = [e for e in eventos if e.get('evento') == 'suite_fim']
    from collections import Counter
    completo = (len(fechamentos) == 1 and fechamentos[0].get('ok') and fechamentos[0].get('casos') == len(finais)
                and Counter(e['caso'] for e in inicios) == Counter(e['caso'] for e in finais))
    if status == 'aprovado' and (not completo or not finais or any(e['status'] != 'aprovado' for e in finais)):
        status, erro = 'incompleto', 'Caso ignorado, indisponível ou sem evidência final'
    return {'teste': teste, 'status': status, 'ms': round((time.perf_counter() - inicio) * 1000, 2),
            'repeticao': repeticao, 'erro': erro, 'casos': finais, 'log': str(base / 'saida.log'),
            'comando': comando, 'eventos': str(caso)}


def validar_liberacao(raiz, relatorio):
    r = json.loads(Path(relatorio).read_text(encoding='utf-8'))
    if r.get('versao') != 1 or r.get('status') != 'aprovado' or r.get('lacunas') or not r.get('resultados'):
        raise ValueError('relatório reprovado ou incompleto; aplicação bloqueada')
    if r.get('raiz') != str(Path(raiz).resolve()) or r.get('impressao') != impressao(raiz):
        raise ValueError('o projeto mudou depois da verificação; execute novamente')
    if r.get('bateria') not in ('essencial', 'completa'):
        raise ValueError('reinício validado exige bateria essencial + impacto')
    esperados = {(t, n) for t in r['selecao']['testes'] for n in range(1, r['repeticoes'] + 1)}
    obtidos = [(x['teste'], x['repeticao']) for x in r['resultados']]
    essenciais = set(selecionar(raiz)['testes'])
    if set(obtidos) != esperados or len(obtidos) != len(esperados) or not essenciais.issubset(r['selecao']['testes']):
        raise ValueError('faltam evidências da bateria essencial ou das repetições')
    if any(x['status'] == 'falhou' for x in r.get('sintaxe', [])):
        raise ValueError('há falha de sintaxe')
    for item in r['resultados']:
        if item['status'] != 'aprovado' or not item.get('casos') or any(c['status'] != 'aprovado' for c in item['casos']):
            raise ValueError('há suíte ou caso não aprovado')
    return r


def executar(raiz, selecao, saida, scripts, workers=1, repeticoes=1):
    raiz, saida = Path(raiz).resolve(), Path(saida).resolve()
    if not saida.is_relative_to(Path('D:/kanivete_testes').resolve()):
        raise ValueError('saída deve ficar em D:/kanivete_testes')
    if not 1 <= workers <= 4 or not 1 <= repeticoes <= 5:
        raise ValueError('workers: 1–4; repetições: 1–5')
    saida.mkdir(parents=True, exist_ok=True)
    inicio, antes = time.perf_counter(), impressao(raiz)
    r = dict(versao=1, raiz=str(raiz), bateria=selecao['bateria'], impressao=antes,
             lacunas=selecao['lacunas'], selecao=selecao, resultados=[], sintaxe=[], status='incompleto')
    destino = saida / 'resultado.json'
    def gravar():
        destino.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    gravar()
    if not r['lacunas']:
        for i, nome in enumerate(selecao['arquivos']):
            p = raiz / nome
            try:
                if p.suffix == '.py':
                    py_compile.compile(str(p), cfile=str(saida / f'sintaxe_{i}.pyc'), doraise=True)
                elif p.suffix in ('.js', '.html'):
                    entradas = [(str(p), False)] if p.suffix == '.js' else []
                    if p.suffix == '.html':
                        parser = scripts(); parser.feed(p.read_text(encoding='utf-8'))
                        for j, (texto, modulo) in enumerate(parser.scripts):
                            arq = saida / (f'inline_{i}_{j}' + ('.mjs' if modulo else '.js'))
                            arq.write_text(texto, encoding='utf-8'); entradas.append((str(arq), modulo))
                    for arq, _ in entradas:
                        proc = subprocess.run(['node', '--check', arq], capture_output=True, text=True,
                                              encoding='utf-8', errors='replace', timeout=15)
                        if proc.returncode:
                            raise ValueError(proc.stderr)
                r['sintaxe'].append({'arquivo': nome, 'status': 'aprovado' if p.suffix in ('.py', '.js', '.html') else 'nao_aplicavel'})
            except (OSError, ValueError, py_compile.PyCompileError, subprocess.TimeoutExpired) as e:
                r['sintaxe'].append({'arquivo': nome, 'status': 'falhou', 'erro': str(e)})
        if not any(x['status'] == 'falhou' for x in r['sintaxe']):
            for repeticao in range(1, repeticoes + 1):
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futuros = {pool.submit(rodar_suite, raiz, saida, t, prazo, repeticao): t for t, prazo in selecao['testes'].items()}
                    for f in as_completed(futuros):
                        try:
                            item = f.result()
                        except Exception as e:
                            item = {'teste': futuros[f], 'status': 'falhou', 'erro': str(e), 'ms': 0, 'repeticao': repeticao, 'casos': []}
                        r['resultados'].append(item)
                        print(f"{item['status'].upper()}: {item['teste']} ({item['ms']:.0f} ms)", flush=True)
                        gravar()
    mudou = impressao(raiz) != antes
    if mudou:
        r['lacunas'] = r['lacunas'] + ['Arquivos mudaram durante a verificação']
    if r['lacunas']:
        r['status'] = 'incompleto'
    elif any(x['status'] != 'aprovado' for x in r['resultados']) or any(x['status'] == 'falhou' for x in r['sintaxe']):
        r['status'] = 'falhou'
    elif len(r['resultados']) == len(selecao['testes']) * repeticoes and r['resultados']:
        r['status'] = 'aprovado'
    tempos = [x['ms'] for x in r['resultados']]
    r.update(ms=round((time.perf_counter() - inicio) * 1000, 2), workers=workers, repeticoes=repeticoes,
             mediana_suite_ms=statistics.median(tempos) if tempos else None,
             python=sys.version, modo='simulado sem modelos; processos/UI locais reais',
             perfil_tempos={t: [x['ms'] for x in r['resultados'] if x['teste'] == t] for t in selecao['testes']})
    gravar()
    print(f"{r['status'].upper()}: relatório {destino}", flush=True)
    return 0 if r['status'] == 'aprovado' else 1
