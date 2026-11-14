import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_CONFIG

VERDE = "\033[92m"
VERM  = "\033[91m"
AZUL  = "\033[94m"
RESET = "\033[0m"



VALORES_OFICIAIS = [
    # ── Selic Diária (% ao dia - SGS 11) ──────────────────────────
    ("SELIC", "2015-01-02", 0.0437,  0.001),
    ("SELIC", "2020-08-06", 0.0075,  0.001), 
    ("SELIC", "2022-08-04", 0.0508,  0.001), 
    ("SELIC", "2023-08-03", 0.0490,  0.001), 

    # ── IPCA (variação mensal % - SGS 433) ─────────────
    ("IPCA",  "2015-01-02",  1.24,  0.02), # Ajustado para o 1º dia útil
    ("IPCA",  "2021-01-01",  0.25,  0.02),
    ("IPCA",  "2022-04-01",  1.06,  0.02),

    # ── Câmbio USD/BRL (compra - SGS 1) ──────────────
    ("USD_BRL", "2015-01-02", 2.69, 0.05),
    ("USD_BRL", "2020-05-13", 5.90, 0.10), 
    ("USD_BRL", "2024-12-27", 6.18, 0.10),
]


def get_engine():
    c = DB_CONFIG
    url = (
        f"postgresql+psycopg2://{c['user']}:{c['password']}"
        f"@{c['host']}:{c['port']}/{c['database']}"
    )
    return create_engine(url, pool_pre_ping=True)


def buscar_valor_banco(engine, sigla, data_iso):
    """Busca o valor armazenado no banco para um indicador em uma data."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT f.valor
            FROM fato_indicadores f
            JOIN dim_tempo     t ON f.id_tempo     = t.id_tempo
            JOIN dim_indicador i ON f.id_indicador = i.id_indicador
            WHERE i.sigla = :sigla AND t.data = :data
        """), {"sigla": sigla, "data": data_iso}).fetchone()
    return float(row.valor) if row else None


def main():
    print()
    print("═" * 68)
    print("  COMPARAÇÃO COM VALORES OFICIAIS (BCB / IBGE)")
    print("═" * 68)
    print()

    try:
        engine = get_engine()
    except Exception as e:
        print(f"{VERM}Erro de conexão: {e}{RESET}")
        sys.exit(1)

    # Cabeçalho da tabela
    print(f"{'Indicador':<10} {'Data':<12} {'Oficial':>10} {'Banco':>10} {'Δ':>8}  Status")
    print("─" * 68)

    acertos = 0
    total   = 0
    linhas_tabela = []

    for sigla, data_iso, oficial, tol in VALORES_OFICIAIS:
        banco = buscar_valor_banco(engine, sigla, data_iso)
        total += 1

        if banco is None:
            print(f"{sigla:<10} {data_iso:<12} {oficial:>10.4f} {'—':>10} {'—':>8}  {VERM}SEM DADO{RESET}")
            linhas_tabela.append((sigla, data_iso, oficial, None, None, "SEM DADO"))
            continue

        delta = abs(banco - oficial)
        ok = delta <= tol

        if ok:
            acertos += 1
            status = f"{VERDE}OK{RESET}"
            status_txt = "OK"
        else:
            status = f"{VERM}DIVERGE{RESET}"
            status_txt = "DIVERGE"

        print(f"{sigla:<10} {data_iso:<12} {oficial:>10.4f} {banco:>10.4f} {delta:>8.4f}  {status}")
        linhas_tabela.append((sigla, data_iso, oficial, banco, delta, status_txt))

    engine.dispose()

    # Resumo
    taxa = (acertos / total * 100) if total else 0
    print("─" * 68)
    print(f"  Acurácia: {VERDE}{acertos}/{total}{RESET} valores conferem  ·  taxa: {taxa:.1f}%")
    print("═" * 68)

    # ── Gerar tabela Markdown para o TCC ──────────────────────────
    caminho = Path(__file__).parent / "tabela_comparacao_oficial.md"
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("# Tabela de Comparação com Valores Oficiais\n\n")
        f.write("Validação de acurácia — Pipeline vs. fontes oficiais (BCB/IBGE)\n\n")
        f.write("| Indicador | Data | Valor Oficial | Valor no Banco | Diferença | Status |\n")
        f.write("|-----------|------|--------------:|---------------:|----------:|--------|\n")
        for sigla, data, oficial, banco, delta, status in linhas_tabela:
            banco_str = f"{banco:.4f}" if banco is not None else "—"
            delta_str = f"{delta:.4f}" if delta is not None else "—"
            f.write(f"| {sigla} | {data} | {oficial:.4f} | {banco_str} | {delta_str} | {status} |\n")
        f.write(f"\n**Taxa de acurácia: {taxa:.1f}%** ({acertos} de {total} valores)\n")

    print(f"\n{AZUL}Tabela Markdown salva em: {caminho}{RESET}")
    print("  → Use esta tabela no capítulo de Resultados do TCC.\n")


if __name__ == "__main__":
    main()
