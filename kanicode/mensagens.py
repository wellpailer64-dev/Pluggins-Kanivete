"""Fila de mensagens por aba; urgência explícita e entrega única no processo atual.

Com `arquivo`, as pendentes vão para o disco (2026-10-24) e voltam ao reabrir o KaniCode — pausadas: nada é
entregue sozinho depois de um reinício (um novo envio ou o duplo clique retoma). A que estava sendo entregue
na hora volta como falha, porque pode ter chegado ao agente. Anexos de imagem não são guardados.
"""
import json
import os
import threading


class Fila:
    def __init__(self, arquivo=None, restaurar=False):
        self.trava = threading.RLock()
        self.itens = []
        self.entregues = set()
        self.enviando = None
        self.interrompendo = None
        self.interromper_apos_envio = False
        self.pausada = False
        self.arquivo = arquivo
        if arquivo and restaurar:
            self._restaurar()
        elif arquivo:
            self.esquecer()   # aba nova com o número de uma fechada: não herda a fila dela

    def _restaurar(self):
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                itens = json.load(f)
        except (OSError, ValueError):
            return
        for i in itens if isinstance(itens, list) else []:
            if not isinstance(i, dict) or not i.get("id") or not i.get("texto"):
                continue
            if i.get("estado") == "enviando":
                i["estado"], i["erro"] = "falha", "O KaniCode reiniciou durante a entrega; confira se o agente recebeu antes de reenviar."
            elif i.get("estado") != "falha":
                i["estado"] = "pendente"
            self.itens.append(dict(i, imagens=[]))
        self.pausada = bool(self.itens)

    def _salvar(self):
        if not self.arquivo:
            return
        try:
            if not self.itens:
                self.esquecer()
                return
            os.makedirs(os.path.dirname(self.arquivo), exist_ok=True)
            guardar = [{k: v for k, v in i.items() if k != "imagens"} for i in self.itens]
            with open(self.arquivo + ".parte", "w", encoding="utf-8") as f:
                json.dump(guardar, f, ensure_ascii=False)
            os.replace(self.arquivo + ".parte", self.arquivo)
        except OSError:
            pass   # a fila continua na memória

    def esquecer(self):
        if self.arquivo:
            try:
                os.remove(self.arquivo)
            except OSError:
                pass

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
            self._salvar()
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
                self._salvar()
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
            self._salvar()
            return item, not repetir

    def editar(self, id_, texto):
        """Muda só o texto, antes da entrega; preserva prioridade, anexos e pausa."""
        with self.trava:
            item = next((i for i in self.itens if i['id'] == id_), None)
            if not item or item['estado'] not in ('pendente', 'urgente', 'falha'):
                return None
            if not isinstance(texto, str) or (not texto.strip() and not item.get('imagens')):
                raise ValueError('Escreva a mensagem antes de salvar.')
            item['texto'] = texto.strip()
            self._salvar()
            return item

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
            self._salvar()
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
            self._salvar()

    def visivel(self, item):
        return {k: item.get(k) for k in ('id', 'texto', 'quem', 'estado', 'erro')} | {
            'minis': [i.get('mini') for i in item.get('imagens', []) if i.get('mini')]}

    def listar(self):
        with self.trava:
            return [self.visivel(i) for i in self.itens]
