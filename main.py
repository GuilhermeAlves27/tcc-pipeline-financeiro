import argparse
import time
from datetime import datetime
import sys

# Importação REAL da Camada Bronze
try:
    from src.bronze.extract import executar_bronze
except ImportError as e:
    print(f"Erro de importação. Verifique se a pasta src/bronze existe: {e}")
    sys.exit(1)

# Importação REAL da Camada Silver
try:
    from src.silver.transform import executar_silver
except ImportError as e:
    print(f"Erro de importação na Silver: {e}")
    sys.exit(1)

# Importação REAL da Camada Gold
try:
    from src.gold.load import executar_gold
except ImportError as e:
    print(f"Aviso de importação na Gold: {e}")
    # Stub temporário para não quebrar caso a Gold ainda não esteja 100% pronta
    executar_gold = lambda: print("  -> Módulo Gold ainda não codificado.")

def cabecalho():
    """Imprime o cabeçalho oficial de execução do pipeline do TCC."""
    print("=" * 60)
    print(" PIPELINE DE DADOS - INDICADORES MACROECONÔMICOS (TCC)")
    print(f" Data de Execução: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

def orquestrar(run_bronze, run_silver, run_gold):
    """Executa as camadas solicitadas sequencialmente com medição de tempo."""
    cabecalho()
    tempo_inicio_total = time.perf_counter()

    if run_bronze:
        print("\n[1/3] INICIANDO CAMADA BRONZE (Extração)")
        t0 = time.perf_counter()
        try:
            # Chama a função sem argumentos
            executar_bronze()
            print(f"✓ Bronze finalizada em {time.perf_counter() - t0:.2f}s")
        except Exception as e:
            print(f" ERRO CRÍTICO na Camada Bronze: {e}")
            sys.exit(1)

    if run_silver:
        print("\n[2/3] INICIANDO CAMADA SILVER (Transformação)")
        t0 = time.perf_counter()
        try:
            # Chama a função sem argumentos (ela lê os JSONs do disco)
            executar_silver()
            print(f"✓ Silver finalizada em {time.perf_counter() - t0:.2f}s")
        except Exception as e:
            print(f" ERRO CRÍTICO na Camada Silver: {e}")
            sys.exit(1)

    if run_gold:
        print("\n[3/3] INICIANDO CAMADA GOLD (Carga no PostgreSQL)")
        t0 = time.perf_counter()
        try:
            # Chama a função sem argumentos (ela lê o CSV do disco)
            executar_gold()
            print(f"✓ Gold finalizada em {time.perf_counter() - t0:.2f}s")
        except Exception as e:
            print(f" ERRO CRÍTICO na Camada Gold: {e}")
            sys.exit(1)

    tempo_total = time.perf_counter() - tempo_inicio_total
    print("\n" + "=" * 60)
    print(f" PIPELINE CONCLUÍDO COM SUCESSO - Tempo Total: {tempo_total:.2f}s")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestrador do Pipeline ETL - TCC")
    parser.add_argument("--bronze", action="store_true", help="Executa apenas a camada Bronze")
    parser.add_argument("--silver", action="store_true", help="Executa apenas a camada Silver")
    parser.add_argument("--gold", action="store_true", help="Executa apenas a camada Gold")
    
    args = parser.parse_args()

    # Se nenhum argumento for passado, executa o pipeline completo
    if not (args.bronze or args.silver or args.gold):
        orquestrar(run_bronze=True, run_silver=True, run_gold=True)
    else:
        orquestrar(run_bronze=args.bronze, run_silver=args.silver, run_gold=args.gold)