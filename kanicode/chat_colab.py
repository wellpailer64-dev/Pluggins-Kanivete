"""Canal dos chats para modelos com terminal: não depende de ferramentas MCP específicas."""
import argparse
import json
import socket
import sys


def chamar(de, para, acao='ler', texto='', n=10):
    pedido = dict(de=str(de), para=str(para), acao=acao, texto=texto, n=n)
    with socket.create_connection(('127.0.0.1', 47613), timeout=5) as s:
        s.settimeout(1900 if acao == 'enviar' else 15)
        s.sendall(('fio ' + json.dumps(pedido, ensure_ascii=False) + '\n').encode('utf-8'))
        with s.makefile('r', encoding='utf-8') as entrada:
            resposta = json.loads(entrada.readline())
    return resposta['texto']


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--de', required=True)
    p.add_argument('--para', required=True)
    p.add_argument('--acao', choices=['ler', 'enviar', 'colab'], default='ler')
    p.add_argument('--texto', default='')
    p.add_argument('--n', type=int, default=10)
    p.add_argument('--arquivo', help='arquivo UTF-8 com o JSON da ação Colab')
    a = p.parse_args()
    try:
        if a.arquivo:
            from pathlib import Path
            a.texto = Path(a.arquivo).read_text(encoding='utf-8-sig')
        resposta = chamar(a.de, a.para, a.acao, a.texto, a.n)
        print(resposta)
        sys.exit(1 if resposta.startswith('ERRO:') else 0)
    except (OSError, ValueError, KeyError) as e:
        print('ERRO: canal do KaniCode: ' + str(e))
        sys.exit(1)
