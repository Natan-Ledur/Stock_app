import os
import sys
import importlib
import io
import datetime
import platform
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, message="pandas only supports SQLAlchemy")

import pyodbc

import time
import matplotlib.pyplot as plt  # Para gráficos
from datetime import date

from pathlib import Path


# Carrega .env próximo (compatível com execução direta deste script)
try:
    from dotenv import load_dotenv, find_dotenv
except Exception:
    load_dotenv = None
    find_dotenv = None

if find_dotenv:
    dotenv_path = find_dotenv()
    if not dotenv_path:
        # fallback para frontend/.env (subindo três níveis a partir de frontend/app/Meia)
        fallback = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
        if os.path.exists(fallback):
            dotenv_path = fallback
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        # última tentativa
        if load_dotenv:
            load_dotenv()


# ---------------- Mongo helpers (similar ao Boxer) ----------------
try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None


def _get_mongo_client_and_db():
    if MongoClient is None:
        return None, None

    MONGO_URI = os.environ.get("MONGO_URI")
    MONGO_DB = os.environ.get("MONGO_DB", "mydb")

    # Preferência por Compass/localhost no Windows
    try:
        if platform.system().lower().startswith('windows'):
            compass = os.environ.get('MONGO_URI_COMPASS')
            if compass:
                MONGO_URI = compass
    except Exception:
        pass

    if not MONGO_URI:
        MONGO_USER = os.environ.get("MONGO_USER", os.getenv("MONGO_INITDB_ROOT_USERNAME", "user"))
        MONGO_PASS = os.environ.get("MONGO_PASS", os.getenv("MONGO_INITDB_ROOT_PASSWORD", "password"))
        MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
        MONGO_URI = f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}:27017/"

    try:
        if platform.system().lower().startswith('windows') and 'mongodb2:27017' in MONGO_URI:
            MONGO_URI = MONGO_URI.replace('mongodb2:27017', 'localhost:27018')
    except Exception:
        pass

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        db = client[MONGO_DB]
        return client, db
    except Exception as e:
        print(f"WARNING: Não foi possível conectar ao MongoDB em '{MONGO_URI}': {e}")
        return None, None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    df2.columns = [str(c).strip().lower().replace(' ', '_') for c in df2.columns]
    return df2


def salvar_df_mongo(db, df: pd.DataFrame, nome_colecao: str, historico: bool = False):
    if db is None:
        print(f"WARNING: Pular salvar '{nome_colecao}' porque conexão com MongoDB não está disponível.")
        return
    try:
        col = db[nome_colecao]
        # limpa a coleção principal
        try:
            col.delete_many({})
        except Exception as e:
            print(f"WARNING: falha ao limpar coleção {nome_colecao}: {e}")
        if df is not None and not df.empty:
            df2 = _normalize_columns(df)
            # Garante serialização de NaN -> None e numpy -> types python
            df2 = df2.where(pd.notnull(df2), None)
            registros = df2.to_dict('records')
            # Usar horário local (consistente com a implementação do Boxer)
            
            for reg in registros:
                reg['data_atualizacao'] = datetime.datetime.now()
            try:
                if registros:
                    col.insert_many(registros)
            except Exception as e:
                print(f"WARNING: falha ao inserir registros em {nome_colecao}: {e}")
            if historico:
                try:
                    db[f"{nome_colecao}_historico"].insert_many(registros)
                except Exception as e:
                    print(f"WARNING: falha ao escrever histórico {nome_colecao}_historico: {e}")
    except Exception as e:
        print(f"WARNING: erro ao salvar coleção {nome_colecao}: {e}")




###====================================================================consumo meias + estoque - finte sisplam===============================================================================

# Bibliotecas principais


#======================================================================================================================
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
    
#======================================================================================================================
# 3.2 Consulta de estoque atual (sempre considerando o dia da pesquisa)
def consulta_estoque_atual(grupo='02', deposito='2000'):
    # Lê a query do arquivo externo
    caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/Orig_Consulta estoque.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    # Preenche os parâmetros nomeados
    query = query.replace(':GRUPO', f"'{grupo}'")
    query = query.replace(':DEPOSITO', f"'{deposito}'")
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_estoque = consulta_estoque_atual()

#======================================================================================================================
# 3.3 Consulta e armazenamento das informações de consumo de material por produto (todas as colunas)
def consulta_consumo_todos_produtos():
    caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/consumos_fios.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_consumo_fios = consulta_consumo_todos_produtos()

