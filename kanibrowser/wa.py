"""WhatsApp Web pela aba da Kani do KaniBrowser (logado com a conta do Pailer), barato e conferido.

  py -3.13 wa.py ler --conversa "camila studio" [--n 20] [--transcrever]
  py -3.13 wa.py conversas [--busca termo]
  py -3.13 wa.py arquivo --conversa "camila studio" [--nome proposta] [--pasta P]   (baixa o documento; imprime o caminho)
  py -3.13 wa.py enviar --conversa "CLAUDE CODE" --texto "linha 1\\nlinha 2"

Abre o navegador e o WhatsApp sozinho se preciso. --conversa aceita parte do nome, sem acento nem emoji ("camila studio"
acha "Camila 🧿 Studio"); se não está na lista, usa a busca do WhatsApp. Confere o cabeçalho antes de ler/colar (nunca
manda para outra conversa).
ler: uma linha por mensagem — hora, quem (Eu/nome), texto; áudio vira [áudio 1:08] e, com --transcrever, o texto falado
(Parakeet pt-BR local, no processador; guardado em D:/Kanivete/KaniBrowser/wa_audios/<id>.txt: a 2ª leitura é grátis).
Atenção: transcrever TOCA o áudio (mudo) no WhatsApp: o áudio de quem mandou fica marcado como ouvido.
Mandar só com o ok do Pailer.
"""
import argparse, base64, json, os, re, subprocess, sys, time, unicodedata

from kb import chamar

sys.stdout.reconfigure(encoding="utf-8")
PASTA_AUD = os.path.join(os.path.splitdrive(os.path.abspath(__file__))[0] + os.sep, "Kanivete", "KaniBrowser", "wa_audios")
APP = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), "CANIVETE DO PAILER")
PORTA = 9222

# normalizar no JS igual ao Python: sem acento, sem emoji/símbolo, minúsculo, espaços simples
NORM = r"""const norm = s => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();"""
CABEC = """const cab = () => { const h = document.querySelector('#main header'); return h ? h.innerText.split(String.fromCharCode(10))[0].trim() : ''; };"""

ABRIR = """(async () => {
  NORMCAB
  const q = %s, palavras = q.split(' ');
  if (norm(cab()) === q) return {ok: 1, titulo: cab()};
  const nota = t => { const n = norm(t); return n === q ? 3 : n.startsWith(q) ? 2 : palavras.every(p => n.includes(p)) ? 1 : 0; };
  const achar = () => { let m = null, b = 0;
    for (const s of document.querySelectorAll('#pane-side span[title]')) { const v = nota(s.getAttribute('title')); if (v > b) { b = v; m = s; } }
    return m; };
  let alvo = achar(), inp = document.querySelector('#side input[role=textbox]');
  if (!alvo && inp) {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    inp.focus(); set.call(inp, %s); inp.dispatchEvent(new Event('input', {bubbles: true}));
    for (let i = 0; i < 15 && !(alvo = achar()); i++) await new Promise(r => setTimeout(r, 300));
  }
  if (!alvo) return {erro: 'conversa não encontrada'};
  const titulo = alvo.getAttribute('title').trim();
  const r = alvo.getBoundingClientRect(), o = {bubbles: true, cancelable: true, view: window, clientX: r.x + 5, clientY: r.y + 5, button: 0};
  for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'])
    alvo.dispatchEvent(t.startsWith('pointer') ? new PointerEvent(t, o) : new MouseEvent(t, o));
  for (let i = 0; i < 25; i++) {
    await new Promise(r => setTimeout(r, 300));
    if (norm(cab()) === norm(titulo)) {
      if (inp && inp.value) { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        set.call(inp, ''); inp.dispatchEvent(new Event('input', {bubbles: true})); }
      return {ok: 1, titulo};
    }
  }
  return {erro: 'não abriu a conversa'};
})()"""

