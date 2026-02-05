# ===============================================================
# ARQUIVO app.py (VERSÃO DIAGNÓSTICO - "CAIXA-PRETA")
# ===============================================================
import streamlit as st
from google_auth_oauthlib.flow import Flow
import traceback

st.set_page_config(page_title="Diagnóstico de Autenticação", layout="wide")

st.title("🕵️‍♂️ Ferramenta de Diagnóstico OAuth 2.0")
st.subheader("Plano C - Operação 'Caixa-Preta'")
st.info("Esta ferramenta irá expor os dados exatos que estão sendo enviados ao Google para encontrarmos a falha.")

try:
    # --- PASSO 1: LER OS SEGREDOS ---
    st.markdown("---")
    st.header("PASSO 1: Verificando os Segredos (Secrets)")
    with st.expander("Clique para ver os segredos carregados"):
        client_id = st.secrets.get("gcreds_oauth", {}).get("web", {}).get("client_id")
        client_secret = st.secrets.get("gcreds_oauth", {}).get("web", {}).get("client_secret")
        
        if client_id and client_secret:
            st.success("Segredos 'gcreds_oauth' (client_id e client_secret) encontrados!")
            st.text_input("Client ID Carregado", value=client_id, disabled=True)
            st.text_input("Client Secret Carregado", value="************" + client_secret[-4:], disabled=True)
        else:
            st.error("ERRO CRÍTICO: Não foi possível encontrar 'client_id' e 'client_secret' nos seus segredos. Verifique o formato em 'Manage App'.")
            st.stop()

    # --- PASSO 2: CONSTRUIR A REDIRECT_URI ---
    st.markdown("---")
    st.header("PASSO 2: Construindo a URL de Redirecionamento")
    
    # Lógica robusta para obter a URL base do Streamlit
    try:
        from streamlit.web.server.server import Server
        session_info = Server.get_current().get_session_info(st.runtime.get_script_run_ctx().session_id)
        if session_info:
             # A URL base que o Streamlit está realmente usando
            server_address = session_info.server_address
            server_port = session_info.server_port
            # Em produção, a URL completa é o que importa
            host = session_info.client.host
            redirect_uri = f"https://{host}"
            st.success("URL de Redirecionamento construída com sucesso!" )
            st.text_input("URL de Redirecionamento (redirect_uri)", value=redirect_uri, disabled=True)
            st.info("Esta é a URL que DEVE estar listada em 'URIs de redirecionamento autorizados' no Google Cloud.")
        else:
            st.error("Não foi possível obter as informações da sessão do Streamlit.")
            st.stop()
    except Exception as e:
        st.error(f"Erro ao tentar obter a URL do servidor Streamlit: {e}")
        st.warning("Usando um método alternativo (pode não ser 100% preciso).")
        redirect_uri = "https://SUA-URL-COMPLETA-AQUI.streamlit.app/" # Fallback
        st.text_input("URL de Redirecionamento (Fallback )", value=redirect_uri, disabled=True)


    # --- PASSO 3: GERAR A URL DE AUTORIZAÇÃO ---
    st.markdown("---")
    st.header("PASSO 3: Gerando a URL de Autorização Final")

    client_config = st.secrets["gcreds_oauth"].to_dict()
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
     )

    auth_url, _ = flow.authorization_url(prompt='consent')

    st.success("URL de Autorização gerada!")
    st.info("Esta é a URL para a qual você será enviado. Clique no botão abaixo para testar.")
    st.text_area("URL de Autorização Completa", value=auth_url, height=200, disabled=True)

    st.markdown("---")
    st.header("PASSO 4: A Execução do Teste")
    st.warning("Antes de clicar, verifique se a 'URL de Redirecionamento' do PASSO 2 está EXATAMENTE igual à que você configurou no Google Cloud.")
    
    if st.button("Iniciar Teste de Autorização", use_container_width=True, type="primary"):
        webbrowser.open_new_tab(auth_url)
        st.balloons()
        st.info("Uma nova aba foi aberta para autorização. Siga os passos lá.")

except Exception as e:
    st.error("Ocorreu um erro fatal durante a fase de diagnóstico.")
    st.code(traceback.format_exc())

