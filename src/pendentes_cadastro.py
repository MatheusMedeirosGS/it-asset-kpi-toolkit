#!/usr/bin/env python3
"""
Indice de Ativos Pendentes de Cadastro no Sistema.

Mede a defasagem entre o que ja existe fisicamente (contratado, entregue
ou em estoque) e o que de fato esta registrado no sistema de gestao de
ativos, com 3 componentes:

    DNI = Disponibilizados Nao Inventariados
    ENI = Estoque Nao Inventariados
    CAD = Cadastrado no sistema

    Realizado = (DNI + ENI) / (DNI + ENI + CAD)

CAD conta TODOS os ativos Ativos do inventario, em qualquer categoria de
equipamento - nao so a base usada no indicador de obsolescencia. Se a sua
organizacao quiser restringir o universo (por ex., so notebook/desktop),
ajuste esse filtro nesta funcao.

O DNI e a soma de "frentes": programas/contratos diferentes, cada um com
sua propria forma de apurar quantos itens ainda nao foram cadastrados.
Este script reconhece 3 tipos de frente, descritos em config/frentes.json:

  1. "frentes_por_contagem": total contratado (numero fixo) menos quantos
     desse modelo ja estao Ativos no inventario.
  2. "frente_kit_distribuicao": soma de uma coluna de quantidade enviada
     numa planilha de controle de distribuicao, menos quantos desse
     modelo ja estao Ativos no inventario.
  3. "frente_situacao_confirmada": linhas de uma planilha de entregas
     cuja situacao esteja na lista de situacoes validas (ex.: "Entrega
     Confirmada"), menos quantas dessas linhas tem numero de serie que
     bate com o inventario.

Nenhuma dessas frentes vem hardcoded no codigo: adicione, remova ou ajuste
frentes editando o JSON, sem precisar tocar neste script.

Se o mesmo ativo puder ser contado em mais de uma frente (porque os
modelo_patterns de duas frentes se sobrepoem), ou se um "cadastrado"
superar o "contratado" de uma frente (ex.: o modelo tambem veio de outro
programa), o script avisa em stderr - revise a configuracao nesses casos,
porque o resultado pode estar sub ou superestimado.

Uso:
    python src/pendentes_cadastro.py --exemplo
    python src/pendentes_cadastro.py --inventario caminho.csv --estoque caminho.csv --frentes caminho.json --dados-dir pasta/
"""
import argparse
import os
import sys

import pandas as pd

from common import (load_csv, load_json, matches_any, carregar_inventario_ativo,
                     carregar_estoque, formatar_pct, to_int_ptbr)

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SAMPLE_DIR = os.path.join(RAIZ, "data", "sample")


def _nao_inventariado(nome: str, contratado: int, cadastrado: int) -> dict:
    bruto = contratado - cadastrado
    if bruto < 0:
        print(
            f"Aviso: na frente '{nome}', cadastrado ({cadastrado}) e maior que "
            f"contratado/enviado ({contratado}). Tratando como 0 nao inventariados, "
            "mas isso normalmente significa que o modelo tambem pertence a outro "
            "programa/frente e esta sendo contado duas vezes.",
            file=sys.stderr,
        )
    return {
        "nome": nome,
        "contratado_ou_enviado": contratado,
        "cadastrado": cadastrado,
        "nao_inventariado": max(0, bruto),
    }


def _checar_sobreposicao(inv_ativo: pd.DataFrame, frentes_com_mascara: list[tuple]) -> None:
    for i in range(len(frentes_com_mascara)):
        nome_a, mask_a = frentes_com_mascara[i]
        for j in range(i + 1, len(frentes_com_mascara)):
            nome_b, mask_b = frentes_com_mascara[j]
            sobreposicao = int((mask_a & mask_b).sum())
            if sobreposicao:
                print(
                    f"Aviso: {sobreposicao} ativo(s) do inventario batem tanto com a "
                    f"frente '{nome_a}' quanto com '{nome_b}'. Eles estao sendo "
                    "contados como 'cadastrado' nas duas, o que pode subestimar o DNI total.",
                    file=sys.stderr,
                )


def _frentes_por_contagem(inv_ativo: pd.DataFrame, frentes: list[dict]) -> tuple[list[dict], list[tuple]]:
    resultados, mascaras = [], []
    for f in frentes:
        mask = matches_any(inv_ativo["modelo"], f["modelo_patterns"])
        mascaras.append((f["nome"], mask))
        resultados.append(_nao_inventariado(f["nome"], int(f["total_contratado"]), int(mask.sum())))
    return resultados, mascaras


def _frente_kit_distribuicao(inv_ativo: pd.DataFrame, dados_dir: str, cfg: dict):
    if not cfg:
        return None, None
    caminho = os.path.join(dados_dir, cfg["arquivo"])
    df = load_csv(caminho)
    df.columns = [c.strip().lower() for c in df.columns]
    col_qtd = cfg["coluna_quantidade"].strip().lower()
    if col_qtd not in df.columns:
        raise KeyError(f"'{cfg['arquivo']}' precisa ter a coluna '{col_qtd}'. Colunas: {list(df.columns)}")

    enviado = int(to_int_ptbr(df[col_qtd], f"{col_qtd} em {caminho}").sum())
    mask = matches_any(inv_ativo["modelo"], cfg["modelo_patterns"])
    return _nao_inventariado(cfg["nome"], enviado, int(mask.sum())), (cfg["nome"], mask)


