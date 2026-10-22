"""Contexto e orçamento do Big Pickle; registros contêm medidas, nunca os pedidos."""
import json
import re
import time
import unicodedata
import uuid

import opencode_mvp

PADRAO = {"etapas": 10, "segundos": 180, "tokens": 60000}


def selecionar(pedido, historico, leitura, navegacao, codigo, editar):
    texto = pedido + " " + " ".join(str(m.get("content", ""))[:300] for m in (historico or [])[-2:])
    texto = unicodedata.normalize("NFD", texto.lower()).encode("ascii", "ignore").decode()
    if not editar:
        return leitura
    if re.search(r"codigo|programa[cç]ao|unittest|\bbug\b|\bfuncao\b|\.(?:py|js|html|css|json)\b", texto):
        consultas = tuple(n for n in leitura if n not in ("ver_kanivete", "ver_kanibrowser", "programas_abertos", "espaco_disco"))
        if re.search(r"(?:abra|abrir|inicie|clique).{0,60}(?:kanivete|canivete|photo|vetor|video|kanibrowser)", texto):
            return leitura + navegacao + tuple(codigo)
        return consultas + tuple(codigo)
    if re.search(r"kanivete|canivete|kanibrowser|photo|vetor|\bvideo\b", texto):
        return leitura + navegacao
    if re.search(r"disco|espaco|livres|listar|consulte|consultar|programas abertos", texto):
        return leitura
    return leitura + navegacao + tuple(codigo)


def compactar(mensagens):
    # Pedido, correções e resultados permanecem distintos. Não resumir o estado como se fosse fato novo.
    saida = []
    resultados = [i for i, m in enumerate(mensagens) if str(m.get("content", "")).startswith("Resultado (")]
    recentes = set(resultados[-2:])
    for i, m in enumerate(mensagens):
        texto = str(m.get("content", ""))
        if m["role"] == "assistant":
            try:
                acao = json.loads(texto)
                if "acao" in acao:
                    texto = json.dumps({"acao":acao["acao"], "estado":"solicitação anterior; consulte o resultado observado"}, ensure_ascii=False)
            except ValueError:
                texto = texto[:300]
        elif i in resultados and i not in recentes and len(texto) > 850:
            texto = texto[:650] + "\n[resultado anterior abreviado; releia o arquivo se precisar do trecho exato]\n" + texto[-150:]
        saida.append({"role":m["role"], "content":texto})
    # O limite é em caracteres, não uma estimativa apresentada como tokens reais.
    if len(json.dumps(saida, ensure_ascii=False)) > 24000:
        raise opencode_mvp.FalhaOpenCode("contexto", "O contexto atingiu 24 mil caracteres. Divida a tarefa; resultados anteriores continuam na conversa.")
    return saida


