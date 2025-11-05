import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from google import genai
import re
import unicodedata 
import numpy as np 
import os 

# ----------------------------------------------------------------------
# ---------- CONFIGURAÇÃO DA API - SUBSTITUA PELA SUA CHAVE REAL ----------
# ----------------------------------------------------------------------
#
# Lembre-se de instalar o SDK do Google: pip install google-genai
# E certifique-se de ter as bibliotecas auxiliares: pip install pandas matplotlib openpyxl xlsxwriter
#
GEMINI_API_KEY = "CHAVE DA API" 
#
# ----------------------------------------------------------------------
client = genai.Client(api_key=GEMINI_API_KEY)
# ----------------------------------------------------------------------

# ---------- Dados Globais e Estrutura ----------
# DataFrame 'dados' continua agregando os gastos para o painel de visualização
dados = pd.DataFrame(columns=["departamento_normalizado", "departamento", "gasto_total"])
ganhos_df = pd.DataFrame(columns=["fonte_normalizada", "fonte", "valor"]) 

# DataFrames de DETALHE BRUTO: Armazenam cada lançamento individual (para detalhe no Excel)
gastos_detalhe_bruto = pd.DataFrame(columns=["data_lancamento", "departamento", "gasto_total", "descricao_original"])
ganhos_detalhe_bruto = pd.DataFrame(columns=["data_lancamento", "fonte", "valor", "descricao_original"])

renda_total = 0.0
total_gastos = 0.0 
RENDAS_DEFINITIVAS = ["salario fixo"] 

# Variáveis globais para os gráficos, definidas abaixo na seção de inicialização da GUI
fig = None
canvas = None 

# ---------- Funções de Normalização e Limpeza ----------

def normalizar_texto(texto):
    """
    Normaliza o nome do departamento/fonte: remove acentos, minúsculas, remove espaços extras.
    """
    if not isinstance(texto, str):
        return texto
    
    nfkd_form = unicodedata.normalize('NFKD', texto)
    sem_acento = u"".join([c for c in nfkd_form if not unicodedata.combining(c)])
    
    return sem_acento.strip().lower()

def capitalizar_normalizado(texto_normalizado):
    """
    Retorna o texto capitalizado para exibição.
    """
    if not isinstance(texto_normalizado, str):
        return texto_normalizado
    return texto_normalizado.capitalize()

def limpar_relatorio(texto):
    """
    Remove caracteres de formatação Markdown e excesso de espaçamento
    para exibir um texto mais limpo no widget tk.Text.
    """
    if not isinstance(texto, str):
        return texto
    
    # 1. Remove cabeçalhos Markdown (#, ##, ###) e a linha horizontal (---)
    texto = re.sub(r"^(#+[\s]*|---+)\s*", "", texto, flags=re.MULTILINE)
    
    # 2. Remove caracteres de lista (*) e negrito/itálico (_ ou *)
    texto = re.sub(r"[\*\_]", "", texto) 
    
    # 3. Normaliza espaçamentos e quebras de linha múltiplas
    texto = re.sub(r"\n{3,}", "\n\n", texto) 
    texto = re.sub(r"^[ \t]+|[ \t]+$", "", texto, flags=re.MULTILINE)
    
    return texto.strip()

def recarregar_dados_agregados():
    """
    Recarrega e agrega todos os DataFrames a partir dos DataFrames brutos (detalhados).
    Atualiza a UI (label, tabela, gráficos).
    """
    global dados, ganhos_df, renda_total, total_gastos
    
    # 1. Agrega Ganhos
    if not ganhos_detalhe_bruto.empty:
        ganhos_df = ganhos_detalhe_bruto.groupby("fonte", as_index=False)["valor"].sum()
        ganhos_df.rename(columns={'valor': 'valor'}, inplace=True)
        ganhos_df["fonte_normalizada"] = ganhos_df["fonte"].apply(normalizar_texto)
    else:
        ganhos_df = pd.DataFrame(columns=["fonte_normalizada", "fonte", "valor"])

    # 2. Agrega Gastos
    if not gastos_detalhe_bruto.empty:
        dados = gastos_detalhe_bruto.groupby("departamento", as_index=False)["gasto_total"].sum()
        dados.rename(columns={'departamento': 'departamento', 'gasto_total': 'gasto_total'}, inplace=True)
        dados["departamento_normalizado"] = dados["departamento"].apply(normalizar_texto)
    else:
        dados = pd.DataFrame(columns=["departamento_normalizada", "departamento", "gasto_total"])
        
    # 3. Atualiza Totais e UI
    atualizar_renda_label()
    atualizar_tabela() 
    # Chama atualizar_graficos (seguro, pois 'fig' e 'canvas' já foram definidos)
    atualizar_graficos() 


