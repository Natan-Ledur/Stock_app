import streamlit as st
import os
import sys
from importlib.util import spec_from_file_location, module_from_spec
from pymongo import MongoClient
import hashlib
from dotenv import load_dotenv

import os
st.set_page_config(page_title="Dashboard Principal", layout="wide")
st.sidebar.title("Menu de Dashboards")

# Carrega variáveis do arquivo .env
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
# Conexão com MongoDB usando variáveis de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION")
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
usuarios = db[MONGO_COLLECTION]

# Função para hash de senha
def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

# Função para autenticação
def autenticar(username, senha):
    user = usuarios.find_one({"username": username, "aprovado": True})
    if user and user["senha"] == hash_senha(senha):
        return True
    return False

# Função para registrar novo usuário
def registrar_usuario(username, senha):
    if usuarios.find_one({"username": username}):
        return False
    usuarios.insert_one({"username": username, "senha": hash_senha(senha), "aprovado": False})
    return True

# Interface de login/cadastro
st.title("Login do Sistema")
if "logado" not in st.session_state:
    st.session_state["logado"] = False
if "usuario" not in st.session_state:
    st.session_state["usuario"] = ""

if not st.session_state["logado"]:
    aba_login = st.radio("Acesso:", ["Entrar", "Registrar"])
    username = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if aba_login == "Entrar":
        if st.button("Login"):
            if autenticar(username, senha):
                st.session_state["logado"] = True
                st.session_state["usuario"] = username
                st.success("Login realizado com sucesso!")
                st.rerun()
            else:
                user = usuarios.find_one({"username": username})
                if user and not user.get("aprovado", False):
                    st.warning("Usuário aguardando aprovação do administrador.")
                else:
                    st.error("Usuário ou senha incorretos!")
    else:
        if st.button("Registrar"):
            if registrar_usuario(username, senha):
                st.success("Cadastro realizado! Aguarde aprovação do administrador.")
            else:
                st.error("Usuário já existe!")
else:
    st.sidebar.title("Menu de Dashboards")
    aba = st.sidebar.radio("Selecione o dashboard:", ["Boxer", "Meias"])
    # Se usuário for admin, mostra painel de aprovação
    if st.session_state["usuario"] == "admin":
        st.subheader("Painel de Aprovação de Usuários")
        pendentes = list(usuarios.find({"aprovado": False}))
        if pendentes:
            for user in pendentes:
                col1, col2 = st.columns([3,1])
                with col1:
                    st.write(f"Usuário: {user['username']}")
                with col2:
                    if st.button(f"Aprovar {user['username']}"):
                        usuarios.update_one({"_id": user["_id"]}, {"$set": {"aprovado": True}})
                        st.success(f"Usuário {user['username']} aprovado!")
                        st.rerun()
                    if st.button(f"Rejeitar {user['username']}"):
                        usuarios.delete_one({"_id": user["_id"]})
                        st.info(f"Usuário {user['username']} rejeitado e removido!")
                        st.rerun()
        else:
            st.info("Nenhum usuário pendente de aprovação.")
    # Dashboards
    if aba == "Boxer":
        st.header("Dashboard Boxer")
        dashboard_path = os.path.join(os.path.dirname(__file__), "Boxer", "dashboard.py")
        spec = spec_from_file_location("dashboard", dashboard_path)
        dashboard = module_from_spec(spec)
        sys.modules["dashboard"] = dashboard
        spec.loader.exec_module(dashboard)
    elif aba == "Meias":
        st.header("Dashboard Meias")
        dashboard_meia_path = os.path.join(os.path.dirname(__file__), "Meia", "dashboard_streamlit.py")
        spec = spec_from_file_location("dashboard_streamlit", dashboard_meia_path)
        dashboard_meia = module_from_spec(spec)
        sys.modules["dashboard_streamlit"] = dashboard_meia
        spec.loader.exec_module(dashboard_meia)
