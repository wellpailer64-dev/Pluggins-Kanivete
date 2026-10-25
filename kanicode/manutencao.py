"""Manutenção do PC (aba Saúde do PC, 2026-10-24): roda ELEVADO (UAC), num processo à parte, e escreve o andamento em
<dados>/saude/estado.json; a aba só lê esse arquivo. No fim espera as decisões (ameaças) em decisao.json.

Regras de segurança da limpeza:
- só pastas de cache/temporários conhecidas; nunca segue junção/atalho de pasta;
- navegadores: SÓ as pastas de cache (Cache, Code Cache, GPUCache, shaders, cache2). Cookies, Login Data, Local
  Storage, IndexedDB, Network, Sessions, Web Applications ficam (logins continuam);
- Kanivete: temporários de teste com mais de 2 dias; renders/prévias/proxys sem uso há mais de 45 dias;
- duplicados: só LISTA (a aba manda para a Lixeira o que o Pailer marcar);
- ameaças: o Defender isola; a decisão final é do Pailer.

  py -3.13 manutencao.py --estado <estado.json> [--etapas limpeza,navegadores,...] [--completa] [--seco]
"""
import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

NO_WIN = 0x08000000
HOME = Path(os.path.expanduser("~"))
LOCAL = Path(os.environ.get("LOCALAPPDATA") or HOME / "AppData/Local")
ROAMING = Path(os.environ.get("APPDATA") or HOME / "AppData/Roaming")
WIN = Path(os.environ.get("SystemRoot") or r"C:\Windows")
PDATA = Path(os.environ.get("ProgramData") or r"C:\ProgramData")
DIA = 86400

ETAPAS = [
    ("preparar", "Preparar (ponto de restauração)"),
    ("sensores", "Ler sensores dos discos"),
    ("limpeza", "Lixo do Windows"),
    ("navegadores", "Cache dos navegadores e apps"),
    ("kanivete", "Resíduos do Kanivete e KaniCode"),
    ("duplicados", "Procurar arquivos duplicados"),
    ("virus", "Vírus e ameaças (Defender)"),
    ("drivers", "Drivers desatualizados"),
    ("reparo", "Reparar o Windows (DISM + SFC)"),
    ("discos", "Desfragmentar / otimizar discos"),
]

# pastas de cache do Chromium/Electron/WebView2: só valem com um "perfil" ao lado (marca)
CACHE_NOMES = {"cache", "code cache", "gpucache", "dawngraphitecache", "dawnwebgpucache", "grshadercache",
               "shadercache", "graphitedawncache", "component_crx_cache"}
MARCAS_PERFIL = {"preferences", "local storage", "network", "cookies", "local state", "web data"}
# nada abaixo disto é apagado, mesmo se cair numa varredura (logins, sessões, favoritos, PWAs)
PROTEGIDO = re.compile(r"\\(local storage|session storage|indexeddb|network|sessions|web applications|extensions|"
                       r"sync data|local extension settings|databases|storage)(\\|$)|"
                       r"\\(login data|cookies|web data|bookmarks|history|preferences|secure preferences|local state|"
                       r"key4\.db|logins\.json|cert9\.db|cookies\.sqlite)$", re.I)


class Estado:
    def __init__(self, caminho, etapas, seco):
        self.caminho = Path(caminho)
        self.d = {"situacao": "rodando", "seco": seco, "inicio": time.time(), "pid": os.getpid(),
                  "etapas": [{"id": i, "nome": n, "estado": "espera" if i in etapas else "pulada", "detalhe": "",
                              "progresso": 0, "liberado": 0} for i, n in ETAPAS],
                  "log": [], "discos_antes": livres(), "liberado": 0, "ameacas": [], "drivers": [],
                  "duplicados": [], "avisos": [], "reiniciar": False}
        self._t = 0
        self.gravar(True)

    def etapa(self, i):
        return next(e for e in self.d["etapas"] if e["id"] == i)

    def gravar(self, ja=False):
        if not ja and time.time() - self._t < 0.5:
            return
        self._t = time.time()
        tmp = self.caminho.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.d, ensure_ascii=False), "utf-8")
            os.replace(tmp, self.caminho)
        except OSError:
            pass

    def log(self, txt):
        self.d["log"] = (self.d["log"] + [time.strftime("%H:%M:%S ") + txt])[-1500:]
        self.gravar()

    def det(self, i, detalhe=None, progresso=None):
        e = self.etapa(i)
        if detalhe is not None:
            e["detalhe"] = detalhe
        if progresso is not None:
            e["progresso"] = max(0, min(100, round(progresso)))
        # texto novo grava na hora: antes de um comando longo (DISM, SFC) a gravação adiada se perdia
        self.gravar(detalhe is not None)


def livres():
    r = {}
    for l in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        if ctypes.windll.kernel32.GetDriveTypeW(f"{l}:\\") == 3:   # disco fixo
            try:
                u = shutil.disk_usage(f"{l}:\\")
                r[l] = {"livre": u.free, "total": u.total}
            except OSError:
                pass
    return r


