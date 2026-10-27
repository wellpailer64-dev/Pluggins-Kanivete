import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ajudantes
import codex_contexto
import mapa_codigo


class EventosCodexTest(unittest.TestCase):
    def rodar(self, linhas, retomar=None, **processo):
        eventos = []
        def executar(cmd, pasta, entrada, receber, espera, **kw):
            for linha in linhas:
                receber(json.dumps(linha) if isinstance(linha, dict) else linha)
            return {"codigo": 0, "erro": "", "cancelado": False, "estourou": False,
                    "primeiro_evento_ms": 1, "ms": 10, **processo}
        with patch.object(ajudantes.shutil, "which", return_value="codex"), \
                patch.object(ajudantes.codex_processo, "executar", side_effect=executar), \
                patch.object(ajudantes, "_codex_cota", return_value=None), \
                patch.object(codex_contexto.licoes, "anexo", return_value=""):
            return ajudantes.codex("Oi", str(Path.cwd()), retomar=retomar, ao_evento=eventos.append), eventos

    def test_retomada_conta_so_diferenca_do_acumulado(self):
        antes = {"input_tokens": 1000, "cached_input_tokens": 800, "output_tokens": 50}
        depois = {"input_tokens": 1300, "cached_input_tokens": 1000, "output_tokens": 60}
        with patch.object(ajudantes, "_codex_uso", side_effect=[antes, depois]):
            r, _ = self.rodar([{"type": "turn.completed", "usage": depois}], retomar="sessao")
        self.assertEqual(r["tokens"], 110)  # 100 de entrada nova + 10 de saída, sem os 250 antigos
        self.assertEqual(r["uso"]["entrada"], 300)
        self.assertEqual(r["uso"]["cache"], 200)

    def test_pulso_publica_medicao_antes_do_fim(self):
        eventos = []
        def executar(cmd, pasta, entrada, receber, espera, **kw):
            receber(json.dumps({"type":"thread.started","thread_id":"medicao-teste"}))
            kw["ao_pulso"]()
            self.assertTrue(any(e["t"] == "codex_uso" for e in eventos))
            receber(json.dumps({"type":"turn.completed","usage":{}}))
            return {"codigo":0,"erro":"","cancelado":False,"estourou":False,"primeiro_evento_ms":1,"ms":10}
        with patch.object(ajudantes.shutil, "which", return_value="codex"), \
                patch.object(ajudantes.codex_processo, "executar", side_effect=executar), \
                patch.object(ajudantes, "_codex_uso", return_value={"input_tokens":100,"cached_input_tokens":50,"output_tokens":7}), \
                patch.object(ajudantes, "_codex_cota", return_value=None), \
                patch.object(codex_contexto.licoes, "anexo", return_value=""):
            ajudantes.codex("Oi", str(Path.cwd()), ao_evento=eventos.append)
        uso = next(e for e in eventos if e["t"] == "codex_uso")
        self.assertEqual(uso["tokens"], 57)
        self.assertEqual(uso["uso"]["saida"], 7)

    def test_esgotamento_emite_aviso_especifico_com_mensagem(self):
        mensagem = "You've hit your usage limit. Try again at 23:00."
        r, eventos = self.rodar([{"type":"turn.failed","error":{"message":mensagem}}])
        self.assertFalse(r["ok"])
        self.assertEqual(next(e for e in eventos if e["t"] == "codex_limite")["mensagem"], mensagem)

    def test_comentarios_chegam_inteiros_e_entram_no_historico(self):
        texto = "Conferi soma.py. " + "Detalhes úteis. " * 20
        r, eventos = self.rodar([
            {"type":"item.updated","item":{"id":"a","type":"agent_message","text":"Conferindo"}},
            {"type":"item.completed","item":{"id":"a","type":"agent_message","text":texto}},
            {"type":"item.completed","item":{"id":"b","type":"agent_message","text":"Pronto"}},
            {"type":"turn.completed","usage":{}}
        ])
        self.assertEqual(r["progresso"], [texto])
        self.assertEqual(r["texto"], "Pronto")
        comentarios = [e for e in eventos if e["t"] == "codex_progresso"]
        self.assertEqual(comentarios[0]["texto"], "Conferindo")
        self.assertEqual(comentarios[1]["texto"], texto)
        self.assertFalse(comentarios[0].get("concluido", False))
        self.assertTrue(comentarios[1]["concluido"])

    def test_turno_falhou_nao_vira_sucesso_com_exit_zero(self):
        r, _ = self.rodar([{"type": "turn.failed", "error": {"message": "sem conexão"}}])
        self.assertFalse(r["ok"])
        self.assertIn("sem conexão", r["texto"])

    def test_final_sem_evento_de_sucesso_e_falha(self):
        r, _ = self.rodar(["não é json", "[]", {"type": "turn.started"}])
        self.assertFalse(r["ok"])
        self.assertIn("sem confirmar", r["texto"])

    def test_falha_de_cli_mantem_stderr_e_texto_parcial(self):
        r, _ = self.rodar([{"type": "item.completed", "item": {
            "type": "agent_message", "text": "Comecei a tarefa"}}], codigo=2, erro="opção inválida")
        self.assertFalse(r["ok"])
        self.assertIn("Comecei a tarefa", r["texto"])
        self.assertIn("opção inválida", r["texto"])

    def test_cancelamento_tem_motivo_distinto_de_prazo(self):
        r, _ = self.rodar([], cancelado=True)
        self.assertIn("interrompido pelo usuário", r["texto"])
        self.assertNotIn("passou do prazo", r["texto"])
        r, _ = self.rodar([], estourou=True)
        self.assertIn("passou do prazo", r["texto"])

    def test_progresso_antes_de_comando_e_saida_final_sem_repetir_comentario(self):
        r, ev = self.rodar([
            {"type": "item.started", "item": {"type": "command_execution", "command": "teste"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Vou conferir"}},
            {"type": "item.completed", "item": {"type": "command_execution", "command": "teste"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Concluído"}},
            {"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 800,
                                                   "output_tokens": 50, "reasoning_output_tokens": 20}},
        ])
        self.assertTrue(r["ok"])
        self.assertEqual(r["texto"], "Concluído")
        self.assertLess(next(i for i,e in enumerate(ev) if e["texto"] == "executando teste"),
                        next(i for i,e in enumerate(ev) if e["texto"] == "rodou teste"))
        self.assertEqual(r["uso"], {"entrada": 1000, "cache": 800, "saida": 50,
                                    "raciocinio": 20, "novos": 200, "total": 1050})
        self.assertEqual(r["tokens"], 250)  # raciocínio já faz parte da saída


class ContextoCodexTest(unittest.TestCase):
    def test_oi_inclui_mapa_e_regras_uma_vez(self):
        with patch.object(codex_contexto.licoes, "anexo", return_value="REGRAS DESTE PROJETO: exemplo"):
            inicial = codex_contexto.preparar("Oi", str(Path.cwd()), True, None)
            seguinte = codex_contexto.preparar("Continue", str(Path.cwd()), True, "sessao")
        self.assertIn("MAPA.md", inicial)
        self.assertIn("REGRAS DESTE PROJETO", inicial)
        self.assertNotIn("MAPA.md", seguinte)
        self.assertTrue(seguinte.startswith("Continue"))
        self.assertIn("MODO ATUAL: execução", seguinte)

    def test_navegador_interno_orienta_inicio_e_retomada(self):
        for sessao in (None, "sessao"):
            for pedido in ("Leia o WhatsApp", "Corrija nosso browser interno"):
                with self.subTest(sessao=sessao, pedido=pedido):
                    texto = codex_contexto.preparar(pedido, str(Path.cwd()), True, sessao)
                    self.assertIn("kb.py", texto)
                    self.assertIn("wa.py", texto)
                    self.assertIn("--onde kanicode", texto)
                    self.assertIn("--porta 9333", texto)
                    self.assertIn("Falha do controle externo não comprova", texto)

    def test_troca_de_modo_e_explicita_em_cada_turno(self):
        plano = codex_contexto.preparar("Analise", str(Path.cwd()), False, "sessao")
        build = codex_contexto.preparar("Agora implemente", str(Path.cwd()), True, "sessao")
        self.assertIn("SOMENTE LEITURA", plano)
        self.assertIn("MODO ATUAL: execução", build)
        self.assertNotIn("SOMENTE LEITURA", build)

    def test_nao_duplica_regras_do_contrato_equipe(self):
        with patch.object(codex_contexto.licoes, "anexo") as anexo:
            codex_contexto.preparar("Pedido\nREGRAS DESTE PROJETO: exemplo", str(Path.cwd()), True, None)
        anexo.assert_not_called()

    def test_esforco_e_conversa(self):
        self.assertTrue(codex_contexto.conversa("Olá Codex!"))
        self.assertFalse(codex_contexto.conversa("Oi, altere o botão"))
        self.assertFalse(codex_contexto.conversa("Preciso mudar o botão"))
        self.assertEqual(codex_contexto.esforco("Troque a cor do botão"), "low")
        self.assertEqual(codex_contexto.esforco("Investigue o travamento"), "medium")

    def test_mapa_extrai_simbolo_e_recusa_fora_da_pasta(self):
        p = mapa_codigo.arquivo("codex_contexto.py")
        self.assertIn("def preparar", mapa_codigo.simbolo(p, "preparar"))
        self.assertLessEqual(len(mapa_codigo.trecho(p, 1, 10000).splitlines()), 80)
        with self.assertRaises(ValueError):
            mapa_codigo.arquivo("../README.md")

    def test_cota_na_cauda_e_sem_emprestar_cota_de_outra_sessao(self):
        with tempfile.TemporaryDirectory(dir="D:/kanivete_testes") as d:
            pasta = Path(d)/"sessions/2026/10/21"
            pasta.mkdir(parents=True)
            p = pasta/"rollout-sessao-123.jsonl"
            p.write_text('x'*300000+'\n'+json.dumps({"payload": {"rate_limits": {
                "primary": {"used_percent": 25}, "secondary": {"used_percent": 10}}}})+'\n',encoding="utf-8")
            with patch.dict(os.environ, {"CODEX_HOME": d}):
                self.assertEqual(ajudantes._codex_cota("sessao-123")["h5"], 0.25)
                self.assertIsNone(ajudantes._codex_cota("sessao-ausente"))


if __name__ == "__main__":
    unittest.main()
