# ==============================================================================
# OTIMIZADOR 1: NIVELAMENTO FÍSICO DE DEMANDA (PEAK SHAVING & VALLEY FILLING)
# Comando de instalação: pip install pyomo pandas matplotlib numpy
# ==============================================================================

import os
import shutil
import numpy as np
import pyomo.environ as pyo


class OptimizerBESS:
    """
    Otimizador MILP (Pyomo + GLPK) para nivelamento de carga (Load Leveling) em janelas de 24h.

    Fórmula Final do Otimizador:
        min  (P_max - P_min)
        sujeito a:
          - Balanço na Rede:   P_grid[t] = NetLoad[t] + P_ch[t] - P_dis[t]
          - Envelope Min-Max:  P_min <= P_grid[t] <= P_max
          - Dinâmica de SoC:   E[t] = E[t-1] + (eta * P_ch[t]) - (P_dis[t] / eta)
          - Intertravamento:   0 <= P_ch[t] <= P_max_inv * is_charging[t]
                               0 <= P_dis[t] <= P_max_inv * (1 - is_charging[t])
          - Meta Terminal:     E[23] >= 0.50 * E_cap
    """

    def __init__(self, capacity_kwh, max_power_kw, soc_min=0.0, soc_max=1.0, efficiency=0.95):
        self.capacity_kwh = capacity_kwh
        self.max_power_kw = max_power_kw
        self.soc_min = soc_min
        self.soc_max = soc_max
        self.efficiency = efficiency

    def optimize_24h(self, net_load_24h, initial_soc):
        """
        Recebe o vetor net_load_24h (Load - Solar) das 24 horas e o SoC inicial (0.0 a 1.0).
        Retorna a lista de potências horárias da bateria: P_bess[t] = P_ch[t] - P_dis[t] (kW).
        """
        model = pyo.ConcreteModel()
        model.T = pyo.RangeSet(0, 23)

        # ----------------------------------------------------------------------
        # 1. Variáveis de Decisão
        # ----------------------------------------------------------------------
        # Potência de Carga (P_ch >= 0) e de Descarga (P_dis >= 0) limitadas pelo inversor [kW]
        model.P_ch = pyo.Var(model.T, within=pyo.NonNegativeReals, bounds=(0, self.max_power_kw))
        model.P_dis = pyo.Var(model.T, within=pyo.NonNegativeReals, bounds=(0, self.max_power_kw))

        # Energia armazenada na bateria ao final da hora t [kWh]: E_min <= E[t] <= E_max
        model.E = pyo.Var(
            model.T,
            within=pyo.NonNegativeReals,
            bounds=(self.capacity_kwh * self.soc_min, self.capacity_kwh * self.soc_max),
        )

        # Variável binária de intertravamento: 1 = Carregando, 0 = Descarregando
        model.is_charging = pyo.Var(model.T, within=pyo.Binary)

        # Variáveis de Teto (P_max) e Piso (P_min) da demanda na rede no dia [kW]
        model.P_max = pyo.Var(within=pyo.Reals)
        model.P_min = pyo.Var(within=pyo.Reals)

        # ----------------------------------------------------------------------
        # 2. Restrições (Constraints)
        # ----------------------------------------------------------------------
        # 2.1 Intertravamento Lógico: impede carga e descarga simultâneas
        # Fórmula: P_ch[t] <= P_max_inv * is_charging[t]
        def ch_limit_rule(m, t):
            return m.P_ch[t] <= self.max_power_kw * m.is_charging[t]
        model.ch_limit = pyo.Constraint(model.T, rule=ch_limit_rule)

        # Fórmula: P_dis[t] <= P_max_inv * (1 - is_charging[t])
        def dis_limit_rule(m, t):
            return m.P_dis[t] <= self.max_power_kw * (1 - m.is_charging[t])
        model.dis_limit = pyo.Constraint(model.T, rule=dis_limit_rule)

        # 2.2 Dinâmica de Energia da Bateria (passo de 1h)
        # Fórmula: E[t] = E[t-1] + (eta * P_ch[t]) - (P_dis[t] / eta)
        def battery_dynamics_rule(m, t):
            e_prev = (self.capacity_kwh * initial_soc) if t == 0 else m.E[t - 1]
            return m.E[t] == e_prev + (m.P_ch[t] * self.efficiency) - (m.P_dis[t] / self.efficiency)
        model.battery_dynamics = pyo.Constraint(model.T, rule=battery_dynamics_rule)

        # 2.3 Envelope Min-Max sobre o intercâmbio com a concessionária
        # Fórmula: NetLoad[t] + P_ch[t] - P_dis[t] <= P_max
        def p_max_rule(m, t):
            grid_exchange = net_load_24h[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange <= m.P_max
        model.p_max_constraint = pyo.Constraint(model.T, rule=p_max_rule)

        # Fórmula: NetLoad[t] + P_ch[t] - P_dis[t] >= P_min
        def p_min_rule(m, t):
            grid_exchange = net_load_24h[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange >= m.P_min
        model.p_min_constraint = pyo.Constraint(model.T, rule=p_min_rule)

        # 2.4 Condição de Contorno à Meia-Noite (t = 23)
        # Fórmula: E[23] >= 0.50 * E_cap
        def terminal_soc_rule(m):
            return m.E[23] >= self.capacity_kwh * 0.50
        model.terminal_soc = pyo.Constraint(rule=terminal_soc_rule)

        # ----------------------------------------------------------------------
        # 3. Função Objetivo (Fórmula Final)
        # ----------------------------------------------------------------------
        # Fórmula Final: min (P_max - P_min)
        model.obj = pyo.Objective(expr=model.P_max - model.P_min, sense=pyo.minimize)

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
            print("Aviso: Otimizador não encontrou solução ótima!")
            return [0.0] * 24

        bess_power_plan = []
        for t in model.T:
            bess_power_plan.append(pyo.value(model.P_ch[t]) - pyo.value(model.P_dis[t]))

        return bess_power_plan


if __name__ == "__main__":
    dummy_net_load = [20, 25, 10, -30, -50, -20, 30, 40, 50, 60, 40, 30, 20, 10, -10, -20, 10, 30, 50, 70, 80, 50, 30, 20]
    opt = OptimizerBESS(capacity_kwh=200, max_power_kw=50)
    plan = opt.optimize_24h(dummy_net_load, initial_soc=0.5)

    print("Plano de 24 horas gerado pelo Otimizador (P_bateria):")
    for t, p in enumerate(plan):
        print(f"Hora {t:02d} | Net Load: {dummy_net_load[t]:.1f} kW | Ação Bateria: {p:+.1f} kW")