# foto de perfil grande: abre "Dados do contato/grupo", clica na foto (visualizador em 640 px), copia pelo canvas e fecha tudo
FOTO = """(async () => {
  const z = ms => new Promise(r => setTimeout(r, ms));
  const fechar = () => { for (const b of document.querySelectorAll('[aria-label="Fechar"], [data-icon="x-viewer"], [data-icon="close"]')) (b.closest('button,[role=button]') || b).click(); };
  const h = document.querySelector('#main header'); if (!h) return {erro: 'conversa não aberta'};
  (h.querySelector('[role=button]') || h).click();
  let bt = null;
  for (let i = 0; i < 20 && !bt; i++) { await z(250);
    bt = [...document.querySelectorAll('button')].find(b => { const r = b.getBoundingClientRect(); return r.width >= 90 && r.height >= 90 && r.x > innerWidth * 0.4 && r.y < 300; }); }
  if (!bt) { fechar(); return {erro: 'sem foto de perfil (ou a pessoa esconde a foto)'}; }
  bt.click();
  let im = null;
  for (let i = 0; i < 20 && !im; i++) { await z(300); im = [...document.querySelectorAll('img')].find(x => x.naturalWidth > 200 && x.complete); }
  if (!im) { fechar(); return {erro: 'a foto grande não abriu'}; }
  const c = document.createElement('canvas'); c.width = im.naturalWidth; c.height = im.naturalHeight;
  c.getContext('2d').drawImage(im, 0, 0); const url = c.toDataURL('image/jpeg', 0.95);
  fechar(); await z(600); fechar();
  return {ok: 1, w: c.width, b64: url.split(',')[1]};
})()"""

# documento colado na caixa de mensagem (o WhatsApp abre a prévia) → legenda opcional → enviar; confere o cabeçalho antes
ANEXO = """(async () => {
  NORMCAB
  if (norm(cab()) !== %s) return {erro: 'conversa errada: ' + cab()};
  const bin = atob(%s), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  const f = new File([u], %s, {type: %s});
  const ed = document.querySelector('#main footer [contenteditable=true]'); ed.focus();
  const dt = new DataTransfer(); dt.items.add(f);
  ed.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt}));
  let s = null;
  for (let i = 0; i < 40 && !s; i++) { await new Promise(r => setTimeout(r, 500)); s = document.querySelector('[aria-label^="Enviar"][aria-label*="item"]'); }
  if (!s) return {erro: 'a prévia do arquivo não abriu'};
  const leg = %s;
  if (leg) { const c = [...document.querySelectorAll('[contenteditable=true]')].find(e => !e.closest('#main footer'));
    if (c) { c.focus(); document.execCommand('insertText', false, leg); await new Promise(r => setTimeout(r, 300)); } }
  s.click(); return {ok: 1};
})()""".replace("NORMCAB", NORM + CABEC)

