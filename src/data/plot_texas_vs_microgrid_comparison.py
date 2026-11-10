# ==============================================================================
# COMPARATIVO DE DEMANDA: MICRORREDE (25 CASAS) vs. TEXAS INTEIRO (ERCOT) vs. PREÇO
# ==============================================================================
#
# Objetivo deste script:
#   Demonstrar visualmente e empiricamente por que o pico de preço da energia no
#   mercado atacadista do Texas (ERCOT) ocorre às 15h–16h, enquanto o pico de
#   demanda da nossa microrrede residencial (25 casas em Austin) ocorre às 18h–20h.
#
# Estrutura dos gráficos gerados (3 painéis verticais sincronizados):
#   1º Painel (Superior) : Carga da Microrrede Comunitária (Net Load e Carga Bruta em kW)
#   2º Painel (Meio)     : Carga Total do Sistema Elétrico do Texas (ERCOT System Load em MW)
#   3º Painel (Inferior) : Variação do Preço da Energia no ERCOT (US$/kWh e US$/MWh)
# ==============================================================================

import os
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

API_KEY = "8ad12354d8bd4ced97c6017a85f2514e"
ERCOT_LOAD_URL = "https://api.gridstatus.io/v1/datasets/ercot_load/query"

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def fetch_or_load_texas_load_july2018():
    """
    Baixa (ou carrega do cache em disco) a demanda horária oficial do sistema
    ERCOT inteiro (em MW) para as semanas de Julho de 2018, convertida para o
    horário local de Austin, Texas (America/Chicago, sem tzinfo).
    """
    cache_path = os.path.join(
        base_dir, 'data', '3_otimizador_ercot_atacado', 'dados', 'ercot_system_load_july2018.csv'
    )
    if os.path.exists(cache_path):
        df_cached = pd.read_csv(cache_path)
        df_cached['timestamp'] = pd.to_datetime(df_cached['timestamp'])
        return df_cached

    print("Baixando curva de carga oficial do estado do Texas (ERCOT System Load) via API GridStatus...")
    windows = [
        ("2018-07-01T00:00:00Z", "2018-07-11T00:00:00Z"),
        ("2018-07-15T00:00:00Z", "2018-07-25T00:00:00Z"),
    ]
    frames = []
    headers = {"x-api-key": API_KEY}

    for start_utc, end_utc in windows:
        params = {
            "start_time": start_utc,
            "end_time": end_utc,
            "limit": 5000,
        }
        r = requests.get(ERCOT_LOAD_URL, params=params, headers=headers)
        if r.status_code != 200:
            raise RuntimeError(f"Erro ao consultar API GridStatus ({r.status_code}): {r.text}")
        data = r.json().get("data", [])
        frames.append(pd.DataFrame(data))

    df_raw = pd.concat(frames, ignore_index=True)
    df_raw['timestamp'] = (
        pd.to_datetime(df_raw['interval_start_utc'], utc=True)
        .dt.tz_convert('America/Chicago')
        .dt.tz_localize(None)
    )
    df_hourly = (
        df_raw.drop_duplicates(subset=['timestamp'])
        .set_index('timestamp')[['load']]
        .resample('1h')
        .mean()
        .rename(columns={'load': 'texas_load_mw'})
        .dropna()
        .reset_index()
    )

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    df_hourly.to_csv(cache_path, index=False)
    print(f"Base de carga do Texas salva em: {cache_path}")
    return df_hourly


def load_merged_comparison_data():
    """
    Combina os dados da microrrede (25 casas em Austin + Preço Spot ERCOT) com a
    carga total do estado do Texas (ERCOT System Load em MW) no fuso local do Texas.
    """
    micro_path = os.path.join(
        base_dir, 'data', '3_otimizador_ercot_atacado', 'dados', 'microgrid_ercot_atacado_2018.csv'
    )
    df_micro = pd.read_csv(micro_path)
    df_micro['timestamp'] = (
        pd.to_datetime(df_micro['timestamp'], utc=True)
        .dt.tz_convert('America/Chicago')
        .dt.tz_localize(None)
    )
    df_micro = (
        df_micro.drop_duplicates(subset=['timestamp'])
        .set_index('timestamp')
        .resample('1h')
        .asfreq()
        .interpolate(method='linear')
        .reset_index()
    )
    df_micro['net_load'] = df_micro['load'] - df_micro['total_solar']

    df_tx = fetch_or_load_texas_load_july2018()
    df_merged = pd.merge(df_micro, df_tx, on='timestamp', how='inner')
    return df_merged


