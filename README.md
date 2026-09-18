# it-asset-kpi-toolkit

Scripts para calcular dois indicadores de gestao de ativos de TI a partir de
um inventario exportado em CSV:

- **Indice de Obsolescencia de Ativos de TIC** - que fracao do parque de
  equipamentos ja esta obsoleta.
- **Indice de Ativos Pendentes de Cadastro no Sistema** - que fracao dos
  ativos que existem fisicamente (contratados, entregues ou em estoque)
  ainda nao foi registrada no sistema de gestao de ativos.

## Como funciona

Os dois scripts sao genericos: nenhuma regra de negocio vem fixa no
codigo. Toda regra de classificacao entra por arquivo de configuracao
(`config/*.json`) e todo dado de entrada entra por CSV (`data/*.csv`). Os
arquivos em `config/*.example.json` e `data/sample/*.csv` sao ficticios,
so para o codigo rodar "out of the box" e servir de referencia de
formato. Aponte `--regras`/`--frentes`/`--inventario`/`--estoque` para os
seus proprios arquivos para usar com dados reais.

## Instalacao

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso rapido (com os dados de exemplo)

```bash
python src/obsolescencia.py --exemplo
python src/pendentes_cadastro.py --exemplo
```

Isso roda os dois indicadores contra os CSVs ficticios de `data/sample/` e
as regras ficticias de `config/*.example.json`, so pra mostrar que o
codigo funciona e como a saida se parece. A flag `--exemplo` e obrigatoria
de proposito: sem ela, `--inventario`/`--regras`/`--frentes` sao exigidos
explicitamente, para nao ter risco de rodar sem perceber com um inventario
real misturado a regras ou estoque de exemplo.

## Uso com dados reais

```bash
python src/obsolescencia.py \
  --inventario /caminho/para/inventario.csv \
  --estoque /caminho/para/estoque.csv \
  --regras /caminho/para/regras.local.json

python src/pendentes_cadastro.py \
  --inventario /caminho/para/inventario.csv \
  --estoque /caminho/para/estoque.csv \
  --frentes /caminho/para/frentes.local.json \
  --dados-dir /caminho/para/pasta/com/planilhas/de/cada/frente
```

### Formato esperado do CSV de inventario

Separador `;`, cabecalho com (pelo menos) estas colunas:

| coluna              | exemplo         |
|---------------------|-----------------|
| `status_contratual` | `Ativo`         |
| `equipamento`       | `Notebook`      |
| `modelo`            | `ACME OFFICE X1`|
| `processador`       | `CPU-OLD 2400`  |
| `numero_serie`      | `SN00001`       |

### Formato esperado do CSV de estoque

Separador `;`, colunas `categoria`, `material`, `estoque_disponivel`.

### Arquivos de regras (`config/*.json`)

Veja os comentarios dentro de `config/regras.example.json` e
`config/frentes.example.json` - cada campo esta documentado ali mesmo.

## Estrutura

```
it-asset-kpi-toolkit/
├── config/
│   ├── regras.example.json      # criterio de obsolescencia (ficticio)
│   └── frentes.example.json     # frentes do indicador de pendencia (ficticio)
├── data/sample/                 # CSVs ficticios de demonstracao
├── src/
│   ├── common.py
│   ├── obsolescencia.py
│   └── pendentes_cadastro.py
└── requirements.txt
```

## Licenca

MIT - veja `LICENSE`.
