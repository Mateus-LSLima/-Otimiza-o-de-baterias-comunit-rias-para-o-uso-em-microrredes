# ==============================================================================
# AMBIENTE FÍSICO DA MICRORREDE COMUNITÁRIA E BATERIA (BESS)
# ==============================================================================


class Battery:
    """
    Modelo físico orientado a objetos do Sistema de Armazenamento em Bateria (BESS).
    Fórmula de atualização de estado:
        E(t) = clip(E(t-1) + P_aplicada * dt, 0, E_cap)
        SoC(t) = E(t) / E_cap
    """

    def __init__(self, capacity_kwh, max_power_kw, initial_soc=0.50):
        self.capacity_kwh = capacity_kwh
        self.max_power_kw = max_power_kw

        # Estado atual de energia armazenada (em kWh)
        self.current_energy = capacity_kwh * initial_soc

    @property
    def soc(self):
        """Retorna o Estado de Carga (State of Charge - SoC) atual entre 0.0 e 1.0."""
        return self.current_energy / self.capacity_kwh

    def step(self, power_kw, hours=1.0):
        """
        Executa um passo de simulação de duração `hours` (padrão: 1h).
          - power_kw > 0: Carrega a bateria.
          - power_kw < 0: Descarrega a bateria.
        Retorna a potência efetivamente aplicada (kW), respeitando os limites do inversor e de capacidade.
        """
        # Limita a potência solicitada à potência nominal do inversor [-P_max, +P_max]
        applied_power = max(min(power_kw, self.max_power_kw), -self.max_power_kw)

        # Variação de energia no passo de tempo (kWh)
        energy_change = applied_power * hours
        new_energy = self.current_energy + energy_change

        # Saturação nos limites físicos de capacidade [0%, 100%]
        max_energy = self.capacity_kwh
        min_energy = 0.0

        if new_energy > max_energy:
            energy_change = max_energy - self.current_energy
            self.current_energy = max_energy
        elif new_energy < min_energy:
            energy_change = min_energy - self.current_energy
            self.current_energy = min_energy
        else:
            self.current_energy = new_energy

        actual_power = energy_change / hours
        return actual_power


class Microgrid:
    """
    Simulador do balanço de potência ativa horária da microrrede comunitária.
    Fórmulas de balanço:
        NetLoad[t] = Load[t] - Solar[t]
        GridExchange[t] = NetLoad[t] + P_bateria[t]
    """

    def __init__(self, battery):
        self.battery = battery
        self.time_step = 0

    def run_hour(self, load_kw, solar_kw, requested_battery_power_kw=0):
        """
        Avança 1 hora na simulação da microrrede e retorna o dicionário de estados elétricos:
          - grid_exchange_kw > 0: Importando energia da concessionária.
          - grid_exchange_kw < 0: Exportando excedente para a concessionária.
        """
        # 1. Atuação da bateria respeitando limites físicos
        actual_battery_power = self.battery.step(requested_battery_power_kw, hours=1.0)

        # 2. Demanda líquida nativa da comunidade: NetLoad = Load - Solar
        net_load = load_kw - solar_kw

        # 3. Fluxo resultante no medidor da concessionária: GridExchange = NetLoad + P_bateria
        grid_exchange = net_load + actual_battery_power

        self.time_step += 1

        return {
            "hour": self.time_step,
            "load_kw": load_kw,
            "solar_kw": solar_kw,
            "net_load_kw": net_load,
            "battery_soc": self.battery.soc,
            "battery_power_kw": actual_battery_power,
            "grid_exchange_kw": grid_exchange,
        }
