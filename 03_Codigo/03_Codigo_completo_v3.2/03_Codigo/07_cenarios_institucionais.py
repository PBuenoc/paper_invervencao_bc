
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import CONFIG, TABELAS, TRATADOS, log, salvar_json  # noqa: E402
from src.simulacao import Blocos  # noqa: E402

spec = importlib.util.spec_from_file_location("mc", Path(__file__).parent / "06_montecarlo.py")
mc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mc)

P = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
HMAX = mc.HMAX

b = Blocos.de_tabela(pd.read_csv(TABELAS / "episodios_blocos.csv"))
ent = mc.entradas()
lambdas = [("alívio fiscal", l) for l in P["regimes_premio_risco"]["alivio_fiscal"]["lambda"]] + \
          [("perda de credibilidade", l) for l in P["regimes_premio_risco"]["perda_credibilidade"]["lambda"]]

# (b) dólares de exportadores — sem série oficial: valor mínimo implícito na afirmação de Lara Resende
res = pd.read_csv(TRATADOS / "reservas_diarias.csv", parse_dates=["data"]).set_index("data")["reservas_usd_bi"]
data_afirm = pd.Timestamp("2026-11-16")
r_afirm = float(res.loc[:data_afirm].iloc[-1])
d_r_afirm = res.loc[:data_afirm].index[-1].date().isoformat()
estoque_exp = 400.0 - r_afirm
conv = json.loads((TABELAS / "cenario_b_conversao_exportacoes.json").read_text(encoding="utf-8"))
fluxo_b = conv["fluxo_mensal_medio_2021_2025_usd_bi"]  # excesso retido médio por mês, 2021–2025 (dado)

# (c) desindexação — participação das LFTs na data de referência (Tesouro)
lft = pd.read_csv(TRATADOS / "tesouro_participacao_lft.csv", parse_dates=["mes"]).set_index("mes")
dref = pd.Timestamp(ent["data_ref"])
mes_ref = pd.Timestamp(dref.year, dref.month, 1)
part_atual = float(lft.loc[mes_ref, "participacao_lft"])
alvo = P["cenario_c_desindexacao"]["participacao_alvo_lft"]
delta_max = 1 - alvo / part_atual
mes_ini_c = P["cenario_c_desindexacao"]["mes_inicio"]

linhas = []
for regime, lam in lambdas:
    base = {"etapa": 4, "regime": regime, "lambda": lam, "pi_corrida": 0.0}
    for f in P["cenario_b_exportadores"]["fracao_f"]:
        for mb in P["cenario_b_exportadores"]["mes_entrada_m_b"]:
            extra = np.zeros(HMAX)
            extra[mb - 1:] = f * fluxo_b
            cen = {**base, "cenario": "b) conversão das exportações (lei nova, fluxo)", "f": f, "mes_entrada": mb,
                   "aporte_usd_bi": f * fluxo_b, "aporte_tipo": "fluxo mensal"}
            linhas += mc.rodar(b, ent, cen, lambda: np.full(HMAX, lam), entradas_extra=extra)
    for f in (0.5, 1.0):  # comparação: estoque implícito na afirmação de Lara Resende, entrada única no mês 12
        cen = {**base, "cenario": "b') estoque implícito (comparação)", "f": f, "mes_entrada": 12,
               "aporte_usd_bi": f * estoque_exp, "aporte_tipo": "entrada única"}
        linhas += mc.rodar(b, ent, cen, lambda: np.full(HMAX, lam), aporte=(12, f * estoque_exp))
    for frac in P["cenario_c_desindexacao"]["delta_fracoes_de_max"]:
        delta = frac * delta_max
        cen = {**base, "cenario": "c) desindexação das LFTs (De Bolle)", "delta": delta, "delta_frac_max": frac}

        def lamvec(lam=lam, delta=delta):
            v = np.full(HMAX, lam)
            v[mes_ini_c - 1:] = lam * (1 - delta)
            return v
        linhas += mc.rodar(b, ent, cen, lamvec, horizontes=[h for h in mc.HS if h >= 24])

df = pd.DataFrame(linhas)
df.to_csv(TABELAS / "etapa4_cenarios_resultados.csv", index=False)
salvar_json({"cenario_b": {"natureza": "fluxo ancorado em dado (conversão das exportações); estoque de terceiro só como comparação",
                           "fluxo_mensal_usd_bi": fluxo_b, "conversao": conv,
                           "fonte": "Lara Resende (16/11/2026), p. 4–5: reservas + dólares de exportadores no exterior > US$ 400 bi",
                           "reservas_na_data_da_afirmacao_usd_bi": r_afirm, "data_reservas": d_r_afirm,
                           "estoque_implicito_minimo_usd_bi": estoque_exp,
                           "requisito_legal": "Lei 14.286/2021, art. 26: manutenção no exterior é facultativa; exige lei nova"},
             "cenario_c": {"participacao_lft_data_ref": part_atual, "mes": mes_ref.date().isoformat(), "fonte_atual": "Tesouro, estoque da DPF (DPMFi em mercado)",
                           "participacao_alvo": alvo, "fonte_alvo": "De Bolle (16/11/2026), p. 8", "delta_max": delta_max,
                           "mes_inicio": mes_ini_c}},
            TABELAS / "etapa4_entradas.json")
log(f"Etapa 4 concluída: {len(df)} linhas. Estoque exportadores implícito = {estoque_exp:.2f}; δ_max = {delta_max:.4f}")
p100 = [k for k in ent["pisos"] if k.startswith("100% ARA (M") and "sensib" not in k][0]
sel = df[(df.piso == p100) & (df.medida == "T_F") & (df.versao == "substituível") & (df["lambda"] == 1.0)]
pd.set_option("display.width", 250)
print(sel[["cenario", "f", "mes_entrada", "delta", "horizonte_meses", "p_esgotar_ate_H", "mediana_entre_esgotadas", "p10_entre_esgotadas",
           "p90_entre_esgotadas"]].round(3).to_string())