# ---------- Funções do Aplicativo ----------

def definir_renda_base():
    """Define ou atualiza o Salário Fixo Mensal no detalhe bruto de ganhos."""
    global ganhos_detalhe_bruto
    fonte_chave = "salario fixo"
    fonte_formatada = capitalizar_normalizado(fonte_chave)
    
    try:
        valor_str = simpledialog.askstring("Definir Salário Fixo", 
                                           f"Digite o valor do seu Salário Fixo Mensal (R$):")
        if not valor_str:
            return
            
        valor = float(valor_str.replace(",", ".")) 
        
        if valor < 0:
            messagebox.showwarning("Aviso", "A renda base deve ser um valor não negativo.")
            return

        # Remove entradas anteriores de "salario fixo" para evitar duplicidade
        ganhos_detalhe_bruto = ganhos_detalhe_bruto[ganhos_detalhe_bruto["fonte"] != fonte_formatada].copy()
        
        novo_ganho_detalhe = pd.DataFrame({
            "data_lancamento": [pd.Timestamp.today().strftime('%Y-%m-%d')],
            "fonte": [fonte_formatada],
            "valor": [valor],
            "descricao_original": [f"Salário Fixo Mensal ({fonte_formatada})"]
        })
        
        ganhos_detalhe_bruto = pd.concat([ganhos_detalhe_bruto, novo_ganho_detalhe], ignore_index=True)
        
        recarregar_dados_agregados()
        messagebox.showinfo("Sucesso", f"Salário Fixo definido para R$ {valor:,.2f}")
        
    except ValueError:
        messagebox.showerror("Erro", "Valor inválido. Digite apenas números.")

def atualizar_renda_label():
    """Atualiza o label de Renda Total e Saldo na interface."""
    global renda_total, total_gastos
    
    renda_total = ganhos_detalhe_bruto["valor"].sum() if not ganhos_detalhe_bruto.empty else 0.0
    total_gastos = gastos_detalhe_bruto["gasto_total"].sum() if not gastos_detalhe_bruto.empty else 0.0
    
    saldo = renda_total - total_gastos
    cor_saldo = "red" if saldo < 0 else "green"
    
    lbl_renda_total.config(text=f"💰 Renda Total: R$ {renda_total:,.2f} | "
                                f"💸 Saldo: R$ {saldo:,.2f}", fg=cor_saldo)

def carregar_csv():
    """
    Carrega gastos de um arquivo CSV, normaliza e adiciona ao detalhe bruto.
    O CSV deve ter as colunas 'departamento' e 'gasto_total'.
    """
    global gastos_detalhe_bruto
    caminho = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
    if caminho:
        try:
            df_temp = pd.read_csv(caminho)
            
            if "departamento" not in df_temp.columns or "gasto_total" not in df_temp.columns:
                messagebox.showerror("Erro", "O CSV deve conter as colunas 'departamento' e 'gasto_total'.")
                return

            # Prepara os dados brutos para o DataFrame de detalhe
            df_temp["data_lancamento"] = pd.Timestamp.today().strftime('%Y-%m-%d')
            df_temp["descricao_original"] = df_temp["departamento"]
            df_temp["departamento"] = df_temp["departamento"].apply(lambda x: capitalizar_normalizado(normalizar_texto(x)))
            
            df_temp = df_temp.rename(columns={'gasto_total': 'gasto_total'})
            
            # Adiciona ao DataFrame de detalhe bruto
            gastos_detalhe_bruto = pd.concat([gastos_detalhe_bruto, 
                                              df_temp[['data_lancamento', 'departamento', 'gasto_total', 'descricao_original']]], 
                                              ignore_index=True)
            
            recarregar_dados_agregados() 
            messagebox.showinfo("Sucesso", "CSV de Gastos carregado e dados normalizados/agregados!")
            
        except Exception as e:
            messagebox.showerror("Erro de Leitura", f"Não foi possível ler o arquivo CSV.\nErro: {e}")

