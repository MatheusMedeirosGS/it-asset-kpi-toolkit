#!/usr/bin/env python3
"""
Indice de Obsolescencia de Ativos de TIC.

Calcula o percentual de ativos obsoletos dentro de um inventario, seguindo
a metodologia de 4 componentes:

    OC   = Obsoletos Cadastrados
    ONC  = Obsoletos Nao Cadastrados
    NOC  = Nao Obsoletos Cadastrados
    NONC = Nao Obsoletos Nao Cadastrados

    Realizado = (ONC + OC) / (OC + ONC + NOC + NONC)

O CRITERIO de obsolescencia (quais modelos/processadores contam como
obsoletos) NAO fica hardcoded neste script: ele vem de um arquivo de regras
(--regras), para que o mesmo codigo sirva para qualquer organizacao que
tenha seu proprio criterio de classificacao. Este repositorio traz um
exemplo com valores ficticios em config/regras.example.json; o criterio
real de uma organizacao deve ficar em config/regras.local.json (ignorado
pelo git) ou em qualquer outro caminho fora do repositorio.

Uso:
    python src/obsolescencia.py --exemplo
    python src/obsolescencia.py --inventario caminho.csv --estoque caminho.csv --regras caminho.json
"""
import argparse
import os
import sys

from common import load_json, apply_obsolete_criteria, carregar_inventario_ativo, carregar_estoque, formatar_pct

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SAMPLE_DIR = os.path.join(RAIZ, "data", "sample")


def _int_nao_negativo(valor: str) -> int:
    n = int(valor)
    if n < 0:
        raise argparse.ArgumentTypeError("nao pode ser negativo")
    return n


def calcular(inventario_path: str, estoque_path: str, regras_path: str,
             obsoletos_nao_cadastrados: int = 0) -> dict:
    regras = load_json(regras_path)
    for chave in ("base_equipamento", "criterios_obsoleto"):
        if chave not in regras:
            raise KeyError(f"O arquivo de regras ({regras_path}) precisa ter a chave '{chave}'.")

    ativos = carregar_inventario_ativo(inventario_path)

    base_tipos = [t.strip().upper() for t in regras["base_equipamento"]]
    if "equipamento" not in ativos.columns:
        raise KeyError(
            f"O inventario ({inventario_path}) precisa ter uma coluna 'equipamento'. "
            f"Colunas encontradas: {list(ativos.columns)}"
        )
    base = ativos[ativos["equipamento"].str.strip().str.upper().isin(base_tipos)].copy()

    if base.empty:
        raise ValueError(
            "Nenhum ativo Ativo encontrado nas categorias "
            f"{regras['base_equipamento']}. Confira o inventario de entrada "
            "(os valores da coluna 'equipamento' batem com as categorias do regras.json?)."
        )

    mask_obsoleto = apply_obsolete_criteria(base, regras["criterios_obsoleto"])

    oc = int(mask_obsoleto.sum())
    onc = int(obsoletos_nao_cadastrados)
    noc = len(base) - oc
    nonc = carregar_estoque(estoque_path, regras.get("estoque", {}))

    denom = oc + onc + noc + nonc
    realizado = (onc + oc) / denom if denom else 0.0

    return {
        "base_total": len(base),
        "OC": oc,
        "ONC": onc,
        "NOC": noc,
        "NONC": nonc,
        "realizado": realizado,
        "realizado_pct": formatar_pct(realizado),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exemplo", action="store_true",
                     help="Usa os dados e regras ficticios de demonstracao (data/sample/, config/*.example.json). "
                          "Sem essa flag, --inventario e --regras sao obrigatorios, para nao rodar sem perceber "
                          "misturando inventario real com estoque/regras de exemplo.")
    ap.add_argument("--inventario")
    ap.add_argument("--estoque", help="Opcional: sem esse argumento, NONC = 0.")
    ap.add_argument("--regras")
    ap.add_argument("--obsoletos-nao-cadastrados", type=_int_nao_negativo, default=0,
                     help="Ativos obsoletos que existem fisicamente mas ainda nao foram cadastrados (ONC). Nao ha como deduzir isso automaticamente de um inventario; informe manualmente se souber esse numero.")
    args = ap.parse_args()

    if args.exemplo:
        inventario = args.inventario or os.path.join(SAMPLE_DIR, "inventario.csv")
        estoque = args.estoque or os.path.join(SAMPLE_DIR, "estoque.csv")
        regras = args.regras or os.path.join(RAIZ, "config", "regras.example.json")
    else:
        if not args.inventario or not args.regras:
            print("Erro: --inventario e --regras sao obrigatorios (ou use --exemplo para rodar com dados ficticios).",
                  file=sys.stderr)
            sys.exit(2)
        inventario, estoque, regras = args.inventario, args.estoque, args.regras

    try:
        r = calcular(inventario, estoque, regras, args.obsoletos_nao_cadastrados)
    except (KeyError, ValueError, FileNotFoundError) as e:
        print(f"Erro: {e}", file=sys.stderr)
        sys.exit(1)

    print("Indice de Obsolescencia de Ativos de TIC")
    print("=" * 45)
    print(f"Base de equipamentos analisada.......: {r['base_total']}")
    print(f"Obsoletos Cadastrados (OC)...........: {r['OC']}")
    print(f"Obsoletos Nao Cadastrados (ONC).......: {r['ONC']}")
    print(f"Nao Obsoletos Cadastrados (NOC).......: {r['NOC']}")
    print(f"Nao Obsoletos Nao Cadastrados (NONC)..: {r['NONC']}")
    print("-" * 45)
    print(f"Realizado = ({r['ONC']} + {r['OC']}) / ({r['OC']} + {r['ONC']} + {r['NOC']} + {r['NONC']})")
    print(f"Realizado = {r['realizado_pct']}")


if __name__ == "__main__":
    main()
