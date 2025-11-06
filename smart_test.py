import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from google import genai
import re
import unicodedata
import numpy as np
import os

# Optional: interactive cursor for matplotlib (install mplcursors if desired)
try:
    import mplcursors
    MPLCURSORS_AVAILABLE = True
except Exception:
    MPLCURSORS_AVAILABLE = False

# ----------------------------------------------------------------------
# ---------- CONFIGURAÇÃO DA API - SUBSTITUA PELA SUA CHAVE REAL ----------
# ----------------------------------------------------------------------
# Lembre-se de instalar o SDK do Google: pip install google-genai
# E certifique-se de ter as bibliotecas auxiliares: pip install pandas matplotlib openpyxl xlsxwriter
GEMINI_API_KEY = "AIzaSyB-DqAdn0St1mW2CpX5mzy5HTUAjvkfXog"
client = genai.Client(api_key=GEMINI_API_KEY)
# ----------------------------------------------------------------------

# ---------- Dados Globais e Estrutura ----------
dados = pd.DataFrame(columns=["departamento_normalizado", "departamento", "gasto_total"])
ganhos_df = pd.DataFrame(columns=["fonte_normalizada", "fonte", "valor"])

gastos_detalhe_bruto = pd.DataFrame(columns=["id_unico", "data_lancamento", "departamento", "gasto_total", "descricao_original"])
ganhos_detalhe_bruto = pd.DataFrame(columns=["id_unico", "data_lancamento", "fonte", "valor", "descricao_original"])

renda_total = 0.0
total_gastos = 0.0
RENDAS_DEFINITIVAS = ["salario fixo"]

fig = None
canvas = None

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

# ---------- UI update functions (shared) ----------
def atualizar_renda_label():
    global renda_total, total_gastos
    renda_total = ganhos_detalhe_bruto["valor"].sum() if not ganhos_detalhe_bruto.empty else 0.0
    total_gastos = gastos_detalhe_bruto["gasto_total"].sum() if not gastos_detalhe_bruto.empty else 0.0
    saldo = renda_total - total_gastos
    cor_saldo = "danger" if saldo < 0 else "success"
    # Atualiza label com cor apropriada usando ttkbootstrap styles
    lbl_renda_total.config(text=f"💰 Renda Total: R$ {renda_total:,.2f}    💸 Saldo: R$ {saldo:,.2f}")
    # Aplicar cor no label -> usando foreground tag via style
    if saldo < 0:
        lbl_renda_total.configure(foreground="#B00020")
    else:
        lbl_renda_total.configure(foreground="#0B6E4F")
    status_var.set(f"Renda: R$ {renda_total:,.2f}  |  Gastos: R$ {total_gastos:,.2f}  |  Saldo: R$ {saldo:,.2f}")

def recarregar_dados_agregados():
    global dados, ganhos_df, renda_total, total_gastos
    # Agrega Ganhos
    if not ganhos_detalhe_bruto.empty:
        ganhos_df = ganhos_detalhe_bruto.groupby("fonte", as_index=False)["valor"].sum()
        ganhos_df["fonte_normalizada"] = ganhos_df["fonte"].apply(normalizar_texto)
    else:
        ganhos_df = pd.DataFrame(columns=["fonte_normalizada", "fonte", "valor"])
    # Agrega Gastos
    if not gastos_detalhe_bruto.empty:
        dados = gastos_detalhe_bruto.groupby("departamento", as_index=False)["gasto_total"].sum()
        dados["departamento_normalizado"] = dados["departamento"].apply(normalizar_texto)
    else:
        dados = pd.DataFrame(columns=["departamento_normalizada", "departamento", "gasto_total"])
    atualizar_renda_label()
    atualizar_tabela()
    atualizar_graficos()

# ---------- Funções do Aplicativo (mantive sua lógica) ----------
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

