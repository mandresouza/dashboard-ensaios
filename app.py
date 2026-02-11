# =======================================================================
# ARQUIVO: app.py (VERSÃO FINAL E COMPLETA)
# =======================================================================

# [BLOCO 01] - IMPORTAÇÕES E CONFIGURAÇÕES INICIAIS
import streamlit as st
import pandas as pd
from datetime import datetime, date, timezone, timedelta
import plotly.express as px
import plotly.graph_objects as go
import traceback
import re
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

def to_excel(df):
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    processed_data = output.getvalue()
    return processed_data

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
        
        # --- LÓGICA COM NOVO TERMO TÉCNICO ---
        if pd.isna(cn) and pd.isna(cp) and pd.isna(ci):
            status, detalhe, motivo = "Não Ligou / Não Ensaido", "", "N/A"
            erros_pontuais = []
        else:
            status, detalhe, motivo = "APROVADO", "", "Nenhum"
            erros_pontuais = []
            
            v_cn, v_cp, v_ci = valor_num(cn), valor_num(cp), valor_num(ci)
            
            if v_cn is not None and abs(v_cn) > limite: erros_pontuais.append('CN')
            if v_cp is not None and abs(v_cp) > limite: erros_pontuais.append('CP')
            if v_ci is not None and abs(v_ci) > limite: erros_pontuais.append('CI')
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
                    
        medidores.append({
            "pos": pos, "serie": serie, "cn": texto(cn), "cp": texto(cp), "ci": texto(ci), 
            "mv": texto(row.get(f"P{pos}_MV")), "status": status, 
            "detalhe": detalhe, "motivo": motivo, "limite": limite,
            "erros_pontuais": erros_pontuais
        })
    return medidores
    
# [BLOCO 05] - COMPONENTES VISUAIS
def renderizar_card(medidor):
    status_cor = {"APROVADO": "#dcfce7", "REPROVADO": "#fee2e2", "CONTRA O CONSUMIDOR": "#ede9fe", "Não Ligou / Não Ensaido": "#e5e7eb"}
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
                <div style="padding:10px; margin-top: 16px; border-radius:8px; font-weight:800; font-size: 15px; text-align:center; background: rgba(0,0,0,0.08);">{medidor['status']}</div>
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

def renderizar_cabecalho_ensaio(n_ensaio, bancada, temperatura):
    st.markdown(f"""
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 10px 15px; border-radius: 10px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-weight: bold; font-size: 1.1em;">📋 Ensaio #{n_ensaio}</span>
        <span style="color: #475569;"><strong>Bancada:</strong> {bancada.replace('_', ' ')}</span>
        <span style="color: #475569;">🌡️ {temperatura}</span>
    </div>
    """, unsafe_allow_html=True)

