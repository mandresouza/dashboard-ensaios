# =======================================================================
# ARQUIVO app.py (VERSÃO FINAL E VITORIOSA - Inspirada por você)
# =======================================================================
import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import traceback
from google.oauth2.service_account import Credentials

# --- CONFIGURAÇÕES GLOBAIS ---
st.set_page_config(page_title="Dashboard de Ensaios", page_icon="📊", layout="wide")
LIMITES_CLASSE = {"A": 1.0, "B": 1.3, "C": 2.0, "D": 0.3}
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# --- FUNÇÃO DE CARREGAMENTO ROBUSTA (VERSÃO PANDAS) ---
@st.cache_data(ttl=600)
def carregar_dados():
    try:
        # Caminho direto para o arquivo, como no Colab
        caminho_arquivo = "/mount/src/dashboard-ensaios/BANCO_DADOS_GERAL.xlsx"
        
        # Usando o "rolo compressor" (pandas) para ler as abas
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
        st.error("ERRO CRÍTICO AO CARREGAR DADOS COM PANDAS:")
        st.error(f"Detalhes: {e}")
        st.code(traceback.format_exc())
        return pd.DataFrame()
    except Exception as e:
        st.error("ERRO CRÍTICO AO CARREGAR DADOS:")
        st.error(f"Detalhes: {e}")
        st.code(traceback.format_exc())
        return pd.DataFrame()

# --- FUNÇÕES DE PROCESSAMENTO E RENDERIZAÇÃO ---
def valor_num(v):
    try:
        if pd.isna(v): return None
        return float(str(v).replace("%", "").replace(",", "."))
    except (ValueError, TypeError): return None

def texto(v):
    if pd.isna(v) or v is None: return "-"
    return str(v)

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

def renderizar_card(medidor):
    status_cor = {"APROVADO": "#dcfce7", "REPROVADO": "#fee2e2", "CONTRA O CONSUMIDOR": "#ede9fe", "NÃO ENTROU": "#e5e7eb"}
    cor = status_cor.get(medidor['status'], "#f3f4f6")
    st.markdown(f"""<div style="background:{cor}; border-radius:12px; padding:16px; font-size:14px; box-shadow:0 2px 8px rgba(0,0,0,0.1); border-left: 6px solid rgba(0,0,0,0.1); display: flex; flex-direction: column; justify-content: space-between; height: 100%;"><div><div style="font-size:18px; font-weight:700; border-bottom:2px solid rgba(0,0,0,0.15); margin-bottom:12px; padding-bottom: 8px;">🔢 Posição {medidor['pos']}</div><p style="margin:0 0 12px 0;"><b>Série:</b> {medidor['serie']}</p><div style="background: rgba(0,0,0,0.05); padding: 10px; border-radius: 8px; margin-bottom:12px;"><b style="display: block; margin-bottom: 8px;">Exatidão (±{medidor['limite']}%)</b><div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px;"><span><b>CN:</b> {medidor['cn']}%</span><span><b>CP:</b> {medidor['cp']}%</span><span><b>CI:</b> {medidor['ci']}%</span><span><b>MV:</b> {medidor['mv']}</span></div></div><div style="background: rgba(0,0,0,0.05); padding: 10px; border-radius: 8px;"><b style="display: block; margin-bottom: 8px;">Registrador</b><div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px;"><span><b>Início:</b> {medidor['reg_ini']}</span><span><b>Fim:</b> {medidor['reg_fim']}</span><span style="grid-column: span 2;"><b>Erro:</b> {medidor['reg_err']}</span></div></div></div><div><div style="padding:10px; margin-top: 16px; border-radius:8px; font-weight:800; font-size: 15px; text-align:center; background: rgba(0,0,0,0.08);">{medidor['status'].replace('_', ' ')}</div><div style="margin-top:8px; font-size:12px; text-align:center;">{medidor['detalhe']}</div></div></div>""", unsafe_allow_html=True)

