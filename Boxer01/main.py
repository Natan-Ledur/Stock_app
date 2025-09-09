# Bibliotecas principais
import pyodbc
import pandas as pd
import time
import matplotlib.pyplot as plt  # Para gráficos
from datetime import date
import numpy as np

#==============================================================================================
def criar_conexao():
    server = '192.168.1.224'
    database = '15060P'
    username = 'consulta'
    password = '15060Psisplan'
    conn_str = (f"DRIVER={{PostgreSQL ODBC Driver(UNICODE)}};SERVER={server};DATABASE={database};UID={username};PWD={password};")
    return pyodbc.connect(conn_str)
try:
    criar_conexao()
    print("✅ Conexão estabelecida com sucesso!")
except Exception as erros:
    print("❌ Erro na conexão:", erros)
    
#==============================================================================================

# 3.2 Consulta de estoque atual (sempre considerando o dia da pesquisa)
def consulta_estoque_atual(grupo='02', deposito='2001'):
    # Lê a query do arquivo externo
    with open('Orig_Consulta estoque.sql', 'r', encoding='utf-8') as f:
        query = f.read()
    # Preenche os parâmetros nomeados
    query = query.replace(':GRUPO', f"'{grupo}'")
    query = query.replace(':DEPOSITO', f"'{deposito}'")
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_estoque = consulta_estoque_atual()

#==============================================================================================

# 3.3 Consulta e armazenamento das informações de consumo de material por produto (todas as colunas)
def consulta_consumo_todos_produtos():
    """Lê todos os consumos de produtos da tabela consumoprod (query tab_consumo.sql) e armazena em um DataFrame."""
    with open('tab_consumo.sql', 'r', encoding='utf-8') as f:
        query = f.read()
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_consumo_produtos = consulta_consumo_todos_produtos()


#==============================================================================================

# 4.1 Consulta usando apenas o SQL puro do 3011.sql
def consulta_3011():
    with open('3011.sql', 'r', encoding='utf-8') as f:
        query = f.read()
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_pedidos_setores_grupos = consulta_3011()

#==============================================================================================

# 4.2 Agrupamento dos pedidos pelos campos corretos e soma das quantidades, separado por setor (fac_op)
colunas_agrupamento = ['fac_op', 'fac_pedido', 'fac_codigo', 'fac_cor', 'fac_tam']
colunas_soma = ['fac_qt_orig', 'of_qtde_orig']
df_agrupado = df_pedidos_setores_grupos.groupby(colunas_agrupamento, as_index=False)[colunas_soma].sum()

#==============================================================================================

# 5.1 Associação e cálculo do consumo por produto (ajustado para nomes corretos das colunas)
colunas_merge_agrupado = ['fac_codigo', 'fac_cor', 'fac_tam']
colunas_merge_consumo = ['produto', 'cor_prod', 'tam']
df_agrupado_consumo = pd.merge(
    df_agrupado,
    df_consumo_produtos,
    left_on=colunas_merge_agrupado,
    right_on=colunas_merge_consumo,
    how='left'
)

# Multiplica of_qtde_orig pelo consumo, tratando casos sem consumo
def calcula_consumo(row):
    if pd.isna(row.get('consumo')):
        return 'sem consumo cadastrado'
    return row['of_qtde_orig'] * row['consumo']

df_agrupado_consumo['consumo_total'] = df_agrupado_consumo.apply(calcula_consumo, axis=1)



#==============================================================================================

# Soma do consumo_total agrupando por fac_pedido, fac_codigo, fac_cor, fac_tam, fac_op
df_soma_consumo = df_agrupado_consumo.groupby(
    ['fac_pedido', 'material', 'cor_insumo', 'fac_op'],
    as_index=False
)['consumo_total'].sum()

#==============================================================================================

# Agrupamento dos pedidos conforme setores e regras solicitadas

# Pedidos do setor 19 (inclui também os que estão no setor 18)
pedidos_19 = df_soma_consumo[df_soma_consumo['fac_op'] == '19']
pedidos_18 = df_soma_consumo[df_soma_consumo['fac_op'] == '18']
pedidos_19_18 = pd.concat([
    pedidos_19,
    pedidos_18[pedidos_18['fac_pedido'].isin(pedidos_19['fac_pedido'])]
])

# Pedidos exclusivamente no setor 18
pedidos_exclusivos_18 = pedidos_18[~pedidos_18['fac_pedido'].isin(pedidos_19['fac_pedido'])]
dfs_exclusivos_18 = {
    pedido: pedidos_exclusivos_18[pedidos_exclusivos_18['fac_pedido'] == pedido]
    for pedido in pedidos_exclusivos_18['fac_pedido'].unique()
}

# Pedidos do setor 01
pedidos_01 = df_soma_consumo[df_soma_consumo['fac_op'] == '01']
dfs_01 = {
    pedido: pedidos_01[pedidos_01['fac_pedido'] == pedido]
    for pedido in pedidos_01['fac_pedido'].unique()
}
#==============================================================================================
# Pivotar os DataFrames para exibir: material, cor_insumo e uma coluna para cada fac_pedido
def pivotar_por_pedido(df):
    return df.pivot_table(
        index=['material', 'cor_insumo'],
        columns='fac_pedido',
        values='consumo_total',
        aggfunc='sum',
        fill_value=0
    )

# Pivotando os principais DataFrames
pivot_19_18 = pivotar_por_pedido(pedidos_19_18)
pivot_exclusivos_18 = {pedido: pivotar_por_pedido(df) for pedido, df in dfs_exclusivos_18.items()}
pivot_01 = {pedido: pivotar_por_pedido(df) for pedido, df in dfs_01.items()}

#==============================================================================================