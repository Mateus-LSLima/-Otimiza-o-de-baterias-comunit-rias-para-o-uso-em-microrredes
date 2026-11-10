import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
import sys

# Garante que o Python encontre as outras pastas (src/control e pasta raiz)
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(base_dir, 'src', 'control'))

from optimizer_pyomo import OptimizerBESS

def simulate_period(df_subset, capacity_kwh=200.0, max_power_kw=50.0, efficiency=0.95, initial_soc=0.50):
    """
    Executa a otimização diária em blocos de 24h para o subconjunto de dados fornecido.
    """
    opt = OptimizerBESS(capacity_kwh=capacity_kwh, max_power_kw=max_power_kw, efficiency=efficiency)
    
    bess_power_list = []
    bess_energy_list = []
    grid_exchange_list = []
    
    current_energy = capacity_kwh * initial_soc
    num_days = len(df_subset) // 24
    print(f"Otimizando {num_days} dias ({num_days * 24} horas)...")
    
    for day in range(num_days):
        day_net_load = df_subset['net_load'].iloc[day*24 : (day+1)*24].tolist()
        
        # Otimização com Pyomo / GLPK
        plan = opt.optimize_24h(day_net_load, initial_soc=(current_energy / capacity_kwh))
        
        for t, p_kw in enumerate(plan):
            if p_kw > 0:
                current_energy += p_kw * efficiency
            else:
                current_energy += p_kw / efficiency
                
            current_energy = max(0.0, min(capacity_kwh, current_energy))
            bess_power_list.append(p_kw)
            bess_energy_list.append(current_energy)
            grid_exchange = day_net_load[t] + p_kw
            grid_exchange_list.append(grid_exchange)

    res = df_subset.iloc[:len(bess_power_list)].copy()
    res['bess_power'] = bess_power_list
    res['bess_energy_kwh'] = bess_energy_list
    res['bess_soc_pct'] = (res['bess_energy_kwh'] / capacity_kwh) * 100.0
    res['grid_exchange'] = grid_exchange_list
    return res

