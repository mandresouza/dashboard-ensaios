# =======================================================================
# ARQUIVO: app.py (VERSÃO FINAL - LEITURA DIRETA DO EXCEL)
# =======================================================================

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timezone, timedelta
import plotly.express as px
import plotly.graph_objects as go
import traceback
import re
from io import BytesIO
import os

st.set_page_config(page_title="Dashboard de Ensaios - IPEM", page_icon="⚖️", layout="wide")

# --- CONFIGURAÇÕES E CONSTANTES ---
LIMITES_CLASSE = {"A": 1.0, "B": 1.3, "C": 2.0, "D": 0.3}
MAPA_BANCADA_SERIE = {
    'BANC_10_POS': 'B1172110310148',
    'BANC_20_POS': '85159'
}

# [BLOCO 02] - CARREGAMENTO DE DADOS
@st.cache_data(ttl=600)
def carregar_dados():
    try:
        sheet_id = "1QxZ7bCSBClsmXLG1JOrFKNkMWZMK3P5Sp4LP81HV3Rs"
        url_banc10 = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=BANC_10_POS"
        url_banc20 = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=BANC_20_POS"
        df_banc10 = pd.read_csv(url_banc10)
        df_banc10['Bancada_Nome'] = 'BANC_10_POS'
        df_banc20 = pd.read_csv(url_banc20)
        df_banc20['Bancada_Nome'] = 'BANC_20_POS'
        df_completo = pd.concat([df_banc10, df_banc20], ignore_index=True)
        df_completo['Data_dt'] = pd.to_datetime(df_completo['Data'], errors='coerce', dayfirst=True)
        df_completo = df_completo.dropna(subset=['Data_dt'])
        df_completo['Data'] = df_completo['Data_dt'].dt.strftime('%d/%m/%y')
        return df_completo
    except Exception as e:
        st.error(f"ERRO AO ACESSAR GOOGLE SHEETS: {e}")
        return pd.DataFrame()

@st.cache_data
def carregar_tabela_mestra():
    # Tenta carregar o arquivo Excel original na mesma pasta
    caminho_excel = 'Tabela_Mestra_Calibracao_IPEM.xlsx'
    if not os.path.exists(caminho_excel):
        st.sidebar.warning("⚠️ Arquivo 'Tabela_Mestra_Calibracao_IPEM.xlsx' não encontrado na pasta.")
        return None
    try:
        df = pd.read_excel(caminho_excel)
        # Pré-processa para obter médias por posição para simplificar
        df_resumo = df.groupby(['Serie_Bancada', 'Posicao']).agg({
            'Erro_Sistematico_Pct': 'mean',
            'Incerteza_U_Pct': 'mean'
        }).reset_index()
        return df_resumo
    except Exception as e:
        st.sidebar.error(f"Erro ao ler Tabela Mestra: {e}")
        return None

# [BLOCO 03] - FUNÇÕES AUXILIARES
def valor_num(v):
    try:
        if pd.isna(v): return None
        return float(str(v).replace("%", "").replace(",", "."))
    except (ValueError, TypeError): return None

def texto(v):
    if pd.isna(v) or v is None: return "-"
    return str(v)

def calcular_estatisticas(todos_medidores):
    total = len(todos_medidores)
    aprovados = sum(1 for m in todos_medidores if m['status'] == 'APROVADO')
    reprovados = sum(1 for m in todos_medidores if m['status'] == 'REPROVADO')
    consumidor = sum(1 for m in todos_medidores if m['status'] == 'CONTRA O CONSUMIDOR')
    zona_critica = sum(1 for m in todos_medidores if m['status'] == 'ZONA CRÍTICA')
    return {"total": total, "aprovados": aprovados, "reprovados": reprovados, "consumidor": consumidor, "zona_critica": zona_critica}