class Controle:
    def __init__(self, emitir, parar=None, limites=None):
        self.emitir = emitir
        self.parar = parar
        self.limites = dict(PADRAO)
        for nome, valor in (limites or {}).items():
            if nome not in PADRAO or type(valor) not in (int, float) or not 0 < valor <= PADRAO[nome]:
                raise ValueError("orçamento inválido: " + str(nome))
            if nome != "segundos" and int(valor) != valor:
                raise ValueError("orçamento deve ser inteiro: " + nome)
            self.limites[nome] = int(valor) if nome != "segundos" else valor
        self.inicio = time.monotonic()
        self.tokens = self.etapas = self.recuperacoes = 0
        self.ultimo_consumo = 0
        self.falha = ""
        self.id = str(uuid.uuid4())
        self.diagnosticos = []

    def is_set(self):
        return bool(self.parar and self.parar.is_set()) or self.tempo_esgotado()

    def tempo_esgotado(self):
        return time.monotonic() - self.inicio >= self.limites["segundos"]

    def progresso(self, texto):
        self.emitir({"t":"pickle_progresso", "texto":texto})

    def conferir(self):
        if self.parar and self.parar.is_set():
            raise InterruptedError("Parei.")
        motivo = ""
        if self.etapas >= self.limites["etapas"]:
            motivo = "etapas"
        elif time.monotonic() - self.inicio >= self.limites["segundos"]:
            motivo = "tempo"
        elif self.tokens >= self.limites["tokens"] or (self.ultimo_consumo and self.tokens + self.ultimo_consumo > self.limites["tokens"]):
            motivo = "tokens"
        if motivo:
            self.falha = "orcamento_" + motivo
            raise opencode_mvp.FalhaOpenCode(self.falha, "Orçamento de " + motivo + " atingido. Parei antes de executar outra ação; revise o resultado parcial e a cópia.")

    def registrar(self, tipo, caracteres, tokens):
        medida = {"tarefa":self.id, "etapa":self.etapas, "tipo":tipo, "caracteres":caracteres,
                  "tokens":tokens, "tokens_tarefa":self.tokens, "recuperacoes":self.recuperacoes,
                  "segundos":round(time.monotonic() - self.inicio, 2)}
        self.diagnosticos.append(medida)
        try:
            opencode_mvp.BASE.mkdir(parents=True, exist_ok=True)
            with (opencode_mvp.BASE / "diagnostico_agente.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(medida) + "\n")
        except OSError:
            pass

    def consultar(self, mensagens):
        self.conferir()
        contexto = compactar(mensagens)
        self.etapas += 1
        caracteres = len(json.dumps(contexto, ensure_ascii=False))
        prazo = min(60, self.limites["segundos"] - (time.monotonic() - self.inicio))
        consumidos = 0
        tipo = "ok"
        try:
            texto, consumidos = opencode_mvp.conversar(contexto, self.parar, prazo=max(.01, prazo))
            return texto
        except opencode_mvp.FalhaOpenCode as e:
            consumidos, tipo = e.tokens, e.tipo
            raise
        except (OSError, ValueError, TimeoutError, InterruptedError):
            tipo = "transporte"
            self.falha = tipo
            raise
        finally:
            self.tokens += consumidos
            self.ultimo_consumo = consumidos
            self.emitir({"t":"agente_uso", "quem":"pickle", "tokens":self.tokens})
            self.registrar(tipo, caracteres, consumidos)

    def decisao(self, mensagens, permitidas):
        antes = self.tokens
        while True:
            try:
                texto = self.consultar(mensagens).strip()
                if texto.startswith('```') and texto.endswith('```') and '\n' in texto:
                    texto = texto.split('\n', 1)[1].rsplit('```', 1)[0].strip()
                try:
                    r = json.loads(texto)
                except ValueError:
                    raise opencode_mvp.FalhaOpenCode("json_invalido", "O modelo não devolveu JSON válido; nenhuma ação da ponte foi executada nesta etapa.") from None
                if not isinstance(r, dict) or r.get("acao") not in permitidas or not isinstance(r.get("args"), dict):
                    raise opencode_mvp.FalhaOpenCode("decisao_invalida", "Decisão inválida ou ferramenta não liberada; nenhuma ação desta etapa foi executada.")
                if any(not isinstance(v, str) for v in r["args"].values()):
                    raise opencode_mvp.FalhaOpenCode("decisao_invalida", "Os argumentos das ferramentas devem ser texto.")
                if self.tokens >= self.limites["tokens"] or time.monotonic() - self.inicio >= self.limites["segundos"]:
                    self.conferir()
                self.falha = ""
                return r, self.tokens - antes
            except opencode_mvp.FalhaOpenCode as e:
                self.falha = e.tipo
                self.registrar(e.tipo, 0, 0)
                # Só repetir uma decisão ainda não entregue ao executor. Nunca repetir ação já executada.
                if self.recuperacoes or e.tipo not in ("resposta_vazia", "json_invalido", "decisao_invalida", "nativa_recusada"):
                    raise
                self.conferir()
                self.recuperacoes += 1
                self.progresso("A etapa não trouxe uma decisão utilizável (" + e.tipo + "). Vou tentar corrigir a resposta uma única vez; as ações concluídas ficam preservadas.")
                mensagens = [*mensagens, {"role":"user", "content":"CORREÇÃO DE FORMATO: a última consulta não entregou decisão válida à ponte. Devolva somente JSON {acao,args}, usando a lista liberada. Não use ferramentas nativas; não repita ações já concluídas nos Resultados. Se faltar capacidade, responda explicando."}]

    def resumo(self):
        return {"limites":self.limites, "etapas":self.etapas, "tokens":self.tokens,
                "segundos":round(time.monotonic() - self.inicio, 2), "recuperacoes":self.recuperacoes, "falha":self.falha}
