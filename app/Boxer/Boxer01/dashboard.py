
# Dashboard usando Streamlit, lendo dados do cache
import streamlit as st
import pandas as pd
import os
import json
import pickle
import subprocess
import plotly.figure_factory as ff
import datetime
import plotly.express as px
import io
import requests
import sys
import importlib
import os
import numpy as np

# Quando o módulo é carregado dinamicamente via spec_from_file_location, imports relativos
# podem falhar porque não existe um pacote pai conhecido. Para contornar, adicionamos o
# diretório `frontend/app` ao `sys.path` e importamos `format_utils` por nome.
try:
    from format_utils import format_dataframe_brazilian
except Exception:
    app_dir = os.path.dirname(os.path.dirname(__file__))  # frontend/app
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    format_utils = importlib.import_module('format_utils')
    format_dataframe_brazilian = format_utils.format_dataframe_brazilian
# Função para buscar DataFrames direto do MongoDB
try:
    from mongo_utils import get_database, get_mongo_client_with_retry
except Exception:
    app_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    mongo_utils = importlib.import_module('mongo_utils')
    get_database = mongo_utils.get_database
    get_mongo_client_with_retry = getattr(mongo_utils, 'get_mongo_client_with_retry', lambda **kw: None)


def _resolve_database_with_retry():
    """Tenta conectar ao MongoDB com retry e fallback."""
    # Primeira tentativa com retry robusto
    client = get_mongo_client_with_retry(max_retries=3, server_timeout_ms=5000)
    if client is not None:
        try:
            client.admin.command('ping')
            return client[os.getenv('MONGO_DB', 'stock_app')]
        except Exception:
            pass

    # Segunda tentativa direta como fallback
    client = get_mongo_client_with_retry(max_retries=2, server_timeout_ms=5000)
    if client is not None:
        try:
            client.admin.command('ping')
            return client[os.getenv('MONGO_DB', 'stock_app')]
        except Exception:
            pass

    return None

st.title("Dados Boxer")

#========================load env e conecta ao MongoDB========================================#
db = _resolve_database_with_retry()
if db is None:
    st.warning("Aviso: não foi possível conectar ao MongoDB (tentativas local e VM). Verifique as variáveis MONGO_* no .env.")
#==============================================================================================#
def ler_df_mongo(nome_colecao):
    global db
    if db is None:
        db = _resolve_database_with_retry()
    if db is None:
        st.warning(f"Banco de dados MongoDB não disponível; não é possível ler {nome_colecao}.")
        return pd.DataFrame()
    try:
        col = db[nome_colecao]
        dados = list(col.find({}, {"_id": 0}))
        if dados:
            return pd.DataFrame(dados)
        else:
            st.warning(f"Coleção {nome_colecao} não encontrada ou vazia.")
            return pd.DataFrame()
    except Exception as e:
        st.warning(f"Erro ao ler coleção {nome_colecao}: {e}")
        return pd.DataFrame()

# Conjunto global com os nomes de colunas de pedidos de COMPRA (derivadas de compras_fios)
PURCHASE_ORDER_COLUMNS: set[str] = set()
# Mapa global (descricao, descricao_cor, numero) -> (data_entrega: date, qtde_total: float)
PURCHASE_DELIVERY_BY_ITEM = {}


# ---------------- Preferences helpers ----------------
API_BASE = os.environ.get('API_BASE', 'http://backend2:8001/api')

# ---------------- Cookies helpers (compartilha CookieManager criado em maindash) ----------------
def _get_cookie_manager():
    try:
        cm = getattr(st.session_state, 'cookie_manager', None) if hasattr(st, 'session_state') else None
        if cm is not None:
            return cm
        # fallback: tentar criar localmente se extra_streamlit_components estiver disponível
        try:
            import extra_streamlit_components as stx  # type: ignore
            return stx.CookieManager()
        except Exception:
            return None
    except Exception:
        return None

def _get_headers():
    try:
        token = st.session_state.get('token')
        if token:
            return {'Authorization': f'Bearer {token}'}
    except Exception:
        pass
    return {}

def load_preferences(key):
    hdrs = _get_headers()
    if not hdrs:
        return {}
    try:
        r = requests.get(f"{API_BASE}/preferences/?key={key}", headers=hdrs, timeout=5)
        if r.status_code == 200:
            return r.json().get('payload', {})
    except Exception:
        pass
    return {}

def save_preferences(key, payload):
    hdrs = _get_headers()
    if not hdrs:
        st.warning('Usuário não autenticado; não foi possível salvar preferências.')
        return False
    try:
        r = requests.post(f"{API_BASE}/preferences/", json={'key': key, 'payload': payload}, headers=hdrs, timeout=5)
        return r.status_code == 200 and r.json().get('ok')
    except Exception:
        return False

# Try to preload preferences for this dashboard
pref = {}
try:
    pref = load_preferences('boxer') or {}
except Exception:
    pref = {}

# Função para rodar main.py e atualizar os dados
def rodar_main_py():
    # Use o mesmo interpretador Python que está rodando o Streamlit
    script = os.path.join(os.path.dirname(__file__), "main.py")
    cmd = [sys.executable, script]
    try:
        resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        st.error("Tempo esgotado ao executar a atualização (timeout).")
        return
    # Mostra saída completa (stdout + stderr) para diagnóstico
    output = "".join(filter(None, [resultado.stdout or "", resultado.stderr or ""]))
    if resultado.returncode == 0:
        st.success("Dados atualizados com sucesso!")
        if output:
            st.text(output)
    else:
        st.error("Erro ao atualizar dados. Verifique a saída abaixo:")
        if output:
            st.text(output)

# Função para buscar a última atualização
def buscar_ultima_atualizacao():
    if db is None:
        return None
    try:
        col = db["boxer_df_final"]
        doc = col.find_one(sort=[("data_atualizacao", -1)])
        if doc and "data_atualizacao" in doc:
            return doc["data_atualizacao"]
    except Exception:
        return None
    return None



# Botão para atualizar os dados manualmente
if st.button("Atualizar dados"):
       rodar_main_py()
       st.rerun()

 # Exibe a última atualização
ultima_atualizacao = buscar_ultima_atualizacao()
if ultima_atualizacao:
        st.info(f"Última atualização dos dados: {ultima_atualizacao.strftime('%d/%m/%Y %H:%M:%S') if isinstance(ultima_atualizacao, datetime.datetime) else str(ultima_atualizacao)}")
else:
        st.info("Dados nunca foram atualizados.")

#atualizar_automatico_docker()
df_final = ler_df_mongo("boxer_df_final")

