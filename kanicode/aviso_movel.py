"""Aviso no celular (Web Push): "terminei" e "preciso de você" chegam como notificação, mesmo com o KaniCode fechado lá.

Só quando a conversa foi puxada PELO CELULAR (a última mensagem veio de lá) e nenhuma tela do KaniCode está à vista no
celular — quem está no PC não recebe nada. O aviso passa pelo serviço de notificação do Google (é assim que o Android
entrega), cifrado de ponta a ponta com as chaves deste PC (VAPID, guardadas em DADOS/movel_push.json).
"""
import base64, json, os, threading, time

_dados = None
_trava = threading.Lock()
_vistos = {}            # celular (KC_DE) → tela à vista agora?
_turno_movel = False    # a última mensagem do Pailer saiu do celular
_texto = ""             # a resposta que está chegando (vira o corpo do aviso de "terminei")


def iniciar(dados):
    global _dados
    _dados = dados


def _arq():
    return os.path.join(_dados, "movel_push.json")


def _ler():
    try:
        with open(_arq(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _gravar(d):
    tmp = _arq() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _arq())


def chave_publica():
    """chave pública VAPID (base64url, formato que o navegador pede); gera o par na 1ª vez"""
    with _trava:
        d = _ler()
        if not d.get("publica"):
            from cryptography.hazmat.primitives import serialization
            from py_vapid import Vapid
            v = Vapid()
            v.generate_keys()
            pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            d["publica"] = base64.urlsafe_b64encode(pub).rstrip(b"=").decode()
            d["privada"] = v.private_pem().decode()
            d.setdefault("assinaturas", [])
            _gravar(d)
        return d["publica"]


def assinar(sub):
    with _trava:
        d = _ler()
        lista = [s for s in d.get("assinaturas", []) if s.get("endpoint") != sub.get("endpoint")]
        d["assinaturas"] = lista + [sub]
        _gravar(d)
    return True


def sair(endpoint):
    with _trava:
        d = _ler()
        d["assinaturas"] = [s for s in d.get("assinaturas", []) if s.get("endpoint") != endpoint]
        _gravar(d)
    return True


def visto(de, on):
    if on:
        _vistos[de] = True
    else:
        _vistos.pop(de, None)


def avisar(titulo, corpo, tag="kc"):
    """manda para todos os celulares assinados (numa thread: o Google pode demorar)"""
    def mandar():
        from pywebpush import WebPushException, webpush
        d = _ler()
        if not d.get("assinaturas"):
            return
        from py_vapid import Vapid
        vapid = Vapid.from_pem(d["privada"].encode())
        dados = json.dumps({"titulo": titulo, "corpo": corpo[:180], "tag": tag}, ensure_ascii=False)
        mortas = []
        for s in d["assinaturas"]:
            try:
                webpush(s, dados, vapid_private_key=vapid, vapid_claims={"sub": "mailto:kanicode@localhost"}, ttl=3600)
            except WebPushException as e:
                if e.response is not None and e.response.status_code in (404, 410):   # celular desinstalou/limpou
                    mortas.append(s.get("endpoint"))
            except Exception:
                pass
        for m in mortas:
            sair(m)
    threading.Thread(target=mandar, daemon=True).start()


def ver(ev):
    """cada evento da conversa passa por aqui (movel.publicar)"""
    global _turno_movel, _texto
    t = ev.get("t")
    if t == "eco_eu":
        _turno_movel = str(ev.get("de", "pc")) != "pc"
        _texto = ""
        return
    if t == "texto_novo":
        _texto = ""
    elif t == "texto":
        _texto += ev.get("d") or ""
    if not _turno_movel or any(_vistos.values()):
        return
    if t == "permissao":
        avisar("KaniCode precisa de você", "Posso fazer isto? " + str(ev.get("ferr") or ""), "kc-decisao")
    elif t == "pergunta":
        p = (ev.get("perguntas") or [{}])[0].get("question") or "Tenho uma pergunta para você."
        avisar("KaniCode tem uma pergunta", p, "kc-decisao")
    elif t == "fim":
        corpo = " ".join(_texto.replace("*", "").replace("`", "").split()) or "Pronto."
        avisar("KaniCode terminou", corpo, "kc-fim")
    elif t == "saiu" and ev.get("erro"):
        avisar("KaniCode parou com erro", str(ev.get("erro")), "kc-fim")
