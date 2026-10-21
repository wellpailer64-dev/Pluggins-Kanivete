"""Transporte do Codex CLI: três pipes drenados e cancelamento da árvore inteira."""
from collections import deque
import os
import queue
import subprocess
import threading
import time

_SEM_JANELA = 0x08000000 if os.name == "nt" else 0


def _job(processo):
    """Job próprio: nenhum filho do Codex fica vivo após Parar ou fechar o app."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class Limites(ctypes.Structure):
        _fields_ = [("tempo_processo", ctypes.c_int64), ("tempo_job", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t),
                    ("processos", wintypes.DWORD), ("afinidade", ctypes.c_size_t),
                    ("prioridade", wintypes.DWORD), ("agendamento", wintypes.DWORD)]

    class Estendidos(ctypes.Structure):
        _fields_ = [("limites", Limites), ("io", ctypes.c_uint64 * 6),
                    ("mem_processo", ctypes.c_size_t), ("mem_job", ctypes.c_size_t),
                    ("pico_processo", ctypes.c_size_t), ("pico_job", ctypes.c_size_t)]

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    handle = k.CreateJobObjectW(None, None)
    if not handle:
        return None
    info = Estendidos()
    info.limites.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k.SetInformationJobObject(wintypes.HANDLE(handle), 9, ctypes.byref(info), ctypes.sizeof(info)) or \
            not k.AssignProcessToJobObject(wintypes.HANDLE(handle), wintypes.HANDLE(int(processo._handle))):
        k.CloseHandle(wintypes.HANDLE(handle))
        return None
    return k, wintypes.HANDLE(handle)


def _encerrar(processo, job):
    if job:
        job[0].TerminateJobObject(job[1], 1)
    elif os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(processo.pid), "/T", "/F"],
                           capture_output=True, timeout=5, creationflags=_SEM_JANELA)
        except (OSError, subprocess.TimeoutExpired):
            pass
    if processo.poll() is None:
        processo.kill()


def executar(cmd, pasta, entrada, ao_linha, ao_espera, parar=None, prazo=600):
    """Entrega stdout linha a linha, stderr limitado e motivo distinto de interrupção."""
    inicio = time.monotonic()
    ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    processo = subprocess.Popen(cmd, cwd=pasta, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                                creationflags=_SEM_JANELA, env=ambiente)
    try:
        job = _job(processo)
    except (OSError, AttributeError):
        job = None
    fila = queue.Queue(maxsize=64)
    erros = deque(maxlen=30)
    terminar = threading.Event()

    def enviar(item):
        while not terminar.is_set():
            try:
                fila.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def ler_saida():
        try:
            for linha in processo.stdout:
                enviar(linha)
        finally:
            enviar(None)
            processo.stdout.close()

    def ler_erros():
        try:
            for linha in processo.stderr:
                erros.append(linha[-1500:])
        finally:
            processo.stderr.close()

    def escrever():
        try:
            processo.stdin.write(entrada)
        except (BrokenPipeError, OSError):
            pass  # erro de CLI é preservado em stderr
        finally:
            try:
                processo.stdin.close()
            except OSError:
                pass

    leitores = [threading.Thread(target=f, daemon=True) for f in (ler_saida, ler_erros, escrever)]
    cancelado = estourou = saida_fim = False
    primeiro = None
    atividade = inicio
    encerrado = None
    try:
        for leitor in leitores:
            leitor.start()
        while not saida_fim or processo.poll() is None:
            agora = time.monotonic()
            cancelado = bool(parar and parar.is_set())
            estourou = not cancelado and agora - inicio >= prazo
            if cancelado or estourou:
                _encerrar(processo, job)
                break
            try:
                linha = fila.get(timeout=0.2)
            except queue.Empty:
                if processo.poll() is not None:
                    # Um neto pode ter herdado stdout. O CLI já saiu; não esperar o neto por dez minutos.
                    if encerrado is None:
                        encerrado = agora
                        if job:
                            job[0].TerminateJobObject(job[1], 1)
                    if agora - encerrado >= 1:
                        break
                if agora - atividade >= 15:
                    ao_espera()
                    atividade = agora
                continue
            if linha is None:
                saida_fim = True
            else:
                if primeiro is None:
                    primeiro = int((time.monotonic() - inicio) * 1000)
                ao_linha(linha)
                atividade = time.monotonic()
        processo.wait(timeout=5)
    finally:
        terminar.set()
        # Fechar o Job encerra também netos que herdaram os pipes após o CLI sair.
        if job:
            job[0].CloseHandle(job[1])
        elif processo.poll() is None:
            _encerrar(processo, None)
        for leitor in leitores:
            if leitor.ident is not None:
                leitor.join(timeout=1)
    return {"codigo": processo.returncode, "erro": "".join(erros).strip()[-6000:],
            "cancelado": cancelado, "estourou": estourou,
            "primeiro_evento_ms": primeiro, "ms": int((time.monotonic() - inicio) * 1000)}
