import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Garante que o Python encontre src/control e a pasta raiz
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(base_dir, 'src', 'control'))

from optimizer_ercot import OptimizerErcotBESS


def simulate_ercot_period(
    df_subset,
    capacity_kwh=200.0,
    max_power_kw=50.0,
    efficiency=0.95,
    initial_soc=0.50,
):
    """
    Executa a otimização puramente monetária diária (ERCOT DAM + TDSP + Micro-desempate)
    em blocos de 24h para o subconjunto de dados fornecido.
    """
    opt = OptimizerErcotBESS(
        capacity_kwh=capacity_kwh,
        max_power_kw=max_power_kw,
        efficiency=efficiency,
    )

    bess_power_list = []
    bess_energy_list = []
    grid_exchange_list = []
    buy_price_list = []
    sell_price_list = []
    cost_no_bess_list = []
    cost_with_bess_list = []
    bess_balance_list = []

    current_energy = capacity_kwh * initial_soc
    num_days = len(df_subset) // 24
    print(f"Otimizando (ERCOT Atacado + TDSP) para {num_days} dias ({num_days * 24} horas)...")

    for day in range(num_days):
        slice_df = df_subset.iloc[day * 24 : (day + 1) * 24]
        day_net_load = slice_df['net_load'].tolist()
        day_spp_kwh = slice_df['ercot_spp_usd_kwh'].tolist()

        buy_p, sell_p = opt.get_hourly_prices(day_spp_kwh)
        plan = opt.optimize_24h(
            day_net_load,
            initial_soc=(current_energy / capacity_kwh),
            spp_usd_kwh_24h=day_spp_kwh,
        )

        for t, p_kw in enumerate(plan):
            if p_kw > 0:
                current_energy += p_kw * efficiency
            else:
                current_energy += p_kw / efficiency

            current_energy = max(0.0, min(capacity_kwh, current_energy))
            grid_exchange = day_net_load[t] + p_kw

            fin = opt.evaluate_hourly_financials(
                net_load_kw=day_net_load[t],
                grid_exchange_kw=grid_exchange,
                buy_price=buy_p[t],
                sell_price=sell_p[t],
            )

            bess_power_list.append(p_kw)
            bess_energy_list.append(current_energy)
            grid_exchange_list.append(grid_exchange)
            buy_price_list.append(buy_p[t])
            sell_price_list.append(sell_p[t])
            cost_no_bess_list.append(fin['cost_no_bess_usd'])
            cost_with_bess_list.append(fin['cost_with_bess_usd'])
            bess_balance_list.append(fin['bess_balance_usd'])

    res = df_subset.iloc[: len(bess_power_list)].copy()
    res['bess_power'] = bess_power_list
    res['bess_energy_kwh'] = bess_energy_list
    res['bess_soc_pct'] = (res['bess_energy_kwh'] / capacity_kwh) * 100.0
    res['grid_exchange'] = grid_exchange_list
    res['buy_price_usd'] = buy_price_list
    res['sell_price_usd'] = sell_price_list
    res['cost_no_bess_usd'] = cost_no_bess_list
    res['cost_with_bess_usd'] = cost_with_bess_list
    res['bess_balance_usd'] = bess_balance_list
    res['cumulative_cost_no_bess_usd'] = res['cost_no_bess_usd'].cumsum()
    res['cumulative_cost_with_bess_usd'] = res['cost_with_bess_usd'].cumsum()
    res['cumulative_bess_savings_usd'] = res['bess_balance_usd'].cumsum()
    return res


