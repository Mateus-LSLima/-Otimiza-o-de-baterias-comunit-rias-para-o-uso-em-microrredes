# ==============================================================================
# OTIMIZADOR 1B: PEAK SHAVING COM HORIZONTE DESLIZANTE (24h A CADA 12h, SOC LIVRE)
# Comando de instalação: pip install pyomo pandas matplotlib numpy
# ==============================================================================

import os
import shutil
import numpy as np
import pyomo.environ as pyo


class OptimizerRollingBESS:
    """
    Otimizador MILP (Pyomo + GLPK) para nivelamento de demanda (Peak Shaving & Valley Filling)
    operando em regime de Horizonte Deslizante (Rolling / Receding Horizon Control):
      - Horizonte de Previsão/Planejamento (N_p): 24 horas
      - Horizonte de Execução/Atualização (N_c):  12 horas (replanejamento às 00h e às 12h)
      - Condição Terminal: Livre entre 0% e 100% SoC (sem a trava de 50% à meia-noite).

    Fórmula Final do Otimizador na Janela H (padrão H = 24h):
        min  (P_max - P_min) + epsilon * sum_{t=0}^{H-1} (P_ch[t] + P_dis[t])
        sujeito a:
          - Balanço na Rede:   P_grid[t] = NetLoad[t] + P_ch[t] - P_dis[t]
          - Envelope Min-Max:  P_min <= P_grid[t] <= P_max
          - Dinâmica de SoC:   E[t] = E[t-1] + (eta * P_ch[t]) - (P_dis[t] / eta)
          - Limites de SoC:    0 <= E[t] <= E_cap  (Livre, sem obrigação de 50% em t=H-1)
          - Intertravamento:   0 <= P_ch[t] <= P_max_inv * is_charging[t]
                               0 <= P_dis[t] <= P_max_inv * (1 - is_charging[t])
    """

    def __init__(
        self,
        capacity_kwh=200.0,
        max_power_kw=50.0,
        soc_min=0.0,
        soc_max=1.0,
        efficiency=0.95,
        regularization_eps=1e-5,
    ):
        self.capacity_kwh = capacity_kwh
        self.max_power_kw = max_power_kw
        self.soc_min = soc_min
        self.soc_max = soc_max
        self.efficiency = efficiency
        self.regularization_eps = regularization_eps

    def optimize_window(self, net_load_window, initial_soc):
        """
        Recebe o vetor net_load_window (Load - Solar) das próximas H horas (padrão 24h)
        e o Estado de Carga inicial (initial_soc entre 0.0 e 1.0).
        Retorna a lista de potências planejadas da bateria para toda a janela H:
            P_bess[t] = P_ch[t] - P_dis[t] (kW),
        da qual o controlador executará as primeiras 12 horas antes da próxima atualização.
        """
        horizon = len(net_load_window)
        if horizon == 0:
            return []

        model = pyo.ConcreteModel()
        model.T = pyo.RangeSet(0, horizon - 1)

        # ----------------------------------------------------------------------
        # 1. Variáveis de Decisão
        # ----------------------------------------------------------------------
        # Potência de Carga (P_ch >= 0) e de Descarga (P_dis >= 0) limitadas pelo inversor [kW]
        model.P_ch = pyo.Var(model.T, within=pyo.NonNegativeReals, bounds=(0, self.max_power_kw))
        model.P_dis = pyo.Var(model.T, within=pyo.NonNegativeReals, bounds=(0, self.max_power_kw))

        # Energia armazenada na bateria ao final da hora t [kWh]: E_min <= E[t] <= E_max
        # (Livre entre 0% e 100%, sem trava artificial de 50% no final da janela)
        model.E = pyo.Var(
            model.T,
            within=pyo.NonNegativeReals,
            bounds=(self.capacity_kwh * self.soc_min, self.capacity_kwh * self.soc_max),
        )

        # Variável binária de intertravamento: 1 = Carregando, 0 = Descarregando
        model.is_charging = pyo.Var(model.T, within=pyo.Binary)

        # Variáveis de Teto (P_max) e Piso (P_min) da demanda na rede na janela [kW]
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
            grid_exchange = net_load_window[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange <= m.P_max
        model.p_max_constraint = pyo.Constraint(model.T, rule=p_max_rule)

        # Fórmula: NetLoad[t] + P_ch[t] - P_dis[t] >= P_min
        def p_min_rule(m, t):
            grid_exchange = net_load_window[t] + m.P_ch[t] - m.P_dis[t]
            return grid_exchange >= m.P_min
        model.p_min_constraint = pyo.Constraint(model.T, rule=p_min_rule)

        # ----------------------------------------------------------------------
        # 3. Função Objetivo (Fórmula Final com Micro-Regularização)
        # ----------------------------------------------------------------------
        # Fórmula Final: min (P_max - P_min) + eps * sum(P_ch[t] + P_dis[t])
        # O micro-peso eps = 1e-5 evita oscilações/ciclagens inúteis nas horas intermediárias
        # em que P_grid[t] já está estritamente dentro do envelope [P_min, P_max].
        inverter_usage = sum(model.P_ch[t] + model.P_dis[t] for t in model.T)
        model.obj = pyo.Objective(
            expr=(model.P_max - model.P_min) + self.regularization_eps * inverter_usage,
            sense=pyo.minimize,
        )

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
            print("Aviso: Otimizador de Horizonte Deslizante não encontrou solução ótima!")
            return [0.0] * horizon

        bess_power_plan = []
        for t in model.T:
            bess_power_plan.append(pyo.value(model.P_ch[t]) - pyo.value(model.P_dis[t]))

        return bess_power_plan


if __name__ == "__main__":
    # Teste unitário de 2 dias (48 horas) atualizado de 12 em 12 horas
    day_pattern = [
        25, 22, 20, 18, 18, 20, 25, 30, 15, -10, -25, -30,
        -25, -15, 5, 25, 45, 70, 85, 90, 80, 65, 45, 32
    ]
    two_days_net_load = day_pattern * 2

    opt = OptimizerRollingBESS(capacity_kwh=200.0, max_power_kw=50.0, efficiency=0.95)
    current_energy = 200.0 * 0.50

    print("=== TESTE UNITÁRIO: HORIZONTE DESLIZANTE (24h A CADA 12h, SEM TRAVA DE 50%) ===")
    for step_idx in range(3):  # 3 turnos de 12h (36h executadas, olhando 24h à frente)
        start_h = step_idx * 12
        window_24h = two_days_net_load[start_h : start_h + 24]
        soc_init = current_energy / 200.0
        plan_24h = opt.optimize_window(window_24h, initial_soc=soc_init)
        exec_12h = plan_24h[:12]

        print(f"\n--- Turno {step_idx + 1} (Horas {start_h:02d}h a {start_h + 11:02d}h | Janela prevista: {start_h:02d}h..{start_h + 23:02d}h | SoC Inicial: {soc_init*100:.1f}%) ---")
        for h_rel, p_kw in enumerate(exec_12h):
            if p_kw > 0:
                current_energy += p_kw * 0.95
            else:
                current_energy += p_kw / 0.95
            current_energy = max(0.0, min(200.0, current_energy))
            nl = window_24h[h_rel]
            ge = nl + p_kw
            print(
                f"Hora {start_h + h_rel:02d}h | NetLoad: {nl:+6.1f} kW | BESS: {p_kw:+6.1f} kW | "
                f"Grid: {ge:+6.1f} kW | SoC: {(current_energy/200.0)*100:5.1f}%"
            )
