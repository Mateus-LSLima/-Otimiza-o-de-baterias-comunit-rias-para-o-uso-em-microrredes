# ==============================================================================
# OTIMIZADOR 2: TARIFA BRANCA BRASILEIRA (CPFL PAULISTA) + FIO B (LEI 14.300)
# ==============================================================================

import os
import json
import shutil
import numpy as np
import pandas as pd
import pyomo.environ as pyo


class OptimizerTariffBESS:
    """
    Otimizador MILP (Pyomo + GLPK) para minimização do custo diário (24h) em R$
    sob a Tarifa Branca (CPFL Paulista) e cobrança de 60% do Fio B na exportação.

    Fórmula Final do Otimizador:
        min  sum_{t=0..23} (C_buy[t] * P_import[t] - C_sell[t] * P_export[t])
             - V_res * E[23]
             + eps * (P_max - P_min)
        sujeito a:
          - Balanço no Medidor: P_import[t] - P_export[t] == NetLoad[t] + P_ch[t] - P_dis[t]
          - Preço de Venda:     C_sell[t] = C_buy[t] - (0.60 * TUSD_FioB)
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
        tusd_fio_b_brl=0.180,
        fio_b_pct=0.60,
        peak_shaving_weight=1e-3,
        tariff_json_path=None,
    ):
        self.capacity_kwh = capacity_kwh
        self.max_power_kw = max_power_kw
        self.soc_min = soc_min
        self.soc_max = soc_max
        self.efficiency = efficiency
        self.peak_shaving_weight = peak_shaving_weight

        # Tarifas padrão CPFL Paulista (R$/kWh): Ponta (18-21h), Intermediário (16-18h, 21-22h) e Fora de Ponta
        self.rate_ponta = 1.299
        self.rate_intermediario = 0.883
        self.rate_fora_ponta = 0.625
        self.fio_b_pct = fio_b_pct
        self.tusd_fio_b_brl = tusd_fio_b_brl

        # Carrega automaticamente do JSON de parâmetros tarifários do projeto
        if tariff_json_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            candidate_paths = [
                os.path.join(base_dir, 'data', '2_otimizador_tarifa_branca_brasil', 'dados', 'tariff_parameters_2018_2026.json'),
                os.path.join(base_dir, 'data', 'tariff_parameters_2018_2026.json'),
            ]
            for cp in candidate_paths:
                if os.path.exists(cp):
                    tariff_json_path = cp
                    break

        if tariff_json_path and os.path.exists(tariff_json_path):
            try:
                with open(tariff_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                tb = data['brasil_cpfl']['historical_2018']['tarifa_branca_b1_residencial']['postos_horarios_dias_uteis']
                self.rate_ponta = float(tb['ponta']['tarifa_aplicada_brl_kwh'])
                self.rate_intermediario = float(tb['intermediario']['tarifa_aplicada_brl_kwh'])
                self.rate_fora_ponta = float(tb['fora_de_ponta']['tarifa_aplicada_brl_kwh'])
                self.fio_b_pct = float(data['brasil_cpfl']['regulations_2026']['percentual_fio_b_ano_2026'])
            except Exception as e:
                print(f"Aviso ao ler JSON de tarifas ({e}). Usando parâmetros padrão.")

        # Parcela não compensável do Fio B na injeção/exportação (R$/kWh)
        self.fio_b_cost_brl = self.tusd_fio_b_brl * self.fio_b_pct

    def get_hourly_tariffs(self, timestamps_24h=None, is_weekend=False):
        """
        Gera os vetores horários (24h) de preço de compra C_buy[t] e venda C_sell[t] (R$/kWh).
        """
        buy_prices = []
        sell_prices = []

        for t in range(24):
            if timestamps_24h is not None:
                ts = pd.Timestamp(timestamps_24h[t])
                hour = ts.hour
                weekend_flag = ts.weekday() >= 5
            else:
                hour = t
                weekend_flag = is_weekend

            if weekend_flag:
                buy_rate = self.rate_fora_ponta
            else:
                if 18 <= hour <= 20:
                    buy_rate = self.rate_ponta
                elif (16 <= hour <= 17) or (hour == 21):
                    buy_rate = self.rate_intermediario
                else:
                    buy_rate = self.rate_fora_ponta

            # Fórmula do crédito de exportação: C_sell[t] = C_buy[t] - C_FioB
            sell_rate = max(0.0, buy_rate - self.fio_b_cost_brl)

            buy_prices.append(buy_rate)
            sell_prices.append(sell_rate)

        return buy_prices, sell_prices

    def optimize_24h(self, net_load_24h, initial_soc, timestamps_24h=None, is_weekend=False):
        """
        Resolve o MILP diário de 24h e retorna o plano de potência da bateria: P_ch[t] - P_dis[t] (kW).
        """
        buy_prices, sell_prices = self.get_hourly_tariffs(timestamps_24h=timestamps_24h, is_weekend=is_weekend)

        model = pyo.ConcreteModel()
        model.T = pyo.RangeSet(0, 23)
        model.T_fp = pyo.RangeSet(0, 15)

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

        # Envelope de demanda global (P_max, P_min) e exclusivo Fora de Ponta (P_max_fp, P_min_fp, P_ch_peak) [kW]
        model.P_max = pyo.Var(within=pyo.Reals)
        model.P_min = pyo.Var(within=pyo.Reals)
        model.P_max_fp = pyo.Var(within=pyo.Reals)
        model.P_min_fp = pyo.Var(within=pyo.Reals)
        model.P_ch_peak = pyo.Var(within=pyo.Reals)

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

        # 2.4 Envelope Min-Max Global (24h) e Envelope Exclusivo Fora de Ponta (00h..15h)
        def p_max_rule(m, t):
            grid_exchange = net_load_24h[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange <= m.P_max
        model.p_max_constraint = pyo.Constraint(model.T, rule=p_max_rule)

        def p_min_rule(m, t):
            grid_exchange = net_load_24h[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange >= m.P_min
        model.p_min_constraint = pyo.Constraint(model.T, rule=p_min_rule)

        def p_max_fp_rule(m, t):
            grid_exchange = net_load_24h[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange <= m.P_max_fp
        model.p_max_fp_constraint = pyo.Constraint(model.T_fp, rule=p_max_fp_rule)

        def p_min_fp_rule(m, t):
            grid_exchange = net_load_24h[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange >= m.P_min_fp
        model.p_min_fp_constraint = pyo.Constraint(model.T_fp, rule=p_min_fp_rule)

        # Teto de recarga (Water-Filling): limita o patamar da rede nas horas em que a bateria carrega (is_charging=1)
        big_m = 500.0
        def p_ch_peak_rule(m, t):
            grid_exchange = net_load_24h[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange <= m.P_ch_peak + big_m * (1 - m.is_charging[t])
        model.p_ch_peak_constraint = pyo.Constraint(model.T_fp, rule=p_ch_peak_rule)

        # ----------------------------------------------------------------------
        # 3. Função Objetivo (Fórmula Final)
        # ----------------------------------------------------------------------
        # Valor residual V_res para energia solar retida em E[23]:
        # Fórmula: V_res = 0.5 * ((C_sell_FP / eta) + (C_buy_FP * eta))
        sell_fp = max(0.0, self.rate_fora_ponta - self.fio_b_cost_brl)
        cost_store_solar = sell_fp / self.efficiency
        value_use_fp = self.rate_fora_ponta * self.efficiency
        terminal_value_per_kwh = 0.5 * (cost_store_solar + value_use_fp)

        # Fórmula Final:
        # min sum_{t=0..23} (C_buy[t] * P_import[t] - C_sell[t] * P_export[t]) - V_res * E[23] + eps * (P_max - P_min)
        def objective_rule(m):
            daily_energy_cost = sum(
                (buy_prices[t] * m.P_import[t]) - (sell_prices[t] * m.P_export[t])
                for t in m.T
            )
            terminal_salvage = terminal_value_per_kwh * m.E[23]
            peak_shaving_tiebreaker = self.peak_shaving_weight * (
                (m.P_max - m.P_min) + (m.P_max_fp - m.P_min_fp) + m.P_ch_peak
            )
            return daily_energy_cost - terminal_salvage + peak_shaving_tiebreaker

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
            print("Aviso: Otimizador Tarifário não encontrou solução ótima!")
            return [0.0] * 24

        bess_power_plan = []
        for t in model.T:
            bess_power_plan.append(pyo.value(model.P_ch[t]) - pyo.value(model.P_dis[t]))

        return bess_power_plan

    def evaluate_hourly_financials(self, net_load_kw, grid_exchange_kw, buy_price, sell_price):
        """
        Calcula o custo horário (R$) sem bateria, com bateria e o balanço líquido da bateria:
        bess_balance_brl = cost_no_bess - cost_with_bess.
        """
        if net_load_kw >= 0:
            cost_no_bess = net_load_kw * buy_price
        else:
            cost_no_bess = net_load_kw * sell_price

        if grid_exchange_kw >= 0:
            cost_with_bess = grid_exchange_kw * buy_price
        else:
            cost_with_bess = grid_exchange_kw * sell_price

        bess_financial_balance = cost_no_bess - cost_with_bess

        return {
            'cost_no_bess_brl': cost_no_bess,
            'cost_with_bess_brl': cost_with_bess,
            'bess_balance_brl': bess_financial_balance,
        }


if __name__ == "__main__":
    dummy_net_load = [
        20, 18, 15, 14, 15, 20, 30, 35,
        10, -25, -55, -70, -65, -45, -15, 15,
        35, 55, 85, 95, 80, 60, 40, 25
    ]
    opt = OptimizerTariffBESS(capacity_kwh=200.0, max_power_kw=50.0)
    buy_p, sell_p = opt.get_hourly_tariffs(is_weekend=False)
    plan = opt.optimize_24h(dummy_net_load, initial_soc=0.0, is_weekend=False)

    print("=== TESTE DO OTIMIZADOR TARIFA BRANCA + FIO B (DIA ÚTIL) ===")
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
        total_no_bess += fin['cost_no_bess_brl']
        total_with_bess += fin['cost_with_bess_brl']
        print(
            f"Hora {t:02d}h | Tarifa Compra: R${buy_p[t]:.3f} (Venda: R${sell_p[t]:.3f}) | "
            f"NetLoad: {dummy_net_load[t]:+6.1f} kW | BESS: {p:+6.1f} kW (SoC: {soc_energy/200*100:5.1f}%) | "
            f"Grid: {grid_ex:+6.1f} kW | Balanço BESS: R$ {fin['bess_balance_brl']:+6.2f}"
        )
    print("------------------------------------------------------------")
    print(f"Custo Diário SEM Bateria: R$ {total_no_bess:.2f}")
    print(f"Custo Diário COM Bateria: R$ {total_with_bess:.2f}")
    print(f"Economia Líquida Gerada : R$ {total_no_bess - total_with_bess:.2f}")
