"""
Config.py
É aonde ficam as configurações do projeto como banco de dados, API, etc.
Com ele, você pode alterar as configurações do projeto sem precisar alterar o código principal.
"""


import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import date

# Carrega as variáveis do arquivo .env automaticamente
load_dotenv()

# ── Caminhos do projeto (Arquitetura Medalhão) ────────────────────
BASE_DIR       = Path(__file__).resolve().parent
DIR_BRONZE     = BASE_DIR / "data" / "bronze"
DIR_SILVER     = BASE_DIR / "data" / "silver"

# Garante que as pastas existam ao importar o módulo
DIR_BRONZE.mkdir(parents=True, exist_ok=True)
DIR_SILVER.mkdir(parents=True, exist_ok=True)


# ── Séries temporais do SGS (Banco Central) ───────────────────────
SERIES: dict[str, dict] = {
    "selic": {
        "codigo":      11,
        "nome":        "Taxa Selic Over",
        "sigla":       "SELIC",
        "unidade":     "% a.a.",
        "frequencia":  "D",
        "instituicao": "Banco Central do Brasil",
    },
    "ipca": {
        "codigo":      433,
        "nome":        "IPCA - Variação Mensal",
        "sigla":       "IPCA",
        "unidade":     "% mês",
        "frequencia":  "M",
        "instituicao": "IBGE",
    },
    "cambio": {
        "codigo":      1,
        "nome":        "Taxa de Câmbio - Dólar Americano (Compra)",
        "sigla":       "USD_BRL",
        "unidade":     "R$/USD",
        "frequencia":  "D",
        "instituicao": "Banco Central do Brasil",
    },
}

# ── Parâmetros da API do BCB ──────────────────────────────────────
BCB_BASE_URL = os.getenv(
    "BCB_BASE_URL",
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{}/dados",
)
DATA_INICIO = os.getenv("DATA_INICIO", "01/01/2015")
# Usa hoje quando o .env não define nada
DATA_FIM = os.getenv("DATA_FIM") or date.today().strftime("%d/%m/%Y")

# Configurações de resiliência para requisições HTTP (Camada Bronze)
REQUEST_TIMEOUT      = 30   # segundos para timeout de cada requisição
RETRY_MAX_ATTEMPTS   = 5    # número máximo de tentativas em caso de falha
RETRY_WAIT_MIN       = 2    # segundos de espera mínima entre tentativas
RETRY_WAIT_MAX       = 30   # segundos de espera máxima entre tentativas


# ── Parâmetros do banco de dados ──────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     os.getenv("DB_PORT",     "5433"),
    "database": os.getenv("DB_NAME",     "tcc_macro_db"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", "3124"),
}


# ── Janela temporal (Transformação Pandas - Camada Silver) ─────────
DATA_INICIO_PANDAS = "2015-01-01"
# Sempre derivado de DATA_FIM, nunca diverge
DATA_FIM_PANDAS = date.today().strftime("%Y-%m-%d") \
                  if not os.getenv("DATA_FIM") \
                  else date(
                      int(DATA_FIM[6:10]),  # ano
                      int(DATA_FIM[3:5]),   # mês
                      int(DATA_FIM[0:2]),   # dia
                  ).strftime("%Y-%m-%d")
