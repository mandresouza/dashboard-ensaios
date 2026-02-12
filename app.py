# =======================================================================
# ARQUIVO: app.py (VERSÃO FINAL E COMPLETA COM BLOCO DE METROLOGIA)
# =======================================================================

# =========================================================
# [BLOCO 01] - IMPORTAÇÕES E CONFIGURAÇÕES INICIAIS
# =========================================================

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timezone, timedelta
import plotly.express as px
import plotly.graph_objects as go
import traceback
import re
import os
from io import BytesIO

# Tenta importar o gerador de PDF original
try:
    from pdf_generator import gerar_pdf_relatorio
except ImportError:
    def gerar_pdf_relatorio(*args, **kwargs):
        return None

st.set_page_config(
    page_title="Dashboard de Ensaios",
    page_icon="📊",
    layout="wide"
)

# --- CONFIGURAÇÕES E CONSTANTES ORIGINAIS ---
LIMITES_CLASSE = {
    "A": 1.0,
    "B": 1.3,
    "C": 2.0,
    "D": 0.3
}

# =======================================================================
# [BLOCO ISOLADO] - METROLOGIA AVANÇADA (VERSÃO FINAL DE ALTA PRECISÃO)
# =======================================================================

MAPA_BANCADA_SERIE = {
    'BANC_10_POS_MQN-1': 'B1172110310148',
    'BANC_20_POS_MQN-2': '85159',
    'BANC_20_POS_MQN-3': '93959',
    'BANC_3_MQN-4': '96850'
}


def valor_num_metrologia(v):
    """Converte valores tratando vírgulas e escala decimal de forma robusta."""
    try:
        if pd.isna(v) or str(v).strip() in ["", "-", "None"]:
            return None

        s = str(v).replace("%", "").replace(" ", "").replace(",", ".").strip()
        val = float(s)

        if abs(val) > 100:
            val = val / 1000  # Correção de escala (ex: 49986 -> 49.986)

        return val
    except:
        return None


@st.cache_data(ttl=600)
def carregar_tabela_mestra_sheets():
    sheet_id = "1kcN5lUZ14hwFyQMdrsFbMxjpALI4x6yd2AMCMq_who8"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"

    try:
        df = pd.read_csv(url)

        df['Erro_Sistematico_Pct'] = df['Erro_Sistematico_Pct'].apply(valor_num_metrologia)

        if 'Incerteza_U_Pct' in df.columns:
            df['Incerteza_U_Pct'] = df['Incerteza_U_Pct'].apply(valor_num_metrologia)

        return df.groupby(['Serie_Bancada', 'Posicao']).agg({
            'Erro_Sistematico_Pct': 'mean',
            'Incerteza_U_Pct': 'mean' if 'Incerteza_U_Pct' in df.columns else 'first'
        }).reset_index()

    except:
        return None


def processar_metrologia_isolada(row, df_mestra=None, classe_banc20=None):
    medidores = []
    bancada_row = str(row.get('Bancada_Nome', ''))
    n_ensaio = row.get('N_ENSAIO', 'N/A')

    serie_bancada = next(
        (v for k, v in MAPA_BANCADA_SERIE.items() if k in bancada_row),
        None
    )

    tamanho_bancada = 20 if '20_POS' in bancada_row else 10
    classe = str(row.get("Classe", "")).upper()

    limite = 4.0 if "ELETROMEC" in (classe or 'B') else LIMITES_CLASSE.get(
        str(classe or 'B').replace("ELETROMEC", "").strip(),
        1.3
    )

    for pos in range(1, tamanho_bancada + 1):

        serie = texto(row.get(f"P{pos}_Série"))
        v_cn = valor_num_metrologia(row.get(f"P{pos}_CN"))
        v_cp = valor_num_metrologia(row.get(f"P{pos}_CP"))
        v_ci = valor_num_metrologia(row.get(f"P{pos}_CI"))

        erro_ref, inc_banc = 0.0, 0.05

        if df_mestra is not None and serie_bancada:
            ref_row = df_mestra[
                (df_mestra['Serie_Bancada'].astype(str) == str(serie_bancada)) &
                (df_mestra['Posicao'] == pos)
            ]

            if not ref_row.empty:
                erro_ref = ref_row['Erro_Sistematico_Pct'].values[0] or 0.0
                inc_banc = ref_row['Incerteza_U_Pct'].values[0] \
                    if 'Incerteza_U_Pct' in ref_row.columns else 0.05

        if v_cn is None and v_cp is None and v_ci is None:
            status, detalhe = "Não Ligou / Não Ensaido", ""
        else:
            status, detalhe = "APROVADO", ""

            erros_p = []
            alertas_gb = []

            for n, v in [('CN', v_cn), ('CP', v_cp), ('CI', v_ci)]:
                if v is not None:
                    if abs(v) > limite:
                        erros_p.append(n)
                    elif (abs(v) + inc_banc) > limite:
                        alertas_gb.append(n)

            if erros_p:
                status, detalhe = "REPROVADO", "⚠️ Erro de Exatidão"
            elif alertas_gb:
                status, detalhe = "ZONA CRÍTICA", f"⚠️ Guardband: {', '.join(alertas_gb)}"

        medidores.append({
            "n_ensaio": n_ensaio,
            "pos": pos,
            "serie": serie,
            "cn": v_cn,
            "cp": v_cp,
            "ci": v_ci,
            "status": status,
            "detalhe": detalhe,
            "erro_ref": erro_ref,
            "inc_banc": inc_banc
        })

    return medidores
