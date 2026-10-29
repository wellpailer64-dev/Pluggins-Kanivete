"""KaniADB: contratos isolados. Nenhum celular, adb ou porta de rede participa dos testes."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kaniadb


SAIDA_DEVICES = (
    "List of devices attached\n"
    "R58M12345              device usb:1-1 product:edge40 model:Motorola_Edge_40 device:dev transport_id:3\n"
    "9A0B1C                 unauthorized usb:1-2 transport_id:4\n"
    "\n"
)


class AdbFalso:
    """Guarda as chamadas e devolve uma saída por argumento pedido."""

    def __init__(self, respostas=None):
        self.respostas = respostas or {}
        self.chamadas = []

    def __call__(self, *args, **kwargs):
        self.chamadas.append(args)
        return self.respostas.get(args, "")


class DispositivosTest(unittest.TestCase):
    def test_dois_aparelhos(self):
        falso = AdbFalso({("devices", "-l"): SAIDA_DEVICES})
        with patch.object(kaniadb, "_run", falso):
            devs = kaniadb.dispositivos()
        self.assertEqual([d["serial"] for d in devs], ["R58M12345", "9A0B1C"])
        self.assertEqual(devs[0]["estado"], "device")
        self.assertEqual(devs[0]["modelo"], "Motorola Edge 40")
        self.assertEqual(devs[1]["estado"], "unauthorized")

    def test_sem_aparelho(self):
        with patch.object(kaniadb, "_run", AdbFalso({("devices", "-l"): "List of devices attached\n"})):
            self.assertEqual(kaniadb.dispositivos(), [])
            with self.assertRaises(kaniadb.ErroADB):
                kaniadb.serial_padrao()

    def test_nao_autorizado(self):
        so_pendente = "List of devices attached\n9A0B1C unauthorized usb:1-2 transport_id:4\n"
        with patch.object(kaniadb, "_run", AdbFalso({("devices", "-l"): so_pendente})):
            with self.assertRaises(kaniadb.ErroADB) as ctx:
                kaniadb.serial_padrao()
        self.assertIn("autorizada", str(ctx.exception))


class TelaTest(unittest.TestCase):
    def test_override_tem_prioridade(self):
        saida = "Physical size: 1080x2400\nOverride size: 720x1600\n"
        with patch.object(kaniadb, "_run", AdbFalso({("shell", "wm", "size"): saida})):
            self.assertEqual(kaniadb.tamanho("x"), {"largura": 720, "altura": 1600})

    def test_tamanho_fisico(self):
        with patch.object(kaniadb, "_run", AdbFalso({("shell", "wm", "size"): "Physical size: 1080x2400\n"})):
            self.assertEqual(kaniadb.tamanho("x"), {"largura": 1080, "altura": 2400})

    def test_quadro_png(self):
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 40
        with patch.object(kaniadb, "_run", AdbFalso({("exec-out", "screencap", "-p"): png})):
            self.assertEqual(kaniadb.quadro("x"), png)

    def test_quadro_invalido(self):
        with patch.object(kaniadb, "_run", AdbFalso({("exec-out", "screencap", "-p"): b"erro: tela bloqueada"})):
            with self.assertRaises(kaniadb.ErroADB):
                kaniadb.quadro("x")


class ControleTest(unittest.TestCase):
    def test_tocar(self):
        falso = AdbFalso()
        with patch.object(kaniadb, "_run", falso):
            self.assertEqual(kaniadb.tocar(540, 1200, "x"), {"x": 540, "y": 1200})
        self.assertEqual(falso.chamadas[0], ("shell", "input", "tap", "540", "1200"))

    def test_tocar_negativo_vira_zero(self):
        falso = AdbFalso()
        with patch.object(kaniadb, "_run", falso):
            kaniadb.tocar(-5, -9, "x")
        self.assertEqual(falso.chamadas[0], ("shell", "input", "tap", "0", "0"))

    def test_deslizar(self):
        falso = AdbFalso()
        with patch.object(kaniadb, "_run", falso):
            r = kaniadb.deslizar(540, 1800, 540, 600, 250, "x")
        self.assertEqual(r, {"de": [540, 1800], "ate": [540, 600], "ms": 250})
        self.assertEqual(falso.chamadas[0], ("shell", "input", "swipe", "540", "1800", "540", "600", "250"))

    def test_texto_remove_acento(self):
        falso = AdbFalso()
        with patch.object(kaniadb, "_run", falso):
            r = kaniadb.texto("Olá, tudo bem?", "x")
        self.assertEqual(r["digitado"], "Ola, tudo bem?")
        self.assertEqual(falso.chamadas[0], ("shell", "input", "text", "'Ola, tudo bem?'"))
        self.assertIn("Acentos removidos", r["aviso"])

    def test_texto_sem_acento_nao_avisa(self):
        falso = AdbFalso()
        with patch.object(kaniadb, "_run", falso):
            r = kaniadb.texto("boa noite", "x")
        self.assertEqual(r["aviso"], "")

    def test_texto_com_apostrofo(self):
        falso = AdbFalso()
        with patch.object(kaniadb, "_run", falso):
            kaniadb.texto("d'agua", "x")
        self.assertEqual(falso.chamadas[0], ("shell", "input", "text", "'d'\\''agua'"))

    def test_texto_vazio(self):
        with self.assertRaises(kaniadb.ErroADB):
            kaniadb.texto("   ", "x")

    def test_teclas_conhecidas(self):
        falso = AdbFalso()
        with patch.object(kaniadb, "_run", falso):
            self.assertEqual(kaniadb.tecla("voltar", "x"), "KEYCODE_BACK")
            self.assertEqual(kaniadb.tecla("Volume+", "x"), "KEYCODE_VOLUME_UP")
            self.assertEqual(kaniadb.tecla("KEYCODE_ENTER", "x"), "KEYCODE_ENTER")
            self.assertEqual(kaniadb.tecla("A", "x"), "KEYCODE_A")
        self.assertEqual(falso.chamadas[0], ("shell", "input", "keyevent", "KEYCODE_BACK"))

    def test_tecla_desconhecida(self):
        with self.assertRaises(kaniadb.ErroADB):
            kaniadb.tecla("dançar", "x")


class PontoTest(unittest.TestCase):
    TAM = {"largura": 1080, "altura": 2400}

    def test_fracao(self):
        self.assertEqual(kaniadb._ponto((0.5, 0.25), self.TAM), (540, 600))

    def test_pixel(self):
        self.assertEqual(kaniadb._ponto((540, 1200), self.TAM), (540, 1200))

    def test_borda_nao_estoura(self):
        self.assertEqual(kaniadb._ponto((1, 1), self.TAM), (1078, 2397))

    def test_invalido(self):
        with self.assertRaises(kaniadb.ErroADB):
            kaniadb._ponto(("a", "b"), self.TAM)


class EstadoTest(unittest.TestCase):
    def test_sem_adb(self):
        with patch.object(kaniadb, "caminho_adb", side_effect=kaniadb.ErroADB("sem adb")):
            r = kaniadb.estado()
        self.assertFalse(r["pronto"])
        self.assertIn("sem adb", r["erro"])

    def test_sem_celular(self):
        with patch.object(kaniadb, "caminho_adb", return_value="adb.exe"), \
             patch.object(kaniadb, "dispositivos", return_value=[]):
            r = kaniadb.estado()
        self.assertFalse(r["pronto"])
        self.assertIn("Nenhum celular", r["erro"])

    def test_pronto(self):
        devs = [{"serial": "R58", "estado": "device", "modelo": "Motorola Edge 40", "transporte": "3"}]
        with patch.object(kaniadb, "caminho_adb", return_value="adb.exe"), \
             patch.object(kaniadb, "dispositivos", return_value=devs), \
             patch.object(kaniadb, "tamanho", return_value={"largura": 1080, "altura": 2400}), \
             patch.object(kaniadb, "_prop", side_effect=lambda nome, serial=None: "14" if "release" in nome else "34"), \
             patch.object(kaniadb, "audio_estado", return_value={"pronto": False, "motivo": "pendente"}):
            r = kaniadb.estado()
        self.assertTrue(r["pronto"])
        self.assertEqual(r["aparelho"]["modelo"], "Motorola Edge 40")
        self.assertEqual(r["aparelho"]["tela"]["largura"], 1080)
        self.assertEqual(r["aparelho"]["android"], "14")
        self.assertFalse(r["audio"]["pronto"])


class AudioTest(unittest.TestCase):
    def test_sdk_novo_continua_pendente(self):
        with patch.object(kaniadb, "_prop", return_value="34"):
            r = kaniadb.audio_estado("x")
        self.assertFalse(r["pronto"])
        self.assertTrue(r["android_ok"])
        self.assertIn("auxiliar", r["motivo"])

    def test_sdk_antigo(self):
        with patch.object(kaniadb, "_prop", return_value="28"):
            r = kaniadb.audio_estado("x")
        self.assertFalse(r["android_ok"])


class ManifestoTest(unittest.TestCase):
    def test_manifesto_do_kanicode(self):
        caminho = Path(__file__).resolve().parents[1] / "kanicode.json"
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        self.assertEqual(dados["nome"], "KaniADB")
        self.assertEqual(dados["cli"], "kaniadb.py")
        self.assertTrue((caminho.parent / dados["icone"]).is_file())
        self.assertTrue((caminho.parent / dados["cli"]).is_file())
        self.assertTrue(dados["comandos"])
        for chave in ("serve", "descricao", "chamado_por"):
            self.assertTrue(dados[chave], chave)

    def test_pagina_existe(self):
        ui = Path(__file__).resolve().parents[1] / "ui"
        for nome in ("telefone.html", "telefone.css", "telefone.js"):
            self.assertTrue((ui / nome).is_file(), nome)


class CliTest(unittest.TestCase):
    """O caminho que o KaniCode chama: kaniadb.py <comando>."""

    def rodar(self, *argv):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = kaniadb.main(list(argv))
        return codigo, saida.getvalue()

    def test_estado_sem_celular_devolve_2(self):
        with patch.object(kaniadb, "estado", return_value={"pronto": False, "erro": "Nenhum celular conectado."}):
            codigo, saida = self.rodar("estado")
        self.assertEqual(codigo, 2)
        self.assertIn("Nenhum celular", saida)

    def test_dispositivos(self):
        devs = [{"serial": "R58", "estado": "device", "modelo": "Edge 40", "transporte": "3"}]
        with patch.object(kaniadb, "dispositivos", return_value=devs):
            codigo, saida = self.rodar("dispositivos")
        self.assertEqual(codigo, 0)
        self.assertIn("R58", saida)
        self.assertIn("Edge 40", saida)

    def test_tamanho(self):
        with patch.object(kaniadb, "tamanho", return_value={"largura": 1080, "altura": 2400}):
            self.assertEqual(self.rodar("tamanho"), (0, "1080x2400\n"))

    def test_tela_salva_png(self):
        with tempfile.TemporaryDirectory(dir="D:/kanivete_testes") as tmp:
            destino = str(Path(tmp) / "sub" / "tela.png")
            with patch.object(kaniadb, "quadro", return_value=b"\x89PNG\r\n\x1a\nxyz"):
                codigo, saida = self.rodar("tela", "--salvar", destino)
            self.assertEqual(codigo, 0)
            self.assertEqual(Path(destino).read_bytes(), b"\x89PNG\r\n\x1a\nxyz")
            self.assertIn("tela.png", saida)

    def test_tocar_sem_coordenadas_erra(self):
        codigo, saida = self.rodar("tocar", "10")
        self.assertEqual(codigo, 2)
        self.assertIn("x e y", saida)

    def test_tocar(self):
        with patch.object(kaniadb, "tocar", return_value={"x": 540, "y": 1200}) as falso:
            codigo, saida = self.rodar("tocar", "540", "1200")
        self.assertEqual(codigo, 0)
        falso.assert_called_once_with("540", "1200", None)
        self.assertIn("1200", saida)

    def test_texto_junta_valores(self):
        with patch.object(kaniadb, "texto", return_value={"digitado": "boa noite", "aviso": ""}) as falso:
            codigo, saida = self.rodar("texto", "boa", "noite")
        self.assertEqual(codigo, 0)
        falso.assert_called_once_with("boa noite", None)
        self.assertIn("boa noite", saida)

    def test_audio_pendente_devolve_3(self):
        with patch.object(kaniadb, "audio_estado", return_value={"pronto": False, "motivo": "falta auxiliar"}):
            codigo, saida = self.rodar("audio")
        self.assertEqual(codigo, 3)
        self.assertIn("falta auxiliar", saida)

    def test_comando_desconhecido(self):
        codigo, saida = self.rodar("voar")
        self.assertEqual(codigo, 2)
        self.assertIn("desconhecido", saida)


class HttpLocalTest(unittest.TestCase):
    """Os filtros da página: nada de socket, nada de adb real — o handler roda com um falso em memória."""

    PORTA = 47615
    HOST = "127.0.0.1:47615"

    def pedido(self, rota, metodo="POST", corpo=b"", cabecalhos=None, extras=None):
        campos = {"Host": self.HOST}
        campos.update(cabecalhos or {})
        casa = object.__new__(kaniadb._Casa)
        casa.path = rota
        casa.headers = campos
        casa.rfile = io.BytesIO(corpo)
        casa.wfile = io.BytesIO()
        casa._headers_buffer = []
        casa.request_version = "HTTP/1.0"
        casa.server = type("Srv", (), {"server_address": ("127.0.0.1", self.PORTA)})()
        casa.captura = None
        respostas = []
        casa._json = lambda codigo, obj: respostas.append((codigo, obj))
        falso = AdbFalso(extras or {})
        with patch.object(kaniadb, "_run", falso):
            getattr(casa, "do_" + metodo)()
        codigo = respostas[-1][0] if respostas else None
        return codigo, falso.chamadas

    def post_valido(self, rota, dados, **kwargs):
        corpo = json.dumps(dados).encode("utf-8")
        cabecalhos = {"Content-Type": "application/json", "Content-Length": str(len(corpo))}
        cabecalhos.update(kwargs.pop("cabecalhos", {}))
        return self.pedido(rota, corpo=corpo, cabecalhos=cabecalhos, **kwargs)

    def test_host_externo_recusado(self):
        codigo, chamadas = self.post_valido("/tocar", {"x": 0.5, "y": 0.5},
                                            cabecalhos={"Host": "celular.example.com:47615"})
        self.assertEqual(codigo, 403)
        self.assertEqual(chamadas, [])

    def test_host_com_porta_errada_recusado(self):
        codigo, chamadas = self.post_valido("/tocar", {"x": 0.5, "y": 0.5},
                                            cabecalhos={"Host": "127.0.0.1:8080"})
        self.assertEqual(codigo, 403)
        self.assertEqual(chamadas, [])

    def test_host_ausente_recusado(self):
        codigo, chamadas = self.post_valido("/tocar", {"x": 0.5, "y": 0.5}, cabecalhos={"Host": ""})
        self.assertEqual(codigo, 403)
        self.assertEqual(chamadas, [])

    def test_origin_externo_recusado(self):
        codigo, chamadas = self.post_valido("/tecla", {"tecla": "home"},
                                            cabecalhos={"Origin": "http://malicioso.example.com"})
        self.assertEqual(codigo, 403)
        self.assertEqual(chamadas, [])

    def test_sec_fetch_site_cross_site_recusado(self):
        codigo, chamadas = self.post_valido("/texto", {"texto": "oi"},
                                            cabecalhos={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(codigo, 403)
        self.assertEqual(chamadas, [])

    def test_content_type_exigido(self):
        codigo, chamadas = self.post_valido("/tecla", {"tecla": "home"},
                                            cabecalhos={"Content-Type": "text/plain"})
        self.assertEqual(codigo, 415)
        self.assertEqual(chamadas, [])

    def test_content_length_obrigatorio(self):
        casa = object.__new__(kaniadb._Casa)
        respostas = []
        for valor in (None, "", "abc", "-3"):
            campos = {"Host": self.HOST, "Content-Type": "application/json"}
            if valor is not None:
                campos["Content-Length"] = valor
            casa.path = "/tecla"
            casa.headers = campos
            casa.rfile = io.BytesIO(b"{}")
            casa.wfile = io.BytesIO()
            casa._headers_buffer = []
            casa.request_version = "HTTP/1.0"
            casa.server = type("Srv", (), {"server_address": ("127.0.0.1", self.PORTA)})()
            casa._json = lambda codigo, obj: respostas.append(codigo)
            falso = AdbFalso()
            with patch.object(kaniadb, "_run", falso):
                casa.do_POST()
            self.assertEqual(respostas[-1], 411, valor)
            self.assertEqual(falso.chamadas, [])

    def test_corpo_grande_recusado(self):
        corpo = json.dumps({"texto": "a" * (kaniadb.LIMITE_CORPO + 1)}).encode("utf-8")
        codigo, chamadas = self.pedido("/texto", corpo=corpo, cabecalhos={
            "Content-Type": "application/json", "Content-Length": str(len(corpo))})
        self.assertEqual(codigo, 413)
        self.assertEqual(chamadas, [])

    def test_limite_do_corpo(self):
        self.assertEqual(kaniadb.LIMITE_CORPO, 16 * 1024)

    def test_pedido_local_valido_toca(self):
        with patch.object(kaniadb, "tamanho", return_value={"largura": 1000, "altura": 2000}), \
             patch.object(kaniadb, "serial_padrao", return_value="R58"):
            codigo, chamadas = self.post_valido(
                "/tocar", {"x": 0.5, "y": 0.25},
                cabecalhos={"Origin": "http://127.0.0.1:47615", "Sec-Fetch-Site": "same-origin"})
        self.assertEqual(codigo, 200)
        self.assertEqual(chamadas, [("shell", "input", "tap", "500", "500")])

    def test_get_local_aceito(self):
        with patch.object(kaniadb, "estado", return_value={"pronto": False, "erro": "x"}):
            codigo, chamadas = self.pedido("/estado", metodo="GET")
        self.assertEqual(codigo, 200)
        self.assertEqual(chamadas, [])

    def test_get_host_externo_recusado(self):
        codigo, chamadas = self.pedido("/estado", metodo="GET", cabecalhos={"Host": "127.0.0.1:1"})
        self.assertEqual(codigo, 403)
        self.assertEqual(chamadas, [])


if __name__ == "__main__":
    unittest.main()
