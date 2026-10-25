"""Senha adicional do perfil no Drive; a autorização Google continua obrigatória."""
import base64
import hashlib
import hmac
import json
import secrets

import google_calendar as google
import perfil_portatil as perfil

_ITERACOES = 600_000
_SESSOES = {}
_NOME = 'acesso-kanicode.json'


class AcessoPerfil:
    def __init__(self, nuvem):
        self.nuvem=nuvem
        self.arq=nuvem.dados/'perfil/acesso.dpapi'
        self.chave=str(nuvem.dados.resolve())

    def _sessao(self):
        if self.chave in _SESSOES: return _SESSOES[self.chave]
        try:
            bruto=base64.b64decode(self.arq.read_text(encoding='utf-8'),validate=True)
            s=json.loads(google._dpapi(bruto,False))
            if isinstance(s,dict) and set(s)=={'email','assinatura'} and all(isinstance(v,str) for v in s.values()):
                _SESSOES[self.chave]=s
                return s
        except (OSError,ValueError,google.FalhaCalendar): pass
        return {}

    def status(self):
        s=self._sessao()
        valido=bool(s) and s.get('email')==self.nuvem._email()
        return {'autenticado':valido,'requer_acesso':not valido,'email':s.get('email','') if valido else self.nuvem._email()}

    def _registro(self, access, pasta):
        itens=self.nuvem._listar(access,"'"+pasta+"' in parents and name = '"+_NOME+"'")
        if len(itens)>1: raise ValueError('Há cadastros de acesso duplicados na pasta KaniCode. Não foi possível determinar qual usar.')
        if not itens: return None
        texto=self.nuvem._conteudo(access,itens[0]['id'],16*1024)
        try:
            r=json.loads(texto)
            if (r.get('formato')!='kanicode-acesso' or r.get('versao')!=1 or r.get('iteracoes')!=_ITERACOES
                or not isinstance(r.get('email'),str) or len(bytes.fromhex(r['sal']))!=16 or len(bytes.fromhex(r['hash']))!=32):
                raise ValueError()
        except (ValueError,KeyError,TypeError,AttributeError):
            raise ValueError('Cadastro de acesso inválido no Drive. Nenhum perfil foi alterado.') from None
        return {'id':itens[0]['id'],'dados':r}

    def autorizado(self, access, pasta, conta):
        r=self._registro(access,pasta)
        if not r:
            self._invalidar();return False,False
        if r['dados']['email']!=conta: raise ValueError('O cadastro do KaniCode pertence a outro e-mail.')
        s=self._sessao()
        assinatura=perfil._hash(perfil._json(r))
        valido=bool(s.get('email')==conta and hmac.compare_digest(s.get('assinatura',''),assinatura))
        if not valido: self._invalidar()
        return valido,True

    def _invalidar(self):
        _SESSOES.pop(self.chave,None)
        if self.arq.exists(): perfil._gravar(self.arq,'')

    def _lembrar(self, registro, email, lembrar):
        s={'email':email,'assinatura':perfil._hash(perfil._json(registro))}
        _SESSOES[self.chave]=s
        # Nunca guarda a senha ou o hash verificável da senha neste PC.
        perfil._gravar(self.arq,'')
        if lembrar:
            try:
                protegido=base64.b64encode(google._dpapi(perfil._json(s).encode())).decode('ascii')
                perfil._gravar(self.arq,protegido)
            except google.FalhaCalendar:
                return False
        return lembrar

    def executar(self, acao='status', campos=None):
        if acao=='status': return self.status()
        if acao=='sair':
            _SESSOES.pop(self.chave,None);perfil._gravar(self.arq,'')
            return dict(self.status(),mensagem='Acesso encerrado neste PC. Os dados locais e o perfil do Drive foram preservados.')
        if acao not in ('cadastrar','entrar'): raise ValueError('Ação de acesso inválida.')
        campos=campos or {}
        email=campos.get('email','');senha=campos.get('senha','');lembrar=campos.get('lembrar',True)
        if not isinstance(email,str) or not isinstance(senha,str) or type(lembrar) is not bool:
            raise ValueError('Informe e-mail e senha válidos.')
        from perfil_nuvem import normalizar_email
        email=normalizar_email(email)
        if not email or '@' not in email or len(email)>200: raise ValueError('Informe um e-mail válido.')
        if not senha or len(senha)>1024: raise ValueError('Informe uma senha de até 1024 caracteres.')
        conta,access=self.nuvem._acesso(email)
        pasta=self.nuvem._pasta(access);registro=self._registro(access,pasta)
        if acao=='cadastrar':
            if registro: raise ValueError('Este e-mail já tem senha cadastrada no Drive. Use Entrar no meu perfil.')
            if len(senha)<12: raise ValueError('Use uma senha própria do KaniCode com pelo menos 12 caracteres.')
            if campos.get('confirmacao')!=senha: raise ValueError('As duas senhas precisam ser iguais.')
            sal=secrets.token_bytes(16)
            r={'formato':'kanicode-acesso','versao':1,'email':conta,'iteracoes':_ITERACOES,'sal':sal.hex(),
               'hash':hashlib.pbkdf2_hmac('sha256',senha.encode('utf-8'),sal,_ITERACOES).hex()}
            self.nuvem._enviar_json(access,{'name':_NOME,'mimeType':'application/json','parents':[pasta]},r)
            registro=self._registro(access,pasta)
            if not registro or registro['dados']!=r: raise ValueError('O Drive não confirmou o cadastro. Tente entrar com a senha cadastrada.')
        else:
            if not registro: raise ValueError('Ainda não existe acesso cadastrado nessa conta. Use Cadastrar meu acesso.')
            r=registro['dados']
            calculado=hashlib.pbkdf2_hmac('sha256',senha.encode('utf-8'),bytes.fromhex(r['sal']),_ITERACOES)
            if r['email']!=conta or not hmac.compare_digest(calculado,bytes.fromhex(r['hash'])):
                raise ValueError('E-mail ou senha do KaniCode incorretos.')
        cadastro=perfil._ler(self.nuvem.dados/'perfil/usuario.json',{})
        cadastro['email']=conta;perfil._gravar(self.nuvem.dados/'perfil/usuario.json',perfil._json(cadastro))
        lembrado=self._lembrar(registro,conta,lembrar)
        return dict(self.status(),lembrado=lembrado,
                    mensagem='Acesso liberado. '+('Este PC vai lembrar seu acesso.' if lembrado else 'A sessão vale até fechar o KaniCode.'))
