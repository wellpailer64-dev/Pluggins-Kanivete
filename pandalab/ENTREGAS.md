# Entregas e correções pelo plugin PandaLab

Use Python 3.13 na pasta do plugin. Não precisa abrir o site ou o KANIVETE.

```powershell
py -3.13 panda.py entregas --busca "medo" --cliente "Carlinhos" --json
py -3.13 panda.py entrega 1172 --json
py -3.13 panda.py substituir-artes 1172 --pasta "D:\pasta\dos\finais"
py -3.13 panda.py substituir-artes 1172 --pasta "D:\pasta\dos\finais" --sim
py -3.13 panda.py operacoes-entrega 1172 --json
py -3.13 panda.py recuperar-entrega 1172 --operacao ID_DA_OPERACAO
py -3.13 panda.py recuperar-entrega 1172 --operacao ID_DA_OPERACAO --sim
```

`entregas` consulta entregas concluídas, com paginação e filtro por título, número ou cliente (sem diferenciar acentos).
`entrega` aceita número, UUID, prefixo de UUID ou trecho único do título. Referências ambíguas são recusadas.
`demandas` continua consultando os cards; `entregar` continua entregando um card. Para corrigir uma entrega existente,
use `substituir-artes`, que preserva a entrega, título, número, legenda, aprovação e demais dados.

Sem `--sim`, os comandos de escrita mostram a prévia e não criam registros nem fazem uploads.
Finais são arquivos soltos da pasta nos formatos já suportados pelo plugin; fontes editáveis ficam de fora.
A ordem é natural por nome: slide_1, slide_2, slide_10. Confira a relação e a quantidade na prévia.

## Como a substituição funciona

1. Registra os anexos anteriores e a assinatura SHA-256 dos arquivos em `D:/Kanivete/Pandalab/operacoes`.
2. Sobe os finais ao Drive, salvando cada confirmação antes de continuar.
3. Cadastra os novos anexos com IDs persistidos e confere o resultado por leitura.
4. Somente após essa conferência, retira da entrega os IDs dos anexos anteriores e confere a ordem final.

**Retirar da entrega não apaga arquivos no Drive.** As versões antigas continuam no Drive; nenhum arquivo local é
apagado. A recuperação restaura os links antigos, por isso eles são preservados. Limpeza do Drive exige outra operação.

Repetir o mesmo comando retoma a operação pendente sem reenviar uploads confirmados. Repetir uma operação já concluída,
com os mesmos arquivos ainda na entrega, apenas devolve o resultado. `--operacao ID` escolhe explicitamente um registro.
Não altere, renomeie ou mova os arquivos locais durante a troca. Uma operação pendente com outros arquivos bloqueia
nova troca até ser concluída ou recuperada. A trava impede dois processos locais na mesma entrega.

Se um upload não retornar confirmação (inclusive se o processo fechar durante o envio), a operação para antes de
descartar anexos. Confira o Drive. `--repetir-incerto --sim` autoriza repetir esse envio, podendo criar uma cópia extra:
o serviço de upload atual não oferece chave de idempotência. Uploads já confirmados não são repetidos.

`recuperar-entrega` restaura todos os anexos anteriores antes de retirar os novos. Também pode ser retomado se falhar.
Uploads feitos ao Drive permanecem disponíveis. Os registros locais não contêm a chave ou o token de autenticação.

O serviço não fornece transação única entre Drive e banco. Falhas deixam um registro recuperável, e a conferência final
recusa sucesso se o sistema não aplicar uma escrita ou houver alteração concorrente. Alterações feitas no site por outra
pessoa são detectadas por ID, link, tipo e posição; nesse caso o comando para para evitar descartar material alheio.

## Verificação isolada

```powershell
$env:PYTHONPYCACHEPREFIX='D:\kanivete_testes\pycache'
py -3.13 -m py_compile panda.py pandalab_entregas.py tests/test_entregas.py
py -3.13 -m unittest discover -s tests -p "test_entregas.py" -v
```

Os testes usam arquivos e registros temporários no D e um backend simulado. Nenhuma conta ou entrega real é alterada.
