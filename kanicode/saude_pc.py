"""Saúde do PC (aba Saúde do PC do KaniCode, 2026-10-24): leitura do hardware SEM admin (CIM + psutil + NVML) e o
que o último passe elevado deixou em <dados>/saude/sensores.json (SMART dos discos). A manutenção em si é
manutencao.py, aberto elevado por iniciar(); o andamento fica em <dados>/saude/estado.json.

Temperatura real da CPU no Windows só sai com driver de núcleo (LibreHardwareMonitor/PawnIO): sem ele, a aba mostra
a zona térmica ACPI (placa) e diz que é aproximada.
"""
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import dados_app

NO_WIN = 0x08000000
AQUI = Path(__file__).resolve().parent
_fixo = {"t": 0, "d": None}
_trava = threading.Lock()


def pasta():
    p = dados_app.pasta_dados() / "saude"
    p.mkdir(parents=True, exist_ok=True)
    return p


FIXO_PS = r"""
$o = [ordered]@{}
$o.cpu = Get-CimInstance Win32_Processor | Select -First 1 Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,L3CacheSize,SocketDesignation
$o.placa = Get-CimInstance Win32_BaseBoard | Select -First 1 Manufacturer,Product,Version
$b = Get-CimInstance Win32_BIOS | Select -First 1; $o.bios = @{versao=$b.SMBIOSBIOSVersion; data=$b.ReleaseDate.ToString('yyyy-MM-dd')}
$o.ram = @(Get-CimInstance Win32_PhysicalMemory | % { @{gb=[math]::Round($_.Capacity/1GB); mhz=$_.ConfiguredClockSpeed; max=$_.Speed; fab=$_.Manufacturer; modelo=($_.PartNumber).Trim(); slot=$_.DeviceLocator} })
$a = Get-CimInstance Win32_PhysicalMemoryArray | Select -First 1; $o.ram_slots = $a.MemoryDevices; $o.ram_max_gb = [math]::Round($a.MaxCapacityEx/1MB)
$o.gpu = @(Get-CimInstance Win32_VideoController | % { @{nome=$_.Name; driver=$_.DriverVersion; data=$_.DriverDate.ToString('yyyy-MM-dd')} })
$o.discos = @(Get-PhysicalDisk | % { @{id=[string]$_.DeviceId; nome=$_.FriendlyName; tipo=[string]$_.MediaType; bus=[string]$_.BusType; saude=[string]$_.HealthStatus; op=[string]$_.OperationalStatus; gb=[math]::Round($_.Size/1GB)} })
$o.volumes = @(Get-Partition | ? DriveLetter | % { $v = Get-Volume -Partition $_; @{l=[string]$_.DriveLetter; disco=[string]$_.DiskNumber; nome=$v.FileSystemLabel; fs=$v.FileSystem; saude=[string]$v.HealthStatus} })
$s = Get-CimInstance Win32_OperatingSystem; $o.so = @{nome=$s.Caption; build=$s.BuildNumber; boot=$s.LastBootUpTime.ToString('s')}
try { $m = Get-MpComputerStatus -EA Stop; $o.defender = @{ligado=$m.RealTimeProtectionEnabled; assinatura=$m.AntivirusSignatureLastUpdated.ToString('s'); rapida=$(if($m.QuickScanEndTime){$m.QuickScanEndTime.ToString('s')}); completa=$(if($m.FullScanEndTime){$m.FullScanEndTime.ToString('s')})} } catch {}
try { $o.acpi = (Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation | Select -First 1).HighPrecisionTemperature } catch {}
$o.reinicio_pendente = (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') -or (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired')
$o | ConvertTo-Json -Depth 5 -Compress
"""


def _fixo_ler():
    with _trava:
        if _fixo["d"] and time.time() - _fixo["t"] < 120:
            return _fixo["d"]
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + FIXO_PS],
                               capture_output=True, timeout=60, creationflags=NO_WIN)
            out = r.stdout.decode("utf-8", "replace")
            d = json.loads(out[out.index("{"):])
        except (OSError, ValueError, subprocess.TimeoutExpired):
            d = _fixo["d"] or {}
        _fixo.update(t=time.time(), d=d)
        return d


