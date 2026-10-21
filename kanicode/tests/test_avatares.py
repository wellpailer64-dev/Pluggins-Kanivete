import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import avatares


class AvataresTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        (self.raiz / "Default").mkdir()
        self.foto = self.raiz / "Default/Google Profile Picture.png"
        Image.new("RGB", (256, 192), "#556633").save(self.foto)
        self.indice = {"Default": {"user_name": "teste@example.com", "gaia_picture_file_name": self.foto.name}}
        p = patch.object(avatares, "_raizes", return_value=[self.raiz])
        p.start()
        self.addCleanup(p.stop)
        avatares._miniatura.cache_clear()

    def salvar(self):
        (self.raiz / "Local State").write_text(json.dumps({"profile": {"info_cache": self.indice}}), encoding="utf-8")

    def test_corresponde_email_e_reduz_foto(self):
        self.salvar()
        fotos = avatares.fotos([" TESTE@EXAMPLE.COM ", "outro@example.com"])
        self.assertEqual(list(fotos), ["teste@example.com"])
        with Image.open(io.BytesIO(base64.b64decode(fotos["teste@example.com"].partition(",")[2]))) as im:
            self.assertEqual(im.size, (96, 96))
        avatares.fotos(["teste@example.com"])
        self.assertEqual(avatares._miniatura.cache_info().hits, 1)

    def test_arquivo_fora_do_perfil_e_recusado(self):
        self.indice["Default"]["gaia_picture_file_name"] = "../../fora.png"
        self.salvar()
        self.assertEqual(avatares.fotos(["teste@example.com"]), {})

    def test_metadados_e_foto_indisponiveis_nao_quebram_contas(self):
        (self.raiz / "Local State").write_text("{incompleto", encoding="utf-8")
        self.assertEqual(avatares.fotos(["teste@example.com"]), {})
        self.salvar()
        self.foto.write_bytes(b"imagem invalida")
        self.assertEqual(avatares.fotos(["teste@example.com"]), {})


if __name__ == "__main__":
    unittest.main()
