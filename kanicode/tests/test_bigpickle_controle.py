"""Orçamentos e recuperação com decisões simuladas; nenhuma conexão ao app."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bigpickle_modo as bp
import codigo_agente
import kani_modo
import opencode_mvp as oc
import pickle_controle as pc


def decisao(acao, tokens=3, **args):
    return json.dumps({"acao":acao, "args":args}), tokens


class ControlePickleTest(unittest.TestCase):
    def setUp(self):
        import perfil_cerebro
        fonte = patch.object(perfil_cerebro, 'ponto_de_partida', return_value='')
        fonte.start(); self.addCleanup(fonte.stop)   # RAG externo não faz parte deste cenário
        self.base = Path(tempfile.mkdtemp(prefix="pickle_controle_", dir=r"D:\kanivete_testes"))
        p = patch.object(oc, "BASE", self.base)
        p.start()
        self.addCleanup(p.stop)

    def rodar(self, respostas, **kw):
        eventos = []
        with patch.object(oc, "conversar", side_effect=respostas) as chamar, \
                patch.object(kani_modo, "_executar", return_value="D: 12 GB livres") as executar:
            r = bp.rodar("Consulte o espaço livre", str(self.base), eventos.append, **kw)
        return r, chamar, executar, eventos

    def test_json_invalido_recupera_sem_repetir_acao(self):
        r, chamar, executar, ev = self.rodar([("texto inválido",5), decisao("espaco_disco"), decisao("responder", mensagem="D tem espaço.")])
        self.assertTrue(r["ok"], r["texto"])
        self.assertEqual(r["tokens"], 11)
        self.assertEqual(r["orcamento"]["recuperacoes"], 1)
        executar.assert_called_once()
        self.assertEqual(chamar.call_count, 3)
        self.assertTrue(any("até 3 vezes" in e.get("texto", "") for e in ev))
        self.assertIn('json_invalido', (self.base / 'diagnostico_agente.jsonl').read_text())

    def test_cota_nao_repete_e_conta_consumo_da_falha(self):
        r, chamar, executar, _ = self.rodar([oc.FalhaOpenCode("cota", "Limite do provedor", 17)])
        self.assertFalse(r["ok"])
        self.assertEqual(r["tokens"], 17)
        self.assertEqual(r["orcamento"]["falha"], "cota")
        self.assertEqual(chamar.call_count, 1)
        executar.assert_not_called()

    def test_orcamento_de_etapas_preserva_resultado_parcial(self):
        r, chamar, executar, ev = self.rodar([decisao("espaco_disco")], limites={"etapas":1})
        self.assertFalse(r["ok"])
        self.assertEqual(chamar.call_count, 1)
        executar.assert_called_once()
        self.assertTrue(any("Passos feitos: espaco_disco (ok)" in e.get("texto", "") for e in ev))   # no andamento, não na resposta
        self.assertEqual(r["etapas_concluidas"], [{"acao":"espaco_disco", "ok":True}])

    def test_orcamento_de_tokens_bloqueia_acao_de_resposta_em_voo(self):
        r, _, executar, _ = self.rodar([decisao("espaco_disco", tokens=50)], limites={"tokens":10})
        self.assertFalse(r["ok"])
        self.assertEqual(r["tokens"], 50)
        executar.assert_not_called()

    def test_tempo_e_cancelamento_impedem_nova_consulta(self):
        controle = pc.Controle(lambda ev: None, limites={"segundos":1})
        controle.inicio -= 2
        with patch.object(oc, "conversar") as chamar, self.assertRaisesRegex(oc.FalhaOpenCode, "tempo"):
            controle.consultar([{"role":"user","content":"oi"}])
        chamar.assert_not_called()

    def test_quarta_falha_nao_recupera_nem_repete_acao_concluida(self):
        # até 3 correções de formato por pedido (2026-10-22); a 4ª encerra sem repetir a ação já feita
        r, chamar, executar, _ = self.rodar([("inválido",1), decisao("espaco_disco"), ("inválido",1), ("inválido",1), ("inválido outra vez",2)])
        self.assertFalse(r["ok"])
        self.assertEqual(chamar.call_count, 5)
        executar.assert_called_once()

    def test_nativa_incerta_nao_recupera(self):
        r, chamar, executar, _ = self.rodar([oc.FalhaOpenCode("nativa_incerta", "Ferramenta nativa sem confirmação")])
        self.assertFalse(r["ok"])
        self.assertEqual(chamar.call_count, 1)
        executar.assert_not_called()

    def test_selecao_reduz_ferramentas_sem_liberar_escrita_em_planejar(self):
        args = (bp.LEITURA, bp.NAVEGACAO, codigo_agente.FERRAMENTAS)
        codigo = pc.selecionar("Corrija soma.py e rode unittest", [], *args, True)
        self.assertIn("codigo_testar", codigo)
        self.assertNotIn("abrir_kanivete", codigo)
        consulta = pc.selecionar("Consulte espaço no disco", [], *args, True)
        self.assertNotIn("codigo_substituir", consulta)
        plano = pc.selecionar("Corrija soma.py", [], *args, False)
        self.assertNotIn("codigo_substituir", plano)
        self.assertNotIn("abrir_kanivete", plano)

    def test_compactacao_preserva_pedido_resultados_recentes_e_correcoes(self):
        pedido = {"role":"user", "content":"Corrija apenas soma.py"}
        atual = {"role":"user", "content":"Resultado (codigo_ler):\n" + "b" * 3000}
        mensagens = [pedido, {"role":"assistant","content":json.dumps({"acao":"codigo_criar","args":{"conteudo":"x" * 12000}})},
                     {"role":"user","content":"Resultado (listar_pasta):\n" + "a" * 3000}, atual, atual,
                     {"role":"user","content":"Última ação: responder"}]
        compactas = pc.compactar(mensagens)
        self.assertEqual(compactas[0], pedido)
        self.assertEqual(compactas[-2], atual)
        self.assertEqual(compactas[-1], mensagens[-1])
        self.assertLess(len(json.dumps(compactas)), len(json.dumps(mensagens)) // 2)

    def test_resposta_prematura_nao_pula_consulta(self):
        r, chamar, executar, _ = self.rodar([
            decisao('responder', mensagem='Não consultei; máximo de etapas internas.'),
            decisao('espaco_disco'), decisao('responder', mensagem='D tem 12 GB livres.')])
        self.assertTrue(r['ok'], r['texto'])
        self.assertEqual(r['orcamento']['recuperacoes'], 1)
        self.assertEqual(chamar.call_count, 3)
        executar.assert_called_once()

    def test_limites_invalidos_nao_iniciam_modelo(self):
        for limites in ({"etapas":0.5}, {"segundos":0}, {"tokens":True}, {"etapas":pc.PADRAO["etapas"] + 1}):
            with patch.object(oc, 'conversar') as chamar:
                self.assertFalse(bp.rodar('oi', str(self.base), lambda ev: None, limites=limites)['ok'])
                chamar.assert_not_called()

    def test_cancelador_de_orcamento_interrompe_teste_sem_mudar_parada_do_usuario(self):
        import threading
        original = threading.Event()
        controle = pc.Controle(lambda ev: None, original, {"segundos":1})
        self.assertFalse(controle.is_set())
        controle.inicio -= 2
        self.assertTrue(controle.is_set())
        self.assertFalse(original.is_set())

    def test_interpretacao_distingue_erros_sem_expor_mensagem_do_provedor(self):
        for evento, tipo in [({"type":"error","error":{"message":"429 segredo-do-pedido"}},"cota"),
                             ({"type":"tool_use","part":{"state":{"status":"error","error":"Permission denied"}}},"nativa_recusada"),
                             ({"type":"tool_use","part":{"state":{"status":"completed"}}},"nativa_incerta")]:
            r = oc.interpretar(json.dumps(evento), 0)
            self.assertEqual(r["tipo"], tipo)
            self.assertNotIn("segredo-do-pedido", r["texto"])
        self.assertEqual(oc.interpretar("", 0)["tipo"], "resposta_vazia")
