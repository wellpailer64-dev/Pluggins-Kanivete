"""Motor universal do cérebro: busca híbrida, mesmas respostas por Python/MCP/HTTP, permissões, escrita controlada e
contexto por perfil. Dados isolados em D:/kanivete_testes (nunca o cérebro de verdade); o modelo de sentido é o cache
compartilhado em D:/Kanivete/KaniCode/modelos (sem ele, a parte de sentido é pulada)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
import cerebro_http  # noqa: E402
import cerebro_motor as cm  # noqa: E402
import perfil_cerebro as pc  # noqa: E402

FATOS = [
    ("Padrão de legenda", "Legendas sem caixa e sem contorno, com sombra projetada 100%. Nunca tudo em maiúsculas.", "video"),
    ("Testes no disco D", "Cache, testes e modelos baixados vão para o disco D; o C é só do sistema e enche.", "dev"),
    ("Logo do Carlinhos por fundo", "No fundo escuro usar o logo 3D; no claro, o chapado. Cliente Carlinhos.", "clientes"),
    ("Rotina pessoal do Pailer", "Ele prefere reuniões depois das 14h e treina de manhã.", "eu"),
]


class MotorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs("D:/kanivete_testes", exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(dir="D:/kanivete_testes")
        pasta = os.path.join(cls.tmp.name, "cerebro")
        os.makedirs(pasta)
        cls.patches = [patch.object(pc, "DADOS", cls.tmp.name), patch.object(pc, "PASTA", pasta),
                       patch.object(pc, "_fonte_ferramentas_kani", return_value=()), patch.object(pc, "_fonte_pc", return_value=())]
        for nome, arq in (("ARQ_PROPRIOS", "neuronios.json"), ("ARQ_VIDA", "vida.json"), ("ARQ_ARQUIVO", "arquivo.json"),
                          ("ARQ_HIST", "historico.jsonl")):
            cls.patches.append(patch.object(pc, nome, os.path.join(pasta, arq)))
        for p in cls.patches:
            p.start()
        pc._MEM.update(chave=None, dados=None, vets=[], idf={})
        cls.chaves = {}
        for titulo, texto, area in FATOS:
            r = pc.guardar(titulo, texto, "feedback", area, origem="teste", certeza="pailer", forcar=True)
            cls.chaves[titulo] = r["chave"]
        cls.porta = cerebro_http.iniciar(0)
        cls.semantica = cm.indexar()["semantica"]

    @classmethod
    def tearDownClass(cls):
        cerebro_http.parar()
        for p in reversed(cls.patches):
            p.stop()
        pc._MEM.update(chave=None, dados=None, vets=[], idf={})
        cm._IDX.update(assinatura=None, d=None)
        cls.tmp.cleanup()

    def _http(self, nome, args, agente="claude", chave=None):
        chave = cm.permissao(agente)["chave"] if chave is None else chave
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}/v1/{nome}", data=json.dumps(args).encode(),
                                     headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def _mcp(self, pedidos, agente="claude"):
        env = dict(os.environ, KANICODE_TESTE="1", KANICODE_DADOS_TESTE=self.tmp.name, PYTHONIOENCODING="utf-8")
        entrada = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}]
        entrada += [{"jsonrpc": "2.0", "id": i + 1, "method": "tools/call", "params": {"name": n, "arguments": a}}
                    for i, (n, a) in enumerate(pedidos)]
        with patch.object(pc, "_fonte_pc", return_value=()):
            r = subprocess.run([sys.executable, os.path.join(AQUI, "mcp_cerebro.py"), "--agente", agente],
                               input="\n".join(json.dumps(x) for x in entrada) + "\n", capture_output=True, text=True,
                               encoding="utf-8", env=env, timeout=180)
        resp = {}
        for linha in r.stdout.splitlines():
            m = json.loads(linha)
            if m.get("id"):
                resp[m["id"]] = m["result"]
        return [json.loads(resp[i + 1]["content"][0]["text"]) if not resp[i + 1]["isError"] else resp[i + 1]["content"][0]["text"]
                for i in range(len(pedidos))]

    # ── busca ─────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_busca_por_palavra_chave_exata_e_nada_sem_relacao(self):
        r = cm.buscar("legenda com contorno?", agente="claude", marcar=False)
        self.assertEqual(r[0]["chave"], self.chaves["Padrão de legenda"])
        self.assertIn("procedencia", r[0])
        exato = cm.buscar(self.chaves["Testes no disco D"], agente="claude", marcar=False)
        self.assertEqual(exato[0]["chave"], self.chaves["Testes no disco D"])
        self.assertEqual(exato[0]["veio_por"], "exato")
        self.assertEqual(cm.buscar("receita de feijoada", agente="claude", marcar=False), [])

    def test_busca_por_sentido(self):
        if not self.semantica:
            self.skipTest("modelo de sentido não baixado")
        r = cm.buscar("onde guardar os arquivos temporários? pode ser no C?", agente="claude", modo="semantica", marcar=False)
        self.assertTrue(r and r[0]["chave"] == self.chaves["Testes no disco D"], r)

    # ── as três portas devolvem o mesmo ───────────────────────────────────────────────────────────────────────────
    def test_python_mcp_http_iguais(self):
        perguntas = ["legenda sem caixa", "logo do carlinhos no fundo escuro", "onde ficam os testes e o cache"]
        py = [[x["chave"] for x in cm.buscar(q, agente="claude", marcar=False)] for q in perguntas]
        http = [[x["chave"] for x in self._http("brain_search", {"pergunta": q, "marcar": False})["resultado"]] for q in perguntas]
        mcp = [[x["chave"] for x in r] for r in self._mcp([("brain_search", {"pergunta": q, "marcar": False}) for q in perguntas])]
        self.assertEqual(py, http)
        self.assertEqual(py, mcp)
        self.assertTrue(all(py), py)

    # ── permissões e isolamento ───────────────────────────────────────────────────────────────────────────────────
    def test_isolamento_por_agente_e_projeto(self):
        q = "logo do carlinhos no fundo escuro"
        self.assertTrue(cm.buscar(q, agente="claude", marcar=False))
        self.assertEqual(cm.buscar(q, agente="codex", marcar=False), [], "cliente só aparece para o Codex no trabalho dele")
        self.assertTrue(cm.buscar(q, agente="codex", projeto="Carlinhos", marcar=False))
        self.assertEqual(cm.buscar("rotina e reuniões do Pailer", agente="visitante", marcar=False), [])
        with self.assertRaises(PermissionError):
            cm.obter(self.chaves["Rotina pessoal do Pailer"], agente="codex")
        with self.assertRaises(PermissionError):
            cm.buscar("legenda", agente="desconhecido")

    def test_http_sem_chave_recusa_e_agente_vem_da_chave(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self._http("brain_search", {"pergunta": "legenda"}, chave="errada")
        self.assertEqual(e.exception.code, 401)
        r = self._http("brain_search", {"pergunta": "logo do carlinhos", "agente": "claude"}, agente="codex")
        self.assertEqual(r["agente"], "codex")
        self.assertEqual(r["resultado"], [], "mandar agente no corpo não troca quem pergunta")

    # ── escrita controlada ────────────────────────────────────────────────────────────────────────────────────────
    def test_kani_so_propoe_e_claude_decide(self):
        r = cm.propor("Fonte preferida do Pailer em slides", "Usa Inter nos títulos dos slides.", agente="kani",
                      origem="conversa", certeza="pailer", natureza="preferencia")
        self.assertTrue(r.get("proposto"))
        self.assertIn(r["id"].replace("prop:", ""), [p["id"] for p in cm.propostas()])
        a = cm.decidir_proposta(r["id"], True, agente="claude")
        self.assertTrue(a["guardado"])
        self.assertEqual(pc._achar(a["chave"])["natureza"], "preferencia")
        with self.assertRaises(PermissionError):
            cm.decidir_proposta("qualquer", True, agente="kani")

    def test_duplicata_recusada_conflito_vai_para_fila_e_versao_gravada(self):
        dup = cm.propor("Padrão de legenda", "Legendas sem caixa e sem contorno, sombra projetada 100%.", agente="claude",
                        origem="teste", certeza="pailer")
        self.assertFalse(dup["guardado"])
        self.assertEqual(dup["parecido"]["chave"], self.chaves["Padrão de legenda"])
        hip = cm.propor("Sombra da legenda talvez 80%", "Hipótese: sombra a 80% fica melhor no celular.", agente="claude",
                        origem="teste", certeza="pailer", natureza="hipotese")
        self.assertTrue(hip.get("proposto"))
        novo = cm.propor("Taxa da timeline", "Timeline sempre em 24, 25, 30, 50 ou 60 quadros.", agente="claude",
                         origem="teste", certeza="verificado", natureza="decisao")
        self.assertTrue(novo["guardado"], novo)
        cm.atualizar(novo["chave"], agente="claude", texto="Timeline sempre em 24, 25, 30, 50 ou 60 quadros por segundo.")
        tl = cm.linha_tempo(novo["chave"], agente="claude")
        self.assertEqual([e["acao"] for e in tl if e["acao"] in ("guardou", "atualizou")][:2], ["atualizou", "guardou"])

    # ── contexto por perfil ───────────────────────────────────────────────────────────────────────────────────────
    def test_contexto_respeita_orcamento_e_citacoes(self):
        kani = cm.contexto("como fazer a legenda do reels", perfil="kani")
        self.assertIn("legenda", kani["texto"].lower())
        self.assertLessEqual(kani["tokens"], 600)
        self.assertNotIn("[pro:", kani["texto"])
        ag = cm.contexto("como fazer a legenda do reels", perfil="agente")
        self.assertIn(self.chaves["Padrão de legenda"], ag["texto"])
        curto = cm.contexto("como fazer a legenda do reels", perfil="agente", orcamento_tokens=30)
        self.assertLessEqual(len(curto["texto"]), 30 * 4 + 60)
        self.assertEqual(cm.contexto("receita de feijoada", perfil="kani")["texto"], "")

    def test_ponto_de_partida_da_kani_usa_o_motor(self):
        t = pc.ponto_de_partida("vou fazer a legenda de um reels", quem="kani")
        self.assertIn("Padrão de legenda", t)
        with patch.dict(os.environ, {"CEREBRO_MOTOR": "v1"}):
            self.assertIn("Padrão de legenda", pc.ponto_de_partida("legenda sem caixa e sem contorno", quem="kani"))


if __name__ == "__main__":
    unittest.main()
