import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import habilidades as H

ITENS = [{"f": "editor-imagem", "tipo": "ie", "menu": "Arquivo", "rotulo": "Novo...", "atalho": "Ctrl+N", "chave": "novo"},
         {"f": "editor-imagem", "tipo": "ie", "menu": "Camada", "rotulo": "Duplicar camada", "atalho": "Ctrl+J", "chave": "dup"},
         {"f": "video-cutter", "tipo": "ve", "menu": "Arquivo", "rotulo": "Exportar mídia...", "atalho": "Ctrl+E", "chave": "exp"},
         {"f": "video-cutter", "tipo": "botao", "menu": "botão", "rotulo": "Vídeo", "atalho": "", "chave": "Vídeo"},
         {"f": "vetor-kanivete", "tipo": "vkcmd", "menu": "comando", "rotulo": "duplicar objetos", "atalho": "", "chave": "duplicar"}]


class Habilidades(unittest.TestCase):
    def setUp(self):
        hab = H.montar(ITENS)
        df = {}
        for h in hab:
            h["_t"] = set(H.termos(h["busca"]))
            for t in h["_t"]:
                df[t] = df.get(t, 0) + 1
        H._cache.update(t=-1, hab=hab, idf={t: 1.0 for t in df})
        self.hab = hab

    def test_ids(self):
        ids = [h["id"] for h in self.hab]
        self.assertIn("photo:Arquivo › Novo...", ids)
        self.assertIn("vetor:comando duplicar", ids)

    def test_busca_pela_ferramenta(self):
        self.assertEqual(H.buscar("duplica no vetor", 1, hab=self.hab)[0]["id"], "vetor:comando duplicar")
        self.assertEqual(H.buscar("duplica a camada no photo", 1, hab=self.hab)[0]["id"], "photo:Camada › Duplicar camada")
        self.assertEqual(H.buscar("exporta o video", 1, hab=self.hab)[0]["id"], "video:Arquivo › Exportar mídia...")

    def test_achar_tolerante(self):
        H.carregar = lambda atualizar=True: self.hab
        self.assertEqual(H.achar("video:Arquivo › Exportar mídia... — Vídeo: Arquivo › Exportar")["chave"], "exp")
        self.assertEqual(H.achar("video:arquivo › exportar midia...")["chave"], "exp")
        self.assertIsNone(H.achar("video"))

    def test_perigo(self):
        self.assertTrue(H.PERIGO.search("Fechar"))
        self.assertFalse(H.PERIGO.search("Duplicar camada"))


if __name__ == "__main__":
    unittest.main()
