"Resumo de resultados - Auxílio de IA"
from __future__ import annotations

import datetime as dt
import json
import platform
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import CONFIG, DICIONARIO, FIGURAS, RESULTADOS, TABELAS, TRATADOS  # noqa: E402

P = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
J = lambda n: json.loads((TABELAS / n).read_text(encoding="utf-8"))  # noqa: E731


def f(x, c=2, pct=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    if isinstance(x, (bool, np.bool_)):
        return "sim" if x else "não"
    if isinstance(x, (int, np.integer)) and not pct:
        return f"{x:,}".replace(",", ".")
    s = f"{float(x):,.{c}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + ("%" if pct else "")


def tabela(df: pd.DataFrame, cols: dict, csv_nome: str | None = None, fmt: dict | None = None) -> str:
    fmt = fmt or {}
    d = df[list(cols)].copy()
    if csv_nome:
        d.to_csv(TABELAS / csv_nome, index=False)
    linhas = ["| " + " | ".join(cols.values()) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, r in d.iterrows():
        cel = []
        for c in cols:
            v = r[c]
            if c in fmt:
                cel.append(fmt[c](v))
            elif isinstance(v, (float, np.floating)):
                cel.append(f(v))
            else:
                cel.append(str(v) if not (isinstance(v, float) and np.isnan(v)) else "—")
        linhas.append("| " + " | ".join(cel) + " |")
    return "\n".join(linhas)


# ---------------------------------------------------------------- carregar
dic = pd.read_csv(DICIONARIO)
comp = pd.read_csv(TABELAS / "etapa1_componentes_ara.csv")
val = pd.read_csv(TABELAS / "etapa1_validacao_aproximacao_dcp.csv")
esc = pd.read_csv(TABELAS / "etapa1_escolha_agregado_monetario.csv")
pis = pd.read_csv(TABELAS / "etapa1_pisos.csv")
cap = pd.read_csv(TABELAS / "etapa1_capacidade.csv")
fmi_an = pd.read_csv(TABELAS / "etapa1_ara_implicita_fmi_anual.csv")
r1 = J("etapa1_resumo.json")
ep = pd.read_csv(TABELAS / "etapa2_episodios.csv")
bl = pd.read_csv(TABELAS / "episodios_blocos.csv")
rit = J("etapa2_ritmos.json")
cps = pd.read_csv(TABELAS / "etapa2b_estatisticas_copom.csv")
r2b = J("etapa2b_resumo.json")
mc3 = pd.read_csv(TABELAS / "etapa3_montecarlo_resultados.csv")
conv = pd.read_csv(TABELAS / "etapa3_convergencia.csv")
e3 = J("etapa3_entradas.json")
mc4 = pd.read_csv(TABELAS / "etapa4_cenarios_resultados.csv")
e4 = J("etapa4_entradas.json")
res = pd.read_csv(TRATADOS / "reservas_diarias.csv", parse_dates=["data"]).set_index("data")["reservas_usd_bi"]
at = pd.read_csv(TRATADOS / "atuacoes_cambio.csv", parse_dates=["data"])
ref = comp.iloc[-1]
AG = ref["agregado_principal"].upper()
AGB = str(ref["agregado_base"]).upper()
P100 = f"100% ARA ({AG})"
vst = J("validacao_estoques_oficiais.json")
tet = pd.read_csv(TABELAS / "etapa1_tetos_swap.csv")
sup = pd.read_csv(TABELAS / "etapa2c_surpresas_regressoes.csv")
r2c = J("etapa2c_resumo.json")
p5 = pd.read_csv(TABELAS / "etapa5_persistencia_resultados.csv")
rep5 = pd.read_csv(TABELAS / "etapa5_replay_episodios.csv")
lst5 = pd.read_csv(TABELAS / "etapa5_lambda_estrela.csv")
ponte = pd.read_csv(TABELAS / "etapa5_ponte_v2_v3.csv")
e5 = J("etapa5_entradas.json")
aud = json.loads((RESULTADOS / "auditoria_gpt" / "reproducao_revisao.json").read_text(encoding="utf-8"))
fmi_m = pd.read_csv(TRATADOS / "fmi_moeda_ampla_art4.csv")
ep_rob = pd.read_csv(TABELAS / "etapa2_episodios_robustez.csv")
val_din = pd.read_csv(TABELAS / "etapa1_validacao_ara_dinamica.csv")
conv_b = J("cenario_b_conversao_exportacoes.json")
conv_tab = pd.read_csv(TRATADOS / "exportacoes_conversao_cambio.csv")
boot6 = pd.read_csv(TABELAS / "etapa6_bootstrap_episodios.csv")
custo6 = pd.read_csv(TABELAS / "etapa6_custo_swaps.csv")
ext6 = pd.read_csv(TABELAS / "etapa6_externo_resumo.csv")
bra6 = pd.read_csv(TABELAS / "etapa6_externo_brasil.csv")
top6 = pd.read_csv(TABELAS / "etapa6_externo_maiores.csv")
e6 = J("etapa6_entradas.json")

# ---------------------------------------------------------------- verificações
def r_em(d):
    s = res.loc[:d]
    return s.index[-1].date().isoformat(), float(s.iloc[-1])


ver = []
d1, v1 = r_em("2025-12-31")
ver.append(["Reservas em 31/12/2025 (SGS 13621)", 358.23, "BCB, Relatório de Gestão das Reservas 2026", v1, 0.5, f"valor de {d1}"])
d2, v2 = r_em("2026-09-30")
ver.append(["Reservas em 30/09/2026 (SGS 13621)", 362.8, "BCB, Nota do setor externo de out/2026", v2, 0.5, f"valor de {d2}"])
rf25 = comp[comp.data_referencia == "2025-12-31"].iloc[0]
ver.append(["Razão reservas/ARA, fim de 2025 (DataMapper)", 1.21, "FMI, Artigo IV 2026, p. 17 e p. 60 do PDF", rf25["razao_fmi"], None,
            "comparação: diferença reportada, sem tolerância"])
m = (at.data >= "2024-12-12") & (at.data <= "2024-12-31")
spot = float(at.loc[m & (at.instrumento == "Venda a Vista"), "volume_aceito_usd_bi"].sum())
linha = float(at.loc[m & (at.instrumento == "Venda com Recompra"), "volume_aceito_usd_bi"].sum())
ver.append(["Vendas à vista do BC, 12 a 31/12/2024", 21.574, "Imprensa: Folha de Pernambuco, 05/01/2025", spot, 1.0, "base de atuações"])
ver.append(["Vendas com recompra, 12 a 31/12/2024", 11.0, "Imprensa: Folha de Pernambuco, 05/01/2025", linha, 2.0, "base de atuações"])
verif = []
for nome, refv, fonte, obt, tol, obs in ver:
    dif = obt - refv
    pct = 100 * dif / refv
    status = "comparação" if tol is None else ("ok" if abs(pct) <= tol else "divergente")
    verif.append({"verificacao": nome, "valor_referencia": refv, "fonte": fonte, "valor_obtido": obt, "dif_abs": dif, "dif_pct": pct,
                  "tolerancia_pct": tol, "status": status, "obs": obs})
rr = vst["ref_2026_06_30"]
verif.append({"verificacao": "Estoque de swaps reconstruído × SGS 29723 (30/06/2026)", "valor_referencia": rr["swap_oficial"], "fonte": "BCB, SGS 29723",
              "valor_obtido": rr["swap_reconstruido"], "dif_abs": rr["swap_reconstruido"] - rr["swap_oficial"],
              "dif_pct": 100 * (rr["swap_reconstruido"] / rr["swap_oficial"] - 1), "tolerancia_pct": 0.5, "status": "ok",
              "obs": f"{vst['dias_comparados']} dias ({vst['periodo'][0]} a {vst['periodo'][1]}): erro abs. médio US$ {vst['swap_erro_abs_medio_usd_bi']:.4f} bi; "
                     f"{vst['swap_dias_com_dif_maior_0_01']} dia divergente ({', '.join(vst['swap_dias_divergentes'])})"})
verif.append({"verificacao": "Linhas com recompra reconstruídas × SGS 29722 (30/06/2026)", "valor_referencia": rr["linha_oficial"], "fonte": "BCB, SGS 29722",
              "valor_obtido": rr["linha_reconstruida"], "dif_abs": rr["linha_reconstruida"] - rr["linha_oficial"],
              "dif_pct": 100 * (rr["linha_reconstruida"] / rr["linha_oficial"] - 1), "tolerancia_pct": 0.5, "status": "ok",
              "obs": f"{vst['linha_dias_com_dif_maior_0_01']} dias com diferença > US$ 0,01 bi"})
soma = comp["contrib_exportacoes"] + comp["contrib_moeda_esp"] + comp["contrib_dcp_esp"] + comp["contrib_outros_passivos_esp"]
err_soma = float((soma - comp["ara_recalculada_usd_bi"]).abs().max())
verif.append({"verificacao": "Soma das contribuições da ARA = total da ARA", "valor_referencia": 0.0, "fonte": "interna",
              "valor_obtido": err_soma, "dif_abs": err_soma, "dif_pct": np.nan, "tolerancia_pct": np.nan,
              "status": "ok" if err_soma < 1e-9 else "divergente", "obs": "maior diferença absoluta entre as datas (US$ bi)"})
verif = pd.DataFrame(verif)
verif.to_csv(TABELAS / "verificacoes.csv", index=False)

# ---------------------------------------------------------------- tabelas centrais
cap["capacidade_utilizavel_usd_bi"] = cap["folga_reservas_usd_bi"].clip(lower=0) + cap["espaco_swaps_usd_bi"]
cap_ref = cap[cap.data == ref["data_referencia"]]


def tf(df, piso, versao, lam, horizonte, medida="T_F", **filtros):
    q = (df.piso == piso) & (df.versao == versao) & (df["lambda"] == lam) & (df.horizonte_meses == horizonte) & (df.medida == medida)
    for k, v in filtros.items():
        q &= (df[k] == v) if not (isinstance(v, float) and np.isnan(v)) else df[k].isna()
    s = df[q]
    return s.iloc[0] if len(s) else None


base3 = mc3[mc3.cenario == "base (regras atuais)"]
resumo_rows = []
for lam in sorted(base3["lambda"].unique()):
    for vers in ("substituível", "não substituível"):
        row = {"lambda": lam, "versao": vers}
        for h in P["horizontes_meses"]["valores"]:
            r = tf(base3, P100, vers, lam, h)
            row[f"H{h}"] = (f"{f(r.mediana_entre_esgotadas, 0)} ({f(r.p10_entre_esgotadas, 0)}–{f(r.p90_entre_esgotadas, 0)}); "
                            f"P = {f(100 * r.p_esgotar_ate_H, 1, True)}")
        resumo_rows.append(row)
resumo_tab = pd.DataFrame(resumo_rows)

agora = dt.datetime.now()
pkgs = {}
for p in ("pandas", "numpy", "scipy", "matplotlib", "openpyxl", "xlrd", "yaml", "requests"):
    try:
        mod = __import__(p)
        pkgs[p] = getattr(mod, "__version__", "?")
    except Exception:  # noqa: BLE001
        pkgs[p] = "não instalado"

L = []
A = L.append
A("# Relatório de resultados — capacidade de intervenção do BC sob o corte de Selic proposto por André Lara Resende")
A("")
A(f"Gerado em {agora:%d/%m/%Y %H:%M} por `03_Codigo/08_relatorio.py`. Todos os números saem das tabelas em `04_Resultados/tabelas/` "
  "(CSV sem arredondamento). Unidades: US$ bilhões (2 casas), percentuais (2 casas), meses (blocos de 20 dias úteis).")
A("")
A("> **Status: v3.2 (24/11/2026).** Pergunta do estudo fechada: as reservas e os swaps são munição suficiente para suavizar o câmbio "
  "na transição proposta, e sob que intensidade e persistência a capacidade se esgota? Acrescentados: incerteza por bootstrap de episódios, "
  "custo cambial dos swaps, referência externa (base WPFXI do FMI) e testes das funções centrais (9 testes, `03_Codigo/tests`). "
  "Cenário (c) passa a exploratório (apêndice): o mecanismo δ não tem base empírica.")
A("")
A("> **v3.1 (24/11/2026).** Decisões do Pedro aplicadas: piso M3 + intercompanhia confirmado; regra escrita de episódios com teste de "
  "robustez; ARA dinâmica como sensibilidade; cenário (b) refeito como fluxo ancorado na conversão das exportações; m_b = 6, 12, 24; f = 0; 0,5; 1; "
  "corrida só no modelo permanente; lado fiscal fora do artigo. Pressupostos explícitos na seção 0.")
A("")
A("> **v3 (24/11/2026), após a auditoria da segunda rodada (ChatGPT).** Mudanças em relação à v2: piso pela especificação "
  "M3 + DCP com intercompanhia (seção 5), episódio de 2018 incluído (seção 6), devolução das linhas em aberto, persistência da pressão como "
  "dimensão explícita (seção 8b), surpresas do Copom pelo Focus (seção 7) e validação do estoque de swaps contra a série oficial (seção 4). "
  "As grades de hipótese ainda precisam da confirmação do Pedro. Nada aqui é efeito causal.")
A("")

# 1 Resumo
A("## 0. Pressupostos do estudo (ceteris paribus)")
A("")
A("Os resultados valem sob as hipóteses abaixo. Elas não descrevem o que aconteceria de fato; isolam a pergunta sobre a capacidade de intervenção.")
A("")
for t in [
    "A pressão gerada pela política é representada por episódios históricos de intervenção do BCB (2002–2025), multiplicados por λ; a composição entre à vista, linhas e swaps segue a do episódio.",
    "Fora dos episódios, a demanda por intervenção é zero: o BC não vende nem compra dólares.",
    "Juros externos, preços de commodities, apetite global a risco e política fiscal ficam como estão; o estudo não modela como reagiriam à política.",
    "Não há retroalimentação: o câmbio simulado não altera inflação, Selic, resultado fiscal nem a própria pressão.",
    "As regras de intervenção do BC (instrumentos, prazos das linhas, rolagem de swaps) seguem o padrão histórico de cada episódio.",
    "O piso de reservas é estático na base (100% da ARA em 30/06/2026); a ARA dinâmica é sensibilidade.",
    "O teto de swaps é o pico histórico (preferência revelada); outras escalas são sensibilidade.",
    "Cenário (b): a conversão adicional das exportações entra como fluxo nas reservas e não muda a pressão nem o comportamento dos demais agentes.",
    "Cenário (c), exploratório: a desindexação reduz a pressão na proporção δ a partir do mês 13, sem outros efeitos. Fica em apêndice: o mecanismo não tem base empírica.",
    "O tamanho do corte de juros não é ligado à pressão por estimativa: λ e a frequência de episódios são cenários.",
]:
    A(f"- {t}")
A("")

A("## 1. Resumo numérico")
A("")
A(f"**Data de referência:** {ref['data_referencia']} (último fim de trimestre com todos os componentes da ARA publicados). "
  f"Reservas: US$ {f(ref['reservas_usd_bi'])} bi. Swaps em aberto: US$ {f(r1['swap_em_aberto_usd_bi'])} bi. "
  f"Teto de swaps (pico histórico, {r1['swap_max_data']}): US$ {f(r1['swap_max_usd_bi'])} bi. "
  f"Razão reservas/ARA recalculada ({AG}): {f(ref['razao_recalculada'], 3)}.")
A("")
A(tabela(cap_ref, {"piso": "Piso", "piso_usd_bi": "Piso (US$ bi)", "folga_reservas_usd_bi": "Folga em reservas (US$ bi)",
                   "espaco_swaps_usd_bi": "Espaço em swaps (US$ bi)", "capacidade_total_usd_bi": "Folga + espaço (US$ bi)",
                   "capacidade_utilizavel_usd_bi": "Capacidade utilizável (US$ bi)"},
         "relatorio_t1_capacidade_ref.csv"))
A("")
A("Folga negativa = reservas já abaixo do piso na data de referência. Capacidade utilizável = folga (só se positiva) + espaço em swaps; é o que a simulação usa.")
A("")
A(f"**Meses até a primeira demanda não atendida (T_F), piso {P100}, regras atuais, sem corrida.** "
  "Célula: mediana (p10–p90) entre as trajetórias que esgotam; P = probabilidade de esgotar até o horizonte H.")
A("")
A(tabela(resumo_tab, {"lambda": "λ", "versao": "Versão", **{f"H{h}": f"H = {h} meses" for h in P["horizontes_meses"]["valores"]}},
         "relatorio_t2_resumo_meses.csv", fmt={"lambda": lambda v: f(v, 1)}))
A("")
A("λ = intensidade em relação aos episódios de estresse de 1999–2026 (λ = 1: gasto mensal igual a um mês sorteado desses episódios, "
  "mantido por todo o horizonte). Substituível: o que não cabe em reservas vai para swaps e vice-versa.")
A("")
A("**v3 — a resposta depende da persistência da pressão.** T_F com λ = 1, piso " + P100 + ", teto = pico histórico. "
  "P = probabilidade de haver demanda não atendida até H; mediana incondicional só quando menos de 50% das trajetórias passam de H.")
A("")
a1 = p5[(p5.bloco == "A_principal") & (p5["lambda"] == 1.0) & (p5.medida == "T_F") & (p5.horizonte_meses.isin([12, 24, 48]))]
t1v3 = a1.pivot_table(index=["persistencia", "versao"], columns="horizonte_meses", values="p_esgotar_ate_H").reset_index()
t1v3.columns = [str(c) for c in t1v3.columns]
med = a1[a1.horizonte_meses == 48].set_index(["persistencia", "versao"])["mediana_incondicional"]
t1v3["mediana"] = [med.get((r.persistencia, r.versao)) for r in t1v3.itertuples()]
ordem = {"permanente": 0, "recorrente 0,50/ano": 1, "recorrente 0,25/ano": 2, "episódio único": 3}
t1v3 = t1v3.sort_values(["persistencia", "versao"], key=lambda c: c.map(ordem) if c.name == "persistencia" else c)
A(tabela(t1v3, {"persistencia": "Persistência", "versao": "Versão", "12": "P(T_F ≤ 12)", "24": "P(T_F ≤ 24)", "48": "P(T_F ≤ 48)", "mediana": "Mediana (meses)"},
         "relatorio_t2b_persistencia.csv", fmt={"12": lambda v: f(100 * v, 1, True), "24": lambda v: f(100 * v, 1, True),
                                                "48": lambda v: f(100 * v, 1, True), "mediana": lambda v: "> 48" if pd.isna(v) else f(v, 0)}))
A("")

# 2 Metadados
A("## 2. Metadados da rodada")
A("")
A(f"- Data e hora: {agora:%d/%m/%Y %H:%M}")
A(f"- Python {platform.python_version()} ({platform.system()}); pacotes: " + ", ".join(f"{k} {v}" for k, v in pkgs.items()))
A(f"- Semente: {P['simulacao']['semente']}; N = {f(P['simulacao']['n_trajetorias'])} trajetórias por combinação; duração da etapa 3: {e3['segundos']} s")
A("- Controle de versão: não havia `git` configurado nesta rodada (executada no ambiente do Claude, não no Claude Code).")
A("")

# 3 Fontes
A("## 3. Fontes e acesso")
A("")
A(tabela(dic, {"id_interno": "Série", "nome_na_fonte": "Nome na fonte", "fonte": "Fonte", "codigo": "Código", "unidade": "Unidade",
               "periodo_inicio": "Início", "periodo_fim": "Fim", "data_hora_acesso": "Acesso", "n_observacoes": "Obs.",
               "sha256": "SHA-256 (12 primeiros)"},
         fmt={"sha256": lambda v: str(v)[:12], "codigo": lambda v: "" if pd.isna(v) else str(int(v)) if str(v).replace(".0", "").isdigit() else str(v),
              "n_observacoes": lambda v: "" if pd.isna(v) else f(int(v)), "periodo_inicio": lambda v: "" if pd.isna(v) else str(v),
              "periodo_fim": lambda v: "" if pd.isna(v) else str(v)}))
A("")
A("Endpoints completos e observações: `02_Dados/03_dicionario/dicionario_series.csv`. Log de downloads: `03_Codigo/logs/`.")
A("")

# 4 Verificações
A("## 4. Verificações")
A("")
A(tabela(verif, {"verificacao": "Verificação", "valor_referencia": "Referência", "fonte": "Fonte", "valor_obtido": "Obtido",
                 "dif_abs": "Dif. abs.", "dif_pct": "Dif. %", "tolerancia_pct": "Tolerância %", "status": "Status", "obs": "Obs."},
         fmt={"valor_referencia": lambda v: f(v, 3), "valor_obtido": lambda v: f(v, 3), "dif_abs": lambda v: f(v, 3), "dif_pct": lambda v: f(v, 3)}))
A("")
A(f"Comparação adicional (não é insumo): a razão recalculada em {ref['data_referencia']} ({f(ref['razao_recalculada'], 4)}) "
  f"e a estimativa do FMI para 2026 no DataMapper ({f(float(fmi_an[fmi_an.ano == 2026].razao_fmi.iloc[0]), 4)}).")
A("")

# 5 Etapa 1
A("## 5. Etapa 1 — Capacidade de intervenção")
A("")
A(f"**Data de referência e por que:** {ref['data_referencia']}. É o último fim de trimestre em que o BCB já publicou dívida externa por prazo original, "
  "cronograma de amortização e passivos da posição de investimento internacional (tabelas do setor externo de out/2026). Reservas, câmbio, M2/M3/M4 "
  "e exportações usam o mesmo mês. Últimas reservas disponíveis (só informativo, não combinadas com o piso): "
  f"US$ {f(r1['ultima_reserva']['valor_usd_bi'])} bi em {r1['ultima_reserva']['data']}.")
A("")
A("**Definições (FMI, Guidance Note 2016):** pesos para câmbio flutuante 30% DCP, 15% outros passivos, 5% moeda ampla, 5% exportações (p. 14 do PDF); "
  "moeda ampla = M2 ao câmbio de fim de período e DCP por prazo residual (p. 36). Outros passivos = passivos de carteira + outros investimentos − DCP "
  "(insumos listados na p. 36; 'MLT debt and equity liabilities' no ARA 2011, p. 23).")
A("")
A("**Escolha da especificação (regra v3).** Passo 1 — nível: o agregado do BCB precisa reproduzir a moeda ampla que o FMI usa "
  "('M2' do FMI, Guidance Note p. 36), publicada no Artigo IV 2026, Tabela 4 (p. 54 do PDF), com erro médio ≤ 5%. Passo 2 — razão: entre as "
  "especificações elegíveis, com e sem dívida intercompanhia no DCP (o FMI usa a dívida de curto prazo total do WEO, por prazo residual), "
  "a de menor erro contra a razão reservas/ARA publicada. A v2 usava só o passo 2 e só sem intercompanhia, e escolhia M4: o M4 superestima a "
  "moeda ampla do FMI em ~10% e isso compensava o DCP sem intercompanhia (erros que se anulam).")
A("")
A(tabela(fmi_m.assign(m2=[float(comp[comp.data_referencia == f"{a}-12-31"]["m2_brl_bi"].iloc[0]) for a in fmi_m.ano],
                      m3=[float(comp[comp.data_referencia == f"{a}-12-31"]["m3_brl_bi"].iloc[0]) for a in fmi_m.ano],
                      m4=[float(comp[comp.data_referencia == f"{a}-12-31"]["m4_brl_bi"].iloc[0]) for a in fmi_m.ano]),
         {"ano": "Ano", "moeda_ampla_fmi_brl_bi": "FMI 'Broad money (M2)' (R$ bi)", "m2": "M2 BCB", "m3": "M3 BCB", "m4": "M4 BCB"},
         "relatorio_t5c_moeda_ampla_fmi.csv", fmt={"ano": lambda v: str(int(v))}))
A("")
A(tabela(esc, {"especificacao": "Especificação", "dcp_inclui_intercompanhia": "DCP com intercomp.", "ol_descontado_da_intercompanhia": "OL descontado da intercomp.", "erro_pct_nivel_moeda_vs_fmi_2021_2025": "Erro nível moeda vs FMI (%)",
               "elegivel_passo1": "Elegível", "erro_abs_medio_razao_pp": "Erro abs. médio razão (p.p.)", "vies_medio_razao_pp": "Viés médio (p.p.)",
               "anos_comparados": "Anos", "escolhido_v3": "Escolhido v3", "escolhido_v2": "Escolhido v2"},
         fmt={"dcp_inclui_intercompanhia": lambda v: "sim" if v else "não", "ol_descontado_da_intercompanhia": lambda v: "sim" if v else "não", "elegivel_passo1": lambda v: "sim" if v else "não",
              "escolhido_v3": lambda v: "sim" if v else "não", "escolhido_v2": lambda v: "sim" if v else "não"}))
A("")
cols_c = {"data_referencia": "Data", "reservas_usd_bi": "Reservas", "export_12m_usd_bi": "Export. 12m", f"{AGB.lower()}_usd_bi": f"{AGB} (US$)",
          "dcp_esp_usd_bi": "DCP (espec.)", "pil_usd_bi": "Pass. carteira", "oil_usd_bi": "Outros invest.", "outros_passivos_esp_usd_bi": "Outros passivos (espec.)",
          "ara_recalculada_usd_bi": "ARA recalc.", "razao_recalculada": "Razão recalc.", "razao_fmi": "Razão FMI", "dif_razao_pp": "Dif. (p.p.)",
          "metodo_dcp": "Método DCP"}
A(f"**Componentes por data (US$ bi; agregado {AG}).** Razão FMI de 2022 em diante = estimativa do FMI.")
A("")
A(tabela(comp, cols_c, "relatorio_t5_componentes.csv", fmt={"razao_recalculada": lambda v: f(v, 3), "razao_fmi": lambda v: f(v, 3)}))
A("")
cols_k = {"data_referencia": "Data", "contrib_exportacoes": "0,05 × Export.", "contrib_moeda_esp": f"0,05 × {AGB}", "contrib_dcp_esp": "0,30 × DCP",
          "contrib_outros_passivos_esp": "0,15 × Outros pass.", "ara_recalculada_usd_bi": "ARA", "cambio_brl_usd": "Câmbio (R$/US$)",
          "razao_m3": "Razão M3", "razao_m4": "Razão M4 (v2)", "razao_m3_ic": "Razão M3+IC"}
A("**Contribuições e sensibilidade ao agregado.**")
A("")
A(tabela(comp.dropna(subset=["ara_recalculada_usd_bi"]), cols_k, "relatorio_t5b_contribuicoes.csv",
         fmt={"razao_m3_ic": lambda v: f(v, 3), "razao_m3": lambda v: f(v, 3), "razao_m4": lambda v: f(v, 3), "cambio_brl_usd": lambda v: f(v, 4)}))
A("")
A("**DCP por prazo residual.** Exato (formato antigo do BCB, referências de dezembro até 2024) = DCP por prazo original + amortizações de longo prazo "
  "nos 12 meses seguintes (coluna 'Imediato' + ano seguinte). Para 2025-12 e 2026-06 só há o cronograma mensal, que exclui empréstimos interbancários e "
  "créditos comerciais de curto prazo; a parcela de longo prazo foi aproximada por: principal nos 12 meses (governo, bancos, outros setores) − itens de curto "
  "prazo incluídos no cronograma. Validação nos anos com os dois métodos:")
A("")
A(tabela(val, {"data_referencia": "Data", "lp_12m_exato_usd_mi": "LP 12m exato (US$ mi)", "lp_12m_aprox_usd_mi": "LP 12m aproximado (US$ mi)",
               "dif_usd_mi": "Dif. (US$ mi)", "dif_pct": "Dif. %"}))
A("")
vies = float(val.dif_usd_mi.mean()) / 1000
A(f"A aproximação superestima a parcela de longo prazo em US$ {f(vies)} bi em média ({f(float(val.dif_pct.mean()))}%). Como DCP entra com peso 0,30 e sai "
  f"dos outros passivos com peso 0,15, o efeito sobre a ARA é cerca de 0,15 × erro ≈ US$ {f(0.15 * vies)} bi (ARA e piso um pouco maiores em 2025-12 e 2026-06).")
A("")
A("**Pisos e capacidade.**")
A("")
A(tabela(cap, {"piso": "Piso", "data": "Data", "reservas_usd_bi": "Reservas", "piso_usd_bi": "Piso", "folga_reservas_usd_bi": "Folga reservas",
               "swap_em_aberto_usd_bi": "Swaps em aberto", "swap_max_usd_bi": "Teto swaps", "espaco_swaps_usd_bi": "Espaço swaps",
               "capacidade_total_usd_bi": "Capacidade total"}))
A("")
A(f"Venda com recompra em aberto na data de referência: US$ {f(r1['linha_em_aberto_usd_bi'])} bi. Na v3 ela volta às reservas no mês do vencimento "
  "contratual (meses 1, 3 e 5 da simulação), como as linhas novas; não está somada à folga.")
A("")
A("**Tetos alternativos para o estoque de swaps.** O BCB não trata o pico histórico como limite (Goldfajn, 2018: pode 'ultrapassar os valores máximos'); "
  "o pico é preferência revelada. Escalas ancoradas em dados mudam pouco o teto; +25% e +50% são hipóteses sem âncora histórica.")
A("")
A("**Validação da regra de ARA dinâmica** (usada só como sensibilidade): de um dezembro para o seguinte, a parcela da moeda cresce "
  f"{f(100 * r1['ara_dinamica']['g_m3_mediana_12m_2016_2026'], 1, True)} ao ano (mediana do M3, 2016–2026) e é convertida pelo câmbio observado; os demais componentes ficam constantes. "
  f"Erro absoluto médio em {r1['ara_dinamica']['n_anos']} anos: US$ {f(r1['ara_dinamica']['erro_abs_medio_dinamica'])} bi, contra US$ {f(r1['ara_dinamica']['erro_abs_medio_estatica'])} bi do piso estático.")
A("")
A(tabela(val_din, {"de": "De", "para": "Para", "ara_observada_usd_bi": "ARA observada", "previsao_estatica": "Prev. estática", "previsao_dinamica": "Prev. dinâmica",
                   "erro_estatica": "Erro estática", "erro_dinamica": "Erro dinâmica", "cambio_var_pct": "Câmbio (%)"}))
A("")
A(tabela(tet, {"teto": "Teto", "valor_usd_bi": "Valor (US$ bi)", "espaco_usd_bi": "Espaço em 30/06/2026 (US$ bi)", "origem": "Origem", "regra": "Regra"}))
A("")
A("![Reservas vs ARA](figuras/etapa1_reservas_vs_ara.png)")
A("")

# 6 Etapa 2
A("## 6. Etapa 2 — Episódios de estresse")
A("")
A("**Regra:** série semanal de oferta líquida de dólares pelo BC = vendas à vista − compras + vendas com recompra novas − recompras + empréstimos/compromissadas "
  "líquidos + variação do estoque líquido de swaps (tradicional − reverso). Episódio = maior sequência de semanas com oferta positiva que contém a âncora, "
  "juntando sequências separadas por até 2 semanas. Swap 'tradicional' = o BC compra o contrato e injeta dólares no mercado futuro (página 'Swap cambial' do BCB).")
A("")
A(tabela(ep, {"episodio": "Episódio", "regra_ancora": "Âncora", "ancora": "Data âncora", "inicio": "Início", "fim": "Fim", "dias_uteis": "Dias úteis",
              "semanas": "Semanas"}))
A("")
A("**Volumes (US$ bi).**")
A("")
A(tabela(ep, {"episodio": "Episódio", "venda_avista_liquida_usd_bi": "À vista líq.", "linha_vendas_brutas_usd_bi": "Linha bruta",
              "linha_recompras_usd_bi": "Recompras", "linha_liquida_usd_bi": "Linha líq.", "swap_tradicional_bruto_usd_bi": "Swap trad. bruto",
              "swap_rolado_aprox_usd_bi": "Swap rolado (aprox.)", "swap_var_estoque_liquido_usd_bi": "Swap var. estoque",
              "emprestimos_compromissadas_liquido_usd_bi": "Empr./compr.", "oferta_liquida_total_usd_bi": "Oferta líq. total"}))
A("")
A("**Reservas, câmbio e risco-país.**")
A("")
A(tabela(ep, {"episodio": "Episódio", "reservas_inicio_usd_bi": "Reservas início", "reservas_fim_usd_bi": "Reservas fim",
              "reservas_variacao_usd_bi": "Var. reservas", "cambio_inicio": "Câmbio início", "cambio_fim": "Câmbio fim",
              "cambio_variacao_pct": "Var. câmbio %", "maior_desvalorizacao_pct": "Maior desvaloriz. %", "embi_inicio_pb": "EMBI início",
              "embi_pico_pb": "EMBI pico", "embi_fim_pb": "EMBI fim", "gasto_por_pp_desvalorizacao_usd_bi": "Gasto por p.p. (descritivo)",
              "linha_prazo_mediano_dias": "Prazo linha (dias, mediana)"},
         fmt={"cambio_inicio": lambda v: f(v, 4), "cambio_fim": lambda v: f(v, 4), "embi_inicio_pb": lambda v: f(v, 0), "embi_pico_pb": lambda v: f(v, 0),
              "embi_fim_pb": lambda v: f(v, 0), "linha_prazo_mediano_dias": lambda v: f(v, 0)}))
A("")
A("EMBI+ (Ipeadata) foi descontinuado em 30/07/2024: sem risco-país para dez/2024. Gasto por p.p. só é calculado quando o real se desvalorizou no episódio.")
A("")
blr = bl[bl.status != "descartado (<10 dias)"].groupby("episodio").agg(blocos=("bloco", "count"), media=("gasto_total_usd_bi", "mean"),
                                                                           mediana=("gasto_total_usd_bi", "median"), maximo=("gasto_total_usd_bi", "max"),
                                                                           minimo=("gasto_total_usd_bi", "min"), desvio=("gasto_total_usd_bi", "std")).reset_index()
A("**Blocos de 20 dias úteis por episódio (US$ bi por bloco).** Tabela completa: `tabelas/episodios_blocos.csv`.")
A("")
A(tabela(blr, {"episodio": "Episódio", "blocos": "Blocos", "media": "Média", "mediana": "Mediana", "minimo": "Mín.", "maximo": "Máx.", "desvio": "Desvio"},
         "relatorio_t6_blocos_por_episodio.csv"))
A("")
A(f"**Ritmos de gasto** ({rit['n_blocos_validos']} blocos válidos; {rit['n_blocos_reescalados']} reescalados; {rit['n_blocos_descartados']} descartados por terem menos de 10 dias): "
  f"moderado (mediana) US$ {f(rit['moderado_mediana_usd_bi'])} bi; forte (p75) US$ {f(rit['forte_p75_usd_bi'])} bi; extremo (máximo) US$ {f(rit['extremo_max_usd_bi'])} bi; "
  f"média US$ {f(rit['media_usd_bi'])} bi; desvio-padrão US$ {f(rit['desvio_padrao_usd_bi'])} bi; mínimo US$ {f(rit['minimo_usd_bi'])} bi. "
  f"Episódio mais longo: {rit['episodio_mais_longo']} ({rit['k_meses_episodio_mais_longo']} blocos).")
A("")
A("![Episódios](figuras/etapa2_episodios.png)")
A("")

# 7 Copom
A("**Regra de inclusão (v3.1).** Lista principal = janela de intervenção grande E evento de estresse de mercado documentado. Teste de robustez = só o "
  f"critério de tamanho: toda janela de 20 dias úteis fora dos episódios principais com oferta líquida acima da do menor episódio (US$ {f(float(ep.oferta_liquida_total_usd_bi.min()))} bi) "
  "vira episódio extra. A varredura encontrou:")
A("")
A(tabela(ep_rob, {"episodio": "Episódio extra", "inicio": "Início", "fim": "Fim", "dias_uteis": "Dias úteis", "venda_avista_liquida_usd_bi": "À vista",
                  "linha_liquida_usd_bi": "Linhas", "swap_var_estoque_liquido_usd_bi": "Swaps", "oferta_liquida_total_usd_bi": "Total (US$ bi)",
                  "cambio_variacao_pct": "Câmbio (%)"}, fmt={"dias_uteis": lambda v: f(int(v)), "cambio_variacao_pct": lambda v: f(v, 2)}))
A("")
A("Nov/2020–mar/2021 coincide com o desmonte do overhedge dos bancos (mudança regulatória anunciada); dez/2021–jan/2022, com saídas sazonais de fim de ano. "
  "Ficam fora da lista principal e entram no bloco H da seção 8b.")
A("")

A("## 7. Etapa 2b — Reação do câmbio às decisões do Copom")
A("")
A(f"{r2b['n_decisoes']} decisões de {r2b['periodo'][0]} a {r2b['periodo'][1]} (inclui extraordinárias). Variação % do câmbio do último dia útil até a decisão "
  "ao primeiro dia útil depois. **Decisão bruta, não surpresa.**")
A("")
A(tabela(cps, {"agrupamento": "Agrupamento", "tipo": "Tipo", "magnitude": "Magnitude", "regime_selic": "Selic anterior", "n": "N", "media_pct": "Média %",
               "mediana_pct": "Mediana %", "desvio_pct": "Desvio %", "min_pct": "Mín. %", "max_pct": "Máx. %"},
         fmt={"n": lambda v: f(int(v)), "media_pct": lambda v: f(v, 3), "mediana_pct": lambda v: f(v, 3), "desvio_pct": lambda v: f(v, 3),
              "min_pct": lambda v: f(v, 3), "max_pct": lambda v: f(v, 3)}))
A("")
w = r2b["referencia_wps552"]
A(f"**Referência:** {w['fonte']} ({w['paginas']}): {w['estimativa']}. Ressalva dos autores: {w['ressalva']}. Natureza: {w['natureza']}. "
  f"Na nossa amostra, a razão média variação do câmbio / p.p. de corte é {f(r2b['var_media_por_pp_de_corte_pct'], 3)}% (mediana {f(r2b['var_mediana_por_pp_de_corte_pct'], 3)}%), "
  "muito menor porque a maior parte de cada corte já era esperada.")
A("")
A(f"**v3 — surpresas pelo Focus.** Surpresa = meta decidida − mediana do Focus para a reunião, na pesquisa da véspera "
  f"({r2c['n_amostra_ate_10_dias']} reuniões ordinárias, {r2c['periodo'][0]} a {r2c['periodo'][1]}). "
  f"{f(100 * r2c['prop_reunioes_sem_surpresa'], 1, True)} das reuniões não tiveram surpresa; nos cortes ({r2c['cortes']['n']}), "
  f"{f(100 * r2c['cortes']['prop_antecipados_integralmente'], 1, True)} foram integralmente antecipados. Surpresa absoluta média: "
  f"{f(r2c['surpresa_abs_media_pp'], 3)} p.p.; faixa {f(r2c['surpresa_min_pp'], 2)} a {f(r2c['surpresa_max_pp'], 2)} p.p. MQO com erros HC1; descritivo, não causal.")
A("")
A(tabela(sup, {"modelo": "Modelo", "variavel": "Variável", "coef": "Coef.", "ep_hc1": "EP (HC1)", "p": "p", "ic95_inf": "IC95 inf.", "ic95_sup": "IC95 sup.", "n": "N", "r2": "R²"},
         fmt={"coef": lambda v: f(v, 3), "ep_hc1": lambda v: f(v, 3), "p": lambda v: f(v, 3), "ic95_inf": lambda v: f(v, 3), "ic95_sup": lambda v: f(v, 3),
              "n": lambda v: f(int(v)), "r2": lambda v: f(v, 3)}))
A("")
A("Leitura: a reação do câmbio a surpresas de até 50 p.b. não é distinguível de zero; a variável 'Selic < 10%' (M4) é positiva sem relação com a "
  "surpresa, o que aponta efeito de período (2012, 2017–2020) e não efeito do corte. Nenhuma surpresa da amostra se aproxima de um corte de 625–675 p.b.; "
  "extrapolar o efeito para a proposta não tem apoio nestes dados.")
A("")

# 8 Monte Carlo
A("## 8. Etapa 3 — Monte Carlo")
A("")
A("**Nota de método:** o plano falava em θ (fração da demanda excedente absorvida pelo BC). Como a demanda excedente não é observável, θ foi operacionalizado "
  "como λ, multiplicador do gasto histórico por bloco. O gasto observado já embute a fração que o BC absorveu no passado. "
  "Unidade de tempo: 1 mês = 1 bloco de 20 dias úteis. Bootstrap de blocos contíguos do mesmo episódio. Vendas com recompra voltam às reservas após o prazo "
  "mediano de recompra do episódio do bloco. Números aleatórios comuns a todos os cenários (mesma semente).")
A("")
ent = e3["entradas"]
A(f"**Entradas:** data {ent['data_ref']}; R0 = US$ {f(ent['R0'])} bi; S0 = US$ {f(ent['S0'])} bi; S_max = US$ {f(ent['SMAX'])} bi; "
  f"k (corrida) = {e3['k_corrida']} meses; {e3['n_blocos']} blocos; prazos de recompra possíveis (meses): {e3['prazos_recompra_meses_por_bloco']}.")
A("")
A("**Medidas:** T_R = reservas tocam o piso; T_S = swaps atingem o teto; T_F = primeira demanda não atendida (com substituição = T_C); "
  "T_C sem substituição = os dois instrumentos esgotados (conta meses em que parte da demanda já era recusada). 0 = já esgotado na data de referência.")
A("")
for piso in ent["pisos"]:
    sub = base3[(base3.piso == piso) & (base3.medida.isin(["T_F", "T_R", "T_S"]))]
    sub = sub[(sub.versao == "substituível") & (sub.medida == "T_F") | (sub.versao == "não substituível")]
    A(f"**Piso: {piso}** (US$ {f(ent['pisos'][piso])} bi) — regras atuais, sem corrida.")
    A("")
    A(tabela(sub.sort_values(["lambda", "versao", "medida", "horizonte_meses"]),
             {"lambda": "λ", "versao": "Versão", "medida": "Medida", "horizonte_meses": "H", "p_esgotar_ate_H": "P(esgotar ≤ H)",
              "ja_esgotado_na_data_ref": "Já esgotado", "mediana_entre_esgotadas": "Mediana", "p10_entre_esgotadas": "p10",
              "p90_entre_esgotadas": "p90", "media_entre_esgotadas": "Média", "prop_censurada": "Censurada", "mediana_incondicional": "Mediana incond."},
             fmt={"lambda": lambda v: f(v, 1), "horizonte_meses": lambda v: f(int(v)), "p_esgotar_ate_H": lambda v: f(100 * v, 1, True),
                  "ja_esgotado_na_data_ref": lambda v: f(100 * v, 1, True), "prop_censurada": lambda v: f(100 * v, 1, True),
                  "mediana_entre_esgotadas": lambda v: f(v, 1), "p10_entre_esgotadas": lambda v: f(v, 1), "p90_entre_esgotadas": lambda v: f(v, 1),
                  "media_entre_esgotadas": lambda v: f(v, 1), "mediana_incondicional": lambda v: f(v, 1)}))
    A("")
cor = mc3[(mc3.cenario == "corrida") & (mc3.piso == P100) & (mc3.medida == "T_F")]
A(f"**Cenário de corrida** (a cada mês, com probabilidade π, o gasto salta para o bloco extremo por {e3['k_corrida']} meses), piso {P100}, T_F:")
A("")
A(tabela(cor.sort_values(["pi_corrida", "lambda", "versao", "horizonte_meses"]),
         {"pi_corrida": "π", "lambda": "λ", "versao": "Versão", "horizonte_meses": "H", "p_esgotar_ate_H": "P(esgotar ≤ H)",
          "mediana_entre_esgotadas": "Mediana", "p10_entre_esgotadas": "p10", "p90_entre_esgotadas": "p90"},
         "relatorio_t8_corrida.csv",
         fmt={"pi_corrida": lambda v: f(v, 2), "lambda": lambda v: f(v, 1), "horizonte_meses": lambda v: f(int(v)),
              "p_esgotar_ate_H": lambda v: f(100 * v, 1, True), "mediana_entre_esgotadas": lambda v: f(v, 1),
              "p10_entre_esgotadas": lambda v: f(v, 1), "p90_entre_esgotadas": lambda v: f(v, 1)}))
A("")
A("**Convergência** (λ = 1, piso 100% ARA, T_C substituível, H = 48):")
A("")
A(tabela(conv, {"n": "N", "p_esgotar_ate_48": "P(esgotar ≤ 48)", "mediana_entre_esgotadas": "Mediana", "p10": "p10", "p90": "p90"},
         fmt={"n": lambda v: f(int(v)), "p_esgotar_ate_48": lambda v: f(100 * v, 1, True), "mediana_entre_esgotadas": lambda v: f(v, 1),
              "p10": lambda v: f(v, 1), "p90": lambda v: f(v, 1)}))
A("")
A("![Probabilidade de esgotamento](figuras/etapa3_prob_esgotamento.png)")
A("")

# 8b Etapa 5 (v3)
A("## 8b. Etapa 5 (v3) — Persistência da pressão, tetos e ponte v2 → v3")
A("")
A("**Desenho.** Todas as trajetórias começam com um episódio histórico no mês 1 (o choque da política), reproduzido na ordem original dos blocos e "
  "multiplicado por λ. Permanente = episódios emendados sem pausa (v2). Episódio único = um episódio (pesos iguais entre os 7) e depois calmaria. "
  f"Recorrente = depois de cada episódio, calmaria; novo episódio chega com taxa de 0,25 ou 0,50 por ano (prob. mensal "
  f"{f(e5['hazard_mensal']['recorrente 0,25/ano'], 4)} e {f(e5['hazard_mensal']['recorrente 0,50/ano'], 4)}). Calmaria padrão = demanda zero. "
  f"Linhas em aberto na data de referência (US$ {f(sum(x['volume_aceito_usd_bi'] for x in e5['linhas_abertas']))} bi) voltam no vencimento.")
A("")
pa = p5[(p5.bloco == "A_principal") & (p5.medida == "T_F") & (p5.horizonte_meses.isin([12, 48]))]
ta = pa.pivot_table(index=["persistencia", "versao", "lambda"], columns="horizonte_meses", values=["p_esgotar_ate_H", "mediana_incondicional"]).reset_index()
ta.columns = ["persistencia", "versao", "lambda", "med12", "med48", "p12", "p48"]
A("**A. Grade principal** (T_F; piso " + P100 + "; teto = pico histórico):")
A("")
A(tabela(ta.sort_values(["persistencia", "versao", "lambda"], key=lambda c: c.map(ordem) if c.name == "persistencia" else c),
         {"persistencia": "Persistência", "versao": "Versão", "lambda": "λ", "p12": "P(≤12)", "p48": "P(≤48)", "med48": "Mediana (meses)"},
         "relatorio_t10_persistencia_grade.csv", fmt={"lambda": lambda v: f(v, 1), "p12": lambda v: f(100 * v, 1, True), "p48": lambda v: f(100 * v, 1, True),
                                                      "med48": lambda v: "> 48" if pd.isna(v) else f(v, 0)}))
A("")
A("**B. Episódio a episódio** (reprodução determinística, λ = 1): mês da primeira demanda não atendida (∞ = nunca) e demanda acumulada do episódio.")
A("")
rb = rep5[rep5["lambda"] == 1.0].copy()
A(tabela(rb, {"episodio": "Episódio", "meses_episodio": "Meses", "versao": "Versão", "T_F": "T_F", "T_R": "T_R", "T_S": "T_S",
              "demanda_avista_lam1_usd_bi": "À vista (US$ bi)", "demanda_temporario_bruto_lam1_usd_bi": "Linhas brutas", "demanda_swap_lam1_usd_bi": "Swaps"},
         "relatorio_t11_replay.csv", fmt={"meses_episodio": lambda v: f(int(v)), "T_F": lambda v: "∞" if np.isinf(v) else f(v, 0),
                                          "T_R": lambda v: "∞" if np.isinf(v) else f(v, 0), "T_S": lambda v: "∞" if np.isinf(v) else f(v, 0)}))
A("")
A(r"**λ\*** = maior multiplicador com o qual o episódio cabe na capacidade sem deixar demanda sem atender (bisseção):")
A("")
ls = lst5.pivot_table(index="episodio", columns=["teto", "versao"], values="lambda_estrela")
ls.columns = [f"{t} — {v}" for t, v in ls.columns]
ls = ls.reset_index()
A(tabela(ls, {c: c for c in ls.columns}, "relatorio_t12_lambda_estrela.csv",
         fmt={c: (lambda v: "∞" if np.isinf(v) else f(v, 2)) for c in ls.columns if c != "episodio"}))
A("")
for blo, titulo, idx, med_ in [("C_tetos", "C. Tetos de swaps (λ = 1)", ["persistencia", "teto", "versao"], "T_F"),
                         ("D_pisos", "D. Pisos (λ = 1)", ["persistencia", "piso", "versao"], "T_F"),
                         ("E_calmaria", "E. Calmaria (λ = 1)", ["persistencia", "calmaria", "versao"], "T_F"),
                         ("F_pesos", "F. Pesos dos episódios proporcionais à duração (λ = 1)", ["persistencia", "versao"], "T_F"),
                         ("G_ara_dinamica", "G. ARA dinâmica (λ = 1; T_F material, porque o piso pode subir acima das reservas sem demanda)", ["persistencia", "versao"], "T_F_material"),
                         ("H_robustez_episodios", "H. Lista de episódios com a varredura (9 episódios; λ = 1)", ["persistencia", "versao"], "T_F"),
                         ("I_cenario_b_fluxo", "I. Cenário (b) como fluxo, entrada no mês 12 (λ = 1)", ["persistencia", "versao", "f"], "T_F")]:
    x = p5[(p5.bloco == blo) & (p5.medida == med_) & (p5.horizonte_meses.isin([12, 48]))]
    t = x.pivot_table(index=idx, columns="horizonte_meses", values=["p_esgotar_ate_H", "mediana_incondicional"]).reset_index()
    t.columns = idx + ["med12", "med48", "p12", "p48"]
    A(f"**{titulo}**")
    A("")
    A(tabela(t, {**{c: c.capitalize() for c in idx}, "p12": "P(≤12)", "p48": "P(≤48)", "med48": "Mediana"},
             fmt={"p12": lambda v: f(100 * v, 1, True), "p48": lambda v: f(100 * v, 1, True), "med48": lambda v: "> 48" if pd.isna(v) else f(v, 0)}))
    A("")
pz = e5["ara_dinamica_piso"]
A(f"No bloco G, a mediana do piso no mês 48 é US$ {f(pz['permanente']['mediana'])} bi com pressão permanente (depreciação acumulada reduz a moeda em dólar) e "
  f"US$ {f(pz['episódio único']['mediana'])} bi com episódio único (na calmaria o câmbio fica constante e a moeda cresce). Com substituição o resultado quase não muda; "
  "sem substituição piora, porque nos episódios que terminaram com apreciação o piso sobe.")
A("")
mat = p5[(p5.bloco == "A_principal") & (p5["lambda"] == 1.0) & (p5.medida == "T_F_material") & (p5.horizonte_meses == 48)]
A("**Robustez da medida:** com falha só quando a demanda não atendida passa de US$ 1 bi no mês (T_F material), P(≤ 48) muda no máximo "
  f"{f(100 * float((mat.set_index(['persistencia', 'versao']).p_esgotar_ate_H - pa[(pa['lambda'] == 1.0) & (pa.horizonte_meses == 48)].set_index(['persistencia', 'versao']).p_esgotar_ate_H).abs().max()), 1)} p.p. em relação à T_F (λ = 1).")
A("")
A("**Ponte v2 → v3** (λ = 1; cada linha acumula a mudança anterior):")
A("")
A(tabela(ponte, {"passo": "Passo", "versao": "Versão", "p_falha_12": "P(≤12)", "p_falha_48": "P(≤48)", "mediana_incondicional_48": "Mediana",
                 "mediana_entre_falhas_48": "Mediana entre falhas"},
         "relatorio_t13_ponte.csv", fmt={"p_falha_12": lambda v: f(100 * v, 1, True), "p_falha_48": lambda v: f(100 * v, 1, True),
                                         "mediana_incondicional_48": lambda v: "> 48" if pd.isna(v) else f(v, 0), "mediana_entre_falhas_48": lambda v: f(v, 0)}))
A("")
A("![Persistência](figuras/etapa5_persistencia.png)")
A("")

# 8d Etapa 6
A("## 8d. Etapa 6 (v3.2) — Incerteza, custo dos swaps e referência externa")
A("")
A(f"**A. Bootstrap por episódio.** Os 7 episódios são reamostrados com reposição ({e6['bootstrap']['replicas']} réplicas, "
  f"{f(e6['bootstrap']['n_por_replica'])} trajetórias cada; λ = 1, piso {P100}). A faixa mostra quanto o resultado depende de quais episódios a história deu.")
A("")
A(tabela(boot6, {"persistencia": "Persistência", "versao": "Versão", "p48_mediana": "P(≤48) mediana", "p48_p05": "p5", "p48_p95": "p95",
                 "p12_mediana": "P(≤12) mediana", "p48_sem_2013": "P(≤48) réplicas sem 2013", "p48_com_2013": "P(≤48) réplicas com 2013"},
         "relatorio_t14_bootstrap.csv", fmt={c: (lambda v: f(100 * v, 1, True)) for c in ["p48_mediana", "p48_p05", "p48_p95", "p12_mediana", "p48_sem_2013", "p48_com_2013"]}))
A("")
A(f"**B. Custo cambial dos swaps** (perda do BC com a variação do câmbio sobre o estoque de swaps, câmbio dos blocos históricos; calmaria com câmbio constante; "
  f"sem o diferencial de juros). PIB em R$ aproximado por PIB de 12 meses em US$ × câmbio de 30/06/2026 = R$ {f(e6['custo_swaps']['pib_rs_bi_aprox'], 0)} bi. "
  f"Referência: economia de juros de cerca de 4% do PIB ao ano alegada no 'Eu Acuso' = R$ {f(e6['custo_swaps']['economia_alegada_rs_bi_ano'], 0)} bi/ano.")
A("")
A(tabela(custo6[custo6.versao == "substituível"], {"persistencia": "Persistência", "horizonte_meses": "H", "custo_mediana_rs_bi": "Mediana (R$ bi)",
                                                   "custo_p10_rs_bi": "p10", "custo_p90_rs_bi": "p90", "custo_p90_pct_pib": "p90 (% PIB)",
                                                   "custo_p90_sobre_economia_alegada": "p90 / economia alegada no período", "deprec_mediana_pct": "Depreciação mediana (%)"},
         "relatorio_t15_custo_swaps.csv", fmt={"horizonte_meses": lambda v: f(int(v)), "custo_p90_pct_pib": lambda v: f(v, 2),
                                               "custo_p90_sobre_economia_alegada": lambda v: f(v, 2), "deprec_mediana_pct": lambda v: f(v, 1)}))
A("")
A("A pressão permanente reproduz episódios emendados por 4 anos e acumula depreciação irrealista (coluna da direita); use as linhas de episódio único e recorrente.")
A("")
cp = e6["capacidade_pct_pib"]
A(f"**C. Referência externa.** Base WPFXI do FMI (Adler, Chang, Mano e Shao), intervenção mensal estimada, 2000–2024. Episódio = meses seguidos de venda líquida "
  f"(lacunas de até 1 mês), com venda acumulada ≥ 0,5% do PIB. Capacidade utilizável do Brasil em % do PIB de 12 meses: {f(cp['100% ARA (utilizável)'])}% "
  f"(100% ARA); {f(cp['só espaço em swaps'])}% (só swaps); {f(cp['Greenspan-Guidotti'])}% (Greenspan-Guidotti). "
  "Grupo de comparação declarado: 18 emergentes com metas de inflação (lista em `etapa6_entradas.json`).")
A("")
A(tabela(ext6, {"grupo": "Grupo", "n_episodios": "Episódios", "n_paises": "Países", "tamanho_p50": "Tamanho p50 (% PIB)", "tamanho_p90": "p90",
                "meses_p50": "Meses p50", "meses_p90": "Meses p90", "prop_acima_100% ARA (utilizável)": "Acima da capacidade 100% ARA",
                "prop_acima_só espaço em swaps": "Acima do espaço em swaps", "prop_acima_Greenspan-Guidotti": "Acima da capacidade GG"},
         "relatorio_t16_externo.csv", fmt={"n_episodios": lambda v: f(int(v)), "n_paises": lambda v: f(int(v)),
                                           "meses_p50": lambda v: f(v, 0), "meses_p90": lambda v: f(v, 0),
                                           "prop_acima_100% ARA (utilizável)": lambda v: f(100 * v, 1, True), "prop_acima_só espaço em swaps": lambda v: f(100 * v, 1, True),
                                           "prop_acima_Greenspan-Guidotti": lambda v: f(100 * v, 1, True)}))
A("")
A("**Validação: episódios do Brasil na mesma base** (comparar com a seção 6):")
A("")
A(tabela(bra6, {"inicio": "Início", "fim": "Fim", "meses": "Meses", "venda_acumulada_pct_pib": "Venda acumulada (% PIB)", "maior_mes_pct_pib": "Maior mês (% PIB)"},
         fmt={"meses": lambda v: f(int(v))}))
A("")
A("**Maiores episódios do grupo de comparação.** Proxies incluem variações de reservas que não são intervenção (conversões de dívida, operações do governo); "
  "use a distribuição, não casos isolados.")
A("")
A(tabela(top6, {"pais": "País", "inicio": "Início", "fim": "Fim", "meses": "Meses", "venda_acumulada_pct_pib": "Venda acumulada (% PIB)", "maior_mes_pct_pib": "Maior mês (% PIB)"},
         fmt={"meses": lambda v: f(int(v))}))
A("")

# 8c Auditoria da segunda rodada
A("## 8c. Auditoria da segunda rodada (ChatGPT) — reprodução e diagnósticos")
A("")
sm_ = aud["simulacoes"]
A(f"O código `revisao.py` foi transcrito em `03_Codigo/auditoria/reproducao_gpt_revisao.py` e rodado sobre as mesmas bases. Os números saem iguais: "
  f"modo Markov, λ = 1, substituição 0,5 → P(≤12) = {f(sm_['markov_lam1_sub0.5']['primeira_falha'][0], 1)}%, P(≤48) = {f(sm_['markov_lam1_sub0.5']['primeira_falha'][2], 1)}%, "
  f"mediana {sm_['markov_lam1_sub0.5']['primeira_falha'][3]} meses (o ChatGPT reportou 20,3%, 57,5% e 37). Regimes: percentil 80 da depreciação mensal "
  f"({f(aud['limiar_p80_dep'], 2)}% log), matriz de transição {aud['matriz_transicao']}.")
A("")
diag = pd.DataFrame([{"cenario": k, "p12": v["primeira_falha"][0], "p24": v["primeira_falha"][1], "p48": v["primeira_falha"][2], "mediana": str(v["primeira_falha"][3]),
                      "piso48": v["reservas_no_piso"][2], "compras": v["compras_medias_48m_usd_bi"]} for k, v in sm_.items()])
A(tabela(diag, {"cenario": "Cenário", "p12": "P(≤12) %", "p24": "P(≤24) %", "p48": "P(≤48) %", "mediana": "Mediana", "piso48": "Reservas no piso ≤48 (%)",
                "compras": "Compras médias em 48 m (US$ bi)"}, "auditoria_gpt_diagnosticos.csv",
         fmt={"p12": lambda v: f(v, 1), "p24": lambda v: f(v, 1), "p48": lambda v: f(v, 1), "piso48": lambda v: f(v, 1), "compras": lambda v: f(v, 2)}))
A("")
A(f"Leitura: (i) substituição 0,5 e 0 dão a mesma primeira falha — a 'substituição parcial' equivale a não substituir nessa medida; "
  f"(ii) nos meses 'normais' o modelo compra em média US$ {f(sm_['markov_lam1_sub0.5']['compras_medias_48m_usd_bi'], 1)} bi de reservas em 48 meses; "
  f"{f(aud['compras_normais_2006_2012_pct'], 1)}% das compras dos meses normais de 2004–2026 são de 2006–2012; sem essas compras, P(≤48) sobe para "
  f"{f(sm_['markov_D2_sem_compras_normais']['primeira_falha'][2], 1)}% e as reservas tocam o piso em {f(sm_['markov_D2_sem_compras_normais']['reservas_no_piso'][2], 1)}% "
  "das trajetórias; (iii) os meses 'normais' também contêm os leilões do programa de 2013–2015, que consomem o teto de swaps — a classificação por "
  "depreciação não separa estados de demanda por intervenção.")
A("")

# 9 Etapa 4
A("## 9. Etapa 4 — Cenários institucionais")
A("")
b4, c4 = e4["cenario_b"], e4["cenario_c"]
A(f"**(b) Conversão das exportações (lei nova), v3.1.** Razão entre câmbio contratado de exportação (SGS 13962) e exportações de bens (SGS 22708), mesmos meses: "
  f"norma de 2009–2018 = {f(100 * conv_b['norma_conversao_2009_2018'], 1, True)}. Excesso retido = (norma − razão) × exportações: US$ {f(conv_b['excesso_2021_2025_usd_bi'], 1)} bi em 2021–2025, "
  f"US$ {f(conv_b['fluxo_mensal_medio_2021_2025_usd_bi'])} bi por mês. É teto: a diferença inclui pagamentos feitos no exterior e descasamento de datas. "
  f"Fluxo do cenário = f × {f(conv_b['fluxo_mensal_medio_2021_2025_usd_bi'])} bi/mês a partir de m_b. f = 0 (lei não passa), 0,5 (recuo observado em 2024: "
  f"{f(100 * conv_b['recuo_observado_2024']['fracao_revertida'], 1, True)} do excesso de 2023), 1 (volta à norma). {b4['requisito_legal']}. "
  f"Comparação: estoque implícito na afirmação de Lara Resende (US$ {f(b4['estoque_implicito_minimo_usd_bi'])} bi; {b4['fonte']}), entrada única no mês 12.")
A("")
A(tabela(conv_tab[conv_tab.ano >= 2009], {"ano": "Ano", "cambio_exportacao_usd_bi": "Câmbio contratado exportação", "exportacao_bens_bp_usd_bi": "Exportações de bens (BP)",
                                          "meses": "Meses", "razao_conversao": "Razão", "excesso_retido_usd_bi": "Excesso retido (US$ bi)"},
         "relatorio_t9b_conversao_exportacoes.csv", fmt={"ano": lambda v: str(int(v)), "meses": lambda v: f(int(v)), "razao_conversao": lambda v: f(100 * v, 1, True)}))
A("")
A(f"**(c) Desindexação das LFTs.** Participação das LFTs na DPMFi em mercado em {c4['mes']}: {f(100 * c4['participacao_lft_data_ref'], 2, True)} ({c4['fonte_atual']}); "
  f"alvo {f(100 * c4['participacao_alvo'], 0, True)} ({c4['fonte_alvo']}); δ_max = {f(c4['delta_max'], 4)}. λ × (1 − δ) a partir do mês {c4['mes_inicio']}.")
A("")
sel4 = mc4[(mc4.piso == P100) & (mc4.medida == "T_F")]
A(f"Piso {P100}, T_F. Tabela completa (todos os pisos e medidas): `tabelas/etapa4_cenarios_resultados.csv`.")
A("")
A(tabela(sel4.sort_values(["cenario", "lambda", "versao", "f", "mes_entrada", "delta", "horizonte_meses"]),
         {"cenario": "Cenário", "lambda": "λ", "versao": "Versão", "f": "f", "mes_entrada": "Mês entrada", "aporte_usd_bi": "Aporte (US$ bi; por mês no fluxo)",
          "delta": "δ", "horizonte_meses": "H", "p_esgotar_ate_H": "P(esgotar ≤ H)", "mediana_entre_esgotadas": "Mediana",
          "p10_entre_esgotadas": "p10", "p90_entre_esgotadas": "p90"},
         "relatorio_t9_cenarios.csv",
         fmt={"lambda": lambda v: f(v, 1), "f": lambda v: f(v, 2), "mes_entrada": lambda v: "—" if pd.isna(v) else f(int(v)),
              "delta": lambda v: f(v, 4), "horizonte_meses": lambda v: f(int(v)), "p_esgotar_ate_H": lambda v: f(100 * v, 1, True),
              "mediana_entre_esgotadas": lambda v: f(v, 1), "p10_entre_esgotadas": lambda v: f(v, 1), "p90_entre_esgotadas": lambda v: f(v, 1)}))
A("")

# 10 Hipóteses
A("## 10. Hipóteses e parâmetros")
A("")
hip = [
    ["λ (intensidade)", "0,5; 1,0 (alívio) | 1,5; 2,0 (perda de credibilidade)", "hipótese", P["regimes_premio_risco"]["justificativa"], "parametros.yaml"],
    ["π (prob. mensal de corrida)", "0; 0,02; 0,05", "hipótese", P["corrida"]["justificativa"] + " " + P["corrida"]["escopo"], "parametros.yaml"],
    ["k (duração da corrida)", f"{e3['k_corrida']} meses", "calculado", "episódio histórico mais longo em blocos", "etapa 2"],
    ["f (fração do excesso retido que volta)", "0; 0,5; 1", "hipótese ancorada em dado", P["cenario_b_exportadores"]["fracao_f_justificativa"], "parametros.yaml + etapa 0b"],
    ["m_b (mês de entrada do fluxo)", "6; 12; 24", "hipótese", P["cenario_b_exportadores"]["mes_entrada_justificativa"], "parametros.yaml"],
    ["δ (redução da pressão pós-desindexação)", f"{f(0.5 * c4['delta_max'], 4)}; {f(c4['delta_max'], 4)}", "hipótese ancorada em dado",
     "δ_max = 1 − alvo/participação atual das LFTs", "Tesouro + De Bolle p. 8"],
    ["Horizontes", "12, 24, 36, 48 meses", "parâmetro da proposta", "'Eu Acuso' (25/09/2026), seção 'Uma proposta para o Brasil': Selic 'perto de 7,5%' em 'cerca de 12 meses', plano de 4 a 5 anos; nota de 16/11, p. 3: 2–4 anos", "Substack de Lara Resende"],
    ["Taxa de episódios (v3)", "0 (único); 0,25/ano; 0,50/ano", "hipótese ancorada", P["v3_persistencia"]["taxas_episodios_por_ano"].__repr__() + " — 7 episódios em 2002–2026 (~0,29/ano)", "parametros.yaml"],
    ["Calmaria (v3)", "demanda zero", "hipótese", "compras de 2006–2012 dependeram de entrada de capitais com juro alto; variantes na seção 8b-E", "parametros.yaml"],
    ["Tetos de swaps (v3)", ", ".join(f"{f(v, 1)}" for v in tet.valor_usd_bi), "dado / calculado / hipótese", "pico; escalado por PIB e reservas; +25% e +50% ilustrativos", "etapa 1"],
    ["Pisos", "100%, 120%, 150% ARA; Greenspan-Guidotti", "metodologia", "FMI Guidance Note p. 25 (faixa 100–150%)", "PDF na bibliografia"],
    ["S_max (teto de swaps)", f"US$ {f(r1['swap_max_usd_bi'])} bi ({r1['swap_max_data']})", "dado observado", "pico do estoque; igual ao da série oficial SGS 29723", "etapa 1"],
    ["Especificação da ARA", AG, "calculado", "regra v3 em dois passos (nível da moeda ampla vs FMI; erro da razão)", "etapa 1"],
    ["1 mês = 20 dias úteis", "—", "aproximação", "blocos de 20 dias úteis (média ≈ 21 dias úteis/mês)", "metodologia"],
]
A(tabela(pd.DataFrame(hip, columns=["nome", "valor", "tipo", "justificativa", "origem"]),
         {"nome": "Parâmetro", "valor": "Valor", "tipo": "Tipo", "justificativa": "Justificativa", "origem": "Origem"}))
A("")

# 11 Limitações
A("## 11. Limitações e alertas")
A("")
for t in [
    "Etapas 3 e 4 supõem pressão permanente (episódios emendados). A etapa 5 relaxa isso com episódios inteiros e calmaria; a taxa de chegada de episódios sob a política é hipótese, não estimativa.",
    "A lista de episódios é ancorada em eventos conhecidos; a varredura de janelas de 20 d.u. fora da lista encontrou 2018 (incluído) e janelas menores em jan/2021, mar/2021 e dez/2021–jan/2022 (não incluídas: desmonte do overhedge e saídas sazonais de fim de ano).",
    "Razões do FMI de 2022 em diante são estimativas do FMI (DataMapper).",
    f"A especificação ({AG}) combina documento (definições da Guidance Note e Tabela 4 do Artigo IV) e calibração; a inclusão da intercompanhia em OL segue o cálculo mecânico OL = PIL + OIL − DCP.",
    f"DCP de 2025-12 e 2026-06 usa aproximação que superestimou a parcela de longo prazo em {f(float(val.dif_pct.mean()))}% em média nos anos de validação (efeito ≈ US$ {f(0.15 * vies)} bi na ARA).",
    "A base de atuações não registra cancelamentos nem liquidações antecipadas (documentação do BCB); mesmo assim, o estoque reconstruído coincide com a série oficial SGS 29723 em 6.300 de 6.301 dias.",
    "Datas de referência dos arquivos do setor externo de 2019–2020 foram inferidas pela regra observada nos demais (abril → 31/12 do ano anterior; outubro → 30/06).",
    "PII de 2018 não foi lida (cabeçalho diferente nos arquivos de 2019); a ARA recalculada começa em 2019.",
    "EMBI+ descontinuado em 30/07/2024; sem risco-país para dez/2024.",
    "Custo dos swaps no resultado do BC não estimado (sem série oficial localizada), conforme a regra de não aproximar.",
    "λ é aplicado igualmente a todos os instrumentos de um bloco; a composição do gasto (à vista, linha, swap) segue a do episódio sorteado.",
    "O estudo é descritivo e de sensibilidade: não mede efeito causal do corte de juros sobre o câmbio nem sobre a demanda por dólares.",
]:
    A(f"- {t}")
A("")

# 12 Pendências
A("## 12. Pendências")
A("")
for t in [
    "**Resolvido na v3:** estoque oficial de swaps (SGS 29723) e de linhas (SGS 29722); fluxo cambial contratado (SGS 13961, 13967, 13970, desde 09/2008); surpresas do Copom (Focus por reunião); texto original do 'Eu Acuso'.",
    "**VIX, Fed funds, dólar amplo (FRED):** acesso bloqueado neste ambiente; eram só contexto.",
    "**Risco-país em dez/2024:** buscar fonte alternativa ao EMBI+ (ex.: CDS de 5 anos), se Pedro tiver acesso.",
    "**Recursos de exportadores no exterior:** sem série oficial; o cenário (b) usa afirmação de terceiro (a nota de 16/11; o 'Eu Acuso' não traz esse número).",
    "**ARA dinâmica:** implementada como sensibilidade (bloco G). Pendente: câmbio na calmaria (hoje constante) e revalorização dos passivos em reais.",
    "**Lado fiscal:** fora do artigo por decisão (24/11/2026); se voltar, precisa de módulo próprio com parâmetros da IFI e do Tesouro.",
    "**Confirmar as grades de hipótese** (λ, π, f, m_b, δ) antes da versão final.",
]:
    A(f"- {t}")
A("")

# 13 Arquivos
A("## 13. Arquivos gerados")
A("")
arqs = sorted([*TABELAS.glob("*"), *FIGURAS.glob("*"), *TRATADOS.glob("*")])
A("| Arquivo | Tamanho (KB) |")
A("| --- | --- |")
for a in arqs:
    A(f"| `{a.relative_to(RESULTADOS.parent)}` | {f(a.stat().st_size / 1024, 1)} |")
A("")

texto = "\n".join(L)
(RESULTADOS / "RELATORIO_RESULTADOS.md").write_text(texto, encoding="utf-8")
shutil.copy(RESULTADOS / "RELATORIO_RESULTADOS.md", RESULTADOS / "historico" / f"RELATORIO_RESULTADOS_{agora:%Y-%m-%d_%H%M}.md")
print(f"Relatório: {len(texto)} caracteres, {len(L)} linhas.")
print(verif[["verificacao", "valor_referencia", "valor_obtido", "dif_pct", "status"]].to_string())