def juncao(p):
    try:
        return os.path.islink(p) or os.path.isjunction(p)
    except (OSError, AttributeError):
        return False


def ps(script, timeout=600):
    """roda PowerShell e devolve (código, saída)"""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script],
                           capture_output=True, timeout=timeout, creationflags=NO_WIN)
        return r.returncode, (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return -1, "tempo esgotado"
    except OSError as e:
        return -1, str(e)


class Limpador:
    def __init__(self, est, seco):
        self.est, self.seco = est, seco

    def conteudo(self, pasta, idade_dias=0, etapa=None, filtro=None):
        """apaga o CONTEÚDO de pasta (arquivos com mais de idade_dias); devolve bytes. Pastas vazias somem, a raiz fica."""
        pasta = Path(pasta)
        if not pasta.is_dir() or juncao(pasta) or PROTEGIDO.search(str(pasta)):
            return 0
        limite, total, subpastas = time.time() - idade_dias * DIA, 0, []
        for raiz, dirs, arqs in os.walk(pasta):
            # o os.walk entra em junções: corta aqui (nunca apagar o que mora em outro lugar)
            dirs[:] = [d for d in dirs if not juncao(os.path.join(raiz, d))]
            if Path(raiz) != pasta:
                subpastas.append(raiz)
            for a in arqs:
                p = os.path.join(raiz, a)
                if PROTEGIDO.search(p) or (filtro and not filtro(p)):
                    continue
                try:
                    s = os.stat(p)
                    if idade_dias and max(s.st_mtime, s.st_atime if idade_dias > 7 else 0) > limite:
                        continue
                    if not self.seco:
                        try:
                            os.remove(p)
                        except PermissionError:
                            os.chmod(p, 0o666)
                            os.remove(p)
                    total += s.st_size
                except OSError:
                    pass   # em uso: fica
        if not self.seco:
            for raiz in reversed(subpastas):
                try:
                    os.rmdir(raiz)
                except OSError:
                    pass
        if etapa and total:
            e = self.est.etapa(etapa)
            e["liberado"] += total
            self.est.d["liberado"] += total
            self.est.log(f"{fmt(total)} · {pasta}")
        return total


def fmt(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}".replace(".", ",")
        n /= 1024


# ── etapas ────────────────────────────────────────────────────────────────

def e_preparar(est, L, a):
    if a.seco:
        est.det("preparar", "simulação: nada é apagado")
        return
    est.det("preparar", "criando ponto de restauração…", 30)
    c, out = ps("Checkpoint-Computer -Description 'KaniCode - manutencao' -RestorePointType MODIFY_SETTINGS", 300)
    if c == 0:
        est.det("preparar", "ponto de restauração criado")
    else:
        est.det("preparar", "sem ponto de restauração (Proteção do Sistema desligada)")
        est.d["avisos"].append("A Proteção do Sistema está desligada: não deu para criar um ponto de restauração.")


def e_sensores(est, L, a):
    script = ("Get-PhysicalDisk | % { $r = $_ | Get-StorageReliabilityCounter -EA SilentlyContinue; "
              "[pscustomobject]@{id=$_.DeviceId; nome=$_.FriendlyName; temp=$r.Temperature; tempmax=$r.TemperatureMax; "
              "desgaste=$r.Wear; horas=$r.PowerOnHours; erros_leitura=$r.ReadErrorsUncorrected; "
              "erros_escrita=$r.WriteErrorsUncorrected; ligado=$r.StartStopCycleCount} } | ConvertTo-Json -Compress")
    c, out = ps(script, 120)
    discos = []
    try:
        j = json.loads(out[out.index("["):] if "[" in out else out[out.index("{"):])
        discos = j if isinstance(j, list) else [j]
    except (ValueError, json.JSONDecodeError):
        pass
    cdi = cristal()
    dados = {"quando": time.time(), "discos": discos, "crystal": cdi}
    try:
        (est.caminho.parent / "sensores.json").write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
    except OSError:
        pass
    est.det("sensores", f"{len(discos)} discos lidos" + (" + CrystalDiskInfo" if cdi else ""), 100)


def cristal():
    """CrystalDiskInfo instalado: /CopyExit grava DiskInfo.txt com o SMART completo e a nota de saúde de cada disco"""
    for base in (r"C:\Program Files\CrystalDiskInfo", r"C:\Program Files (x86)\CrystalDiskInfo"):
        exe = Path(base) / "DiskInfo64.exe"
        if not exe.exists():
            exe = Path(base) / "DiskInfo32.exe"
        if not exe.exists():
            continue
        try:
            subprocess.run([str(exe), "/CopyExit"], timeout=90, creationflags=NO_WIN, cwd=base)
            txt = (Path(base) / "DiskInfo.txt").read_bytes()
            txt = txt.decode("utf-16") if txt[:2] in (b"\xff\xfe", b"\xfe\xff") else txt.decode("utf-8", "replace")
        except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
            return []
        r = []
        for bloco in re.split(r"\n\s*-{20,}\s*\n\s*\(\d+\)", txt)[1:]:
            g = lambda rx: (re.search(rx, bloco, re.M) or [None, ""])[1].strip()
            r.append({"modelo": g(r"^\s*(.+?)\s*$"), "saude": g(r"Health Status\s*:\s*(.+)"),
                      "temp": g(r"Temperature\s*:\s*(.+)"), "horas": g(r"Power On Hours\s*:\s*(.+)"),
                      "ligado": g(r"Power On Count\s*:\s*(.+)"), "escrito": g(r"Host Writes\s*:\s*(.+)"),
                      "serial": g(r"Serial Number\s*:\s*(.+)")})
        return r
    return []


def e_limpeza(est, L, a):
    i = "limpeza"
    alvos = [
        ("Temporários do usuário", Path(os.environ.get("TEMP", LOCAL / "Temp")), 1),
        ("Temporários do Windows", WIN / "Temp", 1),
        ("Relatórios de erro", PDATA / "Microsoft/Windows/WER/ReportArchive", 0),
        ("Relatórios de erro", PDATA / "Microsoft/Windows/WER/ReportQueue", 0),
        ("Relatórios de erro", LOCAL / "Microsoft/Windows/WER", 0),
        ("Despejos de memória", WIN / "Minidump", 0),
        ("Despejos de memória", LOCAL / "CrashDumps", 0),
        ("Logs antigos do Windows", WIN / "Logs/CBS", 7),
        ("Logs antigos do Windows", WIN / "Logs/DISM", 7),
        ("Cache de shaders do DirectX", LOCAL / "D3DSCache", 0),
        ("Cache de shaders NVIDIA", LOCAL / "NVIDIA/DXCache", 0),
        ("Cache de shaders NVIDIA", LOCAL / "NVIDIA/GLCache", 0),
        ("Cache de shaders NVIDIA", LOCAL / "NVIDIA Corporation/NV_Cache", 0),
        ("Instaladores antigos NVIDIA", PDATA / "NVIDIA Corporation/Downloader", 3),
        ("Cache da Loja", LOCAL / "Packages/Microsoft.WindowsStore_8wekyb3d8bbwe/LocalCache", 0),
        ("Cache do Windows Update", WIN / "SoftwareDistribution/Download", 0),
        ("Cache do pip", LOCAL / "pip/cache", 0),
        ("Cache do npm", LOCAL / "npm-cache/_cacache", 0),
        ("Cache de miniaturas", LOCAL / "Microsoft/Windows/Explorer", 0),
        # achados no PC do Pailer (2026-10-24): instaladores e sobras que os programas não apagam sozinhos
        ("Drivers antigos baixados pelo NVIDIA app", PDATA / "NVIDIA Corporation/NVIDIA app/UpdateFramework/ota-artifacts", 3),
        ("Temporários do instalador da Adobe", Path("C:/adobeTemp"), 3),
        ("Temporários de atualização do Windows", WIN / "CbsTemp", 3),
        ("Instaladores já usados", LOCAL / "Downloaded Installations", 7),
        ("Atualizações baixadas do Ollama", LOCAL / "Ollama/updates_v2", 3),
        ("Cache do HitPaw", LOCAL / "cache/HitPawPhotoEnhancer", 7),
    ]
    # dados de plugins de versões ANTIGAS do Photoshop (UXP/PluginsStorage/PHSP/<versão>): fica só a mais nova
    phsp = ROAMING / "Adobe/UXP/PluginsStorage/PHSP"
    if phsp.is_dir():
        vers = sorted((p for p in phsp.iterdir() if p.is_dir() and p.name.isdigit()), key=lambda p: int(p.name))
        alvos += [(f"Plugins do Photoshop antigo (v{p.name})", p, 0) for p in vers[:-1]]
    # modelos do Ollama numa pasta que ele NÃO usa mais (a valendo é a OLLAMA_MODELS)
    atual = _ollama_models()
    for p in (HOME / ".ollama/models", Path("D:/Program Files/.ollama/models"), Path("C:/Program Files/.ollama/models")):
        if atual and p.is_dir() and not juncao(p) and os.path.normcase(str(p.resolve())) != os.path.normcase(atual):
            alvos.append(("Modelos antigos do Ollama (pasta sem uso)", p, 0))
    # dependências (node_modules) de projetos do Dyad parados há 30 dias: "npm install" refaz
    for app in (HOME / "dyad-apps").glob("*"):
        nm = app / "node_modules"
        if nm.is_dir() and not juncao(nm) and time.time() - _mais_novo(app) > 30 * DIA:
            alvos.append((f"Dependências do projeto parado {app.name} (Dyad)", nm, 0))
    if not a.seco:
        ps("Stop-Service wuauserv,bits,dosvc -Force -EA SilentlyContinue", 60)
    for k, (nome, p, dias) in enumerate(alvos):
        est.det(i, nome, k / len(alvos) * 85)
        filtro = (lambda x: os.path.basename(x).lower().startswith(("thumbcache_", "iconcache_"))) if "Explorer" in str(p) else None
        L.conteudo(p, dias, i, filtro)
    if not a.seco:
        ps("Start-Service wuauserv,bits,dosvc -EA SilentlyContinue", 60)
        dump = WIN / "MEMORY.DMP"
        if dump.exists():
            try:
                n = dump.stat().st_size
                dump.unlink()
                est.etapa(i)["liberado"] += n
                est.d["liberado"] += n
            except OSError:
                pass
        est.det(i, "otimização de entrega e lixeiras", 88)
        ps("Delete-DeliveryOptimizationCache -Force -EA SilentlyContinue", 120)
    # lixeira de cada disco
    lix = 0
    for l in est.d["discos_antes"]:
        lix += L.conteudo(f"{l}:\\$Recycle.Bin", 0, None)
    if lix:
        est.etapa(i)["liberado"] += lix
        est.d["liberado"] += lix
        est.log(f"{fmt(lix)} · lixeiras")
    if not a.seco:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, creationflags=NO_WIN)
    # hibernação desligada (decisão do Pailer, 2026-10-24): o hiberfil.sys some do C
    hib = Path("C:/hiberfil.sys")
    try:
        n = hib.stat().st_size if hib.exists() else 0
    except OSError:
        n = 0
    if n:
        est.det(i, "desligando a hibernação…", 95)
        if not a.seco:
            subprocess.run(["powercfg", "/hibernate", "off"], capture_output=True, creationflags=NO_WIN)
        if a.seco or not hib.exists():
            est.etapa(i)["liberado"] += n
            est.d["liberado"] += n
            est.log(f"{fmt(n)} · hibernação desligada")
    mover_videos(est, a)
    est.det(i, f"{fmt(est.etapa(i)['liberado'])} liberados", 100)


