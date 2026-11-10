# Levantamento de Dados Tarifários e Regras Regulatórias: Austin (EUA) vs. CPFL Paulista (Brasil)

**Projeto:** TCC - Previsão de Carga/Geração Solar e Otimização de Bateria em Microrrede  
**Data do Levantamento:** Outubro de 2026  
**Arquivo de Parâmetros Estruturado:** `data/tariff_parameters_2018_2026.json`

---

## 1. Austin, Texas (Austin Energy & ERCOT)

### 1.1 Tarifas Históricas de 2018 (Alinhadas ao Dataset Pecan Street)
* **Concessionária:** Austin Energy (concessionária pública municipal de Austin, TX).
* **Operador do Sistema Elétrico:** ERCOT (Electric Reliability Council of Texas).
* **Regra de Faturamento do Consumo (Importação da Rede):**
  * Modelo em 4 patamares de consumo mensal (*Four-Tier Inverted Block Rates*):
    * **Tier 1 (0 a 300 kWh):** $0.02801 / kWh
    * **Tier 2 (301 a 900 kWh):** $0.05832 / kWh
    * **Tier 3 (901 a 2.000 kWh):** $0.07814 / kWh
    * **Tier 4 (> 2.000 kWh):** $0.09314 / kWh
  * Taxa fixa mensal de conexão (*Customer Charge*): **$17,35 / mês**.
  * Encargos variáveis adicionais (*Riders*):
    * Ajuste de Fornecimento (*Power Supply Adjustment - PSA*): ~$0.02897 / kWh
    * Encargo Regulatório ERCOT (*Regulatory Charge*): ~$0.01342 / kWh
    * Encargos de Benefício Comunitário (*Community Benefit Charges*): ~$0.00554 / kWh
  * **Tarifa Residencial Média Efetiva:** **~US$ 0,108 / kWh**.
* **Regra Real de Injeção Solar (Exportação) — *Value of Solar (VoS)*:**
  * Austin Energy utiliza o modelo pioneiro de **Medição Bruta** (*Gross Metering* / *Buy All, Sell All*):
    * Todo o consumo da residência é medido e faturado pela tarifa regular.
    * 100% da geração solar fotovoltaica recebe um crédito monetário na fatura pelo valor do VoS.
  * **Valor Homologado em 2018:** **US$ 0,097 / kWh (9,7 ¢/kWh)**.
* **Mercado Atacadista ERCOT 2018 (Arbitragem de Bateria):**
  * Zona de Carga: `LZ_AUSTIN`
  * Relatório Oficial ERCOT: *DAM Settlement Point Prices* (EMIL ID `NP4-180-ER`, Relatório `13060`).
  * Link: [ERCOT Data Products: NP4-180-ER](https://www.ercot.com/mp/data-products/data-product-details?id=NP4-180-ER)

### 1.2 Regras Regulatórias Reais de 2026
* **Atualização do Value of Solar:**
  * O crédito de geração solar residencial foi atualizado para **US$ 0,1289 / kWh (12,89 ¢/kWh)**.
* **Programa Real de Baterias Residenciais (Virtual Power Plant - VPP):**
  * Programa: **Austin Energy Power Partner Battery Program**.
  * Incentivo Financeiro Inicial (*Upfront Rebate*): **US$ 500,00** por sistema aprovado.
  * Remuneração de Desempenho Anual (*Annual Performance Payment*): **~US$ 75,00 / kW instalado**.
  * Despacho Operacional:
    * Até **40 eventos por ano** disparados pela concessionária nos horários de estresse da rede.
    * Duração de **2 a 3 horas** por evento.
    * A bateria supre primeiro as cargas essenciais da residência; o excedente é injetado na rede.
    * Garantia de reserva mínima de segurança configurada pelo proprietário para emergências/apagões.

---

## 2. Brasil (CPFL Paulista & ANEEL)

### 2.1 Tarifas Históricas de 2018 (Resolução Homologatória ANEEL nº 2.381/2018)
* **Concessionária:** CPFL Paulista (área de concessão de Campinas e região da Unicamp).
* **Agência Reguladora:** ANEEL (Agência Nacional de Energia Elétrica).
* **Estrutura da Tarifa Branca (Classe B1 - Residencial):**
  * **Posto Ponta (18h00 às 20h59 nos dias úteis):** **R$ 1,299 / kWh**
  * **Posto Intermediário (16h00 às 17h59 e 21h00 às 21h59 nos dias úteis):** **R$ 0,883 / kWh**
  * **Posto Fora de Ponta (22h00 às 15h59 nos dias úteis; 24h sábados, domingos e feriados):** **R$ 0,625 / kWh**
  * **Tarifa Convencional de Referência (Preço único 24h):** **R$ 0,739 / kWh**
* **Regra de Injeção e Compensação de 2018 (ANEEL RN 482/2012):**
  * O consumidor acumula **créditos de energia em kWh** no Sistema de Compensação de Energia Elétrica (SCEE).
  * **Fator de Conversão / Relação de Tarifas:**  
    $$\text{Créditos na Ponta} = E_{\text{injetada (Fora de Ponta)}} \times \left( \frac{\text{Tarifa}_{\text{Fora Ponta}}}{\text{Tarifa}_{\text{Ponta}}} \right)$$
    $$\text{Fator} = \frac{0,625}{1,299} \approx 0,481$$
  * *Conclusão:* 1 kWh solar injetado no período diurno compensa apenas **~0,48 kWh** do consumo da noite.

### 2.2 Regras Regulatórias Reais de 2026 (Marco Legal da GD)
* **Base Legal:** **Lei Federal nº 14.300/2022** e **Resolução Normativa ANEEL nº 1.000/2021**.
* **Cobrança do Fio B em 2026 (Art. 27 da Lei 14.300/2022):**
  * Para unidades conectadas sob as novas regras (GD II), a transição tarifária atinge:
    * 2023: 15% | 2024: 30% | 2025: 45% | **2026: 60% do Fio B**.
  * Portanto, sobre cada kWh injetado na rede pública, há o desconto de **60% da componente TUSD Fio B**.
* **Impacto Econômico da Bateria Comunitária em 2026:**
  1. **Autoconsumo Atrás do Medidor (*Behind-the-Meter*):** Toda a energia solar armazenada e consumida internamente **não passa pelo medidor**, economizando 100% da tarifa cheia e ficando totalmente isenta do Fio B.
  2. **Arbitragem Horária Evitando Depreciação:** A bateria descarrega no horário de Ponta (18h-21h), abatendo o consumo no momento de maior valor tarifário (R$ 1,30/kWh), sem sofrer a perda de 52% decorrente da relação de tarifas entre Fora de Ponta e Ponta.

---

## 3. Síntese Comparativa

| Critério | Austin, Texas (EUA) | CPFL Paulista (Brasil) |
| :--- | :--- | :--- |
| **Tarifa de Compra (2018)** | Média volumétrica em 4 patamares (~US$ 0,108/kWh) | Tarifa Branca horária: Ponta R$ 1,30 / Fora Ponta R$ 0,62 |
| **Venda/Injeção Solar (2018)** | Crédito fixo *Value of Solar* (US$ 0,097/kWh) | Compensação em créditos com fator de ajuste (~0,481) |
| **Regulação Vigente em 2026** | *Power Partner Battery Program* (VPP + incentivo $75/kW) | Marco Legal Lei 14.300/2022 (cobrança de 60% do Fio B) |
| **Papel Principal da Bateria** | Redução do pico comunitário + participação em eventos VPP | Evitar Fio B e desvalorização do crédito solar na ponta |
