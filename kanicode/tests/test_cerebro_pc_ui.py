"""PC no cérebro e abertura do mapa existente: navegador isolado, índice/ponte simulados."""
import unittest
from pathlib import Path
from unittest.mock import patch
import test_layout as layout
import test_cerebro_classificacao_ui as interface
import test_cerebro_pc as pc
import perfil_cerebro as c


@unittest.skipUnless(layout.sync_playwright, 'Playwright opcional não instalado')
class CerebroPCUITest(unittest.TestCase):
    setUpClass = interface.ClassificacaoUITest.__dict__['setUpClass']
    tearDown = interface.ClassificacaoUITest.tearDown

    def setUp(self):
        interface.ClassificacaoUITest.setUp(self)
        pasta=Path(self.tmp.name)/'Clientes'; pasta.mkdir()
        self.pasta=str(pasta)
        with patch.object(c,'_fonte_pc',pc.FONTE_PC), patch.object(c,'_pc_pastas',return_value=[(self.pasta,'Clientes')]):
            c.guardar('Organização de pastas','Observar o padrão local do cliente antes de salvar.',tipo='processo',certeza='pailer',origem='conversa',forcar=True)
            c._MEM.update(chave=None)
            self.dados=c.ler()
        self.page.expose_function('dadosPCTeste',lambda:self.dados)
        self.page.evaluate('''pasta => {
          window.pcPastaTeste=pasta;window.pcConsultas=[];window.pcParcial=false;
          const anterior=pywebview.api;
          pywebview.api=new Proxy(anterior,{get:(alvo,nome)=> {
            if(nome==='cerebro_ler') return ()=>dadosPCTeste();
            if(nome==='mapa_d_status') return async()=>{
              if(window.pcFalha) throw Error('indisponível');
              return {estado:'pronto',total:1200,monitor_ativo:true,monitor:'windows',parcial:pcParcial};
            };
            if(nome==='mapa_d_listar') return async pasta=> {
              pcConsultas.push(pasta);
              return {mapa:{estado:'pronto',total:1200,monitor_ativo:true,monitor:'windows',parcial:false},itens:[{nome:'Cliente de teste',caminho:pcPastaTeste,pasta:1}],parcial:false};
            };
            return alvo[nome];
          }});
          document.querySelector('#cerebro-teste').remove();
          const el=document.createElement('div');el.id='cerebro-pc-teste';el.className='cerebro grande';document.body.appendChild(el);
        }''',self.pasta)
        self.page.evaluate("async()=>{await Cerebro.montar(document.querySelector('#cerebro-pc-teste'),{nome:'Pailer'});}")
        self.page.select_option('[data-cer-filtro="ambito"]','pc')

    def test_grupos_referencias_organizacao_e_mapa_aberto_na_pasta(self):
        p=self.page
        self.assertEqual(set(p.evaluate('Cerebro.visiveis()')),{'Mapa vivo do disco D','Clientes','Organização de pastas'})
        p.evaluate("Cerebro.selecionarTeste('pc:mapa_d')")
        p.wait_for_function("document.querySelector('.cer-pc-estado').textContent.includes('monitor ativo')")
        self.assertEqual(p.locator('.cer-cartao [data-c="descartar"]').count(),0)
        p.screenshot(path='D:/kanivete_testes/cerebro_pc.png')
        p.locator('[data-c="pc-mapa"]').click()
        p.wait_for_selector('.mapa-d-painel',state='visible')
        self.assertEqual(p.evaluate('pcConsultas.at(-1)'),'D:/')
        p.get_by_role('button',name='Fechar mapa',exact=True).click()
        chave=next(n['chave'] for n in self.dados['nos'] if n.get('pc',{}).get('pasta')==self.pasta)
        p.evaluate('(chave)=>Cerebro.selecionarTeste(chave)',chave)
        p.locator('[data-c="pc-mapa"]').click()
        p.wait_for_function('(pasta)=>pcConsultas.at(-1)===pasta',arg=self.pasta)

    def test_cobertura_parcial_e_mapa_indisponivel_ficam_visiveis(self):
        p=self.page
        p.evaluate("() => { pcParcial=true; Cerebro.selecionarTeste('pc:mapa_d'); }")
        p.wait_for_function("document.querySelector('.cer-pc-estado').textContent.includes('parcial')")
        p.evaluate("() => { pcFalha=true; Cerebro.selecionarTeste('pc:mapa_d'); }")
        p.wait_for_function("document.querySelector('.cer-pc-estado').textContent.includes('indisponível')")


if __name__ == '__main__':
    unittest.main()
