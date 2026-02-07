# =======================================================================
# ARQUIVO: app.py (VERSÃO ORGANIZADA POR BLOCOS NUMERADOS)
# =======================================================================

# [BLOCO 01] - IMPORTAÇÕES E CONFIGURAÇÕES INICIAIS
import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import traceback

st.set_page_config(page_title="Dashboard de Ensaios", page_icon="📊", layout="wide")
LIMITES_CLASSE = {"A": 1.0, "B": 1.3, "C": 2.0, "D": 0.3}

# -----------------------------------------------------------------------

# [BLOCO 02] - CARREGAMENTO DE DADOS (BANCO DE DADOS)
@st.cache_data(ttl=600)
def carregar_dados():
    try:
        caminho_arquivo = "/mount/src/dashboard-ensaios/BANCO_DADOS_GERAL.xlsx"
        
        df_banc10 = pd.read_excel(caminho_arquivo, sheet_name="BANC_10_POS")
        df_banc10['Bancada'] = 'BANC_10_POS'
        
        df_banc20 = pd.read_excel(caminho_arquivo, sheet_name="BANC_20_POS")
        df_banc20['Bancada'] = 'BANC_20_POS'

        df_completo = pd.concat([df_banc10, df_banc20], ignore_index=True)
        df_completo['Data_dt'] = pd.to_datetime(df_completo['Data'], errors='coerce', dayfirst=True)
        df_completo = df_completo.dropna(subset=['Data_dt'])
        df_completo['Data'] = df_completo['Data_dt'].dt.strftime('%d/%m/%y')
        return df_completo
    except Exception as e:
        st.error(f"ERRO NO BLOCO 02 (CARREGAMENTO): {e}")
        return pd.DataFrame()

# -----------------------------------------------------------------------

# [BLOCO 03] - FUNÇÕES AUXILIARES (CONVERSÃO E ESTATÍSTICAS)
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

# -----------------------------------------------------------------------

# [BLOCO 04] - PROCESSAMENTO TÉCNICO DOS ENSAIOS (LÓGICA DE APROVAÇÃO)
def processar_ensaio(row, classe_banc20=None):
    medidores = []
    bancada = row.get('Bancada')
    tamanho_bancada = 20 if bancada == 'BANC_20_POS' else 10
    classe = str(row.get("Classe", "")).upper()
    
    if not classe and bancada == 'BANC_20_POS' and classe_banc20: 
        classe = classe_banc20
    if not classe: 
        classe = 'B'
        
    limite = 4.0 if "ELETROMEC" in classe else LIMITES_CLASSE.get(classe.replace("ELETROMEC", "").strip(), 1.3)
    
    for pos in range(1, tamanho_bancada + 1):
        serie = texto(row.get(f"P{pos}_Série"))
        cn, cp, ci = row.get(f"P{pos}_CN"), row.get(f"P{pos}_CP"), row.get(f"P{pos}_CI")
        
        if pd.isna(cn) and pd.isna(cp) and pd.isna(ci): 
            status, detalhe = "NÃO ENTROU", ""
        else:
            cargas_positivas_acima = sum(1 for v in [cn, cp, ci] if valor_num(v) is not None and valor_num(v) > 0 and abs(valor_num(v)) > limite)
            reg_ini, reg_fim = valor_num(row.get(f"P{pos}_REG_Inicio")), valor_num(row.get(f"P{pos}_REG_Fim"))
            reg_incremento_maior = (reg_ini is not None and reg_fim is not None and (reg_fim - reg_ini) > 1)
            reg_ok = (reg_ini is not None and reg_fim is not None and (reg_fim - reg_ini) == 1)
            mv_reprovado = str(texto(row.get(f"P{pos}_MV"))).upper() in ["REPROVADO", "NOK", "FAIL", "-"]
            
            pontos_contra = sum([cargas_positivas_acima >= 1, mv_reprovado, reg_incremento_maior])
            
            if pontos_contra >= 2: 
                status, detalhe = "CONTRA O CONSUMIDOR", "<b>⚠️ Medição a mais</b>"
            else:
                aprovado = all(valor_num(v) is None or abs(valor_num(v)) <= limite for v in [cn, cp, ci]) and reg_ok and not mv_reprovado
                if aprovado: 
                    status, detalhe = "APROVADO", ""
                else:
                    status = "REPROVADO"
                    normais = sum(1 for v in [cn, cp, ci] if valor_num(v) is not None and abs(valor_num(v)) <= limite)
                    reprovados = sum(1 for v in [cn, cp, ci] if valor_num(v) is not None and abs(valor_num(v)) > limite)
                    detalhe = "<b>⚠️ Verifique este medidor</b>" if normais >= 1 and reprovados >= 1 else ""
                    
        medidores.append({
            "pos": pos, "serie": serie, "cn": texto(cn), "cp": texto(cp), "ci": texto(ci), 
            "mv": texto(row.get(f"P{pos}_MV")), "reg_ini": texto(row.get(f"P{pos}_REG_Inicio")), 
            "reg_fim": texto(row.get(f"P{pos}_REG_Fim")), "reg_err": texto(row.get(f"P{pos}_REG_Erro")), 
            "status": status, "detalhe": detalhe, "limite": limite, "bancada": bancada, "classe_exatidao": classe
        })
    return medidores

