
# Dashboard usando Streamlit, lendo dados do cache

import streamlit as st
import pandas as pd
import os
import pickle
import subprocess  # Usado apenas para atualizar o cache
import plotly.figure_factory as ff
import datetime
import plotly.express as px
import io
import sys
# import json  # Usado apenas em bloco específico
# import boto3  # Usado apenas em bloco específico
# from botocore.exceptions import BotoCoreError, ClientError  # Usado apenas em bloco específico

# Função para carregar dados do main.py e salvar em cache persistente
import pickle
import os

def caminho_cache():
    return os.path.join(os.path.dirname(__file__), "main_cache.pkl")

st.set_page_config(page_title="Dashboard Fios Boxer", layout="wide")
st.title("Dashboard - Dados Boxer")

cache_path = caminho_cache()

def ler_cache():
	if os.path.exists(cache_path):
		with open(cache_path, "rb") as f:
			dados = pickle.load(f)
			# Se for dict, tenta pegar a chave 'df_final'
			if isinstance(dados, dict) and 'df_final' in dados:
				return dados['df_final']
			return dados
	else:
		st.warning("Cache não encontrado. Clique em atualizar para gerar os dados.")
		return pd.DataFrame()

def atualizar_cache():
        resultado = subprocess.run(["python", "Boxer/main.py"], capture_output=True, text=True)
        if resultado.returncode == 0:
            st.success("Cache atualizado com sucesso!")
        else:
            st.error(f"Erro ao atualizar cache: {resultado.stderr}")

    # Botão para atualizar os dados
df_final = ler_cache()

if st.button("Atualizar dados do cache"):
        atualizar_cache()

df_final = ler_cache()

aba1, aba2, aba3 = st.tabs(["Geral", "Planejamento", "Relatórios"])

with aba1:
    

    if isinstance(df_final, pd.DataFrame) and not df_final.empty:

        col1, col2, col4 = st.columns([2,2,2])
        # Filtro por descricao
        opcoes_descricao = df_final['descricao'].dropna().unique().tolist() if 'descricao' in df_final.columns else []
        descricao_selecionada = col1.selectbox("Filtrar por Material (descricao)", ["Todos"] + opcoes_descricao)

        # Filtro por descricao_cor
        opcoes_cor = df_final['descricao_cor'].dropna().unique().tolist() if 'descricao_cor' in df_final.columns else []
        cor_selecionada = col2.selectbox("Filtrar por Cor (descricao_cor)", ["Todos"] + opcoes_cor)

        # Filtro por pedidos (multiselect) dentro de expander
        colunas_pedidos = [col for col in df_final.columns if col.isdigit() or col.startswith('18_') or col.startswith('01_')]
        with st.expander("Exibir/ocultar colunas de pedidos", expanded=False):
            pedidos_selecionados = st.multiselect(
                "Selecione os pedidos que deseja visualizar:",
                colunas_pedidos,
                default=colunas_pedidos,
                help="Todos estão selecionados por padrão. Use para filtrar visualmente."
            )

        # Filtro por setor
        opcoes_setor = ["Todos", "Setor 01", "Setor 18", "Setor 19"]
        setor_selecionado = col4.selectbox("Filtrar por Setor", opcoes_setor)

        # Aplicar filtros
        df_filtrado = df_final.copy()
        if descricao_selecionada != "Todos" and 'descricao' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['descricao'] == descricao_selecionada]
        if cor_selecionada != "Todos" and 'descricao_cor' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['descricao_cor'] == cor_selecionada]

        # Filtrar colunas de pedidos
        colunas_base = ['descricao', 'descricao_cor', 'codigo_tabela_cor', 'estoque_total']
        colunas_exibir = colunas_base + pedidos_selecionados
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

        # Recalcular Consumo_Total_Pedidos e Estoque_Descontado
        pedidos_cols = [col for col in df_filtrado.columns if col not in colunas_base]
        df_filtrado['Consumo_Total_Pedidos'] = df_filtrado[pedidos_cols].sum(axis=1) if pedidos_cols else 0
        df_filtrado['Estoque_Descontado'] = df_filtrado['estoque_total'] - df_filtrado['Consumo_Total_Pedidos']

        # Ordenar do maior para o menor estoque
        df_filtrado = df_filtrado.sort_values(by='Consumo_Total_Pedidos', ascending=False)

        st.dataframe(df_filtrado, height=700) # Tamanho da tabela
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
            'Setor 19': [col for col in df_filtrado.columns if col.isdigit()]
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
            fig_disp = px.scatter(
                df_filtrado,
                x='estoque_total',
                y='Consumo_Total_Pedidos',
                color='descricao_cor' if 'descricao_cor' in df_filtrado.columns else None,
                hover_data=['descricao'] if 'descricao' in df_filtrado.columns else None,
                title="Estoque vs Consumo Total"
            )
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
                fig_disp_cor = px.scatter(
                    df_cor,
                    x='estoque_total',
                    y='Consumo_Total_Pedidos',
                    color='descricao',
                    hover_data=['descricao'],
                    title=f"Estoque vs Consumo Total - Cor: {cor_selecionada_graf}"
                )
                st.plotly_chart(fig_disp_cor, use_container_width=True)
            else:
                st.info("Não há dados para essa cor.")
    #==============================================================================================
        


    # Se não estiver dados!
    else:
        st.info("Nenhum dado disponível ou formato inválido. Atualize o cache para visualizar os dados.")


