import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from google import genai
from google.genai import types
import re
import unicodedata
import numpy as np
import os
import json 
from datetime import datetime
import requests 
import yfinance as yf 
from matplotlib.figure import Figure 
import random 
import time

# Optional: interactive cursor for matplotlib
try:
    import mplcursors
    MPLCURSORS_AVAILABLE = True
except Exception:
    MPLCURSORS_AVAILABLE = False

# ----------------------------------------------------------------------
# ---------- CONFIGURAÇÃO DA API - SUBSTITUA PELA SUA CHAVE REAL ----------
# ----------------------------------------------------------------------
GEMINI_API_KEY = "AIzaSyBjhHyIOJ9u-KG4LmlK2O0OcTE8Zw5TSAA" # Substitua pela sua chave REAL
client = None
if GEMINI_API_KEY and GEMINI_API_KEY.startswith("AIza"):
    try:
        # AQUI VOCÊ DEVE INSERIR SUA CHAVE REAL
        client = genai.Client(api_key="AIzaSyBjhHyIOJ9u-KG4LmlK2O0OcTE8Zw5TSAA") 
    except Exception as e:
        print(f"Atenção: Erro ao inicializar o cliente Gemini. Funções de IA não funcionarão. Erro: {e}")
# ----------------------------------------------------------------------

# ---------- Dados Globais e Estrutura ----------
DATA_FILE = "smart_budget_data.json" 

# DataFrames Agregados
dados = pd.DataFrame(columns=["departamento_normalizado", "departamento", "gasto_total"])
ganhos_df = pd.DataFrame(columns=["fonte_normalizada", "fonte", "valor"])
poupancas_df = pd.DataFrame(columns=["meta", "meta_normalizada", "valor_depositado", "valor_meta"])

# DataFrames Detalhados (dados brutos)
gastos_detalhe_bruto = pd.DataFrame(columns=["id_unico", "data_lancamento", "departamento", "gasto_total", "descricao_original"])
ganhos_detalhe_bruto = pd.DataFrame(columns=["id_unico", "data_lancamento", "fonte", "valor", "descricao_original"])
poupancas_detalhe = pd.DataFrame(columns=["id_meta", "id_lancamento", "data_lancamento", "meta", "descricao", "valor_deposito", "valor_meta_total", "valor_atingido"])

# Lista de ativos de investimento - CORRIGIDO O PADRÃO PARA B3 (.SA)
LISTA_ATIVOS_ACOMPANHADOS = []

# SIMULADO: Lista de sugestões de investimento
SUGESTOES_INVESTIMENTO = [] 

renda_total = 0.0
total_gastos = 0.0
RENDAS_DEFINITIVAS = ["salario fixo"]

# Variáveis para Gráficos
fig = None
canvas = None
fig_invest = None
canvas_invest = None
ax_invest = None

# Variável global para a sessão de chat (necessária para manter o contexto)
chat_session = None

def gerar_id_unico():
    return f"id_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S%f')}{np.random.randint(1000, 9999)}"

# ---------- Funções de Normalização e Limpeza ----------
def normalizar_texto(texto):
    if not isinstance(texto, str):
        return texto
    nfkd_form = unicodedata.normalize('NFKD', texto)
    sem_acento = u"".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return sem_acento.strip().lower()

def capitalizar_normalizado(texto_normalizado):
    if not isinstance(texto_normalizado, str):
        return texto_normalizado
    return texto_normalizado.capitalize()