# carrega até n mensagens (rola para cima) e devolve cada uma já resumida
# junta até n mensagens rolando para cima (a lista do WhatsApp só guarda na tela um pedaço) e volta para o fim
LER = r"""(async () => {
  const n = %d, lista = () => [...document.querySelectorAll('#main [role=row]')];
  const main = document.querySelector('#main').getBoundingClientRect(), meio = main.x + main.width / 2;
  const caixa = () => { for (let e = lista()[0]; e; e = e.parentElement) if (e.scrollHeight > e.clientHeight + 50 && getComputedStyle(e).overflowY !== 'visible') return e; };
  let autor = %s;
  const ler = r => {
    const d = r.querySelector('[data-id]'); if (!d) return {sis: r.innerText.trim().slice(0, 120)};
    const pre = r.querySelector('[data-pre-plain-text]'), pp = pre ? pre.getAttribute('data-pre-plain-text') : '';
    const m = pp.match(/\[([^\]]+)\]\s*([^:]+):/);
    const bolha = [...d.querySelectorAll('div')].map(e => e.getBoundingClientRect()).filter(b => b.width > 60 && b.width < main.width * 0.8)
      .sort((a, b) => b.width - a.width)[0] || d.getBoundingClientRect(), eu = bolha.x + bolha.width / 2 > meio;
    const play = r.querySelector('button[aria-label="Reproduzir mensagem de voz"], button[aria-label="Pausar mensagem de voz"]');
    const txt = [...r.querySelectorAll('span.selectable-text')].filter(e => !e.parentElement.closest('span.selectable-text')).map(e => e.innerText).join(' ').trim();
    const linhas = r.innerText.split(String.fromCharCode(10)).map(s => s.trim()).filter(Boolean);
    const hora = (linhas.filter(s => /^\d{1,2}:\d{2}$/.test(s)).pop()) || (m ? m[1] : '');
    const o = {id: d.getAttribute('data-id'), eu, autor: m ? m[2].trim() : '', hora};
    if (play) o.audio = (linhas.find(s => /^\d+:\d{2}$/.test(s) && s !== hora)) || '?';
    else if (r.querySelector('[data-icon^="document"]')) o.doc = ((r.querySelector('[title^="Mostrar"]') || {}).title || '').replace(/^Mostrar "?|"$/g, '');
    else if (!txt && r.querySelector('img')) o.img = 1;
    o.txt = txt || (!play && !o.doc && !o.img ? linhas.filter(s => s !== hora).join(' ').slice(0, 400) : '');
    return o;
  };
  // um passo por chamada (o navegador corta comando longo): junta o que está na tela e rola um pouco para cima
  const E = window.__kvLer = (%s) ? {vistos: new Map(), msgs: [], parado: 0} : window.__kvLer;
  if (!E.desceu) { E.desceu = 1;      // começa do fim de verdade (a lista vai crescendo enquanto desce)
    for (let i = 0, ok = 0; i < 15 && ok < 2; i++) { const c0 = caixa(); if (!c0) break; c0.scrollTop = c0.scrollHeight;
      await new Promise(r => setTimeout(r, 600)); ok = c0.scrollTop + c0.clientHeight >= c0.scrollHeight - 5 ? ok + 1 : 0; } }
  const novas = [];
  const cx = caixa(), vis = cx ? cx.getBoundingClientRect() : null;
  for (const r of lista().filter(r => { if (!vis) return true; const b = r.getBoundingClientRect(); return b.bottom > vis.top - 50 && b.top < vis.bottom + 50; })) { const o = ler(r), k = o.id || ('s:' + o.sis), cheia = o.sis !== undefined ? !!o.sis : !!(o.hora || o.txt || o.audio || o.doc || o.img);
    if (!E.vistos.has(k)) { E.vistos.set(k, o); novas.push(o); } else if (cheia) Object.assign(E.vistos.get(k), o); }
  E.msgs.unshift(...novas);
  const c = caixa();
  if (E.msgs.length < n && c) {
    const antes = c.scrollTop; c.scrollTop = Math.max(0, antes - c.clientHeight * 0.6);
    await new Promise(r => setTimeout(r, 900));
    if (c.scrollTop === antes) E.parado++;
    if (E.parado < 3) return {mais: 1, total: E.msgs.length};
  }
  if (c) c.scrollTop = c.scrollHeight;
  E.desceu = 0;
  const fim = E.msgs.slice(-n);
  for (const o of fim) { if (o.autor) autor = o.autor; if (o.id) o.quem = o.eu ? 'Eu' : (o.autor || autor); }
  return {fim};
})()"""

# toca a mensagem de voz (mudo), pega o arquivo e para
AUDIO = """(async () => {
  if (!window.__kvPlay) { window.__kvPlay = 1; const op = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function () { this.muted = true; window.__kvm = this; return op.apply(this, arguments); }; }
  const sel = '#main [data-id="%s"]', caixa = () => { for (let e = document.querySelector('#main [role=row]'); e; e = e.parentElement) if (e.scrollHeight > e.clientHeight + 50 && getComputedStyle(e).overflowY !== 'visible') return e; };
  let d = document.querySelector(sel);
  for (let i = 0; i < 40 && !d; i++) { const c = caixa(); if (!c || c.scrollTop === 0) break; c.scrollTop -= c.clientHeight * 0.8;
    await new Promise(r => setTimeout(r, 600)); d = document.querySelector(sel); }
  if (!d) return {erro: 'mensagem sumiu'};
  d.scrollIntoView({block: 'center'});
  const r = d.closest('[role=row]'), b = r.querySelector('button[aria-label="Reproduzir mensagem de voz"]');
  if (!b) return {erro: 'sem botão de play'};
  window.__kvm = null; b.click();
  for (let i = 0; i < 75 && !(window.__kvm && window.__kvm.src); i++) await new Promise(r => setTimeout(r, 200));
  const m = window.__kvm; if (!m) return {erro: 'não tocou'};
  m.pause(); m.currentTime = 0;
  const blob = await (await fetch(m.src)).blob();
  const url = await new Promise(ok => { const f = new FileReader(); f.onload = () => ok(f.result); f.readAsDataURL(blob); });
  return {ok: 1, b64: url.split(',')[1]};
})()"""

