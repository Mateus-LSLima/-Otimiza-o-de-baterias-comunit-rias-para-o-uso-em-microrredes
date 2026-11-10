import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Garante que o Python encontre src/control e a pasta raiz
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(base_dir, 'src', 'control'))

from optimizer_tariff import OptimizerTariffBESS


def simulate_tariff_period(
    df_subset,
    capacity_kwh=200.0,
    max_power_kw=50.0,
    efficiency=0.95,
    initial_soc=0.50,
):
    """
    Executa a otimização econômica diária (Tarifa Branca + Fio B + Tie-breaker Peak Shaving)
    em blocos de 24h para o subconjunto de dados fornecido.
    """
    opt = OptimizerTariffBESS(
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
    print(f"Otimizando (Tarifa Branca + Fio B) para {num_days} dias ({num_days * 24} horas)...")

    for day in range(num_days):
        slice_df = df_subset.iloc[day * 24 : (day + 1) * 24]
        day_net_load = slice_df['net_load'].tolist()
        day_timestamps = slice_df['timestamp'].tolist()

        # Garante que toda janela de 24h receba a previsão exatamente às 00h (horário local do Texas)
        assert pd.Timestamp(day_timestamps[0]).hour == 0 and pd.Timestamp(day_timestamps[-1]).hour == 23, (
            f"Erro de alinhamento no dia {day}: início={day_timestamps[0]}, fim={day_timestamps[-1]}"
        )

        buy_p, sell_p = opt.get_hourly_tariffs(timestamps_24h=day_timestamps)
        plan = opt.optimize_24h(
            day_net_load,
            initial_soc=(current_energy / capacity_kwh),
            timestamps_24h=day_timestamps,
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
            cost_no_bess_list.append(fin['cost_no_bess_brl'])
            cost_with_bess_list.append(fin['cost_with_bess_brl'])
            bess_balance_list.append(fin['bess_balance_brl'])

    res = df_subset.iloc[: len(bess_power_list)].copy()
    res['bess_power'] = bess_power_list
    res['bess_energy_kwh'] = bess_energy_list
    res['bess_soc_pct'] = (res['bess_energy_kwh'] / capacity_kwh) * 100.0
    res['grid_exchange'] = grid_exchange_list
    res['buy_price_brl'] = buy_price_list
    res['sell_price_brl'] = sell_price_list
    res['cost_no_bess_brl'] = cost_no_bess_list
    res['cost_with_bess_brl'] = cost_with_bess_list
    res['bess_balance_brl'] = bess_balance_list
    res['cumulative_cost_no_bess_brl'] = res['cost_no_bess_brl'].cumsum()
    res['cumulative_cost_with_bess_brl'] = res['cost_with_bess_brl'].cumsum()
    res['cumulative_bess_savings_brl'] = res['bess_balance_brl'].cumsum()
    return res


def plot_tariff_bess_simulation(df_res, title, out_filename, time_scale='week', show_total_cost_panel=False):
    """
    Gera o gráfico sincronizado:
      1. Curva de Demanda (Net Load vs Grid Exchange)
      2. Dinâmica da Bateria (SOC % e Potência do Inversor kW)
      3. Balanço Monetário da Bateria (Fluxo Horário R$/h de Compra/Venda + Economia Acumulada R$)
      4. [Opcional: show_total_cost_panel=True] Comparativo do Total Gasto Acumulado Sem BESS vs. Com BESS (R$)
    """
    if time_scale == 'quarter':
        fig_size = (20, 17.0 if show_total_cost_panel else 13.5)
        lw_net, lw_grid, lw_soc, lw_power, lw_cum = 0.95, 0.95, 1.3, 0.75, 1.8
        alpha_fill, alpha_power, alpha_fin = 0.22, 0.35, 0.45
    elif time_scale == 'month':
        fig_size = (18, 16.5 if show_total_cost_panel else 13)
        lw_net, lw_grid, lw_soc, lw_power, lw_cum = 1.2, 1.2, 1.6, 0.9, 2.0
        alpha_fill, alpha_power, alpha_fin = 0.28, 0.45, 0.50
    elif time_scale == 'week':
        fig_size = (16, 15.5 if show_total_cost_panel else 12.5)
        lw_net, lw_grid, lw_soc, lw_power, lw_cum = 1.8, 1.8, 2.2, 1.2, 2.4
        alpha_fill, alpha_power, alpha_fin = 0.32, 0.55, 0.55
    else:
        fig_size = (15, 15.0 if show_total_cost_panel else 12)
        lw_net, lw_grid, lw_soc, lw_power, lw_cum = 2.2, 2.2, 2.8, 1.5, 2.6
        alpha_fill, alpha_power, alpha_fin = 0.35, 0.60, 0.60

    if show_total_cost_panel:
        fig, (ax1, ax2, ax3, ax4) = plt.subplots(
            4,
            1,
            figsize=fig_size,
            sharex=True,
            gridspec_kw={'height_ratios': [1.25, 1.0, 1.1, 1.1]},
        )
    else:
        fig, (ax1, ax2, ax3) = plt.subplots(
            3,
            1,
            figsize=fig_size,
            sharex=True,
            gridspec_kw={'height_ratios': [1.25, 1.0, 1.1]},
        )
        ax4 = None

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
        label='Demanda com Bateria (Grid Exchange - Otimizado Tarifa Branca + Fio B)',
    )
    ax1.axhline(0, color='black', linewidth=0.8, alpha=0.7)

    ax1.fill_between(
        df_res['timestamp'],
        df_res['net_load'],
        df_res['grid_exchange'],
        where=(df_res['net_load'] > df_res['grid_exchange']),
        color='orange',
        alpha=alpha_fill,
        label='Descarga da Bateria (Abatendo Ponta / Vendendo à Rede)',
    )
    ax1.fill_between(
        df_res['timestamp'],
        df_res['net_load'],
        df_res['grid_exchange'],
        where=(df_res['net_load'] < df_res['grid_exchange']),
        color='cyan',
        alpha=alpha_fill,
        label='Carga da Bateria (Absorvendo Excesso Solar / Comprando Fora de Ponta)',
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
    # PAINEL 3: Balanço Monetário da Bateria (Fluxo Horário R$/h e Economia Acumulada R$)
    # --------------------------------------------------------------------------
    total_no_bess = df_res['cost_no_bess_brl'].sum()
    total_with_bess = df_res['cost_with_bess_brl'].sum()
    total_savings = df_res['bess_balance_brl'].sum()
    savings_pct = (total_savings / abs(total_no_bess) * 100.0) if total_no_bess != 0 else 0.0

    ax3.axhline(0, color='black', linewidth=0.8, alpha=0.7)
    ax3.fill_between(
        df_res['timestamp'],
        0,
        df_res['bess_balance_brl'],
        where=(df_res['bess_balance_brl'] >= 0),
        color='#27ae60',
        alpha=alpha_fin,
        step='mid',
        label='Ganho na Descarga (+R$/h: Economia na Ponta / Venda com Fio B)',
    )
    ax3.fill_between(
        df_res['timestamp'],
        0,
        df_res['bess_balance_brl'],
        where=(df_res['bess_balance_brl'] < 0),
        color='#c0392b',
        alpha=alpha_fin,
        step='mid',
        label='Custo na Recarga (-R$/h: Compra na Baixa / Retenção Solar)',
    )
    ax3.plot(
        df_res['timestamp'],
        df_res['bess_balance_brl'],
        color='#2c3e50',
        linewidth=lw_power * 0.8,
        alpha=0.6,
    )
    ax3.set_ylabel('Fluxo BESS Horário (R$/h)', fontsize=11.5, fontweight='bold', color='#2c3e50')
    ax3.tick_params(axis='y', labelcolor='#2c3e50')
    ax3.grid(True, alpha=0.3)

    ax3_twin = ax3.twinx()
    ax3_twin.plot(
        df_res['timestamp'],
        df_res['cumulative_bess_savings_brl'],
        color='#d35400',
        linewidth=lw_cum,
        label=(
            f'Economia Líquida Acumulada: R\\$ {total_savings:,.2f} ({savings_pct:.1f}%) '
            f'[Sem BESS: R\\$ {total_no_bess:,.2f} -> Com BESS: R\\$ {total_with_bess:,.2f}]'
        ),
    )
    ax3_twin.set_ylabel('Economia Acumulada (R$)', fontsize=11.5, fontweight='bold', color='#d35400')
    ax3_twin.tick_params(axis='y', labelcolor='#d35400')

    lines_3a, labels_3a = ax3.get_legend_handles_labels()
    lines_3b, labels_3b = ax3_twin.get_legend_handles_labels()
    ax3.legend(lines_3a + lines_3b, labels_3a + labels_3b, loc='upper left', framealpha=0.9)

    # --------------------------------------------------------------------------
    # PAINEL 4 (Opcional): Comparativo do Total Gasto Acumulado Sem BESS vs. Com BESS (R$)
    # --------------------------------------------------------------------------
    if show_total_cost_panel and ax4 is not None:
        ax4.plot(
            df_res['timestamp'],
            df_res['cumulative_cost_no_bess_brl'],
            color='crimson',
            linewidth=lw_cum,
            label=f'Total Gasto Acumulado na Rede SEM BESS: R\\$ {total_no_bess:,.2f}',
        )
        ax4.plot(
            df_res['timestamp'],
            df_res['cumulative_cost_with_bess_brl'],
            color='navy',
            linestyle='--',
            linewidth=lw_cum,
            label=f'Total Gasto Acumulado de Energia COM BESS: R\\$ {total_with_bess:,.2f}',
        )
        ax4.fill_between(
            df_res['timestamp'],
            df_res['cumulative_cost_with_bess_brl'],
            df_res['cumulative_cost_no_bess_brl'],
            color='#27ae60',
            alpha=0.22,
            label=f'Economia Acumulada (Diferença Sem BESS - Com BESS): R\\$ {total_savings:,.2f} (-{savings_pct:.1f}%)',
        )
        ax4.axhline(0, color='black', linewidth=0.8, alpha=0.6)
        ax4.set_ylabel('Total Gasto Acumulado (R$)', fontsize=11.5, fontweight='bold', color='#2c3e50')
        ax4.tick_params(axis='y', labelcolor='#2c3e50')
        ax4.grid(True, alpha=0.3)
        ax4.legend(loc='upper left', framealpha=0.9)
        bottom_ax = ax4
    else:
        bottom_ax = ax3

    bottom_ax.set_xlabel('Tempo (Calendário Real 2018 - Tarifas CPFL Paulista + 60% Fio B)', fontsize=12, fontweight='bold')

    # --------------------------------------------------------------------------
    # LINHAS VERTICAIS PONTILHADAS DE TROCA DE PREÇO (1 Semana e 1 Mês)
    # --------------------------------------------------------------------------
    if time_scale in ('week', 'month') and 'buy_price_brl' in df_res.columns:
        price_diff = df_res['buy_price_brl'].diff().fillna(0.0)
        change_rows = df_res[price_diff != 0.0]

        lw_vline = 1.15 if time_scale == 'week' else 0.75
        alpha_vline = 0.70 if time_scale == 'week' else 0.45

        added_ponta_label = False
        added_inter_label = False
        added_fp_label = False

        for _, row in change_rows.iterrows():
            ts_change = row['timestamp']
            new_price = row['buy_price_brl']

            # Define cor conforme o novo posto tarifário que se inicia naquele horário
            if np.isclose(new_price, 1.299, atol=1e-2):
                v_color = '#c0392b'  # Entrada na Ponta (18h)
                lbl = 'Troca Tarifária: Início Ponta (18h - R$ 1,299)' if not added_ponta_label else None
                added_ponta_label = True
            elif np.isclose(new_price, 0.883, atol=1e-2):
                v_color = '#e67e22'  # Entrada no Intermediário (16h e 21h)
                lbl = 'Troca Tarifária: Intermediário (16h/21h - R$ 0,883)' if not added_inter_label else None
                added_inter_label = True
            else:
                v_color = '#2980b9'  # Retorno para Fora de Ponta (22h)
                lbl = 'Troca Tarifária: Fora de Ponta (22h - R$ 0,625)' if not added_fp_label else None
                added_fp_label = True

            ax1.axvline(ts_change, color=v_color, linestyle=':', linewidth=lw_vline, alpha=alpha_vline, label=lbl)
            ax2.axvline(ts_change, color=v_color, linestyle=':', linewidth=lw_vline, alpha=alpha_vline)
            ax3.axvline(ts_change, color=v_color, linestyle=':', linewidth=lw_vline, alpha=alpha_vline)
            if ax4 is not None:
                ax4.axvline(ts_change, color=v_color, linestyle=':', linewidth=lw_vline, alpha=alpha_vline)

        # Atualiza legenda do Painel 1 para incluir os marcos de troca tarifária
        ax1.legend(loc='upper right', framealpha=0.9, fontsize=9.5)

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
        os.path.join(base_dir, 'data', '2_otimizador_tarifa_branca_brasil', 'imagens'),
        os.path.join(base_dir, 'Resultados de Otimizacao'),
    ]
    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)
        out_file = os.path.join(d, out_filename)
        if os.path.exists(out_file):
            try:
                os.remove(out_file)
            except OSError:
                pass
        with open(out_file, 'wb') as f:
            plt.savefig(f, format='png', dpi=160, bbox_inches='tight')
        print(f"Gráfico tarifário salvo com sucesso em: {out_file}")
    plt.close()


