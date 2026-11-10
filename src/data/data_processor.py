# ==============================================================================
# PROCESSAMENTO E AGREGAÇÃO DOS DADOS BRUTOS DO PECAN STREET (15 MIN -> 1 HORA)
# Fórmula de reconstrução da carga residencial: Load[t] = Grid[t] + Solar[t]
# ==============================================================================

import pandas as pd
import os

def process_pecan_street_data(input_csv_path, output_csv_path):
    """
    Lê as medições de 15 minutos das 25 casas de Austin (Pecan Street 2018),
    reconstrói a carga total comunitária e reamostra para potência média horária (1h).
    """
    print("Iniciando o processamento dos dados do Pecan Street...")
    
    # Lendo apenas as colunas que importam para economizar RAM
    cols_to_use = ['dataid', 'local_15min', 'grid', 'solar', 'solar2']
    
    print(f"Lendo o arquivo: {input_csv_path}")
    df = pd.read_csv(input_csv_path, usecols=lambda c: c in cols_to_use)
    
    # Forçando conversão para float para evitar erro com strings
    df['solar'] = pd.to_numeric(df['solar'], errors='coerce').fillna(0)
    df['grid'] = pd.to_numeric(df['grid'], errors='coerce').fillna(0)
    
    # Se houver 'solar2', soma ao solar principal
    if 'solar2' in df.columns:
        df['solar2'] = pd.to_numeric(df['solar2'], errors='coerce').fillna(0)
        df['total_solar'] = df['solar'] + df['solar2']
    else:
        df['total_solar'] = df['solar']
        
    # Calculando a Carga da Casa (Load). 
    # Em Pecan Street, grid = consumo_da_rede. solar = geração_local.
    # Portanto, Carga Total da casa = Energia pega da rede + Energia que o painel gerou e a casa usou na hora.
    # Assumindo que geração solar é reportada como positiva.
    df['load'] = df['grid'] + df['total_solar']
    
    # Agrupando todas as 25 casas por timestamp para criar a "Microrrede Comunitária"
    print("Agregando dados de todas as casas por timestamp...")
    df_community = df.groupby('local_15min').agg({
        'load': 'sum',
        'total_solar': 'sum'
    }).reset_index()
    
    # Convertendo a coluna de tempo para datetime e arrumando o fuso horário se necessário
    # Os dados vêm com timezone no final ex: '2018-11-21 15:15:00-06'
    df_community['timestamp'] = pd.to_datetime(df_community['local_15min'], utc=True)
    df_community = df_community.sort_values('timestamp').set_index('timestamp')
    
    # Reamostrando de 15 minutos para 1 HORA (resolução decidida no Grill-Me)
    print("Reamostrando de 15 minutos para blocos de 1 Hora...")
    # 'sum' porque estamos lidando com kWh ou kW médio no período de 15 min? 
    # Pecan street 15-min data is usually average kW over the 15 mins.
    # To get average kW over the hour, we use 'mean'.
    df_hourly = df_community.resample('1h').mean(numeric_only=True)
    
    # Limpando dados nulos provenientes de buracos no dataset
    df_hourly = df_hourly.dropna()
    
    print(f"Salvando o arquivo final em: {output_csv_path}")
    df_hourly.to_csv(output_csv_path)
    
    print("Processamento concluído! Temos nossa base da Microrrede.")
    return df_hourly

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    input_file = os.path.join(base_dir, 'data', '15minute_data_austin', '15minute_data_austin.csv')
    out_dir = os.path.join(base_dir, 'data', '1_otimizador_peak_shaving', 'dados')
    os.makedirs(out_dir, exist_ok=True)
    output_file = os.path.join(out_dir, 'community_microgrid.csv')
    
    process_pecan_street_data(input_file, output_file)
