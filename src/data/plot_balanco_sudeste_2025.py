# ==============================================================================
# BALANÇO DE ENERGIA HORÁRIO: SUBSISTEMA SUDESTE/CENTRO-OESTE (ONS - JULHO/2025)
# ==============================================================================
#
# Objetivo deste script:
#   Analisar e plotar o comportamento horário da matriz de geração elétrica do
#   subsistema Sudeste/Centro-Oeste (SE) durante uma semana completa de inverno/estiagem
#   (07/Jul a 13/Jul/2025, de segunda-feira a domingo), comparando:
#     - Fontes Renováveis Variáveis: Geração Solar Fotovoltaica + Geração Eólica
#     - Fontes Não Variáveis (Firmes/Despacháveis): Hidrelétricas + Térmicas e Nuclear
#
# Estrutura do Gráfico (2 Painéis Verticais Sincronizados):
#   Painel Superior:
#     - Geração Total do Sudeste (em MW, eixo esquerdo Y1)
#     - Linha de Porcentagem de Participação das Fontes Variáveis (em %, eixo direito Y2)
#   Painel Inferior:
#     - Linha 1: Energias Renováveis Variáveis (Solar + Eólica em MW)
#     - Linha 2: Energias Não Variáveis / Firmes (Hidro + Térmica/Nuclear em MW)
#
# Fonte de Dados:
#   Operador Nacional do Sistema Elétrico (ONS) - Dados Abertos
#   Arquivo: data/BALANCO_ENERGIA_SUBSISTEMA_2025.csv
# ==============================================================================

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

# Diretório raiz do projeto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_FILE = os.path.join(BASE_DIR, 'data', 'BALANCO_ENERGIA_SUBSISTEMA_2025.csv')
OUTPUT_DIR = os.path.join(BASE_DIR, 'Resultados de Otimizacao')


def format_mw(x, pos):
    """Formata valores em MW com separador de milhar brasileiro."""
    return f"{int(x):,}".replace(",", ".")


def load_and_preprocess_se_week(
    start_date='2025-07-07 00:00:00',
    end_date='2025-07-13 23:00:00',
    subsystem='SIN'
):
    """
    Carrega o balanço de energia oficial do ONS para 2025, filtra o subsistema
    selecionado (padrão 'SIN' - Sistema Interligado Nacional / Brasil Geral)
    e extrai a semana selecionada.
    """
    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(f"Arquivo de dados não encontrado em: {DATA_FILE}")

    print(f"Lendo base de dados oficial do ONS: {DATA_FILE}...")
    df = pd.read_csv(DATA_FILE, sep=';')

    # Filtrar subsistema selecionado (SIN = Sistema Interligado Nacional)
    df_sub = df[df['id_subsistema'] == subsystem].copy()
    df_sub['din_instante'] = pd.to_datetime(df_sub['din_instante'])

    # Filtrar intervalo temporal
    mask = (df_sub['din_instante'] >= start_date) & (df_sub['din_instante'] <= end_date)
    df_week = df_sub[mask].sort_values('din_instante').reset_index(drop=True)

    if len(df_week) == 0:
        raise ValueError(f"Nenhum registro encontrado para o intervalo {start_date} a {end_date} no subsistema {subsystem}.")

    print(f"Total de horas extraídas para o subsistema {subsystem}: {len(df_week)} horas (esperado: 168h)")

    # --------------------------------------------------------------------------
    # Agregações Matemáticas das Fontes de Energia
    # --------------------------------------------------------------------------
    # 1. Fontes Renováveis Variáveis (VRE): Solar Centralizada + Eólica
    df_week['variavel_mw'] = df_week['val_gersolar'] + df_week['val_gereolica']

    # 2. Fontes Não Variáveis / Firmes e Despacháveis: Hidrelétrica + Térmica (inclui Nuclear Angra 1 e 2)
    df_week['nao_variavel_mw'] = df_week['val_gerhidraulica'] + df_week['val_gertermica']

    # 3. Geração Total Interna do Sistema
    df_week['geracao_total_mw'] = df_week['variavel_mw'] + df_week['nao_variavel_mw']

    # 4. Proporção Percentual de Participação das Renováveis Variáveis
    df_week['pct_variavel'] = np.where(
        df_week['geracao_total_mw'] > 0,
        (df_week['variavel_mw'] / df_week['geracao_total_mw']) * 100.0,
        0.0
    )

    return df_week


