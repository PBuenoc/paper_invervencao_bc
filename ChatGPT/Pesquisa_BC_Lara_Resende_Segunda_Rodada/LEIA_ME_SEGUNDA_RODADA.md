# Revisão da pesquisa — segunda rodada

Cópia local, sem alterações no Google Drive. Data de referência: 30/06/2026. Semente: 20261123; 10.000 trajetórias por cenário. O pacote contém os scripts e bases recuperados do projeto original, os quatro scripts exploratórios da segunda rodada e o script de exportação e reestimação de projeções locais.

## Estrutura
- `02_Dados/01_brutos/`: arquivos brutos recuperados dos ZIPs do Drive (não inclui os dois XLS do DataMapper, cujos dados tratados estão disponíveis).
- `02_Dados/02_tratados/`: bases tratadas originais.
- `03_Codigo/`: código, configuração e logs originais, preservados.
- `04_Resultados/tabelas/`: resultados originais, preservados.
- `04_Resultados/segunda_rodada/`: saídas efetivamente reexecutadas, tabelas CSV consolidadas, base mensal de regimes, fluxos cambiais, comparação dos agregados e projeções locais reestimadas.
- `revisao.py`, `fluxo.py`, `extensao.py`, `final_checks.py`, `complementos.py`: scripts adicionais, executados a partir da raiz.

## Reproduzir
Em um ambiente Python 3.13, instale `requirements_revisao.txt`. A partir da raiz extraída, execute em ordem:

```bash
python revisao.py > 04_Resultados/segunda_rodada/revisao.txt
python fluxo.py > 04_Resultados/segunda_rodada/fluxo.txt
python extensao.py > 04_Resultados/segunda_rodada/extensao.txt
python final_checks.py > 04_Resultados/segunda_rodada/final_checks.txt
python complementos.py > 04_Resultados/segunda_rodada/complementos.txt
```

Os cinco scripts foram executados com sucesso na preparação deste pacote. A reestimação das projeções locais apresenta diferenças mínimas de arredondamento em relação à resposta anterior; use os CSVs para os números reproduzíveis. Os resultados são condicionais, não causais.

## Principais resultados
- Monte Carlo original: 62,0% de primeira demanda não atendida em 12 meses, 100% em 48 meses, mediana de 9 meses.
- Modelo revisado, M4, teto histórico, substituição parcial e transição de regimes: 20,3% em 12 meses, 37,5% em 24 meses, 57,5% em 48 meses; mediana de 37 meses.
- M3 ajustado (piso hipotético de US$ 321,464 bi): 18,8%, 35,5%, 55,9%; mediana de 40 meses.
- Teto de swaps 50% acima do histórico, M4: 9,6% em 48 meses.
- Estoque oficial de linhas em junho de 2026: US$ 4,05 bi.
- Fluxos: 93 meses de janeiro de 2018 a setembro de 2025.
- Regressões HAC e projeções locais: associação contemporânea do EMBI com câmbio; coeficiente Selic não significativo. Sem identificação de surpresas monetárias.

## Limitações
As séries oficiais SGS 29722/29723 foram localizadas, mas a validação independente do estoque reconstruído de swaps não foi concluída. O piso ARA e o teto histórico de swaps são hipóteses de cenário; não são limites legais. As intervenções realizadas historicamente aproximam a demanda, que não é observada. O módulo fiscal e os cenários institucionais são exercícios ilustrativos. A ARA dinâmica altera apenas a moeda ampla em dólares. As receitas das reservas são cenários de sensibilidade. A comparação de moeda ampla utiliza os valores transcritos do quadro do FMI Article IV 2026 (2021–2025), não uma confirmação da definição específica da ARA. O modelo mensal ignora a pressão intramensal; não constitui previsão de crise ou teste causal da proposta de Lara Resende.

## Fontes internas
- Relatório original: https://docs.google.com/document/d/1NQJIAXlRhz4FOttW-TdliH5khM4vNXJV/edit
- Article IV Brasil 2026: https://drive.google.com/file/d/1_8OkFQW5l4F3fjsa3IMEYKE8y5xQCXr1/view
- Protocolo original: https://docs.google.com/document/d/1DeXDUF9TlGKcIEmHrlbpulMfwcFMjQdR/edit
- As fontes BCB/Tesouro/Ipeadata estão identificadas nos nomes dos arquivos e nos logs originais.
