import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
import requests
from io import BytesIO
import traceback

# [CONFIGURAÇÃO DA PÁGINA]
st.set_page_config(page_title="Dashboard INMETRO", page_icon="⚖️", layout="wide")

LIMITES_CLASSE = {"A": 1.0, "B": 1.3, "C": 2.0, "D": 0.3}

# [FUNÇÃO AUXILIAR: GERAR PDF]
def gerar_pdf_fiscalizacao(lista_medidores, data_str):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(190, 10, "RELATÓRIO DE FISCALIZAÇÃO - INMETRO", ln=True, align='C')
    pdf.set_font("helvetica", "", 12)
    pdf.cell(190, 10, f"Data do Ensaio: {data_str}", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(20, 10, "Pos", 1, 0, 'C', True)
    pdf.cell(40, 10, "Série", 1, 0, 'C', True)
    pdf.cell(50, 10, "Status", 1, 0, 'C', True)
    pdf.cell(80, 10, "Irregularidade", 1, 1, 'C', True)
    
    pdf.set_font("helvetica", "", 9)
    for m in lista_medidores:
        if m['status'] in ["REPROVADO", "CONTRA O CONSUMIDOR"]:
            pdf.cell(20, 10, str(m['pos']), 1, 0, 'C')
            pdf.cell(40, 10, m['serie'], 1, 0, 'C')
            pdf.cell(50, 10, m['status'], 1, 0, 'C')
            pdf.cell(80, 10, str(m.get('motivo', 'N/A')), 1, 1, 'L')
            
    return pdf.output()

# [BLOCO 02] - CARREGAMENTO DE DADOS (GOOGLE SHEETS)
@st.cache_data(ttl=600)
def carregar_dados():
    try:
        sheet_id = "1QxZ7bCSBClsmXLG1JOrFKNkMWZMK3P5Sp4LP81HV3Rs"
        url_b10 = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=BANC_10_POS"
        url_b20 = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=BANC_20_POS"
        
        df10 = pd.read_csv(url_b10 )
        df10['Bancada'] = 'BANC_10_POS'
        df20 = pd.read_csv(url_b20)
        df20['Bancada'] = 'BANC_20_POS'

        df = pd.concat([df10, df20], ignore_index=True)
        df['Data_dt'] = pd.to_datetime(df['Data'], errors='coerce', dayfirst=True)
        df = df.dropna(subset=['Data_dt'])
        df['Data'] = df['Data_dt'].dt.strftime('%d/%m/%y')
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()

# [BLOCO 03/04] - PROCESSAMENTO TÉCNICO
def valor_num(v):
    try:
        if pd.isna(v): return None
        return float(str(v).replace("%", "").replace(",", "."))
    except: return None

def texto(v):
    return str(v) if pd.notna(v) else "-"

def processar_ensaio(row, classe_banc20=None):
    medidores = []
    bancada = row.get('Bancada')
    tamanho = 20 if bancada == 'BANC_20_POS' else 10
    classe = str(row.get("Classe", "B")).upper()
    if bancada == 'BANC_20_POS' and classe_banc20: classe = classe_banc20
    
    limite = 4.0 if "ELETROMEC" in classe else LIMITES_CLASSE.get(classe.replace("ELETROMEC", "").strip(), 1.3)
    
    for pos in range(1, tamanho + 1):
        serie = texto(row.get(f"P{pos}_Série"))
        cn, cp, ci = row.get(f"P{pos}_CN"), row.get(f"P{pos}_CP"), row.get(f"P{pos}_CI")
        mv = texto(row.get(f"P{pos}_MV"))
        reg_i, reg_f = valor_num(row.get(f"P{pos}_REG_Inicio")), valor_num(row.get(f"P{pos}_REG_Fim"))
        
        status, motivo = "APROVADO", "Nenhum"
        if pd.isna(cn) and pd.isna(cp) and pd.isna(ci):
            status, motivo = "NÃO ENTROU", "N/A"
        else:
            v_cn, v_cp, v_ci = valor_num(cn), valor_num(cp), valor_num(ci)
            erro_exat = any(v is not None and abs(v) > limite for v in [v_cn, v_cp, v_ci])
            erro_reg = (reg_i is not None and reg_f is not None and (reg_f - reg_i) != 1)
            mv_nok = mv.upper() in ["REPROVADO", "NOK", "FAIL", "-"]
            
            if erro_exat or erro_reg or mv_nok:
                status = "REPROVADO"
                m_list = []
                if erro_exat: m_list.append("Exatidão")
                if erro_reg: m_list.append("Registrador")
                if mv_nok: m_list.append("Mostrador")
                motivo = " / ".join(m_list)
            
            # Lógica Contra Consumidor
            pontos = sum([sum(1 for v in [v_cn, v_cp, v_ci] if v is not None and v > 0 and abs(v) > limite) >= 1, mv_nok, (reg_i is not None and reg_f is not None and (reg_f - reg_i) > 1)])
            if pontos >= 2: status, motivo = "CONTRA O CONSUMIDOR", "Contra Consumidor"

        medidores.append({
            "pos": pos, "serie": serie, "cn": texto(cn), "cp": texto(cp), "ci": texto(ci), 
            "mv": mv, "reg_ini": texto(reg_i), "reg_fim": texto(reg_f),
            "status": status, "motivo": motivo, "limite": limite, "bancada": bancada
        })
    return medidores

# [BLOCO 05] - COMPONENTES VISUAIS
def renderizar_card(m):
    cores = {"APROVADO": "#dcfce7", "REPROVADO": "#fee2e2", "CONTRA O CONSUMIDOR": "#ede9fe", "NÃO ENTROU": "#e5e7eb"}
    cor = cores.get(m['status'], "#f3f4f6")
    st.markdown(f"""
        <div style="background:{cor}; border-radius:8px; padding:10px; border-left: 5px solid rgba(0,0,0,0.1); margin-bottom:10px;">
            <div style="font-weight:bold;">Posição {m['pos']} - {m['serie']}</div>
            <div style="font-size:12px;">Status: {m['status']}</div>
            <div style="font-size:11px; color:#666;">{m['motivo']}</div>
        </div>
    """, unsafe_allow_html=True)

def renderizar_resumo(stats):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", stats['total'])
    c2.metric("Aprovados", stats['aprovados'])
    c3.metric("Reprovados", stats['reprovados'])
    c4.metric("Contra Cons.", stats['consumidor'])

# [BLOCO 06] - VISÃO DIÁRIA
def pagina_visao_diaria(df):
    st.sidebar.header("🔍 Filtros Diários")
    if "s_key" not in st.session_state: st.session_state.s_key = 0
    busca = st.sidebar.text_input("Buscar Série", key=f"s_{st.session_state.s_key}").strip().lower()
    
    if busca:
        if st.sidebar.button("Limpar"):
            st.session_state.s_key += 1
            st.rerun()
        res = []
        for _, row in df.iterrows():
            meds = processar_ensaio(row)
            for m in meds:
                if busca in m['serie'].lower(): res.append({"d": row['Data'], "b": row['Bancada'], "m": m})
        if res:
            for r in res:
                with st.expander(f"{r['d']} | {r['b']} | {r['m']['serie']}"): renderizar_card(r['m'])
        else: st.warning("Não encontrado.")
    else:
        dt_sel = st.sidebar.date_input("Data", value=date.today(), format="DD/MM/YYYY")
        dt_str = dt_sel.strftime('%d/%m/%y')
        b_sel = st.sidebar.selectbox("Bancada", ['Todas'] + df['Bancada'].unique().tolist())
        
        df_f = df[df['Data'] == dt_str]
        if b_sel != 'Todas': df_f = df_f[df_f['Bancada'] == b_sel]
        
        if df_f.empty:
            st.info(f"Sem registros para {dt_str}")
            return
            
        all_m = []
        for _, row in df_f.iterrows(): all_m.extend(processar_ensaio(row))
        
        st.subheader(f"📅 Relatório: {dt_str}")
        s = {"total": len(all_m), "aprovados": sum(1 for x in all_m if x['status']=="APROVADO"), 
             "reprovados": sum(1 for x in all_m if x['status']=="REPROVADO"), "consumidor": sum(1 for x in all_m if x['status']=="CONTRA O CONSUMIDOR")}
        renderizar_resumo(s)
        
        if s['reprovados'] + s['consumidor'] > 0:
            pdf = gerar_pdf_fiscalizacao(all_m, dt_str)
            st.download_button("📄 Baixar PDF de Irregularidades", data=pdf, file_name=f"Fiscalizacao_{dt_str}.pdf", mime="application/pdf")
        
        cols = st.columns(5)
        for i, m in enumerate(all_m):
            with cols[i % 5]: renderizar_card(m)

# [BLOCO 07] - VISÃO MENSAL
def pagina_visao_mensal(df):
    st.sidebar.header("📅 Filtros Mensais")
    ano = st.sidebar.selectbox("Ano", sorted(df['Data_dt'].dt.year.unique(), reverse=True))
    mes = st.sidebar.selectbox("Mês", range(1, 13), format_func=lambda x: date(2024, x, 1).strftime('%B'))
    
    df_m = df[(df['Data_dt'].dt.year == ano) & (df['Data_dt'].dt.month == mes)]
    if df_m.empty:
        st.info("Sem dados.")
        return
        
    all_meds = []
    for _, row in df_m.iterrows(): all_meds.extend(processar_ensaio(row))
    
    ap = sum(1 for x in all_meds if x['status']=="APROVADO")
    tt = len(all_meds)
    tx = (ap/tt*100) if tt > 0 else 0
    
    st.header(f"Análise Mensal: {mes}/{ano}")
    c1, c2 = st.columns(2)
    c1.metric("Taxa de Aprovação", f"{tx:.1f}%", delta=f"{tx-95:.1f}% vs Meta")
    
    # Gráfico de Tendência
    df_d = []
    for d, g in df_m.groupby('Data'):
        m_d = []
        for _, r in g.iterrows(): m_d.extend(processar_ensaio(r))
        df_d.append({'Data': d, 'Aprovados': sum(1 for x in m_d if x['status']=="APROVADO")})
    
    st.plotly_chart(px.line(pd.DataFrame(df_d), x='Data', y='Aprovados', title="Evolução de Aprovações"), use_container_width=True)

# [MAIN]
def main():
    st.title("📊 Dashboard INMETRO")
    df = carregar_dados()
    if not df.empty:
        v = st.sidebar.radio("Navegação", ["Visão Diária", "Visão Mensal"])
        if v == "Visão Diária": pagina_visao_diaria(df)
        else: pagina_visao_mensal(df)
    else:
        st.error("Erro ao carregar dados.")

if __name__ == "__main__":
    main()
