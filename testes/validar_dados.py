"""
testes/validar_dados.py
─────────────────────────────────────────────────────────────────────
Suite de testes de validação de integridade e qualidade dos dados.

Executa verificações automatizadas sobre o Star Schema no PostgreSQL:
  1. Integridade referencial (sem órfãos na fato)
  2. Ausência de valores nulos
  3. Cobertura temporal completa
  4. Plausibilidade dos valores por indicador
  5. Contagem correta de registros
  6. Alinhamento temporal (todas as datas têm os 3 indicadores)

Gera um relatório de validação que serve como evidência documental
para o capítulo de Resultados do TCC.

Uso:
  python testes/validar_dados.py
─────────────────────────────────────────────────────────────────────
"""

import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_CONFIG

# ── Cores para o terminal ─────────────────────────────────────────
VERDE = "\033[92m"
VERM  = "\033[91m"
AMAR  = "\033[93m"
AZUL  = "\033[94m"
RESET = "\033[0m"

OK    = f"{VERDE}[PASSOU]{RESET}"
FALHA = f"{VERM}[FALHOU]{RESET}"
AVISO = f"{AMAR}[AVISO ]{RESET}"


def get_engine():
    c = DB_CONFIG
    url = (
        f"postgresql+psycopg2://{c['user']}:{c['password']}"
        f"@{c['host']}:{c['port']}/{c['database']}"
    )
    return create_engine(url, pool_pre_ping=True)


class ResultadoTeste:
    """Acumula os resultados dos testes para o relatório final."""
    def __init__(self):
        self.passou = 0
        self.falhou = 0
        self.avisos = 0
        self.detalhes = []

    def registrar(self, nome, status, mensagem=""):
        self.detalhes.append((nome, status, mensagem))
        if status == "PASSOU":
            self.passou += 1
        elif status == "FALHOU":
            self.falhou += 1
        else:
            self.avisos += 1


# ─────────────────────────────────────────────────────────────────
# TESTES
# ─────────────────────────────────────────────────────────────────

def teste_integridade_referencial(engine, res):
    """Verifica se todas as FKs da fato apontam para dimensões válidas."""
    with engine.connect() as conn:
        orfaos_tempo = conn.execute(text("""
            SELECT COUNT(*) FROM fato_indicadores f
            LEFT JOIN dim_tempo t ON f.id_tempo = t.id_tempo
            WHERE t.id_tempo IS NULL
        """)).scalar()

        orfaos_ind = conn.execute(text("""
            SELECT COUNT(*) FROM fato_indicadores f
            LEFT JOIN dim_indicador i ON f.id_indicador = i.id_indicador
            WHERE i.id_indicador IS NULL
        """)).scalar()

    if orfaos_tempo == 0 and orfaos_ind == 0:
        print(f"{OK} Integridade referencial — nenhum registro órfão")
        res.registrar("Integridade referencial", "PASSOU")
    else:
        print(f"{FALHA} Integridade referencial — {orfaos_tempo} órfãos em dim_tempo, {orfaos_ind} em dim_indicador")
        res.registrar("Integridade referencial", "FALHOU",
                      f"{orfaos_tempo + orfaos_ind} órfãos")


def teste_valores_nulos(engine, res):
    """Verifica ausência de valores nulos na tabela fato."""
    with engine.connect() as conn:
        nulos = conn.execute(text("""
            SELECT COUNT(*) FROM fato_indicadores WHERE valor IS NULL
        """)).scalar()

    if nulos == 0:
        print(f"{OK} Valores nulos — nenhum valor nulo na fato_indicadores")
        res.registrar("Valores nulos", "PASSOU")
    else:
        print(f"{FALHA} Valores nulos — {nulos} registros com valor nulo")
        res.registrar("Valores nulos", "FALHOU", f"{nulos} nulos")


def teste_cobertura_temporal(engine, res):
    """Verifica se a cobertura temporal cobre 2015–2025."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT MIN(data) AS inicio, MAX(data) AS fim, COUNT(*) AS total
            FROM dim_tempo
        """)).fetchone()

    inicio, fim, total = row.inicio, row.fim, row.total
    cobre_inicio = inicio.year <= 2015
    cobre_fim    = fim.year >= 2025

    if cobre_inicio and cobre_fim:
        print(f"{OK} Cobertura temporal — {inicio} até {fim} ({total} dias)")
        res.registrar("Cobertura temporal", "PASSOU", f"{inicio} → {fim}")
    else:
        print(f"{AVISO} Cobertura temporal — {inicio} até {fim} (esperado 2015–2025)")
        res.registrar("Cobertura temporal", "AVISO", f"{inicio} → {fim}")


def teste_plausibilidade(engine, res):
    """Verifica se os valores estão dentro de intervalos plausíveis."""
    intervalos = {
        "SELIC":   (0.0,  30.0),
        "IPCA":    (-5.0, 10.0),
        "USD_BRL": (1.0,  10.0),
    }

    with engine.connect() as conn:
        for sigla, (vmin, vmax) in intervalos.items():
            row = conn.execute(text("""
                SELECT MIN(f.valor) AS mn, MAX(f.valor) AS mx
                FROM fato_indicadores f
                JOIN dim_indicador i ON f.id_indicador = i.id_indicador
                WHERE i.sigla = :sigla
            """), {"sigla": sigla}).fetchone()

            if row.mn is None:
                print(f"{AVISO} Plausibilidade {sigla} — sem dados")
                res.registrar(f"Plausibilidade {sigla}", "AVISO", "sem dados")
                continue

            dentro = vmin <= float(row.mn) and float(row.mx) <= vmax
            if dentro:
                print(f"{OK} Plausibilidade {sigla:<8} — [{row.mn:.4f}, {row.mx:.4f}] dentro de [{vmin}, {vmax}]")
                res.registrar(f"Plausibilidade {sigla}", "PASSOU")
            else:
                print(f"{AVISO} Plausibilidade {sigla:<8} — [{row.mn:.4f}, {row.mx:.4f}] fora de [{vmin}, {vmax}]")
                res.registrar(f"Plausibilidade {sigla}", "AVISO",
                              f"[{row.mn:.2f}, {row.mx:.2f}]")


