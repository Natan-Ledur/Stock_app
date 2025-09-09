import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os

st.set_page_config(page_title="Dashboard Consumo e Estoque", layout="wide")
st.title("Dashboard de Consumo, Estoque e Cobertura de Produtos")

# Configuração do caminho dos arquivos
upload_path = 'C:/Users/Fabrica-hoahi/Documents/Projetos_HOAHI_PY/Fios_meias_projeto_so_py/data_base'  # Altere se necessário
if not os.path.exists(upload_path):
    st.error(f"Pasta '{upload_path}' não encontrada.")
    st.stop()
excel_files = [f for f in os.listdir(upload_path) if f.endswith(".xlsx")]
if not excel_files:
    st.warning("Nenhum arquivo Excel encontrado na pasta.")
    st.stop()

# Processamento dos arquivos (adaptado do notebook)
dfs_por_mes = {}
dias_consumo_por_mes = {}
estoque_atual_por_produto = {}
lista_consumo_diario = []
# NOVO: lista para entradas diárias
lista_entrada_diario = []

for file in excel_files:
    file_path = os.path.join(upload_path, file)
    try:
        df = pd.read_excel(file_path, header=None)
        header_row_index = -1
        for r_idx, row in df.iterrows():
            if 'Titulo' in row.values and 'Color' in row.values:
                header_row_index = r_idx
                break
        if header_row_index != -1:
            df_real = pd.read_excel(file_path, header=header_row_index)
            # Estoque atual
            coluna_estoque_nome_real = None
            for col_name in df_real.columns:
                if 'Cantidad de Bolsas TOTAL' in str(col_name):
                    coluna_estoque_nome_real = col_name
                    break
            if coluna_estoque_nome_real:
                df_real[coluna_estoque_nome_real] = pd.to_numeric(df_real[coluna_estoque_nome_real], errors='coerce').fillna(0)
                if 'Produto' not in df_real.columns:
                    df_real['Produto'] = df_real['Titulo'].astype(str) + ' - ' + df_real['Color'].astype(str)
                for _, row in df_real.iterrows():
                    produto = row['Produto']
                    estoque = row[coluna_estoque_nome_real]
                    if pd.notna(produto):
                        estoque_atual_por_produto[produto] = estoque
            # Dias de consumo
            try:
                df_consumo_diario = pd.read_excel(file_path, sheet_name='Consumo_Diario')
                if 'Titulo' in df_consumo_diario.columns and 'Color' in df_consumo_diario.columns:
                    colunas_data = [col for col in df_consumo_diario.columns if col not in ['Titulo', 'Color']]
                    df_consumo_diario['Produto'] = df_consumo_diario['Titulo'].astype(str) + ' - ' + df_consumo_diario['Color'].astype(str)
                    contagem_dias = {}
                    for _, row in df_consumo_diario.iterrows():
                        produto = row['Produto']
                        dias_com_consumo = sum(pd.notna(row[col]) and row[col] > 0 for col in colunas_data)
                        contagem_dias[produto] = dias_com_consumo
                    mes_nome = file.split('-')[1] if '-' in file else file.split('.')[0]
                    dias_consumo_por_mes[mes_nome] = contagem_dias
                    # Para dashboard real: formato longo
                    df_long = df_consumo_diario.melt(id_vars=['Produto'], value_vars=colunas_data, var_name='Data', value_name='Consumo')
                    df_long = df_long.dropna(subset=['Consumo'])
                    df_long = df_long[df_long['Consumo'] > 0]
                    lista_consumo_diario.append(df_long)
            except Exception:
                pass
            # NOVO: Entradas diárias
            try:
                df_entrada_diario = pd.read_excel(file_path, sheet_name='Entrada_Diario')
                if 'Titulo' in df_entrada_diario.columns and 'Color' in df_entrada_diario.columns:
                    colunas_data_entrada = [col for col in df_entrada_diario.columns if col not in ['Titulo', 'Color']]
                    df_entrada_diario['Produto'] = df_entrada_diario['Titulo'].astype(str) + ' - ' + df_entrada_diario['Color'].astype(str)
                    df_long_entrada = df_entrada_diario.melt(id_vars=['Produto'], value_vars=colunas_data_entrada, var_name='Data', value_name='Entrada')
                    df_long_entrada = df_long_entrada.dropna(subset=['Entrada'])
                    df_long_entrada = df_long_entrada[df_long_entrada['Entrada'] > 0]
                    lista_entrada_diario.append(df_long_entrada)
            except Exception:
                pass
            # Médias de consumo
            coluna_cantidad_nome_real = None
            for col_name in df_real.columns:
                if 'Cantidad utilizada' in str(col_name):
                    coluna_cantidad_nome_real = col_name
                    break
            if coluna_cantidad_nome_real:
                df_real[coluna_cantidad_nome_real] = pd.to_numeric(df_real[coluna_cantidad_nome_real], errors='coerce')
                if 'Produto' not in df_real.columns:
                    df_real['Produto'] = df_real['Titulo'].astype(str) + ' - ' + df_real['Color'].astype(str)
                medias_por_produto = df_real.groupby('Produto')[coluna_cantidad_nome_real].mean().reset_index()
                mes_nome = file.split('-')[1] if '-' in file else file.split('.')[0]
                medias_por_produto.rename(columns={coluna_cantidad_nome_real: mes_nome}, inplace=True)
                dfs_por_mes[mes_nome] = medias_por_produto
    except Exception:
        pass

