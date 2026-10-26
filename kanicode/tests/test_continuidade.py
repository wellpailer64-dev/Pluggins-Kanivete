"""Interrupção, reabertura e pontos de retomada sem chamar o Claude nem o app do usuário."""
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from continuidade import Registro, ler, missao
from sessao import Sessao


class ContinuidadeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=r"D:\kanivete_testes", prefix="continuidade_")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.eventos = []

    def sessao(self, id_=None):
        return Sessao(str(self.base), str(self.base / 'dados'), self.eventos.append, id_)

    def iniciar(self, s, id_='sessao-1'):
        s._traduzir({'type':'system', 'subtype':'init', 'session_id':id_, 'model':'teste'})

    def processo(self, stdout='', stderr='', codigo=1):
        return SimpleNamespace(stdout=io.StringIO(stdout), stderr=io.StringIO(stderr), stdin=io.StringIO(),
                               returncode=codigo, wait=Mock(return_value=codigo), poll=Mock(return_value=codigo),
                               _kanicode_erros=[])

    def diario(self, s):
        return [json.loads(l) for l in (s.registro.pasta / 'eventos.jsonl').read_text(encoding='utf-8').splitlines()]

    def test_ponto_sobrevive_reabertura_e_isola_abas(self):
        s = self.sessao()
        self.iniciar(s)
        s._registrar('pedido', {'texto':'Editar entrevista'})
        referencia = {'timeline':'principal', 'clipe':'c42', 'faixa':2, 'entrada':12.5, 'saida':19.2}
        missao(s.registro.pasta, {'objetivo':'Editar entrevista', 'concluido':['Corte conferido'],
                                'proximo':'Revisar áudio', 'referencias':[referencia]})
        outra = self.sessao('sessao-1')
        self.assertEqual(outra.registro.pasta, s.registro.pasta)
        self.assertEqual(missao(outra.registro.pasta)['missao']['referencias'], [referencia])
        self.assertIn('Revisar áudio', outra.registro.contexto())
        self.assertNotEqual(self.sessao('sessao-2').registro.pasta, s.registro.pasta)
        outro_projeto = Registro(self.base / 'dados', self.base / 'outro', 'sessao-1')
        self.assertNotEqual(outro_projeto.pasta, s.registro.pasta)

    def test_missao_parcial_preserva_campos_e_listas_substituem(self):
        s = self.sessao()
        missao(s.registro.pasta, {'objetivo':'Cortes', 'concluido':['A'], 'proximo':'B'})
        r = missao(s.registro.pasta, {'concluido':['A','B']})
        self.assertEqual(r['missao']['objetivo'], 'Cortes')
        self.assertEqual(r['missao']['concluido'], ['A','B'])
        with self.assertRaises(ValueError):
            missao(s.registro.pasta, {'concluido':'feito'})
        with self.assertRaises(ValueError):
            missao(s.registro.pasta, {'arquivo':'fora'})

    def test_interrupcao_guarda_texto_pendente_e_codigo_real(self):
        s = self.sessao()
        self.iniciar(s)
        s.ocupada = True
        s._texto = ['Corte analisado antes da queda']
        s._traduzir({'type':'assistant','message':{'content':[{'type':'tool_use','id':'render-1','name':'Bash',
                                                              'input':{'command':'renderizar'}}]}})
        s.proc = self.processo(stderr='erro detalhado\n', codigo=None)
        s.proc.wait.side_effect = lambda **k: setattr(s.proc, 'returncode', 9)
        s._ler_erro(s.proc)
        s._ler(s.proc)
        self.assertEqual(s.registro.estado['situacao'], 'interrompida')
        self.assertIn('render-1', s.registro.estado['ferramentas_pendentes'])
        self.assertEqual(s.registro.estado['ultima_falha']['codigo'], 9)
        self.assertIn('Corte analisado antes da queda', str(s.historico()))
        self.assertIn('erro detalhado', self.eventos[-1]['erro'])
        self.assertTrue(Path(self.eventos[-1]['diagnostico']).is_file())

    def test_fim_de_canal_sem_resultado_nao_vira_sucesso(self):
        s = self.sessao()
        self.iniciar(s)
        s.ocupada = True
        s.proc = self.processo(codigo=0)
        s._ler(s.proc)
        self.assertEqual(s.registro.estado['situacao'], 'interrompida')
        self.assertTrue(self.eventos[-1]['erro'])

    def test_erro_completo_de_ferramenta_e_stderr_em_disco(self):
        s = self.sessao()
        self.iniciar(s)
        grande = 'diagnóstico ' * 1000 + 'FIM COMPLETO'
        s._traduzir({'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'t1',
                                                        'is_error':True,'content':grande}]}})
        self.assertLessEqual(len(self.eventos[-1]['saida']), 3000)
        self.assertEqual(self.diario(s)[-1]['dados']['saida'], grande)
        s.proc = self.processo(stderr='\n'.join('linha '+str(i) for i in range(50)))
        s._ler_erro(s.proc)
        linhas = [x for x in self.diario(s) if x['tipo'] == 'stderr']
        self.assertEqual(len(linhas), 50)
        self.assertEqual(len(s.proc._kanicode_erros), 20)

    def test_resultado_falho_expoe_motivo_e_diagnostico(self):
        s = self.sessao()
        self.iniciar(s)
        motivo = 'Falha de exportação: ' + 'x' * 4000
        s._traduzir({'type':'result','subtype':'error_during_execution','errors':[motivo]})
        self.assertTrue(self.eventos[-1]['erro'])
        self.assertTrue(self.eventos[-1]['mensagem'].startswith('Falha de exportação'))
        self.assertLessEqual(len(self.eventos[-1]['mensagem']), 1200)
        self.assertEqual(next(x for x in self.diario(s) if x['tipo']=='resultado')['dados']['errors'], [motivo])
        self.assertEqual(s.registro.estado['situacao'], 'falha')

    def test_ferramenta_respondida_nao_fica_pendente_e_turno_nao_conclui_missao(self):
        s = self.sessao()
        self.iniciar(s)
        s._traduzir({'type':'assistant','message':{'content':[{'type':'tool_use','id':'t1','name':'Read','input':{}}]}})
        s._traduzir({'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'t1','content':'ok'}]}})
        missao(s.registro.pasta, {'objetivo':'Montar vídeo', 'proximo':'Conferir a imagem'})
        s._traduzir({'type':'result','subtype':'success'})
        self.assertEqual(s.registro.estado['ferramentas_pendentes'], {})
        self.assertEqual(s.registro.estado['situacao'], 'turno_concluido')
        self.assertEqual(missao(s.registro.pasta)['missao']['proximo'], 'Conferir a imagem')
        s.proc = self.processo(codigo=0)
        s._ler(s.proc)
        self.assertFalse(self.eventos[-1]['erro'])
        self.assertEqual(s.registro.estado['situacao'], 'turno_concluido')

    def test_retoma_com_conferencia_sem_reenviar_comando_anterior(self):
        s = self.sessao()
        self.iniciar(s)
        s._registrar('pedido', {'texto':'Renderize a versão antiga'})
        s._registrar('ferr', {'id':'render', 'nome':'Bash', 'entrada':{'command':'exportar-antigo'}})
        missao(s.registro.pasta, {'proximo':'Conferir se a saída já existe'})
        outra = self.sessao('sessao-1')
        outra._abrir = Mock(side_effect=lambda: setattr(outra, 'proc', self.processo(codigo=None)))
        outra._escrever = Mock()
        outra.enviar('Continue com a versão revisada')
        outra._abrir.assert_called_once()
        outra._escrever.assert_called_once()
        envio = outra._escrever.call_args.args[0]['message']['content'][-1]['text']
        self.assertIn('confira o estado real', envio)
        self.assertIn('pode ter concluído', envio)
        self.assertTrue(envio.endswith('Continue com a versão revisada'))
        self.assertEqual(outra.registro.estado['pedido'], 'Continue com a versão revisada')
        self.assertIn('render', outra.registro.estado['ferramentas_pendentes'])

    def test_corrupcao_nao_apaga_registro_e_falha_de_disco_avisa(self):
        s = self.sessao()
        self.iniciar(s)
        arquivo = s.registro.pasta / 'missao.json'
        arquivo.write_text('{quebrado', encoding='utf-8')
        with self.assertRaises(ValueError):
            s.registro.contexto()
        self.assertEqual(arquivo.read_text(encoding='utf-8'), '{quebrado')
        with patch.object(s.registro, 'evento', side_effect=OSError('disco indisponível')):
            s._registrar('pedido', {'texto':'teste'})
            s._registrar('pedido', {'texto':'teste'})
        avisos = [e for e in self.eventos if e['t']=='aviso']
        self.assertEqual(len(avisos), 1)
        self.assertIn('disco indisponível', avisos[0]['texto'])

    def test_tarefa_em_segundo_plano_e_compactacao_ficam_no_registro(self):
        s = self.sessao()
        self.iniciar(s)
        s._traduzir({'type':'system', 'subtype':'task_started', 'task_id':'exportacao',
                     'description':'Render em andamento', 'output_file':'D:/kanivete_testes/render.log'})
        s._traduzir({'type':'system', 'subtype':'compact_boundary', 'compact_metadata':{'trigger':'auto'}})
        outra = self.sessao('sessao-1')
        self.assertIn('exportacao', outra.registro.estado['tarefas'])
        self.assertIn('render.log', outra.registro.contexto())
        self.assertTrue(any(x['tipo']=='compactacao' for x in self.diario(s)))
        s._traduzir({'type':'system', 'subtype':'task_notification', 'task_id':'exportacao', 'status':'completed'})
        self.assertEqual(s.registro.estado['tarefas']['exportacao']['status'], 'completed')

    def test_historico_longo_com_ultima_linha_incompleta(self):
        s = self.sessao()
        self.iniciar(s)
        for n in range(500):
            s._guardar({'t':'eu', 'texto':str(n)})
        with open(s._arquivo(), 'a', encoding='utf-8') as arq:
            arq.write('{"t":"kc","texto":"interrompido')
        historico = self.sessao('sessao-1').historico()
        self.assertLessEqual(len(historico), 400)
        self.assertEqual(historico[-1]['texto'], '499')
        self.assertGreater(len(historico), 300)

    def test_abertura_usa_resume_e_pasta_correta_do_mcp(self):
        s = self.sessao('sessao-1')
        proc = self.processo(codigo=None)
        with patch('sessao.shutil.which', return_value='claude'), patch('sessao.subprocess.Popen', return_value=proc) as abrir, \
             patch('sessao.threading.Thread'), patch('contas.ambiente', return_value=None):
            s._abrir()
        cmd = abrir.call_args.args[0]
        self.assertEqual(cmd[cmd.index('--resume')+1], 'sessao-1')
        mcp = json.loads(cmd[cmd.index('--mcp-config')+1])['mcpServers']['equipe']
        self.assertEqual(mcp['args'][-1], str(s.registro.pasta))
        self.assertIn('mcp__equipe__missao', cmd)

    def test_processo_real_interrompido_deixa_retomada_sem_repeticao(self):
        s = self.sessao()
        codigo = """
import json, sys
print(json.dumps({'type':'system','subtype':'init','session_id':'queda-real'}), flush=True)
print(json.dumps({'type':'assistant','message':{'content':[{'type':'tool_use','id':'render-ativo','name':'Bash','input':{'command':'render'}}]}}), flush=True)
print('Falha simulada de render', file=sys.stderr, flush=True)
sys.exit(7)
"""
        proc = subprocess.Popen([sys.executable, '-c', codigo], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding='utf-8', creationflags=0x08000000)
        s.proc = proc
        s.ocupada = True
        proc._kanicode_erros = []
        proc._kanicode_leitor_erro = threading.Thread(target=s._ler_erro, args=(proc,), daemon=True)
        proc._kanicode_leitor_erro.start()
        try:
            s._ler(proc)
            self.assertEqual(proc.poll(), 7)
            self.assertEqual(s.registro.estado['situacao'], 'interrompida')
            self.assertIn('Falha simulada de render', self.eventos[-1]['erro'])
            outra = self.sessao('queda-real')
            self.assertIn('render-ativo', outra.registro.estado['ferramentas_pendentes'])
            self.assertIn('pode ter concluído', outra.registro.contexto())
        finally:
            proc.wait(timeout=5)
            proc.stdin.close()
            proc.stdout.close()
            proc.stderr.close()

    def test_falha_do_vinculo_nao_descarta_id_recebido(self):
        s = self.sessao()
        with patch.object(s.registro, 'evento', side_effect=OSError('disco indisponível')):
            self.iniciar(s, 'id-confirmado')
        self.assertEqual(self.eventos[-1]['t'], 'inicio')
        self.assertEqual(self.eventos[-1]['sessao'], 'id-confirmado')
        self.assertTrue(any(e['t']=='aviso' for e in self.eventos))

    def test_mcp_real_guarda_e_le_missao(self):
        s = self.sessao()
        self.iniciar(s)
        script = str(Path(__file__).resolve().parents[1] / 'mcp_equipe.py')
        proc = subprocess.Popen([sys.executable, script, str(self.base), str(s.registro.pasta)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding='utf-8', creationflags=0x08000000)
        respostas = queue.Queue()
        def ler_saida():
            for linha in proc.stdout:
                respostas.put(json.loads(linha))
        leitor = threading.Thread(target=ler_saida, daemon=True)
        leitor.start()
        def chamar(id_, metodo, params=None):
            proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':id_,'method':metodo,'params':params or {}})+'\n')
            proc.stdin.flush()
            r = respostas.get(timeout=10)
            self.assertEqual(r['id'], id_)
            return r['result']
        try:
            chamar(1, 'initialize')
            ferramentas = chamar(2, 'tools/list')['tools']
            self.assertTrue(any(f['name']=='missao' for f in ferramentas))
            r = chamar(3, 'tools/call', {'name':'missao','arguments':{'objetivo':'Vídeo','proximo':'Conferir render'}})
            self.assertFalse(r['isError'])
            r = chamar(4, 'tools/call', {'name':'missao','arguments':{}})
            self.assertEqual(json.loads(r['content'][0]['text'])['missao']['proximo'], 'Conferir render')
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            leitor.join(timeout=2)
            proc.stdout.close()
            proc.stderr.close()




class ContasAutomaticasTest(unittest.TestCase):
    def setUp(self):
        import contas
        self.contas = contas
        self.temp = tempfile.TemporaryDirectory(dir="D:/kanivete_testes", prefix="contas_auto_")
        self.addCleanup(self.temp.cleanup)
        self.eventos = []
        self.s = Sessao(self.temp.name, self.temp.name, self.eventos.append, sessao_id="conversa-1")
        self.s._ultimo_envio = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "Pedido"}]}}
        self.s.escolher_conta = Mock(return_value="outra")
        self.s._abrir = Mock()
        self.s._escrever = Mock()

    def conta(self, id_, h5=.4, sem=.6, **extra):
        return dict(id=id_, apelido=id_, email=id_ + "@example.com", logado=True,
                    cotas={"h5": h5, "sem": sem, "lido": 1000}, **extra)

    def test_prioriza_semana_depois_cinco_horas(self):
        lista = [self.conta("atual"), self.conta("a", .8, .7), self.conta("b", .9, .7), self.conta("c", .95, .2)]
        self.assertEqual(self.contas.escolher(lista, "atual", set(), 1000)["id"], "b")

    def test_descarta_esgotadas_erros_e_desatualizadas(self):
        lista = [self.conta("h", 1), self.conta("s", sem=1), self.conta("erro", cota_erro="falhou"),
                 self.conta("antiga"), self.conta("saiu"), self.conta("parcial"), self.conta("boa")]
        lista[3]["cotas"]["lido"] = 800
        lista[4]["logado"] = False
        lista[5]["cotas"].pop("sem")
        self.assertEqual(self.contas.escolher(lista, "atual", set(), 1000)["id"], "boa")

    def test_nao_repete_id_nem_mesmo_email(self):
        lista = [self.conta("atual"), self.conta("espelho"), self.conta("tentada"), self.conta("livre")]
        lista[1]["email"] = "ATUAL@example.com"
        self.assertIsNone(self.contas.escolher(lista, "atual", {"tentada", "livre"}, 1000))

    def test_parcial_preserva_janela_e_resposta_antiga_nao_regride(self):
        q = {"h5": .7, "sem": .9, "lido": 20}
        self.assertEqual(self.contas.mesclar_cotas(q, {"h5": .1, "lido": 10}), q)
        r = self.contas.mesclar_cotas(q, {"h5": None, "sem": .95, "lido": 30, "t": "limite"})
        self.assertEqual((r["h5"], r["sem"]), (.7, .95))
        self.assertNotIn("t", r)
        self.assertEqual(self.contas.mesclar_cotas(q, {"erro": "offline"}), q)

    def test_evento_suporta_janela_unica_e_nao_inventa_zero(self):
        r = self.contas.normalizar_evento({"rateLimitType": "five_hour", "utilization": .84, "resetsAt": 2000})
        self.assertEqual(r["h5"], .84)
        self.assertNotIn("sem", r)
        r = self.contas.normalizar_evento({"unifiedWindows": {"seven_day": {"utilization": .5}}})
        self.assertEqual(r["sem"], .5)
        self.assertNotIn("h5", r)

    def test_rate_limit_temporario_nao_dispara_rotacao(self):
        self.assertFalse(self.contas.limite_confirmado({"errors": ["429 Too Many Requests"]}))
        self.assertFalse(self.contas.limite_confirmado({"errors": ["Network disconnected"]}))
        self.assertTrue(self.contas.limite_confirmado({"error": "rate_limit"}))
        self.assertTrue(self.contas.limite_confirmado({"result": "You've hit your limit · resets 5pm"}))

    def test_resultado_esgotado_retoma_sem_finalizar_conversa(self):
        class Imediata:
            def __init__(self, target, args, **kw): self.rodar = lambda: target(*args)
            def start(self): self.rodar()
        self.s.proc = None
        self.s._contas_tentadas = {"principal"}
        with patch("sessao.threading.Thread", Imediata):
            self.s._traduzir({"type": "result", "subtype": "error_during_execution", "errors": ["You've hit your limit"]})
        self.assertEqual(self.s.conta, "outra")
        self.assertTrue(self.s.ocupada)
        self.s._abrir.assert_called_once()
        self.assertIn("não repita", self.s._escrever.call_args.args[0]["message"]["content"][0]["text"])
        self.assertFalse(any(e["t"] == "fim" for e in self.eventos))
        self.assertEqual(self.s._contas_tentadas, {"principal", "outra"})

    def test_assistant_rate_limit_com_result_success_tambem_retoma(self):
        self.s._traduzir({"type": "assistant", "error": "rate_limit", "message": {"content": []}})
        with patch("sessao.threading.Thread") as thread:
            self.s._traduzir({"type": "result", "subtype": "success", "is_error": True})
        thread.assert_called_once()

    def test_sem_saldo_encerra_com_explicacao(self):
        self.s.escolher_conta.return_value = None
        self.s._trocar_apos_limite(None, {"t": "fim", "erro": True})
        self.assertFalse(self.s.ocupada)
        self.assertIn("Nenhuma outra conta", self.eventos[-1]["mensagem"])
        self.s._abrir.assert_not_called()

    def test_parar_durante_consulta_impede_nova_execucao(self):
        def escolher(*args):
            self.s.parar()
            return "outra"
        self.s.escolher_conta.side_effect = escolher
        self.s._trocar_apos_limite(None, {"t": "fim", "erro": True})
        self.s._abrir.assert_not_called()
        self.assertFalse(self.s.ocupada)

    def test_erro_consulta_preserva_diagnostico(self):
        self.s.escolher_conta.side_effect = ValueError("offline")
        self.s._trocar_apos_limite(None, {"t": "fim", "erro": True, "diagnostico": "registro"})
        self.assertIn("offline", self.eventos[-1]["mensagem"])
        self.assertEqual(self.eventos[-1]["diagnostico"], "registro")

    def test_evento_identifica_conta_da_sessao(self):
        self.s.conta = "secundaria"
        self.s._traduzir({"type": "rate_limit_event", "rate_limit_info": {"rateLimitType": "seven_day", "utilization": .9}})
        self.assertEqual(self.eventos[-1]["conta"], "secundaria")
        self.assertEqual(self.eventos[-1]["sem"], .9)

    def test_resultado_generico_nao_troca(self):
        self.s._traduzir({"type": "result", "subtype": "error_during_execution", "errors": ["Connection failed"]})
        self.s.escolher_conta.assert_not_called()
        self.assertEqual(self.eventos[-1]["t"], "fim")




