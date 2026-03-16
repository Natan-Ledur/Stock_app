import os
import platform
import sys
from datetime import datetime
import pandas as pd

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

def _get_configured_uri():
    """Retorna a URI do MongoDB ajustada para o ambiente (Docker vs Local/Windows)."""
    _uri = os.getenv('MONGO_URI')
    
    # Fallback padrão para setup local Docker/Windows se não definido
    if not _uri:
        _uri = 'mongodb://appuser:apppass@mongodb2:27018/stock_app?authSource=stock_app'

    # Ajuste Windows/Compass
    if platform.system() == 'Windows':
        _compass = os.getenv('MONGO_URI_COMPASS')
        if _compass:
            _uri = _compass
        elif _uri and 'mongodb2:27017' in _uri:
            # Fallback para rodar fora do Docker no Windows sabendo o mapa de portas
            _uri = _uri.replace('mongodb2:27017', 'localhost:27018')
            
    return _uri

def get_mongo_client(server_timeout_ms=3000):
    """Retorna cliente MongoDB conectado ou None se falhar."""
    uri = _get_configured_uri()
    if not uri or not MongoClient:
        return None
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=server_timeout_ms)
        # Check connection cheaply
        client.admin.command('ping')
        return client
    except Exception as e:
        print(f"Erro ao conectar ao Mongo ({uri}): {e}")
        return None

def get_database(db_name=None):
    """Retorna conexão com o database padrão configurado."""
    client = get_mongo_client()
    if not client:
        return None
    default_db = os.getenv('MONGO_DB', 'stock_app')
    target_db = db_name or default_db
    return client[target_db]

# Globais legacy (para não quebrar imports que usam MONGO_DB)
MONGO_DB = os.getenv('MONGO_DB', 'stock_app')
MONGO_COLLECTION = os.getenv('MONGO_COLLECTION', 'dataframes')


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    # Garant tipos serializáveis ​​em JSON
    df2 = df.copy()
    df2 = df2.where(pd.notnull(df2), None)
    for col in df2.columns:
        try:
            df2[col] = df2[col].apply(lambda v: v.item() if hasattr(v, 'item') else v)
        except Exception:
            pass
    return df2


def save_dataframe(df: pd.DataFrame, username: str = None, description: str = None, token: str = None):
    """Save a DataFrame to MongoDB with metadata."""
    try:
        df2 = _normalize_dataframe(df)
        records = df2.to_dict('records')
    except Exception as e:
        return {'ok': False, 'error': f'error_serializing_dataframe: {e}'}

    doc = {
        'username': username,
        'description': description,
        'timestamp': datetime.utcnow(),
        'count': len(records),
        'columns': list(df.columns),
        'records': records,
        'token_present': bool(token),
    }

    try:
        client = get_mongo_client()
        if client is None:
             return {'ok': False, 'error': 'mongodb_connection_failed'}
        db = client[MONGO_DB]
        coll = db[MONGO_COLLECTION]
        res = coll.insert_one(doc)
        return {'ok': True, 'id': str(res.inserted_id)}
    except ImportError as e:
        return {'ok': False, 'error': 'pymongo_not_installed'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
