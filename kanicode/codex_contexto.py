"""Orientação curta do Codex: caminhos reais, contrato e esforço por demanda.

Só o modo Codex usa este módulo. Não altera configurações globais nem o Claude.
"""
import os
import re
import unicodedata

import licoes

RAIZ = os.path.dirname(os.path.realpath(__file__))


def _normalizar(texto):
    return unicodedata.normalize("NFD", texto.lower()).encode("ascii", "ignore").decode()


def conversa(tarefa):
    """Só cumprimentos completos; 'oi, corrija o bug' já é uma demanda."""
    return bool(re.fullmatch(
        r"(?:oi|ola|bom dia|boa tarde|boa noite|obrigad[oa]|valeu|ok|perfeito|tudo bem)"
        r"(?:[\s!,.?]|codex|kani|pailer)*", _normalizar(tarefa.strip())))


def esforco(tarefa):
    """Pedidos curtos usam low; investigação e mudanças amplas usam medium."""
    if conversa(tarefa):
        return "low"
    complexo = re.search(r"arquitet|investig|diagnostic|otimiz|desempenh|seguranca|migrac|concorr|"
                         r"trav[aou]|deadlock|refator|multipl|corrigir.*erro", _normalizar(tarefa))
    return "medium" if complexo or len(tarefa) > 500 else "low"


def preparar(tarefa, pasta, editar, retomar):
    """Orienta uma vez, inclusive se a primeira mensagem for só 'oi'."""
    modo = ("\n\nMODO ATUAL: execução; escrita disponível, o pedido define o que fazer." if editar else
            "\n\nSOMENTE LEITURA: analise/planeje; não altere arquivos nem o app.")
    if retomar:
        return tarefa + modo
    partes = [tarefa + modo,
              "CONTEXTO DO KANICODE (orientação inicial; não é uma tarefa extra):\n"
              "Responda em pt-BR, curto. Cumprimento/pergunta sem necessidade de código: responda sem ferramentas. "
              "Pedido concreto autoriza trabalhar; preserve o escopo/contrato, alterações locais e regras do projeto. "
              "Não faça commit/push, publicação, exclusões ou feche programas sem pedido explícito.\n"
              "Ache o trecho pelo mapa/busca antes de abrir arquivos grandes; limite saídas a ~80 linhas. "
              "Leia só o guia do assunto e teste o que mudou. Falha de ferramenta/permissão: informe a causa, "
              "não repita a mesma tentativa. Python deste PC: py -3.13; PowerShell: caminhos com espaços entre aspas.\n"
              f"KaniCode é um PLUGIN, separado do Kanivete. Código do KaniCode: {RAIZ}\n"
              f"Mapa curto: {os.path.join(RAIZ, 'MAPA.md')}\n"
              f'Busca com linhas atuais: py -3.13 "{os.path.join(RAIZ, "mapa_codigo.py")}" --busca termo\n'
              "Nesse plugin: janela/estilo/eventos = ui/janela.html; ponte Python = kanicode.py; "
              "motor Codex = ajudantes.py; orientação = codex_contexto.py; equipe MCP = mcp_equipe.py. "
              "Para mexer no KaniCode, comece nesses arquivos, mesmo que a pasta ativa seja o Kanivete."]
    if os.path.isfile(os.path.join(pasta, "tools", "mapa_geral.py")):
        partes.append("Projeto ativo Kanivete: mapa por assunto = py -3.13 tools/mapa_geral.py --busca termo; "
                      "editor/imagem/vetor = py -3.13 tools/mapa_codigo.py <area> --busca termo. "
                      "Contrato/edição: tools/patch.py; aplicar no app em uso: tools/aplicar.py (não recarregue). "
                      "Leia só os trechos relevantes de Instructions/MAPA.md e CLAUDE.md.")
    # O modo Equipe já anexa regras e lições; o modo direto passa a recebê-las também.
    if "REGRAS DESTE PROJETO" not in tarefa and "ARMADILHAS JÁ CONHECIDAS" not in tarefa:
        extra = licoes.anexo(pasta, tarefa)
        if extra:
            partes.append(extra)
    return "\n\n".join(partes)
