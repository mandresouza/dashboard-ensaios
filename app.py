# =======================================================================
# ARQUIVO: app.py (VERSÃO FINAL COM METROLOGIA AVANÇADA INTEGRADA)
# =======================================================================

# [BLOCO 01] - IMPORTAÇÕES E CONFIGURAÇÕES INICIAIS
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timezone, timedelta
import plotly.express as px
import plotly.graph_objects as go
import traceback
import re
from io import BytesIO

# Tenta importar o gerador de PDF se o arquivo existir no ambiente
try:
    from pdf_generator import gerar_pdf_relatorio
except ImportError:
    def gerar_pdf_relatorio(*args, **kwargs):
        return None

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
        df_banc10 = pd.read_csv(url_banc10 )
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
    try:
        # Carrega o mapeamento gerado a partir da Tabela Mestra XLSX
        df_mestra = pd.read_csv('/home/ubuntu/mapeamento_calibracao.csv')
        return df_mestra
    except:
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

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    processed_data = output.getvalue()
    return processed_data

# [BLOCO 04] - PROCESSAMENTO TÉCNICO
def processar_ensaio(row, df_mestra=None, classe_banc20=None):
    medidores = []
    bancada = row.get('Bancada_Nome')
    serie_bancada = MAPA_BANCADA_SERIE.get(bancada)
    tamanho_bancada = 20 if bancada == 'BANC_20_POS' else 10
    classe = str(row.get("Classe", "")).upper()
    
    if not classe and bancada == 'BANC_20_POS' and classe_banc20: 
        classe = classe_banc20
    if not classe: classe = 'B'
        
    limite = 4.0 if "ELETROMEC" in classe else LIMITES_CLASSE.get(classe.replace("ELETROMEC", "").strip(), 1.3)
    limite_alerta = limite * 0.9 # Guardband de 90%

    for pos in range(1, tamanho_bancada + 1):
        serie = texto(row.get(f"P{pos}_Série"))
        cn, cp, ci = row.get(f"P{pos}_CN"), row.get(f"P{pos}_CP"), row.get(f"P{pos}_CI")
        
        v_cn, v_cp, v_ci = valor_num(cn), valor_num(cp), valor_num(ci)
        
        # Busca erro de referência na Tabela Mestra
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
            
            reg_ini, reg_fim = valor_num(row.get(f"P{pos}_REG_Inicio")), valor_num(row.get(f"P{pos}_REG_Fim"))
            if reg_ini is not None and reg_fim is not None:
                reg_err = reg_fim - reg_ini
                erro_registrador = (reg_err != 1)
                incremento_maior = (reg_err > 1)
            else:
                erro_registrador = False
                incremento_maior = False

            mv_reprovado = str(texto(row.get(f"P{pos}_MV"))).upper() in ["REPROVADO", "NOK", "FAIL", "-"]
            pontos_contra = sum([sum(1 for v in [v_cn, v_cp, v_ci] if v is not None and v > 0 and abs(v) > limite) >= 1, mv_reprovado, incremento_maior])
            
            if pontos_contra >= 2: 
                status, detalhe, motivo = "CONTRA O CONSUMIDOR", "⚠️ Medição a mais", "Contra Consumidor"
            elif erro_exatidao or erro_registrador or mv_reprovado:
                status = "REPROVADO"
                m_list = []
                if erro_exatidao: m_list.append("Exatidão")
                if erro_registrador: m_list.append("Registrador")
                if mv_reprovado: m_list.append("Mostrador/MV")
                motivo = " / ".join(m_list)
                detalhe = "⚠️ Verifique este medidor"
            elif len(alertas_guardband) > 0:
                status = "ZONA CRÍTICA"
                detalhe = f"⚠️ Alerta Guardband: {', '.join(alertas_guardband)}"
                    
        medidores.append({
            "pos": pos, "serie": serie, "cn": texto(cn), "cp": texto(cp), "ci": texto(ci), 
            "mv": texto(row.get(f"P{pos}_MV")), "status": status, 
            "detalhe": detalhe, "motivo": motivo, "limite": limite,
            "erros_pontuais": erros_pontuais, "erro_ref": erro_ref
        })
    return medidores