def plot_ercot_bess_simulation(df_res, title, out_filename, time_scale='week', show_total_cost_panel=False):
    """
    Gera o gráfico sincronizado (em US$):
      1. Curva de Demanda (Net Load vs Grid Exchange)
      2. Dinâmica da Bateria (SOC % e Potência do Inversor kW)
      3. Balanço Monetário da Bateria (Fluxo Horário US$/h + Economia/Lucro Acumulado US$)
      4. [Para 1 Semana e 1 Mês] Variação Horária do Custo da Energia (Compra Spot+TDSP vs Venda Spot ERCOT)
      5. [Opcional: show_total_cost_panel=True] Comparativo do Total Gasto Acumulado Sem BESS vs. Com BESS (US$)
    """
    show_price_panel = time_scale in ('week', 'month')

    if time_scale == 'quarter':
        fig_size = (20, 17.0 if show_total_cost_panel else 13.5)
        lw_net, lw_grid, lw_soc, lw_power, lw_cum = 0.95, 0.95, 1.3, 0.75, 1.8
        alpha_fill, alpha_power, alpha_fin = 0.22, 0.35, 0.45
    elif time_scale == 'month':
        fig_size = (18, 20.0 if show_total_cost_panel else 16.5)
        lw_net, lw_grid, lw_soc, lw_power, lw_cum = 1.2, 1.2, 1.6, 0.9, 2.0
        alpha_fill, alpha_power, alpha_fin = 0.28, 0.45, 0.50
    elif time_scale == 'week':
        fig_size = (16, 19.0 if show_total_cost_panel else 15.5)
        lw_net, lw_grid, lw_soc, lw_power, lw_cum = 1.8, 1.8, 2.2, 1.2, 2.4
        alpha_fill, alpha_power, alpha_fin = 0.32, 0.55, 0.55
    else:
        fig_size = (15, 18.5 if show_total_cost_panel else 15.0)
        lw_net, lw_grid, lw_soc, lw_power, lw_cum = 2.2, 2.2, 2.8, 1.5, 2.6
        alpha_fill, alpha_power, alpha_fin = 0.35, 0.60, 0.60

    if show_price_panel and show_total_cost_panel:
        fig, (ax1, ax2, ax3, ax4, ax5) = plt.subplots(
            5,
            1,
            figsize=fig_size,
            sharex=True,
            gridspec_kw={'height_ratios': [1.25, 1.0, 1.1, 0.95, 1.1]},
        )
    elif show_price_panel:
        fig, (ax1, ax2, ax3, ax4) = plt.subplots(
            4,
            1,
            figsize=fig_size,
            sharex=True,
            gridspec_kw={'height_ratios': [1.25, 1.0, 1.1, 0.95]},
        )
        ax5 = None
    elif show_total_cost_panel:
        fig, (ax1, ax2, ax3, ax5) = plt.subplots(
            4,
            1,
            figsize=fig_size,
            sharex=True,
            gridspec_kw={'height_ratios': [1.25, 1.0, 1.1, 1.1]},
        )
        ax4 = None
    else:
        fig, (ax1, ax2, ax3) = plt.subplots(
            3,
            1,
            figsize=fig_size,
            sharex=True,
            gridspec_kw={'height_ratios': [1.25, 1.0, 1.1]},
        )
        ax4 = None
        ax5 = None

    # --------------------------------------------------------------------------
    # PAINEL 1: Demanda da Microrrede (Net Load vs Grid Exchange)
    # --------------------------------------------------------------------------
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
        label='Demanda com Bateria (Grid Exchange - Otimizado ERCOT Spot + TDSP)',
    )
    ax1.axhline(0, color='black', linewidth=0.8, alpha=0.7)

    ax1.fill_between(
        df_res['timestamp'],
        df_res['net_load'],
        df_res['grid_exchange'],
        where=(df_res['net_load'] > df_res['grid_exchange']),
        color='orange',
        alpha=alpha_fill,
        label='Descarga da Bateria (Abatendo Pico Spot / Exportando com Lucro à Rede)',
    )
    ax1.fill_between(
        df_res['timestamp'],
        df_res['net_load'],
        df_res['grid_exchange'],
        where=(df_res['net_load'] < df_res['grid_exchange']),
        color='cyan',
        alpha=alpha_fill,
        label='Carga da Bateria (Recarga no Vale Eólico Noturno / Excesso Solar)',
    )

    ax1.set_ylabel('Potência Ativa (kW)', fontsize=12, fontweight='bold')
    ax1.set_title(title, fontsize=13, fontweight='bold')
    ax1.legend(loc='upper right', framealpha=0.9)
    ax1.grid(True, alpha=0.3)

    # --------------------------------------------------------------------------
    # PAINEL 2: Ciclo Físico da Bateria (SOC % e Potência do Inversor)
    # --------------------------------------------------------------------------
    ax2.plot(
        df_res['timestamp'],
        df_res['bess_soc_pct'],
        color='green',
        linewidth=lw_soc,
        label='Estado de Carga da Bateria (SOC %)',
    )
    ax2.set_ylabel('Carga da Bateria (% SOC)', fontsize=12, fontweight='bold', color='green')
    ax2.tick_params(axis='y', labelcolor='green')
    ax2.set_ylim(-5, 105)
    ax2.axhline(100, color='gray', linestyle=':', alpha=0.6)
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
    ax2.grid(True, alpha=0.3)

    lines_1, labels_1 = ax2.get_legend_handles_labels()
    lines_2, labels_2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper right', framealpha=0.9)

    # --------------------------------------------------------------------------
    # PAINEL 3: Balanço Monetário da Bateria (Fluxo Horário US$/h e Economia Acumulada US$)
    # --------------------------------------------------------------------------
    total_no_bess = df_res['cost_no_bess_usd'].sum()
    total_with_bess = df_res['cost_with_bess_usd'].sum()
    total_savings = df_res['bess_balance_usd'].sum()
    savings_pct = (total_savings / abs(total_no_bess) * 100.0) if total_no_bess != 0 else 0.0

    ax3.axhline(0, color='black', linewidth=0.8, alpha=0.7)
    ax3.fill_between(
        df_res['timestamp'],
        0,
        df_res['bess_balance_usd'],
        where=(df_res['bess_balance_usd'] >= 0),
        color='#27ae60',
        alpha=alpha_fin,
        step='mid',
        label='Ganho na Descarga (+US$/h: Economia no Pico / Venda Spot ERCOT)',
    )
    ax3.fill_between(
        df_res['timestamp'],
        0,
        df_res['bess_balance_usd'],
        where=(df_res['bess_balance_usd'] < 0),
        color='#c0392b',
        alpha=alpha_fin,
        step='mid',
        label='Custo na Recarga (-US$/h: Compra no Vale da Madrugada / Retenção Solar)',
    )
    ax3.plot(
        df_res['timestamp'],
        df_res['bess_balance_usd'],
        color='#2c3e50',
        linewidth=lw_power * 0.8,
        alpha=0.6,
    )
    ax3.set_ylabel('Fluxo BESS Horário (US$/h)', fontsize=11.5, fontweight='bold', color='#2c3e50')
    ax3.tick_params(axis='y', labelcolor='#2c3e50')
    ax3.grid(True, alpha=0.3)

    ax3_twin = ax3.twinx()
    ax3_twin.plot(
        df_res['timestamp'],
        df_res['cumulative_bess_savings_usd'],
        color='#d35400',
        linewidth=lw_cum,
        label=(
            f'Economia/Lucro Líquido Acumulado: US\\$ {total_savings:,.2f} ({savings_pct:.1f}%) '
            f'[Sem BESS: US\\$ {total_no_bess:,.2f} -> Com BESS: US\\$ {total_with_bess:,.2f}]'
        ),
    )
    ax3_twin.set_ylabel('Economia Acumulada (US$)', fontsize=11.5, fontweight='bold', color='#d35400')
    ax3_twin.tick_params(axis='y', labelcolor='#d35400')

    lines_3a, labels_3a = ax3.get_legend_handles_labels()
    lines_3b, labels_3b = ax3_twin.get_legend_handles_labels()
    ax3.legend(lines_3a + lines_3b, labels_3a + labels_3b, loc='upper left', framealpha=0.9)

    # --------------------------------------------------------------------------
    # PAINEL 4 (1 Semana e 1 Mês): Variação do Custo da Energia no Período
    # --------------------------------------------------------------------------
    if show_price_panel and ax4 is not None:
        min_spot = df_res['sell_price_usd'].min()
        mean_spot = df_res['sell_price_usd'].mean()
        max_spot = df_res['sell_price_usd'].max()
        mean_buy = df_res['buy_price_usd'].mean()

        ax4.plot(
            df_res['timestamp'],
            df_res['buy_price_usd'],
            color='#8e44ad',
            linewidth=lw_grid,
            label=f'Tarifa de Compra na Rede (Spot ERCOT + TDSP US\\$ 0,019/kWh) [Média: US\\$ {mean_buy:.3f}/kWh]',
        )
        ax4.plot(
            df_res['timestamp'],
            df_res['sell_price_usd'],
            color='#2980b9',
            linestyle='--',
            linewidth=lw_net * 0.95,
            label=(
                f'Preço Spot Puro ERCOT DAM (Venda/Exportação) '
                f'[Mín: US\\$ {min_spot:.3f} | Méd: US\\$ {mean_spot:.3f} | Máx: US\\$ {max_spot:.3f}/kWh]'
            ),
        )
        ax4.fill_between(
            df_res['timestamp'],
            0,
            df_res['sell_price_usd'],
            color='#3498db',
            alpha=0.18,
        )
        ax4.fill_between(
            df_res['timestamp'],
            df_res['sell_price_usd'],
            df_res['buy_price_usd'],
            color='#9b59b6',
            alpha=0.22,
            label='Parcela de Fio TDSP na Importação (US\\$ 0,01896/kWh)',
        )
        ax4.axhline(
            mean_spot,
            color='#e67e22',
            linestyle=':',
            linewidth=1.4,
            label=f'Média Spot do Período (US\\$ {mean_spot:.3f}/kWh = US\\$ {mean_spot*1000:.1f}/MWh)',
        )

        ax4.set_ylabel('Preço Energia (US$/kWh)', fontsize=11.5, fontweight='bold', color='#2c3e50')
        ax4.tick_params(axis='y', labelcolor='#2c3e50')
        ax4.grid(True, alpha=0.3)

        # Eixo secundário equivalente em US$/MWh (padrão atacadista ERCOT)
        ax4_twin = ax4.twinx()
        y1_min, y1_max = ax4.get_ylim()
        ax4_twin.set_ylim(y1_min * 1000.0, y1_max * 1000.0)
        ax4_twin.set_ylabel('Cotação Atacado (US$/MWh)', fontsize=11, fontweight='bold', color='#2980b9')
        ax4_twin.tick_params(axis='y', labelcolor='#2980b9')

        ax4.legend(loc='upper right', framealpha=0.9)
        bottom_ax = ax4
    else:
        bottom_ax = ax3

    # --------------------------------------------------------------------------
    # PAINEL 5 (Opcional): Comparativo do Total Gasto Acumulado Sem BESS vs. Com BESS (US$)
    # --------------------------------------------------------------------------
    if show_total_cost_panel and ax5 is not None:
        ax5.plot(
            df_res['timestamp'],
            df_res['cumulative_cost_no_bess_usd'],
            color='crimson',
            linewidth=lw_cum,
            label=f'Total Gasto Acumulado na Rede SEM BESS: US\\$ {total_no_bess:,.2f}',
        )
        ax5.plot(
            df_res['timestamp'],
            df_res['cumulative_cost_with_bess_usd'],
            color='navy',
            linestyle='--',
            linewidth=lw_cum,
            label=f'Total Gasto Acumulado de Energia COM BESS: US\\$ {total_with_bess:,.2f}',
        )
        ax5.fill_between(
            df_res['timestamp'],
            df_res['cumulative_cost_with_bess_usd'],
            df_res['cumulative_cost_no_bess_usd'],
            color='#27ae60',
            alpha=0.22,
            label=f'Economia/Lucro Acumulado (Diferença Sem BESS - Com BESS): US\\$ {total_savings:,.2f} (-{savings_pct:.1f}%)',
        )
        ax5.axhline(0, color='black', linewidth=0.8, alpha=0.6)
        ax5.set_ylabel('Total Gasto Acumulado (US$)', fontsize=11.5, fontweight='bold', color='#2c3e50')
        ax5.tick_params(axis='y', labelcolor='#2c3e50')
        ax5.grid(True, alpha=0.3)
        ax5.legend(loc='upper left', framealpha=0.9)
        bottom_ax = ax5

    bottom_ax.set_xlabel('Tempo (Calendário Real 2018 - Mercado Atacadista ERCOT DAM LZ_AEN + TDSP)', fontsize=12, fontweight='bold')

    # Formatação do eixo X conforme escala
    if time_scale == 'quarter':
        bottom_ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))
        bottom_ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b'))
        bottom_ax.xaxis.set_minor_locator(mdates.DayLocator(interval=1))
    elif time_scale == 'month':
        bottom_ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        bottom_ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b'))
        bottom_ax.xaxis.set_minor_locator(mdates.DayLocator(interval=1))
    elif time_scale == 'week':
        bottom_ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12]))
        bottom_ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b %Hh'))
        bottom_ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 18]))
    else:
        bottom_ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b %Hh'))

    plt.tight_layout()

    dest_dirs = [
        os.path.join(base_dir, 'data', '3_otimizador_ercot_atacado', 'imagens'),
        os.path.join(base_dir, 'Resultados de Otimizacao'),
    ]
    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)
        out_file = os.path.join(d, out_filename)
        plt.savefig(out_file, dpi=160, bbox_inches='tight')
        print(f"Gráfico ERCOT salvo com sucesso em: {out_file}")
    plt.close()


