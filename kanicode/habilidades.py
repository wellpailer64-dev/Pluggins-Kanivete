"""Habilidades da Kani: o mapa de tudo que dá para fazer no KANIVETE, consultado na hora (como um livro de receitas).

De onde vem: os menus de cada ferramenta são lidos do app aberto (só leitura, sem clicar) — Photo (IE_MENUS → ieCmd),
Vídeo (VE_CMDS), Vetor (VK_MENUS), Slider (sdItensMenu), Lux (luxItensMenu) — mais os botões com nome de cada página
(painéis, ferramentas). Por cima, habilidades_extra.json acrescenta frases do jeito que o Pailer fala e as habilidades
com parâmetro (documento novo, escrever texto...).

Uso: buscar(pedido) → as que parecem servir (o modo Kani já põe as 5 melhores no pedido); executar(id) → roda no app.
Coletar de novo: py -3.13 habilidades.py --coletar  (sozinho: quando o arquivo some ou fica com mais de 3 dias)."""
import json
import math
import os
import re
import sys
import time
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
from dados_app import pasta_dados
DADOS = str(pasta_dados())   # o mesmo de kani_modo
ARQ = os.path.join(DADOS, "habilidades.json")
EXTRA = os.path.join(AQUI, "habilidades_extra.json")
VALIDADE = 3 * 86400

FERR = {"editor-imagem": "Photo", "video-cutter": "Vídeo", "vetor-kanivete": "Vetor", "slider-kanivete": "Slider",
        "lux-kanivete": "Lux", "sound-kanivete": "Sound", "kanivete-encoder": "Encoder", "ata-kanivete": "Ata"}
_NOMES = {"photo": "editor-imagem", "foto": "editor-imagem", "imagem": "editor-imagem", "photoshop": "editor-imagem",
          "video": "video-cutter", "editor": "video-cutter", "premiere": "video-cutter", "timeline": "video-cutter",
          "vetor": "vetor-kanivete", "illustrator": "vetor-kanivete", "slider": "slider-kanivete", "slide": "slider-kanivete",
          "apresentacao": "slider-kanivete", "powerpoint": "slider-kanivete", "lux": "lux-kanivete", "3d": "lux-kanivete",
          "sound": "sound-kanivete", "som": "sound-kanivete", "audio": "sound-kanivete", "encoder": "kanivete-encoder",
          "ata": "ata-kanivete"}

