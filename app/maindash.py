import streamlit as st
import os
import sys
import requests
from importlib.util import spec_from_file_location, module_from_spec
from datetime import datetime, timedelta, timezone
import jwt

try:
    import extra_streamlit_components as stx
except Exception:
    stx = None  # será verificado em runtime

API_BASE = os.getenv("API_BASE", "http://192.168.1.205:8001/api")  # definido no docker-compose
API_TIMEOUT = float(os.getenv("API_TIMEOUT_SECONDS", "5"))

st.set_page_config(page_title="Principal", layout="wide")


def _api_request(method: str, path: str, **kwargs):
    """Faz chamada HTTP para o backend com timeout padrão e captura erros de rede."""
    url = f"{API_BASE}{path}" if path.startswith("/") else f"{API_BASE}/{path}"
    timeout = kwargs.pop("timeout", API_TIMEOUT)
    try:
        return requests.request(method, url, timeout=timeout, **kwargs), None
    except requests.exceptions.RequestException as e:
        return None, str(e)


def maybe_rerun():
    """Compatibility wrapper for streamlit rerun across versions.

    Newer/older streamlit versions may not expose `experimental_rerun`.
    If available, call it; otherwise call `st.stop()` which halts execution and
    the user can refresh the page.
    """
    if hasattr(st, 'rerun'):
        try:
            st.rerun()
        except Exception:
            st.stop()
    elif hasattr(st, 'experimental_rerun'):
        try:
            st.experimental_rerun()
        except Exception:
            st.stop()
    else:
        # fallback: stop execution and suggest a manual refresh
        st.stop()


def _reset_user_scoped_state():
    """Remove chaves de estado específicas de telas/usuário para evitar vazamento
    entre logins diferentes na mesma sessão do navegador.
    """
    try:
        prefixes = (
            'inicio_plan_', 'fim_plan_', 'pedidos_plan_', 'salvar_plan_',
            'selected_rows_plan_', 'excluir_pedidos_plan_', 'consumo_perc_extra_plan_',
            'inicio_', 'fim_', 'pedidos_', 'salvar_', 'selected_rows_', 'excluir_pedidos_', 'consumo_perc_extra_',
        )
        to_delete = []
        for k in list(st.session_state.keys()):
            # Não apagar credenciais e controle
            if k in ('token', 'refresh', 'username', '_last_user'):
                continue
            if any(k.startswith(p) for p in prefixes) or k in (
                'planos', 'plano_ativo_idx', 'msg_salvar_planos', 'msg_excluir_plano', 'selected_tab'
            ):
                to_delete.append(k)
        for k in to_delete:
            try:
                del st.session_state[k]
            except Exception:
                pass
    except Exception:
        pass

def _cookie_manager():
    """Inicializa e retorna o CookieManager (se disponível)."""
    if stx is None:
        return None
    if 'cookie_manager' not in st.session_state:
        st.session_state.cookie_manager = stx.CookieManager()
    return st.session_state.cookie_manager


def _jwt_expiry_utc(token: str):
    """Extrai exp do JWT sem verificar assinatura; retorna datetime em UTC.
    Caso falhe, retorna agora + 7 dias.
    """
    try:
        payload = jwt.decode(token, options={
            "verify_signature": False,
            "verify_exp": False,
            "verify_aud": False,
        })
        exp = payload.get('exp')
        if exp:
            return datetime.fromtimestamp(int(exp), tz=timezone.utc)
    except Exception:
        pass
    return datetime.now(timezone.utc) + timedelta(days=7)


# Bootstrap: tenta repovoar a sessão a partir de cookies do navegador
cm = _cookie_manager()
try:
    if cm and (not st.session_state.get('refresh') or not st.session_state.get('username')):
        cookies = cm.get_all(key="boot_cookies")
        if cookies:
            ref = cookies.get('refresh')
            usr = cookies.get('username')
            if ref:
                st.session_state.refresh = ref
            if usr:
                st.session_state.username = usr
except Exception:
    pass

