# ==============================================================================
# SIMULADOR DO OTIMIZADOR 1B: PEAK SHAVING COM HORIZONTE DESLIZANTE (24h / 12h)
# Preserva intactos os gráficos do Otimizador 1 clássico e gera a nova suíte
# de gráficos e comparativos em data/1b_otimizador_peak_shaving_12h/imagens/
# e em Resultados de Otimizacao/.
# ==============================================================================

import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Garante que o Python encontre a pasta src/control
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(base_dir, 'src', 'control'))

from optimizer_rolling_horizon import OptimizerRollingBESS
from optimizer_pyomo import OptimizerBESS


def load_preprocessed_dataset():
    """
    Carrega a série horária da microrrede, alinha os timestamps ao fuso local de Austin
    (America/Chicago) sem tzinfo antes da reamostragem (garantindo que os turnos de 12h
    iniciem estritamente às 00:00:00 e 12:00:00 do horário do Texas).
    Fórmula da demanda líquida: NetLoad[t] = Load[t] - Solar[t].
    """
    data_path = os.path.join(base_dir, 'data', '1_otimizador_peak_shaving', 'dados', 'community_microgrid.csv')
    df = pd.read_csv(data_path)
    df['timestamp'] = (
        pd.to_datetime(df['timestamp'], utc=True)
        .dt.tz_convert('America/Chicago')
        .dt.tz_localize(None)
    )
    df = df.drop_duplicates(subset=['timestamp']).set_index('timestamp')
    df = df.resample('1h').asfreq()
    df['load'] = df['load'].interpolate(method='linear')
    df['total_solar'] = df['total_solar'].interpolate(method='linear')
    df = df.reset_index()
    df['net_load'] = df['load'] - df['total_solar']
    return df


def simulate_rolling_period(
    df_full,
    start_idx,
    num_hours,
    capacity_kwh=200.0,
    max_power_kw=50.0,
    efficiency=0.95,
    initial_soc=0.50,
    step_hours=12,
    horizon_hours=24,
):
    """
    Executa a otimização em Horizonte Deslizante (Rolling Horizon):
      - A cada `step_hours` (12h: às 00h e às 12h), o otimizador recebe `horizon_hours` (24h)
        de previsão do Net Load.
      - O otimizador planeja as 24h sem restrição de 50% no fim da janela, e o simulador
        executa apenas as primeiras 12h antes de receber a nova janela de 24h.
    """
    opt = OptimizerRollingBESS(
        capacity_kwh=capacity_kwh,
        max_power_kw=max_power_kw,
        efficiency=efficiency,
    )

    bess_power_list = []
    bess_energy_list = []
    grid_exchange_list = []

    current_energy = capacity_kwh * initial_soc
    total_len = len(df_full)
    num_steps = num_hours // step_hours
    print(
        f"Otimizando {num_hours // 24} dias ({num_hours} horas) em {num_steps} turnos de {step_hours}h "
        f"(janela de planejamento de {horizon_hours}h)..."
    )

    for step in range(num_steps):
        cur_idx = start_idx + step * step_hours
        end_window_idx = cur_idx + horizon_hours

        # Extrai a janela futura de 24h (se passar do fim de 31/Dez, completa com o início da série)
        if end_window_idx <= total_len:
            window_net_load = df_full['net_load'].iloc[cur_idx:end_window_idx].tolist()
        else:
            part1 = df_full['net_load'].iloc[cur_idx:total_len].tolist()
            rem = horizon_hours - len(part1)
            part2 = df_full['net_load'].iloc[:rem].tolist()
            window_net_load = part1 + part2

        plan_24h = opt.optimize_window(window_net_load, initial_soc=(current_energy / capacity_kwh))
        exec_12h = plan_24h[:step_hours]

        for t_rel, p_kw in enumerate(exec_12h):
            if p_kw > 0:
                current_energy += p_kw * efficiency
            else:
                current_energy += p_kw / efficiency

            current_energy = max(0.0, min(capacity_kwh, current_energy))
            bess_power_list.append(p_kw)
            bess_energy_list.append(current_energy)
            grid_exchange = window_net_load[t_rel] + p_kw
            grid_exchange_list.append(grid_exchange)

    res = df_full.iloc[start_idx : start_idx + len(bess_power_list)].copy().reset_index(drop=True)
    res['bess_power'] = bess_power_list
    res['bess_energy_kwh'] = bess_energy_list
    res['bess_soc_pct'] = (res['bess_energy_kwh'] / capacity_kwh) * 100.0
    res['grid_exchange'] = grid_exchange_list
    return res


