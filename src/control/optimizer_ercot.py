# ==============================================================================
# OTIMIZADOR 3: MERCADO ATACADISTA ERCOT (REAL-TIME WHOLESALE + TDSP)
# ==============================================================================

import os
import json
import shutil
import numpy as np
import pandas as pd
import pyomo.environ as pyo


class OptimizerErcotBESS:
    """
    Otimizador MILP (Pyomo + GLPK) puramente monetário em US$ para o mercado
    atacadista do Texas (ERCOT DAM - LZ_AEN) sob o modelo RTW + Taxa de Fio (TDSP).

    Fórmula Final do Otimizador:
        min  sum_{t=0..23} (C_buy[t] * P_import[t] - C_sell[t] * P_export[t])
             - V_term * E[23]
             + eps * (P_max - P_min)
        sujeito a:
          - Balanço no Medidor: P_import[t] - P_export[t] == NetLoad[t] + P_ch[t] - P_dis[t]
          - Preços Horários:    C_sell[t] = SPP_ERCOT[t]
                                C_buy[t]  = SPP_ERCOT[t] + C_TDSP
          - Dinâmica de SoC:    E[t] = E[t-1] + (eta * P_ch[t]) - (P_dis[t] / eta)
          - Intertravamento:    0 <= P_ch[t] <= P_max_inv * is_charging[t]
                                0 <= P_dis[t] <= P_max_inv * (1 - is_charging[t])
          - Envelope Desempate: P_min <= NetLoad[t] + P_ch[t] - P_dis[t] <= P_max
    """

    def __init__(
        self,
        capacity_kwh=200.0,
        max_power_kw=50.0,
        soc_min=0.0,
        soc_max=1.0,
        efficiency=0.95,
        tdsp_fee_usd_kwh=0.01896,
        peak_shaving_weight=1e-6,
        tariff_json_path=None,
    ):
        self.capacity_kwh = capacity_kwh
        self.max_power_kw = max_power_kw
        self.soc_min = soc_min
        self.soc_max = soc_max
        self.efficiency = efficiency
        self.tdsp_fee_usd_kwh = tdsp_fee_usd_kwh
        self.peak_shaving_weight = peak_shaving_weight

        # Carrega automaticamente os encargos de fio (Riders) da Austin Energy do JSON
        if tariff_json_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            candidate_paths = [
                os.path.join(base_dir, 'data', '3_otimizador_ercot_atacado', 'dados', 'tariff_parameters_2018_2026.json'),
                os.path.join(base_dir, 'data', 'tariff_parameters_2018_2026.json'),
            ]
            for p in candidate_paths:
                if os.path.exists(p):
                    tariff_json_path = p
                    break

        if tariff_json_path and os.path.exists(tariff_json_path):
            try:
                with open(tariff_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                riders = data['austin_texas']['historical_2018']['residential_retail_rates']['riders_usd_kwh']
                reg_charge = float(riders.get('regulatory_charge', 0.01342))
                comm_charge = float(riders.get('community_benefit_charge', 0.00554))
                self.tdsp_fee_usd_kwh = reg_charge + comm_charge
            except Exception as e:
                print(f"Aviso ao ler JSON de tarifas ERCOT ({e}). Usando TDSP padrão US$ {self.tdsp_fee_usd_kwh:.5f}/kWh.")

    def get_hourly_prices(self, spp_usd_kwh_24h):
        """
        Gera os vetores horários (24h) de preço de compra C_buy[t] e venda C_sell[t] (US$/kWh):
          - C_sell[t] = SPP_ERCOT[t]
          - C_buy[t]  = SPP_ERCOT[t] + C_TDSP
        """
        buy_prices = []
        sell_prices = []
        effective_tdsp = max(1e-7, self.tdsp_fee_usd_kwh)

        for t in range(24):
            spp = float(spp_usd_kwh_24h[t])
            sell_rate = spp
            buy_rate = spp + effective_tdsp
            buy_prices.append(buy_rate)
            sell_prices.append(sell_rate)

        return buy_prices, sell_prices

    def optimize_24h(self, net_load_24h, initial_soc, spp_usd_kwh_24h):
        """
        Resolve o MILP diário de 24h e retorna o plano de potência da bateria: P_ch[t] - P_dis[t] (kW).
        """
        buy_prices, sell_prices = self.get_hourly_prices(spp_usd_kwh_24h)

        model = pyo.ConcreteModel()
        model.T = pyo.RangeSet(0, 23)

        # ----------------------------------------------------------------------
        # 1. Variáveis de Decisão
        # ----------------------------------------------------------------------
        model.P_ch = pyo.Var(model.T, within=pyo.NonNegativeReals, bounds=(0, self.max_power_kw))
        model.P_dis = pyo.Var(model.T, within=pyo.NonNegativeReals, bounds=(0, self.max_power_kw))
        model.E = pyo.Var(
            model.T,
            within=pyo.NonNegativeReals,
            bounds=(self.capacity_kwh * self.soc_min, self.capacity_kwh * self.soc_max),
        )
        model.is_charging = pyo.Var(model.T, within=pyo.Binary)

        # Fluxos separados no medidor bidirecional (compra P_import >= 0 e exportação P_export >= 0) [kW]
        model.P_import = pyo.Var(model.T, within=pyo.NonNegativeReals)
        model.P_export = pyo.Var(model.T, within=pyo.NonNegativeReals)

        # Envelope de demanda (P_max, P_min) para micro-desempate [kW]
        model.P_max = pyo.Var(within=pyo.Reals)
        model.P_min = pyo.Var(within=pyo.Reals)

        # ----------------------------------------------------------------------
        # 2. Restrições (Constraints)
        # ----------------------------------------------------------------------
        # 2.1 Intertravamento Lógico: P_ch[t] <= P_max_inv * is_charging[t]
        def ch_limit_rule(m, t):
            return m.P_ch[t] <= self.max_power_kw * m.is_charging[t]
        model.ch_limit = pyo.Constraint(model.T, rule=ch_limit_rule)

        # Fórmula: P_dis[t] <= P_max_inv * (1 - is_charging[t])
        def dis_limit_rule(m, t):
            return m.P_dis[t] <= self.max_power_kw * (1 - m.is_charging[t])
        model.dis_limit = pyo.Constraint(model.T, rule=dis_limit_rule)

        # 2.2 Dinâmica de Energia: E[t] = E[t-1] + (eta * P_ch[t]) - (P_dis[t] / eta)
        def battery_dynamics_rule(m, t):
            e_prev = (self.capacity_kwh * initial_soc) if t == 0 else m.E[t - 1]
            return m.E[t] == e_prev + (m.P_ch[t] * self.efficiency) - (m.P_dis[t] / self.efficiency)
        model.battery_dynamics = pyo.Constraint(model.T, rule=battery_dynamics_rule)

        # 2.3 Balanço no Medidor: P_import[t] - P_export[t] == NetLoad[t] + P_ch[t] - P_dis[t]
        def grid_balance_rule(m, t):
            return m.P_import[t] - m.P_export[t] == net_load_24h[t] + m.P_ch[t] - m.P_dis[t]
        model.grid_balance = pyo.Constraint(model.T, rule=grid_balance_rule)

        # 2.4 Envelope Min-Max: P_min <= NetLoad[t] + P_ch[t] - P_dis[t] <= P_max
        def p_max_rule(m, t):
            grid_exchange = net_load_24h[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange <= m.P_max
        model.p_max_constraint = pyo.Constraint(model.T, rule=p_max_rule)

        def p_min_rule(m, t):
            grid_exchange = net_load_24h[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange >= m.P_min
        model.p_min_constraint = pyo.Constraint(model.T, rule=p_min_rule)

        # ----------------------------------------------------------------------
        # 3. Função Objetivo (Fórmula Final)
        # ----------------------------------------------------------------------
        # Fórmula do valor residual: V_term = min_t(C_sell[t]) * eta
        terminal_value_per_kwh = max(0.0, min(sell_prices) * self.efficiency)

        # Fórmula Final:
        # min sum_{t=0..23} (C_buy[t] * P_import[t] - C_sell[t] * P_export[t]) - V_term * E[23] + eps * (P_max - P_min)
        def objective_rule(m):
            daily_net_cost_usd = sum(
                (buy_prices[t] * m.P_import[t]) - (sell_prices[t] * m.P_export[t])
                for t in m.T
            )
            terminal_salvage = terminal_value_per_kwh * m.E[23]
            peak_shaving_tiebreaker = self.peak_shaving_weight * (m.P_max - m.P_min)
            return daily_net_cost_usd - terminal_salvage + peak_shaving_tiebreaker

        model.obj = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

        # ----------------------------------------------------------------------
        # 4. Resolução via Solver GLPK
        # ----------------------------------------------------------------------
        if shutil.which('glpsol'):
            solver = pyo.SolverFactory('glpk')
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            local_glpk = os.path.join(base_dir, 'bin', 'glpk', 'glpk-4.65', 'w64', 'glpsol.exe')
            if os.path.exists(local_glpk):
                solver = pyo.SolverFactory('glpk', executable=local_glpk)
            else:
                solver = pyo.SolverFactory('glpk')

        results = solver.solve(model)

        if (results.solver.status != pyo.SolverStatus.ok) or (
            results.solver.termination_condition != pyo.TerminationCondition.optimal
        ):
            print("Aviso: Otimizador ERCOT não encontrou solução ótima!")
            return [0.0] * 24

        bess_power_plan = []
        for t in model.T:
            bess_power_plan.append(pyo.value(model.P_ch[t]) - pyo.value(model.P_dis[t]))

        return bess_power_plan

    def evaluate_hourly_financials(self, net_load_kw, grid_exchange_kw, buy_price, sell_price):
        """
        Calcula o custo horário (US$) sem bateria, com bateria e o balanço líquido da bateria:
        bess_balance_usd = cost_no_bess_usd - cost_with_bess_usd.
        """
        if net_load_kw >= 0:
            cost_no_bess_usd = net_load_kw * buy_price
        else:
            cost_no_bess_usd = net_load_kw * sell_price

        if grid_exchange_kw >= 0:
            cost_with_bess_usd = grid_exchange_kw * buy_price
        else:
            cost_with_bess_usd = grid_exchange_kw * sell_price

        bess_financial_balance_usd = cost_no_bess_usd - cost_with_bess_usd

        return {
            'cost_no_bess_usd': cost_no_bess_usd,
            'cost_with_bess_usd': cost_with_bess_usd,
            'bess_balance_usd': bess_financial_balance_usd,
        }


if __name__ == "__main__":
    dummy_net_load = [
        35, 30, 27, 25, 24, 26, 30, 28,
        15, -10, -35, -50, -45, -25, 5, 35,
        65, 85, 95, 90, 75, 60, 48, 40
    ]
    dummy_ercot_spp_kwh = [
        0.024, 0.020, 0.018, 0.017, 0.018, 0.021, 0.025, 0.028,
        0.030, 0.032, 0.035, 0.042, 0.055, 0.085, 0.140, 0.280,
        0.450, 0.380, 0.190, 0.095, 0.055, 0.038, 0.030, 0.026
    ]

    opt = OptimizerErcotBESS(capacity_kwh=200.0, max_power_kw=50.0)
    buy_p, sell_p = opt.get_hourly_prices(dummy_ercot_spp_kwh)
    plan = opt.optimize_24h(dummy_net_load, initial_soc=0.0, spp_usd_kwh_24h=dummy_ercot_spp_kwh)

    print("=== TESTE DO OTIMIZADOR PURAMENTE MONETÁRIO ERCOT (RTW + TDSP) ===")
    print(f"Taxa de Fio TDSP aplicada na importação: US$ {opt.tdsp_fee_usd_kwh:.5f}/kWh")
    total_no_bess = 0.0
    total_with_bess = 0.0
    soc_energy = 0.0
    for t, p in enumerate(plan):
        if p > 0:
            soc_energy += p * opt.efficiency
        else:
            soc_energy += p / opt.efficiency
        grid_ex = dummy_net_load[t] + p
        fin = opt.evaluate_hourly_financials(dummy_net_load[t], grid_ex, buy_p[t], sell_p[t])
        total_no_bess += fin['cost_no_bess_usd']
        total_with_bess += fin['cost_with_bess_usd']
        print(
            f"Hora {t:02d}h | Compra: ${buy_p[t]:.4f} (Spot: ${sell_p[t]:.4f}) | "
            f"NetLoad: {dummy_net_load[t]:+6.1f} kW | BESS: {p:+6.1f} kW (SoC: {soc_energy/200*100:5.1f}%) | "
            f"Grid: {grid_ex:+6.1f} kW | Balanço BESS: US$ {fin['bess_balance_usd']:+6.2f}"
        )
    print("--------------------------------------------------------------------------")
    print(f"Custo Diário SEM Bateria: US$ {total_no_bess:.2f}")
    print(f"Custo Diário COM Bateria: US$ {total_with_bess:.2f}")
    print(f"Economia / Lucro Gerado : US$ {total_no_bess - total_with_bess:.2f}")
