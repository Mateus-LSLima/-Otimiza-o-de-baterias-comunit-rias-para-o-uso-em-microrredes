# Relatório de Resultados - Otimizador Puramente Monetário ERCOT (RTW + TDSP)

## 1. Parâmetros Regulatórios e de Mercado Utilizados
- **Operador de Mercado / Zona de Liquidação:** ERCOT Day-Ahead Market (DAM) — `LZ_AEN` (Austin Energy, 2018)
- **Modalidade Tarifária:** Real-Time Wholesale (RTW) com repasse de taxa de fio (TDSP) na importação:
  - **Preço de Venda / Exportação (`sell_price[t]`):** 100% do preço spot horário do ERCOT (`ercot_spp_usd_kwh[t]`)
  - **Preço de Compra / Importação (`buy_price[t]`):** `ercot_spp_usd_kwh[t]` + **US\$ 0,01896 / kWh** (*Regulatory Charge* US\$ 0,01342 + *Community Benefit* US\$ 0,00554 da Austin Energy)
  - **Autoconsumo Local (*Behind-the-Meter*):** Isento de compra na rede e isento da taxa TDSP
- **Critério Secundário de Desempate (Tie-breaker):** Micro-peso (`1e-6 US$/kW`) sobre `P_max - P_min`

## 2. Resumo Financeiro e Operacional por Horizonte

| Horizonte Simulado | Custo Sem BESS (US\$) | Custo/Saldo Com BESS (US\$) | Economia / Lucro Gerado (US\$) | Economia (%) | Spot Máx (US\$/kWh) | Pico Original (kW) | Pico Com BESS (kW) | Arquivo de Gráfico |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 1 Semana Padrão (02/Jul a 09/Jul) | US\$ 293.49 | US\$ 239.96 | **US\$ 53.53** | **18.2%** | US\$ 0.162 | 96.25 | 97.22 | `grafico_ercot_1semana.png` |
| 1 Semana Onda de Calor (16/Jul a 23/Jul) | US\$ 1,181.76 | US\$ 13.30 | **US\$ 1,168.46** | **98.9%** | US\$ 1.879 | 94.98 | 98.23 | `grafico_ercot_1semana_onda_calor.png` |
| 1 Mês Completo (Julho/2018) | US\$ 2,668.57 | US\$ 828.80 | **US\$ 1,839.77** | **68.9%** | US\$ 2.061 | 96.25 | 110.46 | `grafico_ercot_1mes.png` |
| 1º Trimestre (Jan a Mar / 2018 - Inverno) | US\$ 1,621.66 | US\$ 1,052.45 | **US\$ 569.21** | **35.1%** | US\$ 1.661 | 51.04 | 86.84 | `grafico_ercot_trimestre1_jan_mar.png` |
| 2º Trimestre (Abr a Jun / 2018 - Primavera) | US\$ 2,414.58 | US\$ 1,848.96 | **US\$ 565.62** | **23.4%** | US\$ 0.529 | 94.94 | 120.99 | `grafico_ercot_trimestre2_abr_jun.png` |
| 3º Trimestre (Jul a Set / 2018 - Verão) | US\$ 5,111.95 | US\$ 2,959.11 | **US\$ 2,152.83** | **42.1%** | US\$ 2.061 | 99.21 | 141.61 | `grafico_ercot_trimestre3_jul_set.png` |
| 4º Trimestre (Out a Dez / 2018 - Outono) | US\$ 1,820.45 | US\$ 1,452.71 | **US\$ 367.74** | **20.2%** | US\$ 0.117 | 75.93 | 90.27 | `grafico_ercot_trimestre4_out_dez.png` |
| **Total Anual (2018 Completo - 365 dias)** | **US\$ 10,968.63** | **US\$ 7,313.22** | **US\$ 3,655.41** | **33.3%** | **US\$ 2.061** | - | - | - |
