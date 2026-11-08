"""
gold/load.py
─────────────────────────────────────────────────────────────────────
Camada Gold — Persistência no PostgreSQL com Star Schema.

Responsabilidades desta camada:
  1. Criar o banco de dados se não existir
  2. Executar o DDL (schema.sql) para criar as tabelas
  3. Popular dim_indicador com os metadados das séries
  4. Popular dim_tempo com o calendário completo (2015–2025)
  5. Popular fato_indicadores em formato normalizado (long)
  6. Usar INSERT ... ON CONFLICT para operações idempotentes
─────────────────────────────────────────────────────────────────────
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

# Ajuste do path para encontrar o config.py na raiz do projeto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import DB_CONFIG, DIR_SILVER, SERIES

# ── Logger ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gold.load")

# ─────────────────────────────────────────────────────────────────
# CONEXÃO COM O BANCO DE DADOS
# ─────────────────────────────────────────────────────────────────

def _url_banco(nome_banco: str) -> str:
    c = DB_CONFIG
    return (
        f"postgresql+psycopg2://{c['user']}:{c['password']}"
        f"@{c['host']}:{c['port']}/{nome_banco}"
    )

def criar_banco_se_necessario() -> None:
    nome_banco = DB_CONFIG["database"]

    engine_postgres = create_engine(
        _url_banco("postgres"),
        isolation_level="AUTOCOMMIT",
    )

    with engine_postgres.connect() as conn:
        existe = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :nome"),
            {"nome": nome_banco},
        ).fetchone()

        if existe:
            log.info("Banco '%s' já existe. Continuando...", nome_banco)
        else:
            log.info("Criando banco '%s'...", nome_banco)
            conn.execute(text(
                f"CREATE DATABASE {nome_banco} "
                f"WITH ENCODING 'UTF8' TEMPLATE template0"
            ))
            log.info("  ✓ Banco criado.")

    engine_postgres.dispose()

def get_engine():
    engine = create_engine(
        _url_banco(DB_CONFIG["database"]),
        pool_pre_ping=True,
    )
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return engine

# ─────────────────────────────────────────────────────────────────
# DDL — CRIAÇÃO DAS TABELAS
# ─────────────────────────────────────────────────────────────────

def executar_schema(engine) -> None:
    schema_path = Path(__file__).resolve().parent / "schema.sql"

    with open(schema_path, encoding="utf-8") as f:
        sql_bruto = f.read()

    blocos_validos = []
    for bloco in sql_bruto.split(";"):
        bloco = bloco.strip()
        linhas_limpas = [
            l for l in bloco.splitlines()
            if not l.strip().startswith("\\")
            and not l.strip().startswith("--")
            and l.strip()
        ]
        sql_limpo = "\n".join(linhas_limpas).strip()
        if sql_limpo and any(
            sql_limpo.upper().startswith(kw)
            for kw in ("CREATE", "ALTER", "DROP", "INSERT", "SELECT", "COMMENT")
        ):
            blocos_validos.append(sql_limpo)

    log.info("Executando DDL (%d instruções)...", len(blocos_validos))

    with engine.begin() as conn:
        for bloco in blocos_validos:
            try:
                conn.execute(text(bloco))
            except Exception as e:
                if "already exists" not in str(e).lower() and "já existe" not in str(e).lower():
                    log.warning("  DDL ignorado: %s", str(e)[:80])

    log.info("  ✓ Schema aplicado: tabelas, índices e view criados.")

# ─────────────────────────────────────────────────────────────────
# POPULAR dim_indicador
# ─────────────────────────────────────────────────────────────────

def popular_dim_indicador(engine) -> None:
    log.info("Populando dim_indicador...")

    sql = text("""
        INSERT INTO dim_indicador
            (codigo_bcb, nome, sigla, unidade, frequencia, instituicao)
        VALUES
            (:codigo_bcb, :nome, :sigla, :unidade, :frequencia, :instituicao)
        ON CONFLICT (sigla) DO NOTHING
    """)

    with engine.begin() as conn:
        for info in SERIES.values():
            conn.execute(sql, {
                "codigo_bcb":  info["codigo"],
                "nome":        info["nome"],
                "sigla":       info["sigla"],
                "unidade":     info["unidade"],
                "frequencia":  info["frequencia"],
                "instituicao": info["instituicao"],
            })

    log.info("  ✓ dim_indicador: %d indicadores inseridos/confirmados.", len(SERIES))

# ─────────────────────────────────────────────────────────────────
# POPULAR dim_tempo
# ─────────────────────────────────────────────────────────────────

def popular_dim_tempo(engine, df: pd.DataFrame) -> None:
    log.info("Populando dim_tempo (%d datas)...", len(df))

    registros = []
    for data, row in df.iterrows():
        registros.append({
            "data":       data.date(),
            "ano":        int(row["ano"]),
            "trimestre":  int(row["trimestre"]),
            "mes":        int(row["mes"]),
            "nome_mes":   str(row["nome_mes"]),
            "semana_ano": int(row["semana_ano"]),
            "dia":        int(row["dia"]),
            "dia_semana": int(row["dia_semana"]),
            "dia_util":   bool(row["dia_util"]),
            "feriado":    bool(row["feriado"]),
            "fim_semana": bool(row["fim_semana"]),
        })

    sql = text("""
        INSERT INTO dim_tempo
            (data, ano, trimestre, mes, nome_mes,
             semana_ano, dia, dia_semana, dia_util, feriado, fim_semana)
        VALUES
            (:data, :ano, :trimestre, :mes, :nome_mes,
             :semana_ano, :dia, :dia_semana, :dia_util, :feriado, :fim_semana)
        ON CONFLICT (data) DO NOTHING
    """)

    LOTE = 500
    with engine.begin() as conn:
        for i in range(0, len(registros), LOTE):
            conn.execute(sql, registros[i: i + LOTE])

    log.info("  ✓ dim_tempo: %d datas inseridas/confirmadas.", len(registros))

# ─────────────────────────────────────────────────────────────────
# POPULAR fato_indicadores
# ─────────────────────────────────────────────────────────────────

def popular_fato_indicadores(engine, df: pd.DataFrame) -> None:
    log.info("Populando fato_indicadores...")

    with engine.connect() as conn:
        dim_t = pd.read_sql(
            "SELECT id_tempo, data FROM dim_tempo ORDER BY data",
            conn,
            parse_dates=["data"],
        )
        dim_i = pd.read_sql(
            "SELECT id_indicador, sigla FROM dim_indicador",
            conn,
        )

    mapa_tempo = dict(zip(dim_t["data"].dt.date, dim_t["id_tempo"]))
    mapa_indicador = dict(zip(dim_i["sigla"], dim_i["id_indicador"]))

    log.info("  FKs carregadas: %d datas · %d indicadores", len(mapa_tempo), len(mapa_indicador))

    colunas_indicadores = [info["sigla"] for info in SERIES.values()]

    df_long = (
        df[colunas_indicadores]
        .reset_index()
        .melt(id_vars="data", var_name="sigla", value_name="valor")
    )

    df_long["id_tempo"]     = df_long["data"].dt.date.map(mapa_tempo)
    df_long["id_indicador"] = df_long["sigla"].map(mapa_indicador)

    antes = len(df_long)
    df_long = df_long.dropna(subset=["id_tempo", "id_indicador", "valor"])
    if len(df_long) < antes:
        log.warning("  %d linhas ignoradas por FK ou valor nulo.", antes - len(df_long))

    df_long["id_tempo"]     = df_long["id_tempo"].astype(int)
    df_long["id_indicador"] = df_long["id_indicador"].astype(int)

    log.info("  %d registros para inserir (wide → long).", len(df_long))

    sql = text("""
        INSERT INTO fato_indicadores (id_tempo, id_indicador, valor)
        VALUES (:id_tempo, :id_indicador, :valor)
        ON CONFLICT (id_tempo, id_indicador)
        DO UPDATE SET valor = EXCLUDED.valor
    """)

    registros = df_long[["id_tempo", "id_indicador", "valor"]].to_dict("records")

    LOTE = 1000
    with engine.begin() as conn:
        for i in range(0, len(registros), LOTE):
            conn.execute(sql, registros[i: i + LOTE])
            
    log.info("  ✓ fato_indicadores: %d registros inseridos/atualizados.", len(registros))

# ─────────────────────────────────────────────────────────────────
# VERIFICAÇÃO PÓS-CARGA
# ─────────────────────────────────────────────────────────────────

def verificar_carga(engine) -> None:
    log.info("Verificando integridade da carga...")

    sql_resumo = text("""
        SELECT
            i.sigla,
            COUNT(*)            AS total_registros,
            MIN(t.data)         AS data_inicio,
            MAX(t.data)         AS data_fim,
            ROUND(MIN(f.valor)::numeric, 4) AS valor_min,
            ROUND(MAX(f.valor)::numeric, 4) AS valor_max,
            ROUND(AVG(f.valor)::numeric, 4) AS valor_medio
        FROM fato_indicadores f
        JOIN dim_tempo     t ON f.id_tempo     = t.id_tempo
        JOIN dim_indicador i ON f.id_indicador = i.id_indicador
        GROUP BY i.sigla
        ORDER BY i.sigla
    """)

    sql_contagem = text("""
        SELECT
            (SELECT COUNT(*) FROM dim_tempo)        AS dim_tempo,
            (SELECT COUNT(*) FROM dim_indicador)    AS dim_indicador,
            (SELECT COUNT(*) FROM fato_indicadores) AS fato_indicadores
    """)

    with engine.connect() as conn:
        contagens = conn.execute(sql_contagem).fetchone()
        resumo    = conn.execute(sql_resumo).fetchall()

    print()
    print("╔" + "═" * 53 + "╗")
    print("║  VERIFICAÇÃO DA CARGA — Star Schema PostgreSQL       ║")
    print("╠" + "═" * 53 + "╣")
    print(f"║  dim_tempo:        {contagens.dim_tempo:>6} linhas{' ' * 26}║")
    print(f"║  dim_indicador:    {contagens.dim_indicador:>6} linhas{' ' * 26}║")
    print(f"║  fato_indicadores: {contagens.fato_indicadores:>6} linhas{' ' * 26}║")
    print("╠" + "═" * 53 + "╣")
    print("║  Indicador  Registros  Início      Fim         Média ║")
    print("╠" + "─" * 53 + "╣")
    for r in resumo:
        print(
            f"║  {r.sigla:<9}  {r.total_registros:>8}  "
            f"{str(r.data_inicio):<10}  {str(r.data_fim):<10}  "
            f"{float(r.valor_medio):>6.2f} ║"
        )
    print("╚" + "═" * 53 + "╝")
    print()

# ─────────────────────────────────────────────────────────────────
# ORQUESTRAÇÃO DA CAMADA GOLD
# ─────────────────────────────────────────────────────────────────

def executar_gold() -> None:
    inicio = datetime.now()

    log.info("=" * 55)
    log.info("CAMADA GOLD — Início da persistência")
    log.info("=" * 55)

    csv_path = DIR_SILVER / "indicadores_silver.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Arquivo Silver não encontrado: {csv_path}\n"
            f"Execute primeiro: python main.py --silver"
        )

    log.info("Carregando dados Silver...")
    df = pd.read_csv(csv_path)
    
    # Renomeia as colunas para o padrão do banco
    df = df.rename(columns={
        "data_afericao": "data",
        "is_dia_util": "dia_util",
        "is_feriado": "feriado",
        "is_fim_semana": "fim_semana"
    })
    
    # Prepara o DatetimeIndex para iteração
    df["data"] = pd.to_datetime(df["data"])
    df.set_index("data", inplace=True)
    
    log.info("  %d linhas × %d colunas carregadas.", len(df), df.shape[1])

    log.info("-" * 55)
    criar_banco_se_necessario()

    log.info("-" * 55)
    log.info("Conectando ao banco '%s'...", DB_CONFIG["database"])
    engine = get_engine()
    log.info("  ✓ Conexão estabelecida.")

    log.info("-" * 55)
    executar_schema(engine)

    log.info("-" * 55)
    popular_dim_indicador(engine)

    log.info("-" * 55)
    popular_dim_tempo(engine, df)

    log.info("-" * 55)
    popular_fato_indicadores(engine, df)

    log.info("-" * 55)
    verificar_carga(engine)

    engine.dispose()

    duracao = (datetime.now() - inicio).total_seconds()
    log.info("=" * 55)
    log.info("GOLD concluído em %.1fs", duracao)
    log.info("=" * 55)

if __name__ == "__main__":
    try:
        executar_gold()
        print("✓ Camada Gold finalizada com sucesso!")
        print("  Próximo passo: abrir o Power BI e conectar ao PostgreSQL.\n")
    except Exception as e:
        log.error("Erro crítico na Gold: %s", e)
        sys.exit(1)