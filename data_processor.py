# ===============================================================
# ARQUIVO data_processor.py (VERSÃO PLANO C)
# ===============================================================
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import json

LIMITES_CLASSE = {"A": 1.0, "B": 1.3, "C": 2.0, "D": 0.3}

def valor_num(v):
    try:
        if pd.isna(v): return None
        return float(str(v).replace("%", "").replace(",", "."))
    except (ValueError, TypeError): return None

def texto(v):
    if pd.isna(v) or v is None: return "-"
    return str(v)

def authenticate():
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    if "gcreds_token" in st.secrets:
        creds_dict = st.secrets["gcreds_token"].to_dict( )
        creds = Credentials.from_authorized_user_info(creds_dict, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return gspread.authorize(creds)
    else:
        flow = InstalledAppFlow.from_client_secrets_info(st.secrets["gcreds_oauth"].to_dict(), SCOPES)
        auth_url, _ = flow.authorization_url(prompt='consent')
        
        st.warning("⚠️ Ação necessária: Autorize o acesso ao Google Drive")
        st.write("Por favor, acesse o link abaixo para autorizar a aplicação:")
        st.code(auth_url)
        
        auth_code = st.text_input("Cole o código de autorização que você recebeu aqui:")
        
        if st.button("Autorizar Aplicação"):
            if not auth_code:
                st.error("O código de autorização não pode estar vazio.")
                st.stop()
            
            try:
                with st.spinner("Verificando código e gerando token de acesso..."):
                    flow.fetch_token(code=auth_code)
                    creds = flow.credentials
                    creds_dict_to_save = {
                        'token': creds.token,
                        'refresh_token': creds.refresh_token,
                        'token_uri': creds.token_uri,
                        'client_id': creds.client_id,
                        'client_secret': creds.client_secret,
                        'scopes': creds.scopes
                    }
                    st.success("Autorização bem-sucedida! O token foi gerado.")
                    st.info("Copie o texto abaixo e cole nos segredos do seu app no Streamlit como uma nova seção [gcreds_token].")
                    st.code(json.dumps(creds_dict_to_save, indent=2))
                    st.warning("Depois de salvar o segredo, você precisará reiniciar ('Reboot') a aplicação.")
                    st.stop()
            except Exception as e:
                st.error(f"Ocorreu um erro ao buscar o token: {e}")
                st.stop()
        
        st.stop()

@st.cache_data(ttl=600)
def carregar_dados(_client):
    try:
        spreadsheet = _client.open(st.secrets["sheet_name"])
        
        worksheet10 = spreadsheet.worksheet("BANC_10_POS")
        df_banc10 = pd.DataFrame(worksheet10.get_all_records())
        df_banc10['Bancada'] = 'BANC_10_POS'

        worksheet20 = spreadsheet.worksheet("BANC_20_POS")
        df_banc20 = pd.DataFrame(worksheet20.get_all_records())
        df_banc20['Bancada'] = 'BANC_20_POS'
        
        df_completo = pd.concat([df_banc10, df_banc20], ignore_index=True)
        
        df_completo['Data_dt'] = pd.to_datetime(df_completo['Data'], errors='coerce', dayfirst=True)
        df_completo = df_completo.dropna(subset=['Data_dt'])
        df_completo['Data'] = df_completo['Data_dt'].dt.strftime('%d/%m/%y')
        return df_completo
    except Exception as e:
        st.error(f"Erro ao carregar dados do Google Sheets: {e}")
        return pd.DataFrame()

def processar_ensaio(row, classe_banc20=None):
    medidores = []
    bancada = row.get('Bancada'); tamanho_bancada = 20 if bancada == 'BANC_20_POS' else 10
    classe = str(row.get("Classe", "")).upper()
    if not classe and bancada == 'BANC_20_POS' and classe_banc20: classe = classe_banc20
    if not classe: classe = 'B'
    limite = 4.0 if "ELETROMEC" in classe else LIMITES_CLASSE.get(classe.replace("ELETROMEC", "").strip(), 1.3)
    for pos in range(1, tamanho_bancada + 1):
        serie, cn, cp, ci = texto(row.get(f"P{pos}_Série")), row.get(f"P{pos}_CN"), row.get(f"P{pos}_CP"), row.get(f"P{pos}_CI")
        if pd.isna(cn) and pd.isna(cp) and pd.isna(ci): status, detalhe = "NÃO ENTROU", ""
        else:
            cargas_positivas_acima = sum(1 for v in [cn, cp, ci] if valor_num(v) is not None and valor_num(v) > 0 and abs(valor_num(v)) > limite)
            reg_ini, reg_fim = valor_num(row.get(f"P{pos}_REG_Inicio")), valor_num(row.get(f"P{pos}_REG_Fim"))
            reg_incremento_maior = (reg_ini is not None and reg_fim is not None and (reg_fim - reg_ini) > 1)
            reg_ok = (reg_ini is not None and reg_fim is not None and (reg_fim - reg_ini) == 1)
            mv_reprovado = str(texto(row.get(f"P{pos}_MV"))).upper() in ["REPROVADO", "NOK", "FAIL", "-"]
            pontos_contra = sum([cargas_positivas_acima >= 1, mv_reprovado, reg_incremento_maior])
            if pontos_contra >= 2: status, detalhe = "CONTRA O CONSUMIDOR", "<b>⚠️ Medição a mais</b>"
            else:
                aprovado = all(valor_num(v) is None or abs(valor_num(v)) <= limite for v in [cn, cp, ci]) and reg_ok and not mv_reprovado
                if aprovado: status, detalhe = "APROVADO", ""
                else:
                    status = "REPROVADO"
                    normais = sum(1 for v in [cn, cp, ci] if valor_num(v) is not None and abs(valor_num(v)) <= limite)
                    reprovados = sum(1 for v in [cn, cp, ci] if valor_num(v) is not None and abs(valor_num(v)) > limite)
                    detalhe = "<b>⚠️ Verifique este medidor</b>" if normais >= 1 and reprovados >= 1 else ""
        medidores.append({"pos": pos, "serie": serie, "cn": texto(cn), "cp": texto(cp), "ci": texto(ci), "mv": texto(row.get(f"P{pos}_MV")), "reg_ini": texto(row.get(f"P{pos}_REG_Inicio")), "reg_fim": texto(row.get(f"P{pos}_REG_Fim")), "reg_err": texto(row.get(f"P{pos}_REG_Erro")), "status": status, "detalhe": detalhe, "limite": limite})
    return medidores

def get_stats_por_dia(df_mes):
    daily_stats = []
    for data, group in df_mes.groupby('Data_dt'):
        medidores = [];
        for _, row in group.iterrows(): medidores.extend(processar_ensaio(row, 'B'))
        aprovados = sum(1 for m in medidores if m['status'] == 'APROVADO')
        reprovados = sum(1 for m in medidores if m['status'] == 'REPROVADO')
        daily_stats.append({'Data': data, 'Aprovados': aprovados, 'Reprovados': reprovados})
    return pd.DataFrame(daily_stats)
