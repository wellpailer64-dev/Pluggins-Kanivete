# Codex no KaniCode: acompanhamento, consumo e próximos recursos

## Disponível nesta implementação

- Comentários completos de andamento na conversa, separados da resposta final.
- Com o chat recolhido, os comentários concluídos e a resposta final usam a voz local do KaniCode, sem repetir mensagens. Parar corta a leitura; o microfone só volta ao fim da tarefa.
- Confirmação de prontidão por voz após 1 segundo sem resposta (Claude, Codex, Kani e Big Pickle): três clipes locais, com tom +2 semitons e duração preservada. Sem tokens nem alteração do histórico. Resposta, término, erro, pedido de decisão e Parar invalidam o aviso; cada aba guarda o próprio temporizador. O primeiro uso prepara o cache e só confirma se a tarefa ainda aguarda resposta. Cache em `modelos_voz/prontidao-v2-<voz>-<velocidade>-tom2.npz`.
- Operações identificadas por início/conclusão/falha, com indicação do arquivo editado.
- Barras **Ver alterações** recolhidas, com expansão/recolhimento por clique. Código é texto, sem executar HTML.
- Fotografia local anterior ao turno: até 300 arquivos de texto, 512 KB por arquivo e cerca de 8 MB no total.
  Exclui dependências geradas, modelos, links e arquivos fora da pasta. Se faltar a base, identifica conteúdo atual
  como conteúdo, sem inventar um diff. Edições simultâneas do usuário podem aparecer na comparação desde o início.
- Comentários e diffs recuperáveis no histórico do Codex.
- Medições reais de tokens da sessão consultadas durante a execução; contagem recebida por etapa, sem estimativa
  por caractere. O cliente pode demorar a publicar a próxima medição. Entrada em cache e raciocínio não são somados duas vezes.
- Limites consultados pelo protocolo oficial, a cada cinco segundos com o Codex selecionado e a página visível.
  Retornar à janela ou concluir uma tarefa força atualização. Erros recuam a consulta automática para 30 segundos.
- Horário local de redefinição, benefício disponível, aviso de esgotamento e **Atualizar limites**.
- **Usar 1 redefinição disponível** somente por clique, quando a conta informa o benefício e há esgotamento.
  Uma tentativa usa a mesma chave mesmo depois de perda de resposta/reabertura. O saldo é consultado depois.
- **Abrir painel oficial de uso** para controles adicionais. Nenhuma compra ou redefinição automática.

Tokens medem texto processado; cota do plano e créditos de redefinição são informações distintas. A conta
consultada é a conta autenticada no cliente Codex. O seletor de contas do Claude não troca essa autenticação.
Na consulta real desta implementação, a conta informou zero redefinições; o resgate foi testado com protocolo simulado.

## Recursos para discutir em outra etapa

| Recurso oficial | Situação no KaniCode / possibilidade |
| --- | --- |
| Texto em deltas e plano estruturado | A execução usa `codex exec --json`; migrar turnos para app-server permite `item/agentMessage/delta`, `turn/plan/updated` e `turn/diff/updated`. Exige adaptar retomada, cancelamento e histórico juntos. |
| Intervir durante a tarefa | Hoje Parar interrompe. `turn/steer` permite uma nova instrução durante o turno, mediante migração do transporte. |
| Aprovar comandos/arquivos por ação | A ponte Codex atual distingue Planejar/execução. A UI de aprovação granular exige tratar solicitações do app-server e preservar a política escolhida. |
| Modelo, esforço e velocidade | Modelo fixo e esforço automático. Um seletor deve consultar capacidades da conta; não assumir que todo modelo/modo está disponível. |
| Limites por categoria, créditos e workspace | O painel prioriza a cota Codex. O protocolo também pode informar outras categorias e motivos de bloqueio; ampliar o painel conforme dados realmente retornados. |
| Atividade diária da conta | `account/usage/read` pode alimentar um histórico de consumo; não corresponde só às tarefas deste KaniCode. |
| Conta Codex ativa | Identificação, plano, foto local por e-mail e cotas na lateral; clique abre detalhes, atualização e redefinições. Login próprio ainda não oferecido; o seletor do Claude não altera a conta Codex. |

Fontes oficiais verificadas em 21/10/2026:
[protocolo app-server](https://learn.chatgpt.com/docs/app-server),
[uso e limites](https://learn.chatgpt.com/docs/pricing),
[painel de uso](https://chatgpt.com/codex/settings/usage).
Capacidades conferidas também no schema do CLI instalado, versão 0.163.0.

## Conferir sem o app do usuário

`py -3.13 verificar.py --area codex` e `py -3.13 verificar.py --area interface`.
API da conta, redefinições e janelas são simuladas nos testes; consulta real de limites é somente leitura.
Nenhum teste conecta à porta 9222, compra créditos ou consome uma redefinição.
