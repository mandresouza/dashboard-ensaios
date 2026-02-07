from fpdf import FPDF

# Esta classe define o cabeçalho e rodapé do nosso PDF
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        # Usamos texto sem acentos para máxima compatibilidade
        self.cell(0, 10, 'Relatorio de Fiscalizacao de Ensaios', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

# Esta é a função principal que vamos chamar do nosso app.py
def gerar_pdf_relatorio(medidores, data, bancada, stats):
    pdf = PDF()
    pdf.add_page()
    
    # Função interna para limpar o texto para o PDF
    def texto_pdf(txt):
        return str(txt).encode('latin-1', 'replace').decode('latin-1')

    # --- Seção 1: Cabeçalho do Relatório ---
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 8, texto_pdf(f"Data do Relatorio: {data}"), 0, 1)
    pdf.cell(0, 8, texto_pdf(f"Bancada(s) Inclusa(s): {bancada}"), 0, 1)
    pdf.ln(10)

    # --- Seção 2: Tabela de Resumo ---
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Resumo dos Resultados", 0, 1, 'L')
    pdf.set_font('Arial', '', 11)
    pdf.cell(95, 8, texto_pdf(f"Total de Medidores Ensaiados: {stats['total']}"), 1, 0)
    pdf.cell(95, 8, texto_pdf(f"Medidores Aprovados: {stats['aprovados']}"), 1, 1)
    pdf.cell(95, 8, texto_pdf(f"Medidores Reprovados: {stats['reprovados']}"), 1, 0)
    pdf.cell(95, 8, texto_pdf(f"Irregularidade (Contra Consumidor): {stats['consumidor']}"), 1, 1)
    pdf.ln(10)

    # --- Seção 3: Tabela de Detalhes ---
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Detalhes dos Medidores", 0, 1, 'L')
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(15, 7, "Pos.", 1)
    pdf.cell(40, 7, "Serie", 1)
    pdf.cell(45, 7, "Status", 1)
    pdf.cell(90, 7, "Motivo da Reprovacao", 1)
    pdf.ln()

    # Corpo da tabela
    pdf.set_font('Arial', '', 8)
    for medidor in medidores:
        pdf.cell(15, 7, texto_pdf(medidor['pos']), 1)
        pdf.cell(40, 7, texto_pdf(medidor['serie'])[:20], 1)
        pdf.cell(45, 7, texto_pdf(medidor['status'].replace('_', ' ')), 1)
        pdf.cell(90, 7, texto_pdf(medidor['motivo'])[:50], 1)
        pdf.ln()
    
    # Retorna o PDF no formato de 'bytes', que é o que o Streamlit precisa
    return bytes(pdf.output())
