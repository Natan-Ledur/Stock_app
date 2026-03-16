import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
import os
import sys
import subprocess
import platform
from datetime import datetime, timedelta

API_BASE = os.getenv("API_BASE", "http://backend2:8001/api")

# Correção de importação para encontrar mongo_utils em frontend/app
app_dir = os.path.dirname(os.path.dirname(__file__))  # frontend/app
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

try:
    from mongo_utils import get_database
except ImportError as e:
    st.error(f"Erro ao importar mongo_utils: {e}")
    def get_database(db_name=None): return None

try:
    import format_utils
    import importlib
    importlib.reload(format_utils)
    from format_utils import get_color_hex
except ImportError as e:
    st.error(f"Erro ao importar format_utils: {e}")
    # Fallback simples se falhar
    def get_color_hex(name): return "#808080"

# ==============================================================================
# Configuração de Ambiente e Conexão
# ==============================================================================
@st.cache_resource(ttl=60)
def get_mongo_connection():
    return get_database()

# ==============================================================================
# Helpers de Atualização e Persistência (Inspirado no basedashboard)
# ==============================================================================

def rodar_main_py():
    """Executa o script de atualização de dados (maindf.py)."""
    # Procura maindf.py na mesma pasta
    script = os.path.join(os.path.dirname(__file__), "maindf.py")
    if not os.path.exists(script):
        st.error(f"Script {script} não encontrado.")
        return
        
    cmd = [sys.executable, script]
    try:
        with st.spinner("Atualizando dados... Isso pode levar alguns minutos."):
            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        output = "".join(filter(None, [resultado.stdout or "", resultado.stderr or ""]))
        
        if resultado.returncode == 0:
            st.success("Dados atualizados com sucesso!")
            with st.expander("Ver log da execução"):
                st.code(output)
            # Limpa cache para pegar dados novos
            st.cache_data.clear()
        else:
            st.error("Erro ao atualizar dados.")
            with st.expander("Ver detalhes do erro"):
                st.code(output)
    except subprocess.TimeoutExpired:
        st.error("Tempo limite esgotado na atualização.")
    except Exception as e:
        st.error(f"Erro ao tentar executar script: {e}")

# --- Gerenciamento de Planejamentos (Salvos no Mongo) ---
def get_all_plans(db):
    """Lista todos os planejamentos salvos."""
    if db is None: return []
    try:
        col = db['boxer_planejamento']
        return list(col.find({}, {'_id': 0}).sort('plan_id', 1))
    except Exception:
        return []

def save_plan(db, plan_id, name, data):
    """Salva ou atualiza um planejamento."""
    if db is None: return False
    try:
        col = db['boxer_planejamento']
        # Flatten structure to match existing MongoDB schema if possible
        payload = {
            'plan_id': plan_id,
            'name': name,
            'updated_at': datetime.now(),
            'pedidos_selecionados': data.get('pedidos_selecionados', []),
            'gantt_dates': data.get('dates', {}) 
        }
        col.replace_one({'plan_id': plan_id}, payload, upsert=True)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar plano: {e}")
        return False

def delete_plan_db(db, plan_id):
    if db is None: return False
    try:
        col = db['boxer_planejamento']
        col.delete_one({'plan_id': plan_id})
        return True
    except Exception:
        return False

# ==============================================================================
# Carregamento de Dados
# ==============================================================================
@st.cache_data(ttl=300) # Cache por 5 minutos
def load_data():
    db = get_mongo_connection()
    if db is None:
        return None, None, None

    # Helper para carregar e limpar _id
    def fetch_collection(coll_name):
        try:
            data = list(db[coll_name].find())
            if not data:
                return pd.DataFrame()
            df = pd.DataFrame(data)
            if '_id' in df.columns:
                df = df.drop(columns=['_id'])
            return df
        except Exception:
            return pd.DataFrame()

    df_consumos = fetch_collection('boxer_pedido_consumos')
    df_estoque = fetch_collection('boxer_estoque')
    df_compras = fetch_collection('compras_fios')

    return df_consumos, df_estoque, df_compras

