import matplotlib.pyplot as plt

# Configuracao de estilo visual identico ao grafico da Tarifa Branca
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 7.5), dpi=300)
plt.subplots_adjust(hspace=0.55, left=0.06, right=0.96, top=0.90, bottom=0.08)

c_low = '#2980b9'    # Azul - Vale de precos (Off-Peak / Madrugada)
c_mid = '#f39c12'    # Laranja - Preco intermediario (Dia)
c_peak = '#c0392b'   # Vermelho - Pico de preco atacadista (On-Peak / Tarde)

# -------------------------------------------------------------
# 1. DIAS UTEIS (Segunda a Sexta) - ERCOT DAM 2018 (Austin / LZ_AUSTIN)
# -------------------------------------------------------------
ax1.set_title('MERCADO ATACADISTA DE AUSTIN (ERCOT DAM 2018) - DIAS ÚTEIS', fontsize=15, fontweight='bold', pad=15, color='#2c3e50')
ax1.set_xlim(0, 24)
ax1.set_ylim(0, 2.0)

# Faixas horarias caracteristicas do mercado atacadista do Texas
ax1.barh(0.7, 6.0, left=0, height=0.65, color=c_low, edgecolor='white', linewidth=2)
ax1.barh(0.7, 9.0, left=6.0, height=0.65, color=c_mid, edgecolor='white', linewidth=2)
ax1.barh(0.7, 5.0, left=15.0, height=0.65, color=c_peak, edgecolor='white', linewidth=2)
ax1.barh(0.7, 4.0, left=20.0, height=0.65, color=c_low, edgecolor='white', linewidth=2)

# Textos informativos (usando r'\$' para evitar formatacao LaTeX math indesejada)
ax1.text(3.0, 0.7, 'VALE NOTURNO\n~US\\$ 20 / MWh\n(US\\$ 0,020 / kWh)\n[Vento forte Texas]',
         ha='center', va='center', color='white', fontweight='bold', fontsize=10.5)

ax1.text(10.5, 0.7, 'DIURNO / SOLAR\n~US\\$ 32 / MWh\n(US\\$ 0,032 / kWh)\n[Preço estável com solar]',
         ha='center', va='center', color='white', fontweight='bold', fontsize=10.5)

ax1.text(17.5, 0.7, 'PICO DO ATACADO (PICO TÉRMICO)\n~US\\$ 85 a 250+ / MWh\n(US\\$ 0,085 a 0,25+/kWh)\n[Picos de calor Julho/Agosto]',
         ha='center', va='center', color='white', fontweight='bold', fontsize=9.5)

ax1.text(22.0, 0.7, 'DESACELERAÇÃO\n~US\\$ 30 / MWh\n(US\\$ 0,030 / kWh)',
         ha='center', va='center', color='white', fontweight='bold', fontsize=9.5)

# Anotacoes explicativas para a operacao do BESS
ax1.annotate('Recarga Econômica do BESS (01h às 05h)\n• Compra no menor preço spot da rede\n• Armazena energia barata de fontes eólicas',
             xy=(3.0, 1.05), xytext=(3.5, 1.62),
             ha='center', fontsize=9.5, fontweight='bold', color='#2980b9',
             arrowprops=dict(arrowstyle='->', color='#2980b9', lw=2))

ax1.annotate('Descarga e Arbitragem Máxima (16h às 19h)\n• Injeção nos picos extremos de preço da rede\n• Lucro multiplicado em ondas de calor no Texas!',
             xy=(17.5, 1.05), xytext=(17.5, 1.62),
             ha='center', fontsize=9.5, fontweight='bold', color='#c0392b',
             arrowprops=dict(arrowstyle='->', color='#c0392b', lw=2))

ax1.set_xticks(range(0, 25))
ax1.set_xticklabels([f'{h:02d}h' for h in range(25)], fontsize=11)
ax1.set_yticks([])
ax1.grid(axis='x', linestyle=':', alpha=0.6)

# -------------------------------------------------------------
# 2. FINAIS DE SEMANA - ERCOT DAM 2018
# -------------------------------------------------------------
ax2.set_title('MERCADO ATACADISTA DE AUSTIN (ERCOT DAM 2018) - FINAIS DE SEMANA', fontsize=15, fontweight='bold', pad=15, color='#2c3e50')
ax2.set_xlim(0, 24)
ax2.set_ylim(0, 1.4)

ax2.barh(0.5, 7.0, left=0, height=0.65, color=c_low, edgecolor='white', linewidth=2)
ax2.barh(0.5, 17.0, left=7.0, height=0.65, color=c_mid, edgecolor='white', linewidth=2)

ax2.text(3.5, 0.5, 'VALE DA MADRUGADA\n~US\\$ 18 / MWh (US\\$ 0,018 / kWh)',
         ha='center', va='center', color='white', fontweight='bold', fontsize=11)

ax2.text(15.5, 0.5, 'CONSUMO REDUZIDO NO FIM DE SEMANA (COMÉRCIO/INDÚSTRIA FECHADOS)\nPreço Médio Contínuo: ~US\\$ 25 a US\\$ 32 / MWh (US\\$ 0,025 a 0,032 / kWh) — Sem Grandes Picos Térmicos',
         ha='center', va='center', color='white', fontweight='bold', fontsize=11)

ax2.set_xticks(range(0, 25))
ax2.set_xticklabels([f'{h:02d}h' for h in range(25)], fontsize=11)
ax2.set_yticks([])
ax2.grid(axis='x', linestyle=':', alpha=0.6)

plt.savefig('data/3_otimizador_ercot_atacado/imagens/grafico_austin_atacadista_ercot_2018.png', dpi=300, bbox_inches='tight')
print('OK')