def adicionar_ganho_ia_natural():
    """Solicita uma frase de ganho e usa IA para extrair a fonte e o valor."""
    global ganhos_detalhe_bruto
    
    texto = simpledialog.askstring("Adicionar Ganho IA", 
                                   "Digite o ganho em linguagem natural:\nEx: 'Recebi 500 de freelance'")
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
            "data_lancamento": [pd.Timestamp.today().strftime('%Y-%m-%d')],
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
    """Solicita uma frase de gasto e usa IA para extrair o departamento e o valor."""
    global gastos_detalhe_bruto
    
    texto = simpledialog.askstring("Adicionar Gasto IA", 
                                   "Digite o gasto em linguagem natural:\nEx: 'Adicione 200 no lazer'")
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
        
        # 🐛 CORREÇÃO APLICADA AQUI: Mudança de 'dept_bruta' para 'dept_bruto'
        dept_normalizado = normalizar_texto(dept_bruto)
        dept_formatado = capitalizar_normalizado(dept_normalizado)
        
        novo_gasto_detalhe = pd.DataFrame({
            "data_lancamento": [pd.Timestamp.today().strftime('%Y-%m-%d')],
            "departamento": [dept_formatado],
            "gasto_total": [valor],
            "descricao_original": [texto] 
        })
        
        gastos_detalhe_bruto = pd.concat([gastos_detalhe_bruto, novo_gasto_detalhe], ignore_index=True)
        
        recarregar_dados_agregados()
        messagebox.showinfo("Sucesso", f"Gasto adicionado a {dept_formatado}: R$ {valor:,.2f}")
        
    except Exception as e:
        messagebox.showerror("Erro", f"Não foi possível interpretar a frase ou processar.\nErro: {e}\nResultado da IA: {resultado if 'resultado' in locals() else 'N/A'}")

def gerar_relatorio_ia():
    """Gera um relatório financeiro inteligente usando a IA Gemini."""
    global renda_total 
    
    if gastos_detalhe_bruto.empty and ganhos_detalhe_bruto.empty:
        messagebox.showwarning("Aviso", "Adicione ganhos e gastos primeiro para gerar o relatório!")
        return
        
    # Prepara dados de GASTOS (usa o DataFrame agregado 'dados')
    resumo_gastos = dados.sort_values(by="gasto_total", ascending=False)
    gasto_total = resumo_gastos["gasto_total"].sum()
    
    resumo_gastos_texto = ""
    for index, row in resumo_gastos.iterrows():
        resumo_gastos_texto += f"- {row['departamento']}: R$ {row['gasto_total']:.2f}\n"

    # Prepara dados de GANHOS (usa o DataFrame agregado 'ganhos_df')
    resumo_ganhos = ganhos_df.sort_values(by="valor", ascending=False)
    renda_total = resumo_ganhos["valor"].sum()
    
    resumo_ganhos_texto = ""
    if not resumo_ganhos.empty:
        for index, row in resumo_ganhos.iterrows():
            resumo_ganhos_texto += f"- {row['fonte']}: R$ {row['valor']:.2f}\n"
    else:
        resumo_ganhos_texto = "Nenhuma fonte de renda foi registrada."


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

    ## Tarefas de Análise:
    
    1. Calcule o Saldo (Renda Total - Gastos Totais).
    2. **Analise a sua estrutura de ganhos:** Comente sobre a diversificação (se há mais de uma fonte) e a estabilidade da sua principal fonte de renda.
    3. Analise a distribuição dos gastos (em % da Renda Total) e identifique os 3 principais pontos de atenção (onde o gasto é muito alto ou representa risco para a saúde financeira).
    4. Crie uma recomendação de ação breve para cada ponto de atenção de gasto E UMA recomendação para a estrutura de ganhos.
    
    Responda em português, de forma amigável e utilize a formatação de tópicos (bullet points) para clareza.
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"temperature": 0.5}
        )
        
        texto_limpo = limpar_relatorio(response.text)
        
        relatorio_window = tk.Toplevel(janela)
        relatorio_window.title("Relatório IA Inteligente de Gastos")
        
        tk.Label(relatorio_window, text=f"📊 Análise Completa Baseada em Renda e Gastos", font=("Arial", 14, "bold")).pack(padx=10, pady=(10, 5))
        
        relatorio_text = tk.Text(relatorio_window, wrap="word", font=("Arial", 11), padx=10, pady=10, height=20, width=80)
        relatorio_text.insert(tk.END, texto_limpo)
        relatorio_text.config(state=tk.DISABLED)
        relatorio_text.pack(padx=10, pady=(0, 10))
        
    except Exception as e:
        messagebox.showerror("Erro IA", f"Não foi possível gerar o relatório da IA.\nErro: {e}")