def process_mrp_data(df_consumos, df_estoque, df_compras):
    """
    Processa e cruza as informações para gerar o Balanço de Materiais (MRP).
    """
    if df_consumos.empty:
        return pd.DataFrame()

    # 1. Agrupar Consumo (Necessidade)
    # Chaves: material_cod, cor_cod
    # Soma: consumo_total
    
    # Normalização de tipos para garantir merge
    df_cons_agg = df_consumos.groupby(['material_cod', 'cor_cod', 'descricao_mat', 'descricao_cor'], as_index=False)['consumo_total'].sum()
    df_cons_agg['key_mat'] = df_cons_agg['material_cod'].astype(str).str.strip()
    df_cons_agg['key_cor'] = df_cons_agg['cor_cod'].astype(str).str.strip()

    # 2. Agrupar Estoque (Disponibilidade)
    # Chaves: codigo, cor
    # Soma: estoque_total
    if not df_estoque.empty:
        df_est_agg = df_estoque.groupby(['codigo', 'cor'], as_index=False)['estoque_total'].sum()
        df_est_agg['key_mat'] = df_est_agg['codigo'].astype(str).str.strip()
        df_est_agg['key_cor'] = df_est_agg['cor'].astype(str).str.strip()
    else:
        df_est_agg = pd.DataFrame(columns=['key_mat', 'key_cor', 'estoque_total'])

    # 3. Agrupar Compras (Entradas Futuras)
    # Chaves: codigo, cor
    # Soma: qtde
    if not df_compras.empty:
        # Garantir colunas
        cols_compras = [c.lower() for c in df_compras.columns]
        df_compras.columns = cols_compras
        if 'qtde' in df_compras.columns and 'codigo' in df_compras.columns:
            df_comp_agg = df_compras.groupby(['codigo', 'cor'], as_index=False)['qtde'].sum()
            df_comp_agg['key_mat'] = df_comp_agg['codigo'].astype(str).str.strip()
            df_comp_agg['key_cor'] = df_comp_agg['cor'].astype(str).str.strip()
        else:
            df_comp_agg = pd.DataFrame(columns=['key_mat', 'key_cor', 'qtde'])
    else:
        df_comp_agg = pd.DataFrame(columns=['key_mat', 'key_cor', 'qtde'])

    # 4. Merge Completo (Começando pelo Consumo pois é o foco da necessidade)
    # Usaremos outer join para ver também o que tem estoque mas sem demanda (opcional, aqui focaremos na demanda)
    df_mrp = pd.merge(df_cons_agg, df_est_agg[['key_mat', 'key_cor', 'estoque_total']], on=['key_mat', 'key_cor'], how='left')
    df_mrp = pd.merge(df_mrp, df_comp_agg[['key_mat', 'key_cor', 'qtde']], on=['key_mat', 'key_cor'], how='left')

    # 5. Limpeza e Cálculos
    df_mrp['estoque_total'] = df_mrp['estoque_total'].fillna(0)
    df_mrp['compras_futuras'] = df_mrp['qtde'].fillna(0)
    
    # Saldo = (Estoque + Compras) - Demanda
    df_mrp['saldo_final'] = (df_mrp['estoque_total'] + df_mrp['compras_futuras']) - df_mrp['consumo_total']
    
    # Status
    def get_status(row):
        if row['saldo_final'] >= 0:
            return 'OK'
        elif (row['saldo_final'] + row['compras_futuras']) < 0:
            # Mesmo com compras, falta
             return 'CRÍTICO' # (na verdade a conta acima ja inclui compras, então se saldo < 0 é falta real)
        else:
            return 'ATENÇÃO'

    df_mrp['status'] = df_mrp['saldo_final'].apply(lambda x: 'CRÍTICO' if x < -0.01 else 'OK')
    
    return df_mrp

# ==============================================================================
# Helpers de UI e Gráficos
# ==============================================================================
# Função get_color_hex movida para format_utils.py para ser compartilhada

# ==============================================================================
# Interface Principal
# ==============================================================================

# Sidebar de Ações
#with st.sidebar:
 #   st.header("Ferramentas")
  #  if st.button("🔄 Atualizar Dados (Script)"):
   #     rodar_main_py()
    
    #st.divider()
    #st.caption("Conexão MongoDB:")
    #db_conn = get_mongo_connection()
    #if db_conn is not None:
    #    st.success("Conectado")
    #else:
    #    st.error("Desconectado")

st.title("🧶 Dashboard Controle de Fios (Boxer)")
st.markdown("Visualização integrada de Consumo Previsto, Estoques e Compras.")

df_consumos, df_estoque, df_compras = load_data()

if df_consumos is None:
    st.warning("Não foi possível carregar os dados. Verifique a conexão com o MongoDB.")
    st.stop()

# Gera dados MRP
df_mrp = process_mrp_data(df_consumos, df_estoque, df_compras)

# Abas Superiores (Adicionada aba de Planejamento)
tab4, tab1, tab2, tab3, tab_plan = st.tabs([
    "⚖️ Balanço & Necessidade (MRP)", 
    "📊 Pedidos & Consumo", 
    "📦 Estoque Disponível", 
    "🛒 Compras & Entregas",
    "📅 Planejamento"
])

