# Bibliotecas necesarias
import os
import sys
import datetime
import pandas as pd
import logging
#import pyodbc
from datetime import datetime, date

# Configuração de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import psycopg2
from contextlib import contextmanager

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, message="pandas only supports SQLAlchemy")
#============================================================================================================================
# Carrega .env próximo (compatível com execução direta deste script)
try:
    from dotenv import load_dotenv, find_dotenv
except Exception:
    load_dotenv = None
    find_dotenv = None

if find_dotenv:
    dotenv_path = find_dotenv()
    if not dotenv_path:
        # fallback para frontend/.env (subindo três níveis a partir de frontend/app/Boxer)
        fallback = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
        if os.path.exists(fallback):
            dotenv_path = fallback
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        # última tentativa
        if load_dotenv:
            load_dotenv()


try:
    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from mongo_utils import get_mongo_client
except Exception:
    get_mongo_client = None

#============================================================================================================================
## conexão com o MongoDB


def _get_mongo_client_and_db():
    """Estabelece conexão com o MongoDB usando o utilitário central local-first."""
    if get_mongo_client is None:
        logging.warning("Não foi possível importar mongo_utils.get_mongo_client.")
        return None, None

    mongo_db = os.environ.get("MONGO_DB", "mydb")
    try:
        client = get_mongo_client(server_timeout_ms=5000)
        if client is None:
            return None, None
        return client, client[mongo_db]
    except Exception as e:
        logging.warning(f"Erro ao conectar no MongoDB: {e}")
        return None, None

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nomes de colunas: minúsculo, sem espaços e sem acentos básicos."""
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(' ', '_', regex=False)
    )
    return df

def salvar_df_mongo(db, df: pd.DataFrame, nome_colecao: str, historico: bool = False):
    """Salva um DataFrame no MongoDB convertendo datas e limpando NaNs."""
    if db is None or df is None or df.empty:
        return

    try:
        # 1. Normalização de colunas
        df_proc = _normalize_columns(df)
        
        # 2. Conversão de tipos incompatíveis (Date e Timestamp -> Datetime)
        # Convertemos tudo que é data para datetime padrão do Python
        for col in df_proc.columns:
            # Se for datetime do pandas (Timestamp), converte para datetime nativo
            if pd.api.types.is_datetime64_any_dtype(df_proc[col]):
                df_proc[col] = df_proc[col].apply(lambda x: x.to_pydatetime() if pd.notnull(x) else None)
            
            # Se forem objetos (como o datetime.date do seu erro), converte para datetime
            elif df_proc[col].dtype == 'object':
                df_proc[col] = df_proc[col].apply(
                    lambda x: datetime.combine(x, datetime.min.time()) if isinstance(x, date) and not isinstance(x, datetime) else x
                )

        # 3. Tratar NaNs/Nulos (converte para None que o Mongo aceita como null)
        df_proc = df_proc.where(pd.notnull(df_proc), None)
        
        # 4. Adicionar data de atualização
        df_proc['data_atualizacao'] = datetime.now()
        
        # 5. Se houver uma coluna '_id' vinda do merge, o Mongo pode dar erro se ela já existir.
        # É mais seguro remover o '_id' para que o Mongo gere um novo ou atualize.
        if '_id' in df_proc.columns:
            df_proc = df_proc.drop(columns=['_id'])

        registros = df_proc.to_dict('records')

        # 6. Operação no banco
        col = db[nome_colecao]
        col.delete_many({}) 
        if registros:
            col.insert_many(registros)

        if historico and registros:
            db[f"{nome_colecao}_historico"].insert_many(registros)

    except Exception as e:
        print(f"WARNING: Erro ao salvar coleção {nome_colecao}: {e}")
        
#============================================================================================================================
## conexão com o Postgres - modo leitura
@contextmanager
def obter_conexao():
    """Gerenciador de contexto para garantir que a conexão sempre feche."""
    conn = None
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_SERVER'),
            database=os.getenv('DB_DATABASE'),
            user=os.getenv('DB_USERNAME'),
            password=os.getenv('DB_PASSWORD'),
            port=os.getenv('DB_PORT', 5432) # Porta padrão do Postgres
        )
        # Configura a conexão para modo APENAS LEITURA a nível de sessão
        conn.set_session(readonly=True, autocommit=True)
        yield conn
    except Exception as e:
        print(f"Erro na conexão com Postgres: {e}")
        raise
    finally:
        if conn:
            conn.close()
#============================================================================================================================
def consulta_estoque_atual(grupo='02', deposito='2001'):
    caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/Orig_Consulta estoque.sql')    
    try:
        with open(caminho_sql, 'r', encoding='utf-8') as f:
            query = f.read()

        # Preenche os parâmetros
        query = query.replace(':GRUPO', f"'{grupo}'")
        query = query.replace(':DEPOSITO', f"'{deposito}'")

        # Executa usando o gerenciador de contexto
        with obter_conexao() as conn:
            df = pd.read_sql(query, conn)
        return df
        
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_sql}' não foi encontrado.")
        return pd.DataFrame()
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return pd.DataFrame()

# Executa e mostra o resultado
df_estoque = consulta_estoque_atual()

#============================================================================================================================
# 3.3 Consulta e armazenamento das informações de consumo de material por produto (todas as colunas)
def consulta_consumo_fios():
    caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/consumos_fios.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    with obter_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_consumo_fios = consulta_consumo_fios()

#============================================================================================================================
# 3. Consulta e armazenamento das informações de consumo etiqueta 01
def consulta_consumo_etiqueta_01():
    caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/222.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    with obter_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_et01= consulta_consumo_etiqueta_01()

def processar_tamanhos_etiqueta_01(df):
    """Expande tamanho 'U' para P, M, G, GG e remove duplicatas."""
    if df.empty: return df
    df = df.drop_duplicates().copy()
    # preserve o valor original em faixa2
    df['faixa2'] = df['faixa']
    
    df['faixa'] = df['faixa'].apply(lambda x: ['P','M','G','GG'] if x == 'U' else x)
    df = df.explode('faixa')
    return df.drop_duplicates().reset_index(drop=True)

# Processa o DataFrame
df_et01 = processar_tamanhos_etiqueta_01(df_et01)

#============================================================================================================================
# 4.1 Consulta usando apenas o SQL puro do 3011.sql
def consulta_3011():
    caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/3011.sql')
    with open(caminho_sql, 'r', encoding='utf-8') as f:
        query = f.read()
    with obter_conexao() as conn:
        df = pd.read_sql(query, conn)
    return df

# Executa a consulta e armazena em um DataFrame
df_pedidos_setores_grupos = consulta_3011()

#============================================================================================================================
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

#============================================================================================================================
# Execução simples da query Q1 e armazenamento em DataFrame


caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/Q1_1002_acesso.sql')
with open(caminho_sql, 'r', encoding='utf-8') as f:
    query = f.read()

with obter_conexao() as conn:
    df_q1 = pd.read_sql_query(query, conn)

#============================================================================================================================
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

    with obter_conexao() as conn:
        df_q2 = pd.read_sql_query(query, conn)

    # Normalizar para DataFrame 'pedidos_com_resultados' com a coluna 'numero'
    cols = {c.lower(): c for c in df_q2.columns}
    base_col = cols['pedido'] if 'pedido' in cols else (cols['numero'] if 'numero' in cols else None)
    if base_col is None or df_q2.empty:
        pedidos_com_resultados = pd.DataFrame(columns=['numero'])
    else:
        s = df_q2[base_col].astype(str).str.strip()
        s = s[s != ''].dropna().unique()
        pedidos_com_resultados = pd.DataFrame({'numero': s})
        
#============================================================================================================================

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

#============================================================================================================================
# Q3: Para cada pedido em df_sem_demanda, obter itens comerciais (Q3_1002_itempedido.sql)
caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/qtd.sql')
with open(caminho_sql, 'r', encoding='utf-8') as f:
    query_q3_template = f.read()

# Assumindo que df_sem_demanda existe e possui a coluna 'numero'
pedidos = df_sem_demanda['numero'].astype(str).str.strip().dropna().unique().tolist() # caso queira conferir troque aqui a lista de pedidos que seram calculados os consumos!!!!

if not pedidos:
    df_q3v2 = pd.DataFrame()
else:
    # Otimização: Consulta em lote usando IN
    sel = ','.join([f"'{str(p).replace('\'', '\'\'')}'" for p in pedidos])
    query = query_q3_template.replace(':sel', sel)
    
    try:
        with obter_conexao() as conn:
            df_q3v2 = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"Erro na consulta Q3 em lote: {e}")
        df_q3v2 = pd.DataFrame()
        
    # Garantir coluna numero como string se vier do banco com outro tipo ou nome diferente
    if not df_q3v2.empty and 'numero' in df_q3v2.columns:
         df_q3v2['numero'] = df_q3v2['numero'].astype(str).str.strip()

# Se por acaso o SQL não estivesse retornando numero, teríamos problemas pois não saberíamos qual linha é de qual pedido.
# Ajustamos o SQL qtd.sql para retornar 'pi.numero as numero'.

#============================================================================================================================

# Para cada linha de df_q3, buscar correspondência em df_et01 (código, cor, tam)
# Se encontrar, concatenar as informações; se não, armazenar em df_sem_corresp


# Garantir que os tipos e espaços estejam padronizados
for col in ['codigo', 'cor_i', 'faixa']:
    df_q3v2[col] = df_q3v2[col].astype(str).str.strip()
    df_et01[col] = df_et01[col].astype(str).str.strip()

# Realizar o merge (inner para correspondentes, left_anti para não correspondentes)
df_merged = pd.merge(df_q3v2, df_et01, on=['codigo','cor','cor_i', 'faixa'], how='inner', suffixes=('', '_et01'))
df_sem_corresp = pd.merge(df_q3v2, df_et01, on=['codigo', 'cor', 'cor_i', 'faixa'], how='left', indicator=True)
df_sem_corresp = df_sem_corresp[df_sem_corresp['_merge'] == 'left_only'].drop(columns=['_merge'])

#============================================================================================================================
# pesquisa dos consumos de fios, É a mesma logica usada entre o df-q3 e o df_et01(bem simples)!

df_merged2 = df_merged.rename(columns={
    'insumo': 'produto', 
    'cor_i': 'cor_prod',
    'faixa': 'tam'    
})

df_merged2= pd.merge(df_merged2,df_consumo_fios, on=['produto','cor_prod','tam'], how='inner', suffixes=('', '_fios'))

#============================================================================================================================
# Multiplicar quantidade_final por consumo_fios e criar coluna consumo_total

required_cols = ['qtde_por_cor', 'consumo']
missing = [c for c in required_cols if c not in df_merged2.columns]
if missing:
    raise ValueError(f"Colunas ausentes em df_merged2: {missing}")

# Garantir que ambas sejam numéricas (NaN -> 0)
df_merged2['qtde_por_cor'] = pd.to_numeric(df_merged2['qtde_por_cor'], errors='coerce').fillna(0)
df_merged2['consumo'] = pd.to_numeric(df_merged2['consumo'], errors='coerce').fillna(0)

# Consumo total de fios por linha
df_merged2['consumo_total'] = df_merged2['qtde_por_cor'] * df_merged2['consumo']
# Adicionar coluna 'setor' com valor fixo 'SD'
df_merged2['setor'] = 'SD'

#============================================================================================================================
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
df_boxer_cof = df_agrupado_consumo[colunas_usar].rename(columns=colunas_renomear_cd)

#============================================================================================================================
# Selecionar e renomear as colunas do DataFrame df_merged2 conforme solicitado
colunas_renomear_sd = {
    'setor' : 'setor' ,
    'numero': 'pedido',
    'codigo' : 'codigo' ,
    'cor' : 'cor' ,
    'faixa2' : 'tamanho' ,
    'qtde_por_cor' : 'quantidade',
    'material' : 'material_cod',
    'cor_insumo' : 'cor_cod',
    'codigo2' : 'codigo2',
    'descricao_cor' : 'descricao_cor',
    'descricao_mat': 'descricao_mat',
    'consumo' : 'consumo',
    'consumo_total' : 'consumo_total'    
}

# Selecionar apenas as colunas desejadas
colunas_usar = list(colunas_renomear_sd.keys())
df_boxer_sof = df_merged2[colunas_usar].rename(columns=colunas_renomear_sd)

#============================================================================================================================
# Selecionar e renomear as colunas do DataFrame df_sem_corresp conforme solicitado
colunas_renomear_sdsc = {
    'setor' : 'setor' ,
    'numero': 'pedido',
    'codigo' : 'codigo' ,
    'cor' : 'cor' ,
    'faixa2' : 'tamanho' ,
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
df_boxer_sofsc = df_sem_corresp[colunas_usar].rename(columns=colunas_renomear_sdsc)

#============================================================================================================================
# Concatenar os DataFrames padronizados
df_boxer_final = pd.concat([df_boxer_cof, df_boxer_sof, df_boxer_sofsc], ignore_index=True)

#============================================================================================================================

# Executar uma query de arquivo SQL e carregar em um DataFrame
# escolher o arquivo SQL (prefere 1602_01_r.sql, senão usa 1602_02_reduced.sql)
caminho_sql = os.path.join(os.path.dirname(__file__), 'SQLs/1602_01_r.sql')
with open(caminho_sql, 'r', encoding='utf-8') as f:
    sql = f.read()
# abrir conexão e executar
conn = None
try:
    with obter_conexao() as conn:
        df_1602_01 = pd.read_sql_query(sql, conn)
        logging.info(f"df_1602_01 carregado: {df_1602_01.shape[0]} linhas x {df_1602_01.shape[1]} colunas")
        # mostrar as primeiras linhas
    
except Exception as e:
    logging.error(f"Erro ao executar a query: {e}")
    df_1602_01 = None
finally:
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass

# variável 'df' contém o resultado (ou None em caso de erro)

#============================================================================================================================
# Para cada NUMERO no df_1602_01, executar a query reduzida (1602_02_r.sql) substituindo :numero

# localizar arquivo SQL reduzido
caminho_sql_02 = os.path.join(os.path.dirname(__file__), 'SQLs/1602_02_r.sql')
with open(caminho_sql_02, 'r', encoding='utf-8') as f:
    sql_02_template = f.read()

# Verifica se df_1602_01 existe e tem a coluna 'NUMERO' (caso sensível)
df_1602_02 = None
if 'df_1602_01' not in globals() or df_1602_01 is None:
    print("df_1602_01 não encontrado. Execute a célula anterior para carregar df_1602_01.")
else:
    if 'numero' not in df_1602_01.columns:
        # Tentar com lowercase/upper
        possible = [c for c in df_1602_01.columns if c.lower() == 'numero']
        if possible:
            df_1602_01 = df_1602_01.rename(columns={possible[0]: 'numero'})
        else:
            raise KeyError("Coluna 'NUMERO' não encontrada em df_1602_01")
            
    # preparar lista de numeros (converter para str e remover NaN)
    numeros = df_1602_01['numero'].dropna().unique().tolist()
    # se já estiverem numéricos, converte para int e depois para string sem espaços
    numeros = [str(int(x)) if (not isinstance(x, str) and pd.notna(x)) else str(x).strip() for x in numeros]
    
    if not numeros:
        df_1602_02 = pd.DataFrame()
    else:
        # Otimização: Consulta em lote
        # Formata lista para IN ('N1', 'N2', ...)
        valor_sql = ','.join([f"'{n}'" for n in numeros])
        sql_exec = sql_02_template.replace(':numero', valor_sql) # :numero aqui recebe a lista inteira
        
        try:
            with obter_conexao() as conn:
                df_1602_02 = pd.read_sql_query(sql_exec, conn)
                
            if df_1602_02 is not None and not df_1602_02.empty:
               # Normalizar colunas para garantir join correto. A coluna NUMERO foi adicionada ao SQL.
               df_1602_02.columns = [c.lower() for c in df_1602_02.columns]
               if 'numero' in df_1602_02.columns:
                   df_1602_02['numero'] = df_1602_02['numero'].astype(str).str.strip()
                   
        except Exception as e:
            logging.error(f"Erro executando consulta 1602 em lote: {e}")
            df_1602_02 = pd.DataFrame()

    logging.info(f"df_1602_02 carregado: {df_1602_02.shape[0]} linhas x {df_1602_02.shape[1]} colunas")
    

# Mesclar df_1602_01 com os resultados (left join por NUMERO)
if df_1602_02 is not None and not df_1602_02.empty:
    df_1602_01_local = df_1602_01.copy()
    # garantir strings para chave de merge
    df_1602_01_local['numero'] = df_1602_01_local['numero'].astype(str)
    df_1602_02['numero'] = df_1602_02['numero'].astype(str)
    df_1602_merged = pd.merge(df_1602_01_local, df_1602_02, on='numero', how='left', suffixes=('_orig','_res'))
    print(f"df_1602_merged: {df_1602_merged.shape[0]} linhas x {df_1602_merged.shape[1]} colunas")
else:
    print("Nenhum resultado para mesclar.")
    
#============================================================================================================================
# Verificação de segurança
if 'df_1602_merged' in globals() and df_1602_merged is not None and not df_1602_merged.empty:
    
    # 1. Obtém a conexão usando a função auxiliar
    client, db = _get_mongo_client_and_db()
    
    if db is not None:
        try:
            # 2. Define o nome da coleção
            nome_colecao = 'compras_fios'
            
            # 3. Salva os dados (a função já faz: normalização, delete_many, insert e data_atualizacao)
            # Se quiser manter histórico, mude para historico=True
            salvar_df_mongo(db, df_1602_merged, nome_colecao, historico=False)
            
            logging.info(f"Processo concluído: '{nome_colecao}' atualizado no MongoDB.")
            
        finally:
            # 4. Garante o fechamento da conexão
            client.close()
    else:
        print("❌ Não foi possível prosseguir: Erro na conexão com o MongoDB.")
else:
    print("⚠️ df_1602_merged está vazio ou não existe. Nada foi salvo.")
    
#============================================================================================================================
# Salva df_final na coleção esperada pelo dashboard (AJUSTAR)
try:
    client2, db2 = _get_mongo_client_and_db()
    salvar_df_mongo(db2, df_boxer_final, "boxer_pedido_consumos")
    print("boxer_pedido_consumos salvo no MongoDB.")
except Exception as e:
    print(f"WARNING: falha ao salvar boxer_pedido_consumos: {e}")
    

    
try:
    client2, db2 = _get_mongo_client_and_db()
    salvar_df_mongo(db2, df_estoque, "boxer_estoque")
    print("boxer_estoque salvo no MongoDB.")
except Exception as e:
    print(f"WARNING: falha ao salvar boxer_estoque: {e}")
    