def plot_weekly_three_panel_comparison(df_week, title, out_filename):
    """
    Gera o gráfico comparativo semanal com 3 painéis um abaixo do outro:
      1º Painel: Carga da nossa Microrrede (Net Load e Carga Bruta das 25 Casas em kW)
      2º Painel: Carga Total do Sistema do Texas (ERCOT System Load em MW)
      3º Painel: Preço da Energia no ERCOT (US$/kWh e US$/MWh)
    """
    fig, (ax1, ax2, ax3) = plt.subplots(
        3,
        1,
        figsize=(16, 13.5),
        sharex=True,
        gridspec_kw={'height_ratios': [1.15, 1.1, 1.1]},
    )

    # Identifica os horários de pico diário do Texas (~15h-16h) e da Microrrede (~19h)
    df_week = df_week.copy()
    df_week['date'] = df_week['timestamp'].dt.date
    tx_peak_times = []
    micro_peak_times = []
    for _, grp in df_week.groupby('date'):
        if len(grp) == 24:
            tx_peak_times.append(grp.loc[grp['texas_load_mw'].idxmax(), 'timestamp'])
            micro_peak_times.append(grp.loc[grp['net_load'].idxmax(), 'timestamp'])

    # --------------------------------------------------------------------------
    # PAINEL 1 (SUPERIOR): Carga da Nossa Microrrede (25 Casas em Austin)
    # --------------------------------------------------------------------------
    ax1.plot(
        df_week['timestamp'],
        df_week['net_load'],
        color='crimson',
        linewidth=2.0,
        label='Demanda Líquida da Microrrede - Net Load (Carga - Solar) [Pico ~19h–20h]',
    )
    ax1.plot(
        df_week['timestamp'],
        df_week['load'],
        color='#e67e22',
        linestyle='--',
        linewidth=1.5,
        alpha=0.85,
        label='Consumo Bruto Total das 25 Casas (Sem descontar Solar) [Pico ~18h–19h]',
    )
    ax1.axhline(0, color='black', linewidth=0.8, alpha=0.6)
    ax1.fill_between(
        df_week['timestamp'],
        df_week['net_load'],
        df_week['load'],
        color='#f1c40f',
        alpha=0.22,
        label='Abatimento pela Geração Solar Fotovoltaica Local (PV)',
    )

    for i, t_mc in enumerate(micro_peak_times):
        lbl = 'Horário de Pico da Microrrede Residencial (~19h)' if i == 0 else None
        ax1.axvline(t_mc, color='crimson', linestyle=':', linewidth=1.2, alpha=0.65, label=lbl)
        ax2.axvline(t_mc, color='crimson', linestyle=':', linewidth=1.0, alpha=0.35)
        ax3.axvline(t_mc, color='crimson', linestyle=':', linewidth=1.0, alpha=0.35)

    for i, t_tx in enumerate(tx_peak_times):
        lbl = 'Horário de Pico do Texas / ERCOT (~15h–16h)' if i == 0 else None
        ax1.axvline(t_tx, color='#1f618d', linestyle='-.', linewidth=1.0, alpha=0.35)
        ax2.axvline(t_tx, color='#1f618d', linestyle='-.', linewidth=1.2, alpha=0.70, label=lbl)
        ax3.axvline(t_tx, color='#1f618d', linestyle='-.', linewidth=1.2, alpha=0.70, label=lbl)

    ax1.set_ylabel('Potência Microrrede (kW)', fontsize=12, fontweight='bold', color='crimson')
    ax1.tick_params(axis='y', labelcolor='crimson')
    ax1.set_title(title, fontsize=13.5, fontweight='bold')
    ax1.legend(loc='upper right', framealpha=0.92, fontsize=9.5)
    ax1.grid(True, alpha=0.3)

    # --------------------------------------------------------------------------
    # PAINEL 2 (MEIO): Carga do Sistema Elétrico do Texas Inteiro (ERCOT MW)
    # --------------------------------------------------------------------------
    ax2.plot(
        df_week['timestamp'],
        df_week['texas_load_mw'],
        color='#1f618d',
        linewidth=2.2,
        label=(
            f"Demanda Total do Estado do Texas (ERCOT System Load) "
            f"[Mín: {df_week['texas_load_mw'].min():,.0f} MW | Máx: {df_week['texas_load_mw'].max():,.0f} MW]"
        ),
    )
    ax2.fill_between(
        df_week['timestamp'],
        df_week['texas_load_mw'].min() * 0.95,
        df_week['texas_load_mw'],
        color='#2980b9',
        alpha=0.18,
    )
    ax2.set_ylabel('Carga do Texas (MW)', fontsize=12, fontweight='bold', color='#1f618d')
    ax2.tick_params(axis='y', labelcolor='#1f618d')
    ax2.legend(loc='upper right', framealpha=0.92, fontsize=10)
    ax2.grid(True, alpha=0.3)

    # --------------------------------------------------------------------------
    # PAINEL 3 (INFERIOR): Variação do Preço da Energia no ERCOT
    # --------------------------------------------------------------------------
    tdsp_fee = 0.01896
    buy_price = df_week['ercot_spp_usd_kwh'] + tdsp_fee
    sell_price = df_week['ercot_spp_usd_kwh']
    mean_spot = sell_price.mean()
    max_spot = sell_price.max()

    ax3.plot(
        df_week['timestamp'],
        buy_price,
        color='#8e44ad',
        linewidth=1.9,
        label=f'Tarifa de Compra (Spot ERCOT + TDSP US\\$ 0,019/kWh) [Pico: US\\$ {(max_spot+tdsp_fee):.3f}/kWh]',
    )
    ax3.plot(
        df_week['timestamp'],
        sell_price,
        color='#27ae60',
        linestyle='--',
        linewidth=1.7,
        label=f'Preço Spot Puro ERCOT (Venda/Atacado) [Méd: US\\$ {mean_spot:.3f} | Máx: US\\$ {max_spot:.3f}/kWh]',
    )
    ax3.fill_between(
        df_week['timestamp'],
        0,
        sell_price,
        color='#2ecc71',
        alpha=0.18,
    )
    ax3.axhline(
        mean_spot,
        color='#d35400',
        linestyle=':',
        linewidth=1.4,
        label=f'Preço Médio Spot na Semana (US\\$ {mean_spot:.3f}/kWh = US\\$ {mean_spot*1000:.1f}/MWh)',
    )

    ax3.set_ylabel('Preço Energia (US$/kWh)', fontsize=12, fontweight='bold', color='#2c3e50')
    ax3.tick_params(axis='y', labelcolor='#2c3e50')
    ax3.grid(True, alpha=0.3)

    ax3_twin = ax3.twinx()
    y1_min, y1_max = ax3.get_ylim()
    ax3_twin.set_ylim(y1_min * 1000.0, y1_max * 1000.0)
    ax3_twin.set_ylabel('Cotação ERCOT (US$/MWh)', fontsize=11, fontweight='bold', color='#8e44ad')
    ax3_twin.tick_params(axis='y', labelcolor='#8e44ad')

    ax3.legend(loc='upper right', framealpha=0.92, fontsize=9.5)
    ax3.set_xlabel(
        'Tempo (Horário Local de Austin, Texas - CST/CDT | Comparativo Microrrede vs. Texas vs. Preço)',
        fontsize=12,
        fontweight='bold',
    )
    ax3.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12]))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b %Hh'))
    ax3.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 18]))

    plt.tight_layout()

    dest_dirs = [
        os.path.join(base_dir, 'data', '3_otimizador_ercot_atacado', 'imagens'),
        os.path.join(base_dir, 'Resultados de Otimizacao'),
    ]
    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)
        out_path = os.path.join(d, out_filename)
        plt.savefig(out_path, dpi=160, bbox_inches='tight')
        print(f"Gráfico comparativo salvo em: {out_path}")
    plt.close()


