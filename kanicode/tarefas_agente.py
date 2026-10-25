"""Pendências de trabalho dos agentes, com cópia e vínculo ao pedido; separadas das tarefas pessoais."""
import argparse
import datetime as dt
import hashlib
import json
import os
import uuid
from tarefas import Tarefas, DADOS


class TarefasAgente(Tarefas):
    def __init__(self, dados=DADOS):
        super().__init__(dados, 'tarefas_agente.json')

    def registrar(self, aba, mensagem_id, texto, agente, pasta):
        if not mensagem_id or not isinstance(texto, str):
            raise ValueError('Pedido sem mensagem de origem.')
        id = hashlib.sha256(f'{aba}:{mensagem_id}'.encode()).hexdigest()[:24]
        with self._lock():
            itens = self._ler()
            anterior = next((i for i in itens if i['id'] == id), None)
            if anterior: return anterior
            item = {'id':id, 'titulo':(texto.strip().splitlines() or ['Pedido com anexo'])[0][:300],
                    'texto':texto, 'aba':str(aba), 'mensagem_id':mensagem_id, 'agente':agente,
                    'pasta':pasta, 'estado':'pendente', 'concluida':False, 'criado':dt.datetime.now().isoformat(),
                    'origem':'fila', 'parent':'', 'motivo':'', 'resultado':''}
            itens.append(item); self._salvar(itens)
            return item

    def obter(self, id):
        with self._lock():
            item = next((i for i in self._ler() if i['id'] == id), None)
            if not item: raise ValueError('Tarefa do agente não encontrada.')
            return item

    def estado(self, id, estado, motivo='', automatico=False):
        if estado not in ('pendente','em_andamento','a_conferir','adiada','falha','concluida','cancelada'):
            raise ValueError('Estado de tarefa inválido.')
        with self._lock():
            itens = self._ler()
            i = next((i for i in itens if i['id'] == id), None)
            if not i: raise ValueError('Tarefa do agente não encontrada.')
            # O fim do turno não conclui o que foi explicitamente adiado nem as subtarefas anotadas.
            if automatico and (i['estado'] in ('adiada','concluida','cancelada') or i.get('parent')):
                return i
            if i['estado']==estado and (not motivo or i.get('motivo')==motivo):
                return i
            i.update(estado=estado, concluida=estado=='concluida', atualizado=dt.datetime.now().isoformat())
            if motivo: i['motivo'] = str(motivo)[:2000]
            elif estado in ('pendente','em_andamento'): i['motivo']=''
            if estado=='concluida': i['resultado'] = str(motivo)[:4000]
            self._salvar(itens)
            return i

    def anotar(self, ref, titulo):
        if not isinstance(titulo,str) or not 1 <= len(titulo.strip()) <= 300:
            raise ValueError('Escreva uma tarefa de até 300 caracteres.')
        with self._lock():
            itens = self._ler()
            origem = next((i for i in itens if i['id'] == ref), None)
            if not origem: raise ValueError('Indique a tarefa que contém o pedido original.')
            raiz = origem.get('parent') or origem['id']
            existente=next((i for i in itens if i.get('parent')==raiz and i['titulo']==titulo.strip() and not i['concluida']),None)
            if existente: return existente
            item=dict(origem, id=uuid.uuid4().hex, titulo=titulo.strip(), parent=raiz, origem='combinado',
                      estado='adiada', concluida=False, motivo='', resultado='', criado=dt.datetime.now().isoformat())
            itens.append(item); self._salvar(itens)
            return item

    def resumo(self):
        return [{k:v for k,v in i.items() if k not in ('texto','resultado')} for i in self.listar()]

    def recuperar(self):
        with self._lock():
            itens=self._ler()
            mudou=False
            for i in itens:
                if i['estado']=='em_andamento':
                    i.update(estado='falha',motivo='O KaniCode reiniciou durante a tarefa. Confira o pedido antes de retomar.')
                    mudou=True
            if mudou: self._salvar(itens)


def contexto(pasta, pedido=''):
    """Só o identificador do pedido atual e até três pendências da mesma pasta, sem copiar conversas."""
    itens = TarefasAgente().listar()
    iguais = [i for i in itens if os.path.normcase(os.path.realpath(i.get('pasta','')))==os.path.normcase(os.path.realpath(pasta))]
    atual = [i for i in iguais if i['estado']=='em_andamento' and not i.get('parent') and
             (pedido.strip()==i['texto'].strip() or (i['texto'].strip() and pedido.strip().endswith('\n'+i['texto'].strip())))]
    linhas=[]
    if len(atual)==1:
        ref=atual[0]['id']
        linhas.append(f'TO-DO DO AGENTE: pedido atual {ref}. Antes de encerrar, use concluir com resultado conferido se cumpriu; '
                      'se faltar trabalho, use adiar. Encerrar o motor não comprova conclusão. Para algo combinado para depois, '
                      'use anotar com esta ref; a pendência fica ligada à mensagem original.')
        linhas.append('Ferramenta tarefa_agente (Claude/Kani/Pickle), ou Python local: py -3.13 "'+__file__+'" '
                      'adiar --ref '+ref+' --motivo "o que falta"; anotar --ref '+ref+' --titulo "pendência"; concluir --ref ID --motivo "resultado conferido".')
    pendentes=[i for i in iguais if i['estado'] in ('adiada','falha','a_conferir')][:3]
    if pendentes:
        linhas.append('Pendências registradas (consulte o pedido original antes de retomar): '+
                      '; '.join(i['id']+': '+i['titulo'][:100] for i in pendentes))
    return '\n'.join(linhas)


def acao(args):
    tarefas=TarefasAgente()
    a=args.get('acao','listar')
    if a=='listar': return tarefas.resumo()
    if a=='ler': return tarefas.obter(args.get('ref'))
    if a=='anotar': return tarefas.anotar(args.get('ref'),args.get('titulo'))
    if a in ('adiar','concluir','reabrir'):
        if a in ('adiar','concluir') and not str(args.get('motivo') or '').strip():
            raise ValueError('Informe o que falta ou o resultado conferido.')
        return tarefas.estado(args.get('ref'),{'adiar':'adiada','concluir':'concluida','reabrir':'pendente'}[a],args.get('motivo',''))
    raise ValueError('Ação de tarefa inválida.')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('acao',choices=['listar','ler','anotar','adiar','concluir','reabrir'])
    p.add_argument('--ref'); p.add_argument('--titulo'); p.add_argument('--motivo')
    print(json.dumps(acao(vars(p.parse_args())),ensure_ascii=False))