# ==============================================================================
# ABA 4: MRP (BALANÇO) - NOVA ABA PRINCIPAL
# ==============================================================================
with tab4:
    st.header("Planejamento de Necessidades de Materiais")
    st.markdown("Cruzamento entre **Demanda dos Pedidos** vs. **Estoque Físico + Compras**.")

    # Filtro de Setor para o MRP
    df_cons_mrp = df_consumos.copy()
    if 'setor' in df_cons_mrp.columns:
        setores_disp = sorted(df_cons_mrp['setor'].astype(str).unique())
        # Coloca o filtro em um expander para não poluir
        with st.expander("🔎 Filtrar Demanda por Setor"):
            sel_setores_mrp = st.multiselect("Considerar demanda apenas dos setores:", options=setores_disp, default=[])
        
        if sel_setores_mrp:
            df_cons_mrp = df_cons_mrp[df_cons_mrp['setor'].astype(str).isin(sel_setores_mrp)]
            st.caption(f"Calculando necessidades baseadas apenas nos setores: {', '.join(sel_setores_mrp)}")

    # Recalcula MRP com base no consumo filtrado (Estoque e Compras permanecem totais)
    df_mrp_calc = process_mrp_data(df_cons_mrp, df_estoque, df_compras)

    if df_mrp_calc.empty:
        st.info("Sem dados suficientes para gerar MRP.")
    else:
        # KPI do MRP
        criticos = df_mrp_calc[df_mrp_calc['status'] == 'CRÍTICO']
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total de Materiais", df_mrp_calc.shape[0])
        k2.metric("Itens Críticos (Falta)", criticos.shape[0], delta_color="inverse", delta=f"{criticos.shape[0]}")
        
        falta_kg = criticos['saldo_final'].sum()
        k3.metric("Déficit Total (Kg)", f"{falta_kg:,.2f}", delta_color="inverse")
        
        # Filtro de visualização
        st.divider()
        viz_mode = st.radio("Filtro de Visualização:", ["Apenas Críticos (Com Falta)", "Todos os Itens"], horizontal=True)
        
        df_view = criticos if viz_mode == "Apenas Críticos (Com Falta)" else df_mrp_calc

        # Tabela Colorida
        # Vamos formatar para exibir melhor
        df_display = df_view[['descricao_mat', 'descricao_cor', 'key_mat', 'key_cor', 'estoque_total', 'compras_futuras', 'consumo_total', 'saldo_final', 'status']].copy()
        
        # Renomear colunas para PT-BR amigável
        df_display.columns = ['Material', 'Cor', 'Cód. Mat', 'Cód. Cor', 'Estoque (Kg)', 'Compras (Kg)', 'Necessidade (Kg)', 'Saldo (Kg)', 'Status']

        st.dataframe(
            df_display.style.map(lambda x: 'color: red; font-weight: bold' if x < 0 else 'color: green', subset=['Saldo (Kg)']),
            use_container_width=True,
            hide_index=True,
            height=500
        )
        
        # Gráficos de Apoio
        c_mrp1, c_mrp2 = st.columns(2)
        with c_mrp1:
            st.subheader("Top 10 Maiores Déficits (Kg)")
            if not criticos.empty:
                # 1. Identificar Top 10 Materiais com maior déficit total (soma dos saldos negativos)
                df_deficit_mat = criticos.groupby('descricao_mat')['saldo_final'].sum().sort_values(ascending=True).head(10)
                top_deficit_mats = df_deficit_mat.index.tolist()

                # 2. Filtrar dados e preparar para o gráfico
                df_chart_mrp = criticos[criticos['descricao_mat'].isin(top_deficit_mats)].copy()
                df_chart_mrp['falta_abs'] = df_chart_mrp['saldo_final'].abs()

                # 3. Ordenação para Overlay (Maior falta no fundo)
                # Ordena por Material (alfabético ou cluster) e depois pela Quantidade de Falta (Decrescente)
                df_chart_mrp = df_chart_mrp.sort_values(by=['descricao_mat', 'falta_abs'], ascending=[True, False])

                # 4. Mapa de Cores (usando a função global 'get_color_hex')
                unique_colors_mrp = df_chart_mrp['descricao_cor'].unique()
                color_map_mrp = {}
                for c_name in unique_colors_mrp:
                     hex_val = get_color_hex(c_name)
                     if hex_val: 
                        color_map_mrp[c_name] = hex_val

                fig_falta = px.bar(
                    df_chart_mrp, 
                    y='descricao_mat', 
                    x='falta_abs', 
                    color='descricao_cor',
                    orientation='h', 
                    text_auto='.1f', 
                    title="Top 10 Materiais em Falta (Detalhado por Cor)",
                    color_discrete_map=color_map_mrp
                )
                
                # Configuração para Overlay (Camadas)
                fig_falta.update_layout(
                    xaxis_title="Quantidade Faltante (Kg)", 
                    yaxis_title="Material", 
                    barmode='overlay', 
                    yaxis={'categoryorder':'total ascending'} # Ordena o eixo Y pelo total geral da barra
                )
                fig_falta.update_traces(marker_line_color='rgb(50,50,50)', marker_line_width=1, opacity=1.0)
                
                st.plotly_chart(fig_falta, use_container_width=True)
            else:
                st.success("Tudo certo! Sem déficits no momento.")

        with c_mrp2:
            st.subheader("Status Geral dos Materiais")
            df_status = df_mrp_calc['status'].value_counts().reset_index()
            df_status.columns = ['status', 'count']
            fig_pie = px.pie(df_status, names='status', values='count', color='status', color_discrete_map={'OK': '#00CC96', 'CRÍTICO': '#EF553B'})
            st.plotly_chart(fig_pie, use_container_width=True)