def carregar_csv():
    global gastos_detalhe_bruto
    caminho = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
    if caminho:
        try:
            df_temp = pd.read_csv(caminho)
            if "departamento" not in df_temp.columns or "gasto_total" not in df_temp.columns:
                messagebox.showerror("Erro", "O CSV deve conter as colunas 'departamento' e 'gasto_total'.")
                return
            df_temp["id_unico"] = [gerar_id_unico() for _ in range(len(df_temp))]
            df_temp["data_lancamento"] = pd.Timestamp.today().strftime('%Y-%m-%d')
            df_temp["descricao_original"] = df_temp["departamento"]
            df_temp["departamento"] = df_temp["departamento"].apply(lambda x: capitalizar_normalizado(normalizar_texto(x)))
            df_temp = df_temp.rename(columns={'gasto_total': 'gasto_total'})
            gastos_detalhe_bruto = pd.concat([gastos_detalhe_bruto,
                                              df_temp[['id_unico', 'data_lancamento', 'departamento', 'gasto_total', 'descricao_original']]],
                                             ignore_index=True)
            recarregar_dados_agregados()
            messagebox.showinfo("Sucesso", "CSV de Gastos carregado e dados normalizados/agregados!")
        except Exception as e:
            messagebox.showerror("Erro de Leitura", f"Não foi possível ler o arquivo CSV.\nErro: {e}")

def adicionar_ganho_ia_natural():
    global ganhos_detalhe_bruto
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
    global gastos_detalhe_bruto
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
    global renda_total
    if gastos_detalhe_bruto.empty and ganhos_detalhe_bruto.empty:
        messagebox.showwarning("Aviso", "Adicione ganhos e gastos primeiro para gerar o relatório!")
        return
    resumo_gastos = dados.sort_values(by="gasto_total", ascending=False)
    gasto_total = resumo_gastos["gasto_total"].sum()
    resumo_gastos_texto = ""
    for index, row in resumo_gastos.iterrows():
        resumo_gastos_texto += f"- {row['departamento']}: R$ {row['gasto_total']:.2f}\n"
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
        relatorio_window = tb.Toplevel(janela)
        relatorio_window.title("Relatório IA Inteligente de Gastos")
        tb.Label(relatorio_window, text=f"📊 Análise Completa Baseada em Renda e Gastos", font=("Arial", 14, "bold")).pack(padx=10, pady=(10, 5))
        relatorio_text = tk.Text(relatorio_window, wrap="word", font=("Arial", 11), padx=10, pady=10, height=20, width=80)
        relatorio_text.insert(tk.END, texto_limpo)
        relatorio_text.config(state=tk.DISABLED)
        relatorio_text.pack(padx=10, pady=(0, 10))
    except Exception as e:
        messagebox.showerror("Erro IA", f"Não foi possível gerar o relatório da IA.\nErro: {e}")