#======================================================================================================================
# 3. Consulta e armazenamento das informações de consumo etiqueta 01
def consulta_consumo_todos_produtos():
    caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/222.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_et01= consulta_consumo_todos_produtos()

#======================================================================================================================
# 4.1 Consulta usando apenas o SQL puro do 3011.sql
def consulta_3011():
    caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/3011.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_pedidos_setores_grupos = consulta_3011()

#======================================================================================================================
# 4.2 Agrupamento dos pedidos pelos campos corretos e soma das quantidades, separado por setor (fac_op)
colunas_agrupamento = ['fac_op', 'fac_pedido', 'fac_codigo', 'fac_cor', 'fac_tam']
colunas_soma = ['fac_qt_orig', 'of_qtde_orig']
df_agrupado = df_pedidos_setores_grupos.groupby(colunas_agrupamento, as_index=False)[colunas_soma].sum()

#======================================================================================================================
# 5.1 Associação e cálculo do consumo por produto (ajustado para nomes corretos das colunas)
colunas_merge_agrupado = ['fac_codigo', 'fac_cor', 'fac_tam']
colunas_merge_consumo = ['produto', 'cor_prod', 'tam']
df_agrupado_consumo = pd.merge(
    df_agrupado,
    df_consumo_fios,
    left_on=colunas_merge_agrupado,
    right_on=colunas_merge_consumo,
    how='left'
)

# Multiplica of_qtde_orig pelo consumo, tratando casos sem consumo
def calcula_consumo(row):
    if pd.isna(row.get('consumo')):
        return '*'
    return row['of_qtde_orig'] * row['consumo']

df_agrupado_consumo['consumo_total'] = df_agrupado_consumo.apply(calcula_consumo, axis=1)

#======================================================================================================================
# Execução simples da query Q1 e armazenamento em DataFrame


caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/Q1_1002_acesso.sql')
with open(caminho_sql, 'r', encoding='utf-8') as f:
    query = f.read()

conn = criar_conexao()
df_q1 = pd.read_sql_query(query, conn)
conn.close()

#======================================================================================================================
# Q2: Pesquisar todos os pedidos de uma só vez na query Q2 usando IN e retornar DataFrame com coluna 'numero'


caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/Q2_220_filtro.sql')
with open(caminho_sql, 'r', encoding='utf-8') as f:
    query_q2_template = f.read()

# Lista de pedidos a partir da coluna 'numero' de df_q1
pedidos = df_q1['numero'].astype(str).str.strip().dropna().unique().tolist()

if len(pedidos) == 0:
    print("❌ Nenhum pedido encontrado na coluna 'numero' de df_q1.")
    pedidos_com_resultados = pd.DataFrame(columns=['numero'])
else:
    def format_in(values):
        return ','.join(["'{}'".format(str(v).replace("'", "''")) for v in values])

    in_list = format_in(pedidos)
    query = query_q2_template.replace(':sel', in_list)

    conn = criar_conexao()
    df_q2 = pd.read_sql_query(query, conn)
    conn.close()

    # Normalizar para DataFrame 'pedidos_com_resultados' com a coluna 'numero'
    cols = {c.lower(): c for c in df_q2.columns}
    base_col = cols['pedido'] if 'pedido' in cols else (cols['numero'] if 'numero' in cols else None)
    if base_col is None or df_q2.empty:
        pedidos_com_resultados = pd.DataFrame(columns=['numero'])
    else:
        s = df_q2[base_col].astype(str).str.strip()
        s = s[s != ''].dropna().unique()
        pedidos_com_resultados = pd.DataFrame({'numero': s})
        
#======================================================================================================================
# Construir df_sem_demanda = df_q1 - df_q2 (apenas pedidos que NAO apareceram na Q2)


# Extrair a coluna de pedidos de df_q1
numeros_q1 = df_q1['numero'].astype(str).str.strip()

# Tentar identificar a coluna de pedidos em df_q2 (pode ser 'numero' ou 'pedido')
if 'numero' in pedidos_com_resultados.columns:
   numeros_q2 = pedidos_com_resultados['numero'].astype(str).str.strip()
elif 'pedido' in pedidos_com_resultados.columns:
    numeros_q2 = pedidos_com_resultados['pedido'].astype(str).str.strip()
else:
    # Se não houver coluna identificável, considerar nenhum pedido filtrado na Q2
    numeros_q2 = pd.Series([], dtype='string')

