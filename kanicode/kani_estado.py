"""Checkpoints transacionais da Kani; evidências e autorizações não dependem do prompt."""
import contextlib
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid

from dados_app import pasta_dados


def limpar(valor):
    if isinstance(valor, dict):
        return {k: ('[protegido]' if re.search(r'(?:access|refresh|id)_token|api[_-]?key|senha|password|secret|authorization|cookie|credencial', k, re.I) else limpar(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [limpar(v) for v in valor]
    if isinstance(valor, str):
        valor = re.sub(r'(?i)(bearer\s+)[^\s,;"}]+', r'\1[protegido]', valor)
        padrao = r'''(?i)(["']?(?:access_token|refresh_token|client_secret|password|senha|api[_-]?key)["']?\s*[:=]\s*["']?)[^\s,;"'}]+'''
        return re.sub(padrao, r'\1[protegido]', valor)
    return valor


class Estado:
    def __init__(self, base=None):
        self.base = Path(base or pasta_dados()) / 'kani_execucoes'
        self.base.mkdir(parents=True, exist_ok=True)
        self.arquivo = self.base / 'estado.sqlite3'
        with self.conectar() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS tarefas (id TEXT PRIMARY KEY, estado TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evidencias (id TEXT PRIMARY KEY, tarefa TEXT, etapa TEXT, dados TEXT);
                CREATE TABLE IF NOT EXISTS eventos (n INTEGER PRIMARY KEY, tarefa TEXT, etapa TEXT, quando REAL, dados TEXT);
            ''')

    @contextlib.contextmanager
    def conectar(self):
        c = sqlite3.connect(self.arquivo, timeout=10)
        try:
            c.execute('PRAGMA journal_mode=WAL')
            with c:
                yield c
        finally:
            c.close()

    def salvar(self, tarefa):
        tarefa['atualizado'] = time.time()
        with self.conectar() as c:
            c.execute('INSERT OR REPLACE INTO tarefas VALUES (?, ?)', (tarefa['id'], json.dumps(limpar(tarefa), ensure_ascii=False)))

    def obter(self, id):
        if not re.fullmatch(r'[a-f0-9]{32}', str(id)):
            raise ValueError('Identificador de execução inválido.')
        with self.conectar() as c:
            r = c.execute('SELECT estado FROM tarefas WHERE id=?', (id,)).fetchone()
        if not r:
            raise ValueError('Execução não encontrada.')
        return json.loads(r[0])

    def listar(self, pasta):
        with self.conectar() as c:
            rs = c.execute('SELECT estado FROM tarefas ORDER BY rowid DESC LIMIT 100').fetchall()
        return [t for r in rs if (t := json.loads(r[0]))['pasta'] == str(Path(pasta).resolve())]

    def evidencia(self, tarefa, etapa, dados):
        id = uuid.uuid4().hex
        with self.conectar() as c:
            c.execute('INSERT INTO evidencias VALUES (?, ?, ?, ?)',
                      (id, tarefa, etapa, json.dumps(limpar(dados), ensure_ascii=False)))
        return id

    def ler_evidencia(self, tarefa, id):
        with self.conectar() as c:
            r = c.execute('SELECT dados FROM evidencias WHERE id=? AND tarefa=?', (id, tarefa)).fetchone()
        if not r:
            raise ValueError('Evidência ausente ou de outra tarefa.')
        return json.loads(r[0])

    def confirmacao(self,tarefa,chave):
        with self.conectar() as c:
            linhas=c.execute('SELECT id,dados FROM evidencias WHERE tarefa=? ORDER BY rowid DESC LIMIT 100',(tarefa,)).fetchall()
        for id,conteudo in linhas:
            dados=json.loads(conteudo)
            if dados.get('ok') is True and dados.get('assinatura')==chave:
                return id
        return None

    def registrar(self, tarefa, etapa, **dados):
        with self.conectar() as c:
            c.execute('INSERT INTO eventos (tarefa, etapa, quando, dados) VALUES (?, ?, ?, ?)',
                      (tarefa, etapa, time.time(), json.dumps(limpar(dados), ensure_ascii=False)))

    def eventos(self, tarefa):
        with self.conectar() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT dados FROM eventos WHERE tarefa=? ORDER BY n', (tarefa,))]

    @contextlib.contextmanager
    def exclusiva(self, id):
        # Arquivo de bloqueio do SO: liberado automaticamente se o processo morrer.
        import msvcrt
        arq = self.base / (id + '.lock')
        with arq.open('a+b') as f:
            f.seek(0); f.write(b'0'); f.flush(); f.seek(0)
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                raise RuntimeError('Execução já está em andamento.') from e
            try:
                yield
            finally:
                f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def assinatura(acao, args):
    return hashlib.sha256(json.dumps([acao, args], sort_keys=True, ensure_ascii=False).encode()).hexdigest()