def exportar_para_xls():
    global renda_total, total_gastos, gastos_detalhe_bruto, ganhos_detalhe_bruto, dados, ganhos_df
    if gastos_detalhe_bruto.empty and ganhos_detalhe_bruto.empty:
        messagebox.showwarning("Aviso", "Não há dados para exportar.")
        return
    caminho = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")], title="Salvar Dados Financeiros como Excel")
    if not caminho:
        return
    try:
        gastos_detalhe_export = gastos_detalhe_bruto.rename(columns={'departamento': 'Categoria', 'gasto_total': 'Valor'})
        gastos_detalhe_export['Tipo'] = 'Gasto'
        gastos_detalhe_export['Valor'] = -gastos_detalhe_export['Valor']
        gastos_detalhe_export = gastos_detalhe_export.rename(columns={'descricao_original': 'Descricao_Bruta'})
        ganhos_detalhe_export = ganhos_detalhe_bruto.rename(columns={'fonte': 'Categoria', 'valor': 'Valor'})
        ganhos_detalhe_export['Tipo'] = 'Ganho'
        ganhos_detalhe_export = ganhos_detalhe_export.rename(columns={'descricao_original': 'Descricao_Bruta'})
        df_detalhe_completo = pd.concat([
            ganhos_detalhe_export[['data_lancamento', 'Tipo', 'Categoria', 'Valor', 'Descricao_Bruta']],
            gastos_detalhe_export[['data_lancamento', 'Tipo', 'Categoria', 'Valor', 'Descricao_Bruta']]
        ], ignore_index=True)
        df_detalhe_completo = df_detalhe_completo.fillna('N/A').sort_values(by=['data_lancamento', 'Tipo'], ascending=[True, False])
        if 'id_unico' in df_detalhe_completo.columns:
            df_detalhe_completo = df_detalhe_completo.drop(columns=['id_unico'], errors='ignore')
        df_totais = pd.DataFrame({
            "Métrica": ["Renda Total", "Gastos Totais", "Saldo"],
            "Valor": [renda_total, total_gastos, renda_total - total_gastos]
        })
        df_resumo_categorias = pd.concat([
            ganhos_df.rename(columns={'fonte': 'Categoria', 'valor': 'Valor'}).assign(Tipo='Ganho')[['Tipo', 'Categoria', 'Valor']],
            dados.rename(columns={'departamento': 'Categoria', 'gasto_total': 'Valor'}).assign(Tipo='Gasto')[['Tipo', 'Categoria', 'Valor']]
        ], ignore_index=True).sort_values(by=['Tipo', 'Valor'], ascending=[False, False])
        with pd.ExcelWriter(caminho, engine='xlsxwriter') as writer:
            workbook = writer.book
            money_fmt = workbook.add_format({'num_format': 'R$ #,##0.00', 'font_size': 10})
            df_detalhe_completo.to_excel(writer, sheet_name='Detalhe_Completo', index=False, freeze_panes=(1, 0))
            worksheet_detalhe = writer.sheets['Detalhe_Completo']
            worksheet_detalhe.set_column('E:E', 15, money_fmt)
            worksheet_detalhe.set_column('A:A', 15)
            worksheet_detalhe.set_column('B:D', 15)
            worksheet_detalhe.set_column('F:F', 40)
            df_resumo_categorias.to_excel(writer, sheet_name='Resumo_Categorias', index=False)
            worksheet_resumo = writer.sheets['Resumo_Categorias']
            worksheet_resumo.set_column('C:C', 15, money_fmt)
            worksheet_resumo.set_column('A:B', 15)
            df_totais.to_excel(writer, sheet_name='Resumo_Geral', index=False)
            worksheet_totais = writer.sheets['Resumo_Geral']
            worksheet_totais.set_column('B:B', 15, money_fmt)
            worksheet_totais.set_column('A:A', 15)
        messagebox.showinfo("Sucesso", f"Dados exportados com sucesso para:\n{caminho}")
    except Exception as e:
        messagebox.showerror("Erro de Exportação", f"Não foi possível exportar os dados para Excel.\nErro: {e}")

def atualizar_tabela():
    for row in tabela.get_children():
        tabela.delete(row)
    df_ganhos_exibicao = ganhos_detalhe_bruto.rename(columns={'fonte': 'Categoria', 'valor': 'Valor'})[['Categoria', 'Valor', 'id_unico', 'data_lancamento']]
    df_ganhos_exibicao['Tipo'] = 'Ganho 🟢'
    df_gastos_exibicao = gastos_detalhe_bruto.rename(columns={'departamento': 'Categoria', 'gasto_total': 'Valor'})[['Categoria', 'Valor', 'id_unico', 'data_lancamento']]
    df_gastos_exibicao['Tipo'] = 'Gasto 🔴'
    df_combinado = pd.concat([df_ganhos_exibicao, df_gastos_exibicao], ignore_index=True)
    df_combinado = df_combinado.sort_values(by='data_lancamento', ascending=False)
    for index, row in df_combinado.iterrows():
        tabela.insert("", "end", iid=row["id_unico"], values=(
            row["data_lancamento"],
            row["Categoria"],
            row["Tipo"],
            f"R$ {row['Valor']:.2f}"
        ), tags=(row["Tipo"].replace(' ', '_'),))
    tabela.tag_configure('Ganho_🟢', foreground='green', background='#E6F7E6')
    tabela.tag_configure('Gasto_🔴', foreground='red', background='#F7E6E6')