def load_ercot_dataset():
    """
    Carrega a base unificada da microrrede com os preços horários reais do ERCOT DAM 2018 (LZ_AEN),
    alinhando os timestamps ao horário local de Austin (America/Chicago).
    Fórmula da demanda líquida: NetLoad[t] = Load[t] - Solar[t].
    """
    data_path = os.path.join(base_dir, 'data', '3_otimizador_ercot_atacado', 'dados', 'microgrid_ercot_atacado_2018.csv')
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
    df['ercot_spp_usd_mwh'] = df['ercot_spp_usd_mwh'].interpolate(method='linear')
    df['ercot_spp_usd_kwh'] = df['ercot_spp_usd_kwh'].interpolate(method='linear')
    df = df.reset_index()
    df['net_load'] = df['load'] - df['total_solar']
    return df


def run_all_ercot_simulations():
    df = load_ercot_dataset()
    summary_rows = []

    # 1. Horizonte de 1 Semana Padrão (02/Jul a 09/Jul/2018)
    print("\n=== [ERCOT ATACADO + TDSP] GERANDO GRÁFICO PARA 1 SEMANA (02/Jul a 09/Jul) ===")
    start_week = '2018-07-02 00:00:00'
    end_week = '2018-07-09 00:00:00'
    df_week = df[(df['timestamp'] >= start_week) & (df['timestamp'] < end_week)].copy().reset_index(drop=True)
    res_week = simulate_ercot_period(df_week)
    plot_ercot_bess_simulation(
        res_week,
        title='Otimizador Monetário ERCOT (Spot + TDSP) - 1 Semana (02/Jul a 09/Jul/2018)',
        out_filename='grafico_ercot_1semana.png',
        time_scale='week',
    )
    summary_rows.append(_extract_summary('1 Semana Padrão (02/Jul a 09/Jul)', res_week, 'grafico_ercot_1semana.png'))

    # 2. Horizonte de 1 Semana de Onda de Calor Extrema (16/Jul a 23/Jul/2018 - Pico US$ 2,06/kWh)
    print("\n=== [ERCOT ATACADO + TDSP] GERANDO GRÁFICO PARA SEMANA DE ONDA DE CALOR (16/Jul a 23/Jul) ===")
    start_hw = '2018-07-16 00:00:00'
    end_hw = '2018-07-23 00:00:00'
    df_hw = df[(df['timestamp'] >= start_hw) & (df['timestamp'] < end_hw)].copy().reset_index(drop=True)
    res_hw = simulate_ercot_period(df_hw)
    plot_ercot_bess_simulation(
        res_hw,
        title='Otimizador Monetário ERCOT (Spot + TDSP) - Onda de Calor Extrema (16/Jul a 23/Jul/2018 - Pico US$ 2,06/kWh)',
        out_filename='grafico_ercot_1semana_onda_calor.png',
        time_scale='week',
    )
    summary_rows.append(_extract_summary('1 Semana Onda de Calor (16/Jul a 23/Jul)', res_hw, 'grafico_ercot_1semana_onda_calor.png'))

    # 3. Horizonte de 1 Mês Completo (Julho de 2018)
    print("\n=== [ERCOT ATACADO + TDSP] GERANDO GRÁFICO PARA 1 MÊS (Julho/2018) ===")
    start_month = '2018-07-01 00:00:00'
    end_month = '2018-08-01 00:00:00'
    df_month = df[(df['timestamp'] >= start_month) & (df['timestamp'] < end_month)].copy().reset_index(drop=True)
    res_month = simulate_ercot_period(df_month)
    plot_ercot_bess_simulation(
        res_month,
        title='Otimizador Monetário ERCOT (Spot + TDSP) - Mês Completo (Julho de 2018)',
        out_filename='grafico_ercot_1mes.png',
        time_scale='month',
    )
    summary_rows.append(_extract_summary('1 Mês Completo (Julho/2018)', res_month, 'grafico_ercot_1mes.png'))

    # 3B. Horizonte de 1 Mês sem Onda de Calor (Agosto de 2018) - Comparativo de Gasto Total
    print("\n=== [ERCOT ATACADO + TDSP] GERANDO GRÁFICO COMPARATIVO DE CUSTOS TOTAIS (Agosto/2018) ===")
    start_aug = '2018-08-01 00:00:00'
    end_aug = '2018-09-01 00:00:00'
    df_aug = df[(df['timestamp'] >= start_aug) & (df['timestamp'] < end_aug)].copy().reset_index(drop=True)
    res_aug = simulate_ercot_period(df_aug)
    plot_ercot_bess_simulation(
        res_aug,
        title='Otimizador Monetário ERCOT (Spot + TDSP) - Mês Completo (Agosto de 2018) - Comparativo de Gasto Total',
        out_filename='grafico_ercot_custos_1mes.png',
        time_scale='month',
        show_total_cost_panel=True,
    )

    # 4. Horizontes dos 4 Trimestres
    quarters_config = [
        {
            'name': '1º Trimestre (Jan a Mar / 2018 - Inverno)',
            'days': 90,
            'start_idx': 0,
            'filename': 'grafico_ercot_trimestre1_jan_mar.png',
        },
        {
            'name': '2º Trimestre (Abr a Jun / 2018 - Primavera)',
            'days': 91,
            'start_idx': 90 * 24,
            'filename': 'grafico_ercot_trimestre2_abr_jun.png',
        },
        {
            'name': '3º Trimestre (Jul a Set / 2018 - Verão)',
            'days': 92,
            'start_idx': (90 + 91) * 24,
            'filename': 'grafico_ercot_trimestre3_jul_set.png',
        },
        {
            'name': '4º Trimestre (Out a Dez / 2018 - Outono)',
            'days': 92,
            'start_idx': (90 + 91 + 92) * 24,
            'filename': 'grafico_ercot_trimestre4_out_dez.png',
        },
    ]

    for q in quarters_config:
        print(f"\n=== [ERCOT ATACADO + TDSP] SIMULANDO {q['name']} ===")
        end_idx = q['start_idx'] + q['days'] * 24
        df_q = df.iloc[q['start_idx'] : end_idx].copy().reset_index(drop=True)
        res_q = simulate_ercot_period(df_q)
        plot_ercot_bess_simulation(
            res_q,
            title=f"Otimizador Monetário ERCOT (Spot + TDSP) - {q['name']}",
            out_filename=q['filename'],
            time_scale='quarter',
        )
        summary_rows.append(_extract_summary(q['name'], res_q, q['filename']))

    _save_markdown_report(summary_rows)
    return summary_rows