# ==============================================================================
# ABA PLAN: PLANEJAMENTO (GANTT E CENÁRIOS) - Baseado no BaseDashboard
# ==============================================================================
with tab_plan:
    st.header("Planejamento & Cronograma")
    
    # 1. Carregar Planos do Banco
    db = get_mongo_connection()
    planos_db = get_all_plans(db) # Lista de dicts {plan_id, name, data}
    
    if not planos_db:
        # Cria plano default se não existir
        save_plan(db, 1, "Planejamento Inicial", {})
        planos_db = get_all_plans(db)

    # 2. Controles de Seleção de Plano
    col_sel_p, col_add_p, col_del_p = st.columns([6, 3, 1])
    
    with col_sel_p:
        plan_options = {p['plan_id']: f"{p['plan_id']} - {p['name']}" for p in planos_db}
        selected_plan_id = st.selectbox("Selecione o Plano:", options=list(plan_options.keys()), format_func=lambda x: plan_options[x])
    
    with col_add_p:
        new_plan_name = st.text_input("Novo Plano", placeholder="Nome do plano...", label_visibility="collapsed")
        if st.button("➕ Criar Plano"):
            if new_plan_name:
                new_id = max([p['plan_id'] for p in planos_db]) + 1
                save_plan(db, new_id, new_plan_name, {})
                st.rerun()

    with col_del_p:
        if st.button("🗑️", help="Excluir plano selecionado"):
            if len(planos_db) > 1:
                delete_plan_db(db, selected_plan_id)
                st.rerun()
            else:
                st.toast("Não é possível excluir o último plano.")

    # 3. Carregar Dados do Plano Selecionado
    current_plan = next((p for p in planos_db if p['plan_id'] == selected_plan_id), None)
    
    plan_data = {}
    if current_plan:
        # Compatibilidade: Verifica se está no formato antigo ('data') ou novo (raiz)
        if 'data' in current_plan and current_plan['data']:
             plan_data = current_plan['data']
        else:
             plan_data = {
                 'pedidos_selecionados': current_plan.get('pedidos_selecionados', []),
                 'dates': current_plan.get('gantt_dates', {})
             }
    
    st.divider()
    
    # 4. Seleção de Pedidos para o Gantt
    st.markdown("##### Seleção de Pedidos")
    
    # Filtro auxiliar de setor para facilitar a busca
    df_aux_plan = df_consumos.copy()
    if 'setor' in df_aux_plan.columns:
        setores_plan = sorted(df_aux_plan['setor'].astype(str).unique())
        filtro_setor_plan = st.multiselect("Filtrar lista por Setor:", options=setores_plan, key="filter_sector_plan")
        if filtro_setor_plan:
            df_aux_plan = df_aux_plan[df_aux_plan['setor'].astype(str).isin(filtro_setor_plan)]
            
    all_pedidos = sorted(df_aux_plan['pedido'].astype(str).unique()) if not df_aux_plan.empty else []
    
    saved_pedidos = plan_data.get('pedidos_selecionados', [])
    # Filtra apenas os que ainda existem no dataframe global (para evitar erro de chave)
    # Mas precisamos permitir que pedidos SALVOS apareçam mesmo se o filtro de setor estiver ativo? 
    # Melhor não, o filtro serve para seleção. Os salvos devem persistir.
    
    # Lista combinada para o multiselect: opções filtradas + o que já está salvo (para não sumir visualmente)
    options_combined = sorted(list(set(all_pedidos + saved_pedidos)))
    
    pedidos_selecionados = st.multiselect(
        f"Selecione os pedidos para o planejamento ({current_plan['name']}):",
        options=options_combined,
        default=saved_pedidos
    )
    
    # 5. Configuração de Datas (Inputs)
    st.subheader("Definição de Datas")
    
    # Recupera datas salvas
    saved_dates = plan_data.get('dates', {}) # Formato: {'pedido': {'start': 'Y-m-d', 'end': 'Y-m-d'}}
    
    current_dates = {}
    has_changes = False
    
    gantt_rows = []
    
    if pedidos_selecionados:
        # Grid para inputs de data
        for pedido in pedidos_selecionados:
            c1, c2, c3 = st.columns([1, 1, 3])
            
            # Tenta pegar datas salvas (compatibilidade end/finish)
            saved_date_obj = saved_dates.get(pedido, {})
            p_start_saved = saved_date_obj.get('start')
            p_end_saved = saved_date_obj.get('finish') or saved_date_obj.get('end')
            
            # Defaults: Hoje e Hoje+7
            d_start = datetime.strptime(p_start_saved, '%Y-%m-%d').date() if p_start_saved else datetime.now().date()
            d_end = datetime.strptime(p_end_saved, '%Y-%m-%d').date() if p_end_saved else (datetime.now() + timedelta(days=7)).date()
            
            with c1:
                new_start = st.date_input(f"Início {pedido}", value=d_start, key=f"start_{selected_plan_id}_{pedido}")
            with c2:
                new_end = st.date_input(f"Fim {pedido}", value=d_end, key=f"end_{selected_plan_id}_{pedido}")
            with c3:
                # Info extra do pedido
                info_ped = df_consumos[df_consumos['pedido'] == pedido]['quantidade'].sum()
                st.caption(f"Qtd Peças: {info_ped:,.0f} | Duração: {(new_end - new_start).days} dias")

            # Salva como 'finish' para manter padrão do schema do banco
            current_dates[pedido] = {'start': str(new_start), 'finish': str(new_end)}
            gantt_rows.append(dict(Task=pedido, Start=str(new_start), Finish=str(new_end), Resource=pedido))

        # Botão Salvar
        if st.button("💾 Salvar Planejamento"):
            new_data = {
                'pedidos_selecionados': pedidos_selecionados,
                'dates': current_dates
            }
            if save_plan(db, selected_plan_id, current_plan['name'], new_data):
                st.toast("Planejamento salvo com sucesso!", icon="💾")
            else:
                st.error("Erro ao salvar.")
    else:
        st.info("Selecione pedidos para iniciar o planejamento.")

    # 6. Gráfico de Gantt
    if gantt_rows:
        st.subheader("Cronograma Visual")
        df_gantt_chart = pd.DataFrame(gantt_rows)
        
        fig_gantt = px.timeline(
            df_gantt_chart, 
            x_start="Start", 
            x_end="Finish", 
            y="Task", 
            color="Resource",
            title=f"Cronograma - {current_plan['name']}"
        )
        fig_gantt.update_yaxes(categoryorder="total ascending") # Ordenar
        st.plotly_chart(fig_gantt, use_container_width=True)


