"""Consultas isoladas da Kani; documentos sintéticos, sem contas reais nem rede."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kani_consultas as consultas
import kani_modo as kani


class ConsultasTest(unittest.TestCase):
    def test_fonte_do_pedido(self):
        casos = {'Me acha o PDF da cliente Camila orçamento': 'pc',
                 'Procura o orçamento da Camila no Drive': 'drive',
                 'Checa meus e-mails não lidos': 'gmail', 'Vai chover amanhã em Santos?': 'clima',
                 'Cria um PDF para Camila': '', 'Pesquisa um PDF público na internet': '',
                 'Abre o Gmail': '', 'Abre o Drive': '', 'Quanto tempo tem esse vídeo?': ''}
        for pedido, fonte in casos.items():
            with self.subTest(pedido=pedido): self.assertEqual(consultas.fonte_pedido(pedido), fonte)

    def test_acha_pdf_pela_pasta_da_cliente(self):
        with tempfile.TemporaryDirectory(dir='D:/kanivete_testes') as tmp:
            cliente = Path(tmp) / 'Camila'; cliente.mkdir()
            arquivo = cliente / 'Orçamento.pdf'; arquivo.write_bytes(b'PDF de teste')
            (cliente / 'foto.jpg').write_bytes(b'foto')
            r = consultas.buscar_arquivos('camila', tmp, raiz=tmp, extensao='pdf')
            self.assertEqual([a['caminho'] for a in r['arquivos']], [str(arquivo)])
            self.assertFalse(r['parcial'])
            self.assertEqual(arquivo.read_bytes(), b'PDF de teste')

    def test_limite_indica_resultado_parcial(self):
        with tempfile.TemporaryDirectory(dir='D:/kanivete_testes') as tmp:
            for i in range(3): (Path(tmp) / f'camila{i}.pdf').write_bytes(b'')
            r = consultas.buscar_arquivos('camila', tmp, raiz=tmp, limite=1)
            self.assertEqual(len(r['arquivos']), 1)
            self.assertTrue(r['parcial'])

    def test_clima_exige_cidade_e_nao_consulta_rede(self):
        with patch.object(consultas, '_json') as rede:
            with self.assertRaises(ValueError): consultas.previsao_tempo('')
            rede.assert_not_called()

    def test_clima_homonimo_nao_escolhe_sozinho(self):
        with patch.object(consultas, '_json', return_value={'results': [dict(name='Santos',admin1='SP',country='Brasil'),dict(name='Santos',admin1='Outra',country='Outro')]}):
            r = consultas.previsao_tempo('Santos')
            self.assertEqual(len(r['escolher_local']), 2)
            self.assertNotIn('previsao', r)

    def test_cidade_com_estado_nao_confunde_aeroporto(self):
        cidade = dict(name='Sorocaba',latitude=1,longitude=2,feature_code='PPLA2')
        aeroporto = dict(name='Aeroporto de Sorocaba',feature_code='AIRP')
        with patch.object(consultas, '_json', side_effect=[{'results':[cidade,aeroporto]}, {'daily':{}}]):
            self.assertIn('dias', consultas.previsao_tempo('Sorocaba, São Paulo'))

    def test_previsao_traz_datas_e_fonte(self):
        with patch.object(consultas, '_json', side_effect=[{'results':[dict(name='Cidade',latitude=1,longitude=2)]},
                       {'daily': {'time':['2026-10-23'],'temperature_2m_max':[27]}, 'daily_units':{'temperature_2m_max':'°C'}, 'timezone':'America/Sao_Paulo'}]) as rede:
            r = consultas.previsao_tempo('Cidade',99)
            self.assertEqual(rede.call_args.args[1]['forecast_days'],7)
            self.assertEqual(r['dias'][0]['data'][:5],'23/10'); self.assertEqual(r['dias'][0]['max_c'],27)
            self.assertIn('open-meteo.com',r['fonte'])

    def test_gmail_so_consulta_e_le(self):
        import google_gmail
        with patch.object(google_gmail.gmail,'buscar',return_value={'mensagens':[{'id':'id-real'}]}) as buscar, patch.object(google_gmail.gmail,'ler',return_value={'texto':'teste'}) as ler:
            self.assertIn('id-real',kani._executar('gmail_buscar',{'busca':'is:unread'},'D:/kanivete_testes'))
            self.assertIn('teste',kani._executar('gmail_ler',{'id':'id-real'},'D:/kanivete_testes'))
            buscar.assert_called_once_with('is:unread',''); ler.assert_called_once_with('id-real')
        self.assertNotIn('gmail_enviar', kani.FERRAMENTAS)

    def test_pdf_da_camila_nao_abre_google(self):
        respostas = [({'acao':'navegar_kani','args':{'site':'Camila orçamento'},'pensamento':''},1),
                     ({'acao':'buscar_arquivos','args':{'busca':'Camila','extensao':'pdf'},'pensamento':''},1),
                     ({'acao':'responder','args':{'mensagem':'Encontrei um candidato: D:/Clientes/Camila/Orcamento.pdf'},'pensamento':''},1)]
        with patch.object(kani.ajudantes,'_kani_subir',return_value=123), patch.object(kani,'_chamar',side_effect=respostas), patch.object(kani,'_dica_habilidades',return_value=''), patch.object(kani,'notas',return_value=''), patch.object(kani,'_executar',return_value=json.dumps({'arquivos':[{'caminho':'D:/Clientes/Camila/Orcamento.pdf'}]})) as executar:
            r=kani._rodar_pedido('Me acha o PDF da cliente Camila orçamento','D:/kanivete_testes',Mock())
        self.assertTrue(r['ok'],r)
        executar.assert_called_once_with('buscar_arquivos',{'busca':'Camila','extensao':'pdf'},'D:/kanivete_testes')


if __name__ == '__main__': unittest.main()