def _extract_summary(period_name, df_res, filename):
    cost_no = df_res['cost_no_bess_usd'].sum()
    cost_with = df_res['cost_with_bess_usd'].sum()
    savings = df_res['bess_balance_usd'].sum()
    savings_pct = (savings / abs(cost_no) * 100.0) if cost_no != 0 else 0.0
    orig_peak = df_res['net_load'].max()
    opt_peak = df_res['grid_exchange'].max()
    peak_red_pct = ((orig_peak - opt_peak) / orig_peak * 100.0) if orig_peak > 0 else 0.0
    max_spot = df_res['sell_price_usd'].max()

    print(
        f"-> {period_name}: Sem BESS = US$ {cost_no:,.2f} | Com BESS = US$ {cost_with:,.2f} | "
        f"Economia/Lucro = US$ {savings:,.2f} ({savings_pct:.1f}%) | Spot Máx: US$ {max_spot:.3f}/kWh"
    )
    return {
        'periodo': period_name,
        'cost_no_bess': cost_no,
        'cost_with_bess': cost_with,
        'savings_usd': savings,
        'savings_pct': savings_pct,
        'orig_peak': orig_peak,
        'opt_peak': opt_peak,
        'peak_red_pct': peak_red_pct,
        'max_spot_usd_kwh': max_spot,
        'filename': filename,
    }


