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

# Abas laterais
aba = st.sidebar.radio("Selecione o dashboard:", ["Boxer", "Meias"])

if aba == "Boxer":
    st.header("Dashboard Boxer")
    # Executa o dashboard.py como módulo
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