# ==============================================================================
# ABA 1: PEDIDOS & CONSUMO
# ==============================================================================
with tab1:

    st.header("Análise de Demanda de Fios")
    
    if df_consumos.empty:
        st.info("Nenhum dado de consumo encontrado.")
    else:
        # Filtros Globais da Aba
        col_filtro1, col_filtro2, col_filtro3 = st.columns(3)
        with col_filtro1:
            setores_list = sorted(df_consumos['setor'].astype(str).unique()) if 'setor' in df_consumos.columns else []
            filtro_setor = st.multiselect("Filtrar por Setor", options=setores_list)

        with col_filtro2:
            pedidos_list = sorted(df_consumos['pedido'].astype(str).unique())
            filtro_pedido = st.multiselect("Filtrar por Pedido", options=pedidos_list)
        
        with col_filtro3:
            materiais_list = sorted(df_consumos['descricao_mat'].astype(str).unique()) if 'descricao_mat' in df_consumos.columns else []
            filtro_material = st.multiselect("Filtrar por Material", options=materiais_list)

        # Aplica Filtros
        df_cons_filtrado = df_consumos.copy()
        if filtro_setor:
             df_cons_filtrado = df_cons_filtrado[df_cons_filtrado['setor'].astype(str).isin(filtro_setor)]
        if filtro_pedido:
            df_cons_filtrado = df_cons_filtrado[df_cons_filtrado['pedido'].astype(str).isin(filtro_pedido)]
        if filtro_material:
            df_cons_filtrado = df_cons_filtrado[df_cons_filtrado['descricao_mat'].astype(str).isin(filtro_material)]
        
        # Garante coluna Setor na exibição
        display_cols = ['setor', 'pedido', 'codigo', 'cor', 'tamanho', 'quantidade', 'descricao_mat', 'consumo_total']
        if 'setor' not in df_cons_filtrado.columns:
            display_cols.remove('setor')

        # Garantir tipos numéricos
        cols_num = ['quantidade', 'consumo', 'consumo_total']
        for c in cols_num:
            if c in df_cons_filtrado.columns:
                df_cons_filtrado[c] = pd.to_numeric(df_cons_filtrado[c], errors='coerce').fillna(0)

        # KPIs
        kpi1, kpi2, kpi3 = st.columns(3)
        
        # Correção: Calcular peças únicas (Produto = Pedido + Codigo + Cor + Tamanho)
        # Se um produto consome 3 fios, ele aparece 3 vezes. Devemos contar apenas 1 vez a sua quantidade.
        df_unique_prod = df_cons_filtrado.drop_duplicates(subset=['pedido', 'codigo', 'cor', 'tamanho'])
        
        total_pecas = df_unique_prod['quantidade'].sum()
        total_kg = df_cons_filtrado['consumo_total'].sum()
        qtd_pedidos = df_cons_filtrado['pedido'].nunique()

        kpi1.metric("Peças Totais", f"{total_pecas:,.0f}")
        kpi2.metric("Consumo Estimado (Kg)", f"{total_kg:,.2f}")
        kpi3.metric("Pedidos Selecionados", f"{qtd_pedidos}")

        st.divider()

        # Gráficos
        c1, c2 = st.columns(2)
        
        with c1:
            # Consumo por Material (Top 10) - Agora Stacked por Cor
            if 'descricao_mat' in df_cons_filtrado.columns:
                # Se tiver a coluna de cor, fazemos empilhado
                if 'descricao_cor' in df_cons_filtrado.columns:
                     # 1. Identificar Top 10 Materiais (pelo total)
                    top_materials = df_cons_filtrado.groupby('descricao_mat')['consumo_total'].sum().sort_values(ascending=True).tail(10).index.tolist()
                    
                    # 2. Filtrar apenas esses materiais
                    df_chart = df_cons_filtrado[df_cons_filtrado['descricao_mat'].isin(top_materials)].copy()
                    
                    # 3. Agrupar por Material e Cor para o gráfico empilhado
                    df_chart_grouped = df_chart.groupby(['descricao_mat', 'descricao_cor'])['consumo_total'].sum().reset_index()
                    
                    # --- Lógica de Mapeamento de Cores ---
                    # (Usa função global get_color_hex)

                    # Cria o mapa de cores apenas para as cores presentes
                    unique_colors = df_chart_grouped['descricao_cor'].unique()
                    color_map = {}
                    for c_name in unique_colors:
                        hex_code = get_color_hex(c_name)
                        if hex_code:
                            color_map[c_name] = hex_code
                            
                    # Ordenação para Overlay: 
                    # Ordenamos de forma decrescente de 'consumo_total' dentro de cada material.
                    # O Plotly desenha na ordem do DataFrame. A primeira linha é desenhada primeiro (fica no fundo).
                    # A última linha é desenhada por último (fica na frente).
                    # Queremos: MAIORES A TRAZ (Fundo) -> MENORES A FRENTE (Topo).
                    # Portanto, a ordem no DataFrame deve ser: Maior -> ... -> Menor.
                    df_chart_grouped = df_chart_grouped.sort_values(by=['descricao_mat', 'consumo_total'], ascending=[True, False])

                    # Cria o mapa de cores apenas para as cores presentes
                    unique_colors = df_chart_grouped['descricao_cor'].unique()
                    color_map = {}
                    for c_name in unique_colors:
                        hex_code = get_color_hex(c_name)
                        if hex_code:
                            color_map[c_name] = hex_code
                            
                    # Ordenação para Overlay: 
                    # Ordenamos de forma decrescente de 'consumo_total' dentro de cada material.
                    # O Plotly desenha na ordem do DataFrame. A primeira linha é desenhada primeiro (fica no fundo).
                    # A última linha é desenhada por último (fica na frente).
                    # Queremos: MAIORES A TRAZ (Fundo) -> MENORES A FRENTE (Topo).
                    # Portanto, a ordem no DataFrame deve ser: Maior -> ... -> Menor.
                    df_chart_grouped = df_chart_grouped.sort_values(by=['descricao_mat', 'consumo_total'], ascending=[True, False])

                    fig_mat = px.bar(
                        df_chart_grouped, 
                        x='consumo_total', 
                        y='descricao_mat', 
                        color='descricao_cor',
                        orientation='h', 
                        title="Top 10 Materiais por Consumo (Cores Sobrepostas: Maior p/ Menor)", 
                        text_auto='.1f',
                        color_discrete_map=color_map 
                    )
                    
                    # barmode='overlay' faz todas as barras começarem do eixo 0.
                    # A ordem de desenho garante que as menores fiquem visíveis sobre as maiores.
                    fig_mat.update_layout(yaxis={'categoryorder':'total ascending'}, barmode='overlay')
                    
                    # Opacidade 1.0 para garantir que a barra da frente cubra a de trás (overlay visual)
                    fig_mat.update_traces(marker_line_color='rgb(50,50,50)', marker_line_width=1, opacity=1.0)
                    
                    st.plotly_chart(fig_mat, use_container_width=True)
                
                else:
                    # Fallback (caso não tenha coluna de cor)
                    df_mat = df_cons_filtrado.groupby('descricao_mat')['consumo_total'].sum().sort_values(ascending=True).tail(10)
                    fig_mat = px.bar(df_mat, orientation='h', title="Top 10 Materiais por Consumo (Kg)", text_auto='.2f')
                    st.plotly_chart(fig_mat, use_container_width=True)
            else:
                st.warning("Coluna 'descricao_mat' não encontrada.")

        with c2:
            # Distribuição por Tamanho
            if 'tamanho' in df_unique_prod.columns:
                # Usa o dataframe de produtos únicos para não somar quantidades duplicadas por material
                df_tam = df_unique_prod.groupby('tamanho')['quantidade'].sum().reset_index()
                fig_tam = px.pie(df_tam, values='quantidade', names='tamanho', title="Distribuição de Peças por Tamanho", hole=0.4)
                st.plotly_chart(fig_tam, use_container_width=True)

        st.subheader("Detalhamento de Consumo (Tabela)")
        st.dataframe(
            df_cons_filtrado[display_cols].sort_values('consumo_total', ascending=False),
            use_container_width=True,
            hide_index=True
        )