def simulate_classic_period(df_subset, capacity_kwh=200.0, max_power_kw=50.0, efficiency=0.95, initial_soc=0.50):
    """
    Executa o Otimizador 1 Clássico (blocos fixos de 24h com trava E[23] >= 50%)
    apenas em memória para fins de comparação direta de métricas e plotagem sobreposta.
    """
    opt = OptimizerBESS(capacity_kwh=capacity_kwh, max_power_kw=max_power_kw, efficiency=efficiency)
    bess_power_list = []
    bess_energy_list = []
    grid_exchange_list = []

    current_energy = capacity_kwh * initial_soc
    num_days = len(df_subset) // 24

    for day in range(num_days):
        day_net_load = df_subset['net_load'].iloc[day * 24 : (day + 1) * 24].tolist()
        plan = opt.optimize_24h(day_net_load, initial_soc=(current_energy / capacity_kwh))
        for t, p_kw in enumerate(plan):
            if p_kw > 0:
                current_energy += p_kw * efficiency
            else:
                current_energy += p_kw / efficiency
            current_energy = max(0.0, min(capacity_kwh, current_energy))
            bess_power_list.append(p_kw)
            bess_energy_list.append(current_energy)
            grid_exchange_list.append(day_net_load[t] + p_kw)

    res = df_subset.iloc[: len(bess_power_list)].copy().reset_index(drop=True)
    res['bess_power'] = bess_power_list
    res['bess_energy_kwh'] = bess_energy_list
    res['bess_soc_pct'] = (res['bess_energy_kwh'] / capacity_kwh) * 100.0
    res['grid_exchange'] = grid_exchange_list
    return res


def save_figure_both_dirs( out_filename):
    dest_dirs = [
        os.path.join(base_dir, 'data', '1b_otimizador_peak_shaving_12h', 'imagens'),
        os.path.join(base_dir, 'Resultados de Otimizacao'),
    ]
    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)
        out_file = os.path.join(d, out_filename)
        plt.savefig(out_file, dpi=160, bbox_inches='tight')
        print(f"Gráfico salvo com sucesso em: {out_file}")


def plot_rolling_simulation(df_res, title, out_filename, time_scale='week'):
    """
    Gera o gráfico duplo sincronizado do Otimizador 1B (Horizonte Deslizante 24h/12h sem trava de 50%).
    """
    if time_scale == 'quarter':
        fig_size = (20, 10)
        lw_net, lw_grid, lw_soc, lw_power = 0.95, 0.95, 1.3, 0.75
        alpha_fill, alpha_power = 0.22, 0.35
    elif time_scale == 'month':
        fig_size = (18, 9.5)
        lw_net, lw_grid, lw_soc, lw_power = 1.2, 1.2, 1.6, 0.9
        alpha_fill, alpha_power = 0.28, 0.45
    else:  # week
        fig_size = (16, 9)
        lw_net, lw_grid, lw_soc, lw_power = 1.8, 1.8, 2.2, 1.2
        alpha_fill, alpha_power = 0.32, 0.55

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=fig_size, sharex=True, gridspec_kw={'height_ratios': [1.3, 1]})

    # --- GRÁFICO SUPERIOR: Peak Shaving & Valley Filling ---
    ax1.plot(
        df_res['timestamp'],
        df_res['net_load'],
        color='crimson',
        linewidth=lw_net,
        label='Demanda Original da Microrrede (Net Load)',
    )
    ax1.plot(
        df_res['timestamp'],
        df_res['grid_exchange'],
        color='navy',
        linestyle='--',
        linewidth=lw_grid,
        label='Demanda com Bateria — Horizonte Deslizante 24h/12h (Sem Trava 50%)',
    )
    ax1.axhline(0, color='black', linewidth=0.8, alpha=0.7)

    ax1.fill_between(
        df_res['timestamp'],
        df_res['net_load'],
        df_res['grid_exchange'],
        where=(df_res['net_load'] > df_res['grid_exchange']),
        color='orange',
        alpha=alpha_fill,
        label='Alívio de Pico (Bateria Descarregando)',
    )
    ax1.fill_between(
        df_res['timestamp'],
        df_res['net_load'],
        df_res['grid_exchange'],
        where=(df_res['net_load'] < df_res['grid_exchange']),
        color='cyan',
        alpha=alpha_fill,
        label='Preenchimento de Vale (Bateria Carregando)',
    )

    ax1.set_ylabel('Potência Ativa (kW)', fontsize=12, fontweight='bold')
    ax1.set_title(title, fontsize=13, fontweight='bold')
    ax1.legend(loc='upper right', framealpha=0.9)
    ax1.grid(True, alpha=0.3)

    # --- GRÁFICO INFERIOR: Ciclo Completo da Bateria (0% a 100% Livre) ---
    ax2.plot(
        df_res['timestamp'],
        df_res['bess_soc_pct'],
        color='green',
        linewidth=lw_soc,
        label='Estado de Carga da Bateria (SOC % — Livre 0% a 100%)',
    )
    ax2.set_ylabel('Carga da Bateria (% SOC)', fontsize=12, fontweight='bold', color='green')
    ax2.tick_params(axis='y', labelcolor='green')
    ax2.set_ylim(-5, 105)
    ax2.axhline(100, color='gray', linestyle=':', alpha=0.6)
    ax2.axhline(50, color='darkorange', linestyle='-.', linewidth=1.0, alpha=0.6, label='Antiga Trava Noturna (50% SOC — Removida)')
    ax2.axhline(0, color='gray', linestyle=':', alpha=0.6)

    ax2_twin = ax2.twinx()
    ax2_twin.plot(
        df_res['timestamp'],
        df_res['bess_power'],
        color='purple',
        alpha=alpha_power,
        linestyle='-',
        linewidth=lw_power,
        label='Potência Bateria (+ Carga / - Descarga) [kW]',
    )
    ax2_twin.set_ylabel('Potência Inversor (kW)', fontsize=11, color='purple')
    ax2_twin.tick_params(axis='y', labelcolor='purple')
    ax2_twin.axhline(0, color='purple', linestyle=':', alpha=0.3)

    ax2.set_xlabel('Tempo (Horário Local de Austin, Texas)', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3)

    if time_scale == 'quarter':
        ax2.xaxis.set_major_locator(mdates.DayLocator(interval=7))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b'))
        ax2.xaxis.set_minor_locator(mdates.DayLocator(interval=1))
    elif time_scale == 'month':
        ax2.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b'))
        ax2.xaxis.set_minor_locator(mdates.DayLocator(interval=1))
    else:  # week
        ax2.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12]))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b %Hh'))
        ax2.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 18]))

    lines_1, labels_1 = ax2.get_legend_handles_labels()
    lines_2, labels_2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper right', framealpha=0.9)

    plt.tight_layout()
    save_figure_both_dirs(out_filename)
    plt.close()