def deletar_lancamento_selecionado():
    global gastos_detalhe_bruto, ganhos_detalhe_bruto
    selecionado = tabela.focus()
    if not selecionado:
        messagebox.showwarning("Aviso", "Selecione um lançamento na tabela para deletar.")
        return
    id_para_deletar = selecionado
    confirmar = messagebox.askyesno("Confirmar Deleção", "Tem certeza que deseja deletar o lançamento selecionado? Esta ação é irreversível.")
    if confirmar:
        linhas_antes_gastos = len(gastos_detalhe_bruto)
        gastos_detalhe_bruto = gastos_detalhe_bruto[gastos_detalhe_bruto["id_unico"] != id_para_deletar].copy()
        linhas_depois_gastos = len(gastos_detalhe_bruto)
        linhas_antes_ganhos = len(ganhos_detalhe_bruto)
        ganhos_detalhe_bruto = ganhos_detalhe_bruto[ganhos_detalhe_bruto["id_unico"] != id_para_deletar].copy()
        linhas_depois_ganhos = len(ganhos_detalhe_bruto)
        if linhas_antes_gastos > linhas_depois_gastos or linhas_antes_ganhos > linhas_depois_ganhos:
            tabela.delete(selecionado)
            recarregar_dados_agregados()
            messagebox.showinfo("Sucesso", "Lançamento deletado com sucesso.")
        else:
            messagebox.showwarning("Erro", "Lançamento não encontrado nos dados brutos.")

