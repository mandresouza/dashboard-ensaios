# =======================================================================
# ARQUIVO: app.py (VERSÃO FINAL E COMPLETA COM BLOCO DE METROLOGIA)
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
import os
from io import BytesIO

# Tenta importar o gerador de PDF original
try:
    from pdf_generator import gerar_pdf_relatorio
except ImportError:
    def gerar_pdf_relatorio(*args, **kwargs):
        return None

st.set_page_config(page_title="Dashboard de Ensaios", page_icon="📊", layout="wide")

# --- CONFIGURAÇÕES E CONSTANTES ORIGINAIS ---
LIMITES_CLASSE = {"A": 1.0, "B": 1.3, "C": 2.0, "D": 0.3}

# =======================================================================
# [BLOCO ISOLADO] - METROLOGIA AVANÇADA (VERSÃO FINAL DE ALTA PRECISÃO)
# =======================================================================

# --- CONSTANTES EXCLUSIVAS DO BLOCO DE METROLOGIA ---
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
    
    serie_bancada = next((v for k, v in MAPA_BANCADA_SERIE.items() if k in bancada_row), None)
    tamanho_bancada = 20 if '20_POS' in bancada_row else 10
    
    classe = str(row.get("Classe", "")).upper()
    limite = 4.0 if "ELETROMEC" in (classe or 'B') else LIMITES_CLASSE.get(str(classe or 'B').replace("ELETROMEC", "").strip(), 1.3)
    
    def texto(val): return str(val) if val is not None else ""

    for pos in range(1, tamanho_bancada + 1):
        serie = texto(row.get(f"P{pos}_Série"))
        v_cn = valor_num_metrologia(row.get(f"P{pos}_CN"))
        v_cp = valor_num_metrologia(row.get(f"P{pos}_CP"))
        v_ci = valor_num_metrologia(row.get(f"P{pos}_CI"))
        
        erro_ref, inc_banc = 0.0, 0.05
        
        if df_mestra is not None and serie_bancada:
            ref_row = df_mestra[(df_mestra['Serie_Bancada'].astype(str) == str(serie_bancada)) & (df_mestra['Posicao'] == pos)]
            if not ref_row.empty:
                erro_ref = ref_row['Erro_Sistematico_Pct'].values[0] or 0.0
                inc_banc = ref_row['Incerteza_U_Pct'].values[0] if 'Incerteza_U_Pct' in ref_row.columns else 0.05
        
        if v_cn is None and v_cp is None and v_ci is None:
            status, detalhe = "Não Ligou / Não Ensaido", ""
        else:
            status, detalhe = "APROVADO", ""
            erros_p, alertas_gb = [], []
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
            "n_ensaio": n_ensaio, "pos": pos, "serie": serie,
            "cn": v_cn, "cp": v_cp, "ci": v_ci,
            "status": status, "detalhe": detalhe, 
            "erro_ref": erro_ref, "inc_banc": inc_banc
        })
    return medidores