# Se houver refresh e ainda não houver access token, tenta obter um novo access
try:
    if st.session_state.get('refresh') and not st.session_state.get('token') and not st.session_state.get('_refresh_in_progress'):
        st.session_state['_refresh_in_progress'] = True
        r = requests.post(f"{API_BASE}/token/refresh/", json={"refresh": st.session_state.get('refresh')}, timeout=5)
        if r.status_code == 200:
            new_access = r.json().get('access')
            if new_access:
                st.session_state.token = new_access
        else:
            # refresh inválido → limpa estado
            try:
                cm = _cookie_manager()
                if cm:
                    cm.delete('refresh', key='cookie_refresh_del_boot')
                    cm.delete('username', key='cookie_username_del_boot')
            except Exception:
                pass
            st.session_state.clear()
except Exception:
    pass

# ============================================================
# Autenticação
# ============================================================

if "token" not in st.session_state:
    # Defensiva: Se o gerenciador de cookies ainda estiver carregando (retorna None),
    # aguardamos o próximo ciclo (rerun automático do componente) antes de mostrar login.
    if cm:
        if cm.get_all(key="check_cookies") is None:
            st.stop()

    # Layout centralizado para login
    _, col_login, _ = st.columns([1, 1.8, 1])
    
    with col_login:
        st.markdown("<h2 style='text-align: center;'>Acesso ao Sistema</h2>", unsafe_allow_html=True)
        tab_login, tab_register = st.tabs(["Entrar", "Cadastrar"])

        with tab_login:
            username = st.text_input("Usuário", key="login_username")
            senha = st.text_input("Senha", type="password", key="login_password")

            if st.button("Entrar", use_container_width=True):
                try:
                    resp = requests.post(f"{API_BASE}/token/", json={"username": username, "password": senha}, timeout=5)
                except requests.exceptions.ConnectionError:
                    st.error(f"Não foi possível conectar ao backend em {API_BASE}. Verifique se o serviço está rodando.")
                    st.stop()
                except Exception as e:
                    st.error(f"Erro ao conectar: {e}")
                    st.stop()

                if resp.status_code == 200:
                    body = resp.json()
                    st.session_state.token = body.get("access")
                    if body.get("refresh"):
                            st.session_state.refresh = body.get("refresh")
                            try:
                                cm = _cookie_manager()
                                if cm:
                                    exp = _jwt_expiry_utc(st.session_state.refresh)
                                    cm.set('refresh', st.session_state.refresh, expires_at=exp, key='cookie_refresh_set')
                                    cm.set('username', username, expires_at=exp, key='cookie_username_set')
                            except Exception:
                                pass
                    if st.session_state.get('_last_user') and st.session_state['_last_user'] != username:
                        _reset_user_scoped_state()
                    st.session_state.username = username
                    st.session_state['_last_user'] = username
                    maybe_rerun()
                else:
                    st.error("Usuário ou senha inválidos.")

        with tab_register:
            st.subheader("Criar nova conta")
            new_username = st.text_input("Usuário (novo)", key="reg_username")
            new_email = st.text_input("Email (opcional)", key="reg_email")
            new_password = st.text_input("Senha (nova)", type="password", key="reg_password")

            if st.button("Cadastrar", use_container_width=True):
                try:
                    resp = requests.post(f"{API_BASE}/register/", json={"username": new_username, "password": new_password, "email": new_email}, timeout=5)
                except requests.exceptions.ConnectionError:
                    st.error(f"Não foi possível conectar ao backend em {API_BASE}. Verifique se o serviço está rodando.")
                    st.stop()
                except Exception as e:
                    st.error(f"Erro ao conectar: {e}")
                    st.stop()

                if resp.status_code == 201:
                    st.success("Conta criada com sucesso. Faça login na aba ao lado.")
                else:
                    try:
                        err = resp.json()
                        st.error(f"Erro ao cadastrar: {err}")
                    except Exception:
                        st.error("Erro ao cadastrar usuário.")
    st.stop()
