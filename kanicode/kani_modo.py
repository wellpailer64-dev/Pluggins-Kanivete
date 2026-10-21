"""Modo Kani do KaniCode: a Kani local (Qwen 4B, grátis) responde no lugar do Claude, EM ETAPAS como o agente do
KANIVETE (Functions/kani_agente.py): a cada passo o modelo escolhe UMA ferramenta (resposta travada em JSON pelo
schema do llama.cpp), o KaniCode roda, devolve um resumo curto e ela decide o próximo passo com o que já viu.
Termina com "responder" (fala com o Pailer) ou "passar_para_claude" (pedido difícil: código, edição, problema).

Ferramentas só de leitura ou de abrir coisas (nada apaga nem edita). Eventos para a janela no formato dos passos do
Claude (ferr / ferr_fim), e kani_pensando para a bolinha.
"""
import json, os, re, shutil, subprocess, sys, time, urllib.parse, urllib.request

import ajudantes

MAX_PASSOS = 6
_SEM_JANELA = 0x08000000
PANDA = r"D:\Kanivete\Plugins\pandalab\panda.py"

FERRAMENTAS = {
    "responder": "Responde ao Pailer e TERMINA. args: {mensagem}",
    "passar_para_claude": "Passa o pedido ao Claude e TERMINA (programar, editar código/vídeo/arte, consertar erro, tarefa longa). args: {motivo}",
    "espaco_disco": "Espaço livre e usado dos discos C e D. args: {}",
    "listar_pasta": "Lista o que tem numa pasta (com tamanhos). args: {caminho}",
    "ler_arquivo": "Lê o começo de um arquivo de texto (md, py, js, txt, json...). args: {caminho}",
    "procurar_no_codigo": "Procura um termo nos arquivos do projeto (git grep). args: {termo}",
    "buscar_no_mapa": "Busca no mapa geral do KANIVETE (ferramentas, guias, testes, comandos). args: {termo}",
    "demandas_panda": "Lista as demandas abertas do Laboratório Panda. args: {}",
    "git_resumo": "Últimos commits e arquivos mudados no projeto. args: {}",
    "abrir": "Abre no Windows uma pasta ou um arquivo (sites: use abrir_no_kanibrowser). args: {alvo}",
    "abrir_no_kanibrowser": "Mostra um site no KaniBrowser (o navegador do KANIVETE, com os logins do Pailer: WhatsApp, Instagram, "
                            "ChatGPT, Drive...): se já tem aba dele, vai para ela; senão abre e deixa à vista. args: {site: nome ou https://...}",
    "ver_kanibrowser": "Lista as abas DENTRO do KaniBrowser e qual está à vista. args: {}",
    "navegar_kani": "Abre um site no SEU navegador (lado direito do KaniBrowser, só seu: pesquisar, ler, preencher, baixar). "
                    "Nunca WhatsApp. args: {site: AS PALAVRAS da pesquisa (vai para o Google; nunca invente endereço) ou o https:// que o Pailer deu}",
    "ler_kani": "Lê o texto da página aberta no SEU navegador (lado direito). args: {}",
    "clicar_kani": "Clica num botão ou link da página do SEU navegador, pelo texto. args: {texto}",
    "ler_site": "Lê o texto da página que está à vista no KaniBrowser (avisos, botões, conteúdo). args: {}",
    "clicar_no_site": "Clica num botão ou link da página à vista no KaniBrowser, pelo texto dele (ex.: 'Usar nesta janela'). "
                      "Nada de enviar mensagem, comprar ou postar sem o Pailer pedir. args: {texto}",
    "fechar_aba_kanibrowser": "Fecha abas DENTRO do KaniBrowser (não fecha o KaniBrowser). args: {nome: parte do título/site, ou 'repetidas'}",
    "fechar_aba": "Fecha uma aba aberta no KANIVETE (ex.: Slider, KaniBrowser, Vídeo) ou 'todas'. args: {nome}",
    "responder_janela": "Clica num botão da janelinha de pergunta aberta no KANIVETE (ex.: Close/Fechar, Cancel/Cancelar, Salvar). "
                        "Veja os botões com ver_kanivete ou no resultado de fechar_aba. args: {botao}",
    "salvar_texto": "Cria um arquivo de texto com o conteúdo que você escrever e abre ele. args: {nome, conteudo, onde: area_de_trabalho|projeto}",
    "salvar_conversa": "Salva a conversa de hoje com o Pailer (inteira, palavra por palavra) num arquivo e abre. args: {onde: area_de_trabalho|projeto}",
    "lembrar": "Anota no seu caderno algo que o Pailer ENSINOU ou pediu para lembrar (vale para as próximas conversas). args: {fato}",
    "ver_kanivete": "Lê o que está aberto AGORA no app KANIVETE (ferramenta, projeto, camadas, clipes, abas). args: {}",
    "abrir_ferramenta": "Troca a ferramenta aberta no KANIVETE. args: {nome: video|photo|vetor|sound|slider|lux|encoder|ata|remover-fundo|transcrever|home}",
    "reiniciar_kanivete": "Fecha e reabre o app KANIVETE (para receber atualização de plugin). SÓ quando o Pailer pediu para reiniciar/reabrir "
                          "ou disse sim à sua pergunta; projeto sem salvar aparece como janelinha. args: {}",
    "pedir_ao_kanivete": "SÓ para CRIAR algo novo com IA: gerar imagem, efeito sonoro, narração, vinheta, pesquisa na internet, "
                         "PDF/documento, tirar fundo de imagem, flyer. Passa à Kani de dentro do KANIVETE e TERMINA. NUNCA para mexer no "
                         "app (abas, telas, abrir coisas). args: {pedido: o pedido completo}",
}

