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


def _get_upload_path() -> str:
    """Resolve o caminho de entrada dos arquivos Excel, suportando Docker e Windows local."""
    if os.environ.get("RUNNING_IN_DOCKER") == "1":
        return '/app/data_base'
    # fallback local (mantém compatibilidade com versão anterior)
    return 'C:/Users/Fabrica-hoahi/Documents/Projetos_HOAHI_PY/Fios_meias_projeto_so_py/data_base'


def _listar_excels(pasta: str):
    try:
        return [f for f in os.listdir(pasta) if f.lower().endswith('.xlsx')]
    except Exception:
        return []


def _converter_data_mes_pt_es(valor):
    meses_es = {
        'ENERO': '01', 'FEBRERO': '02', 'MARZO': '03', 'ABRIL': '04',
        'MAYO': '05', 'JUNIO': '06', 'JULIO': '07', 'AGOSTO': '08',
        'SEPTIEMBRE': '09', 'OCTUBRE': '10', 'NOVIEMBRE': '11', 'DICIEMBRE': '12'
    }
    try:
        partes = str(valor).split()
        if len(partes) == 2 and partes[0].upper() in meses_es:
            mes, ano = partes
            return f'{ano}-{meses_es[mes.upper()]}-01'
        return valor
    except Exception:
        return valor