# abre o documento da mensagem, aperta Baixar com o download desviado para cá e fecha o visualizador
ARQUIVO = """(async () => {
  if (!window.__kvArq) { window.__kvArq = 1; const o = URL.createObjectURL; window.__kvArqB = [];
    URL.createObjectURL = function (b) { const u = o.apply(this, arguments); if (window.__kvPega) window.__kvArqB.push(b); return u; };
    const oc = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function () { if (window.__kvPega && this.href.startsWith('blob:')) { window.__kvArqH = this.href; return; } return oc.apply(this, arguments); };
    const od = HTMLAnchorElement.prototype.dispatchEvent;
    HTMLAnchorElement.prototype.dispatchEvent = function (e) { if (window.__kvPega && this.href.startsWith('blob:')) { window.__kvArqH = this.href; return true; } return od.apply(this, arguments); }; }
  const q = %s.toLowerCase();
  const achar = () => [...document.querySelectorAll('#main [role=row]')].filter(r => r.querySelector('[data-icon^="document"]') && r.innerText.toLowerCase().includes(q)).pop();
  const caixa = () => { for (let e = document.querySelector('#main [role=row]'); e; e = e.parentElement) if (e.scrollHeight > e.clientHeight + 50 && getComputedStyle(e).overflowY !== 'visible') return e; };
  let row = achar();
  for (let i = 0; i < 25 && !row; i++) { const c = caixa(); if (!c || c.scrollTop === 0) break; c.scrollTop -= c.clientHeight * 0.6;
    await new Promise(r => setTimeout(r, 700)); row = achar(); }
  if (!row) return {erro: 'arquivo não achado na conversa'};
  row.scrollIntoView({block: 'center'}); await new Promise(r => setTimeout(r, 400));
  const nome = (row.querySelector('[title^="Mostrar"]') || {}).title || '';
  (row.querySelector('[title^="Mostrar"]') || row.querySelector('[data-icon^="document"]')).click();
  const baixar = () => [...document.querySelectorAll('[aria-label="Baixar"],[title="Baixar"]')].pop();
  for (let i = 0; i < 40 && !baixar(); i++) await new Promise(r => setTimeout(r, 250));
  if (!baixar()) return {erro: 'sem botão Baixar'};
  window.__kvArqB = []; window.__kvArqH = null; window.__kvPega = 1; baixar().click();
  for (let i = 0; i < 100 && !window.__kvArqB.length && !window.__kvArqH; i++) await new Promise(r => setTimeout(r, 200));
  window.__kvPega = 0;
  const fechar = [...document.querySelectorAll('[aria-label="Fechar"],[title="Fechar"]')].pop(); if (fechar) fechar.click();
  const blob = window.__kvArqB[0] || (window.__kvArqH && await (await fetch(window.__kvArqH)).blob()); if (!blob) return {erro: 'o download não veio'};
  const url = await new Promise(ok => { const f = new FileReader(); f.onload = () => ok(f.result); f.readAsDataURL(blob); });
  return {ok: 1, nome: nome.replace(/^Mostrar "?|"$/g, ''), b64: url.split(',')[1]};
})()"""

ENVIAR = """(async () => {
  NORMCAB
  if (norm(cab()) !== %s) return {erro: 'conversa errada'};
  const caixa = document.querySelector('footer [contenteditable="true"]');
  if (!caixa) return {erro: 'sem caixa de texto'};
  caixa.focus();
  const dt = new DataTransfer(); dt.setData('text/plain', %s);
  caixa.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
  await new Promise(r => setTimeout(r, 1200));
  if (!caixa.innerText.trim()) return {erro: 'não colou'};
  caixa.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));
  await new Promise(r => setTimeout(r, 2500));
  const ult = [...document.querySelectorAll('#main [role="row"]')].slice(-1)[0];
  return {ok: 1, ultima: ult ? ult.innerText.slice(-300) : ''};
})()"""

