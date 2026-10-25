"""KaniCode: conversar com o Claude (e depois Codex/Kani) numa janelinha na área de trabalho.

Processo PRÓPRIO, aberto pelo plugin do KANIVETE (ponte.py) mas independente dele: fechar ou reiniciar o KANIVETE não
fecha o KaniCode. A bolinha verde-limão é nativa do Windows (bolinha.py: sem navegador, sempre por cima, arrastável);
a janela da conversa é uma janela do pywebview (ui/janela.html) que aparece/some com o clique na bolinha.
Uma instância só: o canal de controle (127.0.0.1:PORTA, só aceita "ping", "mostrar" e "sair") avisa a que já está aberta.

Rodar à mão: pyw -3.13 kanicode.py   (ferramentas do navegador: --console; testes por CDP: --agente[=9350])
"""
import json, os, re, shutil, socket, sys, threading, time
from collections import deque
from mensagens import Fila

import webview

PASTA = os.path.dirname(os.path.abspath(__file__))
from dados_app import pasta_dados
DADOS = str(pasta_dados())   # nada no C:
ESTADO = os.path.join(DADOS, "estado.json")
PORTA = 47613
BOLA = 64                 # tamanho da bolinha em pixels da interface (o Windows aplica o zoom do monitor)
JW, JH = 550, 660         # janela da conversa, idem (+50 do painel das contas, à esquerda); o Pailer estica pelas bordas
MIN_W, MIN_H = 340, 420
VERSAO = 3
AUMID = "Pandalab.KaniCode"   # o mesmo dos atalhos (atalhos.py): ícone fixado na barra = esta janela
# pasta padrão das conversas: o KANIVETE (ao lado da pasta dos plugins)
# (realpath: aberto pela junção D:\Kanivete\Plugins, o "ao lado" seria D:\Kanivete — pasta que não existe, WinError 267)
PROJETO_PADRAO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), "CANIVETE DO PAILER")
_ESTADO_TRAVA = threading.RLock()