else:
    # Verifica se o token ainda é válido
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    resp, req_err = _api_request("GET", "/me/", headers=headers)
    if req_err:
        st.error(f"Não foi possível conectar ao backend em {API_BASE}.")
        st.caption(f"Detalhe: {req_err}")
        st.stop()

    if resp.status_code != 200:
        # try refresh token if available
        refresh_token = st.session_state.get('refresh')
        if refresh_token:
            try:
                # lightweight log for container stdout: attempt refresh (no token printed)
                print('[maindash] tentando refresh de token...')
                r, refresh_err = _api_request("POST", "/token/refresh/", json={"refresh": refresh_token})
                if refresh_err:
                    st.warning(f"Backend indisponível para renovar sessão: {refresh_err}")
                    st.stop()
                print(f"[maindash] token/refresh returned status: {r.status_code}")
                if r.status_code == 200:
                    new_access = r.json().get('access')
                    if new_access:
                        st.session_state.token = new_access
                        # re-check /me/ with new token
                        headers = {"Authorization": f"Bearer {st.session_state.token}"}
                        resp, req_err = _api_request("GET", "/me/", headers=headers)
                        if req_err:
                            st.warning(f"Backend indisponível após refresh: {req_err}")
                            st.stop()
                else:
                    # refresh failed - clear session
                    st.warning("Sessão expirada. Faça login novamente.")
                    st.session_state.clear()
                    st.experimental_rerun()
            except Exception as e:
                # print error for container logs (do not print tokens)
                print(f"[maindash] erro ao tentar refresh: {e}")
                st.warning("Erro ao renovar sessão. Faça login novamente.")
                st.session_state.clear()
                st.experimental_rerun()
        else:
            st.warning("Sessão expirada. Faça login novamente.")
            st.session_state.clear()
            st.experimental_rerun()

    if resp is None or resp.status_code != 200:
        st.warning("Não foi possível validar a sessão no backend. Faça login novamente.")
        st.session_state.clear()
        maybe_rerun()
        st.stop()

    # ============================================================
    # Menu
    # ============================================================
    st.sidebar.title("Menu de Seleção")
    abas = ["Boxer","Boxer_V2", "Meias"]

    # Se for admin, adiciona aba de logs
    user_data = resp.json()
    # detectar troca de usuário e limpar estado de UI
    try:
        current_user = user_data.get('username') or st.session_state.get('username')
        if current_user:
            if st.session_state.get('_last_user') and st.session_state['_last_user'] != current_user:
                _reset_user_scoped_state()
            st.session_state['_last_user'] = current_user
    except Exception:
        pass
    if user_data.get("is_staff"):
        abas.insert(0, "Logs do Sistema")
        # admin approvals
        abas.insert(1, "Aprovações")

    # Gestão de abas via Query Params (URL)
    # Suporte Híbrido: st.query_params (novo) vs experimental (velho)
    saved_tab = None
    try:
        if hasattr(st, 'query_params'):
            # Streamlit moderno: st.query_params é um objeto dict-like
            saved_tab = st.query_params.get('tab')
        elif hasattr(st, 'experimental_get_query_params'):
            # Fallback legado
            params = st.experimental_get_query_params()
            saved_tab = params.get('tab')[0] if params.get('tab') else None
    except Exception:
        pass

    default_index = 0
    if saved_tab in abas:
        default_index = abas.index(saved_tab)

    aba = st.sidebar.radio("Selecione a opção:", abas, index=default_index, key='selected_tab')

    # Atualiza a URL quando a seleção muda
    try:
        if hasattr(st, 'query_params'):
             st.query_params['tab'] = aba
        elif hasattr(st, 'experimental_set_query_params'):
             st.experimental_set_query_params(tab=aba)
    except Exception:
        pass

    if st.sidebar.button("Sair do sistema"):
        # remove cookies
        try:
            cm = _cookie_manager()
            if cm:
                cm.delete('refresh', key='cookie_refresh_del')
                cm.delete('username', key='cookie_username_del')
                cm.delete('tab', key='cookie_tab_del')
        except Exception:
            pass
        # limpar toda a sessão (evita resquícios do usuário anterior)
        try:
            st.session_state.clear()
        except Exception:
            for k in list(st.session_state.keys()):
                try:
                    del st.session_state[k]
                except Exception:
                    pass
        st.success("Logout realizado!")
        maybe_rerun()


    # ============================================================
    # Abas
    # ============================================================
    if aba == "Boxer":
        st.header("Boxer")
        dashboard_path = os.path.join(os.path.dirname(__file__), "Boxer", "dashboard.py")
        spec = spec_from_file_location("dashboard_boxer", dashboard_path)
        dashboard = module_from_spec(spec)
        sys.modules["dashboard_boxer"] = dashboard
        spec.loader.exec_module(dashboard)

    elif aba == "Meias":
        st.header("Meias")
        dashboard_meia_path = os.path.join(os.path.dirname(__file__), "Meia", "dashboard_streamlit.py")
        spec = spec_from_file_location("dashboard_meias", dashboard_meia_path)
        dashboard_meia = module_from_spec(spec)
        sys.modules["dashboard_meias"] = dashboard_meia
        spec.loader.exec_module(dashboard_meia)
        
    elif aba == "Boxer_V2":
        st.header("Boxer V2")
        dashboard_v2_path = os.path.join(os.path.dirname(__file__), "BoxerV2", "dashboard.py")
        spec = spec_from_file_location("dashboard_boxerv2", dashboard_v2_path)
        dashboard_v2 = module_from_spec(spec)
        sys.modules["dashboard_boxerv2"] = dashboard_v2
        spec.loader.exec_module(dashboard_v2)

    # Upload / Salvar dados removed: frontend artifact upload was deprecated

    elif aba == "Logs do Sistema":
        st.header("Logs do Sistema")
        resp_logs, req_err = _api_request("GET", "/logs/", headers=headers)
        if req_err:
            st.error(f"Falha ao conectar ao backend: {req_err}")
        elif resp_logs.status_code == 200:
            logs = resp_logs.json()
            # map action keys to human-friendly Portuguese labels
            action_map = {
                'login_success': 'login (sucesso)',
                'login_failed': 'login (falhou)',
                'login_pending': 'login (pendente)',
                'register_pending': 'cadastro (pendente)',
                'register_approved': 'cadastro (aprovado)',
                'register_rejected': 'cadastro (rejeitado)',
                'artifact_saved': 'artifact salvo',
            }
            for log in logs:
                action_key = log.get('action') or log.get('acao') or ''
                action_label = action_map.get(action_key, action_key)
                ts = log.get('timestamp')
                st.write(f"[{ts}] {log.get('username','-')} → {action_label}")
        else:
            st.error("Erro ao carregar logs.")

    elif aba == "Aprovações":
        st.header("Aprovar Usuários")
        resp_pending, req_err = _api_request("GET", "/register/pending/", headers=headers)
        if req_err:
            st.error(f"Falha ao conectar ao backend: {req_err}")
        elif resp_pending.status_code == 200:
            pendentes = resp_pending.json()
            if not pendentes:
                st.info("Nenhum usuário pendente.")
            for u in pendentes:
                with st.expander(f"{u['username']} (id: {u['id']})"):
                    st.write(f"Email: {u.get('email','-')}")
                    col1, col2 = st.columns(2)
                    if col1.button("Aprovar", key=f"ap_{u['id']}"):
                        r, action_err = _api_request("POST", f"/register/approve/{u['id']}/", headers=headers)
                        if action_err:
                            st.error(f"Falha ao aprovar: {action_err}")
                        elif r.status_code == 200:
                            st.success("Usuário aprovado")
                            st.experimental_rerun()
                        else:
                            st.error("Erro ao aprovar")
                    if col2.button("Rejeitar", key=f"rj_{u['id']}"):
                        r, action_err = _api_request("POST", f"/register/reject/{u['id']}/", headers=headers)
                        if action_err:
                            st.error(f"Falha ao rejeitar: {action_err}")
                        elif r.status_code == 200:
                            st.success("Usuário rejeitado")
                            st.experimental_rerun()
                        else:
                            st.error("Erro ao rejeitar")
        else:
            st.error("Erro ao buscar usuários pendentes")
