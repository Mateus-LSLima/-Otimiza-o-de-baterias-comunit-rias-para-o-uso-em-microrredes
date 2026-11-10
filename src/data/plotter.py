import pandas as pd
import matplotlib.pyplot as plt
import os
import matplotlib.dates as mdates

def generate_plots():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    input_file = os.path.join(base_dir, 'data', '15minute_data_austin', '15minute_data_austin.csv')
    
    print("Lendo os dados...")
    cols = ['dataid', 'local_15min', 'grid', 'solar', 'solar2']
    df = pd.read_csv(input_file, usecols=lambda c: c in cols)
    
    # Conversões numéricas
    df['solar'] = pd.to_numeric(df['solar'], errors='coerce').fillna(0)
    df['grid'] = pd.to_numeric(df['grid'], errors='coerce').fillna(0)
    if 'solar2' in df.columns:
        df['solar2'] = pd.to_numeric(df['solar2'], errors='coerce').fillna(0)
        df['total_solar'] = df['solar'] + df['solar2']
    else:
        df['total_solar'] = df['solar']
        
    df['load'] = df['grid'] + df['total_solar']
    
    # Conversão de data para o horário local de Austin, Texas (America/Chicago)
    df['timestamp'] = (
        pd.to_datetime(df['local_15min'], utc=True)
        .dt.tz_convert('America/Chicago')
        .dt.tz_localize(None)
    )
    df = df.sort_values('timestamp')
    
    # --- FILTRANDO 1 SEMANA PARA O GRÁFICO FICAR LEGÍVEL ---
    # Pegar uma semana ensolarada no verão do Texas (ex: Julho de 2018)
    start_date = '2018-07-01'
    end_date = '2018-07-07'
    df_week = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]
    
    # ========================================================
    # Consumo individual de cada casa
    # ========================================================
    plt.figure(figsize=(12, 6))
    for dataid, group in df_week.groupby('dataid'):
        plt.plot(group['timestamp'], group['load'], alpha=0.5, linewidth=1)
    
    plt.title("Consumo Elétrico de Cada Casa Individual (1 Semana)")
    plt.ylabel("Carga (kW)")
    plt.xlabel("Data")
    plt.grid(True, alpha=0.3)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d/%b'))
    img_dir = os.path.join(base_dir, 'data', '1_otimizador_peak_shaving', 'imagens')
    os.makedirs(img_dir, exist_ok=True)
    out1 = os.path.join(img_dir, 'grafico1_casas_individuais.png')
    plt.savefig(out1, bbox_inches='tight')
    plt.close()
    
    # ========================================================
    # Consumo Médio Diário da Comunidade
    # ========================================================
    # Agrupa por hora para tirar a média de consumo por casa
    df_mean = df_week.groupby('timestamp').agg({'load': 'mean'}).reset_index()
    
    plt.figure(figsize=(12, 6))
    plt.plot(df_mean['timestamp'], df_mean['load'], color='purple', linewidth=2)
    plt.title("Consumo Médio (Carga Média por Casa)")
    plt.ylabel("Carga Média (kW)")
    plt.xlabel("Data")
    plt.grid(True, alpha=0.3)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d/%b'))
    out2 = os.path.join(img_dir, 'grafico2_consumo_medio.png')
    plt.savefig(out2, bbox_inches='tight')
    plt.close()
    
    # ========================================================
    # Net Load (O que o Otimizador vê) e Geração Fotovoltaica
    # ========================================================
    df_comm = df_week.groupby('timestamp').agg({'load': 'sum', 'total_solar': 'sum'}).reset_index()
    df_comm['net_load'] = df_comm['load'] - df_comm['total_solar']
    
    plt.figure(figsize=(12, 6))
    plt.plot(df_comm['timestamp'], df_comm['net_load'], color='red', linewidth=2, label="Net Load (Carga Líquida - Otimizador)")
    plt.plot(df_comm['timestamp'], df_comm['total_solar'], color='orange', linewidth=2, label="Geração Fotovoltaica (PV)")
    
    # Preenchimento para mostrar a inversão (Geração maior que carga)
    plt.fill_between(df_comm['timestamp'], 0, df_comm['net_load'], where=(df_comm['net_load'] < 0), color='green', alpha=0.3, label="Excesso Solar (Venda/Bateria)")
    
    plt.title("Visão da Microrrede (Net Load e Geração Solar)")
    plt.ylabel("Potência (kW)")
    plt.xlabel("Data")
    plt.axhline(0, color='black', linewidth=1)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d/%b'))
    out3 = os.path.join(img_dir, 'grafico3_netload_solar.png')
    plt.savefig(out3, bbox_inches='tight')
    plt.close()
    
    print("Gráficos gerados com sucesso!")

if __name__ == "__main__":
    generate_plots()