def exportar_para_xls():
    """
    Exporta o detalhe completo, resumo por categoria e resumo geral
    para abas separadas em um arquivo Excel (.xlsx), com formatação de moeda.
    """
    global renda_total, total_gastos, gastos_detalhe_bruto, ganhos_detalhe_bruto, dados, ganhos_df
    
    if gastos_detalhe_bruto.empty and ganhos_detalhe_bruto.empty:
        messagebox.showwarning("Aviso", "Não há dados para exportar.")
        return

    caminho = filedialog.asksaveasfilename(
        defaultextension=".xlsx",
        filetypes=[("Excel files", "*.xlsx")],
        title="Salvar Dados Financeiros como Excel"
    )
    
    if not caminho:
        return

    try:
        # --- 1. PREPARAÇÃO DO DETALHE COMPLETO ---
        
        # Gastos: Inverte o sinal para representar saída no fluxo de caixa
        gastos_detalhe_export = gastos_detalhe_bruto.rename(columns={'departamento': 'Categoria', 'gasto_total': 'Valor'})
        gastos_detalhe_export['Tipo'] = 'Gasto'
        gastos_detalhe_export['Valor'] = -gastos_detalhe_export['Valor'] # Sinal negativo para gastos
        gastos_detalhe_export = gastos_detalhe_export.rename(columns={'descricao_original': 'Descricao_Bruta'})
        
        # Ganhos: Mantém o sinal positivo
        ganhos_detalhe_export = ganhos_detalhe_bruto.rename(columns={'fonte': 'Categoria', 'valor': 'Valor'})
        ganhos_detalhe_export['Tipo'] = 'Ganho'
        ganhos_detalhe_export = ganhos_detalhe_export.rename(columns={'descricao_original': 'Descricao_Bruta'})
        
        # DataFrame final de detalhe
        df_detalhe_completo = pd.concat([
            ganhos_detalhe_export[['data_lancamento', 'Tipo', 'Categoria', 'Valor', 'Descricao_Bruta']], 
            gastos_detalhe_export[['data_lancamento', 'Tipo', 'Categoria', 'Valor', 'Descricao_Bruta']]
        ], ignore_index=True)
        
        # Preenche vazios com 'N/A' e ordena por Data e Tipo
        df_detalhe_completo = df_detalhe_completo.fillna('N/A').sort_values(by=['data_lancamento', 'Tipo'], ascending=[True, False])

        # --- 2. PREPARAÇÃO DO RESUMO E TOTAIS ---
        df_totais = pd.DataFrame({
            "Métrica": ["Renda Total", "Gastos Totais", "Saldo"],
            "Valor": [renda_total, total_gastos, renda_total - total_gastos]
        })
        
        # Prepara o resumo por categoria
        df_resumo_categorias = pd.concat([
            ganhos_df.rename(columns={'fonte': 'Categoria', 'valor': 'Valor'}).assign(Tipo='Ganho')[['Tipo', 'Categoria', 'Valor']],
            dados.rename(columns={'departamento': 'Categoria', 'gasto_total': 'Valor'}).assign(Tipo='Gasto')[['Tipo', 'Categoria', 'Valor']]
        ], ignore_index=True).sort_values(by=['Tipo', 'Valor'], ascending=[False, False])
        
        
        # --- 3. ESCRITA NO EXCEL E FORMATAÇÃO ---
        with pd.ExcelWriter(caminho, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # Formato de Moeda Brasileira (R$ #.##0,00)
            money_fmt = workbook.add_format({
                'num_format': 'R$ #,##0.00', 
                'font_size': 10 
            })
            
            # --- ABA 1: DETALHE COMPLETO (Gastos e Ganhos Linha a Linha) ---
            df_detalhe_completo.to_excel(writer, sheet_name='Detalhe_Completo', index=False, freeze_panes=(1, 0))
            worksheet_detalhe = writer.sheets['Detalhe_Completo']
            
            # Aplica formatação de moeda na coluna 'Valor' (Coluna E, índice 4)
            worksheet_detalhe.set_column('E:E', 15, money_fmt)
            # Ajusta largura de outras colunas
            worksheet_detalhe.set_column('A:A', 15) # Data
            worksheet_detalhe.set_column('B:D', 15) # Tipo, Categoria
            worksheet_detalhe.set_column('F:F', 40) # Descrição Bruta
            
            
            # --- ABA 2: RESUMO POR CATEGORIA ---
            df_resumo_categorias.to_excel(writer, sheet_name='Resumo_Categorias', index=False)
            worksheet_resumo = writer.sheets['Resumo_Categorias']
            # Aplica formatação de moeda na coluna 'Valor' (Coluna C, índice 2)
            worksheet_resumo.set_column('C:C', 15, money_fmt)
            worksheet_resumo.set_column('A:B', 15)

            # --- ABA 3: RESUMO GERAL ---
            df_totais.to_excel(writer, sheet_name='Resumo_Geral', index=False)
            worksheet_totais = writer.sheets['Resumo_Geral']
            # Aplica formatação de moeda na coluna 'Valor' (Coluna B, índice 1)
            worksheet_totais.set_column('B:B', 15, money_fmt)
            worksheet_totais.set_column('A:A', 15)


        messagebox.showinfo("Sucesso", f"Dados exportados com sucesso para:\n{caminho}")

    except Exception as e:
        messagebox.showerror("Erro de Exportação", f"Não foi possível exportar os dados para Excel.\nErro: {e}")
        
def atualizar_tabela():
    """Combina Ganhos e Gastos em uma única tabela Treeview para exibição."""
    for row in tabela.get_children():
        tabela.delete(row)
    
    # 1. Prepara Ganhos
    df_ganhos_exibicao = ganhos_df.rename(columns={'fonte': 'Categoria', 'valor': 'Valor'})[['Categoria', 'Valor']]
    df_ganhos_exibicao['Tipo'] = 'Ganho 🟢'
    
    # 2. Prepara Gastos
    df_gastos_exibicao = dados.rename(columns={'departamento': 'Categoria', 'gasto_total': 'Valor'})[['Categoria', 'Valor']]
    df_gastos_exibicao['Tipo'] = 'Gasto 🔴'
    
    # 3. Combina e ordena (Ganhos primeiro, depois Gastos)
    df_combinado = pd.concat([df_ganhos_exibicao, df_gastos_exibicao], ignore_index=True)
    
    # Ordena por Tipo e depois por Valor (decrescente)
    df_combinado = df_combinado.sort_values(by=['Tipo', 'Valor'], ascending=[False, False])
    
    for index, row in df_combinado.iterrows():
        tabela.insert("", "end", values=(
            row["Categoria"], 
            row["Tipo"], 
            f"R$ {row['Valor']:.2f}"
        ), tags=(row["Tipo"].replace(' ', '_'),)) # Adiciona tag para cores

    # Configura cores para melhor visualização (opcional)
    tabela.tag_configure('Ganho_🟢', foreground='green')
    tabela.tag_configure('Gasto_🔴', foreground='red')

def atualizar_graficos():
    """Atualiza os 4 subplots de visualização de dados financeiros."""
    global renda_total, total_gastos, ganhos_df, fig, canvas
    
    # Garantia de que fig está definido
    if fig is None or canvas is None:
        return
        
    fig.clear()
    
    if dados.empty and ganhos_df.empty:
        fig.suptitle("Carregue ou adicione dados para visualizar os gráficos.", fontsize=14)
        canvas.draw()
        return

    # --- Ajustes de Espaçamento e Tamanho da Figura ---
    fig.set_size_inches(12, 10) 
    fig.subplots_adjust(hspace=0.4, wspace=0.3, top=0.92, bottom=0.08, left=0.08, right=0.92)

    # --- Gráfico 1: Fluxo de Caixa (Renda vs. Gastos) ---
    ax1 = fig.add_subplot(221)
    saldo = renda_total - total_gastos
    cores = ["green", "red", "gray"]
    
    df_fluxo = pd.DataFrame({
        "Tipo": ["Renda Total", "Gasto Total", "Saldo"],
        "Valor": [renda_total, -total_gastos, saldo] 
    })
    
    # Evita plotar o saldo se for zero e apenas dois itens estão sendo plotados
    if saldo == 0 and len(df_fluxo) == 3:
        df_fluxo = df_fluxo.iloc[:2]
        cores = cores[:2]
        
    barras = ax1.bar(df_fluxo["Tipo"], df_fluxo["Valor"], 
                     color=cores) 
                     
    for bar in barras:
        yval = bar.get_height()
        va = 'bottom' if yval >= 0 else 'top'
        y_offset = 5 if yval >= 0 else -15 
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + y_offset, f"R$ {abs(yval):,.0f}", ha='center', va=va, 
                 color='black' if yval >= 0 else 'red', fontsize=9)

    ax1.set_title("1. Fluxo de Caixa (Renda vs. Gastos)", fontsize=12)
    ax1.set_ylabel("Valor (R$)", fontsize=10)
    ax1.tick_params(axis='x', rotation=0, labelsize=9)
    ax1.tick_params(axis='y', labelsize=9)


    # --- Gráfico 2: Distribuição de Fontes de Renda ---
    ax2 = fig.add_subplot(222)
    if not ganhos_df.empty and len(ganhos_df) > 0:
        wedges, texts, autotexts = ax2.pie(
            ganhos_df["valor"], 
            labels=ganhos_df["fonte"], 
            autopct="%1.1f%%", 
            startangle=90, 
            colors=plt.cm.Set2.colors,
            pctdistance=0.85 
        )
        for autotext in autotexts:
            autotext.set_fontsize(9) 
        for text in texts:
            text.set_fontsize(9) 
        ax2.set_title("2. Distribuição das Fontes de Renda", fontsize=12)
    else:
        ax2.text(0.5, 0.5, "Sem dados de Renda", ha='center', va='center', fontsize=12)

    # --- Gráfico 3: Ganhos e Gastos por Categoria (Unificado) ---
    ax3 = fig.add_subplot(223)
    
    if not dados.empty or not ganhos_df.empty:
        # Prepara Gastos (valores negativos)
        df_gastos_unificado = dados.rename(columns={'departamento': 'Categoria', 'gasto_total': 'Valor'})
        df_gastos_unificado['Valor'] = -df_gastos_unificado['Valor']
        df_gastos_unificado['Tipo'] = 'Gasto'
        
        # Prepara Ganhos (valores positivos)
        df_ganhos_unificado = ganhos_df.rename(columns={'fonte': 'Categoria', 'valor': 'Valor'})
        df_ganhos_unificado = df_ganhos_unificado[['Categoria', 'Valor']].copy()
        df_ganhos_unificado['Tipo'] = 'Ganho'
        
        df_combinado = pd.concat([df_ganhos_unificado, df_gastos_unificado[['Categoria', 'Valor', 'Tipo']]], ignore_index=True)
        
        df_combinado = df_combinado.sort_values(by="Valor", ascending=False)
        
        cores_map = {'Ganho': 'green', 'Gasto': 'red'}
        cores = [cores_map[tipo] for tipo in df_combinado['Tipo']]
        
        barras = ax3.bar(df_combinado["Categoria"], df_combinado["Valor"], color=cores)
        
        for bar in barras:
            yval = bar.get_height()
            va = 'bottom' if yval >= 0 else 'top'
            y_offset = 5 if yval >= 0 else -15 
            ax3.text(bar.get_x() + bar.get_width()/2.0, yval + y_offset, f"R$ {abs(yval):,.0f}", ha='center', va=va, 
                     color='black' if yval >= 0 else 'red', fontsize=8)
        
        ax3.set_title("3. Ganhos (Verde) e Gastos (Vermelho) por Categoria", fontsize=12)
        ax3.set_ylabel("Valor (R$)", fontsize=10)
        ax3.set_xlabel("Categoria", fontsize=10)
        ax3.tick_params(axis='x', rotation=70, labelsize=9) 
        ax3.tick_params(axis='y', labelsize=9)
        ax3.axhline(0, color='black', linewidth=0.8) 
    else:
        ax3.text(0.5, 0.5, "Sem dados de Ganhos/Gastos", ha='center', va='center', fontsize=12)

    # --- Gráfico 4: Distribuição Percentual de Gastos (Pizza) ---
    ax4 = fig.add_subplot(224)
    if not dados.empty:
        df_agregado = dados.sort_values(by="gasto_total", ascending=False)
        wedges, texts, autotexts = ax4.pie(
            df_agregado["gasto_total"], 
            labels=df_agregado["departamento"], 
            autopct="%1.1f%%", 
            startangle=90, 
            colors=plt.cm.Pastel2.colors,
            pctdistance=0.85
        )
        for autotext in autotexts:
            autotext.set_fontsize(9)
        for text in texts:
            text.set_fontsize(9)
        ax4.set_title("4. Distribuição Percentual de Gastos", fontsize=12)
    else:
        ax4.text(0.5, 0.5, "Sem dados de Gastos", ha='center', va='center', fontsize=12)

    canvas.draw()