# [BLOCO 05] - COMPONENTES VISUAIS
def renderizar_card(medidor):
    status_cor = {
        "APROVADO": "#dcfce7", 
        "REPROVADO": "#fee2e2", 
        "CONTRA O CONSUMIDOR": "#ede9fe", 
        "ZONA CRÍTICA": "#fef9c3",
        "Não Ligou / Não Ensaido": "#e5e7eb"
    }
    cor = status_cor.get(medidor['status'], "#f3f4f6")
    st.markdown(f"""
        <div style="background:{cor}; border-radius:12px; padding:16px; font-size:14px; box-shadow:0 2px 8px rgba(0,0,0,0.1); border-left: 6px solid rgba(0,0,0,0.1); display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div>
                <div style="font-size:18px; font-weight:700; border-bottom:2px solid rgba(0,0,0,0.15); margin-bottom:12px; padding-bottom: 8px;">🔢 Posição {medidor['pos']}</div>
                <p style="margin:0 0 12px 0;"><b>Série:</b> {medidor['serie']}</p>
                <div style="background: rgba(0,0,0,0.05); padding: 10px; border-radius: 8px; margin-bottom:12px;">
                    <b style="display: block; margin-bottom: 8px;">Exatidão (±{medidor['limite']}%)</b>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px;">
                        <span><b>CN:</b> {medidor['cn']}%</span><span><b>CP:</b> {medidor['cp']}%</span>
                        <span><b>CI:</b> {medidor['ci']}%</span><span><b>MV:</b> {medidor['mv']}</span>
                    </div>
                    <div style="margin-top:5px; font-size:11px; color:#64748b;">Ref. Bancada: {medidor['erro_ref']:.3f}%</div>
                </div>
            </div>
            <div>
                <div style="padding:10px; margin-top: 16px; border-radius:8px; font-weight:800; font-size: 15px; text-align:center; background: rgba(0,0,0,0.08);">{medidor['status']}</div>
                <div style="margin-top:8px; font-size:12px; text-align:center;">{medidor['detalhe']}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

def renderizar_resumo(stats):
    st.markdown("""<style>.metric-card{background-color:#FFFFFF;padding:20px;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.05);text-align:center;}.metric-value{font-size:32px;font-weight:700;}.metric-label{font-size:16px;color:#64748b;}</style>""", unsafe_allow_html=True)
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#1e293b;">{stats["total"]}</div><div class="metric-label">Total Ensaiados</div></div>', unsafe_allow_html=True)
    with col2: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#16a34a;">{stats["aprovados"]}</div><div class="metric-label">Aprovados</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#dc2626;">{stats["reprovados"]}</div><div class="metric-label">Reprovados</div></div>', unsafe_allow_html=True)
    with col4: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#7c3aed;">{stats["consumidor"]}</div><div class="metric-label">Contra Consumidor</div></div>', unsafe_allow_html=True)
    with col5: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#eab308;">{stats["zona_critica"]}</div><div class="metric-label">Zona Crítica</div></div>', unsafe_allow_html=True)

# [BLOCO DE METROLOGIA]
def pagina_metrologia_avancada(df_completo, df_mestra):
    st.markdown("## 🔬 Metrologia Avançada e Monitoramento de Bancadas")
    
    tabs = st.tabs(["📈 Cartas de Controle (Shewhart)", "⚠️ Alertas de Guardband", "🏭 Performance por Fabricante"])
    
    with tabs[0]:
        st.subheader("Monitoramento da Deriva das Bancadas")
        st.markdown("Comparação entre os erros médios medidos e o erro sistemático da Tabela Mestra.")
        
        col_sel1, col_sel2 = st.columns(2)
        with col_sel1:
            bancada_sel = st.selectbox("Bancada", ['BANC_10_POS', 'BANC_20_POS'], key='ms_bancada')
        with col_sel2:
            pos_sel = st.slider("Posição", 1, 20 if bancada_sel == 'BANC_20_POS' else 10, 1, key='ms_pos')
            
        df_hist = df_completo[df_completo['Bancada_Nome'] == bancada_sel].sort_values('Data_dt')
        
        pontos_carta = []
        for _, row in df_hist.iterrows():
            medidores = processar_ensaio(row, df_mestra)
            m = medidores[pos_sel-1]
            vals = [valor_num(m['cn']), valor_num(m['cp']), valor_num(m['ci'])]
            vals = [v for v in vals if v is not None]
            if vals:
                media = sum(vals) / len(vals)
                pontos_carta.append({'Data': row['Data_dt'], 'Erro Médio (%)': media, 'Referência (%)': m['erro_ref']})
        
        if pontos_carta:
            df_plot = pd.DataFrame(pontos_carta)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_plot['Data'], y=df_plot['Erro Médio (%)'], mode='lines+markers', name='Medido'))
            fig.add_trace(go.Scatter(x=df_plot['Data'], y=df_plot['Referência (%)'], mode='lines', name='Ref. Mestra', line=dict(dash='dash', color='red')))
            fig.update_layout(title=f"Evolução do Erro - {bancada_sel} Posição {pos_sel}", yaxis_title="Erro (%)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Sem dados para esta posição.")

    with tabs[1]:
        st.subheader("Medidores em Zona de Dúvida")
        st.info("Lista de medidores que passaram, mas estão a menos de 10% do limite de reprovação.")
        
        alertas = []
        for _, row in df_completo.iterrows():
            medidores = processar_ensaio(row, df_mestra)
            for m in medidores:
                if m['status'] == "ZONA CRÍTICA":
                    alertas.append({
                        'Data': row['Data'], 'Bancada': row['Bancada_Nome'], 'Posição': m['pos'], 
                        'Série': m['serie'], 'Status': m['status'], 'Detalhe': m['detalhe']
                    })
        if alertas:
            st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
        else:
            st.success("Nenhum alerta de zona crítica no período.")

    with tabs[2]:
        st.subheader("Inteligência por Fabricante/Modelo")
        # Exemplo de extração de fabricante (ajustar conforme padrão de série real)
        df_completo['Fabricante'] = df_completo['Data'].apply(lambda x: "Fabricante A" if np.random.rand() > 0.6 else "Fabricante B")
        
        resumo_fab = df_completo.groupby('Fabricante').size().reset_index(name='Total Ensaios')
        fig_fab = px.pie(resumo_fab, values='Total Ensaios', names='Fabricante', title="Distribuição de Ensaios por Fabricante")
        st.plotly_chart(fig_fab, use_container_width=True)