# ── coleta (no app, só leitura) ──
JS_COLETAR = r"""() => {
  const out = [], limpa = s => String(s || '').replace(/\s+/g, ' ').trim();
  const add = (f, tipo, menu, rotulo, atalho, chave) => { rotulo = limpa(rotulo); if (rotulo && rotulo !== '-' && !rotulo.startsWith('—'))
    out.push({ f, tipo, menu: limpa(menu), rotulo, atalho: limpa(atalho), chave: chave == null ? rotulo : chave }); };
  try { const anda = (f, itens, menu) => (itens || []).forEach(it => { if (!Array.isArray(it)) return;
      if (Array.isArray(it[1])) anda(f, it[1], menu + ' › ' + it[0]); else if (typeof it[1] === 'string') add(f, 'ie', menu, it[0], it[2], it[1]); });
    IE_MENUS.forEach(m => anda('editor-imagem', Array.isArray(m[1]) && m[1].length ? m[1] : (typeof m[2] === 'function' ? (() => { try { return m[2](); } catch (e) { return []; } })() : []), m[0]));
  } catch (e) {}
  try { const g = Object.fromEntries(VE_MENUS); VE_CMDS.forEach(c => add('video-cutter', 've', g[c.grupo] || c.grupo, c.nome, (c.teclas || [])[0], c.id)); } catch (e) {}
  try { VK_MENUS.forEach(m => (m[1] || []).forEach(it => Array.isArray(it) && add('vetor-kanivete', 'vk', m[0], it[0], it[1], m[0] + '|' + it[0]))); } catch (e) {}
  try { [...document.querySelectorAll('#page-slider-kanivete [data-menu]')].map(b => [b.dataset.menu, b.innerText]).forEach(([k, n]) => {
      try { sdItensMenu(k).forEach(it => it[0] && add('slider-kanivete', 'sd', n || k, it[0], it[1], k + '|' + it[0])); } catch (e) {} }); } catch (e) {}
  try { LUX_MENUS.forEach(([k, n]) => { try { luxItensMenu(k).forEach(it => it[0] && it[0] !== '#' && add('lux-kanivete', 'lux', n, it[0], it[1], k + '|' + it[0])); } catch (e) {} }); } catch (e) {}
  try { VED.ids.forEach(id => add('video-cutter', 'vedpainel', 'Janela › Painéis', 'Painel ' + vedTitle(id), '', id)); } catch (e) {}
  // comandos de agente com descrição (os mesmos da API: args no texto entre chaves)
  try { Object.entries(VK_CMDS).forEach(([k, v]) => v.desc && add('vetor-kanivete', 'vkcmd', 'comando', v.desc, '', k)); } catch (e) {}
  try { Object.entries(SD_CMDS).forEach(([k, v]) => v.desc && add('slider-kanivete', 'sdcmd', 'comando', v.desc, '', k)); } catch (e) {}
  // botões com nome dentro de cada página (painéis, ferramentas, cabeçalhos): clicar pelo texto/título
  for (const f of Object.keys(FERR)) { const pg = document.getElementById('page-' + f); if (!pg) continue; const vistos = new Set();
    pg.querySelectorAll('button, [role=button], .tab-btn, [data-tool]').forEach(b => { const t = limpa(b.getAttribute('title') || b.getAttribute('aria-label') || b.innerText);
      if (!t || t.length < 3 || t.length > 60 || vistos.has(t) || /^[\d\s.,:%×x+−-]+$/.test(t)) return; vistos.add(t); add(f, 'botao', 'botão', t, '', t); }); }
  return out;
}""".replace("FERR", json.dumps(FERR))

# executar: troca para a ferramenta e roda o comando pelo mesmo caminho do menu
JS_EXECUTAR = r"""async h => {
  const espera = ms => new Promise(r => setTimeout(r, ms));
  if (h.f && typeof switchTool === 'function' && !document.querySelector('#page-' + h.f + '.active')) { switchTool(h.f); await espera(500); }
  const vis = e => e && e.offsetParent !== null;
  try {
    if (h.tipo === 'ie') { if (typeof ieCmdPode === 'function' && !ieCmdPode(h.chave)) return 'NÃO FEITO: "' + h.rotulo + '" está desligado agora (precisa de documento aberto, camada ou seleção).';
      ieCmd(h.chave); }
    else if (h.tipo === 've') { const c = VE_CMD[h.chave]; if (!c) return 'ERRO: comando sumiu do Vídeo';
      if (!c.sempre && !VE.ready) return 'NÃO FEITO: abra um projeto no Vídeo antes.'; if (c.pode && !c.pode()) return 'NÃO FEITO: "' + h.rotulo + '" está desligado agora.'; c.fn(); }
    else if (h.tipo === 'vedpainel') { if (!VE.ready) return 'NÃO FEITO: abra um projeto no Vídeo antes.'; vedShow(h.chave); }
    else if (h.tipo === 'vk') { const [m, r] = h.chave.split('|'); const it = VK_MENUS.find(x => x[0] === m)[1].find(x => Array.isArray(x) && x[0] === r);
      if (!VK.doc && !/Novo|Abrir/.test(r)) return 'NÃO FEITO: abra um documento no Vetor antes.'; it[2](); }
    else if (h.tipo === 'sd') { const [m, r] = h.chave.split('|'); const it = sdItensMenu(m).find(x => x[0] === r); if (!it) return 'ERRO: item sumiu do Slider';
      if (it[3]) return 'NÃO FEITO: "' + r + '" está desligado agora.'; it[2](); }
    else if (h.tipo === 'lux') { const [m, r] = h.chave.split('|'); const it = luxItensMenu(m).find(x => x[0] === r); if (!it) return 'ERRO: item sumiu da Lux';
      if (it[3]) return 'NÃO FEITO: "' + r + '" está desligado agora.'; it[2](); }
    else if (h.tipo === 'botao') { const pg = document.getElementById('page-' + h.f);
      const b = [...pg.querySelectorAll('button, [role=button], .tab-btn, [data-tool]')].filter(vis).find(b =>
        (b.getAttribute('title') || b.getAttribute('aria-label') || b.innerText || '').replace(/\s+/g, ' ').trim() === h.chave);
      if (!b) return 'NÃO FEITO: o botão "' + h.chave + '" não está à vista agora (abra o painel ou o projeto antes).'; if (b.disabled) return 'NÃO FEITO: o botão "' + h.chave + '" está desligado.'; b.click(); }
    else if (h.tipo === 'vkcmd' || h.tipo === 'sdcmd') { const r = h.tipo === 'vkcmd' ? await VKN.cmd(h.chave, h.args || {}, 'kani') : await SDK.cmd(h.chave, h.args || {});
      const t = typeof r === 'string' ? r : JSON.stringify(r); return (r && r.erro ? 'ERRO: ' : 'FEITO: ') + h.rotulo + ' → ' + String(t).slice(0, 600); }
    else if (h.tipo === 'js') { const fn = eval('(' + h.js + ')'); const r = await fn(h.args || {}); return String(r); }
    else return 'ERRO: tipo desconhecido ' + h.tipo;
  } catch (e) { return 'ERRO: ' + (e.message || e); }
  await espera(700);
  return 'FEITO: ' + (h.menu && h.menu !== 'botão' ? h.menu + ' › ' : '') + h.rotulo + '.';
}"""