def plot_balanco_sin(
    df_data,
    title='Balanço de Energia Horário no Sistema Interligado Nacional — SIN (ONS — 2025)',
    out_filename='grafico_balanco_sin_julho_2025.png',
    time_scale='week'
):
    """
    Gera o gráfico comparativo de 2 painéis verticais sincronizados em alta resolução
    para o Sistema Interligado Nacional (Geral Brasil), com legendas limpas.
    Suporta time_scale='week' (7 dias com marcação diária) e 'month' (31 dias com marcações periódicas).
    """
    plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
    plt.rcParams['axes.edgecolor'] = '#bdc3c7'
    plt.rcParams['axes.linewidth'] = 0.9

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(16, 11),
        sharex=True,
        gridspec_kw={'height_ratios': [1.1, 1.1]}
    )

    timestamps = df_data['din_instante']

    # ==========================================================================
    # PAINEL 1 (SUPERIOR): Geração Total do Sistema e Demanda / Carga
    # ==========================================================================
    color_total = '#1a5276'      # Azul marinho escuro
    color_carga = '#7f8c8d'      # Cinza neutro

    # Curva de Geração Total (Eixo Esquerdo Y1)
    ax1.plot(
        timestamps,
        df_data['geracao_total_mw'],
        color=color_total,
        linewidth=2.2 if time_scale == 'week' else 1.7,
        label="Geração Total (Sistema Interligado Nacional - SIN)"
    )
    ax1.fill_between(
        timestamps,
        df_data['geracao_total_mw'].min() * 0.95,
        df_data['geracao_total_mw'],
        color=color_total,
        alpha=0.10
    )

    # Curva de Demanda / Carga Total do Sistema
    ax1.plot(
        timestamps,
        df_data['val_carga'],
        color=color_carga,
        linestyle='--',
        linewidth=1.5 if time_scale == 'week' else 1.3,
        alpha=0.85,
        label="Carga / Demanda Total do Sistema"
    )

    ax1.set_ylabel('Potência (MW)', fontsize=12, fontweight='bold', color=color_total)
    ax1.tick_params(axis='y', labelcolor=color_total)
    ax1.yaxis.set_major_formatter(FuncFormatter(format_mw))
    ax1.grid(True, linestyle='--', alpha=0.35)
    ax1.legend(loc='upper left', framealpha=0.92, fontsize=10.5)

    period_str = (
        "Quarta-Feira, 09/Jul/2025 (24 Horas)" if time_scale == 'day'
        else ("Semana de 07/Jul a 13/Jul/2025" if time_scale == 'week' else "Mês Completo de Julho/2025 (31 Dias)")
    )
    ax1.set_title(
        f"Balanço de Energia Horário no Sistema Interligado Nacional — SIN (ONS — {period_str})\n"
        f"Painel 1: Geração Total do Sistema Elétrico vs. Demanda / Carga",
        fontsize=13,
        fontweight='bold',
        pad=10
    )

    # ==========================================================================
    # PAINEL 2 (INFERIOR): Comparativo das Duas Famílias de Fontes (em MW)
    # ==========================================================================
    color_var = '#27ae60'        # Verde esmeralda para variáveis (solar + eólica)
    color_nao_var = '#2980b9'    # Azul para fontes firmes (hidro + térmica/nuclear)

    # 1. Linha de Fontes Variáveis (Solar + Eólica)
    ax2.plot(
        timestamps,
        df_data['variavel_mw'],
        color=color_var,
        linewidth=2.4 if time_scale in ['week', 'day'] else 1.7,
        label="Fontes Renováveis Variáveis (Solar Fotovoltaica + Eólica)"
    )
    ax2.fill_between(
        timestamps,
        0,
        df_data['variavel_mw'],
        color=color_var,
        alpha=0.20
    )

    # 2. Linha de Fontes Não Variáveis / Firmes (Hidráulica + Térmica/Nuclear)
    ax2.plot(
        timestamps,
        df_data['nao_variavel_mw'],
        color=color_nao_var,
        linewidth=2.4 if time_scale in ['week', 'day'] else 1.7,
        label="Fontes Não Variáveis / Firmes e Despacháveis (Hidrelétricas + Térmicas / Nuclear)"
    )
    ax2.fill_between(
        timestamps,
        df_data['nao_variavel_mw'].min() * 0.95,
        df_data['nao_variavel_mw'],
        color=color_nao_var,
        alpha=0.10
    )

    ax2.set_ylabel('Potência Gerada (MW)', fontsize=12, fontweight='bold', color='#2c3e50')
    ax2.yaxis.set_major_formatter(FuncFormatter(format_mw))
    ax2.grid(True, linestyle='--', alpha=0.35)
    ax2.legend(loc='upper left', framealpha=0.92, fontsize=10.5)

    ax2.set_title(
        'Painel 2: Decomposição da Potência por Grupo — Renováveis Variáveis vs. Fontes Firmes e Despacháveis',
        fontsize=12,
        fontweight='bold',
        pad=10
    )

    # ==========================================================================
    # Configuração do Eixo X e Linhas Divisórias
    # ==========================================================================
    if time_scale == 'day':
        ax2.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 2)))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Hh'))
        ax2.xaxis.set_minor_locator(mdates.HourLocator(byhour=range(0, 24, 1)))
        ax2.tick_params(axis='x', labelsize=10)
        ax2.set_xlabel(
            'Tempo (Horário de Brasília — Quarta-Feira, 09/Jul/2025 — 24 Horas)',
            fontsize=12,
            fontweight='bold',
            labelpad=12
        )
    elif time_scale == 'week':
        midnight_marks = df_data[df_data['din_instante'].dt.hour == 0]['din_instante']
        for dt in midnight_marks:
            ax1.axvline(dt, color='#7f8c8d', linestyle=':', linewidth=1.2, alpha=0.7)
            ax2.axvline(dt, color='#7f8c8d', linestyle=':', linewidth=1.2, alpha=0.7)

        dias_semana_pt = {
            'Mon': 'Seg', 'Tue': 'Ter', 'Wed': 'Qua',
            'Thu': 'Qui', 'Fri': 'Sex', 'Sat': 'Sáb', 'Sun': 'Dom'
        }

        def date_formatter_pt(x, pos):
            dt = mdates.num2date(x)
            dia_pt = dias_semana_pt.get(dt.strftime('%a'), '')
            return f"{dt.strftime('%d/%m')}\n({dia_pt})"

        ax2.xaxis.set_major_locator(mdates.DayLocator())
        ax2.xaxis.set_major_formatter(FuncFormatter(date_formatter_pt))
        ax2.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 12, 18]))
        ax2.tick_params(axis='x', labelsize=10)
        ax2.set_xlabel(
            'Tempo (Horário de Brasília — Dias da Semana de 07/Jul a 13/Jul/2025)',
            fontsize=12,
            fontweight='bold',
            labelpad=12
        )
    else:
        # Escala Mensal: linhas verticais em todas as segundas-feiras (virada da semana)
        monday_marks = df_data[(df_data['din_instante'].dt.hour == 0) & (df_data['din_instante'].dt.dayofweek == 0)]['din_instante']
        for dt in monday_marks:
            ax1.axvline(dt, color='#7f8c8d', linestyle=':', linewidth=1.1, alpha=0.65)
            ax2.axvline(dt, color='#7f8c8d', linestyle=':', linewidth=1.1, alpha=0.65)

        ax2.xaxis.set_major_locator(mdates.DayLocator(bymonthday=[1, 5, 10, 15, 20, 25, 30]))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%b'))
        ax2.xaxis.set_minor_locator(mdates.DayLocator())
        ax2.tick_params(axis='x', labelsize=10)
        ax2.set_xlabel(
            'Tempo (Horário de Brasília — Mês Completo de Julho/2025 — 31 Dias / 744 Horas)',
            fontsize=12,
            fontweight='bold',
            labelpad=12
        )

    plt.tight_layout()

    # Salva nas pastas de destino
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, out_filename)
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"\n[SUCESSO] Gráfico salvo com sucesso em: {out_path}")

    # Também salva uma cópia na pasta data para conveniência
    data_out = os.path.join(BASE_DIR, 'data', out_filename)
    plt.savefig(data_out, dpi=300, bbox_inches='tight')
    print(f"[SUCESSO] Cópia de segurança salva em: {data_out}")

    plt.close()
    return out_path