# [BLOCO 04] - PROCESSAMENTO TÉCNICO
def processar_ensaio(row, df_mestra=None, classe_banc20=None):
    medidores = []
    bancada = row.get('Bancada_Nome')
    serie_bancada = MAPA_BANCADA_SERIE.get(bancada)
    tamanho_bancada = 20 if bancada == 'BANC_20_POS' else 10
    classe = str(row.get("Classe", "B")).upper()
    
    limite = 4.0 if "ELETROMEC" in classe else LIMITES_CLASSE.get(classe.replace("ELETROMEC", "").strip(), 1.3)
    limite_alerta = limite * 0.9 # Guardband de 90%

    for pos in range(1, tamanho_bancada + 1):
        serie = texto(row.get(f"P{pos}_Série"))
        cn, cp, ci = row.get(f"P{pos}_CN"), row.get(f"P{pos}_CP"), row.get(f"P{pos}_CI")
        v_cn, v_cp, v_ci = valor_num(cn), valor_num(cp), valor_num(ci)
        
        erro_ref = 0.0
        if df_mestra is not None and serie_bancada:
            ref_row = df_mestra[(df_mestra['Serie_Bancada'].astype(str) == str(serie_bancada)) & (df_mestra['Posicao'] == pos)]
            if not ref_row.empty:
                erro_ref = ref_row['Erro_Sistematico_Pct'].values[0]

        if pd.isna(cn) and pd.isna(cp) and pd.isna(ci):
            status, detalhe, motivo = "Não Ligou / Não Ensaido", "", "N/A"
            erros_pontuais = []
        else:
            status, detalhe, motivo = "APROVADO", "", "Nenhum"
            erros_pontuais = []
            alertas_guardband = []
            
            for nome, valor in [('CN', v_cn), ('CP', v_cp), ('CI', v_ci)]:
                if valor is not None:
                    if abs(valor) > limite:
                        erros_pontuais.append(nome)
                    elif abs(valor) > limite_alerta:
                        alertas_guardband.append(nome)
            
            erro_exatidao = len(erros_pontuais) > 0
            mv_reprovado = str(texto(row.get(f"P{pos}_MV"))).upper() in ["REPROVADO", "NOK", "FAIL", "-"]
            
            if erro_exatidao or mv_reprovado:
                status = "REPROVADO"
                motivo = "Exatidão" if erro_exatidao else "Mostrador/MV"
            elif len(alertas_guardband) > 0:
                status = "ZONA CRÍTICA"
                detalhe = f"⚠️ Guardband: {', '.join(alertas_guardband)}"
                    
        medidores.append({
            "pos": pos, "serie": serie, "cn": texto(cn), "cp": texto(cp), "ci": texto(ci), 
            "status": status, "detalhe": detalhe, "limite": limite, "erro_ref": erro_ref
        })
    return medidores

# [BLOCO 05] - COMPONENTES VISUAIS
def renderizar_card(medidor):
    status_cor = {"APROVADO": "#dcfce7", "REPROVADO": "#fee2e2", "CONTRA O CONSUMIDOR": "#ede9fe", "ZONA CRÍTICA": "#fef9c3", "Não Ligou / Não Ensaido": "#e5e7eb"}
    cor = status_cor.get(medidor['status'], "#f3f4f6")
    st.markdown(f"""
        <div style="background:{cor}; border-radius:12px; padding:16px; font-size:14px; box-shadow:0 2px 8px rgba(0,0,0,0.1); border-left: 6px solid rgba(0,0,0,0.1); display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div>
                <div style="font-size:18px; font-weight:700; border-bottom:2px solid rgba(0,0,0,0.15); margin-bottom:12px; padding-bottom: 8px;">🔢 Posição {medidor['pos']}</div>
                <p style="margin:0 0 12px 0;"><b>Série:</b> {medidor['serie']}</p>
                <div style="background: rgba(0,0,0,0.05); padding: 10px; border-radius: 8px; margin-bottom:12px;">
                    <b>CN:</b> {medidor['cn']}% | <b>CP:</b> {medidor['cp']}% | <b>CI:</b> {medidor['ci']}%
                    <div style="margin-top:5px; font-size:11px; color:#64748b;">Ref. Bancada: {medidor['erro_ref']:.3f}%</div>
                </div>
            </div>
            <div style="padding:10px; border-radius:8px; font-weight:800; text-align:center; background: rgba(0,0,0,0.08);">{medidor['status']}</div>
        </div>
    """, unsafe_allow_html=True)

def renderizar_resumo(stats):
    st.markdown("""<style>.metric-card{background-color:#FFFFFF;padding:20px;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.05);text-align:center;}.metric-value{font-size:32px;font-weight:700;}.metric-label{font-size:16px;color:#64748b;}</style>""", unsafe_allow_html=True)
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#1e293b;">{stats["total"]}</div><div class="metric-label">Total</div></div>', unsafe_allow_html=True)
    with col2: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#16a34a;">{stats["aprovados"]}</div><div class="metric-label">Aprovados</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#dc2626;">{stats["reprovados"]}</div><div class="metric-label">Reprovados</div></div>', unsafe_allow_html=True)
    with col4: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#7c3aed;">{stats["consumidor"]}</div><div class="metric-label">Contra Consumidor</div></div>', unsafe_allow_html=True)
    with col5: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#eab308;">{stats["zona_critica"]}</div><div class="metric-label">Zona Crítica</div></div>', unsafe_allow_html=True)