# =======================================================================
# [BLOCO 04] - PROCESSAMENTO TÉCNICO (CORRIGIDO - REGRA MV REAL)
# =======================================================================

def processar_ensaio(row, classe_banc20=None):

    medidores = []
    bancada = row.get('Bancada_Nome')
    tamanho_bancada = 20 if bancada == 'BANC_20_POS' else 10

    classe = str(row.get("Classe", "")).upper()

    if not classe and bancada == 'BANC_20_POS' and classe_banc20:
        classe = classe_banc20

    if not classe:
        classe = 'B'

    limite = 4.0 if "ELETROMEC" in classe else LIMITES_CLASSE.get(
        classe.replace("ELETROMEC", "").strip(),
        1.3
    )

    for pos in range(1, tamanho_bancada + 1):

        serie = texto(row.get(f"P{pos}_Série"))
        cn = row.get(f"P{pos}_CN")
        cp = row.get(f"P{pos}_CP")
        ci = row.get(f"P{pos}_CI")

        if pd.isna(cn) and pd.isna(cp) and pd.isna(ci):
            status = "Não Ligou / Não Ensaido"
            detalhe = ""
            motivo = "N/A"
            erros_pontuais = []

        else:
            status = "APROVADO"
            detalhe = ""
            motivo = "Nenhum"
            erros_pontuais = []

            v_cn = valor_num(cn)
            v_cp = valor_num(cp)
            v_ci = valor_num(ci)

            if v_cn is not None and abs(v_cn) > limite:
                erros_pontuais.append('CN')

            if v_cp is not None and abs(v_cp) > limite:
                erros_pontuais.append('CP')

            if v_ci is not None and abs(v_ci) > limite:
                erros_pontuais.append('CI')

            erro_exatidao = len(erros_pontuais) > 0

            reg_ini = valor_num(row.get(f"P{pos}_REG_Inicio"))
            reg_fim = valor_num(row.get(f"P{pos}_REG_Fim"))

            if reg_ini is not None and reg_fim is not None:
                reg_err = reg_fim - reg_ini
                erro_registrador = (reg_err != 1)
                incremento_maior = (reg_err > 1)
            else:
                erro_registrador = False
                incremento_maior = False

            # ================= REGRA REAL MV =================
            mv = str(texto(row.get(f"P{pos}_MV"))).strip().upper()

            if bancada == 'BANC_10_POS':
                mv_reprovado = (mv != "+")
            else:
                mv_reprovado = (mv != "OK")
            # =================================================

            pontos_contra = sum([
                sum(1 for v in [v_cn, v_cp, v_ci]
                    if v is not None and v > 0 and abs(v) > limite) >= 1,
                mv_reprovado,
                incremento_maior
            ])

            if pontos_contra >= 2:
                status = "CONTRA O CONSUMIDOR"
                detalhe = "⚠️ Medição a mais"
                motivo = "Contra Consumidor"

            elif erro_exatidao or erro_registrador or mv_reprovado:
                status = "REPROVADO"
                m_list = []

                if erro_exatidao:
                    m_list.append("Exatidão")

                if erro_registrador:
                    m_list.append("Registrador")

                if mv_reprovado:
                    m_list.append("Mostrador/MV")

                motivo = " / ".join(m_list)
                detalhe = "⚠️ Verifique este medidor"

        medidores.append({
            "pos": pos,
            "serie": serie,
            "cn": texto(cn),
            "cp": texto(cp),
            "ci": texto(ci),
            "mv": texto(row.get(f"P{pos}_MV")),
            "status": status,
            "detalhe": detalhe,
            "motivo": motivo,
            "limite": limite,
            "erros_pontuais": erros_pontuais
        })

    return medidores

