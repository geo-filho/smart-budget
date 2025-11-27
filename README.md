# 💸 Smart Budget AI: Sistema Inteligente de Gestão Financeira Pessoal

<p align="center">
  <img src="https://img.shields.io/badge/Linguagem-Python-blue?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Interface-Tkinter%2FTTKBooostrap-informational?style=for-the-badge&logo=tKinter&logoColor=white" />
  <img src="https://img.shields.io/badge/IA%20Integrada-Google%20Gemini-FF6E00?style=for-the-badge&logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/Dados%20Financeiros-yfinance%20%2F%20Pandas-success?style=for-the-badge&logo=pandas&logoColor=white" />
</p>

## 🌟 Visão Geral

O **Smart Budget AI** é um robusto sistema de gestão financeira pessoal construído em Python. Ele combina uma interface gráfica intuitiva com o poder da **Inteligência Artificial (Gemini API)** para simplificar o registro de transações, gerar relatórios detalhados e fornecer análises e sugestões de investimento em tempo real.

O grande diferencial é a capacidade de **lançar gastos e ganhos usando linguagem natural**, além de receber um **relatório financeiro inteligente** gerado pela IA.

## ✨ Recursos Principais

* **Lançamentos com IA (Linguagem Natural):** Adicione gastos ("Adicione 200 no lazer") e ganhos ("Recebi 500 de freelance") usando frases simples, e a IA categoriza e registra automaticamente.
* **Relatórios e Análises Inteligentes:** Geração de um relatório detalhado com balanço financeiro, identificação de despesas críticas e sugestões personalizadas de ação, tudo fornecido pelo Gemini.
* **Gestão de Metas de Poupança:** Crie metas de poupança com valores-alvo e acompanhe o progresso de cada depósito.
* **Acompanhamento de Investimentos:** Busque e monitore cotações de ativos em tempo real (via `yfinance`), visualize gráficos históricos e receba sugestões de investimento simuladas.
* **Chatbot de Economia:** Um assistente financeiro baseado em IA para tirar dúvidas sobre economia, inflação e investimentos (também powered by Gemini).
* **Visualização de Dados:** Gráficos de pizza (distribuição de gastos) e barras (histórico mensal) para uma visão clara de suas finanças.
* **Persistência e Exportação:** Salva todos os dados localmente (`.json`) e permite a exportação para um arquivo Excel (`.xlsx`) limpo, **sem colunas desnecessárias como a descrição bruta da IA**.

## 🛠️ Instalação e Configuração

### 1. Pré-requisitos

Certifique-se de ter o Python 3.8 ou superior instalado.

### 2. Configuração do Ambiente

Crie um ambiente virtual (recomendado) e instale as dependências:

```bash
# Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate  # No Linux/macOS
# venv\Scripts\activate   # No Windows

# Instale as dependências
pip install pandas numpy matplotlib ttkbootstrap google-genai yfinance openpyxl