def renderizar_resumo(stats):
    st.markdown("""<style>.metric-card{background-color:#FFFFFF;padding:20px;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.05);text-align:center;}.metric-value{font-size:32px;font-weight:700;}.metric-label{font-size:16px;color:#64748b;}</style>""", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#1e293b;">{stats["total"]}</div><div class="metric-label">Total Ensaiados</div></div>', unsafe_allow_html=True)
    with col2: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#16a34a;">{stats["aprovados"]}</div><div class="metric-label">Aprovados</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#dc2626;">{stats["reprovados"]}</div><div class="metric-label">Reprovados</div></div>', unsafe_allow_html=True)
    with col4: st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#7c3aed;">{stats["consumidor"]}</div><div class="metric-label">Contra Consumidor</div></div>', unsafe_allow_html=True)

def pagina_visao_diaria(df_completo):
    st.sidebar.header("Filtros da Visão Diária")
    serie_filter = st.sidebar.text_input("Buscar por Número de Série")

    if serie_filter:
        st.markdown(f"### Buscando por série: **{serie_filter}**")
        with st.spinner("Buscando em todo o banco de dados..."):
            for _, ensaio_row in df_completo.iterrows():
                for i in range(1, 21):
                    serie_col = f'P{i}_Série'
                    if serie_col in ensaio_row and pd.notna(ensaio_row[serie_col]):
                        if serie_filter.strip().lower() in str(ensaio_row[serie_col]).lower():
                            medidores_processados = processar_ensaio(ensaio_row)
                            for medidor in medidores_processados:
                                if serie_filter.strip().lower() in medidor['serie'].lower():
                                    st.info(f"Medidor encontrado no ensaio de **{ensaio_row['Data']}** na bancada **{ensaio_row['Bancada']}**.")
                                    renderizar_card(medidor)
                                    st.stop()
            st.warning("Nenhum medidor encontrado com este número de série em todo o banco de dados.")
    else:
        data_selecionada_dt = st.sidebar.date_input("Selecione a Data", value=datetime.today(), format="DD/MM/YYYY")
        data_selecionada_str = data_selecionada_dt.strftime('%d/%m/%y')
        bancadas_disponiveis = df_completo['Bancada'].unique().tolist()
        bancada_selecionada = st.sidebar.selectbox("Selecione a Bancada", options=['Todas'] + bancadas_disponiveis)
        st.sidebar.markdown("---")
        status_filter = st.sidebar.multiselect("Filtrar por Status", options=["APROVADO", "REPROVADO", "CONTRA O CONSUMIDOR"], placeholder="Selecione um ou mais status")
        
        df_filtrado = df_completo[df_completo['Data'] == data_selecionada_str].copy()
        if bancada_selecionada != 'Todas': df_filtrado = df_filtrado[df_filtrado['Bancada'] == bancada_selecionada]
        
        st.markdown(f"### Relatório do dia: **{data_selecionada_str}**")
        if df_filtrado.empty:
            st.info(f"Nenhum ensaio encontrado para os filtros selecionados.")
            return

        with st.spinner("Processando ensaios... Por favor, aguarde."):
            todos_medidores = []
            classe_banc20 = None
            if not df_filtrado[df_filtrado['Bancada'] == 'BANC_20_POS'].empty:
                st.sidebar.markdown("---"); st.sidebar.subheader("⚙️ Config. Bancada 20")
                tipo_medidor = st.sidebar.radio("Tipo de Medidor", ["Eletrônico", "Eletromecânico"])
                if tipo_medidor == 'Eletromecânico': classe_banc20 = "ELETROMECANICO"
                else: classe_banc20 = st.sidebar.selectbox("Classe de Exatidão", ['A', 'B', 'C', 'D'], index=1)
            
            for _, ensaio_row in df_filtrado.iterrows():
                todos_medidores.extend(processar_ensaio(ensaio_row, classe_banc20))
            
            medidores_para_exibir = todos_medidores
            if status_filter: medidores_para_exibir = [m for m in medidores_para_exibir if m['status'] in status_filter]

        stats = {"aprovados": sum(1 for m in todos_medidores if m['status'] == 'APROVADO'), "reprovados": sum(1 for m in todos_medidores if m['status'] == 'REPROVADO'), "consumidor": sum(1 for m in todos_medidores if m['status'] == 'CONTRA O CONSUMIDOR'), "total": sum(1 for m in todos_medidores if m['status'] != 'NÃO ENTROU')}
        renderizar_resumo(stats)
        
        st.markdown("---")
        st.subheader("Detalhes dos Medidores")
        if not medidores_para_exibir:
            st.warning("Nenhum medidor encontrado com os filtros de status aplicados.")
        else:
            num_colunas = 5
            # Agrupa os medidores em "linhas" de 5
            linhas_de_medidores = [medidores_para_exibir[i:i + num_colunas] for i in range(0, len(medidores_para_exibir), num_colunas)]

            # Itera sobre cada linha de medidores
            for linha in linhas_de_medidores:
                # Cria um novo conjunto de colunas para ESTA linha
                cols = st.columns(num_colunas)
                # Preenche as colunas com os cards desta linha
                for i, medidor in enumerate(linha):
                    with cols[i]:
                        renderizar_card(medidor)
                
def pagina_visao_mensal(df_completo):
    st.sidebar.header("Filtros da Visão Mensal")
    anos = sorted(df_completo['Data_dt'].dt.year.unique(), reverse=True)
    meses = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
    ano_selecionado = st.sidebar.selectbox("Selecione o Ano", anos)
    mes_selecionado_num = st.sidebar.selectbox("Selecione o Mês", options=list(meses.keys()), format_func=lambda x: meses[x])
    df_mes = df_completo[(df_completo['Data_dt'].dt.year == ano_selecionado) & (df_completo['Data_dt'].dt.month == mes_selecionado_num)]
    st.markdown(f"### Análise Consolidada de **{meses[mes_selecionado_num]} de {ano_selecionado}**")
    if df_mes.empty:
        st.info("Nenhum dado encontrado para este mês/ano.")
        return
    with st.spinner("Gerando gráficos mensais..."):
        todos_medidores_mes = []
        for _, row in df_mes.iterrows(): todos_medidores_mes.extend(processar_ensaio(row, 'B'))
        stats_mes = {"Aprovados": sum(1 for m in todos_medidores_mes if m['status'] == 'APROVADO'), "Reprovados": sum(1 for m in todos_medidores_mes if m['status'] == 'REPROVADO'), "Contra o Consumidor": sum(1 for m in todos_medidores_mes if m['status'] == 'CONTRA O CONSUMIDOR')}
        df_pie = pd.DataFrame(list(stats_mes.items()), columns=['Status', 'Quantidade'])
        fig_pie = px.pie(df_pie, values='Quantidade', names='Status', title='Consolidado do Mês', color_discrete_map={'Aprovados':'#16a34a', 'Reprovados':'#dc2626', 'Contra o Consumidor':'#7c3aed'})
        df_daily = get_stats_por_dia(df_mes)
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(x=df_daily['Data'], y=df_daily['Aprovados'], mode='lines+markers', name='Aprovados', line=dict(color='#16a34a')))
        fig_line.add_trace(go.Scatter(x=df_daily['Data'], y=df_daily['Reprovados'], mode='lines+markers', name='Reprovados', line=dict(color='#dc2626')))
        fig_line.update_layout(title='Evolução Diária de Aprovados vs. Reprovados', xaxis_title='Dia', yaxis_title='Quantidade')
        col1, col2 = st.columns([1, 2])
        with col1: st.plotly_chart(fig_pie, use_container_width=True)
        with col2: st.plotly_chart(fig_line, use_container_width=True)

# --- LÓGICA PRINCIPAL DE EXECUÇÃO ---
def main():
    st.title("📊 Dashboard de Ensaios")
    try:
        df_completo = carregar_dados()
        if not df_completo.empty:
            st.success("Dados carregados com sucesso!")
            st.sidebar.title("Menu de Navegação")
            tipo_visao = st.sidebar.radio("Escolha o tipo de análise:", ('Visão Diária', 'Visão Mensal'))
            if tipo_visao == 'Visão Diária':
                pagina_visao_diaria(df_completo)
            else:
                pagina_visao_mensal(df_completo)
        else:
            st.error("Não foi possível carregar os dados. Verifique a mensagem de erro acima.")
    except Exception as e:
        st.error("Um erro inesperado ocorreu na aplicação principal.")
        st.code(traceback.format_exc())

if __name__ == "__main__":
    main()
