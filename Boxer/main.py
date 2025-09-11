# Bibliotecas principais
import pyodbc
import pandas as pd
# import time
# import matplotlib.pyplot as plt  # Para gráficos, Não estou utilizando no momento
# from datetime import date
# import numpy as np #Para Arrays melhores, usei na versão anterior!
import pickle # Para conversão  objeto Python.
from dotenv import load_dotenv
import os

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, message="pandas only supports SQLAlchemy")

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

def criar_conexao():
    server = os.getenv('DB_SERVER')
    database = os.getenv('DB_DATABASE')
    username = os.getenv('DB_USERNAME')
    password = os.getenv('DB_PASSWORD')
    conn_str = (f"DRIVER={{PostgreSQL ODBC Driver(UNICODE)}};SERVER={server};DATABASE={database};UID={username};PWD={password};")
    return pyodbc.connect(conn_str)
try:
    criar_conexao()
    print("Conexão estabelecida com sucesso!")
except Exception as erros:
    print("Erro na conexão:", erros)
    
#==============================================================================================

# 3.2 Consulta de estoque atual (sempre considerando o dia da pesquisa)
def consulta_estoque_atual(grupo='02', deposito='2001'):
    # Lê a query do arquivo externo
    with open('Boxer/Orig_Consulta estoque.sql', 'r', encoding='utf-8') as f:
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
    with open('Boxer/tab_consumo.sql', 'r', encoding='utf-8') as f:
        query = f.read()
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_consumo_produtos = consulta_consumo_todos_produtos()


#==============================================================================================

# 4.1 Consulta usando apenas o SQL puro do 3011.sql
def consulta_3011():
    with open('Boxer/3011.sql', 'r', encoding='utf-8') as f:
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
# 1. Merge do estoque com o pivot principal (setor 19 e 18)
df_resultado = pd.merge(
    df_estoque,
    pivot_19_18.reset_index(),
    left_on=['codigo', 'cor'],
    right_on=['material', 'cor_insumo'],
    how='left'
    )

# 2. Adiciona colunas dos pivots exclusivos do setor 18
for pedido, df_pivot in pivot_exclusivos_18.items():
    df_resultado[f'18_{pedido}'] = df_resultado.set_index(['material', 'cor_insumo']).index.map(
        lambda idx: df_pivot.loc[idx, pedido] if idx in df_pivot.index and pedido in df_pivot.columns else 0
    )

# 3. Soma dos consumos exclusivos do setor 18
colunas_18 = [f'18_{pedido}' for pedido in pivot_exclusivos_18.keys()]
df_resultado['Soma_Consumo_18'] = df_resultado[colunas_18].sum(axis=1)

# 4. Adiciona colunas dos pivots do setor 01
for pedido, df_pivot in pivot_01.items():
    df_resultado[f'01_{pedido}'] = df_resultado.set_index(['material', 'cor_insumo']).index.map(
        lambda idx: df_pivot.loc[idx, pedido] if idx in df_pivot.index and pedido in df_pivot.columns else 0
    )

# 5. Soma dos consumos do setor 01
colunas_01 = [f'01_{pedido}' for pedido in pivot_01.keys()]
df_resultado['Soma_Consumo_01'] = df_resultado[colunas_01].sum(axis=1)

# 6. Soma total dos consumos dos pedidos (todas as colunas de pedidos)
colunas_pedidos_19_18 = [col for col in pivot_19_18.columns if col not in ['material', 'cor_insumo']]
df_resultado['Soma_Consumo_19_18'] = df_resultado[colunas_pedidos_19_18].sum(axis=1)

df_resultado['Consumo_Total_Pedidos'] = (
    df_resultado['Soma_Consumo_19_18'] +
    df_resultado['Soma_Consumo_18'] +
    df_resultado['Soma_Consumo_01']
    )

# 7. Última coluna: estoque atual descontado dos consumos
df_resultado['Estoque_Descontado'] = df_resultado['estoque_total'] - df_resultado['Consumo_Total_Pedidos']

# 8. Seleciona as colunas finais
colunas_finais = (
    ['descricao', 'descricao_cor', 'codigo_tabela_cor', 'estoque_total'] +
    colunas_pedidos_19_18 + ['Soma_Consumo_19_18'] +
    colunas_18 + ['Soma_Consumo_18'] +
    colunas_01 + ['Soma_Consumo_01'] +
    ['Consumo_Total_Pedidos', 'Estoque_Descontado']
    )

df_final = df_resultado[colunas_finais]


#======================================================================
# Salva todos os principais DataFrames em um arquivo de cache para o dashboard

cache_dict = {
    'df_final': df_final,
    'df_resultado': df_resultado,
    'df_estoque': df_estoque,
    'df_consumo_produtos': df_consumo_produtos,
    'df_pedidos_setores_grupos': df_pedidos_setores_grupos,
    'df_agrupado': df_agrupado,
    'df_agrupado_consumo': df_agrupado_consumo,
    'df_soma_consumo': df_soma_consumo,
    'pedidos_19': pedidos_19,
    'pedidos_18': pedidos_18,
    'pedidos_19_18': pedidos_19_18,
    'pedidos_exclusivos_18': pedidos_exclusivos_18,
    'pedidos_01': pedidos_01,
    'pivot_19_18': pivot_19_18,
    'pivot_exclusivos_18': pivot_exclusivos_18,
    'pivot_01': pivot_01
}
with open("Boxer/main_cache.pkl", "wb") as f:
    pickle.dump(cache_dict, f)
#===================================================================