# nomes que o modelo usa → id da ferramenta no KANIVETE (data-tool da barra lateral)
_FERR_IDS = {"video": "video-cutter", "vídeo": "video-cutter", "editor": "video-cutter", "photo": "editor-imagem", "foto": "editor-imagem",
             "imagem": "editor-imagem", "vetor": "vetor-kanivete", "sound": "sound-kanivete", "som": "sound-kanivete",
             "slider": "slider-kanivete", "lux": "lux-kanivete", "3d": "lux-kanivete", "encoder": "kanivete-encoder",
             "ata": "ata-kanivete", "transcrever": "transcrever-audio", "inicio": "home", "início": "home"}
PORTA_KANIVETE = 9222
DADOS = os.path.join(os.path.splitdrive(os.path.abspath(__file__))[0] + os.sep, "Kanivete", "KaniCode")
NOTAS = os.path.join(DADOS, "kani_notas.md")          # o caderno da Kani (ferramenta lembrar)
REGISTRO = os.path.join(DADOS, "kani_modo.jsonl")     # cada pedido do modo Kani (kanicode.py grava)
KB = r"D:\Kanivete\Plugins\kanibrowser\kb.py"
_SITES = {"whatsapp": "https://web.whatsapp.com", "zap": "https://web.whatsapp.com", "instagram": "https://www.instagram.com",
          "chatgpt": "https://chatgpt.com", "drive": "https://drive.google.com", "gmail": "https://mail.google.com",
          "youtube": "https://www.youtube.com", "pinterest": "https://br.pinterest.com", "panda": "https://laboratoriopanda.com"}
# "vou abrir…", "só um momento" sem ter feito: a trava manda fazer AGORA (2026-10-21: prometeu 4 vezes e não fez)
# 2026-10-21 (2): "Vou seguir suas instruções e usar a ferramenta certa… agora" escapava: qualquer "vou + verbo" conta
_PROMESSA = re.compile(r"\b(?:vou|irei|j[aá] vou|vamos)\s+(?:agora\s+|j[aá]\s+|te\s+|lhe\s+|logo\s+)?[a-zà-ú]+(?:ar|er|ir|or)\b|"
                       r"\b(?:estou|t[oô])\s+(?:agora\s+)?[a-zà-ú]+(?:ando|endo|indo)\b|"
                       r"\b(?:em um instante|s[oó] um momento|agora mesmo|em seguida)\b", re.I)
# resultado de ferramenta que NÃO fez o pedido; resposta que diz que fez (ou que inventa o que vai acontecer)
_FALHOU = re.compile(r"^(?:ERRO|NÃO FEITO)|\bn[aã]o achei\b|\bn[aã]o (?:consegui|cliquei|existe|está carregado)|nenhuma aba", re.I)
_DIZ_FEITO = re.compile(r"\b(?:pronto|feito|consegui|cliquei|j[aá] est[aá]|est[aá] pront|deu certo|funcionou|resolvido|agora (?:quando|est[aá]|o|a))\b", re.I)
# pedir_ao_kanivete é só para CRIAR (2026-10-21: "reinicie o KaniBrowser" virou Remover fundo)
_CRIAR = re.compile(r"\b(?:cri|ger|fa[çz]|narr|vinheta|imagem|foto|som|efeito|m[uú]sica|pesquis|pdf|documento|fundo|flyer|desenh|escrev|arte|logo)", re.I)
_MEXER_APP = re.compile(r"reinici|reabr|atualiz|clic|bot[aã]o|\baba|fech|janela|kanibrowser|whats", re.I)
_PODE_REINICIAR = re.compile(r"reinici|reabr|reinstal|^\s*(?:sim|pode|ok|confirmo|claro|isso|manda ver|faz)\b", re.I)

_SISTEMA = """Você é a Kani, assistente do Pailer no KaniCode (janelinha na área de trabalho), rodando no computador dele.
Hoje é {data}, {hora}. Pasta do projeto: {pasta}
Trabalhe EM ETAPAS: a cada resposta escolha UMA ação; o app executa e te devolve o resultado; então decida a próxima.

FERRAMENTAS:
{ferramentas}

REGRAS:
- Seu nome se escreve Kani (com K) e o app é o KANIVETE (com K). Nunca escreva "Cani" nem "Canivete".
- Você TEM acesso ao app KANIVETE aberto pelas ferramentas ver_kanivete, abrir_ferramenta e pedir_ao_kanivete:
  nunca diga que não tem permissão. "O que está na tela/aberto" = ver_kanivete.
- Criar imagem, som, narração, vinheta, pesquisa na internet, documento, tirar fundo ou flyer = pedir_ao_kanivete.
- NUNCA prometa ("vou abrir", "vou criar", "só um momento"): FAÇA agora com a ferramenta. Se nenhuma ferramenta faz o que foi
  pedido, diga que ainda não sabe fazer isso e use passar_para_claude.
- Abrir o KANIVETE = ver_kanivete (ele quase sempre JÁ está aberto); nunca rode .bat, .py ou .exe.
- Fechou aba e apareceu JANELINHA (pergunta com botões)? Leia os botões e use responder_janela; projeto com mudança
  não salva: pergunte ao Pailer antes de escolher fechar sem salvar.
- Site (WhatsApp, Instagram, ChatGPT...) = abrir_no_kanibrowser, nunca abrir. Ele já deixa a aba à vista.
- Pesquisar, ler um site, buscar informação, baixar: use o SEU navegador (navegar_kani, ler_kani, clicar_kani) e
  responda com o que leu. O lado do Pailer (abrir_no_kanibrowser) é só quando ele quiser VER/usar o site; WhatsApp sempre lá.
- Site com aviso ou botão ("Usar nesta janela", "Continuar"): ler_site e clicar_no_site.
- Abas de SITES ficam DENTRO do KaniBrowser: ver_kanibrowser / fechar_aba_kanibrowser. fechar_aba é só para as ferramentas
  do KANIVETE: NUNCA feche o KaniBrowser para consertar um site. Abas repetidas = fechar_aba_kanibrowser 'repetidas'.
- O Pailer te ensinou algo ou pediu para lembrar = lembrar. Você só lembra do que está no caderno abaixo.
- Conversa, dúvida simples ou ideia: responda direto com "responder" (sem ferramenta antes).
- Pergunta sobre arquivos, disco, demandas ou o projeto: use a ferramenta certa, olhe o resultado e responda com os dados.
- No máximo {max} ações. Nunca invente resultado de ferramenta.
- Ferramenta disse ERRO, NÃO FEITO ou "não achei"? Diga ao Pailer, com as palavras do resultado, que NÃO deu e por quê.
  Nunca diga "pronto" nem invente o que vai acontecer depois.
- Reiniciar ou reabrir o KANIVETE = reiniciar_kanivete (nunca pedir_ao_kanivete).
- Programar, editar código, montar vídeo/arte, consertar erro ou qualquer coisa além das ferramentas: "passar_para_claude".
- Resposta em português do Brasil, curta, simples e simpática, sem tabelas.{voz}{notas}"""