# ── texto: normalizar, raiz curta, sinônimos ──
_PARE = set("a o as os de da do das dos e em no na nos nas um uma uns umas para pra pro por com que se me mim eu voce você "
            "isso esse essa este esta ali aqui la lá ai aí ele ela favor por-favor consegue consegues pode poderia quero queria "
            "gostaria preciso faz faca faça fazer abre abra coloca coloque deixa deixe dentro kanivete kani tambem também agora "
            "nao não sim ok entao então ja já bem muito mais menos meu minha seu sua tudo todo toda".split())
_SINON = {"criar": "novo", "cria": "novo", "crie": "novo", "nova": "novo", "novo": "novo", "inicia": "novo", "iniciar": "novo",
          "comecar": "novo", "comeco": "inicio", "inicial": "inicio", "documento": "documento", "arquivo": "documento", "projeto": "documento", "doc": "documento",
          "excluir": "apagar", "deletar": "apagar", "remover": "apagar", "tirar": "apagar", "apaga": "apagar",
          "desfaz": "desfazer", "voltar": "desfazer", "volta": "desfazer", "refaz": "refazer",
          "gravar": "salvar", "salva": "salvar", "guardar": "salvar", "exporta": "exportar", "renderizar": "exportar",
          "render": "exportar", "escrever": "texto", "escreva": "texto", "escreve": "texto", "palavra": "texto", "frase": "texto",
          "letra": "texto", "titulo": "texto", "duplicar": "duplicar", "copia": "copiar", "cola": "colar",
          "cortar": "cortar", "corta": "cortar", "dividir": "cortar", "picotar": "cortar", "aumentar": "zoom", "ampliar": "zoom",
          "imagem": "imagem", "foto": "imagem", "figura": "imagem", "girar": "girar", "rodar": "girar", "virar": "girar",
          "espelhar": "espelhar", "inverter": "espelhar", "camadas": "camada", "layer": "camada", "fechar": "fechar",
          "fecha": "fechar", "abrir": "abrir", "abre": "abrir", "efeitos": "efeito", "filtro": "filtro", "filtros": "filtro",
          "legendas": "legenda", "marcador": "marcador", "marcadores": "marcador", "painel": "janela", "paineis": "janela",
          "musica": "som", "audio": "som", "volume": "som"}


def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s).lower()) if unicodedata.category(c) != "Mn")


def termos(s):
    out = []
    for p in re.findall(r"[a-z0-9]+", _sem_acento(s)):
        if p in _PARE or len(p) < 2:
            continue
        p = _SINON.get(p, p)
        out.append(p[:5] if len(p) > 5 else p)   # raiz curta: "documentos" ≈ "documento", "seleção" ≈ "selecionar"
    return out