def _frente_situacao_confirmada(inv_ativo: pd.DataFrame, dados_dir: str, cfg: dict):
    if not cfg:
        return None
    caminho = os.path.join(dados_dir, cfg["arquivo"])
    df = load_csv(caminho)
    df.columns = [c.strip().lower() for c in df.columns]

    col_sit = cfg["coluna_situacao"].strip().lower()
    col_serie = cfg["coluna_serie"].strip().lower()
    for col in (col_sit, col_serie):
        if col not in df.columns:
            raise KeyError(f"'{cfg['arquivo']}' precisa ter a coluna '{col}'. Colunas: {list(df.columns)}")

    situacoes_validas = [s.strip().upper() for s in cfg["situacoes_validas"]]
    disponibilizado = df[df[col_sit].str.strip().str.upper().isin(situacoes_validas)].copy()

    serie_col = disponibilizado[col_serie].fillna("").astype(str).str.strip().str.upper()
    total_bruto = len(disponibilizado)
    duplicadas = int(serie_col[serie_col != ""].duplicated().sum())
    if duplicadas:
        print(
            f"Aviso: '{cfg['arquivo']}' tem {duplicadas} numero(s) de serie duplicado(s) "
            "entre as linhas disponibilizadas; cada ocorrencia esta sendo contada.",
            file=sys.stderr,
        )

    if "numero_serie" not in inv_ativo.columns:
        raise KeyError(
            "O inventario precisa ter a coluna 'numero_serie' para a frente "
            f"'{cfg['nome']}' poder cruzar por numero de serie."
        )
    series_inventario = set(inv_ativo["numero_serie"].fillna("").astype(str).str.strip().str.upper())
    series_inventario.discard("")

    # series_inventario nao contem "", entao uma linha sem serie preenchida
    # nunca "casa" por acidente - ela sempre conta como nao inventariada.
    com_correspondencia = int(serie_col.isin(series_inventario).sum())

    return _nao_inventariado(cfg["nome"], total_bruto, com_correspondencia)


def calcular(inventario_path: str, estoque_path: str, frentes_path: str, dados_dir: str) -> dict:
    frentes_cfg = load_json(frentes_path)

    inv_ativo = carregar_inventario_ativo(inventario_path)
    if "modelo" not in inv_ativo.columns:
        raise KeyError(f"O inventario ({inventario_path}) precisa ter uma coluna 'modelo'.")

    cad = len(inv_ativo)

    frentes_resultado, mascaras = _frentes_por_contagem(inv_ativo, frentes_cfg.get("frentes_por_contagem", []))

    r_kit, mask_kit = _frente_kit_distribuicao(inv_ativo, dados_dir, frentes_cfg.get("frente_kit_distribuicao"))
    if r_kit:
        frentes_resultado.append(r_kit)
        mascaras.append(mask_kit)

    r_sit = _frente_situacao_confirmada(inv_ativo, dados_dir, frentes_cfg.get("frente_situacao_confirmada"))
    if r_sit:
        frentes_resultado.append(r_sit)
        # a frente por situacao casa por numero de serie, nao por modelo,
        # entao nao entra na checagem de sobreposicao por mascara de modelo.

    _checar_sobreposicao(inv_ativo, mascaras)

    dni = sum(f["nao_inventariado"] for f in frentes_resultado)
    eni = carregar_estoque(estoque_path, frentes_cfg.get("estoque", {}))

    denom = dni + eni + cad
    realizado = (dni + eni) / denom if denom else 0.0

    return {
        "frentes": frentes_resultado,
        "DNI": dni,
        "ENI": eni,
        "CAD": cad,
        "realizado": realizado,
        "realizado_pct": formatar_pct(realizado),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exemplo", action="store_true",
                     help="Usa os dados e regras ficticios de demonstracao. Sem essa flag, "
                          "--inventario e --frentes sao obrigatorios.")
    ap.add_argument("--inventario")
    ap.add_argument("--estoque", help="Opcional: sem esse argumento, ENI = 0.")
    ap.add_argument("--frentes")
    ap.add_argument("--dados-dir", help="Pasta onde estao os arquivos referenciados em cada frente (campo 'arquivo' no JSON).")
    args = ap.parse_args()

    if args.exemplo:
        inventario = args.inventario or os.path.join(SAMPLE_DIR, "inventario.csv")
        estoque = args.estoque or os.path.join(SAMPLE_DIR, "estoque.csv")
        frentes = args.frentes or os.path.join(RAIZ, "config", "frentes.example.json")
        dados_dir = args.dados_dir or SAMPLE_DIR
    else:
        if not args.inventario or not args.frentes:
            print("Erro: --inventario e --frentes sao obrigatorios (ou use --exemplo para rodar com dados ficticios).",
                  file=sys.stderr)
            sys.exit(2)
        inventario, estoque, frentes = args.inventario, args.estoque, args.frentes
        dados_dir = args.dados_dir or os.path.dirname(os.path.abspath(frentes))

    try:
        r = calcular(inventario, estoque, frentes, dados_dir)
    except (KeyError, ValueError, FileNotFoundError) as e:
        print(f"Erro: {e}", file=sys.stderr)
        sys.exit(1)

    print("Indice de Ativos Pendentes de Cadastro no Sistema")
    print("=" * 51)
    for f in r["frentes"]:
        print(f"  {f['nome']}")
        print(f"    contratado/enviado = {f['contratado_ou_enviado']}, cadastrado = {f['cadastrado']}, "
              f"nao inventariado = {f['nao_inventariado']}")
    print("-" * 51)
    print(f"DNI (Disponibilizados Nao Inventariados)....: {r['DNI']}")
    print(f"ENI (Estoque Nao Inventariados)..............: {r['ENI']}")
    print(f"CAD (Cadastrado no sistema)...................: {r['CAD']}")
    print("-" * 51)
    print(f"Realizado = ({r['DNI']} + {r['ENI']}) / ({r['DNI']} + {r['ENI']} + {r['CAD']})")
    print(f"Realizado = {r['realizado_pct']}")


if __name__ == "__main__":
    main()
