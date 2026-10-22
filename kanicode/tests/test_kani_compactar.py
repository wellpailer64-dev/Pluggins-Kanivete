import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kani_modo


class Compactar(unittest.TestCase):
    def test_resume_os_antigos_e_mantem_os_ultimos(self):
        msgs = [{"role": "system", "content": "s" * 3000}, {"role": "user", "content": "pedido"}]
        for i in range(8):
            msgs += [{"role": "assistant", "content": "{}"}, {"role": "user", "content": f"Resultado (ler_kani):\n" + "x" * 2600}]
        kani_modo.compactar(msgs, limite=12000)
        self.assertLessEqual(sum(len(m["content"]) for m in msgs), 12000)
        self.assertEqual(len(msgs[-1]["content"]), len("Resultado (ler_kani):\n") + 2600)   # o último fica inteiro
        self.assertTrue(msgs[3]["content"].endswith("(resumido)"))
        self.assertEqual(msgs[1]["content"], "pedido")


if __name__ == "__main__":
    unittest.main()
