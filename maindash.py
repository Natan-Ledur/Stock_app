import streamlit as st
import os
import sys
from importlib.util import spec_from_file_location, module_from_spec
# Adiciona autenticação
import streamlit_authenticator as stauth

st.set_page_config(page_title="Dashboard Principal", layout="wide")
st.sidebar.title("Menu de Dashboards")

# Abas laterais
aba = st.sidebar.radio("Selecione o dashboard:", ["Boxer", "Meias"])


# Configuração de usuários (hashes gerados previamente)
usernames = ['admin', 'usuario1', 'usuario2']
names = ['Administrador', 'Usuário 1', 'Usuário 2']
# Hashes gerados com stauth.Hasher(['senha123', 'senha1', 'senha2']).generate()
hashed_passwords = [
    '$2b$12$KIXQwQJQpQwQJQpQwQJQpOQJQpQwQJQpQwQJQpQwQJQpQwQJQpQwQ',  # exemplo
    '$2b$12$KIXQwQJQpQwQJQpQwQJQpOQJQpQwQJQpQwQJQpQwQJQpQwQJQpQwQ',  # exemplo
    '$2b$12$KIXQwQJQpQwQJQpQwQJQpOQJQpQwQJQpQwQJQpQwQJQpQwQJQpQwQ'   # exemplo
]

authenticator = stauth.Authenticate(
    names, usernames, hashed_passwords,
    'stock_app_dashboard', 'abcdef', cookie_expiry_days=1
)

name, authentication_status, username = authenticator.login('Login', 'sidebar')

if authentication_status:
    st.sidebar.success(f'Bem-vindo, {name}!')
    if aba == "Boxer":
        st.header("Dashboard Boxer")
        dashboard_path = "Boxer/dashboard.py"
        spec = spec_from_file_location("dashboard", dashboard_path)
        dashboard = module_from_spec(spec)
        sys.modules["dashboard"] = dashboard
        # Passa o nome do usuário para o dashboard
        dashboard.usuario_logado = username
        spec.loader.exec_module(dashboard)
    elif aba == "Meias":
        st.header("Dashboard Meias")
        dashboard_meia_path = "Meia/dashboard_streamlit.py"
        spec = spec_from_file_location("dashboard_streamlit", dashboard_meia_path)
        dashboard_meia = module_from_spec(spec)
        sys.modules["dashboard_streamlit"] = dashboard_meia
        dashboard_meia.usuario_logado = username
        spec.loader.exec_module(dashboard_meia)
elif authentication_status == False:
    st.error('Usuário ou senha incorretos')
elif authentication_status == None:
    st.warning('Por favor, faça login para acessar o dashboard.')
