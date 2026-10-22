"""Pontos de retomada do Claude e diagnóstico local; nenhum comando é repetido automaticamente."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid


def ler(caminho):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def gravar(caminho, valor):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=caminho.parent, suffix=".tmp", delete=False) as arq:
        json.dump(valor, arq, ensure_ascii=False, indent=2)
        temporario = arq.name
    os.replace(temporario, caminho)


class Registro:
    def __init__(self, dados, projeto, sessao=None):
        self.base = Path(dados) / "continuidade"
        self.projeto = os.path.normcase(os.path.realpath(projeto))
        self._trava = threading.RLock()
        vinculo = ler(self._vinculo(sessao)) if sessao else {}
        codigo = vinculo.get("registro") or (self._vinculo(sessao).stem[:32] if sessao else uuid.uuid4().hex)
        if not isinstance(codigo, str) or len(codigo) != 32 or any(c not in '0123456789abcdef' for c in codigo):
            raise ValueError("registro de continuidade inválido")
        self.pasta = self.base / codigo
        self.estado = ler(self.pasta / "estado.json")
        if self.estado and self.estado.get("projeto") != self.projeto:
            raise ValueError("registro pertence a outro projeto")
        if sessao and not vinculo:
            self.vincular(sessao)

    def _vinculo(self, sessao):
        chave = hashlib.sha256((self.projeto + '\0' + str(sessao)).encode()).hexdigest()
        return self.base / "sessoes" / (chave + ".json")

    def vincular(self, sessao):
        with self._trava:
            gravar(self._vinculo(sessao), {"registro": self.pasta.name})
            self.estado["sessao"] = sessao
            self._salvar()

    def _salvar(self):
        self.estado.update(projeto=self.projeto, atualizado_em=time.time())
        gravar(self.pasta / "estado.json", self.estado)

    def evento(self, tipo, valor=None):
        valor = valor or {}
        with self._trava:
            self.pasta.mkdir(parents=True, exist_ok=True)
            with (self.pasta / "eventos.jsonl").open("a", encoding="utf-8") as arq:
                arq.write(json.dumps({"data": time.time(), "tipo": tipo, "dados": valor}, ensure_ascii=False) + '\n')
            if tipo == "inicio":
                sessao = valor["sessao"]
                gravar(self._vinculo(sessao), {"registro": self.pasta.name})
                self.estado["sessao"] = sessao
            elif tipo == "pedido":
                self.estado.update(pedido=valor.get("texto", ""), situacao="em_execucao")
            elif tipo == "ferr":
                pendentes = self.estado.setdefault("ferramentas_pendentes", {})
                pendentes[valor["id"]] = valor
                self.estado["ultima_ferramenta"] = valor
            elif tipo == "ferr_fim":
                self.estado.setdefault("ferramentas_pendentes", {}).pop(valor.get("id"), None)
                self.estado["ultimo_resultado"] = {k: valor.get(k) for k in ("id", "ok")}
                if not valor.get("ok"):
                    self.estado["ultima_falha"] = {"id": valor.get("id"), "diagnostico": str(self.pasta / "eventos.jsonl")}
            elif tipo == "tarefa":
                self.estado.setdefault("tarefas", {})[str(valor.get("id"))] = valor
            elif tipo == "fim":
                self.estado["situacao"] = "falha" if valor.get("erro") else "turno_concluido"
                if valor.get("erro"):
                    self.estado["ultima_falha"] = valor
            elif tipo == "interrompida":
                self.estado.update(situacao="interrompida", ultima_falha=valor)
            elif tipo in ("stderr", "saida_invalida", "evento_invalido"):
                return   # diagnóstico completo no diário, sem regravar o estado por linha
            self._salvar()

    def contexto(self):
        with self._trava:
            missao = ler(self.pasta / "missao.json")
            if not self.estado and not missao:
                return ""
            dados = {"situacao": self.estado.get("situacao"), "pedido_anterior": self.estado.get("pedido", ""),
                     "ferramentas_pendentes": self.estado.get("ferramentas_pendentes", {}),
                     "tarefas": self.estado.get("tarefas", {}),
                     "ultima_falha": self.estado.get("ultima_falha"), "missao": missao}
            resumo = json.dumps(dados, ensure_ascii=False)
            # O registro completo fica disponível à ferramenta; o contexto de reabertura é curto.
            return ("[Continuidade do KaniCode: confira o estado real do projeto, arquivos e tarefas em andamento antes de "
                    "repetir ações. Uma ferramenta pendente pode ter concluído mesmo sem resposta. Use mcp__equipe__missao "
                    "para ler o registro completo. O pedido atual do Pailer prevalece sobre este registro.\n"
                    + resumo[:10000] + "\nRegistro: " + str(self.pasta) + "]\n\n")


def missao(pasta, campos=None):
    """O MCP só recebe a pasta atribuída pelo processo da sessão, não um caminho fornecido pelo agente."""
    pasta = Path(pasta)
    if campos:
        permitidos = {"objetivo", "concluido", "proximo", "referencias", "observacoes"}
        if set(campos) - permitidos:
            raise ValueError("campo de missão desconhecido")
        for nome, valor in campos.items():
            if nome in ("concluido", "referencias"):
                if not isinstance(valor, list):
                    raise ValueError(nome + " precisa ser uma lista")
            elif not isinstance(valor, str):
                raise ValueError(nome + " precisa ser texto")
        atual = ler(pasta / "missao.json")
        atual.update(campos, atualizado_em=time.time())
        gravar(pasta / "missao.json", atual)
    return {"missao": ler(pasta / "missao.json"), "estado": ler(pasta / "estado.json"),
            "diagnostico": str(pasta / "eventos.jsonl")}