# ==============================================================================
# ABA 2: ESTOQUE
# ==============================================================================
with tab2:
    st.header("Posição de Estoque")
    
    if df_estoque.empty:
        st.info("Nenhum dado de estoque encontrado.")
    else:
        # Garantir numéricos
        if 'estoque_total' in df_estoque.columns:
            df_estoque['estoque_total'] = pd.to_numeric(df_estoque['estoque_total'], errors='coerce').fillna(0)

        # Filtro de grupo/subgrupo se existir
        if 'grupo' in df_estoque.columns:
            grupos = df_estoque['grupo'].unique()
            sel_grupo = st.selectbox("Filtrar Grupo de Estoque", options=['Todos'] + list(grupos))
            if sel_grupo != 'Todos':
                df_est_filtrado = df_estoque[df_estoque['grupo'] == sel_grupo]
            else:
                df_est_filtrado = df_estoque
        else:
            df_est_filtrado = df_estoque

        # Busca texto
        search_term = st.text_input("Buscar Item no Estoque (Descrição ou Código)")
        if search_term:
            mask = df_est_filtrado.astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)
            df_est_filtrado = df_est_filtrado[mask]

        # Visão Geral Estoque
        total_stock = df_est_filtrado['estoque_total'].sum() if 'estoque_total' in df_est_filtrado.columns else 0
        distinct_items = df_est_filtrado['codigo'].nunique() if 'codigo' in df_est_filtrado.columns else 0

        c_est1, c_est2 = st.columns(2)
        c_est1.metric("Saldo Físico Total (Kg)", f"{total_stock:,.2f}")
        c_est2.metric("Quantidade de Itens", f"{distinct_items}")

        # Gráfico de Barras com Overlay de Cores (Estilo Tab 1 e 4)
        if 'descricao' in df_est_filtrado.columns and 'estoque_total' in df_est_filtrado.columns:
            st.subheader("Top 15 Materiais em Estoque (Por Cor)")
            
            # 1. Identificar Top 15 Materiais por Estoque Total
            top_materials_est = df_est_filtrado.groupby('descricao')['estoque_total'].sum().sort_values(ascending=False).head(15).index.tolist()
            
            # 2. Filtrar dados apenas desses materiais
            df_chart_est = df_est_filtrado[df_est_filtrado['descricao'].isin(top_materials_est)].copy()
            
            # 3. Agrupar por Material e Cor (garantindo unicidade)
            if 'descricao_cor' in df_chart_est.columns:
                 df_chart_est_grouped = df_chart_est.groupby(['descricao', 'descricao_cor'])['estoque_total'].sum().reset_index()
                 
                 # 4. Ordenação para Overlay: 
                 # Material (para agrupar no eixo Y) e Quantidade Decrescente (para as maiores ficarem atrás)
                 df_chart_est_grouped = df_chart_est_grouped.sort_values(by=['descricao', 'estoque_total'], ascending=[True, False])
                 
                 # 5. Mapeamento de Cores
                 unique_colors_est = df_chart_est_grouped['descricao_cor'].unique()
                 color_map_est = {}
                 for c_name in unique_colors_est:
                     hex_val = get_color_hex(c_name)
                     if hex_val: 
                        color_map_est[c_name] = hex_val

                 fig_est = px.bar(
                    df_chart_est_grouped, 
                    x='estoque_total', 
                    y='descricao', 
                    orientation='h', 
                    color='descricao_cor',
                    title="Top 15 Estoques (Detalhado por Cor)",
                    text_auto='.1f',
                    color_discrete_map=color_map_est
                )
                 
                 fig_est.update_layout(
                     xaxis_title="Estoque Total (Kg)", 
                     yaxis_title="Material", 
                     barmode='overlay', 
                     yaxis={'categoryorder':'total ascending'},
                     height=800
                 )
                 fig_est.update_traces(marker_line_color='rgb(50,50,50)', marker_line_width=1, opacity=1.0)
                 
            else:
                # Fallback se não tiver cor
                df_top_est = df_est_filtrado.groupby('descricao')['estoque_total'].sum().nlargest(15)
                fig_est = px.bar(
                    df_top_est, 
                    orientation='h', 
                    title="Top 15 Itens em Estoque",
                    text_auto='.2f',
                    height=800
                )
            
            st.plotly_chart(fig_est, use_container_width=True)

        st.dataframe(df_est_filtrado, use_container_width=True, hide_index=True)