# Consolidação dos resultados
def consolidar_medias(dfs_por_mes):
    if not dfs_por_mes:
        return None
    resultado_final = list(dfs_por_mes.values())[0].copy()
    for mes, df in list(dfs_por_mes.items())[1:]:
        resultado_final = pd.merge(resultado_final, df, on='Produto', how='outer')
    resultado_final = resultado_final.fillna(0)
    resultado_final = resultado_final.sort_values('Produto').reset_index(drop=True)
    return resultado_final

def consolidar_dias(dias_consumo_por_mes):
    if not dias_consumo_por_mes:
        return None
    df_dias_consumo = pd.DataFrame(dias_consumo_por_mes).fillna(0)
    df_dias_consumo = df_dias_consumo.reset_index()
    df_dias_consumo.rename(columns={'index': 'Produto'}, inplace=True)
    df_dias_consumo = df_dias_consumo.sort_values('Produto').reset_index(drop=True)
    return df_dias_consumo

resultado_final = consolidar_medias(dfs_por_mes)
df_dias_consumo = consolidar_dias(dias_consumo_por_mes)

# Cálculo de meses de cobertura
if resultado_final is not None and estoque_atual_por_produto:
    colunas_meses = [col for col in resultado_final.columns if col != 'Produto']
    resultado_final['Consumo_Medio_Mensal'] = resultado_final[colunas_meses].mean(axis=1)
    resultado_final['Consumo_Medio_Diario'] = resultado_final['Consumo_Medio_Mensal'] / 30
    resultado_final['Estoque_Atual'] = resultado_final['Produto'].map(estoque_atual_por_produto).fillna(0)
    resultado_final['Meses_Cobertura'] = np.where(
        resultado_final['Consumo_Medio_Diario'] > 0,
        (resultado_final['Estoque_Atual'] / resultado_final['Consumo_Medio_Diario']) / 30,
        np.inf
    )
    resultado_final['Meses_Cobertura'] = resultado_final['Meses_Cobertura'].replace(np.inf, 999)
    resultado_final['Meses_Cobertura'] = resultado_final['Meses_Cobertura'].round(2)
    resultado_final['Consumo_Medio_Mensal'] = resultado_final['Consumo_Medio_Mensal'].round(2)
    resultado_final['Consumo_Medio_Diario'] = resultado_final['Consumo_Medio_Diario'].round(4)