def teste_alinhamento_temporal(engine, res):
    """
    Verifica que cada data possui exatamente os 3 indicadores.
    Este é o teste que valida o núcleo do TCC: o alinhamento temporal.
    """
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT COUNT(*) AS datas_incompletas FROM (
                SELECT id_tempo, COUNT(DISTINCT id_indicador) AS qtd
                FROM fato_indicadores
                GROUP BY id_tempo
                HAVING COUNT(DISTINCT id_indicador) <> 3
            ) sub
        """)).fetchone()

    incompletas = row.datas_incompletas
    if incompletas == 0:
        print(f"{OK} Alinhamento temporal — todas as datas têm os 3 indicadores")
        res.registrar("Alinhamento temporal", "PASSOU")
    else:
        print(f"{FALHA} Alinhamento temporal — {incompletas} datas com indicadores faltando")
        res.registrar("Alinhamento temporal", "FALHOU", f"{incompletas} incompletas")


def teste_contagem_registros(engine, res):
    """Verifica se a fato tem o número esperado de registros (datas × 3)."""
    with engine.connect() as conn:
        datas = conn.execute(text("SELECT COUNT(*) FROM dim_tempo")).scalar()
        fato  = conn.execute(text("SELECT COUNT(*) FROM fato_indicadores")).scalar()

    esperado = datas * 3
    if fato == esperado:
        print(f"{OK} Contagem de registros — {fato} = {datas} datas × 3 indicadores")
        res.registrar("Contagem de registros", "PASSOU", f"{fato} registros")
    else:
        print(f"{AVISO} Contagem de registros — {fato} registros (esperado {esperado})")
        res.registrar("Contagem de registros", "AVISO",
                      f"{fato} de {esperado}")


def teste_duplicatas(engine, res):
    """Verifica ausência de duplicatas (data × indicador)."""
    with engine.connect() as conn:
        dups = conn.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT id_tempo, id_indicador, COUNT(*) AS qtd
                FROM fato_indicadores
                GROUP BY id_tempo, id_indicador
                HAVING COUNT(*) > 1
            ) sub
        """)).scalar()

    if dups == 0:
        print(f"{OK} Duplicatas — nenhum par (data, indicador) duplicado")
        res.registrar("Duplicatas", "PASSOU")
    else:
        print(f"{FALHA} Duplicatas — {dups} pares duplicados encontrados")
        res.registrar("Duplicatas", "FALHOU", f"{dups} duplicatas")


# ─────────────────────────────────────────────────────────────────
# RELATÓRIO
# ─────────────────────────────────────────────────────────────────

def gerar_relatorio(res):
    """Gera relatório de validação em arquivo texto para o TCC."""
    caminho = Path(__file__).parent / "relatorio_validacao.txt"

    with open(caminho, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("RELATÓRIO DE VALIDAÇÃO DE DADOS\n")
        f.write("Pipeline de Indicadores Financeiros — TCC UNIFAGOC\n")
        f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"{'TESTE':<30} {'STATUS':<10} {'DETALHE'}\n")
        f.write("-" * 60 + "\n")
        for nome, status, msg in res.detalhes:
            f.write(f"{nome:<30} {status:<10} {msg}\n")

        f.write("\n" + "=" * 60 + "\n")
        f.write("RESUMO\n")
        f.write("-" * 60 + "\n")
        f.write(f"  Testes aprovados: {res.passou}\n")
        f.write(f"  Testes com aviso: {res.avisos}\n")
        f.write(f"  Testes falhos:    {res.falhou}\n")
        total = res.passou + res.avisos + res.falhou
        taxa = (res.passou / total * 100) if total else 0
        f.write(f"  Taxa de aprovação: {taxa:.1f}%\n")
        f.write("=" * 60 + "\n")

    print(f"\n{AZUL}Relatório salvo em: {caminho}{RESET}")
    return caminho


def main():
    print()
    print("═" * 60)
    print("  VALIDAÇÃO DE DADOS — Star Schema PostgreSQL")
    print("═" * 60)
    print()

    try:
        engine = get_engine()
    except Exception as e:
        print(f"{FALHA} Não foi possível conectar ao banco: {e}")
        sys.exit(1)

    res = ResultadoTeste()

    teste_integridade_referencial(engine, res)
    teste_valores_nulos(engine, res)
    teste_duplicatas(engine, res)
    teste_cobertura_temporal(engine, res)
    teste_alinhamento_temporal(engine, res)
    teste_contagem_registros(engine, res)
    teste_plausibilidade(engine, res)

    engine.dispose()

    # Resumo no terminal
    print()
    print("─" * 60)
    total = res.passou + res.avisos + res.falhou
    taxa = (res.passou / total * 100) if total else 0
    print(f"  {VERDE}{res.passou} aprovados{RESET}  ·  "
          f"{AMAR}{res.avisos} avisos{RESET}  ·  "
          f"{VERM}{res.falhou} falhas{RESET}  ·  "
          f"taxa: {taxa:.1f}%")
    print("─" * 60)

    gerar_relatorio(res)

    # Código de saída: 1 se houve falha crítica
    sys.exit(1 if res.falhou > 0 else 0)


if __name__ == "__main__":
    main()