def _ollama_models():
    v = os.environ.get("OLLAMA_MODELS")
    if not v:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                v = winreg.QueryValueEx(k, "OLLAMA_MODELS")[0]
        except OSError:
            v = None
    return str(Path(v).resolve()) if v and Path(v).is_dir() else None


def _mais_novo(pasta):
    """data da mudança mais recente fora do node_modules (até 3 níveis: barato)"""
    t = pasta.stat().st_mtime
    for r, dirs, arqs in os.walk(pasta):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "dist", ".next")]
        if len(Path(r).relative_to(pasta).parts) >= 3:
            dirs[:] = []
        for f in arqs:
            try:
                t = max(t, os.stat(os.path.join(r, f)).st_mtime)
            except OSError:
                pass
    return t


def mover_videos(est, a):
    """Vídeos do C vão para "E:/Vídeos (do C)" (decisão do Pailer, 2026-10-24: o C é pequeno; o E tem espaço).
    Só arquivos sem mudança há 1 dia (não pega gravação em andamento); robocopy /MOV confere e só então apaga."""
    orig, dest = HOME / "Videos", Path("E:/Vídeos (do C)")
    if not orig.is_dir() or not Path("E:/").exists():
        return
    try:
        n = sum(f.stat().st_size for f in orig.rglob("*") if f.is_file() and time.time() - f.stat().st_mtime > DIA)
    except OSError:
        n = 0
    if not n or shutil.disk_usage("E:/").free < n * 1.2:
        return
    est.det("limpeza", f"movendo {fmt(n)} de vídeos do C para o E…", 97)
    if not a.seco:
        subprocess.run(["robocopy", str(orig), str(dest), "/E", "/MOV", "/MINAGE:1", "/R:1", "/W:1", "/NP", "/NFL", "/NDL",
                        "/XF", "desktop.ini"], capture_output=True, creationflags=NO_WIN, timeout=6 * 3600)
    est.etapa("limpeza")["liberado"] += n
    est.d["liberado"] += n
    est.log(f"{fmt(n)} · vídeos movidos para {dest}")