def plot_hourly_profile_three_panels(df_week, out_filename='grafico_perfil_horario_texas_vs_casas.png'):
    """
    Gera o perfil médio horário (00h às 23h) da semana de 02/Jul a 09/Jul/2018
    em 3 painéis verticais (1º Microrrede, 2º Texas, 3º Preço da Energia),
    evidenciando com anotações a defasagem de 3 a 4 horas entre o pico do Texas (15h-16h)
    e o pico da Microrrede (18h-20h).
    """
    df_w = df_week.copy()
    df_w['hour'] = df_w['timestamp'].dt.hour
    prof = df_w.groupby('hour')[['load', 'total_solar', 'net_load', 'texas_load_mw', 'ercot_spp_usd_mwh', 'ercot_spp_usd_kwh']].mean()

    fig, (ax1, ax2, ax3) = plt.subplots(
        3,
        1,
        figsize=(14, 12.5),
        sharex=True,
        gridspec_kw={'height_ratios': [1.15, 1.05, 1.05]},
    )
    hours = prof.index.tolist()

    # 1º Painel: Microrrede
    ax1.plot(hours, prof['net_load'], marker='o', color='crimson', linewidth=2.4, label='Net Load da Microrrede (Carga - Solar) [kW]')
    ax1.plot(hours, prof['load'], marker='s', color='#e67e22', linestyle='--', linewidth=1.8, label='Carga Bruta das 25 Casas (Sem Solar) [kW]')
    ax1.axhline(0, color='black', linewidth=0.8, alpha=0.6)
    ax1.axvline(15.5, color='#1f618d', linestyle='-.', linewidth=1.5, alpha=0.75, label='Pico do Estado do Texas e do Preço (15h–16h)')
    ax1.axvline(19.0, color='crimson', linestyle=':', linewidth=1.8, alpha=0.85, label='Pico Líquido da Microrrede Residencial (19h)')
    ax1.annotate(
        'Pico da Microrrede (19h: 74,2 kW)\nSol se pôs + moradores em casa',
        xy=(19, prof.loc[19, 'net_load']),
        xytext=(19.3, 45),
        fontsize=9.5,
        fontweight='bold',
        color='crimson',
        arrowprops=dict(arrowstyle='->', color='crimson', lw=1.8),
    )
    ax1.set_title(
        'Perfil Médio Horário (02/Jul a 09/Jul/2018): Descolamento entre Pico da Microrrede (19h) e Pico do Texas (15h–16h)',
        fontsize=12.5,
        fontweight='bold',
    )
    ax1.set_ylabel('Potência Microrrede (kW)', fontsize=11.5, fontweight='bold', color='crimson')
    ax1.legend(loc='upper left', framealpha=0.92, fontsize=9.5)
    ax1.grid(True, alpha=0.3)

    # 2º Painel: Carga do Texas
    ax2.plot(hours, prof['texas_load_mw'], marker='o', color='#1f618d', linewidth=2.4, label='Demanda Total do Sistema ERCOT - Texas Inteiro (MW)')
    ax2.axvline(15.5, color='#1f618d', linestyle='-.', linewidth=1.5, alpha=0.75)
    ax2.axvline(19.0, color='crimson', linestyle=':', linewidth=1.8, alpha=0.85)
    ax2.annotate(
        'Pico do Estado do Texas (15h–16h: 61.706 MW)\nComércio + Indústria + Ar-Condicionado no auge',
        xy=(15, prof.loc[15, 'texas_load_mw']),
        xytext=(8.5, 58500),
        fontsize=9.5,
        fontweight='bold',
        color='#1f618d',
        arrowprops=dict(arrowstyle='->', color='#1f618d', lw=1.8),
    )
    ax2.set_ylabel('Carga do Texas (MW)', fontsize=11.5, fontweight='bold', color='#1f618d')
    ax2.legend(loc='upper left', framealpha=0.92, fontsize=10)
    ax2.grid(True, alpha=0.3)

    # 3º Painel: Preço da Energia
    ax3.plot(hours, prof['ercot_spp_usd_kwh'], marker='D', color='#8e44ad', linewidth=2.4, label='Preço Spot Médio ERCOT (US$/kWh)')
    ax3.axvline(15.5, color='#1f618d', linestyle='-.', linewidth=1.5, alpha=0.75)
    ax3.axvline(19.0, color='crimson', linestyle=':', linewidth=1.8, alpha=0.85)
    ax3.annotate(
        'Pico do Preço da Energia (16h: US$ 0,084/kWh)\nSegue exatamente o pico do Texas (15h–16h)!',
        xy=(16, prof.loc[16, 'ercot_spp_usd_kwh']),
        xytext=(9.0, 0.072),
        fontsize=9.5,
        fontweight='bold',
        color='#8e44ad',
        arrowprops=dict(arrowstyle='->', color='#8e44ad', lw=1.8),
    )
    ax3.annotate(
        'Às 19h o preço já caiu 59%\n(US$ 0,035/kWh)',
        xy=(19, prof.loc[19, 'ercot_spp_usd_kwh']),
        xytext=(19.8, 0.060),
        fontsize=9.5,
        fontweight='bold',
        color='#2c3e50',
        arrowprops=dict(arrowstyle='->', color='#2c3e50', lw=1.5),
    )
    ax3.set_ylabel('Preço Spot (US$/kWh)', fontsize=11.5, fontweight='bold', color='#8e44ad')
    ax3.set_xlabel('Hora do Dia (Horário Local de Austin, Texas - 00h às 23h)', fontsize=12, fontweight='bold')
    ax3.set_xticks(range(0, 24))
    ax3.set_xticklabels([f'{h:02d}h' for h in range(24)])
    ax3.legend(loc='upper left', framealpha=0.92, fontsize=10)
    ax3.grid(True, alpha=0.3)

    ax3_twin = ax3.twinx()
    y1_min, y1_max = ax3.get_ylim()
    ax3_twin.set_ylim(y1_min * 1000.0, y1_max * 1000.0)
    ax3_twin.set_ylabel('Preço Spot (US$/MWh)', fontsize=11, fontweight='bold', color='#8e44ad')

    plt.tight_layout()
    dest_dirs = [
        os.path.join(base_dir, 'data', '3_otimizador_ercot_atacado', 'imagens'),
        os.path.join(base_dir, 'Resultados de Otimizacao'),
    ]
    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)
        out_path = os.path.join(d, out_filename)
        plt.savefig(out_path, dpi=160, bbox_inches='tight')
        print(f"Gráfico de perfil horário salvo em: {out_path}")
    plt.close()


