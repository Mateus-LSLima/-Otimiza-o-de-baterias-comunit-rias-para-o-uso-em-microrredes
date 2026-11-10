# ==============================================================================
# DOWNLOAD E ALINHAMENTO DOS PREÇOS HORÁRIOS DO ERCOT DAM 2018 (AUSTIN / LZ_AEN)
# Converte de US$/MWh para US$/kWh: SPP_kWh[t] = SPP_MWh[t] / 1000.0
# ==============================================================================

import os
import requests
import pandas as pd
import numpy as np

API_KEY = "8ad12354d8bd4ced97c6017a85f2514e"
BASE_URL = "https://api.gridstatus.io/v1/datasets/ercot_spp_day_ahead_hourly/query"

def download_ercot_dam_2018():
    print("[1/4] Baixando precos horarios do ERCOT DAM 2018 (LZ_AEN) via GridStatus API...")
    params = {
        "start_time": "2018-01-01T00:00:00Z",
        "end_time": "2019-01-01T06:00:00Z",
        "filter_column": "location",
        "filter_value": "LZ_AEN",
        "limit": 10000
    }
    headers = {"x-api-key": API_KEY}
    
    response = requests.get(BASE_URL, params=params, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Erro na requisicao ({response.status_code}): {response.text}")
    
    data = response.json().get("data", [])
    print(f"      Total de registros recebidos: {len(data)}")
    
    df_prices = pd.DataFrame(data)
    df_prices["timestamp"] = pd.to_datetime(df_prices["interval_start_utc"])
    df_prices = df_prices[["timestamp", "location", "spp"]].copy()
    df_prices.rename(columns={"spp": "ercot_spp_usd_mwh"}, inplace=True)
    df_prices["ercot_spp_usd_kwh"] = df_prices["ercot_spp_usd_mwh"] / 1000.0
    
    # Salvar arquivo individual de precos ERCOT
    os.makedirs("data/3_otimizador_ercot_atacado/dados", exist_ok=True)
    prices_path = "data/3_otimizador_ercot_atacado/dados/ercot_dam_austin_2018.csv"
    df_prices.to_csv(prices_path, index=False)
    print(f"      Salvo com sucesso: {prices_path}")
    
    return df_prices

def align_with_community_microgrid(df_prices):
    print("\n[2/4] Alinhando precos com os dados de carga e geracao solar da microrrede...")
    microgrid_path = "data/1_otimizador_peak_shaving/dados/community_microgrid.csv"
    df_micro = pd.read_csv(microgrid_path)
    df_micro["timestamp"] = pd.to_datetime(df_micro["timestamp"])
    
    # Merge com precos ERCOT
    df_merged = pd.merge(df_micro, df_prices[["timestamp", "ercot_spp_usd_mwh", "ercot_spp_usd_kwh"]], on="timestamp", how="left")
    
    # Caso haja pequenas lacunas de fuso, interpolar linearmente
    missing_count = df_merged["ercot_spp_usd_kwh"].isna().sum()
    if missing_count > 0:
        print(f"      Aviso: {missing_count} registros faltantes no merge. Aplicando interpolacao...")
        df_merged["ercot_spp_usd_mwh"] = df_merged["ercot_spp_usd_mwh"].interpolate(method="linear")
        df_merged["ercot_spp_usd_kwh"] = df_merged["ercot_spp_usd_kwh"].interpolate(method="linear")
        
    df_merged["net_load"] = df_merged["load"] - df_merged["total_solar"]
    print(f"      Base combinada: {df_merged.shape[0]} horas (de {df_merged['timestamp'].min()} ate {df_merged['timestamp'].max()})")
    
    # Salvar base para o Otimizador 3 (ERCOT Atacado)
    ercot_micro_path = "data/3_otimizador_ercot_atacado/dados/microgrid_ercot_atacado_2018.csv"
    df_merged[["timestamp", "load", "total_solar", "net_load", "ercot_spp_usd_mwh", "ercot_spp_usd_kwh"]].to_csv(ercot_micro_path, index=False)
    print(f"      Base ERCOT salva em: {ercot_micro_path}")
    
    print("\n[3/4] Mapeando postos da Tarifa Branca brasileira (CPFL Paulista 2018 + Fio B 2026)...")
    local_time = df_merged["timestamp"].dt.tz_convert("America/Chicago")
    hours = local_time.dt.hour
    dayofweek = local_time.dt.dayofweek # 0=Mon, ..., 6=Sun
    is_weekday = dayofweek < 5
    
    posto = []
    tarifa_branca_brl = []
    
    for h, wd in zip(hours, is_weekday):
        if not wd:
            posto.append("fora_ponta")
            tarifa_branca_brl.append(0.625)
        else:
            if 18 <= h < 21:
                posto.append("ponta")
                tarifa_branca_brl.append(1.299)
            elif (16 <= h < 18) or (21 <= h < 22):
                posto.append("intermediario")
                tarifa_branca_brl.append(0.883)
            else:
                posto.append("fora_ponta")
                tarifa_branca_brl.append(0.625)
                
    df_merged["tarifa_branca_posto"] = posto
    df_merged["tarifa_branca_brl_kwh"] = tarifa_branca_brl
    df_merged["fio_b_retido_2026_brl_kwh"] = 0.156
    
    # Salvar base para o Otimizador 2 (Tarifa Branca Brasil)
    os.makedirs("data/2_otimizador_tarifa_branca_brasil/dados", exist_ok=True)
    br_micro_path = "data/2_otimizador_tarifa_branca_brasil/dados/microgrid_tarifa_branca_2018.csv"
    df_merged[["timestamp", "load", "total_solar", "net_load", "tarifa_branca_posto", "tarifa_branca_brl_kwh", "fio_b_retido_2026_brl_kwh"]].to_csv(br_micro_path, index=False)
    print(f"      Base Tarifa Branca salva em: {br_micro_path}")
    
    return df_merged

def print_summary_statistics(df):
    print("\n[4/4] Estatisticas Descritivas dos Precos Reais ERCOT DAM 2018 (Austin - LZ_AEN):")
    spp_mwh = df["ercot_spp_usd_mwh"]
    spp_kwh = df["ercot_spp_usd_kwh"]
    
    print(f"      - Preco Medio Anual:     US$ {spp_mwh.mean():.2f} / MWh (US$ {spp_kwh.mean():.4f} / kWh)")
    print(f"      - Preco Mediano:         US$ {spp_mwh.median():.2f} / MWh (US$ {spp_kwh.median():.4f} / kWh)")
    print(f"      - Preco Minimo:          US$ {spp_mwh.min():.2f} / MWh (US$ {spp_kwh.min():.4f} / kWh)")
    print(f"      - Preco Maximo (Pico):   US$ {spp_mwh.max():.2f} / MWh (US$ {spp_kwh.max():.4f} / kWh)")
    print(f"      - Percentil 95:          US$ {spp_mwh.quantile(0.95):.2f} / MWh (US$ {spp_kwh.quantile(0.95):.4f} / kWh)")
    print(f"      - Horas com preco > $100/MWh: {(spp_mwh > 100).sum()} horas")
    print(f"      - Horas com preco > $200/MWh: {(spp_mwh > 200).sum()} horas")
    print("\nSincronizacao de dados concluida com exito!")

if __name__ == "__main__":
    df_prices = download_ercot_dam_2018()
    df_unified = align_with_community_microgrid(df_prices)
    print_summary_statistics(df_unified)
