# Resultado — Ganho de Eficiência do Pipeline

Medição realizada em 14/11/2026 16:00

## Detalhamento do processo manual (baseline)

| Etapa | Tempo estimado |
|-------|---------------:|
| Acessar o site do BCB e localizar a série Selic | 3min 0s |
| Baixar planilha da Selic (2015-2025) e conferir | 2min 30s |
| Acessar o SIDRA/IBGE e localizar a série IPCA | 3min 30s |
| Baixar planilha do IPCA e conferir | 2min 30s |
| Acessar o BCB e baixar cotações de câmbio | 3min 0s |
| Abrir os 3 arquivos no Excel | 1min 0s |
| Padronizar formatos de data entre as planilhas | 5min 0s |
| Alinhar manualmente datas divergentes (Selic×IPCA) | 10min 0s |
| Preencher lacunas de fins de semana e feriados | 7min 0s |
| Consolidar em uma única planilha | 4min 0s |
| Construir gráficos manualmente no Excel | 6min 0s |
| Revisar e corrigir erros de digitação/cópia | 5min 0s |
| **Total manual** | **52min 30s** |

## Detalhamento do pipeline automatizado

| Camada | Tempo medido |
|--------|-------------:|
| Bronze (extração) | 7,6s |
| Silver (transformação e alinhamento) | 0,5s |
| Gold (carga no PostgreSQL) | 4,6s |
| **Total pipeline** | **12,7s** |

## Comparativo final

| Métrica | Valor |
|---------|------:|
| Tempo manual | 52min 30s |
| Tempo pipeline | 12,7s |
| Redução absoluta | 52min 17s |
| **Ganho de eficiência** | **99.6%** |
| **Fator de aceleração** | **248×** |

## Análise de erros

| Tipo de erro | Processo manual | Pipeline |
|--------------|:---------------:|:--------:|
| Erros de digitação/cópia | Frequentes | Zero (automatizado) |
| Datas desalinhadas | Comum | Zero (forward-fill) |
| Valores nulos não tratados | Comum | Zero (validação) |
| Inconsistência de tipos | Comum | Zero (tipagem explícita) |
