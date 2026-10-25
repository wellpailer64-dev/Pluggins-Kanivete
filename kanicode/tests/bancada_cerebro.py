"""Bancada do cérebro: mede a BUSCA (sem LLM) com perguntas reais do dia a dia do Pailer.

py -3.13 tests/bancada_cerebro.py [--modo v1|semantica|lexical|hibrido|todos] [--detalhe] [--validacao] [--contexto]

Cada pergunta tem as chaves esperadas (basta acertar uma; casa por pedaço da chave). As negativas não deveriam trazer nada.
Lê o cérebro real (só leitura: marcar=False, nada é gravado)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

PERGUNTAS = [
    ("como o Pailer quer as legendas, com caixa ou contorno?", ["padrao-legenda"]),
    ("posso escrever as mensagens em inglês para ele?", ["sempre-portugues"]),
    ("onde guardar cache, testes e modelos baixados? pode ir no C?", ["tudo-disco-d", "teste-appdata", "disco-c-so-sistema"]),
    ("qual versão do python roda o app e os testes", ["python-313"]),
    ("vídeo de celular veio com 59,18 quadros por segundo, que taxa usar na timeline", ["taxa-cravada"]),
    ("devo responder com textos longos e detalhados?", ["Respostas curtas"]),
    ("posso simular cliques no programa que ele está usando para testar a interface?", ["clique-app-usuario"]),
    ("recarregar a página do kanivete aberto do usuário", ["recarregar-app-usuario"]),
    ("gerar o executável apaga os modelos de IA?", ["release-flow"]),
    ("qual versão do logotipo do Carlinhos usar em fundo escuro", ["logo-por-fundo"]),
    ("o que o Carlinhos mudou quando finalizou o carrossel que eu fiz", ["correcoes-carlinhos"]),
    ("quantas palavras e qual margem as peças da agência costumam ter", ["gabarito-pailer"]),
    ("música do reels de black friday sem licença para o cliente", ["reels-bf-carlinhos"]),
    ("duas pessoas conversando, como alternar a câmera entre elas", ["multicam-duas-faixas"]),
    ("no depoimento, quando entra o rosto e quando entra imagem de apoio", ["rosto-primeiro"]),
    ("o drone fica corrigindo o ângulo no meio da tomada", ["drone-estavel-lettering"]),
    ("qual voz usar nos testes de narração sintetizada", ["voz-testes-fran"]),
    ("arquivo de patch com várias trocas no mesmo arquivo só aplicou a primeira", ["patch-blocos"]),
    ("alterei o código do kanicode, o que preciso fazer no final", ["kanicode-recarregar"]),
    ("mandar mensagem no grupo do whatsapp", ["whatsapp-envio", "whatsapp-claude-code"]),
    ("como ver as demandas abertas do laboratório panda", ["laboratorio-panda", "plugin_pandalab", "pandalab-workflow"]),
    ("tabelas abertas sem login e troca de senha do sistema do panda", ["seguranca_pandalab"]),
    ("ligar as lâmpadas e tomadas tuya pela voz", ["casa_inteligente"]),
    ("teaser do condomínio náutico com drone", ["nautic-bay"]),
    ("clipe musical do Dago para a Brasativa", ["clipe-dago"]),
    ("prestação de contas do Mega Artesanal", ["cultsp-mega-artesanal", "cultsp-padrao-edicao", "cultsp-videos-status"]),
    ("documentário da linha 4 com o Edgar", ["arco-edgar"]),
    ("posso enviar e-mail em nome dele?", ["nunca-enviar-emails"]),
    ("posso entrar no painel da vercel para conferir o deploy?", ["vercel-nao-acessar"]),
    ("feed e story no mesmo projeto do photo", ["pranchetas-formatos"]),
    ("pessoa recortada sem fundo parece colada, como deixar natural", ["humanizacao-cenario", "humanizacao-bancos"]),
    ("pode usar travessão nos textos?", ["sem-travessao"]),
    ("aplicar desfoque e contraste direto na camada de pixels", ["ajuste-no-objeto"]),
    ("como devem ser os controles deslizantes da interface", ["barras-delicadas"]),
    ("terminei uma animação, como organizar a timeline em composições", ["motion-comps-cenas"]),
    ("como explicar uma conclusão técnica para o Pailer", ["explicar-com-analogia"]),
    ("modelo de linguagem pequeno entende melhor com exemplos no prompt?", ["small-llm-fewshot"]),
    ("a voz sintetizada pronuncia errado as palavras com acento", ["tts-portuguese-accents"]),
    ("montar orçamento para cliente em folha A4", ["orcamento_cliente"]),
    ("texto por cima de vídeo com muito movimento não dá para ler", ["texto-sobre-imagem"]),
    ("conferir o monitor antes e depois de mexer na comp", ["lic:48a8529374", "motion-comps-cenas"]),
    ("elemento com hidden continua aparecendo por causa do display flex", ["lic:430df453a0", "testar-visivel"]),
    ("no git bash um argumento começando com barra vira caminho do windows", ["lic:f7dcfcb806"]),
    ("onde ficam e como se organizam as pastas de clientes no disco", ["pref:organizacao_clientes"]),
    ("receita de rolagem infinita com parallax", ["pro:f845ee3e"]),
    ("pro:89bcc8cb", ["pro:89bcc8cb"]),
    ("feedback-emenda-export", ["emenda-export"]),
    ("como está a evolução do cérebro do kanicode", ["pro:370a72ffe229"]),
    ("tirar o fundo de uma foto de produto usando a placa de vídeo", ["remover-fundo"]),
    ("criar uma imagem nova com inteligência artificial no computador", ["gerador-imagem"]),
]
# validação: escritas DEPOIS da calibragem (limites e sinônimos não foram ajustados para elas) — mede se generaliza
VALIDACAO = [
    ("como faço o Pailer ver o resultado quando termino o trabalho", ["deixar-aberto"]),
    ("flyer: como garantir que o texto se leia em cima da foto", ["acabamento-flyer", "texto-sobre-imagem"]),
    ("carrossel com enfeites e formas soltas em todos os slides", ["formas-com-funcao"]),
    ("onde fica a biblioteca de recursos e modelos de design", ["biblioteca-kanivete"]),
    ("app de teste aberto, como fechar sem matar o processo errado", ["fechar-app-teste"]),
    ("painéis soltos no segundo monitor", ["dois-monitores"]),
    ("onde cortar entre as falas e evitar piscada depois do motion", ["edicao-ritmo"]),
    ("o que aprendi estudando os PSDs do Pailer", ["metodo-photoshop-pailer"]),
    ("um trecho do vídeo exportado saiu errado, preciso exportar tudo de novo?", ["emenda-export"]),
    ("quanto custou em tokens fazer o carrossel 3D", ["custo-tokens"]),
    ("o logo foi recusado, como desenhar com mais qualidade", ["logotipo-qualidade"]),
    ("visão geral dos arquivos e comandos do app, por onde começar", ["mapa-geral"]),
    ("material em 4K pesado deixando a exportação lenta", ["teste-4k"]),
    ("assistente local que executa contratos no Photo", ["worker-local"]),
    ("pessoa gerada por IA ficou com a cabeça cortada", ["pessoa-gerada"]),
]
NEGATIVAS_VALIDACAO = ["como consertar torneira pingando", "melhores praias da Grécia", "quem inventou o telefone"]
NEGATIVAS = ["receita de bolo de cenoura com cobertura", "qual é a capital da Mongólia", "cotação do bitcoin hoje",
             "como trocar o pneu furado do carro", "regras do campeonato de xadrez", "história do império romano"]


def buscador(modo):
    if modo == "v1":
        import perfil_cerebro as pc
        return lambda q, k: [r["chave"] for r in pc.consultar(q, k, marcar=False)]
    import cerebro_motor as cm
    return lambda q, k: [r["chave"] for r in cm.buscar(q, k=k, modo=modo, marcar=False)]


def avaliar(modo, detalhe=False, perguntas=None, negativas=None):
    perguntas, negativas = perguntas or PERGUNTAS, negativas or NEGATIVAS
    busca = buscador(modo)
    busca("aquecer", 5)    # índice e modelo carregados fora da medida
    h1 = h3 = h5 = mrr = 0
    tempos, falhas = [], []
    for q, esperadas in perguntas:
        t = time.perf_counter()
        r = busca(q, 5)
        tempos.append(time.perf_counter() - t)
        pos = next((i for i, c in enumerate(r) if any(e in c for e in esperadas)), None)
        if pos is None:
            falhas.append((q, r[:3]))
            continue
        h1 += pos == 0; h3 += pos < 3; h5 += 1; mrr += 1 / (pos + 1)
    neg = [(q, r) for q in negativas if (r := busca(q, 5))]
    n = len(perguntas)
    tempos.sort()
    print(f"{modo:10s} acerto@1 {h1/n:5.0%}  @3 {h3/n:5.0%}  @5 {h5/n:5.0%}  MRR {mrr/n:.2f}  "
          f"falso+ {len(neg)}/{len(negativas)}  mediana {tempos[n//2]*1000:.0f} ms  pior {tempos[-1]*1000:.0f} ms")
    if detalhe:
        for q, r in falhas:
            print("   ✗", q, "→", r)
        for q, r in neg:
            print("   falso+", q, "→", r[:3])
    return {"h1": h1 / n, "h5": h5 / n, "mrr": mrr / n, "falso": len(neg)}


def avaliar_contexto(perfil):
    """compactação: o neurônio certo chega no contexto pronto do perfil? quantos tokens custa?"""
    import cerebro_motor as cm
    ok, toks = 0, []
    for q, esperadas in PERGUNTAS:
        c = cm.contexto(q, perfil=perfil, marcar=False)
        toks.append(c["tokens"])
        ok += any(e in k for k in c["itens"] for e in esperadas)
    neg = sum(1 for q in NEGATIVAS if cm.contexto(q, perfil=perfil, marcar=False)["texto"])
    print(f"contexto {perfil:7s} certo dentro {ok/len(PERGUNTAS):5.0%}  tokens médios {sum(toks)/len(toks):.0f}  "
          f"máx {max(toks)}  vazio nas negativas {len(NEGATIVAS)-neg}/{len(NEGATIVAS)}")


if __name__ == "__main__":
    a = sys.argv[1:]
    modo = a[a.index("--modo") + 1] if "--modo" in a else "v1"
    if "--contexto" in a:
        for p in ("kani", "codex", "agente"):
            avaliar_contexto(p)
        sys.exit(0)
    for m in (["v1", "lexical", "semantica", "hibrido"] if modo == "todos" else [modo]):
        if "--validacao" in a:
            avaliar(m, "--detalhe" in a, VALIDACAO, NEGATIVAS_VALIDACAO)
        else:
            avaliar(m, "--detalhe" in a)
