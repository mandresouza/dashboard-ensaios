# ===============================================================
# ARQUIVO data_processor.py (VERSÃO FINAL E À PROVA DE FALHAS)
# ===============================================================
import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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

@st.cache_data(ttl=600)
def carregar_dados():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope )
        client = gspread.authorize(creds)

        spreadsheet = client.open(st.secrets["sheet_name"])
        
        # Bloco de verificação de abas
        try:
            worksheet10 = spreadsheet.worksheet("BANC_10_POS")
        except gspread.exceptions.WorksheetNotFound:
            st.error("ERRO CRÍTICO: A aba 'BANC_10_POS' não foi encontrada na sua planilha. Verifique o nome exato.")
            return pd.DataFrame()

        try:
            worksheet20 = spreadsheet.worksheet("BANC_20_POS")
        except gspread.exceptions.WorksheetNotFound:
            st.error("ERRO CRÍTICO: A aba 'BANC_20_POS' não foi encontrada na sua planilha. Verifique o nome exato.")
            return pd.DataFrame()

        df_banc10 = pd.DataFrame(worksheet10.get_all_records())
        df_banc10['Bancada'] = 'BANC_10_POS'

        df_banc20 = pd.DataFrame(worksheet20.get_all_records())
        df_banc20['Bancada'] = 'BANC_20_POS'
        
        df_completo = pd.concat([df_banc10, df_banc20], ignore_index=True)
        
        if 'Data' not in df_completo.columns:
            st.error("ERRO CRÍTICO: A coluna 'Data' não foi encontrada na sua planilha. Verifique os cabeçalhos.")
            return pd.DataFrame()

        df_completo['Data_dt'] = pd.to_datetime(df_completo['Data'], errors='coerce', dayfirst=True)
        df_completo = df_completo.dropna(subset=['Data_dt'])
        df_completo['Data'] = df_completo['Data_dt'].dt.strftime('%d/%m/%y')
        return df_completo
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("ERRO CRÍTICO: Planilha não encontrada.")
        st.error(f"Verifique se o nome '{st.secrets['sheet_name']}' está correto e se o e-mail '{creds.service_account_email}' tem permissão de 'Leitor'.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao carregar os dados: {e}")
        return pd.DataFrame()

# O resto do arquivo (processar_ensaio, get_stats_por_dia) continua igual
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