def perfis_cache(raizes, prof=7):
    """pastas de cache dentro de perfis do Chromium/Electron/WebView2 (tem Preferences/Local Storage... ao lado)"""
    achadas = []
    for raiz in raizes:
        raiz = Path(raiz)
        if not raiz.is_dir():
            continue
        base = len(raiz.parts)
        for r, dirs, _ in os.walk(raiz):
            rp = Path(r)
            if len(rp.parts) - base >= prof or juncao(rp) or PROTEGIDO.search(r):
                dirs[:] = []
                continue
            nomes = {d.lower() for d in dirs}
            try:
                vizinhos = {n.lower() for n in os.listdir(r)}
            except OSError:
                continue
            perfil = bool(vizinhos & MARCAS_PERFIL)
            for d in list(dirs):
                if d.lower() in CACHE_NOMES and perfil:
                    achadas.append(rp / d)
                    dirs.remove(d)
                elif d.lower() in ("service worker",) and perfil:
                    for sub in ("CacheStorage", "ScriptCache"):
                        if (rp / d / sub).is_dir():
                            achadas.append(rp / d / sub)
                    dirs.remove(d)
            dirs[:] = [d for d in dirs if d.lower() not in ("packages", "microsoft\\windows", "programs")]
    return achadas


def e_navegadores(est, L, a):
    i = "navegadores"
    est.det(i, "procurando perfis…", 5)
    raizes = [LOCAL, ROAMING, Path("D:/Kanivete/KaniBrowser"), Path("D:/Kanivete/KaniCode")]
    pastas = perfis_cache(raizes)
    for ff in (LOCAL / "Mozilla/Firefox/Profiles").glob("*"):
        pastas += [ff / "cache2", ff / "startupCache", ff / "thumbnails"]
    for k, p in enumerate(pastas):
        est.det(i, str(p.relative_to(p.anchor))[-60:], 5 + k / max(1, len(pastas)) * 95)
        L.conteudo(p, 0, i)
    est.det(i, f"{len(pastas)} caches · {fmt(est.etapa(i)['liberado'])} (logins mantidos)", 100)


