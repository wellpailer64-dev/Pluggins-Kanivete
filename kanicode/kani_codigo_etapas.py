"""Reutiliza contratos e verificadores do código na cópia; nunca aplica na origem."""
import json
from pathlib import Path

import codigo_agente as codigo
from kani_orquestracao import Ferramenta


def adicionar(ferramentas,pasta,evento,parar,permitidas=None):
    for nome,descricao in codigo.FERRAMENTAS.items():
        if permitidas is not None and nome not in permitidas: continue
        def preparar(args,t,n=nome):
            if n in ('codigo_preparar','codigo_incluir'):
                arquivos=str(args.get('arquivos','')).split(';')
                pedido=(t['pedido']+' '+str(t.get('informacoes',[]))).replace('\\','/').lower()
                if not arquivos or any(not a.strip() or codigo.relativo(a.strip()).lower() not in pedido for a in arquivos):
                    raise PermissionError('Informe explicitamente os arquivos do contrato de código.')
            elif t.get('codigo_sessao'):
                atual=codigo.Contexto(pasta,'kani').carregar()
                if atual.pasta.name != t['codigo_sessao']:
                    raise PermissionError('A sessão de código mudou; confira a cópia antes de retomar.')
            return args
        def executar(args,n=nome):
            return codigo.executar(n,args,pasta,'kani',parar)
        def verificar(args,bruto,criterio,n=nome):
            if str(bruto).startswith('NÃO FEITO:'): return {'ok':False,'motivo':'O verificador de código recusou a operação.'}
            with codigo.TRAVA:
                ctx=codigo.Contexto(pasta,'kani').carregar()
                revisao=ctx.revisar()
                dados={'sessao':revisao['sessao'],'copia':revisao['copia'],'revisao':revisao['revisao']}
                if n in ('codigo_verificar','codigo_testar'):
                    r=json.loads(bruto)
                    if r.get('ok') is not True: return {'ok':False,'motivo':'Sintaxe ou testes falharam na cópia.'}
                    return {'ok':True,'dados':dados,'resumo':'Verificação na cópia confirmou sucesso: '+n}
                if n in ('codigo_criar','codigo_substituir','codigo_ler'):
                    arquivo=ctx.arquivo(args['caminho'])
                    if not arquivo.is_file(): return {'ok':False,'motivo':'Arquivo ausente na cópia.'}
                    texto=arquivo.read_text(encoding='utf-8-sig').replace('\r\n','\n')
                    if n=='codigo_criar' and texto!=args['conteudo'].replace('\r\n','\n'):
                        return {'ok':False,'motivo':'Conteúdo da cópia não confere.'}
                    if n=='codigo_substituir' and args['depois'].replace('\r\n','\n') not in texto:
                        return {'ok':False,'motivo':'Substituição não confirmada na cópia.'}
                if n in ('codigo_criar','codigo_substituir','codigo_revisar'):
                    evento({'t':'codigo_alteracao','id':revisao['sessao'],'arquivo':'Código na cópia isolada','diff':revisao['diff'][:60000]})
                resumo='Código conferido SOMENTE na cópia: '+n+'\n'+str(bruto)[:900]
                return {'ok':True,'dados':dados,'resumo':resumo}
        leitura=nome in ('codigo_ler','codigo_revisar','codigo_verificar')
        ferramentas[nome]=Ferramenta(descricao,executar,verificar,leitura,preparar,aprovacao=nome=='codigo_testar')