# ---------- Janela ----------
janela = tk.Tk()
janela.title("💸 Smart Budget Mês Atual com Renda Total")
janela.geometry("1200x850") 

main_frame = tk.Frame(janela)
main_frame.pack(expand=1, fill="both", padx=10, pady=10)

# ---------- Linha da Renda Total e Saldo ----------
renda_frame = tk.Frame(main_frame)
renda_frame.pack(pady=10)

lbl_renda_total = tk.Label(renda_frame, text=f"💰 Renda Total: R$ {renda_total:,.2f} | 💸 Saldo: R$ 0.00", font=("Arial", 12, "bold"))
lbl_renda_total.pack(side=tk.LEFT, padx=10)

btn_definir_renda_base = tk.Button(
    renda_frame, text="Definir Renda Base", command=definir_renda_base,
    bg="#2196F3", fg="white", font=("Arial", 11)
)
btn_definir_renda_base.pack(side=tk.LEFT, padx=5)

# ---------- Botões de Ação ----------
btn_frame = tk.Frame(main_frame)
btn_frame.pack(pady=10)

btn_carregar = tk.Button(
    btn_frame, text="Carregar CSV (Gastos)", command=carregar_csv,
    width=20, bg="#4CAF50", fg="white", font=("Arial", 11)
)
btn_carregar.pack(side=tk.LEFT, padx=5)

