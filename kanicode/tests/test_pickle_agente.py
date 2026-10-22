"""Big Pickle nativo: a cópia isolada (git worktree) e a revisão, sem chamar o OpenCode."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import codigo_agente
import pickle_agente as pa


def git(pasta, *args):
    subprocess.run(["git", "-C", str(pasta), *args], check=True, capture_output=True)


class PickleAgenteTest(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="pickle_agente_", dir=r"D:\kanivete_testes"))
        self.repo = self.temp / "repo"
        (self.repo / "app").mkdir(parents=True)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "teste@kanicode")
        git(self.repo, "config", "user.name", "teste")
        (self.repo / ".gitignore").write_text("segredo.py\n", encoding="utf-8")
        (self.repo / "segredo.py").write_text("SENHA = 'x'\n", encoding="utf-8")
        (self.repo / "app" / "conta.py").write_text("def media(l):\n    return sum(l) / len(l) + 1\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        # mudança do Pailer ainda não commitada: vai para a cópia e não pode se perder no Aplicar
        with open(self.repo / "app" / "conta.py", "a", encoding="utf-8") as f:
            f.write("\n\ndef dobro(x):\n    return x * 2\n")
        p = patch.object(codigo_agente, "BASE", self.temp / "sessoes")
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(lambda: subprocess.run(["git", "-C", str(self.repo), "worktree", "prune"], capture_output=True))

    def test_roteamento(self):
        self.assertTrue(pa.para_ponte("Abra o Photo e o projeto mais recente"))
        self.assertTrue(pa.para_ponte("quanto espaço livre tem no disco?"))
        self.assertFalse(pa.para_ponte("corrija o bug em app/conta.py"))
        self.assertFalse(pa.para_ponte("você consegue editar código?"))
        self.assertTrue(pa.quer_editar("corrija a função media"))
        self.assertFalse(pa.quer_editar("onde fica a função media?"))

    def test_copia_revisao_e_aplicar(self):
        s = pa.Sessao(self.repo).nova("corrigir media")
        copia = Path(s.meta["trabalho"])
        self.assertNotEqual(copia.resolve(), self.repo.resolve())
        self.assertFalse((copia / "segredo.py").exists())   # ignorado pelo git: fora do alcance do agente
        self.assertIn("dobro", (copia / "app" / "conta.py").read_text(encoding="utf-8"))
        alvo = copia / "app" / "conta.py"
        alvo.write_text(alvo.read_text(encoding="utf-8").replace(" + 1", ""), encoding="utf-8")
        (copia / "notas.bat").write_text("echo oi\n", encoding="utf-8")   # tipo protegido: não vai para a revisão
        m = s.registrar_mudancas()
        self.assertEqual(m["arquivos"], ["app/conta.py"])
        self.assertIn("notas.bat", m["fora"])
        ctx = codigo_agente.Contexto(self.repo, "pickle").carregar()
        rv = ctx.revisar()
        self.assertIn("-    return sum(l) / len(l) + 1", rv["diff"])
        self.assertNotIn("dobro", "".join(l for l in rv["diff"].splitlines(True) if l.startswith(("+", "-"))))
        self.assertTrue(ctx.aplicar(rv["revisao"])["ok"])
        final = (self.repo / "app" / "conta.py").read_text(encoding="utf-8")
        self.assertNotIn("+ 1", final)
        self.assertIn("dobro", final)

    def test_origem_mexida_durante_o_trabalho_recusa_aplicar(self):
        s = pa.Sessao(self.repo).nova("corrigir media")
        alvo = Path(s.meta["trabalho"]) / "app" / "conta.py"
        alvo.write_text(alvo.read_text(encoding="utf-8").replace(" + 1", ""), encoding="utf-8")
        (self.repo / "app" / "conta.py").write_text("# o Pailer mexeu\n", encoding="utf-8")
        s.registrar_mudancas()
        ctx = codigo_agente.Contexto(self.repo, "pickle").carregar()
        with self.assertRaises(ValueError):
            ctx.aplicar(ctx.revisar()["revisao"])
        self.assertEqual((self.repo / "app" / "conta.py").read_text(encoding="utf-8"), "# o Pailer mexeu\n")
        self.assertIsNone(pa.Sessao(self.repo).atual())   # a próxima tarefa começa outra cópia

    def test_dentro_da_copia(self):
        self.assertTrue(pa._dentro(self.repo / "app" / "conta.py", self.repo))
        self.assertFalse(pa._dentro(self.temp / "fora.py", self.repo))


if __name__ == "__main__":
    unittest.main()