def _ler_estado():
    try:
        with open(ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _gravar_estado(**kw):
    with _ESTADO_TRAVA:
        os.makedirs(DADOS, exist_ok=True)
        try:
            with open(ESTADO, encoding="utf-8") as f:
                e = json.load(f)
        except FileNotFoundError:
            e = {}
        except (OSError, ValueError):   # corrompido: guarda uma cópia antes de regravar (senão sessões e contas sumiam)
            try:
                shutil.copy2(ESTADO, ESTADO + time.strftime(".corrompido-%Y%m%d-%H%M%S"))
            except OSError:
                pass
            e = {}
        e.update(kw)
        tmp = ESTADO + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(e, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ESTADO)


def _tamanho():
    """tamanho guardado da janela (pixels da interface) ou o de fábrica"""
    t = _ler_estado().get("tamanho")
    return (max(MIN_W, int(t[0])), max(MIN_H, int(t[1]))) if t else (JW, JH)


def avisar(cmd):
    """manda um comando à instância aberta; devolve a resposta ou None se não houver nenhuma"""
    try:
        with socket.create_connection(("127.0.0.1", PORTA), timeout=1.5) as s:
            s.sendall(cmd.encode() + b"\n")
            return s.recv(64).decode().strip()
    except OSError:
        return None


class _Aba:
    """uma aba da janela (2026-10-21): conversa e tarefa próprias; várias rodam ao mesmo tempo.
    A aba "1" usa as chaves antigas do estado.json (conversas de antes das abas continuam nela)."""

    def __init__(self, id, quem="claude", nome="", restaurar=False):
        self.id, self.quem, self.nome = str(id), quem, nome
        self.assunto, self.modelo, self.manual = "", "", False
        self.pasta = ""                # pasta de trabalho da aba (2026-10-23: cada aba com a sua)
        self.sessao = None             # Claude Code (sessao.py)
        self.ajudante_ativo = None     # codex/kani/pickle trabalhando
        self.ajudante_trava = threading.Lock()
        self.codex_parar = None
        self.kani_parar = None
        self.modo = "auto"
        self.kani_hist = []
        self.respondendo = False
        self.prontidao_pendente = None
        self.mensagens = Fila(os.path.join(DADOS, "fila", f"aba{self.id}.json"), restaurar)
        self.resposta = ""
        self.pedido_turno = ""
        self.tarefa_agente = None
        self.por_voz = False           # a resposta desta aba volta falada (pedido por voz / minimizou no meio)
        self.codex_comentario, self.codex_lidos, self.codex_falando = "", set(), False         # pedido do turno do Claude em andamento (passagem.py registra no fim)

    def ocupada(self):
        return bool(self.ajudante_ativo or (self.sessao and self.sessao.ocupada))


def _da_aba(nome):
    """atributo da App que é da aba em contexto (a da tarefa que está rodando, ou a aba aberta na janela)"""
    return property(lambda s: getattr(s._ctx(), nome), lambda s, v: setattr(s._ctx(), nome, v))


class App:
    """o que a página da conversa pode chamar (js_api): só os métodos sem _ na frente"""

    _sessao = _da_aba("sessao")
    _ajudante_ativo = _da_aba("ajudante_ativo")
    _ajudante_trava = _da_aba("ajudante_trava")
    _codex_parar = _da_aba("codex_parar")
    _kani_parar = _da_aba("kani_parar")
    _modo = _da_aba("modo")
    _kani_hist = _da_aba("kani_hist")
    _respondendo = _da_aba("respondendo")
    _resposta = _da_aba("resposta")
    _prontidao_pendente = _da_aba("prontidao_pendente")
    _por_voz = _da_aba("por_voz")
    _codex_comentario = _da_aba("codex_comentario")
    _codex_lidos = _da_aba("codex_lidos")
    _codex_falando = _da_aba("codex_falando")

    def __init__(self):
        self._local = threading.local()   # .aba = id da aba da tarefa que roda nesta thread
        e = _ler_estado()
        if e.get("pickle_modelo"):   # modelo grátis escolhido para o Big Pickle (MiniMax, DeepSeek...)
            import opencode_mvp
            opencode_mvp.definir_modelo(e["pickle_modelo"])
        lista = [a for a in (e.get("abas") or []) if isinstance(a, dict) and a.get("id")]
        if not lista:
            lista = [{"id": "1", "quem": e.get("quem") or "claude", "nome": ""}]
        self._abas = {str(a["id"]): _Aba(a["id"], a.get("quem") or "claude", a.get("nome") or "", True) for a in lista}
        for a in lista:   # assunto atual e modelo, para a faixa das abas (2026-10-22)
            ab = self._abas[str(a["id"])]
            ab.assunto, ab.modelo, ab.manual = a.get("assunto") or "", a.get("modelo") or "", bool(a.get("manual"))
            ab.pasta = a.get("pasta") or e.get("projeto") or ""   # antes das pastas por aba: a pasta única de todas
        self._fechadas = {}   # abas fechadas com a tarefa ainda terminando (o fim dela não pode cair noutra aba)
        self._aba_ativa = str(e.get("aba_ativa")) if str(e.get("aba_ativa")) in self._abas else next(iter(self._abas))
        self._bola = None
        self._janela = None
        self._aberta = False
        self._saindo = False
        self._limite = _ler_estado().get("limite")   # o último visto (a cota aparece antes da 1ª resposta)
        self._comandos = []
        self._pendente = None      # "recarregar"/"reiniciar" pedido no meio de uma resposta: roda quando ela terminar
        self._carregado = time.time()   # para o "atualizar" saber o que mudou depois de aberto
        self._mtimes = self._fotografar()   # data de cada arquivo do código: o "atualizar" aplica só o que mudou
        self._voz = None           # voz.py: "Ei Kani" + fala para texto
        self._fala = None          # fala.py: resposta lida em voz alta (pedido por voz com a janela fechada)
        self._estado_voz = ""
        self._microfone_prioritario = False
        self._sons_ativos = bool(_ler_estado().get("sons_bolinha", True))
        self._fala_sempre = bool(_ler_estado().get("fala_sempre", False))   # a bolinha fala também com a janela aberta
        self._prontidao_pendente = None
        # _respondendo/_resposta (por aba): resposta do Claude chegando, para falar o resto se a janela for minimizada
        self._pend = {}            # permissões/perguntas abertas, por id (para o celular, movel.py)

    # ── abas ──
    def _ctx(self):
        i = getattr(self._local, "aba", None)
        return self._abas.get(i) or self._fechadas.get(i) or self._abas[self._aba_ativa]

    def _na_aba(self, aba, fn):
        """fn rodando no contexto da aba (callbacks de threads da tarefa: eventos, fim)"""
        def f(*a, **k):
            antes = getattr(self._local, "aba", None)
            self._local.aba = aba
            try:
                return fn(*a, **k)
            finally:
                self._local.aba = antes
        return f

    def _sufixo(self):
        """chave da conversa da aba no estado.json: a aba 1 usa as chaves antigas"""
        i = self._ctx().id
        return "" if i == "1" else "#aba" + i

    def _alguma_ocupada(self):
        return any(a.ocupada() for a in self._abas.values())

    def _abas_gravar(self):
        _gravar_estado(abas=[{"id": a.id, "quem": a.quem, "nome": a.nome, "assunto": a.assunto, "modelo": a.modelo,
                              "manual": a.manual, "pasta": a.pasta} for a in self._abas.values()],
                       aba_ativa=self._aba_ativa)
        # toda mudança na lista vai na hora para o PC e os celulares (criar/fechar/renomear num aparece no outro)
        self._para_janela(dict(self.abas(), t="abas"))

    def abas(self):
        return {"ativa": self._aba_ativa, "lista": [{"id": a.id, "quem": a.quem, "nome": a.nome, "ocupada": a.ocupada(),
                                                    "assunto": a.assunto, "modelo": a.modelo, "manual": a.manual}
                                                    for a in self._abas.values()]}

    def aba_nova(self, ativar=True):
        # número nunca repetido: a conversa de uma aba fechada não reaparece numa aba nova
        usados = [int(i) for i in list(self._abas) + list(self._fechadas) if i.isdigit()]
        n = max(usados + [int(_ler_estado().get("aba_ultima") or 0)]) + 1
        _gravar_estado(aba_ultima=n)
        self._abas[str(n)] = _Aba(n, self._ctx().quem)
        self._abas[str(n)].pasta = self._ctx().pasta   # a aba nova começa na pasta da que estava aberta
        if ativar:
            self._aba_ativa = str(n)
        self._abas_gravar()
        return dict(self.abas(), ativa=str(n))

    def aba_ativar(self, aba):
        aba = str(aba)
        if aba in self._abas and aba != self._aba_ativa:
            self._aba_ativa = aba
            self._abas_gravar()
            q = self._abas[aba].quem
            self._na_ui(lambda: self._bola and self._bola.definir(quem=q))
        return self.abas()

    def perfil_acesso(self, acao="status", campos=None):
        import perfil_nuvem
        from perfil_acesso import AcessoPerfil
        from google_drive import drive
        with perfil_nuvem._TRAVA:
            return AcessoPerfil(perfil_nuvem.PerfilNuvem(drive)).executar(acao, campos)

    def perfil_nuvem(self, acao="status", escolha="", conferencia="", politica="manter"):
        import perfil_nuvem
        def restaurar(texto, token, modo):
            return self.perfil_restaurar(texto, token, modo)
        return perfil_nuvem.executar(acao, restaurar, escolha, conferencia, politica)

    def perfil_resumo(self):
        import perfil_portatil
        return perfil_portatil.resumo()

    def perfil_exportar(self):
        import perfil_portatil
        return perfil_portatil.exportar()

    def perfil_conferir(self, texto):
        import perfil_portatil
        with _ESTADO_TRAVA:
            return perfil_portatil.previa(texto)

    def perfil_restaurar(self, texto, conferencia, politica="manter"):
        import perfil_portatil
        if self._alguma_ocupada():
            raise ValueError("Espere as tarefas terminarem antes de restaurar o perfil.")
        with _ESTADO_TRAVA:
            return perfil_portatil.aplicar(texto, conferencia, politica)

    def usuario_ler(self):
        import perfil_usuario
        return perfil_usuario.ler()

    def usuario_salvar(self, campos):
        import perfil_usuario
        return perfil_usuario.salvar(campos)

    def cerebro_ler(self):
        import perfil_cerebro
        return perfil_cerebro.ler()

    def cerebro_consultar(self, tema, ambito=None):
        import perfil_cerebro
        return perfil_cerebro.consultar(tema, 10, marcar=False, ambito=ambito)   # o Pailer olhando não conta como uso

    def cerebro_painel(self):
        import perfil_cerebro
        return {"atividade": perfil_cerebro.atividade(25), "revisar": perfil_cerebro.revisar(6),
                "faxina": perfil_cerebro._jler(perfil_cerebro.ARQ_FAXINA, {}),
                "pendencias": len(perfil_cerebro._jler(perfil_cerebro.ARQ_PEND, []))}

    def cerebro_faxina(self):
        import perfil_cerebro
        return perfil_cerebro.faxina()

    def cerebro_descartar(self, ref, motivo):
        import perfil_cerebro
        return perfil_cerebro.descartar(ref, motivo or "descartado pelo Pailer")

    def usuario_foto(self, data_url):
        import perfil_usuario
        return perfil_usuario.foto(data_url)

    def mapa_d_status(self):
        import mapa_d
        return mapa_d.status()

    def mapa_d_buscar(self, busca):
        import mapa_d
        mapa_d.iniciar()
        return mapa_d.buscar(busca, limite=80, pastas=True)

    def mapa_d_listar(self, pasta="D:/"):
        import mapa_d
        if not mapa_d.dentro(pasta, 'D:/'):
            raise ValueError("O mapa cobre apenas o disco D.")
        return mapa_d.listar(pasta, limite=200)

    def consumo(self):
        import consumo
        return consumo.resumo(DADOS)

    # ── painel Projeto (projeto.py: árvore, alterações do git, ler arquivo; só leitura) ──
    def projeto(self, acao, arq=""):
        import projeto
        try:
            f = {"arvore": projeto.arvore, "alteracoes": projeto.alteracoes, "diff": projeto.diff, "ler": projeto.ler,
                 "buscar": projeto.buscar}[acao]
            return f(self._pasta(), arq) if acao != "alteracoes" else f(self._pasta())
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    # ── aba Casa (casa.py: aparelhos Tuya pela rede local) ──
    def casa_estado(self):
        import casa
        try:
            return {"ok": True, "itens": casa.estado()}
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    def casa_alternar(self, nome):
        import casa
        try:
            return casa.alternar(str(nome))
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    def casa_alimentar(self, porcoes=1):
        """só pelo botão da aba Casa, depois da confirmação na tela"""
        import casa, io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = casa.alimentar(int(porcoes or 1), True)
        return {"ok": rc == 0, "texto": buf.getvalue().strip()}

    # ── aba Saúde do PC (saude_pc.py lê o hardware; manutencao.py roda elevado e grava o andamento) ──
    def saude_ler(self):
        import saude_pc
        try:
            return saude_pc.ler()
        except Exception as e:
            return {"ok": False, "erro": f"{type(e).__name__}: {e}"}

    def saude_estado(self):
        import saude_pc
        return saude_pc.estado()

    def saude_iniciar(self, opcoes=None):
        import saude_pc
        o = opcoes or {}
        return saude_pc.iniciar(o.get("etapas"), bool(o.get("completa")), bool(o.get("seco")))

    def saude_parar(self):
        import saude_pc
        return saude_pc.parar()

    def saude_decidir(self, ameacas, offline=False):
        import saude_pc
        return saude_pc.decidir(ameacas, offline)

    def saude_lixeira(self, caminhos):
        """só pela aba, com os duplicados que o Pailer deixou marcados"""
        import saude_pc
        return saude_pc.lixeira(caminhos)

    def todo_listar(self):
        import tarefas
        return tarefas.tarefas.listar()

    def progresso_listar(self):
        import progresso
        return progresso.listar()

    def todo_agente_listar(self):
        from tarefas_agente import TarefasAgente
        return TarefasAgente(DADOS).resumo()

    def todo_agente_contexto(self, id):
        from tarefas_agente import TarefasAgente
        return TarefasAgente(DADOS).obter(id)

    def todo_agente_concluir(self, id, concluida):
        if not isinstance(concluida, bool): raise ValueError('Estado de tarefa inválido.')
        from tarefas_agente import TarefasAgente
        return TarefasAgente(DADOS).estado(id, 'concluida' if concluida else 'pendente', 'Alterado pelo Pailer no to-do.')

    def _todo_agente_fila(self, item):
        if item.get('texto', '').startswith('/'):
            return
        try:
            from tarefas_agente import TarefasAgente
            tarefas=TarefasAgente(DADOS)
            r=tarefas.registrar(self._ctx().id,item['id'],item.get('texto',''),item['quem'],item.get('pasta') or self._pasta())
            estado={'pendente':'pendente','urgente':'pendente','enviando':'em_andamento','falha':'falha','cancelada':'cancelada'}.get(item.get('estado'))
            if estado:
                tarefas.estado(r['id'],estado,item.get('erro',''),automatico=True)
            if item.get('estado')=='enviando': self._ctx().tarefa_agente=r['id']
            self._para_janela({'t':'todo_agente'})
        except Exception as e:
            self._para_janela({'t':'erro','texto':'Não foi possível atualizar o to-do do agente: '+str(e)})

    def _todo_agente_restaurar(self):
        for aba in tuple(self._abas.values()):
            with aba.mensagens.trava:
                itens=list(aba.mensagens.itens)
            for item in itens:
                self._na_aba(aba.id,self._todo_agente_fila)(item)

    def _todo_agente_finalizar(self, ok, texto=''):
        id=self._ctx().tarefa_agente
        if not id: return
        self._ctx().tarefa_agente=None
        try:
            from tarefas_agente import TarefasAgente
            estado='a_conferir' if ok else 'falha'
            if ok and getattr(self,'_modo','auto')=='plan': estado='adiada'
            motivo='Planejamento concluído; execução pendente.' if estado=='adiada' else (
                'Resposta entregue; falta o agente confirmar a conclusão.' if ok else texto)
            TarefasAgente(DADOS).estado(id,estado,motivo,automatico=True)
            self._para_janela({'t':'todo_agente'})
        except Exception as e:
            self._para_janela({'t':'erro','texto':'Não foi possível atualizar o to-do do agente: '+str(e)})

    def todo_salvar(self, titulo, prazo="", id=""):
        import tarefas
        return tarefas.tarefas.salvar(titulo, prazo, id)

    def todo_concluir(self, id, concluida):
        import tarefas
        return tarefas.tarefas.concluir(id, concluida)

    def todo_agenda(self, sincronizar=False):
        import tarefas
        if sincronizar:
            import google_calendar
            if google_calendar.calendar.status().get("conectado"):
                self.google_sincronizar()
        return tarefas.agenda()

    def todo_lembrar(self, titulo, inicio, antes=10):
        import tarefas
        return tarefas.lembrar(titulo, inicio, antes)

    def todo_alarmes(self):
        import tarefas
        return tarefas.alarmes()

    def todo_alarme_salvar(self, id, titulo, inicio="", antes=10, dias=None):
        import tarefas
        return tarefas.alarme_salvar(id, titulo, inicio, antes, dias)

    def todo_alarme_apagar(self, id):
        import tarefas
        return tarefas.alarme_apagar(id)

    def gmail_status(self):
        import google_gmail
        return google_gmail.gmail.status()

    def gmail_importar(self):
        import google_gmail
        arquivos = self._janela.create_file_dialog(webview.FileDialog.OPEN, file_types=('Credenciais Google (*.json)',))
        return google_gmail.gmail.importar(arquivos[0]) if arquivos else google_gmail.gmail.status()

    def gmail_usar_calendar(self):
        import google_gmail
        return google_gmail.gmail.usar_calendar()

    def gmail_conectar(self):
        import google_gmail
        return google_gmail.gmail.conectar()

    def gmail_desconectar(self):
        import google_gmail
        return google_gmail.gmail.desconectar()

    def gmail_buscar(self, busca="", proxima=""):
        import google_gmail
        return google_gmail.gmail.buscar(busca, proxima)

    def gmail_ler(self, id):
        import google_gmail
        return google_gmail.gmail.ler(id)

    def gmail_rascunho(self, para, assunto, texto):
        import google_gmail
        return google_gmail.gmail.rascunho(para, assunto, texto)

    def drive_status(self):
        import google_drive
        return google_drive.drive.status()

    def drive_importar(self):
        import google_drive
        arquivos = self._janela.create_file_dialog(webview.FileDialog.OPEN,
                                                   file_types=('Credenciais Google (*.json)',))
        return google_drive.drive.importar(arquivos[0]) if arquivos else google_drive.drive.status()

    def drive_usar_calendar(self):
        import google_drive
        return google_drive.drive.usar_calendar()

    def drive_conectar(self):
        import google_drive
        return google_drive.drive.conectar()

    def drive_sincronizar(self):
        import google_drive
        return google_drive.drive.sincronizar()

    def drive_buscar(self, busca="", proxima="", pasta="", lixeira=False):
        import google_drive
        return google_drive.drive.buscar(busca, proxima, pasta, lixeira)

    def drive_criar_pasta(self, nome, pasta="root"):
        import google_drive
        return google_drive.drive.criar_pasta(nome, pasta)

    def drive_renomear(self, id, nome):
        import google_drive
        return google_drive.drive.renomear(id, nome)

    def drive_mover(self, id, pasta):
        import google_drive
        return google_drive.drive.mover(id, pasta)

    def drive_lixeira(self, id, restaurar=False):
        import google_drive
        return google_drive.drive.lixeira(id, restaurar)

    def drive_enviar(self, caminho=None, pasta="root"):
        import google_drive
        if caminho is None:
            arquivos = self._janela.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False)
            if not arquivos:
                return {"cancelado": True}
            caminho = arquivos[0]
        return google_drive.drive.enviar(caminho, pasta)

    def drive_baixar(self, id, destino=None, formato=""):
        import google_drive
        if destino is None:
            pastas = self._janela.create_file_dialog(webview.FileDialog.FOLDER)
            if not pastas:
                return {"cancelado": True}
            destino = pastas[0]
        return google_drive.drive.baixar(id, destino, formato)

    def drive_desconectar(self):
        import google_drive
        return google_drive.drive.desconectar()

    def google_status(self):
        import google_calendar
        return google_calendar.calendar.status()

    def google_importar(self):
        import google_calendar
        arquivos = self._janela.create_file_dialog(webview.FileDialog.OPEN,
                                                   file_types=('Credenciais Google (*.json)',))
        return google_calendar.calendar.importar(arquivos[0]) if arquivos else google_calendar.calendar.status()

    def google_conectar(self):
        import google_calendar
        return google_calendar.calendar.conectar(self._google_preparar_avisos)

    def google_sincronizar(self):
        import google_calendar
        resultado = google_calendar.calendar.sincronizar()
        self._google_preparar_avisos()
        return resultado

    def google_selecionar(self, ids, antes=10):
        import google_calendar
        try:
            return google_calendar.calendar.selecionar(ids, antes)
        finally:
            self._google_preparar_avisos()

    def google_desconectar(self):
        import google_calendar
        resultado = google_calendar.calendar.desconectar()
        self._google_preparar_avisos()
        return resultado

    def _google_preparar_avisos(self):
        # Subprocesso evita carregar o sintetizador de voz na janela.
        def preparar():
            import datetime, subprocess
            from pathlib import Path
            from google_calendar import _salvar
            pasta = Path(DADOS) / 'avisos'
            estado = pasta / 'preparar_estado.json'
            try:
                _salvar(estado, {'estado': 'preparando'})
                with (pasta / 'preparar.log').open('a', encoding='utf-8') as log:
                    r = subprocess.run([sys.executable, os.path.join(PASTA, 'compromissos.py'), 'preparar'],
                                       stdout=log, stderr=log, creationflags=0x08000000, timeout=300)
                _salvar(estado, {'estado': 'pronto' if r.returncode == 0 else 'erro',
                                'atualizado': datetime.datetime.now().isoformat()})
            except (OSError, subprocess.TimeoutExpired):
                _salvar(estado, {'estado': 'erro', 'atualizado': datetime.datetime.now().isoformat()})
        threading.Thread(target=preparar, daemon=True).start()

        def faxina_cerebro():
            import subprocess
            from pathlib import Path
            time.sleep(600)
            try:
                with (Path(DADOS) / 'cerebro_faxina.log').open('a', encoding='utf-8') as log:
                    subprocess.run([sys.executable, os.path.join(PASTA, 'perfil_cerebro.py'), 'faxina', '--diaria'],
                                   stdout=log, stderr=log, creationflags=0x08000000 | 0x00004000, timeout=1800)
            except (OSError, subprocess.TimeoutExpired):
                pass
        threading.Thread(target=faxina_cerebro, daemon=True).start()

    def compromissos(self):
        """próximos compromissos com aviso falado (compromissos.py preparar grava a cada 30 min), para o selo da janela"""
        try:
            with open(os.path.join(DADOS, "avisos", "agenda.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def aba_ajudante(self, aba, quem, texto):
        """o Claude de outra aba manda um pedido nesta (vigiar o Big Pickle, 2026-10-22)"""
        if str(aba) not in self._abas:
            raise ValueError("aba não existe")
        return self._na_aba(str(aba), self.ajudante)(quem, texto, _de="claude")

    def aba_parar(self, aba):
        if str(aba) not in self._abas:
            raise ValueError("aba não existe")
        return self._na_aba(str(aba), self.parar)()

    def aba_renomear(self, aba, nome, manual=True):
        if str(aba) in self._abas:
            a = self._abas[str(aba)]
            a.nome = str(nome or "").strip()[:40]
            a.manual = bool(manual and a.nome)
            self._abas_gravar()
        return True

    def aba_assunto(self, aba, assunto=None, modelo=None):
        """o assunto atual (frase curta do último pedido) e o modelo em uso, mostrados na aba"""
        a = self._abas.get(str(aba))
        if a:
            if assunto is not None:
                a.assunto = str(assunto).strip()[:80]
            if modelo is not None:
                a.modelo = str(modelo).strip()[:60]
            self._abas_gravar()
        return True

    def aba_fechar(self, aba):
        """fecha a aba (a conversa fica guardada no disco); a tarefa dela é parada"""
        aba = str(aba)
        if aba not in self._abas or len(self._abas) < 2:
            return self.abas()
        self._na_aba(aba, self.parar)()
        self._na_aba(aba, self._encerrar)()
        ids = list(self._abas)
        self._fechadas[aba] = self._abas.pop(aba)
        self._fechadas[aba].mensagens.esquecer()   # recados não entregues saem junto com a aba
        if self._aba_ativa == aba:
            self._aba_ativa = ids[max(0, ids.index(aba) - 1)] if ids[0] != aba else ids[1]
        self._abas_gravar()
        return self.abas()

    # ── js_api ──
    def mostrar(self):
        if not self._janela:
            return
        ja = self._aberta
        if not ja:
            self._janela.move(*self._perto_da_bola())
        self._janela.show()
        self._janela.restore()
        self._aberta = True
        self._encaixe_ligar()
        ocupada = self._alguma_ocupada()
        self._na_ui(lambda: self._bola and self._bola.definir(aberta=True, estado="trabalhando" if ocupada else ""))
        if not ja:
            self._encaixar()

    # ── KaniBall dentro do chat (2026-10-22, pedido do Pailer): ao abrir, a bolinha pula para cima da faixa de status
    # e a cópia em HTML (ui/kaniball.js) fica espiando com o alto da cabeça para fora; ao recolher, volta ao lugar ──
    def _doca_ligada(self):
        return bool(_ler_estado().get("doca", True)) and self._bola is not None

    def _doca_ponto(self):
        """onde a bolinha nativa fica (pixels reais) para coincidir com a da página; None se a página não respondeu"""
        try:
            r = self._janela.evaluate_js("window.kbDocaAlvo ? kbDocaAlvo() : null")
        except Exception:
            return None
        if not r:
            return None
        wx, wy, _, _ = self.tam_inicio()
        k, b = float(r.get("dpr") or 1), self._bola
        return round(wx + r["x"] * k) - b.margem, round(wy + r["y"] * k) - b.margem

    def _encaixar(self):
        # reinício pelo botão (2026-10-23): o chat abre junto com a ENTRADA da bolinha (voo de 3,4 s) e com a página
        # ainda carregando (sem kbDocaAlvo) — desistia na 1ª tentativa e a bolinha ficava fora. Espera as duas (até 10 s)
        ponto, fim = None, time.time() + 10
        while time.time() < fim:
            if not self._aberta or not self._doca_ligada() or self._bola.na_doca:
                return
            if not self._bola._voo:
                time.sleep(0.12)   # a janela acabou de aparecer: o layout da página assenta
                ponto = self._doca_ponto()
                if ponto:
                    break
            time.sleep(0.2)
        if not ponto or not self._aberta:
            return
        b = self._bola
        if not b._voo:
            self._bola_casa = (b.x, b.y)

        def pousou():   # na thread da interface: a página mostra a cópia e só então a nativa some
            def trocar():
                try:
                    self._janela.evaluate_js("window.kbDoca && kbDoca(true)")
                except Exception:
                    pass
                self._na_ui(lambda: self._aberta and b.esconder())
                self._doca_ultimo = None
                self._na_ui(self._doca_sync)
            threading.Thread(target=trocar, daemon=True).start()
        self._som_bolinha("entrada_chat")
        self._na_ui(lambda: b.voar(ponto, pousou))

    def _desencaixar(self, voar=True, depois=None):
        """a cópia da página sobe, a nativa aparece no mesmo lugar e (voar) volta para onde estava"""
        b = self._bola
        if not b or not b.na_doca:
            if depois:
                self._na_ui(depois)
            return
        if voar:
            self._som_bolinha("saida_chat")
        try:
            self._janela.evaluate_js("window.kbDoca && kbDoca(false)")
        except Exception:
            pass
        time.sleep(0.22)   # a subida da cópia (kaniball.js SOBE_MS)
        ponto = self._doca_ponto() or (b.x, b.y)
        casa = getattr(self, "_bola_casa", None) or ponto
        done = threading.Event()

        def sair_da_doca():
            b.mostrar_em(*ponto)
            done.set()
        self._na_ui(sair_da_doca)
        done.wait(1)
        try:
            self._janela.evaluate_js("window.kbDoca && kbDoca('fora')")
        except Exception:
            pass
        if voar:
            self._na_ui(lambda: b.voar(casa, depois))
        elif depois:
            self._na_ui(depois)

    def _doca_sync(self):
        """(thread da interface) manda à cópia da página a cara/estado da bolinha, quando muda"""
        b = self._bola
        if not b or not b.na_doca:
            return
        d = {"expr": b.expressao(), "estado": b.estado, "voz": b.voz, "quem": b.quem,
             "humor_ate": max(0.0, b._humor_ate - time.time()) if b.humor else 0}
        if d == getattr(self, "_doca_ultimo", None):
            return
        self._doca_ultimo = d
        if d["humor_ate"]:   # a comemoração acaba sozinha: avisa a cópia quando voltar à cara de antes
            threading.Timer(d["humor_ate"] + 0.05, lambda: self._na_ui(self._doca_sync)).start()
        js = "window.kbDocaEstado && kbDocaEstado(%s)" % json.dumps(d)
        threading.Thread(target=lambda: self._janela.evaluate_js(js), daemon=True).start()

    def rosto_quadros(self, expressao):
        """quadros do rosto 8-bit (rosto.py) a 10 por segundo, para a cópia da bolinha desenhar igual"""
        import rosto
        dur = 2.8 if expressao == "concluido" else 8.4
        return {"fps": 10, "quadros": [rosto.quadro(expressao, i / 10) for i in range(int(dur * 10))]}

    def bola_clique(self):
        """clique na cópia dentro do chat = o mesmo da bolinha: recolhe"""
        threading.Thread(target=self.esconder, daemon=True).start()

    # ── tamanho: a janela é sem moldura, então as bordas são desenhadas no HTML e o redimensionar vem por aqui ──
    def _encaixe_ligar(self):
        """Win + setas encaixam a janela (encaixe.py); "encaixe": false no estado desliga. Pode repetir."""
        if not _ler_estado().get("encaixe", True):
            return
        def ligar():
            try:
                import encaixe
                encaixe.ligar(self._hwnd())
            except Exception as ex:
                print("encaixe:", ex, file=sys.stderr)
        self._na_ui(ligar)

    def _hwnd(self):
        return int(self._janela.native.Handle.ToInt64())

    def tam_inicio(self):
        """retângulo atual da janela em pixels físicos [x, y, w, h]"""
        import ctypes
        from ctypes import wintypes
        r = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(self._hwnd(), ctypes.byref(r))
        return [r.left, r.top, r.right - r.left, r.bottom - r.top]

    def tam_mudar(self, x, y, w, h):
        import ctypes
        k = self._bola.escala if self._bola else 1
        w, h = max(int(w), int(MIN_W * k)), max(int(h), int(MIN_H * k))
        ctypes.windll.user32.SetWindowPos(self._hwnd(), 0, int(x), int(y), w, h, 0x0004 | 0x0010)   # NOZORDER | NOACTIVATE

    def tam_fim(self, extra=0):
        """guarda o tamanho sem as colunas laterais abertas (extra = quanto elas somam agora)"""
        k = self._bola.escala if self._bola else 1
        _, _, w, h = self.tam_inicio()
        _gravar_estado(tamanho=[round(w / k - float(extra or 0)), round(h / k)])

    def _area(self):
        """área útil do monitor da janela (pixels físicos): esquerda, direita"""
        import ctypes
        from ctypes import wintypes

        class MI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        mi = MI(); mi.cbSize = ctypes.sizeof(MI)
        mon = ctypes.windll.user32.MonitorFromWindow(self._hwnd(), 2)
        ctypes.windll.user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        return mi.rcWork.left, mi.rcWork.right

    def crescer(self, esq, dir):
        """abre/fecha uma coluna lateral PARA FORA: a janela ganha (ou perde) esq px à esquerda e dir px à direita,
        num deslize curto, sem sair da tela"""
        import ctypes
        k = self._bola.escala if self._bola else 1
        x, y, w, h = self.tam_inicio()
        de, dd = int(float(esq) * k), int(float(dir) * k)
        nx, nw = x - de, max(int(MIN_W * k), w + de + dd)
        try:
            l, r = self._area()
            if nx + nw > r:
                nx = r - nw
            nx = max(l, nx)
        except Exception:
            pass
        for i in range(1, 8):
            t = i / 7
            t = 1 - (1 - t) ** 3
            ctypes.windll.user32.SetWindowPos(self._hwnd(), 0, int(x + (nx - x) * t), y, int(w + (nw - w) * t), h, 0x0004 | 0x0010)
            time.sleep(0.012)
        return True

    def painel_espaco(self, largura=270):
        """Abre espaço para as ferramentas sem reduzir uma janela maior ou sair do monitor."""
        if self.maximizada() or getattr(self, '_imagem_tela_cheia', False):
            return False
        k = self._bola.escala if self._bola else 1
        largura = max(270, min(1600, float(largura)))
        x, y, w, h = self.tam_inicio()
        esquerda, direita = self._area()
        alvo = max(w, min(round((JW + largura) * k), direita - esquerda))
        if alvo <= w:
            return False
        x = max(esquerda, min(x, direita - alvo))
        self.tam_mudar(x, y, alvo, h)
        return True

    def tarefas_ler(self, arquivos):
        """andamento das tarefas em segundo plano do Claude Code: última linha da saída e o código de saída quando acaba"""
        r = {}
        for a in (arquivos or [])[:20]:
            if not str(a).lower().endswith(".output"):
                continue
            try:
                tam = os.path.getsize(a)
                with open(a, "rb") as f:
                    f.seek(max(0, tam - 8192))
                    fim = f.read().decode("utf-8", "replace")
            except OSError:
                r[a] = {"falta": True}
                continue
            m = re.search(r"\[exited with code (-?\d+)\]\s*$", fim)
            linhas = [l.strip() for l in re.sub(r"\[exited with code -?\d+\]\s*$", "", fim).replace("\r", "\n").split("\n") if l.strip()]
            r[a] = {"tail": "\n".join(linhas[-3:])[-400:], "fim": int(m.group(1)) if m else None, "kb": round(tam / 1024)}
        return r

    def expandir(self, on):
        """⤢ janela grande (diffs e saídas inteiros): ocupa quase o monitor inteiro; de novo = volta ao retângulo de antes"""
        import ctypes
        from ctypes import wintypes

        class MI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        if on:
            self._antes = self.tam_inicio()
            mi = MI(); mi.cbSize = ctypes.sizeof(MI)
            ctypes.windll.user32.GetMonitorInfoW(ctypes.windll.user32.MonitorFromWindow(self._hwnd(), 2), ctypes.byref(mi))
            a = mi.rcWork
            k = self._bola.escala if self._bola else 1
            m = int(24 * k)
            w = min(int(1280 * k), a.right - a.left - 2 * m)
            r = [a.left + (a.right - a.left - w) // 2, a.top + m, w, a.bottom - a.top - 2 * m]
        else:
            r = getattr(self, "_antes", None)
            if not r:
                return False
            self._antes = None
        ctypes.windll.user32.SetWindowPos(self._hwnd(), 0, *map(int, r), 0x0004 | 0x0010)
        return bool(on)

    def maximizar(self, on):
        """botão ⤢: maximiza de verdade (a tela toda, como Win+cima); de novo = volta ao tamanho de antes"""
        import ctypes
        ctypes.windll.user32.ShowWindow(self._hwnd(), 3 if on else 9)   # SW_MAXIMIZE | SW_RESTORE
        return self.maximizada()

    def maximizada(self):
        import ctypes
        return bool(ctypes.windll.user32.IsZoomed(self._hwnd()))

    def tam_padrao(self):
        """duplo clique no canto: volta ao tamanho de fábrica, ao lado da bolinha"""
        _gravar_estado(tamanho=None)
        self._janela.resize(JW, JH)
        self._janela.move(*self._perto_da_bola())

    # ── voz (voz.py): "Ei Kani" acorda, a fala vai para a conversa ──
    def voz(self, on=None):
        """liga/desliga o Ei Kani (None = só diz o estado). Fica gravado: abre ligado da próxima vez."""
        if on is None:
            return {"on": bool(self._voz and self._voz.ligada)}
        if on:
            try:
                if not self._voz:
                    from voz import Voz
                    self._voz = Voz(self._voz_acordou, self._voz_texto, self._voz_estado)
                self._voz.ligar()
                threading.Thread(target=self._fala_obj().carregar, daemon=True).start()   # 1ª resposta sem espera
            except Exception as e:
                return {"on": False, "erro": str(e)}
        elif self._voz:
            self._voz.desligar()
            if self._fala:
                self._fala.soltar()
            self._na_ui(lambda: self._bola and self._bola.definir(voz=""))
        _gravar_estado(voz=bool(on))
        return {"on": bool(on)}

    def ouvir(self, fim=False, cancelar=False):
        """botão do microfone na caixa de texto: ouve um pedido sem "Ei Kani" (fim=True: terminou de falar;
        cancelar=True: o ✕ descarta a gravação)"""
        try:
            if cancelar:
                if self._voz:
                    self._voz.cancelar()
                return {"ok": True}
            if fim:
                if self._voz:
                    self._voz.terminar()
                return {"ok": True}
            if not self._voz:
                from voz import Voz
                self._voz = Voz(self._voz_acordou, self._voz_texto, self._voz_estado)
            self._microfone_fala(True)
            if self._voz.escutar() is False:
                self._microfone_fala(False)
                return {"ok": False, "erro": "Não foi possível abrir o microfone."}
            return {"ok": True}
        except Exception as e:
            self._microfone_fala(False)
            return {"ok": False, "erro": str(e)}

    def _microfone_fala(self, ativo):
        mudou = self._microfone_prioritario != bool(ativo)
        self._microfone_prioritario = bool(ativo)
        if self._fala:
            self._fala.pausar(self._microfone_prioritario)
        if mudou:
            self._para_janela({"t": "microfone_prioridade", "ativo": self._microfone_prioritario})

    def _voz_acordou(self):
        # a janela fica como está: fechada, a conversa é toda por voz (a bolinha mostra o rosto ouvindo)
        self._microfone_fala(True)

    def _voz_estado(self, e):
        self._estado_voz = e
        if e in ("ouvindo", "transcrevendo"):
            self._microfone_fala(True)
        elif e != "escutando" or not (self._voz and getattr(self._voz, "_seguir", 0)):
            self._microfone_fala(False)
        if e in ("ouvindo", "transcrevendo"):
            from sons_bolinha import parar
            parar()
        b = {"escutando": "escutando", "ouvindo": "ouvindo", "transcrevendo": "pensando"}.get(e, "")
        self._na_ui(lambda: self._bola and self._bola.definir(voz=b))
        self._para_janela({"t": "voz", "fase": e})

    def _voz_texto(self, texto):
        # pedido por voz com a janela fechada: a resposta volta falada (fala.py), frase a frase enquanto é escrita
        self._por_voz = not self._aberta
        self._para_janela({"t": "voz", "fase": "texto", "texto": texto})

    def _fala_obj(self):
        if not self._fala:
            from fala import Fala
            self._fala = Fala(self._fala_estado)
            self._fala.pausar(self._microfone_prioritario)
        return self._fala

    def _fala_estado(self, e):
        if self._microfone_prioritario and e == "falando":
            return
        if e in ("fim", ""):
            self._para_janela({"t": "voz", "fase": "fala_fim"})   # a janela apaga o 🔊 da mensagem lida
        if e == "falando":
            from sons_bolinha import parar
            parar()
        if e == "fim":   # terminou de falar a resposta: ouve o próximo pedido sem "Ei Kani" (janela fechada)
            if not self._microfone_prioritario and not self._aberta and not self._ocupada():   # chat minimizado = conversa por voz, mesmo com o Ei Kani desligado
                try:
                    if not self._voz:
                        from voz import Voz
                        self._voz = Voz(self._voz_acordou, self._voz_texto, self._voz_estado)
                    from voz import SEGUIR_S
                    self._voz.escutar(SEGUIR_S)
                except Exception:
                    pass
            return
        b = "falando" if e == "falando" else ("escutando" if self._voz and self._voz.ligada else "")
        self._na_ui(lambda: self._bola and self._bola.definir(voz=b))

    def esconder(self, focar=False):
        """focar: veio do Ctrl+Q — a bolinha fica com o teclado (outro Ctrl+Q fecha o KaniCode)"""
        if not self._aberta and not focar:
            return
        b = self._bola
        if b and b.na_doca:
            def voltou():
                if focar:
                    b.focar()
            self._desencaixar(True, voltou)
            if self._janela:
                self._janela.hide()
        else:
            if self._janela:
                self._janela.hide()
            if focar and b:
                self._na_ui(b.focar)
        self._aberta = False
        self._na_ui(lambda: self._bola and self._bola.definir(aberta=False))
        if self._ajudante_ativo == "codex":
            self._codex_ler(self._codex_comentario)
        # minimizou com a resposta ainda chegando (pedido escrito): o resto vira voz, a partir da mensagem atual
        if self._respondendo and not self._por_voz:
            try:
                f = self._fala_obj()
                self._por_voz = True
                f.novo()
                if self._resposta:
                    f.pedaco(self._resposta)
            except Exception:
                self._por_voz = False

    def _falar_agora(self):
        """a resposta vira voz: pedido por voz, janela minimizada ou "Falar sempre" ligado"""
        # Falar sempre vale para a aba à vista: duas abas falando ao mesmo tempo embaralhavam as frases
        return self._por_voz or (self._fala_sempre and self._ctx().id == self._aba_ativa)

    def fala_sempre(self, on=None):
        """liga/desliga "Falar sempre" (None = só diz o estado); desligado, só fala com a janela minimizada"""
        if on is not None:
            self._fala_sempre = bool(on)
            _gravar_estado(fala_sempre=self._fala_sempre)
            if self._fala_sempre:
                threading.Thread(target=self._fala_obj().carregar, daemon=True).start()   # 1ª resposta sem espera
            elif self._fala and self._aberta and not self._por_voz:
                self._fala.parar()
        return self._fala_sempre

    def falar_texto(self, texto):
        """botão 🔊 de uma mensagem: lê o texto com a voz da Kani (de novo = para)"""
        try:
            f = self._fala_obj()
            if f.falando:
                f.parar()
                return {"ok": True, "falando": False}
            f.novo()
            f.pedaco(str(texto or ""))
            f.terminar()
            return {"ok": True, "falando": True}
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    def sons_acoes(self, on=None):
        if on is not None:
            self._sons_ativos = bool(on)
            _gravar_estado(sons_bolinha=self._sons_ativos)
            if not self._sons_ativos:
                from sons_bolinha import parar
                parar()
        return self._sons_ativos

    def bola_som_envio(self):
        """Gravação do Pailer junto da animação de envio ao GitHub."""
        return self._som_bolinha("git_push")

    def _som_bolinha(self, acao):
        if not self._sons_ativos or self._estado_voz in ("ouvindo", "transcrevendo"):
            return False
        if self._fala and self._fala.falando:
            return False
        from sons_bolinha import tocar
        return tocar(acao)

    def fixar(self, on):
        """janela sempre por cima (alfinete)"""
        if self._janela:
            # O pywebview altera TopMost diretamente; a ponte chama fora da thread da interface.
            self._na_ui(lambda: setattr(self._janela, "on_top", bool(on)))
        _gravar_estado(fixa=bool(on))
        return bool(on)

    def info(self):
        e = _ler_estado()
        return {"versao": VERSAO, "pasta": self._pasta(), "fixa": bool(e.get("fixa", True)), "limite": self._limite,
                "pastas_internas": [PROJETO_PADRAO, PASTA],
                "ocupada": self._ocupada(), "comandos": self._comandos,
                "modelo": e.get("modelo") or "", "cota_codex": e.get("cota_codex"), "quem": self._ctx().quem, "aba": self._ctx().id,
                "modo": getattr(self, "_modo", "auto")}

    def codex_identidade(self):
        import codex_conta, avatares
        conta = codex_conta.identidade()
        if conta.get("ok"):
            email = conta.get("email", "").strip().casefold()
            conta["foto"] = avatares.fotos([email]).get(email) if email else None
        return conta

    def codex_limites(self, forcar=False):
        import codex_conta
        r = codex_conta.consultar(bool(forcar))
        if r.get("ok"):
            _gravar_estado(cota_codex=r["cota"])
        return r

    def codex_redefinir(self, tentativa, credito=""):
        import codex_conta
        r = codex_conta.redefinir(tentativa, credito)
        if r.get("cota"):
            _gravar_estado(cota_codex=r["cota"])
        return r

    def codigo_revisar(self):
        import codigo_agente
        if self._ocupada():
            return {"ok": False, "mensagem": "Acompanhe os passos na conversa; espere a tarefa terminar para revisar o diff."}
        agente = self._ctx().quem
        try:
            with codigo_agente.TRAVA:
                ctx = codigo_agente.Contexto(self._pasta(), agente).carregar()
                r = ctx.revisar()
                r["verificacao"] = ctx.verificar()
                r["ok"] = True
                r["pode_aplicar"] = bool(r["arquivos"]) and not r["aplicada"] and r["verificacao"]["ok"] and getattr(self, "_modo", "auto") != "plan"
                if r.get("testes") and not r["testes"]["ok"]:
                    r["pode_aplicar"] = False
                return r
        except (ValueError, OSError) as e:
            return {"ok": False, "mensagem": str(e)}

    def codigo_aplicar(self, agente, revisao):
        import codigo_agente
        if self._ocupada() or getattr(self, "_modo", "auto") == "plan":
            return {"ok": False, "mensagem": "Termine a tarefa e saia de Planejar antes de aplicar."}
        if agente != self._ctx().quem:
            return {"ok": False, "mensagem": "O agente selecionado mudou; abra a revisão novamente."}
        try:
            with codigo_agente.TRAVA:
                return codigo_agente.Contexto(self._pasta(), agente).carregar().aplicar(str(revisao))
        except (ValueError, OSError) as e:
            return {"ok": False, "mensagem": str(e)}

    def opencode_info(self):
        import opencode_mvp
        return opencode_mvp.info()

    def pickle_modelo(self, modelo=None):
        """Modelo gratuito do OpenCode usado pelo Big Pickle (MiniMax, DeepSeek...). Sem argumento, consulta."""
        import opencode_mvp
        if modelo:
            _gravar_estado(pickle_modelo=opencode_mvp.definir_modelo(modelo))
        else:
            opencode_mvp.definir_modelo(_ler_estado().get("pickle_modelo") or opencode_mvp.MODELO)
        return opencode_mvp.info()

    def opencode_testar(self, texto):
        import opencode_mvp
        return opencode_mvp.testar(texto)

    def gpu_info(self):
        """Telemetria do PC, solicitada pela interface apenas no modo Kani visível."""
        import gpu
        return gpu.info()

    # ── contas do Claude (contas.py): salvas, com apelido e e-mail; troca MANUAL ──
    def _contas(self):
        e = _ler_estado()
        lista = e.get("contas") or []
        if not any(c["id"] == "principal" for c in lista):
            lista.insert(0, {"id": "principal", "apelido": "Principal"})
        return lista, e.get("conta") or "principal"

    def contas_listar(self):
        lista, ativa = self._contas()
        return self._contas_com_fotos(lista, ativa)

    def _contas_com_fotos(self, lista, ativa):
        import avatares
        fotos = avatares.fotos(c.get("email") for c in lista)
        # Fotos só na resposta da API; não duplicar base64 no estado nem nas credenciais.
        return {"lista": [dict(c, foto=fotos.get((c.get("email") or "").strip().casefold())) for c in lista], "ativa": ativa}

    def conta_atualizar(self, conta_id=None):
        """lê e-mail, plano e cotas (sem gastar tokens) de uma conta ou de todas; guarda no estado"""
        import contas
        lista, ativa = self._contas()
        for c in lista:
            if conta_id and c["id"] != conta_id:
                continue
            st = contas.status(c["id"])
            c.update(email=st.get("email", ""), plano=st.get("plano", ""), logado=st.get("logado", False))
            if c["logado"]:
                c["cotas"] = contas.cotas(c["id"])
        # a mesma conta duas vezes (mesmo e-mail): mostra uma só — a em uso; senão uma salva (a "Principal" segue o
        # login do PC e pode mudar por fora; as salvas têm login próprio e ficam). Nada é apagado: as outras só somem.
        por = {}
        for c in lista:
            c.pop("igual", None)
            c.pop("oculta", None)
            if c.get("logado") and c.get("email"):
                por.setdefault(c["email"].lower(), []).append(c)
        for grupo in por.values():
            if len(grupo) > 1:
                fica = next((x for x in grupo if x["id"] == ativa), None) \
                    or next((x for x in grupo if x["id"] != "principal"), grupo[0])
                fica["cotas"] = max(grupo, key=lambda x: (x.get("cotas") or {}).get("lido") or 0).get("cotas")
                for c in grupo:
                    if c is not fica:
                        c["oculta"] = True
        _gravar_estado(contas=lista)
        return self._contas_com_fotos(lista, ativa)

    def conta_adicionar(self, apelido):
        import contas, re as _re
        apelido = (apelido or "").strip() or "Conta"
        lista, ativa = self._contas()
        base = _re.sub(r"[^a-z0-9]+", "-", apelido.lower()).strip("-") or "conta"
        cid, n = base, 2
        while any(c["id"] == cid for c in lista) or cid == "principal":
            cid, n = f"{base}-{n}", n + 1
        lista.append({"id": cid, "apelido": apelido})
        _gravar_estado(contas=lista)
        contas.abrir_login(cid, apelido)
        return {"id": cid, "lista": lista, "ativa": ativa}

    def conta_entrar_de_novo(self, conta_id):
        import contas
        lista, _ = self._contas()
        c = next((x for x in lista if x["id"] == conta_id), None)
        return bool(c) and contas.abrir_login(conta_id, c["apelido"])

    def conta_renomear(self, conta_id, apelido):
        lista, ativa = self._contas()
        for c in lista:
            if c["id"] == conta_id and (apelido or "").strip():
                c["apelido"] = apelido.strip()[:40]
        _gravar_estado(contas=lista)
        return self._contas_com_fotos(lista, ativa)

    def conta_remover(self, conta_id):
        import contas
        lista, ativa = self._contas()
        if conta_id == "principal":
            return self._contas_com_fotos(lista, ativa)
        contas.remover(conta_id)
        lista = [c for c in lista if c["id"] != conta_id]
        if ativa == conta_id:
            ativa = "principal"
            self._encerrar()
        _gravar_estado(contas=lista, conta=ativa)
        return self._contas_com_fotos(lista, ativa)

    def conta_usar(self, conta_id):
        """troca manual: a próxima mensagem já vai pela conta escolhida, na MESMA conversa"""
        lista, ativa = self._contas()
        if conta_id == ativa or not any(c["id"] == conta_id for c in lista):
            return self._contas_com_fotos(lista, ativa)
        if self._sessao and self._sessao.ocupada:
            raise RuntimeError("espere a resposta terminar para trocar de conta")
        self._encerrar()
        c = next(c for c in lista if c["id"] == conta_id)
        self._limite = c.get("cotas")
        _gravar_estado(conta=conta_id, limite=self._limite)
        return self._contas_com_fotos(lista, conta_id)

    # ── falar direto com um ajudante ("Quem responde": Codex ou Kani) ──
    def quem(self, nome):
        nome = nome if nome in ("claude", "codex", "kani", "pickle") else "claude"
        self._ctx().quem = nome
        _gravar_estado(quem=nome)
        self._abas_gravar()
        self.bola_quem(nome)
        return True

    def bola_quem(self, nome):
        """selo do agente selecionado, junto do rosto animado"""
        self._na_ui(lambda: self._bola and self._bola.definir(quem=nome if nome in ("claude", "codex", "kani", "pickle") else "claude"))
        return True

    # ── conversa da Kani: vai para a mesma conversa da janela (trocar Kani ⇄ Claude não apaga) e o Claude lê depois ──
    def _kani_arquivo(self, pasta, so_previa=False):
        """antes de existir conversa do Claude nesta pasta, a da Kani fica à parte (entra na dele na 1ª mensagem)"""
        pasta = pasta + self._sufixo()
        sid = None if so_previa else (_ler_estado().get("sessoes") or {}).get(pasta)
        if sid:
            return os.path.join(DADOS, "conversas", sid + ".jsonl")
        import hashlib
        return os.path.join(DADOS, "conversas_kani", hashlib.md5(os.path.normcase(pasta).encode()).hexdigest()[:12] + ".jsonl")

    def _kani_guardar(self, pasta, eventos, pedido, resposta):
        try:
            with _ESTADO_TRAVA:
                a = self._kani_arquivo(pasta)
                os.makedirs(os.path.dirname(a), exist_ok=True)
                with open(a, "a", encoding="utf-8") as f:
                    for ev in eventos:
                        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                nv = _ler_estado().get("kani_nao_visto") or {}
                k = pasta + self._sufixo()
                nv[k] = ((nv.get(k) or []) + [{"pedido": pedido, "resposta": resposta}])[-8:]
                _gravar_estado(kani_nao_visto=nv)
        except OSError:
            pass

    def _kani_previa(self, pasta, tirar=False):
        a = self._kani_arquivo(pasta, so_previa=True)
        try:
            with open(a, encoding="utf-8") as f:
                evs = [json.loads(l) for l in f if l.strip()]
        except (OSError, ValueError):
            return []
        if tirar:
            try:
                os.remove(a)
            except OSError:
                pass
        return evs

    def _kani_para_claude(self, pasta):
        """trocas com a Kani que o Claude ainda não viu: vão junto da próxima mensagem (o Pailer não vê o bloco)"""
        with _ESTADO_TRAVA:
            nv = _ler_estado().get("kani_nao_visto") or {}
            trocas = nv.pop(pasta + self._sufixo(), None)
            if not trocas:
                return ""
            _gravar_estado(kani_nao_visto=nv)
        linhas = "\n".join(f"Pailer: {t['pedido']}\nKani: {t['resposta']}" for t in trocas)
        return ("[Contexto do KaniCode, o Pailer não vê este bloco: antes desta mensagem ele conversou com a Kani (modo Kani, "
                "modelo local). Últimas trocas:\n" + linhas + "\nPassos/ferramentas de cada pedido: "
                + os.path.join(DADOS, "kani_modo.jsonl") + "]\n\n")

    def _comando_conclusao(self, texto, de="pc"):
        import unicodedata
        t = re.sub(r"\s*\(por voz\)\s*$", "", texto or "", flags=re.I)
        t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if not unicodedata.combining(c))
        t = re.sub(r"[.!?,;:]", "", t)
        t = " ".join(t.split())
        if t not in ("/concluir", "tarefa concluida", "concluir tarefa", "concluir a tarefa",
                     "pode concluir a tarefa", "finalizamos a tarefa", "tarefa finalizada") or self._ocupada():
            return False
        self._para_janela({"t": "eco_eu", "texto": texto, "de": de, "minis": []})
        self._na_ui(lambda: self._bola and self._bola.definir(humor="concluido", segundos=2.8))
        self._para_janela({"t": "local", "acao": "aviso", "texto": "Tarefa concluída! 👍"})
        return True

    def _casa_rapido(self, texto, de):
        """casa (casa.py): "apaga a cozinha", "alimenta os gatos" → executa na hora, sem IA (~0,5 s, como a Alexa)"""
        if texto.strip().startswith("/"):
            return False
        try:
            import casa
            r = casa.rapido(texto)
        except Exception:
            return False
        if not r:
            return False
        self._para_janela({"t": "local", "acao": "aviso", "texto": "🏠 " + r})
        if "(por voz)" in texto and de == "pc":
            try:
                f = self._fala_obj()
                f.novo()
                f.pedaco(r)
                f.terminar()
            except Exception:
                pass
        return True

    def janela_diagnostico(self, etapa, mensagem=""):
        """Falhas da janela e entrada na ponte, sem copiar o pedido para o diagnóstico."""
        try:
            os.makedirs(DADOS, exist_ok=True)
            ev = {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "etapa": str(etapa)[:100],
                  "mensagem": str(mensagem)[:1500],
                  "aba": getattr(getattr(self, '_local', None), 'aba', None) or getattr(self, '_aba_ativa', None)}
            with open(os.path.join(DADOS, "janela_diagnostico.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return True

    def ajudante(self, quem, texto, _de="pc"):
        self.janela_diagnostico("ajudante.recebido", quem)
        try:
            return self._ajudante_iniciar(quem, texto, _de)
        except Exception as erro:
            self.janela_diagnostico("ajudante.erro", str(erro))
            raise

    def kani_execucao(self, acao, id="", chave="", concedida=False, informacao=""):
        """Ponte da revisão humana; não é ferramenta disponível ao modelo."""
        import kani_modo
        from kani_estado import Estado
        from kani_etapas import construir
        estado = Estado(kani_modo.DADOS)
        pasta = self._pasta()
        if acao == "listar":
            return [{"t":"kani_checkpoint", "execucao":t["id"], "status":t["status"],
                     "pedido":t["pedido"][:200], "pergunta":t.get("pergunta"), "aprovacao":t.get("aprovacao")}
                    for t in estado.listar(pasta) if t["status"] != "concluida"]
        t = estado.obter(id)
        if os.path.normcase(os.path.abspath(t["pasta"])) != os.path.normcase(os.path.abspath(pasta)):
            raise PermissionError("Execução pertence a outra pasta.")
        if self._ocupada():
            raise RuntimeError("Espere a tarefa terminar antes de retomar ou aprovar.")
        if acao == "aprovar":
            t = construir(kani_modo, pasta).autorizar(id, chave, concedida)
            if not concedida:
                self._para_janela({"t":"kani_checkpoint", "execucao":id, "status":"negada"})
                return True
        elif acao != "retomar":
            raise ValueError("Use listar, aprovar ou retomar.")
        return self._ajudante_iniciar("kani", t["pedido"], _execucao=id, _informacao=informacao)

    def _ajudante_iniciar(self, quem, texto, _de="pc", _execucao=None, _informacao=None):
        import ajudantes
        if quem not in ("codex", "kani", "pickle"):
            raise ValueError("ajudante desconhecido")
        if not texto or not texto.strip():
            return False
        if self._casa_rapido(texto, _de):
            return False
        if self._comando_conclusao(texto, _de):
            return True
        if self._ocupada() or not self._ajudante_trava.acquire(blocking=False):
            raise RuntimeError("Espere a resposta terminar ou use Parar antes de enviar outra demanda.")
        # a mensagem aparece também nos outros aparelhos (pedido por voz no celular aparecia só a resposta)
        self._para_janela({"t": "eco_eu", "texto": texto, "de": _de, "minis": []})
        self._ajudante_ativo = quem
        pasta = self._pasta()   # não deixar uma troca de pasta mudar o destino no meio da tarefa
        editar = getattr(self, "_modo", "auto") != "plan"
        aba = self._ctx().id
        if quem == "codex":
            self._codex_parar = threading.Event()
        self._prontidao_agendar()
        passou = self._passagem_pendente(quem)   # trocou de agente: o novo recebe o que os outros fizeram nesta aba

        def evento_codex(ev):
            if ev.get("sessao"):
                self._codex_guardar(pasta, ev["sessao"])
            self._evento(ev)

        def rodar():
            por_voz = self._por_voz
            resposta = None
            try:
                self._bola_estado("trabalhando")
                if quem == "codex":
                    r = ajudantes.codex(passou + texto, pasta, editar=editar, ao_evento=self._na_aba(aba, evento_codex),
                                        retomar=self._codex_id(pasta), parar=self._codex_parar)
                    if r.get("sessao"):
                        self._codex_guardar(pasta, r["sessao"])
                    self._codex_registrar(pasta, texto, r)
                elif quem == "pickle":
                    r = self._pickle_rodar(texto, pasta, por_voz, editar, passou)
                else:   # modo Kani: em etapas (kani_modo.py), com a conversa recente como contexto
                    import kani_modo
                    self._kani_parar = threading.Event()
                    passos, vistos = [], []

                    def ev(e):   # guarda os passos para o registro (D:/Kanivete/KaniCode/kani_modo.jsonl)
                        if e.get("t") in ("ferr", "ferr_fim"):
                            passos.append({k: e.get(k) for k in ("t", "nome", "entrada", "ok", "saida") if e.get(k) is not None})
                            vistos.append(dict(e))
                        self._evento(e)
                    hist = getattr(self, "_kani_hist", [])
                    if passou:
                        hist = hist + [{"role": "user", "content": passou.strip()}, {"role": "assistant", "content": "Entendi, continuo daí."}]
                    extras = {"retomar":_execucao, "informacao":_informacao} if _execucao else {}
                    r = kani_modo.rodar(texto, pasta, self._na_aba(aba, ev), hist, por_voz, self._kani_parar, editar=editar, **extras)
                    try:   # registro de cada pedido do modo Kani: o Claude lê depois para achar limitações
                        with open(os.path.join(DADOS, "kani_modo.jsonl"), "a", encoding="utf-8") as f:
                            f.write(json.dumps({"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "pedido": texto, "voz": por_voz,
                                                "passos": passos, "resposta": r.get("texto"), "claude": r.get("claude"),
                                                "ok": r.get("ok"), "ms": r.get("ms"), "tokens": r.get("tokens")}, ensure_ascii=False) + chr(10))
                    except Exception:
                        pass
                    if r.get("claude"):   # mantém o pedido e as evidências da continuação local
                        self._kani_hist = []
                        self._para_janela({"t": "ajudante_resposta", "quem": "kani", "ok": True, "tokens": r["tokens"],
                                           "texto": "O fluxo local precisa do Claude; encaminhando o pedido." + (f" ({r['texto']})" if r["texto"] else "")})
                        self._bola_atividade("")
                        self._para_janela({"t": "local", "acao": "quem", "quem": "claude"})
                        self.enviar(texto + r.get("passagem", ""))
                        return
                    self._kani_hist = (getattr(self, "_kani_hist", []) + [{"role": "user", "content": texto},
                                                                          {"role": "assistant", "content": r["texto"]}])[-20:]
                    self._kani_guardar(pasta, [{"t": "eu", "texto": texto}] + vistos +
                                       [{"t": "ajudante_resposta", "quem": "kani", "texto": r["texto"], "ok": r["ok"]}],
                                       texto, r["texto"])
                    self._bola_atividade("")
                    if por_voz or self._falar_agora():   # pedido por voz (ou Falar sempre): a resposta volta falada
                        f = self._fala_obj()
                        f.novo()
                        f.pedaco(r["texto"])
                        f.terminar()
                        self._por_voz = False
                resposta = {"t": "ajudante_resposta", "quem": quem, "texto": r["texto"], "ok": r["ok"],
                            "tokens": r["tokens"], "uso": r.get("uso")}
                if r.get("texto"):
                    import passagem
                    passagem.registrar(DADOS, pasta + self._sufixo(), quem, texto, r["texto"])
                self._na_ui(lambda: self._bola and self._bola.definir(humor="feliz" if r["ok"] else "erro", segundos=3))
            except Exception as e:
                resposta = {"t": "ajudante_resposta", "quem": quem, "texto": str(e), "ok": False, "tokens": 0}
            finally:
                self._prontidao_cancelar()
                if quem == "codex" and resposta is not None:
                    resposta["cancelado"] = bool(self._codex_parar and self._codex_parar.is_set())
                self._ajudante_ativo = None
                self._codex_parar = None
                if resposta:
                    self._codex_voz(resposta)
                self._ajudante_trava.release()
                if resposta:
                    self._todo_agente_finalizar(resposta.get('ok') is True and not resposta.get('cancelado'), resposta.get('texto',''))
                    self._para_janela(resposta)   # só liberar a caixa da janela depois de liberar o motor
                self._bola_atividade("")
                self._bola_estado("" if self._aberta else "pergunta")
                if self._pendente:
                    threading.Timer(1.5, self._pendente_rodar).start()
                self._fila_tentar()
        try:
            threading.Thread(target=self._na_aba(aba, rodar), daemon=True).start()
        except Exception:
            self._prontidao_cancelar()
            self._ajudante_ativo = None
            self._codex_parar = None
            self._ajudante_trava.release()
            raise
        return True

    def _passagem_pendente(self, destino):
        """o que outro agente fez nesta aba e `destino` ainda não viu (troca de agente sem perder o fio)"""
        try:
            import passagem
            # só conta como visto quando o agente responde (registrar): falha no envio não perde o contexto
            return passagem.pendente(DADOS, self._pasta() + self._sufixo(), destino, marcar=False)
        except Exception:
            return ""

    def _ocupada(self):
        return bool(self._ajudante_ativo or (self._sessao and self._sessao.ocupada))

    def _pickle_arquivo(self, pasta, nova=False):
        import uuid
        chave = os.path.normcase(os.path.realpath(pasta)) + self._sufixo()
        with _ESTADO_TRAVA:
            sessoes = _ler_estado().get("pickle_sessoes") or {}
            sid = sessoes.get(chave, "")
            if nova or not re.fullmatch(r"[a-f0-9]{32}", sid):
                sid = uuid.uuid4().hex
                sessoes[chave] = sid
                _gravar_estado(pickle_sessoes=sessoes)
        return os.path.join(DADOS, "conversas_pickle", sid + ".jsonl")

    def _pickle_historico(self, pasta):
        try:
            with open(self._pickle_arquivo(pasta), encoding="utf-8") as f:
                eventos = []
                for linha in deque(f, maxlen=400):
                    try:
                        ev = json.loads(linha)
                        if isinstance(ev, dict):
                            eventos.append(ev)
                    except ValueError:
                        continue
                return eventos
        except OSError:
            return []

    def _pickle_rodar(self, texto, pasta, por_voz, editar, passou=""):
        import bigpickle_modo
        self._kani_parar = threading.Event()
        vistos = []
        historico = []
        for ev in self._pickle_historico(pasta):
            if ev.get("t") == "eu":
                historico.append({"role": "user", "content": ev.get("texto", "")})
            elif ev.get("t") == "ajudante_resposta":
                historico.append({"role": "assistant", "content": ev.get("texto", "")})

        def evento(ev):
            if ev.get("t") in ("ferr", "ferr_fim", "pickle_progresso", "codigo_alteracao", "codigo_pronto"):
                vistos.append(dict(ev))
            self._evento(ev)

        import pickle_agente
        ponte = pickle_agente.rota_ponte(texto, [h["content"] for h in historico if h["role"] == "user"])
        if passou:   # trocou de agente: o que os outros fizeram entra como a troca mais recente
            historico = historico[-14:] + [{"role": "user", "content": passou.strip()}, {"role": "assistant", "content": "Entendi, continuo daí."}]
        if ponte:   # mexer no KANIVETE, sites, disco, arte (e a continuação deles): a ponte em etapas
            evento = self._na_aba(self._ctx().id, evento)
            r = bigpickle_modo.rodar(ponte, pasta, evento, historico[-16:], por_voz, self._kani_parar, editar)
        else:   # código e conversa: o OpenCode nativo, numa cópia isolada (pickle_agente.py)
            r = pickle_agente.rodar(texto, pasta, self._na_aba(self._ctx().id, evento), historico[-16:], por_voz, self._kani_parar,
                                    editar and getattr(self, "_modo", "auto") != "plan")
        eventos = [{"t": "eu", "texto": texto}] + vistos + [
            {"t": "ajudante_resposta", "quem": "pickle", "texto": r["texto"], "ok": r["ok"], "tokens": r["tokens"],
             "orcamento":r.get("orcamento"), "etapas_concluidas":r.get("etapas_concluidas")}]
        with _ESTADO_TRAVA:
            arquivo = self._pickle_arquivo(pasta)
            os.makedirs(os.path.dirname(arquivo), exist_ok=True)
            with open(arquivo, "a", encoding="utf-8") as f:
                for ev in eventos:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if por_voz or self._falar_agora():
            fala = self._fala_obj()
            fala.novo()
            fala.pedaco(r["texto"])
            fala.terminar()
            self._por_voz = False
        return r

    def _codex_id(self, pasta):
        chave = os.path.normcase(os.path.realpath(pasta)) + self._sufixo()
        return (_ler_estado().get("codex_sessoes") or {}).get(chave)

    def _codex_guardar(self, pasta, sessao):
        chave = os.path.normcase(os.path.realpath(pasta)) + self._sufixo()
        with _ESTADO_TRAVA:
            sessoes = _ler_estado().get("codex_sessoes") or {}
            if sessoes.get(chave) != sessao:
                sessoes[chave] = sessao
                _gravar_estado(codex_sessoes=sessoes)

    def _codex_registrar(self, pasta, texto, r):
        """Histórico para a janela; medidas separadas sem copiar prompts para a telemetria."""
        try:
            with _ESTADO_TRAVA:
                os.makedirs(DADOS, exist_ok=True)
                medida = {k: r.get(k) for k in ("sessao", "ok", "uso", "tokens", "ms", "primeiro_evento_ms",
                                               "esforco", "cancelado", "estourou")}
                medida.update(quando=time.strftime("%Y-%m-%d %H:%M:%S"), pasta=pasta,
                              comandos=len(r.get("comandos") or []))
                with open(os.path.join(DADOS, "codex_uso.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(medida, ensure_ascii=False) + "\n")
                sid = r.get("sessao")
                if not sid or not re.fullmatch(r"[a-fA-F0-9-]{36}", sid):
                    return
                diretorio = os.path.join(DADOS, "conversas_codex")
                os.makedirs(diretorio, exist_ok=True)
                with open(os.path.join(diretorio, sid + ".jsonl"), "a", encoding="utf-8") as f:
                    progresso = [{"t": "codex_progresso", "texto": t, "reiniciar": i == 0}
                                 for i, t in enumerate(r.get("progresso") or [])]
                    for ev in [{"t": "eu", "texto": texto}, *progresso, *(r.get("alteracoes") or []),
                               {"t": "ajudante_resposta", "quem": "codex", "texto": r["texto"], "ok": r["ok"]}]:
                        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except OSError:
            pass   # falha de registro não deve esconder uma resposta que já terminou

    def habilidades(self):
        """o que sabemos fazer, para o painel 🧰: guias e ferramentas do KANIVETE (Instructions/mapa.json) + skills"""
        out = {"kanivete": [], "ferramentas": [], "scripts": []}
        try:
            with open(os.path.join(PROJETO_PADRAO, "Instructions", "mapa.json"), encoding="utf-8") as f:
                m = json.load(f)
            out["kanivete"] = []
            for k, v in (m.get("guias") or {}).items():
                # o 1º parágrafo vira o resumo e os títulos das seções entram na busca (achar "legenda" na Legenda Premium)
                g = {"caminho": k, "titulo": v}
                try:
                    with open(os.path.join(PROJETO_PADRAO, k), encoding="utf-8") as f:
                        txt = f.read(60000)
                    linhas = txt.splitlines()
                    g["secoes"] = " ".join(l.lstrip("#").strip() for l in linhas if l.startswith("#"))[:3000]
                    corpo = [l.strip() for l in linhas[1:40] if l.strip() and not l.startswith(("#", "|", "-", "`", ">"))]
                    g["resumo"] = (corpo[0] if corpo else "")[:220]
                except OSError:
                    pass
                out["kanivete"].append(g)
            out["ferramentas"] = [{"id": x.get("id"), "nome": x.get("nome"), "grupo": x.get("grupo"),
                                   "guias": x.get("guias") or [], "testes": x.get("testes") or []} for x in m.get("ferramentas") or []]
            out["scripts"] = [{"caminho": k, "titulo": v} for k, v in (m.get("tools") or {}).items()]
        except Exception as e:
            out["erro"] = str(e)
        return out

    # ── mensagens aguardam o término; só a urgência explícita interrompe o turno ──
    def mensagens_fila(self):
        return self._ctx().mensagens.listar()

    def mensagem_enviar(self, id_, texto, imagens=None, quem=None):
        return self._na_aba(self._ctx().id, self._mensagem_enviar)(id_, texto, imagens, quem)

    def _mensagem_enviar(self, id_, texto, imagens=None, quem=None):
        texto = str(texto or '').strip()
        if not texto and not imagens:
            return False
        if not isinstance(id_, str) or not id_ or len(id_) > 80:
            raise ValueError('identificador de mensagem inválido')
        a = self._ctx()
        quem = quem or a.quem
        if quem not in ('claude', 'codex', 'kani', 'pickle'):
            raise ValueError('agente desconhecido')
        if quem == 'pickle' and (imagens or (texto.startswith('/') and texto.split()[0] not in ('/clear', '/nova', '/new'))):
            raise ValueError('Big Pickle recebe texto e os comandos de nova conversa')
        item, nova = a.mensagens.adicionar({'id': id_, 'texto': texto, 'imagens': imagens or [],
                                           'quem': quem, 'pasta': self._pasta()})
        if nova:
            self._fila_evento(item)
            self._fila_tentar()
        return a.mensagens.visivel(item)

    def _fila_evento(self, item):
        self._todo_agente_fila(item)
        self._para_janela({'t': 'fila_mensagem', **self._ctx().mensagens.visivel(item)})

    def mensagem_urgente(self, id_):
        return self._na_aba(self._ctx().id, self._mensagem_urgente)(id_)

    def _mensagem_urgente(self, id_):
        fila = self._ctx().mensagens
        # O término do turno não pode despachar a urgente antes de pedirmos a interrupção do anterior.
        with fila.trava:
            item, interromper = fila.urgente(id_)
            if not item:
                return False
            if interromper:
                if self._ocupada():
                    self.parar(preservar_fila=True)
                elif fila.enviando:
                    fila.interromper_apos_envio = True
        self._fila_evento(item)
        self._fila_tentar()
        return True

    def mensagem_cancelar(self, id_):
        return self._na_aba(self._ctx().id, self._mensagem_cancelar)(id_)

    def _mensagem_cancelar(self, id_):
        item = self._ctx().mensagens.cancelar(id_)
        if not item:
            return False
        self._fila_evento(item)
        self._fila_tentar()   # se ela pausava a fila (falha), a próxima segue
        return True

    def _fila_tentar(self):
        a = self._ctx()
        with a.mensagens.trava:
            if a.ocupada():
                return
            item = a.mensagens.proxima()
        if not item:
            return
        self._fila_evento(item)

        def entregar():
            ok, erro = False, ''
            try:
                if self._abas.get(a.id) is not a or a.mensagens.pausada:
                    raise RuntimeError('A aba foi fechada ou a entrega foi pausada antes do envio.')
                if os.path.normcase(os.path.realpath(item['pasta'])) != os.path.normcase(os.path.realpath(self._pasta())):
                    raise RuntimeError('A pasta do projeto mudou; a mensagem não foi entregue em outra pasta.')
                if a.quem != item['quem']:
                    self.quem(item['quem'])
                if item['quem'] != 'claude' and not item['texto'].startswith('/') and not item['imagens']:
                    ok = bool(self.ajudante(item['quem'], item['texto'], _de='fila'))
                else:
                    ok = bool(self.enviar(item['texto'], item['imagens'], _de='fila'))
                if not ok:
                    erro = 'O motor não confirmou o recebimento da mensagem.'
            except Exception as e:
                erro = str(e)
            finally:
                if a.mensagens.interromper_apos_envio:
                    a.mensagens.interromper_apos_envio = False
                    if a.ocupada():
                        self.parar(preservar_fila=True)
                a.mensagens.concluir(item, ok, erro)
                self._fila_evento(item)
                if ok:
                    if not a.ocupada():
                        self._para_janela({'t': 'fila_livre'})
                    self._fila_tentar()   # comandos locais e respostas rápidas podem terminar antes desta confirmação
        try:
            threading.Thread(target=self._na_aba(a.id, entregar), daemon=True).start()
        except Exception as e:
            a.mensagens.concluir(item, False, str(e))
            self._fila_evento(item)

    # ── conversa (sessao.py) ──
    def enviar(self, texto, imagens=None, _de="pc"):
        texto = (texto or "").strip()
        if not texto and not imagens:
            return False
        if not imagens and self._comando_conclusao(texto, _de):
            return True
        # a mensagem aparece também nos outros aparelhos abertos (janela do PC × celular, movel.py)
        self._para_janela({"t": "eco_eu", "texto": texto, "de": _de, "minis": [i.get("mini") for i in imagens or [] if i.get("mini")]})
        if not imagens and self._casa_rapido(texto, _de):
            return False   # resolvido aqui: a janela não fica esperando resposta
        # comandos que o próprio KaniCode resolve (os outros "/" vão para o Claude Code como no terminal)
        cmd, _, arg = texto.partition(" ")
        if cmd in ("/clear", "/nova", "/new"):
            self.nova()
            self._para_janela({"t": "local", "acao": "recarregar"})
            return True
        if cmd == "/pasta":
            self._para_janela({"t": "local", "acao": "pasta"})
            return True
        if cmd == "/model" and arg.strip():
            _gravar_estado(modelo=arg.strip())
            self._encerrar()   # a próxima mensagem abre o Claude Code com o modelo novo (a conversa continua)
            self._para_janela({"t": "local", "acao": "aviso", "texto": f"Modelo trocado para {arg.strip()}."})
            return True
        if not self._sessao:
            from sessao import Sessao
            sid = (_ler_estado().get("sessoes") or {}).get(self._pasta() + self._sufixo())
            self._sessao = Sessao(self._pasta(), DADOS, self._na_aba(self._ctx().id, self._evento), sessao_id=sid)
            self._sessao.modelo = _ler_estado().get("modelo") or None
            self._sessao.conta = _ler_estado().get("conta") or None
            self._sessao.modo = getattr(self, "_modo", "auto")
        self._bola_estado("trabalhando")
        if not self._respondendo:
            self._respondendo, self._resposta = True, ""
        pasta = self._pasta()
        if not self._sessao.sessao_id:   # conversa nova: o que a Kani falou antes entra no começo dela
            self._sessao._pendentes = self._kani_previa(pasta, tirar=True) + (getattr(self._sessao, "_pendentes", None) or [])
        contexto = "" if texto.startswith("/") else self._kani_para_claude(pasta) + self._passagem_pendente("claude")
        if not texto.startswith('/'):
            from tarefas_agente import contexto as contexto_tarefas
            contexto += '\n\n' + contexto_tarefas(pasta,texto)
        self._ctx().pedido_turno = "" if texto.startswith("/") else texto
        if not texto.startswith("/"):
            self._prontidao_agendar()
        try:
            self._sessao.enviar(texto, imagens, contexto=contexto)
        except Exception as e:
            self._prontidao_cancelar()
            self._respondendo = False
            self._bola_estado("")
            self._para_janela({"t": "saiu", "erro": str(e)})
            return False
        return True

    def responder_pergunta(self, pedido_id, entrada, respostas):
        """múltipla escolha: {texto da pergunta: rótulo escolhido (vários = separados por vírgula)}"""
        ok = bool(self._sessao and self._sessao.responder_pergunta(pedido_id, entrada, respostas))
        self._bola_estado("trabalhando")
        return ok

    def responder(self, pedido_id, permitir, entrada=None):
        """cartão de permissão: Permitir / Recusar"""
        ok = bool(self._sessao and self._sessao.responder(pedido_id, permitir, entrada))
        self._bola_estado("trabalhando")
        return ok

    def sempre(self, add=None, tirar=None):
        """"Permitir sempre" do cartão (git push, git commit…): lista guardada em DADOS/sempre.json"""
        import sessao
        return sessao.sempre(DADOS, add, tirar)

    def preparar(self):
        """abre o Claude Code já ao mostrar a janela (a lista de comandos "/" e a 1ª resposta chegam mais rápido)"""
        if not self._sessao:
            from sessao import Sessao
            sid = (_ler_estado().get("sessoes") or {}).get(self._pasta() + self._sufixo())
            self._sessao = Sessao(self._pasta(), DADOS, self._na_aba(self._ctx().id, self._evento), sessao_id=sid)
            self._sessao.modelo = _ler_estado().get("modelo") or None
            self._sessao.conta = _ler_estado().get("conta") or None
            self._sessao.modo = getattr(self, "_modo", "auto")
        if not self._sessao.vivo():
            try:
                self._sessao._abrir()
            except Exception as e:
                self._para_janela({"t": "saiu", "erro": str(e)})
        return self._comandos

    def parar(self, preservar_fila=False):
        self._todo_agente_finalizar(False, 'Interrompida; o pedido original continua disponível para retomar.')
        if not preservar_fila:
            with self._ctx().mensagens.trava:
                self._ctx().mensagens.pausada = True
        self._prontidao_cancelar()
        parar = self._codex_parar
        if parar:
            parar.set()
        if self._fala:
            self._fala.parar()
        if getattr(self, "_kani_parar", None):
            self._kani_parar.set()
        if self._sessao:
            self._sessao.parar()
        return True

    _IMG = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

    def miniatura(self, caminho, lado=900):
        """print na conversa: a imagem reduzida como dataURL (None se não for imagem ou não existir)"""
        try:
            from recursos_resposta import caminho as resolver
            caminho = resolver(caminho, self._pasta())
            lado = max(64, min(1200, int(lado)))
            if not caminho.lower().endswith(self._IMG) or not os.path.isfile(caminho):
                return None
            import base64, io
            from PIL import Image
            with Image.open(caminho) as im:
                im.thumbnail((lado, lado))
                buf = io.BytesIO()
                if im.mode in ("RGBA", "LA", "P"):
                    im.convert("RGBA").save(buf, "PNG", optimize=True)
                    tipo = "png"
                else:
                    im.convert("RGB").save(buf, "JPEG", quality=85)
                    tipo = "jpeg"
            return f"data:image/{tipo};base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return None

    def abrir_imagem(self, caminho):
        if caminho.lower().endswith(self._IMG) and os.path.isfile(caminho):
            os.startfile(caminho)
        return True

    def resposta_abrir_caminho(self, caminho):
        import recursos_resposta as recursos
        return recursos.abrir_caminho(caminho, self._pasta())

    # ── navegador dentro da janela (navegador_painel.py + ui/navegador.js): KaniBrowser encaixado à direita ──
    _nav_trava = threading.Lock()

    def _nav(self):
        with self._nav_trava:   # o HTML chama nav_area/nav_abrir/favoritos juntos: um painel só (eram dois → tela branca)
            return self._nav_criar()

    def _nav_criar(self):
        if not getattr(self, "_nav_painel", None):
            import navegador, navegador_painel
            navegador._ponte(self._pasta())
            self._nav_painel = navegador_painel.Painel(sys.modules["kanibrowser"], self._hwnd(), self._na_ui)
        return self._nav_painel

    def nav_abrir(self, largura=0):
        """abre o painel; largura > 0 = a janela cresce para a direita esse tanto (px da página) antes"""
        if float(largura or 0) > 0 and not self.maximizada():
            self.crescer(0, largura)
        try:
            return self._nav().abrir()
        except Exception as e:
            return {"erro": str(e)}

    def nav_fechar(self, largura=0):
        self._nav().fechar()
        if float(largura or 0) > 0 and not self.maximizada():
            self.crescer(0, -float(largura))
        return True

    def nav_area(self, x, y, w, h, largura=0):
        return self._nav().area(x, y, w, h, largura)

    def nav_estado(self):
        try:
            return self._nav().estado()
        except Exception as e:
            return {"erro": str(e), "abas": []}

    def nav_favoritos(self, op="listar", a=None):
        """barra de favoritos do painel: listar / salvar (☆, alterna) / remover / renomear / ordenar"""
        try:
            import navegador_painel
            self._nav()
            return navegador_painel.favoritos(op, a)
        except Exception as e:
            return {"erro": str(e)}

    def nav_cmd(self, o, a=None):
        """ir/nova/mostrar/fechar_aba/acao/foco/print na aba mostrada do painel"""
        p = self._nav()
        try:
            if o == "print":
                return {"caminho": p.print_aba(os.path.join(DADOS, "anexos", "paginas"))}
            if o in ("ir", "nova", "mostrar", "fechar_aba", "acao", "aparelho"):
                return getattr(p, o)(a) if a is not None else getattr(p, o)()
            if o == "foco":
                return p.foco()
        except Exception as e:
            return {"erro": str(e)}
        return {"erro": "comando desconhecido: " + str(o)}

    def resposta_navegador(self, navegador=None):
        if navegador is not None:
            if navegador not in ('chrome', 'padrao'):
                raise ValueError('Navegador inválido.')
            _gravar_estado(navegador_links=navegador)
        return {'navegador': _ler_estado().get('navegador_links') or 'chrome'}

    def resposta_abrir_link(self, url):
        import recursos_resposta as recursos
        return recursos.abrir_link(url, self.resposta_navegador()['navegador'])

    def resposta_copiar_texto(self, texto):
        import recursos_resposta as recursos
        return recursos.copiar_texto(texto)

    def resposta_imagem(self, origem):
        import recursos_resposta as recursos
        return recursos.imagem_dados(origem, self._pasta())

    def resposta_tela_cheia(self, on):
        on = bool(on)
        if self._janela and on != getattr(self, '_imagem_tela_cheia', False):
            self._janela.toggle_fullscreen()
            self._imagem_tela_cheia = on
        return bool(getattr(self, '_imagem_tela_cheia', False))

    def resposta_copiar_imagem(self, origem):
        import recursos_resposta as recursos
        return recursos.copiar_imagem(origem, self._pasta())

    def resposta_salvar_imagem(self, origem):
        import recursos_resposta as recursos
        dados, info = recursos.imagem(origem, self._pasta())
        ext = os.path.splitext(info['nome'])[1]
        destino = self._janela.create_file_dialog(webview.FileDialog.SAVE, save_filename=info['nome'],
                                                 file_types=(f'Imagem (*{ext})', 'Todas as imagens (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp)'))
        if not destino:
            return False
        if not isinstance(destino, str):
            destino = destino[0]
        return recursos.salvar_imagem(dados, info, destino)

    def modo(self, modo):
        """botão Planejar: 'plan' = o Claude só planeja e pede aprovação; 'auto' = trabalha normal"""
        modo = "plan" if modo == "plan" else "auto"
        self._modo = modo
        if self._sessao:
            self._sessao.definir_modo(modo)
        return modo

    def nova(self):
        """conversa nova nesta pasta (a anterior continua guardada)"""
        if self._ocupada():
            raise RuntimeError("Espere a resposta terminar ou use Parar antes de abrir outra conversa.")
        if self._ctx().quem == "pickle":
            self._pickle_arquivo(self._pasta(), nova=True)
            return True
        if self._ctx().quem == "codex":
            with _ESTADO_TRAVA:
                sessoes = _ler_estado().get("codex_sessoes") or {}
                sessoes.pop(os.path.normcase(os.path.realpath(self._pasta())) + self._sufixo(), None)
                _gravar_estado(codex_sessoes=sessoes)
            return True
        self._encerrar()
        e = _ler_estado()
        ss = e.get("sessoes") or {}
        ss.pop(self._pasta() + self._sufixo(), None)
        nv = e.get("kani_nao_visto") or {}
        nv.pop(self._pasta() + self._sufixo(), None)
        _gravar_estado(sessoes=ss, kani_nao_visto=nv)
        self._kani_previa(self._pasta(), tirar=True)
        self._kani_hist = []
        return True

    def historico(self):
        if self._ctx().quem == "pickle":
            return self._pickle_historico(self._pasta())
        if self._ctx().quem == "codex":
            sid = self._codex_id(self._pasta())
            if not sid or not re.fullmatch(r"[a-fA-F0-9-]{36}", sid):
                return []
            try:
                with open(os.path.join(DADOS, "conversas_codex", sid + ".jsonl"), encoding="utf-8") as f:
                    eventos = []
                    for linha in deque(f, maxlen=400):
                        try:
                            eventos.append(json.loads(linha))
                        except ValueError:
                            continue
                    return eventos
            except OSError:
                return []
        previa = self._kani_previa(self._pasta())   # conversa com a Kani antes de haver uma do Claude
        sid = (_ler_estado().get("sessoes") or {}).get(self._pasta() + self._sufixo())
        if not sid:
            return previa
        from sessao import Sessao
        return previa + Sessao(self._pasta(), DADOS, None, sessao_id=sid).historico()

    def escolher_pasta(self):
        """só a aba aberta troca de pasta (as outras seguem trabalhando). Pasta nova ainda não confiada volta como
        {"confiar": caminho}: a janela pergunta e chama definir_pasta(caminho, True)."""
        if self._ocupada():
            return None
        r = self._janela.create_file_dialog(webview.FileDialog.FOLDER, directory=self._pasta())
        if not r:
            return None
        nova = os.path.normpath(r[0] if isinstance(r, (list, tuple)) else r)
        if not self._confiavel(nova):
            return {"confiar": nova}
        return self.definir_pasta(nova)

    def definir_pasta(self, caminho, confiar=False):
        if self._ocupada() or not caminho or not os.path.isdir(caminho):
            return None
        caminho = os.path.normpath(caminho)
        if confiar:
            with _ESTADO_TRAVA:
                lista = [c for c in (_ler_estado().get("pastas_confiaveis") or []) if isinstance(c, str)]
                if not self._confiavel(caminho):
                    _gravar_estado(pastas_confiaveis=lista + [caminho])
        elif not self._confiavel(caminho):
            return {"confiar": caminho}
        if os.path.normcase(caminho) != os.path.normcase(self._pasta()):
            self._encerrar()
            self._ctx().pasta = caminho
            self._abas_gravar()
        return caminho

    def _confiavel(self, caminho):
        """como o Claude Code: pasta dentro de uma já confiada (ou das do próprio app) não pergunta de novo"""
        alvo = os.path.normcase(os.path.realpath(caminho))
        base = [PROJETO_PADRAO, PASTA, _ler_estado().get("projeto") or ""] + list(_ler_estado().get("pastas_confiaveis") or [])
        for b in base:
            if not b:
                continue
            b = os.path.normcase(os.path.realpath(b))
            if alvo == b or alvo.startswith(b.rstrip("\\/") + os.sep):
                return True
        return False

    def remover_pasta(self):
        if self._ocupada():
            return False
        self._encerrar()
        self._ctx().pasta = PROJETO_PADRAO
        self._abas_gravar()
        return True

    def reiniciar(self):
        """Reabre o KaniCode; tarefas em andamento terminam antes do reinício."""
        return self._pedir("reiniciar")

    def sair(self):
        self._saindo = True
        if self._bola and self._bola.na_doca:   # dentro do chat: sai dele e a despedida parte dali
            self._desencaixar(False)
        try:   # o chat some na hora; só a KaniBall faz a despedida (2026-10-21, pedido do Pailer)
            self._janela.hide()
            self._aberta = False
        except Exception:
            pass
        self._encerrar_todas()
        try:   # a Kani direta roda neste processo: sai da placa de vídeo junto
            import ajudantes
            ajudantes.kani_parar()
        except Exception:
            pass
        terminou = threading.Event()
        self._na_ui(lambda: self._bola.sair(terminou.set) if self._bola else terminou.set())
        terminou.wait(self._bola.duracao_saida + 0.7 if self._bola else 0)
        self._na_ui(lambda: self._bola and self._bola.fechar())
        try:
            self._janela.destroy()
        except Exception:
            pass

    # ── internos ──
    def _pasta(self):
        p = self._ctx().pasta
        return p if p and os.path.isdir(p) else PROJETO_PADRAO

    def _encerrar(self):
        self._prontidao_cancelar()
        parar = self._codex_parar
        if parar:
            parar.set()
        if self._sessao:
            s, self._sessao = self._sessao, None
            threading.Thread(target=s.fechar, daemon=True).start()
        self._bola_estado("")

    def _encerrar_todas(self):
        for a in list(self._abas):
            self._na_aba(a, self._encerrar)()

    def _prontidao_cancelar(self):
        pendente, self._prontidao_pendente = self._prontidao_pendente, None
        if pendente:
            pendente[0].set()
            pendente[1].cancel()

    def _prontidao_agendar(self):
        self._prontidao_cancelar()
        if self._aberta and not self._falar_agora():
            return
        cancelado = threading.Event()
        aba = self._ctx()
        def valido():
            trabalhando = aba.ajudante_ativo or aba.respondendo or (aba.sessao and aba.sessao.ocupada)
            return not cancelado.is_set() and self._abas.get(aba.id) is aba and bool(trabalhando) and (not self._aberta or self._falar_agora())
        def confirmar():
            if valido():
                try:
                    self._fala_obj().prontidao(valido)
                except Exception:
                    pass  # mensagem opcional; a tarefa continua normalmente
        temporizador = threading.Timer(1.0, self._na_aba(self._ctx().id, confirmar))
        temporizador.daemon = True
        self._prontidao_pendente = (cancelado, temporizador)
        temporizador.start()

    def _codex_ler(self, texto):
        texto = (texto or "").strip()
        if (self._aberta and not self._falar_agora()) or not texto or texto in self._codex_lidos:
            return
        if self._codex_parar and self._codex_parar.is_set():
            return
        try:
            fala = self._fala_obj()
            if not self._codex_falando:
                fala.novo()
                self._codex_falando = True
            fala.dizer(texto)
            self._codex_lidos.add(texto)
        except Exception as erro:
            self._para_janela({"t": "voz", "fase": "erro:" + str(erro)})

    def _codex_voz(self, ev):
        t = ev.get("t")
        if (t in ("codex_progresso", "pickle_progresso") and ev.get("texto")) or (t == "texto" and ev.get("d")) or t in ("ajudante_resposta", "fim", "saiu", "permissao", "pergunta"):
            self._prontidao_cancelar()
        if t == "ajudante" and ev.get("quem") == "codex" and ev.get("fase") == "inicio":
            self._codex_comentario = ""
            self._codex_lidos = set()
            self._codex_falando = False
        elif t == "codex_progresso" and ev.get("concluido"):
            self._codex_comentario = ev.get("texto") or ""
            self._codex_ler(self._codex_comentario)
        elif t == "ajudante_resposta" and ev.get("quem") == "codex":
            try:
                if not ev.get("cancelado"):
                    self._codex_ler(ev.get("texto"))
                if self._codex_falando and self._fala and not ev.get("cancelado"):
                    self._fala.terminar()
            except Exception as erro:
                self._para_janela({"t": "voz", "fase": "erro:" + str(erro)})
            finally:
                self._codex_falando = False
                self._codex_comentario = ""
                self._por_voz = False

    def _evento(self, ev):
        self._codex_voz(ev)
        t = ev.get("t")
        if t not in ("texto", "pensando", "kani_pensando"):   # passos ao vivo para o Claude acompanhar (2026-10-21)
            try:
                os.makedirs(DADOS, exist_ok=True)
                vivo = os.path.join(DADOS, "ao_vivo.jsonl")
                self._vivo_n = getattr(self, "_vivo_n", 0) + 1
                if self._vivo_n % 200 == 1 and os.path.exists(vivo) and os.path.getsize(vivo) > 5_000_000:
                    os.replace(vivo, vivo + ".1")   # rodízio: fica a parte atual e a anterior (antes crescia sem limite)
                with open(vivo, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"h": time.strftime("%H:%M:%S"), **ev}, ensure_ascii=False, default=str)[:1500] + "\n")
            except OSError:
                pass
        if t == "inicio":
            self._respondendo, self._resposta = True, ""
        elif t == "texto_novo":
            self._resposta = ""
        elif t == "texto":
            self._resposta += ev.get("d") or ""
        elif t in ("fim", "saiu"):
            self._todo_agente_finalizar(t=='fim' and not ev.get('erro'), self._resposta or str(ev.get('erro') or ''))
            if self._ctx().pedido_turno:
                import passagem
                passagem.registrar(DADOS, self._pasta() + self._sufixo(), "claude", self._ctx().pedido_turno,
                                   self._resposta or ("(interrompido)" if t == "saiu" else ""))
                self._ctx().pedido_turno = ""
            self._respondendo, self._resposta = False, ""
        if t == "ferr":
            self._bola_atividade(self._ATIV.get(ev.get("nome"), ""))
        elif t in ("pensando", "kani_pensando"):
            self._bola_atividade("pensando")
        elif t in ("texto_novo", "fim", "saiu"):
            self._bola_atividade("")
        if self._falar_agora() and t in ("texto_novo", "texto", "permissao", "pergunta", "fim", "saiu"):
            self._fala_obj()
            if t == "texto_novo":
                self._fala.novo()
            elif t == "texto":
                self._fala.pedaco(ev.get("d") or "")
            elif t in ("permissao", "pergunta"):
                self._fala.dizer("Preciso da sua decisão na janela.")
            elif t in ("fim", "saiu"):
                self._fala.terminar()
                self._por_voz = False
        if t == "inicio" and ev.get("sessao"):
            ss = _ler_estado().get("sessoes") or {}
            if ss.get(self._pasta() + self._sufixo()) != ev["sessao"]:
                ss[self._pasta() + self._sufixo()] = ev["sessao"]
                _gravar_estado(sessoes=ss)
        elif t == "limite":
            self._limite = {k: ev.get(k) for k in ("h5", "h5_zera", "sem", "sem_zera")}
            # a cota ao vivo também vai para a conta em uso (o painel de contas mostra sem consultar)
            lista, ativa = self._contas()
            for c in lista:
                if c["id"] == ativa:
                    c["cotas"] = dict(self._limite, lido=int(time.time()))
            _gravar_estado(limite=self._limite, contas=lista)
        elif t == "comandos":
            self._comandos = ev.get("lista") or []
        elif t == "ajudante" and ev.get("fase") == "fim" and ev.get("cota") and ev.get("quem") == "codex":
            _gravar_estado(cota_codex=ev["cota"])   # a cota do Codex aparece de novo ao reabrir
        elif t in ("permissao", "pergunta"):
            # pergunta para o Pailer: a janela aparece e a bolinha fica com a marca
            self._bola_estado("pergunta")
            if not self._aberta:
                threading.Thread(target=self.mostrar, daemon=True).start()
        elif t in ("fim", "saiu"):
            # terminou: com a janela recolhida, a bolinha fica com a marca de "tem resposta"
            self._bola_estado("" if self._aberta else "pergunta")
            if t == "fim" or ev.get("erro"):   # carinha feliz/triste por 3 s (sair sem erro não entristece)
                ok = t == "fim" and not ev.get("erro")
                self._na_ui(lambda: self._bola and self._bola.definir(humor="feliz" if ok else "erro", segundos=3))
            if t == "saiu":
                self._sessao = None
        self._para_janela(ev)
        if t in ("fim", "saiu"):
            self._fila_tentar()
        if t in ("fim", "saiu") and self._pendente:
            threading.Timer(1.5, self._pendente_rodar).start()   # a última bolha chega à tela antes

    def _pendente_rodar(self):
        """recarregar/reiniciar pedido no meio de uma tarefa: só quando nenhuma aba estiver trabalhando"""
        if self._pendente and not self._alguma_ocupada():
            acao, self._pendente = self._pendente, None
            self._atualizar(acao)

    def pendentes(self):
        """cartões de permissão/pergunta ainda sem resposta (o celular que abre agora mostra eles vivos)"""
        return list(self._pend.values())

    def _para_janela(self, ev):
        ev = dict(ev, aba=self._ctx().id)
        if ev.get("t") in ("permissao", "pergunta") and ev.get("id"):
            self._pend[ev["id"]] = ev
        elif ev.get("t") == "eco_resp":
            self._pend.pop(ev.get("id"), None)
        elif ev.get("t") in ("fim", "saiu"):
            self._pend.clear()
        try:
            import movel
            movel.publicar(ev)   # cada tela filtra pela própria aba selecionada
        except Exception:
            pass
        try:
            self._janela.evaluate_js("window.kcEv && kcEv(%s)" % json.dumps(ev, ensure_ascii=False))
        except Exception as erro:
            self.janela_diagnostico("evento.janela", str(erro))

    def _bola_estado(self, estado):
        self._na_ui(lambda: self._bola and self._bola.definir(estado=estado))

    # o que está fazendo agora → rosto da bolinha (lendo, digitando, procurando, pensando)
    _ATIV = {"Read": "lendo", "Grep": "procurando", "Glob": "procurando", "WebSearch": "procurando", "WebFetch": "lendo",
             "ToolSearch": "procurando", "Edit": "digitando", "MultiEdit": "digitando", "Write": "digitando",
             "NotebookEdit": "digitando", "Bash": "digitando", "PowerShell": "digitando",
             "kani_ler_arquivo": "lendo", "kani_listar_pasta": "procurando", "kani_procurar_no_codigo": "procurando",
             "kani_buscar_no_mapa": "procurando", "kani_demandas_panda": "lendo", "kani_git_resumo": "lendo",
             "kani_espaco_disco": "procurando", "kani_abrir": "digitando", "kani_ver_kanivete": "procurando",
             "kani_abrir_ferramenta": "digitando", "kani_pedir_ao_kanivete": "digitando",
             "kani_abrir_no_kanibrowser": "digitando", "kani_fechar_aba": "digitando", "kani_salvar_texto": "digitando",
             "kani_salvar_conversa": "digitando", "kani_lembrar": "digitando", "kani_responder_janela": "digitando",
             "kani_ver_kanibrowser": "procurando", "kani_fechar_aba_kanibrowser": "digitando", "kani_ler_site": "lendo",
             "kani_clicar_no_site": "digitando", "kani_photo_novo_documento": "digitando", "kani_photo_escrever": "digitando",
             "kani_navegar_kani": "procurando", "kani_ler_kani": "lendo", "kani_clicar_kani": "digitando"}

    def _bola_atividade(self, a):
        self._na_ui(lambda: self._bola and self._bola.definir(atividade=a))

    def _na_ui(self, fn):
        """roda fn na thread da interface do Windows (a bolinha só pode ser mexida lá)"""
        try:
            from System import Action
            self._janela.native.Invoke(Action(fn))
        except Exception:
            pass

    def _clique(self):
        # chamado na thread da interface: abrir/esconder a janela do pywebview sai dela (senão trava esperando)
        # falando: espera meio segundo para ver se vêm mais cliques; 3 cliques rápidos = calar (não abre nem fecha)
        if not (self._fala and self._fala.falando):
            threading.Thread(target=self.esconder if self._aberta else self.mostrar, daemon=True).start()
            return
        agora = time.time()
        self._cliques = [t for t in getattr(self, "_cliques", []) if agora - t < 1.5] + [agora]
        t = getattr(self, "_clique_timer", None)
        if t:
            t.cancel()
        if len(self._cliques) >= 3:
            self._cliques = []
            self._fala.parar()
            self._fala_estado("parou")   # rosto da bolinha volta ao normal (sem reabrir o microfone)
            return
        self._clique_timer = threading.Timer(0.5, self._clique_solto)
        self._clique_timer.daemon = True
        self._clique_timer.start()

    def _clique_solto(self):
        self._cliques = []
        (self.esconder if self._aberta else self.mostrar)()

    def _movida(self, x, y):
        _gravar_estado(bola_px=[int(x), int(y)])
        if self._aberta:
            threading.Thread(target=lambda: self._janela.move(*self._perto_da_bola()), daemon=True).start()

    def _perto_da_bola(self):
        """posição da janela ao lado da bolinha, inteira na tela (em pixels da interface, como o pywebview quer)"""
        b = self._bola
        k = b.escala
        ax, ay, aw, ah = (v / k for v in b.area_util())
        bx, by, bl = b.x / k, b.y / k, b.total / k
        try:   # o tamanho de agora (com as colunas laterais abertas a janela é mais larga)
            _, _, fw, fh = self.tam_inicio()
            JW, JH = fw / k, fh / k
        except Exception:
            JW, JH = _tamanho()
        JW, JH = min(JW, aw - 16), min(JH, ah - 16)
        x = bx - JW - 10 if bx - JW - 10 >= ax else bx + bl + 10
        y = by + bl - JH
        x = max(ax + 8, min(x, ax + aw - JW - 8))
        y = max(ay + 8, min(y, ay + ah - JH - 8))
        return int(x), int(y)

    def _criar_bola(self):
        from bolinha import Bolinha
        e = _ler_estado()
        x, y = e.get("bola_px") or (None, None)

        def criar():
            b = Bolinha(-10000, -10000, BOLA, self._clique, self._movida, ao_direito=self._clique, ao_som=self._som_bolinha,
                        ao_sair=lambda: threading.Thread(target=self.sair, daemon=True).start())
            definir = b.definir

            def definir_e_copiar(*a, **k):   # a cópia dentro do chat acompanha a cara da bolinha
                definir(*a, **k)
                self._doca_sync()
            b.definir = definir_e_copiar
            ax, ay, aw, ah = b.area_util()
            if x is None:
                px, py_ = ax + aw - b.total - round(24 * b.escala), ay + ah - b.total - round(24 * b.escala)
            else:   # a posição guardada pode ser de um monitor que saiu: traz para dentro da área útil
                px, py_ = x, y
            from System.Drawing import Point
            from System.Windows.Forms import Screen
            dentro = any(s.WorkingArea.Contains(Point(int(px + b.total / 2), int(py_ + b.total / 2))) for s in Screen.AllScreens)
            if not dentro:
                px, py_ = ax + aw - b.total - 24, ay + ah - b.total - 24
            b.quem = e.get("quem") if e.get("quem") in ("kani", "pickle") else "claude"
            b.entrar(px, py_)
            self._bola = b
        for _ in range(100):   # a janela da conversa (escondida) precisa existir para dar a thread da interface
            try:
                self._janela.native.Handle
                break
            except Exception:
                time.sleep(0.05)
        self._na_ui(criar)

    def _fechando(self):
        # Alt+F4 / fechar na janela da conversa: só esconde (a bolinha continua); sair de verdade = botão Sair
        if self._saindo:
            return True
        threading.Thread(target=self.esconder, daemon=True).start()
        return False

    # ── atualizar depois de um ajuste no código do KaniCode (recarregar.py) ──
    def _fotografar(self):
        r = {}
        for raiz, pastas, nomes in os.walk(PASTA):
            pastas[:] = [d for d in pastas if d not in ("__pycache__", "android", "modelos", "tests", ".git")]
            for n in nomes:
                if n.endswith((".py", ".css", ".js", ".html")):
                    c = os.path.join(raiz, n)
                    try:
                        r[c] = os.path.getmtime(c)
                    except OSError:
                        pass
        return r

    def _quente(self):
        """atualizar SEM reiniciar (2026-10-23): CSS troca na página; JS/HTML recarregam só a página (a conversa e a tarefa
        em andamento continuam, o motor do Claude mora neste processo); .py de módulo com RECARREGAVEL = True é recarregado
        aqui dentro e os objetos vivos trocam de classe (o painel do navegador mantém as janelas). Outro .py = None
        (precisa reiniciar). Devolve o que fez ou None."""
        novo = self._fotografar()
        mud = [c for c, t in novo.items() if t > self._mtimes.get(c, self._carregado)]
        if not mud:
            return "nada"
        py = [c for c in mud if c.endswith(".py")]
        mods = []
        for c in py:
            nome = os.path.splitext(os.path.basename(c))[0]
            m = sys.modules.get(nome)
            if m is None and nome != "kanicode":
                continue   # nunca carregado: vale o arquivo novo quando for importado
            if m is None or not getattr(m, "RECARREGAVEL", False) or os.path.dirname(os.path.abspath(getattr(m, "__file__", ""))) != os.path.dirname(c):
                return None
            mods.append(m)
        import importlib
        for m in mods:
            velho = {k: v for k, v in vars(m).items() if isinstance(v, type)}
            importlib.reload(m)
            for obj in (getattr(self, "_nav_painel", None),):   # objetos vivos: mesma memória, métodos novos
                if obj is not None and type(obj) in velho.values():
                    nova = getattr(m, type(obj).__name__, None)
                    if isinstance(nova, type):
                        obj.__class__ = nova
        css = [os.path.relpath(c, os.path.join(PASTA, "ui")).replace("\\", "/") for c in mud if c.endswith(".css")]
        pagina = any(c.endswith((".js", ".html")) for c in mud)
        self._mtimes, self._carregado = novo, time.time()
        feito = [f"py: {', '.join(m.__name__ for m in mods)}"] if mods else []
        try:
            if pagina:
                self._janela.evaluate_js("setTimeout(() => location.reload(), 50)")
                feito.append("página recarregada")
            elif css:
                self._janela.evaluate_js("(" + json.dumps(css) + ").forEach(n => document.querySelectorAll('link[rel=stylesheet]').forEach(l => {"
                                         " if (l.getAttribute('href').split('?')[0] === n) l.href = n + '?v=' + Date.now(); }))")
                feito.append("css: " + ", ".join(css))
        except Exception:
            pass
        return "quente: " + "; ".join(feito) if feito else "nada"

    def _o_que_mudou(self):
        """'reiniciar' se algum .py mudou depois de aberto; 'recarregar' se só a janela (ui/, .css/.js); senão None"""
        py = ui = False
        for raiz, _, nomes in os.walk(PASTA):
            if "__pycache__" in raiz:
                continue
            for n in nomes:
                try:
                    novo = os.path.getmtime(os.path.join(raiz, n)) > self._carregado
                except OSError:
                    continue
                if novo and n.endswith(".py"):
                    py = True
                elif novo and n.endswith((".html", ".css", ".js")):
                    ui = True
        return "reiniciar" if py else "recarregar" if ui else None

    def _pedir(self, acao):
        """acao: atualizar (decide sozinho) | recarregar | reiniciar. No meio de uma resposta, espera ela terminar."""
        if acao == "atualizar":
            # sem reiniciar sempre que der; recarregar a página no meio de uma tarefa só sem cartão esperando resposta
            pagina = any(c.endswith((".js", ".html")) and t > self._mtimes.get(c, self._carregado) for c, t in self._fotografar().items())
            if not (pagina and self._pend):
                r = self._quente()
                if r is not None:
                    return r
            acao = self._o_que_mudou()
            if not acao:
                return "nada"
        if self._alguma_ocupada():
            if self._pendente != "reiniciar":
                self._pendente = acao
            return "depois:" + acao
        threading.Thread(target=self._atualizar, args=(acao,), daemon=True).start()
        return acao

    def _atualizar(self, acao):
        if acao == "recarregar":
            self._carregado = time.time()
            try:
                self._janela.evaluate_js("setTimeout(() => location.reload(), 50)")
            except Exception:
                pass
            return
        # reiniciar: abre um KaniCode novo (que espera este soltar a porta) e este sai; a conversa continua (--resume)
        import subprocess
        args = [a for a in sys.argv[1:] if a not in ("--reaberto", "--abrir")] + ["--reaberto"] + (["--abrir"] if self._aberta else [])
        subprocess.Popen([sys.executable, os.path.abspath(__file__), *args], cwd=PASTA, close_fds=True,
                         creationflags=0x00000008 | 0x00000200)
        # 2026-10-23: algum fio preso segurava este processo (e a porta): o novo esperava 15 s e desistia, ou abria por
        # cima do navegador interno deste ainda fechando. Sai de verdade, no máximo 8 s depois (a despedida da bolinha leva ~3,5 s)
        threading.Timer(8, lambda: os._exit(0)).start()
        self.sair()

    def _kb_painel(self):
        """o agente vai usar o navegador: abre o painel 🌐 (o Pailer vê ao vivo, com o brilho verde-limão) → estado"""
        p = getattr(self, "_nav_painel", None)
        if not (p and p.aberto) and self._janela:
            self._janela.evaluate_js("window.kcNavegador && window.kcNavegador.abrir(); true")
        return {"aberto": bool(getattr(self, "_nav_painel", None) and self._nav_painel.aberto)}

    def _kb(self, c, linha):
        with c:
            try:
                import navegador
                r = navegador.chamar(linha, DADOS, self._pasta(), {"painel": self._kb_painel})
                c.settimeout(30)
                c.sendall(json.dumps(r, ensure_ascii=False, default=str).encode("utf-8") + b"\n")
            except OSError:
                pass

    def previa_git(self):
        """Reproduz a animação com som, sem executar comandos nem criar eventos de Git."""
        if not self._aberta:
            self.mostrar()
        js = "setTimeout(() => window.kbGitAnimar && kbGitAnimar('push'), 1200); true"
        return self._janela.evaluate_js(js)

    def _canal_atender(self, c):
        # Cada conexão fica fora da escuta: uma chamada da interface não prende ping/reinício.
        with c:
            try:
                c.settimeout(3)
                buf = b""
                while not buf.endswith(b"\n") and len(buf) < 1_000_000:
                    pedaco = c.recv(65536)
                    if not pedaco:
                        break
                    buf += pedaco
                cmd = buf.decode("utf-8", "replace").strip()
                if cmd.startswith("progresso "):
                    import progresso
                    try:
                        for item in json.loads(cmd[10:])[:64]:
                            progresso.registrar(item)
                        c.sendall(b"ok\n")
                    except (ValueError, TypeError, AttributeError):
                        c.sendall(b"?\n")
                    return
                if cmd.startswith("kb "):
                    self._kb(c, cmd[3:])
                    return
                if cmd.startswith("evento "):
                    with self._canal_eventos:   # início/fim das ferramentas continuam na mesma ordem
                        c.sendall(b"ok\n")
                        try:
                            self._evento(json.loads(cmd[7:]))
                        except ValueError:
                            pass
                    return
                if cmd in ("atualizar", "recarregar", "reiniciar"):
                    c.sendall(self._pedir(cmd).encode() + b"\n")
                    return
                c.sendall(b"ok\n" if cmd in ("ping", "mostrar", "sair", "previa_git") else b"?\n")
                if cmd == "mostrar":
                    self.mostrar()
                elif cmd == "previa_git":
                    self.previa_git()
                elif cmd == "sair":
                    self.sair()
            except OSError:
                pass

    def _servir(self, srv):
        self._canal_eventos = threading.Lock()
        while not self._saindo:
            try:
                c, _ = srv.accept()
            except OSError:
                break
            threading.Thread(target=self._canal_atender, args=(c,), daemon=True).start()
        srv.close()


def _icone_na_janela(titulo="KaniCode"):
    """a janela do pywebview herda o ícone do python.exe: põe o do KaniCode (barra de tarefas e Alt+Tab) por WM_SETICON"""
    try:
        import ctypes
        from ctypes import wintypes
        ico = os.path.join(DADOS, "kanicode.ico")   # o mesmo dos atalhos (atalhos.py)
        if not os.path.isfile(ico):
            from PIL import Image
            Image.open(os.path.join(PASTA, "icone.png")).convert("RGBA").save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])
        u = ctypes.WinDLL("user32")   # cópia própria: tipar o windll compartilhado quebra outros módulos (pywebview)
        u.LoadImageW.restype = wintypes.HANDLE
        u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        meu, achadas = os.getpid(), []

        def ver(hwnd, _):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == meu:
                buf = ctypes.create_unicode_buffer(256)
                u.GetWindowTextW(hwnd, buf, 256)
                if buf.value == titulo:
                    achadas.append(hwnd)
            return True
        u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(ver), 0)
        for hwnd in achadas:
            for tipo, metrica in ((0, 49), (1, 11)):   # ICON_SMALL/SM_CXSMICON, ICON_BIG/SM_CXICON (no tamanho do DPI)
                t = u.GetSystemMetrics(metrica)
                h = u.LoadImageW(None, ico, 1, t, t, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
                if h:
                    u.SendMessageW(hwnd, 0x80, tipo, h)   # WM_SETICON
        return bool(achadas)
    except Exception:
        return False


def main():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(AUMID)
    except Exception:
        pass
    # --agente[=porta]: a janela da conversa aceita CDP em 127.0.0.1 (testes e o agente lendo a tela); nunca por padrão
    ag = next((a for a in sys.argv if a.startswith("--agente")), None)
    if ag:
        porta = ag.split("=", 1)[1] if "=" in ag else "9350"
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={porta} --remote-allow-origins=http://127.0.0.1:{porta}"
    reaberto = "--reaberto" in sys.argv   # reiniciado pelo _atualizar: espera o anterior soltar a porta
    if not reaberto and avisar("mostrar"):   # já existe uma aberta: ela aparece e esta sai
        return
    srv = None
    for _ in range(100 if reaberto else 1):
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.bind(("127.0.0.1", PORTA))   # a porta é a trava de instância única
            srv.listen(4)
            break
        except OSError:
            srv.close()
            srv = None
            time.sleep(0.15)
    if not srv:
        return
    if reaberto:
        _esperar_webview_antigo()
    app = App()
    from tarefas_agente import TarefasAgente
    try:
        TarefasAgente(DADOS).recuperar()
        app._todo_agente_restaurar()
    except (OSError, ValueError):
        pass   # o painel informa a falha de leitura sem impedir a abertura do KaniCode
    e = _ler_estado()
    w, h = _tamanho()
    app._janela = webview.create_window("KaniCode", os.path.join(PASTA, "ui", "janela.html"), js_api=app, width=w, height=h,
                                        hidden=True, frameless=True, easy_drag=False, text_select=True, on_top=bool(e.get("fixa", True)),
                                        resizable=True, min_size=(MIN_W, MIN_H), background_color="#0E1110")
    app._janela.events.closing += app._fechando
    import anexos_locais
    app._janela.events.loaded += lambda: anexos_locais.ligar(app._janela)
    threading.Thread(target=app._servir, args=(srv,), daemon=True).start()
    os.makedirs(DADOS, exist_ok=True)
    try:
        import mapa_d
        mapa_d.iniciar()   # processo próprio: busca e observação do disco continuam durante o reinício
    except Exception:
        pass
    if e.get("movel", True):   # KaniCode no celular (movel.py): só em 127.0.0.1; de fora, pelo Tailscale
        try:
            import movel
            movel.iniciar(app, DADOS)
        except Exception:
            pass

    def comecar():
        def icone():   # a janela nasce escondida: tenta até ela existir
            for _ in range(20):
                if _icone_na_janela():
                    return
                time.sleep(0.3)
        threading.Thread(target=icone, daemon=True).start()
        app._criar_bola()
        app._encaixe_ligar()
        if e.get("voz"):   # o Ei Kani estava ligado: volta ligado
            threading.Timer(1.5, app.voz, args=(True,)).start()
        # Reinício pelo topo retoma o chat; abertura normal continua só com a KaniBall.
        if reaberto and "--abrir" in sys.argv:
            for _ in range(100):   # a bolinha nasce na thread da interface: espera ela existir (o encaixe precisa dela)
                if app._bola:
                    break
                time.sleep(0.05)
            app.mostrar()
    webview.start(comecar, debug="--console" in sys.argv, storage_path=os.path.join(DADOS, "webview"))


def _esperar_webview_antigo(limite=8.0):
    """reinício: o navegador interno (WebView2) do KaniCode anterior ainda fechando com a MESMA pasta de dados faz o
    novo se pendurar nele e a página vem quebrada (script faltando, 2026-10-23). Espera ele sumir (até 8 s)."""
    try:
        import psutil
    except ImportError:
        time.sleep(1.5)
        return
    pasta = os.path.normcase(os.path.join(DADOS, "webview"))
    fim = time.time() + limite
    while time.time() < fim:
        vivos = False
        for p in psutil.process_iter(["name", "cmdline"]):
            try:
                if (p.info["name"] or "").lower() == "msedgewebview2.exe" and pasta in os.path.normcase(" ".join(p.info["cmdline"] or [])):
                    vivos = True
                    break
            except (psutil.Error, TypeError):
                continue
        if not vivos:
            return
        time.sleep(0.25)


if __name__ == "__main__":
    if sys.argv[1:] == ["reiniciar"]:
        resposta = avisar("reiniciar")
        print(resposta or "KaniCode não está aberto.")
        sys.exit(0 if resposta else 1)
    main()
