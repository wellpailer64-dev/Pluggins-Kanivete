"""Perfil no Drive autenticado; versões imutáveis preservam alterações simultâneas."""
import json
import threading
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import perfil_portatil as perfil
from google_drive_arquivos import _abrir, _id

_TRAVA = threading.RLock()


def normalizar_email(email):
    """No Gmail, pontos e +sufixo não mudam a conta (well.pailer64 = wellpailer.64)."""
    email=str(email or '').strip().casefold()
    nome,arroba,dominio=email.rpartition('@')
    if arroba and dominio in ('gmail.com','googlemail.com'):
        return nome.split('+',1)[0].replace('.','')+'@gmail.com'
    return email


class PerfilNuvem:
    def __init__(self, drive, dados=perfil.DADOS, app=perfil.APP):
        self.drive, self.dados, self.app = drive, Path(dados), Path(app)
        self.arq = self.dados/'perfil/nuvem.json'

    def _ler(self):
        return perfil._ler(self.arq,{})

    def _salvar(self, estado):
        perfil._gravar(self.arq,perfil._json(estado))

    def _email(self):
        return normalizar_email(perfil._ler(self.dados/'perfil/usuario.json',{}).get('email',''))

    def status(self):
        e=self._ler()
        from perfil_acesso import AcessoPerfil
        return {'ativo':bool(e.get('ativo')), 'conta':e.get('conta',''),
                'mensagem':e.get('mensagem','Conecte a conta Google e entre no perfil para sincronizar.'),
                **AcessoPerfil(self).status()}

    def _acesso(self, email=None):
        email=self._email() if email is None else normalizar_email(email)
        if not email or '@' not in email: raise ValueError('Preencha e salve seu e-mail em Meu perfil → Informações básicas.')
        with self.drive._lock():
            access=self.drive._exigir_escrita()
            usuario=self.drive._pedido('GET','about',access,fields='user(emailAddress)').get('user',{})
        conta=normalizar_email(usuario.get('emailAddress',''))
        if conta!=email: raise ValueError('A conta Google autenticada não corresponde ao e-mail do Meu perfil. Conecte a conta correta.')
        return conta,access

    def _listar(self, access, query):
        saida=[]; pagina=''
        while True:
            params={'q':query+' and trashed = false','pageSize':100,
                    'fields':'nextPageToken,incompleteSearch,files(id,name,mimeType,description)', 'pageToken':pagina}
            r=self.drive._pedido('GET','files',access,**params)
            if r.get('incompleteSearch'): raise ValueError('Busca incompleta no Drive. Tente novamente antes de sincronizar.')
            saida.extend(r.get('files',[]));pagina=r.get('nextPageToken','')
            if not pagina: return saida

    def _pasta(self, access):
        pastas=self._listar(access,"'root' in parents and name = 'KaniCode' and mimeType = 'application/vnd.google-apps.folder'")
        if len(pastas)>1: raise ValueError('Há mais de uma pasta KaniCode no Meu Drive. Escolha uma única pasta com esse nome antes de sincronizar.')
        if pastas: return _id(pastas[0]['id'])
        return _id(self.drive._pedido('POST','files',access,{'name':'KaniCode','mimeType':'application/vnd.google-apps.folder','parents':['root']},fields='id')['id'])

    def _versoes(self, access, pasta):
        arquivos=self._listar(access,"'"+_id(pasta)+"' in parents and mimeType = 'application/json'")
        versoes={};pais=set()
        for a in arquivos:
            if not a.get('name','').startswith('perfil-'): continue
            try: meta=json.loads(a.get('description',''))
            except (ValueError,TypeError): continue
            if meta.get('formato')!='kanicode-nuvem-1': continue
            revisao=meta.get('revisao',''); anteriores=meta.get('pais',[])
            if len(revisao)!=64 or not isinstance(anteriores,list) or not all(isinstance(p,str) for p in anteriores):
                raise ValueError('Metadados de versão do perfil inválidos no Drive.')
            versoes[a['id']]=dict(a,revisao=revisao);pais.update(anteriores)
        atuais=[a for id,a in versoes.items() if id not in pais]
        if versoes and not atuais: raise ValueError('O histórico do perfil no Drive não tem uma versão atual válida.')
        return atuais

    def _conteudo(self, access, id, limite):
        url='https://www.googleapis.com/drive/v3/files/'+_id(id)+'?alt=media'
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+access})
        with _abrir(req) as r: bruto=r.read(limite+1)
        if len(bruto)>limite: raise ValueError('Arquivo do Drive ultrapassa o tamanho permitido.')
        return bruto.decode('utf-8')

    def _baixar(self, access, remoto):
        texto=self._conteudo(access,remoto['id'],perfil.LIMITE*2);p=perfil.validar(texto)
        if p['revisao']!=remoto['revisao']: raise ValueError('A revisão do perfil não corresponde ao arquivo do Drive.')
        return texto

    def _enviar(self, access, pasta, pacote, pais):
        # Arquivos novos por revisão: uma corrida entre PCs nunca sobrescreve o outro.
        meta={'name':'perfil-'+pacote['revisao']+'.json','mimeType':'application/json','parents':[pasta],
              'description':perfil._json({'formato':'kanicode-nuvem-1','revisao':pacote['revisao'],'pais':pais})}
        return self._enviar_json(access,meta,pacote)

    def _enviar_json(self, access, meta, conteudo):
        borda='kanicode_'+uuid.uuid4().hex
        corpo=('--'+borda+'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+perfil._json(meta)+
               '\r\n--'+borda+'\r\nContent-Type: application/json\r\n\r\n'+perfil._json(conteudo)+'\r\n--'+borda+'--\r\n').encode('utf-8')
        url='https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id'
        req=urllib.request.Request(url,data=corpo,method='POST',headers={'Authorization':'Bearer '+access,'Content-Type':'multipart/related; boundary='+borda})
        with _abrir(req) as r: resultado=json.load(r)
        if not resultado.get('id'): raise ValueError('O Drive não confirmou o envio. Confira novamente antes de repetir.')
        return resultado['id']

    def executar(self, acao='sincronizar', restaurar=None, escolha='', conferencia='', politica='manter'):
        with _TRAVA:
            e=self._ler()
            if acao=='status': return self.status()
            if acao=='pausar':
                e.update(ativo=False,mensagem='Sincronização do perfil pausada neste PC.');self._salvar(e);return self.status()
            if acao not in ('ativar','sincronizar','conferir','restaurar','publicar'): raise ValueError('Ação do perfil inválida.')
            if acao=='sincronizar' and not e.get('ativo'): return self.status()
            conta,access=self._acesso()
            if e.get('conta') and e['conta']!=conta:
                if acao!='ativar': raise ValueError('A conta mudou. Ative a sincronização para vincular este PC à nova conta.')
                e={}  # outra conta nunca herda a revisão-base da anterior
            if acao=='ativar': e.update(ativo=True,conta=conta)
            pasta=self._pasta(access)
            from perfil_acesso import AcessoPerfil
            autorizado,cadastrado=AcessoPerfil(self).autorizado(access,pasta,conta)
            if not autorizado:
                mensagem='Entre com a senha do KaniCode para acessar o perfil do Drive.' if cadastrado else 'Cadastre sua senha do KaniCode para ativar o perfil do Drive.'
                if acao not in ('ativar','sincronizar'): raise ValueError(mensagem)
                return dict(self.status(),autenticado=False,requer_acesso=True,cadastrado=cadastrado,mensagem=mensagem)
            cabecas=self._versoes(access,pasta)
            pacote=perfil.montar(self.dados,self.app);local=pacote['revisao']
            remoto=next((a for a in cabecas if a['id']==escolha),None) if escolha else (cabecas[0] if len(cabecas)==1 else None)
            if acao in ('conferir','restaurar'):
                if not remoto: raise ValueError('Escolha uma versão atual do perfil no Drive e confira novamente.')
                texto=self._baixar(access,remoto)
                if acao=='conferir': return {'texto':texto,'id':remoto['id']}
                if not restaurar: raise ValueError('Restauração indisponível.')
                resultado=restaurar(texto,conferencia,politica)
                e.update(base=remoto['id'],local=perfil.montar(self.dados,self.app)['revisao'],conta=conta,
                         mensagem='Perfil restaurado do Drive. Reinicie o KaniCode pelo botão do topo para aplicar.')
                self._salvar(e);return resultado
            if remoto and len(cabecas)==1 and local==remoto['revisao']:
                e.update(base=remoto['id'],local=local,mensagem='Perfil atualizado no Drive e neste PC.')
            elif acao=='publicar' or not cabecas or (remoto and len(cabecas)==1 and remoto['id']==e.get('base')):
                if acao=='publicar' and not conferencia==perfil._hash(perfil._json({'local':local,'remotos':sorted(a['id'] for a in cabecas)})):
                    raise ValueError('Os perfis mudaram. Sincronize e confira antes de publicar este PC.')
                enviado=self._enviar(access,pasta,pacote,[a['id'] for a in cabecas])
                e.update(base=enviado,local=local,mensagem='Perfil salvo em Meu Drive / KaniCode. Versões anteriores preservadas.')
            elif remoto and len(cabecas)==1 and local==e.get('local') and restaurar:
                texto=self._baixar(access,remoto)
                # Alterações já sincronizadas podem vir automaticamente, sempre com backup.
                previa=perfil.previa(texto,self.dados,self.app)
                if any(a['arquivo']=='rotinas.json' and a['estado']!='igual' for a in previa['arquivos']):
                    e['mensagem']='Há uma versão no Drive para conferir antes de restaurar.'
                else:
                    restaurar(texto,previa['conferencia'],'substituir')
                    e.update(base=remoto['id'],local=perfil.montar(self.dados,self.app)['revisao'],mensagem='Perfil atualizado do Drive. Reinicie pelo botão do topo para aplicar.')
            else:
                e['mensagem']='Perfil encontrado no Drive. Confira antes de restaurar: há dados locais diferentes ou este é um novo PC.'
            e['conta']=conta;self._salvar(e)
            cabecas=self._versoes(access,pasta)
            r=self.status();r['versoes']=[{'id':a['id'],'revisao':a['revisao']} for a in cabecas]
            r['conferencia']=perfil._hash(perfil._json({'local':perfil.montar(self.dados,self.app)['revisao'],'remotos':sorted(a['id'] for a in cabecas)}))
            return r


def executar(acao='status', restaurar=None, escolha='', conferencia='', politica='manter'):
    from google_drive import drive
    return PerfilNuvem(drive).executar(acao,restaurar,escolha,conferencia,politica)
