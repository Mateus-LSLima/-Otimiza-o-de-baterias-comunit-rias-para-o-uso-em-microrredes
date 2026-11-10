import os
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def create_word_report():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    res_dir = os.path.join(base_dir, 'Resultados de Otimizacao')
    doc_path = os.path.join(res_dir, 'Resultados_Otimizacao_BESS.docx')

    doc = Document()

    # Configuração de Margens (2 cm / 0.8 in)
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    def set_cell_background(cell, fill_hex):
        shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
        cell._tc.get_or_add_tcPr().append(shading_elm)

    # Título Principal
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(4)
    title_run = title_p.add_run('Resultados da Otimização BESS: Análise Temporal Completa')
    title_run.font.name = 'Calibri'
    title_run.font.size = Pt(22)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(16, 44, 87)

    # Subtítulo
    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_after = Pt(14)
    sub_run = sub_p.add_run('Cenário de Benchmark Ideal (Pyomo / GLPK) — Microrrede Comunitária de Austin (Texas)')
    sub_run.font.name = 'Calibri'
    sub_run.font.size = Pt(13)
    sub_run.font.color.rgb = RGBColor(80, 80, 80)
    sub_run.font.italic = True

    # Introdução
    intro_p = doc.add_paragraph(
        'Este documento consolida os resultados do modelo de otimização determinística do Sistema de Armazenamento de Energia em Baterias '
        '(BESS comunitário centralizado de 200 kWh de capacidade e inversor de 50 kW). A formulação matemática baseada em Programação Linear Inteira Mista (MILP) '
        'resolveu o problema de nivelamento de carga (Load Leveling: Peak Shaving e Valley Filling) em blocos diários de 24 horas contínuos ao longo de todo o ano de 2018.'
    )
    intro_p.paragraph_format.space_after = Pt(14)
    intro_p.paragraph_format.line_spacing = 1.15

    # Dados das Seções
    sections_data = [
        {
            'title': '1. Visão de Curto Prazo (1 Semana: 02/Jul a 09/Jul/2018)',
            'img': 'grafico5_1semana.png',
            'desc': 'A escala de 1 semana (168 horas consecutivas) permite observar a repetibilidade dos ciclos diários de carga e descarga, demonstrando o comportamento suave do Estado de Carga (SOC) e a pronta resposta do inversor.',
            'bullets': [
                'Pico Original de Demanda (Net Load): 96,25 kW',
                'Pico Controlado com Bateria (Grid Exchange): 65,63 kW',
                'Redução Absoluta do Pico: -30,62 kW (Redução de 31,8%)',
                'Atuação de Valley Filling: Recarga completa durante o excesso de geração solar entre 11h e 15h.',
                'Terminal SOC: Bateria preserva 50% de energia à meia-noite para assegurar autonomia no dia seguinte.'
            ]
        },
        {
            'title': '2. Visão Mensal (Julho de 2018 — 31 Dias / 744 Horas)',
            'img': 'grafico5_1mes.png',
            'desc': 'Julho representa o período mais crítico do verão texano, com altas temperaturas, radiação solar máxima e intensa solicitação de ar-condicionado residencial.',
            'bullets': [
                'Pico Original no Mês: 96,25 kW | Pico Nivelado com Bateria: 66,88 kW (Redução de 30,5%)',
                'Robustez Numérica: Convergência ótima garantida pelo GLPK para todos os 31 dias.',
                'Adaptação Dinâmica: Em dias de forte insolação e consumo moderado, o patamar é achatado para a faixa de 35 a 45 kW; em dias de onda de calor severa, o teto se estabiliza em ~66 kW.'
            ]
        },
        {
            'title': '3. Análise Sazonal — 1º Trimestre (Jan a Mar / 2018 — Inverno)',
            'img': 'grafico_trimestre1_jan_mar.png',
            'desc': 'No 1º Trimestre (90 dias / 2.160 horas), as baixas temperaturas reduzem o consumo de refrigeração e dias de céu limpo provocam sobreinjeção solar severa na rede.',
            'bullets': [
                'Net Load Mínimo (Injeção Solar Líquida): Atinge -60,50 kW ao meio-dia.',
                'Pico Original: 51,04 kW | Pico com BESS: 32,25 kW (Redução de 36,8%).',
                'Aproveitamento de Energia: A bateria estoca o excedente fotovoltaico que seria exportado a baixo valor para cobrir picos noturnos de aquecimento.'
            ]
        },
        {
            'title': '4. Análise Sazonal — 2º Trimestre (Abr a Jun / 2018 — Primavera)',
            'img': 'grafico_trimestre2_abr_jun.png',
            'desc': 'O 2º Trimestre (91 dias / 2.184 horas) marca a transição climática entre a primavera amena e o início do verão rigoroso.',
            'bullets': [
                'Comportamento Térmico: Em abril e início de maio o consumo é baixo (~40 kW); a partir de junho, o calor eleva os picos para quase 95 kW.',
                'Pico Original: 94,94 kW | Pico com BESS: 64,53 kW (Redução de 32,0%).',
                'Despacho Proporcional: O otimizador eleva progressivamente o patamar diário de descarga conforme o aquecimento sazonal avança.'
            ]
        },
        {
            'title': '5. Análise Sazonal — 3º Trimestre (Jul a Set / 2018 — Verão)',
            'img': 'grafico_trimestre3_jul_set.png',
            'desc': 'O 3º Trimestre (92 dias / 2.208 horas) é a época de estresse extremo da microrrede e da concessionária do Texas (ERCOT).',
            'bullets': [
                'Pico Máximo Anual: 99,21 kW registrado no horário nobre de consumo residencial (17h - 20h).',
                'Pico com BESS: 67,69 kW (Redução de -31,52 kW ou 31,8%).',
                'Potência do Inversor: Opera próximo de 45 kW na descarga durante os picos vespertinos sustentados.'
            ]
        },
        {
            'title': '6. Análise Sazonal — 4º Trimestre (Out a Dez / 2018 — Outono)',
            'img': 'grafico_trimestre4_out_dez.png',
            'desc': 'No 4º Trimestre (92 dias / 2.208 horas), as temperaturas arrefecem e a microrrede retoma a moderação de demanda.',
            'bullets': [
                'Pico Original: 75,93 kW | Pico com BESS: 48,03 kW (Redução de 36,7%).',
                'Net Load Mínimo: -51,87 kW nos finais de semana de forte geração solar.',
                'Estabilidade Global: Bateria opera com alta confiabilidade e oscilação de SOC sem sobredescargas.'
            ]
        }
    ]

    for sec in sections_data:
        h = doc.add_heading(sec['title'], level=1)
        h.paragraph_format.space_before = Pt(16)
        h.paragraph_format.space_after = Pt(6)
        for r in h.runs:
            r.font.name = 'Calibri'
            r.font.color.rgb = RGBColor(24, 76, 120)
            
        p = doc.add_paragraph(sec['desc'])
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.15
        
        # Adiciona a imagem se existir
        img_path = os.path.join(res_dir, sec['img'])
        if os.path.exists(img_path):
            img_p = doc.add_paragraph()
            img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            img_p.paragraph_format.space_before = Pt(4)
            img_p.paragraph_format.space_after = Pt(6)
            img_run = img_p.add_run()
            img_run.add_picture(img_path, width=Inches(6.8))
            
            cap = doc.add_paragraph()
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.paragraph_format.space_after = Pt(8)
            cap_run = cap.add_run(f'Figura: {sec["title"]}')
            cap_run.font.size = Pt(9.5)
            cap_run.font.italic = True
            cap_run.font.color.rgb = RGBColor(100, 100, 100)
            
        # Bullets
        for b in sec['bullets']:
            bp = doc.add_paragraph(style='List Bullet')
            bp.paragraph_format.space_after = Pt(2)
            bp.paragraph_format.line_spacing = 1.15
            parts = b.split(':', 1)
            if len(parts) == 2:
                r_bold = bp.add_run(parts[0] + ':')
                r_bold.bold = True
                bp.add_run(parts[1])
            else:
                bp.add_run(b)
                
        doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # Tabela Síntese
    h_tab = doc.add_heading('7. Síntese Quantitativa de Desempenho do BESS', level=1)
    h_tab.paragraph_format.space_before = Pt(18)
    h_tab.paragraph_format.space_after = Pt(8)
    for r in h_tab.runs:
        r.font.name = 'Calibri'
        r.font.color.rgb = RGBColor(24, 76, 120)

    table_data = [
        ['Período / Escala', 'Horas', 'Pico Original', 'Pico com BESS', 'Redução (kW)', 'Redução (%)', 'Menor Net Load'],
        ['1 Semana (Julho)', '168 h', '96,25 kW', '65,63 kW', '-30,62 kW', '31,8%', '-20,08 kW'],
        ['1 Mês (Julho)', '744 h', '96,25 kW', '66,88 kW', '-29,37 kW', '30,5%', '-20,08 kW'],
        ['T1: Inverno (Jan - Mar)', '2.160 h', '51,04 kW', '32,25 kW', '-18,79 kW', '36,8%', '-60,50 kW'],
        ['T2: Primavera (Abr - Jun)', '2.184 h', '94,94 kW', '64,53 kW', '-30,41 kW', '32,0%', '-58,74 kW'],
        ['T3: Verão (Jul - Set)', '2.208 h', '99,21 kW', '67,69 kW', '-31,52 kW', '31,8%', '-49,33 kW'],
        ['T4: Outono (Out - Dez)', '2.208 h', '75,93 kW', '48,03 kW', '-27,90 kW', '36,7%', '-51,87 kW']
    ]

    table = doc.add_table(rows=len(table_data), cols=7)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    col_widths = [Inches(1.8), Inches(0.7), Inches(1.0), Inches(1.0), Inches(1.0), Inches(0.9), Inches(1.0)]

    for i, row in enumerate(table.rows):
        for j, cell in enumerate(row.cells):
            cell.width = col_widths[j]
            cell.text = table_data[i][j]
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            run = p.runs[0]
            run.font.name = 'Calibri'
            run.font.size = Pt(9.5)
            
            if i == 0:
                set_cell_background(cell, '102C57')
                run.font.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                if i % 2 == 1:
                    set_cell_background(cell, 'F2F4F8')
                else:
                    set_cell_background(cell, 'FFFFFF')
                if j == 0:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    run.font.bold = True
                else:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.save(doc_path)
    print(f"Documento Word salvo com sucesso em: {doc_path}")

if __name__ == '__main__':
    create_word_report()