# =======================================================================
# [BLOCO 04B] - CÁLCULO DA AUDITORIA REAL (SEM EXIBIÇÃO VISUAL)
# =======================================================================

def calcular_auditoria_real(df_filtrado):

    total_posicoes = 0
    total_ensaiadas = 0
    total_aprovadas = 0
    total_reprovadas = 0
    total_nao_ensaiadas = 0

    reprov_exatidao = 0
    reprov_registrador = 0
    reprov_mv = 0
    reprov_consumidor = 0

    for _, row in df_filtrado.iterrows():

        medidores = processar_ensaio(row)

        for m in medidores:

            total_posicoes += 1

            tem_resultado = any([
                m["cn"] not in [None, "", "None"],
                m["cp"] not in [None, "", "None"],
                m["ci"] not in [None, "", "None"]
            ])

            if not tem_resultado:
                total_nao_ensaiadas += 1
                continue

            total_ensaiadas += 1

            if m["status"] == "APROVADO":
                total_aprovadas += 1
            else:
                total_reprovadas += 1

            motivo = str(m.get("motivo", "")).upper()

            if "EXATID" in motivo:
                reprov_exatidao += 1

            if "REGISTRADOR" in motivo:
                reprov_registrador += 1

            if "MOSTRADOR" in motivo or "MV" in motivo:
                reprov_mv += 1

            if "CONTRA" in motivo:
                reprov_consumidor += 1

    taxa_aprov = (total_aprovadas / total_ensaiadas * 100) if total_ensaiadas else 0

    return {
        "total_posicoes": total_posicoes,
        "total_ensaiadas": total_ensaiadas,
        "total_aprovadas": total_aprovadas,
        "total_reprovadas": total_reprovadas,
        "total_nao_ensaiadas": total_nao_ensaiadas,
        "taxa_aprovacao": taxa_aprov,
        "reprov_exatidao": reprov_exatidao,
        "reprov_registrador": reprov_registrador,
        "reprov_mv": reprov_mv,
        "reprov_consumidor": reprov_consumidor
    }

# [BLOCO 05] - COMPONENTES VISUAIS (ORIGINAL)