btn_adicionar_ganho = tk.Button(
    btn_frame, text="Adicionar Ganho (IA)", command=adicionar_ganho_ia_natural,
    width=20, bg="#FFC107", fg="black", font=("Arial", 11)
)
btn_adicionar_ganho.pack(side=tk.LEFT, padx=5)

btn_adicionar_ia = tk.Button(
    btn_frame, text="Adicionar Gasto (IA)", command=adicionar_gasto_ia_natural,
    width=20, bg="#FF9800", fg="white", font=("Arial", 11)
)
btn_adicionar_ia.pack(side=tk.LEFT, padx=5)

btn_exportar_xls = tk.Button(
    btn_frame, text="Exportar para Excel (.xlsx)", command=exportar_para_xls,
    width=25, bg="#107C10", fg="white", font=("Arial", 11, "bold")
)
btn_exportar_xls.pack(side=tk.LEFT, padx=5)

btn_relatorio_ia = tk.Button(
    btn_frame, text="Gerar Relatório IA Inteligente", command=gerar_relatorio_ia,
    width=28, bg="#9C27B0", fg="white", font=("Arial", 11)
)
btn_relatorio_ia.pack(side=tk.LEFT, padx=5)

# --------------------------------------------------------------------------
# Definição de fig e canvas (essencial para a ordem de inicialização)
# --------------------------------------------------------------------------
fig = plt.Figure(figsize=(12, 10))
canvas = FigureCanvasTkAgg(fig, master=main_frame) 

# ---------- Tabela Unificada de Ganhos e Gastos (Empacotada primeiro)----------
tabela_frame = tk.Frame(main_frame)
tabela_frame.pack(pady=10, fill="x") 

# Configura a nova tabela com as colunas Categoria, Tipo e Valor
tabela = ttk.Treeview(tabela_frame, columns=("Categoria", "Tipo", "Valor"), show="headings")
tabela.heading("Categoria", text="Categoria")
tabela.heading("Tipo", text="Tipo")
tabela.heading("Valor", text="Valor (R$)")

# Ajusta as larguras das colunas
tabela.column("Categoria", anchor="w", width=250)
tabela.column("Tipo", anchor="center", width=120)
tabela.column("Valor", anchor="e", width=150)

tabela.pack(fill="x", expand=True)

# --------------------------------------------------------------------------
# ---------- Gráficos (4 subplots) (Empacotado por último) ---------- 
canvas.get_tk_widget().pack(pady=10, fill="both", expand=True) 

# Inicializa a tabela E OS GRÁFICOS
recarregar_dados_agregados() 

janela.mainloop()
