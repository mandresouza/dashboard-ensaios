
# =======================================================================
# ARQUIVO: app.py (VERSÃO FINAL CORRIGIDA)
# =======================================================================

# [BLOCO 01] - IMPORTAÇÕES E CONFIGURAÇÕES INICIAIS
import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import plotly.graph_objects as go
import traceback
import re # Importa a biblioteca de expressões regulares
from pdf_generator import gerar_pdf_relatorio

st.set_page_config(page_title="Dashboard de Ensaios", page_icon="📊", layout="wide")
LIMITES_CLASSE = {"A": 1.0, "B": 1.3, "C": 2.0, "D": 0.3}

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
    return {"total": total, "aprovados": aprovados, "reprovados": reprovados, "consumidor": consumidor}

# [BLOCO 04] - PROCESSAMENTO TÉCNICO
def processar_ensaio(row, classe_banc20=None):
    medidores = []
    bancada = row.get('Bancada_Nome')
    tamanho_bancada = 20 if bancada == 'BANC_20_POS' else 10
    classe = str(row.get("Classe", "")).upper()
    
    if not classe and bancada == 'BANC_20_POS' and classe_banc20: 
        classe = classe_banc20
    if not classe: classe = 'B'
        
    limite = 4.0 if "ELETROMEC" in classe else LIMITES_CLASSE.get(classe.replace("ELETROMEC", "").strip(), 1.3)
    
    for pos in range(1, tamanho_bancada + 1):
        serie = texto(row.get(f"P{pos}_Série"))
        cn, cp, ci = row.get(f"P{pos}_CN"), row.get(f"P{pos}_CP"), row.get(f"P{pos}_CI")
        
        status, detalhe, motivo = "NÃO ENTROU", "", "N/A"
        reg_err = None
        
        if serie != "-":
            v_cn, v_cp, v_ci = valor_num(cn), valor_num(cp), valor_num(ci)
            erro_exatidao = any(v is not None and abs(v) > limite for v in [v_cn, v_cp, v_ci])
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
            else:
                status, detalhe, motivo = "APROVADO", "", "Nenhum"
                    
        medidores.append({
            "pos": pos, "serie": serie, "cn": texto(cn), "cp": texto(cp), "ci": texto(ci), 
            "mv": texto(row.get(f"P{pos}_MV")), "reg_ini": texto(row.get(f"P{pos}_REG_Inicio")), 
            "reg_fim": texto(row.get(f"P{pos}_REG_Fim")), "status": status, 
            "detalhe": detalhe, "motivo": motivo, "limite": limite
        })
    return medidores

# [BLOCO 05] - COMPONENTES VISUAIS
def renderizar_card(medidor):
    status_cor = {"APROVADO": "#dcfce7", "REPROVADO": "#fee2e2", "CONTRA O CONSUMIDOR": "#ede9fe", "NÃO ENTROU": "#e5e7eb"}
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
                </div>
            </div>
            <div>
                <div style="padding:10px; margin-top: 16px; border-radius:8px; font-weight:800; font-size: 15px; text-align:center; background: rgba(0,0,0,0.08);">{medidor['status'].replace('_', ' ')}</div>
                <div style="margin-top:8px; font-size:12px; text-align:center;">{medidor['detalhe']}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

