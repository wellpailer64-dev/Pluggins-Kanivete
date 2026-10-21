"""WhatsApp Web pela aba da Kani do KaniBrowser (logado com a conta do Pailer), barato e conferido.

  py -3.13 wa.py enviar --conversa "CLAUDE CODE" --texto "linha 1\nlinha 2" [--porta 9222]
  py -3.13 wa.py ler --conversa "CLAUDE CODE" [--n 5]

Abre o WhatsApp se preciso, acha a conversa pelo título EXATO, confere o cabeçalho antes de colar (nunca manda para
outra conversa) e confere a última mensagem depois. Sai com 1 se algo não bater. Mandar só com o ok do Pailer.
"""
import argparse, json, sys, time

from kb import chamar

sys.stdout.reconfigure(encoding="utf-8")

ABRIR = """(async () => {
  const alvo = [...document.querySelectorAll('span[title]')].find(s => s.getAttribute('title').trim().toUpperCase() === %s);
  if (!alvo) return {erro: 'conversa não está na lista'};
  const r = alvo.getBoundingClientRect(), o = {bubbles: true, cancelable: true, view: window, clientX: r.x + 5, clientY: r.y + 5, button: 0};
  for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'])
    alvo.dispatchEvent(t.startsWith('pointer') ? new PointerEvent(t, o) : new MouseEvent(t, o));
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 300));
    const h = document.querySelector('#main header');
    if (h && h.innerText.split('\\n')[0].trim().toUpperCase() === %s) return {ok: 1};
  }
  return {erro: 'não abriu a conversa'};
})()"""

ENVIAR = """(async () => {
  const h = document.querySelector('#main header');
  if (!h || h.innerText.split('\\n')[0].trim().toUpperCase() !== %s) return {erro: 'conversa errada'};
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

LER = """(() => [...document.querySelectorAll('#main [role="row"]')].slice(-%d).map(r => r.innerText.slice(0, 300)))()"""


def js(porta, codigo):
    return chamar(porta, "js_kani", {"codigo": codigo})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["enviar", "ler"])
    ap.add_argument("--conversa", required=True)
    ap.add_argument("--texto", default="")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--porta", type=int, default=9222)
    a = ap.parse_args()
    nome = json.dumps(a.conversa.strip().upper())
    est = js(a.porta, "location.host")
    if "whatsapp" not in str(est):
        chamar(a.porta, "ir", {"url": "https://web.whatsapp.com"})
        time.sleep(20)
    r = js(a.porta, ABRIR % (nome, nome))
    if not isinstance(r, dict) or not r.get("ok"):
        print("ERRO:", r); return 1
    if a.acao == "ler":
        for linha in js(a.porta, LER % a.n) or []:
            print("·", linha.replace("\n", " | "))
        return 0
    texto = a.texto.replace("\\n", "\n")
    r = js(a.porta, ENVIAR % (nome, json.dumps(texto)))
    if not isinstance(r, dict) or not r.get("ok"):
        print("ERRO:", r); return 1
    primeira = texto.splitlines()[0][:40]
    ok = primeira in (r.get("ultima") or "")
    print(("enviado: " if ok else "ENVIADO? confira — última: ") + (r.get("ultima") or "").replace("\n", " | ")[-200:])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
