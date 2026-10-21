"""GPU NVIDIA via NVML: leitura sob demanda, sem subprocessos nem dependências extras.

A medida é do dispositivo inteiro, não só da Kani. Drivers sem suporte retornam
indisponível; não substituímos a leitura por uma estimativa.
"""
import atexit
import ctypes as C
import os
import threading


class _Utilizacao(C.Structure):
    _fields_ = [("gpu", C.c_uint), ("memory", C.c_uint)]


class _Memoria(C.Structure):
    _fields_ = [("total", C.c_ulonglong), ("free", C.c_ulonglong), ("used", C.c_ulonglong)]


class _Monitor:
    def __init__(self):
        self._trava = threading.Lock()
        self._iniciado = False
        self._dll = None
        self._dispositivo = C.c_void_p()

    def _iniciar(self):
        self._iniciado = True
        candidatos = ([os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvml.dll"),
                       os.path.join(os.environ.get("ProgramW6432", r"C:\Program Files"),
                                    "NVIDIA Corporation", "NVSMI", "nvml.dll")]
                      if os.name == "nt" else ["libnvidia-ml.so.1"])
        for caminho in candidatos:
            try:
                dll = C.CDLL(caminho)
                dll.nvmlInit_v2.argtypes = []
                dll.nvmlInit_v2.restype = C.c_int
                dll.nvmlShutdown.argtypes = []
                dll.nvmlShutdown.restype = C.c_int
                dll.nvmlDeviceGetHandleByIndex_v2.argtypes = [C.c_uint, C.POINTER(C.c_void_p)]
                dll.nvmlDeviceGetHandleByIndex_v2.restype = C.c_int
                dll.nvmlDeviceGetName.argtypes = [C.c_void_p, C.c_char_p, C.c_uint]
                dll.nvmlDeviceGetName.restype = C.c_int
                dll.nvmlDeviceGetUtilizationRates.argtypes = [C.c_void_p, C.POINTER(_Utilizacao)]
                dll.nvmlDeviceGetUtilizationRates.restype = C.c_int
                dll.nvmlDeviceGetMemoryInfo.argtypes = [C.c_void_p, C.POINTER(_Memoria)]
                dll.nvmlDeviceGetMemoryInfo.restype = C.c_int
                dll.nvmlDeviceGetTemperature.argtypes = [C.c_void_p, C.c_uint, C.POINTER(C.c_uint)]
                dll.nvmlDeviceGetTemperature.restype = C.c_int
                if dll.nvmlInit_v2() != 0:
                    continue
                if dll.nvmlDeviceGetHandleByIndex_v2(0, C.byref(self._dispositivo)) != 0:
                    dll.nvmlShutdown()
                    continue
                self._dll = dll
                atexit.register(self.fechar)
                return
            except (OSError, AttributeError):
                continue

    def ler(self):
        with self._trava:
            if not self._iniciado:
                self._iniciar()
            if self._dll is None:
                return {"disponivel": False}
            dll, disp = self._dll, self._dispositivo
            nome = C.create_string_buffer(96)
            uso, memoria, temperatura = _Utilizacao(), _Memoria(), C.c_uint()
            nome_ok = dll.nvmlDeviceGetName(disp, nome, len(nome)) == 0
            uso_ok = dll.nvmlDeviceGetUtilizationRates(disp, C.byref(uso)) == 0
            memoria_ok = dll.nvmlDeviceGetMemoryInfo(disp, C.byref(memoria)) == 0
            temperatura_ok = dll.nvmlDeviceGetTemperature(disp, 0, C.byref(temperatura)) == 0
            return {"disponivel": uso_ok or memoria_ok,
                    "nome": nome.value.decode("utf-8", errors="replace") if nome_ok else "GPU NVIDIA",
                    "uso": min(100, uso.gpu) if uso_ok else None,
                    "memoria_usada": memoria.used if memoria_ok else None,
                    "memoria_total": memoria.total if memoria_ok else None,
                    "temperatura": temperatura.value if temperatura_ok else None}

    def fechar(self):
        with self._trava:
            if self._dll is not None:
                self._dll.nvmlShutdown()
                self._dll = None


_monitor = _Monitor()


def info():
    return _monitor.ler()
