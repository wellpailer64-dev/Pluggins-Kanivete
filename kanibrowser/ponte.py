"""Ponte do KaniBrowser com o KANIVETE (Functions/plugins_pessoais.py só chama o que está em API_KANIVETE)."""
import os, subprocess

import kanibrowser as kb
import favoritos as fav
import visao

API_KANIVETE = ("estado", "abrir", "fechar_navegador", "abas", "ir", "nova", "fechar", "frente", "foto", "texto",
                "imagens", "destinos", "baixar_imagens", "abrir_pasta", "visitar", "instagram", "baixar_link", "pesquisar", "ler_pagina",
                "ajustar", "entrada", "escolher", "dialogo", "arquivo", "navegar", "ponto", "kani_ir", "abrir_downloads",
                "favoritos", "favorito", "favorito_remover", "favorito_renomear", "favoritos_ordem", "chatgpt", "diagnostico_chatgpt", "js_kani", "kani_parar", "vista", "clicar_texto")


def vista(aba=None):
    """print pequeno (JPEG) da aba da Kani depois de uma ação do agente: o caminho sai no kb.py e o KaniCode mostra na
    conversa (PC e celular). Guarda os 40 últimos em <RAIZ>/prints."""
    import base64, time
    tid = aba or kb._k.get("aba")
    if not tid or not kb.ativo():
        return None
    try:
        dados = kb._cdp(tid, "Page.captureScreenshot", {"format": "jpeg", "quality": 60}, timeout=20)["data"]
    except kb.ErroKB:
        return None
    pasta = os.path.join(kb.RAIZ, "prints")
    os.makedirs(pasta, exist_ok=True)
    velhos = sorted(os.listdir(pasta))
    for v in velhos[:-39]:
        try:
            os.remove(os.path.join(pasta, v))
        except OSError:
            pass
    cam = os.path.join(pasta, time.strftime("tela_%Y%m%d_%H%M%S.jpg"))
    with open(cam, "wb") as f:
        f.write(base64.b64decode(dados))
    return cam


def kani_parar():
    """interrompe a espera do trabalho da Kani (ex.: resposta do ChatGPT)"""
    kb._k["cancelar"] = True
    return True


def clicar_texto(texto, aba=None):
    """a Kani do KaniCode clica num botão/link pelo texto visível, na aba que o Pailer está vendo (só clique, sem script livre)"""
    import json
    cod = """(q => { q = q.toLowerCase(); const vis = e => e.offsetParent !== null;
      const els = [...document.querySelectorAll('button, a, [role=button], [role=link], input[type=submit], input[type=button]')].filter(vis);
      const b = els.find(e => (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().toLowerCase() === q)
             || els.find(e => (e.innerText || e.value || e.getAttribute('aria-label') || '').toLowerCase().includes(q));
      if (!b) return 'não achei "' + q + '". Botões: ' + els.map(e => (e.innerText || e.getAttribute('aria-label') || '').trim()).filter(Boolean).slice(0, 25).join(' | ');
      b.click(); return 'cliquei em: ' + (b.innerText || b.value || b.getAttribute('aria-label')).trim(); })(""" + json.dumps(str(texto)) + ")"
    return kb.js(cod, aba)


def js_kani(codigo):
    """ferramenta de quem desenvolve o plugin (kb.py/agente): roda JavaScript na aba da Kani e devolve o valor"""
    return kb.js(codigo, kb.aba_kani())


def diagnostico_chatgpt():
    return kb.diagnostico_chatgpt()


def chatgpt(pergunta, nova=True, pasta=None):
    """a Kani (ou o agente) pergunta ao ChatGPT na conta do Pailer; devolve {texto, imagens, url}"""
    return kb.chatgpt(pergunta, nova, pasta)


def favoritos():
    return fav.listar()


def favorito(url, nome=None):
    return fav.salvar(url, nome)


def favorito_remover(url):
    return fav.remover(url)


def favorito_renomear(url, nome):
    return fav.renomear(url, nome)


def favoritos_ordem(urls):
    return fav.ordenar(urls)