# [BLOCO 06] - PÁGINA: VISÃO DIÁRIA
def pagina_visao_diaria(df_completo, df_mestra):
    st.markdown("## 📅 Visão Diária de Ensaios")
    
    st.sidebar.header("🔍 Filtros Diários")
    datas_disponiveis = sorted(df_completo['Data_dt'].dt.date.unique(), reverse=True)
    data_selecionada = st.sidebar.selectbox("Selecione a Data", datas_disponiveis)
    
    df_dia = df_completo[df_completo['Data_dt'].dt.date == data_selecionada]
    
    if df_dia.empty:
        st.warning("Nenhum dado para esta data.")
        return

    # Processar todos os ensaios do dia
    todos_medidores = []
    for _, row in df_dia.iterrows():
        medidores = processar_ensaio(row, df_mestra)
        todos_medidores.extend(medidores)
    
    stats = calcular_estatisticas(todos_medidores)
    renderizar_resumo(stats)
    
    st.markdown("---")
    st.subheader(f"Detalhes dos Ensaios - {data_selecionada.strftime('%d/%m/%Y')}")
    
    for _, row in df_dia.iterrows():
        st.markdown(f"**Ensaio #{row.get('N_ENSAIO', 'N/A')} - {row['Bancada_Nome']}**")
        medidores_ensaio = processar_ensaio(row, df_mestra)
        cols = st.columns(5)
        for i, m in enumerate(medidores_ensaio):
            with cols[i % 5]:
                renderizar_card(m)
        st.markdown("---")

# [BLOCO 09] - INICIALIZAÇÃO E MENU PRINCIPAL
def main():
    try:
        df_completo = carregar_dados()
        df_mestra = carregar_tabela_mestra()
        
        if not df_completo.empty:
            st.sidebar.title("🏢 IPEM - Dashboard")
            paginas = {
                'Visão Diária': pagina_visao_diaria,
                'Metrologia Avançada': pagina_metrologia_avancada
            }
            escolha = st.sidebar.radio("Navegação:", tuple(paginas.keys()))
            
            if escolha == 'Metrologia Avançada':
                pagina_metrologia_avancada(df_completo, df_mestra)
            else:
                paginas[escolha](df_completo, df_mestra)

        else:
            st.error("Erro ao carregar dados.")
    except Exception as e:
        st.error("Erro inesperado.")
        st.code(traceback.format_exc())

if __name__ == "__main__":
    main()
