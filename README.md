# 📊 Pipeline de Dados - Indicadores Macroeconômicos (BCB)

![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-2.0+-150458?style=for-the-badge&logo=pandas&logoColor=white)
![Power BI](https://img.shields.io/badge/Power_BI-F2C811?style=for-the-badge&logo=powerbi&logoColor=black)

Este repositório contém o código-fonte do Trabalho de Conclusão de Curso (TCC) em Ciência da Computação (UNIFAGOC). O projeto consiste em um **Pipeline ETL automatizado** baseado na **Arquitetura Medalhão**, projetado para extrair, alinhar e modelar indicadores financeiros (Taxa Selic, IPCA e Câmbio USD/BRL) a partir da API do Banco Central do Brasil (SGS).

## 🏛️ Arquitetura do Projeto (Medalhão)

- **🥉 Camada Bronze (Raw):** Extração resiliente (com retries exponenciais via `tenacity`) da API SGS do Banco Central. Os dados brutos são persistidos imutavelmente em formato `.json`.
- **🥈 Camada Silver (Trusted):** Transformação e limpeza em memória utilizando `Pandas`. Resolve a assimetria do calendário financeiro (mensal vs diário) aplicando reindexação, preenchimento direcional (*forward-fill*) e marcação de dias úteis, fins de semana e feriados (via `holidays`).
- **🥇 Camada Gold (Refined):** Modelagem dimensional em **Star Schema**. Ingestão idempotente (`UPSERT`) no banco de dados **PostgreSQL**, garantindo integridade referencial e eliminação de duplicidades.
- **📈 Camada Semântica:** Dashboard executivo no **Microsoft Power BI**, com métricas de inteligência temporal (DAX) para análise do Juro Real, inflação acumulada e mecanismo de transmissão monetária.

## 📂 Estrutura do Repositório

```text
tcc_pipeline_financeiro/
├── dashboard/                 # Medidas DAX e guias de formatação do Power BI
├── data/                      # Armazenamento local temporário (Bronze/Silver)
├── src/                       # Código-fonte principal do Pipeline
│   ├── bronze/                # Scripts de extração (requests, json)
│   ├── silver/                # Scripts de transformação (pandas)
│   ├── gold/                  # Scripts de carga e DDL do PostgreSQL (sqlalchemy)
│   └── testes/                # Scripts de validação de dados e benchmarking
├── .env.example               # Template de variáveis de ambiente
├── .gitignore                 # Arquivos ignorados pelo Git
├── config.py                  # Parâmetros centrais e limites de plausibilidade
├── main.py                    # Orquestrador central do Pipeline (ETL)
└── requirements.txt           # Dependências do projeto

🚀 Como Executar o Projeto
1. Pré-requisitos
Python 3.11 ou superior

PostgreSQL (Rodando na porta padrão 5432 ou 5433)

Git

2. Clonar o Repositório e Instalar Dependências
Bash
# Clone o repositório
git clone [https://github.com/GuilhermeAlves27/tcc-pipeline-financeiro.git](https://github.com/GuilhermeAlves27/tcc-pipeline-financeiro.git)
cd tcc-pipeline-financeiro

# Crie e ative o ambiente virtual
python -m venv venv
venv\Scripts\activate  # No Windows

# Instale as dependências
pip install -r requirements.txt
3. Configurar Variáveis de Ambiente
Copie o arquivo de exemplo e renomeie para .env. Preencha com as suas credenciais do PostgreSQL:

Bash
cp .env.example .env
(Edite o .env com seu DB_USER, DB_PASSWORD, DB_PORT, etc.)

4. Executar o Pipeline
O orquestrador principal roda as 3 camadas em sequência. Execute na raiz do projeto:

Bash
python main.py
5. Executar a Bateria de Testes
Para auditar a qualidade da malha de dados (nulos, plausibilidade e chaves):

Bash
python src/testes/validar_dados.py
👨‍💻 Autor
Guilherme Silva Alves Vieira

Graduando em Ciência da Computação - UNIFAGOC

Orientador: Prof. Joas Baia