ABRIR = ABRIR.replace("NORMCAB", NORM + CABEC)
ENVIAR = ENVIAR.replace("NORMCAB", NORM + CABEC)
LISTA = """[...document.querySelectorAll('#pane-side span[title]')].map(s => s.getAttribute('title')).filter(t => t && t.length < 60 && !t.includes(String.fromCharCode(10))).slice(0, 60)"""


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def js(codigo):
    return chamar(PORTA, "js_kani", {"codigo": codigo})


def garantir_whatsapp():
    """KaniBrowser aberto e a aba da Kani no WhatsApp carregado"""
    try:
        host = js("location.host")
    except RuntimeError as e:
        if "fechado" not in str(e):
            raise
        chamar(PORTA, "abrir", {})
        host = ""
    if "whatsapp" not in str(host):
        chamar(PORTA, "ir", {"url": "https://web.whatsapp.com"})
    for _ in range(60):
        if js("document.querySelectorAll('#pane-side span[title]').length"):
            return
        time.sleep(1)
    raise RuntimeError("o WhatsApp não carregou (sem login? abra o KaniBrowser e confira)")


def abrir(conversa):
    q = norm(conversa)
    r = js(ABRIR % (json.dumps(q), json.dumps(conversa)))
    if not isinstance(r, dict) or not r.get("ok"):
        raise RuntimeError(f"{r}")
    return r["titulo"]


# ---------- transcrição (Parakeet pt-BR do KANIVETE, o mesmo do "Ei Kani") ----------
_asr = []


def _modelo():
    if not _asr:
        import onnx_asr
        _asr.append(onnx_asr.load_model("nemo-conformer-tdt", os.path.join(APP, "modelos_ia", "asr", "pt"), quantization="int8"))
    return _asr[0]