def _save_markdown_report(summary_rows):
    report_paths = [
        os.path.join(base_dir, 'data', '3_otimizador_ercot_atacado', 'dados', 'relatorio_ercot_atacado.md'),
        os.path.join(base_dir, 'Resultados de Otimizacao', 'relatorio_ercot_atacado.md'),
    ]
    lines = [
        "# Relatório de Resultados - Otimizador Puramente Monetário ERCOT (RTW + TDSP)",
        "",
        "## 1. Parâmetros Regulatórios e de Mercado Utilizados",
        "- **Operador de Mercado / Zona de Liquidação:** ERCOT Day-Ahead Market (DAM) — `LZ_AEN` (Austin Energy, 2018)",
        "- **Modalidade Tarifária:** Real-Time Wholesale (RTW) com repasse de taxa de fio (TDSP) na importação:",
        "  - **Preço de Venda / Exportação (`sell_price[t]`):** 100% do preço spot horário do ERCOT (`ercot_spp_usd_kwh[t]`)",
        "  - **Preço de Compra / Importação (`buy_price[t]`):** `ercot_spp_usd_kwh[t]` + **US\\$ 0,01896 / kWh** (*Regulatory Charge* US\\$ 0,01342 + *Community Benefit* US\\$ 0,00554 da Austin Energy)",
        "  - **Autoconsumo Local (*Behind-the-Meter*):** Isento de compra na rede e isento da taxa TDSP",
        "- **Critério Secundário de Desempate (Tie-breaker):** Micro-peso (`1e-6 US$/kW`) sobre `P_max - P_min`",
        "",
        "## 2. Resumo Financeiro e Operacional por Horizonte",
        "",
        "| Horizonte Simulado | Custo Sem BESS (US\\$) | Custo/Saldo Com BESS (US\\$) | Economia / Lucro Gerado (US\\$) | Economia (%) | Spot Máx (US\\$/kWh) | Pico Original (kW) | Pico Com BESS (kW) | Arquivo de Gráfico |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]
    for r in summary_rows:
        lines.append(
            f"| {r['periodo']} | US\\$ {r['cost_no_bess']:,.2f} | US\\$ {r['cost_with_bess']:,.2f} | "
            f"**US\\$ {r['savings_usd']:,.2f}** | **{r['savings_pct']:.1f}%** | "
            f"US\\$ {r['max_spot_usd_kwh']:.3f} | {r['orig_peak']:.2f} | {r['opt_peak']:.2f} | `{r['filename']}` |"
        )

    q_rows = summary_rows[3:]
    if len(q_rows) == 4:
        tot_no = sum(r['cost_no_bess'] for r in q_rows)
        tot_with = sum(r['cost_with_bess'] for r in q_rows)
        tot_sav = sum(r['savings_usd'] for r in q_rows)
        tot_pct = (tot_sav / tot_no * 100.0) if tot_no != 0 else 0.0
        max_yr_spot = max(r['max_spot_usd_kwh'] for r in q_rows)
        lines.append(
            f"| **Total Anual (2018 Completo - 365 dias)** | **US\\$ {tot_no:,.2f}** | **US\\$ {tot_with:,.2f}** | "
            f"**US\\$ {tot_sav:,.2f}** | **{tot_pct:.1f}%** | **US\\$ {max_yr_spot:.3f}** | - | - | - |"
        )

    content = "\n".join(lines) + "\n"
    for p in report_paths:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Relatório ERCOT salvo em: {p}")


def run_ercot_monthly_cost_comparison():
    """
    Gera exclusivamente a nova figura mensal (Agosto de 2018 - sem onda de calor) com o
    5º painel de comparativo de Total Gasto Acumulado Sem BESS vs. Com BESS
    (grafico_ercot_custos_1mes.png), preservando todos os arquivos PNG anteriores intactos.
    """
    df = load_ercot_dataset()
    print("\n=== [ERCOT ATACADO + TDSP] GERANDO GRÁFICO MENSAL (AGOSTO/2018) COM COMPARATIVO DE CUSTOS TOTAIS ===")
    start_month = '2018-08-01 00:00:00'
    end_month = '2018-09-01 00:00:00'
    df_month = df[(df['timestamp'] >= start_month) & (df['timestamp'] < end_month)].copy().reset_index(drop=True)
    res_month = simulate_ercot_period(df_month)
    plot_ercot_bess_simulation(
        res_month,
        title='Otimizador Monetário ERCOT (Spot + TDSP) - Mês Completo (Agosto de 2018) - Comparativo de Gasto Total',
        out_filename='grafico_ercot_custos_1mes.png',
        time_scale='month',
        show_total_cost_panel=True,
    )
    _extract_summary('1 Mês Comparativo Custos (Agosto/2018)', res_month, 'grafico_ercot_custos_1mes.png')


if __name__ == '__main__':
    if '--only-monthly-costs' in sys.argv:
        run_ercot_monthly_cost_comparison()
    else:
        run_all_ercot_simulations()