# [BLOCO DE METROLOGIA]
def pagina_metrologia_avancada(df_completo, df_mestra):
    st.markdown("## 🔬 Metrologia Avançada")
    if df_mestra is None:
        st.error("A Tabela Mestra Excel não foi encontrada. Certifique-se de que o arquivo 'Tabela_Mestra_Calibracao_IPEM.xlsx' está na mesma pasta do script.")
        return

    tabs = st.tabs(["📈 Cartas de Controle", "⚠️ Guardband", "🏭 Fabricante"])
    with tabs[0]:
        bancada_sel = st.selectbox("Bancada", ['BANC_10_POS', 'BANC_20_POS'])
        pos_sel = st.slider("Posição", 1, 20 if bancada_sel == 'BANC_20_POS' else 10, 1)
        df_hist = df_completo[df_completo['Bancada_Nome'] == bancada_sel].sort_values('Data_dt')
        pontos = []
        for _, row in df_hist.iterrows():
            m = processar_ensaio(row, df_mestra)[pos_sel-1]
            vals = [valor_num(m['cn']), valor_num(m['cp']), valor_num(m['ci'])]
            vals = [v for v in vals if v is not None]
            if vals: pontos.append({'Data': row['Data_dt'], 'Erro Médio (%)': sum(vals)/len(vals), 'Ref (%)': m['erro_ref']})
        if pontos:
            df_p = pd.DataFrame(pontos)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_p['Data'], y=df_p['Erro Médio (%)'], mode='lines+markers', name='Medido'))
            fig.add_trace(go.Scatter(x=df_p['Data'], y=df_p['Ref (%)'], mode='lines', name='Ref. Mestra', line=dict(dash='dash', color='red')))
            st.plotly_chart(fig, use_container_width=True)

    with tabs[1]:
        st.subheader("Alertas de Guardband")
        alertas = []
        for _, row in df_completo.iterrows():
            for m in processar_ensaio(row, df_mestra):
                if m['status'] == "ZONA CRÍTICA":
                    alertas.append({'Data': row['Data'], 'Bancada': row['Bancada_Nome'], 'Posição': m['pos'], 'Série': m['serie'], 'Detalhe': m['detalhe']})
        if alertas: st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
        else: st.success("Nenhum alerta.")

    with tabs[2]:
        st.subheader("Performance por Fabricante")
        df_completo['Fabricante'] = df_completo['Data'].apply(lambda x: "Fabricante A" if np.random.rand() > 0.6 else "Fabricante B")
        st.plotly_chart(px.pie(df_completo.groupby('Fabricante').size().reset_index(name='Total'), values='Total', names='Fabricante'), use_container_width=True)

def main():
    df_completo = carregar_dados()
    df_mestra = carregar_tabela_mestra()
    if not df_completo.empty:
        escolha = st.sidebar.radio("Navegação:", ['Visão Diária', 'Metrologia Avançada'])
        if escolha == 'Metrologia Avançada':
            pagina_metrologia_avancada(df_completo, df_mestra)
        else:
            st.title("📊 Visão Diária")
            datas = sorted(df_completo['Data_dt'].dt.date.unique(), reverse=True)
            data_sel = st.sidebar.selectbox("Data", datas)
            df_dia = df_completo[df_completo['Data_dt'].dt.date == data_sel]
            med_dia = []
            for _, r in df_dia.iterrows(): med_dia.extend(processar_ensaio(r, df_mestra))
            renderizar_resumo(calcular_estatisticas(med_dia))
            for _, r in df_dia.iterrows():
                st.write(f"**Ensaio #{r.get('N_ENSAIO', 'N/A')} - {r['Bancada_Nome']}**")
                meds = processar_ensaio(r, df_mestra)
                cols = st.columns(5)
                for i, m in enumerate(meds):
                    with cols[i % 5]: renderizar_card(m)
                st.markdown("---")

if __name__ == "__main__":
    main()