def _prefs_kanivete():
    try:
        return json.loads((ROAMING / "CaniveteDoPailer" / "preferencias.json").read_text("utf-8")) or {}
    except (OSError, ValueError):
        return {}


def e_kanivete(est, L, a):
    i = "kanivete"
    cache_dir = ((_prefs_kanivete().get("cache") or {}).get("dir") or "").strip()
    bases = {LOCAL / "CaniveteDoPailer"}
    if cache_dir:
        bases.add(Path(cache_dir))
    for l in est.d["discos_antes"]:
        bases.add(Path(f"{l}:\\"))
    alvos = [("Temporários dos testes", Path("D:/kanivete_testes/tmp"), 2),
             ("Temporários dos testes", Path("D:/kanivete_testes/localappdata/Temp"), 2),
             ("Logs do Kanivete", ROAMING / "CaniveteDoPailer/logs", 30),
             ("Resíduos do KaniCode", Path("D:/Kanivete/KaniCode/tmp"), 2),
             # cache do app de teste (renders/prévias dos testes de export, porta 9333): refeito sozinho
             ("Cache dos testes de export", Path("D:/kanivete_testes/cache_teste"), 1 / 24)]
    # cópias temporárias dos testes do KaniCode (tempfile "codigo_teste_*", tests/test_codigo_agente.py)
    for q in Path("D:/kanivete_testes").glob("codigo_teste_*"):
        if q.is_dir() and not juncao(q) and time.time() - q.stat().st_mtime > 2 * DIA:
            alvos.append(("Cópias de teste do KaniCode", q, 0))
    for b in bases:
        for sub, nome, dias in (("Canivete Render Cache", "Renders sem uso há 14 dias", 14),
                                ("Canivete Media Cache", "Prévias e proxys sem uso há 45 dias", 45),
                                ("Canivete Cache", "Caches do Kanivete sem uso há 45 dias", 45)):
            if (b / sub).is_dir():
                alvos.append((nome, b / sub, dias))
    # Adobe/DaVinci (como os bats): caches de mídia antigos
    alvos += [("Cache de mídia da Adobe", ROAMING / "Adobe/Common/Media Cache Files", 30),
              ("Cache de mídia da Adobe", ROAMING / "Adobe/Common/Media Cache", 30),
              ("Cache de mídia da Adobe", ROAMING / "Adobe/Common/Peak Files", 30)]
    for l in est.d["discos_antes"]:
        for p in (r"Adobe\Common\Media Cache Files", "Adobe Media Cache", r"DaVinci Resolve\CacheClip", r"Resolve\CacheClip",
                  r"Steam\steamapps\downloading", r"Steam\steamapps\temp", r"SteamLibrary\steamapps\downloading",
                  r"SteamLibrary\steamapps\temp", "Temp", "tmp"):
            q = Path(f"{l}:\\") / p
            if q.is_dir() and not (l == "C" and p.lower() in ("temp", "tmp")):
                alvos.append((p.split("\\")[0], q, 7 if "Cache" in p else 2))
    for k, (nome, p, dias) in enumerate(alvos):
        est.det(i, nome, k / len(alvos) * 100)
        L.conteudo(p, dias, i)
        if nome.startswith("Cópias de teste") and not a.seco:
            try:
                p.rmdir()   # a pasta temporária inteira some quando ficou vazia
            except OSError:
                pass
    est.det(i, f"{fmt(est.etapa(i)['liberado'])} liberados", 100)