def plot_bess_simulation(df_res, title, out_filename, time_scale='week'):
    """
    Gera o gráfico duplo sincronizado adaptando a espessura de linhas e formatação do eixo X
    conforme o período simulado (3days, week, month).
    """
    if time_scale == 'quarter':
        fig_size = (20, 10)
        lw_net = 0.95
        lw_grid = 0.95
        lw_soc = 1.3
        lw_power = 0.75
        alpha_fill = 0.22
        alpha_power = 0.35
    elif time_scale == 'month':
        fig_size = (18, 9.5)
        lw_net = 1.2
        lw_grid = 1.2
        lw_soc = 1.6
        lw_power = 0.9
        alpha_fill = 0.28
        alpha_power = 0.45
    elif time_scale == 'week':
        fig_size = (16, 9)
        lw_net = 1.8
        lw_grid = 1.8
        lw_soc = 2.2
        lw_power = 1.2
        alpha_fill = 0.32
        alpha_power = 0.55
    else: # 3days
        fig_size = (15, 9)
        lw_net = 2.2
        lw_grid = 2.2
        lw_soc = 2.8
        lw_power = 1.5
        alpha_fill = 0.35
        alpha_power = 0.60
        
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=fig_size, sharex=True, gridspec_kw={'height_ratios': [1.3, 1]})
    
    # --- GRÁFICO SUPERIOR: Peak Shaving & Valley Filling ---
    ax1.plot(df_res['timestamp'], df_res['net_load'], color='crimson', linewidth=lw_net, label='Demanda Original da Microrrede (Net Load)')
    ax1.plot(df_res['timestamp'], df_res['grid_exchange'], color='navy', linestyle='--', linewidth=lw_grid, label='Demanda com Bateria (Grid Exchange - Achatada)')
    ax1.axhline(0, color='black', linewidth=0.8, alpha=0.7)
    
    # Sombras para ilustrar a atuação
    ax1.fill_between(df_res['timestamp'], df_res['net_load'], df_res['grid_exchange'], 
                     where=(df_res['net_load'] > df_res['grid_exchange']), color='orange', alpha=alpha_fill, label='Alívio de Pico (Bateria Injetando Energia)')
    ax1.fill_between(df_res['timestamp'], df_res['net_load'], df_res['grid_exchange'], 
                     where=(df_res['net_load'] < df_res['grid_exchange']), color='cyan', alpha=alpha_fill, label='Preenchimento de Vale (Bateria Importando da Rede / Carregando)')
    
    ax1.set_ylabel('Potência Ativa (kW)', fontsize=12, fontweight='bold')
    ax1.set_title(title, fontsize=13, fontweight='bold')
    ax1.legend(loc='upper right', framealpha=0.9)
    ax1.grid(True, alpha=0.3)
    
    # --- GRÁFICO INFERIOR: Ciclo Completo da Bateria ---
    ax2.plot(df_res['timestamp'], df_res['bess_soc_pct'], color='green', linewidth=lw_soc, label='Estado de Carga da Bateria (SOC %)')
    ax2.set_ylabel('Carga da Bateria (% SOC)', fontsize=12, fontweight='bold', color='green')
    ax2.tick_params(axis='y', labelcolor='green')
    ax2.set_ylim(-5, 105)
    ax2.axhline(100, color='gray', linestyle=':', alpha=0.6)
    ax2.axhline(0, color='gray', linestyle=':', alpha=0.6)
    
    # Eixo secundário: Potência do Inversor
    ax2_twin = ax2.twinx()
    ax2_twin.plot(df_res['timestamp'], df_res['bess_power'], color='purple', alpha=alpha_power, linestyle='-', linewidth=lw_power, label='Potência Bateria (+ Carga / - Descarga) [kW]')
    ax2_twin.set_ylabel('Potência Inversor (kW)', fontsize=11, color='purple')
    ax2_twin.tick_params(axis='y', labelcolor='purple')
    ax2_twin.axhline(0, color='purple', linestyle=':', alpha=0.3)
    
    ax2.set_xlabel('Tempo (Horário Local de Austin, Texas)', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    
    # Formatação do eixo X conforme escala
    if time_scale == 'quarter':
        ax2.xaxis.set_major_locator(mdates.DayLocator(interval=7))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b'))
        ax2.xaxis.set_minor_locator(mdates.DayLocator(interval=1))
    elif time_scale == 'month':
        ax2.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b'))
        ax2.xaxis.set_minor_locator(mdates.DayLocator(interval=1))
    elif time_scale == 'week':
        ax2.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12]))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b %Hh'))
        ax2.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 18]))
    else:
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b %Hh'))
        
    lines_1, labels_1 = ax2.get_legend_handles_labels()
    lines_2, labels_2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper right', framealpha=0.9)
    
    plt.tight_layout()
    
    # Salva na pasta data/1_otimizador_peak_shaving/imagens/ e na pasta Resultados de Otimizacao/
    dest_dirs = [
        os.path.join(base_dir, 'data', '1_otimizador_peak_shaving', 'imagens'),
        os.path.join(base_dir, 'Resultados de Otimizacao')
    ]
    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)
        out_file = os.path.join(d, out_filename)
        plt.savefig(out_file, dpi=160, bbox_inches='tight')
        print(f"Gráfico salvo com sucesso em: {out_file}")
    plt.close()