def renderizar_card(medidor):

    status_cor = {
        "APROVADO": "#dcfce7",
        "REPROVADO": "#fee2e2",
        "CONTRA O CONSUMIDOR": "#ede9fe",
        "Não Ligou / Não Ensaido": "#e5e7eb"
    }

    cor = status_cor.get(medidor['status'], "#f3f4f6")

    st.markdown(f"""
    <div style="background:{cor}; border-radius:12px; padding:16px; font-size:14px;
    box-shadow:0 2px 8px rgba(0,0,0,0.1); border-left: 6px solid rgba(0,0,0,0.1);
    display: flex; flex-direction: column; justify-content: space-between; height: 100%;">

        <div>
            <div style="font-size:18px; font-weight:700; border-bottom:2px solid rgba(0,0,0,0.15);
            margin-bottom:12px; padding-bottom: 8px;">
                🔢 Posição {medidor['pos']}
            </div>

            <p style="margin:0 0 12px 0;"><b>Série:</b> {medidor['serie']}</p>

            <div style="background: rgba(0,0,0,0.05); padding: 10px; border-radius: 8px; margin-bottom:12px;">
                <b style="display: block; margin-bottom: 8px;">
                    Exatidão (±{medidor['limite']}%)
                </b>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px;">
                    <span><b>CN:</b> {medidor['cn']}%</span>
                    <span><b>CP:</b> {medidor['cp']}%</span>
                    <span><b>CI:</b> {medidor['ci']}%</span>
                    <span><b>MV:</b> {medidor['mv']}</span>
                </div>
            </div>
        </div>

        <div>
            <div style="padding:10px; margin-top: 16px; border-radius:8px;
            font-weight:800; font-size: 15px; text-align:center;
            background: rgba(0,0,0,0.08);">
                {medidor['status']}
            </div>

            <div style="margin-top:8px; font-size:12px; text-align:center;">
                {medidor['detalhe']}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# =========================================================
# [BLOCO 06] - PÁGINA: VISÃO DIÁRIA (RESTAURADO - SEM AUDITORIA)
# =========================================================

def pagina_visao_diaria(df_completo):

    # --- BOTÃO VOLTAR AO TOPO ---
    st.markdown('''
        <style>
        .stApp { scroll-behavior: smooth; }
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
        <a href="#top" id="scroll-to-top"><b>^</b></a>
    ''', unsafe_allow_html=True)

    st.sidebar.header("🔍 Busca e Filtros")

    # =====================================================
    # BUSCA POR SÉRIE
    # =====================================================

    if "search_key" not in st.session_state:
        st.session_state.search_key = 0

    serie_input = st.sidebar.text_input(
        "Pesquisar Número de Série",
        value="",
        key=f"busca_{st.session_state.search_key}"
    )

    termo_busca = serie_input.strip().lower()

    if termo_busca:
        if st.sidebar.button("🗑️ Limpar Pesquisa"):
            st.session_state.search_key += 1
            st.rerun()

    if termo_busca:

        st.markdown(f"### 🔍 Histórico de Ensaios para a Série: **{serie_input}**")

        resultados = []

        for _, ensaio_row in df_completo.iterrows():

            colunas_serie = [c for c in ensaio_row.index if "_Série" in str(c)]

            if any(
                termo_busca in str(ensaio_row[col]).lower()
                for col in colunas_serie
                if pd.notna(ensaio_row[col])
            ):

                medidores = processar_ensaio(ensaio_row)

                for m in medidores:
                    if termo_busca in m['serie'].lower():
                        resultados.append({
                            "data": ensaio_row['Data'],
                            "bancada": ensaio_row['Bancada_Nome'],
                            "dados": m
                        })

        if resultados:

            st.success(f"{len(resultados)} registro(s) encontrado(s).")

            for res in sorted(
                resultados,
                key=lambda x: datetime.strptime(x['data'], '%d/%m/%y'),
                reverse=True
            ):
                with st.expander(
                    f"{res['data']} | {res['bancada']} | {res['dados']['status']}"
                ):
                    renderizar_card(res['dados'])

        else:
            st.warning("Nenhum registro encontrado.")

        return

    # =====================================================
    # FILTROS DO DIA
    # =====================================================

    if "filtro_data" not in st.session_state:
        st.session_state.filtro_data = (datetime.now() - pd.Timedelta(hours=3)).date()

    if "filtro_bancada" not in st.session_state:
        st.session_state.filtro_bancada = "Todas"

    if "filtro_status" not in st.session_state:
        st.session_state.filtro_status = []

    if "filtro_irregularidade" not in st.session_state:
        st.session_state.filtro_irregularidade = []

    st.session_state.filtro_data = st.sidebar.date_input(
        "Data do Ensaio",
        value=st.session_state.filtro_data,
        format="DD/MM/YYYY"
    )

    bancadas = df_completo['Bancada_Nome'].unique().tolist()

    st.session_state.filtro_bancada = st.sidebar.selectbox(
        "Bancada",
        ['Todas'] + bancadas
    )

    status_options = [
        "APROVADO",
        "REPROVADO",
        "CONTRA O CONSUMIDOR",
        "Não Ligou / Não Ensaido"
    ]

    st.session_state.filtro_status = st.sidebar.multiselect(
        "Filtrar Status",
        status_options,
        default=st.session_state.filtro_status
    )

    if "REPROVADO" in st.session_state.filtro_status:
        st.session_state.filtro_irregularidade = st.sidebar.multiselect(
            "Filtrar Irregularidade",
            ["Exatidão", "Registrador", "Mostrador/MV"],
            default=st.session_state.filtro_irregularidade
        )
    else:
        st.session_state.filtro_irregularidade = []

    # =====================================================
    # FILTRA DATA
    # =====================================================

    df_filtrado = df_completo[
        df_completo['Data_dt'].dt.date == st.session_state.filtro_data
    ]

    if st.session_state.filtro_bancada != "Todas":
        df_filtrado = df_filtrado[
            df_filtrado['Bancada_Nome'] == st.session_state.filtro_bancada
        ]

    if df_filtrado.empty:
        st.info("Nenhum ensaio neste dia.")
        return

    # =====================================================
    # PROCESSA MEDIDORES
    # =====================================================

    ensaios = []

    for _, row in df_filtrado.iterrows():

        medidores = processar_ensaio(row)
        medidores_filtrados = []

        for m in medidores:

            status_ok = (
                not st.session_state.filtro_status
                or m['status'] in st.session_state.filtro_status
            )

            irr_ok = (
                not st.session_state.filtro_irregularidade
                or any(i in m['motivo']
                       for i in st.session_state.filtro_irregularidade)
            )

            if status_ok and irr_ok:
                medidores_filtrados.append(m)

        if medidores_filtrados:
            ensaios.append({
                "n_ensaio": row.get("N_ENSAIO", "N/A"),
                "bancada": row["Bancada_Nome"],
                "temperatura": row.get("Temperatura", "--"),
                "medidores": medidores_filtrados
            })

    if not ensaios:
        st.info("Nenhum medidor para os filtros.")
        return

    todos = [m for e in ensaios for m in e["medidores"]]

    # =====================================================
    # RESUMO
    # =====================================================

    stats = calcular_estatisticas(todos)
    renderizar_resumo(stats)

    # =====================================================
    # GRÁFICOS E EXPORTAÇÃO
    # =====================================================

    col1, col2 = st.columns([3, 1])

    with col1:
        renderizar_grafico_reprovacoes(todos)

    with col2:
        pdf_bytes = gerar_pdf_relatorio(
            ensaios=ensaios,
            data=st.session_state.filtro_data.strftime('%d/%m/%Y'),
            stats=stats
        )
        st.download_button("📥 PDF", pdf_bytes, file_name="relatorio.pdf")

        df_export = pd.DataFrame(todos)
        excel_bytes = to_excel(df_export)
        st.download_button("📥 Excel", excel_bytes, file_name="dados.xlsx")

    # =====================================================
    # DETALHES
    # =====================================================

    st.markdown("---")
    st.subheader("📋 Detalhes dos Ensaios")

    for ensaio in ensaios:

        renderizar_cabecalho_ensaio(
            ensaio["n_ensaio"],
            ensaio["bancada"],
            ensaio["temperatura"]
        )

        cols_n = 5

        for i in range(0, len(ensaio["medidores"]), cols_n):

            cols = st.columns(cols_n)

            for j, m in enumerate(ensaio["medidores"][i:i+cols_n]):
                with cols[j]:
                    renderizar_card(m)

# =========================================================
# [BLOCO 07] - PÁGINA: VISÃO MENSAL
# =========================================================

def pagina_visao_mensal(df_completo):

    st.title("📅 Visão Mensal")

    if df_completo.empty:
        st.warning("Sem dados disponíveis.")
        return

    # =====================================================
    # FILTRO MÊS / ANO
    # =====================================================

    df_completo["Ano"] = df_completo["Data_dt"].dt.year
    df_completo["Mes"] = df_completo["Data_dt"].dt.month

    anos_disponiveis = sorted(df_completo["Ano"].unique())
    meses_disponiveis = list(range(1, 13))

    col1, col2 = st.columns(2)

    with col1:
        ano_selecionado = st.selectbox("Ano", anos_disponiveis)

    with col2:
        mes_selecionado = st.selectbox("Mês", meses_disponiveis, format_func=lambda x: datetime(1900, x, 1).strftime('%B'))

    df_filtrado = df_completo[
        (df_completo["Ano"] == ano_selecionado) &
        (df_completo["Mes"] == mes_selecionado)
    ]

    if df_filtrado.empty:
        st.info("Nenhum ensaio encontrado para este período.")
        return

    # =====================================================
    # PROCESSAMENTO DOS MEDIDORES
    # =====================================================

    todos_medidores = []

    for _, row in df_filtrado.iterrows():
        medidores = processar_ensaio(row)
        todos_medidores.extend(medidores)

    if not todos_medidores:
        st.info("Nenhum medidor processado.")
        return

    # =====================================================
    # RESUMO MENSAL
    # =====================================================

    stats = calcular_estatisticas(todos_medidores)
    renderizar_resumo(stats)

    st.markdown("---")

    # =====================================================
    # GRÁFICO MENSAL
    # =====================================================

    renderizar_grafico_reprovacoes(todos_medidores)

    st.markdown("---")

    # =====================================================
    # TABELA CONSOLIDADA
    # =====================================================

    df_export = pd.DataFrame(todos_medidores)

    st.subheader("📋 Dados Consolidados")

    st.dataframe(df_export, use_container_width=True)

    # =====================================================
    # EXPORTAÇÃO
    # =====================================================

    col_pdf, col_excel = st.columns(2)

    with col_pdf:
        pdf_bytes = gerar_pdf_relatorio(
            ensaios=[{
                "n_ensaio": "MENSAL",
                "bancada": "Consolidado",
                "temperatura": "--",
                "medidores": todos_medidores
            }],
            data=f"{mes_selecionado}/{ano_selecionado}",
            stats=stats
        )
        st.download_button(
            "📥 Exportar PDF Mensal",
            pdf_bytes,
            file_name="relatorio_mensal.pdf"
        )

    with col_excel:
        excel_bytes = to_excel(df_export)
        st.download_button(
            "📥 Exportar Excel Mensal",
            excel_bytes,
            file_name="dados_mensal.xlsx"
        )

# =========================================================
# [BLOCO 08] - PÁGINA: ANÁLISE DE POSIÇÕES (ORIGINAL)
# =========================================================

def pagina_analise_posicoes(df_completo):

    # =====================================================
    # BOTÃO VOLTAR AO TOPO
    # =====================================================

    st.markdown('''
        <style>
        .stApp { scroll-behavior: smooth; }

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

    # =====================================================
    # TÍTULO
    # =====================================================

    st.markdown("## 🔥 Análise de Reprovação por Posição (Mapa de Calor)")
    st.info(
        "Esta análise identifica quais posições e pontos de medição "
        "(CN, CP, CI) concentram o maior número de reprovações por exatidão."
    )

    # =====================================================
    # FILTROS
    # =====================================================

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

    # =====================================================
    # PROCESSAMENTO POR BANCADA
    # =====================================================

    for bancada in bancadas_selecionadas:

        st.markdown("---")
        st.markdown(f"### Análise para: **{bancada.replace('_', ' ')}**")

        with st.spinner(f"Processando dados para a {bancada.replace('_', ' ')}..."):

            df_filtrado = df_completo[
                (df_completo['Bancada_Nome'] == bancada) &
                (df_completo['Data_dt'].dt.date >= data_inicio) &
                (df_completo['Data_dt'].dt.date <= data_fim)
            ]

            if df_filtrado.empty:
                st.info(
                    f"Nenhum dado encontrado para a "
                    f"{bancada.replace('_', ' ')} no período selecionado."
                )
                continue

            reprovacoes_detalhadas = []

            for _, row in df_filtrado.iterrows():

                medidores = processar_ensaio(row)

                for medidor in medidores:

                    if (
                        medidor['status'] == 'REPROVADO'
                        and 'Exatidão' in medidor['motivo']
                    ):

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
                st.success(
                    f"🎉 Excelente! Nenhuma reprovação por exatidão "
                    f"encontrada na {bancada.replace('_', ' ')} "
                    f"para os filtros selecionados."
                )
                continue

            # =====================================================
            # DATAFRAME
            # =====================================================

            df_reprovacoes = pd.DataFrame(reprovacoes_detalhadas)

            # =====================================================
            # HEATMAP
            # =====================================================

            heatmap_data = df_reprovacoes.pivot_table(
                index='Posição',
                columns='Ponto do Erro',
                aggfunc='size',
                fill_value=0
            )

            for ponto in ['CN', 'CP', 'CI']:
                if ponto not in heatmap_data.columns:
                    heatmap_data[ponto] = 0

            heatmap_data = heatmap_data[['CN', 'CP', 'CI']]

            fig = go.Figure(
                data=go.Heatmap(
                    z=heatmap_data.values,
                    x=heatmap_data.columns,
                    y=[f"Posição {i}" for i in heatmap_data.index],
                    colorscale='Reds',
                    hoverongaps=False,
                    text=heatmap_data.values,
                    texttemplate="%{text}",
                    showscale=True
                )
            )

            fig.update_layout(
                title=f'<b>Mapa de Calor de Reprovações - {bancada.replace("_", " ")}</b>',
                xaxis_title="Ponto de Medição",
                yaxis_title="Posição na Bancada",
                yaxis=dict(autorange='reversed'),
                height=600
            )

            st.plotly_chart(fig, use_container_width=True)

            # =====================================================
            # DETALHES EXPANSÍVEIS
            # =====================================================

            with st.expander(
                f"📄 Detalhes dos {len(df_reprovacoes)} Medidores "
                f"Reprovados na {bancada.replace('_', ' ')} "
                f"(Clique para expandir)"
            ):

                st.dataframe(
                    df_reprovacoes[
                        [
                            'Data',
                            'Ensaio #',
                            'Posição',
                            'Série',
                            'Ponto do Erro',
                            'Valor CN',
                            'Valor CP',
                            'Valor CI'
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True
                )

            # =====================================================
            # EXPORTAÇÃO EXCEL
            # =====================================================

            excel_bytes_reprovacoes = to_excel(df_reprovacoes)

            st.download_button(
                label=f"📥 Baixar detalhes da {bancada.replace('_', ' ')} em Excel",
                data=excel_bytes_reprovacoes,
                file_name=(
                    f"Detalhes_Reprovacoes_{bancada}_"
                    f"{data_inicio.strftime('%Y%m%d')}-"
                    f"{data_fim.strftime('%Y%m%d')}.xlsx"
                ),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# =========================================================
# [BLOCO 09] - INICIALIZAÇÃO E MENU PRINCIPAL
# =========================================================

def main():

    try:
        # =====================================================
        # CARREGAMENTO DOS DADOS
        # =====================================================

        df_completo = carregar_dados()

        if not df_completo.empty:

            # =====================================================
            # CABEÇALHO PRINCIPAL
            # =====================================================

            col_titulo, col_data = st.columns([3, 1])

            with col_titulo:
                st.title("📊 Dashboard de Ensaios")

            with col_data:
                ultima_data = df_completo['Data_dt'].max()

                st.markdown(
                    f"""
                    <div style="text-align: right; padding-top: 15px;">
                        <span style="font-size: 0.9em; color: #64748b;">
                            Último ensaio:
                            <strong>{ultima_data.strftime('%d/%m/%Y')}</strong>
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            # =====================================================
            # MENU LATERAL
            # =====================================================

            st.sidebar.title("Menu de Navegação")

            paginas = {
                'Visão Diária': pagina_visao_diaria,
                'Visão Mensal': pagina_visao_mensal,
                'Análise de Posições': pagina_analise_posicoes,
                'Metrologia Avançada': pagina_metrologia_avancada
            }

            escolha = st.sidebar.radio(
                "Escolha a análise:",
                tuple(paginas.keys())
            )

            pagina_selecionada = paginas[escolha]

            # =====================================================
            # EXECUTA A PÁGINA ESCOLHIDA
            # =====================================================

            pagina_selecionada(df_completo)

        else:
            st.error("Erro ao carregar dados. Verifique a conexão com o Google Sheets.")

    except Exception as e:
        st.error("Ocorreu um erro inesperado na aplicação.")
        st.code(traceback.format_exc())


# =========================================================
# EXECUÇÃO DA APLICAÇÃO
# =========================================================

if __name__ == "__main__":
    main()