# ── índice ──
_cache = {"t": 0, "hab": None, "idf": None}


def _extra():
    try:
        with open(EXTRA, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"frases": {}, "habilidades": []}


def _ident(h):
    sig = FERR.get(h["f"], h["f"]).lower().replace("í", "i")
    if h["tipo"] in ("vkcmd", "sdcmd"):
        return f"{sig}:comando {h['chave']}"
    return f"{sig}:{h['menu']} › {h['rotulo']}" if h["tipo"] != "botao" else f"{sig}:botão › {h['rotulo']}"


def montar(coletados):
    """coletados (do app) + extras → lista de habilidades com id e texto de busca"""
    ex, vistos, hab = _extra(), set(), []
    for h in ex.get("habilidades", []):   # as feitas à mão vêm primeiro (ganham no empate)
        h = dict(h, tipo=h.get("tipo", "js"))
        h.setdefault("rotulo", h["id"].split(":", 1)[-1])
        vistos.add(h["id"])
        hab.append(h)
    for h in coletados:
        h = dict(h)
        h["id"] = _ident(h)
        if h["id"] in vistos:
            continue
        vistos.add(h["id"])
        hab.append(h)
    for h in hab:
        frases = " ".join(ex.get("frases", {}).get(h["id"], []))
        h["busca"] = " ".join([h.get("rotulo", ""), h.get("menu", "") if h.get("tipo") != "botao" else "",
                               h.get("desc", ""), h.get("busca_extra", ""), frases, h.get("rotulo", "")])   # rótulo conta 2×
    return hab


def coletar(visitar=False):
    """visitar=True abre cada ferramenta antes (Slider, Sound, Lux... só montam a página ao abrir): SÓ no app de teste"""
    import kani_modo
    if visitar:
        if kani_modo.PORTA_KANIVETE == 9222:
            raise ValueError("visitar troca de ferramenta: use o app de teste (KANI_PORTA_KANIVETE=9333)")
        kani_modo._kanivete_js("""async fs => { for (const f of fs) { try { switchTool(f); } catch (e) {} await new Promise(r => setTimeout(r, 2500)); }
                                 switchTool('home'); }""", list(FERR))
    dados = json.loads(kani_modo._kanivete_js("() => JSON.stringify((" + JS_COLETAR + ")())"))
    os.makedirs(DADOS, exist_ok=True)
    with open(ARQ, "w", encoding="utf-8") as f:
        json.dump({"quando": time.strftime("%Y-%m-%d %H:%M"), "itens": dados}, f, ensure_ascii=False)
    _cache["t"] = 0
    return len(dados)


def carregar(atualizar=True):
    try:
        mt = os.path.getmtime(ARQ)
    except OSError:
        mt = 0
    if atualizar and time.time() - mt > VALIDADE:
        try:
            coletar()
            mt = os.path.getmtime(ARQ)
        except Exception:
            pass
    me = max(mt, os.path.getmtime(EXTRA) if os.path.exists(EXTRA) else 0)
    if _cache["hab"] is None or _cache["t"] != me:
        try:
            with open(ARQ, encoding="utf-8") as f:
                itens = json.load(f)["itens"]
        except (OSError, ValueError, KeyError):
            itens = []
        hab = montar(itens)
        df = {}
        for h in hab:
            h["_t"] = set(termos(h["busca"]))
            for t in h["_t"]:
                df[t] = df.get(t, 0) + 1
        n = max(1, len(hab))
        _cache.update(t=me, hab=hab, idf={t: math.log(1 + n / d) for t, d in df.items()})
    return _cache["hab"]


_FORTES = {"photo", "photoshop", "video", "premiere", "vetor", "illustrator", "slider", "lux", "sound", "encoder", "ata"}


def ferramenta_do_pedido(pedido):
    ps = re.findall(r"[a-z0-9]+", _sem_acento(pedido))
    for p in ps:   # o nome da ferramenta ganha de palavra genérica ("mixer de áudio do vídeo" = Vídeo)
        if p in _FORTES:
            return _NOMES[p]
    for p in ps:
        if p in _NOMES:
            return _NOMES[p]
    return None