def processar_meia():
    """Processa os arquivos Excel e retorna os DataFrames consolidados.

    Retorna um dict:
    {
        'resultado_final': df,
        'dias_consumo': df,
        'consumo_diario': df_long,
        'entrada_diario': df_long_entrada or None
    }
    """
    upload_path = _get_upload_path()
    if not os.path.exists(upload_path):
        raise FileNotFoundError(f"Pasta '{upload_path}' não encontrada")

    excel_files = _listar_excels(upload_path)
    if not excel_files:
        # retorna vazios mas válidos
        return {
            'resultado_final': pd.DataFrame(),
            'dias_consumo': pd.DataFrame(),
            'consumo_diario': pd.DataFrame(),
            'entrada_diario': pd.DataFrame(),
        }

    dfs_por_mes = {}
    dias_consumo_por_mes = {}
    estoque_atual_por_produto = {}
    lista_consumo_diario = []
    lista_entrada_diario = []

    for file in excel_files:
        file_path = os.path.join(upload_path, file)
        try:
            df = pd.read_excel(file_path, header=None)
            header_row_index = -1
            for r_idx, row in df.iterrows():
                try:
                    if 'Titulo' in row.values and 'Color' in row.values:
                        header_row_index = r_idx
                        break
                except Exception:
                    continue
            if header_row_index == -1:
                continue

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
                    produto = row.get('Produto')
                    estoque = row.get(coluna_estoque_nome_real, 0)
                    if pd.notna(produto):
                        estoque_atual_por_produto[str(produto)] = float(0 if pd.isna(estoque) else estoque)

            # Consumo diário
            try:
                df_consumo_diario = pd.read_excel(file_path, sheet_name='Consumo_Diario')
                if 'Titulo' in df_consumo_diario.columns and 'Color' in df_consumo_diario.columns:
                    colunas_data = [col for col in df_consumo_diario.columns if col not in ['Titulo', 'Color']]
                    df_consumo_diario['Produto'] = df_consumo_diario['Titulo'].astype(str) + ' - ' + df_consumo_diario['Color'].astype(str)
                    contagem_dias = {}
                    for _, row in df_consumo_diario.iterrows():
                        produto = row['Produto']
                        dias_com_consumo = int(sum(pd.notna(row[col]) and row[col] > 0 for col in colunas_data))
                        contagem_dias[str(produto)] = dias_com_consumo
                    mes_nome = file.split('-')[1] if '-' in file else file.split('.')[0]
                    dias_consumo_por_mes[mes_nome] = contagem_dias
                    # formato longo
                    df_long = df_consumo_diario.melt(id_vars=['Produto'], value_vars=colunas_data, var_name='Data', value_name='Consumo')
                    df_long = df_long.dropna(subset=['Consumo'])
                    df_long = df_long[df_long['Consumo'] > 0]
                    lista_consumo_diario.append(df_long)
            except Exception:
                pass

            # Entradas diárias
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
            # ignora arquivo problemático e segue
            continue

    def consolidar_medias(dfs_por_mes):
        if not dfs_por_mes:
            return pd.DataFrame()
        resultado_final = list(dfs_por_mes.values())[0].copy()
        for _, dfm in list(dfs_por_mes.items())[1:]:
            resultado_final = pd.merge(resultado_final, dfm, on='Produto', how='outer')
        resultado_final = resultado_final.fillna(0)
        resultado_final = resultado_final.sort_values('Produto').reset_index(drop=True)
        return resultado_final

    def consolidar_dias(dias_consumo_por_mes):
        if not dias_consumo_por_mes:
            return pd.DataFrame()
        df_dias_consumo = pd.DataFrame(dias_consumo_por_mes).fillna(0)
        df_dias_consumo = df_dias_consumo.reset_index()
        df_dias_consumo.rename(columns={'index': 'Produto'}, inplace=True)
        df_dias_consumo = df_dias_consumo.sort_values('Produto').reset_index(drop=True)
        return df_dias_consumo

    resultado_final = consolidar_medias(dfs_por_mes)
    df_dias_consumo = consolidar_dias(dias_consumo_por_mes)

    # Cálculo de meses de cobertura
    if not resultado_final.empty and estoque_atual_por_produto:
        colunas_meses = [col for col in resultado_final.columns if col != 'Produto']
        resultado_final['Consumo_Medio_Mensal'] = resultado_final[colunas_meses].mean(axis=1)
        resultado_final['Consumo_Medio_Diario'] = resultado_final['Consumo_Medio_Mensal'] / 30
        resultado_final['Estoque_Atual'] = resultado_final['Produto'].map(estoque_atual_por_produto).fillna(0)
        resultado_final['Meses_Cobertura'] = np.where(
            resultado_final['Consumo_Medio_Diario'] > 0,
            (resultado_final['Estoque_Atual'] / resultado_final['Consumo_Medio_Diario']) / 30,
            np.inf
        )
        resultado_final['Meses_Cobertura'] = resultado_final['Meses_Cobertura'].replace(np.inf, 0)
        resultado_final['Meses_Cobertura'] = resultado_final['Meses_Cobertura'].round(2)
        resultado_final['Consumo_Medio_Mensal'] = resultado_final['Consumo_Medio_Mensal'].round(2)
        resultado_final['Consumo_Medio_Diario'] = resultado_final['Consumo_Medio_Diario'].round(4)

    # Consolidar diários
    df_consumo_diario = pd.concat(lista_consumo_diario, ignore_index=True) if lista_consumo_diario else pd.DataFrame()
    df_entrada_diario = pd.concat(lista_entrada_diario, ignore_index=True) if lista_entrada_diario else pd.DataFrame()

    # Normaliza datas para ISO yyyy-mm-dd
    if not df_consumo_diario.empty:
        df_consumo_diario['Data'] = df_consumo_diario['Data'].apply(_converter_data_mes_pt_es)
        df_consumo_diario['Data'] = pd.to_datetime(df_consumo_diario['Data'], errors='coerce')
        df_consumo_diario = df_consumo_diario.dropna(subset=['Data'])
        df_consumo_diario['Data'] = df_consumo_diario['Data'].dt.strftime('%Y-%m-%d')
    if not df_entrada_diario.empty:
        df_entrada_diario['Data'] = df_entrada_diario['Data'].apply(_converter_data_mes_pt_es)
        df_entrada_diario['Data'] = pd.to_datetime(df_entrada_diario['Data'], errors='coerce')
        df_entrada_diario = df_entrada_diario.dropna(subset=['Data'])
        df_entrada_diario['Data'] = df_entrada_diario['Data'].dt.strftime('%Y-%m-%d')

    return {
        'resultado_final': resultado_final,
        'dias_consumo': df_dias_consumo,
        'consumo_diario': df_consumo_diario,
        'entrada_diario': df_entrada_diario,
    }


# ---------------- Mongo helpers (similar ao Boxer) ----------------
try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None


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