def plot_comparison_week(df_classic, df_rolling, out_filename='grafico_comparativo_ps24h_vs_ps12h_1semana.png'):
    """
    Plota a comparação direta na Semana de Julho (02/Jul a 09/Jul/2018) entre:
      - Otimizador 1 Clássico (Bloco Fixo 24h com Trava de 50% SoC à meia-noite)
      - Otimizador 1B Novo (Horizonte Deslizante 24h a cada 12h com SoC Livre)
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 9.5), sharex=True, gridspec_kw={'height_ratios': [1.3, 1]})

    # Painel Superior: Demanda na Rede
    ax1.plot(
        df_rolling['timestamp'],
        df_rolling['net_load'],
        color='crimson',
        linewidth=1.5,
        alpha=0.65,
        label=f"Demanda Original (Net Load) — Pico: {df_rolling['net_load'].max():.2f} kW",
    )
    ax1.plot(
        df_classic['timestamp'],
        df_classic['grid_exchange'],
        color='darkorange',
        linestyle='-.',
        linewidth=1.9,
        label=f"Otimizador 1 Clássico (24h Fixo c/ Trava 50% SoC) — Pico: {df_classic['grid_exchange'].max():.2f} kW",
    )
    ax1.plot(
        df_rolling['timestamp'],
        df_rolling['grid_exchange'],
        color='navy',
        linestyle='-',
        linewidth=2.1,
        label=f"Otimizador 1B Novo (Horizonte 24h a cada 12h, SoC Livre) — Pico: {df_rolling['grid_exchange'].max():.2f} kW",
    )
    ax1.fill_between(
        df_rolling['timestamp'],
        df_classic['grid_exchange'],
        df_rolling['grid_exchange'],
        where=(df_classic['grid_exchange'] > df_rolling['grid_exchange']),
        color='royalblue',
        alpha=0.25,
        label='Ganho Adicional de Redução de Pico (Horizonte Deslizante 12h)',
    )
    ax1.axhline(0, color='black', linewidth=0.8, alpha=0.7)
    ax1.set_ylabel('Potência na Rede (kW)', fontsize=12, fontweight='bold')
    ax1.set_title(
        'Comparativo Direto (02/Jul a 09/Jul/2018): Bloco Fixo 24h (Trava 50%) vs. Horizonte Deslizante 24h/12h (SoC Livre)',
        fontsize=13,
        fontweight='bold',
    )
    ax1.legend(loc='upper right', framealpha=0.92)
    ax1.grid(True, alpha=0.3)

    # Painel Inferior: Trajetória do Estado de Carga (SOC %)
    ax2.plot(
        df_classic['timestamp'],
        df_classic['bess_soc_pct'],
        color='darkorange',
        linestyle='-.',
        linewidth=1.9,
        label='SOC % — Otimizador 1 Clássico (Preso acima de 50% à meia-noite)',
    )
    ax2.plot(
        df_rolling['timestamp'],
        df_rolling['bess_soc_pct'],
        color='green',
        linestyle='-',
        linewidth=2.2,
        label='SOC % — Otimizador 1B Horizonte 24h/12h (Usa de 100% até 0% nos picos)',
    )
    ax2.axhline(50, color='red', linestyle=':', linewidth=1.2, alpha=0.75, label='Limite de 50% SOC à Meia-Noite (Trava Antiga)')
    ax2.axhline(100, color='gray', linestyle=':', alpha=0.5)
    ax2.axhline(0, color='gray', linestyle=':', alpha=0.5)
    ax2.set_ylim(-5, 105)
    ax2.set_ylabel('Estado de Carga (% SOC)', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Tempo (Horário Local de Austin, Texas — Atualizações às 00h e 12h)', fontsize=12, fontweight='bold')
    ax2.legend(loc='upper right', framealpha=0.92)
    ax2.grid(True, alpha=0.3)

    ax2.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12]))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b %Hh'))
    ax2.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 18]))

    plt.tight_layout()
    save_figure_both_dirs(out_filename)
    plt.close()


def run_all():
    df = load_preprocessed_dataset()
    comparison_table = []

    # 1. Visão de 1 Semana (02/Jul a 09/Jul/2018)
    print("\n=== 1. SIMULANDO 1 SEMANA (02/Jul a 09/Jul/2018) ===")
    start_week_ts = pd.Timestamp('2018-07-02 00:00:00')
    start_week_idx = int(df.index[df['timestamp'] == start_week_ts][0])
    hours_week = 7 * 24

    res_week_rolling = simulate_rolling_period(df, start_week_idx, hours_week)
    res_week_classic = simulate_classic_period(df.iloc[start_week_idx : start_week_idx + hours_week])

    plot_rolling_simulation(
        res_week_rolling,
        title='Otimizador 1B (Horizonte Deslizante 24h a cada 12h, SoC Livre) — Visão de 1 Semana (02/Jul a 09/Jul/2018)',
        out_filename='grafico_ps12h_1semana.png',
        time_scale='week',
    )
    plot_comparison_week(
        res_week_classic,
        res_week_rolling,
        out_filename='grafico_comparativo_ps24h_vs_ps12h_1semana.png',
    )

    comparison_table.append({
        'periodo': '1 Semana (02 a 09/Jul)',
        'horas': hours_week,
        'orig_peak': res_week_rolling['net_load'].max(),
        'classic_peak': res_week_classic['grid_exchange'].max(),
        'rolling_peak': res_week_rolling['grid_exchange'].max(),
        'classic_red_pct': ((res_week_rolling['net_load'].max() - res_week_classic['grid_exchange'].max()) / res_week_rolling['net_load'].max()) * 100.0,
        'rolling_red_pct': ((res_week_rolling['net_load'].max() - res_week_rolling['grid_exchange'].max()) / res_week_rolling['net_load'].max()) * 100.0,
        'min_net': res_week_rolling['net_load'].min(),
        'classic_min_grid': res_week_classic['grid_exchange'].min(),
        'rolling_min_grid': res_week_rolling['grid_exchange'].min(),
    })

    # 2. Visão de 1 Mês (Julho de 2018 completo)
    print("\n=== 2. SIMULANDO 1 MÊS (Julho/2018 Completo) ===")
    start_month_ts = pd.Timestamp('2018-07-01 00:00:00')
    start_month_idx = int(df.index[df['timestamp'] == start_month_ts][0])
    hours_month = 31 * 24

    res_month_rolling = simulate_rolling_period(df, start_month_idx, hours_month)
    res_month_classic = simulate_classic_period(df.iloc[start_month_idx : start_month_idx + hours_month])

    plot_rolling_simulation(
        res_month_rolling,
        title='Otimizador 1B (Horizonte Deslizante 24h a cada 12h, SoC Livre) — Visão Mensal (Julho de 2018)',
        out_filename='grafico_ps12h_1mes.png',
        time_scale='month',
    )

    comparison_table.append({
        'periodo': '1 Mês (Julho/2018)',
        'horas': hours_month,
        'orig_peak': res_month_rolling['net_load'].max(),
        'classic_peak': res_month_classic['grid_exchange'].max(),
        'rolling_peak': res_month_rolling['grid_exchange'].max(),
        'classic_red_pct': ((res_month_rolling['net_load'].max() - res_month_classic['grid_exchange'].max()) / res_month_rolling['net_load'].max()) * 100.0,
        'rolling_red_pct': ((res_month_rolling['net_load'].max() - res_month_rolling['grid_exchange'].max()) / res_month_rolling['net_load'].max()) * 100.0,
        'min_net': res_month_rolling['net_load'].min(),
        'classic_min_grid': res_month_classic['grid_exchange'].min(),
        'rolling_min_grid': res_month_rolling['grid_exchange'].min(),
    })

    # 3. Os 4 Trimestres de 2018
    quarters_config = [
        {
            'name': '1º Trimestre (Jan a Mar / 2018 - Inverno)',
            'short': 'T1: Inverno (Jan–Mar)',
            'days': 90,
            'start_idx': 0,
            'filename': 'grafico_ps12h_trimestre1_jan_mar.png',
        },
        {
            'name': '2º Trimestre (Abr a Jun / 2018 - Primavera)',
            'short': 'T2: Primavera (Abr–Jun)',
            'days': 91,
            'start_idx': 90 * 24,
            'filename': 'grafico_ps12h_trimestre2_abr_jun.png',
        },
        {
            'name': '3º Trimestre (Jul a Set / 2018 - Verão)',
            'short': 'T3: Verão (Jul–Set)',
            'days': 92,
            'start_idx': (90 + 91) * 24,
            'filename': 'grafico_ps12h_trimestre3_jul_set.png',
        },
        {
            'name': '4º Trimestre (Out a Dez / 2018 - Outono)',
            'short': 'T4: Outono (Out–Dez)',
            'days': 92,
            'start_idx': (90 + 91 + 92) * 24,
            'filename': 'grafico_ps12h_trimestre4_out_dez.png',
        },
    ]

    for q in quarters_config:
        print(f"\n=== SIMULANDO {q['name']} ===")
        q_hours = q['days'] * 24
        res_q_rolling = simulate_rolling_period(df, q['start_idx'], q_hours)
        res_q_classic = simulate_classic_period(df.iloc[q['start_idx'] : q['start_idx'] + q_hours])

        plot_rolling_simulation(
            res_q_rolling,
            title=f"Otimizador 1B (Horizonte Deslizante 24h/12h, SoC Livre) — {q['name']}",
            out_filename=q['filename'],
            time_scale='quarter',
        )

        comparison_table.append({
            'periodo': q['short'],
            'horas': q_hours,
            'orig_peak': res_q_rolling['net_load'].max(),
            'classic_peak': res_q_classic['grid_exchange'].max(),
            'rolling_peak': res_q_rolling['grid_exchange'].max(),
            'classic_red_pct': ((res_q_rolling['net_load'].max() - res_q_classic['grid_exchange'].max()) / res_q_rolling['net_load'].max()) * 100.0,
            'rolling_red_pct': ((res_q_rolling['net_load'].max() - res_q_rolling['grid_exchange'].max()) / res_q_rolling['net_load'].max()) * 100.0,
            'min_net': res_q_rolling['net_load'].min(),
            'classic_min_grid': res_q_classic['grid_exchange'].min(),
            'rolling_min_grid': res_q_rolling['grid_exchange'].min(),
        })

    print("\n====================================================================================================")
    print("RESUMO COMPARATIVO: OTIMIZADOR 1 CLÁSSICO (50% FIXO) vs. OTIMIZADOR 1B HORIZONTE DESLIZANTE (24h/12h)")
    print("====================================================================================================")
    for row in comparison_table:
        extra_kw = row['classic_peak'] - row['rolling_peak']
        extra_pct_pts = row['rolling_red_pct'] - row['classic_red_pct']
        print(
            f"{row['periodo']:<24} | Orig: {row['orig_peak']:6.2f} kW | "
            f"Clássico (50%): {row['classic_peak']:6.2f} kW (-{row['classic_red_pct']:4.1f}%) | "
            f"Deslizante (12h): {row['rolling_peak']:6.2f} kW (-{row['rolling_red_pct']:4.1f}%) | "
            f"Ganho Extra: -{extra_kw:5.2f} kW (+{extra_pct_pts:4.1f} p.p.)"
        )


if __name__ == '__main__':
    run_all()