def e_duplicados(est, L, a):
    i = "duplicados"
    raizes = [HOME / n for n in ("Desktop", "Downloads", "Documents", "Pictures", "Videos", "Music")]
    raizes += [Path(f"{l}:\\Downloads") for l in est.d["discos_antes"]]
    por_tam = {}
    vistos = 0
    for raiz in raizes:
        if not raiz.is_dir() or juncao(raiz):
            continue
        for r, dirs, arqs in os.walk(raiz):
            dirs[:] = [d for d in dirs if not juncao(os.path.join(r, d)) and not d.startswith((".", "$"))
                       and d.lower() not in ("node_modules", "appdata")]
            for f in arqs:
                p = os.path.join(r, f)
                try:
                    s = os.stat(p)
                except OSError:
                    continue
                if s.st_size >= 1 << 20:
                    por_tam.setdefault(s.st_size, []).append(p)
                vistos += 1
                if vistos % 2000 == 0:
                    est.det(i, f"{vistos} arquivos vistos", 20)
    cands = [ps_ for ps_ in por_tam.values() if len(ps_) > 1]
    grupos = []
    for k, lista in enumerate(cands):
        est.det(i, f"comparando {k + 1}/{len(cands)}", 20 + k / max(1, len(cands)) * 80)
        por_hash = {}
        for p in lista:
            h = hash_arquivo(p)
            if h:
                por_hash.setdefault(h, []).append(p)
        for lst in por_hash.values():
            if len(lst) > 1:
                # fica o mais antigo fora de Downloads; o resto é cópia
                lst.sort(key=lambda p: ("\\downloads\\" in p.lower(), os.path.getmtime(p), len(p)))
                grupos.append({"tamanho": os.path.getsize(lst[0]), "manter": lst[0], "copias": lst[1:]})
    grupos.sort(key=lambda g: -g["tamanho"] * len(g["copias"]))
    est.d["duplicados"] = grupos[:300]
    total = sum(g["tamanho"] * len(g["copias"]) for g in grupos)
    est.det(i, f"{len(grupos)} grupos · {fmt(total)} em cópias (você escolhe no fim)", 100)


def hash_arquivo(p):
    """começo+fim primeiro (barato); igual nisso, o arquivo inteiro"""
    try:
        with open(p, "rb") as f:
            h = hashlib.blake2b(f.read(1 << 16), digest_size=16)
            f.seek(-min(1 << 16, os.path.getsize(p)), 2)
            h.update(f.read())
            f.seek(0)
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
        return h.hexdigest()
    except OSError:
        return None


def e_virus(est, L, a):
    i = "virus"
    inicio = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 60))
    est.det(i, "atualizando as definições…", 5)
    ps("Update-MpSignature -EA SilentlyContinue", 600)
    tipo = "FullScan" if a.completa else "QuickScan"
    est.det(i, "verificação " + ("completa (demora)" if a.completa else "rápida") + "…", 15)
    if not a.seco:
        # o Defender não diz a porcentagem: roda numa linha à parte e a aba mostra o tempo passando
        import threading
        nome = "completa" if a.completa else "rápida"
        t = threading.Thread(target=ps, args=(f"Start-MpScan -ScanType {tipo}", 6 * 3600 if a.completa else 3600), daemon=True)
        t0 = time.time()
        t.start()
        while t.is_alive():
            seg = time.time() - t0
            media = 3 * 3600 if a.completa else 600   # rápida costuma levar 5–15 min; completa, horas
            est.det(i, f"verificação {nome} do Defender · {int(seg // 60)} min {int(seg % 60):02d} s"
                       + (" (costuma levar 5–15 min)" if not a.completa else " (pode levar horas)"),
                    15 + 78 * (1 - 2.718 ** (-seg / media)))
            t.join(2)
    est.det(i, "lendo o que foi achado…", 95)
    c, out = ps("$t = @{}; Get-MpThreat -EA SilentlyContinue | % { $t[[string]$_.ThreatID] = $_ }; "
                "Get-MpThreatDetection -EA SilentlyContinue | ? { $_.InitialDetectionTime -gt (Get-Date).AddDays(-30) } | % { "
                "$x = $t[[string]$_.ThreatID]; [pscustomobject]@{id=[string]$_.ThreatID; nome=$x.ThreatName; "
                "gravidade=$x.SeverityID; ativo=$x.IsActive; status=$_.ThreatStatusID; recursos=($_.Resources -join ' | '); "
                "quando=$_.InitialDetectionTime.ToString('s'); acao_ok=$_.ActionSuccess} } | ConvertTo-Json -Compress", 300)
    amea = []
    try:
        j = out[min([k for k in (out.find("["), out.find("{")) if k >= 0]):]
        j = json.loads(j)
        amea = j if isinstance(j, list) else [j]
    except (ValueError, json.JSONDecodeError):
        pass
    vistos = {}
    for t in amea:
        vistos.setdefault(t.get("id"), t)
    lista = list(vistos.values())
    for t in lista:
        g = int(t.get("gravidade") or 0)
        t["nivel"] = {1: "baixa", 2: "moderada", 4: "alta", 5: "grave"}.get(g, "?")
        t["recomendo"] = "remover" if g >= 2 else "avaliar"
        t["nova"] = (t.get("quando") or "") >= inicio
    est.d["ameacas"] = lista
    est.det(i, "nenhuma ameaça" if not lista else f"{len(lista)} ameaça(s) isolada(s)", 100)