def limpar_relatorio(texto):
    if not isinstance(texto, str):
        return texto
    texto = re.sub(r"^(#+[\s]*|---+)\s*", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"[\*\_]", "", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = re.sub(r"^[ \t]+|[ \t]+$", "", texto, flags=re.MULTILINE)
    return texto.strip()

# ---------- FUNÇÕES DE PERSISTÊNCIA DE DADOS (COM CORREÇÃO DE ATIVOS) ----------
def carregar_dados_locais():
    global gastos_detalhe_bruto, ganhos_detalhe_bruto, poupancas_detalhe, LISTA_ATIVOS_ACOMPANHADOS
    
    # Lista padrão corrigida com .SA para yfinance
    default_ativos = ["PETR4.SA", "VALE3.SA"]

    if not os.path.exists(DATA_FILE):
        LISTA_ATIVOS_ACOMPANHADOS = default_ativos
        return
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        def load_df(key, columns):
            if key in data and data[key]:
                df = pd.DataFrame(data[key], columns=columns)
                if 'data_lancamento' in df.columns:
                    df['data_lancamento'] = df['data_lancamento'].astype(str)
                for col in ['gasto_total', 'valor', 'valor_deposito', 'valor_meta_total', 'valor_atingido']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                return df.copy() 
            return pd.DataFrame(columns=columns)

        gastos_detalhe_bruto = load_df('gastos_detalhe_bruto', gastos_detalhe_bruto.columns)
        ganhos_detalhe_bruto = load_df('ganhos_detalhe_bruto', ganhos_detalhe_bruto.columns)
        poupancas_detalhe = load_df('poupancas_detalhe', poupancas_detalhe.columns)
        
        if 'lista_ativos_acompanhados' in data and isinstance(data['lista_ativos_acompanhados'], list):
            # Limpeza e padronização dos tickers ao carregar
            carregados = []
            for a in data['lista_ativos_acompanhados']:
                if isinstance(a, str) and a.strip():
                    ticker_limpo = a.strip().upper()
                    # Garante o .SA para tickers comuns da B3
                    if not ticker_limpo.endswith(".SA") and len(ticker_limpo) < 6 and any(char.isdigit() for char in ticker_limpo):
                        ticker_limpo = f"{ticker_limpo}.SA"
                    carregados.append(ticker_limpo)
            LISTA_ATIVOS_ACOMPANHADOS = list(set(carregados)) # Remove duplicados
        else:
            LISTA_ATIVOS_ACOMPANHADOS = default_ativos

        recarregar_dados_agregados(is_silent=True)
    except Exception as e:
        messagebox.showerror("Erro de Carregamento", f"Não foi possível carregar os dados locais: {e}")

def salvar_dados_locais():
    global gastos_detalhe_bruto, ganhos_detalhe_bruto, poupancas_detalhe, LISTA_ATIVOS_ACOMPANHADOS
    data = {
        'gastos_detalhe_bruto': gastos_detalhe_bruto.to_dict('records'),
        'ganhos_detalhe_bruto': ganhos_detalhe_bruto.to_dict('records'),
        'poupancas_detalhe': poupancas_detalhe.to_dict('records'),
        'lista_ativos_acompanhados': LISTA_ATIVOS_ACOMPANHADOS
    }
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        messagebox.showerror("Erro de Salvamento", f"Não foi possível salvar os dados locais: {e}")

# ---------- UI update functions (shared) ----------
def atualizar_renda_label():
    global renda_total, total_gastos
    renda_total = ganhos_detalhe_bruto["valor"].sum() if not ganhos_detalhe_bruto.empty else 0.0
    total_gastos = gastos_detalhe_bruto["gasto_total"].sum() if not gastos_detalhe_bruto.empty else 0.0
    
    total_depositado_poupanca = poupancas_df['valor_atingido'].sum() if not poupancas_df.empty else 0.0
    saldo_real = renda_total - total_gastos - total_depositado_poupanca
    
    lbl_renda_total.config(text=f"💰 Renda Total: R$ {renda_total:,.2f}      💸 Saldo Real: R$ {saldo_real:,.2f}")
    if saldo_real < 0:
        lbl_renda_total.configure(foreground="#B00020")
    else:
        lbl_renda_total.configure(foreground="#0B6E4F")
    
    status_var.set(f"Renda: R$ {renda_total:,.2f}  |  Gastos: R$ {total_gastos:,.2f}  |  Poupança/Inv: R$ {total_depositado_poupanca:,.2f}  |  Saldo: R$ {saldo_real:,.2f}")

def recarregar_dados_agregados(is_silent=False):
    global dados, ganhos_df, poupancas_df, renda_total, total_gastos
    
    # Atualiza ganhos agregados
    if not ganhos_detalhe_bruto.empty:
        ganhos_df = ganhos_detalhe_bruto.groupby("fonte", as_index=False)["valor"].sum()
        ganhos_df["fonte_normalizada"] = ganhos_df["fonte"].apply(normalizar_texto)
    else:
        ganhos_df = pd.DataFrame(columns=["fonte_normalizada", "fonte", "valor"])
        
    # Atualiza gastos agregados
    if not gastos_detalhe_bruto.empty:
        dados = gastos_detalhe_bruto.groupby("departamento", as_index=False)["gasto_total"].sum()
        dados["departamento_normalizado"] = dados["departamento"].apply(normalizar_texto)
    else:
        dados = pd.DataFrame(columns=["departamento_normalizada", "departamento", "gasto_total"])

    # Atualiza poupanças agregadas
    if not poupancas_detalhe.empty:
        poupancas_agg = poupancas_detalhe.groupby("meta", as_index=False).agg(
            valor_atingido=('valor_deposito', 'sum'),
            valor_meta_total=('valor_meta_total', 'last') 
        )
        poupancas_agg["meta_normalizada"] = poupancas_agg["meta"].apply(normalizar_texto)
        poupancas_df = poupancas_agg.copy()
    else:
        poupancas_df = pd.DataFrame(columns=["meta", "meta_normalizada", "valor_atingido", "valor_meta_total"])

    atualizar_renda_label()
    atualizar_tabela()
    atualizar_tabela_poupanca() 
    if not is_silent:
        atualizar_graficos()
        salvar_dados_locais() 
        carregar_investimentos() 

def atualizar_tabela():
    tabela.delete(*tabela.get_children())
    
    # 1. Adiciona Ganhos
    for index, row in ganhos_df.iterrows():
        tabela.insert("", "end", iid=row["fonte_normalizada"], values=(
            datetime.now().strftime('%Y-%m-%d'), 
            row["fonte"], 
            "Ganho", 
            f"R$ {row['valor']:,.2f}"
        ), tags=('ganho',))

    # 2. Adiciona Gastos
    for index, row in dados.iterrows():
        tabela.insert("", "end", iid=row["departamento_normalizado"], values=(
            datetime.now().strftime('%Y-%m-%d'), 
            row["departamento"], 
            "Gasto", 
            f"R$ -{row['gasto_total']:,.2f}"
        ), tags=('gasto',))

    # 3. Adiciona Poupanças
    if not poupancas_df.empty:
        for index, row in poupancas_df.iterrows():
            if row['valor_atingido'] > 0:
                tabela.insert("", "end", iid=f"poupanca_{row['meta_normalizada']}", values=(
                    datetime.now().strftime('%Y-%m-%d'), 
                    f"Poupança: {row['meta']}", 
                    "Poupança", 
                    f"R$ -{row['valor_atingido']:,.2f}"
                ), tags=('poupanca',))
                
    # Configurações de tags
    tabela.tag_configure('ganho', foreground='#0B6E4F') 
    tabela.tag_configure('gasto', foreground='#B00020') 
    tabela.tag_configure('poupanca', foreground='#00008B') 

# ---------------------- FUNÇÕES DE POUFANÇA ----------------------
def adicionar_meta_poupanca():
    global poupancas_detalhe
    meta_nome = simpledialog.askstring("Nova Meta de Poupança", "Nome da Meta (Ex: Viagem 2026, Fundo de Emergência):")
    if not meta_nome:
        return
    
    meta_formatada = capitalizar_normalizado(meta_nome)
    meta_normalizada = normalizar_texto(meta_nome)
    
    if meta_normalizada in poupancas_df["meta_normalizada"].values:
        messagebox.showwarning("Aviso", f"A meta '{meta_formatada}' já existe. Por favor, escolha outro nome ou registre um depósito.")
        return
    
    try:
        meta_valor_str = simpledialog.askstring("Valor da Meta", f"Digite o valor total da meta '{meta_formatada}' (R$):")
        if not meta_valor_str:
            return
        meta_valor = float(meta_valor_str.replace(",", "."))
        if meta_valor <= 0:
            messagebox.showwarning("Aviso", "O valor da meta deve ser maior que zero.")
            return

        novo_id_meta = gerar_id_unico()
        
        nova_meta_detalhe = pd.DataFrame({
            "id_meta": [novo_id_meta],
            "id_lancamento": [gerar_id_unico()],
            "data_lancamento": [datetime.now().strftime('%Y-%m-%d')],
            "meta": [meta_formatada],
            "descricao": [f"Meta inicial de R$ {meta_valor:,.2f} - Criada em {datetime.now().strftime('%d/%m/%Y')}"],
            "valor_deposito": [0.0],
            "valor_meta_total": [meta_valor],
            "valor_atingido": [0.0]
        })
        
        poupancas_detalhe = pd.concat([poupancas_detalhe, nova_meta_detalhe], ignore_index=True)
        recarregar_dados_agregados()
        messagebox.showinfo("Sucesso", f"Meta '{meta_formatada}' de R$ {meta_valor:,.2f} adicionada!")

    except ValueError:
        messagebox.showerror("Erro", "Valor inválido. Digite apenas números.")
        
def registrar_deposito_poupanca():
    global poupancas_detalhe, poupancas_df
    
    if poupancas_df.empty:
        messagebox.showwarning("Aviso", "Crie uma meta de poupança primeiro!")
        return
    
    metas = poupancas_df["meta"].tolist()
    
    top = tb.Toplevel(janela)
    top.title("Registrar Depósito")
    top.geometry("350x200")
    
    tk.Label(top, text="Selecione a Meta:", font=("Arial", 10)).pack(pady=(10, 0))
    
    meta_selecionada = tk.StringVar(top)
    meta_selecionada.set(metas[0])
    
    meta_dropdown = ttk.OptionMenu(top, meta_selecionada, meta_selecionada.get(), *metas)
    meta_dropdown.pack(pady=5)

    tk.Label(top, text="Valor do Depósito (R$):", font=("Arial", 10)).pack(pady=(5, 0))
    valor_entry = ttk.Entry(top)
    valor_entry.insert(0, "0.00")
    valor_entry.pack(pady=5)
    
    def confirmar_deposito():
        global poupancas_detalhe 
        
        meta = meta_selecionada.get()
        valor_str = valor_entry.get().replace(",", ".")
        if not meta or not valor_str:
            messagebox.showwarning("Aviso", "Selecione uma meta e digite um valor.")
            return
            
        try:
            valor = float(valor_str)
            if valor <= 0:
                messagebox.showwarning("Aviso", "O valor do depósito deve ser maior que zero.")
                return
            
            meta_info = poupancas_df[poupancas_df['meta'] == meta].iloc[0]
            id_meta = poupancas_detalhe[poupancas_detalhe['meta'] == meta]['id_meta'].iloc[-1]
            valor_meta_total = meta_info['valor_meta_total']
            valor_atingido_atual = meta_info['valor_atingido']

            novo_lancamento = pd.DataFrame({
                "id_meta": [id_meta],
                "id_lancamento": [gerar_id_unico()],
                "data_lancamento": [datetime.now().strftime('%Y-%m-%d')],
                "meta": [meta],
                "descricao": [f"Depósito em {meta} - R$ {valor:,.2f}"],
                "valor_deposito": [valor],
                "valor_meta_total": [valor_meta_total],
                "valor_atingido": [valor_atingido_atual + valor] 
            })
            
            poupancas_detalhe = pd.concat([poupancas_detalhe, novo_lancamento], ignore_index=True)
            recarregar_dados_agregados()
            messagebox.showinfo("Sucesso", f"Depósito de R$ {valor:,.2f} registrado na meta '{meta}'!")
            top.destroy()
            
        except ValueError:
            messagebox.showerror("Erro", "Valor inválido. Digite apenas números.")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao registrar depósito: {e}")

    btn_confirmar = tb.Button(top, text="Registrar", bootstyle="success", command=confirmar_deposito)
    btn_confirmar.pack(pady=10)
    top.wait_window(top)

def atualizar_tabela_poupanca():
    for row in tabela_poupancas.get_children():
        tabela_poupancas.delete(row)
        
    if poupancas_df.empty:
        return
        
    for index, row in poupancas_df.iterrows():
        atingido = row['valor_atingido']
        meta_total = row['valor_meta_total']
        progresso = (atingido / meta_total) * 100 if meta_total > 0 else 0
        
        tag = 'completa' if progresso >= 100 else 'progresso'
        
        tabela_poupancas.insert("", "end", iid=row["meta_normalizada"], values=(
            row["meta"],
            f"R$ {atingido:,.2f}",
            f"R$ {meta_total:,.2f}",
            f"{progresso:,.1f}%"
        ), tags=(tag,))
        
    tabela_poupancas.tag_configure('completa', foreground='green', background='#E6F7E6')
    tabela_poupancas.tag_configure('progresso', foreground='navy', background='#E6F0F7')

# ---------------------- FUNÇÕES DE LANÇAMENTO E IA ----------------------

# Adicione esta função na parte de "FUNÇÕES DE DADOS/AGREGAÇÃO"
def gerar_contexto_financeiro_ia():
    """Gera um resumo dos dados financeiros atuais para o contexto da IA."""
    
    # 1. Resumo da Renda
    contexto = f"CONTEXTO FINANCEIRO DO USUÁRIO:\n"
    contexto += f"- Renda Mensal Base Atual: R$ {renda_total:,.2f}\n"
    
    # 2. Resumo de Gastos por Categoria
    if not dados.empty:
        total_gasto = dados["gasto_total"].sum()
        contexto += f"- Total de Gastos Acumulados: R$ {total_gasto:,.2f}\n"
        
        # Top 5 gastos por categoria
        top_gastos = dados.sort_values(by="gasto_total", ascending=False).head(5)
        contexto += "- Top 5 Gastos por Categoria:\n"
        for index, row in top_gastos.iterrows():
            contexto += f"  - {row['departamento']}: R$ {row['gasto_total']:,.2f}\n"
    
    # 3. Resumo de Ganhos (últimos 3 meses - Exemplo)
    if not ganhos_detalhe_bruto.empty:
        try:
            df_ganhos = ganhos_detalhe_bruto.copy()
            df_ganhos['data_lancamento'] = pd.to_datetime(df_ganhos['data_lancamento'])
            df_ganhos['Mes_Ano'] = df_ganhos['data_lancamento'].dt.to_period('M')
            
            ganhos_recente = df_ganhos.tail(3).groupby('Mes_Ano')['valor'].sum()
            
            contexto += f"- Ganhos Totais Registrados nos Últimos {len(ganhos_recente)} Meses:\n"
            for periodo, valor in ganhos_recente.items():
                 contexto += f"  - {periodo}: R$ {valor:,.2f}\n"
        except Exception:
            pass # Ignora se a coluna de data falhar
            
    # 4. Sugestão de Perfil de Risco (Exemplo Simplificado)
    # Você pode adicionar lógica mais complexa aqui, como:
    # risco = "Alto" if total_gasto / renda_total > 0.8 else "Baixo"
    if 'total_gasto' in locals():
        if total_gasto > renda_total * 0.7:
            contexto += "\nAVISO DE PERFIL: O usuário possui uma alta taxa de comprometimento da renda (Alto Risco).\n"
        else:
            contexto += "\nAVISO DE PERFIL: O usuário possui uma baixa taxa de comprometimento da renda (Baixo Risco).\n"
            
    return contexto

def definir_renda_base():
    global ganhos_detalhe_bruto
    fonte_chave = "salario fixo"
    fonte_formatada = capitalizar_normalizado(fonte_chave)
    try:
        valor_str = simpledialog.askstring("Definir Salário Fixo", "Digite o valor do seu Salário Fixo Mensal (R$):")
        if not valor_str:
            return
        valor = float(valor_str.replace(",", "."))
        if valor < 0:
            messagebox.showwarning("Aviso", "A renda base deve ser um valor não negativo.")
            return
        
        ganhos_detalhe_bruto = ganhos_detalhe_bruto[ganhos_detalhe_bruto["fonte"] != fonte_formatada].copy()
        
        novo_ganho_detalhe = pd.DataFrame({
            "id_unico": [gerar_id_unico()],
            "data_lancamento": [datetime.now().strftime('%Y-%m-%d')],
            "fonte": [fonte_formatada],
            "valor": [valor],
            "descricao_original": [f"Salário Fixo Mensal ({fonte_formatada})"]
        })
        ganhos_detalhe_bruto = pd.concat([ganhos_detalhe_bruto, novo_ganho_detalhe], ignore_index=True)
        recarregar_dados_agregados()
        messagebox.showinfo("Sucesso", f"Salário Fixo definido para R$ {valor:,.2f}")
    except ValueError:
        messagebox.showerror("Erro", "Valor inválido. Digite apenas números.")

def carregar_csv():
    global gastos_detalhe_bruto
    caminho = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
    if caminho:
        try:
            df_temp = pd.read_csv(caminho)
            if "departamento" not in df_temp.columns or "gasto_total" not in df_temp.columns:
                messagebox.showerror("Erro", "O CSV deve conter as colunas 'departamento' e 'gasto_total'.")
                return
            
            df_temp["gasto_total"] = pd.to_numeric(df_temp["gasto_total"], errors='coerce').fillna(0)

            df_temp["id_unico"] = [gerar_id_unico() for _ in range(len(df_temp))]
            df_temp["data_lancamento"] = datetime.now().strftime('%Y-%m-%d')
            df_temp["descricao_original"] = df_temp["departamento"]
            
            df_temp["departamento"] = df_temp["departamento"].apply(lambda x: capitalizar_normalizado(normalizar_texto(str(x))))
            
            gastos_detalhe_bruto = pd.concat([gastos_detalhe_bruto,
                                              df_temp[['id_unico', 'data_lancamento', 'departamento', 'gasto_total', 'descricao_original']]],
                                              ignore_index=True)
            recarregar_dados_agregados()
            messagebox.showinfo("Sucesso", "CSV de Gastos carregado e dados normalizados/agregados!")
        except Exception as e:
            messagebox.showerror("Erro de Leitura", f"Não foi possível ler o arquivo CSV.\nErro: {e}")

def adicionar_ganho_ia_natural():
    global ganhos_detalhe_bruto
    if not client:
        messagebox.showwarning("Aviso", "Cliente Gemini não inicializado. Verifique sua chave API.")
        return
        
    texto = simpledialog.askstring("Adicionar Ganho IA", "Digite o ganho em linguagem natural:\nEx: 'Recebi 500 de freelance'")
    if not texto:
        return
    try:
        prompt = f"""
        Interprete a seguinte frase de ganho (receita) e extraia a FONTE (ex: Salário, Freelance, Bônus) e o VALOR.
        Responda o nome da fonte exatamente como foi dito na frase.
        Responda apenas em CSV no formato: fonte,valor
        Frase: {texto}
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"temperature": 0}
        )
        resultado = response.text.strip()
        resultado = re.sub(r"^`*csv\n|`*$", "", resultado, flags=re.MULTILINE).strip()
        resultado = re.sub(r"\s+", "", resultado)
        partes = resultado.split(",")
        
        if len(partes) != 2:
            raise ValueError("Formato de resposta inesperado da IA.")
            
        fonte_bruta, valor_str = partes
        valor = float(valor_str)
        fonte_normalizada = normalizar_texto(fonte_bruta)
        
        if fonte_normalizada in RENDAS_DEFINITIVAS:
            messagebox.showwarning("Aviso", "Use o botão 'Definir Renda Base' para configurar seu salário fixo, ou descreva outra fonte de renda (Ex: 'Freelance').")
            return
            
        fonte_formatada = capitalizar_normalizado(fonte_normalizada)
        novo_ganho_detalhe = pd.DataFrame({
            "id_unico": [gerar_id_unico()],
            "data_lancamento": [datetime.now().strftime('%Y-%m-%d')],
            "fonte": [fonte_formatada],
            "valor": [valor],
            "descricao_original": [texto]
        })
        ganhos_detalhe_bruto = pd.concat([ganhos_detalhe_bruto, novo_ganho_detalhe], ignore_index=True)
        recarregar_dados_agregados()
        messagebox.showinfo("Sucesso", f"Ganho de {fonte_formatada} adicionado: R$ {valor:,.2f}")
    except Exception as e:
        messagebox.showerror("Erro", f"Não foi possível interpretar a frase ou processar.\nErro: {e}\nResultado da IA: {resultado if 'resultado' in locals() else 'N/A'}")

def adicionar_gasto_ia_natural():
    global gastos_detalhe_bruto
    if not client:
        messagebox.showwarning("Aviso", "Cliente Gemini não inicializado. Verifique sua chave API.")
        return
        
    texto = simpledialog.askstring("Adicionar Gasto IA", "Digite o gasto em linguagem natural:\nEx: 'Adicione 200 no lazer'")
    if not texto:
        return
    try:
        prompt = f"""
        Interprete a seguinte frase de gasto e extraia DEPARTAMENTO e VALOR. 
        Responda o nome do departamento exatamente como foi dito na frase.
        Responda apenas em CSV no formato: departamento,valor
        Frase: {texto}
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"temperature": 0}
        )
        resultado = response.text.strip()
        resultado = re.sub(r"^`*csv\n|`*$", "", resultado, flags=re.MULTILINE).strip()
        resultado = re.sub(r"\s+", "", resultado)
        partes = resultado.split(",")
        
        if len(partes) != 2:
            raise ValueError("Formato de resposta inesperado da IA.")
            
        dept_bruto, valor_str = partes
        valor = float(valor_str)
        dept_normalizado = normalizar_texto(dept_bruto)
        dept_formatado = capitalizar_normalizado(dept_normalizado)
        novo_gasto_detalhe = pd.DataFrame({
            "id_unico": [gerar_id_unico()],
            "data_lancamento": [datetime.now().strftime('%Y-%m-%d')],
            "departamento": [dept_formatado],
            "gasto_total": [valor],
            "descricao_original": [texto]
        })
        gastos_detalhe_bruto = pd.concat([gastos_detalhe_bruto, novo_gasto_detalhe], ignore_index=True)
        recarregar_dados_agregados()
        messagebox.showinfo("Sucesso", f"Gasto adicionado a {dept_formatado}: R$ {valor:,.2f}")
    except Exception as e:
        messagebox.showerror("Erro", f"Não foi possível interpretar a frase ou processar.\nErro: {e}\nResultado da IA: {resultado if 'resultado' in locals() else 'N/A'}")