# Diferença de conjuntos
sem_demanda = numeros_q1[~numeros_q1.isin(numeros_q2)].dropna()
sem_demanda = sem_demanda[sem_demanda != '']
df_sem_demanda = pd.DataFrame({'numero': sem_demanda.unique()}).reset_index(drop=True)

#======================================================================================================================

# Q3: Para cada pedido em df_sem_demanda, obter itens comerciais (Q3_1002_itempedido.sql)
caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/Q3_1002_itempedido.sql')
with open(caminho_sql, 'r', encoding='utf-8') as f:
    query_q3_template = f.read()

# Assumindo que df_sem_demanda existe e possui a coluna 'numero'
pedidos = df_sem_demanda['numero'].astype(str).str.strip().dropna().unique().tolist()

df_q3_parts = []
for pedido in pedidos:
    sel = "'{}'".format(str(pedido).replace("'", "''"))
    query = query_q3_template.replace(':sel', sel)
    conn = criar_conexao()
    df_part = pd.read_sql_query(query, conn)
    conn.close()
    if not df_part.empty and 'numero' not in df_part.columns:
        df_part['numero'] = str(pedido)
    df_q3_parts.append(df_part)

df_q3 = pd.concat(df_q3_parts, ignore_index=True, sort=False) if len(df_q3_parts) > 0 else pd.DataFrame()

#======================================================================================================================
# Para cada linha de df_q3, buscar correspondência em df_et01 (código, cor, tam)
# Se encontrar, concatenar as informações; se não, armazenar em df_sem_corresp

# Renomear colunas de df_et01 para facilitar o merge
et01 = df_et01.rename(columns={
    'codigo': 'codigo',
    'cor_prod': 'cor',
    'faixa': 'tam'
})

# Garantir que os tipos e espaços estejam padronizados
for col in ['codigo', 'cor', 'tam']:
    df_q3[col] = df_q3[col].astype(str).str.strip()
    et01[col] = et01[col].astype(str).str.strip()

# Realizar o merge (inner para correspondentes, left_anti para não correspondentes)
df_merged = pd.merge(df_q3, et01, on=['codigo', 'cor', 'tam'], how='inner', suffixes=('', '_et01'))
df_sem_corresp = pd.merge(df_q3, et01, on=['codigo', 'cor', 'tam'], how='left', indicator=True)
df_sem_corresp = df_sem_corresp[df_sem_corresp['_merge'] == 'left_only'].drop(columns=['_merge'])

#======================================================================================================================
# Cálculo das quantidades finais para cada linha do df_merged de uma só vez
if not all(col in df_merged.columns for col in ['qtde', 'qtde_fat', 'categoria', 'consumo', 'numero', 'codigo', 'cor_i', 'tam']):
    raise ValueError("Colunas necessárias não encontradas em df_merged!")

# Calcular soma dos consumos para cada grupo de uma só vez
group_cols = ['numero', 'codigo', 'cor_i','tam']
df_merged['soma_consumos'] = df_merged.groupby(group_cols)['consumo'].transform('sum')

# Calcular a quantidade final de uma só vez
df_merged['quantidade_final'] = ((df_merged['qtde'] + df_merged['qtde_fat']) * df_merged['categoria'] * 2) * (df_merged['consumo'] / df_merged['soma_consumos'].replace(0, 1))
# (evita divisão por zero usando .replace(0, 1), mas se preferir pode usar np.where para zerar nesses casos)

#======================================================================================================================
# É a mesma logica usada entre o df-q3 e o df_et01(bem simples)!

df_merged2 = df_merged.rename(columns={
    'insumo': 'produto', 
    'cor_i': 'cor_prod',
    'tam': 'tam'    
})

df_merged2= pd.merge(df_merged2,df_consumo_fios, on=['produto','cor_prod','tam'], how='inner', suffixes=('', '_fios'))

#======================================================================================================================
# Multiplicar quantidade_final por consumo_fios e criar coluna consumo_total

required_cols = ['quantidade_final', 'consumo_fios']
missing = [c for c in required_cols if c not in df_merged2.columns]
if missing:
    raise ValueError(f"Colunas ausentes em df_merged2: {missing}")

# Garantir que ambas sejam numéricas (NaN -> 0)
df_merged2['quantidade_final'] = pd.to_numeric(df_merged2['quantidade_final'], errors='coerce').fillna(0)
df_merged2['consumo_fios'] = pd.to_numeric(df_merged2['consumo_fios'], errors='coerce').fillna(0)

