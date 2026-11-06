"""Canal de comando pelo WhatsApp: o Pailer escreve no grupo KaniCode, o pedido vai para a aba Gerente do KaniCode
(kanicode/gerente.py), que faz, delega a outras abas e responde ali.

  py -3.13 wa_comando.py ouvir [--a-cada 60]        espera notificações; conferência de segurança até 60s
  py -3.13 wa_comando.py estado                     últimas etapas e falhas persistidas
  py -3.13 wa_comando.py pendentes                   mostra os pedidos novos e marca como lidos
  py -3.13 wa_comando.py responder --texto "..."     manda no grupo (wa.py põe a marca da Kani sozinho)

Regra anti-loop: vira pedido só o que aparece no grupo como "Eu" SEM a marca da Kani. Tudo que a Kani manda leva a marca 🟢 *KANI*:,
e o ouvinte ignora. Como a conta é a do Pailer, o WhatsApp mostra as duas coisas como "Eu": só a marca da Kani separa.
Arquivos em D:/kanivete_testes/wa_comando (estado.json, fila.jsonl, historico.jsonl, ouvinte.log).
Confirma a recepção antes do preparo. Áudios próprios novos são transcritos localmente antes de encaminhar. A primeira leitura (também na
migração de estado antigo) só marca histórico. Deduplica por ID, não pela transcrição. Falhas ficam no
log e não são reenviadas automaticamente; reenvie o áudio se necessário. Transcrever pode marcar ouvido.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import queue
import sqlite3
import threading
from contextlib import contextmanager

sys.stdout.reconfigure(encoding="utf-8")
AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = "D:/kanivete_testes/wa_comando"
GRUPO = "KaniCode"
MARCA = ("[KANI]", "🟢 *KANI*:", "🟢 KANI:", "KANI:", "*KANI*:")
TRAVA_ENVIO = threading.Lock()
LINHA = re.compile(r"^\[(\d{1,2}:\d{2})\] ([^:]+): (.*)$")
ESTADO = os.path.join(PASTA, "estado.json")       # chaves de mensagens já vistas
FILA = os.path.join(PASTA, "fila.jsonl")          # pedidos esperando o pendentes
HIST = os.path.join(PASTA, "historico.jsonl")     # pedidos já lidos
LOG = os.path.join(PASTA, "ouvinte.log")
AMB = {**os.environ, "PYTHONIOENCODING": "utf-8"}
MAX_VISTOS = 400
MAX_CONFERENCIA_SEG = 60


def intervalo_conferencia(segundos):
    return max(1, min(MAX_CONFERENCIA_SEG, segundos))


def log(msg):
    os.makedirs(PASTA, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%d/%m %H:%M:%S} {msg}\n")


def wa(*args, timeout=180):
    r = subprocess.run([sys.executable, os.path.join(AQUI, "wa.py"), *args, "--porta", "9333"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=AMB, timeout=timeout)
    if r.returncode:
        raise RuntimeError((r.stdout + r.stderr).strip()[-300:])
    return r.stdout


def mensagens(saida):
    """[(chave, quem, texto)] de cada linha '[HH:MM] Quem: texto' que o wa.py ler devolve."""
    out = []
    for linha in saida.splitlines():
        m = LINHA.match(linha.strip())
        if m:
            hora, quem, txt = m.group(1), m.group(2).strip(), m.group(3).strip()
            out.append((f"{hora}|{quem}|{txt}", quem, txt))
    return out


def da_kani(txt):
    """Marca da Kani mesmo com emoji virado em caractere invisível (U+FE0F, ZWJ) ou espaço na frente."""
    t = re.sub(r"^[\s\u200b-\u200f\u2060\ufe00-\ufe0f\U0001F7E0-\U0001F7EB]+", "", txt or "")
    return t.startswith(MARCA) or bool(re.match(r"^(\[KANI\]|\**KANI\**:)", t))


def e_pedido(quem, txt):
    return quem == "Eu" and bool(txt.strip()) and not da_kani(txt)


def carregar_vistos():
    if not os.path.isfile(ESTADO):
        return None
    return json.load(open(ESTADO, encoding="utf-8")).get("vistos", [])


def salvar_vistos(vistos):
    os.makedirs(PASTA, exist_ok=True)
    json.dump({"vistos": vistos[-MAX_VISTOS:]}, open(ESTADO, "w", encoding="utf-8"), ensure_ascii=False)


def registrar(texto):
    os.makedirs(PASTA, exist_ok=True)
    agora = datetime.datetime.now().isoformat(timespec="seconds")
    with open(FILA, "a", encoding="utf-8") as f:
        f.write(json.dumps({"quando": agora, "texto": texto}, ensure_ascii=False) + "\n")


def entregar_gerente(texto):
    """põe o pedido na fila da aba Gerente do KaniCode (cria a aba na 1ª vez); erro se o KaniCode não responder"""
    import socket
    with socket.create_connection(("127.0.0.1", 47613), timeout=5) as s:
        s.settimeout(30)
        orientacao = ('\n\n[Canal WhatsApp: a recepção já foi confirmada automaticamente. '
                      'Ao começar este pedido, avise no grupo KaniCode que começou. '
                      'Informe espera, falha e conclusão com o estado real; não repita a confirmação de recebimento.]')
        s.sendall(("gerente " + json.dumps({"acao": "entregar", "texto": texto + orientacao}, ensure_ascii=False) + chr(10)).encode("utf-8"))
        with s.makefile("r", encoding="utf-8") as entrada:
            r = json.loads(entrada.readline())
    if "erro" in r or not r.get("entregue"):
        raise RuntimeError(r.get("erro") or "a gerente não aceitou o pedido")
    return r


def responder(texto):
    # Avisos e resultados usam o mesmo editor; não podem digitar juntos.
    with TRAVA_ENVIO:
        return wa("enviar", "--conversa", GRUPO, "--texto", texto)


@contextmanager
def banco():
    os.makedirs(PASTA, exist_ok=True)
    con = sqlite3.connect(os.path.join(PASTA, 'recepcao.sqlite'), timeout=10)
    try:
        with con:
            con.execute('CREATE TABLE IF NOT EXISTS pedidos (id TEXT PRIMARY KEY, mensagem TEXT, estado TEXT, recebido REAL, detalhe TEXT)')
            yield con
    finally:
        con.close()


def etapa(mid, estado, detalhe=''):
    with banco() as con:
        con.execute('UPDATE pedidos SET estado=?, detalhe=? WHERE id=?', (estado, detalhe[:400], mid))
        r = con.execute('SELECT recebido FROM pedidos WHERE id=?', (mid,)).fetchone()
    log('etapa=' + estado + ' id=' + mid + ' decorrido=%.3fs ' % (time.time() - r[0] if r else 0) + detalhe[:200])


def guardar(m):
    with banco() as con:
        return bool(con.execute('INSERT OR IGNORE INTO pedidos VALUES (?,?,?,?,?)',
                    (m['id'], json.dumps(m, ensure_ascii=False), 'detectado', time.time(), '')).rowcount)


def avisar(texto, mid):
    inicio = time.monotonic()
    try:
        responder(texto)
        log('aviso id=' + mid + ' duracao=%.3fs' % (time.monotonic() - inicio))
    except Exception as e:
        log('aviso não confirmado id=' + mid + ': ' + str(e)[:150])


def confirmar_recebimento(m):
    # Persiste antes do envio: uma interrupção não repete o aviso automaticamente.
    etapa(m['id'], 'avisando')
    avisar('Estou ouvindo seu áudio!' if m.get('audio') else 'Recebi seu pedido.', m['id'])
    etapa(m['id'], 'recebido')


def processar(m):
    mid = m['id']
    etapa(mid, 'processando')
    try:
        inicio = time.monotonic()
        txt = pedido_mensagem(m)
        log('preparo id=' + mid + ' duracao=%.3fs' % (time.monotonic() - inicio))
        if not txt:
            etapa(mid, 'ignorado')
            return
        registrar(txt)
        etapa(mid, 'encaminhando')
        r = entregar_gerente(txt)
        etapa(mid, 'encaminhado', 'aba=' + str(r.get('aba')))
        avisar('Pedido encaminhado à gerente. Ela avisa aqui quando começar.', mid)
    except Exception as e:
        etapa(mid, 'falhou', str(e))
        avisar('Não consegui concluir o encaminhamento do pedido. Vou precisar que você confira ou reenvie.', mid)


def receber(dados, vistos, primeira, avisos):
    if dados.get('conversa') != GRUPO:
        raise RuntimeError('Conversa retornada diferente do grupo de comandos.')
    novas = []
    for m in dados.get('mensagens', []):
        if not m.get('id') or 'msg:' + m['id'] in vistos:
            continue
        vistos.append('msg:' + m['id'])
        if not primeira and m.get('quem') == 'Eu' and (m.get('audio') or e_pedido('Eu', m.get('txt') or '')):
            if not da_kani(m.get('txt') or ''):
                novas.append(m)
    # O banco mantém os trabalhos mesmo se o processo cair depois da recepção.
    for m in novas:
        if guardar(m):
            avisos.put(m)
            etapa(m['id'], 'detectado')
    salvar_vistos(vistos)
    return False


def ler_eventos(confirmados, conferir=False):
    from kb import chamar
    r = chamar(9333, 'scripts_browser', {'acao': 'rodar', 'nome': 'whatsapp_eventos',
               'dados': {'confirmados': confirmados, 'conferir': conferir}}, onde='kanicode', timeout=15)
    return r['resultado']


def ouvir(a_cada):
    os.makedirs(PASTA, exist_ok=True)
    # Um receptor por grupo; evita dois processos enviando os mesmos avisos.
    import msvcrt
    trava = open(os.path.join(PASTA, 'ouvinte.lock'), 'a+b')
    trava.seek(0)
    if not trava.read(1):
        trava.write(b'1'); trava.flush()
    trava.seek(0)
    try:
        msvcrt.locking(trava.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        trava.close()
        raise RuntimeError('Ja existe um ouvinte ativo para este grupo.')
    avisos, trabalhos = queue.Queue(), queue.Queue()
    parar = threading.Event()
    def trabalhador(fila, funcao, proxima=None):
        while not parar.is_set():
            try:
                m = fila.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                funcao(m)
                if proxima is not None:
                    proxima.put(m)
            except Exception as e:
                log('erro trabalhador: ' + str(e)[:200])
            finally:
                fila.task_done()
    with banco() as con:
        antigos = con.execute('SELECT mensagem, estado FROM pedidos WHERE estado IN (?,?,?,?,?)',
                              ('detectado', 'avisando', 'recebido', 'processando', 'encaminhando')).fetchall()
    for mensagem, estado in antigos:
        m = json.loads(mensagem)
        if da_kani(m.get('txt') or ''):
            etapa(m['id'], 'ignorado', 'Resposta propria; nao e pedido.')
            continue
        if estado == 'detectado':
            avisos.put(m)
        elif estado in ('avisando', 'recebido'):
            trabalhos.put(m)
        else:
            etapa(m['id'], 'incerto', 'Interrompido; conferir antes de reenviar, sem repeticao automatica.')
    for fila, funcao, proxima in ((avisos, confirmar_recebimento, trabalhos), (trabalhos, processar, None)):
        threading.Thread(target=trabalhador, args=(fila, funcao, proxima), daemon=True).start()
    vistos = carregar_vistos()
    primeira = True  # Cada partida marca o DOM carregado como histórico; trabalhos persistidos são retomados acima.
    vistos = list(vistos or [])
    confirmados, ultima_conferencia = [], 0
    a_cada = intervalo_conferencia(a_cada)
    log('ouvindo grupo ' + GRUPO + ' por notificacao; conferencia %.1fs' % a_cada)
    try:
        while True:
            inicio = time.monotonic()
            try:
                conferir = inicio - ultima_conferencia > 15
                try:
                    dados = ler_eventos(confirmados, conferir)
                    if conferir:
                        ultima_conferencia = inicio
                except Exception as e:
                    log('reserva leitura: ' + str(e)[:120])
                    dados = json.loads(wa('ler', '--conversa', GRUPO, '--n', '12', '--json'))
                primeira = receber(dados, vistos, primeira or dados.get('reiniciado', False), avisos)
                confirmados = [m['id'] for m in dados.get('mensagens', []) if m.get('id')]
                log('recepcao fonte=' + dados.get('fonte', 'reserva') + ' duracao=%.3fs' % (time.monotonic() - inicio))
            except Exception as e:
                log('erro recepcao: ' + str(e)[:200])
            try:
                aguardar_eventos(confirmados, a_cada)
            except Exception as e:
                log('espera indisponivel: ' + str(e)[:120])
                parar.wait(a_cada)
    finally:
        parar.set()
        trava.close()


def aguardar_eventos(confirmados, segundos):
    """Espera resolvida no navegador; não segura a trava dos trabalhos da Kani."""
    from kb import chamar
    codigo = """(async () => {
      if (location.origin !== 'https://web.whatsapp.com' ||
          (document.querySelector('#main header')?.innerText || '').split('\\n')[0].trim() !== 'KaniCode')
        throw new Error('Abra o grupo KaniCode.');
      const e = globalThis.__kbWaEventos;
      if (e?.versao !== 3) throw new Error('Observador indisponivel.');
      return await e.esperar(%s, %s);
    })()""" % (json.dumps(confirmados), int(intervalo_conferencia(segundos) * 1000))
    return chamar(9333, 'js_kani', {'codigo': codigo}, onde='kanicode', timeout=70)


def pedido_mensagem(m):
    """Somente mensagens próprias; transcrição nunca altera a chave de deduplicação."""
    if m.get("quem") != "Eu":
        return None
    txt = (m.get("txt") or "").strip()
    if da_kani(txt):
        return None
    if m.get("audio"):
        r = json.loads(wa("ler", "--conversa", GRUPO, "--audio-id", m["id"], timeout=600))
        txt = (r.get("texto") or "").strip()
        if r.get("id") != m["id"] or not txt or txt == "(sem fala)" or txt.startswith("(não transcrevi:"):
            raise RuntimeError("Transcrição inválida; pedido não encaminhado.")
        if da_kani(txt):
            return None
        return "Pedido por áudio do Pailer (transcrição automática; confirme ambiguidades antes de agir):\n" + txt
    return txt if e_pedido("Eu", txt) else None


def pendentes():
    if not os.path.isfile(FILA) or not os.path.getsize(FILA):
        print("nenhum pedido novo")
        return
    pedidos = [json.loads(x) for x in open(FILA, encoding="utf-8") if x.strip()]
    for p in pedidos:
        print(f"[{p['quando']}] {p['texto']}")
    with open(HIST, "a", encoding="utf-8") as f:
        f.write(open(FILA, encoding="utf-8").read())
    os.remove(FILA)


def estado_recepcao():
    with banco() as con:
        linhas = con.execute('SELECT id, estado, recebido, detalhe FROM pedidos ORDER BY recebido DESC LIMIT 20').fetchall()
    return [{'id': mid, 'estado': estado, 'recebido': datetime.datetime.fromtimestamp(quando).isoformat(),
             'detalhe': detalhe} for mid, estado, quando, detalhe in linhas]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["ouvir", "pendentes", "responder", "estado"])
    ap.add_argument("--a-cada", type=float, default=MAX_CONFERENCIA_SEG)
    ap.add_argument("--texto", default="")
    a = ap.parse_args()
    if a.acao == "ouvir":
        ouvir(a.a_cada)
    elif a.acao == "pendentes":
        pendentes()
    elif a.acao == "estado":
        print(json.dumps(estado_recepcao(), ensure_ascii=False, indent=2))
    else:
        if not a.texto.strip():
            sys.exit("responder precisa de --texto")
        print(responder(a.texto).strip())


if __name__ == "__main__":
    main()