#====================================================ABA 2==========================================================
#===================================================================================================================

with aba2:
#================================Grafico Gantt============================================================

    st.markdown("### Planejamento dos Pedidos - Gráfico de Gantt (Setor 01 e 18)")

    # Seleciona colunas de pedidos dos setores 01 e 18
    pedidos_01 = [col for col in df_final.columns if col.startswith('01_')]
    pedidos_18 = [col for col in df_final.columns if col.startswith('18_')]
    pedidos_gantt = pedidos_01 + pedidos_18

    # Usuário escolhe os pedidos que vão aparecer no Gantt
    pedidos_selecionados = st.multiselect(
        "Selecione os pedidos para o planejamento:",
        pedidos_gantt,
        default=pedidos_gantt[:3] if len(pedidos_gantt) > 3 else pedidos_gantt
    )


    # Usuário define datas de início e fim para cada pedido
    df_gantt = []
    for pedido in pedidos_selecionados:
        col1, col2 = st.columns(2)
        with col1:
            data_inicio = st.date_input(f"Data de início para {pedido}", value=datetime.date.today(), key=f"inicio_{pedido}")
        with col2:
            data_fim = st.date_input(f"Data de fim para {pedido}", value=datetime.date.today() + datetime.timedelta(days=2), key=f"fim_{pedido}")
        df_gantt.append(dict(Task=pedido, Start=str(data_inicio), Finish=str(data_fim)))

    # Salva informações preenchidas pelo usuário
    import json
    def get_usuario_logado():
        # Recebe do maindash.py
        return getattr(sys.modules[__name__], 'usuario_logado', None)

    if st.button('Salvar planejamento do usuário'):
        usuario = get_usuario_logado() or 'anonimo'
        registro = {
            'usuario': usuario,
            'data': str(datetime.datetime.now()),
            'pedidos_selecionados': pedidos_selecionados,
            'df_gantt': df_gantt
        }
        # Salva em arquivo local
        pasta_logs = os.path.join(os.path.dirname(__file__), 'logs_usuarios')
        os.makedirs(pasta_logs, exist_ok=True)
        nome_arquivo = f"planejamento_{usuario}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        caminho_arquivo = os.path.join(pasta_logs, nome_arquivo)
        with open(caminho_arquivo, 'w', encoding='utf-8') as f:
            json.dump(registro, f, ensure_ascii=False, indent=2)
        st.success(f"Planejamento salvo para o usuário {usuario}!")

        # Upload automático para S3
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
        # Configurações do S3 (preencha conforme necessário)
        BUCKET_NAME = 'SEU_BUCKET_AQUI'  # Substitua pelo nome do seu bucket
        S3_FOLDER = 'planejamentos'      # Pasta dentro do bucket (opcional)
        S3_KEY = f"{S3_FOLDER}/{nome_arquivo}" if S3_FOLDER else nome_arquivo

        try:
            s3 = boto3.client('s3')
            s3.upload_file(caminho_arquivo, BUCKET_NAME, S3_KEY)
            st.success(f"Arquivo enviado para o S3: {BUCKET_NAME}/{S3_KEY}")
        except (BotoCoreError, ClientError) as e:
            st.error(f"Falha ao enviar para o S3: {e}")

    if df_gantt:
        # Lista de cores para o Gantt
        cores = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52']
        while len(cores) < len(df_gantt):
            cores += cores  # Repete as cores se necessário
        fig_gantt = ff.create_gantt(
            df_gantt,
            index_col='Task',
            show_colorbar=True,
            group_tasks=True,
            colors=cores[:len(df_gantt)],
            title="Execução dos Pedidos - Setor 01 e 18"
        )
        st.plotly_chart(fig_gantt, use_container_width=True)

        # Cálculo de consumo e estoque para os pedidos selecionados + pedidos pivot_19_18
        st.markdown("#### Consumo e Estoque dos pedidos planejados")
        colunas_base = ['descricao', 'descricao_cor', 'codigo_tabela_cor', 'estoque_total']
        # Pedidos fixos do pivot_19_18
        pedidos_fixos = [col for col in df_final.columns if col.isdigit() or col.startswith('19_') or col.startswith('18_')]
        # Junta pedidos fixos e selecionados, sem duplicar
        pedidos_tabela = list(dict.fromkeys(pedidos_fixos + pedidos_selecionados))

        df_filtrado_gantt = df_final.copy()
        colunas_exibir = colunas_base + pedidos_tabela
        colunas_exibir = [col for col in colunas_exibir if col in df_filtrado_gantt.columns]
        df_filtrado_gantt = df_filtrado_gantt[colunas_exibir]

        pedidos_cols = [col for col in df_filtrado_gantt.columns if col not in colunas_base]
        df_filtrado_gantt['Consumo_Total_Pedidos'] = df_filtrado_gantt[pedidos_cols].sum(axis=1) if pedidos_cols else 0
        df_filtrado_gantt['Estoque_Descontado'] = df_filtrado_gantt['estoque_total'] - df_filtrado_gantt['Consumo_Total_Pedidos']

        # Ordena pelo maior consumo primeiro
        df_filtrado_gantt = df_filtrado_gantt.sort_values(by='Consumo_Total_Pedidos', ascending=False)

        st.dataframe(df_filtrado_gantt, height=400)
        # Seleção de linhas para evolução do estoque
        st.markdown("#### Selecione os itens para visualizar a evolução do estoque")
        selected_rows = st.multiselect(
            "Selecione os materiais (linha) para evolução do estoque:",
            [f"{row['descricao']} | {row['descricao_cor']}" for _, row in df_filtrado_gantt.iterrows()] if 'descricao' in df_filtrado_gantt.columns and 'descricao_cor' in df_filtrado_gantt.columns else df_filtrado_gantt.index.astype(str),
            help="Selecione um ou mais materiais para visualizar a evolução do estoque ao longo do tempo. Cada opção mostra o material e a cor."
        )

        if selected_rows:
            # Prepara dados do Gantt
            datas_gantt = []
            pedidos_gantt = []
            for pedido in pedidos_selecionados:
                for entry in df_gantt:
                    if entry['Task'] == pedido:
                        data_inicio = datetime.datetime.strptime(entry['Start'], "%Y-%m-%d").date()
                        data_fim = datetime.datetime.strptime(entry['Finish'], "%Y-%m-%d").date()
                        datas_gantt.append((pedido, data_inicio, data_fim))
                        pedidos_gantt.append(pedido)
            # Gera lista de datas únicas ordenadas
            todas_datas = set()
            for _, ini, fim in datas_gantt:
                for d in range((fim-ini).days+1):
                    todas_datas.add(ini + datetime.timedelta(days=d))
            todas_datas = sorted(list(todas_datas))

            # Monta evolução do estoque para cada item selecionado
            evolucao = {}
            for item in selected_rows:
                # item é "descricao | descricao_cor"
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
                # Evolução do estoque: lista ordenada por data
                estoque_evol = []
                estoque_atual = estoque_inicial
                for dt in todas_datas:
                    # Para cada data, desconta o consumo dos pedidos ativos nesse dia
                    consumo_dia = 0
                    for pedido, ini, fim in datas_gantt:
                        if pedido in linha.columns and ini <= dt <= fim:
                            consumo_total = linha[pedido].values[0]
                            dias = (fim-ini).days+1
                            consumo_diario = consumo_total/dias if dias > 0 else consumo_total
                            consumo_dia += consumo_diario
                    estoque_atual -= consumo_dia
                    estoque_evol.append(estoque_atual)
                evolucao[nome_legenda] = estoque_evol

            # Plota gráfico de evolução
            import plotly.graph_objects as go
            fig_evol = go.Figure()
            for item, estoque_evol in evolucao.items():
                fig_evol.add_trace(go.Scatter(x=[dt.strftime('%d/%m/%Y') for dt in todas_datas], y=estoque_evol, mode='lines+markers', name=str(item)))
            fig_evol.update_layout(title="Evolução do Estoque dos Materiais Selecionados", xaxis_title="Data", yaxis_title="Estoque", legend_title="Material")
            st.plotly_chart(fig_evol, use_container_width=True)
    else:
        st.info("Selecione ao menos um pedido para visualizar o Gantt.")