DRIVERS_PS = r"""
$s = New-Object -ComObject Microsoft.Update.Session; $s.ClientApplicationID = 'KaniCode'
$b = $s.CreateUpdateSearcher(); $b.ServiceID = '7971f918-a847-4430-9279-4a52d1efe18d'; $b.ServerSelection = 3
try { $r = $b.Search("IsInstalled=0 and Type='Driver' and IsHidden=0") } catch { $b = $s.CreateUpdateSearcher(); $r = $b.Search("IsInstalled=0 and Type='Driver' and IsHidden=0") }
$lista = @(); foreach ($u in $r.Updates) { $lista += [pscustomobject]@{nome=$u.Title; fab=$u.DriverManufacturer; classe=$u.DriverClass; data=$u.DriverVerDate.ToString('yyyy-MM-dd'); ok=$null} }
if ($env:KC_SECO -ne '1' -and $r.Updates.Count -gt 0) {
  $c = New-Object -ComObject Microsoft.Update.UpdateColl; foreach ($u in $r.Updates) { if (-not $u.EulaAccepted) { $u.AcceptEula() }; [void]$c.Add($u) }
  Write-Host "BAIXANDO"; $d = $s.CreateUpdateDownloader(); $d.Updates = $c; [void]$d.Download()
  Write-Host "INSTALANDO"; $n = $s.CreateUpdateInstaller(); $n.Updates = $c; $res = $n.Install()
  for ($k = 0; $k -lt $c.Count; $k++) { $lista[$k].ok = ($res.GetUpdateResult($k).ResultCode -eq 2) }
  if ($res.RebootRequired) { Write-Host "REINICIAR" }
}
Write-Host ("JSON" + (ConvertTo-Json @($lista) -Compress))
"""


def e_drivers(est, L, a):
    i = "drivers"
    est.det(i, "procurando no Windows Update…", 10)
    os.environ["KC_SECO"] = "1" if a.seco else "0"
    c, out = ps(DRIVERS_PS, 3600)
    lista = []
    m = re.search(r"JSON(\[.*\])", out, re.S)
    if m:
        try:
            lista = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    if "REINICIAR" in out:
        est.d["reiniciar"] = True
    est.d["drivers"] = lista
    if c != 0 and not lista:
        est.det(i, "não consegui falar com o Windows Update", 100)
        est.d["avisos"].append("Drivers: o Windows Update não respondeu (" + out.strip()[-160:] + ")")
    else:
        inst = sum(1 for d in lista if d.get("ok"))
        est.det(i, "todos em dia" if not lista else
                (f"{len(lista)} disponíveis (simulação)" if a.seco else f"{inst} de {len(lista)} instalados"), 100)


def e_reparo(est, L, a):
    i = "reparo"
    if a.seco:
        est.det(i, "simulação: não roda", 100)
        return
    est.det(i, "DISM: limpando componentes antigos…", 5)
    ps("dism /Online /Cleanup-Image /StartComponentCleanup /Quiet", 3600)
    est.det(i, "DISM: conferindo a imagem do Windows…", 35)
    c, out = ps("dism /Online /Cleanup-Image /RestoreHealth", 5400)
    dism_ok = c == 0
    est.det(i, "SFC: conferindo arquivos do sistema…", 70)
    try:
        r = subprocess.run(["sfc", "/scannow"], capture_output=True, timeout=5400, creationflags=NO_WIN)
        txt = r.stdout.decode("utf-16-le", "replace") if b"\x00" in r.stdout[:200] else r.stdout.decode("cp850", "replace")
    except (OSError, subprocess.TimeoutExpired):
        txt = ""
    if re.search(r"não encontrou|did not find", txt, re.I):
        sfc = "sem problemas"
    elif re.search(r"reparou|successfully repaired", txt, re.I):
        sfc = "consertou arquivos"
        est.d["reiniciar"] = True
    elif re.search(r"não pôde|unable to fix", txt, re.I):
        sfc = "achou arquivos que não conseguiu consertar"
        est.d["avisos"].append("SFC achou arquivos do sistema que não conseguiu consertar (veja C:\\Windows\\Logs\\CBS\\CBS.log).")
    else:
        sfc = "terminou"
    est.det(i, ("DISM ok · " if dism_ok else "DISM falhou · ") + "SFC " + sfc, 100)


