"""Plano e diário do Colab entre duas abas. Estado puro; a ponte grava sob _ESTADO_TRAVA."""
from copy import deepcopy
import ntpath
import time


def criar(de, para, objetivo):
    if not str(objetivo).strip():
        raise ValueError('descreva o objetivo do Colab')
    return {'membros': [str(de), str(para)], 'coordenador': str(de), 'objetivo': str(objetivo).strip(),
            'fase': 'planejamento', 'revisao': 0, 'aprovacoes': [], 'contrato': '', 'tarefas': [], 'diario': []}


def caminho(valor):
    valor = str(valor).strip().replace('/', '\\')
    if not valor or ntpath.isabs(valor) or ntpath.splitdrive(valor)[0] or '*' in valor or '?' in valor:
        raise ValueError('use caminhos relativos e explícitos para os arquivos')
    valor = ntpath.normpath(valor).casefold()
    if valor == '..' or valor.startswith('..\\') or valor == '.':
        raise ValueError('arquivo fora da pasta do projeto')
    return valor


def registrar(s, de, texto):
    s['diario'].append({'aba': de, 'texto': str(texto), 'quando': time.time()})


def atualizar(estado, de, dados):
    s = deepcopy(estado)
    de = str(de)
    if de not in s['membros']:
        raise ValueError('esta aba não participa do Colab')
    acao = dados.get('acao', 'consultar')
    if acao == 'consultar':
        return s
    if acao == 'propor':
        if s['fase'] != 'planejamento':
            raise ValueError('o plano só muda no planejamento; combine uma nova sessão para mudar o escopo')
        contrato = str(dados.get('contrato', '')).strip()
        tarefas, usados = [], []
        if not contrato or not isinstance(dados.get('tarefas'), list):
            raise ValueError('informe contrato das interfaces e tarefas por aba')
        for t in dados['tarefas']:
            aba, titulo = str(t.get('aba', '')), str(t.get('titulo', '')).strip()
            arquivos = t.get('arquivos')
            if aba not in s['membros'] or not titulo or not isinstance(arquivos, list) or not arquivos:
                raise ValueError('cada tarefa precisa de aba participante, título e arquivos')
            for arq in arquivos:
                c = caminho(arq)
                for outro, dono in usados:
                    if dono != aba and (c == outro or c.startswith(outro + '\\') or outro.startswith(c + '\\')):
                        raise ValueError('arquivo ou pasta reservado para duas abas: ' + str(arq))
                usados.append((c, aba))
            tarefas.append({'aba': aba, 'titulo': titulo, 'arquivos': [str(a).strip() for a in arquivos],
                            'concluida': False, 'evidencia': ''})
        if {t['aba'] for t in tarefas} != set(s['membros']):
            raise ValueError('divida tarefas entre os dois participantes')
        s.update(contrato=contrato, tarefas=tarefas, revisao=s['revisao'] + 1, aprovacoes=[])
        registrar(s, de, 'Plano proposto; os dois precisam aprovar a revisão ' + str(s['revisao']))
    elif acao in ('aprovar', 'executar'):
        if not s['tarefas'] or dados.get('revisao') != s['revisao']:
            raise ValueError('consulte e informe a revisão atual do plano')
        if s['fase'] != 'planejamento':
            raise ValueError('o plano já saiu do planejamento')
        if acao == 'aprovar':
            if de not in s['aprovacoes']:
                s['aprovacoes'].append(de)
                registrar(s, de, 'Aprovou a revisão ' + str(s['revisao']))
        else:
            if de != s['coordenador'] or set(s['aprovacoes']) != set(s['membros']):
                raise ValueError('o coordenador executa depois da aprovação dos dois')
            s['fase'] = 'execucao'
            registrar(s, de, 'Execução iniciada com arquivos divididos')
    elif acao == 'avisar':
        texto = str(dados.get('texto', '')).strip()
        if not texto:
            raise ValueError('faltou o aviso')
        registrar(s, de, texto)
    elif acao == 'concluir_tarefa':
        if s['fase'] != 'execucao':
            raise ValueError('as tarefas só são concluídas durante a execução')
        evidencia = str(dados.get('evidencia', '')).strip()
        if not evidencia:
            raise ValueError('informe o que foi entregue e como foi verificado')
        for t in s['tarefas']:
            if t['aba'] == de:
                t.update(concluida=True, evidencia=evidencia)
        registrar(s, de, evidencia)
        if all(t['concluida'] for t in s['tarefas']):
            s['fase'] = 'integracao'
            registrar(s, de, 'As duas partes foram entregues; falta integrar e verificar o conjunto')
    elif acao == 'finalizar':
        if de != s['coordenador'] or s['fase'] != 'integracao' or not str(dados.get('evidencia', '')).strip():
            raise ValueError('o coordenador finaliza na integração, com evidência do teste conjunto')
        s['fase'] = 'concluido'
        registrar(s, de, dados['evidencia'])
    else:
        raise ValueError('ação Colab desconhecida')
    return s


def contexto(aba, fio, estado):
    import json
    from pathlib import Path
    outro = next(x for x in estado['membros'] if x != str(aba))
    cli = str(Path(__file__).with_name('chat_colab.py'))
    return ('\nCOLAB: esta é a aba ' + str(aba) + ', parceira ' + outro + '. Estado compartilhado:\n' +
            json.dumps(estado, ensure_ascii=False) + '\nCanal local para QUALQUER modelo (inclusive Codex): '
            'py -3.13 "' + cli + '" --de ' + str(aba) + ' --para ' + outro +
            ' --acao colab consulta. Para modificar use --arquivo CAMINHO_JSON_UTF8 (arquivo de ação no D), evitando escapar JSON no shell. A ferramenta MCP chat aceita os mesmos campos. '
            'Em acao=colab, texto é JSON com acao=consultar|propor|aprovar|executar|avisar|concluir_tarefa|finalizar. '
            'propor: contrato (interfaces/API) e tarefas [{aba,titulo,arquivos:[caminhos relativos]}]. '
            'aprovar/executar: revisao numérica. avisar: texto. concluir_tarefa/finalizar: evidencia. '
            'Só o coordenador inicia executar e finaliza. Antes de escrever, proponham e aprovem a MESMA revisão. '
            'No planejamento, o coordenador usa chat acao=enviar para pedir ao parceiro que leia, negocie e aprove o plano, '
            'sem editar. Depois aprova e chama executar: o parceiro começa em paralelo e o coordenador faz sua parte. '
            'Consulte o estado antes de editar e em cada etapa; só altere seus arquivos. '
            'A reserva é um acordo entre agentes, não um bloqueio do sistema de arquivos. '
            'Use avisar para decisões, impedimentos e mudanças necessárias. Não altere unilateralmente interfaces. '
            'Durante execução, NÃO use enviar esperando o parceiro: consulte o diário ou publique avisos sem bloquear. '
            'Ao terminar chame concluir_tarefa com evidência. O coordenador verifica o conjunto na fase integracao '
            'e só então usa finalizar. Se o parceiro ainda trabalha, encerre informando a pendência; o Board permite continuar a integração. '
            'Não faça commit, push, publicação, exclusões ou mude dependências. O objetivo do usuário delimita a autorização.\n')