def deletar_lancamento_selecionado():
    global gastos_detalhe_bruto, ganhos_detalhe_bruto, poupancas_detalhe
    
    selecionado = tabela.focus()
    if not selecionado:
        messagebox.showwarning("Aviso", "Selecione um item da tabela para deletar.")
        return
        
    # CORREÇÃO: Removida a linha que causava o TclError, 'selecionado' já é o iid
    # iid_selecionado = tabela.item(selecionado, 'iid') 
    
    valores = tabela.item(selecionado, 'values')
    
    if not valores or len(valores) < 3:
        messagebox.showwarning("Aviso", "Item inválido selecionado.")
        return

    categoria = valores[1]
    tipo = valores[2]
    
    confirmar = messagebox.askyesno("Confirmar Exclusão", f"Tem certeza que deseja deletar TODAS as entradas da categoria '{categoria}' ({tipo})? Isso é IRREVERSÍVEL.")

    if confirmar:
        if tipo == "Ganho":
            ganhos_detalhe_bruto = ganhos_detalhe_bruto[ganhos_detalhe_bruto['fonte'] != categoria].copy()
        elif tipo == "Gasto":
            gastos_detalhe_bruto = gastos_detalhe_bruto[gastos_detalhe_bruto['departamento'] != categoria].copy()
        elif tipo == "Poupança":
            nome_meta = categoria.replace("Poupança: ", "")
            poupancas_detalhe = poupancas_detalhe[poupancas_detalhe['meta'] != nome_meta].copy()
        
        recarregar_dados_agregados()
        messagebox.showinfo("Sucesso", f"Todas as entradas de '{categoria}' foram deletadas.")

