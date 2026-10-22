"""Operações do Drive: sem SDK, transferências em blocos e exclusão recuperável."""
import json
import mimetypes
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from google_calendar import FalhaCalendar, _salvar

API = 'https://www.googleapis.com/drive/v3/'
ESCOPO_TOTAL = 'https://www.googleapis.com/auth/drive'
PASTA = 'application/vnd.google-apps.folder'
CAMPOS = 'id,name,mimeType,parents,trashed,modifiedTime,size,capabilities(canDownload)'
EXPORTACOES = {
    'application/vnd.google-apps.document': {'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'pdf': 'application/pdf', 'txt': 'text/plain'},
    'application/vnd.google-apps.spreadsheet': {'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'pdf': 'application/pdf', 'csv': 'text/csv'},
    'application/vnd.google-apps.presentation': {'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'pdf': 'application/pdf'},
    'application/vnd.google-apps.drawing': {'pdf': 'application/pdf', 'png': 'image/png', 'svg': 'image/svg+xml'},
}


def _id(valor):
    if not isinstance(valor, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', valor):
        raise FalhaCalendar('Informe um ID válido de arquivo ou pasta do Drive.')
    return valor


def _nome(valor):
    if not isinstance(valor, str) or not valor.strip() or len(valor) > 255 or any(ord(c) < 32 for c in valor):
        raise FalhaCalendar('Informe um nome de 1 a 255 caracteres, sem caracteres de controle.')
    return valor.strip()


def _nome_local(valor):
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', valor).strip(' .')[:180].rstrip(' .') or 'arquivo'
    if nome.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        nome = '_' + nome
    return nome


def _abrir(req, parcial=False):
    try:
        return urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as exc:
        if parcial and exc.code == 308:
            return exc
        if exc.code == 401:
            texto = 'A autorização expirou. Reconecte o Google Drive.'
        elif exc.code == 403:
            texto = 'O Google recusou esta operação. Confira as permissões da conta e do arquivo, a quota e a Drive API.'
        elif exc.code == 404:
            texto = 'Arquivo ou pasta não encontrado, ou sem acesso nesta conta.'
        else:
            texto = f'O Google Drive recusou a operação (HTTP {exc.code}). Confira o estado do item antes de tentar novamente.'
        raise FalhaCalendar(texto) from None
    except OSError:
        raise FalhaCalendar('Falha de conexão com o Drive. Confira o resultado antes de repetir uma alteração.') from None


class OperacoesDrive:
    def _total(self, privado=None):
        p = self._privado() if privado is None else privado
        return ESCOPO_TOTAL in p.get('token', {}).get('scope', '').split()

    def _exigir_escrita(self):
        p = self._privado()
        if not self._total(p):
            raise FalhaCalendar('Autorize o controle total em Conexões → Google Drive antes de alterar arquivos.')
        return self._access(p)

    def _pedido(self, metodo, caminho, access, corpo=None, **params):
        url = API + caminho + ('?' + urllib.parse.urlencode(params) if params else '')
        dados = json.dumps(corpo, ensure_ascii=False).encode() if corpo is not None else None
        req = urllib.request.Request(url, data=dados, method=metodo,
                                     headers={'Authorization': 'Bearer ' + access, 'Content-Type': 'application/json'})
        with _abrir(req) as resposta:
            try:
                return json.load(resposta)
            except (ValueError, OSError):
                raise FalhaCalendar('Resposta incompleta do Drive. Confira o item antes de repetir a operação.') from None

    def _arquivo(self, id, access):
        return self._pedido('GET', 'files/' + _id(id), access, fields=CAMPOS, supportsAllDrives='true')

    def _pasta(self, id, access):
        item = self._arquivo(id, access)
        if item.get('mimeType') != PASTA or item.get('trashed'):
            raise FalhaCalendar('O destino precisa ser uma pasta do Drive fora da lixeira.')
        return item['id']

    def _invalidar(self):
        e = self._estado()
        e.update(arquivos=[], proxima='')
        _salvar(self.dados / 'google.json', e)

    def criar_pasta(self, nome, pasta='root'):
        nome = _nome(nome)
        with self._lock():
            access = self._exigir_escrita()
            destino = self._pasta(pasta, access)
            r = self._pedido('POST', 'files', access, {'name': nome, 'mimeType': PASTA, 'parents': [destino]}, fields=CAMPOS, supportsAllDrives='true')
            if not r.get('id') or r.get('name') != nome or r.get('mimeType') != PASTA:
                raise FalhaCalendar('Não foi possível confirmar a criação da pasta. Consulte o Drive antes de repetir.')
            self._invalidar()
            return r

    def renomear(self, id, nome):
        _id(id); nome = _nome(nome)
        with self._lock():
            access = self._exigir_escrita()
            r = self._pedido('PATCH', 'files/' + id, access, {'name': nome}, fields=CAMPOS, supportsAllDrives='true')
            if r.get('id') != id or r.get('name') != nome:
                raise FalhaCalendar('O Drive não confirmou o novo nome. Consulte o item antes de repetir.')
            self._invalidar()
            return r

    def mover(self, id, pasta):
        _id(id); _id(pasta)
        with self._lock():
            access = self._exigir_escrita()
            destino = self._pasta(pasta, access)
            if id == destino:
                raise FalhaCalendar('Uma pasta não pode ser movida para dentro dela mesma.')
            atual = self._arquivo(id, access)
            if atual.get('trashed'):
                raise FalhaCalendar('Restaure o item antes de mover.')
            pais = atual.get('parents', [])
            if pais == [destino]:
                return atual
            params = {'addParents': destino, 'fields': CAMPOS, 'supportsAllDrives': 'true'}
            remover = [p for p in pais if p != destino]
            if remover:
                params['removeParents'] = ','.join(remover)
            r = self._pedido('PATCH', 'files/' + id, access, {}, **params)
            if r.get('id') != id or destino not in r.get('parents', []):
                raise FalhaCalendar('O Drive não confirmou a pasta destino. Consulte o item antes de repetir.')
            self._invalidar()
            return r

    def lixeira(self, id, restaurar=False):
        _id(id)
        if not isinstance(restaurar, bool):
            raise FalhaCalendar('Informe se deseja restaurar o item.')
        with self._lock():
            access = self._exigir_escrita()
            r = self._pedido('PATCH', 'files/' + id, access, {'trashed': not restaurar}, fields=CAMPOS, supportsAllDrives='true')
            if r.get('id') != id or r.get('trashed') is not (not restaurar):
                raise FalhaCalendar('O Drive não confirmou a alteração da lixeira. Consulte o item antes de repetir.')
            self._invalidar()
            return r

    def enviar(self, caminho, pasta='root'):
        origem = Path(caminho).expanduser()
        if not origem.is_file():
            raise FalhaCalendar('Selecione um arquivo local existente para enviar.')
        with origem.open('rb') as arquivo:
            with self._lock():
                access = self._exigir_escrita()
            destino = self._pasta(pasta, access)
            stat = os.fstat(arquivo.fileno()); total = stat.st_size
            mime = mimetypes.guess_type(origem.name)[0] or 'application/octet-stream'
            metadados = {'name': origem.name, 'parents': [destino], 'mimeType': mime}
            if not total:
                r = self._pedido('POST', 'files', access, metadados, fields=CAMPOS, supportsAllDrives='true')
            else:
                url = 'https://www.googleapis.com/upload/drive/v3/files?' + urllib.parse.urlencode({'uploadType': 'resumable', 'fields': CAMPOS, 'supportsAllDrives': 'true'})
                req = urllib.request.Request(url, data=json.dumps(metadados).encode(), method='POST', headers={
                    'Authorization': 'Bearer ' + access, 'Content-Type': 'application/json', 'X-Upload-Content-Type': mime, 'X-Upload-Content-Length': str(total)})
                with _abrir(req) as resposta:
                    sessao = resposta.headers.get('Location', '')
                u = urllib.parse.urlsplit(sessao)
                if u.scheme != 'https' or u.hostname != 'www.googleapis.com' or not u.path.startswith('/upload/drive/') or u.username or u.password:
                    raise FalhaCalendar('O Drive retornou uma sessão de envio inválida.')
                inicio, r = 0, None
                while inicio < total:
                    bloco = arquivo.read(min(4 * 1024 * 1024, total - inicio))
                    agora = os.fstat(arquivo.fileno())
                    if not bloco or agora.st_size != total or agora.st_mtime_ns != stat.st_mtime_ns:
                        raise FalhaCalendar('O arquivo local mudou durante o envio. Nenhum envio completo foi confirmado.')
                    fim = inicio + len(bloco) - 1
                    with self._lock():
                        access = self._exigir_escrita()
                    req = urllib.request.Request(sessao, data=bloco, method='PUT', headers={
                        'Authorization': 'Bearer ' + access, 'Content-Type': mime, 'Content-Length': str(len(bloco)), 'Content-Range': f'bytes {inicio}-{fim}/{total}'})
                    with _abrir(req, parcial=True) as resposta:
                        if resposta.status == 308:
                            if resposta.headers.get('Range') != f'bytes=0-{fim}' or fim + 1 == total:
                                raise FalhaCalendar('O Drive não confirmou o bloco enviado. Consulte o destino antes de repetir.')
                        else:
                            r = json.load(resposta)
                            if fim + 1 != total:
                                raise FalhaCalendar('O Drive finalizou o envio antes da hora. Consulte o destino.')
                    inicio = fim + 1
            if not r or not r.get('id') or r.get('name') != origem.name or str(r.get('size', '')) != str(total):
                raise FalhaCalendar('Não foi possível confirmar o envio completo. Consulte o destino antes de repetir.')
            with self._lock():
                self._invalidar()
            return r

    def baixar(self, id, destino, formato=''):
        _id(id)
        pasta = Path(destino).expanduser().resolve()
        if not pasta.is_dir():
            raise FalhaCalendar('Escolha uma pasta local existente para receber o arquivo.')
        with self._lock():
            access = self._access(self._privado())
            item = self._arquivo(id, access)
            tipo = item.get('mimeType', '')
            if tipo == PASTA:
                raise FalhaCalendar('Para baixar uma pasta, selecione os arquivos dela individualmente.')
            if item.get('capabilities', {}).get('canDownload') is False:
                raise FalhaCalendar('O proprietário não permite baixar este arquivo.')
            nome = _nome_local(item.get('name', 'arquivo'))
            params = {'alt': 'media', 'supportsAllDrives': 'true'}
            caminho = 'files/' + id
            esperado = int(item['size']) if item.get('size') is not None else None
            if tipo.startswith('application/vnd.google-apps.'):
                opcoes = EXPORTACOES.get(tipo)
                if not opcoes:
                    raise FalhaCalendar('Este tipo de arquivo Google não tem exportação disponível nesta integração.')
                extensao = formato or next(iter(opcoes))
                if extensao not in opcoes:
                    raise FalhaCalendar('Formato de exportação inválido. Opções: ' + ', '.join(opcoes))
                params = {'mimeType': opcoes[extensao]}; caminho += '/export'; esperado = None
                if not nome.lower().endswith('.' + extensao):
                    nome += '.' + extensao
            alvo = pasta / nome
            if alvo.exists():
                raise FalhaCalendar('Já existe um arquivo com esse nome na pasta destino. Escolha outra pasta ou renomeie o arquivo existente.')
            req = urllib.request.Request(API + caminho + '?' + urllib.parse.urlencode(params), headers={'Authorization': 'Bearer ' + access})
            parcial = None
            try:
                with _abrir(req) as resposta, tempfile.NamedTemporaryFile(dir=pasta, prefix='.kanicode_', suffix='.part', delete=False) as saida:
                    parcial = Path(saida.name); tamanho = 0
                    while bloco := resposta.read(1024 * 1024):
                        saida.write(bloco); tamanho += len(bloco)
                if esperado is not None and tamanho != esperado:
                    raise FalhaCalendar('Download incompleto. Nenhum arquivo final foi gravado.')
                # rename no Windows recusa sobrescrever um destino criado durante o download.
                if alvo.exists():
                    raise FalhaCalendar('O nome de destino passou a existir. Nenhum arquivo foi sobrescrito.')
                os.rename(parcial, alvo)
                return {'id': id, 'nome': nome, 'caminho': str(alvo), 'bytes': tamanho}
            except OSError:
                raise FalhaCalendar('Não foi possível concluir o download. Confira a rede, a pasta destino e o espaço disponível.') from None
            finally:
                if parcial is not None:
                    parcial.unlink(missing_ok=True)
