"""Consulta e substituição recuperável de artes; usa a sessão do plugin Pandalab."""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import unicodedata
import uuid
from contextlib import contextmanager

import pandalab as pl

OPERACOES = Path('D:/Kanivete/Pandalab/operacoes')
AVISO_DRIVE = 'Os anexos antigos saem da entrega; seus arquivos no Drive são preservados.'


def _normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(texto)).casefold()
                   if not unicodedata.combining(c))


def entregas(busca=None, cliente=None):
    """Paginação explícita: entregas já concluídas também entram na consulta."""
    rows, inicio = [], 0
    while True:
        lote = pl._ler('deliveries', select='id,short_id,title,content_type,client_tag_id,instagram_username,is_approved,'
                       'needs_adjustment,is_adjusted,created_at,client:client_tags!client_tag_id(name)',
                       order='created_at.desc,id.asc', limit='200', offset=str(inicio))
        rows.extend(lote)
        if len(lote) < 200:
            break
        inicio += len(lote)
    if cliente:
        rows = [r for r in rows if _normalizar(cliente) in _normalizar(
            (r.get('client') or {}).get('name') or r.get('instagram_username') or '')]
    if busca:
        termo = _normalizar(busca)
        rows = [r for r in rows if termo in _normalizar(r.get('title', ''))
                or termo == str(r.get('short_id')) or termo == str(r['id']).lower()]
    return rows


def entrega(ref):
    if not ref:
        raise pl.ErroPanda('Informe o número, título ou ID da entrega.')
    ref = str(ref)
    if re.fullmatch(r'[0-9a-fA-F-]{36}', ref):
        rows = pl._ler('deliveries', select='*', id='eq.' + ref)
    elif ref.isdecimal():
        rows = pl._ler('deliveries', select='*', short_id='eq.' + ref)
        if not rows:
            rows = [r for r in entregas() if str(r['id']).startswith(ref)]
    else:
        rows = [r for r in entregas() if _normalizar(ref) in _normalizar(r.get('title', ''))
                or str(r['id']).startswith(ref.lower())]
    if len(rows) != 1:
        raise pl.ErroPanda(f'A referência encontrou {len(rows)} entregas; use o número ou ID completo.')
    r = dict(pl._ler('deliveries', select='*', id='eq.' + rows[0]['id'])[0])
    r['itens'] = _itens(r['id'])
    return r


def _itens(eid):
    rows, inicio = [], 0
    while True:
        lote = pl._ler('delivery_items', select='*', delivery_id='eq.' + eid,
                       order='position.asc,id.asc', limit='200', offset=str(inicio))
        rows.extend(lote)
        if len(lote) < 200:
            return rows
        inicio += len(lote)


def _chave(item):
    return tuple(item.get(k) for k in ('id', 'delivery_id', 'file_path', 'file_type', 'position'))


def _arquivos(pasta):
    raiz = Path(pasta or '')
    if not pasta or not raiz.is_dir():
        raise pl.ErroPanda('Informe uma pasta existente com os arquivos finais.')
    def ordem(p):
        return [int(t) if t.isdecimal() else t.casefold() for t in re.split(r'(\d+)', p.name)]
    arquivos = sorted((p for p in raiz.iterdir() if p.is_file()
                       and p.suffix.lower() in pl.EXT_FINAIS), key=ordem)
    if not arquivos:
        raise pl.ErroPanda('A pasta não contém arquivos finais suportados.')
    resultado = []
    for p in arquivos:
        h = hashlib.sha256()
        with p.open('rb') as f:
            for bloco in iter(lambda: f.read(1024 * 1024), b''):
                h.update(bloco)
        if not p.stat().st_size:
            raise pl.ErroPanda(f'Arquivo vazio: {p.name}')
        resultado.append({'caminho': str(p.resolve()), 'nome': p.name,
                          'tamanho': p.stat().st_size, 'sha256': h.hexdigest()})
    return resultado


def _salvar(op):
    alvo = OPERACOES / (op['id'] + '.json')
    temporario = alvo.with_suffix('.tmp')
    with temporario.open('w', encoding='utf-8') as f:
        json.dump(op, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporario, alvo)