def gerar_relatorio_ia():
    global renda_total
    if (gastos_detalhe_bruto.empty and ganhos_detalhe_bruto.empty and poupancas_df.empty) or not client:
        if not client:
            messagebox.showwarning("Aviso", "Cliente Gemini não inicializado. Verifique sua chave API.")
        else:
            messagebox.showwarning("Aviso", "Adicione ganhos e gastos primeiro para gerar o relatório!")
        return
        
    resumo_gastos = dados.sort_values(by="gasto_total", ascending=False)
    gasto_total = resumo_gastos["gasto_total"].sum()
    resumo_gastos_texto = "\n".join([f"- {row['departamento']}: R$ {row['gasto_total']:.2f}" for index, row in resumo_gastos.iterrows()])
    
    resumo_ganhos = ganhos_df.sort_values(by="valor", ascending=False)
    renda_total = resumo_ganhos["valor"].sum()
    resumo_ganhos_texto = "\n".join([f"- {row['fonte']}: R$ {row['valor']:.2f}" for index, row in resumo_ganhos.iterrows()]) if not resumo_ganhos.empty else "Nenhuma fonte de renda foi registrada."
    
    resumo_poupancas_texto = "Nenhuma meta de poupança registrada."
    if not poupancas_df.empty:
        resumo_poupancas_texto = ""
        for index, row in poupancas_df.iterrows():
            progresso = (row['valor_atingido'] / row['valor_meta_total']) * 100 if row['valor_meta_total'] > 0 else 0
            resumo_poupancas_texto += f"- {row['meta']}: R$ {row['valor_atingido']:,.2f} de R$ {row['valor_meta_total']:,.2f} ({progresso:,.1f}%)\n"
            
    prompt = f"""
    Com base na sua situação financeira mensal:
    ---
    ### Renda Mensal Total (R$ {renda_total:,.2f})
    As suas fontes de renda registradas são:
    {resumo_ganhos_texto}
    ---
    ### Gastos Mensais Totais (R$ {gasto_total:,.2f})
    A sua distribuição de gastos é:
    {resumo_gastos_texto}
    ---
    ### Metas de Poupança
    {resumo_poupancas_texto}
    ---
    ## Tarefas de Análise:
    1. Calcule o Saldo (Renda Total - Gastos Totais - Poupança Depositada).
    2. **Analise a sua estrutura de ganhos:** Comente sobre a diversificação e estabilidade da sua principal fonte de renda.
    3. Analise a distribuição dos gastos (em % da Renda Total) e identifique os 3 principais pontos de atenção.
    4. **Analise as poupanças:** Comente sobre o progresso geral e a meta mais próxima de ser atingida.
    5. Crie uma recomendação de ação breve para cada ponto de atenção de gasto E UMA recomendação para a estrutura de ganhos.
    Responda em português, de forma amigável e utilize a formatação de tópicos (bullet points) para clareza.
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"temperature": 0.5}
        )
        texto_limpo = limpar_relatorio(response.text)
        relatorio_window = tb.Toplevel(janela)
        relatorio_window.title("Relatório IA Inteligente de Gastos")
        tb.Label(relatorio_window, text=f"📊 Análise Completa Baseada em Renda, Gastos e Poupanças", font=("Arial", 14, "bold")).pack(padx=10, pady=(10, 5))
        
        text_frame = ttk.Frame(relatorio_window)
        text_frame.pack(padx=10, pady=(0, 10), fill='both', expand=True)
        relatorio_text = tk.Text(text_frame, wrap="word", font=("Arial", 11), padx=10, pady=10, height=20, width=80)
        scroll_y = ttk.Scrollbar(text_frame, orient="vertical", command=relatorio_text.yview)
        relatorio_text.configure(yscrollcommand=scroll_y.set)
        
        scroll_y.pack(side=tk.RIGHT, fill="y")
        relatorio_text.pack(side=tk.LEFT, fill="both", expand=True)
        
        relatorio_text.insert(tk.END, texto_limpo)
        relatorio_text.config(state=tk.DISABLED)
        
    except Exception as e:
        messagebox.showerror("Erro IA", f"Não foi possível gerar o relatório da IA.\nErro: {e}")

def exportar_para_xls():
    global renda_total, total_gastos, poupancas_df
    if gastos_detalhe_bruto.empty and ganhos_detalhe_bruto.empty and poupancas_detalhe.empty:
        messagebox.showwarning("Aviso", "Não há dados para exportar.")
        return
    caminho = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], title="Salvar Dados Financeiros como Excel")
    if not caminho:
        return
    try:
        gastos_detalhe_export = gastos_detalhe_bruto.rename(columns={'departamento': 'Categoria', 'gasto_total': 'Valor', 'data_lancamento': 'Data'})
        gastos_detalhe_export['Tipo'] = 'Gasto'
        gastos_detalhe_export['Valor'] = -gastos_detalhe_export['Valor']
        
        ganhos_detalhe_export = ganhos_detalhe_bruto.rename(columns={'fonte': 'Categoria', 'valor': 'Valor', 'data_lancamento': 'Data'})
        ganhos_detalhe_export['Tipo'] = 'Ganho'
        
        df_detalhe_completo = pd.concat([
            ganhos_detalhe_export[['Data', 'Tipo', 'Categoria', 'Valor', 'descricao_original']],
            gastos_detalhe_export[['Data', 'Tipo', 'Categoria', 'Valor', 'descricao_original']]
        ], ignore_index=True)
        df_detalhe_completo = df_detalhe_completo.fillna('N/A').sort_values(by=['Data', 'Tipo'], ascending=[True, False])

        if not poupancas_detalhe.empty:
            df_poupancas_export = poupancas_detalhe.rename(columns={
                'meta': 'Meta',
                'descricao': 'Descrição',
                'valor_deposito': 'Depósito',
                'valor_meta_total': 'Meta Total',
                'data_lancamento': 'Data'
            })
            df_poupancas_export = df_poupancas_export[['Data', 'Meta', 'Descrição', 'Depósito', 'Meta Total']].fillna('N/A')
        else:
            df_poupancas_export = pd.DataFrame(columns=['Data', 'Meta', 'Descrição', 'Depósito', 'Meta Total'])
        
        total_depositado_poupanca = poupancas_df['valor_atingido'].sum() if not poupancas_df.empty else 0.0
        saldo_real = renda_total - total_gastos - total_depositado_poupanca
        df_totais = pd.DataFrame({
            "Métrica": ["Renda Total", "Gastos Totais", "Poupança/Investimento", "Saldo (Real)"],
            "Valor": [renda_total, total_gastos, total_depositado_poupanca, saldo_real]
        })
        
        df_resumo_categorias = pd.concat([
            ganhos_df.rename(columns={'fonte': 'Categoria', 'valor': 'Valor'}).assign(Tipo='Ganho')[['Tipo', 'Categoria', 'Valor']],
            dados.rename(columns={'departamento': 'Categoria', 'gasto_total': 'Valor'}).assign(Tipo='Gasto')[['Tipo', 'Categoria', 'Valor']]
        ], ignore_index=True).sort_values(by=['Tipo', 'Valor'], ascending=[False, False])
        
        df_resumo_poupancas = poupancas_df.rename(columns={
            'meta': 'Meta',
            'valor_atingido': 'Atingido',
            'valor_meta_total': 'Meta Total'
        })
        if not df_resumo_poupancas.empty:
            df_resumo_poupancas['Progresso (%)'] = (df_resumo_poupancas['Atingido'] / df_resumo_poupancas['Meta Total']) * 100
            df_resumo_poupancas = df_resumo_poupancas[['Meta', 'Atingido', 'Meta Total', 'Progresso (%)']].sort_values(by='Atingido', ascending=False)
        
        with pd.ExcelWriter(caminho, engine='xlsxwriter') as writer:
            workbook = writer.book
            money_fmt = workbook.add_format({'num_format': 'R$ #,##0.00', 'font_size': 10})
            perc_fmt = workbook.add_format({'num_format': '0.0%', 'font_size': 10})
            
            def set_column_format(worksheet, cols_width, cols_money=[], cols_perc=[]):
                for col, width in cols_width.items():
                    worksheet.set_column(col, width)
                for col in cols_money:
                    worksheet.set_column(col, 15, money_fmt)
                for col in cols_perc:
                    worksheet.set_column(col, 15, perc_fmt)
            
            df_detalhe_completo.to_excel(writer, sheet_name='Detalhe_Geral', index=False, freeze_panes=(1, 0))
            set_column_format(writer.sheets['Detalhe_Geral'], 
                              {'A:A': 15, 'B:C': 15, 'E:E': 40}, 
                              cols_money=['D:D'])

            df_poupancas_export.to_excel(writer, sheet_name='Detalhe_Poupancas', index=False, freeze_panes=(1, 0))
            set_column_format(writer.sheets['Detalhe_Poupancas'], 
                              {'A:A': 15, 'B:B': 30, 'C:C': 40}, 
                              cols_money=['D:E'])
            
            df_resumo_categorias.to_excel(writer, sheet_name='Resumo_Categorias', index=False)
            set_column_format(writer.sheets['Resumo_Categorias'], 
                              {'A:B': 15}, 
                              cols_money=['C:C'])
            
            df_resumo_poupancas.to_excel(writer, sheet_name='Resumo_Poupancas', index=False)
            if not df_resumo_poupancas.empty:
                set_column_format(writer.sheets['Resumo_Poupancas'], 
                                  {'A:A': 25}, 
                                  cols_money=['B:C'], cols_perc=['D:D'])

            df_totais.to_excel(writer, sheet_name='Resumo_Geral', index=False)
            
        messagebox.showinfo("Exportação", f"Dados exportados com sucesso para {caminho}")

    except Exception as e:
        messagebox.showerror("Erro de Exportação", f"Não foi possível exportar os dados para Excel.\nErro: {e}")

# ---------------------- FUNÇÕES DE GRÁFICOS (DINÂMICO) ----------------------

def atualizar_graficos():
    global fig, canvas

    if fig is None: return

    for ax in fig.get_axes():
        fig.delaxes(ax)
        
    tipo = tipo_grafico_var.get()
    
    if tipo == 'Distribuição de Gastos (Pizza)':
        if dados.empty or dados["gasto_total"].sum() == 0:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "Sem dados de gastos para exibir o gráfico.", ha='center', va='center', fontsize=12)
            ax.axis('off')
        else:
            df_plot = dados[dados["gasto_total"] > 0].sort_values(by="gasto_total", ascending=False).head(10).copy()
            
            if len(dados) > 10:
                outros_gasto = dados["gasto_total"].sum() - df_plot["gasto_total"].sum()
                df_plot = pd.concat([
                    df_plot, 
                    pd.DataFrame([{"departamento": "Outros", "gasto_total": outros_gasto}])
                ], ignore_index=True)
            
            ax = fig.add_subplot(111)
            ax.pie(
                df_plot["gasto_total"], 
                labels=[f"{d} (R$ {g:,.2f})" for d, g in zip(df_plot["departamento"], df_plot["gasto_total"])], 
                autopct='%1.1f%%', 
                startangle=90,
                wedgeprops={'linewidth': 0.5, 'edgecolor': 'white'},
                normalize=True
            )
            ax.axis('equal') 
            ax.set_title("Distribuição de Gastos por Categoria")

    elif tipo == 'Histórico Mensal (Barras)':
        periodo_str = periodo_grafico_var.get()
        periodo = int(periodo_str) if periodo_str.isdigit() else 9999
        
        df_completo = pd.DataFrame(columns=['data_lancamento', 'valor', 'tipo'])

        if not gastos_detalhe_bruto.empty:
            df_gastos = gastos_detalhe_bruto[['data_lancamento', 'gasto_total']].rename(columns={'gasto_total': 'valor'})
            df_gastos['tipo'] = 'Gastos'
            df_completo = pd.concat([df_completo, df_gastos], ignore_index=True)

        if not ganhos_detalhe_bruto.empty:
            df_ganhos = ganhos_detalhe_bruto[['data_lancamento', 'valor']]
            df_ganhos['tipo'] = 'Ganhos'
            df_completo = pd.concat([df_completo, df_ganhos], ignore_index=True)

        if df_completo.empty:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "Sem dados para histórico. Adicione lançamentos.", ha='center', va='center', fontsize=12)
            ax.axis('off')
        else:
            df_completo['data_lancamento'] = pd.to_datetime(df_completo['data_lancamento'])
            df_completo['Mes_Ano'] = df_completo['data_lancamento'].dt.to_period('M')
            
            df_mensal = df_completo.groupby(['Mes_Ano', 'tipo'])['valor'].sum().unstack(fill_value=0)
            
            if periodo != 9999 and len(df_mensal) > periodo:
                df_mensal = df_mensal.tail(periodo)
            
            ax = fig.add_subplot(111)
            df_mensal.plot(
                kind='bar', 
                ax=ax, 
                color={'Ganhos': '#0B6E4F', 'Gastos': '#B00020'},
                alpha=0.8
            )
            
            ax.set_title(f"Ganhos vs. Gastos - Histórico dos Últimos {len(df_mensal)} Meses", fontsize=14)
            ax.set_xlabel("Mês/Ano", fontsize=12)
            ax.set_ylabel("Valor (R$)", fontsize=12)
            ax.tick_params(axis='x', rotation=45)
            ax.grid(axis='y', linestyle='--', alpha=0.7)
            ax.legend(title='Tipo', loc='upper left')

            labels = [str(p) for p in df_mensal.index]
            ax.set_xticklabels(labels, ha='right')

    canvas.draw()
    
    if fig_invest and ax_invest:
        # Apenas garante que o gráfico de investimento não seja redesenhado aqui
        pass

# ---------------------- FUNÇÕES DE INVESTIMENTO (ATUALIZADAS) ----------------------

def simular_sugestoes_investimento():
    """Simula sugestões de investimento baseadas em ativos comuns e um desempenho simulado."""
    global SUGESTOES_INVESTIMENTO
    
    # Simulação de sugestões (exemplo de ativos variados)
    ativos_simulados = [
        {"ticker": "IVVB11", "descricao": "ETF de S&P 500 (Ações Globais)", "risco": "Baixo", "retorno_simulado": 0.08},
        {"ticker": "TESOURO SELIC", "descricao": "Renda Fixa (Segurança)", "risco": "Mínimo", "retorno_simulado": 0.095},
        {"ticker": "FII XPML11", "descricao": "Fundo Imobiliário (Shopping Centers)", "risco": "Médio", "retorno_simulado": 0.007} 
    ]
    
    SUGESTOES_INVESTIMENTO = ativos_simulados
    atualizar_tabela_sugestoes()

def atualizar_tabela_sugestoes():
    """Preenche a tabela de sugestões."""
    for row in tabela_sugestoes.get_children():
        tabela_sugestoes.delete(row)
        
    for item in SUGESTOES_INVESTIMENTO:
        # Formata o retorno para a exibição correta
        if item['risco'] == 'Médio':
            retorno_str = f"{item['retorno_simulado'] * 100:,.2f}%/mês"
        else:
            retorno_str = f"{item['retorno_simulado'] * 100:,.1f}%/ano"
        
        tabela_sugestoes.insert("", "end", values=(
            item["ticker"],
            item["descricao"],
            item["risco"],
            retorno_str
        ), tags=(item["risco"].lower(),))
        
    tabela_sugestoes.tag_configure('baixo', foreground='navy')
    tabela_sugestoes.tag_configure('mínimo', foreground='green')
    tabela_sugestoes.tag_configure('médio', foreground='orange')


def buscar_cotacoes_yfinance(tickers):
    """Busca cotações atuais usando a biblioteca yfinance."""
    resultados = []
    if not tickers:
        return resultados

    try:
        # Adicionado um timeout para evitar que o yfinance trave o UI
        data = yf.download(tickers, period="1d", interval="1d", progress=False, timeout=5)
        
        if data.empty or 'Close' not in data:
            return []

        # Se houver mais de um ticker, a estrutura de data é um multi-index
        if len(tickers) > 1:
            # Pega o último fechamento e abertura disponíveis
            last_close = data['Close'].iloc[-1]
            first_open = data['Open'].iloc[-1] if 'Open' in data else last_close
            
            for ticker in tickers:
                preco_atual = last_close.get(ticker, np.nan)
                preco_abertura = first_open.get(ticker, np.nan)
                
                if pd.isna(preco_atual): continue
                
                if pd.isna(preco_abertura) or preco_abertura == 0:
                    variacao_percentual = 0
                else:
                    variacao_percentual = ((preco_atual - preco_abertura) / preco_abertura) * 100
                
                resultados.append({
                    "Ativo": ticker,
                    "Preco Atual": preco_atual,
                    "Variacao Dia": variacao_percentual
                })
        elif len(tickers) == 1:
            # Se houver apenas um ticker, o acesso é direto
            preco_atual = data['Close'].iloc[-1]
            preco_abertura = data['Open'].iloc[-1] if 'Open' in data else preco_atual
            
            if preco_abertura == 0 or pd.isna(preco_abertura):
                variacao_percentual = 0
            else:
                variacao_percentual = ((preco_atual - preco_abertura) / preco_abertura) * 100
            
            resultados.append({
                "Ativo": tickers[0],
                "Preco Atual": preco_atual,
                "Variacao Dia": variacao_percentual
            })
            
    except Exception as e:
        print(f"Erro ao buscar cotações: {e}")
        return []

    return resultados

def atualizar_tabela_acompanhamento():
    """Preenche a tabela de ativos acompanhados."""
    for row in tabela_acompanhamento.get_children():
        tabela_acompanhamento.delete(row)
        
    cotacoes = buscar_cotacoes_yfinance(LISTA_ATIVOS_ACOMPANHADOS)
    
    if not cotacoes and LISTA_ATIVOS_ACOMPANHADOS:
        tabela_acompanhamento.insert("", "end", values=("N/A", "Falha ao buscar cotações.", "N/A", "🔴"), tags=('erro',))
        tabela_acompanhamento.tag_configure('erro', foreground='red')
        return
    elif not LISTA_ATIVOS_ACOMPANHADOS:
        tabela_acompanhamento.insert("", "end", values=("N/A", "Use a caixa de pesquisa para adicionar ativos.", "N/A", "⚪"), tags=('info',))
        tabela_acompanhamento.tag_configure('info', foreground='gray')
        return
        
    for item in cotacoes:
        variacao = item["Variacao Dia"]
        tag = 'alta' if variacao > 0 else ('baixa' if variacao < 0 else 'estavel')
        
        # O iid é o Ticker COMPLETO (com .SA) para ser usado na deleção e plotagem
        tabela_acompanhamento.insert("", "end", iid=item["Ativo"], values=(
            item["Ativo"].replace(".SA", ""),
            f"R$ {item['Preco Atual']:,.2f}",
            f"{variacao:,.2f}%",
            "🟢" if variacao > 0 else ("🔴" if variacao < 0 else "⚪")
        ), tags=(tag,))
        
    tabela_acompanhamento.tag_configure('alta', foreground='#2E8B57') 
    tabela_acompanhamento.tag_configure('baixa', foreground='#C62828') 
    tabela_acompanhamento.tag_configure('estavel', foreground='#7E7E7E')

def adicionar_ativo():
    global LISTA_ATIVOS_ACOMPANHADOS
    ticker_bruto = entry_ticker.get().strip().upper()
    if not ticker_bruto:
        messagebox.showwarning("Aviso", "Digite um ticker (Ex: PETR4, BBDC4).")
        return
    
    # Lógica de padronização aprimorada
    ticker = ticker_bruto
    if not ticker_bruto.endswith(".SA") and len(ticker_bruto) < 6 and any(char.isdigit() for char in ticker_bruto):
        ticker = f"{ticker_bruto}.SA" # Padroniza para B3

    if ticker in LISTA_ATIVOS_ACOMPANHADOS:
        messagebox.showinfo("Aviso", f"O ativo {ticker_bruto} já está na lista.")
        return

    try:
        # Tenta buscar a info (teste de validade)
        ativo = yf.Ticker(ticker)
        info = ativo.info.get('longName', 'N/A')
        # Pequeno ajuste para garantir que o ticker seja válido
        if info == 'N/A' and not ativo.info.get('regularMarketPrice'): 
             raise ValueError("Dados não encontrados ou ticker inválido.")
            
        LISTA_ATIVOS_ACOMPANHADOS.append(ticker)
        entry_ticker.delete(0, tk.END) 
        messagebox.showinfo("Sucesso", f"Ativo '{ticker.replace('.SA', '')}' adicionado à lista de acompanhamento.")
        
        recarregar_dados_agregados() 
        
    except Exception as e:
        messagebox.showerror("Erro", f"O ticker '{ticker_bruto}' não foi encontrado, a API falhou ou é inválido. Tente novamente ou use o sufixo (.SA para B3).")

def remover_ativo():
    global LISTA_ATIVOS_ACOMPANHADOS
    selecionado = tabela_acompanhamento.focus()
    if not selecionado:
        messagebox.showwarning("Aviso", "Selecione um ativo na tabela de acompanhamento para remover.")
        return
        
    # O iid (selecionado) é o Ticker COMPLETO (Ex: PETR4.SA)
    ticker_completo = selecionado 
    ticker_simples = ticker_completo.replace(".SA", "")
    
    confirmar = messagebox.askyesno("Confirmar Remoção", f"Tem certeza que deseja remover o ativo {ticker_simples} da lista de acompanhamento?")
    
    if confirmar:
        LISTA_ATIVOS_ACOMPANHADOS = [t for t in LISTA_ATIVOS_ACOMPANHADOS if t != ticker_completo]
        recarregar_dados_agregados() 
        limpar_grafico_investimento() 
        messagebox.showinfo("Sucesso", f"Ativo {ticker_simples} removido.")

def plotar_historico_ativo(event=None):
    selecionado = tabela_acompanhamento.focus()
    if not selecionado:
        limpar_grafico_investimento()
        return
        
    # O selecionado aqui é o iid, que é o Ticker COMPLETO (Ex: PETR4.SA)
    ticker = selecionado 
    limpar_grafico_investimento()
    
    try:
        ativo = yf.Ticker(ticker)
        # 6 meses de histórico
        df_historico = ativo.history(period="6mo") 

        if df_historico.empty:
            ax_invest.text(0.5, 0.5, f"Histórico não disponível para {ticker.replace('.SA', '')}", ha='center', va='center', fontsize=12)
        else:
            ax_invest.clear()
            df_historico['Close'].plot(ax=ax_invest, color='royalblue', linewidth=2)
            
            nome = ativo.info.get('longName', ticker.replace(".SA", ""))
            
            ax_invest.set_title(f"Preço de Fechamento (6 Meses) - {nome}", fontsize=12)
            ax_invest.set_ylabel("Preço (R$)", fontsize=10)
            ax_invest.set_xlabel("Data", fontsize=10)
            ax_invest.grid(True, linestyle='--', alpha=0.6)
            ax_invest.tick_params(axis='x', rotation=45)
            
        canvas_invest.draw()
        
    except Exception as e:
        limpar_grafico_investimento(f"Erro ao carregar histórico: {e}")
        
def limpar_grafico_investimento(mensagem="Selecione um ativo para visualizar o histórico."):
    global fig_invest, ax_invest, canvas_invest
    if ax_invest:
        ax_invest.clear()
        ax_invest.text(0.5, 0.5, mensagem, ha='center', va='center', fontsize=12, color='gray')
        ax_invest.axis('off')
        canvas_invest.draw()

def carregar_investimentos():
    simular_sugestoes_investimento() 
    atualizar_tabela_acompanhamento()
    limpar_grafico_investimento()

# ---------------------- CHATBOT DE ECONOMIA ----------------------

# ---------------------- CHATBOT DE ECONOMIA ----------------------

def iniciar_sessao_chatbot():
    """Inicia ou reinicia a sessão de chat do Gemini com System Instruction, INCLUINDO CONTEXTO FINANCEIRO."""
    global chat_session
    if not client:
# ... (código existente) ...
        return
    
    # >>>>>>>>>>>>> ALTERAÇÃO AQUI: GERAR E INSERIR CONTEXTO <<<<<<<<<<<<<
    contexto_financeiro = gerar_contexto_financeiro_ia() # Chama a nova função
    
    # Define a persona do chatbot
    system_instruction = (
        "Você é o 'Smart Budget AI Assistant', um especialista em finanças pessoais, economia e investimentos, com foco no mercado brasileiro. "
        "Seu tom deve ser amigável, educado e informativo. Responda apenas perguntas relacionadas a finanças, economia e investimentos. "
        "Se a pergunta estiver fora de contexto, peça ao usuário para refazer a pergunta focando em tópicos financeiros. "
        "Use negrito (**) e listas para organizar as informações complexas.\n\n"
        
        # INCLUA O CONTEXTO FINANCEIRO NO PROMPT INICIAL DO SISTEMA
        f"{contexto_financeiro}\n" 
        "***USE AS INFORMAÇÕES DE 'CONTEXTO FINANCEIRO DO USUÁRIO' ACIMA PARA PERSONALIZAR E EMBASAR SUAS RESPOSTAS SOBRE ORÇAMENTO E VIABILIDADE DE COMPRAS/PARCELAMENTOS.***"
    )
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    config = types.GenerateContentConfig(
        system_instruction=system_instruction
    )
    
# ... (restante do código da função continua igual) ...
    
    chat_session = client.chats.create(
        model="gemini-2.5-flash", 
        config=config
    )
    
    chat_text.config(state=tk.NORMAL)
    chat_text.delete('1.0', tk.END)
    chat_text.insert(tk.END, "🤖 Smart Budget AI Assistant: Olá! Sou seu assistente de finanças e economia. Pergunte-me sobre inflação, investimentos, dicas de orçamento ou o que desejar!\n\n", "assistent")
    chat_text.tag_config("assistent", foreground="#007BFF", font=("Arial", 10, "bold"))
    chat_text.tag_config("user", foreground="#28A745", font=("Arial", 10, "bold"))
    chat_text.tag_config("erro", foreground="#DC3545", font=("Arial", 10, "bold"))
    chat_text.see(tk.END)
    chat_text.config(state=tk.DISABLED)

def enviar_mensagem_chatbot(event=None):
    """Envia a mensagem do usuário ao Gemini e exibe a resposta."""
    global chat_session
    pergunta = entry_chat_input.get().strip()
    entry_chat_input.delete(0, tk.END)
    
    if not pergunta:
        return
    
    if not client or not chat_session:
        iniciar_sessao_chatbot() # Tenta iniciar se estiver nulo
        if not chat_session:
             return 

    # Exibe a pergunta do usuário
    chat_text.config(state=tk.NORMAL)
    chat_text.insert(tk.END, f"👤 Você: {pergunta}\n", "user")
    chat_text.config(state=tk.DISABLED)
    chat_text.see(tk.END)
    
    # Desabilita o campo enquanto espera a resposta
    entry_chat_input.config(state=tk.DISABLED)
    btn_chat_send.config(state=tk.DISABLED)
    janela.update_idletasks()
    
    try:
        # Chama a API
        response = chat_session.send_message(pergunta)
        
        # Exibe a resposta
        chat_text.config(state=tk.NORMAL)
        chat_text.insert(tk.END, f"🤖 Chatbot: {response.text}\n\n", "assistent")
        chat_text.config(state=tk.DISABLED)
        chat_text.see(tk.END)
        
    except Exception as e:
        chat_text.config(state=tk.NORMAL)
        chat_text.insert(tk.END, f"🤖 Chatbot: Erro ao comunicar com a IA. Tente novamente mais tarde. Detalhe: {e}\n\n", "erro")
        chat_text.config(state=tk.DISABLED)
        chat_text.see(tk.END)
        
    finally:
        # Reabilita o campo
        entry_chat_input.config(state=tk.NORMAL)
        btn_chat_send.config(state=tk.NORMAL)
        entry_chat_input.focus_set()


# ---------------------- UI (ttkbootstrap) ----------------------
janela = tb.Window(themename="flatly")
janela.title("💸 Smart Budget - UX Melhorado")
janela.geometry("1100x700")
janela.minsize(900, 600)

# Top frame and status bar
top_frame = ttk.Frame(janela)
top_frame.pack(side=tk.TOP, fill="x", padx=12, pady=(12, 6))

header_label = ttk.Label(top_frame, text="💸 Smart Budget", font=("Inter", 16, "bold"))
header_label.pack(side=tk.LEFT)

lbl_renda_total = ttk.Label(top_frame, text=f"💰 Renda Total: R$ {renda_total:,.2f}      💸 Saldo Real: R$ 0.00", font=("Inter", 11, "bold"))
lbl_renda_total.pack(side=tk.LEFT, padx=20)

def toggle_theme():
    cur = janela.style.theme_use()
    novo = "darkly" if cur != "darkly" else "flatly"
    janela.style.theme_use(novo)
    btn_toggle_theme.config(text="☀️ Claro" if novo == "darkly" else "🌙 Escuro")
    status_var.set(f"Tema: {novo}")

btn_toggle_theme = tb.Button(top_frame, text="🌙 Escuro", bootstyle="outline-secondary", command=toggle_theme)
btn_toggle_theme.pack(side=tk.RIGHT)

status_var = tk.StringVar(value="Pronto")
status_bar = ttk.Label(janela, textvariable=status_var, relief="sunken", anchor="w")
status_bar.pack(side=tk.BOTTOM, fill="x")

# Notebook (abas)
main_frame = ttk.Frame(janela)
main_frame.pack(expand=1, fill="both", padx=12, pady=8)

notebook = ttk.Notebook(main_frame)
notebook.pack(expand=1, fill="both")

aba_lancamentos = ttk.Frame(notebook)
notebook.add(aba_lancamentos, text="📋 Lançamentos")

aba_poupancas = ttk.Frame(notebook)
notebook.add(aba_poupancas, text="💰 Poupanças")

aba_graficos = ttk.Frame(notebook)
notebook.add(aba_graficos, text="📊 Gráficos")

aba_investimentos = ttk.Frame(notebook)
notebook.add(aba_investimentos, text="📈 Investimentos (Mercado)")

# --- NOVA ABA: CHATBOT ---
aba_chatbot = ttk.Frame(notebook)
notebook.add(aba_chatbot, text="🤖 Assistente IA")

# --- Lançamentos layout ---
actions_frame = ttk.Frame(aba_lancamentos)
actions_frame.pack(fill="x", pady=(8, 6))

btn_definir_renda_base = tb.Button(actions_frame, text="Definir Renda Base", bootstyle="info", command=definir_renda_base)
btn_definir_renda_base.pack(side=tk.LEFT, padx=6)

btn_carregar = tb.Button(actions_frame, text="📂 Carregar CSV (Gastos)", bootstyle="success-outline", command=carregar_csv)
btn_carregar.pack(side=tk.LEFT, padx=6)

btn_adicionar_ganho = tb.Button(actions_frame, text="➕ Adicionar Ganho (IA)", bootstyle="warning-outline", command=adicionar_ganho_ia_natural)
btn_adicionar_ganho.pack(side=tk.LEFT, padx=6)

btn_adicionar_ia = tb.Button(actions_frame, text="➖ Adicionar Gasto (IA)", bootstyle="danger-outline", command=adicionar_gasto_ia_natural)
btn_adicionar_ia.pack(side=tk.LEFT, padx=6)

btn_exportar_xls = tb.Button(actions_frame, text="Exportar para Excel (.xlsx)", bootstyle="success", command=exportar_para_xls)
btn_exportar_xls.pack(side=tk.LEFT, padx=6)

btn_relatorio_ia = tb.Button(actions_frame, text="Gerar Relatório IA Inteligente", bootstyle="primary", command=gerar_relatorio_ia) 
btn_relatorio_ia.pack(side=tk.LEFT, padx=6)

tabela_frame = ttk.Frame(aba_lancamentos)
tabela_frame.pack(fill="both", expand=True, padx=6, pady=(6, 12))

tabela = ttk.Treeview(tabela_frame, columns=("Data", "Categoria", "Tipo", "Valor"), show="headings", selectmode="browse")
tabela.heading("Data", text="Data")
tabela.heading("Categoria", text="Categoria")
tabela.heading("Tipo", text="Tipo")
tabela.heading("Valor", text="Valor (R$)")
tabela.column("Data", anchor="center", width=110)
tabela.column("Categoria", anchor="w", width=350)
tabela.column("Tipo", anchor="center", width=120)
tabela.column("Valor", anchor="e", width=140)
tabela.pack(side=tk.LEFT, fill="both", expand=True)

scroll_y = ttk.Scrollbar(tabela_frame, orient="vertical", command=tabela.yview)
tabela.configure(yscrollcommand=scroll_y.set)
scroll_y.pack(side=tk.RIGHT, fill="y")

btn_deletar = tb.Button(aba_lancamentos, text="❌ Deletar Selecionado", bootstyle="danger", command=deletar_lancamento_selecionado)
btn_deletar.pack(side=tk.LEFT, padx=12, pady=(0, 10))

# --- Poupanças layout ---
poupancas_actions_frame = ttk.Frame(aba_poupancas)
poupancas_actions_frame.pack(fill="x", pady=(8, 6), padx=6)

btn_nova_meta = tb.Button(poupancas_actions_frame, text="➕ Nova Meta", bootstyle="primary", command=adicionar_meta_poupanca)
btn_nova_meta.pack(side=tk.LEFT, padx=6)

btn_registrar_deposito = tb.Button(poupancas_actions_frame, text="💰 Registrar Depósito", bootstyle="success", command=registrar_deposito_poupanca)
btn_registrar_deposito.pack(side=tk.LEFT, padx=6)

tabela_poupancas_frame = ttk.Frame(aba_poupancas)
tabela_poupancas_frame.pack(fill="both", expand=True, padx=6, pady=(6, 12))

tabela_poupancas = ttk.Treeview(tabela_poupancas_frame, columns=("Meta", "Atingido", "Meta Total", "Progresso"), show="headings", selectmode="browse")
tabela_poupancas.heading("Meta", text="Meta de Poupança")
tabela_poupancas.heading("Atingido", text="Valor Atingido (R$)")
tabela_poupancas.heading("Meta Total", text="Meta Total (R$)")
tabela_poupancas.heading("Progresso", text="Progresso (%)")

tabela_poupancas.column("Meta", anchor="w", width=300)
tabela_poupancas.column("Atingido", anchor="e", width=180)
tabela_poupancas.column("Meta Total", anchor="e", width=180)
tabela_poupancas.column("Progresso", anchor="e", width=120)

tabela_poupancas.pack(side=tk.LEFT, fill="both", expand=True)

scroll_y_poupanca = ttk.Scrollbar(tabela_poupancas_frame, orient="vertical", command=tabela_poupancas.yview)
tabela_poupancas.configure(yscrollcommand=scroll_y_poupanca.set)
scroll_y_poupanca.pack(side=tk.RIGHT, fill="y")

# --- Gráficos layout ---
graficos_controls_frame = ttk.Frame(aba_graficos)
graficos_controls_frame.pack(fill="x", padx=10, pady=(10, 5))

ttk.Label(graficos_controls_frame, text="Tipo de Gráfico:").pack(side=tk.LEFT, padx=(0, 5))
tipo_grafico_var = tk.StringVar(janela, value='Distribuição de Gastos (Pizza)')
tipo_grafico_options = ['Distribuição de Gastos (Pizza)', 'Histórico Mensal (Barras)']
tipo_grafico_menu = ttk.OptionMenu(graficos_controls_frame, tipo_grafico_var, tipo_grafico_var.get(), *tipo_grafico_options, command=lambda x: atualizar_graficos())
tipo_grafico_menu.pack(side=tk.LEFT, padx=10)

ttk.Label(graficos_controls_frame, text="Período (Meses):").pack(side=tk.LEFT, padx=(20, 5))
periodo_grafico_var = tk.StringVar(janela, value='12')
periodo_grafico_options = ['3', '6', '12', 'Todos']
periodo_grafico_menu = ttk.OptionMenu(graficos_controls_frame, periodo_grafico_var, periodo_grafico_var.get(), *periodo_grafico_options, command=lambda x: atualizar_graficos())
periodo_grafico_menu.pack(side=tk.LEFT, padx=10)

fig = Figure(figsize=(10, 6)) 
canvas_frame = ttk.Frame(aba_graficos)
canvas_frame.pack(fill="both", expand=True, padx=8, pady=8)

canvas = FigureCanvasTkAgg(fig, master=canvas_frame)
canvas.get_tk_widget().pack(fill="both", expand=True)


# ---------------------- LAYOUT DE INVESTIMENTOS ----------------------

# 1. Seção de Sugestões (Topo)
sugestoes_frame = ttk.LabelFrame(aba_investimentos, text="⭐ Melhores Opções de Investimento (Sugestão IA Simulada)", padding=10)
sugestoes_frame.pack(fill="x", padx=10, pady=(10, 5))

tabela_sugestoes = ttk.Treeview(sugestoes_frame, columns=("Ticker", "Descrição", "Risco", "Retorno Estimado"), show="headings", selectmode="browse", height=3)
tabela_sugestoes.heading("Ticker", text="Ticker")
tabela_sugestoes.heading("Descrição", text="Descrição")
tabela_sugestoes.heading("Risco", text="Risco")
tabela_sugestoes.heading("Retorno Estimado", text="Retorno Estimado")

tabela_sugestoes.column("Ticker", anchor="center", width=120)
tabela_sugestoes.column("Descrição", anchor="w", width=300)
tabela_sugestoes.column("Risco", anchor="center", width=100)
tabela_sugestoes.column("Retorno Estimado", anchor="e", width=150)

tabela_sugestoes.pack(fill="both", expand=True)


# 2. Seção de Pesquisa e Acompanhamento
acompanhamento_labelframe = ttk.LabelFrame(aba_investimentos, text="🔍 Pesquisa e Acompanhamento de Ativos", padding=10)
acompanhamento_labelframe.pack(fill="both", expand=True, padx=10, pady=5)

# Frame de Pesquisa e Controles
invest_controls_frame = ttk.Frame(acompanhamento_labelframe)
invest_controls_frame.pack(fill="x", pady=(0, 10))

# Seção de Adicionar Ativo
search_frame = ttk.Frame(invest_controls_frame)
search_frame.pack(side=tk.LEFT, padx=6)

lbl_ticker = ttk.Label(search_frame, text="Adicionar Novo Ticker (Ex: PETR4, BBDC4.SA):")
lbl_ticker.pack(side=tk.LEFT, padx=(0, 5))

entry_ticker = ttk.Entry(search_frame, width=15)
entry_ticker.pack(side=tk.LEFT, padx=5)

btn_adicionar_ativo = tb.Button(search_frame, text="➕ Adicionar Ativo", bootstyle="success", command=adicionar_ativo)
btn_adicionar_ativo.pack(side=tk.LEFT, padx=5)

# Seção de Controles/Atualização
control_frame = ttk.Frame(invest_controls_frame)
control_frame.pack(side=tk.RIGHT, padx=6)

btn_refresh_invest = tb.Button(control_frame, text="🔄 Atualizar Cotações", bootstyle="primary", command=carregar_investimentos)
btn_refresh_invest.pack(side=tk.LEFT, padx=6)

btn_remover_ativo = tb.Button(control_frame, text="❌ Remover Selecionado", bootstyle="danger", command=remover_ativo)
btn_remover_ativo.pack(side=tk.LEFT, padx=6)


# Frame principal para a tabela (esquerda) e gráfico (direita)
invest_main_content = ttk.Frame(acompanhamento_labelframe)
invest_main_content.pack(fill="both", expand=True, pady=(6, 0))

# Sub-Frame Esquerdo (Tabela de Acompanhamento)
tabela_investimentos_frame = ttk.Frame(invest_main_content)
tabela_investimentos_frame.pack(side=tk.LEFT, fill="both", expand=False, padx=(0, 6)) 

tabela_acompanhamento = ttk.Treeview(tabela_investimentos_frame, columns=("Ativo", "Preco Atual", "Variacao Dia", "Tendencia"), show="headings", selectmode="browse")
tabela_acompanhamento.heading("Ativo", text="Ticker")
tabela_acompanhamento.heading("Preco Atual", text="Preço Atual (R$)")
tabela_acompanhamento.heading("Variacao Dia", text="Variação Dia (%)")
tabela_acompanhamento.heading("Tendencia", text="Tendência")

# Ajuste das larguras das colunas para controle visual (ajusta-se ao Frame)
tabela_acompanhamento.column("Ativo", anchor="center", width=100)
tabela_acompanhamento.column("Preco Atual", anchor="e", width=120)
tabela_acompanhamento.column("Variacao Dia", anchor="e", width=120)
tabela_acompanhamento.column("Tendencia", anchor="center", width=80)
# A largura total da tabela agora é 100+120+120+80 = 420px, e o Frame a abraça.

tabela_acompanhamento.pack(side=tk.LEFT, fill="both", expand=True)

scroll_y_invest = ttk.Scrollbar(tabela_investimentos_frame, orient="vertical", command=tabela_acompanhamento.yview)
tabela_acompanhamento.configure(yscrollcommand=scroll_y_invest.set)
scroll_y_invest.pack(side=tk.RIGHT, fill="y")

# Evento de clique na tabela para plotar o histórico
tabela_acompanhamento.bind("<<TreeviewSelect>>", plotar_historico_ativo)


# Sub-Frame Direito (Gráfico)
grafico_invest_frame = ttk.Frame(invest_main_content)
grafico_invest_frame.pack(side=tk.RIGHT, fill="both", expand=True)

fig_invest = Figure(figsize=(5.5, 4.5), dpi=100)
ax_invest = fig_invest.add_subplot(111)
canvas_invest = FigureCanvasTkAgg(fig_invest, master=grafico_invest_frame)
canvas_invest.get_tk_widget().pack(fill="both", expand=True)
limpar_grafico_investimento() 

# ---------------------- LAYOUT DO CHATBOT ----------------------

chat_frame = ttk.Frame(aba_chatbot)
chat_frame.pack(fill="both", expand=True, padx=10, pady=10)

# 1. Área de Exibição do Chat
chat_display_frame = ttk.Frame(chat_frame)
chat_display_frame.pack(fill="both", expand=True, pady=(0, 10))

chat_text = tk.Text(chat_display_frame, wrap="word", font=("Arial", 10), padx=8, pady=8)
chat_text.pack(side=tk.LEFT, fill="both", expand=True)

scroll_y_chat = ttk.Scrollbar(chat_display_frame, orient="vertical", command=chat_text.yview)
chat_text.configure(yscrollcommand=scroll_y_chat.set)
scroll_y_chat.pack(side=tk.RIGHT, fill="y")

# 2. Área de Entrada do Chat
chat_input_frame = ttk.Frame(chat_frame)
chat_input_frame.pack(fill="x")

entry_chat_input = ttk.Entry(chat_input_frame, font=("Arial", 11))
entry_chat_input.pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 5))
entry_chat_input.bind("<Return>", enviar_mensagem_chatbot) # Envia ao pressionar Enter

btn_chat_send = tb.Button(chat_input_frame, text="Enviar (Enter)", bootstyle="primary", command=enviar_mensagem_chatbot)
btn_chat_send.pack(side=tk.RIGHT)

# --- Inicialização ---

# Inicializa o chatbot na primeira vez que a aba for selecionada
def on_tab_change(event):
    if notebook.tab(notebook.select(), "text") == "🤖 Assistente IA":
        if chat_session is None:
            iniciar_sessao_chatbot()
    elif notebook.tab(notebook.select(), "text") == "📊 Gráficos":
         atualizar_graficos() # Garante a atualização dos gráficos ao mudar para a aba
    elif notebook.tab(notebook.select(), "text") == "📈 Investimentos (Mercado)":
         carregar_investimentos() # Garante a atualização dos investimentos

notebook.bind("<<NotebookTabChanged>>", on_tab_change)

try:
    from idlelib.tooltip import Hovertip
    Hovertip(btn_carregar, "Importe um arquivo CSV com colunas 'departamento' e 'gasto_total'")
    Hovertip(btn_adicionar_ativo, "Adiciona um novo ticker para acompanhamento. Ex: PETR4, BBDC4.SA")
    Hovertip(btn_refresh_invest, "Busca cotações em tempo real ou quase real de ativos acompanhados usando yfinance.")
except Exception:
    pass

# Carregar dados e atualizar a interface inicial
carregar_dados_locais() 
carregar_investimentos() 

# Configurar a chamada para salvar os dados ao fechar a janela
janela.protocol("WM_DELETE_WINDOW", lambda: [salvar_dados_locais(), janela.destroy()])

try:
    janela.eval('tk::PlaceWindow . center')
except Exception:
    pass

janela.mainloop()