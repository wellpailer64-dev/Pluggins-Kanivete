"""H264 do Android por um único pipe; guarda somente o JPEG mais recente."""
from collections import deque
import os
import shutil
import subprocess
import threading
import time
from scrcpy_backend import Scrcpy, localizar as localizar_scrcpy

_SEM_JANELA = 0x08000000 if os.name == 'nt' else 0


class _SeparadorJPEG:
    def __init__(self):
        self.dados = bytearray()

    def receber(self, dados):
        self.dados.extend(dados)
        ultimo, quantidade = None, 0
        while True:
            inicio = self.dados.find(b'\xff\xd8')
            if inicio < 0:
                self.dados[:] = self.dados[-1:]
                break
            if inicio:
                del self.dados[:inicio]
            fim = self.dados.find(b'\xff\xd9', 2)
            if fim < 0:
                if len(self.dados) > 8 * 1024 * 1024:
                    raise RuntimeError('Quadro JPEG excedeu o limite de memória.')
                break
            ultimo = bytes(self.dados[:fim + 2])
            del self.dados[:fim + 2]
            quantidade += 1
        return ultimo, quantidade


class VideoContinuo:
    def __init__(self, adb, serial, largura=720, altura=1600, ffmpeg=None):
        self.adb, self.serial = str(adb), str(serial)
        self.largura, self.altura = int(largura), int(altura)
        self.ffmpeg = ffmpeg or shutil.which('ffmpeg')
        self.condicao = threading.Condition()
        self.processos = []
        self.registros = deque(maxlen=12)
        self.jpeg, self.carimbo, self.quadros = None, 0, 0
        self.erro, self.encerrado, self.geracao = '', False, 0
        self.backend = None

    def _limpar(self):
        processos, self.processos = self.processos, []
        for proc in reversed(processos):
            if proc.poll() is None:
                proc.kill()   # somente os dois processos criados por esta instância
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        if self.backend:
            self.backend.fechar()
            self.backend = None
        for proc in processos:
            for canal in (proc.stdin, proc.stdout, proc.stderr):
                if canal and not canal.closed:
                    canal.close()

    def _stderr(self, canal):
        try:
            for linha in canal:
                self.registros.append(linha.decode('utf-8', 'replace')[-600:].strip())
        except (OSError, ValueError):
            pass

    def _iniciar(self):
        if not self.ffmpeg:
            raise RuntimeError('FFmpeg não encontrado.')
        self._limpar()
        self.jpeg, self.carimbo, self.erro = None, 0, ''
        self.registros.clear()
        self.geracao += 1
        geracao = self.geracao
        adb = [self.adb, '-s', self.serial, 'exec-out', 'screenrecord', '--output-format=h264',
               '--size', f'{self.largura}x{self.altura}', '--bit-rate', '4M', '--time-limit', '0', '-']
        ffmpeg = [self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-threads', '1', '-flags', 'low_delay',
                  '-analyzeduration', '1', '-probesize', '32', '-fpsprobesize', '0',
                  # sem -avioflags direct/-blocksize: picavam o H264 e o decodificador recusava todo quadro
                  '-f', 'h264', '-i', 'pipe:0',
                  '-an', '-fps_mode', 'passthrough', '-c:v', 'mjpeg', '-threads', '1', '-q:v', '5', '-f', 'image2pipe',
                  '-flush_packets', '1', 'pipe:1']
        try:
            pasta_scrcpy = localizar_scrcpy()
            if pasta_scrcpy:
                self.backend = Scrcpy(self.adb, self.serial, pasta_scrcpy, self.largura, self.altura)
                self.backend.iniciar()
                origem = None
            else:
                origem = subprocess.Popen(adb, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          stdin=subprocess.DEVNULL, creationflags=_SEM_JANELA)
                self.processos.append(origem)
            conversor = subprocess.Popen(ffmpeg, stdin=origem.stdout if origem else subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, creationflags=_SEM_JANELA)
            self.processos.append(conversor)
            if origem:
                origem.stdout.close()
            else:
                threading.Thread(target=self.backend.bombear, args=(conversor.stdin,), daemon=True).start()
            for proc in self.processos:
                threading.Thread(target=self._stderr, args=(proc.stderr,), daemon=True).start()
            threading.Thread(target=self._ler, args=(conversor.stdout, geracao), daemon=True).start()
        except OSError:
            self._limpar()
            raise

    def _ler(self, canal, geracao):
        separador = _SeparadorJPEG()
        detalhe = ''
        try:
            while True:
                dados = canal.read1(65536)
                if not dados:
                    break
                jpeg, quantidade = separador.receber(dados)
                if jpeg:
                    with self.condicao:
                        if geracao != self.geracao or self.encerrado:
                            return
                        self.jpeg, self.carimbo = jpeg, time.monotonic()
                        self.quadros += quantidade
                        self.condicao.notify_all()
        except (OSError, ValueError, RuntimeError) as e:
            detalhe = str(e)
        finally:
            with self.condicao:
                if geracao == self.geracao and not self.encerrado:
                    self.erro = detalhe or 'A captura contínua encerrou. ' + ' '.join(self.registros)[-600:]
                    self.jpeg = None
                    self.condicao.notify_all()

    def iniciar(self):
        with self.condicao:
            if self.encerrado:
                raise RuntimeError('Transmissão encerrada.')
            if not self.processos or self.erro or any(p.poll() is not None for p in self.processos):
                self._iniciar()

    def ultimo(self):
        with self.condicao:
            if self.encerrado or self.erro:
                raise RuntimeError(self.erro or 'Transmissão encerrada.')
            return self.jpeg

    def proximo(self, carimbo, timeout=1.0):
        """espera um quadro mais novo que `carimbo` → (jpeg, carimbo); sem novo no prazo devolve (None, carimbo)"""
        with self.condicao:
            if self.carimbo <= carimbo:
                self.condicao.wait(timeout)
            if self.encerrado or self.erro:
                raise RuntimeError(self.erro or 'Transmissão encerrada.')
            if self.jpeg and self.carimbo > carimbo:
                return self.jpeg, self.carimbo
            return None, carimbo

    def controlar(self, acao, origem, **dados):
        with self.condicao:
            return self.backend.comando(acao, origem, **dados) if self.backend else None

    def pegar(self, timeout=10):
        limite = time.monotonic() + timeout
        self.iniciar()
        with self.condicao:
            while True:
                if self.encerrado:
                    raise RuntimeError('Transmissão encerrada.')
                if self.erro:
                    raise RuntimeError(self.erro)
                if self.jpeg:
                    return self.jpeg
                restante = limite - time.monotonic()
                if restante <= 0:
                    self.erro = 'Sem novo quadro do celular. Confira se a tela está acesa e desbloqueada.'
                    self._limpar()
                    raise TimeoutError(self.erro)
                self.condicao.wait(min(restante, 0.2))

    def estado(self):
        with self.condicao:
            idade = round((time.monotonic() - self.carimbo) * 1000) if self.carimbo else None
            return {'pronto': bool(self.jpeg and not self.erro and not self.encerrado),
                    'erro': self.erro, 'quadros': self.quadros, 'idade_ms': idade,
                    'motor': 'scrcpy' if self.backend else 'screenrecord'}

    def fechar(self):
        with self.condicao:
            if self.encerrado:
                return
            self.encerrado = True
            self.geracao += 1
            self.jpeg = None
            self.condicao.notify_all()
            self._limpar()