def load_preprocessed_dataset():
    """
    Carrega a série horária da microrrede e alinha os timestamps ao fuso local de Austin
    (America/Chicago) para aplicação do calendário da Tarifa Branca e plotagem sincronizada.
    Fórmula da demanda líquida: NetLoad[t] = Load[t] - Solar[t].
    """
    candidate_paths = [
        os.path.join(base_dir, 'data', '2_otimizador_tarifa_branca_brasil', 'dados', 'microgrid_tarifa_branca_2018.csv'),
        os.path.join(base_dir, 'data', '1_otimizador_peak_shaving', 'dados', 'community_microgrid.csv'),
        os.path.join(base_dir, 'data', 'community_microgrid.csv'),
    ]
    data_path = next((p for p in candidate_paths if os.path.exists(p)), candidate_paths[-1])
    df = pd.read_csv(data_path)
    df['ts_utc'] = pd.to_datetime(df['timestamp'], utc=True)
    df['timestamp'] = df['ts_utc'].dt.tz_convert('America/Chicago').dt.tz_localize(None)
    # Agrupa eventual hora duplicada no fim do horário de verão (04/Nov) e reamostra na grade civil local (00h..23h)
    df = df.groupby('timestamp', as_index=True)[['load', 'total_solar']].mean()
    df = df.resample('1h').asfreq()
    df['load'] = df['load'].interpolate(method='linear')
    df['total_solar'] = df['total_solar'].interpolate(method='linear')
    df = df.reset_index()
    df['net_load'] = df['load'] - df['total_solar']
    return df