# -----------------------------------------------------------------------

# [BLOCO 05] - COMPONENTES VISUAIS (CARDS E RESUMO)
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
                <div style="background: rgba(0,0,0,0.05); padding: 10px; border-radius: 8px;">
                    <b style="display: block; margin-bottom: 8px;">Registrador</b>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px;">
                        <span><b>Início:</b> {medidor['reg_ini']}</span><span><b>Fim:</b> {medidor['reg_fim']}</span>
                        <span style="grid-column: span 2;"><b>Erro:</b> {medidor['reg_err']}</span>
                    </div>
                </div>
            </div>
            <div>
                <div style="padding:10px; margin-top: 16px; border-radius:8px; font-weight:800; font-size: 15px; text-align:center; background: rgba(0,0,0,0.08);">{medidor['status'].replace('_', ' ')}</div>
                <div style="margin-top:8px; font-size:12px; text-align:center;">{medidor['detalhe']}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

def renderizar_resumo(stats):
    st.markdown("""<style>.metric-card{background-color:#FFFFFF;padding:20px;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.05);text-align:center;}.metric-value{font-size:32px;font-weight:700;}.metric-label{font-size:16px;color:#64748b;}</style>""", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#1e293b;">{stats["total"]}</div><div class="metric-label">Total Ensaiados</div></div>', unsafe_allow_html=True)
    with col2: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#16a34a;">{stats["aprovados"]}</div><div class="metric-label">Aprovados</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#dc2626;">{stats["reprovados"]}</div><div class="metric-label">Reprovados</div></div>', unsafe_allow_html=True)
    with col4: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#7c3aed;">{stats["consumidor"]}</div><div class="metric-label">Contra Consumidor</div></div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------

# [BLOCO 06] - PÁGINA: VISÃO DIÁRIA (FILTROS E PROCESSAMENTO)
def pagina_visao_diaria(df_completo):
    st.sidebar.header("🔍 Busca e Filtros")
    
    # TRUQUE PARA LIMPAR: Usamos uma chave que muda quando queremos resetar o campo
    if "search_key" not in st.session_state:
        st.session_state.search_key = 0

    # Input de busca por série com chave dinâmica
    serie_input = st.sidebar.text_input(
        "Pesquisar Número de Série", 
        value="", 
        key=f"busca_{st.session_state.search_key}", 
        help="Digite o número e pressione Enter"
    )
    termo_busca = serie_input.strip().lower()

    # Botão de Limpar: Ele muda a chave, o que força o Streamlit a criar um campo novo e VAZIO
    if termo_busca:
        if st.sidebar.button("🗑️ Limpar Pesquisa"):
            st.session_state.search_key += 1  # Muda a chave para resetar o campo
            st.rerun()

    # --- LÓGICA 1: BUSCA POR SÉRIE ---
    if termo_busca:
        st.markdown(f"### 🔍 Busca de Série do Medidor: **{serie_input}**")
        
        with st.spinner("Localizando medidor..."):
            resultados_encontrados = []
            for _, ensaio_row in df_completo.iterrows():
                colunas_serie = [c for c in ensaio_row.index if "_Série" in str(c)]
                if any(termo_busca in str(ensaio_row[col]).lower() for col in colunas_serie if pd.notna(ensaio_row[col])):
                    medidores_do_ensaio = processar_ensaio(ensaio_row)
                    for medidor in medidores_do_ensaio:
                        if termo_busca in medidor['serie'].lower():
                            resultados_encontrados.append({"data": ensaio_row['Data'], "bancada": ensaio_row['Bancada'], "dados": medidor})

            if resultados_encontrados:
                st.success(f"Encontrado(s) {len(resultados_encontrados)} registro(s).")
                for res in resultados_encontrados:
                    with st.expander(f"📍 Data: {res['data']} | Bancada: {res['bancada']}", expanded=True):
                        renderizar_card(res['dados'])
            else:
                st.warning(f"Nenhum registro encontrado para a série '{serie_input}'.")

    # --- LÓGICA 2: RELATÓRIO POR DATA ---
    else:
        st.sidebar.markdown("---")
        
        # CORREÇÃO DA DATA: Forçando a data correta (06/02/2026) independente do servidor
        import datetime as dt
        data_hoje = dt.date(2026, 2, 6) # Data fixa solicitada para hoje
        
        data_selecionada_dt = st.sidebar.date_input("Data do Ensaio", value=data_hoje, format="DD/MM/YYYY")
        data_selecionada_str = data_selecionada_dt.strftime('%d/%m/%y')
        
        bancadas_disponiveis = df_completo['Bancada'].unique().tolist()
        bancada_selecionada = st.sidebar.selectbox("Bancada", options=['Todas'] + bancadas_disponiveis)
        status_filter = st.sidebar.multiselect("Filtrar Status", options=["APROVADO", "REPROVADO", "CONTRA O CONSUMIDOR"])
        
        st.markdown(f"### 📅 Relatório de Ensaios Realizados em: **{data_selecionada_str}**")
        
        df_filtrado = df_completo[df_completo['Data'] == data_selecionada_str].copy()
        if bancada_selecionada != 'Todas': 
            df_filtrado = df_filtrado[df_filtrado['Bancada'] == bancada_selecionada]
        
        if df_filtrado.empty:
            st.info(f"Não constam ensaios registrados para o dia {data_selecionada_str}.")
            return

        with st.spinner("Carregando dados..."):
            todos_medidores = []
            for _, ensaio_row in df_filtrado.iterrows():
                todos_medidores.extend(processar_ensaio(ensaio_row))

            classe_banc20 = None
            if (bancada_selecionada == 'BANC_20_POS' or bancada_selecionada == 'Todas') and not df_filtrado[df_filtrado['Bancada'] == 'BANC_20_POS'].empty:
                st.sidebar.markdown("---")
                st.sidebar.subheader("⚙️ Config. Bancada 20")
                tipo_medidor = st.sidebar.radio("Tipo de Medidor", ["Eletrônico", "Eletromecânico"])
                if tipo_medidor == 'Eletromecânico': classe_banc20 = "ELETROMECANICO"
                else: classe_banc20 = st.sidebar.selectbox("Classe de Exatidão", ['A', 'B', 'C', 'D'], index=1)
            
            if classe_banc20:
                todos_medidores = [m for m in todos_medidores if m.get('bancada') != 'BANC_20_POS' or m.get('classe_exatidao') == classe_banc20]

            if status_filter:
                todos_medidores = [m for m in todos_medidores if m['status'] in status_filter]

        if todos_medidores:
            renderizar_resumo(calcular_estatisticas(todos_medidores))
            st.markdown("---")
            st.subheader("📋 Detalhes dos Medidores")
            num_colunas = 5
            for i in range(0, len(todos_medidores), num_colunas):
                cols = st.columns(num_colunas)
                for j, medidor in enumerate(todos_medidores[i:i + num_colunas]):
                    with cols[j]: renderizar_card(medidor)
                st.write("")
        else:
            st.info("Nenhum medidor encontrado.")

# -----------------------------------------------------------------------

# [BLOCO 07] - PÁGINA: VISÃO MENSAL (GRÁFICOS, TENDÊNCIAS E COMPARATIVO)
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
        
        daily_stats.append({
            'Data': data, 
            'Aprovados': aprovados, 
            'Reprovados': reprovados, 
            'Contra Consumidor': consumidor,
            'Total': total,
            'Taxa de Aprovação (%)': round(taxa_aprovacao, 1)
        })
    return pd.DataFrame(daily_stats)

def pagina_visao_mensal(df_completo):
    st.sidebar.header("📅 Filtros Mensais")
    anos = sorted(df_completo['Data_dt'].dt.year.unique(), reverse=True)
    meses_dict = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 
        7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    
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
        # Processamento Geral e por Bancada
        todos_medidores_mes = []
        stats_bancadas = []
        
        for bancada in df_mes['Bancada'].unique():
            df_banc = df_mes[df_mes['Bancada'] == bancada]
            medidores_banc = []
            for _, row in df_banc.iterrows():
                m_list = processar_ensaio(row, 'B')
                medidores_banc.extend(m_list)
                todos_medidores_mes.extend(m_list)
            
            aprov = sum(1 for m in medidores_banc if m['status'] == 'APROVADO')
            repro = sum(1 for m in medidores_banc if m['status'] == 'REPROVADO')
            cons = sum(1 for m in medidores_banc if m['status'] == 'CONTRA O CONSUMIDOR')
            stats_bancadas.append({'Bancada': bancada, 'Aprovados': aprov, 'Reprovados': repro, 'Contra Consumidor': cons})

        total_m = len(todos_medidores_mes)
        aprov_m = sum(1 for m in todos_medidores_mes if m['status'] == 'APROVADO')
        repro_m = sum(1 for m in todos_medidores_mes if m['status'] == 'REPROVADO')
        cons_m = sum(1 for m in todos_medidores_mes if m['status'] == 'CONTRA O CONSUMIDOR')
        taxa_m = (aprov_m / total_m * 100) if total_m > 0 else 0

        # Cards de Resumo Executivo
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Total Ensaiados", total_m)
        col_m2.metric("Taxa de Aprovação", f"{taxa_m:.1f}%", delta=f"{taxa_m-95:.1f}% vs Meta (95%)" if taxa_m > 0 else None)
        col_m3.metric("Total Reprovados", repro_m, delta=repro_m, delta_color="inverse")
        col_m4.metric("Contra Consumidor", cons_m, delta=cons_m, delta_color="inverse")

        st.markdown("---")

        # LINHA 1 DE GRÁFICOS: Distribuição e Tendência
        col_g1, col_g2 = st.columns([1, 1.5])
        with col_g1:
            df_pie = pd.DataFrame({'Status': ['Aprovados', 'Reprovados', 'Contra Consumidor'], 'Qtd': [aprov_m, repro_m, cons_m]})
            fig_donut = px.pie(df_pie, values='Qtd', names='Status', hole=.5, title='<b>Distribuição de Qualidade</b>',
                               color_discrete_map={'Aprovados':'#16a34a', 'Reprovados':'#dc2626', 'Contra Consumidor':'#7c3aed'})
            fig_donut.update_layout(showlegend=False, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_donut, use_container_width=True)

        with col_g2:
            df_daily = get_stats_por_dia(df_mes)
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(x=df_daily['Data'], y=df_daily['Aprovados'], name='Aprovados', marker_color='#16a34a'))
            fig_bar.add_trace(go.Bar(x=df_daily['Data'], y=df_daily['Reprovados'], name='Reprovados', marker_color='#dc2626'))
            fig_bar.update_layout(barmode='stack', title='<b>Evolução Diária</b>', legend=dict(orientation="h", y=1.1), margin=dict(t=80, b=40))
            st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")
        
        # LINHA 2 DE GRÁFICOS: COMPARATIVO DE BANCADAS
        st.subheader("📊 Comparativo de Performance por Bancada")
        df_comp = pd.DataFrame(stats_bancadas)
        
        col_comp1, col_comp2 = st.columns([1.5, 1])
        
        with col_comp1:
            # Gráfico de barras comparativo
            fig_comp = go.Figure()
            fig_comp.add_trace(go.Bar(x=df_comp['Bancada'], y=df_comp['Aprovados'], name='Aprovados', marker_color='#16a34a'))
            fig_comp.add_trace(go.Bar(x=df_comp['Bancada'], y=df_comp['Reprovados'], name='Reprovados', marker_color='#dc2626'))
            fig_comp.add_trace(go.Bar(x=df_comp['Bancada'], y=df_comp['Contra Consumidor'], name='Contra Consumidor', marker_color='#7c3aed'))
            fig_comp.update_layout(title='<b>Aprovados vs Reprovados por Bancada</b>', barmode='group')
            st.plotly_chart(fig_comp, use_container_width=True)
            
        with col_comp2:
            # Tabela de resumo por bancada
            st.markdown("  
  
", unsafe_allow_html=True)
            st.dataframe(df_comp, hide_index=True, use_container_width=True)

        with st.expander("📄 Visualizar Tabela de Performance Diária Completa"):
            st.dataframe(df_daily.sort_values('Data', ascending=False), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------

# [BLOCO 08] - INICIALIZAÇÃO E MENU PRINCIPAL
def main():
    st.title("📊 Dashboard de Ensaios")
    try:
        df_completo = carregar_dados()
        if not df_completo.empty:
            st.sidebar.title("Menu de Navegação")
            tipo_visao = st.sidebar.radio("Escolha a análise:", ('Visão Diária', 'Visão Mensal'))
            if tipo_visao == 'Visão Diária': pagina_visao_diaria(df_completo)
            else: pagina_visao_mensal(df_completo)
        else:
            st.error("Erro ao carregar dados. Verifique o arquivo Excel.")
    except Exception as e:
        st.error("Erro inesperado na aplicação.")
        st.code(traceback.format_exc())

if __name__ == "__main__":
    main()
