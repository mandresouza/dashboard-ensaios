from fpdf import FPDF
from datetime import datetime

# Esta classe define o cabeçalho e rodapé do nosso PDF
class PDF(FPDF):
    # Cabeçalho aprimorado
    def header(self):
        # 1. Adicionar um logo (opcional, se você tiver um link para a imagem)
        # Exemplo: self.image('URL_DA_IMAGEM_DO_LOGO.png', x=10, y=8, w=33)
        # Como não temos um logo, vamos pular esta linha por enquanto.
        
        # 2. Título principal
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Relatorio Tecnico de Ensaios Metrologicos', 0, 1, 'C')
        
        # 3. Subtítulo com o nome da instituição
        self.set_font('Arial', '', 12)
        self.cell(0, 7, 'IPEM-AM - Instituto de Pesos e Medidas do Amazonas', 0, 1, 'C')
        
        # 4. Linha horizontal para separar o cabeçalho do conteúdo
        self.ln(5) # Pula uma linha antes da linha horizontal
        self.set_line_width(0.5)
        self.line(x1=10, y1=self.get_y(), x2=200, y2=self.get_y())
        self.ln(5) # Pula uma linha depois da linha horizontal

    # Rodapé não foi alterado
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

    # --- Seção 1: Informações Gerais do Relatório ---
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, "1. Informacoes Gerais", 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(40, 7, texto_pdf("Data do Ensaio:"), 0, 0)
    pdf.cell(0, 7, texto_pdf(data), 0, 1)
    pdf.cell(40, 7, texto_pdf("Bancada(s) Analisada(s):"), 0, 0)
    pdf.cell(0, 7, texto_pdf(bancada), 0, 1)
    pdf.cell(40, 7, texto_pdf("Data de Emissao:"), 0, 0)
    pdf.cell(0, 7, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), 0, 1)
    pdf.ln(7)

    # --- Seção 2: Resumo Quantitativo ---
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, "2. Resumo dos Resultados", 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(60, 8, texto_pdf(f"Total de Medidores: {stats['total']}"), 1, 0, 'C')
    pdf.cell(60, 8, texto_pdf(f"Aprovados: {stats['aprovados']}"), 1, 0, 'C')
    pdf.cell(70, 8, texto_pdf(f"Reprovados: {stats['reprovados'] + stats['consumidor']}"), 1, 1, 'C')
    pdf.ln(7)

    # --- Seção 3: Detalhamento dos Medidores ---
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, "3. Detalhamento dos Medidores", 0, 1)
    pdf.set_font('Arial', 'B', 9)
    
    # MUDANÇA: A coluna agora se chama "Item"
    pdf.cell(15, 7, "Item", 1, 0, 'C') 
    pdf.cell(40, 7, "Numero de Serie", 1, 0, 'C')
    pdf.cell(45, 7, "Resultado Final", 1, 0, 'C')
    pdf.cell(90, 7, "Motivo da Reprovacao / Observacao", 1, 1, 'C')

    # Corpo da tabela
    pdf.set_font('Arial', '', 8)
    # MUDANÇA: Usamos enumerate para criar um contador sequencial (item_num)
    for item_num, medidor in enumerate(medidores, start=1):
        pdf.cell(15, 7, str(item_num), 1, 0, 'C') # Usando o contador sequencial
        pdf.cell(40, 7, texto_pdf(medidor['serie'])[:20], 1)
        pdf.cell(45, 7, texto_pdf(medidor['status'].replace('_', ' ')), 1)
        pdf.cell(90, 7, texto_pdf(medidor['motivo'])[:50], 1)
        pdf.ln()
    
    # Retorna o PDF no formato de 'bytes', que é o que o Streamlit precisa
    return bytes(pdf.output())