def estado(vistas=()):
    """tudo que o painel mostra: abas do Pailer, aba da Kani, o que ela faz, e das abas à vista endereço/avisos"""
    return visao.estado(vistas)


def ajustar(aba, w, h, dpr=1.0):
    return visao.ajustar(aba, w, h, dpr)


def entrada(aba, eventos):
    return visao.entrada(aba, eventos)


def escolher(aba, indice):
    return visao.escolher(aba, indice)


def dialogo(aba, aceitar=True, texto=None):
    return visao.dialogo(aba, aceitar, texto)


def arquivo(aba, caminhos=()):
    return visao.arquivo(aba, caminhos)


def navegar(aba, acao):
    return visao.navegar(aba, acao)


def ponto(aba, x, y):
    return visao.ponto(aba, x, y)


def kani_ir(url):
    """o Pailer manda a Kani abrir um endereço na aba dela"""
    if not kb.ativo():
        kb.abrir()
    with kb.trabalho("Abrindo " + url):
        return kb.ir(url, kb.aba_kani())


def abrir_downloads():
    return abrir_pasta(kb.SAIDA)



def abrir(url=None):
    return kb.abrir(url)


def fechar_navegador():
    return kb.fechar_navegador()


def abas():
    return kb.abas()


def visitar(url, aba=None, mesma_aba=False):
    """o "Ir" do painel: abre o navegador se estiver fechado; senão usa a aba (mesma_aba) ou abre uma nova.
    Devolve o id da aba e traz a janela para a frente."""
    if not kb.ativo():
        kb.abrir(url)
        aba = kb.abas_usuario()[0]["id"]
    elif mesma_aba and aba and any(t["id"] == aba for t in kb.abas()):
        kb.ir(url, aba)
    else:
        aba = kb.nova(url)["id"]
    kb.frente(aba)
    return aba


def ir(url, aba=None):
    return kb.ir(url, aba)


def nova(url):
    return kb.nova(url)


def fechar(aba):
    return kb.fechar(aba)


def frente(aba=None):
    return kb.frente(aba)


def foto(aba=None, caminho=None, inteira=False):
    return kb.foto(aba, caminho, inteira)


def texto(aba=None):
    return kb.texto(aba)


def imagens(aba=None, minimo=250):
    return kb.imagens(aba, minimo)


def destinos():
    return kb.destinos()


def baixar_imagens(urls, demanda=None, pasta=None, aba=None):
    """demanda = id (ou começo) de uma demanda com pasta → <demanda>/02 - ASSETS/REFERENCIAS; senão `pasta`."""
    if demanda:
        d = next((d for d in kb.destinos() if d["id"].startswith(demanda)), None)
        if not d:
            raise kb.ErroKB("Essa demanda ainda não tem pasta (baixe pelo Pandalab primeiro).")
        pasta = kb.pasta_referencias(d["pasta"])
    ref = None
    try:
        ref = next((t["url"] for t in kb.abas() if not aba or t["id"].startswith(aba)), None)
    except kb.ErroKB:
        pass
    return kb.baixar(urls, pasta, referer=ref)


def abrir_pasta(pasta):
    if not os.path.isdir(pasta):
        raise kb.ErroKB("Pasta não encontrada.")
    subprocess.Popen(["explorer", pasta])
    return pasta


def _destino(demanda=None, pasta=None, sub="REFERENCIAS"):
    if demanda:
        d = next((d for d in kb.destinos() if d["id"].startswith(demanda)), None)
        if not d:
            raise kb.ErroKB("Essa demanda ainda não tem pasta (baixe pelo Pandalab primeiro).")
        return os.path.join(d["pasta"], "02 - ASSETS", sub)
    return pasta or kb.SAIDA


def instagram(usuario, aba=None):
    return kb.instagram(usuario, aba)


def baixar_link(url, demanda=None, pasta=None):
    """material do cliente (Drive, WeTransfer...) → 02 - ASSETS/MATERIAL da demanda"""
    return kb.baixar_link(url, _destino(demanda, pasta, "MATERIAL"))


def pesquisar(termo, n=3):
    return kb.pesquisar(termo, n)


def ler_pagina(url, limite=6000):
    return kb.ler_pagina(url, limite)