def atualizar_graficos():
    global renda_total, total_gastos, ganhos_df, fig, canvas
    if fig is None or canvas is None:
        return
    fig.clear()
    if dados.empty and ganhos_df.empty:
        ax_msg = fig.add_subplot(111)
        ax_msg.text(0.5, 0.5, "Carregue ou adicione dados para visualizar os gráficos.", ha='center', va='center', fontsize=16)
        ax_msg.axis('off')
        canvas.draw()
        return
    fig.set_size_inches(12, 10)
    fig.subplots_adjust(hspace=0.4, wspace=0.3, top=0.92, bottom=0.08, left=0.08, right=0.92)

    # Gráfico 1: Fluxo de Caixa
    ax1 = fig.add_subplot(221)
    saldo = renda_total - total_gastos
    cores = ["#2E8B57", "#C62828", "#7E7E7E"]
    df_fluxo = pd.DataFrame({
        "Tipo": ["Renda Total", "Gasto Total", "Saldo"],
        "Valor": [renda_total, -total_gastos, saldo]
    })
    if saldo == 0 and len(df_fluxo) == 3:
        df_fluxo = df_fluxo.iloc[:2]
        cores = cores[:2]
    barras = ax1.bar(df_fluxo["Tipo"], df_fluxo["Valor"], color=cores)
    for bar in barras:
        yval = bar.get_height()
        va = 'bottom' if yval >= 0 else 'top'
        y_offset = 5 if yval >= 0 else -15
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + y_offset, f"R$ {abs(yval):,.0f}", ha='center', va=va, color='black' if yval >= 0 else '#C62828', fontsize=9)
    ax1.set_title("1. Fluxo de Caixa (Renda vs. Gastos)", fontsize=12)
    ax1.set_ylabel("Valor (R$)", fontsize=10)
    ax1.tick_params(axis='x', rotation=0, labelsize=9)
    ax1.tick_params(axis='y', labelsize=9)

    # Gráfico 2: Fontes de Renda
    ax2 = fig.add_subplot(222)
    if not ganhos_df.empty and len(ganhos_df) > 0:
        wedges, texts, autotexts = ax2.pie(ganhos_df["valor"], labels=ganhos_df["fonte"], autopct="%1.1f%%", startangle=90, colors=plt.cm.Set2.colors, pctdistance=0.85)
        for autotext in autotexts:
            autotext.set_fontsize(9)
        for text in texts:
            text.set_fontsize(9)
        ax2.set_title("2. Distribuição das Fontes de Renda", fontsize=12)
    else:
        ax2.text(0.5, 0.5, "Sem dados de Renda", ha='center', va='center', fontsize=12)

    # Gráfico 3: Ganhos e Gastos por Categoria
    ax3 = fig.add_subplot(223)
    if not dados.empty or not ganhos_df.empty:
        df_gastos_unificado = dados.rename(columns={'departamento': 'Categoria', 'gasto_total': 'Valor'})
        df_gastos_unificado['Valor'] = -df_gastos_unificado['Valor']
        df_gastos_unificado['Tipo'] = 'Gasto'
        df_ganhos_unificado = ganhos_df.rename(columns={'fonte': 'Categoria', 'valor': 'Valor'})
        df_ganhos_unificado = df_ganhos_unificado[['Categoria', 'Valor']].copy()
        df_ganhos_unificado['Tipo'] = 'Ganho'
        df_combinado = pd.concat([df_ganhos_unificado, df_gastos_unificado[['Categoria', 'Valor', 'Tipo']]], ignore_index=True)
        df_combinado = df_combinado.sort_values(by="Valor", ascending=False)
        cores_map = {'Ganho': '#2E8B57', 'Gasto': '#C62828'}
        cores_list = [cores_map[tipo] for tipo in df_combinado['Tipo']]
        barras = ax3.bar(df_combinado["Categoria"], df_combinado["Valor"], color=cores_list)
        for bar in barras:
            yval = bar.get_height()
            va = 'bottom' if yval >= 0 else 'top'
            y_offset = 5 if yval >= 0 else -15
            ax3.text(bar.get_x() + bar.get_width()/2.0, yval + y_offset, f"R$ {abs(yval):,.0f}", ha='center', va=va, color='black' if yval >= 0 else '#C62828', fontsize=8)
        ax3.set_title("3. Ganhos (Verde) e Gastos (Vermelho) por Categoria", fontsize=12)
        ax3.set_ylabel("Valor (R$)", fontsize=10)
        ax3.set_xlabel("Categoria", fontsize=10)
        ax3.tick_params(axis='x', rotation=70, labelsize=9)
        ax3.tick_params(axis='y', labelsize=9)
        ax3.axhline(0, color='black', linewidth=0.8)
    else:
        ax3.text(0.5, 0.5, "Sem dados de Ganhos/Gastos", ha='center', va='center', fontsize=12)

    # Gráfico 4: Pizza de Gastos
    ax4 = fig.add_subplot(224)
    if not dados.empty:
        df_agregado = dados.sort_values(by="gasto_total", ascending=False)
        wedges, texts, autotexts = ax4.pie(df_agregado["gasto_total"], labels=df_agregado["departamento"], autopct="%1.1f%%", startangle=90, colors=plt.cm.Pastel2.colors, pctdistance=0.85)
        for autotext in autotexts:
            autotext.set_fontsize(9)
        for text in texts:
            text.set_fontsize(9)
        ax4.set_title("4. Distribuição Percentual de Gastos", fontsize=12)
    else:
        ax4.text(0.5, 0.5, "Sem dados de Gastos", ha='center', va='center', fontsize=12)

    canvas.draw()
    # optional interactive cursor
    if MPLCURSORS_AVAILABLE:
        try:
            mplcursors.cursor(hover=True)
        except Exception:
            pass

# ---------------------- UI (ttkbootstrap) ----------------------
# Janela principal com tema inicial claro (flatly)
janela = tb.Window(themename="flatly")
janela.title("💸 Smart Budget - UX Melhorado")
# Tamanho recomendado para UX
janela.geometry("1100x700")
janela.minsize(900, 600)

# Top frame (header)
top_frame = ttk.Frame(janela)
top_frame.pack(side=tk.TOP, fill="x", padx=12, pady=(12, 6))

