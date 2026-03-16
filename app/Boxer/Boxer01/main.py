# import time
# import matplotlib.pyplot as plt  # Para gráficos, Não estou utilizando no momento
# from datetime import date
# import numpy as np #Para Arrays melhores, usei na versão anterior!
# import pickle # Para conversão  objeto Python.
# Bibliotecas principais==========================================
import pyodbc
import pandas as pd
from dotenv import load_dotenv, find_dotenv
import os
import datetime
import warnings
from pathlib import Path  # Necessário para uso posterior em consultas SQL
from pymongo import MongoClient
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, message="pandas only supports SQLAlchemy")

# Load the nearest .env file (searches parent directories). If not found,
# fallback to the frontend/.env path (one level above `app`). This avoids
# returning None for DB host when running the script manually from the
# `Boxer` folder.
dotenv_path = find_dotenv()
if not dotenv_path:
    # compute fallback: ../.. -> frontend
    fallback = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    if os.path.exists(fallback):
        dotenv_path = fallback

if dotenv_path:
    load_dotenv(dotenv_path)
else:
    # last resort: attempt default loader (will search cwd)
    load_dotenv()

# Debug: print loaded DB_SERVER when running manually (can be removed later)
try:
    print("DEBUG: loaded DB_SERVER=", os.getenv('DB_SERVER'))
except Exception:
    pass

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
    caminho_sql = os.path.join(os.path.dirname(__file__), 'Orig_Consulta estoque.sql')
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

#==============================================================================================

