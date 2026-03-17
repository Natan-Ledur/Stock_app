# Correção de Erros de Conexão ao MongoDB

## Problema Identificado

Os dashboards estavam exibindo as seguintes mensagens de erro ao inicializar:

- **Boxer**: "Aviso: não foi possível conectar ao MongoDB (tentativas local e VM)"
- **Boxer_V2**: "Não foi possível carregar os dados. Verifique a conexão com o MongoDB"
- **Meias**: "Aviso: não foi possível conectar ao MongoDB (tentativas local e VM)"

## Causa Raiz

A função `_resolve_database_with_retry()` era muito fraca:
- Tentava apenas 2 vezes sem nenhuma espera
- O cache do Streamlit era inicializado antes do MongoDB estar pronto para responder
- Isso causava uma falha permanente de cache (até reiniciar o Streamlit)

## Solução Implementada

### 1. Nova Função com Retry Robusto
Adicionada `get_mongo_client_with_retry()` em `mongo_utils.py`:
- Executa até 3 tentativas
- Backoff exponencial: espera 0.5s, 1s, 2s entre tentativas
- Garante que o MongoDB tenha tempo de responder

### 2. Dashboards Atualizados
Os seguintes arquivos foram atualizados para usar a nova função:
- `app/BoxerV2/dashboard.py`
- `app/Boxer/Boxer01/dashboard.py`
- `app/Meia/dashboard_streamlit.py`
- `app/Meia/Meia01/dashboard_streamlit.py`

### 3. Alteração no Cache do Streamlit
Antes:
```python
@st.cache_resource(ttl=60)
def _cached_mongo_connection():
    return get_database()
```

Depois:
```python
@st.cache_resource(ttl=60)
def _cached_mongo_connection():
    return get_mongo_client_with_retry(max_retries=3)
```

## Como Verificar se Funcionou

Execute o script de diagnóstico para confirmar que tudo está funcionando:

```bash
python test_mongodb_connection.py
```

Este script testa:
- ✓ Conexão direta ao MongoDB
- ✓ Retry com backoff exponencial
- ✓ Acesso ao banco de dados
- ✓ Função `get_database()`
- ✓ Simulação do comportamento do Streamlit

## Se os Erros Persistirem

1. **Verifique se o MongoDB está rodando:**
   ```bash
   python -c "from app.mongo_utils import get_mongo_client; print('OK' if get_mongo_client() else 'FALHA')"
   ```

2. **Confirme as variáveis de ambiente em `.env`:**
   - `MONGO_URI_LOCAL` ou `MONGO_URI_VM`
   - `MONGO_INITDB_ROOT_USERNAME`
   - `MONGO_INITDB_ROOT_PASSWORD`

3. **Limpe o cache do Streamlit:**
   ```bash
   rm -rf ~/.streamlit/cache
   streamlit run app/maindash.py
   ```

## Arquivos Modificados

- `app/mongo_utils.py` - Nova função de retry
- `app/BoxerV2/dashboard.py` - Atualizado para usar retry
- `app/Boxer/Boxer01/dashboard.py` - Atualizado para usar retry
- `app/Meia/dashboard_streamlit.py` - Atualizado para usar retry
- `app/Meia/Meia01/dashboard_streamlit.py` - Atualizado para usar retry
- `test_mongodb_connection.py` - Script de diagnóstico (novo)

## Commit

Commit: `e481c6c` - "Corrigir erros de conexão ao MongoDB com retry robusto"
