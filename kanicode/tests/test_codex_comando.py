"""Regressão: iniciar e continuar o Codex sem rejeitar as opções do exec."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ajudantes


SESSAO = "00000000-0000-0000-0000-000000000001"


class ComandoCodexTest(unittest.TestCase):
    def chamar(self, exe, editar, retomar, tarefa):
        linhas = [json.dumps(evento) for evento in (
            {"type": "thread.started", "thread_id": SESSAO},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Pronto"}},
            {"type": "turn.completed", "usage": {
                "input_tokens": 20, "cached_input_tokens": 12, "output_tokens": 3}},
        )]
        def executar(cmd, pasta, entrada, receber, espera, **kw):
            for linha in linhas:
                receber(linha)
            return {"codigo": 0, "erro": "", "cancelado": False, "estourou": False,
                    "primeiro_evento_ms": 1, "ms": 2}
        eventos = []
        with patch.object(ajudantes.shutil, "which", return_value=exe), \
                patch.object(ajudantes.codex_processo, "executar", side_effect=executar) as abrir, \
                patch.object(ajudantes.codex_contexto.licoes, "anexo", return_value=""), \
                patch.object(ajudantes, "_codex_cota", return_value=None):
            resultado = ajudantes.codex(tarefa, str(Path.cwd()), editar=editar,
                                       retomar=retomar, ao_evento=eventos.append)
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["texto"], "Pronto")
        self.assertEqual(resultado["sessao"], SESSAO)
        self.assertEqual(resultado["tokens"], 11)
        self.assertEqual(eventos[-1]["fase"], "fim")
        self.assertTrue(eventos[-1]["ok"])
        return abrir.call_args.args[0], abrir.call_args.args[2]

    def casos(self):
        for editar in (False, True):
            for retomar in (None, SESSAO):
                for tarefa in ("Oi", "Corrija o erro no projeto"):
                    yield editar, retomar, tarefa

    def test_preserva_permissoes_contexto_e_entrada(self):
        for editar, retomar, tarefa in self.casos():
            with self.subTest(editar=editar, retomar=retomar, tarefa=tarefa):
                cmd, entrada = self.chamar("codex", editar, retomar, tarefa)
                self.assertEqual(cmd[cmd.index("-s") + 1],
                                 "danger-full-access" if editar else "read-only")
                self.assertEqual(cmd[cmd.index("-m") + 1], ajudantes.CODEX_MODELO)
                self.assertIn('model_reasoning_effort="%s"' % ajudantes.codex_contexto.esforco(tarefa), cmd)
                self.assertEqual(cmd[-1], "-")
                if retomar:
                    self.assertEqual(cmd[-2], retomar)
                    self.assertLess(cmd.index("-s"), cmd.index("resume"))
                else:
                    self.assertNotIn("resume", cmd)
                self.assertTrue(entrada.startswith(tarefa))
                if not retomar:
                    self.assertIn("MAPA.md", entrada)  # o primeiro 'Oi' já prepara a próxima demanda
                else:
                    self.assertNotIn("CONTEXTO DO KANICODE", entrada)
                if not editar:
                    self.assertIn("SOMENTE LEITURA", entrada)

    @unittest.skipUnless(shutil.which("codex"), "Codex CLI não instalado")
    def test_cli_instalado_aceita_os_comandos(self):
        # --help valida o parser real sem enviar mensagens ou consumir cota.
        exe = shutil.which("codex")
        for editar, retomar, tarefa in self.casos():
            with self.subTest(editar=editar, retomar=retomar, tarefa=tarefa):
                cmd, _ = self.chamar(exe, editar, retomar, tarefa)
                validacao = subprocess.run(cmd + ["--help"], capture_output=True,
                                           encoding="utf-8", errors="replace", timeout=15)
                self.assertEqual(validacao.returncode, 0, validacao.stderr)


if __name__ == "__main__":
    unittest.main()