# ================================== Integração com compras_fios ==================================
# Lê a coleção de ordens de compra e adiciona colunas por "numero" ao df_final.
try:
    df_compras = ler_df_mongo("compras_fios")
    if isinstance(df_compras, pd.DataFrame) and not df_compras.empty:
        # Normaliza nomes de campos esperados: descricao, descricao_cor, numero, qtde
        if 'descricao' not in df_compras.columns:
            # Sem descricao não há como associar
            df_compras = pd.DataFrame()
        else:
            # Mapeia descricao_cor a partir de alternativas conhecidas (desc_cor, cor)
            if 'descricao_cor' not in df_compras.columns:
                if 'desc_cor' in df_compras.columns:
                    df_compras['descricao_cor'] = df_compras['desc_cor']
                elif 'cor' in df_compras.columns:
                    df_compras['descricao_cor'] = df_compras['cor']
            # Garante tipos corretos
            if 'numero' in df_compras.columns:
                try:
                    df_compras['numero'] = df_compras['numero'].astype(str).str.strip()
                except Exception:
                    df_compras['numero'] = df_compras['numero']
            else:
                # Sem número de pedido, não cria colunas dinâmicas
                df_compras = pd.DataFrame()
            if not df_compras.empty:
                try:
                    df_compras['qtde'] = pd.to_numeric(df_compras.get('qtde', 0), errors='coerce').fillna(0)
                except Exception:
                    pass
                # Converte dt_entrega para date
                try:
                    if 'dt_entrega' in df_compras.columns:
                        df_compras['dt_entrega'] = pd.to_datetime(df_compras['dt_entrega'], errors='coerce').dt.date
                except Exception:
                    pass
        if isinstance(df_compras, pd.DataFrame) and not df_compras.empty and 'descricao_cor' in df_compras.columns:
            # Prepara mapa de entrega por item (usa data mínima por (descricao, descricao_cor, numero) e soma qtde)
            try:
                grp_info = (
                    df_compras.groupby(['descricao', 'descricao_cor', 'numero'], dropna=False)
                    .agg(qtde=('qtde', 'sum'), dt=('dt_entrega', 'min'))
                    .reset_index()
                )
                PURCHASE_DELIVERY_BY_ITEM = {
                    (str(r['descricao']), str(r['descricao_cor']), str(r['numero'])): (r['dt'], float(r['qtde'] or 0))
                    for _, r in grp_info.iterrows()
                }
            except Exception:
                PURCHASE_DELIVERY_BY_ITEM = {}
            # Agrega por material, cor e número de pedido (soma das quantidades)
            grp = (
                df_compras.groupby(['descricao', 'descricao_cor', 'numero'], dropna=False)['qtde']
                .sum()
                .reset_index()
            )
            if not grp.empty:
                compras_pivot = grp.pivot_table(
                    index=['descricao', 'descricao_cor'],
                    columns='numero',
                    values='qtde',
                    aggfunc='sum',
                    fill_value=0
                )
                # Atualiza conjunto global de colunas de pedidos de compra
                try:
                    PURCHASE_ORDER_COLUMNS.clear()
                    PURCHASE_ORDER_COLUMNS.update([str(c) for c in compras_pivot.columns.tolist()])
                except Exception:
                    pass
                # Faz o merge no df_final
                try:
                    df_final = pd.merge(
                        df_final,
                        compras_pivot.reset_index(),
                        on=['descricao', 'descricao_cor'],
                        how='left'
                    )
                    # Preenche NaN das novas colunas de compra com 0 e garante numérico
                    for col in compras_pivot.columns:
                        col_str = str(col)
                        if col_str in df_final.columns:
                            df_final[col_str] = pd.to_numeric(df_final[col_str], errors='coerce').fillna(0)
                except Exception as e:
                    st.warning(f"Falha ao integrar compras_fios: {e}")
except Exception as e:
    st.warning(f"Não foi possível processar compras_fios: {e}")
# ================================================================================================

#================================================================abas============================================================================
#================================================================================================================================================
aba1, aba2, aba3 = st.tabs(["Geral", "Planejamento", "Relatórios"])