def transcrever_ogg(dados):
    import numpy as np
    ff = os.path.join(APP, "modelos_ia", "ffmpeg.exe")
    pcm = subprocess.run([ff if os.path.isfile(ff) else "ffmpeg", "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "pipe:1"], input=dados, capture_output=True, check=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    x = np.frombuffer(pcm, np.float32)
    sr, alvo, partes, i = 16000, 18 * 16000, [], 0
    while i < len(x):           # pedaços de ~18 s cortados no trecho mais quieto (entre 12 e 18 s)
        if len(x) - i <= alvo:
            fim = len(x)
        else:
            j0 = i + 12 * sr
            e = np.convolve(np.abs(x[j0:i + alvo]), np.ones(sr // 10) / (sr // 10), "same")
            fim = j0 + int(np.argmin(e))
        if fim - i > sr // 4:
            partes.append(_modelo().recognize(x[i:fim], sample_rate=sr).strip())
        i = fim
    return " ".join(p for p in partes if p)


def texto_audio(mid):
    os.makedirs(PASTA_AUD, exist_ok=True)
    arq = os.path.join(PASTA_AUD, re.sub(r"[^\w.-]", "_", mid) + ".txt")
    if os.path.isfile(arq):
        return open(arq, encoding="utf-8").read()
    r = js(AUDIO % mid)
    if not isinstance(r, dict) or not r.get("ok"):
        return f"(não transcrevi: {r})"
    t = transcrever_ogg(base64.b64decode(r["b64"])) or "(sem fala)"
    open(arq, "w", encoding="utf-8").write(t)
    return t


def main():
    global PORTA
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["ler", "enviar", "conversas", "arquivo", "foto"])
    ap.add_argument("--conversa", default="")
    ap.add_argument("--texto", default="")
    ap.add_argument("--busca", default="")
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--transcrever", action="store_true")
    ap.add_argument("--nome", default="", help="arquivo: parte do nome do documento (vazio = o último)")
    ap.add_argument("--pasta", default=os.path.join(os.path.dirname(PASTA_AUD), "wa_arquivos"))
    ap.add_argument("--saida", default="", help="foto: onde salvar o .jpg")
    ap.add_argument("--arquivo", default="", help="enviar: arquivo a anexar como documento")
    ap.add_argument("--porta", type=int, default=9222)
    a = ap.parse_args()
    PORTA = a.porta
    try:
        garantir_whatsapp()
        if a.acao == "conversas":
            nomes = js(LISTA)
            print("\n".join(n for n in nomes if not a.busca or all(p in norm(n) for p in norm(a.busca).split())))
            return 0
        if not a.conversa:
            print("ERRO: falta --conversa"); return 1
        titulo = abrir(a.conversa)
        if a.acao == "ler":
            print(f"== {titulo}")
            r = {"mais": 1}; primeiro = "true"
            for _ in range(200):
                r = js(LER % (a.n, json.dumps(titulo), primeiro)); primeiro = "false"
                if not r.get("mais"):
                    break
            for m in r.get("fim") or []:
                if "sis" in m:
                    print("  ·", m["sis"].replace("\n", " ")); continue
                ini = f"[{m['hora']}] {m['quem'] or '?'}:"
                if m.get("audio"):
                    t = texto_audio(m["id"]) if a.transcrever else ""
                    print(ini, f"[áudio {m['audio']}]", t)
                elif m.get("doc"):
                    print(ini, f"[arquivo {m['doc']}]", m.get("txt") or "")
                elif m.get("img"):
                    print(ini, "[imagem]", m.get("txt") or "")
                else:
                    print(ini, (m.get("txt") or "").replace("\n", " "))
            return 0
        if a.acao == "arquivo":
            r = js(ARQUIVO % json.dumps(a.nome))
            if not isinstance(r, dict) or not r.get("ok"):
                print("ERRO:", r); return 1
            os.makedirs(a.pasta, exist_ok=True)
            destino = os.path.join(a.pasta, re.sub(r'[<>:"/\\|?*]', "_", r["nome"] or "arquivo"))
            open(destino, "wb").write(base64.b64decode(r["b64"]))
            print(destino)
            return 0
        if a.acao == "foto":
            r = js(FOTO)
            if not isinstance(r, dict) or not r.get("ok"):
                print("ERRO:", r); return 1
            saida = a.saida or os.path.join(os.path.dirname(PASTA_AUD), "wa_fotos", re.sub(r'[<>:"/\\|?*]', "_", titulo) + ".jpg")
            os.makedirs(os.path.dirname(saida) or ".", exist_ok=True)
            open(saida, "wb").write(base64.b64decode(r["b64"]))
            print(saida, f"({r['w']} px)")
            return 0
        if a.acao == "enviar" and a.arquivo:
            import mimetypes
            if not os.path.isfile(a.arquivo):
                print("ERRO: arquivo não existe:", a.arquivo); return 1
            b64 = base64.b64encode(open(a.arquivo, "rb").read()).decode()
            nome = os.path.basename(a.arquivo)
            r = js(ANEXO % (json.dumps(norm(titulo)), json.dumps(b64), json.dumps(nome),
                            json.dumps(mimetypes.guess_type(nome)[0] or "application/octet-stream"), json.dumps(a.texto.replace("\\n", "\n"))))
            if not isinstance(r, dict) or not r.get("ok"):
                print("ERRO:", r); return 1
            time.sleep(4)
            ult = js(LER % (1, json.dumps(titulo), "true")).get("fim") or []
            ok = any(m.get("doc") and nome[:20] in m["doc"] for m in ult)
            print(("enviado: " if ok else "ENVIADO? confira: ") + nome)
            return 0 if ok else 1
        if a.acao != "enviar" or not a.texto.strip():
            print("ERRO: enviar precisa de --texto"); return 1
        texto = a.texto.replace("\\n", "\n")
        r = js(ENVIAR % (json.dumps(norm(titulo)), json.dumps(texto)))
        if not isinstance(r, dict) or not r.get("ok"):
            print("ERRO:", r); return 1
        primeira = texto.splitlines()[0][:40]
        ok = primeira in (r.get("ultima") or "")
        print(("enviado: " if ok else "ENVIADO? confira — última: ") + (r.get("ultima") or "").replace("\n", " | ")[-200:])
        return 0 if ok else 1
    except RuntimeError as e:
        print("ERRO:", e); return 1


if __name__ == "__main__":
    sys.exit(main())