class ContasAppTest(unittest.TestCase):
    def setUp(self):
        import kanicode
        self.k = kanicode
        self.temp = tempfile.TemporaryDirectory(dir="D:/kanivete_testes", prefix="contas_app_")
        self.addCleanup(self.temp.cleanup)
        for nome, valor in (("DADOS", self.temp.name), ("ESTADO", str(Path(self.temp.name) / "estado.json"))):
            p = patch.object(kanicode, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        self.k._gravar_estado(conta="principal", contas=[
            {"id": "principal", "apelido": "Principal", "email": "a@example.com", "logado": True,
             "cotas": {"h5": .7, "sem": .6, "lido": 100}},
            {"id": "outra", "apelido": "Outra", "email": "b@example.com", "logado": True,
             "cotas": {"h5": .3, "sem": .2, "lido": 100}}])
        self.app = kanicode.App()
        for nome in ("_codex_voz", "_bola_atividade", "_bola_estado", "_na_ui", "_para_janela"):
            setattr(self.app, nome, Mock())
        self.app._falar_agora = Mock(return_value=False)

    def lista(self):
        return self.k._ler_estado()["contas"]

    def test_evento_parcial_atualiza_so_conta_de_origem(self):
        self.app._evento({"t": "limite", "conta": "outra", "h5": .9, "lido": 200})
        self.assertEqual(self.lista()[0]["cotas"]["h5"], .7)
        self.assertEqual(self.lista()[1]["cotas"]["h5"], .9)
        self.assertEqual(self.lista()[1]["cotas"]["sem"], .2)

    def test_consulta_lenta_nao_sobrescreve_evento_mais_recente(self):
        def cotas(_):
            self.app._evento({"t": "limite", "conta": "principal", "h5": .95, "lido": 300})
            return {"h5": .8, "sem": .65, "lido": 200}
        with patch("contas.status", return_value={"logado": True, "email": "a@example.com"}), patch("contas.cotas", side_effect=cotas):
            self.app.conta_atualizar("principal")
        self.assertEqual(self.lista()[0]["cotas"]["h5"], .95)

    def test_troca_usa_medicao_nova_e_notifica_interface(self):
        with patch.object(self.app, "conta_atualizar"), patch("contas.time.time", return_value=100):
            escolhida = self.app._conta_automatica("principal", {"principal"}, threading.Event())
        self.assertEqual(escolhida, "outra")
        self.assertEqual(self.k._ler_estado()["conta"], "outra")
        self.assertEqual(self.app._para_janela.call_args.args[0]["t"], "conta_trocada")

    def test_falha_da_sonda_nao_apaga_cota_mas_impede_troca(self):
        with patch("contas.status", return_value={"logado": True, "email": "b@example.com"}), patch("contas.cotas", return_value={"erro": "offline"}):
            self.app.conta_atualizar("outra")
        self.assertEqual(self.lista()[1]["cotas"]["h5"], .3)
        with patch.object(self.app, "conta_atualizar"), patch("contas.time.time", return_value=100):
            self.assertIsNone(self.app._conta_automatica("principal", {"principal"}, threading.Event()))

    def test_status_indisponivel_nao_permite_usar_saldo_em_cache(self):
        with patch("contas.status", return_value={"logado": False, "erro": "sem resposta"}):
            self.app.conta_atualizar("outra")
        with patch.object(self.app, "conta_atualizar"), patch("contas.time.time", return_value=100):
            self.assertIsNone(self.app._conta_automatica("principal", {"principal"}, threading.Event()))

    def test_troca_cancelada_nao_altera_conta_ativa(self):
        cancelada = threading.Event()
        cancelada.set()
        with patch.object(self.app, "conta_atualizar"), patch("contas.time.time", return_value=100):
            self.assertIsNone(self.app._conta_automatica("principal", {"principal"}, cancelada))
        self.assertEqual(self.k._ler_estado()["conta"], "principal")


if __name__ == '__main__':
    unittest.main(verbosity=2)