_VOZ = "\n- O Pailer está OUVINDO a resposta: no máximo 3 frases curtas, sem caminho de arquivo, código, lista ou emoji."

_SCHEMA = {"type": "object", "properties": {
    "pensamento": {"type": "string", "maxLength": 90},   # curto: cada token é ~25 ms na RTX 3050
    "acao": {"type": "string", "enum": list(FERRAMENTAS)},
    "args": {"type": "object"}},
    "required": ["pensamento", "acao", "args"]}


def _rodar(cmd, cwd=None, prazo=60):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=prazo, creationflags=_SEM_JANELA)
        return (r.stdout or "") + (("\n" + r.stderr[-500:]) if r.returncode and r.stderr else "")
    except subprocess.TimeoutExpired:
        return "(demorou demais e foi parado)"


def _caminho(c, pasta):
    c = str(c or "").strip().strip('"')
    if not c:
        return pasta
    return c if os.path.isabs(c) else os.path.join(pasta, c)


def _gb(n):
    return f"{n / 2 ** 30:.1f} GB"


def _area_de_trabalho():
    try:   # a pasta real (pode estar no OneDrive)
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)
        if buf.value and os.path.isdir(buf.value):
            return buf.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def _onde(o, pasta):
    return pasta if str(o or "").lower().startswith("proj") else _area_de_trabalho()


def _nome_arquivo(n, ext=".txt"):
    n = re.sub(r'[\\/:*?"<>|]+', " ", str(n or "").strip()).strip() or "Kani " + time.strftime("%Y-%m-%d %H-%M")
    return n if os.path.splitext(n)[1].lower() in (".txt", ".md") else n + ext


def notas():
    try:
        with open(NOTAS, encoding="utf-8") as f:
            return f.read().strip()[-2500:]
    except OSError:
        return ""


pedido_atual = [""]   # o pedido em curso (endereço que o Pailer não deu = inventado)