def renderizar_cabecalho_ensaio(n_ensaio, bancada, temperatura):
    st.markdown(f"""
    <div style="background-color: #f0f2f6; padding: 10px 15px; border-radius: 10px; margin-bottom: 15px; border-left: 5px solid #007bff;">
        <h4 style="margin: 0; color: #333;">Ensaio #{n_ensaio}</h4>
        <div style="display: flex; justify-content: space-between; font-size: 14px; color: #555; margin-top: 5px;">
            <span><strong>Bancada:</strong> {bancada}</span>
            <span><strong>Temperatura:</strong> 🌡️ {temperatura}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def renderizar_resumo(stats):
    st.markdown("""<style>.metric-card{background-color:#FFFFFF;padding:20px;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.05);text-align:center;}.metric-value{font-size:32px;font-weight:700;}.metric-label{font-size:16px;color:#64748b;}</style>""", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#1e293b;">{stats["total"]}</div><div class="metric-label">Total Filtrado</div></div>', unsafe_allow_html=True)
    with col2: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#16a34a;">{stats["aprovados"]}</div><div class="metric-label">Aprovados</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#dc2626;">{stats["reprovados"]}</div><div class="metric-label">Reprovados</div></div>', unsafe_allow_html=True)
    with col4: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#7c3aed;">{stats["consumidor"]}</div><div class="metric-label">Contra Consumidor</div></div>', unsafe_allow_html=True)

def renderizar_grafico_reprovacoes(medidores):
    # ... (código sem alterações)
    pass

# [BLOCO 06] - PÁGINA: VISÃO DIÁRIA
def pagina_visao_diaria(df_completo):
    st.sidebar.header("🔍 Busca e Filtros")
    
    if "filtro_data" not in st.session_state: st.session_state.filtro_data = date.today()
    if "filtro_bancada" not in st.session_state: st.session_state.filtro_bancada = "Todas"
    if "filtro_status" not in st.session_state: st.session_state.filtro_status = []
    if "filtro_irregularidade" not in st.session_state: st.session_state.filtro_irregularidade = []
    if "search_key" not in st.session_state: st.session_state.search_key = 0

    serie_input = st.sidebar.text_input("Pesquisar Número de Série", key=f"busca_{st.session_state.search_key}")
    termo_busca = serie_input.strip().lower()

    if st.sidebar.button("🗑️ Limpar Pesquisa", key="limpar"):
        st.session_state.search_key += 1
        st.rerun()
    
    if termo_busca:
        st.markdown(f"### 🔍 Busca de Série do Medidor: **{serie_input}**")
        with st.spinner("Localizando medidor..."):
            resultados_encontrados = []
            for _, ensaio_row in df_completo.iterrows():
                medidores_do_ensaio = processar_ensaio(ensaio_row)
                for medidor in medidores_do_ensaio:
                    if termo_busca in medidor['serie'].lower():
                        resultados_encontrados.append({"ensaio": ensaio_row, "medidor": medidor})

            if resultados_encontrados:
                st.success(f"Encontrado(s) {len(resultados_encontrados)} registro(s).")
                for res in resultados_encontrados:
                    n_ensaio = res['ensaio']['N_ENSAIO']
                    bancada = res['ensaio']['Bancada']
                    temp_str = str(res['ensaio']['Temperatura'])
                    temp_match = re.search(r'(\d+\.\d+°C)', temp_str)
                    temperatura = temp_match.group(1) if temp_match else temp_str
                    
                    renderizar_cabecalho_ensaio(n_ensaio, bancada, temperatura)
                    renderizar_card(res['medidor'])
            else:
                st.warning(f"Nenhum registro encontrado para a série '{serie_input}'.")
    else:
        st.sidebar.markdown("---")
        st.session_state.filtro_data = st.sidebar.date_input("Data do Ensaio", value=st.session_state.filtro_data, format="DD/MM/YYYY")
        
        if st.session_state.filtro_data is None:
            st.info("Por favor, selecione uma data para visualizar os ensaios.")
            return

        data_selecionada_str = st.session_state.filtro_data.strftime('%d/%m/%y')
        
        bancadas_disponiveis = df_completo['Bancada'].unique().tolist()
        bancada_idx = 0
        if st.session_state.filtro_bancada in bancadas_disponiveis:
            bancada_idx = (['Todas'] + bancadas_disponiveis).index(st.session_state.filtro_bancada)
        st.session_state.filtro_bancada = st.sidebar.selectbox("Bancada", options=['Todas'] + bancadas_disponiveis, index=bancada_idx)
        
        status_options = ["APROVADO", "REPROVADO", "CONTRA O CONSUMIDOR"]
        st.session_state.filtro_status = st.sidebar.multiselect("Filtrar Status", options=status_options, default=st.session_state.filtro_status)
        
        if "REPROVADO" in st.session_state.filtro_status:
            irregularidade_options = ["Exatidão", "Registrador", "Mostrador/MV"]
            st.session_state.filtro_irregularidade = st.sidebar.multiselect("Filtrar por Tipo de Irregularidade", options=irregularidade_options, default=st.session_state.filtro_irregularidade)
        else:
            st.session_state.filtro_irregularidade = []

        st.markdown(f"### 📅 Relatório de Ensaios Realizados em: **{st.session_state.filtro_data.strftime('%d/%m/%Y')}**")
        
        df_filtrado_dia = df_completo[df_completo['Data'] == data_selecionada_str].copy()
        if st.session_state.filtro_bancada != 'Todas': 
            df_filtrado_dia = df_filtrado_dia[df_filtrado_dia['Bancada'] == st.session_state.filtro_bancada]

        if df_filtrado_dia.empty:
            st.info(f"Não constam ensaios registrados para o dia {data_selecionada_str}.")
            return

        ensaios_para_pdf = []
        todos_medidores_filtrados = []

        for _, ensaio_row in df_filtrado_dia.iterrows():
            medidores_deste_ensaio = processar_ensaio(ensaio_row)
            medidores_filtrados_deste_ensaio = []

            for medidor in medidores_deste_ensaio:
                if medidor['status'] == "NÃO ENTROU": continue
                
                status_match = not st.session_state.filtro_status or medidor['status'] in st.session_state.filtro_status
                irregularidade_match = True
                if st.session_state.filtro_irregularidade and medidor['status'] == 'REPROVADO':
                    irregularidade_match = any(irr in medidor['motivo'] for irr in st.session_state.filtro_irregularidade)
                
                if status_match and irregularidade_match:
                    medidores_filtrados_deste_ensaio.append(medidor)
            
            if medidores_filtrados_deste_ensaio:
                n_ensaio = ensaio_row['N_ENSAIO']
                bancada = ensaio_row['Bancada']
                temp_str = str(ensaio_row['Temperatura'])
                temp_match = re.search(r'(\d+\.\d+°C)', temp_str)
                temperatura = temp_match.group(1) if temp_match else temp_str

                ensaio_obj = {
                    "n_ensaio": n_ensaio,
                    "bancada": bancada,
                    "temperatura": temperatura,
                    "medidores": medidores_filtrados_deste_ensaio
                }
                ensaios_para_pdf.append(ensaio_obj)
                todos_medidores_filtrados.extend(medidores_filtrados_deste_ensaio)

        if todos_medidores_filtrados:
            stats = calcular_estatisticas(todos_medidores_filtrados)
            renderizar_resumo(stats)
            
            st.sidebar.markdown("---")
            st.sidebar.subheader("📄 Exportar Relatório")
            pdf_bytes = gerar_pdf_relatorio(ensaios=ensaios_para_pdf, data=data_selecionada_str, stats=stats)
            st.sidebar.download_button(label="📥 Baixar Relatório PDF", data=pdf_bytes, file_name=f"Relatorio_Ensaios_{st.session_state.filtro_data.strftime('%Y-%m-%d')}.pdf", mime="application/pdf")

            st.markdown("---")
            st.subheader("📋 Detalhes dos Ensaios")
            
            for ensaio in ensaios_para_pdf:
                renderizar_cabecalho_ensaio(ensaio['n_ensaio'], ensaio['bancada'], ensaio['temperatura'])
                num_colunas = 5
                for idx in range(0, len(ensaio['medidores']), num_colunas):
                    cols = st.columns(num_colunas)
                    for j, medidor in enumerate(ensaio['medidores'][idx:idx + num_colunas]):
                        with cols[j]:
                            renderizar_card(medidor)
                    st.write("")
        else:
            st.info("Nenhum medidor encontrado para os filtros selecionados.")
            
# [BLOCO 07] - PÁGINA: VISÃO MENSAL
def get_stats_por_dia(df_mes):
    daily_stats = []
    for data, group in df_mes.groupby('Data_dt'):
        medidores = []
        for _, row in group.iterrows(): 
            medidores.extend(processar_ensaio(row, 'B'))
        
        aprovados = sum(1 for m in medidores if m['status'] == 'APROVADO')
        reprovados = sum(1 for m in medidores if m['status'] == 'REPROVADO')
        consumidor = sum(1 for m in medidores if m['status'] == 'CONTRA O CONSUMIDOR')
        total = aprovados + reprovados + consumidor
        taxa_aprovacao = (aprovados / total * 100) if total > 0 else 0
        
        daily_stats.append({'Data': data, 'Aprovados': aprovados, 'Reprovados': reprovados, 'Contra Consumidor': consumidor, 'Total': total, 'Taxa de Aprovação (%)': round(taxa_aprovacao, 1)})
    return pd.DataFrame(daily_stats)

def pagina_visao_mensal(df_completo):
    st.sidebar.header("📅 Filtros Mensais")
    anos = sorted(df_completo['Data_dt'].dt.year.unique(), reverse=True)
    meses_dict = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
    
    col_filt1, col_filt2 = st.sidebar.columns(2)
    with col_filt1:
        ano_selecionado = st.selectbox("Ano", anos)
    with col_filt2:
        mes_selecionado_num = st.selectbox("Mês", options=list(meses_dict.keys()), format_func=lambda x: meses_dict[x])
    
    df_mes = df_completo[(df_completo['Data_dt'].dt.year == ano_selecionado) & (df_completo['Data_dt'].dt.month == mes_selecionado_num)]
    
    st.markdown(f"## 📈 Análise Consolidada: {meses_dict[mes_selecionado_num]} / {ano_selecionado}")
    
    if df_mes.empty:
        st.info(f"Nenhum dado encontrado para {meses_dict[mes_selecionado_num]} de {ano_selecionado}.")
        return
        
    with st.spinner("Processando indicadores mensais..."):
        todos_medidores_mes = []
        for _, row in df_mes.iterrows(): 
            todos_medidores_mes.extend(processar_ensaio(row, 'B'))
            
        total_m = len(todos_medidores_mes)
        aprov_m = sum(1 for m in todos_medidores_mes if m['status'] == 'APROVADO')
        repro_m = sum(1 for m in todos_medidores_mes if m['status'] == 'REPROVADO')
        cons_m = sum(1 for m in todos_medidores_mes if m['status'] == 'CONTRA O CONSUMIDOR')
        taxa_m = (aprov_m / total_m * 100) if total_m > 0 else 0

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Total Ensaiados", total_m)
        col_m2.metric("Taxa de Aprovação", f"{taxa_m:.1f}%", delta=f"{taxa_m-95:.1f}% vs Meta (95%)" if taxa_m > 0 else None)
        col_m3.metric("Total Reprovados", repro_m, delta=repro_m, delta_color="inverse")
        col_m4.metric("Contra Consumidor", cons_m, delta=cons_m, delta_color="inverse")

        st.markdown("---")

        col_g1, col_g2 = st.columns([1, 1.5])
        
        with col_g1:
            df_pie = pd.DataFrame({'Status': ['Aprovados', 'Reprovados', 'Contra Consumidor'], 'Qtd': [aprov_m, repro_m, cons_m]})
            fig_donut = px.pie(df_pie, values='Qtd', names='Status', hole=.5, title='<b>Distribuição de Qualidade</b>', color_discrete_map={'Aprovados':'#16a34a', 'Reprovados':'#dc2626', 'Contra Consumidor':'#7c3aed'})
            fig_donut.update_traces(textposition='inside', textinfo='percent+label')
            fig_donut.update_layout(showlegend=False, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_donut, use_container_width=True)

        with col_g2:
            df_daily = get_stats_por_dia(df_mes)
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(x=df_daily['Data'], y=df_daily['Aprovados'], name='Aprovados', marker_color='#16a34a'))
            fig_bar.add_trace(go.Bar(x=df_daily['Data'], y=df_daily['Reprovados'], name='Reprovados', marker_color='#dc2626'))
            fig_bar.add_trace(go.Bar(x=df_daily['Data'], y=df_daily['Contra Consumidor'], name='Contra Consumidor', marker_color='#7c3aed'))
            
            fig_bar.update_layout(barmode='stack', title='<b>Evolução Diária de Ensaios</b>', xaxis_title="Dia do Mês", yaxis_title="Quantidade de Medidores", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(t=80, b=40, l=0, r=0), hovermode="x unified")
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with st.expander("📄 Visualizar Tabela de Performance Diária"):
            st.dataframe(df_daily.sort_values('Data', ascending=False), use_container_width=True, hide_index=True)

# [BLOCO 08] - INICIALIZAÇÃO E MENU PRINCIPAL
def main():
    st.title("📊 Dashboard de Ensaios")
    try:
        df_completo = carregar_dados()
        if not df_completo.empty:
            st.sidebar.title("Menu de Navegação")
            tipo_visao = st.sidebar.radio("Escolha a análise:", ('Visão Diária', 'Visão Mensal'))
            if tipo_visao == 'Visão Diária':
                pagina_visao_diaria(df_completo)
            else:
                pagina_visao_mensal(df_completo)
        else:
            st.error("Erro ao carregar dados. Verifique a conexão com o Google Sheets.")
    except Exception as e:
        st.error("Ocorreu um erro inesperado na aplicação.")
        st.code(traceback.format_exc())

# PONTO DE ENTRADA PRINCIPAL DO SCRIPT
if __name__ == "__main__":
    main()
