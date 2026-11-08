"""
silver/transform.py
─────────────────────────────────────────────────────────────────────
Camada Silver — Transformação e alinhamento temporal dos indicadores.

Responsabilidades desta camada:
  1. Carregar os JSONs brutos da Camada Bronze
  2. Tipar explicitamente datas e valores numéricos
  3. Resolver a assimetria de calendário financeiro
  4. Criar um índice diário contínuo (jan/2015 → atual)
  5. Aplicar forward-fill para preencher lacunas
  6. Adicionar colunas de calendário (dia útil, feriado, etc.)
  7. Exportar o DataFrame limpo como CSV para a Camada Gold
─────────────────────────────────────────────────────────────────────
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Adiciona a raiz do projeto ao path para importar config.py corretamente
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import (
    DATA_FIM_PANDAS,
    DATA_INICIO_PANDAS,
    DIR_SILVER,  # Ajustado para Medalhão
    DIR_BRONZE,  # Ajustado para Medalhão
    SERIES,
)

# ── Configuração do logger ────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("silver.transform")

# ── Detecção de feriados nacionais brasileiros ────────────────────
try:
    import holidays as _holidays_lib
    _USA_HOLIDAYS = True
    log = logging.getLogger("silver.transform")
except ImportError:
    _USA_HOLIDAYS = False

FERIADOS_BR = {
    "01-01", "21-04", "01-05", "07-09", 
    "12-10", "02-11", "15-11", "25-12",
}

def _construir_set_feriados(anos) -> set:
    if _USA_HOLIDAYS:
        return set(_holidays_lib.Brazil(years=list(anos)).keys())
    return set()

# ─────────────────────────────────────────────────────────────────
# ETAPA 1 — Carregamento dos dados brutos (Bronze → Silver)
# ─────────────────────────────────────────────────────────────────

def carregar_json_mais_recente(nome: str) -> list[dict]:
    arquivos = sorted(DIR_BRONZE.glob(f"{nome}_*.json"))

    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum arquivo Bronze encontrado para '{nome}'.\n"
            f"Execute primeiro: python main.py --bronze"
        )

    caminho = arquivos[-1]
    log.info("Carregando %-8s  ← %s", nome.upper(), caminho.name)

    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)

    log.info("  %d registros brutos lidos.", len(dados))
    return dados

def json_para_dataframe(nome: str, dados: list[dict]) -> pd.Series:
    df = pd.DataFrame(dados)

    df["data"]  = pd.to_datetime(df["data"], format="%d/%m/%Y", dayfirst=True)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")

    df = df.drop_duplicates(subset="data", keep="last")

    serie = df.set_index("data")["valor"].sort_index()
    serie.name = SERIES[nome]["sigla"]

    nulos = serie.isna().sum()
    if nulos > 0:
        log.warning("  %-8s %d valor(es) nulo(s) no dado bruto.", nome.upper(), nulos)

    return serie

# ─────────────────────────────────────────────────────────────────
# ETAPA 2 — Alinhamento temporal (núcleo da Camada Silver)
# ─────────────────────────────────────────────────────────────────

def criar_indice_diario() -> pd.DatetimeIndex:
    idx = pd.date_range(start=DATA_INICIO_PANDAS, end=DATA_FIM_PANDAS, freq="D")
    log.info("Índice diário criado: %s → %s  (%d dias)", idx[0].date(), idx[-1].date(), len(idx))
    return idx

def alinhar_series(selic: pd.Series, ipca: pd.Series, cambio: pd.Series, idx: pd.DatetimeIndex) -> pd.DataFrame:
    log.info("Alinhando séries no índice diário (Forward-Fill)...")

    selic_al  = selic.reindex(idx).ffill()
    ipca_al   = ipca.reindex(idx).ffill()
    cambio_al = cambio.reindex(idx).ffill()

    df = pd.DataFrame({
        "SELIC":   selic_al,
        "IPCA":    ipca_al,
        "USD_BRL": cambio_al,
    })
    df.index.name = "data_afericao"

    antes = df.isna().any(axis=1).sum()
    df = df.dropna(how="any")

    if antes > 0:
        log.info("  %d dia(s) removidos por ausência de dado inicial.", antes)

    log.info("  ✓ Alinhamento concluído: %d linhas × %d colunas — zero nulos.", len(df), df.shape[1])
    return df

# ─────────────────────────────────────────────────────────────────
# ETAPA 3 — Enriquecimento com colunas de calendário
# ─────────────────────────────────────────────────────────────────

def enriquecer_calendario(df: pd.DataFrame) -> pd.DataFrame:
    log.info("Adicionando colunas de calendário...")

    idx = df.index

    df["ano"]        = idx.year.astype("int16")
    df["trimestre"]  = idx.quarter.astype("int8")
    df["mes"]        = idx.month.astype("int8")
    df["nome_mes"]   = idx.strftime("%B")
    df["semana_ano"] = idx.isocalendar().week.astype("int8")
    df["dia"]        = idx.day.astype("int8")
    df["dia_semana"] = idx.weekday.astype("int8") # 0 = Segunda, 6 = Domingo para bater com o SQL

    eh_semana = idx.weekday < 5
    feriados_set = _construir_set_feriados(idx.year.unique())
    
    if _USA_HOLIDAYS and feriados_set:
        eh_feriado = pd.Series(idx.date, index=idx).isin(feriados_set).values
        origem_feriado = "biblioteca holidays (fixos + móveis)"
    else:
        eh_feriado = idx.strftime("%d-%m").isin(FERIADOS_BR)
        origem_feriado = "conjunto fixo embutido"

    df["is_feriado"]  = eh_feriado
    df["is_fim_semana"] = ~eh_semana
    df["is_dia_util"] = eh_semana & ~eh_feriado

    log.info(
        "  ✓ Calendário: %d dias úteis, %d fins de semana, %d feriados (%s).",
        df["is_dia_util"].sum(),
        df["is_fim_semana"].sum(),
        df["is_feriado"].sum(),
        origem_feriado,
    )
    return df

# ─────────────────────────────────────────────────────────────────
# ETAPA 4 — Validação de qualidade dos dados
# ─────────────────────────────────────────────────────────────────

def validar_qualidade(df: pd.DataFrame) -> bool:
    log.info("Executando verificações de qualidade...")
    passou = True

    nulos = df[["SELIC", "IPCA", "USD_BRL"]].isna().sum()
    if nulos.sum() > 0:
        log.error("  ✗ Valores nulos encontrados:\n%s", nulos[nulos > 0])
        passou = False
    else:
        log.info("  ✓ Nenhum valor nulo nas colunas de indicadores.")

    checks = {
        "SELIC":   (0.0,  100.0),
        "IPCA":    (-5.0,  10.0),
        "USD_BRL": (1.0,   20.0),
    }
    for col, (vmin, vmax) in checks.items():
        fora = ((df[col] < vmin) | (df[col] > vmax)).sum()
        if fora > 0:
            log.warning("  ⚠ %s: %d valor(es) fora do intervalo [%.1f, %.1f]", col, fora, vmin, vmax)
        else:
            log.info("  ✓ %-7s plausível  [%.4f, %.4f]", col, df[col].min(), df[col].max())

    return passou

# ─────────────────────────────────────────────────────────────────
# ETAPA 5 — Exportação para a Camada Gold
# ─────────────────────────────────────────────────────────────────

def salvar_silver(df: pd.DataFrame) -> Path:
    caminho = DIR_SILVER / "indicadores_silver.csv"
    df.to_csv(caminho, encoding="utf-8-sig")

    tamanho_kb = caminho.stat().st_size / 1024
    log.info("  💾 Salvo em: %s  (%.1f KB)", caminho.name, tamanho_kb)
    return caminho

# ─────────────────────────────────────────────────────────────────
# ORQUESTRAÇÃO DA CAMADA SILVER
# ─────────────────────────────────────────────────────────────────

def executar_silver() -> pd.DataFrame:
    from datetime import datetime
    inicio = datetime.now()

    log.info("=" * 55)
    log.info("CAMADA SILVER — Início da transformação")
    log.info("=" * 55)

    dados_brutos = {}
    for nome in SERIES:
        dados_brutos[nome] = carregar_json_mais_recente(nome)

    log.info("-" * 55)
    log.info("Convertendo e tipando as séries...")
    series = {nome: json_para_dataframe(nome, dados) for nome, dados in dados_brutos.items()}

    log.info("-" * 55)
    idx = criar_indice_diario()
    df  = alinhar_series(series["selic"], series["ipca"], series["cambio"], idx)

    log.info("-" * 55)
    df = enriquecer_calendario(df)

    log.info("-" * 55)
    qualidade_ok = validar_qualidade(df)

    log.info("-" * 55)
    log.info("Exportando para Camada Gold...")
    caminho = salvar_silver(df)

    duracao = (datetime.now() - inicio).total_seconds()

    log.info("=" * 55)
    log.info(
        "SILVER concluído em %.1fs  |  %d linhas × %d colunas  |  qualidade: %s",
        duracao, len(df), df.shape[1],
        "OK ✓" if qualidade_ok else "COM ALERTAS ⚠",
    )
    log.info("=" * 55)

    print("\n── Prévia dos dados Silver (últimas 5 linhas) ──")
    print(df[["SELIC", "IPCA", "USD_BRL", "is_dia_util", "is_feriado"]].tail().to_string())
    print()

    return df

if __name__ == "__main__":
    executar_silver()