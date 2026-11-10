import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Carregar base do otimizador ERCOT
df = pd.read_csv("data/3_otimizador_ercot_atacado/dados/microgrid_ercot_atacado_2018.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"])
df["local_time"] = df["timestamp"].dt.tz_convert("America/Chicago")
df["hour"] = df["local_time"].dt.hour
df["is_weekday"] = df["local_time"].dt.dayofweek < 5

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 8.5), dpi=300)
plt.subplots_adjust(hspace=0.35, left=0.07, right=0.96, top=0.92, bottom=0.08)

# 1. SERIE TEMPORAL COMPLETA DE 2018
ax1.plot(df["local_time"], df["ercot_spp_usd_mwh"], color="#2980b9", linewidth=0.8, alpha=0.85, label="ERCOT DAM Spot Price (LZ_AEN)")
ax1.set_title("SÉRIE TEMPORAL REAL: MERCADO ATACADISTA DE AUSTIN (ERCOT DAM 2018)", fontsize=13, fontweight="bold", color="#2c3e50")
ax1.set_ylabel("Preço Spot (US$ / MWh)", fontsize=11, fontweight="bold")
ax1.grid(True, linestyle=":", alpha=0.6)
ax1.set_xlim(df["local_time"].min(), df["local_time"].max())
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b/%Y"))

# Destacar onda de calor de Julho/Agosto
ax1.annotate("Picos de Estresse Térmico\n(Até US$ 2.060 / MWh em Julho/Agosto)", 
             xy=(pd.Timestamp("2018-07-20", tz="America/Chicago"), 2000), 
             xytext=(pd.Timestamp("2018-04-15", tz="America/Chicago"), 1700),
             ha="center", fontsize=9.5, fontweight="bold", color="#c0392b",
             arrowprops=dict(arrowstyle="->", color="#c0392b", lw=1.8))

ax1.axhline(33.26, color="#e67e22", linestyle="--", linewidth=1.5, label="Média Anual (US$ 33,26 / MWh)")
ax1.legend(loc="upper right", frameon=True, fontsize=10)

# 2. CURVA MEDIA HORARIA: DIAS UTEIS VS FINAIS DE SEMANA
hourly_profile = df.groupby(["hour", "is_weekday"])["ercot_spp_usd_mwh"].mean().unstack()

ax2.plot(hourly_profile.index, hourly_profile[True], marker="o", color="#c0392b", linewidth=2.2, label="Dias Úteis (Segunda a Sexta)")
ax2.plot(hourly_profile.index, hourly_profile[False], marker="s", color="#27ae60", linewidth=2.2, label="Finais de Semana (Sábado e Domingo)")

ax2.set_title("PERFIL MÉDIO HORÁRIO REAL DO ERCOT DAM 2018 (AUSTIN / LZ_AEN)", fontsize=13, fontweight="bold", color="#2c3e50")
ax2.set_xlabel("Hora do Dia (Horário Local de Austin - CST/CDT)", fontsize=11, fontweight="bold")
ax2.set_ylabel("Preço Médio (US$ / MWh)", fontsize=11, fontweight="bold")
ax2.set_xticks(range(0, 24))
ax2.set_xticklabels([f"{h:02d}h" for h in range(24)], fontsize=10)
ax2.grid(True, linestyle=":", alpha=0.6)
ax2.legend(loc="upper left", frameon=True, fontsize=10)

# Anotacoes de recarga e descarga
ax2.annotate("Vale da Madrugada\n(~US$ 20 / MWh)\nRecarga Econômica", 
             xy=(4, hourly_profile[True].loc[4]), xytext=(4, 45),
             ha="center", fontsize=9, fontweight="bold", color="#2980b9",
             arrowprops=dict(arrowstyle="->", color="#2980b9", lw=1.5))

ax2.annotate("Pico Vespertino/Noturno\n(~US$ 80 a 88 / MWh médio)\nDescarga da Bateria", 
             xy=(16, hourly_profile[True].loc[16]), xytext=(19.2, 75),
             ha="center", fontsize=9, fontweight="bold", color="#c0392b",
             arrowprops=dict(arrowstyle="->", color="#c0392b", lw=1.5))

out_img = "data/3_otimizador_ercot_atacado/imagens/grafico_ercot_dam_2018_real.png"
plt.savefig(out_img, dpi=300, bbox_inches="tight")
print(f"Grafico salvo com sucesso em {out_img}")
