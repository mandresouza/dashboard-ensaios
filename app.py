# ===============================================================
# ARQUIVO app.py (VERSÃO FINAL - FORÇA BRUTA)
# ===============================================================
import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
import traceback

# --- CONFIGURAÇÕES GLOBAIS ---
st.set_page_config(page_title="Dashboard de Ensaios", page_icon="📊", layout="wide")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
LIMITES_CLASSE = {"A": 1.0, "B": 1.3, "C": 2.0, "D": 0.3}

# --- FUNÇÕES DE AUTENTICAÇÃO (LÓGICA SIMPLES E DIRETA ) ---
def create_flow():
    """Cria o fluxo de autenticação com a URL de redirecionamento FORÇADA."""
    client_config = st.secrets["gcreds_oauth"].to_dict()
    
    # FORÇA BRUTA: A URL do seu app é colocada diretamente aqui.
    # SUBSTITUA PELA SUA URL REAL.
    redirect_uri = "https://accounts.google.com/signin/oauth/error?authError=Cg9pbnZhbGlkX3JlcXVlc3QS3gEKWW91IGNhbid0IHNpZ24gaW4gdG8gdGhpcyBhcHAgYmVjYXVzZSBpdCBkb2Vzbid0IGNvbXBseSB3aXRoIEdvb2dsZSdzIE9BdXRoIDIuMCBwb2xpY3kgZm9yIGtlZXBpbmcgYXBwcyBzZWN1cmUuCgpZb3UgY2FuIGxldCB0aGUgYXBwIGRldmVsb3BlciBrbm93IHRoYXQgdGhpcyBhcHAgZG9lc24ndCBjb21wbHkgd2l0aCBvbmUgb3IgbW9yZSBHb29nbGUgdmFsaWRhdGlvbiBydWxlcy4KICAaWWh0dHBzOi8vZGV2ZWxvcGVycy5nb29nbGUuY29tL2lkZW50aXR5L3Byb3RvY29scy9vYXV0aDIvcG9saWNpZXMjc2VjdXJlLXJlc3BvbnNlLWhhbmRsaW5nIJADKhgKDHJlZGlyZWN0X3VyaRIIaHR0cHM6Ly8%3D&client_id=806874912622-o07mio7iejdt8l2hvdofg0i47ndabm6v.apps.googleusercontent.com&flowName=GeneralOAuthFlow"
    
    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
     )
    return flow

def get_creds_from_session():
    if 'creds_info' in st.session_state:
        return Credentials.from_authorized_user_info(st.session_state['creds_info'])
    return None

# --- FUNÇÕES DE PROCESSAMENTO E RENDERIZAÇÃO (SEM ALTERAÇÕES) ---
# (O restante do código de processamento e renderização que já tínhamos)
# ... (vou omitir por brevidade, mas você deve colar o código completo da versão anterior) ...
# ... (Cole aqui todas as funções de 'valor_num' até 'pagina_visao_mensal') ...

# --- LÓGICA PRINCIPAL DE EXECUÇÃO ---
def main():
    st.title("📊 Dashboard de Ensaios")

    creds = get_creds_from_session()
    query_params = st.query_params

    # Se o Google redirecionou de volta com um código, processa-o
    if not creds and "code" in query_params:
        try:
            with st.spinner("Autenticando com o Google..."):
                flow = create_flow()
                flow.fetch_token(code=query_params['code'][0]) # Pega o primeiro código
                
                # Salva as informações das credenciais na sessão
                st.session_state['creds_info'] = {
                    'token': flow.credentials.token,
                    'refresh_token': flow.credentials.refresh_token,
                    'token_uri': flow.credentials.token_uri,
                    'client_id': flow.credentials.client_id,
                    'client_secret': flow.credentials.client_secret,
                    'scopes': flow.credentials.scopes
                }
                # Limpa os parâmetros da URL e re-executa o script
                st.query_params.clear()
                st.rerun()
        except Exception as e:
            st.error("Ocorreu um erro ao tentar obter as credenciais.")
            st.code(traceback.format_exc())
            return

    # Se ainda não estiver autenticado, mostra o botão de login
    if not creds:
        st.warning("Para acessar os dados, você precisa autorizar a aplicação a ler suas planilhas do Google.")
        try:
            flow = create_flow()
            auth_url, _ = flow.authorization_url(prompt='consent')
            st.link_button("Fazer Login com o Google e Autorizar", auth_url, use_container_width=True)
        except Exception as e:
            st.error("Erro ao gerar URL de autorização. Verifique os 'Secrets' e a configuração no Google Cloud.")
            st.code(traceback.format_exc())
        return

    # Se estiver autenticado, carrega e mostra o dashboard
    try:
        # ... (O restante da lógica do dashboard que já tínhamos) ...
        st.success("Autenticado com sucesso! Carregando dados...")
        # ... (Chamar carregar_dados() e as funções de página) ...

    except Exception as e:
        st.error("Ocorreu um erro ao carregar os dados após a autenticação.")
        st.code(traceback.format_exc())

if __name__ == "__main__":
    # Cole aqui o código completo da versão "Código Oficial"
    # desde a definição de 'valor_num' até o final de 'main()'
    # para garantir que todas as funções estejam presentes.
    st.error("ERRO DE CONFIGURAÇÃO: O código completo não foi colado. Por favor, substitua este arquivo pelo código completo da versão 'Força Bruta'.")

