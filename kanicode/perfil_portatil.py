"""Perfil portátil v1: preferências e ensinamentos, com revisão de conflitos antes de restaurar."""
from pathlib import Path, PurePosixPath
import argparse
import difflib
import hashlib
import json
import os
import re
import tempfile
import time
import uuid

APP = Path(__file__).resolve().parent
from dados_app import pasta_dados
DADOS = pasta_dados()
LIMITE = 20 * 1024 * 1024
CHAVES_ESTADO = {'quem', 'fixa', 'sons_bolinha'}
PASTAS = {'regras': {'.md'}, 'licoes': {'.jsonl'}, 'preferencias': {'.json', '.md'}, 'contratos': {'.json', '.md'}, 'cerebro': {'.json', '.jsonl', '.md'}}
EXCLUIDOS = ['Credenciais e autorizações de contas', 'Conversas e sessões em andamento', 'Caminhos de projetos e dispositivos',
             'Mapa do disco, caches e modelos de IA', 'Código das ferramentas integradas (pertence à instalação)']


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _hash(valor):
    return hashlib.sha256(valor.encode('utf-8')).hexdigest()


def _ler(caminho, padrao=None):
    try: return json.loads(Path(caminho).read_text(encoding='utf-8'))
    except FileNotFoundError: return padrao


def _gravar(caminho, conteudo):
    p = Path(caminho); p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=p.parent, delete=False, suffix='.tmp') as f:
        tmp = Path(f.name); f.write(conteudo); f.flush(); os.fsync(f.fileno())
    try: os.replace(tmp, p)
    finally:
        if tmp.exists(): tmp.unlink()