def load_preprocessed_dataset():
    """
    Carrega a série horária da microrrede, alinha os timestamps ao fuso local de Austin
    (America/Chicago) sem tzinfo antes da reamostragem (garantindo que todos os blocos
    diários de 24h iniciem estritamente à 00:00:00 do horário do Texas e que o Matplotlib
    não desloque o eixo X para UTC).
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
    # Preenche qualquer lacuna horária pontual mantendo janelas de 24h cravadas em 00h-23h locais
    df = df.resample('1h').asfreq()
    df['load'] = df['load'].interpolate(method='linear')
    df['total_solar'] = df['total_solar'].interpolate(method='linear')
    df = df.reset_index()
    df['net_load'] = df['load'] - df['total_solar']
    return df

def run_quarters():
    df = load_preprocessed_dataset()
    
    # 4 Trimestres completos de 2018 (365 dias)
    quarters_config = [
        {
            'name': '1º Trimestre (Jan a Mar / 2018 - Inverno)',
            'days': 90,
            'start_idx': 0,
            'filename': 'grafico_trimestre1_jan_mar.png'
        },
        {
            'name': '2º Trimestre (Abr a Jun / 2018 - Primavera)',
            'days': 91,
            'start_idx': 90 * 24,
            'filename': 'grafico_trimestre2_abr_jun.png'
        },
        {
            'name': '3º Trimestre (Jul a Set / 2018 - Verão)',
            'days': 92,
            'start_idx': (90 + 91) * 24,
            'filename': 'grafico_trimestre3_jul_set.png'
        },
        {
            'name': '4º Trimestre (Out a Dez / 2018 - Outono)',
            'days': 92,
            'start_idx': (90 + 91 + 92) * 24,
            'filename': 'grafico_trimestre4_out_dez.png'
        }
    ]
    
    summary_metrics = []
    
    for q in quarters_config:
        print(f"\n==========================================")
        print(f"Simulando {q['name']}...")
        print(f"==========================================")
        end_idx = q['start_idx'] + q['days'] * 24
        df_q = df.iloc[q['start_idx']:end_idx].copy().reset_index(drop=True)
        
        res_q = simulate_period(df_q)
        plot_bess_simulation(
            res_q,
            title=f"Efeito Real do Otimizador BESS - {q['name']}: Peak Shaving e Valley Filling",
            out_filename=q['filename'],
            time_scale='quarter'
        )
        
        orig_peak = res_q['net_load'].max()
        opt_peak = res_q['grid_exchange'].max()
        reduction_kw = orig_peak - opt_peak
        reduction_pct = (reduction_kw / orig_peak) * 100.0
        min_net = res_q['net_load'].min()
        min_grid = res_q['grid_exchange'].min()
        
        summary_metrics.append({
            'trimestre': q['name'],
            'orig_peak': orig_peak,
            'opt_peak': opt_peak,
            'reduction_kw': reduction_kw,
            'reduction_pct': reduction_pct,
            'min_net': min_net,
            'min_grid': min_grid,
            'soc_min': res_q['bess_soc_pct'].min(),
            'soc_max': res_q['bess_soc_pct'].max(),
            'filename': q['filename']
        })
        
    print("\n=== RESUMO DAS MÉTRICAS TRIMESTRAIS ===")
    for m in summary_metrics:
        print(f"{m['trimestre']}: Pico Original = {m['orig_peak']:.2f} kW -> Com BESS = {m['opt_peak']:.2f} kW (Redução: {m['reduction_pct']:.1f}%)")
        
    return summary_metrics

def run_all():
    df = load_preprocessed_dataset()
    
    # 1. Semana
    print("\n=== GERANDO GRÁFICO PARA 1 SEMANA ===")
    start_week = '2018-07-02 00:00:00'
    end_week = '2018-07-09 00:00:00'
    df_week = df[(df['timestamp'] >= start_week) & (df['timestamp'] < end_week)].copy().reset_index(drop=True)
    res_week = simulate_period(df_week)
    plot_bess_simulation(
        res_week, 
        title='Efeito Real do Otimizador - Visão de 1 Semana (02/Jul a 09/Jul/2018): Peak Shaving e Valley Filling',
        out_filename='grafico5_1semana.png',
        time_scale='week'
    )
    
    # 2. Mês
    print("\n=== GERANDO GRÁFICO PARA 1 MÊS ===")
    start_month = '2018-07-01 00:00:00'
    end_month = '2018-08-01 00:00:00'
    df_month = df[(df['timestamp'] >= start_month) & (df['timestamp'] < end_month)].copy().reset_index(drop=True)
    res_month = simulate_period(df_month)
    plot_bess_simulation(
        res_month, 
        title='Efeito Real do Otimizador - Visão Mensal Completa (Julho de 2018): Peak Shaving e Valley Filling',
        out_filename='grafico5_1mes.png',
        time_scale='month'
    )
    
    # 3. Trimestres
    run_quarters()

if __name__ == '__main__':
    run_all()