# Dashboard interativo
st.sidebar.header("Filtros")
if resultado_final is not None:
    produtos = resultado_final['Produto'].unique().tolist()
    produto_selecionado = st.sidebar.selectbox("Produto", produtos)
    colunas_meses = [col for col in resultado_final.columns if col not in ['Produto','Estoque_Atual','Consumo_Medio_Mensal','Consumo_Medio_Diario','Meses_Cobertura']]
    mes_selecionado = st.sidebar.selectbox("Mês para Top 10", colunas_meses)
    st.subheader(f"Evolução Mensal do Consumo Médio - {produto_selecionado}")
    linha = resultado_final[resultado_final['Produto']==produto_selecionado][colunas_meses].T.reset_index()
    linha.columns = ['Mês','Consumo Médio']
    fig = px.line(linha, x='Mês', y='Consumo Médio', title=f'Evolução Mensal - {produto_selecionado}', markers=True)
    st.plotly_chart(fig, use_container_width=True)
    st.subheader(f"Top 10 Produtos - Consumo Médio ({mes_selecionado})")
    top10 = resultado_final.sort_values(mes_selecionado, ascending=False).head(10)
    fig2 = px.bar(top10, x='Produto', y=mes_selecionado, title=f'Top 10 Produtos - {mes_selecionado}', text_auto='.2s', color='Produto')
    fig2.update_layout(xaxis_title='Produto', yaxis_title='Consumo Médio', xaxis_tickangle=45)
    st.plotly_chart(fig2, use_container_width=True)
    st.subheader("Tabela de Cobertura de Estoque")
    st.dataframe(resultado_final[['Produto','Estoque_Atual','Consumo_Medio_Mensal','Consumo_Medio_Diario','Meses_Cobertura']])

