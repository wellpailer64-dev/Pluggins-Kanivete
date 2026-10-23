"""Fila de mensagens por aba; urgência explícita e entrega única no processo atual."""
import threading


class Fila:
    def __init__(self):
        self.trava = threading.RLock()
        self.itens = []
        self.entregues = set()
        self.enviando = None
        self.interrompendo = None
        self.interromper_apos_envio = False
        self.pausada = False

    def adicionar(self, item):
        with self.trava:
            existente = next((i for i in self.itens if i['id'] == item['id']), None)
            if existente:
                return existente, False
            if item['id'] in self.entregues:
                return dict(item, estado='enviada'), False
            item = dict(item, estado='pendente')
            self.itens.append(item)
            self.pausada = False
            return item, True

    def proxima(self):
        with self.trava:
            if self.enviando or self.pausada:
                return None
            item = next((i for i in self.itens if i['estado'] in ('pendente', 'urgente')), None)
            if item:
                self.enviando = item['id']
                self.interrompendo = None
                item['estado'] = 'enviando'
            return item

    def urgente(self, id_):
        with self.trava:
            item = next((i for i in self.itens if i['id'] == id_), None)
            if not item or item['estado'] not in ('pendente', 'urgente'):
                return None, False
            repetir = self.interrompendo == id_
            self.itens.remove(item)
            self.itens.insert(0, item)
            item['estado'] = 'urgente'
            self.interrompendo = id_
            self.pausada = False
            return item, not repetir

    def cancelar(self, id_):
        """tira da fila uma mensagem que ainda não foi entregue (o ✕ da bolha)"""
        with self.trava:
            item = next((i for i in self.itens if i['id'] == id_), None)
            if not item or item['estado'] not in ('pendente', 'urgente', 'falha'):
                return None
            self.itens.remove(item)
            if self.interrompendo == id_:
                self.interrompendo = None
            if item['estado'] == 'falha' and not any(i['estado'] == 'falha' for i in self.itens):
                self.pausada = False
            item['estado'] = 'cancelada'
            return item

    def concluir(self, item, ok, erro=''):
        with self.trava:
            self.enviando = None
            item['estado'] = 'enviada' if ok else 'falha'
            if ok:
                self.entregues.add(item['id'])
                self.itens.remove(item)
            else:
                item['erro'] = erro
                self.pausada = True

    def visivel(self, item):
        return {k: item.get(k) for k in ('id', 'texto', 'quem', 'estado', 'erro')} | {
            'minis': [i.get('mini') for i in item.get('imagens', []) if i.get('mini')]}

    def listar(self):
        with self.trava:
            return [self.visivel(i) for i in self.itens]
