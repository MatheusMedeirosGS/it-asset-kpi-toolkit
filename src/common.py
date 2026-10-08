"""Funcoes compartilhadas pelos scripts de indicadores de ativos de TI."""
import json
import os
import unicodedata

import pandas as pd


def load_csv(path: str, sep: str = ";") -> pd.DataFrame:
    """Le um CSV exportado de planilha (separador ; por padrao, como o Excel
    pt-BR costuma gerar) e devolve um DataFrame. Falha alto (nao silencioso)
    se o arquivo nao existir, e tenta utf-8-sig antes de cp1252 porque
    exports do Excel costumam gravar um BOM no inicio do arquivo."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Arquivo nao encontrado: {path}")
    try:
        df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, encoding="cp1252")
    df.columns = [c.strip() for c in df.columns]
    return df


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Arquivo de configuracao nao encontrado: {path}")
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON invalido em {path}: {e}") from e


def sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize(series: pd.Series) -> pd.Series:
    """Deixa uma coluna de texto pronta para comparacao: maiuscula, sem
    espacos nas pontas, sem acento, valores vazios/NaN viram string vazia."""
    limpo = series.fillna("").astype(str).str.strip().str.upper()
    return limpo.apply(sem_acento)


def to_int_ptbr(series: pd.Series, contexto: str = "valor") -> pd.Series:
    """Converte uma coluna de texto numerico para inteiro. Aceita '1762',
    o formato pt-BR '1.762' / '1.762,00' e o decimal com ponto '301.0' (como
    o pandas grava floats). O ponto so e separador de milhar quando segue o
    padrao de grupos de 3 digitos ('1.762', '12.345.678'); caso contrario e
    ponto decimal. Falha alto (nao vira silenciosamente 0 nem 10x) quando
    encontra algo que nao e numero."""
    bruto = series.fillna("").astype(str).str.strip()
    vazio = bruto == ""
    milhar = bruto.str.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?")
    limpo = bruto.where(~milhar, bruto.str.replace(".", "", regex=False))
    limpo = limpo.str.replace(",", ".", regex=False)
    numerico = pd.to_numeric(limpo.where(~vazio, "0"), errors="coerce")
    invalidos = numerico.isna()
    if invalidos.any():
        exemplos = bruto[invalidos].unique()[:5].tolist()
        raise ValueError(
            f"{contexto}: encontrei {invalidos.sum()} valor(es) que nao sao numeros "
            f"validos (nem 'NNNN', 'N.NNN,NN' nem 'NNN.N'). Exemplos: {exemplos}"
        )
    return numerico.round().astype(int)


def matches_any(series: pd.Series, patterns: list[str]) -> pd.Series:
    """True para cada linha cujo valor (normalizado) contem QUALQUER UM dos
    padroes informados (comparacao tambem normalizada, sem acento). Lista
    vazia de padroes nunca bate com nada. Um padrao vazio ou so com espacos
    e rejeitado (senao ele bateria com toda e qualquer linha)."""
    for p in patterns:
        if not str(p).strip():
            raise ValueError(
                f"Padrao vazio na lista {patterns!r}: um padrao em branco bateria "
                "com todas as linhas, o que quase sempre e erro de configuracao."
            )
    if not patterns:
        return pd.Series(False, index=series.index)
    norm = normalize(series)
    mask = pd.Series(False, index=series.index)
    for p in patterns:
        mask = mask | norm.str.contains(sem_acento(str(p).strip().upper()), regex=False, na=False)
    return mask


def apply_obsolete_criteria(df: pd.DataFrame, criterios: list[dict]) -> pd.Series:
    """Aplica a lista de criterios do regras.json (cada um {"campo":..,
    "contem":..}) com logica OU entre eles: se qualquer criterio bater,
    o ativo e obsoleto. Isso NAO e uma prioridade entre campos - e uma
    lista de condicoes independentes, cada uma suficiente por si so. Na
    pratica, quando um criterio usa um campo mais confiavel (ex.: um
    processador exclusivo de uma linha de produto) e outro usa um campo
    mais sujeito a erro de digitacao (ex.: o modelo escrito a mao), o
    efeito e que o campo confiavel "resgata" o ativo mesmo que o campo
    com erro nao bata - mas isso e consequencia do OU, nao uma regra de
    prioridade separada."""
    mask = pd.Series(False, index=df.index)
    for c in criterios:
        col = c["campo"].strip().lower()
        if col not in df.columns:
            raise KeyError(
                f"Criterio referencia a coluna '{col}', que nao existe no "
                f"inventario. Colunas disponiveis: {list(df.columns)}"
            )
        mask = mask | matches_any(df[col], [c["contem"]])
    return mask


def carregar_inventario_ativo(path: str) -> pd.DataFrame:
    """Carrega o CSV de inventario, normaliza os nomes de coluna e devolve
    so as linhas com status_contratual = Ativo. Usado pelos dois scripts
    (obsolescencia.py e pendentes_cadastro.py) para nao duplicar essa
    logica em dois lugares."""
    inv = load_csv(path)
    inv.columns = [c.strip().lower() for c in inv.columns]
    if "status_contratual" not in inv.columns:
        raise KeyError(
            f"O inventario ({path}) precisa ter uma coluna 'status_contratual'. "
            f"Colunas encontradas: {list(inv.columns)}"
        )
    return inv[normalize(inv["status_contratual"]) == "ATIVO"].copy()


def carregar_estoque(path: str, estoque_cfg: dict) -> int:
    """Soma o estoque disponivel numa base de estoque (planilha de logistica)
    para os itens de uma categoria (ex.: Informatica) cujo material comeca
    com um dos prefixos configurados (ex.: Notebook, Microcomputador).
    Devolve 0 se path for vazio - mas propaga o erro se o arquivo foi
    informado e nao existe, para nao confundir 'sem estoque' com 'esqueci
    de configurar o caminho certo'."""
    if not path:
        return 0

    categoria_alvo = sem_acento(estoque_cfg.get("categoria_informatica", "Informatica").strip().upper())
    prefixos = [sem_acento(p.strip().upper()) for p in estoque_cfg.get("prefixos_material_validos", [])]

    estoque = load_csv(path)
    estoque.columns = [c.strip().lower() for c in estoque.columns]
    for col in ("categoria", "material", "estoque_disponivel"):
        if col not in estoque.columns:
            raise KeyError(
                f"A base de estoque ({path}) precisa ter uma coluna '{col}'. "
                f"Colunas encontradas: {list(estoque.columns)}"
            )

    filtro_categoria = normalize(estoque["categoria"]) == categoria_alvo
    if prefixos:
        material_norm = normalize(estoque["material"])
        filtro_material = material_norm.apply(lambda m: any(m.startswith(p) for p in prefixos))
    else:
        filtro_material = pd.Series(True, index=estoque.index)

    linhas = estoque[filtro_categoria & filtro_material]
    if linhas.empty:
        return 0
    return int(to_int_ptbr(linhas["estoque_disponivel"], f"estoque_disponivel em {path}").sum())


def formatar_pct(fracao: float) -> str:
    return f"{fracao * 100:.2f}%".replace(".", ",")