def _vivo():
    import psutil
    v = {"cpu_uso": psutil.cpu_percent(interval=0.3)}
    try:
        f = psutil.cpu_freq()
        v["cpu_mhz"] = round(f.current) if f else None
    except Exception:
        v["cpu_mhz"] = None
    m = psutil.virtual_memory()
    v["ram"] = {"total": m.total, "usada": m.total - m.available, "pct": m.percent}
    sw = psutil.swap_memory()
    v["swap"] = {"total": sw.total, "usada": sw.used}
    v["livres"] = {}
    for l in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        if ctypes.windll.kernel32.GetDriveTypeW(f"{l}:\\") == 3:
            try:
                u = psutil.disk_usage(f"{l}:\\")
                v["livres"][l] = {"total": u.total, "livre": u.free}
            except OSError:
                pass
    try:
        import gpu
        v["gpu"] = gpu.info()
    except Exception:
        v["gpu"] = None
    v["processos"] = len(psutil.pids())
    return v


def _sensores():
    try:
        return json.loads((pasta() / "sensores.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _nota(n):
    return "bom" if n >= 80 else "atenção" if n >= 55 else "ruim"


def ler():
    """tudo que a aba mostra, com nota 0–100 por peça e os alertas em linguagem simples"""
    f, v, s = _fixo_ler(), _vivo(), _sensores()
    alertas, pecas = [], []

    # discos
    smart = {str(d.get("id")): d for d in (s or {}).get("discos") or []}
    cdi = (s or {}).get("crystal") or []
    vols = f.get("volumes") or []
    for d in f.get("discos") or []:
        sm = smart.get(d["id"], {})
        nota = 100 if d.get("saude") == "Healthy" else 40 if d.get("saude") == "Warning" else 10
        wear = sm.get("desgaste")
        if wear:
            nota = min(nota, 100 - int(wear))
        temp = sm.get("temp")
        if temp and temp > 60:
            nota = min(nota, 60)
            alertas.append(f"{d['nome']} está quente ({temp} °C).")
        if (sm.get("erros_leitura") or 0) > 0:
            nota = min(nota, 50)
            alertas.append(f"{d['nome']} tem erros de leitura: faça backup.")
        cd = next((c for c in cdi if d["nome"].split()[0].lower() in (c.get("modelo") or "").lower()), None)
        if cd and cd.get("saude") and not cd["saude"].lower().startswith(("good", "bom")):
            nota = min(nota, 45)
            alertas.append(f"CrystalDiskInfo marca {d['nome']} como \"{cd['saude']}\".")
        letras = [x["l"] for x in vols if x.get("disco") == d["id"]]
        espaco = []
        for l in letras:
            lv = v["livres"].get(l)
            if lv:
                pct = lv["livre"] / lv["total"] * 100
                espaco.append({"l": l, "nome": next((x.get("nome") for x in vols if x["l"] == l), ""),
                               "livre": lv["livre"], "total": lv["total"], "pct": round(pct, 1)})
                if pct < 10:
                    alertas.append(f"Disco {l}: só {pct:.0f}% livre" + (" (o Windows fica lento com o C cheio)." if l == "C" else "."))
                    nota = min(nota, 70 if pct >= 5 else 55)
        pecas.append({"tipo": "disco", "nome": d["nome"], "sub": f"{d.get('tipo')} · {d.get('bus')} · {d.get('gb')} GB",
                      "nota": nota, "estado": _nota(nota), "saude": d.get("saude"), "temp": temp,
                      "desgaste": wear, "horas": sm.get("horas"), "volumes": espaco,
                      "crystal": cd.get("saude") if cd else None, "ssd": d.get("tipo") == "SSD"})

    # CPU
    c = f.get("cpu") or {}
    acpi = f.get("acpi")
    acpi_c = round(acpi / 10 - 273.15) if acpi else None
    nota = 100 if v["cpu_uso"] < 85 else 75
    pecas.insert(0, {"tipo": "cpu", "nome": (c.get("Name") or "Processador").replace("(R)", "").replace("(TM)", "").replace(" CPU", ""),
                     "sub": f"{c.get('NumberOfCores')} núcleos · {c.get('NumberOfLogicalProcessors')} threads · {c.get('MaxClockSpeed')} MHz",
                     "nota": nota, "estado": _nota(nota), "uso": v["cpu_uso"], "mhz": v.get("cpu_mhz"),
                     "temp": None, "temp_placa": acpi_c})

    # GPU
    g = v.get("gpu") or {}
    for k, gg in enumerate(f.get("gpu") or []):
        nvidia = "nvidia" in (gg.get("nome") or "").lower()
        t = g.get("temperatura") if nvidia else None
        nota = 100 if not t or t < 80 else 70 if t < 87 else 45
        if t and t >= 85:
            alertas.append(f"Placa de vídeo quente ({t} °C): limpe o pó e veja a ventilação.")
        pecas.insert(1 + k, {"tipo": "gpu", "nome": gg.get("nome"), "sub": f"driver {gg.get('driver')} · {gg.get('data')}",
                             "nota": nota, "estado": _nota(nota), "uso": g.get("uso") if nvidia else None,
                             "temp": t, "vram": [g.get("memoria_usada"), g.get("memoria_total")] if nvidia else None})

    # RAM
    ram = f.get("ram") or []
    r = v["ram"]
    nota = 100 if r["pct"] < 80 else 75 if r["pct"] < 92 else 50
    if r["pct"] >= 90:
        alertas.append(f"Memória quase cheia ({r['pct']:.0f}%).")
    mhz = [m.get("mhz") for m in ram if m.get("mhz")]
    pecas.append({"tipo": "ram", "nome": f"{round(r['total'] / 2**30)} GB de RAM",
                  "sub": f"{len(ram)} pente(s)" + (f" · {min(mhz)} MHz" if mhz else "") + (f" · {ram[0].get('fab')}" if ram else ""),
                  "nota": nota, "estado": _nota(nota), "pct": r["pct"], "usada": r["usada"], "total": r["total"],
                  "pentes": ram, "slots": f.get("ram_slots"), "max_gb": f.get("ram_max_gb")})
    if ram and len({m.get("slot", "")[:8] for m in ram}) == 1 and len(ram) >= 2:
        alertas.append("Os pentes de RAM parecem estar no mesmo canal (single channel): passar um para o slot do outro canal (veja o manual da placa) dobra a banda da memória.")

    # placa-mãe
    p, b = f.get("placa") or {}, f.get("bios") or {}
    nota = 100
    try:
        idade = (time.time() - time.mktime(time.strptime(b.get("data", ""), "%Y-%m-%d"))) / 86400 / 365
        if idade > 3:
            nota = 85
            alertas.append(f"BIOS de {b['data'][:4]}: vale conferir se a {p.get('Manufacturer', '').split()[0]} tem versão nova.")
    except (ValueError, OverflowError):
        pass
    pecas.append({"tipo": "placa", "nome": f"{(p.get('Manufacturer') or '').replace(' COMPUTER INC.', '')} {p.get('Product') or ''}".strip(),
                  "sub": f"BIOS {b.get('versao')} · {b.get('data')}", "nota": nota, "estado": _nota(nota), "temp": acpi_c})

    # sistema
    so, df = f.get("so") or {}, f.get("defender") or {}
    try:
        dias_boot = (time.time() - time.mktime(time.strptime(so.get("boot", ""), "%Y-%m-%dT%H:%M:%S"))) / 86400
    except (ValueError, OverflowError):
        dias_boot = 0
    if dias_boot > 7:
        alertas.append(f"O PC está ligado há {dias_boot:.0f} dias sem reiniciar.")
    if f.get("reinicio_pendente"):
        alertas.append("O Windows está esperando um reinício para terminar atualizações.")
    if df and not df.get("ligado"):
        alertas.append("A proteção em tempo real do Defender está DESLIGADA.")
    sist = {"so": so, "defender": df, "dias_boot": round(dias_boot, 1), "processos": v["processos"],
            "reinicio_pendente": f.get("reinicio_pendente"), "sensores_quando": (s or {}).get("quando")}
    geral = round(min(x["nota"] for x in pecas) * 0.5 + sum(x["nota"] for x in pecas) / len(pecas) * 0.5) if pecas else 0
    if alertas:
        geral = min(geral, 95 - 5 * min(len(alertas), 6))
    return {"ok": True, "geral": geral, "estado": _nota(geral), "pecas": pecas, "alertas": alertas, "sistema": sist,
            "manutencao": ultimo_resumo()}


# ── manutenção (processo elevado) ──

def estado():
    try:
        d = json.loads((pasta() / "estado.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {"situacao": "nada"}
    if d.get("situacao") in ("rodando", "decidir") and not _vivo_pid(d.get("pid")):
        d["situacao"] = "interrompida"
    return d


def _vivo_pid(pid):
    try:
        import psutil
        return bool(pid) and psutil.pid_exists(int(pid))
    except Exception:
        return True


def iniciar(etapas=None, completa=False, seco=False):
    e = estado()
    if e.get("situacao") in ("rodando", "decidir"):
        return {"ok": False, "erro": "A manutenção já está rodando."}
    arq = pasta() / "estado.json"
    try:
        arq.unlink(missing_ok=True)
        (pasta() / "decisao.json").unlink(missing_ok=True)
    except OSError:
        pass
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() else py)
    args = f'"{AQUI / "manutencao.py"}" --estado "{arq}"'
    if etapas:
        args += " --etapas " + ",".join(etapas)
    if completa:
        args += " --completa"
    if seco:
        args += " --seco"
    if seco:   # simulação não precisa de admin
        subprocess.Popen([exe] + _split(args), creationflags=NO_WIN, cwd=str(AQUI))
        return {"ok": True}
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, str(AQUI), 0)
    if rc <= 32:
        return {"ok": False, "erro": "O Windows não deu permissão de administrador (UAC recusado)."}
    return {"ok": True}


def _split(args):
    import shlex
    return [a.strip('"') for a in shlex.split(args, posix=False)]


def parar():
    try:
        (pasta() / "parar").write_text("1")
        return {"ok": True}
    except OSError as e:
        return {"ok": False, "erro": str(e)}


def decidir(ameacas, offline=False):
    """escolhas da aba para as ameaças: {id: remover|restaurar|ignorar}; o processo elevado aplica"""
    try:
        (pasta() / "decisao.json").write_text(json.dumps({"ameacas": ameacas or {}, "offline": bool(offline)}), "utf-8")
        return {"ok": True}
    except OSError as e:
        return {"ok": False, "erro": str(e)}


def lixeira(caminhos):
    """manda os duplicados escolhidos para a Lixeira (dá para voltar atrás); só arquivos que ainda existem"""
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
    ok, bytes_ = 0, 0
    for c in caminhos or []:
        c = os.path.abspath(str(c))
        if not os.path.isfile(c):
            continue
        n = os.path.getsize(c)
        op = SHFILEOPSTRUCTW(wFunc=3, pFrom=c + "\0\0", fFlags=0x40 | 0x10 | 0x400 | 0x04)   # ALLOWUNDO|NOCONFIRM|NOERRORUI|SILENT
        if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not os.path.exists(c):
            ok += 1
            bytes_ += n
    return {"ok": True, "movidos": ok, "bytes": bytes_}


def ultimo_resumo():
    e = estado()
    if e.get("situacao") == "nada":
        return None
    return {"situacao": e.get("situacao"), "fim": e.get("fim"), "inicio": e.get("inicio"), "liberado": e.get("liberado"),
            "seco": e.get("seco")}


if __name__ == "__main__":
    print(json.dumps(ler(), ensure_ascii=False, indent=1)[:6000])
