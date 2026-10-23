"""Regressões da revisão automática, sem abrir app nem chamar agentes."""
import ast
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


class Revisao(unittest.TestCase):
    def setUp(self):
        fonte = Path(__file__).resolve().parents[1] / "mcp_equipe.py"
        arvore = ast.parse(fonte.read_text(encoding="utf-8"))
        funcoes = [n for n in arvore.body if isinstance(n, ast.FunctionDef)
                   and n.name in ("_git", "_mudados", "_ambiente_revisao", "_sintaxe", "_revisar")]
        self.base = tempfile.TemporaryDirectory(dir="D:/kanivete_testes")
        self.addCleanup(self.base.cleanup)
        self.pasta = Path(self.base.name)
        self.ns = dict(os=os, subprocess=subprocess, sys=__import__("sys"), json=__import__("json"),
                       PASTA=str(self.pasta), TESTE_PRAZO=5, _avisar=lambda ev: None)
        exec(compile(ast.Module(body=funcoes, type_ignores=[]), str(fonte), "exec"), self.ns)
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.pasta, check=True, capture_output=True,
                              creationflags=0x08000000)

    def escrever(self, nome, texto):
        (self.pasta / nome).write_text(texto, encoding="utf-8")

    def test_novo_sem_lista_do_codex_e_sem_teste(self):
        antes = self.ns["_mudados"]()
        self.escrever("ação nova.py", "x = 1")
        r = self.ns["_revisar"](antes, "")
        self.assertIn("ação nova.py", r)
        self.assertIn("sintaxe: ok", r)
        self.assertIn("NÃO EXECUTADO", r)

    def test_alteracao_de_arquivo_ja_presente_no_indice(self):
        self.escrever("existente.py", "x = 1")
        self.git("add", ".")
        antes = self.ns["_mudados"]()
        self.escrever("existente.py", "x = 2")
        self.assertIn("existente.py", self.ns["_revisar"](antes, ""))

    def test_nao_atribui_alteracao_anterior_ao_agente(self):
        self.escrever("anterior.py", "x = 1")
        antes = self.ns["_mudados"]()
        self.assertIn("nenhum arquivo mudou", self.ns["_revisar"](antes, ""))

    def test_sumico_de_arquivo_novo_e_detectado(self):
        self.escrever("novo.py", "x = 1")
        antes = self.ns["_mudados"]()
        # Simula remoção sem apagar arquivo: o conteúdo fica guardado em diretório ignorado.
        self.escrever(".gitignore", "guardado/\n")
        (self.pasta / "guardado").mkdir()
        (self.pasta / "novo.py").rename(self.pasta / "guardado/novo.py")
        self.assertIn("novo.py", self.ns["_revisar"](antes, ""))

    def test_subpasta_git_nao_mistura_outros_projetos(self):
        (self.pasta / "plugin").mkdir()
        self.escrever("fora.py", "x = 1")
        self.escrever("plugin/dentro.py", "x = 2")
        self.git("add", ".")
        self.ns["PASTA"] = str(self.pasta / "plugin")
        self.assertEqual(set(self.ns["_mudados"]()), {"dentro.py"})

    def test_git_com_erro_nao_vira_nenhuma_alteracao(self):
        with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 128, "", "erro simulado")):
            with self.assertRaisesRegex(RuntimeError, "erro simulado"):
                self.ns["_mudados"]()

    def test_codigo_de_encerramento_e_inconclusivo(self):
        with patch.object(subprocess, "Popen") as popen:
            popen.return_value.communicate.return_value = ("encerrado", None)
            popen.return_value.returncode = 4294967295
            with patch.dict(self.ns, _mudados=lambda extras: {}):
                r = self.ns["_revisar"]({}, "comando simulado")
        self.assertIn("INCONCLUSIVO", r)
        self.assertNotIn("PASSOU", r)

    def test_falha_ao_abrir_teste_preserva_relatorio(self):
        with patch.dict(self.ns, _mudados=lambda extras: {}):
            with patch.object(subprocess, "Popen", side_effect=OSError("ferramenta indisponível")):
                r = self.ns["_revisar"]({}, "comando simulado")
        self.assertIn("INCONCLUSIVO (infraestrutura)", r)
        self.assertIn("ferramenta indisponível", r)

    def test_verificador_ausente_nao_vira_sintaxe_ok(self):
        with patch.object(subprocess, "run", side_effect=FileNotFoundError("node ausente")):
            self.assertIn("INCONCLUSIVO", self.ns["_sintaxe"]("novo.js"))

    def test_registro_tem_resultado_e_duracao(self):
        import json
        r = self.ns["_revisar"]({}, "")
        registro = r.split("- evidência e duração: ", 1)[1]
        dados = json.loads(Path(registro).read_text(encoding="utf-8"))
        self.assertEqual(dados["teste"], "não executado")
        self.assertGreaterEqual(dados["duracao_s"], 0)

    def test_sem_base_inicial_nao_afirma_ausencia_de_alteracoes(self):
        r = self.ns["_revisar"](None, "")
        self.assertIn("INCONCLUSIVA", r)
        self.assertNotIn("nenhum arquivo mudou", r)

    def test_caminho_externo_informado_pelo_agente_e_ignorado(self):
        self.assertEqual(self.ns["_mudados"](["C:/fora.py", "../fora.py"]), {})

    def test_sintaxe_invalida_e_detectada(self):
        self.escrever("invalido.py", "def sem_corpo(:")
        self.assertIn("SyntaxError", self.ns["_sintaxe"]("invalido.py"))

    def test_teste_real_aprovado_e_reprovado(self):
        import sys
        for codigo, esperado in ((0, "PASSOU"), (1, "FALHOU (código 1)")):
            with self.subTest(codigo=codigo):
                comando = f'"{sys.executable}" -c "raise SystemExit({codigo})"'
                self.assertIn(esperado, self.ns["_revisar"]({}, comando))

    def test_timeout_encerra_arvore_e_recolhe_saida(self):
        with patch.dict(self.ns, _mudados=lambda extras: {}):
            with patch.object(subprocess, "Popen") as popen, patch.object(subprocess, "run") as run:
                processo = popen.return_value
                processo.pid = 123
                processo.communicate.side_effect = [subprocess.TimeoutExpired("simulado", 5), ("última saída", None)]
                r = self.ns["_revisar"]({}, "comando simulado")
        self.assertIn("TRAVOU", r)
        self.assertIn("última saída", r)
        self.assertEqual(processo.communicate.call_count, 2)
        self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "123", "/T", "/F"])

    def test_ambiente_no_d_sem_alterar_global(self):
        antes = os.environ.copy()
        ambiente = self.ns["_ambiente_revisao"]()
        for chave in ("TEMP", "TMP", "PYTHONPYCACHEPREFIX", "APPDATA", "LOCALAPPDATA"):
            self.assertTrue(ambiente[chave].startswith("D:/kanivete_testes"))
        self.assertEqual(dict(os.environ), antes)


if __name__ == "__main__":
    unittest.main()