def _get_mongo_client_and_db():
    if MongoClient is None:
        return None, None

    mongo_db = os.environ.get("MONGO_DB", "mydb")
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

    uri_candidates = _dedupe_uris(local_candidates + vm_candidates)
    last_error = None
    last_uri = None
    for uri in uri_candidates:
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            db = client[mongo_db]
            return client, db
        except Exception as e:
            last_error = e
            last_uri = uri

    if last_error:
        print(f"WARNING: Não foi possível conectar ao MongoDB em '{last_uri}': {last_error}")
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


def main():
    dados = processar_meia()
    client, db = _get_mongo_client_and_db()
    # Salva coleções principais
    salvar_df_mongo(db, dados.get('resultado_final'), 'meia_resultado_final')
    salvar_df_mongo(db, dados.get('dias_consumo'), 'meia_dias_consumo')
    salvar_df_mongo(db, dados.get('consumo_diario'), 'meia_consumo_diario')
    salvar_df_mongo(db, dados.get('entrada_diario'), 'meia_entrada_diario')
    print("Processamento MEIA concluído e dados salvos no MongoDB.")


if __name__ == '__main__':
    main()

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

#======================================================================================================================
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
print(df_consumo_produtos.columns.tolist())

#======================================================================================================================
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
print(df_pedidos_setores_grupos.columns.tolist())

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

#======================================================================================================================
# Lista dos fac_pedidos com consumo_total igual a 'sem consumo cadastrado' e agrupados por pedido
pedidos_sem_consumo = df_agrupado_consumo[df_agrupado_consumo['consumo_total'] == 'sem consumo cadastrado']
agrupados = pedidos_sem_consumo.groupby('fac_pedido').size().reset_index(name='quantidade_sem_consumo')

#======================================================================================================================
#devido a erros add força o formato de número na coluna consumo_total
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

#======================================================================================================================
# Agrupamento dos pedidos conforme setores e regras solicitadas

# Pedidos do setor 11 e 14 (inclui também os que estão no setor 18)
pedidos_11_14 = df_soma_consumo[df_soma_consumo['fac_op'].isin(['11', '14'])]
pedidos_10_13 = df_soma_consumo[df_soma_consumo['fac_op'].isin(['10', '13'])]
pedidos_11_14_10_13 = pd.concat([
    pedidos_11_14,
    pedidos_10_13[pedidos_10_13['fac_pedido'].isin(pedidos_11_14['fac_pedido'])]
])

# Pedidos exclusivamente no setor 18
pedidos_exclusivos_10_13 = pedidos_10_13[~pedidos_10_13['fac_pedido'].isin(pedidos_11_14['fac_pedido'])]
dfs_exclusivos_10_13 = {
    pedido: pedidos_exclusivos_10_13[pedidos_exclusivos_10_13['fac_pedido'] == pedido]
    for pedido in pedidos_exclusivos_10_13['fac_pedido'].unique()
}

# Pedidos do setor 01
pedidos_01 = df_soma_consumo[df_soma_consumo['fac_op'] == '01']
dfs_01 = {
    pedido: pedidos_01[pedidos_01['fac_pedido'] == pedido]
    for pedido in pedidos_01['fac_pedido'].unique()
}

# Exemplo de exibição dos resultados
print('Pedidos do setor 11 e 14 (incluindo os que também estão no 10 e 13):')


print('Pedidos exclusivamente do setor 10 e 13:')


print('Pedidos do setor 01:')


#======================================================================================================================
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
pivot_11_14_10_13 = pivotar_por_pedido(pedidos_11_14_10_13)
pivot_exclusivos_10_13 =  pivotar_por_pedido(pedidos_exclusivos_10_13)
pivot_01 = pivotar_por_pedido(pedidos_01) 
print('Pivot setor 11, 14, 10 e 13:')

print('Pivot pedidos exclusivos setor 10 e 13:')

print('Pivot pedidos setor 01:')
#======================================================================================================================

# Marca pedidos sem consumo cadastrado nas colunas dos pivots
def marcar_pedidos_sem_consumo(df_pivot, pedidos_sem_consumo):
    pedidos_lista = pedidos_sem_consumo['fac_pedido'].tolist()
    novas_colunas = []
    for col in df_pivot.columns:
        if col in pedidos_lista:
            novas_colunas.append(f'{col}*')
        else:
            novas_colunas.append(col)
    df_pivot.columns = novas_colunas
    return df_pivot