# Dashboard de consumo diário consolidado
if lista_consumo_diario:
    df_consumo_diario = pd.concat(lista_consumo_diario, ignore_index=True)
    # NOVO: consolidar entradas diárias
    df_entrada_diario = pd.concat(lista_entrada_diario, ignore_index=True) if lista_entrada_diario else None
    # Converter Data para datetime
    meses_es = {'ENERO': '01', 'FEBRERO': '02', 'MARZO': '03', 'ABRIL': '04','MAYO': '05', 'JUNIO': '06', 'JULIO': '07', 'AGOSTO': '08','SEPTIEMBRE': '09', 'OCTUBRE': '10', 'NOVIEMBRE': '11', 'DICIEMBRE': '12'}
    def converter_data(col):
        try:
            partes = str(col).split()
            if len(partes) == 2 and partes[0].upper() in meses_es:
                mes, ano = partes
                return f'{ano}-{meses_es[mes.upper()]}-01'
            else:
                return col
        except:
            return col
    df_consumo_diario['Data'] = df_consumo_diario['Data'].apply(converter_data)
    df_consumo_diario['Data'] = pd.to_datetime(df_consumo_diario['Data'], errors='coerce')
    df_consumo_diario = df_consumo_diario.dropna(subset=['Data'])
    if df_entrada_diario is not None:
        df_entrada_diario['Data'] = df_entrada_diario['Data'].apply(converter_data)
        df_entrada_diario['Data'] = pd.to_datetime(df_entrada_diario['Data'], errors='coerce')
        df_entrada_diario = df_entrada_diario.dropna(subset=['Data'])
    st.subheader("Consumo Diário Consolidado - Gráfico Interativo")
    produtos_disp = sorted(df_consumo_diario['Produto'].unique().tolist())
    produto1 = st.sidebar.selectbox("Produto 1 (Consumo Diário)", produtos_disp, key='prod1')
    produto2 = st.sidebar.selectbox("Produto 2 (Consumo Diário)", ['(Nenhum)'] + produtos_disp, key='prod2')
    data_min = df_consumo_diario['Data'].min().date()
    data_max = df_consumo_diario['Data'].max().date()
    periodo = st.sidebar.slider("Período", min_value=data_min, max_value=data_max, value=(data_min, data_max), format="%Y-%m-%d")
    indicadores = st.sidebar.multiselect("Indicadores", ['Média Móvel 7d', 'Média Móvel 14d', 'Bollinger Bands', 'Média Móvel Personalizada', 'Tendência Linear'], default=['Média Móvel 7d'])
    mm_custom = st.sidebar.slider("MM Personalizada (dias)", min_value=2, max_value=60, value=21)
    so_medias = st.sidebar.checkbox("Exibir apenas médias/tendência", value=False)
    produtos_selecionados = [produto1] if produto2 == '(Nenhum)' or produto2 == produto1 else [produto1, produto2]
    fig3 = go.Figure()
    for prod in produtos_selecionados:
        df_prod = df_consumo_diario[df_consumo_diario['Produto'] == prod].sort_values('Data')
        df_prod = df_prod.set_index('Data').asfreq('D', fill_value=0).reset_index()
        # Ajuste: filtrar usando .dt.date
        mask = (df_prod['Data'].dt.date >= periodo[0]) & (df_prod['Data'].dt.date <= periodo[1])
        df_prod = df_prod.loc[mask]
        if not so_medias:
            fig3.add_trace(go.Scatter(x=df_prod['Data'], y=df_prod['Consumo'], mode='lines+markers', name=f'Consumo Diário - {prod}'))
        if 'Média Móvel 7d' in indicadores:
            df_prod['MM7'] = df_prod['Consumo'].rolling(window=7).mean()
            fig3.add_trace(go.Scatter(x=df_prod['Data'], y=df_prod['MM7'], mode='lines', name=f'MM 7d - {prod}'))
        if 'Média Móvel 14d' in indicadores:
            df_prod['MM14'] = df_prod['Consumo'].rolling(window=14).mean()
            fig3.add_trace(go.Scatter(x=df_prod['Data'], y=df_prod['MM14'], mode='lines', name=f'MM 14d - {prod}'))
        if 'Bollinger Bands' in indicadores:
            mm20 = df_prod['Consumo'].rolling(window=20).mean()
            std20 = df_prod['Consumo'].rolling(window=20).std()
            upper = mm20 + 2*std20
            lower = mm20 - 2*std20
            fig3.add_trace(go.Scatter(x=df_prod['Data'], y=upper, mode='lines', name=f'Bollinger Superior - {prod}', line=dict(dash='dot', color='green')))
            fig3.add_trace(go.Scatter(x=df_prod['Data'], y=lower, mode='lines', name=f'Bollinger Inferior - {prod}', line=dict(dash='dot', color='red')))
        if 'Média Móvel Personalizada' in indicadores and mm_custom > 1:
            df_prod['MM_CUSTOM'] = df_prod['Consumo'].rolling(window=mm_custom).mean()
            fig3.add_trace(go.Scatter(x=df_prod['Data'], y=df_prod['MM_CUSTOM'], mode='lines', name=f'MM {mm_custom}d - {prod}', line=dict(color='orange', dash='dash')))
        if 'Tendência Linear' in indicadores and len(df_prod) > 1:
            x = np.arange(len(df_prod))
            y = df_prod['Consumo'].values
            mask_valid = ~np.isnan(y)
            if mask_valid.sum() > 1:
                coef = np.polyfit(x[mask_valid], y[mask_valid], 1)
                y_trend = coef[0]*x + coef[1]
                fig3.add_trace(go.Scatter(x=df_prod['Data'], y=y_trend, mode='lines', name=f'Tendência Linear - {prod}', line=dict(color='magenta', dash='dot')))
    fig3.update_layout(title='Consumo Diário', xaxis_title='Data', yaxis_title='Consumo', template='plotly_dark', height=500)
    st.plotly_chart(fig3, use_container_width=True)
    # Download CSV
    if st.button('Download CSV dos dados filtrados'):
        dfs = []
        for prod in produtos_selecionados:
            df_prod = df_consumo_diario[df_consumo_diario['Produto'] == prod].sort_values('Data')
            df_prod = df_prod.set_index('Data').asfreq('D', fill_value=0).reset_index()
            mask = (df_prod['Data'] >= periodo[0]) & (df_prod['Data'] <= periodo[1])
            df_prod = df_prod.loc[mask]
            dfs.append(df_prod.assign(Produto=prod))
        df_final = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        if not df_final.empty:
            df_final.to_csv('dados_filtrados_dashboard.csv', index=False, sep=';')
            st.success('Arquivo "dados_filtrados_dashboard.csv" salvo com sucesso!')
        else:
            st.warning('Nenhum dado para exportar.')

    # NOVO: Gráfico de Estoque Diário
    if df_entrada_diario is not None:
        st.subheader("Estoque Diário Acumulado - Gráfico Interativo")
        produtos_disp_entrada = sorted(list(set(df_entrada_diario['Produto'].unique()) | set(df_consumo_diario['Produto'].unique())))
        produto1_estoque = st.sidebar.selectbox("Produto 1 (Estoque Diário)", produtos_disp_entrada, key='prod1_estoque')
        produto2_estoque = st.sidebar.selectbox("Produto 2 (Estoque Diário)", ['(Nenhum)'] + produtos_disp_entrada, key='prod2_estoque')
        produtos_selecionados_estoque = [produto1_estoque] if produto2_estoque == '(Nenhum)' or produto2_estoque == produto1_estoque else [produto1_estoque, produto2_estoque]
        fig4 = go.Figure()
        for prod in produtos_selecionados_estoque:
            # Consumo diário
            df_c = df_consumo_diario[df_consumo_diario['Produto'] == prod][['Data','Consumo']].copy()
            df_c = df_c.groupby('Data').sum().sort_index()
            # Entradas diárias
            df_e = df_entrada_diario[df_entrada_diario['Produto'] == prod][['Data','Entrada']].copy() if prod in df_entrada_diario['Produto'].values else pd.DataFrame(columns=['Data','Entrada'])
            df_e = df_e.groupby('Data').sum().sort_index()
            # Corrigir tipos para comparação
            data_min_dt = pd.to_datetime(data_min)
            data_max_dt = pd.to_datetime(data_max)
            e_min = df_e.index.min() if not df_e.empty else data_min_dt
            e_max = df_e.index.max() if not df_e.empty else data_max_dt
            # Unir datas
            todas_datas = pd.date_range(min(data_min_dt, e_min), max(data_max_dt, e_max))
            df_estoque = pd.DataFrame(index=todas_datas)
            df_estoque['Entrada'] = df_e['Entrada'] if not df_e.empty else 0
            df_estoque['Consumo'] = df_c['Consumo'] if not df_c.empty else 0
            df_estoque['Entrada'] = df_estoque['Entrada'].fillna(0)
            df_estoque['Consumo'] = df_estoque['Consumo'].fillna(0)
            # Estoque inicial: pegar do dicionário estoque_atual_por_produto, se existir, senão 0
            estoque_inicial = estoque_atual_por_produto.get(prod, 0)
            # Calcular estoque acumulado
            df_estoque['Estoque'] = estoque_inicial + df_estoque['Entrada'].cumsum() - df_estoque['Consumo'].cumsum()
            # Filtrar período
            mask = (df_estoque.index.date >= periodo[0]) & (df_estoque.index.date <= periodo[1])
            df_estoque = df_estoque.loc[mask]
            fig4.add_trace(go.Scatter(x=df_estoque.index, y=df_estoque['Estoque'], mode='lines+markers', name=f'Estoque Diário - {prod}'))
        fig4.update_layout(title='Estoque Diário Acumulado', xaxis_title='Data', yaxis_title='Estoque', template='plotly_dark', height=500)
        st.plotly_chart(fig4, use_container_width=True)
