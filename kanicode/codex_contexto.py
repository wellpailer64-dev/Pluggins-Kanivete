"""Orientação curta do Codex: caminhos reais, contrato e esforço por demanda.

Só o modo Codex usa este módulo. Não altera configurações globais nem o Claude.
"""
import os
import re
import unicodedata

import licoes
import organizacao_pailer

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
    modo += ("\nDurante tarefas, envie mensagens curtas de andamento ao usuário: antes de começar, "
             "ao concluir etapas relevantes e ao mudar de abordagem. Diga o que foi constatado e o próximo passo. "
             "Se a investigação demorar, atualize em cerca de 30–60 segundos quando houver informação útil. "
             "Não exponha raciocínio privado, não invente progresso e não espere o fim para informar bloqueios.")
    if re.search(r"whats|navegador|browser", _normalizar(tarefa)):
        navegador = os.path.join(os.path.dirname(RAIZ), "kanibrowser")
        modo += (
            "\nNAVEGADOR INTERNO: use primeiro a ponte local do KaniBrowser, não o controle externo do Chrome. "
            f'Estado: py -3.13 "{os.path.join(navegador, "kb.py")}" --onde kanicode --sem-foto estado. '
            "Abas: troque estado por abas; conteúdo: texto --aba ID. "
            f'WhatsApp: py -3.13 "{os.path.join(navegador, "wa.py")}" conversas --busca "nome" --porta 9333; '
            'ler --conversa "nome" --n 20 --porta 9333. '
            "Consulte o cabeçalho desses scripts para outras ações. Enviar exige pedido explícito. "
            "Use --onde kanicode no kb.py e --porta 9333 no wa.py para impedir acesso à porta 9222. "
            "Falha do controle externo não comprova falha do navegador interno; confira a ponte antes de concluir.")
    if retomar:
        return tarefa + modo + organizacao_pailer.contexto(tarefa)
    partes = [tarefa + modo,
              "CONTEXTO DO KANICODE (orientação inicial; não é uma tarefa extra):\n"
              "Responda em pt-BR, curto. Cumprimento/pergunta sem necessidade de código: responda sem ferramentas. "
              "Pedido concreto autoriza trabalhar; preserve o escopo/contrato, alterações locais e regras do projeto. "
              "Não faça commit/push, publicação, exclusões ou feche programas sem pedido explícito.\n"
              "Exceção autorizada pelo Pailer: pode reiniciar o KaniCode para aplicar mudanças usando o botão "
              "Reiniciar KaniCode no topo. O mesmo fluxo pode ser solicitado pelo canal local com "
              "py -3.13 kanicode.py reiniciar; ele aguarda as tarefas terminarem. A autorização não inclui "
              "reiniciar o Kanivete nem outros programas.\n"
              "Ache o trecho pelo mapa/busca antes de abrir arquivos grandes; limite saídas a ~80 linhas. "
              "Leia só o guia do assunto e teste o que mudou. Falha de ferramenta/permissão: informe a causa, "
              "não repita a mesma tentativa. Python deste PC: py -3.13; PowerShell: caminhos com espaços entre aspas.\n"
              f"KaniCode é um PLUGIN, separado do Kanivete. Código do KaniCode: {RAIZ}\n"
              f"Mapa curto: {os.path.join(RAIZ, 'MAPA.md')}\n"
              f'Mapa vivo do disco D (arquivos de clientes e pastas): py -3.13 "{os.path.join(RAIZ, "mapa_d.py")}" buscar "nome do cliente" --ext pdf --limite 20\n'
              "Use o mapa antes de varrer o disco. Ele indexa nomes e caminhos; parcial=true não prova ausência. "
              "Confirme o caminho antes de usar; status informa a saúde do monitor.\n"
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
    preferencia = organizacao_pailer.contexto(tarefa)
    try:
        from tarefas_agente import contexto
        pendencias=contexto(pasta,tarefa,agente='codex')
        if pendencias and not any(pendencias in parte for parte in partes) and pendencias not in tarefa:
            partes.append(pendencias)
    except Exception:
        pass
    if preferencia and not any("PREFERÊNCIAS DE ORGANIZAÇÃO DO PAILER" in parte for parte in partes):
        partes.append(preferencia.strip())
    return "\n\n".join(partes)