# Aplica a marcação nos pivots
pivot_11_14_10_13_marcado = marcar_pedidos_sem_consumo(pivot_11_14_10_13.copy(), agrupados)
pivot_exclusivos_10_13_marcado = marcar_pedidos_sem_consumo(pivot_exclusivos_10_13.copy(), agrupados)
pivot_01_marcado = marcar_pedidos_sem_consumo(pivot_01.copy(), agrupados)

print('Pivot setor 11, 14, 10 e 13 (com pedidos sem consumo marcados):')

print('Pivot pedidos exclusivos setor 10 e 13 (com pedidos sem consumo marcados):')

print('Pivot pedidos setor 01 (com pedidos sem consumo marcados):')
#======================================================================================================================
# 1. Merge do estoque com o pivot principal (setor 11, 14, 10 e 13)
df_resultado = pd.merge(
    df_estoque,
    pivot_11_14_10_13_marcado.reset_index(),
    left_on=['codigo', 'cor'],
    right_on=['material', 'cor_insumo'],
    how='left'
    )

# 2. Adiciona colunas dos pivots exclusivos do setor 10 e 13
for pedido in pivot_exclusivos_10_13_marcado.columns:
    df_pivot = pivot_exclusivos_10_13_marcado
    df_resultado[f'10_13_{pedido}'] = df_resultado.set_index(['material', 'cor_insumo']).index.map(
        lambda idx: df_pivot.at[idx, pedido] if idx in df_pivot.index else 0
    )

# 3. Soma dos consumos exclusivos do setor 10 e 13
colunas_10_13 = [f'10_13_{pedido}' for pedido in pivot_exclusivos_10_13_marcado.columns]
df_resultado['Soma_Consumo_10_13'] = df_resultado[colunas_10_13].sum(axis=1)

# 4. Adiciona colunas dos pivots do setor 01
for pedido in pivot_01_marcado.columns:
    df_pivot = pivot_01_marcado
    df_resultado[f'01_{pedido}'] = df_resultado.set_index(['material', 'cor_insumo']).index.map(
        lambda idx: df_pivot.at[idx, pedido] if idx in df_pivot.index else 0
    )

# 5. Soma dos consumos do setor 01
colunas_01 = [f'01_{pedido}' for pedido in pivot_01_marcado.columns]
df_resultado['Soma_Consumo_01'] = df_resultado[colunas_01].sum(axis=1)

# 6. Soma total dos consumos dos pedidos (todas as colunas de pedidos)
colunas_pedidos_11_14_10_13 = [col for col in pivot_11_14_10_13_marcado.columns if col not in ['material', 'cor_insumo']]
df_resultado['Soma_Consumo_11_14_10_13'] = df_resultado[colunas_pedidos_11_14_10_13].sum(axis=1)

df_resultado['Consumo_Total_Pedidos'] = (
    df_resultado['Soma_Consumo_11_14_10_13'] +
    df_resultado['Soma_Consumo_10_13'] +
    df_resultado['Soma_Consumo_01']
)

# 7. Última coluna: estoque atual descontado dos consumos
df_resultado['Estoque_Descontado'] = df_resultado['estoque_total'] - df_resultado['Consumo_Total_Pedidos']

# 8. Seleciona as colunas finais
colunas_finais = (
    ['descricao', 'descricao_cor', 'codigo_tabela_cor', 'estoque_total'] +
    colunas_pedidos_11_14_10_13 + ['Soma_Consumo_11_14_10_13'] +
    colunas_10_13 + ['Soma_Consumo_10_13'] +
    colunas_01 + ['Soma_Consumo_01'] +
    ['Consumo_Total_Pedidos', 'Estoque_Descontado']
)
df_final = df_resultado[colunas_finais]
# Salva df_final na coleção esperada pelo dashboard (meia_df_final)
try:
    client2, db2 = _get_mongo_client_and_db()
    salvar_df_mongo(db2, df_final, "meia_df_final")
    print("meia_df_final salvo no MongoDB.")
except Exception as e:
    print(f"WARNING: falha ao salvar meia_df_final: {e}")
