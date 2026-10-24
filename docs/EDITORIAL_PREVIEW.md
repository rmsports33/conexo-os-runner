# Previa de comparativo: SIMULACAO_OFFLINE

Operacao `editorial_preview` no worker existente, desabilitada sem
`PreviewConfig(test_mode=True)` fornecida por codigo confiavel. A CLI normal
do worker nao habilita essa configuracao. Nao e prontidao para producao.

## Contratos e conversao

O redator usa EditorialContract v1.0: sources/claims com IDs, subject,
specs_CANDIDATA e specs_PASS. PASS depende de validacao, aprovador e fonte;
o gate de preco ainda exige produto, valor, captura e fonte temporalmente
compativeis. O contrato MKT usa produtos/ficha, preco formatado em BRL,
data DD/MM/AAAA, fonte_preco, notas e criterios. Aprovar estrutura/valor MKT
nao comprova autenticidade factual.

O adaptador revalida um contrato por produto; so specs promovidas viram
specs/ficha. Fonte primaria vem de evidencia de claim de spec; marketplace
vem de evidencia da claim de preco. Nenhuma URL, data ou aprovacao e criada
pelo adaptador. IDs duplicados/claims de outro produto sao rejeitados.
O envelope combinado preserva IDs e evidencias sem mesclar candidatas.
O redator revalida as specs em modo estrito e os precos por seu gate original.
O historico original e conservado para o MKT: o redator remove metadados
de marketplace de sua copia interna. Os normalizadores MKT convertem moeda
e data. Criterios so repetem specs aprovadas, sem declarar vencedor; notas
sao dados de teste e nao avaliacoes reais.

`gerar_comparativo` recebe resposta fixa SOMENTE nesse modo de teste.
`processar_comparativo(dry_run=True)` e os tres gates MKT sao reutilizados.
O plano completo e hipotetico (`execute=false`), sem credenciais e sem envio.

## Isolamento e artefatos

Os caminhos absolutos dos dois checkouts e a raiz temporaria sao configurados
fora do payload e validados. Nao ha caminho de usuario embutido no codigo.
Um filho Python `-I -B` evita colisao com o pacote legado `src` e pycache nos
componentes. Recebe ambiente minimo, sem chaves e flags de publicacao.
Coleta/LLM sao stubs proibitivos; WordPress e HTTP sao bloqueados; audit hook
nega socket e processos descendentes. As contagens registram tentativas.
Isso protege este percurso conhecido; nao e sandbox para codigo Python hostil
ou checkouts modificados maliciosamente, nem garantia contra bibliotecas nativas.

O payload aceita apenas type/simulation/contracts/notas/criterios. Publicacao,
comandos, modulos e caminhos de saida sao rejeitados. A saida tem subdiretorio
aleatorio exclusivo sob TemporaryDirectory do teste, com preview.html,
validation.json e delivery-plan.json. Bloqueios produzem somente relatorio.
HTML usa CSP sem recursos externos e sem scripts; o plano nao e pagina a abrir.

Requer Python 3.12+. O import requests do publisher e substituido no filho
por capacidade bloqueada, sem inicializar HTTP. Nenhuma dependencia e instalada. Os checkouts
atualizados devem estar presentes; a copia antiga aninhada nao e alterada.

## Testes e demonstracao

Configure CONEXO_PREVIEW_REDACTOR e CONEXO_PREVIEW_MKT para os checkouts locais.
Execute na raiz do runner:

    python -B -m unittest discover -s tests -p test_editorial_preview.py -v
    python -B tests/test_editorial_preview.py --redactor CAMINHO_REDATOR --mkt CAMINHO_MKT -v
    python -B tests/test_editorial_preview.py --demo --redactor CAMINHO_REDATOR --mkt CAMINHO_MKT

A demonstracao cria sua propria SQLite, chama process_one do worker e imprime
os caminhos. Seu TemporaryDirectory exclusivo fica retido para revisao humana.
Testes normais removem seus temporarios. Nunca use run-once ou a fila ativa.