# ==============================================================================
# ABA 3: COMPRAS
# ==============================================================================
with tab3:
    st.header("Acompanhamento de Compras (1602)")

    if df_compras.empty:
        st.info("Nenhum dado de compras encontrado.")
    else:
        # Filtros
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            all_ped_compra = sorted(df_compras['numero'].astype(str).unique()) if 'numero' in df_compras.columns else []
            sel_ped_compra = st.multiselect("Filtrar Pedido de Compra", options=all_ped_compra)
        
        df_comp_filt = df_compras.copy()
        if sel_ped_compra:
            df_comp_filt = df_comp_filt[df_comp_filt['numero'].astype(str).isin(sel_ped_compra)]

        if 'qtde' in df_comp_filt.columns:
            df_comp_filt['qtde'] = pd.to_numeric(df_comp_filt['qtde'], errors='coerce').fillna(0)

        # Timeline ou Tabela Simples
        st.subheader("Itens de Compra")
        
        # Tabela com coloração condicional se houver data de entrega
        st.dataframe(
            df_comp_filt,
            use_container_width=True,
            hide_index=True
        )

        # Se houver data, mostrar timeline
        if 'dt_ent_orig' in df_comp_filt.columns:
            df_comp_filt['dt_ent_orig'] = pd.to_datetime(df_comp_filt['dt_ent_orig'], errors='coerce')
            df_valid_dates = df_comp_filt.dropna(subset=['dt_ent_orig'])
            
            if not df_valid_dates.empty:
                st.subheader("Cronograma de Entregas")
                fig_timeline = px.scatter(
                    df_valid_dates, 
                    x='dt_ent_orig', 
                    y='descricao', 
                    size='qtde', 
                    color='numero',
                    title="Previsão de Entregas",
                    hover_data=['numero', 'qtde']
                )
                st.plotly_chart(fig_timeline, use_container_width=True)

# Rodapé
st.divider()
col_foot1, col_foot2 = st.columns([3, 1])
with col_foot1:
    dates = []
    if df_consumos is not None and not df_consumos.empty and 'data_atualizacao' in df_consumos.columns:
        d = pd.to_datetime(df_consumos['data_atualizacao']).max()
        if pd.notnull(d): dates.append(f"Consumo: {d.strftime('%d/%m %H:%M')}")
    
    if df_estoque is not None and not df_estoque.empty and 'data_atualizacao' in df_estoque.columns:
        d = pd.to_datetime(df_estoque['data_atualizacao']).max()
        if pd.notnull(d): dates.append(f"Estoque: {d.strftime('%d/%m %H:%M')}")
    
    if df_compras is not None and not df_compras.empty and 'data_atualizacao' in df_compras.columns:
        d = pd.to_datetime(df_compras['data_atualizacao']).max()
        if pd.notnull(d): dates.append(f"Compras: {d.strftime('%d/%m %H:%M')}")

    if dates:
        st.caption("📅 Módulo de Dados: " + " | ".join(dates))
    else:
        st.caption(f"Visualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

with col_foot2:
    st.caption("v1.2 - Revisado")
