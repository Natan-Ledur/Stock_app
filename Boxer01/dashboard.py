import streamlit as st
import pandas as pd
import plotly.figure_factory as ff
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os


# Função para carregar dados do main.py e salvar em cache persistente
import pickle
import os

def caminho_cache():
    return os.path.join(os.path.dirname(__file__), "main_cache.pkl")

def salvar_cache_main():
    # Aqui você pode adaptar para salvar os dados que quiser, por exemplo, lendo de arquivos .csv, .sql, etc. dentro da Boxer
    # Exemplo: carregar de arquivos .pkl ou .csv na pasta Boxer
    dados = {}
    # Exemplo de leitura de arquivos pickle (ajuste conforme seus arquivos reais)
    for nome in ["df_estoque", "df_soma_consumo", "pedidos_19_18", "dfs_exclusivos_18", "dfs_01"]:
        caminho = os.path.join(os.path.dirname(__file__), f"{nome}.pkl")
        if os.path.exists(caminho):
            with open(caminho, "rb") as f:
                dados[nome] = pickle.load(f)
        else:
            dados[nome] = None
    with open(caminho_cache(), "wb") as f:
        pickle.dump(dados, f)

def carregar_cache_main():
    if os.path.exists(caminho_cache()):
        with open(caminho_cache(), "rb") as f:
            dados = pickle.load(f)
        return (
            dados["df_estoque"],
            dados["df_soma_consumo"],
            dados["pedidos_19_18"],
            dados["dfs_exclusivos_18"],
            dados["dfs_01"]
        )
    else:
        salvar_cache_main()
        return carregar_cache_main()

def atualizar_cache():
    salvar_cache_main()
    st.success("Dados do main.py atualizados!")

st.sidebar.button("🔄 Atualizar Dados", on_click=atualizar_cache)

# Carrega dados do cache local
df_estoque, df_soma_consumo, pedidos_19_18, dfs_exclusivos_18, dfs_01 = carregar_cache_main()


# Carregar pivots diretamente de arquivos na Boxer, se existirem
def carregar_pivot(nome):
    caminho = os.path.join(os.path.dirname(__file__), f"{nome}.pkl")
    if os.path.exists(caminho):
        with open(caminho, "rb") as f:
            return pickle.load(f)
    return None

pivot_19_18 = carregar_pivot("pivot_19_18")
pivot_exclusivos_18 = carregar_pivot("pivot_exclusivos_18")
pivot_01 = carregar_pivot("pivot_01")

st.set_page_config(page_title="Planejamento de Pedidos e Estoque", layout="wide")

st.title("📊 Dashboard de Planejamento de Pedidos e Estoque")

st.subheader("Selecione os pedidos para planejamento")
incluir_18 = st.checkbox("Mostrar OFs exclusivos do setor 18", value=True)
incluir_01 = st.checkbox("Mostrar OFs do setor 01", value=True)

# Monta lista de pedidos disponíveis
pedidos_disp = pedidos_19_18.copy()
if incluir_18:
    for df in dfs_exclusivos_18.values():
        pedidos_disp = pd.concat([pedidos_disp, df])
if incluir_01:
    for df in dfs_01.values():
        pedidos_disp = pd.concat([pedidos_disp, df])

pedidos_disp = pedidos_disp.drop_duplicates(subset=["fac_pedido"]) # Evita duplicidade
lista_pedidos = pedidos_disp["fac_pedido"].astype(str).tolist()
pedidos_selecionados = st.multiselect(
    "Pedidos disponíveis:",
    options=lista_pedidos,
    default=lista_pedidos[:3] # Seleciona alguns por padrão
)

# Filtra o dataframe para os pedidos escolhidos
pedidos = pedidos_disp[pedidos_disp["fac_pedido"].astype(str).isin(pedidos_selecionados)].copy()

# Simulação de datas (Gantt)
if not pedidos.empty:
    st.subheader("Defina as datas dos pedidos selecionados")
    pedidos['start'] = datetime.today()
    pedidos['finish'] = pedidos['start'] + timedelta(weeks=1)
    for idx, row in pedidos.iterrows():
        col1, col2 = st.columns(2)
        pedidos.at[idx, 'start'] = col1.date_input(
            f"Início pedido {row['fac_pedido']}",
            value=row['start'],
            key=f"start_{idx}_{row['fac_pedido']}"
        )
        pedidos.at[idx, 'finish'] = col2.date_input(
            f"Fim pedido {row['fac_pedido']}",
            value=row['finish'],
            key=f"finish_{idx}_{row['fac_pedido']}"
        )