def run_all_tariff_simulations():
    df = load_preprocessed_dataset()
    summary_rows = []

    # 1. Horizonte de 1 Semana
    print("\n=== [TARIFA BRANCA + FIO B] GERANDO GRÁFICO PARA 1 SEMANA ===")
    start_week = '2018-07-02 00:00:00'
    end_week = '2018-07-09 00:00:00'
    df_week = df[(df['timestamp'] >= start_week) & (df['timestamp'] < end_week)].copy().reset_index(drop=True)
    res_week = simulate_tariff_period(df_week)
    plot_tariff_bess_simulation(
        res_week,
        title='Otimizador Econômico (Tarifa Branca + Fio B) - 1 Semana (02/Jul a 09/Jul/2018)',
        out_filename='grafico_tarifab_1semana.png',
        time_scale='week',
    )
    summary_rows.append(_extract_summary('1 Semana (02/Jul a 09/Jul)', res_week, 'grafico_tarifab_1semana.png'))

    # 2. Horizonte de 1 Mês
    print("\n=== [TARIFA BRANCA + FIO B] GERANDO GRÁFICO PARA 1 MÊS ===")
    start_month = '2018-07-01 00:00:00'
    end_month = '2018-08-01 00:00:00'
    df_month = df[(df['timestamp'] >= start_month) & (df['timestamp'] < end_month)].copy().reset_index(drop=True)
    res_month = simulate_tariff_period(df_month)
    plot_tariff_bess_simulation(
        res_month,
        title='Otimizador Econômico (Tarifa Branca + Fio B) - Mês Completo (Julho de 2018)',
        out_filename='grafico_tarifab_1mes.png',
        time_scale='month',
    )
    summary_rows.append(_extract_summary('1 Mês (Julho/2018)', res_month, 'grafico_tarifab_1mes.png'))

    # 2B. Horizonte de 1 Mês sem Onda de Calor (Agosto de 2018) - Comparativo de Gasto Total
    print("\n=== [TARIFA BRANCA + FIO B] GERANDO GRÁFICO COMPARATIVO DE CUSTOS TOTAIS (Agosto/2018) ===")
    start_aug = '2018-08-01 00:00:00'
    end_aug = '2018-09-01 00:00:00'
    df_aug = df[(df['timestamp'] >= start_aug) & (df['timestamp'] < end_aug)].copy().reset_index(drop=True)
    res_aug = simulate_tariff_period(df_aug)
    plot_tariff_bess_simulation(
        res_aug,
        title='Otimizador Econômico (Tarifa Branca + Fio B) - Mês Completo (Agosto de 2018) - Comparativo de Gasto Total',
        out_filename='grafico_tarifab_custos_1mes.png',
        time_scale='month',
        show_total_cost_panel=True,
    )

    # 3. Horizontes dos 4 Trimestres
    quarters_config = [
        {
            'name': '1º Trimestre (Jan a Mar / 2018 - Inverno)',
            'days': 90,
            'start_idx': 0,
            'filename': 'grafico_tarifab_trimestre1_jan_mar.png',
        },
        {
            'name': '2º Trimestre (Abr a Jun / 2018 - Primavera)',
            'days': 91,
            'start_idx': 90 * 24,
            'filename': 'grafico_tarifab_trimestre2_abr_jun.png',
        },
        {
            'name': '3º Trimestre (Jul a Set / 2018 - Verão)',
            'days': 92,
            'start_idx': (90 + 91) * 24,
            'filename': 'grafico_tarifab_trimestre3_jul_set.png',
        },
        {
            'name': '4º Trimestre (Out a Dez / 2018 - Outono)',
            'days': 92,
            'start_idx': (90 + 91 + 92) * 24,
            'filename': 'grafico_tarifab_trimestre4_out_dez.png',
        },
    ]

    for q in quarters_config:
        print(f"\n=== [TARIFA BRANCA + FIO B] SIMULANDO {q['name']} ===")
        end_idx = q['start_idx'] + q['days'] * 24
        df_q = df.iloc[q['start_idx'] : end_idx].copy().reset_index(drop=True)
        res_q = simulate_tariff_period(df_q)
        plot_tariff_bess_simulation(
            res_q,
            title=f"Otimizador Econômico (Tarifa Branca + Fio B) - {q['name']}",
            out_filename=q['filename'],
            time_scale='quarter',
        )
        summary_rows.append(_extract_summary(q['name'], res_q, q['filename']))

    _save_markdown_report(summary_rows)
    return summary_rows