# 3.3 Consulta e armazenamento das informações de consumo de material por produto (todas as colunas)
def consulta_consumo_todos_produtos():
    """Lê todos os consumos de produtos da tabela consumoprod (query tab_consumo.sql) e armazena em um DataFrame."""
    caminho_sql = os.path.join(os.path.dirname(__file__), 'tab_consumo.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_consumo_produtos = consulta_consumo_todos_produtos()


#==============================================================================================

# 4.1 Consulta usando apenas o SQL puro do 3011.sql
def consulta_3011():
    caminho_sql = os.path.join(os.path.dirname(__file__), '3011.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
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
df_agrupado_consumo['consumo_total'] = (
    df_agrupado_consumo['consumo_total']
    .astype(str)
    .str.replace(',', '.', regex=False)
)

df_agrupado_consumo['consumo_total'] = pd.to_numeric(
    df_agrupado_consumo['consumo_total'],
    errors='coerce'
)


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
# Salva todos os principais DataFrames 

# Salvar DataFrames principais no MongoDB


# Ensure env vars are loaded for the Mongo section as well. Reuse find_dotenv
# so running this file directly picks up the same .env as above.
dotenv_path = find_dotenv()
if not dotenv_path:
    fallback = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    if os.path.exists(fallback):
        dotenv_path = fallback
if dotenv_path:
    load_dotenv(dotenv_path)
else:
    load_dotenv()
# Prioriza uso da variável MONGO_URI
MONGO_DB = os.environ.get("MONGO_DB", "mydb")
import platform


def _is_local_uri(uri: str) -> bool:
    if not uri:
        return False
    uri_lower = uri.lower()
    return "localhost" in uri_lower or "127.0.0.1" in uri_lower


def _dedupe_uris(uris):
    seen = set()
    ordered = []
    for uri in uris:
        if uri and uri not in seen:
            seen.add(uri)
            ordered.append(uri)
    return ordered


def _build_mongo_uri_candidates():
    mongo_uri = os.environ.get("MONGO_URI")
    mongo_uri_vm = os.environ.get("MONGO_URI_VM") or os.environ.get("MONGO_URI_REMOTE")
    mongo_uri_local = os.environ.get("MONGO_URI_LOCAL")
    mongo_user = os.environ.get("MONGO_USER", os.getenv("MONGO_INITDB_ROOT_USERNAME", "user"))
    mongo_pass = os.environ.get("MONGO_PASS", os.getenv("MONGO_INITDB_ROOT_PASSWORD", "password"))
    local_host = os.environ.get("MONGO_LOCAL_HOST", "localhost")
    local_port = os.environ.get("MONGO_LOCAL_PORT", "27017")

    local_candidates = []
    if mongo_uri_local:
        local_candidates.append(mongo_uri_local)
    compass = os.environ.get('MONGO_URI_COMPASS')
    if compass:
        local_candidates.append(compass)
    if mongo_uri and _is_local_uri(mongo_uri):
        local_candidates.append(mongo_uri)
    local_candidates.append(f"mongodb://{mongo_user}:{mongo_pass}@{local_host}:{local_port}/")

    if platform.system().lower().startswith('windows'):
        local_candidates.append(f"mongodb://{mongo_user}:{mongo_pass}@{local_host}:27018/")
        if mongo_uri and 'mongodb2:27017' in mongo_uri:
            local_candidates.append(mongo_uri.replace('mongodb2:27017', 'localhost:27018'))

    vm_candidates = []
    if mongo_uri_vm:
        vm_candidates.append(mongo_uri_vm)
    if mongo_uri and not _is_local_uri(mongo_uri):
        vm_candidates.append(mongo_uri)
    vm_host = os.environ.get("MONGO_HOST")
    if vm_host and vm_host.lower() not in ("localhost", "127.0.0.1"):
        vm_candidates.append(f"mongodb://{mongo_user}:{mongo_pass}@{vm_host}:27017/")

    return _dedupe_uris(local_candidates + vm_candidates)


try:
    uri_candidates = _build_mongo_uri_candidates()
    client = None
    db = None
    last_error = None
    last_uri = None
    for uri in uri_candidates:
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            db = client[MONGO_DB]
            last_error = None
            break
        except Exception as e:
            last_error = e
            last_uri = uri
            client = None
            db = None

    if client is None and last_error:
        # If Mongo is not reachable, warn and set client/db to None so the
        # rest of the script can continue without raising an exception.
        print(f"WARNING: Não foi possível conectar ao MongoDB em '{last_uri}': {last_error}")
except Exception as e:
    print(f"WARNING: erro ao configurar MongoDB URI: {e}")
    client = None
    db = None

def salvar_df_mongo(df, nome_colecao):
    # If DB connection wasn't established earlier, skip silently with a warning
    if db is None:
        print(f"WARNING: Pular salvar '{nome_colecao}' porque conexão com MongoDB não está disponível.")
        return

    col = db[nome_colecao]
    # Se for estoque, salva também em uma coleção histórica separada
    if nome_colecao == "boxer_df_estoque":
        if not df.empty:
            df.columns = [str(col).lower().replace(" ", "_") for col in df.columns]
            registros = df.to_dict("records")
            for reg in registros:
                reg["data_atualizacao"] = datetime.datetime.now()
            try:
                col.delete_many({})  # Limpa coleção principal antes de inserir
                col.insert_many(registros)
            except Exception as e:
                print(f"WARNING: falha ao escrever coleção {nome_colecao}: {e}")
            # Salva o snapshot do estoque no histórico
            col_hist = db["boxer_historico_estoque"]
            for reg in registros:
                try:
                    col_hist.insert_one(reg)
                except Exception as e:
                    print(f"WARNING: falha ao inserir histórico em {col_hist.name}: {e}")
    else:
        try:
            col.delete_many({})  # Limpa coleção antes de inserir
        except Exception as e:
            print(f"WARNING: falha ao limpar coleção {nome_colecao}: {e}")
        if not df.empty:
            df.columns = [str(col).lower().replace(" ", "_") for col in df.columns]
            registros = df.to_dict("records")
            for reg in registros:
                reg["data_atualizacao"] = datetime.datetime.now()
            try:
                col.insert_many(registros)
            except Exception as e:
                print(f"WARNING: falha ao inserir registros em {nome_colecao}: {e}")

print("Parte 1 finalizada")
#===================================================================SD dataframes=========================
#==================================================================================================================================================   
 # 3.3 Consulta e armazenamento das informações de consumo de material por produto (todas as colunas)
def consulta_consumo_todos_produtos():
    """Lê todos os consumos de produtos da tabela consumoprod (query tab_consumo2.sql) e armazena em um DataFrame."""
    caminho_sql = os.path.join(os.path.dirname(__file__), 'tab_consumo2.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_consumo_ind = consulta_consumo_todos_produtos()
print(f'Total de linhas no DataFrame unido: {len(df_consumo_ind)}')
print(df_consumo_ind.columns.tolist())


#===================================================================================================================================================
# 3.3 Consulta e armazenamento das informações de consumo de material por produto (todas as colunas)
def consulta_consumo_todos_produtos():
    """Lê todos os consumos de produtos da tabela consumoprod (query consumos_fios.sql) e armazena em um DataFrame."""
    caminho_sql = os.path.join(os.path.dirname(__file__), 'consumos_fios.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_consumo_fios = consulta_consumo_todos_produtos()

print(df_consumo_fios.columns.tolist())

#===================================================================================================================================================
# 3.3 Consulta e armazenamento das informações de consumo de material por produto (todas as colunas)
def consulta_consumo_todos_produtos():
    """Lê todos os consumos de produtos da tabela consumoprod (query terminacao.sql) e armazena em um DataFrame."""
    caminho_sql = os.path.join(os.path.dirname(__file__), 'terminacao.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    with criar_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_terminacao = consulta_consumo_todos_produtos()

#===================================================================================================================================================
# Unir diretamente os DataFrames, sem tratamento ou padronização de colunas
df_unido = pd.concat([df_consumo_ind, df_terminacao])

# Remover linhas duplicadas do DataFrame unido
df_unido = df_unido.drop_duplicates()

#===================================================================================================================================================

# Execução simples da query Q1 e armazenamento em DataFrame

caminho_sql = os.path.join(os.path.dirname(__file__), 'Q1_1002_acesso.sql')
with open(caminho_sql, 'r', encoding='utf-8') as f:
    query = f.read()

conn = criar_conexao()
df_q1 = pd.read_sql_query(query, conn)
conn.close()
# Exibir resumo e DataFrame final
print(f"Pedidos totais: {df_q1.nunique()}")

#===================================================================================================================================================
# Q2: Pesquisar todos os pedidos de uma só vez na query Q2 usando IN e retornar DataFrame com coluna 'numero'

caminho_sql = os.path.join(os.path.dirname(__file__), 'Q2_220_filtro.sql')
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

print(f"Pedidos com resultados: {len(pedidos_com_resultados)}")

#===================================================================================================================================================
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

print(f"Pedidos totais: {numeros_q1.nunique()} | Removidos (com demanda): {pd.Series(numeros_q2).nunique()} | Sem demanda: {len(df_sem_demanda)}")


#===================================================================================================================================================
# Q3: Para cada pedido em df_sem_demanda, obter itens comerciais (Q3_1002_itempedido.sql)
caminho_sql = os.path.join(os.path.dirname(__file__), 'Q3_1002_itempedido.sql')
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

print(df_q3.columns.tolist())
print(f'Pedidos pesquisados: {len(pedidos)}  Linhas retornadas (total): {len(df_q3)}')
#===================================================================================================================================================

# Não é necessário consultar query, apenas filtrar o DataFrame df_consumo_industriais
df_q4_parts = []
pedidos_sem_resultado = []

for _, row in df_q3.iterrows():
    numero = str(row['numero']).strip()
    codigo = str(row['codigo']).strip()
    cor = str(row['cor']).strip()
    tam = str(row['tam']).strip()
    qt = row['qtde']
    qf = row['qtde_fat']

    # Filtrar pelo tam respectivo
    mask_tam = (
        (df_unido['produto'].astype(str).str.strip() == codigo) &
        (df_unido['cor_prod'].astype(str).str.strip() == cor) &
        (df_unido['tam'].astype(str).str.strip() == tam)
    )
    df_part_tam = df_unido[mask_tam].copy()

    # Filtrar também tam == 'u' para mesmo produto e cor_prod
    mask_u = (
        (df_unido['produto'].astype(str).str.strip() == codigo) &
        (df_unido['cor_prod'].astype(str).str.strip() == cor) &
        (df_unido['tam2'].astype(str).str.strip() == tam) &
        (df_unido['tam'].astype(str).str.strip() == 'U')
    )
    df_part_u = df_unido[mask_u].copy()

    # Concatenar ambos (evita duplicidade se tam == 'u' for igual ao tam respectivo)
    df_part = pd.concat([df_part_tam, df_part_u]).drop_duplicates()

    if df_part.empty:
        pedidos_sem_resultado.append(numero)
        continue

    df_part['numero'] = numero
    df_part['qtde'] = qt
    df_part['qtde_fat'] = qf
    df_q4_parts.append(df_part)

# Consolidar resultados
if df_q4_parts:
    df_q4 = pd.concat(df_q4_parts, ignore_index=True, sort=False)
else:
    df_q4 = pd.DataFrame()
df_q4_vazios = pd.DataFrame({'numero': sorted(set(pedidos_sem_resultado))})

print(f"Q4 executada — linhas com consumo: {len(df_q4)} | pedidos sem resultado: {len(df_q4_vazios)}")

#===================================================================================================================================================
# Cálculo das quantidades finais para cada linha do df_q4 de uma só vez
if not all(col in df_q4.columns for col in ['qtde', 'qtde_fat', 'categoria', 'consumo', 'numero', 'codigo', 'cor_prod', 'tam', 'tam2']):
    raise ValueError("Colunas necessárias não encontradas em df_q4!")

# Calcular soma dos consumos para cada grupo de uma só vez
group_cols = ['numero', 'codigo', 'cor_prod','tam','tam2']
df_q4['soma_consumos'] = df_q4.groupby(group_cols)['consumo'].transform('sum')

# Calcular a quantidade final de uma só vez
df_q4['quantidade_final'] = ((df_q4['qtde'] + df_q4['qtde_fat']) * df_q4['categoria']) * (df_q4['consumo'] / df_q4['soma_consumos'].replace(0, 1))
#===================================================================================================================================================
# Pesquisa direta e multiplicação simples do consumo de fios
df_q5 = df_q4.merge(
    df_consumo_fios,
    left_on=['material', 'cor_insumo', 'tam'],
    right_on=['produto', 'cor_prod', 'tam'],
    how='left'
    )
#===================================================================================================================================================
# Multiplicando quantidade_final por consumo_y para cada linha do df_q5 e exibindo colunas adicionais
colunas_exibir = ['numero', 'material_y', 'cor_insumo_y', 'quantidade_final', 'consumo_y', 'quantidade_fio_consumo', 'descricao_cor', 'descricao_mat']
if 'quantidade_final' not in df_q5.columns or 'consumo_y' not in df_q5.columns:
    raise ValueError("Colunas 'quantidade_final' ou 'consumo_y' não encontradas em df_q5!")

df_q5['quantidade_fio_consumo'] = df_q5['quantidade_final'] * df_q5['consumo_y']
colunas_validas = [c for c in colunas_exibir if c in df_q5.columns]
#===================================================================================================================================================
# Agrupamento respeitando os novos nomes das colunas
colunas_agrup = ['numero', 'material_y', 'cor_insumo_y', 'descricao_cor', 'descricao_mat']
faltando = [c for c in colunas_agrup if c not in df_q5.columns]
if faltando:
    raise ValueError(f'Colunas ausentes para agrupamento: {faltando}')

# Filtrar apenas linhas com consumo numérico válido
df_q5_valid = df_q5[df_q5['quantidade_fio_consumo'].notnull()].copy()
df_q5_valid['quantidade_fio_consumo'] = pd.to_numeric(df_q5_valid['quantidade_fio_consumo'], errors='coerce')

# Agrupar somando consumo e quantidade e preservando descrições (primeira ocorrência)
df_q5_group = (
    df_q5_valid.groupby(colunas_agrup, dropna=False)
    .agg(quantidade_fio_consumo_total=('quantidade_fio_consumo','sum'),
         quantidade_final_total=('quantidade_final','sum'),
         consumo_y_total=('consumo_y','sum'),
         linhas=('quantidade_fio_consumo','size'))
    .reset_index()
 )

# Ordenar
df_q5_group = df_q5_group.sort_values(colunas_agrup).reset_index(drop=True)
#===================================================================================================================================================
# Pivotamento adequado do df_q5_group para pedidos nas colunas e fios nas linhas
colunas_pivot = ['numero', 'descricao_mat', 'descricao_cor', 'quantidade_fio_consumo_total']
faltando_pivot = [c for c in colunas_pivot if c not in df_q5_group.columns]
if faltando_pivot:
    raise ValueError(f'Colunas ausentes para pivot: {faltando_pivot}')

pivot_src = df_q5_group[colunas_pivot].copy()

# Criar a tabela dinâmica (pivot)
pivot_tbl = (
    pivot_src.pivot_table(
        index=['descricao_mat', 'descricao_cor',],
        columns='numero',
        values='quantidade_fio_consumo_total',
        aggfunc='sum',
        fill_value=0
    )
 )

pivot_tbl.index.set_names(["descricao", "descricao_cor",], inplace=True)

# Somatório total por fio (todas as colunas de pedidos)
pivot_tbl['TOTAL_GERAL'] = pivot_tbl.sum(axis=1)

# Ordenar por maior TOTAL_GERAL
pivot_tbl = pivot_tbl.sort_values('TOTAL_GERAL', ascending=False)

# Resetar índice para voltar a ser dataframe "plano"
df_q5_pivot = pivot_tbl.reset_index()

# Garantir que TOTAL_GERAL fique ao final
cols = [c for c in df_q5_pivot.columns if c != 'TOTAL_GERAL'] + ['TOTAL_GERAL']
df_q5_pivot = df_q5_pivot[cols]
print(f"Pivot gerado: {df_q5_pivot.shape[0]} linhas x {df_q5_pivot.shape[1]} colunas (inclui TOTAL_GERAL).")


#===================================================================================================================================================

#===================================================================================================================================================

# ===============================================================================================================================================
# Integração: acrescentar (merge) do pivot de pedidos sem demanda (df_q5_pivot) ao df_final
# Requisitos: manter chaves de junção ['descricao','descricao_cor','codigo_tabela_cor'] e evitar colisão de nomes
# Estratégia: renomear todas as colunas de pedido e TOTAL_GERAL com prefixo 'SD_' e fazer merge left
try:
    if 'df_final' in globals() and isinstance(df_final, pd.DataFrame) and 'df_q5_pivot' in globals():
        chaves = ['descricao', 'descricao_cor']
        faltando_chaves_df_final = [c for c in chaves if c not in df_final.columns]
        faltando_chaves_pivot = [c for c in chaves if c not in df_q5_pivot.columns]
        if not faltando_chaves_df_final and not faltando_chaves_pivot:
            # Mapear colunas do pivot que serão renomeadas (todas exceto chaves)
            colunas_renomear = [c for c in df_q5_pivot.columns if c not in chaves]
            mapa = {}
            for c in colunas_renomear:
                if c == 'TOTAL_GERAL':
                    mapa[c] = 'SD_TOTAL_GERAL'
                else:
                    mapa[c] = f'SD_{c}'
            df_q5_pivot_pref = df_q5_pivot.rename(columns=mapa)


            # Guardar quais colunas novas serão adicionadas
            novas_colunas = list(mapa.values())

            # Realizar merge
            df_final = df_final.merge(df_q5_pivot_pref, on=chaves, how='left')

            # Preencher NaN das novas colunas numéricas com 0 (mantém object/string intacto)
            for col in novas_colunas:
                if col in df_final.columns:
                    if pd.api.types.is_numeric_dtype(df_final[col]):
                        df_final[col] = df_final[col].fillna(0)

            # (Opcional) poderíamos criar um total combinado incluindo SD_TOTAL_GERAL, mas não requisitado.
            # Re-salvar df_final atualizado no Mongo (sobrescrevendo a coleção existente)
            try:
                salvar_df_mongo(df_final, "boxer_df_final")
                print(f"df_final atualizado com {len(novas_colunas)} colunas de pedidos sem demanda (prefixo SD_) e re-salvo no Mongo.")
            except Exception as e:
                print(f"WARNING: falha ao re-salvar df_final atualizado: {e}")
        else:
            if faltando_chaves_df_final:
                print(f"WARNING: Chaves ausentes em df_final para merge: {faltando_chaves_df_final}")
            if faltando_chaves_pivot:
                print(f"WARNING: Chaves ausentes em df_q5_pivot para merge: {faltando_chaves_pivot}")
    else:
        print("WARNING: df_final ou df_q5_pivot não estão disponíveis para integração.")
except Exception as e:
    print(f"WARNING: erro inesperado ao integrar df_q5_pivot em df_final: {e}")
    
    


# ===============================================================================================================================================
# BLOCO FINAL ÚNICO DE SALVAMENTO NO MONGODB
# Todos os DataFrames relevantes serão salvos somente aqui, garantindo consistência do snapshot.
try:
    if db is not None:
        salvar_df_mongo(df_final, "boxer_df_final")
        #salvar_df_mongo(df_resultado, "boxer_df_resultado")
        #salvar_df_mongo(df_estoque, "boxer_df_estoque")
        #salvar_df_mongo(df_consumo_produtos, "boxer_df_consumo_produtos")
        #salvar_df_mongo(df_pedidos_setores_grupos, "boxer_df_pedidos_setores_grupos")
        #salvar_df_mongo(df_agrupado, "boxer_df_agrupado")
        #salvar_df_mongo(df_agrupado_consumo, "boxer_df_agrupado_consumo")
        #salvar_df_mongo(df_soma_consumo, "boxer_df_soma_consumo")
        # Novos referentes a pedidos sem demanda
        if 'df_q5_pivot' in globals():
            salvar_df_mongo(df_q5_pivot, "boxer_df_pedidos_sem_demanda_pivot")
        #if 'df_q4' in globals():
        #    salvar_df_mongo(df_q4, "boxer_df_pedidos_sem_demanda_q4_detalhe")
        #if 'df_q5_group' in globals():
        #    salvar_df_mongo(df_q5_group, "boxer_df_pedidos_sem_demanda_group")
        if 'df_q4_vazios' in globals():
            salvar_df_mongo(df_q4_vazios, "boxer_df_pedidos_sem_demanda_sem_resultado")
        print("Snapshot completo salvo no MongoDB com sucesso.")
    else:
        print("WARNING: Salvamento final pulado — conexão MongoDB indisponível.")
except Exception as e:
    print(f"WARNING: Falha no bloco final de salvamento: {e}")



