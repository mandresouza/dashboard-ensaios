# =======================================================================
# ARQUIVO: pdf_generator.py (VERSÃO FINAL COMPLETA)
# =======================================================================

from fpdf import FPDF
from datetime import datetime

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Relatorio Tecnico de Ensaios Metrologicos', 0, 1, 'C')
        self.set_font('Arial', '', 12)
        self.cell(0, 7, 'IPEM-AM - Instituto de Pesos e Medidas do Amazonas', 0, 1, 'C')
        self.ln(5)
        self.set_line_width(0.5)
        self.line(x1=10, y1=self.get_y(), x2=200, y2=self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        assinatura = "Criado por: Marcio Souza - Matricula: 743 - Metrologista Especialista"
        assinatura_pdf = str(assinatura).encode('latin-1', 'replace').decode('latin-1')
        self.cell(0, 5, assinatura_pdf, 0, 0, 'L')
        self.set_x(-40)
        self.cell(0, 5, f'Pagina {self.page_no()}', 0, 0, 'R')

def gerar_pdf_relatorio(ensaios, data, stats):
    pdf = PDF()
    pdf.add_page()
    
    def texto_pdf(txt):
        return str(txt).encode('latin-1', 'replace').decode('latin-1')

    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, "1. Informacoes Gerais", 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(40, 7, texto_pdf("Data do Ensaio:"), 0, 0)
    pdf.cell(0, 7, texto_pdf(data), 0, 1)
    pdf.cell(40, 7, texto_pdf("Data de Emissao:"), 0, 0)
    pdf.cell(0, 7, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), 0, 1)
    pdf.ln(7)

    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, "2. Resumo dos Resultados Filtrados", 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(60, 8, texto_pdf(f"Total de Medidores: {stats['total']}"), 1, 0, 'C')
    pdf.cell(60, 8, texto_pdf(f"Aprovados: {stats['aprovados']}"), 1, 0, 'C')
    pdf.cell(70, 8, texto_pdf(f"Reprovados: {stats['reprovados'] + stats['consumidor']}"), 1, 1, 'C')
    pdf.ln(7)

    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, "3. Detalhamento dos Ensaios e Medidores", 0, 1)
    
    item_num = 1
    for ensaio in ensaios:
        pdf.set_fill_color(240, 242, 246)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, texto_pdf(f"Ensaio #{ensaio['n_ensaio']} | Bancada: {ensaio['bancada']} | Temperatura: {ensaio['temperatura']}"), 1, 1, 'L', fill=True)
        
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(15, 7, "Item", 1, 0, 'C') 
        pdf.cell(40, 7, "Numero de Serie", 1, 0, 'C')
        pdf.cell(45, 7, "Resultado Final", 1, 0, 'C')
        pdf.cell(90, 7, "Motivo da Reprovacao", 1, 1, 'C')

        pdf.set_font('Arial', '', 8)
        for medidor in ensaio['medidores']:
            pdf.cell(15, 7, str(item_num), 1, 0, 'C')
            pdf.cell(40, 7, texto_pdf(medidor['serie'])[:20], 1)
            pdf.cell(45, 7, texto_pdf(medidor['status'].replace('_', ' ')), 1)
            pdf.cell(90, 7, texto_pdf(medidor['motivo'])[:50], 1)
            pdf.ln()
            item_num += 1
        pdf.ln(5)

    return bytes(pdf.output())
