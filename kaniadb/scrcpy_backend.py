"""Reutiliza o scrcpy 4.x existente: vídeo e entrada por sockets persistentes."""
from collections import deque
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import threading
import time

_SEM_JANELA = 0x08000000 if os.name == 'nt' else 0


def localizar():
    indicado = os.environ.get('KANIADB_SCRCPY')
    candidatos = [Path(indicado)] if indicado else [Path.home() / 'Downloads' / 'scrcpy-win64-v4.1']
    for pasta in candidatos:
        if pasta.is_file():
            pasta = pasta.parent
        if (pasta / 'scrcpy.exe').is_file() and (pasta / 'scrcpy-server').is_file():
            return pasta
    return None


def receber(canal, tamanho):
    dados = bytearray()
    while len(dados) < tamanho:
        parte = canal.recv(tamanho - len(dados))
        if not parte:
            raise OSError('O canal do scrcpy encerrou.')
        dados.extend(parte)
    return bytes(dados)


def pacote_toque(acao, x, y, largura, altura):
    return struct.pack('>BBQIIHHHII', 2, acao, 0, x, y, largura, altura,
                       0 if acao in (1, 3) else 65535, 0, 0)


class Scrcpy:
    def __init__(self, adb, serial, pasta, largura, altura):
        self.adb, self.serial, self.pasta = adb, serial, Path(pasta)
        self.largura, self.altura = largura, altura
        self.id = secrets.token_hex(3)
        self.remoto = '/data/local/tmp/kaniadb-' + self.id + '.jar'
        self.porta, self.proc, self.video, self.controle = None, None, None, None
        self.trava = threading.Lock()
        self.logs = deque(maxlen=12)
        self.encerrado = False

    def _adb(self, *args):
        r = subprocess.run([self.adb, '-s', self.serial, *args], capture_output=True,
                           timeout=12, creationflags=_SEM_JANELA)
        if r.returncode:
            raise RuntimeError(r.stderr.decode('utf-8', 'replace')[-500:] or 'Falha no adb do scrcpy.')
        return r.stdout

    def _drenar(self, canal):
        try:
            for linha in canal:
                self.logs.append(linha.decode('utf-8', 'replace')[-600:].strip())
        except (OSError, ValueError):
            pass

    def iniciar(self):
        r = subprocess.run([str(self.pasta / 'scrcpy.exe'), '--version'], capture_output=True,
                           timeout=5, creationflags=_SEM_JANELA)
        versao = re.search(rb'^scrcpy (4\.\d+)', r.stdout)
        if not versao:
            raise RuntimeError('Esta integração requer um scrcpy 4.x existente.')
        try:
            self._adb('push', str(self.pasta / 'scrcpy-server'), self.remoto)
            self.porta = int(self._adb('forward', 'tcp:0', 'localabstract:scrcpy_' + self.id.zfill(8)).strip())
            opcoes = ['scid=' + self.id, 'tunnel_forward=true', 'audio=false', 'control=true',
                      'send_device_meta=false', 'send_stream_meta=true', 'send_frame_meta=true',
                      'clipboard_autosync=false', 'cleanup=false', 'power_on=true',
                      'max_size=' + str(max(self.largura, self.altura)), 'max_fps=60', 'video_bit_rate=4000000']
            self.proc = subprocess.Popen([self.adb, '-s', self.serial, 'shell', 'CLASSPATH=' + self.remoto,
                    'app_process', '/', 'com.genymobile.scrcpy.Server', versao[1].decode(), *opcoes],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_SEM_JANELA)
            for canal in (self.proc.stdout, self.proc.stderr):
                threading.Thread(target=self._drenar, args=(canal,), daemon=True).start()
            limite = time.monotonic() + 8
            while time.monotonic() < limite:
                canal = None
                try:
                    canal = socket.create_connection(('127.0.0.1', self.porta), timeout=0.3)
                    canal.settimeout(1)
                    if receber(canal, 1) == b'\x00':
                        self.video = canal
                        break
                except OSError:
                    pass
                if canal:
                    canal.close()
                if self.proc.poll() is not None:
                    raise RuntimeError('scrcpy encerrou: ' + ' '.join(self.logs)[-500:])
                time.sleep(0.05)
            if not self.video:
                raise RuntimeError('O scrcpy não abriu o vídeo no prazo esperado.')
            self.controle = socket.create_connection(('127.0.0.1', self.porta), timeout=3)
            self.video.settimeout(15)
            if receber(self.video, 4) != b'h264':
                raise RuntimeError('Codec do scrcpy diferente de H264.')
            self.video.settimeout(None)   # tela estática/repouso não significa queda; fechar() interrompe o socket
            threading.Thread(target=self._ler_controle, daemon=True).start()
        except Exception:
            self.fechar()
            raise

    def _ler_controle(self):
        try:
            while self.controle and self.controle.recv(4096):
                pass   # clipboard_autosync=false; não copia nem registra dados do aparelho
        except OSError:
            pass

    def bombear(self, destino):
        try:
            while not self.encerrado:
                cabecalho = receber(self.video, 12)
                if cabecalho[0] & 0x80:
                    self.largura, self.altura = struct.unpack('>II', cabecalho[4:])
                    continue
                tamanho = struct.unpack('>I', cabecalho[8:])[0]
                if not 0 < tamanho <= 16 * 1024 * 1024:
                    raise OSError('Tamanho de pacote inválido do scrcpy.')
                destino.write(receber(self.video, tamanho))
                destino.flush()
        except (OSError, ValueError):
            pass
        finally:
            try:
                destino.close()
            except OSError:
                pass

    def comando(self, acao, origem, **dados):
        with self.trava:
            if not self.controle or self.encerrado:
                raise RuntimeError('Canal de controle do scrcpy indisponível.')
            if acao == 'tecla':
                codigos = {'HOME': 3, 'BACK': 4, 'APP_SWITCH': 187, 'POWER': 26, 'VOLUME_UP': 24,
                           'VOLUME_DOWN': 25, 'VOLUME_MUTE': 164, 'ENTER': 66, 'SPACE': 62, 'DEL': 67,
                           'MENU': 82, 'MEDIA_PLAY_PAUSE': 85, 'CAMERA': 27, 'SYSRQ': 120, 'WAKEUP': 224, 'SLEEP': 223}
                nome = str(dados['codigo']).removeprefix('KEYCODE_')
                codigo = int(nome) if nome.isdigit() else codigos.get(nome)
                if codigo is None:
                    return None
                self.controle.sendall(struct.pack('>BBIII', 0, 0, codigo, 0, 0) +
                                      struct.pack('>BBIII', 0, 1, codigo, 0, 0))
                return {'tecla': dados['codigo']}
            if acao not in ('tocar', 'deslizar', 'ponteiro'):
                return None
            def ponto(tipo, x, y):
                px = max(0, min(self.largura - 1, round(x * self.largura / origem['largura'])))
                py = max(0, min(self.altura - 1, round(y * self.altura / origem['altura'])))
                self.controle.sendall(pacote_toque(tipo, px, py, self.largura, self.altura))
            if acao == 'ponteiro':
                tipo = {'down': 0, 'up': 1, 'move': 2, 'cancel': 3}.get(dados['tipo'])
                if tipo is None:
                    raise ValueError('Ação do ponteiro inválida.')
                ponto(tipo, dados['x'], dados['y'])
            elif acao == 'tocar':
                ponto(0, dados['x'], dados['y'])
                ponto(1, dados['x'], dados['y'])
            else:
                ms = max(50, min(2000, int(dados.get('ms', 300))))
                passos = max(2, ms // 16)
                ponto(0, dados['x1'], dados['y1'])
                for i in range(1, passos + 1):
                    time.sleep(ms / passos / 1000)
                    f = i / passos
                    ponto(2, dados['x1'] + (dados['x2'] - dados['x1']) * f,
                          dados['y1'] + (dados['y2'] - dados['y1']) * f)
                ponto(1, dados['x2'], dados['y2'])
            return {'ok': True}

    def fechar(self):
        if self.encerrado:
            return
        self.encerrado = True
        for canal in (self.video, self.controle):
            if canal:
                try:
                    canal.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                canal.close()
        if self.proc:
            if self.proc.poll() is None:
                self.proc.kill()
            self.proc.wait(timeout=5)
            self.proc.stdout.close()
            self.proc.stderr.close()
        try:
            if self.porta:
                self._adb('forward', '--remove', 'tcp:' + str(self.porta))
            self._adb('shell', 'rm', '-f', self.remoto)   # somente o auxiliar temporário desta instância
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            pass
