import os
import platform
import socket
import sys
from datetime import datetime
from urllib.parse import parse_qsl, quote_plus, unquote_plus, urlencode, urlsplit, urlunsplit
import pandas as pd

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

try:
    from dotenv import load_dotenv, find_dotenv
except Exception:
    load_dotenv = None
    find_dotenv = None


_DOTENV_LOADED = False


def _load_dotenv_once():
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    if not load_dotenv:
        return

    dotenv_path = ""
    try:
        if find_dotenv:
            dotenv_path = find_dotenv()
    except Exception:
        dotenv_path = ""

    if not dotenv_path:
        fallback = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
        if os.path.exists(fallback):
            dotenv_path = fallback

    try:
        if dotenv_path:
            load_dotenv(dotenv_path)
        else:
            load_dotenv()
    except Exception:
        pass


def _dedupe(values):
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _is_local_uri(uri: str) -> bool:
    if not uri:
        return False
    uri_lower = uri.lower()
    return ('localhost' in uri_lower) or ('127.0.0.1' in uri_lower) or ('::1' in uri_lower)


def _set_auth_source(uri: str, auth_source: str) -> str:
    try:
        parts = urlsplit(uri)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query['authSource'] = auth_source
        new_query = urlencode(query, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    except Exception:
        return uri


def _auth_source_variants(uri: str, db_name: str):
    candidates = [uri]
    configured_auth = os.getenv('MONGO_AUTH_SOURCE')
    for auth_source in (configured_auth, 'admin', db_name):
        if auth_source:
            candidates.append(_set_auth_source(uri, auth_source))
    return _dedupe(candidates)


def _escape_credential(value: str) -> str:
    if value is None:
        return value
    try:
        # Normaliza tanto valor cru quanto já percent-encoded.
        return quote_plus(unquote_plus(value))
    except Exception:
        return value


def _extract_host_port(uri: str):
    try:
        parts = urlsplit(uri)
        netloc = parts.netloc.rsplit('@', 1)[-1]
        if netloc.startswith('['):
            end = netloc.find(']')
            if end == -1:
                return None, None
            host = netloc[1:end]
            rest = netloc[end + 1:]
            port = int(rest[1:]) if rest.startswith(':') else 27017
            return host, port
        if ':' in netloc:
            host, port_text = netloc.rsplit(':', 1)
            return host, int(port_text)
        return netloc, 27017
    except Exception:
        return None, None


def _is_local_host(host: str) -> bool:
    if not host:
        return False
    h = host.lower()
    return h in ('localhost', '127.0.0.1', '::1')


def _is_host_port_open(host: str, port: int, timeout_s: float = 0.2) -> bool:
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_s):
            return True
    except Exception:
        return False


def _order_candidates_by_reachability(local_candidates, vm_candidates):
    """Ordena local-first quando local está acessível; evita insistir em localhost fechado."""
    local_reachable = []
    local_unreachable = []
    for uri in _dedupe(local_candidates):
        host, port = _extract_host_port(uri)
        if _is_local_host(host):
            if _is_host_port_open(host, port):
                local_reachable.append(uri)
            else:
                local_unreachable.append(uri)
        else:
            local_reachable.append(uri)

    # Se localhost estiver fechado, tenta VM antes de voltar nas URIs locais indisponíveis.
    return _dedupe(local_reachable + vm_candidates + local_unreachable)


def _build_uri_candidates():
    db_name = os.getenv('MONGO_DB', 'stock_app')
    user = os.getenv('MONGO_USER', os.getenv('MONGO_INITDB_ROOT_USERNAME', 'user'))
    password = os.getenv('MONGO_PASS', os.getenv('MONGO_INITDB_ROOT_PASSWORD', 'password'))

    mongo_uri = os.getenv('MONGO_URI')
    mongo_uri_local = os.getenv('MONGO_URI_LOCAL')
    mongo_uri_vm = os.getenv('MONGO_URI_VM') or os.getenv('MONGO_URI_REMOTE')
    mongo_uri_compass = os.getenv('MONGO_URI_COMPASS')
    mongo_host = os.getenv('MONGO_HOST')

    local_host = os.getenv('MONGO_LOCAL_HOST', 'localhost')
    local_port = os.getenv('MONGO_LOCAL_PORT', '27017')
    user_esc = _escape_credential(user)
    password_esc = _escape_credential(password)

    local_candidates = []
    vm_candidates = []

    if mongo_uri_local:
        local_candidates.append(mongo_uri_local)
    if mongo_uri_compass:
        local_candidates.append(mongo_uri_compass)
    if mongo_uri and _is_local_uri(mongo_uri):
        local_candidates.append(mongo_uri)

    if user_esc and password_esc:
        local_candidates.append(f'mongodb://{user_esc}:{password_esc}@{local_host}:{local_port}/{db_name}')
        if platform.system().lower().startswith('windows'):
            local_candidates.append(f'mongodb://{user_esc}:{password_esc}@{local_host}:27018/{db_name}')

    if mongo_uri and 'mongodb2:27017' in mongo_uri:
        local_candidates.append(mongo_uri.replace('mongodb2:27017', 'localhost:27018'))

    if mongo_host and user_esc and password_esc:
        host_uri = f'mongodb://{user_esc}:{password_esc}@{mongo_host}:27017/{db_name}'
        if mongo_host.lower() in ('localhost', '127.0.0.1', 'mongodb2'):
            local_candidates.append(host_uri)
        else:
            vm_candidates.append(host_uri)

    if mongo_uri_vm:
        vm_candidates.append(mongo_uri_vm)
    if mongo_uri and not _is_local_uri(mongo_uri):
        vm_candidates.append(mongo_uri)

    base_candidates = _order_candidates_by_reachability(local_candidates, _dedupe(vm_candidates))

    expanded = []
    for uri in base_candidates:
        expanded.extend(_auth_source_variants(uri, db_name))

    return _dedupe(expanded)

def get_mongo_client(server_timeout_ms=3000):
    """Retorna cliente MongoDB conectado ou None se falhar.

    Ordem de tentativa: local -> VM, com variações de authSource.
    """
    _load_dotenv_once()

    if not MongoClient:
        return None

    uri_candidates = _build_uri_candidates()
    if not uri_candidates:
        return None

    last_error = None
    last_uri = None
    for uri in uri_candidates:
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=server_timeout_ms)
            client.admin.command('ping')
            return client
        except Exception as e:
            last_error = e
            last_uri = uri

    if last_error:
        print(f"Erro ao conectar ao Mongo ({last_uri}): {last_error}")
    return None

def get_mongo_client_with_retry(server_timeout_ms=3000, max_retries=3):
    """Retorna cliente MongoDB com retry exponencial.

    Útil para Streamlit onde o cache pode ser inicializado
    enquanto o servidor está iniciando.
    """
    import time
    for attempt in range(max_retries):
        try:
            client = get_mongo_client(server_timeout_ms=server_timeout_ms)
            if client is not None:
                return client
        except Exception:
            pass

        if attempt < max_retries - 1:
            wait_time = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s
            time.sleep(wait_time)

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
