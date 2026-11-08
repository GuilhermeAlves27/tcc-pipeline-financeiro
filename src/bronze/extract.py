"""
bronze/extract.py
─────────────────────────────────────────────────────────────────────
Camada Bronze — Extração de dados brutos da API SGS do Banco Central.

Responsabilidades desta camada:
  1. Realizar requisições HTTP à API SGS/BCB para cada indicador
  2. Aplicar resiliência a falhas (retry com back-off exponencial)
  3. Salvar o retorno bruto em JSON, sem nenhuma modificação

Princípio fundamental (Kimball & Caserta, 2004):
  "A camada de extração deve ser resiliente a falhas de comunicação
   com a origem e preservar o dado bruto para reprocessamento."
─────────────────────────────────────────────────────────────────────
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import requests
import urllib3
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Desativa o warning de SSL que aparece ao usar verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Adiciona a raiz do projeto ao path para importar config.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import (
    BCB_BASE_URL,
    DATA_FIM,
    DATA_INICIO,
    DIR_BRONZE,  # Corrigido para a nomenclatura do nosso config.py
    REQUEST_TIMEOUT,
    RETRY_MAX_ATTEMPTS,
    RETRY_WAIT_MAX,
    RETRY_WAIT_MIN,
    SERIES,
)

# ── Configuração do logger ────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bronze.extract")


# ── Função de extração com retry automático ───────────────────────

@retry(
    retry=retry_if_exception_type(
        (requests.exceptions.ConnectionError,
         requests.exceptions.Timeout,
         requests.exceptions.HTTPError)
    ),
    stop=stop_after_attempt(RETRY_MAX_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
    before_sleep=before_sleep_log(log, logging.WARNING),
)
def _requisitar_api(url_completa: str) -> list[dict]:
    """
    Faz uma requisição GET à API do BCB com WAF Bypass e retry automático.
    """
    log.debug("GET %s", url_completa)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }
    
    # Faz a requisição passando a URL completa já formatada, SEM o arg params
    resp = requests.get(url_completa, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)
    resp.raise_for_status() 
    
    dados = resp.json()

    if not isinstance(dados, list) or len(dados) == 0:
        raise ValueError(f"Resposta inesperada da API: {dados!r}")

    return dados


def extrair_serie(nome: str, info: dict) -> list[dict]:
    """
    Extrai uma série temporal completa do SGS utilizando paginação (chunking)
    para contornar a restrição de 10 anos do Banco Central (Erro 406).
    """
    from datetime import timedelta
    url_base = BCB_BASE_URL.format(info["codigo"])
    log.info("Extraindo %-8s  (código SGS: %d) ...", nome.upper(), info["codigo"])

    try:
        formato = "%d/%m/%Y"
        dt_atual = datetime.strptime(DATA_INICIO, formato)
        dt_fim_total = datetime.strptime(DATA_FIM, formato)
        
        dados_completos = []
        passo = timedelta(days=365 * 5) # Quebra em lotes de 5 anos (seguro)
        
        # Loop para extrair a série em blocos menores que 10 anos
        while dt_atual <= dt_fim_total:
            dt_proximo = min(dt_atual + passo, dt_fim_total)
            str_inicio = dt_atual.strftime(formato)
            str_fim = dt_proximo.strftime(formato)
            
            # Monta a URL manualmente sem o dicionário params para preservar as barras
            url_lote = f"{url_base}?formato=json&dataInicial={str_inicio}&dataFinal={str_fim}"
            
            lote_dados = _requisitar_api(url_lote)
            dados_completos.extend(lote_dados)
            
            # Avança o cursor para o dia seguinte ao último dia do lote atual
            dt_atual = dt_proximo + timedelta(days=1)

        log.info(
            "  ✓ %-8s  %d registros  |  %s → %s",
            nome.upper(),
            len(dados_completos),
            dados_completos[0]["data"],
            dados_completos[-1]["data"],
        )
        return dados_completos

    except RetryError:
        log.error(
            "  ✗ %-8s  Falha após %d tentativas. Verifique sua conexão.",
            nome.upper(),
            RETRY_MAX_ATTEMPTS,
        )
        raise
    except ValueError as e:
        log.error("  ✗ %-8s  Dado inválido: %s", nome.upper(), e)
        raise


# ── Persistência do dado bruto ────────────────────────────────────

def salvar_bronze(nome: str, dados: list[dict]) -> Path:
    """
    Salva os dados brutos em JSON dentro de data/bronze/.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho   = DIR_BRONZE / f"{nome}_{timestamp}.json"

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    tamanho_kb = caminho.stat().st_size / 1024
    log.info("  💾 Salvo em: %s  (%.1f KB)", caminho.name, tamanho_kb)
    return caminho


# ── Orquestração da camada Bronze ─────────────────────────────────

def executar_bronze() -> dict[str, Path]:
    """
    Orquestra a extração e salva as séries do config.SERIES.
    """
    log.info("=" * 55)
    log.info("CAMADA BRONZE — Início da extração")
    log.info("Período: %s → %s", DATA_INICIO, DATA_FIM)
    log.info("=" * 55)

    inicio   = datetime.now()
    caminhos = {}
    erros    = []

    for nome, info in SERIES.items():
        try:
            dados          = extrair_serie(nome, info)
            caminho        = salvar_bronze(nome, dados)
            caminhos[nome] = caminho
        except Exception as e:
            erros.append(nome)
            log.error("Série '%s' ignorada: %s", nome, e)

    duracao = (datetime.now() - inicio).total_seconds()

    log.info("=" * 55)
    log.info(
        "BRONZE concluído em %.1fs  |  %d/%d séries extraídas",
        duracao,
        len(caminhos),
        len(SERIES),
    )

    if erros:
        log.warning("Séries com falha: %s", ", ".join(erros))
        log.warning("Execute novamente para retentar as séries com falha.")
        raise RuntimeError("Camada Bronze finalizada com erros parciais.")

    log.info("=" * 55)
    return caminhos


if __name__ == "__main__":
    executar_bronze()