with aba1:
    
    if isinstance(df_final, pd.DataFrame) and not df_final.empty:
        # Persistência de filtros em cookies por usuário
        cm = _get_cookie_manager()
        username = st.session_state.get('username', 'anon')
        cookie_key = f"boxer_{username}_geral_filters"
        saved_filters = {}
        if cm:
            try:
                raw = cm.get(cookie_key)
                if raw:
                    saved_filters = json.loads(raw)
            except Exception:
                saved_filters = {}
    # Fallback: ler de query params se cookie vazio
        if not saved_filters:
            try:
                qp = getattr(st, 'query_params', None)
                if qp:
                    saved_filters = {
                        'descricao': qp.get('bx_desc') if isinstance(qp.get('bx_desc'), str) else (qp.get('bx_desc')[0] if qp.get('bx_desc') else None),
                        'cor': qp.get('bx_cor') if isinstance(qp.get('bx_cor'), str) else (qp.get('bx_cor')[0] if qp.get('bx_cor') else None),
                        'setor': qp.get('bx_setor') if isinstance(qp.get('bx_setor'), str) else (qp.get('bx_setor')[0] if qp.get('bx_setor') else None),
                    }
                    peds = qp.get('bx_peds')
                    if isinstance(peds, list):
                        saved_filters['pedidos'] = peds
                    elif isinstance(peds, str):
                        saved_filters['pedidos'] = [s for s in peds.split(',') if s]
                    ocs = qp.get('bx_ocs')
                    if isinstance(ocs, list):
                        saved_filters['compras'] = ocs
                    elif isinstance(ocs, str):
                        saved_filters['compras'] = [s for s in ocs.split(',') if s]
                else:
                    get_qp = getattr(st, 'experimental_get_query_params', None)
                    if get_qp:
                        params = get_qp() or {}
                        saved_filters = {
                            'descricao': (params.get('bx_desc',[None])[0] if isinstance(params.get('bx_desc'), list) else params.get('bx_desc')),
                            'cor': (params.get('bx_cor',[None])[0] if isinstance(params.get('bx_cor'), list) else params.get('bx_cor')),
                            'setor': (params.get('bx_setor',[None])[0] if isinstance(params.get('bx_setor'), list) else params.get('bx_setor')),
                        }
                        peds = params.get('bx_peds')
                        if isinstance(peds, list):
                            saved_filters['pedidos'] = peds
                        elif isinstance(peds, str):
                            saved_filters['pedidos'] = [s for s in peds.split(',') if s]
                        ocs = params.get('bx_ocs')
                        if isinstance(ocs, list):
                            saved_filters['compras'] = ocs
                        elif isinstance(ocs, str):
                            saved_filters['compras'] = [s for s in ocs.split(',') if s]
            except Exception:
                pass
        # Fallback: carregar do backend de preferências se ainda vazio
        if not saved_filters:
            try:
                pref_payload = load_preferences('boxer') or {}
                gf = pref_payload.get('geral_filters')
                if isinstance(gf, dict):
                    saved_filters = gf
            except Exception:
                pass

        col1, col2, col4 = st.columns([2,2,2])
        # Filtro por descricao
        opcoes_descricao = df_final['descricao'].dropna().unique().tolist() if 'descricao' in df_final.columns else []
        desc_options = ["Todos"] + opcoes_descricao
        try:
            desc_default = saved_filters.get('descricao') if isinstance(saved_filters, dict) else None
            desc_index = desc_options.index(desc_default) if desc_default in desc_options else 0
        except Exception:
            desc_index = 0
        descricao_selecionada = col1.selectbox("Filtrar por Material (descricao)", desc_options, index=desc_index)

        # Filtro por descricao_cor
        opcoes_cor = df_final['descricao_cor'].dropna().unique().tolist() if 'descricao_cor' in df_final.columns else []
        cor_options = ["Todos"] + opcoes_cor
        try:
            cor_default = saved_filters.get('cor') if isinstance(saved_filters, dict) else None
            cor_index = cor_options.index(cor_default) if cor_default in cor_options else 0
        except Exception:
            cor_index = 0
        cor_selecionada = col2.selectbox("Filtrar por Cor (descricao_cor)", cor_options, index=cor_index)

        # Filtro por pedidos (multiselect) dentro de expander
        colunas_pedidos = [col for col in df_final.columns if col.isdigit() or col.startswith('18_') or col.startswith('01_')]
        # --- Novo: selector para filtrar por um Planejamento salvo ---
        planos_pref_global = pref.get('planos_pref', {}) or {}
        planos_salvos_list = st.session_state.get('planos', [])
        plano_options = ['Nenhum'] + [f"{p['id']} - {p['name']}" for p in planos_salvos_list]
        try:
            sel_plano_idx = 0
            # tenta recuperar um plano salvo nas preferências gerais (se houver chave 'plano_geral_selected')
            plano_geral_sel = pref.get('plano_geral_selected')
            if plano_geral_sel:
                # encontrar índice correspondente
                for i, p in enumerate(planos_salvos_list, start=1):
                    if str(p.get('id')) == str(plano_geral_sel) or p.get('name') == plano_geral_sel:
                        sel_plano_idx = i
                        break
        except Exception:
            sel_plano_idx = 0
        sel_plano = st.selectbox('Filtrar por Planejamento salvo (Geral)', plano_options, index=sel_plano_idx, key='sel_plano_geral', help='Ao selecionar um plano salvo, os pedidos definidos nele serão usados como seleção padrão para a tabela.')

        with st.expander("Exibir/ocultar colunas de pedidos e Ordens de compras", expanded=False):
            try:
                # prioridade: se usuário selecionou um Plano salvo no seletor acima, usar os pedidos desse plano
                default_peds = None
                if sel_plano and sel_plano != 'Nenhum':
                    # extrair id do texto "{id} - {name}"
                    try:
                        sel_id = int(str(sel_plano).split(' - ')[0])
                    except Exception:
                        sel_id = None
                    if sel_id is not None:
                        plan_pref = planos_pref_global.get(str(sel_id), {})
                        plan_peds = plan_pref.get('pedidos_selecionados') or []
                        # filtra para garantir que existam nas colunas atuais
                        plan_peds = [p for p in plan_peds if p in colunas_pedidos]
                        if plan_peds:
                            default_peds = plan_peds

                # fallback para preferências salvas nos cookies/query params/old prefs
                if default_peds is None:
                    try:
                        saved_peds = saved_filters.get('pedidos') if isinstance(saved_filters, dict) else None
                        if isinstance(saved_peds, list):
                            default_peds = [c for c in saved_peds if c in colunas_pedidos]
                            if not default_peds:
                                default_peds = colunas_pedidos
                        else:
                            default_peds = colunas_pedidos
                    except Exception:
                        default_peds = colunas_pedidos

            except Exception:
                default_peds = colunas_pedidos
            # Atualiza a seleção do multiselect apenas quando o plano selecionado mudou.
            try:
                current_plan = st.session_state.get('sel_plano_geral')
                last_plan = st.session_state.get('_last_sel_plano_geral')
                desired_default = default_peds if default_peds is not None else colunas_pedidos
                if current_plan != last_plan:
                    # marca o plano atual para próxima verificação
                    st.session_state['_last_sel_plano_geral'] = current_plan
                    if current_plan == 'Nenhum':
                        st.session_state['geral_pedidos_multiselect'] = colunas_pedidos
                    else:
                        # se houver pedidos definidos no plano, aplica; senão aplica todos
                        st.session_state['geral_pedidos_multiselect'] = desired_default or colunas_pedidos
            except Exception:
                pass

            pedidos_selecionados = st.multiselect(
                "Selecione os pedidos que deseja visualizar:",
                colunas_pedidos,
                default=st.session_state.get('geral_pedidos_multiselect', default_peds),
                key='geral_pedidos_multiselect',
                help="Todos estão selecionados por padrão. Use para filtrar visualmente."
            )

            # Seleção específica de NÚMEROS DE COMPRAS (OCs) a considerar no estoque
            try:
                purchase_options = sorted([c for c in PURCHASE_ORDER_COLUMNS if c in df_final.columns])
            except Exception:
                purchase_options = []
            try:
                saved_oc = []
                if isinstance(saved_filters, dict):
                    saved_oc = saved_filters.get('compras') or saved_filters.get('ocs') or []
                if not isinstance(saved_oc, list):
                    saved_oc = []
                default_ocs = [c for c in saved_oc if c in purchase_options] or purchase_options
            except Exception:
                default_ocs = purchase_options
            compras_selecionadas = st.multiselect(
                "Selecione os números de compras (OC) a considerar:",
                purchase_options,
                default=st.session_state.get('geral_compras_multiselect', default_ocs),
                key='geral_compras_multiselect',
                help="As OCs selecionadas serão somadas ao estoque disponível (Estoque_Descontado)."
            )

        # Filtro por setor
        opcoes_setor = ["Todos", "Setor 01", "Setor 18", "Setor 19"]
        try:
            setor_default = saved_filters.get('setor') if isinstance(saved_filters, dict) else None
            setor_index = opcoes_setor.index(setor_default) if setor_default in opcoes_setor else 0
        except Exception:
            setor_index = 0
        setor_selecionado = col4.selectbox("Filtrar por Setor", opcoes_setor, index=setor_index)

        # Salva/atualiza cookie com filtros atuais (validos 30 dias)
        try:
            if cm:
                payload = json.dumps({
                    'descricao': descricao_selecionada,
                    'cor': cor_selecionada,
                    'pedidos': pedidos_selecionados,
                    'setor': setor_selecionado,
                    'compras': compras_selecionadas,
                }, ensure_ascii=False)
                cm.set(cookie_key, payload, expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30), key=f'{cookie_key}_set')
        except Exception:
            pass
        # Persistir também no backend de preferências (merge para não perder outros dados como planos)
        try:
            existing = load_preferences('boxer') or {}
            existing['geral_filters'] = {
                'descricao': descricao_selecionada,
                'cor': cor_selecionada,
                'pedidos': pedidos_selecionados,
                'setor': setor_selecionado,
                'compras': compras_selecionadas,
            }
            # salvar silenciosamente; se não autenticado, save_preferences já emite aviso
            save_preferences('boxer', existing)
        except Exception:
            pass
        # Atualiza query params para espelhar o estado atual (melhora restauração em reload)
        try:
            qp = getattr(st, 'query_params', None)
            params = dict(bx_desc=descricao_selecionada, bx_cor=cor_selecionada, bx_setor=setor_selecionado)
            # multiselect em lista/CSV
            if pedidos_selecionados:
                params['bx_peds'] = pedidos_selecionados
            else:
                params['bx_peds'] = []
            # adiciona OCs como query param
            if compras_selecionadas:
                params['bx_ocs'] = compras_selecionadas
            else:
                params['bx_ocs'] = []
            if qp is not None:
                if hasattr(qp, 'update'):
                    qp.update(**params)
                else:
                    qp['bx_desc'] = descricao_selecionada
                    qp['bx_cor'] = cor_selecionada
                    qp['bx_setor'] = setor_selecionado
                    qp['bx_peds'] = pedidos_selecionados
                    qp['bx_ocs'] = compras_selecionadas
            else:
                set_qp = getattr(st, 'experimental_set_query_params', None)
                if set_qp:
                    set_qp(**params)
        except Exception:
            pass

        # Aplicar filtros
        df_filtrado = df_final.copy()
        if descricao_selecionada != "Todos" and 'descricao' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['descricao'] == descricao_selecionada]
        if cor_selecionada != "Todos" and 'descricao_cor' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['descricao_cor'] == cor_selecionada]

        # Filtrar colunas de pedidos (inclui OCs selecionadas para garantir presença no cálculo)
        selected_ocs = st.session_state.get('geral_compras_multiselect', [])
        colunas_base = ['descricao', 'descricao_cor', 'codigo_tabela_cor', 'estoque_total']
        colunas_exibir = colunas_base + list(dict.fromkeys(pedidos_selecionados + selected_ocs))
        colunas_exibir = [col for col in colunas_exibir if col in df_filtrado.columns]
        df_filtrado = df_filtrado[colunas_exibir]

        # Filtro por setor: exibe apenas colunas do setor escolhido
        if setor_selecionado == "Setor 01":
            colunas_setor = [col for col in df_filtrado.columns if col.startswith('01_')]
            colunas_exibir = [col for col in colunas_exibir if col in colunas_setor or col in colunas_base]
            df_filtrado = df_filtrado[colunas_exibir]
        elif setor_selecionado == "Setor 18":
            colunas_setor = [col for col in df_filtrado.columns if col.startswith('18_')]
            colunas_exibir = [col for col in colunas_exibir if col in colunas_setor or col in colunas_base]
            df_filtrado = df_filtrado[colunas_exibir]
        elif setor_selecionado == "Setor 19":
            colunas_setor = [col for col in df_filtrado.columns if col.isdigit()]
            colunas_exibir = [col for col in colunas_exibir if col in colunas_setor or col in colunas_base]
            df_filtrado = df_filtrado[colunas_exibir]

        # Recalcular Consumo/Compras e Estoque_Descontado
        pedidos_cols = [col for col in df_filtrado.columns if col not in colunas_base]
        # separa colunas de compra vs demanda usando o conjunto global
        try:
            demand_cols = [c for c in pedidos_cols if str(c) not in PURCHASE_ORDER_COLUMNS]
            # usa APENAS as OCs que o usuário selecionou (independente de estarem visíveis como 'pedidos')
            selected_ocs = st.session_state.get('geral_compras_multiselect', []) or []
            purchase_cols_in_df = [c for c in df_filtrado.columns if str(c) in PURCHASE_ORDER_COLUMNS and str(c) in selected_ocs]
        except Exception:
            demand_cols = pedidos_cols
            purchase_cols_in_df = []
        df_filtrado['Consumo_Total_Pedidos'] = df_filtrado[demand_cols].sum(axis=1) if demand_cols else 0
        df_filtrado['Compras_Total'] = df_filtrado[purchase_cols_in_df].sum(axis=1) if purchase_cols_in_df else 0
        df_filtrado['Estoque_Descontado'] = df_filtrado['estoque_total'] - df_filtrado['Consumo_Total_Pedidos'] + df_filtrado['Compras_Total']

        # Ordenar do maior para o menor estoque
        df_filtrado = df_filtrado.sort_values(by='Consumo_Total_Pedidos', ascending=False)

        # Formata apenas para exibição no Streamlit (não altera df_filtrado original usado em cálculos)
        df_exib = df_filtrado.copy()
        # Arredonda colunas numéricas para 1 casa decimal antes de formatar (opcional)
        num_cols = df_exib.select_dtypes(include=['number']).columns.tolist()
        for c in num_cols:
            try:
                df_exib[c] = df_exib[c].round(1)
            except Exception:
                pass
        # Fixar as colunas 'descricao' e 'descricao_cor' como índice para que fiquem visíveis
        # ao rolar horizontalmente na tabela do Streamlit; usa-se a cópia df_exib para não alterar df_filtrado (que é usado para exportação e cálculos).
        try:
            if 'descricao' in df_exib.columns and 'descricao_cor' in df_exib.columns:
                df_exib.set_index(['descricao', 'descricao_cor'], inplace=True)
        except Exception:
            pass
        st.dataframe(format_dataframe_brazilian(df_exib, decimals=1), height=700) # Tamanho da tabela
    #==============================================================================================
    # Botão de download para Excel
        
        buffer = io.BytesIO()
        df_filtrado.to_excel(buffer, index=False)
        buffer.seek(0)
        st.download_button(
            label="Exportar tabela para Excel",
            data=buffer,
            file_name="tabela_fios_boxer.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    #==============================================================================================
        # Gráfico de pizza: proporção de consumo por setor
       
        setores = {
            'Setor 01': [col for col in df_filtrado.columns if col.startswith('01_')],
            'Setor 18': [col for col in df_filtrado.columns if col.startswith('18_')],
            # Não considerar pedidos de COMPRA como consumo no Setor 19 (numéricos)
            'Setor 19': [col for col in df_filtrado.columns if col.isdigit() and str(col) not in PURCHASE_ORDER_COLUMNS]
        }
        consumo_por_setor = {}
        for nome_setor, cols in setores.items():
            if cols:
                consumo_por_setor[nome_setor] = df_filtrado[cols].sum().sum()
            else:
                consumo_por_setor[nome_setor] = 0
        fig = px.pie(
            names=list(consumo_por_setor.keys()),
            values=list(consumo_por_setor.values()),
            title="Proporção de Consumo por Setor"
        )
        st.plotly_chart(fig, use_container_width=True)
    #==============================================================================================
        # Gráfico de dispersão: estoque vs consumo total
        st.markdown("### Gráfico de dispersão: Estoque vs Consumo Total")
        if 'estoque_total' in df_filtrado.columns and 'Consumo_Total_Pedidos' in df_filtrado.columns:
            # Garantir que colunas numéricas existam para desenho da reta
            df_plot = df_filtrado.copy()
            try:
                df_plot['estoque_total'] = pd.to_numeric(df_plot['estoque_total'], errors='coerce')
                df_plot['Consumo_Total_Pedidos'] = pd.to_numeric(df_plot['Consumo_Total_Pedidos'], errors='coerce')
            except Exception:
                pass

            fig_disp = px.scatter(
                df_plot,
                x='estoque_total',
                y='Consumo_Total_Pedidos',
                color='descricao_cor' if 'descricao_cor' in df_plot.columns else None,
                hover_data=['descricao'] if 'descricao' in df_plot.columns else None,
                title="Estoque vs Consumo Total"
            )
            # Adicionar reta y = m * x com m = 0.214 e intercept = 0
            try:
                m = 0.214
                # Definir intervalo x usando quantis para evitar outliers extremos
                x_valid = df_plot['estoque_total'].dropna()
                if not x_valid.empty:
                    x_min = float(np.nanmin(x_valid))
                    x_max = float(np.nanmax(x_valid))
                    # ampliar um pouco o intervalo para visual
                    span = x_max - x_min if x_max > x_min else max(1.0, abs(x_min))
                    x_line = np.linspace(x_min - 0.05 * span, x_max + 0.05 * span, 2)
                    y_line = m * x_line
                    fig_disp.add_traces(px.line(x=x_line, y=y_line, labels={'x': 'estoque_total', 'y': 'Consumo_Total_Pedidos'}, title='').data)
            except Exception:
                # se algo falhar, mostra scatter sem reta
                pass

            st.plotly_chart(fig_disp, use_container_width=True)
        else:
            st.info("Não há dados suficientes para o gráfico de dispersão.")
#   ==============================================================================================
        # Interação: selecionar cor para mostrar gráfico filtrado por cor e materiais
        if 'descricao_cor' in df_filtrado.columns:
            st.markdown("### Visualizar materiais por cor")
            cor_selecionada_graf = st.selectbox("Selecione uma cor para detalhar o gráfico de dispersão:", df_filtrado['descricao_cor'].dropna().unique())
            df_cor = df_filtrado[df_filtrado['descricao_cor'] == cor_selecionada_graf]
            if not df_cor.empty:
                df_cor_plot = df_cor.copy()
                try:
                    df_cor_plot['estoque_total'] = pd.to_numeric(df_cor_plot['estoque_total'], errors='coerce')
                    df_cor_plot['Consumo_Total_Pedidos'] = pd.to_numeric(df_cor_plot['Consumo_Total_Pedidos'], errors='coerce')
                except Exception:
                    pass

                fig_disp_cor = px.scatter(
                    df_cor_plot,
                    x='estoque_total',
                    y='Consumo_Total_Pedidos',
                    color='descricao',
                    hover_data=['descricao'],
                    title=f"Estoque vs Consumo Total - Cor: {cor_selecionada_graf}"
                )
                # Adicionar reta y = 0.214 * x
                try:
                    m = 0.214 #altear o coeficiente
                    x_valid = df_cor_plot['estoque_total'].dropna()
                    if not x_valid.empty:
                        x_min = float(np.nanmin(x_valid))
                        x_max = float(np.nanmax(x_valid))
                        span = x_max - x_min if x_max > x_min else max(1.0, abs(x_min))
                        x_line = np.linspace(x_min - 0.05 * span, x_max + 0.05 * span, 2)
                        y_line = m * x_line
                        fig_disp_cor.add_traces(px.line(x=x_line, y=y_line).data)
                except Exception:
                    pass

                st.plotly_chart(fig_disp_cor, use_container_width=True)
            else:
                st.info("Não há dados para essa cor.")
    #==============================================================================================
        


    # Se não estiver dados!
    else:
        st.info("Nenhum dado disponível ou formato inválido. Execute o processamento para visualizar os dados.")


#====================================================ABA2=====================================================#==================================================================================================

with aba2:
    st.markdown("### Planejamento Boxer")

    # --- Helpers para planos ---
    def _get_plan_prefix(plan_id):
        return f"plan_{plan_id}"

    # Inicializa lista de planos na sessão (cada plano é um dict com 'name' e 'id')
    if 'planos' not in st.session_state:
        # tenta carregar de pref (compatível com versões antigas)
        planos_salvos = pref.get('planos') or []
        if planos_salvos:
            st.session_state['planos'] = planos_salvos
        else:
            st.session_state['planos'] = [{'id': 1, 'name': 'Planejamento 1'}]

    # Área para criar planos (removido botão de remover último planejamento)
    col_add, col_spacer = st.columns([4,6])
    # callback para adicionar plano (executado antes do rerun)
    def _add_plan_callback(novo_nome_key='novo_plano_nome'):
        try:
            novo_nome_val = st.session_state.get(novo_nome_key, '')
            novo_id = max([p['id'] for p in st.session_state['planos']]) + 1 if st.session_state['planos'] else 1
            nome_final = novo_nome_val.strip() or f'Planejamento {novo_id}'
            st.session_state['planos'].append({'id': novo_id, 'name': nome_final})
            # seleciona automaticamente o novo plano
            st.session_state['plano_ativo_idx'] = len(st.session_state['planos']) - 1
            # limpa o campo de input (modificação via callback é permitida)
            st.session_state[novo_nome_key] = ''
            # auto-save: envia planos atualizados para o backend
            try:
                planos_pref = pref.get('planos_pref', {})
                payload = {'planos': st.session_state['planos'], 'planos_pref': planos_pref}
                ok = save_preferences('boxer', payload)
                if ok:
                    st.session_state['msg_salvar_planos'] = 'Plano criado e salvo!.'
                else:
                    st.session_state['msg_salvar_planos'] = 'Plano criado, mas falha ao salvar no backend (verifique autenticação).'
            except Exception:
                st.session_state['msg_salvar_planos'] = 'Plano criado, mas ocorreu erro ao tentar salvar.'
        except Exception:
            # falha silenciosa para não quebrar a UI
            pass

    with col_add:
        # campo para nome do novo plano
        novo_nome = st.text_input('Nome do novo plano', value=st.session_state.get('novo_plano_nome', ''), key='novo_plano_nome')
        st.button('Adicionar Planejamento', on_click=_add_plan_callback, args=('novo_plano_nome',))
        # exibe feedback de salvar planos (se definido pelo callback)
        if st.session_state.get('msg_salvar_planos'):
            st.info(st.session_state.get('msg_salvar_planos'))
            st.session_state['msg_salvar_planos'] = ''

    # col_spacer permanece para espaçamento visual
    with col_spacer:
        pass

    # Seleção do plano ativo e exclusão do plano selecionado
    plano_labels = [f"{p['id']} - {p['name']}" for p in st.session_state['planos']]
    col_sel, col_del = st.columns([6,1])
    with col_sel:
        # index armazenado em session_state para manter seleção entre reruns
        if 'plano_ativo_idx' not in st.session_state:
            st.session_state['plano_ativo_idx'] = 0
        ativo_idx = st.selectbox('Selecione o Planejamento ativo', options=list(range(len(plano_labels))), format_func=lambda i: plano_labels[i], index=st.session_state['plano_ativo_idx'], key='plano_ativo_idx')

    # callback para excluir o plano selecionado
    def _delete_selected_callback(idx_key='plano_ativo_idx'):
        try:
            idx = st.session_state.get(idx_key, 0)
            planos = st.session_state.get('planos', [])
            if len(planos) > 1 and 0 <= idx < len(planos):
                # guarda o plano removido para saber o id e poder limpar prefs associadas
                removed_plan = planos.pop(idx)
                removed_id = removed_plan.get('id')
                # ajusta o índice ativo para o anterior (ou zero)
                st.session_state[idx_key] = max(0, idx-1)
                # auto-save: atualiza backend com planos modificados e limpa prefs relacionadas ao plano removido
                try:
                    planos_pref = pref.get('planos_pref', {}) or {}
                    # copia para evitar modificar o objeto original diretamente
                    new_planos_pref = dict(planos_pref)
                    # Remover chaves que contenham o id do plano ou o prefixo 'plan_<id>' (heurística)
                    to_remove = []
                    for k in list(new_planos_pref.keys()):
                        try:
                            if isinstance(k, str) and (f"plan_{removed_id}" in k or str(removed_id) in k):
                                to_remove.append(k)
                                continue
                            # se o valor for dict e conter referência a 'plan_id', também remove
                            v = new_planos_pref.get(k)
                            if isinstance(v, dict) and v.get('plan_id') == removed_id:
                                to_remove.append(k)
                        except Exception:
                            continue
                    for k in to_remove:
                        new_planos_pref.pop(k, None)

                    payload = {'planos': st.session_state['planos'], 'planos_pref': new_planos_pref}
                    ok = save_preferences('boxer', payload)
                    if ok:
                        st.session_state['msg_excluir_plano'] = 'Plano excluído.'
                    else:
                        st.session_state['msg_excluir_plano'] = 'Plano excluído localmente; falha ao salvar no backend (verifique autenticação).'
                except Exception:
                    st.session_state['msg_excluir_plano'] = 'Plano excluído localmente; erro ao tentar salvar no backend.'
            else:
                # não podemos usar st.warning fora de rerun; setamos uma flag de mensagem
                st.session_state['msg_excluir_plano'] = 'Não é possível excluir o último plano.'
        except Exception:
            st.session_state['msg_excluir_plano'] = 'Erro ao excluir o plano.'

    with col_del:
        st.button('Excluir plano selecionado', on_click=_delete_selected_callback)
        # exibe mensagem de erro se a callback definiu uma
        if st.session_state.get('msg_excluir_plano'):
            st.warning(st.session_state.pop('msg_excluir_plano'))

    plano_ativo = st.session_state['planos'][st.session_state.get('plano_ativo_idx', 0)]

    # Função que executa a UI do Gantt para um plano (isola keys por plan_id)
    def render_gantt_for_plan(plan):
        plan_id = plan['id']
        prefix = _get_plan_prefix(plan_id)

        st.subheader(f"{plan.get('name')} (ID {plan_id})")
        # Seleciona colunas de pedidos dos setores 01 e 18 + pedidos sem demanda (SD_)
        Pedidos_19= [col for col in df_final.columns if col.startswith('0')]
        pedidos_01 = [col for col in df_final.columns if col.startswith('01_')]
        pedidos_18 = [col for col in df_final.columns if col.startswith('18_')]
        # Colunas de "pedidos sem demanda" adicionadas ao planejamento (ignora o total agregado)
        pedidos_sd = [col for col in df_final.columns if col.startswith('sd_')]
        pedidos_gantt = Pedidos_19 + pedidos_01 + pedidos_18 + pedidos_sd 

        # Preferências específicas do plano
        planos_pref = pref.get('planos_pref', {})
        this_pref = planos_pref.get(str(plan_id), {})

        saved_pedidos = this_pref.get('pedidos_selecionados') or []
        filtered_saved = [p for p in saved_pedidos if p in pedidos_gantt]
        if filtered_saved:
            default_pedidos = filtered_saved
        else:
            default_pedidos = (pedidos_gantt[:3] if len(pedidos_gantt) > 3 else pedidos_gantt)

        pedidos_selecionados = st.multiselect(
            f"Selecione os pedidos para o planejamento ({plan['name']}):",
            pedidos_gantt,
            default=default_pedidos,
            key=f"pedidos_{prefix}"
        )

        # Selecionar OCs (compras) a considerar neste plano
        try:
            purchase_options_plan = sorted([c for c in PURCHASE_ORDER_COLUMNS if c in df_final.columns])
        except Exception:
            purchase_options_plan = []
        try:
            saved_plan_ocs = this_pref.get('compras_selecionadas') or []
            if not isinstance(saved_plan_ocs, list):
                saved_plan_ocs = []
            default_plan_ocs = [c for c in saved_plan_ocs if c in purchase_options_plan]
        except Exception:
            default_plan_ocs = []
        compras_selecionadas_plan = st.multiselect(
            f"Selecione as compras (OC) a considerar neste plano ({plan['name']}):",
            purchase_options_plan,
            default=st.session_state.get(f"compras_{prefix}", default_plan_ocs),
            key=f"compras_{prefix}",
            help="As OCs selecionadas serão somadas ao estoque (Estoque_Descontado) apenas neste plano."
        )

        # Salvar preferências do plano
        if st.button('Salvar preferências deste plano', key=f"salvar_{prefix}"):
            gantt_dates = {}
            for pedido in pedidos_selecionados:
                start = st.session_state.get(f'inicio_{prefix}_{pedido}')
                end = st.session_state.get(f'fim_{prefix}_{pedido}')
                if start and end:
                    gantt_dates[pedido] = {'start': str(start), 'finish': str(end)}
            sel_rows = st.session_state.get(f'selected_rows_{prefix}')
            # inclui pedidos excluídos (se o usuário já tiver marcado)
            excluidos = st.session_state.get(f'excluir_pedidos_{prefix}') or []
            # percentual extra definido pelo usuário (ex: 10 para +10%)
            perc_extra = st.session_state.get(f'consumo_perc_extra_{prefix}') or 0
            # Atualiza pref local e chama save_preferences
            planos_pref = pref.get('planos_pref', {})
            planos_pref[str(plan_id)] = {
                'pedidos_selecionados': pedidos_selecionados,
                'gantt_dates': gantt_dates,
                'selected_rows': sel_rows,
                'pedidos_excluidos': excluidos,
                'consumo_perc_extra': perc_extra,
                'compras_selecionadas': st.session_state.get(f"compras_{prefix}", compras_selecionadas_plan)
            }
            ok = save_preferences('boxer', {'planos_pref': planos_pref, 'planos': st.session_state['planos']})
            if ok:
                st.success('Preferências do plano salvas com sucesso.')
            else:
                st.error('Falha ao salvar preferências do plano.')

        # Widgets de datas por pedido (com keys namespaces)
        df_gantt = []
        for pedido in pedidos_selecionados:
            col1, col2 = st.columns(2)
            default_inicio = None
            default_fim = None
            try:
                if this_pref.get('gantt_dates') and this_pref['gantt_dates'].get(pedido):
                    s = this_pref['gantt_dates'][pedido].get('start')
                    f = this_pref['gantt_dates'][pedido].get('finish')
                    try:
                        default_inicio = datetime.datetime.strptime(s, '%Y-%m-%d').date() if s else None
                    except Exception:
                        default_inicio = None
                    try:
                        default_fim = datetime.datetime.strptime(f, '%Y-%m-%d').date() if f else None
                    except Exception:
                        default_fim = None
            except Exception:
                default_inicio = None
                default_fim = None

            if default_inicio and f'inicio_{prefix}_{pedido}' not in st.session_state:
                st.session_state[f'inicio_{prefix}_{pedido}'] = default_inicio
            if default_fim and f'fim_{prefix}_{pedido}' not in st.session_state:
                st.session_state[f'fim_{prefix}_{pedido}'] = default_fim

            with col1:
                data_inicio = st.date_input(f"Data de início para {pedido}", value=default_inicio or datetime.date.today(), key=f"inicio_{prefix}_{pedido}")
            with col2:
                data_fim = st.date_input(f"Data de fim para {pedido}", value=default_fim or (datetime.date.today() + datetime.timedelta(days=2)), key=f"fim_{prefix}_{pedido}")
            df_gantt.append(dict(Task=pedido, Start=str(data_inicio), Finish=str(data_fim)))

        if df_gantt:
            # Paleta expandida para reduzir repetições quando houver muitos pedidos
            cores = [
                '#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52',
                '#008000', '#800080', '#800000', '#008080', '#000080', '#808000', '#B22222', '#20B2AA', '#FF4500', '#2E8B57',
                '#DAA520', '#4B0082', '#7FFF00', '#DC143C', '#00FA9A', '#4682B4', '#9ACD32', '#FF1493', '#00CED1', '#ADFF2F'
            ]
            # Se houver mais tarefas do que cores, repetir a paleta (duplicando) até cobrir
            while len(cores) < len(df_gantt):
                cores = cores + cores
            fig_gantt = ff.create_gantt(
                df_gantt,
                index_col='Task',
                show_colorbar=True,
                group_tasks=True,
                colors=cores[:len(df_gantt)],
                title=f"Execução dos Pedidos - {plan.get('name')}"
            )
            st.plotly_chart(fig_gantt, use_container_width=True)

            st.markdown("#### Consumo e Estoque dos pedidos planejados")
            colunas_base = ['descricao', 'descricao_cor', 'codigo_tabela_cor', 'estoque_total']
            # Colunas fixas padrão (mantém histórico/setores). NÃO inclui sd_ para que só contem se selecionadas.
            # Pedidos fixos (consumo histórico), exclui OCs numéricas do conjunto fixo por padrão
            pedidos_fixos = [
                col for col in df_final.columns
                if (col.isdigit() and str(col) not in PURCHASE_ORDER_COLUMNS) or col.startswith('18_') or col.startswith('19_')
            ]
            #pedidos_tabela = list(dict.fromkeys(pedidos_fixos + pedidos_selecionados)) como era antes
            # Garante que pedidos_tabela siga a ordem dos pedidos_selecionados primeiro, depois pedidos_fixos não selecionados
            # inclui OCs selecionadas no plano
            try:
                compras_plan = st.session_state.get(f"compras_{prefix}", []) or []
            except Exception:
                compras_plan = []
            pedidos_tabela = [p for p in pedidos_fixos if p not in pedidos_selecionados] + pedidos_selecionados
            # inclui compras selecionadas ao final, mantendo ordem e sem duplicar
            for oc in compras_plan:
                if oc not in pedidos_tabela and oc in df_final.columns:
                    pedidos_tabela.append(oc)
            
            # Permitir ao usuário excluir pedidos da tabela (por plano)
            saved_excluidos = this_pref.get('pedidos_excluidos') or []
            default_excluir = [p for p in saved_excluidos if p in pedidos_tabela] if saved_excluidos else []
            excluir_pedidos = st.multiselect(
                f"Excluir pedidos da tabela (não serão considerados no consumo) ({plan['name']}):",
                pedidos_tabela,
                default=default_excluir,
                key=f"excluir_pedidos_{prefix}",
                help="Selecione pedidos que devem ser ignorados nos cálculos e na visualização da tabela de consumo/estoque."
            )

            # Controle para definir percentual extra no consumo total (por plano)
            saved_perc = this_pref.get('consumo_perc_extra')
            try:
                default_perc = float(saved_perc) if saved_perc is not None else 0.0
            except Exception:
                default_perc = 0.0
            perc_extra = st.number_input(f"Ajuste percentual no Consumo Total (%) ({plan['name']}):", min_value=0.0, max_value=500.0, value=default_perc, step=1.0, key=f"consumo_perc_extra_{prefix}", help="Defina um percentual extra para aumentar o consumo previsto (ex: 10 = +10%).")

            # aplica exclusões ao conjunto de pedidos exibidos/cálculados
            pedidos_tabela = [p for p in pedidos_tabela if p not in (excluir_pedidos or [])]

            df_filtrado_gantt = df_final.copy()
            colunas_exibir = colunas_base + pedidos_tabela
            colunas_exibir = [col for col in colunas_exibir if col in df_filtrado_gantt.columns]
            df_filtrado_gantt = df_filtrado_gantt[colunas_exibir]

            # Determina pedidos efetivamente considerados, separando CONSUMO vs COMPRAS
            pedidos_excluidos_set = set(excluir_pedidos or [])
            considerados = [
                col for col in pedidos_tabela
                if col not in pedidos_excluidos_set and col in df_filtrado_gantt.columns
            ]
            # Divide entre demanda (consumo) e compras, com base no conjunto global
            demand_considerados = [c for c in considerados if str(c) not in PURCHASE_ORDER_COLUMNS]
            purchase_considerados = [c for c in considerados if str(c) in PURCHASE_ORDER_COLUMNS]
            # Mantém compatibilidade com a visão mensal, que usa o nome 'pedidos_para_consumo'
            pedidos_para_consumo = list(demand_considerados)

            df_filtrado_gantt['Consumo_Base'] = df_filtrado_gantt[demand_considerados].sum(axis=1) if demand_considerados else 0
            df_filtrado_gantt['Compras_Total'] = df_filtrado_gantt[purchase_considerados].sum(axis=1) if purchase_considerados else 0

            # Feedback ao usuário
            st.caption(
                "Pedidos usados no consumo (fixos + selecionados): " + (
                    (", ".join(demand_considerados)) if demand_considerados else "(nenhum)"
                )
            )
            if purchase_considerados:
                st.caption(
                    "Pedidos de COMPRA incluídos: " + ", ".join(purchase_considerados)
                )
            if pedidos_excluidos_set:
                st.caption(
                    f"Pedidos excluídos (ignorados no cálculo): {', '.join(sorted(pedidos_excluidos_set))}"
                )
            # aplica percentual extra configurado pelo usuário (apenas sobre consumo)
            try:
                perc = float(st.session_state.get(f'consumo_perc_extra_{prefix}', 0) or 0)
            except Exception:
                perc = 0.0
            df_filtrado_gantt['Consumo_Total_Pedidos'] = df_filtrado_gantt['Consumo_Base'] * (1 + perc/100.0)
            df_filtrado_gantt['Estoque_Descontado'] = df_filtrado_gantt['estoque_total'] - df_filtrado_gantt['Consumo_Total_Pedidos'] + df_filtrado_gantt['Compras_Total']

            df_filtrado_gantt = df_filtrado_gantt.sort_values(by='Consumo_Total_Pedidos', ascending=False)

            df_exib_gantt = df_filtrado_gantt.copy()
            num_cols = df_exib_gantt.select_dtypes(include=['number']).columns.tolist()
            for c in num_cols:
                try:
                    df_exib_gantt[c] = df_exib_gantt[c].round(1)
                except Exception:
                    pass
            # Fixar as colunas 'descricao' e 'descricao_cor' como índice para que fiquem visíveis
            # ao rolar horizontalmente na tabela do Streamlit (index é mantido fixo na UI).
            try:
                if 'descricao' in df_exib_gantt.columns and 'descricao_cor' in df_exib_gantt.columns:
                    df_exib_gantt.set_index(['descricao', 'descricao_cor'], inplace=True)
            except Exception:
                pass
            # Aumentada a altura para facilitar visualização do planejamento
            st.dataframe(format_dataframe_brazilian(df_exib_gantt, decimals=1), height=700)

            # Botão para download em Excel da tabela atual + metadados do plano
            try:
                import io as _io
                buffer_xlsx = _io.BytesIO()
                with pd.ExcelWriter(buffer_xlsx, engine='openpyxl') as writer:
                    # salva os dados (sem formatação de exibição)
                    try:
                        df_filtrado_gantt.to_excel(writer, sheet_name='dados', index=False)
                    except Exception:
                        # fallback se houver problemas
                        pd.DataFrame(df_filtrado_gantt).to_excel(writer, sheet_name='dados', index=False)

                    # metadata com seleções do usuário
                    meta = {
                        'plano_id': plan_id,
                        'plano_name': plan.get('name'),
                        'pedidos_selecionados': ','.join(pedidos_selecionados) if pedidos_selecionados else '',
                        'pedidos_excluidos': ','.join(excluir_pedidos) if excluir_pedidos else '',
                        'consumo_perc_extra': perc_extra
                    }
                    meta_df = pd.DataFrame(list(meta.items()), columns=['chave', 'valor'])
                    meta_df.to_excel(writer, sheet_name='metadata', index=False)

                buffer_xlsx.seek(0)
                file_name = f"planejamento_boxer_plan{plan_id}_{plan.get('name').replace(' ', '_')}.xlsx"
                st.download_button(label='Exportar tabela do planejamento para Excel', data=buffer_xlsx, file_name=file_name, mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            except Exception:
                # se openpyxl não estiver disponível ou ocorrer erro, oferecer CSV como fallback
                try:
                    csv_buffer = df_filtrado_gantt.to_csv(index=False).encode('utf-8')
                    st.download_button(label='Exportar tabela do planejamento (CSV)', data=csv_buffer, file_name=f"planejamento_boxer_plan{plan_id}.csv", mime='text/csv')
                except Exception:
                    st.info('Erro ao preparar arquivo para download.')

            # ---------------- Visão mensal do planejamento ----------------
            st.markdown("#### Planejamento Mensal")
            try:
                # Selector único no formato mm/yyyy (namespaced por plano)
                today = datetime.date.today()
                # Determinar somente os meses que têm pelo menos um pedido no planejamento (df_gantt)
                months_set = set()
                for entry in df_gantt:
                    try:
                        s = datetime.datetime.strptime(entry.get('Start'), '%Y-%m-%d').date()
                        f = datetime.datetime.strptime(entry.get('Finish'), '%Y-%m-%d').date()
                        cur = s.replace(day=1)
                        while cur <= f:
                            months_set.add((cur.year, cur.month))
                            cur = (cur.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
                    except Exception:
                        continue

                months_list = sorted(list(months_set))
                options_mmyyyy = [f"{m:02d}/{y}" for (y, m) in months_list]
                # fallback para mês atual se não houver planejamento
                default_value = f"{today.month:02d}/{today.year}"
                if not options_mmyyyy:
                    options_mmyyyy = [default_value]
                default_index = options_mmyyyy.index(default_value) if default_value in options_mmyyyy else 0
                sel_mmyyyy = st.selectbox('Mês/Ano', options_mmyyyy, index=default_index, key=f'mes_ano_{prefix}')

                # calcula intervalo do mês selecionado a partir do mm/yyyy
                try:
                    month_idx = int(sel_mmyyyy.split('/')[0])
                    sel_year = int(sel_mmyyyy.split('/')[1])
                except Exception:
                    month_idx = today.month
                    sel_year = today.year
                month_start = datetime.date(sel_year, month_idx, 1)
                # primeiro dia do próximo mês
                next_month = (month_start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
                month_end = next_month - datetime.timedelta(days=1)

                # mapeia datas de cada pedido a partir de df_gantt (Task, Start, Finish)
                pedidos_dates = {}
                for entry in df_gantt:
                    try:
                        t = entry.get('Task')
                        s = datetime.datetime.strptime(entry.get('Start'), '%Y-%m-%d').date()
                        f = datetime.datetime.strptime(entry.get('Finish'), '%Y-%m-%d').date()
                        pedidos_dates[t] = (s, f)
                    except Exception:
                        continue

                # prepara tabela mensal: mesma estrutura de colunas_base + pedidos considerados
                if pedidos_para_consumo:
                    # filtra apenas pedidos que têm algum overlap com o mês selecionado (para exibir colunas por pedido neste mês)
                    pedidos_in_month = []
                    for pedido in pedidos_para_consumo:
                        s_f = pedidos_dates.get(pedido)
                        if not s_f:
                            continue
                        s, f = s_f
                        overlap_start = max(s, month_start)
                        overlap_end = min(f, month_end)
                        if overlap_end >= overlap_start:
                            pedidos_in_month.append(pedido)

                    rows = []
                    for _, linha in df_filtrado_gantt.iterrows():
                        row_out = {c: linha.get(c) for c in colunas_base}
                        total_mes = 0.0
                        total_prev = 0.0

                        # 1) Consumo acumulado ANTES do início do mês selecionado: considerar TODOS os pedidos_para_consumo
                        prev_end = month_start - datetime.timedelta(days=1)
                        for pedido in pedidos_para_consumo:
                            val_pedido = float(linha.get(pedido, 0) or 0)
                            s_f = pedidos_dates.get(pedido)
                            if not s_f or val_pedido == 0:
                                continue
                            s, f = s_f
                            if s <= prev_end:
                                prev_overlap_end = min(f, prev_end)
                                if prev_overlap_end >= s:
                                    prev_overlap_days = (prev_overlap_end - s).days + 1
                                    dur = (f - s).days + 1 if (f - s).days + 1 > 0 else 1
                                    total_prev += val_pedido * (prev_overlap_days / dur)

                        # 2) Consumo DENTRO do mês selecionado: considerar apenas pedidos com overlap no mês (pedidos_in_month)
                        for pedido in pedidos_in_month:
                            val_pedido = float(linha.get(pedido, 0) or 0)
                            s_f = pedidos_dates.get(pedido)
                            prop_mes = 0.0
                            if s_f and val_pedido != 0:
                                s, f = s_f
                                overlap_start = max(s, month_start)
                                overlap_end = min(f, month_end)
                                if overlap_end >= overlap_start:
                                    overlap_days = (overlap_end - overlap_start).days + 1
                                    dur = (f - s).days + 1 if (f - s).days + 1 > 0 else 1
                                    prop_mes = val_pedido * (overlap_days / dur)
                            # guarda proporcional do mês (coluna por pedido) somente para os que têm overlap no mês
                            row_out[pedido] = round(prop_mes, 1)
                            total_mes += prop_mes

                        # aplica percentual extra configurado no plano (tanto no mês quanto no acumulado anterior)
                        try:
                            perc_cfg = float(st.session_state.get(f'consumo_perc_extra_{prefix}', 0) or 0)
                        except Exception:
                            perc_cfg = 0.0
                        total_mes = total_mes * (1 + perc_cfg / 100.0)
                        total_prev = total_prev * (1 + perc_cfg / 100.0)
                        row_out['Consumo_Total_Pedidos'] = round(total_mes, 1)
                        estoque_total_val = float(linha.get('estoque_total', 0) or 0)
                        # Estoque no fim do mês selecionado = estoque atual - consumo acumulado até o fim do mês (prev + mês)
                        row_out['Estoque_Descontado'] = round(estoque_total_val - (total_prev + total_mes), 1)
                        rows.append(row_out)

                    df_mes = pd.DataFrame(rows)
                    # manter ordem de colunas: base + pedidos_in_month (se houver) + col totals
                    pedidos_cols_order = [p for p in pedidos_in_month if p in df_mes.columns]
                    cols_out = colunas_base + pedidos_cols_order + ['Consumo_Total_Pedidos', 'Estoque_Descontado']
                    df_mes = df_mes[[c for c in cols_out if c in df_mes.columns]]
                    # formatar para exibição
                    try:
                        if 'descricao' in df_mes.columns and 'descricao_cor' in df_mes.columns:
                            df_mes.set_index(['descricao', 'descricao_cor'], inplace=True)
                    except Exception:
                        pass

                    st.dataframe(format_dataframe_brazilian(df_mes, decimals=1), height=400)

                    # download mensal
                    try:
                        buf = io.BytesIO()
                        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                            df_mes.reset_index().to_excel(writer, sheet_name='mes', index=False)
                            meta = {'plano_id': plan_id, 'mes': f'{sel_year}-{month_idx:02d}'}
                            pd.DataFrame(list(meta.items()), columns=['chave', 'valor']).to_excel(writer, sheet_name='metadata', index=False)
                        buf.seek(0)
                        st.download_button(label='Exportar visão mensal (Excel)', data=buf, file_name=f'planejamento_boxer_plan{plan_id}_{sel_year}_{month_idx:02d}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    except Exception:
                        try:
                            csv_buf = df_mes.reset_index().to_csv(index=False).encode('utf-8')
                            st.download_button(label='Exportar visão mensal (CSV)', data=csv_buf, file_name=f'planejamento_boxer_plan{plan_id}_{sel_year}_{month_idx:02d}.csv', mime='text/csv')
                        except Exception:
                            st.info('Erro ao preparar exportação mensal.')
                else:
                    st.info('Nenhum pedido de consumo identificado para cálculo mensal.')
            except Exception as e:
                st.warning(f'Erro ao calcular visão mensal: {e}')

            st.markdown("#### Selecione os itens para visualizar a evolução do estoque")
            options_for_selected = [f"{row['descricao']} | {row['descricao_cor']}" for _, row in df_filtrado_gantt.iterrows()] if 'descricao' in df_filtrado_gantt.columns and 'descricao_cor' in df_filtrado_gantt.columns else df_filtrado_gantt.index.astype(str)
            saved_selected = this_pref.get('selected_rows') or []
            default_selected = [s for s in saved_selected if s in options_for_selected] if saved_selected else None
            selected_rows = st.multiselect(
                f"Selecione os materiais (linha) para evolução do estoque ({plan['name']}):",
                options_for_selected,
                default=default_selected,
                key=f"selected_rows_{prefix}",
                help="Selecione um ou mais materiais para visualizar a evolução do estoque ao longo do tempo. Cada opção mostra o material e a cor."
            )

            if selected_rows:
                datas_gantt = []
                for pedido in pedidos_selecionados:
                    for entry in df_gantt:
                        if entry['Task'] == pedido:
                            data_inicio = datetime.datetime.strptime(entry['Start'], "%Y-%m-%d").date()
                            data_fim = datetime.datetime.strptime(entry['Finish'], "%Y-%m-%d").date()
                            datas_gantt.append((pedido, data_inicio, data_fim))
                todas_datas = set()
                for _, ini, fim in datas_gantt:
                    for d in range((fim-ini).days+1):
                        todas_datas.add(ini + datetime.timedelta(days=d))
                # Adiciona datas de entrega das OCs selecionadas no plano ao eixo X
                try:
                    compras_plan = st.session_state.get(f"compras_{prefix}", []) or this_pref.get('compras_selecionadas') or []
                except Exception:
                    compras_plan = []
                try:
                    for (desc_i, cor_i, num_i), (dt_i, _qt_i) in PURCHASE_DELIVERY_BY_ITEM.items():
                        if str(num_i) in compras_plan and dt_i is not None:
                            todas_datas.add(dt_i)
                except Exception:
                    pass
                todas_datas = sorted(list(todas_datas))

                evolucao = {}
                for item in selected_rows:
                    if 'descricao' in df_filtrado_gantt.columns and 'descricao_cor' in df_filtrado_gantt.columns:
                        desc, cor = item.split(' | ', 1)
                        linha = df_filtrado_gantt[(df_filtrado_gantt['descricao'] == desc) & (df_filtrado_gantt['descricao_cor'] == cor)]
                        nome_legenda = f"{desc} | {cor}"
                    else:
                        linha = df_filtrado_gantt.loc[[item]]
                        nome_legenda = str(item)
                    if linha.empty:
                        continue
                    estoque_inicial = linha['Estoque_Descontado'].values[0] if 'Estoque_Descontado' in linha.columns else linha['estoque_total'].values[0]
                    estoque_evol = []
                    estoque_atual = estoque_inicial
                    # Mapa de acréscimos por data (somatório de OCs selecionadas para este item)
                    add_por_data = {}
                    try:
                        for oc in compras_plan:
                            key = (str(desc), str(cor), str(oc)) if 'descricao' in df_filtrado_gantt.columns else None
                            if key and key in PURCHASE_DELIVERY_BY_ITEM:
                                dt_ent, qt = PURCHASE_DELIVERY_BY_ITEM.get(key, (None, 0.0))
                                if dt_ent:
                                    add_por_data[dt_ent] = add_por_data.get(dt_ent, 0.0) + float(qt or 0)
                    except Exception:
                        pass
                    for dt in todas_datas:
                        consumo_dia = 0
                        for pedido, ini, fim in datas_gantt:
                            if pedido in linha.columns and ini <= dt <= fim:
                                consumo_total = linha[pedido].values[0]
                                dias = (fim-ini).days+1
                                consumo_diario = consumo_total/dias if dias > 0 else consumo_total
                                consumo_dia += consumo_diario
                        estoque_atual -= consumo_dia
                        # Aplica entrada de OCs na data de entrega (estoque cresce a partir dessa data)
                        try:
                            inc = add_por_data.get(dt, 0.0)
                            if inc:
                                estoque_atual += inc
                        except Exception:
                            pass
                        estoque_evol.append(estoque_atual)
                    evolucao[nome_legenda] = estoque_evol

                import plotly.graph_objects as go
                fig_evol = go.Figure()
                for item, estoque_evol in evolucao.items():
                    fig_evol.add_trace(go.Scatter(x=[dt.strftime('%d/%m/%Y') for dt in todas_datas], y=estoque_evol, mode='lines+markers', name=str(item)))
                fig_evol.update_layout(title="Evolução do Estoque dos Materiais Selecionados", xaxis_title="Data", yaxis_title="Estoque", legend_title="Material")
                st.plotly_chart(fig_evol, use_container_width=True)
        else:
            st.info("Selecione ao menos um pedido para visualizar o Gantt.")

    # Renderiza o plano ativo
    render_gantt_for_plan(plano_ativo)