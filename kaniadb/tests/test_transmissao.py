"""Integração do vídeo contínuo: compartilhamento e encerramento sem aparelho real."""
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kaniadb


class TransmissaoTest(unittest.TestCase):
    def test_toque_usa_alvo_ativo_sem_redescobrir_aparelho_ou_resolucao(self):
        casa = kaniadb._Casa.__new__(kaniadb._Casa)
        casa.video = Mock()
        casa.video.alvo.return_value = ('serial-ativo', {'largura': 1080, 'altura': 2400})
        casa.video.comando.return_value = None
        corpo = json.dumps({'x': 0.5, 'y': 0.5}).encode()
        casa.path = '/tocar'
        casa.headers = {'Host': '127.0.0.1:47615', 'Content-Type': 'application/json',
                        'Content-Length': str(len(corpo))}
        casa.server = SimpleNamespace(server_address=('127.0.0.1', 47615))
        casa.rfile, casa._json = io.BytesIO(corpo), Mock()
        with patch.object(kaniadb, 'serial_padrao', side_effect=AssertionError('consulta redundante')), \
             patch.object(kaniadb, 'tamanho', side_effect=AssertionError('consulta redundante')), \
             patch.object(kaniadb, 'tocar', return_value={'x': 540, 'y': 1200}) as tocar:
            casa.do_POST()
        tocar.assert_called_once_with(540, 1200, serial='serial-ativo')

    def test_multiplos_clientes_compartilham_o_mesmo_pipeline(self):
        video = Mock()
        video.pegar.return_value = b'jpeg'
        criar = Mock(return_value=video)
        with patch.dict(sys.modules, {'video_continuo': SimpleNamespace(VideoContinuo=criar)}), \
             patch.object(kaniadb, 'serial_padrao', return_value='teste'), \
             patch.object(kaniadb, 'tamanho', return_value={'largura': 1080, 'altura': 2400}), \
             patch.object(kaniadb, 'caminho_adb', return_value='adb.exe'), \
             patch.object(kaniadb.shutil, 'which', return_value='ffmpeg.exe'), \
             patch.object(kaniadb.threading, 'Timer'):
            fonte = kaniadb._Transmissao(720)
            fonte.entrar()
            fonte.entrar()
            self.assertEqual(fonte.pegar(), b'jpeg')
            self.assertEqual(fonte.pegar(), b'jpeg')
            criar.assert_called_once_with('adb.exe', 'teste', largura=720, altura=1600, ffmpeg='ffmpeg.exe')
            fonte.sair()
            fonte._ociosa()
            video.fechar.assert_not_called()
            fonte.sair()
            fonte._ociosa()
            video.fechar.assert_called_once()
            self.assertIsNone(fonte.video)

    def test_falha_antes_do_primeiro_quadro_nao_anuncia_http_200(self):
        casa = kaniadb._Casa.__new__(kaniadb._Casa)
        casa.video = Mock()
        casa.video.iniciar.side_effect = kaniadb.ErroADB('sem vídeo')
        casa.send_response = Mock()
        with self.assertRaises(kaniadb.ErroADB):
            casa._fluxo()
        casa.send_response.assert_not_called()
        casa.video.sair.assert_called_once()

    def test_cliente_desconectado_libera_sua_referencia(self):
        casa = kaniadb._Casa.__new__(kaniadb._Casa)
        casa.video = Mock()
        casa.video.pegar.return_value = b'jpeg'
        casa.captura = Mock()
        casa.captura.pegar.return_value = b'png'
        casa.send_response, casa.send_header, casa.end_headers = Mock(), Mock(), Mock()
        casa.wfile = Mock()
        casa.wfile.write.side_effect = BrokenPipeError()
        casa._fluxo()
        casa.video.entrar.assert_called_once()
        casa.video.sair.assert_called_once()
        casa.send_header.assert_any_call('Content-Type', 'multipart/x-mixed-replace; boundary=quadro')


if __name__ == '__main__':
    unittest.main()