def _executar(acao, a, pasta):
    """roda a ferramenta; devolve o resumo (texto curto) que volta para o modelo"""
    if acao == "espaco_disco":
        out = []
        for d in ("C:\\", "D:\\"):
            try:
                u = shutil.disk_usage(d)
                out.append(f"{d[0]}: {_gb(u.free)} livres de {_gb(u.total)}")
            except OSError:
                pass
        return "; ".join(out)
    if acao == "listar_pasta":
        p = _caminho(a.get("caminho"), pasta)
        if not os.path.isdir(p):
            raise ValueError(f"pasta não existe: {p}")
        itens = []
        for e in sorted(os.scandir(p), key=lambda e: (not e.is_dir(), e.name.lower()))[:50]:
            try:
                itens.append(e.name + "/" if e.is_dir() else f"{e.name} ({e.stat().st_size // 1024} KB)")
            except OSError:
                pass
        return f"{p}: " + ", ".join(itens) if itens else f"{p} está vazia"
    if acao == "ler_arquivo":
        p = _caminho(a.get("caminho"), pasta)
        if not os.path.isfile(p):
            raise ValueError(f"arquivo não existe: {p}")
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read(3500)
    if acao == "procurar_no_codigo":
        t = str(a.get("termo") or "").strip()
        if not t:
            raise ValueError("faltou o termo")
        linhas = _rodar(["git", "grep", "-n", "-I", "-i", "-F", "--max-count=3", t], cwd=pasta).splitlines()
        return "\n".join(l[:200] for l in linhas[:30]) or "nada encontrado"
    if acao == "buscar_no_mapa":
        t = str(a.get("termo") or "").strip()
        if not t:
            raise ValueError("faltou o termo")
        return _rodar([sys.executable.replace("pythonw", "python"), "tools/mapa_geral.py", "--busca", t], cwd=pasta)[:3000] or "nada encontrado"
    if acao == "demandas_panda":
        if not os.path.isfile(PANDA):
            raise ValueError("o plugin Pandalab não está nesta máquina")
        return _rodar([sys.executable.replace("pythonw", "python"), PANDA, "demandas", "--status", "abertas"], prazo=90)[:3000]
    if acao == "git_resumo":
        return ("Commits:\n" + _rodar(["git", "log", "--oneline", "-6"], cwd=pasta)[:1500]
                + "\nMudados:\n" + (_rodar(["git", "status", "-s"], cwd=pasta)[:1200] or "nada"))
    if acao == "abrir":
        alvo = str(a.get("alvo") or "").strip().strip('"')
        if re.match(r"^https?://", alvo):
            os.startfile(alvo)
            return f"site aberto: {alvo}"
        p = _caminho(alvo, pasta)
        if re.search(r"kanivete|canivete", alvo, re.I) and not os.path.exists(p) or p.lower().endswith((".bat", ".cmd", ".exe", ".py", ".ps1")):
            return _garantir_kanivete()   # o app: usa o que já está aberto ou abre o de verdade (nunca .bat/.py)
        if not os.path.exists(p):
            raise ValueError(f"não existe: {p}")
        os.startfile(p)
        return f"aberto: {p}"
    if acao == "abrir_no_kanibrowser":
        site = str(a.get("site") or a.get("alvo") or "").strip()
        url = site if re.match(r"^https?://", site) else _SITES.get(site.lower().split()[0] if site else "", "")
        if not url:
            url = "https://" + site if "." in site else ""
        if not url:
            raise ValueError("diga o site (whatsapp, instagram, chatgpt, drive...) ou o endereço https://")
        return _kanivete_js(_JS_KB_IR, url)
    if acao == "ver_kanibrowser":
        return _kanivete_js(_JS_KB_VER)
    if acao in ("navegar_kani", "ler_kani", "clicar_kani"):
        if acao == "navegar_kani":
            site = str(a.get("site") or a.get("alvo") or "").strip()
            if not site:
                raise ValueError("diga o site ou o que pesquisar")
            if re.search(r"whats|wpp|zap", site, re.I):
                raise ValueError("WhatsApp só no lado do Pailer (uma aba por vez): use abrir_no_kanibrowser")
            if re.match(r"^https?://", site) and not re.search(re.escape(urllib.parse.urlparse(site).netloc.replace("www.", "")), pedido_atual[0], re.I):
                site = re.sub(r"^https?://(www\.)?|[/._-]+", " ", site).strip()   # endereço inventado: vira pesquisa no Google
            url = site if re.match(r"^https?://", site) else _SITES.get(site.lower().split()[0], "") or \
                ("https://" + site if "." in site and " " not in site else "https://www.google.com/search?q=" + urllib.parse.quote(site))
            o = {"f": "kani_ir", "a": {"url": url}}
        elif acao == "ler_kani":
            o = {"f": "texto", "a": {}}   # sem aba = a aba da Kani
        else:
            t = str(a.get("texto") or "").strip()
            if not t:
                raise ValueError("diga o texto do botão")
            o = {"f": "js_kani", "a": {"codigo": _JS_CLIQUE_TEXTO.replace("TEXTO_AQUI", json.dumps(t))}}
        return _kanivete_js(_JS_KB_KANI, o)
    if acao == "ler_site":
        return _kanivete_js(_JS_KB_SITE, {"f": "texto"})
    if acao == "clicar_no_site":
        t = str(a.get("texto") or "").strip()
        if not t:
            raise ValueError("diga o texto do botão")
        return _kanivete_js(_JS_KB_SITE, {"f": "clicar_texto", "texto": t})
    if acao == "fechar_aba_kanibrowser":
        return _kanivete_js(_JS_KB_FECHAR, str(a.get("nome") or "").strip().lower())
    if acao == "fechar_aba":
        nome = str(a.get("nome") or "").strip().lower()
        return _kanivete_js(_JS_FECHAR, _ferramenta_id(nome) or nome)
    if acao == "responder_janela":
        return _kanivete_js(_JS_CLICAR, str(a.get("botao") or "").strip().lower())
    if acao == "salvar_texto":
        conteudo = str(a.get("conteudo") or "").strip()
        if not conteudo:
            raise ValueError("faltou o conteúdo")
        p = os.path.join(_onde(a.get("onde"), pasta), _nome_arquivo(a.get("nome")))
        with open(p, "w", encoding="utf-8") as f:
            f.write(conteudo + "\n")
        os.startfile(p)
        return f"salvo e aberto: {p}"
    if acao == "salvar_conversa":
        hoje, linhas = time.strftime("%Y-%m-%d"), []
        try:
            with open(REGISTRO, encoding="utf-8") as f:
                for l in f:
                    d = json.loads(l)
                    if str(d.get("quando", "")).startswith(hoje):
                        linhas.append(f"[{d['quando'][11:16]}] Pailer: {d.get('pedido', '')}\n[{d['quando'][11:16]}] Kani: {d.get('resposta', '')}\n")
        except OSError:
            pass
        if not linhas:
            raise ValueError("não achei conversa de hoje no registro")
        p = os.path.join(_onde(a.get("onde"), pasta), f"Conversa com a Kani {hoje}.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"Conversa com a Kani (KaniCode) — {hoje}\n\n" + "\n".join(linhas))
        os.startfile(p)
        return f"conversa de hoje ({len(linhas)} trocas) salva e aberta: {p}"
    if acao == "lembrar":
        fato = str(a.get("fato") or "").strip()
        if not fato:
            raise ValueError("faltou o que lembrar")
        os.makedirs(DADOS, exist_ok=True)
        with open(NOTAS, "a", encoding="utf-8") as f:
            f.write(f"- {fato} ({time.strftime('%d/%m')})\n")
        return "anotado no caderno"
    if acao == "ver_kanivete":
        return _kanivete_js(_JS_VER) + " " + _kanivete_js(_JS_POPUP)
    if acao == "abrir_ferramenta":
        _garantir_kanivete()
        nome = str(a.get("nome") or "").strip().lower()
        return _kanivete_js(_JS_ABRIR, _ferramenta_id(nome) or nome)
    if acao == "reiniciar_kanivete":
        if not _PODE_REINICIAR.search(pedido_atual[0]):
            return "NÃO FEITO: o Pailer não pediu para reiniciar. Pergunte antes (com responder) se pode fechar e reabrir o KANIVETE."
        return _reiniciar_kanivete()
    raise ValueError(f"ferramenta desconhecida: {acao}")


# o que está aberto no KANIVETE: o mesmo resumo em texto que a Kani de lá recebe (frontend/js/kani-tela.js)
_JS_VER = """() => {
  const pg = document.querySelector('.tool-page.active'); const id = pg ? pg.id.replace(/^page-/, '') : '';
  const abas = [...document.querySelectorAll('.tab[data-tab] .tab-nome')].map(e => e.firstChild ? e.firstChild.textContent.trim() : '').filter(Boolean);
  let t = '';
  try { t = id === 'home' ? 'Tela inicial (banners e lista das ferramentas).' : (KANI_TELA[id] ? KANI_TELA[id]() : kaniTelaGenerica(pg)); } catch (e) { t = ''; }
  return 'Ferramenta aberta: ' + (id || '?') + '. Abas: ' + (abas.join(', ') || 'nenhuma') + '. ' + String(t || '').slice(0, 2500);
}"""

_JS_ABRIR = """id => {
  const el = document.querySelector('.menu-item[data-tool="' + id + '"]');
  if (!el) return 'não existe: ' + id + '. Existem: ' + [...document.querySelectorAll('.menu-item[data-tool]')].map(e => e.dataset.tool).join(', ');
  switchTool(id); return 'aberta: ' + id;
}"""

_JS_POPUP = """() => {
  const vis = e => e && !e.hidden && e.offsetParent !== null && getComputedStyle(e).visibility !== 'hidden';
  const caixas = [...document.querySelectorAll('#app-confirm, [role=dialog], .modal-overlay, .ve-modal, dialog[open]')].filter(vis);
  if (!caixas.length) return '';
  const c = caixas[caixas.length - 1];
  const tit = (c.querySelector('h1,h2,h3,h4,.ve-modal-head')?.innerText || '').trim();
  const txt = (c.querySelector('p')?.innerText || '').trim();
  const bts = [...c.querySelectorAll('button')].filter(vis).map(b => b.innerText.trim()).filter(Boolean);
  return 'JANELINHA ABERTA NA TELA: "' + tit + (txt ? ' — ' + txt.slice(0, 200) : '') + '". Botões: ' + bts.join(' | ') + '. (use responder_janela)';
}"""

_JS_CLICAR = """q => {
  const vis = e => e && !e.hidden && e.offsetParent !== null;
  const caixas = [...document.querySelectorAll('#app-confirm, [role=dialog], .modal-overlay, .ve-modal, dialog[open]')].filter(vis);
  if (!caixas.length) return 'não há janelinha aberta';
  const bts = [...caixas[caixas.length - 1].querySelectorAll('button')].filter(vis);
  const b = bts.find(b => b.innerText.trim().toLowerCase() === q) || bts.find(b => b.innerText.trim().toLowerCase().includes(q));
  if (!b) return 'botão não encontrado. Botões: ' + bts.map(b => b.innerText.trim()).join(' | ');
  b.click(); return 'cliquei em: ' + b.innerText.trim();
}"""

# KaniBrowser (plugin; painel.js expõe KB_API.KB e KPLUG.chamar): a aba à vista no painel = KB.sel
_JS_KB = """
  const ID = 'kanibrowser';
  const K = window.KB_API;
  if (!K) return 'o KaniBrowser não está carregado no KANIVETE';
  if (typeof switchTool === 'function' && document.querySelector('.menu-item[data-tool="plugin-kanibrowser"]')) switchTool('plugin-kanibrowser');
  await K.atualizar();
  const host = u => { try { return new URL(u).hostname.replace(/^www\\./, ''); } catch (e) { return ''; } };
  const mostrar = async id => {   // o mesmo caminho do clique na aba do painel
    const el = KPLUG.pagina(ID)?.querySelector('.kb-tab[data-id="' + id + '"]');
    if (el) el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0 }));
    else { K.KB.sel = id; await KPLUG.chamar(ID, 'frente', { aba: id }).catch(() => 0); await K.atualizar(); }
  };
"""

_JS_KB_IR = """async url => {""" + _JS_KB + """
  const h = host(url);
  let a = K.KB.abas.find(t => host(t.url) === h);
  if (!a) {
    if (!K.KB.aberto) await KPLUG.chamar(ID, 'abrir', { url }); else await KPLUG.chamar(ID, 'nova', { url });
    for (let i = 0; i < 20 && !a; i++) { await new Promise(r => setTimeout(r, 300)); await K.atualizar(); a = K.KB.abas.find(t => host(t.url) === h || (t.url || '').startsWith(url)); }
  }
  if (!a) return 'abri ' + url + ', mas não achei a aba no painel';
  await mostrar(a.id);
  const iguais = K.KB.abas.filter(t => host(t.url) === h).length;
  return 'à vista no KaniBrowser: ' + (a.titulo || url) + (iguais > 1 ? ' (há ' + iguais + ' abas iguais: use fechar_aba_kanibrowser repetidas)' : '');
}"""

_JS_KB_VER = """async () => {""" + _JS_KB + """
  if (!K.KB.aberto) return 'o KaniBrowser está fechado';
  return 'Abas do KaniBrowser: ' + K.KB.abas.map(t => (t.id === K.KB.sel ? '[À VISTA] ' : '') + (t.titulo || '?') + ' (' + host(t.url) + ')').join('; ');
}"""

_JS_KB_SITE = """async o => {""" + _JS_KB + """
  if (!K.KB.aberto || !K.KB.sel) return 'o KaniBrowser não tem aba à vista';
  try {
    const r = await KPLUG.chamar(ID, o.f, o.f === 'texto' ? { aba: K.KB.sel } : { texto: o.texto, aba: K.KB.sel });
    return typeof r === 'string' ? r.slice(0, 2500) : JSON.stringify(r).slice(0, 2500);
  } catch (e) {
    const m = String(e && e.message || e);
    return /liberada/.test(m) ? 'NÃO FEITO: o KANIVETE aberto ainda não tem essa habilidade (o KaniBrowser foi atualizado depois que ele abriu). '
      + 'Só funciona depois de reiniciar o KANIVETE (reiniciar_kanivete, se o Pailer quiser).' : 'ERRO: ' + m;
  }
}"""

# o lado direito do KaniBrowser = a aba da Kani (ponte: kani_ir, texto sem aba, js_kani)
_JS_KB_KANI = """async o => {
  if (typeof KPLUG === 'undefined') return 'o KaniBrowser não está no KANIVETE';
  if (typeof switchTool === 'function' && document.querySelector('.menu-item[data-tool="plugin-kanibrowser"]')) switchTool('plugin-kanibrowser');
  try {
    const r = await KPLUG.chamar('kanibrowser', o.f, o.a);
    if (o.f === 'kani_ir') { await new Promise(r => setTimeout(r, 2500)); return 'aberto no seu navegador: ' + r; }
    return typeof r === 'string' ? r.slice(0, 2500) : JSON.stringify(r).slice(0, 2500);
  } catch (e) { return 'erro: ' + String(e && e.message || e); }
}"""

_JS_CLIQUE_TEXTO = """(q => { q = q.toLowerCase(); const vis = e => e.offsetParent !== null;
  const els = [...document.querySelectorAll('button, a, [role=button], [role=link], input[type=submit], input[type=button]')].filter(vis);
  const txt = e => (e.innerText || e.value || e.getAttribute('aria-label') || '').trim();
  const b = els.find(e => txt(e).toLowerCase() === q) || els.find(e => txt(e).toLowerCase().includes(q));
  if (!b) return 'não achei "' + q + '". Botões/links: ' + els.map(txt).filter(Boolean).slice(0, 25).join(' | ');
  b.click(); return 'cliquei em: ' + txt(b); })(TEXTO_AQUI)"""

_JS_KB_FECHAR = """async q => {""" + _JS_KB + """
  const vista = K.KB.sel;
  let alvo;
  if (q === 'repetidas') {   // fica a de cada site que está à vista (ou a primeira)
    const fica = {};
    K.KB.abas.forEach(t => { const h = host(t.url); if (!fica[h] || t.id === vista) fica[h] = t.id; });
    alvo = K.KB.abas.filter(t => fica[host(t.url)] !== t.id);
  } else alvo = K.KB.abas.filter(t => (t.titulo || '').toLowerCase().includes(q) || host(t.url).includes(q));
  if (!alvo.length) return 'nenhuma aba para fechar. Abas: ' + K.KB.abas.map(t => t.titulo).join('; ');
  for (const t of alvo) await KPLUG.chamar(ID, 'fechar', { aba: t.id }).catch(() => 0);
  await K.atualizar();
  return 'fechei ' + alvo.length + ' aba(s). Ficaram: ' + K.KB.abas.map(t => (t.id === K.KB.sel ? '[À VISTA] ' : '') + t.titulo).join('; ');
}"""

_JS_FECHAR = """async q => {
  const abas = [...document.querySelectorAll('.tab[data-tab]')].map(e => ({id: e.dataset.tab, nome: (e.querySelector('.tab-nome')?.firstChild?.textContent || '').trim()}));
  if (!abas.length) return 'não há abas abertas';
  const alvo = q === 'todas' || q === 'tudo' ? abas : abas.filter(a => a.id === q || a.id.includes(q) || a.nome.toLowerCase().includes(q));
  if (!alvo.length) return 'nenhuma aba com esse nome. Abertas: ' + abas.map(a => a.nome).join(', ');
  for (const a of alvo) {   // uma de cada vez; rápido = sem o "Fechar?" (só pergunta se houver algo para salvar)
    await Promise.race([fecharAba(a.id, null, true), new Promise(r => setTimeout(r, 700))]);
    if (document.querySelector('#app-confirm:not([hidden])')) break;
  }
  await new Promise(r => setTimeout(r, 600));
  const pop = (POPUP_AQUI)();
  const ainda = [...document.querySelectorAll('.tab[data-tab]')].map(e => e.dataset.tab).filter(id => alvo.some(a => a.id === id));
  return (ainda.length ? 'ainda aberta(s): ' + ainda.join(', ') + '. ' : 'fechada(s): ' + alvo.map(a => a.nome).join(', ') + '. ') + pop;
}"""

_JS_JOB = """j => {
  for (const c of [KANI.conversa, ...kaniConversas()]) {
    const m = c && c.msgs.find(m => m.agente && m.agente.job === j);
    if (m) { const g = m.agente; return {estado: g.estado, mensagem: g.mensagem || '', resposta: g.resposta || '',
      passos: (g.passos || []).map(p => (p.acao || '') + ' ' + (p.estado || '')), arquivos: (g.arquivos || []).map(a => a.path || a.nome)}; }
  }
  return null;
}"""


_JS_FECHAR = _JS_FECHAR.replace("POPUP_AQUI", _JS_POPUP)


def _ferramenta_id(nome):
    """"Photo Kanivete", "fotocanivete", "remover fundo", "Remove Background" → id da barra lateral"""
    n = re.sub(r"\b(?:kanivete|canivete)\b|kanivete$|canivete$", "", nome.lower()).strip(" -_")
    extra = {"remover fundo": "remover-fundo", "remove background": "remover-fundo", "kanibrowser": "plugin-kanibrowser",
             "browser": "plugin-kanibrowser", "photoshop": "editor-imagem", "fotocanivete": "editor-imagem"}
    return _FERR_IDS.get(n) or extra.get(n) or _FERR_IDS.get(nome) or extra.get(nome) or ""


EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), "CANIVETE DO PAILER",
                   "dist", "CaniveteDoPailer", "CaniveteDoPailer.exe")