# Consumo total de fios por linha
df_merged2['consumo_total'] = df_merged2['quantidade_final'] * df_merged2['consumo_fios']

# Adicionar coluna 'setor' com valor fixo 'SD'
df_merged2['setor'] = 'SD'
#======================================================================================================================
#Salvando os dataframes em excel para conferência
# df_merged2.to_excel('excel/df_meias_sof.xlsx', index=False )

#======================================================================================================================
# Selecionar e renomear as colunas do DataFrame df_agrupado_consumo conforme solicitado
colunas_renomear_cd = {
    'fac_op': 'setor',
    'fac_pedido': 'pedido',
    'fac_codigo' : 'codigo' , 
    'fac_cor': 'cor',
    'fac_tam': 'tamanho',
    'fac_qt_orig': 'quantidade',
    'material': 'material_cod',
    'cor_insumo': 'cor_cod',
    'codigo2': 'codigo2',
    'descricao_cor': 'descricao_cor',
    'descricao_mat': 'descricao_mat',
    'consumo': 'consumo',
    'consumo_total': 'consumo_total'
}

# Selecionar apenas as colunas desejadas
colunas_usar = list(colunas_renomear_cd.keys())
df_meias_cof = df_agrupado_consumo[colunas_usar].rename(columns=colunas_renomear_cd)

#======================================================================================================================
# Selecionar e renomear as colunas do DataFrame df_merged2 conforme solicitado
colunas_renomear_sd = {
    'setor' : 'setor' ,
    'numero': 'pedido',
    'codigo' : 'codigo' ,
    'cor' : 'cor' ,
    'tam' : 'tamanho' ,
    'quantidade_final' : 'quantidade',
    'material' : 'material_cod',
    'cor_insumo' : 'cor_cod',
    'codigo2' : 'codigo2',
    'descricao_cor' : 'descricao_cor',
    'descricao_mat': 'descricao_mat',
    'consumo_fios' : 'consumo',
    'consumo_total' : 'consumo_total'    
}

# Selecionar apenas as colunas desejadas
colunas_usar = list(colunas_renomear_sd.keys())
df_meias_sof = df_merged2[colunas_usar].rename(columns=colunas_renomear_sd)

#======================================================================================================================
# Selecionar e renomear as colunas do DataFrame df_sem_corresp conforme solicitado
colunas_renomear_sdsc = {
    'setor' : 'setor' ,
    'numero': 'pedido',
    'codigo' : 'codigo' ,
    'cor' : 'cor' ,
    'tam' : 'tamanho' ,
    'qtde' : 'quantidade',
    'material' : 'material_cod',
    'cor_insumo' : 'cor_cod',
    'codigo2' : 'codigo2',
    'descricao_cor' : 'descricao_cor',
    'descricao_mat': 'descricao_mat',
    'consumo_fios' : 'consumo',
    'consumo_total' : 'consumo_total'    
}

# Garante que todas as colunas existam, se não existir cria com valor None
for col in colunas_renomear_sdsc.keys():
    if col not in df_sem_corresp.columns:
        df_sem_corresp[col] = None

# Preencher a coluna 'setor' com 'SD' e 'consumo_total' com '*'
df_sem_corresp['setor'] = 'SD'
df_sem_corresp['consumo_total'] = '*'

# Selecionar apenas as colunas desejadas
colunas_usar = list(colunas_renomear_sdsc.keys())
df_meias_sofsc = df_sem_corresp[colunas_usar].rename(columns=colunas_renomear_sdsc)

#======================================================================================================================
# Concatenar os DataFrames padronizados
df_meias_final = pd.concat([df_meias_cof, df_meias_sof, df_meias_sofsc], ignore_index=True)

#======================================================================================================================


#======================================================================================================================
# Salva df_final na coleção esperada pelo dashboard (AJUSTAR)
try:
    client2, db2 = _get_mongo_client_and_db()
    salvar_df_mongo(db2, df_meias_final, "meia_pedido_consumos")
    print("meia_pedido_consumos salvo no MongoDB.")
except Exception as e:
    print(f"WARNING: falha ao salvar meia_pedido_consumos: {e}")
    

    
try:
    client2, db2 = _get_mongo_client_and_db()
    salvar_df_mongo(db2, df_estoque, "meia_estoque")
    print("meia_estoque salvo no MongoDB.")
except Exception as e:
    print(f"WARNING: falha ao salvar meia_estoque: {e}")