def _extract_summary(period_name, df_res, filename):
    cost_no = df_res['cost_no_bess_brl'].sum()
    cost_with = df_res['cost_with_bess_brl'].sum()
    savings = df_res['bess_balance_brl'].sum()
    savings_pct = (savings / abs(cost_no) * 100.0) if cost_no != 0 else 0.0
    orig_peak = df_res['net_load'].max()
    opt_peak = df_res['grid_exchange'].max()
    peak_red_pct = ((orig_peak - opt_peak) / orig_peak * 100.0) if orig_peak > 0 else 0.0

    print(
        f"-> {period_name}: Sem BESS = R$ {cost_no:,.2f} | Com BESS = R$ {cost_with:,.2f} | "
        f"Economia = R$ {savings:,.2f} ({savings_pct:.1f}%) | Pico: {orig_peak:.1f} -> {opt_peak:.1f} kW"
    )
    return {
        'periodo': period_name,
        'cost_no_bess': cost_no,
        'cost_with_bess': cost_with,
        'savings_brl': savings,
        'savings_pct': savings_pct,
        'orig_peak': orig_peak,
        'opt_peak': opt_peak,
        'peak_red_pct': peak_red_pct,
        'filename': filename,
    }


def _save_markdown_report(summary_rows):
    report_path = os.path.join(base_dir, 'Resultados de Otimizacao', 'relatorio_tarifa_branca_fio_b.md')
    lines = [
        "# Relatório de Resultados - Otimizador Econômico (Tarifa Branca + Fio B)",
        "",
        "## 1. Parâmetros Regulatórios e Tarifários Utilizados",
        "- **Concessionária de Referência:** CPFL Paulista (Resolução ANEEL nº 2.381/2018 & Lei 14.300/2022)",
        "- **Tarifa Branca (Dias Úteis):**",
        "  - **Ponta (18h às 20h59):** R\\$ 1,299 / kWh",
        "  - **Intermediário (16h às 17h59 e 21h às 21h59):** R\\$ 0,883 / kWh",
        "  - **Fora de Ponta (22h às 15h59):** R\\$ 0,625 / kWh",
        "- **Fins de Semana (Sábado e Domingo):** 24h em Fora de Ponta (R\\$ 0,625 / kWh)",
        "- **Penalidade do Fio B na Injeção/Exportação (2026 - 60% da TUSD Fio B):** R\\$ 0,108 / kWh descontados sobre a energia exportada para a rede.",
        "- **Autoconsumo Local (Behind-the-Meter):** Isento de Fio B (custo R\\$ 0,00).",
        "- **Critério de Desempate (Tie-breaker):** Peak Shaving / Valley Filling (`P_max - P_min`) nas horas de tarifa idêntica.",
        "",
        "## 2. Resumo Financeiro e Operacional por Horizonte",
        "",
        "| Horizonte Simulado | Custo Sem BESS (R\\$) | Custo Com BESS (R\\$) | Economia Gerada (R\\$) | Economia (%) | Pico Original (kW) | Pico Com BESS (kW) | Arquivo de Gráfico |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]
    for r in summary_rows:
        lines.append(
            f"| {r['periodo']} | R\\$ {r['cost_no_bess']:,.2f} | R\\$ {r['cost_with_bess']:,.2f} | "
            f"**R\\$ {r['savings_brl']:,.2f}** | **{r['savings_pct']:.1f}%** | "
            f"{r['orig_peak']:.2f} | {r['opt_peak']:.2f} | `{r['filename']}` |"
        )

    q_rows = summary_rows[2:]
    if len(q_rows) == 4:
        tot_no = sum(r['cost_no_bess'] for r in q_rows)
        tot_with = sum(r['cost_with_bess'] for r in q_rows)
        tot_sav = sum(r['savings_brl'] for r in q_rows)
        tot_pct = (tot_sav / tot_no * 100.0) if tot_no != 0 else 0.0
        lines.append(
            f"| **Total Anual (2018 Completo)** | **R\\$ {tot_no:,.2f}** | **R\\$ {tot_with:,.2f}** | "
            f"**R\\$ {tot_sav:,.2f}** | **{tot_pct:.1f}%** | - | - | - |"
        )

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nRelatório consolidado salvo em: {report_path}")


def run_tariff_monthly_cost_comparison():
    """
    Gera exclusivamente a nova figura mensal (Agosto de 2018 - sem onda de calor) com o
    4º painel de comparativo de Total Gasto Acumulado Sem BESS vs. Com BESS
    (grafico_tarifab_custos_1mes.png), preservando todos os arquivos PNG anteriores intactos.
    """
    df = load_preprocessed_dataset()
    print("\n=== [TARIFA BRANCA + FIO B] GERANDO GRÁFICO MENSAL (AGOSTO/2018) COM COMPARATIVO DE CUSTOS TOTAIS ===")
    start_month = '2018-08-01 00:00:00'
    end_month = '2018-09-01 00:00:00'
    df_month = df[(df['timestamp'] >= start_month) & (df['timestamp'] < end_month)].copy().reset_index(drop=True)
    res_month = simulate_tariff_period(df_month)
    plot_tariff_bess_simulation(
        res_month,
        title='Otimizador Econômico (Tarifa Branca + Fio B) - Mês Completo (Agosto de 2018) - Comparativo de Gasto Total',
        out_filename='grafico_tarifab_custos_1mes.png',
        time_scale='month',
        show_total_cost_panel=True,
    )
    _extract_summary('1 Mês Comparativo Custos (Agosto/2018)', res_month, 'grafico_tarifab_custos_1mes.png')


if __name__ == '__main__':
    if '--only-monthly-costs' in sys.argv:
        run_tariff_monthly_cost_comparison()
    else:
        run_all_tariff_simulations()