def _garantir_kanivete():
    """KANIVETE aberto em modo agente? senão abre o de verdade (o exe com --agente) e espera ficar pronto"""
    def vivo():
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORTA_KANIVETE}/json/version", timeout=2).close()
            return True
        except Exception:
            return False
    if vivo():
        return "o KANIVETE já está aberto (não abri outro)"
    if not os.path.isfile(EXE):
        raise ValueError("não achei o KANIVETE instalado")
    subprocess.Popen([EXE, "--agente"], cwd=os.path.dirname(EXE), creationflags=_SEM_JANELA)
    for _ in range(60):
        time.sleep(1)
        if vivo():
            time.sleep(3)   # a página termina de carregar
            return "abri o KANIVETE"
    raise ValueError("o KANIVETE não respondeu depois de 1 minuto")


def _vivo():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORTA_KANIVETE}/json/version", timeout=2).close()
        return True
    except Exception:
        return False


def _reiniciar_kanivete():
    """o mesmo "Reiniciar agora" das Preferências: marca, sai pelo appSair (que pergunta do projeto não salvo) e o app se
    reabre sozinho com os mesmos argumentos (--agente continua)"""
    if not _vivo():
        return _garantir_kanivete()
    r = _kanivete_js("""async () => {
      if (!window.pywebview?.api?.reiniciar_marcar) return 'NÃO FEITO: esta versão do KANIVETE não sabe reiniciar sozinha';
      await window.pywebview.api.reiniciar_marcar();
      setTimeout(() => (window.appSair ? appSair() : window.pywebview.api.sair_app()), 50);
      return 'ok';
    }""")
    if r != "ok":
        return r
    time.sleep(1.5)
    if _vivo():
        try:
            pop = _kanivete_js(_JS_POPUP)
        except Exception:
            pop = ""
        if pop:   # projeto sem salvar / render rodando: o Pailer decide
            return "NÃO FEITO ainda: o KANIVETE perguntou antes de fechar. " + pop + " Pergunte ao Pailer qual botão."
    for _ in range(40):   # esperar fechar
        if not _vivo():
            break
        time.sleep(0.5)
    else:
        return "NÃO FEITO: o KANIVETE não fechou (talvez esteja esperando uma resposta na tela)."
    for _ in range(90):   # e reabrir
        time.sleep(1)
        if _vivo():
            time.sleep(4)   # a página termina de carregar
            return "reiniciei o KANIVETE (fechou e já abriu de novo)"
    return "NÃO FEITO: o KANIVETE fechou mas não voltou em 90 s; dá para abrir pelo atalho"