def print_summary_statistics(df_data, period_label="07 a 13/Jul/2025"):
    """
    Imprime um resumo estatístico das métricas calculadas.
    """
    print("\n" + "=" * 70)
    print(f"RESUMO ESTATÍSTICO DO BALANÇO DE ENERGIA — SIN / BRASIL ({period_label})")
    print("=" * 70)
    print(f"• Total de horas analisadas: {len(df_data)} horas")
    print(f"• Carga Máxima do Sistema (SIN): {df_data['val_carga'].max():,.2f} MW")
    print(f"• Carga Média do Sistema (SIN):  {df_data['val_carga'].mean():,.2f} MW")
    print(f"• Carga Mínima do Sistema (SIN): {df_data['val_carga'].min():,.2f} MW")
    print("-" * 70)
    print(f"• Geração Total Máxima:          {df_data['geracao_total_mw'].max():,.2f} MW")
    print(f"• Geração Total Média:           {df_data['geracao_total_mw'].mean():,.2f} MW")
    print(f"• Geração Total Mínima:          {df_data['geracao_total_mw'].min():,.2f} MW")
    print("-" * 70)
    print(f"• Fontes Variáveis (Solar+Eólica) - Pico:    {df_data['variavel_mw'].max():,.2f} MW")
    print(f"• Fontes Variáveis (Solar+Eólica) - Média:   {df_data['variavel_mw'].mean():,.2f} MW")
    print(f"• Fontes Não Variáveis (Hidro+Térmica) - Max: {df_data['nao_variavel_mw'].max():,.2f} MW")
    print(f"• Fontes Não Variáveis (Hidro+Térmica) - Min: {df_data['nao_variavel_mw'].min():,.2f} MW")
    print("-" * 70)
    print(f"• Participação Máxima de Renováveis (%):      {df_data['pct_variavel'].max():.2f}%")
    print(f"• Participação Média no Período (%):          {df_data['pct_variavel'].mean():.2f}%")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    # 1. Horizonte Semanal (07 a 13/Jul/2025)
    print("\n=== GERANDO GRÁFICO SEMANAL (07 A 13/JUL/2025) ===")
    df_week = load_and_preprocess_se_week(
        start_date='2025-07-07 00:00:00',
        end_date='2025-07-13 23:00:00',
        subsystem='SIN'
    )
    print_summary_statistics(df_week, "1 Semana: 07 a 13/Jul/2025")
    plot_balanco_sin(
        df_week,
        out_filename='grafico_balanco_sin_julho_2025.png',
        time_scale='week'
    )

    # 2. Horizonte Mensal Completo (01 a 31/Jul/2025)
    print("\n=== GERANDO GRÁFICO MENSAL (01 A 31/JUL/2025 — 744 HORAS) ===")
    df_month = load_and_preprocess_se_week(
        start_date='2025-07-01 00:00:00',
        end_date='2025-07-31 23:00:00',
        subsystem='SIN'
    )
    print_summary_statistics(df_month, "1 Mês Completo: Julho/2025")
    plot_balanco_sin(
        df_month,
        out_filename='grafico_balanco_sin_1mes_julho_2025.png',
        time_scale='month'
    )

    # 3. Horizonte Diário de 24h (Quarta-Feira, 09/Jul/2025)
    print("\n=== GERANDO GRÁFICO DIÁRIO (09/JUL/2025 — 24 HORAS) ===")
    df_day = load_and_preprocess_se_week(
        start_date='2025-07-09 00:00:00',
        end_date='2025-07-09 23:00:00',
        subsystem='SIN'
    )
    print_summary_statistics(df_day, "1 Dia Útil: 09/Jul/2025")
    plot_balanco_sin(
        df_day,
        out_filename='grafico_balanco_sin_1dia_09jul_2025.png',
        time_scale='day'
    )