def e_discos(est, L, a):
    i = "discos"
    c, out = ps("Get-Partition | ? DriveLetter | % { $d = Get-Disk -Number $_.DiskNumber; $p = Get-PhysicalDisk | ? DeviceId -eq $_.DiskNumber; "
                "[pscustomobject]@{l=[string]$_.DriveLetter; tipo=[string]$p.MediaType} } | ConvertTo-Json -Compress", 120)
    tipos = {}
    try:
        j = json.loads(out[min([k for k in (out.find("["), out.find("{")) if k >= 0]):])
        for x in (j if isinstance(j, list) else [j]):
            tipos[x["l"]] = x["tipo"]
    except (ValueError, json.JSONDecodeError):
        pass
    letras = list(est.d["discos_antes"])
    res = []
    for k, l in enumerate(letras):
        t = tipos.get(l, "?")
        oque = "TRIM" if t == "SSD" else "desfragmentando"
        base = k / len(letras) * 100
        est.det(i, f"{l}: {oque}…", base)
        if a.seco:
            c, out = ps(f"defrag {l}: /A /U", 1800)
        else:
            try:
                p = subprocess.Popen(["defrag", f"{l}:", "/O", "/U", "/V"], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, creationflags=NO_WIN)
                buf = b""
                while True:
                    ch = p.stdout.read(64)
                    if not ch:
                        break
                    buf = (buf + ch)[-400:]
                    m = re.findall(rb"(\d{1,3})\s*%", buf)
                    if m:
                        est.det(i, f"{l}: {oque} {int(m[-1])}%", base + int(m[-1]) / len(letras))
                p.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                pass
        res.append(f"{l}: {'TRIM' if t == 'SSD' else 'ok'}")
    est.det(i, " · ".join(res), 100)


FUNC = {"preparar": e_preparar, "sensores": e_sensores, "limpeza": e_limpeza, "navegadores": e_navegadores,
        "kanivete": e_kanivete, "duplicados": e_duplicados, "virus": e_virus, "drivers": e_drivers,
        "reparo": e_reparo, "discos": e_discos}


def decisoes(est):
    """espera até 2 h as escolhas da aba para as ameaças (decisao.json) e aplica"""
    arq = est.caminho.parent / "decisao.json"
    fim = time.time() + 7200
    while time.time() < fim:
        if arq.exists():
            try:
                d = json.loads(arq.read_text("utf-8"))
                arq.unlink()
            except (OSError, ValueError):
                time.sleep(1)
                continue
            feitos = []
            for t in est.d["ameacas"]:
                ac = (d.get("ameacas") or {}).get(t["id"], "ignorar")
                if ac == "restaurar":
                    ps(f"Add-MpPreference -ThreatIDDefaultAction_Ids {int(t['id'])} -ThreatIDDefaultAction_Actions Allow", 60)
                    ps(f"& \"$env:ProgramFiles\\Windows Defender\\MpCmdRun.exe\" -Restore -Name '{t.get('nome', '')}'", 120)
                t["decisao"] = ac
                feitos.append(ac)
            if "remover" in feitos:
                ps("Remove-MpThreat -EA SilentlyContinue", 600)
            if d.get("offline"):
                est.d["situacao"] = "fim"
                est.gravar(True)
                ps("Start-MpWDOScan", 60)   # reinicia o PC e verifica antes do Windows subir
            est.d["situacao"] = "fim"
            est.log("decisões aplicadas: " + (", ".join(feitos) or "nenhuma"))
            est.gravar(True)
            return
        time.sleep(1)
    est.d["situacao"] = "fim"
    est.gravar(True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estado", required=True)
    ap.add_argument("--etapas", default=",".join(i for i, _ in ETAPAS))
    ap.add_argument("--completa", action="store_true")
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args()
    etapas = [e for e in a.etapas.split(",") if e in FUNC]
    est = Estado(a.estado, etapas, a.seco)
    parar = Path(a.estado).parent / "parar"
    parar.unlink(missing_ok=True)
    L = Limpador(est, a.seco)
    for i in etapas:
        if parar.exists():
            est.etapa(i)["estado"] = "pulada"
            continue
        e = est.etapa(i)
        e["estado"], e["t0"] = "rodando", time.time()
        est.d["agora"] = i
        est.gravar(True)
        try:
            FUNC[i](est, L, a)
            e["estado"] = "ok"
        except Exception as x:   # uma etapa que quebra não para as outras
            e["estado"], e["detalhe"] = "erro", f"{type(x).__name__}: {x}"[:200]
        e["progresso"], e["t1"] = 100, time.time()
        est.gravar(True)
    est.d["discos_depois"] = livres()
    est.d["agora"] = None
    est.d["fim"] = time.time()
    est.d["situacao"] = "decidir" if est.d["ameacas"] and not a.seco else "fim"
    est.gravar(True)
    if est.d["situacao"] == "decidir":
        decisoes(est)


if __name__ == "__main__":
    main()