def _permitido(nome):
    if not isinstance(nome,str): return False
    if any(ord(c)<32 for c in nome): return False
    p = PurePosixPath(nome)
    if any(re.match(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', parte, re.I) for parte in p.parts): return False
    if not isinstance(nome,str) or '\\' in nome or ':' in nome or p.is_absolute() or '..' in p.parts or p.as_posix() != nome:
        return False
    if nome in ('estado_portatil.json','kani_notas.md','rotinas.json','perfil/usuario.json'): return True
    return len(p.parts)>1 and p.parts[0] in PASTAS and p.suffix.lower() in PASTAS[p.parts[0]] and not any(x.startswith('.') for x in p.parts)


def _destino(nome, dados):
    p = Path(dados).resolve() / ('perfil/rotinas.json' if nome=='rotinas.json' else 'estado.json' if nome=='estado_portatil.json' else nome)
    base = Path(dados).resolve()
    if not p.resolve().is_relative_to(base): raise ValueError('Destino fora dos dados do KaniCode.')
    cursor = p
    while cursor != base:
        if cursor.is_symlink() or (hasattr(cursor,'is_junction') and cursor.is_junction()): raise ValueError('Links e junções não são restaurados pelo perfil.')
        cursor = cursor.parent
    return p


def _validar_conteudo(nome, texto):
    if not _permitido(nome) or not isinstance(texto,str) or len(texto.encode('utf-8'))>2*1024*1024:
        raise ValueError('Arquivo não permitido ou grande demais no perfil: '+str(nome))
    if nome.endswith('.json'):
        valor = json.loads(texto)
        if not isinstance(valor,(dict,list)): raise ValueError('JSON de perfil inválido: '+nome)
        if nome=='perfil/usuario.json':
            from perfil_usuario import CAMPOS
            if not isinstance(valor,dict) or set(valor)-set(CAMPOS) or any(not isinstance(v,str) or len(v)>200 for v in valor.values()):
                raise ValueError('Cadastro do perfil inválido.')
        if nome=='estado_portatil.json':
            if not isinstance(valor,dict) or set(valor)-CHAVES_ESTADO: raise ValueError('Configuração de máquina ou conta não pode ser restaurada pelo perfil.')
            if 'quem' in valor and valor['quem'] not in ('claude','codex','kani','pickle'): raise ValueError('Agente padrão inválido.')
            if any(type(v) is not bool for k,v in valor.items() if k!='quem'): raise ValueError('Preferência de interface inválida.')
        if nome=='rotinas.json':
            if not isinstance(valor,dict) or not isinstance(valor.get('rotinas'),list): raise ValueError('Rotinas inválidas.')
            nomes = set()
            for rotina in valor['rotinas']:
                if not isinstance(rotina,dict) or not isinstance(rotina.get('name'),str) or not rotina['name'].isidentifier() or rotina['name'] in nomes:
                    raise ValueError('Nome de rotina inválido ou repetido.')
                if rotina['name'] in {'codex','kani','missao','licao','mapa_d'}: raise ValueError('Rotina não pode substituir uma ferramenta integrada.')
                if not isinstance(rotina.get('description'),str): raise ValueError('Descrição de rotina ausente.')
                if not isinstance(rotina.get('args',{}),dict) or any(not isinstance(v,dict) for v in rotina.get('args',{}).values()): raise ValueError('Argumentos de rotina inválidos.')
                nomes.add(rotina['name'])
                if not isinstance(rotina.get('cmd'),list) or not rotina['cmd'] or not all(isinstance(x,str) for x in rotina['cmd']): raise ValueError('Comando de rotina inválido.')
    elif nome.endswith('.jsonl'):
        for linha in texto.splitlines():
            if linha.strip() and not isinstance(json.loads(linha),dict): raise ValueError('Lição inválida.')


def rotinas(dados=DADOS, app=APP):
    """A personalização fica nos dados do perfil, separada do código instalado."""
    out={}
    for p in [Path(app)/'rotinas.json',Path(dados)/'perfil/rotinas.json']:
        try:
            valor=_ler(p,{'rotinas':[]})
            _validar_conteudo('rotinas.json',_json(valor))
            out.update({r['name']:r for r in valor['rotinas']})
        except (OSError,ValueError,TypeError,KeyError):
            continue
    return out


def coletar(dados=DADOS, app=APP):
    dados, app = Path(dados), Path(app)
    estado = _ler(dados/'estado.json', {})
    itens = {'estado_portatil.json': _json({k:v for k,v in estado.items() if k in CHAVES_ESTADO})}
    candidatos = [dados/'kani_notas.md', dados/'perfil/usuario.json']
    for nome, extensoes in PASTAS.items():
        base = dados/nome
        if base.exists(): candidatos += [p for p in base.rglob('*') if p.is_file() and p.suffix.lower() in extensoes]
    for p in candidatos:
        if not p.exists(): continue
        nome = p.relative_to(dados).as_posix()
        _destino(nome,dados)
        if p.stat().st_size>2*1024*1024: raise ValueError('Arquivo grande demais: '+nome)
        itens[nome] = p.read_text(encoding='utf-8')
    # Memórias das contas viram referências portáteis, sem levar a conta ou seus tokens.
    for p in sorted((dados/'contas').glob('*/projects/*/memory/*.md')):
        if p.name.upper()=='MEMORY.MD': continue
        _destino(p.relative_to(dados).as_posix(),dados)
        if p.stat().st_size>2*1024*1024: raise ValueError('Memória grande demais: '+p.name)
        projeto=p.parent.parent.name
        nome='cerebro/memorias/'+projeto+'/'+p.name
        itens[nome]=p.read_text(encoding='utf-8')
    rotinas = {}
    for p in [app/'rotinas.json', dados/'perfil/rotinas.json']:
        obj = _ler(p,{})
        for rotina in obj.get('rotinas',[]): rotinas[rotina['name']] = rotina
    if rotinas: itens['rotinas.json'] = _json({'rotinas':list(rotinas.values())})
    for nome,texto in itens.items(): _validar_conteudo(nome,texto)
    if len(itens)>1000 or sum(len(t.encode('utf-8')) for t in itens.values())>LIMITE: raise ValueError('Perfil ultrapassa o limite de tamanho.')
    return itens


def _aplicativo(app=APP):
    app=Path(app)
    fontes=list(app.glob('*.py'))+[p for p in (app/'ui').glob('*') if p.suffix in ('.js','.css','.html')]
    hashes={p.relative_to(app).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(fontes)}
    return {'assinatura':_hash(_json(hashes)), 'componentes':len(hashes),
            'observacao':'Ferramentas integradas são código da instalação. Use a versão correspondente no outro computador.'}


def identidade(dados=DADOS):
    p=_destino('perfil/identidade.json',dados)
    existente=_ler(p)
    if existente: return existente
    valor={'id':str(uuid.uuid4()),'nome':'Meu perfil KaniCode'}
    _gravar(p,_json(valor)); return valor


def montar(dados=DADOS, app=APP):
    itens=coletar(dados,app)
    return {'formato':'kanicode-perfil','versao':1,'perfil':identidade(dados),
            'criado_em':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'revisao':_hash(_json(itens)),
            'aplicativo':_aplicativo(app),'itens':{n:{'texto':t,'sha256':_hash(t)} for n,t in itens.items()},'nao_incluidos':EXCLUIDOS}


def validar(texto):
    if not isinstance(texto,str) or len(texto.encode('utf-8'))>LIMITE*2: raise ValueError('Pacote grande demais ou inválido.')
    p=json.loads(texto)
    if not isinstance(p,dict) or p.get('formato')!='kanicode-perfil' or p.get('versao')!=1: raise ValueError('Formato ou versão de perfil incompatível.')
    if not isinstance(p.get('perfil'),dict) or not isinstance(p['perfil'].get('nome'),str): raise ValueError('Identidade do perfil inválida.')
    uuid.UUID(p['perfil']['id'])
    if len(p['perfil']['nome'])>120: raise ValueError('Nome de perfil grande demais.')
    itens=p.get('itens')
    if not isinstance(itens,dict) or len(itens)>1000: raise ValueError('Lista de arquivos inválida.')
    conteudos={}
    for nome,arq in itens.items():
        if not isinstance(arq,dict): raise ValueError('Arquivo de perfil inválido.')
        t=arq.get('texto'); _validar_conteudo(nome,t)
        if arq.get('sha256')!=_hash(t): raise ValueError('Integridade inválida: '+nome)
        conteudos[nome]=t
    if sum(len(t.encode('utf-8')) for t in conteudos.values())>LIMITE: raise ValueError('Perfil grande demais.')
    if p.get('revisao')!=_hash(_json(conteudos)): raise ValueError('Revisão do pacote não confere.')
    return p


def previa(texto, dados=DADOS, app=APP):
    pacote=validar(texto); local=coletar(dados,app); linhas=[]
    for nome,arq in pacote['itens'].items():
        atual=local.get(nome); novo=arq['texto']
        if nome=='rotinas.json' and not (Path(dados)/'perfil/rotinas.json').exists():
            atual=None   # materializa a personalização nos dados, mesmo se coincidir com a instalação
        estado='igual' if atual==novo else 'novo' if atual is None else 'conflito'
        linhas.append({'arquivo':nome,'estado':estado,'diff':''.join(difflib.unified_diff((atual or '').splitlines(True),novo.splitlines(True),fromfile='Neste PC',tofile='Perfil importado'))[:6000] if estado!='igual' else ''})
    token=_hash(_json({'revisao':pacote['revisao'],'local':local}))
    avisos=[]
    if pacote.get('aplicativo',{}).get('assinatura')!=_aplicativo(app)['assinatura']: avisos.append('A instalação é diferente da origem. Ferramentas integradas podem exigir atualização no notebook.')
    if 'rotinas.json' in pacote['itens']: avisos.append('Rotinas podem conter comandos e caminhos do PC de origem. Confira-os no diff; a importação não executa esses comandos.')
    if any(n.startswith('preferencias/') for n in pacote['itens']): avisos.append('Preferências podem citar caminhos antigos como referência; o perfil não move os arquivos nem recria as pastas dos clientes.')
    return {'perfil':pacote['perfil'],'revisao':pacote['revisao'],'conferencia':token,'arquivos':linhas,'avisos':avisos,'nao_incluidos':EXCLUIDOS,
            'resumo':{e:sum(x['estado']==e for x in linhas) for e in ('novo','igual','conflito')}}


def exportar(dados=DADOS, app=APP):
    pacote=montar(dados,app); destino=Path(dados)/'perfil/exportacoes'/('perfil-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.json')
    _gravar(destino,json.dumps(pacote,ensure_ascii=False,indent=2))
    return {'caminho':str(destino),'arquivos':len(pacote['itens']),'revisao':pacote['revisao'],'bytes':destino.stat().st_size,'nao_incluidos':EXCLUIDOS}


def aplicar(texto, conferencia, politica='manter', dados=DADOS, app=APP):
    if politica not in ('manter','substituir'): raise ValueError('Política de conflitos inválida.')
    revisao=previa(texto,dados,app)
    if not conferencia or revisao['conferencia']!=conferencia: raise ValueError('Os dados locais mudaram. Faça uma nova conferência antes de restaurar.')
    pacote=validar(texto); alterar=[x['arquivo'] for x in revisao['arquivos'] if x['estado']=='novo' or (x['estado']=='conflito' and politica=='substituir')]
    caminhos={n:_destino(n,dados) for n in alterar}
    identidade_local=_destino('perfil/identidade.json',dados)
    originais={str(p):p.read_text(encoding='utf-8') if p.exists() else None for p in list(caminhos.values())+[identidade_local]}
    backup=Path(dados)/'perfil/restauracoes'/('antes-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.json')
    _gravar(backup,json.dumps({'originais':originais,'perfil_importado':pacote['perfil'],'criado_em':time.time()},ensure_ascii=False,indent=2))
    gravados=[]
    try:
        for nome,p in caminhos.items():
            conteudo=pacote['itens'][nome]['texto']
            if nome=='estado_portatil.json':
                estado=_ler(p,{})
                estado.update(json.loads(conteudo)); conteudo=json.dumps(estado,ensure_ascii=False,indent=2)
            _gravar(p,conteudo); gravados.append(p)
        _gravar(identidade_local,_json(pacote['perfil'])); gravados.append(identidade_local)
    except Exception:
        for p in reversed(gravados):
            anterior=originais[str(p)]
            if anterior is None:
                if p.exists(): p.unlink()
            else: _gravar(p,anterior)
        raise
    return {'restaurados':len(alterar),'conflitos_mantidos':sum(x['estado']=='conflito' for x in revisao['arquivos']) if politica=='manter' else 0,
            'backup':str(backup),'reinicio_necessario':True,'avisos':revisao['avisos']}


def resumo(dados=DADOS, app=APP):
    itens=coletar(dados,app)
    return {'etapa':'Perfil portátil local; login e sincronização ainda não implementados.','arquivos':len(itens),
            'nomes':list(itens),'revisao':_hash(_json(itens)),'nao_incluidos':EXCLUIDOS}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('acao',choices=['resumo','exportar','conferir'])
    p.add_argument('arquivo',nargs='?');a=p.parse_args()
    if a.acao=='exportar':r=exportar()
    elif a.acao=='conferir':r=previa(Path(a.arquivo).read_text(encoding='utf-8-sig'))
    else:r=resumo()
    print(json.dumps(r,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