# Gantt Chart
    # Gantt Chart
    gantt_df = pedidos[['fac_pedido', 'start', 'finish']]
    gantt_df['Task'] = gantt_df['fac_pedido'].astype(str)
    gantt_df['Start'] = gantt_df['start']
    gantt_df['Finish'] = gantt_df['finish']
    fig_gantt = ff.create_gantt(gantt_df, index_col='Task', show_colorbar=True, group_tasks=True)
    st.plotly_chart(fig_gantt, use_container_width=True)

# Botão para calcular projeções
if st.button("Calcular"):
    # Simulação de consumo e evolução do estoque
    estoque_evolucao = df_estoque.copy()
    # ... lógica de desconto por semana conforme datas do Gantt ...
    # Exemplo simplificado:
    col_prod_pedidos = 'material' if 'material' in pedidos.columns else 'fac_codigo'
    # Detecta coluna de saldo no estoque
    col_saldo_estoque = 'saldo' if 'saldo' in estoque_evolucao.columns else (
        'saldo_atual' if 'saldo_atual' in estoque_evolucao.columns else estoque_evolucao.columns[-1])
    for idx, pedido in pedidos.iterrows():
        produto = pedido[col_prod_pedidos]
        consumo = pedido['consumo_total']
        # Desconta do estoque na semana do pedido
        estoque_evolucao.loc[estoque_evolucao['codigo'] == produto, col_saldo_estoque] -= consumo

    # Gráfico de evolução do estoque
    st.subheader("Evolução do Estoque por Produto")
    for produto in estoque_evolucao['codigo'].unique():
        saldo = estoque_evolucao[estoque_evolucao['codigo'] == produto][col_saldo_estoque].values[0]
        cor = "green" if saldo > 100 else "yellow" if saldo > 0 else "red"
        fig = go.Figure(go.Bar(x=[produto], y=[saldo], marker_color=cor))
        st.plotly_chart(fig, use_container_width=True)
        st.write(f"Produto: {produto} | Saldo: {saldo}")

    # Exportação Excel
    st.download_button(
        label="Exportar para Excel",
        data=estoque_evolucao.to_excel(index=False),
        file_name="projecao_estoque.xlsx"
    )

# Tabela de pedidos/produtos

# Monta tabela detalhada de pedidos e produtos
st.subheader("Tabela de Pedidos e Produtos")
# Seleciona o pivot principal para exibir (exemplo: 19_18)
if pivot_19_18 is not None:
    # Reset index para acessar material/cor_insumo
    tabela_pivot = pivot_19_18.reset_index()
    # Faz merge com estoque usando material/cor_insumo do pivot e codigo/cor do estoque
    tabela = tabela_pivot.merge(
        df_estoque,
        left_on=['material', 'cor_insumo'],
        right_on=['codigo', 'cor'],
        how='left',
        suffixes=('', '_estoque')
    )
    # Exibe apenas as colunas solicitadas
    colunas_exibir = ['descricao', 'descricao_cor', 'codigo_tabela_cor']
    # Garante que as colunas existem
    colunas_exibir = [c for c in colunas_exibir if c in tabela.columns]
    st.dataframe(tabela[colunas_exibir])
else:
    st.info("Não há dados pivotados disponíveis para exibir.")

# Gráfico de evolução do estoque ao clicar em produto
produto_selecionado = st.selectbox("Selecione um produto para ver evolução do estoque", df_estoque['codigo'].unique())
if produto_selecionado:
    # Simulação de evolução semanal
    col_saldo_estoque = 'saldo' if 'saldo' in df_estoque.columns else (
        'saldo_atual' if 'saldo_atual' in df_estoque.columns else df_estoque.columns[-1])
    saldo_inicial = df_estoque[df_estoque['codigo'] == produto_selecionado][col_saldo_estoque].values[0]
    col_prod_pedidos = 'material' if 'material' in pedidos.columns else 'fac_codigo'
    consumos = pedidos[pedidos[col_prod_pedidos] == produto_selecionado]['consumo_total'].tolist()
    semanas = [f"Semana {i+1}" for i in range(len(consumos))]
    saldo_semanal = [saldo_inicial]
    for consumo in consumos:
        saldo_semanal.append(saldo_semanal[-1] - consumo)
    fig = go.Figure(go.Scatter(x=semanas, y=saldo_semanal[1:], mode='lines+markers'))
    st.plotly_chart(fig, use_container_width=True)

st.write("🔴 Vermelho: estoque insuficiente | 🟡 Baixo | 🟢 Adequado")