def pagina_metrologia_avancada(df_completo):
    st.markdown("## 🔬 Metrologia Avançada e Estabilidade")
    df_mestra = carregar_tabela_mestra_sheets()
    
    meses_n = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês de Referência", range(1, 13), index=datetime.now().month-1, format_func=lambda x: meses_n[x-1])
    ano_sel = st.sidebar.selectbox("Ano de Referência", sorted(df_completo['Data_dt'].dt.year.unique(), reverse=True))
    
    todos_meds = []
    df_p = df_completo[(df_completo['Data_dt'].dt.month == mes_sel) & (df_completo['Data_dt'].dt.year == ano_sel)]
    
    for _, r in df_p.sort_values('Data_dt').iterrows():
        for m in processar_metrologia_isolada(r, df_mestra):
            m['Data'] = r['Data_dt']
            m['Bancada'] = r['Bancada_Nome']
            todos_meds.append(m)
            
    if not todos_meds:
        st.info(f"Nenhum dado de ensaio encontrado para {meses_n[mes_sel-1]} de {ano_sel}.")
        return

    df_met = pd.DataFrame(todos_meds)
    tabs = st.tabs(["📈 Cartas de Controle", "⚠️ Alertas Guardband (Risco)", "📊 Dispersão de Erros"])

    with tabs[0]:
        c1, c2 = st.columns(2)
        b_sel = c1.selectbox("Selecione a Bancada", sorted(df_met['Bancada'].unique()))
        p_sel = c2.slider("Selecione a Posição", 1, 20, 1)
        
        df_chart = df_met[(df_met['Bancada'] == b_sel) & (df_met['pos'] == p_sel)].copy()
        df_chart['Erro_Medio'] = df_chart.apply(lambda r: np.mean([x for x in [r['cn'], r['cp'], r['ci']] if x is not None]), axis=1)
        df_chart = df_chart.dropna(subset=['Erro_Medio'])
        
        if not df_chart.empty:
            fig = go.Figure()
            # Linha de Erro do Medidor
            fig.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['Erro_Medio'], mode='lines+markers', name='Erro do Medidor', line=dict(color='#2ecc71', width=3), hovertext=df_chart['n_ensaio']))
            # Linha de Referência da Bancada
            fig.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['erro_ref'], mode='lines', name='Referência Bancada', line=dict(dash='dash', color='#e74c3c')))
            # Linha de Tendência (Média Móvel)
            fig.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['Erro_Medio'].rolling(window=3, min_periods=1).mean(), mode='lines', name='Tendência (Média Móvel)', line=dict(color='rgba(255,255,255,0.3)', width=1)))
            
            avg, std = df_chart['Erro_Medio'].mean(), df_chart['Erro_Medio'].std()
            if not pd.isna(std) and std > 0:
                fig.add_hline(y=avg + 2*std, line_dash="dot", line_color="#f1c40f", annotation_text="LSC (Limite Superior)")
                fig.add_hline(y=avg - 2*std, line_dash="dot", line_color="#f1c40f", annotation_text="LIC (Limite Inferior)")
            
            fig.update_layout(title=f"Carta de Controle Individual: {b_sel} (Posição {p_sel})", xaxis_title="Data do Ensaio", yaxis_title="Erro Médio (%)", hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Não há ensaios válidos para esta posição no período selecionado.")

    with tabs[1]:
        df_gb = df_met[df_met['status'] == 'ZONA CRÍTICA']
        if not df_gb.empty:
            st.warning(f"Identificamos {len(df_gb)} medidores que passaram no limite, mas estão na zona de risco por incerteza.")
            st.dataframe(df_gb[['Data', 'n_ensaio', 'Bancada', 'pos', 'serie', 'detalhe']], use_container_width=True, hide_index=True)
        else:
            st.success("Excelente! Nenhum medidor na zona crítica de Guardband neste mês.")

    with tabs[2]:
        df_met['Erro_Max'] = df_met.apply(lambda r: max([abs(x) for x in [r['cn'], r['cp'], r['ci']] if x is not None] or [0]), axis=1)
        fig_box = px.box(df_met, x='Bancada', y='Erro_Max', color='Bancada', title="Distribuição de Erros Máximos por Bancada", points="all")
        fig_box.update_layout(yaxis_title="Erro Absoluto Máximo (%)")
        st.plotly_chart(fig_box, use_container_width=True)

# =======================================================================
# [FIM DO BLOCO ISOLADO]

# =======================================================================
# [BLOCO 02] - CARREGAMENTO DE DADOS (ORIGINAL)
# =======================================================================

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
        
        # Conversão e limpeza de datas
        df_completo['Data_dt'] = pd.to_datetime(df_completo['Data'], errors='coerce', dayfirst=True)
        df_completo = df_completo.dropna(subset=['Data_dt'])
        df_completo['Data'] = df_completo['Data_dt'].dt.strftime('%d/%m/%y')
        
        return df_completo
    except Exception as e:
        st.error(f"ERRO AO ACESSAR GOOGLE SHEETS: {e}")
        return pd.DataFrame()

# =======================================================================
# [BLOCO 03] - FUNÇÕES AUXILIARES (ORIGINAL)
# =======================================================================

def valor_num(v):
    """Converte strings de erro em números flutuantes tratáveis."""
    try:
        if pd.isna(v):
            return None
        return float(str(v).replace("%", "").replace(",", "."))
    except (ValueError, TypeError):
        return None

def texto(v):
    """Trata valores nulos para exibição em tabelas."""
    if pd.isna(v) or v is None:
        return "-"
    return str(v)

def calcular_estatisticas(todos_medidores):
    """Calcula o resumo estatístico para os cards do dashboard."""
    total = len(todos_medidores)
    aprovados = sum(1 for m in todos_medidores if m['status'] == 'APROVADO')
    reprovados = sum(1 for m in todos_medidores if m['status'] == 'REPROVADO')
    consumidor = sum(1 for m in todos_medidores if m['status'] == 'CONTRA O CONSUMIDOR')
    
    return {
        "total": total, 
        "aprovados": aprovados, 
        "reprovados": reprovados, 
        "consumidor": consumidor
    }

def to_excel(df):
    """Gera o binário do arquivo Excel para download."""
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    processed_data = output.getvalue()
    return processed_data

# =======================================================================
# [BLOCO 04A] - VERSÃO ULTRA SIMPLIFICADA
# =======================================================================

def valor_num(valor):
    """Converte valor para float, retorna None se inválido"""
    if pd.isna(valor) or valor == "" or str(valor).strip() in ["-", "None", "SEM LEITURA", "ERRO"]:
        return None
    try:
        if isinstance(valor, str):
            valor = valor.strip().replace(',', '.')
        return float(valor)
    except:
        return None

def texto(valor):
    """Formata valor como texto, remove '.0' desnecessários"""
    if pd.isna(valor) or str(valor).strip() in ["-", "None"]:
        return "-"
    val_str = str(valor).strip()
    if val_str.endswith('.0'):
        return val_str[:-2]
    return val_str

def processar_ensaio(row, classe_banc20=None):
    """VERSÃO SIMPLIFICADA - SÓ LÊ DA PLANILHA, NÃO CALCULA NADA"""
    medidores = []
    bancada = row.get('Bancada_Nome')
    tamanho_bancada = 20 if bancada == 'BANC_20_POS' else 10
    
    classe = str(row.get("Classe", "")).upper()
    if not classe: 
        classe = 'B'
    limite_exat = 4.0 if "ELETROMEC" in classe else 1.3

    for pos in range(1, tamanho_bancada + 1):
        serie = texto(row.get(f"P{pos}_Série"))
        cn = row.get(f"P{pos}_CN")
        cp = row.get(f"P{pos}_CP")
        ci = row.get(f"P{pos}_CI")
        mv = row.get(f"P{pos}_MV")
        r_ini = row.get(f"P{pos}_REG_Inicio")
        r_fim = row.get(f"P{pos}_REG_Fim")
        
        # *** LÊ O ERRO DA PLANILHA - NÃO CALCULA ***
        reg_erro = row.get(f"P{pos}_REG_Erro")
        
        v_cn = valor_num(cn)
        v_cp = valor_num(cp)
        v_ci = valor_num(ci)
        v_reg_erro = valor_num(reg_erro)
        mv_str = str(texto(mv)).strip().upper()

        # --- POSIÇÃO VAZIA ---
        if v_cn is None and v_cp is None and v_ci is None:
            medidores.append({
                "pos": pos, "serie": serie, "cn": "-", "cp": "-", "ci": "-", "mv": "-",
                "reg_inicio": "-", "reg_fim": "-", "reg_erro": "-",
                "status": "Não Ligou / Não Ensaido", "detalhe": "", "motivo": "N/A", 
                "limite": limite_exat, "erros_pontuais": []
            })
            continue

        erros_list = []
        erros_pontuais = []
        
        # --- 1. EXATIDÃO ---
        if v_cn is not None and abs(v_cn) > limite_exat: 
            erros_pontuais.append('CN')
            erros_list.append("Exatidão")
        if v_cp is not None and abs(v_cp) > limite_exat: 
            erros_pontuais.append('CP')
            erros_list.append("Exatidão")
        if v_ci is not None and abs(v_ci) > limite_exat: 
            erros_pontuais.append('CI')
            erros_list.append("Exatidão")

        # --- 2. MOSTRADOR ---
        if (bancada == 'BANC_10_POS' and mv_str != "+") or \
           (bancada != 'BANC_10_POS' and mv_str != "OK"):
            erros_list.append("Mostrador/MV")

        # --- 3. REGISTRADOR - LÓGICA ULTRA SIMPLES ---
        reg_display = "-"
        
        if v_reg_erro is not None:
            # SE FOR 0, 0.01 ou 1.0 = APROVADO
            if v_reg_erro <= 1.5:
                if v_reg_erro == 0 or v_reg_erro < 0.05:
                    reg_display = "0.01"
                elif v_reg_erro <= 1.05:
                    reg_display = "1.0"
                else:
                    reg_display = f"{v_reg_erro:.2f}"
                # *** NÃO ADICIONA ERRO ***
            
            # SE FOR > 1.5 = REPROVADO
            else:
                reg_display = "ERRO" if v_reg_erro > 100 else f"{v_reg_erro:.2f}"
                erros_list.append("Registrador")  # ← SÓ ADICIONA AQUI!

        # --- 4. STATUS FINAL ---
        erro_exat = len([e for e in erros_list if e == "Exatidão"]) > 0
        erro_reg = "Registrador" in erros_list
        erro_mv = "Mostrador/MV" in erros_list
        
        if (erro_exat and erro_reg) or (erro_exat and erro_mv):
            status = "CONTRA O CONSUMIDOR"
            motivo = "Contra Consumidor"
        elif len(erros_list) > 0:
            status = "REPROVADO"
            motivo = " / ".join(sorted(list(set(erros_list))))
        else:
            status = "APROVADO"
            motivo = "Nenhum"

        medidores.append({
            "pos": pos, 
            "serie": serie, 
            "cn": texto(cn), 
            "cp": texto(cp), 
            "ci": texto(ci), 
            "mv": mv_str,
            "reg_inicio": texto(r_ini), 
            "reg_fim": texto(r_fim), 
            "reg_erro": reg_display,
            "status": status, 
            "detalhe": "", 
            "motivo": motivo, 
            "limite": limite_exat,
            "erros_pontuais": erros_pontuais
        })
    
    return medidores


# =======================================================================
# [BLOCO 04B] - ESTATÍSTICAS (SEM ALTERAÇÕES)
# =======================================================================

def calcular_estatisticas(medidores):
    total = len(medidores)
    apr = sum(1 for m in medidores if m['status'] == 'APROVADO')
    rep = sum(1 for m in medidores if m['status'] == 'REPROVADO')
    con = sum(1 for m in medidores if m['status'] == 'CONTRA O CONSUMIDOR')
    return {"total": total, "aprovados": apr, "reprovados": rep, "consumidor": con}

def calcular_auditoria_real(df):
    t_pos, t_ens, t_apr, t_rep = 0, 0, 0, 0
    r_exat, r_reg, r_mv, r_cons = 0, 0, 0, 0
    
    for _, row in df.iterrows():
        medidores = processar_ensaio(row)
        for m in medidores:
            t_pos += 1
            if m['status'] != "Não Ligou / Não Ensaido":
                t_ens += 1
                if m['status'] == "APROVADO": 
                    t_apr += 1
                else:
                    t_rep += 1
                    if "Exatidão" in m['motivo']: r_exat += 1
                    if "Registrador" in m['motivo']: r_reg += 1
                    if "Mostrador/MV" in m['motivo']: r_mv += 1
                    if m['status'] == "CONTRA O CONSUMIDOR": r_cons += 1
    
    taxa = (t_apr / t_ens * 100) if t_ens > 0 else 0
    
    return {
        "total_posicoes": t_pos, "total_ensaiadas": t_ens, "total_aprovadas": t_apr, 
        "total_reprovadas": t_rep, "taxa_aprovacao": taxa, "reprov_exatidao": r_exat, 
        "reprov_registrador": r_reg, "reprov_mv": r_mv, "reprov_consumidor": r_cons
    }
    
# =======================================================================
# [BLOCO 05] - COMPONENTES VISUAIS (VERSÃO COM ESPAÇAMENTO NOS CARDS)
# =======================================================================

def renderizar_card(medidor):
    """Renderiza o card individual de cada medidor com cores dinâmicas por status."""
    status_cor = {
        "APROVADO": "#dcfce7", 
        "REPROVADO": "#fee2e2", 
        "CONTRA O CONSUMIDOR": "#ede9fe", 
        "Não Ligou / Não Ensaido": "#e5e7eb"
    }
    cor = status_cor.get(medidor['status'], "#f3f4f6")
    
    conteudo_html = f"""
<div style="background:{cor}; border-radius:12px; padding:16px; font-size:14px; box-shadow:0 2px 8px rgba(0,0,0,0.1); border-left: 6px solid rgba(0,0,0,0.1); display: flex; flex-direction: column; justify-content: space-between; min-height: 380px;">
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

<div style="background: rgba(0,0,0,0.03); padding: 10px; border-radius: 8px; border: 1px dashed rgba(0,0,0,0.1); margin-bottom:12px;">
<b style="display: block; margin-bottom: 8px; font-size: 12px;">📑 Registrador (kWh)</b>
<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; font-size: 14px;">
<span><b>Início:</b> {medidor['reg_inicio']}</span>
<span><b>Fim:</b> {medidor['reg_fim']}</span>
<span style="grid-column: span 2; font-weight: bold; border-top: 1px solid rgba(0,0,0,0.05); padding-top: 4px;">Erro: {medidor['reg_erro']}</span>
</div>
</div>

</div>
<div>
<div style="padding:10px; margin-top: 16px; border-radius:8px; font-weight:800; font-size: 15px; text-align:center; background: rgba(0,0,0,0.08);">{medidor['status']}</div>
<div style="margin-top:8px; font-size:12px; text-align:center;">{medidor['detalhe']}</div>
</div>
</div>
""".strip()
    
    st.markdown(conteudo_html, unsafe_allow_html=True)

def renderizar_resumo(stats):
    """Renderiza as métricas de resumo com espaçamento entre o primeiro e os demais cards."""
    st.markdown("""
        <style>
            .metric-card{background-color:#FFFFFF; padding:20px; border-radius:12px; 
                         box-shadow:0 4px 6px rgba(0,0,0,0.05); text-align:center;}
            .metric-value{font-size:32px; font-weight:700;}
            .metric-label{font-size:16px; color:#64748b;}
        </style>
    """, unsafe_allow_html=True)
    
    # --- AJUSTE DE ESPAÇAMENTO ---
    # Criamos 5 colunas: c1 (Card 1), gap (vazia), c2 (Card 2), c3 (Card 3), c4 (Card 4)
    # A proporção [1, 0.2, 1, 1, 1] cria o respiro após o primeiro card.
    c1, gap, c2, c3, c4 = st.columns([1, 0.2, 1, 1, 1])
    
    with c1:
        st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#1e293b;">{stats["total"]}</div><div class="metric-label">Total Ensaiados</div></div>', unsafe_allow_html=True)
    
    # A coluna 'gap' fica vazia propositalmente para dar o espaço
    
    with c2:
        st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#16a34a;">{stats["aprovados"]}</div><div class="metric-label">Aprovados</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#dc2626;">{stats["reprovados"]}</div><div class="metric-label">Reprovados</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#7c3aed;">{stats["consumidor"]}</div><div class="metric-label">Contra Consumidor</div></div>', unsafe_allow_html=True)

def renderizar_cabecalho_ensaio(n_ensaio, bancada, temperatura):
    """Cria uma barra de informações compacta para identificar o ensaio atual."""
    st.markdown(f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 10px 15px; 
                    border-radius: 10px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: bold; font-size: 1.1em;">📋 Ensaio #{n_ensaio}</span>
            <span style="color: #475569;"><strong>Bancada:</strong> {bancada.replace('_', ' ')}</span>
            <span style="color: #475569;">🌡️ {temperatura}</span>
        </div>
    """, unsafe_allow_html=True)

def renderizar_grafico_reprovacoes(medidores):
    """Gera um gráfico horizontal com os motivos das reprovações."""
    import pandas as pd
    import plotly.express as px
    motivos = [m['motivo'] for m in medidores if m['status'] in ['REPROVADO', 'CONTRA O CONSUMIDOR']]
    if not motivos:
        return
        
    contagem = {}
    for m in motivos:
        partes = [p.strip() for p in m.split('/')]
        for parte in partes:
            if parte != "Nenhum":
                contagem[parte] = contagem.get(parte, 0) + 1
                
    df_motivos = pd.DataFrame(list(contagem.items()), columns=['Motivo', 'Quantidade']).sort_values('Quantidade', ascending=True)
    
    fig = px.bar(df_motivos, x='Quantidade', y='Motivo', orientation='h', 
                 title='<b>Principais Motivos de Reprovação</b>', text='Quantidade',
                 color_discrete_sequence=px.colors.qualitative.Pastel)
    
    fig.update_layout(yaxis_title=None, xaxis_title="Número de Medidores", showlegend=False, 
                      margin=dict(l=10, r=10, t=40, b=10), height=250)
    fig.update_traces(textposition='outside')
    st.plotly_chart(fig, use_container_width=True)

def renderizar_botao_scroll_topo():
    """Adiciona um botão flutuante para voltar ao topo da página via JavaScript."""
    scroll_button_html = """
    <style>
        #scrollTopBtn {
            display: none; position: fixed; bottom: 20px; right: 30px; z-index: 99; 
            border: none; outline: none; background-color: #555; color: white; 
            cursor: pointer; padding: 15px; border-radius: 10px; font-size: 18px; opacity: 0.7;
        }
        #scrollTopBtn:hover { background-color: #f44336; opacity: 1; }
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

# =========================================================
# [BLOCO 06] - PÁGINA: VISÃO DIÁRIA (VERSÃO FINAL UNIFICADA)
# =========================================================

def pagina_visao_diaria(df_completo):
    # --- BOTÃO VOLTAR AO TOPO (CSS & HTML) ---
    st.markdown('''
        <style> 
            .stApp { scroll-behavior: smooth; } 
            #scroll-to-top { 
                position: fixed; bottom: 20px; right: 30px; z-index: 99; 
                border: none; outline: none; background-color: #555; 
                color: white; cursor: pointer; padding: 15px; 
                border-radius: 10px; font-size: 18px; opacity: 0.7; 
            } 
            #scroll-to-top:hover { background-color: #f44336; opacity: 1; } 
            
            /* Estilo para os novos cards de performance */
            .metric-card-mensal {
                background-color: #ffffff;
                padding: 15px;
                border-radius: 12px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                text-align: center;
                border-top: 4px solid #3b82f6;
            }
            .val-mensal { font-size: 28px; font-weight: 800; color: #1e293b; display: block; }
            .lab-mensal { font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        </style> 
        <a id="top"></a> 
        <a href="#top" id="scroll-to-top"><b>^</b></a> 
    ''', unsafe_allow_html=True)

    st.sidebar.header("🔍 Busca e Filtros")

    # =====================================================
    # BUSCA POR SÉRIE (Original Mantido)
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
            
        st.markdown(f"### 🔍 Histórico de Ensaios para a Série: **{serie_input}**")
        resultados = []
        for _, ensaio_row in df_completo.iterrows():
            colunas_serie = [c for c in ensaio_row.index if "_Série" in str(c)]
            if any(termo_busca in str(ensaio_row[col]).lower() for col in colunas_serie if pd.notna(ensaio_row[col])):
                medidores = processar_ensaio(ensaio_row)
                for m in medidores:
                    if termo_busca in m['serie'].lower():
                        resultados.append({"data": ensaio_row['Data'], "bancada": ensaio_row['Bancada_Nome'], "dados": m})
        
        if resultados:
            st.success(f"{len(resultados)} registro(s) encontrado(s).")
            for res in sorted(resultados, key=lambda x: datetime.strptime(x['data'], '%d/%m/%y'), reverse=True):
                with st.expander(f"{res['data']} | {res['bancada']} | {res['dados']['status']}"):
                    renderizar_card(res['dados'])
        else:
            st.warning("Nenhum registro encontrado.")
        return

    # =====================================================
    # FILTROS DO DIA (Original Mantido)
    # =====================================================
    if "filtro_data" not in st.session_state:
        st.session_state.filtro_data = (datetime.now() - pd.Timedelta(hours=3)).date()
    if "filtro_bancada" not in st.session_state:
        st.session_state.filtro_bancada = "Todas"
    if "filtro_status" not in st.session_state:
        st.session_state.filtro_status = []
    if "filtro_irregularidade" not in st.session_state:
        st.session_state.filtro_irregularidade = []

    st.session_state.filtro_data = st.sidebar.date_input("Data do Ensaio", value=st.session_state.filtro_data, format="DD/MM/YYYY")
    bancadas = df_completo['Bancada_Nome'].unique().tolist()
    st.session_state.filtro_bancada = st.sidebar.selectbox("Bancada", ['Todas'] + bancadas)
    status_options = ["APROVADO", "REPROVADO", "CONTRA O CONSUMIDOR", "Não Ligou / Não Ensaido"]
    st.session_state.filtro_status = st.sidebar.multiselect("Filtrar Status", status_options, default=st.session_state.filtro_status)

    if "REPROVADO" in st.session_state.filtro_status:
        st.session_state.filtro_irregularidade = st.sidebar.multiselect("Filtrar Irregularidade", ["Exatidão", "Registrador", "Mostrador/MV"], default=st.session_state.filtro_irregularidade)
    else:
        st.session_state.filtro_irregularidade = []

    # =====================================================
    # PROCESSAMENTO DE DADOS (Unificado para evitar erros)
    # =====================================================
    df_filtrado = df_completo[df_completo['Data_dt'].dt.date == st.session_state.filtro_data]
    if st.session_state.filtro_bancada != "Todas":
        df_filtrado = df_filtrado[df_filtrado['Bancada_Nome'] == st.session_state.filtro_bancada]

    if df_filtrado.empty:
        st.info("Nenhum ensaio encontrado para esta data/bancada.")
        return

    ensaios = []
    for _, row in df_filtrado.iterrows():
        medidores = processar_ensaio(row)
        medidores_filtrados = []
        for m in medidores:
            status_ok = not st.session_state.filtro_status or m['status'] in st.session_state.filtro_status
            irr_ok = not st.session_state.filtro_irregularidade or any(i in m['motivo'] for i in st.session_state.filtro_irregularidade)
            if status_ok and irr_ok:
                medidores_filtrados.append(m)
        if medidores_filtrados:
            ensaios.append({"n_ensaio": row.get("N_ENSAIO", "N/A"), "bancada": row["Bancada_Nome"], "temperatura": row.get("Temperatura", "--"), "medidores": medidores_filtrados})

    if not ensaios:
        st.info("Nenhum medidor corresponde aos filtros.")
        return

    todos_os_medidores = [m for e in ensaios for m in e["medidores"]]
    stats = calcular_estatisticas(todos_os_medidores)

    # =====================================================
    # 🎯 NOVA ESTRUTURA DE INDICADORES (LIMPA E UNIFICADA)
    # =====================================================
    st.markdown("### 📊 Resumo da Auditoria")
    
    # Linha principal de métricas
    c1, g1, c2, c3, c4, c5 = st.columns([1, 0.1, 1, 1, 1, 1])
    
    with c1:
        st.markdown(f'<div class="metric-card-mensal" style="border-top-color:#1e293b"><span class="val-mensal">{stats["total"]}</span><span class="lab-mensal">Ensaiados</span></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card-mensal" style="border-top-color:#16a34a"><span class="val-mensal">{stats["aprovados"]}</span><span class="lab-mensal">Aprovados</span></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card-mensal" style="border-top-color:#dc2626"><span class="val-mensal">{stats["reprovados"]}</span><span class="lab-mensal">Reprovados</span></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card-mensal" style="border-top-color:#7c3aed"><span class="val-mensal">{stats["contra_consumidor"]}</span><span class="lab-mensal">Contra Cons.</span></div>', unsafe_allow_html=True)
    with c5:
        cor_idx = "#16a34a" if stats["taxa_aprovacao"] >= 90 else "#ea580c"
        st.markdown(f'<div class="metric-card-mensal" style="border-top-color:{cor_idx}"><span class="val-mensal">{stats["taxa_aprovacao"]:.1f}%</span><span class="lab-mensal">Qualidade</span></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Sub-detalhamento técnico (Informativo)
    d1, d2, d3 = st.columns(3)
    with d1:
        st.info(f"📍 **Falhas de Exatidão:** {stats['motivos'].get('Exatidão', 0)}")
    with d2:
        st.warning(f"📍 **Falhas de Registrador:** {stats['motivos'].get('Registrador', 0)}")
    with d3:
        st.error(f"📍 **Falhas de Mostrador/MV:** {stats['motivos'].get('Mostrador/MV', 0)}")

    st.markdown("---")

    # =====================================================
    # GRÁFICOS E EXPORTAÇÃO (Mantido Original)
    # =====================================================
    col_g, col_e = st.columns([3, 1])
    with col_g:
        renderizar_grafico_reprovacoes(todos_os_medidores)
    with col_e:
        st.write("📂 **Exportação**")
        pdf = gerar_pdf_relatorio(ensaios=ensaios, data=st.session_state.filtro_data.strftime('%d/%m/%Y'), stats=stats)
        if pdf: st.download_button("📥 Baixar PDF", pdf, file_name=f"relatorio_{st.session_state.filtro_data}.pdf", use_container_width=True)
        excel = to_excel(pd.DataFrame(todos_os_medidores))
        st.download_button("📥 Baixar Excel", excel, file_name=f"dados_{st.session_state.filtro_data}.xlsx", use_container_width=True)

    # =====================================================
    # DETALHES DOS ENSAIOS (Não mexer daqui para baixo)
    # =====================================================
    st.subheader("📋 Detalhes dos Ensaios")
    for ensaio in ensaios:
        renderizar_cabecalho_ensaio(ensaio["n_ensaio"], ensaio["bancada"], ensaio["temperatura"])
        cols_n = 5
        for i in range(0, len(ensaio["medidores"]), cols_n):
            cols = st.columns(cols_n)
            for j, m in enumerate(ensaio["medidores"][i : i + cols_n]):
                with cols[j]:
                    renderizar_card(m)

# =========================================================
# [BLOCO 07] - PÁGINA: VISÃO MENSAL (VERSÃO FINAL AJUSTADA)
# =========================================================

def get_stats_por_dia(df_mes):
    """Gera o dataframe consolidado de estatísticas diárias para os gráficos."""
    daily_stats = []
    for data, group in df_mes.groupby('Data_dt'):
        medidores = []
        for _, row in group.iterrows():
            medidores.extend(processar_ensaio(row, 'B'))
        
        aprovados = sum(1 for m in medidores if m['status'] == 'APROVADO')
        reprovados = sum(1 for m in medidores if m['status'] == 'REPROVADO')
        consumidor = sum(1 for m in medidores if m['status'] == 'CONTRA O CONSUMIDOR')
        nao_ensaiados = sum(1 for m in medidores if m['status'] == 'Não Ligou / Não Ensaido')
        
        total_ensaiados = aprovados + reprovados + consumidor
        taxa_aprovacao = (aprovados / total_ensaiados * 100) if total_ensaiados > 0 else 0
        
        daily_stats.append({
            'Data': data,
            'Aprovados': aprovados,
            'Reprovados': reprovados,
            'Contra Consumidor': consumidor,
            'Não Ensaidos': nao_ensaiados,
            'Total': total_ensaiados,
            'Taxa de Aprovação (%)': round(taxa_aprovacao, 1)
        })
    return pd.DataFrame(daily_stats)

def pagina_visao_mensal(df_completo):
    # --- BOTÃO VOLTAR AO TOPO (SUAVIZADO) ---
    st.markdown('''
        <style> 
            .stApp { scroll-behavior: smooth; } 
            #scroll-to-top { 
                position: fixed; bottom: 20px; right: 30px; z-index: 99; 
                border: none; outline: none; background-color: #555; 
                color: white; cursor: pointer; padding: 15px; 
                border-radius: 10px; font-size: 18px; opacity: 0.7; 
            } 
            #scroll-to-top:hover { background-color: #f44336; opacity: 1; } 
        </style> 
        <a id="top"></a> 
        <a href="#top" id="scroll-to-top" title="Voltar ao topo"><b>^</b></a> 
    ''', unsafe_allow_html=True)

    st.markdown("## 📊 Visão Mensal e Performance")
    st.markdown("---")

    # =====================================================
    # AUDITORIA TÉCNICA (ESSA PARTE É VITAL PARA OUTRAS ABAS)
    # =====================================================
    st.markdown("## 🔎 Auditoria Técnica Real dos Ensaios")
    dados_auditoria = calcular_auditoria_real(df_completo)
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Posições Totais", dados_auditoria["total_posicoes"])
    c2.metric("Realmente Ensaiadas", dados_auditoria["total_ensaiadas"])
    c3.metric("Aprovadas Reais", dados_auditoria["total_aprovadas"])
    c4.metric("Reprovadas Reais", dados_auditoria["total_reprovadas"])
    
    st.metric("Aprovação Técnica (%)", f'{dados_auditoria["taxa_aprovacao"]:.2f}%')

    st.markdown("### ⚠️ Reprovação por Motivo")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Erro de Exatidão", dados_auditoria["reprov_exatidao"])
    m2.metric("Registrador", dados_auditoria["reprov_registrador"])
    m3.metric("Mostrador / MV", dados_auditoria["reprov_mv"])
    m4.metric("Contra Consumidor", dados_auditoria["reprov_consumidor"])

    # ==============================
    # PREPARAÇÃO E FILTROS DO MÊS
    # ==============================
    df_completo['Ano'] = df_completo['Data_dt'].dt.year
    df_completo['Mes'] = df_completo['Data_dt'].dt.month
    
    col_f1, col_f2 = st.sidebar.columns(2)
    ano_sel = col_f1.selectbox("Ano", sorted(df_completo['Ano'].unique(), reverse=True))
    meses_disp = sorted(df_completo[df_completo['Ano'] == ano_sel]['Mes'].unique())
    
    mes_sel = col_f2.selectbox(
        "Mês", 
        meses_disp, 
        format_func=lambda x: ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"][x-1]
    )

    df_mes = df_completo[(df_completo['Ano'] == ano_sel) & (df_completo['Mes'] == mes_sel)]
    
    if df_mes.empty:
        st.warning("Nenhum dado encontrado para o período selecionado.")
        return

    # ==============================
    # CONSOLIDAÇÃO DOS DADOS MENSAIS
    # ==============================
    todos_mes = []
    for _, row in df_mes.iterrows():
        todos_mes.extend(processar_ensaio(row))
    
    aprov_m = sum(1 for m in todos_mes if m['status'] == 'APROVADO')
    repro_m = sum(1 for m in todos_mes if m['status'] == 'REPROVADO')
    cons_m = sum(1 for m in todos_mes if m['status'] == 'CONTRA O CONSUMIDOR')
    nao_ensaiados_m = sum(1 for m in todos_mes if m['status'] == 'Não Ligou / Não Ensaido')
    
    total_m = aprov_m + repro_m + cons_m
    taxa_m = (aprov_m / total_m * 100) if total_m > 0 else 0
    
    df_daily = get_stats_por_dia(df_mes)

    # ==============================
    # MÉTRICAS PRINCIPAIS (DASHBOARD)
    # ==============================
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    col_m1.metric("Total Ensaiados", f"{total_m:,.0f}".replace(",", "."))
    col_m2.metric("Taxa de Aprovação", f"{taxa_m:.1f}%", delta=f"{taxa_m-95:.1f}% vs Meta (95%)" if taxa_m > 0 else None)
    col_m3.metric("Total Reprovados", f"{repro_m:,.0f}".replace(",", "."), delta=repro_m, delta_color="inverse")
    col_m4.metric("Contra Consumidor", f"{cons_m:,.0f}".replace(",", "."), delta=cons_m, delta_color="inverse")
    col_m5.metric("Não Ensaidos", f"{nao_ensaiados_m:,.0f}".replace(",", "."))

    # ==============================
    # CÁLCULO DA TEMPERATURA MÉDIA
    # ==============================
    temp_media = 0
    if 'Temperatura' in df_mes.columns:
        temp_series = (
            df_mes['Temperatura']
            .astype(str)
            .str.replace("°C", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )
        temp_series = pd.to_numeric(temp_series, errors="coerce")
        temp_media = temp_series.mean()
        if not pd.isna(temp_media):
            st.info(f"🌡️ **Temperatura Média do Período:** {temp_media:.1f}°C")

    # ==============================
    # GRÁFICOS DE PERFORMANCE
    # ==============================
    col_g1, col_g2 = st.columns([1, 1.5])
    
    with col_g1:
        df_pie = pd.DataFrame({
            'Status': ['Aprovados','Reprovados','Contra Consumidor'],
            'Qtd': [aprov_m, repro_m, cons_m]
        })
        fig_donut = px.pie(
            df_pie, values='Qtd', names='Status', hole=.5,
            color_discrete_map={'Aprovados':'#16a34a', 'Reprovados':'#dc2626', 'Contra Consumidor':'#7c3aed'}
        )
        fig_donut.update_traces(textposition='inside', textinfo='percent+label')
        fig_donut.update_layout(showlegend=False, margin=dict(t=40,b=0,l=0,r=0))
        st.plotly_chart(fig_donut, use_container_width=True)

    with col_g2:
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(x=df_daily['Data'], y=df_daily['Aprovados'], name='Aprovados', marker_color='#16a34a'))
        fig_bar.add_trace(go.Bar(x=df_daily['Data'], y=df_daily['Reprovados'], name='Reprovados', marker_color='#dc2626'))
        fig_bar.add_trace(go.Bar(x=df_daily['Data'], y=df_daily['Contra Consumidor'], name='Contra Consumidor', marker_color='#7c3aed'))
        
        fig_bar.update_layout(
            barmode='stack', title='<b>Evolução Diária de Ensaios</b>',
            xaxis_title="Dia do Mês", yaxis_title="Quantidade",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=80,b=40,l=0,r=0), hovermode="x unified"
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # ==============================
    # TENDÊNCIA DA TAXA
    # ==============================
    st.markdown("---")
    st.subheader("📈 Tendência da Taxa de Aprovação")
    if not df_daily.empty:
        fig_line = px.line(
            df_daily, x='Data', y='Taxa de Aprovação (%)', 
            markers=True, text='Taxa de Aprovação (%)'
        )
        fig_line.update_traces(textposition="top center")
        fig_line.update_layout(
            yaxis=dict(range=[0,110]), 
            yaxis_title="Taxa (%)", 
            xaxis_title="Dia do Mês"
        )
        st.plotly_chart(fig_line, use_container_width=True)

   # =====================================================
    # AUDITORIA DETALHADA PARA CONFERÊNCIA DO USUÁRIO
    # =====================================================
    st.markdown("---")
    with st.expander("🔍 PAINEL DE AUDITORIA: Por que a taxa deu esse valor?"):
        st.write(f"### Análise Detalhada do Mês Selecionado")
        
        # 1. Tabela de Resumo Diário (O que alimenta o gráfico)
        st.write("**1. Resumo Diário (Consolidado):**")
        df_exibicao = df_daily.copy()
        df_exibicao['Data'] = df_exibicao['Data'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_exibicao, use_container_width=True, hide_index=True)

        st.markdown("---")
        
        # 2. Filtro para o usuário auditar um dia específico
        st.write("**2. Auditoria Individual de Medidores:**")
        dia_auditoria = st.selectbox("Selecione um dia para ver quem foi aprovado/reprovado:", df_daily['Data'].dt.strftime('%d/%m/%Y'))
        
        if dia_auditoria:
            # Filtra os medidores daquele dia exato
            data_filtro = pd.to_datetime(dia_auditoria, format='%d/%m/%Y')
            df_dia_f = df_mes[df_mes['Data_dt'] == data_filtro]
            
            medidores_auditoria = []
            for _, r in df_dia_f.iterrows():
                medidores_auditoria.extend(processar_ensaio(r))
            
            # Criar DataFrame de auditoria - COLUNA MV INCLUÍDA
            df_auditoria = pd.DataFrame([{
                "Pos": m['pos'],
                "Série": m['serie'],
                "Status": m['status'],
                "CN": m['cn'],
                "CP": m['cp'],
                "CI": m['ci'],
                "MV": m['mv'],  # <-- INCLUÍDO AQUI
                "Reg": m['reg_erro'],
                "Motivo": m['motivo']
            } for m in medidores_auditoria])

            # Mostrar quantos não ligaram
            nao_ligou = len(df_auditoria[df_auditoria['Status'] == "Não Ligou / Não Ensaido"])
            ensaiados = len(df_auditoria[df_auditoria['Status'] != "Não Ligou / Não Ensaido"])
            
            c_a1, c_a2 = st.columns(2)
            c_a1.warning(f"🔌 Não Ligaram/Vazios: {nao_ligou}")
            c_a2.success(f"✅ Considerados no Cálculo: {ensaiados}")

            st.write(f"Lista de medidores do dia {dia_auditoria}:")
            
            # Colorir a tabela para facilitar a auditoria
            def color_status(val):
                if val == 'APROVADO': color = '#c6f6d5' # Verde
                elif val == 'REPROVADO': color = '#fed7d7' # Vermelho
                elif val == 'CONTRA O CONSUMIDOR': color = '#e9d8fd' # Roxo
                else: color = '#edf2f7' # Cinza (Não ligou)
                return f'background-color: {color}'

            st.dataframe(
                df_auditoria.style.applymap(color_status, subset=['Status']),
                use_container_width=True,
                hide_index=True
            )

# =======================================================================
# [BLOCO 08] - PÁGINA: ANÁLISE DE POSIÇÕES (HEATMAP DE REPROVAÇÃO)
# =======================================================================

def pagina_analise_posicoes(df_completo):
    # --- BOTÃO VOLTAR AO TOPO ---
    st.markdown('''
        <style> .stApp { scroll-behavior: smooth; } #scroll-to-top { position: fixed; bottom: 20px; 
        right: 30px; z-index: 99; border: none; outline: none; background-color: #555; color: white; 
        cursor: pointer; padding: 15px; border-radius: 10px; font-size: 18px; opacity: 0.7; } 
        #scroll-to-top:hover { background-color: #f44336; opacity: 1; } </style>
        <a id="top"></a> <a href="#top" id="scroll-to-top" title="Voltar ao topo"><b>^</b></a>
    ''', unsafe_allow_html=True)

    st.markdown("## 🔥 Análise de Reprovação por Posição (Mapa de Calor)")
    st.info("Esta análise identifica quais posições e pontos de medição (CN, CP, CI) concentram o maior número de reprovações por exatidão.")

    st.sidebar.header("🔬 Filtros da Análise")
    bancadas_selecionadas = st.sidebar.multiselect(
        "Selecione a(s) Bancada(s)", 
        options=['BANC_10_POS', 'BANC_20_POS'],
        default=['BANC_10_POS', 'BANC_20_POS'], 
        key='heatmap_bancadas'
    )

    min_date = df_completo['Data_dt'].min().date()
    max_date = df_completo['Data_dt'].max().date()
    
    # Filtro de Período
    periodo = st.sidebar.date_input(
        "Selecione o Período", 
        value=(max_date - pd.Timedelta(days=30), max_date),
        min_value=min_date, 
        max_value=max_date, 
        key='heatmap_periodo'
    )

    if not isinstance(periodo, tuple) or len(periodo) < 2:
        st.warning("Por favor, selecione o intervalo completo (Data Início e Data Fim).")
        return
        
    data_inicio, data_fim = periodo

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
                st.info(f"Nenhum dado encontrado para a {bancada.replace('_', ' ')} no período.")
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
                st.success(f"🎉 Nenhuma reprovação por exatidão na {bancada.replace('_', ' ')} neste período!")
                continue

            # Construção do Mapa de Calor
            df_reprov = pd.DataFrame(reprovacoes_detalhadas)
            heatmap_data = df_reprov.pivot_table(index='Posição', columns='Ponto do Erro', aggfunc='size', fill_value=0)
            
            # Garante que as colunas CN, CP e CI existam para o gráfico
            for ponto in ['CN', 'CP', 'CI']:
                if ponto not in heatmap_data.columns:
                    heatmap_data[ponto] = 0
            
            heatmap_data = heatmap_data[['CN', 'CP', 'CI']]

            fig = go.Figure(data=go.Heatmap(
                z=heatmap_data.values,
                x=heatmap_data.columns,
                y=[f"Posição {i}" for i in heatmap_data.index],
                colorscale='Reds',
                text=heatmap_data.values,
                texttemplate="%{text}",
                showscale=True
            ))

            fig.update_layout(
                title=f'<b>Distribuição de Falhas - {bancada.replace("_", " ")}</b>',
                xaxis_title="Ponto de Medição",
                yaxis_title="Posição na Bancada",
                yaxis=dict(autorange='reversed'),
                height=600
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander(f"📄 Ver Lista de {len(df_reprov)} Medidores com Erro"):
                st.dataframe(df_reprov, use_container_width=True, hide_index=True)
                excel_bytes = to_excel(df_reprov)
                st.download_button(
                    label=f"📥 Baixar Excel {bancada}",
                    data=excel_bytes,
                    file_name=f"Heatmap_{bancada}.xlsx"
                )

# =======================================================================
# [BLOCO 09] - INICIALIZAÇÃO E MENU PRINCIPAL
# =======================================================================

def main():
    try:
        df_completo = carregar_dados()
        
        if not df_completo.empty:
            # Cabeçalho Principal
            col_titulo, col_data = st.columns([3, 1])
            with col_titulo:
                st.title("📊 Dashboard de Ensaios")
            with col_data:
                ultima_data = df_completo['Data_dt'].max()
                st.markdown(f"""
                    <div style="text-align: right; padding-top: 15px;">
                        <span style="font-size: 0.9em; color: #64748b;">Último ensaio carregado: 
                        <strong>{ultima_data.strftime('%d/%m/%Y')}</strong></span>
                    </div>
                """, unsafe_allow_html=True)

            # Sidebar de Navegação
            st.sidebar.markdown("---")
            st.sidebar.title("Menu de Navegação")
            paginas = {
                'Visão Diária': pagina_visao_diaria,
                'Visão Mensal': pagina_visao_mensal,
                'Análise de Posições': pagina_analise_posicoes,
                'Metrologia Avançada': pagina_metrologia_avancada
            }
            
            escolha = st.sidebar.radio("Selecione uma análise:", tuple(paginas.keys()))
            
            # Chama a função da página selecionada
            paginas[escolha](df_completo)
            
        else:
            st.error("Não foi possível encontrar dados. Verifique a planilha no Google Sheets.")
            
    except Exception as e:
        st.error("Ocorreu um erro crítico na aplicação.")
        with st.expander("Ver detalhes do erro"):
            st.code(traceback.format_exc())

if __name__ == "__main__":
    main()
