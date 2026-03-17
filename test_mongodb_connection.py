#!/usr/bin/env python
"""
Script de diagnóstico para testar a conexão ao MongoDB e validar se os dashboards conseguem conectar.
Use este script para verificar se os erros foram corrigidos.

Uso: python test_mongodb_connection.py
"""

import sys
import os

# Adiciona o diretório app ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from mongo_utils import (
    get_mongo_client,
    get_mongo_client_with_retry,
    get_database,
    _build_uri_candidates
)


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def test_mongo_direct():
    """Testa conexão direta ao MongoDB"""
    print_section("1. TESTE DE CONEXÃO DIRETA")

    print("\nURIs que serão testadas (em ordem):")
    candidates = _build_uri_candidates()
    for i, uri in enumerate(candidates[:5], 1):  # Mostra apenas as primeiras 5
        display_uri = uri[:70] + '...' if len(uri) > 70 else uri
        print(f"  {i}. {display_uri}")
    if len(candidates) > 5:
        print(f"  ... e mais {len(candidates) - 5} URIs")

    print("\nTentando conectar sem retry...")
    client = get_mongo_client(server_timeout_ms=3000)

    if client:
        print("[OK] SUCESSO: Conexao direta estabelecida")
        try:
            server_info = client.server_info()
            print(f"  - Versão MongoDB: {server_info.get('version', 'desconhecida')}")
        except:
            pass
        return client
    else:
        print("[FAIL] FALHA: Não conseguiu conectar diretamente")
        return None


def test_mongo_with_retry():
    """Testa conexão com retry exponencial"""
    print_section("2. TESTE COM RETRY EXPONENCIAL")

    print("\nTestando get_mongo_client_with_retry (máx 3 tentativas, backoff: 0.5s, 1s, 2s)...")
    client = get_mongo_client_with_retry(max_retries=3)

    if client:
        print("[OK] SUCESSO: Cliente conectado com retry")
        return client
    else:
        print("[FAIL] FALHA: Retry não conseguiu conectar")
        return None


def test_database_access(client):
    """Testa acesso ao banco de dados"""
    print_section("3. TESTE DE ACESSO AO BANCO DE DADOS")

    if client is None:
        print("[SKIP] PULADO: Cliente não disponível")
        return False

    try:
        db = client['stock_app']
        collections = db.list_collection_names()
        print(f"[OK] SUCESSO: Banco 'stock_app' acessível")
        print(f"\nColecoes disponíveis ({len(collections)} total):")

        for col_name in sorted(collections):
            count = db[col_name].count_documents({})
            print(f"  - {col_name}: {count:,} documentos")

        return True
    except Exception as e:
        print(f"[FAIL] FALHA: {e}")
        return False


def test_get_database():
    """Testa função get_database()"""
    print_section("4. TESTE DE FUNÇÃO get_database()")

    print("Testando get_database()...")
    db = get_database()

    if db is not None:
        print("[OK] SUCESSO: Função get_database() retornou database")
        try:
            count = db['boxer_pedido_consumos'].count_documents({})
            print(f"  - Amostra: boxer_pedido_consumos tem {count:,} documentos")
        except:
            pass
        return True
    else:
        print("[FAIL] FALHA: Função get_database() retornou None")
        return False


def test_streamlit_cache():
    """Testa comportamento esperado no Streamlit (cache simulation)"""
    print_section("5. TESTE DE SIMULAÇÃO STREAMLIT CACHE")

    print("Simulando comportamento com cache do Streamlit...")
    print("  1. Primeira chamada (primeira renderização):")
    client = get_mongo_client_with_retry(max_retries=3)
    if client:
        print("     [OK] Cache conseguiu conectar")
        status1 = "OK"
    else:
        print("     [FAIL] Cache falhou ao conectar")
        status1 = "FALHA"

    print("  2. Segunda chamada (rerun):")
    client2 = get_mongo_client_with_retry(max_retries=3)
    if client2:
        print("     [OK] Cache reutilizado com sucesso")
        status2 = "OK"
    else:
        print("     [FAIL] Cache perdido ou conexão falhou")
        status2 = "FALHA"

    return status1 == "OK" and status2 == "OK"


def main():
    print_section("DIAGNÓSTICO DE CONEXÃO MONGODB")
    print("\nEste script testa todos os aspéctos da conexão ao MongoDB")
    print("e simula o comportamento esperado nos dashboards Streamlit.")

    results = []

    # Teste 1: Conexão direta
    client = test_mongo_direct()
    results.append(("Conexão Direta", client is not None))

    # Teste 2: Com retry
    client_retry = test_mongo_with_retry()
    results.append(("Retry Exponencial", client_retry is not None))

    # Teste 3: Acesso a banco
    if client_retry:
        test_database_access(client_retry)
        results.append(("Acesso ao Banco", True))
    else:
        results.append(("Acesso ao Banco", False))

    # Teste 4: Função get_database
    test_get_database()
    results.append(("get_database()", get_database() is not None))

    # Teste 5: Simulação Streamlit
    cache_ok = test_streamlit_cache()
    results.append(("Simulação Streamlit", cache_ok))

    # Resumo
    print_section("RESUMO DOS TESTES")
    print()

    all_passed = True
    for test_name, passed in results:
        status = "[OK] PASSOU" if passed else "[FAIL] FALHOU"
        print(f"  {status}: {test_name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("="*60)
        print("  TODOS OS TESTES PASSARAM!")
        print("  Os dashboards devem estar funcionando normalmente.")
        print("="*60)
        return 0
    else:
        print("="*60)
        print("  ALGUNS TESTES FALHARAM")
        print("  Verifique a configuração do MongoDB e .env")
        print("="*60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