# Header: title + saldo + theme toggle
header_label = ttk.Label(top_frame, text="💸 Smart Budget", font=("Inter", 16, "bold"))
header_label.pack(side=tk.LEFT)

lbl_renda_total = ttk.Label(top_frame, text=f"💰 Renda Total: R$ {renda_total:,.2f}    💸 Saldo: R$ 0.00", font=("Inter", 11, "bold"))
lbl_renda_total.pack(side=tk.LEFT, padx=20)

def toggle_theme():
    # Toggle between flatly and darkly
    cur = janela.style.theme_use()
    novo = "darkly" if cur != "darkly" else "flatly"
    janela.style.theme_use(novo)
    btn_toggle_theme.config(text="☀️ Claro" if novo == "darkly" else "🌙 Escuro")
    status_var.set(f"Tema: {novo}")

btn_toggle_theme = tb.Button(top_frame, text="🌙 Escuro", bootstyle="outline-secondary", command=toggle_theme)
btn_toggle_theme.pack(side=tk.RIGHT)

# Status bar variable
status_var = tk.StringVar(value="Pronto")
status_bar = ttk.Label(janela, textvariable=status_var, relief="sunken", anchor="w")
status_bar.pack(side=tk.BOTTOM, fill="x")

# Notebook (abas)
main_frame = ttk.Frame(janela)
main_frame.pack(expand=1, fill="both", padx=12, pady=8)

notebook = ttk.Notebook(main_frame)
notebook.pack(expand=1, fill="both")

# Aba 1 - Lançamentos
aba_lancamentos = ttk.Frame(notebook)
notebook.add(aba_lancamentos, text="📋 Lançamentos")

# Aba 2 - Gráficos
aba_graficos = ttk.Frame(notebook)
notebook.add(aba_graficos, text="📊 Gráficos")

# --- Lançamentos layout ---
# Actions row
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

# Tabela + delete button
tabela_frame = ttk.Frame(aba_lancamentos)
tabela_frame.pack(fill="both", expand=True, padx=6, pady=(6, 12))

# Treeview
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

# Scrollbar
scroll_y = ttk.Scrollbar(tabela_frame, orient="vertical", command=tabela.yview)
tabela.configure(yscrollcommand=scroll_y.set)
scroll_y.pack(side=tk.RIGHT, fill="y")

# Delete button
btn_deletar = tb.Button(aba_lancamentos, text="❌ Deletar Selecionado", bootstyle="danger", command=deletar_lancamento_selecionado)
btn_deletar.pack(side=tk.LEFT, padx=12, pady=(0, 10))

# --- Gráficos layout ---
# Create matplotlib figure and canvas inside aba_graficos
fig = plt.Figure(figsize=(12, 8))
canvas = FigureCanvasTkAgg(fig, master=aba_graficos)
canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

# Tooltips (hover) - best-effort, idlelib Hovertip
try:
    from idlelib.tooltip import Hovertip
    Hovertip(btn_carregar, "Importe um arquivo CSV com colunas 'departamento' e 'gasto_total'")
    Hovertip(btn_definir_renda_base, "Defina o salário fixo mensal (apaga entradas anteriores de salário)")
    Hovertip(btn_adicionar_ganho, "Adicione uma fonte de renda em linguagem natural (usando IA)")
    Hovertip(btn_adicionar_ia, "Adicione um gasto em linguagem natural (usando IA)")
    Hovertip(btn_exportar_xls, "Exporte os dados (detalhe e resumo) para Excel")
    Hovertip(btn_relatorio_ia, "Gera um relatório analítico com a ajuda da IA")
    Hovertip(btn_deletar, "Deleta o lançamento selecionado na tabela")
except Exception:
    # ignore if Hovertip not available in environment
    pass

# Inicializa conteúdo e layout
recarregar_dados_agregados()

# Centraliza a janela
try:
    janela.eval('tk::PlaceWindow . center')
except Exception:
    pass

janela.mainloop()
