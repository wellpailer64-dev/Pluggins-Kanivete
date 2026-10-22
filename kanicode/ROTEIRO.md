# Trabalhar no KaniCode

Plugin separado do Kanivete. Execute os comandos nesta pasta, com `py -3.13`.
Preserve alterações existentes. Sem commit, push, exclusões ou dependências novas.
Não controle o app do usuário para testar; nunca conecte à porta 9222 durante testes.

## Encontrar o trecho e o teste

| Área (`--area`) | Arquivo / entrada | Testes existentes |
| --- | --- | --- |
| `kani` | `kani_modo.py`: `FERRAMENTAS`, `_executar`, `rodar`; `ajudantes.py`: `kani` | `test_kani_historico.py`, `test_modelo_ferramenta.py` |
| `pickle` | `bigpickle_modo.py`, `opencode_mvp.py`, `App._pickle_*`; guia `BIGPICKLE.md` | `test_bigpickle_*.py`, `test_opencode_mvp.py`, `test_kani_historico.py` |
| `codex` | `ajudantes.py`: `codex`; `codex_contexto.py`, `codex_processo.py`, `codex_conta.py`, `codex_alteracoes.py`, `ui/codex_uso.js` | `test_codex_*.py`; guia `CODEX_PARIDADE.md` |
| `codigo` | `codigo_agente.py`, `codigo_testes.py`, `ui/codigo_agente.js`; ponte compartilhada pela Kani e Big Pickle | `test_codigo_*.py` |
| `interface` | `ui/janela.html`, `ui/organizacao.js`, `ui/kani_gpu.js` | `test_layout.py` |
| `respostas` | `recursos_resposta.py`, `ui/respostas.js`, `ui/respostas_render.js` | `test_recursos_resposta.py`, `test_respostas_ui.py` |
| `gpu` | `gpu.py`; `App.gpu_info` em `kanicode.py` | `test_gpu.py` |
| `contas` | `contas.py`, `avatares.py` | `test_avatares.py` |
| `infra` | `verificar.py`, `modelo_ferramenta.py` | `test_verificar.py`, `test_modelo_ferramenta.py` |

Voz, celular e outras áreas: consulte `MAPA.md`. A tabela lista cobertura existente,
não garante cobertura de toda alteração. Acrescente o teste de comportamento necessário.

1. Busque antes de ler: `py -3.13 mapa_codigo.py --arquivo kani_modo.py --busca abrir_ferramenta`.
2. Leia só o símbolo/trecho: `--simbolo _executar` ou `--trecho 350:420`.
3. Liste os testes reais: `py -3.13 verificar.py --area kani --listar`.
4. Copie a âncora exata do arquivo. Valide o patch com `tools/patch.py arquivo.patch --seco`
   na raiz do Kanivete; depois aplique pelo mesmo comando sem `--seco`.
5. Verifique a área e inclua os arquivos alterados que não fazem parte da seleção padrão.

## Verificar com um comando

```powershell
py -3.13 verificar.py --area kani --arquivos kanicode.py
py -3.13 verificar.py --area infra
py -3.13 verificar.py --area todas
```

`--arquivos` acrescenta arquivos à área; não substitui a seleção. Um teste adicional
deve estar em `tests/test_*.py`. Caminho inexistente ou fora do plugin é recusado.
O comando verifica Python, JavaScript e scripts inline do HTML. Scripts externos do
HTML devem entrar na seleção como arquivos; JSON inline não é tratado como JavaScript.
CSS não recebe análise de sintaxe. Os testes de interface cobrem os comportamentos existentes.

Sem erro de sintaxe, roda os módulos de teste selecionados, sem repeti-los.
Retorna 0 sem falhas, 1 se houver falha e 2 para argumentos inválidos.
Testes ignorados são destacados como cobertura parcial; leia os motivos no relatório.
Logs e scripts extraídos ficam numa pasta `D:\kanivete_testes\verificar_*` indicada no final.
TEMP, TMP, APPDATA, LOCALAPPDATA e cache Python são configurados no D para os processos
filhos, sem alterar as configurações globais do Windows. Cada comando filho tem prazo de 180 s.
`--listar` apenas consulta, sem executar testes nem criar saídas.

## Criar uma ferramenta com conferência

Use `modelo_ferramenta.executar` com argumentos, campos obrigatórios e três callbacks:
`observar(args)`, `agir(args)` e `conferir(antes, depois, args)`.
`observar` deve produzir uma fotografia independente do estado, não uma referência mutável.
`conferir` devolve o booleano True somente quando o objetivo foi observado.
O retorno da ação não comprova sucesso. A ação roda uma vez e não é repetida em caso de erro.

Resultado padrão: `ok`, `etapa`, `mensagem`, `antes`, `depois`. `para_kani(resultado)` adapta
esse resultado ao executor atual em texto, com `NÃO FEITO` quando não houve confirmação.
Uma falha após agir pode ter deixado efeito parcial: releia o estado antes de tentar de novo.

O modelo não registra ferramentas automaticamente. Para integrar uma ação autorizada,
adicione sua descrição em `kani_modo.FERRAMENTAS` e um ramo em `_executar` retornando
`para_kani(executar(...))`. Autorizações, nomes permitidos, caminhos e limites pertencem
à ferramenta concreta. Nunca aceite código ou comandos livres como argumento do modelo.
Não execute os callbacks de produção em testes: siga `tests/test_modelo_ferramenta.py`,
que simula estado, ação sem efeito, argumentos inválidos e exceção sem repetição.
Valide com `py -3.13 verificar.py --area kani --arquivos modelo_ferramenta.py`.

Mudanças Python entram no processo na próxima abertura do KaniCode; não reinicie o
programa do usuário só para validar código. Novas ações exigem testes próprios.