def buscar(pedido, n=5, aberta=None, hab=None):
    hab = carregar() if hab is None else hab
    idf = _cache["idf"] or {}
    q = termos(pedido)
    if not q:
        return []
    alvo = ferramenta_do_pedido(pedido) or aberta
    res = []
    for h in hab:
        comum = h["_t"].intersection(q)
        if not comum:
            continue
        s = sum(idf.get(t, 1) for t in comum) / math.sqrt(len(h["_t"]) + 2)
        s *= 1 + 0.5 * len(comum) / len(set(q))
        if alvo and h.get("f") == alvo:
            s *= 1.8
        elif alvo and h.get("f") not in (alvo, None, ""):
            s *= 0.6
        if h.get("tipo") == "js":
            s *= 1.15   # as feitas à mão já sabem conferir
        if h.get("tipo") == "botao":
            s *= 0.8
        res.append((s, h))
    res.sort(key=lambda x: -x[0])
    return [h for s, h in res[:n]]


def resumo(h):
    lugar = FERR.get(h.get("f"), "")
    args = (" args: " + json.dumps(h["args"], ensure_ascii=False)) if h.get("args") else ""
    txt = h.get("desc") or ((h["menu"] + " › " if h.get("menu") and h["tipo"] != "botao" else "botão ") + h["rotulo"])
    return f"{h['id']} — {lugar}: {txt}{(' (' + h['atalho'] + ')') if h.get('atalho') else ''}{args}"


def achar(ident):
    hab = carregar(atualizar=False)
    ident = re.split(r"\s+—\s+", str(ident))[0].strip()   # ela às vezes copia a linha inteira ("id — Vídeo: ...")
    for h in hab:
        if h["id"] == ident:
            return h
    a = _sem_acento(ident)
    for h in hab:   # ela às vezes escreve o id sem acento
        if _sem_acento(h["id"]) == a:
            return h
    if a in _NOMES or len(a) < 5:   # "video" sozinho não é habilidade (virava um botão chamado Vídeo)
        return None
    iguais = [h for h in hab if _sem_acento(h.get("rotulo", "")) == a]   # ou só o rótulo: vale se for um só
    return iguais[0] if len(iguais) == 1 else None


PERIGO = re.compile(r"fechar|exclu|apag|limpar|descart|sair|redefin|resetar|remover (?:camada|documento|slide|faixa|clipe|tudo)", re.I)   # "Remover plano de fundo" é edição


def executar(ident, args=None):
    import kani_modo
    h = achar(str(ident or "").strip())
    if not h:
        sug = buscar(str(ident), 3)
        return "NÃO FEITO: não achei a habilidade \"" + str(ident) + "\"." + (
            " Parecidas: " + " | ".join(x["id"] for x in sug) if sug else " Use buscar_habilidade.")
    if PERIGO.search(h.get("rotulo", "") + " " + h["id"]) and not kani_modo._PODE_APAGAR.search(kani_modo.pedido_atual[0]) \
            and not kani_modo._PODE_FECHAR.search(kani_modo.pedido_atual[0]):
        return "NÃO FEITO: \"" + h["rotulo"] + "\" apaga ou fecha algo e o Pailer não pediu isso. Pergunte antes (com responder)."
    corpo = {k: h.get(k) for k in ("f", "tipo", "menu", "rotulo", "chave", "js")}
    corpo["args"] = args or {}
    r = kani_modo._kanivete_js(JS_EXECUTAR, corpo)
    if h["tipo"] != "js" and not kani_modo._FALHOU.search(r):
        r += " Agora: " + kani_modo._kanivete_js(kani_modo._JS_VER)[:1200] + " " + kani_modo._kanivete_js(kani_modo._JS_POPUP)
    return r


if __name__ == "__main__":
    sys.path.insert(0, AQUI)
    if "--coletar" in sys.argv:
        print("habilidades coletadas:", coletar("--visitar" in sys.argv))
    q = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    if q:
        for h in buscar(q, 8):
            print(resumo(h))
    else:
        hab = carregar(atualizar=False)
        cont = {}
        for h in hab:
            cont[FERR.get(h.get("f"), "?")] = cont.get(FERR.get(h.get("f"), "?"), 0) + 1
        print(len(hab), "habilidades:", cont)
