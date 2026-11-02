"""WhatsApp em um comando, gastando pouco contexto.
    py -3.13 wa_tarefas.py resumo --conversa "Alessandro" [--n 40]
        lê, transcreve áudios e a Kani local devolve só pedidos, pendências e arquivos; texto completo fica em arquivo no D
    py -3.13 wa_tarefas.py assistir --conversa "Alessandro" --pasta P (--nome parte | --duracao 1:10) [--inicio S --fim S]
        baixa o vídeo (arquivo pelo nome; vídeo comum pela duração) e devolve folha com tempos e transcrição
    py -3.13 wa_tarefas.py assistir --arquivo video.mp4       só assistir um vídeo que já está no disco
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
AQUI = os.path.dirname(os.path.abspath(__file__))
KANICODE = os.path.join(os.path.dirname(AQUI), "kanicode")
SAIDA = r"D:\kanivete_testes\wa"
ap = argparse.ArgumentParser()
ap.add_argument("acao", choices=["resumo", "assistir"])
ap.add_argument("--conversa", default="")
ap.add_argument("--n", default="40")
ap.add_argument("--pasta", default="")
ap.add_argument("--nome", default="")
ap.add_argument("--duracao", default="")
ap.add_argument("--arquivo", default="")
ap.add_argument("--inicio", default="")
ap.add_argument("--fim", default="")
a = ap.parse_args()
AMB = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def wa(*args):
    r = subprocess.run([sys.executable, os.path.join(AQUI, "wa.py"), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=AMB)
    for _ in range(2):   # navegador demorou: costuma passar na segunda
        if "demorou" not in r.stdout + r.stderr:
            break
        time.sleep(3)
        r = subprocess.run([sys.executable, os.path.join(AQUI, "wa.py"), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=AMB)
    if r.returncode:
        sys.exit("wa.py falhou: " + (r.stdout + r.stderr).strip()[-300:])
    return r.stdout.strip()


def resumo():
    texto = wa("ler", "--conversa", a.conversa, "--n", a.n, "--transcrever")
    os.makedirs(SAIDA, exist_ok=True)
    arq = os.path.join(SAIDA, re.sub(r"\W+", "_", a.conversa) + "_" + time.strftime("%Y%m%d_%H%M") + ".txt")
    open(arq, "w", encoding="utf-8").write(texto)
    arquivos = [x for x in texto.splitlines() if re.search(r"\b(MP4|PDF|ZIP|arquivo|\[imagem\]|\[v[íi]deo\])", x)]
    print("Completo:", arq)
    print("Arquivos e mídia citados:")
    for x in arquivos[-12:]:
        print(" ", x[:110])
    sys.path.insert(0, KANICODE)
    import ajudantes
    pedido = ("Resuma esta conversa de WhatsApp para quem vai executar o trabalho. 'Eu' é o Pailer. Em até 8 linhas: "
              "o que foi pedido, o que está pendente e com quem, prazos e valores citados. Use só o que está escrito; não invente.")
    for tam in (14000, 6000):
        try:
            r = ajudantes.kani(pedido, texto[-tam:])
            if r.get("ok", True) and r["texto"].strip() and "WinError" not in r["texto"]:
                print("Resumo da Kani (conferir no completo antes de agir em valor, prazo ou nome):")
                print(r["texto"].strip())
                return
        except Exception:  # Kani fora do ar não pode deixar o pedido sem resposta
            pass
    print("Kani indisponível. Últimas mensagens, encurtadas:")
    for x in texto.splitlines()[-10:]:
        print(" ", x[:240])


def duracao(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip() or 0)


def assistir():
    arq = a.arquivo
    if not arq:
        if not a.pasta:
            sys.exit("--pasta é obrigatório para baixar: arquivo vai para a pasta do cliente")
        antes = {f: os.path.getmtime(os.path.join(a.pasta, f)) for f in os.listdir(a.pasta)} if os.path.isdir(a.pasta) else {}
        if a.duracao:
            os.makedirs(a.pasta, exist_ok=True)
            nome = os.path.join(a.pasta, "video_" + a.duracao.replace(":", "m") + ".mp4")
            wa("midia", "--conversa", a.conversa, "--tipo", "video", "--duracao", a.duracao, "--saida", nome)
            arq = nome
        else:
            saida = wa("arquivo", "--conversa", a.conversa, "--nome", a.nome, "--pasta", a.pasta)
            arq = saida.strip().splitlines()[-1].strip()
        if not os.path.isfile(arq):
            novos = [f for f in os.listdir(a.pasta) if os.path.getmtime(os.path.join(a.pasta, f)) != antes.get(f)]
            if not novos:
                sys.exit("não baixou: " + arq[:200])
            arq = os.path.join(a.pasta, novos[-1])
    ini, fim = float(a.inicio or 0), float(a.fim or duracao(arq))
    # em cenas, fala parada vira 1 quadro só; uniforme garante um quadro a cada 3 s, no máximo 40
    qtd = max(6, min(40, int((fim - ini) / 3)))
    cmd = [sys.executable, os.path.join(KANICODE, "video_download.py"), "analisar", "--arquivo", arq, "--metodo", "uniforme", "--quantidade", str(qtd)]
    if a.inicio or a.fim:
        cmd += ["--inicio", str(ini), "--fim", str(fim)]
    d = json.loads(subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=AMB).stdout)
    print("Vídeo:", arq)
    print("Duração:", round(d["duracao"], 1), "s | quadros:", qtd)
    print("Folha:", d["folha"])
    print("Leitura:", d["leitura"])
    t = open(d["leitura"], encoding="utf-8").read()
    print(t[t.find("## Fala transcrita"):][:6000])


{"resumo": resumo, "assistir": assistir}[a.acao]()
