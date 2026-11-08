-- ═══════════════════════════════════════════════════════════════════
-- gold/schema.sql
-- Star Schema — Pipeline de Dados / Indicadores Financeiros
-- ═══════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────────
-- 1. DIMENSÃO TEMPO
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dim_tempo (
    id_tempo     SERIAL       PRIMARY KEY,
    data         DATE         NOT NULL UNIQUE,
    ano          SMALLINT     NOT NULL,
    trimestre    SMALLINT     NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    mes          SMALLINT     NOT NULL CHECK (mes BETWEEN 1 AND 12),
    nome_mes     VARCHAR(15)  NOT NULL,
    semana_ano   SMALLINT     NOT NULL CHECK (semana_ano BETWEEN 1 AND 53),
    dia          SMALLINT     NOT NULL CHECK (dia BETWEEN 1 AND 31),
    dia_semana   SMALLINT     NOT NULL,
    dia_util     BOOLEAN      NOT NULL DEFAULT FALSE,
    feriado      BOOLEAN      NOT NULL DEFAULT FALSE,
    fim_semana   BOOLEAN      NOT NULL DEFAULT FALSE,
    CONSTRAINT ck_feriado_nao_util CHECK (NOT (feriado = TRUE AND dia_util = TRUE))
);

-- ───────────────────────────────────────────────────────────────────
-- 2. DIMENSÃO INDICADOR
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dim_indicador (
    id_indicador  SERIAL       PRIMARY KEY,
    codigo_bcb    INTEGER      NOT NULL UNIQUE,
    nome          VARCHAR(80)  NOT NULL,
    sigla         VARCHAR(15)  NOT NULL UNIQUE,
    unidade       VARCHAR(20)  NOT NULL,
    frequencia    CHAR(1)      NOT NULL CHECK (frequencia IN ('D', 'M')),
    instituicao   VARCHAR(80)  NOT NULL
);

-- ───────────────────────────────────────────────────────────────────
-- 3. TABELA FATO — INDICADORES
-- ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fato_indicadores (
    id_fato       SERIAL          PRIMARY KEY,
    id_tempo      INTEGER         NOT NULL REFERENCES dim_tempo(id_tempo) ON DELETE RESTRICT,
    id_indicador  INTEGER         NOT NULL REFERENCES dim_indicador(id_indicador) ON DELETE RESTRICT,
    valor         NUMERIC(12, 6)  NOT NULL,
    CONSTRAINT uq_fato_tempo_indicador UNIQUE (id_tempo, id_indicador)
);

-- ───────────────────────────────────────────────────────────────────
-- 4. ÍNDICES DE PERFORMANCE
-- ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_fato_tempo ON fato_indicadores (id_tempo);
CREATE INDEX IF NOT EXISTS idx_fato_indicador ON fato_indicadores (id_indicador);
CREATE INDEX IF NOT EXISTS idx_tempo_data ON dim_tempo (data);
CREATE INDEX IF NOT EXISTS idx_tempo_ano_mes ON dim_tempo (ano, mes);

-- ───────────────────────────────────────────────────────────────────
-- 5. VIEW ANALÍTICA 
-- ───────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_indicadores AS
SELECT
    t.data, t.ano, t.trimestre, t.mes, t.nome_mes,
    t.dia_util, t.feriado,
    i.sigla AS indicador, i.nome AS nome_indicador, i.unidade,
    f.valor
FROM fato_indicadores f
JOIN dim_tempo     t ON f.id_tempo     = t.id_tempo
JOIN dim_indicador i ON f.id_indicador = i.id_indicador
ORDER BY t.data, i.sigla;