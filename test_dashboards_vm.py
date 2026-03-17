#!/usr/bin/env python
"""
Script para simular exatamente o comportamento inside VM.

Simula os 3 dashboards (BoxerV2, Boxer, Meias) com o mesmo cache
que eles usam dentro do Streamlit.

Use dentro da VM para verificar se tudo funciona.
"""

import sys
import os
import time

# Simula importação dentro da VM (pode estar em path diferente)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from mongo_utils import get_mongo_client_with_retry

# Simula cache do Streamlit (TTL 60s)
_cache = {}
_cache_time = {}

def simulate_streamlit_cache(key, factory, ttl=60):
    """Simula o comportamento do @st.cache_resource(ttl=60)"""
    now = time.time()

    # Se não há cache, executa factory
    if key not in _cache:
        _cache[key] = factory()
        _cache_time[key] = now
        return _cache[key]

    # Se cache expirou, limpa e recria
    if now - _cache_time[key] > ttl:
        _cache[key] = factory()
        _cache_time[key] = now
        return _cache[key]

    # Retorna do cache
    return _cache[key]


def test_boxerv2_simulation():
    """Simula BoxerV2 dashboard"""
    print("\n" + "="*60)
    print("TESTE: BoxerV2 Dashboard (com cache)")
    print("="*60)

    def _cached_mongo_connection():
        print("  > Executando factory: get_mongo_client_with_retry(max_retries=3, timeout=5000)")
        return get_mongo_client_with_retry(max_retries=3, server_timeout_ms=5000)

    # Primeira inicializacao (tipo pagina loaded)
    print("\n1. Primeira inicialização (cache vazio):")
    client = simulate_streamlit_cache('boxerv2_cache', _cached_mongo_connection)
    if client:
        print("   [OK] Cache conseguiu conectar")
        return True
    else:
        print("   [FAIL] Cache falhou")

        # Fallback: tenta reconectar
        print("\n2. Tentando fallback (sem cache):")
        client = get_mongo_client_with_retry(max_retries=3, server_timeout_ms=5000)
        if client:
            print("   [OK] Fallback conectou!")
            return True
        else:
            print("   [FAIL] Fallback tambem falhou")
            return False


def test_boxer_simulation():
    """Simula Boxer dashboard (sem cache)"""
    print("\n" + "="*60)
    print("TESTE: Boxer Dashboard (sem cache)")
    print("="*60)

    print("\n1. Tentativa 1 (retry 3x):")
    client = get_mongo_client_with_retry(max_retries=3, server_timeout_ms=5000)
    if client:
        print("   [OK] Primeira tentativa conectou")
        return True
    else:
        print("   [FAIL] Primeira tentativa falhou")

        print("\n2. Tentativa 2 (fallback, retry 2x):")
        client = get_mongo_client_with_retry(max_retries=2, server_timeout_ms=5000)
        if client:
            print("   [OK] Fallback conectou")
            return True
        else:
            print("   [FAIL] Fallback tambem falhou")
            return False


def test_meia_simulation():
    """Simula Meia dashboard (sem cache)"""
    print("\n" + "="*60)
    print("TESTE: Meia Dashboard (sem cache)")
    print("="*60)

    print("\n1. Tentativa 1 (retry 3x):")
    client = get_mongo_client_with_retry(max_retries=3, server_timeout_ms=5000)
    if client:
        print("   [OK] Primeira tentativa conectou")
        return True
    else:
        print("   [FAIL] Primeira tentativa falhou")

        print("\n2. Tentativa 2 (fallback, retry 2x):")
        client = get_mongo_client_with_retry(max_retries=2, server_timeout_ms=5000)
        if client:
            print("   [OK] Fallback conectou")
            return True
        else:
            print("   [FAIL] Fallback tambem falhou")
            return False


def main():
    print("\n" + "="*60)
    print("SIMULACAO: Dashboards dentro da VM")
    print("="*60)
    print("\nEste script simula exatamente o que cada dashboard")
    print("faz quando inicializa dentro da VM.")

    results = []

    # Testa cada dashboard
    results.append(("BoxerV2", test_boxerv2_simulation()))
    results.append(("Boxer", test_boxer_simulation()))
    results.append(("Meia", test_meia_simulation()))

    # Resumo
    print("\n" + "="*60)
    print("RESUMO")
    print("="*60)

    for name, passed in results:
        status = "[OK]" if passed else "[FAIL]"
        print(f"  {status} {name}")

    all_passed = all(passed for _, passed in results)

    if all_passed:
        print("\n" + "-"*60)
        print("TODOS OS DASHBOARDS FUNCIONANDO!")
        print("Os erros de MongoDB dentro da VM devem estar resolvidos.")
        print("-"*60)
        return 0
    else:
        print("\n" + "-"*60)
        print("ALGUNS DASHBOARDS FALHARAM")
        print("Verifique a conectividade de rede até o MongoDB.")
        print("-"*60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
