@st.cache_data(ttl=600)
def carregar_dados():
    try:
        # A MUDANÇA ESTÁ AQUI!
        # Em vez de tentar converter o segredo, nós o usamos DIRETAMENTE.
        creds_dict = st.secrets["gcp_service_account"]
        
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope )
        client = gspread.authorize(creds)

        # Abre a planilha pelo nome (que também está nos segredos)
        spreadsheet = client.open(st.secrets["sheet_name"])
        
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
        st.error("Verifique se a chave da conta de serviço está correta nos segredos do Streamlit e se o email da conta de serviço foi compartilhado como 'Leitor' na sua planilha.")
        return pd.DataFrame()