def _pagina(pw):
    try:
        nav = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORTA_KANIVETE}", timeout=4000)
    except Exception:
        raise ValueError("o KANIVETE não está aberto (ou foi aberto sem o modo agente)")
    for c in nav.contexts:
        for pg in c.pages:
            if "index.html" in pg.url:
                return nav, pg
    raise ValueError("não achei a janela principal do KANIVETE")


def _kanivete_js(js, arg=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        nav, pg = _pagina(pw)
        try:
            return str(pg.evaluate(js, arg) if arg is not None else pg.evaluate(js))
        finally:
            nav.close()   # só a conexão (o app continua aberto)


def pedir_ao_kanivete(pedido, ao_evento, parar=None, prazo=900):
    """a Kani do KANIVETE faz o pedido em etapas (gaveta aberta na tela dele) e devolve a mensagem final e os arquivos"""
    from playwright.sync_api import sync_playwright
    ajudantes.kani_parar()   # libera a placa: a Kani de lá e os geradores precisam dela
    with sync_playwright() as pw:
        nav, pg = _pagina(pw)
        try:
            job = pg.evaluate("""async p => { if (typeof kaniAbrir === 'function') await kaniAbrir();
                                 await new Promise(r => setTimeout(r, 300)); kaniAgenteIniciar(p); return KANI.agenteJob; }""", pedido)
            t0, visto = time.time(), 0
            while time.time() - t0 < prazo:
                if parar and parar.is_set():
                    pg.evaluate("j => kaniApi().kani_agente_parar && kaniApi().kani_agente_parar(j)", job)
                    return "Parei o pedido no KANIVETE."
                g = pg.evaluate(_JS_JOB, job)
                if g and len(g["passos"]) > visto:
                    visto = len(g["passos"])
                    ao_evento({"t": "kani_estado", "texto": "no KANIVETE: " + g["passos"][-1]})
                if g and g["estado"] in ("ok", "erro"):
                    arqs = "\n".join("- " + str(a) for a in g["arquivos"] if a)
                    return (g["resposta"] or g["mensagem"] or "Pronto.") + (("\n\nArquivos:\n" + arqs) if arqs else "")
                time.sleep(1.5)
            return "O pedido continua rodando no KANIVETE (passou de 15 min); veja na gaveta da Kani de lá."
        finally:
            nav.close()


def _para_voz(t):
    """resposta que vai ser LIDA: sem markdown e no máximo 3 frases"""
    t = re.sub(r"^\s*#+.*$", "", t, flags=re.M)   # títulos fora
    t = re.sub(r"[#*_`>|]+", "", t)
    t = re.sub(r"^\s*[-•\d.]+\s+", "", t, flags=re.M)
    t = re.sub(r"\s+", " ", t).strip()
    frases = re.split(r"(?<=[.!?])\s+", t)
    return " ".join(frases[:3])


def _nome_certo(t):
    """o modelo às vezes escreve como se fala: Cani/Canivete → Kani/KANIVETE"""
    t = re.sub(r"\bCanivete\b", "KANIVETE", t, flags=re.I)
    return re.sub(r"\b[CK]an[iy]e?\b", "Kani", t)


def _chamar(msgs, porta):
    corpo = {"messages": msgs, "temperature": 0.3, "max_tokens": 600, "stream": False,
             "chat_template_kwargs": {"enable_thinking": False}, "response_format": {"type": "json_object", "schema": _SCHEMA}}
    req = urllib.request.Request(f"http://127.0.0.1:{porta}/v1/chat/completions", json.dumps(corpo).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode("utf-8"))
    out = d["choices"][0]["message"]["content"]
    tok = (d.get("usage") or {}).get("total_tokens") or 0
    try:
        return json.loads(out), tok
    except ValueError:
        m = re.search(r"\{.*\}", out or "", re.S)
        if m:
            return json.loads(m.group(0)), tok
        raise


def _texto(msgs, porta):
    corpo = {"messages": msgs, "temperature": 0.4, "max_tokens": 400, "stream": False, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(f"http://127.0.0.1:{porta}/v1/chat/completions", json.dumps(corpo).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d["choices"][0]["message"]["content"].strip(), (d.get("usage") or {}).get("total_tokens") or 0


def rodar(pedido, pasta, ao_evento, historico=None, por_voz=False, parar=None):
    """roda o pedido em etapas (bloqueia: chamar numa thread). Devolve {ok, texto, claude, tokens, ms}
    claude=True: a Kani passou para o Claude (texto = o motivo)."""
    t0, tokens = time.time(), 0
    ajudantes._kani["uso"] = time.time()
    ferr = "\n".join(f"- {k}: {d}" for k, d in FERRAMENTAS.items())
    sis = (_SISTEMA.replace("{data}", time.strftime("%d/%m/%Y")).replace("{hora}", time.strftime("%H:%M"))
           .replace("{pasta}", pasta).replace("{ferramentas}", ferr).replace("{max}", str(MAX_PASSOS))
           .replace("{voz}", _VOZ if por_voz else "")
           .replace("{notas}", ("\n\nSEU CADERNO (o que o Pailer já te ensinou):\n" + notas()) if notas() else ""))
    msgs = [{"role": "system", "content": sis}]
    for m in (historico or [])[-16:]:
        msgs.append({"role": m["role"], "content": str(m["content"])[:500]})
    msgs.append({"role": "user", "content": pedido})
    pedido_atual[0] = pedido
    cobrou = desmentiu = falhou = False
    fim = (lambda t: _para_voz(_nome_certo(t))) if por_voz else _nome_certo
    try:
        porta = ajudantes._kani_subir(lambda ev: ao_evento({"t": "kani_estado", "texto": ev.get("texto", "")}))
        for n in range(1, MAX_PASSOS + 1):
            if parar and parar.is_set():
                return {"ok": False, "texto": "Parei.", "claude": False, "tokens": tokens, "ms": int((time.time() - t0) * 1000)}
            if n == MAX_PASSOS:
                msgs.append({"role": "user", "content": "Última ação: TEM que ser responder, com o que você já sabe."})
            ao_evento({"t": "kani_pensando"})
            r, tk = _chamar(msgs, porta)
            tokens += tk
            ajudantes._kani["uso"] = time.time()
            acao, args = r.get("acao"), r.get("args") or {}
            msgs.append({"role": "assistant", "content": json.dumps({"pensamento": str(r.get("pensamento") or "")[:300],
                                                                     "acao": acao, "args": args}, ensure_ascii=False)})
            if acao == "responder":
                txt = str(args.get("mensagem") or next((v for v in args.values() if isinstance(v, str) and len(v) > 3), "")).strip()
                if not txt:   # esqueceu o texto (vinha o pensamento no lugar): pede só a resposta, sem JSON
                    txt, tk = _texto(msgs[:-1] + [{"role": "user", "content": "Agora escreva só a resposta ao Pailer, em texto normal."}], porta)
                    tokens += tk
                if _PROMESSA.search(txt) and not cobrou and n < MAX_PASSOS:   # prometeu sem fazer: faz agora
                    cobrou = True
                    msgs.append({"role": "user", "content": "Você PROMETEU fazer algo e ia parar sem fazer. Faça AGORA com a ferramenta "
                                 "certa. Se nenhuma ferramenta faz isso, use passar_para_claude dizendo o que falta."})
                    continue
                if falhou and _DIZ_FEITO.search(txt) and not desmentiu and n < MAX_PASSOS:   # a ferramenta não fez e ela diz que fez
                    desmentiu = True
                    msgs.append({"role": "user", "content": "O último resultado disse que NÃO deu certo. Reescreva a resposta dizendo "
                                 "isso com sinceridade e o motivo (não diga pronto, não invente)."})
                    continue
                return {"ok": True, "texto": fim(txt), "claude": False, "tokens": tokens, "ms": int((time.time() - t0) * 1000)}
            if acao == "passar_para_claude":
                return {"ok": True, "texto": str(args.get("motivo") or "").strip(), "claude": True, "tokens": tokens,
                        "ms": int((time.time() - t0) * 1000)}
            if acao == "pedir_ao_kanivete":
                p = str(args.get("pedido") or pedido)
                if (_MEXER_APP.search(p) or not _CRIAR.search(p)) and n < MAX_PASSOS:   # não é criação: não vai para lá
                    falhou = True
                    msgs.append({"role": "user", "content": "Recusado: pedir_ao_kanivete é SÓ para criar algo novo (imagem, som, "
                                 "narração, documento...). Para reiniciar use reiniciar_kanivete; para abas, sites e botões, as "
                                 "outras ferramentas. Se nenhuma serve, diga ao Pailer que ainda não sabe fazer isso."})
                    continue
                fid = f"kani{int(t0)}_{n}"
                ao_evento({"t": "ferr", "id": fid, "nome": "kani_pedir_ao_kanivete", "entrada": args})
                try:
                    txt, ok = pedir_ao_kanivete(str(args.get("pedido") or pedido), ao_evento, parar), True
                except Exception as e:
                    txt, ok = f"Não consegui passar ao KANIVETE: {e}", False
                ao_evento({"t": "ferr_fim", "id": fid, "ok": ok, "saida": txt[:3000]})
                return {"ok": ok, "texto": fim(txt), "claude": False, "tokens": tokens, "ms": int((time.time() - t0) * 1000)}
            fid = f"kani{int(t0)}_{n}"
            ao_evento({"t": "ferr", "id": fid, "nome": "kani_" + str(acao), "entrada": args})
            try:
                resumo, ok = _executar(acao, args, pasta), True
            except Exception as e:
                resumo, ok = f"ERRO: {e}", False
            ao_evento({"t": "ferr_fim", "id": fid, "ok": ok, "saida": resumo[:3000]})
            falhou = bool(_FALHOU.search(resumo))
            msgs.append({"role": "user", "content": f"Resultado ({acao}):\n{resumo[:3000]}\n\nQual a próxima ação?"})
        return {"ok": True, "texto": "Não consegui fechar a resposta nas etapas que tenho.", "claude": False, "tokens": tokens,
                "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "texto": f"A Kani engasgou: {e}", "claude": False, "tokens": tokens, "ms": int((time.time() - t0) * 1000)}
