# Testando MongoDB dentro da VM

## Problema
Quando você acessa a aplicação de dentro da VM (via navegador dentro da máquina virtual), os dashboards ainda exibem o erro "não foi possível conectar ao MongoDB".

## Causa
O cache do Streamlit estava ficando preso em `None` porque:
1. Na primeira inicialização, o cache tentava conectar e falhava
2. O cache retornava `None` por 60 segundos
3. Sem fallback, nenhuma reconexão era possível

## Solução Implementada
Agora foi adicionado um sistema de **fallback duplo**:

### BoxerV2
```
1️⃣ Tenta usar cache (com retry 3x, timeout 5000ms)
   ↓
   Se falhar:
2️⃣ Tenta reconectar diretamente (sem cache, retry 3x, timeout 5000ms)
```

### Boxer, Meias
```
1️⃣ Primeira tentativa com retry robusto (3x, timeout 5000ms)
   ↓
   Se falhar:
2️⃣ Segunda tentativa como fallback (2x, timeout 5000ms)
```

## Como Testar

### Opção 1: Teste Rápido (Recomendado)
```bash
# Em um terminal DENTRO DA VM:
cd ~/Controle_fios_sisplan_py/Stock_app
python test_mongodb_connection.py
```

Você deve ver:
```
[OK] PASSOU: Conexão Direta
[OK] PASSOU: Retry Exponencial
[OK] PASSOU: Acesso ao Banco
[OK] PASSOU: get_database()
[OK] PASSOU: Simulação Streamlit

TODOS OS TESTES PASSARAM!
```

### Opção 2: Teste no Navegador
1. Abra a aplicação Streamlit dentro da VM
2. Vá para cada aba:
   - **Boxer**: Deve mostrar dados, não aviso
   - **BoxerV2**: Deve mostrar dados, não erro
   - **Meias**: Deve mostrar dados, não aviso

### Opção 3: Teste Manual em Python
```bash
# Terminal dentro da VM:
python -c "
import sys
sys.path.insert(0, './app')
from mongo_utils import get_mongo_client_with_retry
client = get_mongo_client_with_retry(max_retries=3, server_timeout_ms=5000)
print('CONEXAO OK' if client else 'FALHA NA CONEXAO')
"
```

## Se Ainda Falhar

### 1. Verificar conectividade de rede
```bash
# Dentro da VM, testar ping para a máquina com MongoDB:
ping 192.168.1.205  # ou IP da máquina com MongoDB
```

Se falhar aqui, o problema é rede (não é Streamlit).

### 2. Limpar cache do Streamlit
```bash
# Dentro da VM:
rm -rf ~/.streamlit/cache
rm -rf ~/.streamlit/config.toml
streamlit run app/maindash.py
```

### 3. Verificar variáveis de ambiente
```bash
# Dentro da VM, no diretório Stock_app:
cat .env | grep MONGO
```

Deve mostrar algo como:
```
MONGO_URI_LOCAL=mongodb://comercial:***@localhost:27017/stock_app?authSource=admin
MONGO_URI_VM=mongodb://comercial:***@192.168.1.205:27017/stock_app?authSource=admin
```

### 4. Aumentar verbosidade de debug
Edite um dashboard e adicione print:
```python
from mongo_utils import get_mongo_client_with_retry
client = get_mongo_client_with_retry(max_retries=3, server_timeout_ms=5000)
print(f"[DEBUG] Cliente MongoDB: {client}")  # Mostrará None ou objeto
```

## Timeouts

- **Local** (localhost): 3000ms é suficiente
- **VM** (rede): 5000ms foi aumentado para dar mais tempo

Se ainda tiver problemas de timeout, você pode aumentar mais:

```python
# Em qualquer dashboard:
client = get_mongo_client_with_retry(max_retries=3, server_timeout_ms=10000)  # 10 segundos
```

## Commits Relacionados

- `e481c6c` - Versão inicial com retry exponencial
- `571fe41` - Melhorias com timeout aumentado e fallback

## Logs de Erro

Se você ver log similar a:
```
Erro ao conectar ao Mongo (mongodb://...): timeout waiting for server selection
```

Significa que o MongoDB não está respondendo dentro do timeout. Aumentar o timeout pode ajudar.
