"""Mapa vivo do disco D: índice de nomes e caminhos, consulta rápida e atualização local.

py -3.13 mapa_d.py iniciar | status | buscar Camila --ext pdf | listar --pasta D:/
O monitor é um processo separado, iniciado pelo KaniCode; dados em D:/Kanivete/KaniCode/mapa_d.
"""
from collections import deque
from contextlib import contextmanager
from pathlib import Path
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time

from dados_app import pasta_dados
BASE = pasta_dados() / "mapa_d"
BANCO = BASE / 'indice.sqlite3'
RAIZ = 'D:/'


def chave(caminho):
    return os.path.normcase(os.path.abspath(caminho))


def dentro(caminho, raiz):
    try: return os.path.commonpath([chave(caminho), chave(raiz)]) == chave(raiz)
    except ValueError: return False


def _prefixo(caminho):
    return chave(caminho).rstrip('\\/') + os.sep


def _like(texto):
    return texto.replace('!', '!!').replace('%', '!%').replace('_', '!_')


class Indice:
    def __init__(self, raiz=RAIZ, banco=BANCO, excluir=()):
        self.raiz, self.banco = chave(raiz), Path(banco)
        self.excluir = [chave(self.banco.parent),
                        chave(os.path.join(self.raiz, '$RECYCLE.BIN')),
                        chave(os.path.join(self.raiz, 'System Volume Information'))] + [chave(p) for p in excluir]
        if not dentro(self.raiz, 'D:/kanivete_testes'):
            self.excluir.append(chave('D:/kanivete_testes'))
        self.banco.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.banco, timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS itens(id INTEGER PRIMARY KEY, caminho TEXT NOT NULL UNIQUE COLLATE NOCASE,
                pai TEXT NOT NULL COLLATE NOCASE, nome TEXT NOT NULL, extensao TEXT, pasta INTEGER, tamanho INTEGER,
                modificado_ns INTEGER, visto INTEGER);
            CREATE INDEX IF NOT EXISTS itens_pai ON itens(pai);
            CREATE INDEX IF NOT EXISTS itens_extensao ON itens(extensao);
            CREATE TABLE IF NOT EXISTS meta(chave TEXT PRIMARY KEY, valor TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS busca USING fts5(caminho, nome, content='itens', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2');
            CREATE TRIGGER IF NOT EXISTS itens_inserir AFTER INSERT ON itens BEGIN
                INSERT INTO busca(rowid,caminho,nome) VALUES(new.id,new.caminho,new.nome); END;
            CREATE TRIGGER IF NOT EXISTS itens_nome AFTER UPDATE OF nome ON itens WHEN old.nome<>new.nome BEGIN
                INSERT INTO busca(busca,rowid,caminho,nome) VALUES('delete',old.id,old.caminho,old.nome);
                INSERT INTO busca(rowid,caminho,nome) VALUES(new.id,new.caminho,new.nome); END;
            CREATE TRIGGER IF NOT EXISTS itens_apagar AFTER DELETE ON itens BEGIN
                INSERT INTO busca(busca,rowid,caminho,nome) VALUES('delete',old.id,old.caminho,old.nome); END;
        ''')
        self.db.commit()

    def fechar(self):
        self.db.close()

    def meta(self, **dados):
        self.db.executemany('INSERT OR REPLACE INTO meta VALUES(?,?)',
                            [(k, json.dumps(v, ensure_ascii=False)) for k, v in dados.items()])
        self.db.commit()

    def ignorado(self, caminho):
        return not dentro(caminho, self.raiz) or any(dentro(caminho, p) for p in self.excluir)

    def registrar(self, caminho, visto):
        p = Path(caminho)
        if self.ignorado(p) or p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
            return False
        s = p.stat()
        self.db.execute('''INSERT INTO itens(caminho,pai,nome,extensao,pasta,tamanho,modificado_ns,visto)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(caminho) DO UPDATE SET pai=excluded.pai,nome=excluded.nome,
            extensao=excluded.extensao,pasta=excluded.pasta,tamanho=excluded.tamanho,
            modificado_ns=excluded.modificado_ns,visto=excluded.visto''',
            (chave(p), chave(p.parent), p.name, p.suffix.lower().lstrip('.'), int(p.is_dir()), s.st_size, s.st_mtime_ns, visto))
        return True

    def remover(self, caminho):
        self.db.execute("DELETE FROM itens WHERE caminho=? OR caminho LIKE ? ESCAPE '!'",
                        (chave(caminho), _like(_prefixo(caminho)) + '%'))

    def percorrer(self, raiz, visto, parar=None):
        fila = deque([str(raiz)]); quantidade = 0; erros = []
        ultimo = time.monotonic()
        while fila and not (parar and parar.is_set()):
            pasta = fila.popleft()
            if self.ignorado(pasta): continue
            try:
                if not self.registrar(pasta, visto): continue
                quantidade += 1
                with os.scandir(pasta) as itens:
                    for item in itens:
                        if parar and parar.is_set(): break
                        if self.ignorado(item.path) or item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()): continue
                        try:
                            if item.is_dir(follow_symlinks=False): fila.append(item.path)
                            else:
                                self.registrar(item.path, visto); quantidade += 1
                        except OSError as e:
                            if len(erros) < 50: erros.append({'pasta': item.path, 'erro': str(e)})
                        if quantidade % 1000 == 0 or time.monotonic() - ultimo > 3:
                            self.db.commit(); ultimo = time.monotonic()
                            self.meta(heartbeat=time.time(), progresso=quantidade)
            except OSError as e:
                if len(erros) < 50: erros.append({'pasta': pasta, 'erro': str(e)})
        self.db.commit()
        return quantidade, erros, bool(parar and parar.is_set())

    def reconstruir(self, parar=None):
        inicio = time.time_ns()
        if not os.path.isdir(self.raiz):
            self.meta(estado='indisponivel', erro='Unidade ou pasta raiz indisponível.'); return
        self.meta(estado='construindo', raiz=self.raiz, heartbeat=time.time(), progresso=0)
        quantidade, erros, cancelado = self.percorrer(self.raiz, inicio, parar)
        if not erros and not cancelado:
            self.db.execute('DELETE FROM itens WHERE visto<>?', (inicio,)); self.db.commit()
        self.meta(estado='interrompido' if cancelado else 'parcial' if erros else 'pronto',
                  ultima_varredura=time.time(), erros=erros, progresso=quantidade,
                  total=self.db.execute('SELECT count(*) FROM itens').fetchone()[0], heartbeat=time.time())

    def atualizar(self, caminho, acao=0):
        if self.ignorado(caminho): return
        if not os.path.lexists(caminho): self.remover(caminho)
        else:
            try:
                if os.path.isdir(caminho) and acao != 3:
                    # Renomear pasta troca também todos os caminhos dos descendentes.
                    self.remover(caminho)
                    _, erros, _ = self.percorrer(caminho, time.time_ns())
                    if erros: self.meta(estado='parcial', erros=erros)
                else: self.registrar(caminho, time.time_ns())
            except OSError as e:
                self.meta(estado='parcial', erro=str(e))
        self.db.commit()
        self.meta(ultima_mudanca=time.time(), heartbeat=time.time())


@contextmanager
def _ler(banco):
    con = sqlite3.connect(Path(banco).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def status(banco=BANCO):
    if not Path(banco).exists(): return {'estado': 'nao_iniciado', 'banco': str(banco), 'parcial': True}
    try:
        with _ler(banco) as db:
            meta = {r['chave']: json.loads(r['valor']) for r in db.execute('SELECT * FROM meta')}
        meta.setdefault('estado', 'iniciando')
        meta['monitor_ativo'] = time.time() - meta.get('heartbeat', 0) < 20
        meta['banco'] = str(banco)
        meta['parcial'] = meta.get('estado') != 'pronto' or not meta['monitor_ativo'] or meta.get('monitor') != 'windows'
        return meta
    except sqlite3.Error as e: return {'estado': 'indisponivel', 'erro': str(e), 'parcial': True}


def buscar(consulta, raiz='', extensao='', limite=40, banco=BANCO, pastas=False):
    termos = re.findall(r'\w+', str(consulta), flags=re.UNICODE)[:12]
    if not termos: raise ValueError('Informe parte do nome do arquivo, cliente ou pasta.')
    estado = status(banco)
    if estado['estado'] in ('nao_iniciado', 'indisponivel'): return {'arquivos': [], 'mapa': estado, 'parcial': True}
    consulta_fts = ' AND '.join('"' + t + '"*' for t in termos)
    filtros = ['busca MATCH ?']; valores = [consulta_fts]
    if raiz:
        filtros.append("(i.caminho=? OR i.caminho LIKE ? ESCAPE '!')")
        valores += [chave(raiz), _like(_prefixo(raiz)) + '%']
    if extensao:
        filtros.append('i.extensao=?'); valores.append(str(extensao).lower().lstrip('.'))
    if not pastas: filtros.append('i.pasta=0')
    limite = max(1, min(200, int(limite)))
    with _ler(banco) as db:
        linhas = db.execute('SELECT i.caminho,i.nome,i.pasta,i.tamanho,i.modificado_ns FROM busca JOIN itens i ON i.id=busca.rowid WHERE '
                            + ' AND '.join(filtros) + ' ORDER BY rank LIMIT ?', valores + [limite * 3]).fetchall()
    arquivos = [dict(r) for r in linhas if os.path.exists(r['caminho'])][:limite]
    return {'arquivos': arquivos, 'parcial': estado.get('parcial', True) or len(arquivos) >= limite,
            'mapa': estado, 'aviso': 'Pesquisa por nomes e caminhos, sem ler o conteúdo. Caminhos conferidos no disco ao consultar.'}


def listar(pasta=RAIZ, limite=100, banco=BANCO):
    estado = status(banco)
    if not Path(banco).exists(): return {'itens': [], 'mapa': estado}
    with _ler(banco) as db:
        itens = [dict(r) for r in db.execute('SELECT caminho,nome,pasta,tamanho FROM itens WHERE pai=? AND caminho<>? ORDER BY pasta DESC,nome LIMIT ?',
                                            (chave(pasta), chave(pasta), max(1,min(500,int(limite))))) if os.path.exists(r['caminho'])]
    return {'itens': itens, 'mapa': estado, 'parcial': estado.get('parcial') or len(itens) >= limite}


def iniciar(raiz=RAIZ, banco=BANCO):
    estado = status(banco)
    if estado.get('monitor_ativo'): return estado
    Path(banco).parent.mkdir(parents=True, exist_ok=True)
    exe = Path(sys.executable).with_name('pythonw.exe')
    if not exe.exists(): exe = Path(sys.executable)
    env = dict(os.environ, PYTHONPYCACHEPREFIX='D:/kanivete_testes/pycache', TEMP='D:/kanivete_testes/tmp', TMP='D:/kanivete_testes/tmp')
    with open(Path(banco).with_suffix('.log'), 'a', encoding='utf-8') as log:
        subprocess.Popen([str(exe), str(Path(__file__).resolve()), 'servico', '--raiz', str(raiz), '--banco', str(banco)],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env,
                         creationflags=0x08000000 if os.name=='nt' else 0)
    return dict(estado, inicio_solicitado=True)


def instalar_inicio():
    """Inicia o monitor no logon deste usuário; não precisa de privilégios de administrador."""
    if os.name != 'nt': raise OSError('Inicialização automática disponível apenas no Windows.')
    import winreg
    exe = Path(sys.executable).with_name('pythonw.exe')
    if not exe.exists(): exe = Path(sys.executable)
    comando = subprocess.list2cmdline([str(exe), '-X', 'pycache_prefix=D:/kanivete_testes/pycache', str(Path(__file__).resolve()), 'servico'])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as reg:
        winreg.SetValueEx(reg, 'KaniCodeMapaDiscoD', 0, winreg.REG_SZ, comando)
    return {'inicio_automatico': True, 'quando': 'logon deste usuário no Windows', 'comando': comando}


def servico(raiz=RAIZ, banco=BANCO, parar=None):
    os.environ['TEMP'] = os.environ['TMP'] = 'D:/kanivete_testes/tmp'
    Path(os.environ['TEMP']).mkdir(parents=True, exist_ok=True)
    import mapa_d_monitor
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL('kernel32')
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)   # abaixo do normal: prioriza o trabalho do Pailer
    Path(banco).parent.mkdir(parents=True, exist_ok=True)
    trava = open(Path(banco).with_suffix('.lock'), 'a+b')
    if os.name == 'nt':
        import msvcrt
        try:
            trava.seek(0); msvcrt.locking(trava.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            trava.close(); return
    parar = parar or threading.Event()
    indice = Indice(raiz, banco)
    sujos = {}; mutex = threading.Lock(); refazer = threading.Event(); pronto = threading.Event()
    falhas = []
    def receber(caminho):
        with mutex:
            if caminho is None or len(sujos) >= 10000:
                refazer.set(); sujos.clear()
            elif not indice.ignorado(caminho[0]): sujos[chave(caminho[0])] = caminho[1]
    def erro(texto):
        falhas.append(texto); refazer.set()
    monitor = threading.Thread(target=mapa_d_monitor.monitorar, args=(str(raiz), receber, parar, pronto, erro), daemon=True)
    monitor.start(); pronto.wait(10)
    try:
        indice.meta(pid=os.getpid(), monitor='windows' if not falhas and pronto.is_set() else 'periodico')
        indice.reconstruir(parar)
        ultima = time.monotonic(); ultimo_pulso = 0
        while not parar.wait(.5):
            with mutex:
                pendentes = list(sujos.items()); sujos.clear()
            for caminho, acao in pendentes:
                if parar.is_set(): break
                indice.atualizar(caminho, acao)
            if falhas:
                indice.meta(monitor='periodico', erro_monitor=falhas[-1])
            periodo = 300 if falhas else 21600
            if refazer.is_set() or time.monotonic() - ultima > periodo:
                refazer.clear(); indice.reconstruir(parar); ultima = time.monotonic()
            if time.time() - ultimo_pulso >= 5:
                indice.meta(heartbeat=time.time(), pendentes=len(sujos), total=indice.db.execute('SELECT count(*) FROM itens').fetchone()[0])
                ultimo_pulso = time.time()
    finally:
        parar.set(); monitor.join(4)
        indice.meta(estado='parado', heartbeat=0)
        indice.fechar(); trava.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('acao', choices=['iniciar','servico','status','buscar','listar','construir','instalar'])
    p.add_argument('consulta', nargs='?', default='')
    p.add_argument('--raiz', default=RAIZ); p.add_argument('--banco', default=str(BANCO))
    p.add_argument('--ext', default=''); p.add_argument('--limite', type=int, default=40)
    p.add_argument('--pasta', default=RAIZ); p.add_argument('--pastas', action='store_true')
    a = p.parse_args()
    if a.acao=='servico': return servico(a.raiz,a.banco)
    if a.acao=='construir':
        i=Indice(a.raiz,a.banco)
        try: i.reconstruir()
        finally: i.fechar()
        r=status(a.banco)
    elif a.acao=='instalar': r=instalar_inicio()
    elif a.acao=='iniciar': r=iniciar(a.raiz,a.banco)
    elif a.acao=='status': r=status(a.banco)
    elif a.acao=='listar': r=listar(a.pasta,a.limite,a.banco)
    else: r=buscar(a.consulta,a.raiz if a.raiz!=RAIZ else '',a.ext,a.limite,a.banco,a.pastas)
    print(json.dumps(r,ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