def renderizar_grafico_reprovacoes(medidores):
    motivos = [m['motivo'] for m in medidores if m['status'] == 'REPROVADO']
    if not motivos: return
    
    contagem = {}
    for m in motivos:
        partes = [p.strip() for p in m.split('/')]
        for parte in partes:
            contagem[parte] = contagem.get(parte, 0) + 1
            
    df_motivos = pd.DataFrame(list(contagem.items()), columns=['Motivo', 'Quantidade']).sort_values('Quantidade', ascending=True)
    
    fig = px.bar(df_motivos, x='Quantidade', y='Motivo', orientation='h', title='<b>Principais Motivos de Reprovação</b>', text='Quantidade', color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(yaxis_title=None, xaxis_title="Número de Medidores", showlegend=False, margin=dict(l=10, r=10, t=40, b=10), height=250)
    fig.update_traces(textposition='outside')
    st.plotly_chart(fig, use_container_width=True)

def renderizar_botao_scroll_topo():
    scroll_button_html = """
        <style>
            #scrollTopBtn {
                display: none;
                position: fixed;
                bottom: 20px;
                right: 30px;
                z-index: 99;
                border: none;
                outline: none;
                background-color: #555;
                color: white;
                cursor: pointer;
                padding: 15px;
                border-radius: 10px;
                font-size: 18px;
                opacity: 0.7;
            }
            #scrollTopBtn:hover {
                background-color: #f44336;
                opacity: 1;
            }
        </style>
        
        <button onclick="topFunction()" id="scrollTopBtn" title="Voltar ao topo"><b>^</b></button>
        
        <script>
            var mybutton = document.getElementById("scrollTopBtn");
            window.onscroll = function() {scrollFunction()};
            function scrollFunction() {
                if (document.body.scrollTop > 100 || document.documentElement.scrollTop > 100) {
                    mybutton.style.display = "block";
                } else {
                    mybutton.style.display = "none";
                }
            }
            function topFunction() {
                document.body.scrollTop = 0;
                document.documentElement.scrollTop = 0;
            }
        </script>
    """
    st.components.v1.html(scroll_button_html, height=0)
    
# [BLOCO 06] - PÁGINA: VISÃO DIÁRIA
def pagina_visao_diaria(df_completo):
    # --- INÍCIO DO CÓDIGO DO BOTÃO "VOLTAR AO TOPO" ---
    st.markdown('''
        <style>
            .stApp {
                scroll-behavior: smooth;
            }
            #scroll-to-top {
                position: fixed;
                bottom: 20px;
                right: 30px;
                z-index: 99;
                border: none;
                outline: none;
                background-color: #555;
                color: white;
                cursor: pointer;
                padding: 15px;
                border-radius: 10px;
                font-size: 18px;
                opacity: 0.7;
            }
            #scroll-to-top:hover {
                background-color: #f44336;
                opacity: 1;
            }
        </style>
        <a id="top"></a>
        <a href="#top" id="scroll-to-top" title="Voltar ao topo"><b>^</b></a>
    ''', unsafe_allow_html=True)
    # --- FIM DO CÓDIGO DO BOTÃO "VOLTAR AO TOPO" ---

    st.sidebar.header("🔍 Busca e Filtros")
    
    # Lógica de busca por série
    if "search_key" not in st.session_state:
        st.session_state.search_key = 0
    serie_input = st.sidebar.text_input("Pesquisar Número de Série", value="", key=f"busca_{st.session_state.search_key}", help="Digite o número e pressione Enter")
    termo_busca = serie_input.strip().lower()

    if termo_busca:
        if st.sidebar.button("🗑️ Limpar Pesquisa"):
            st.session_state.search_key += 1
            st.rerun()

    if termo_busca:
        st.markdown(f"### 🔍 Histórico de Ensaios para a Série: **{serie_input}**")
        with st.spinner("Localizando medidor..."):
            resultados_encontrados = []
            for _, ensaio_row in df_completo.iterrows():
                colunas_serie = [c for c in ensaio_row.index if "_Série" in str(c)]
                if any(termo_busca in str(ensaio_row[col]).lower() for col in colunas_serie if pd.notna(ensaio_row[col])):
                    medidores_do_ensaio = processar_ensaio(ensaio_row)
                    for medidor in medidores_do_ensaio:
                        if termo_busca in medidor['serie'].lower():
                            resultados_encontrados.append({"data": ensaio_row['Data'], "bancada": ensaio_row['Bancada_Nome'], "dados": medidor})
            
            if resultados_encontrados:
                st.success(f"Encontrado(s) {len(resultados_encontrados)} registro(s) para este medidor.")
                st.markdown(f"""
                - **Primeiro Ensaio:** {resultados_encontrados[0]['data']}
                - **Último Ensaio:** {resultados_encontrados[-1]['data']}
                """)
                for res in sorted(resultados_encontrados, key=lambda x: datetime.strptime(x['data'], '%d/%m/%y'), reverse=True):
                    with st.expander(f"📍 **{res['data']}** | {res['bancada']} | Status: **{res['dados']['status']}**", expanded=False):
                        renderizar_card(res['dados'])
            else:
                st.warning(f"Nenhum registro encontrado para a série '{serie_input}'.")

    else:
        # Lógica de relatório por data
        if "filtro_data" not in st.session_state:
            data_hoje = datetime.now() - pd.Timedelta(hours=3)
            st.session_state.filtro_data = data_hoje.date()
        if "filtro_bancada" not in st.session_state:
            st.session_state.filtro_bancada = 'Todas'
        if "filtro_status" not in st.session_state:
            st.session_state.filtro_status = []
        if "filtro_irregularidade" not in st.session_state:
            st.session_state.filtro_irregularidade = []

        st.session_state.filtro_data = st.sidebar.date_input("Data do Ensaio", value=st.session_state.filtro_data, format="DD/MM/YYYY")
        bancadas_disponiveis = df_completo['Bancada_Nome'].unique().tolist()
        st.session_state.filtro_bancada = st.sidebar.selectbox("Bancada", options=['Todas'] + bancadas_disponiveis, index=0 if st.session_state.filtro_bancada == 'Todas' else bancadas_disponiveis.index(st.session_state.filtro_bancada) + 1)
        
        status_options = ["APROVADO", "REPROVADO", "CONTRA O CONSUMIDOR", "Não Ligou / Não Ensaido"]
        st.session_state.filtro_status = st.sidebar.multiselect("Filtrar Status", options=status_options, default=st.session_state.filtro_status)
        
        if "REPROVADO" in st.session_state.filtro_status:
            irregularidade_options = ["Exatidão", "Registrador", "Mostrador/MV"]
            st.session_state.filtro_irregularidade = st.sidebar.multiselect("Filtrar por Tipo de Irregularidade", options=irregularidade_options, default=st.session_state.filtro_irregularidade)
        else:
            st.session_state.filtro_irregularidade = []

        if not st.session_state.filtro_data:
            st.warning("Por favor, selecione uma data.")
            return
            
        st.markdown(f"### 📅 Relatório de Ensaios Realizados em: **{st.session_state.filtro_data.strftime('%d/%m/%Y')}**")
        
        df_filtrado_dia = df_completo[df_completo['Data_dt'].dt.date == st.session_state.filtro_data].copy()
        if st.session_state.filtro_bancada != 'Todas': 
            df_filtrado_dia = df_filtrado_dia[df_filtrado_dia['Bancada_Nome'] == st.session_state.filtro_bancada]

        if df_filtrado_dia.empty:
            st.info(f"Não constam ensaios registrados para o dia {st.session_state.filtro_data.strftime('%d/%m/%Y')}.")
            return

        ensaios_do_dia = []
        for _, ensaio_row in df_filtrado_dia.iterrows():
            medidores_processados = processar_ensaio(ensaio_row)
            
            medidores_filtrados = []
            for m in medidores_processados:
                status_ok = not st.session_state.filtro_status or m['status'] in st.session_state.filtro_status
                irregularidade_ok = not st.session_state.filtro_irregularidade or any(irr in m['motivo'] for irr in st.session_state.filtro_irregularidade)
                if status_ok and irregularidade_ok:
                    medidores_filtrados.append(m)
            
            if medidores_filtrados:
                ensaios_do_dia.append({
                    'n_ensaio': ensaio_row.get('N_ENSAIO', 'N/A'),
                    'bancada': ensaio_row['Bancada_Nome'],
                    'temperatura': ensaio_row.get('Temperatura', '--°C / --°C'),
                    'medidores': medidores_filtrados
                })

        if ensaios_do_dia:
            todos_medidores_visiveis = [medidor for ensaio in ensaios_do_dia for medidor in ensaio['medidores']]
            stats = calcular_estatisticas(todos_medidores_visiveis)
            renderizar_resumo(stats)
            
            col_exp, col_down = st.columns([3, 1])
            with col_exp:
                renderizar_grafico_reprovacoes(todos_medidores_visiveis)
            with col_down:
                st.write("")
                st.write("")
                pdf_bytes = gerar_pdf_relatorio(ensaios=ensaios_do_dia, data=st.session_state.filtro_data.strftime('%d/%m/%Y'), stats=stats)
                st.download_button(label="📥 Baixar Relatório PDF", data=pdf_bytes, file_name=f"Relatorio_{st.session_state.filtro_data.strftime('%Y%m%d')}.pdf", mime="application/pdf")
                
                df_export = pd.DataFrame(todos_medidores_visiveis)
                excel_bytes = to_excel(df_export)
                st.download_button(label="📥 Baixar Dados em Excel", data=excel_bytes, file_name=f"Dados_{st.session_state.filtro_data.strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            st.markdown("---")
            st.subheader("📋 Detalhes dos Ensaios")
            
            for ensaio in ensaios_do_dia:
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
        total_ensaiados = aprovados + reprovados + consumidor
        
        taxa_aprovacao = (aprovados / total_ensaiados * 100) if total_ensaiados > 0 else 0
        
        daily_stats.append({
            'Data': data, 
            'Aprovados': aprovados, 
            'Reprovados': reprovados, 
            'Contra Consumidor': consumidor,
            'Total': total_ensaiados,
            'Taxa de Aprovação (%)': round(taxa_aprovacao, 1)
        })
    return pd.DataFrame(daily_stats)

def pagina_visao_mensal(df_completo):
    # --- INÍCIO DO CÓDIGO DO BOTÃO "VOLTAR AO TOPO" ---
    st.markdown('''
        <style>
            .stApp {
                scroll-behavior: smooth;
            }
            #scroll-to-top {
                position: fixed;
                bottom: 20px;
                right: 30px;
                z-index: 99;
                border: none;
                outline: none;
                background-color: #555;
                color: white;
                cursor: pointer;
                padding: 15px;
                border-radius: 10px;
                font-size: 18px;
                opacity: 0.7;
            }
            #scroll-to-top:hover {
                background-color: #f44336;
                opacity: 1;
            }
        </style>
        <a id="top"></a>
        <a href="#top" id="scroll-to-top" title="Voltar ao topo"><b>^</b></a>
    ''', unsafe_allow_html=True)
    # --- FIM DO CÓDIGO DO BOTÃO "VOLTAR AO TOPO" ---

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
    # ===== MÉDIA DE TEMPERATURA DO MÊS =====
    temps = df_mes['Temperatura'].dropna().astype(str)
    
    valores_temp = []
    for t in temps:
        nums = re.findall(r"[-+]?\d*\.\d+|\d+", t)
        nums = [float(n) for n in nums]
        if nums:
            valores_temp.append(sum(nums) / len(nums))
    
    media_temp_mes = round(sum(valores_temp) / len(valores_temp), 1) if valores_temp else None
    
    if media_temp_mes is not None:
        st.markdown(
            f"""
            <div style="position:absolute; top:120px; right:40px;
                        background:#f1f5f9; padding:8px 12px;
                        border-radius:8px; font-size:14px;
                        color:#334155; border:1px solid #e2e8f0;">
                🌡️ <b>Temperatura média mensal:</b> {media_temp_mes} °C
            </div>
            """,
            unsafe_allow_html=True
        )
    
    if df_mes.empty:
        st.info(f"Nenhum dado encontrado para {meses_dict[mes_selecionado_num]} de {ano_selecionado}.")
        return
        
    with st.spinner("Processando indicadores mensais..."):
        todos_medidores_mes = []
        for _, row in df_mes.iterrows(): 
            todos_medidores_mes.extend(processar_ensaio(row, 'B'))
            
        aprov_m = sum(1 for m in todos_medidores_mes if m['status'] == 'APROVADO')
        repro_m = sum(1 for m in todos_medidores_mes if m['status'] == 'REPROVADO')
        cons_m = sum(1 for m in todos_medidores_mes if m['status'] == 'CONTRA O CONSUMIDOR')
        nao_ensaiados_m = sum(1 for m in todos_medidores_mes if m['status'] == 'Não Ligou / Não Ensaido')
        total_m = aprov_m + repro_m + cons_m
        taxa_m = (aprov_m / total_m * 100) if total_m > 0 else 0

        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
        col_m1.metric("Total Ensaiados", f"{total_m:,.0f}".replace(",", "."))
        col_m2.metric("Taxa de Aprovação", f"{taxa_m:.1f}%", delta=f"{taxa_m-95:.1f}% vs Meta (95%)" if taxa_m > 0 else None)
        col_m3.metric("Total Reprovados", f"{repro_m:,.0f}".replace(",", "."), delta=repro_m, delta_color="inverse")
        col_m4.metric("Contra Consumidor", f"{cons_m:,.0f}".replace(",", "."), delta=cons_m, delta_color="inverse")
        col_m5.metric("Não Ensaidos", f"{nao_ensaiados_m:,.0f}".replace(",", "."))

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
        
        st.markdown("---")
        st.subheader("Tendência da Taxa de Aprovação")
        if not df_daily.empty:
            fig_line = px.line(df_daily, x='Data', y='Taxa de Aprovação (%)', title='<b>Evolução da Taxa de Aprovação ao Longo do Mês</b>', markers=True, text='Taxa de Aprovação (%)')
            fig_line.update_traces(textposition="top center")
            fig_line.update_layout(yaxis=dict(range=[0, 110]), yaxis_title="Taxa de Aprovação (%)", xaxis_title="Dia do Mês")
            st.plotly_chart(fig_line, use_container_width=True)
            
        with st.expander("📄 Visualizar Tabela de Performance Diária"):
            st.dataframe(df_daily.sort_values('Data', ascending=False), use_container_width=True, hide_index=True)
            
# [BLOCO 08] - PÁGINA: ANÁLISE DE POSIÇÕES (MAPA DE CALOR)
def pagina_analise_posicoes(df_completo):
    # --- INÍCIO DO CÓDIGO DO BOTÃO "VOLTAR AO TOPO" ---
    st.markdown('''
        <style>
            .stApp {
                scroll-behavior: smooth;
            }
            #scroll-to-top {
                position: fixed;
                bottom: 20px;
                right: 30px;
                z-index: 99;
                border: none;
                outline: none;
                background-color: #555;
                color: white;
                cursor: pointer;
                padding: 15px;
                border-radius: 10px;
                font-size: 18px;
                opacity: 0.7;
            }
            #scroll-to-top:hover {
                background-color: #f44336;
                opacity: 1;
            }
        </style>
        <a id="top"></a>
        <a href="#top" id="scroll-to-top" title="Voltar ao topo"><b>^</b></a>
    ''', unsafe_allow_html=True)
    # --- FIM DO CÓDIGO DO BOTÃO "VOLTAR AO TOPO" ---

    st.markdown("## 🔥 Análise de Reprovação por Posição (Mapa de Calor)")
    st.info("Esta análise identifica quais posições e pontos de medição (CN, CP, CI) concentram o maior número de reprovações por exatidão.")
    st.markdown("""
    **Como ler o mapa:** Cada célula mostra o número total de reprovações para uma posição específica (linha) em um ponto de medição (coluna). A barra de cores à direita serve como legenda: quanto mais **vermelha e escura** a cor, **maior o número de reprovações**, indicando um ponto crítico que pode merecer investigação.
    """)

    st.sidebar.header("🔬 Filtros da Análise")
    
    bancadas_selecionadas = st.sidebar.multiselect(
        "Selecione a(s) Bancada(s)", 
        options=['BANC_10_POS', 'BANC_20_POS'],
        default=['BANC_10_POS', 'BANC_20_POS'],
        key='heatmap_bancadas'
    )
    
    min_date = df_completo['Data_dt'].min().date()
    max_date = df_completo['Data_dt'].max().date()
    
    data_inicio, data_fim = st.sidebar.date_input(
        "Selecione o Período",
        value=(max_date - pd.Timedelta(days=30), max_date),
        min_value=min_date,
        max_value=max_date,
        key='heatmap_periodo'
    )

    if not data_inicio or not data_fim or data_inicio > data_fim:
        st.warning("Por favor, selecione um período de datas válido.")
        return
        
    if not bancadas_selecionadas:
        st.warning("Por favor, selecione pelo menos uma bancada para a análise.")
        return

    for bancada in bancadas_selecionadas:
        st.markdown(f"---")
        st.markdown(f"### Análise para: **{bancada.replace('_', ' ')}**")

        with st.spinner(f"Processando dados para a {bancada.replace('_', ' ')}..."):
            df_filtrado = df_completo[
                (df_completo['Bancada_Nome'] == bancada) &
                (df_completo['Data_dt'].dt.date >= data_inicio) &
                (df_completo['Data_dt'].dt.date <= data_fim)
            ]

            if df_filtrado.empty:
                st.info(f"Nenhum dado encontrado para a {bancada.replace('_', ' ')} no período selecionado.")
                continue

            reprovacoes_detalhadas = []
            for _, row in df_filtrado.iterrows():
                medidores = processar_ensaio(row)
                for medidor in medidores:
                    if medidor['status'] == 'REPROVADO' and 'Exatidão' in medidor['motivo']:
                        for erro_tipo in medidor['erros_pontuais']:
                            reprovacoes_detalhadas.append({
                                'Data': row['Data'],
                                'Ensaio #': row.get('N_ENSAIO', 'N/A'),
                                'Posição': medidor['pos'],
                                'Série': medidor['serie'],
                                'Ponto do Erro': erro_tipo,
                                'Valor CN': medidor['cn'],
                                'Valor CP': medidor['cp'],
                                'Valor CI': medidor['ci']
                            })
            
            if not reprovacoes_detalhadas:
                st.success(f"🎉 Excelente! Nenhuma reprovação por exatidão encontrada na {bancada.replace('_', ' ')} para os filtros selecionados.")
                continue

            df_reprovacoes = pd.DataFrame(reprovacoes_detalhadas)
            
            heatmap_data = df_reprovacoes.pivot_table(index='Posição', columns='Ponto do Erro', aggfunc='size', fill_value=0)
            for ponto in ['CN', 'CP', 'CI']:
                if ponto not in heatmap_data.columns:
                    heatmap_data[ponto] = 0
            heatmap_data = heatmap_data[['CN', 'CP', 'CI']]

            fig = go.Figure(data=go.Heatmap(z=heatmap_data.values, x=heatmap_data.columns, y=[f"Posição {i}" for i in heatmap_data.index], colorscale='Reds', hoverongaps=False, text=heatmap_data.values, texttemplate="%{text}", showscale=True))
            fig.update_layout(title=f'<b>Mapa de Calor de Reprovações - {bancada.replace("_", " ")}</b>', xaxis_title="Ponto de Medição", yaxis_title="Posição na Bancada", yaxis=dict(autorange='reversed'), height=600)
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander(f"📄 Detalhes dos {len(df_reprovacoes)} Medidores Reprovados na {bancada.replace('_', ' ')} (Clique para expandir)"):
                st.dataframe(df_reprovacoes[['Data', 'Ensaio #', 'Posição', 'Série', 'Ponto do Erro', 'Valor CN', 'Valor CP', 'Valor CI']], use_container_width=True, hide_index=True)
                
                excel_bytes_reprovacoes = to_excel(df_reprovacoes)
                st.download_button(
                    label=f"📥 Baixar detalhes da {bancada.replace('_', ' ')} em Excel",
                    data=excel_bytes_reprovacoes,
                    file_name=f"Detalhes_Reprovacoes_{bancada}_{data_inicio.strftime('%Y%m%d')}-{data_fim.strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# =========================================================
# [BLOCO 09] - CONTROLE METROLÓGICO DAS BANCADAS
# =========================================================
# ⚠️ BLOCO ISOLADO
# - NÃO altera Visão Diária
# - NÃO altera Visão Mensal
# - NÃO altera Análise das Posições
# - Apenas adiciona uma nova aba conceitual
# =========================================================

def pagina_controle_metrologico_bancadas(df_completo):
    """
    Aba dedicada ao monitoramento metrológico das bancadas de ensaio.
    Este bloco é exclusivamente para análises de estabilidade, deriva
    e controle estatístico de processo (CEP).
    """

    st.markdown("## 🧪 Controle Metrológico das Bancadas")
    st.write("Prévia dos dados carregados:")
    st.dataframe(df_completo.head(5))
    st.markdown(
        """
        ### 📊 Objetivo da Análise

        Esta área tem como finalidade o **monitoramento preventivo da saúde metrológica**
        das bancadas de ensaio do laboratório, indo além do simples critério
        de aprovação ou reprovação de medidores.

        As análises aqui apresentadas permitem:
        - Identificar **deriva metrológica** das bancadas
        - Detectar **tendências positivas ou negativas** antes de reprovações
        - Subsidiar **calibração preventiva**
        - Aumentar a **segurança jurídica e técnica** dos resultados
        """
    )

    st.markdown(
        """
        ### 🔍 Escopo Técnico

        As análises serão baseadas em:
        - Número de série da bancada (rastreabilidade metrológica)
        - Erros de medição (CN, CP, CI)
        - Análise estatística ao longo do tempo
        - Cartas de Controle (Shewhart)
        """
    )

    st.info(
        "📈 Em implementação: Cartas de Controle por bancada (MQN) para análise de estabilidade e deriva."
    )

    st.warning(
        "⚠️ Esta aba é independente das análises operacionais e não interfere "
        "nos resultados de Visão Diária, Visão Mensal ou Análise das Posições."
    )

# [BLOCO 10] - INICIALIZAÇÃO E MENU PRINCIPAL
def main():
    try:
        df_completo = carregar_dados()
        if not df_completo.empty:
            # --- INÍCIO DA NOVA FUNCIONALIDADE ---
            # Cria duas colunas: uma para o título, outra para a data
            col_titulo, col_data = st.columns([3, 1])

            with col_titulo:
                st.title("📊 Dashboard de Ensaios")

            with col_data:
                # Encontra a data mais recente no DataFrame
                ultima_data = df_completo['Data_dt'].max()
                # Usa HTML para alinhar o texto à direita e estilizar
                st.markdown(
                    f"""
                    <div style="text-align: right; padding-top: 15px;">
                        <span style="font-size: 0.9em; color: #64748b;">Último ensaio: <strong>{ultima_data.strftime('%d/%m/%Y')}</strong></span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            # --- FIM DA NOVA FUNCIONALIDADE ---

            st.sidebar.title("Menu de Navegação")
            paginas = {
                'Visão Diária': pagina_visao_diaria,
                'Visão Mensal': pagina_visao_mensal,
                'Análise de Posições': pagina_analise_posicoes,
                'Controle Metrológico das Bancadas': pagina_controle_metrologico_bancadas
            }
            escolha = st.sidebar.radio("Escolha a análise:", tuple(paginas.keys()))
                        
            pagina_selecionada = paginas[escolha]
            pagina_selecionada(df_completo)
            
        else:
            st.error("Erro ao carregar dados. Verifique a conexão com o Google Sheets.")
    except Exception as e:
        st.error("Ocorreu um erro inesperado na aplicação.")
        st.code(traceback.format_exc())
        
# PONTO DE ENTRADA PRINCIPAL DO SCRIPT
if __name__ == "__main__":
    main()