@contextmanager
def _trava(eid):
    OPERACOES.mkdir(parents=True, exist_ok=True)
    f = (OPERACOES / (eid + '.lock')).open('a+b')
    bloqueado = False
    try:
        if not f.tell():
            f.write(b'0')
            f.flush()
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            bloqueado = True
        except OSError as e:
            raise pl.ErroPanda('Já há uma operação nesta entrega. Aguarde sua conclusão.') from e
        yield
    finally:
        if bloqueado:
            f.seek(0)
            if os.name == 'nt':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def _carregar(oid):
    if not re.fullmatch(r'[0-9a-f]{32}', str(oid or '')):
        raise pl.ErroPanda('Identificador de operação inválido.')
    try:
        return json.loads((OPERACOES / (oid + '.json')).read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise pl.ErroPanda('Não foi possível ler o registro da operação.') from e


def operacoes(ref):
    eid = entrega(ref)['id']
    rows = []
    for p in OPERACOES.glob('*.json'):
        op = _carregar(p.stem)
        if op['entrega']['id'] == eid:
            rows.append(op)
    return sorted(rows, key=lambda x: x['criada'], reverse=True)


def _conferir(op, recuperar=False):
    atuais = {i['id']: i for i in _itens(op['entrega']['id'])}
    antigos = {i['id']: i for i in op['anteriores']}
    novos = {i['id']: i for i in op['novos']}
    esperados = {**antigos, **novos}
    if any(i not in esperados or _chave(item) != _chave(esperados[i]) for i, item in atuais.items()):
        raise pl.ErroPanda('A entrega foi alterada por outra operação. Nenhum anexo será descartado.')
    if not recuperar and op['fase'] not in ('removendo', 'concluida') and not antigos.keys() <= atuais.keys():
        raise pl.ErroPanda('Há anexos antigos ausentes. Confira a entrega ou recupere a operação.')
    return atuais


def _inserir_faltantes(op, desejados, recuperar=False):
    atuais = _conferir(op, recuperar)
    faltantes = [i for i in desejados if i['id'] not in atuais]
    if faltantes:
        # IDs persistidos antes do POST permitem conferir um timeout sem duplicar os anexos.
        pl._gravar('POST', 'delivery_items', faltantes)
    atuais = _conferir(op, recuperar)
    if not {i['id'] for i in desejados} <= atuais.keys():
        raise pl.ErroPanda('O sistema não aplicou a inclusão dos anexos; os antigos foram preservados.')


def _remover(op, itens):
    if itens:
        ids = ','.join(i['id'] for i in itens)
        pl._gravar('DELETE', 'delivery_items', None,
                   '?delivery_id=eq.' + op['entrega']['id'] + '&id=in.(' + ids + ')')


def _resumo(op):
    return {'operacao': op['id'], 'entrega': op['entrega']['id'], 'numero': op['entrega'].get('short_id'),
            'fase': op['fase'], 'arquivos': [a['nome'] for a in op['arquivos']],
            'quantidade': len(op['arquivos']), 'anexos_antigos': len(op['anteriores']),
            'destino_antigos': AVISO_DRIVE, 'registro': str(OPERACOES / (op['id'] + '.json'))}


def substituir(ref, pasta, sim=False, operacao=None, repetir_incerto=False, progresso=None):
    e = entrega(ref)
    arquivos = _arquivos(pasta)
    if not sim:
        return {'previa': True, 'numero': e.get('short_id'), 'titulo': e['title'],
                'arquivos': [a['nome'] for a in arquivos], 'anexos_antigos': len(e['itens']),
                'destino_antigos': AVISO_DRIVE}
    avisar = progresso or (lambda t: None)
    with _trava(e['id']):
        pendentes = [o for o in operacoes(e['id']) if o['fase'] not in ('concluida', 'recuperada')]
        op = _carregar(operacao) if operacao else (pendentes[0] if pendentes else None)
        if len(pendentes) > 1 or (pendentes and op['id'] != pendentes[0]['id']):
            raise pl.ErroPanda('Há outra operação pendente nesta entrega; conclua ou recupere primeiro.')
        if op and (op['entrega']['id'] != e['id'] or op['arquivos'] != arquivos):
            raise pl.ErroPanda('Entrega ou arquivos diferentes do registro. Retome com os originais ou recupere a operação.')
        if op and op['fase'] == 'recuperada':
            raise pl.ErroPanda('Esta operação já foi desfeita. Inicie outra sem --operacao.')
        if not op:
            # Repetir o mesmo comando já concluído não faz uploads novamente.
            concluidas = [o for o in operacoes(e['id']) if o['fase'] == 'concluida' and o['arquivos'] == arquivos]
            for anterior in concluidas:
                if {_chave(i) for i in e['itens']} == {_chave(i) for i in anterior['novos']}:
                    return _resumo(anterior)
            op = {'id': uuid.uuid4().hex, 'criada': time.time(), 'entrega': {k: v for k, v in e.items() if k != 'itens'},
                  'arquivos': arquivos, 'anteriores': e['itens'], 'uploads': [], 'novos': [], 'fase': 'uploads',
                  'incerto': None}
            _salvar(op)
        avisar('Operação ' + op['id'])
        try:
            if op['fase'] == 'recuperando':
                raise pl.ErroPanda('A recuperação foi iniciada; conclua recuperar-entrega.')
            _conferir(op)
            if op.get('incerto') is not None and not repetir_incerto:
                raise pl.ErroPanda('Upload sem confirmação. Use --repetir-incerto somente após conferir o Drive; pode gerar cópia extra.')
            for a in arquivos[len(op['uploads']):]:
                if _arquivos(pasta) != arquivos:
                    raise pl.ErroPanda('Os arquivos locais mudaram durante a operação.')
                op['incerto'] = a['nome']
                _salvar(op)
                cliente = (e.get('client') or {}).get('name') or e.get('instagram_username') or 'Cliente'
                f = pl._subir_drive(a['caminho'], cliente, e['title'])
                if not f.get('link') or not f.get('tipo'):
                    raise pl.ErroPanda('O upload não devolveu link e tipo válidos.')
                op['uploads'].append(f)
                op['novos'].append({'id': str(uuid.uuid4()), 'delivery_id': e['id'],
                                    'file_path': f['link'], 'file_type': f['tipo'], 'position': len(op['uploads']) - 1})
                op['incerto'] = None
                _salvar(op)
                avisar(f"Enviado {len(op['uploads'])}/{len(arquivos)}: {a['nome']}")
            if _arquivos(pasta) != arquivos:
                raise pl.ErroPanda('Os arquivos locais mudaram durante a operação.')
            if len({f['link'] for f in op['uploads']}) != len(arquivos):
                raise pl.ErroPanda('O serviço devolveu links repetidos. Confira o Drive antes de substituir os anexos.')
            _inserir_faltantes(op, op['novos'])
            op['fase'] = 'removendo'
            _salvar(op)
            _conferir(op)
            _remover(op, op['anteriores'])
            if {_chave(i) for i in _itens(e['id'])} != {_chave(i) for i in op['novos']}:
                raise pl.ErroPanda('O sistema não confirmou a retirada dos anexos antigos. Retome a mesma operação.')
            op['fase'] = 'concluida'
            op.pop('erro', None)
            _salvar(op)
            return _resumo(op)
        except Exception as erro:
            op['erro'] = str(erro)
            _salvar(op)
            raise pl.ErroPanda(f"Operação {op['id']} interrompida: {erro}. Registro: {OPERACOES / (op['id'] + '.json')}") from erro


def recuperar(ref, operacao, sim=False):
    e, op = entrega(ref), _carregar(operacao)
    if op['entrega']['id'] != e['id']:
        raise pl.ErroPanda('A operação pertence a outra entrega.')
    if not sim:
        return {'previa': True, 'operacao': op['id'], 'restaurar_anexos': len(op['anteriores']),
                'aviso': 'Restaura os anexos anteriores. Arquivos enviados ao Drive são preservados.'}
    with _trava(e['id']):
        op = _carregar(operacao)
        _conferir(op, recuperar=True)
        op['fase'] = 'recuperando'
        _salvar(op)
        antigos = [{k: i[k] for k in ('id', 'delivery_id', 'file_path', 'file_type', 'position')} for i in op['anteriores']]
        _inserir_faltantes(op, antigos, recuperar=True)
        _remover(op, op['novos'])
        if {_chave(i) for i in _itens(e['id'])} != {_chave(i) for i in antigos}:
            raise pl.ErroPanda('Recuperação não confirmada; retome recuperar-entrega com a mesma operação.')
        op['fase'] = 'recuperada'
        _salvar(op)
        return {'operacao': op['id'], 'fase': 'recuperada', 'anexos_restaurados': len(antigos),
                'aviso': 'Anexos anteriores restaurados; nenhum arquivo do Drive foi apagado.'}