if __name__ == '__main__':
    df_all = load_merged_comparison_data()

    # 1. Semana Padrão (02/Jul a 09/Jul/2018)
    df_w1 = df_all[(df_all['timestamp'] >= '2018-07-02 00:00:00') & (df_all['timestamp'] < '2018-07-09 00:00:00')].copy()
    plot_weekly_three_panel_comparison(
        df_w1,
        title='Comparativo Sincronizado (02/Jul a 09/Jul/2018): 1º Carga da Microrrede (25 Casas) vs. 2º Carga do Texas (ERCOT) vs. 3º Preço da Energia',
        out_filename='grafico_comparativo_texas_vs_casas_1semana.png',
    )
    plot_hourly_profile_three_panels(df_w1, out_filename='grafico_perfil_horario_texas_vs_casas.png')

    # 2. Semana da Onda de Calor Extrema (16/Jul a 23/Jul/2018)
    df_w2 = df_all[(df_all['timestamp'] >= '2018-07-16 00:00:00') & (df_all['timestamp'] < '2018-07-23 00:00:00')].copy()
    plot_weekly_three_panel_comparison(
        df_w2,
        title='Comparativo na Onda de Calor (16/Jul a 23/Jul/2018): 1º Carga da Microrrede (25 Casas) vs. 2º Carga do Texas (ERCOT) vs. 3º Preço da Energia',
        out_filename='grafico_comparativo_texas_vs_casas_onda_calor.png',
    )
