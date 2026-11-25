
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import BRUTOS, TABELAS, TRATADOS, log, salvar_json  # noqa: E402

if __name__ == "__main__":
    f = sorted(BRUTOS.glob("BCB-Olinda_Focus_ExpectativasMercadoSelic_*.json"))[-1]
    fo = pd.DataFrame([r for v in json.loads(f.read_text(encoding="utf-8"))["anos"].values() for r in v])
    fo["Data"] = pd.to_datetime(fo["Data"])
    fo[["k", "ano"]] = fo["Reuniao"].str.extract(r"R(\d+)/(\d{4})").astype(int)
    ev = pd.read_csv(TABELAS / "etapa2b_eventos_copom.csv", parse_dates=["data_reuniao"])
    ordi = ev[~ev.extraordinaria.astype(bool)].copy()
    ordi["ano"] = ordi.data_reuniao.dt.year
    ordi["k"] = ordi.groupby("ano").data_reuniao.rank(method="first").astype(int)
    # checagem: nº de reuniões ordinárias por ano no Copom x maior k observado no Focus para o ano
    nk = ordi.groupby("ano").k.max()
    fk = fo.groupby("ano").k.max()
    chk = pd.concat([nk.rename("reunioes_copom"), fk.rename("max_k_focus")], axis=1).dropna()
    linhas = []
    for _, r in ordi.iterrows():
        sub = fo[(fo.ano == r.ano) & (fo.k == r.k) & (fo.Data < r.data_reuniao)]
        if sub.empty:
            continue
        ult = sub[sub.Data == sub.Data.max()].iloc[0]
        linhas.append({"data_reuniao": r.data_reuniao.date(), "reuniao_focus": f"R{r.k}/{r.ano}", "data_pesquisa": ult.Data.date(),
                       "dias_antes": (r.data_reuniao - ult.Data).days, "mediana_focus": ult.Mediana, "media_focus": ult.Media,
                       "respondentes": ult.numeroRespondentes, "meta_anterior": r.meta_anterior, "meta_nova": r.meta_nova,
                       "mudanca_pp": r.mudanca_pp, "esperada_pp": ult.Mediana - r.meta_anterior, "surpresa_pp": r.meta_nova - ult.Mediana,
                       "variacao_cambio_pct": r.variacao_cambio_pct})
    s = pd.DataFrame(linhas)
    s.to_csv(TRATADOS / "copom_surpresas_focus.csv", index=False)
    # amostra: pesquisa até 10 dias antes (garante que a expectativa é da véspera, não de meses antes)
    a = s[s.dias_antes <= 10].copy()
    a["selic_baixa"] = (a.meta_anterior < 10).astype(int)
    a["surpresa_x_baixa"] = a.surpresa_pp * a.selic_baixa
    regs = []

    def ols(nome, y, X, amostra):
        m = sm.OLS(y, sm.add_constant(X)).fit(cov_type="HC1")
        for v in m.params.index:
            regs.append({"modelo": nome, "variavel": v, "coef": m.params[v], "ep_hc1": m.bse[v], "p": m.pvalues[v],
                         "ic95_inf": m.conf_int().loc[v, 0], "ic95_sup": m.conf_int().loc[v, 1], "n": int(m.nobs), "r2": m.rsquared,
                         "amostra": amostra})
        return m

    ols("M1 variação ~ surpresa", a.variacao_cambio_pct, a[["surpresa_pp"]], "todas as reuniões ordinárias com Focus")
    ols("M2 variação ~ mudança observada", a.variacao_cambio_pct, a[["mudanca_pp"]], "mesma amostra (comparação com a etapa 2b)")
    ols("M3 variação ~ esperada + surpresa", a.variacao_cambio_pct, a[["esperada_pp", "surpresa_pp"]], "mesma amostra")
    ols("M4 variação ~ surpresa × Selic<10%", a.variacao_cambio_pct, a[["surpresa_pp", "selic_baixa", "surpresa_x_baixa"]], "mesma amostra")
    nz = a[a.surpresa_pp.abs() > 1e-9]
    ols("M5 variação ~ surpresa (só reuniões com surpresa ≠ 0)", nz.variacao_cambio_pct, nz[["surpresa_pp"]], "surpresa diferente de zero")
    reg = pd.DataFrame(regs)
    reg.to_csv(TABELAS / "etapa2c_surpresas_regressoes.csv", index=False)
    cortes = a[a.mudanca_pp < 0]
    resumo = {"n_reunioes_com_focus": int(len(s)), "n_amostra_ate_10_dias": int(len(a)),
              "periodo": [str(a.data_reuniao.min()), str(a.data_reuniao.max())],
              "checagem_numeracao": chk.astype(int).to_dict("index"),
              "prop_reunioes_sem_surpresa": float((a.surpresa_pp.abs() < 1e-9).mean()),
              "surpresa_abs_media_pp": float(a.surpresa_pp.abs().mean()), "surpresa_max_pp": float(a.surpresa_pp.max()),
              "surpresa_min_pp": float(a.surpresa_pp.min()),
              "cortes": {"n": int(len(cortes)), "prop_antecipados_integralmente": float((cortes.surpresa_pp.abs() < 1e-9).mean()),
                         "esperada_media_pp": float(cortes.esperada_pp.mean()), "surpresa_media_pp": float(cortes.surpresa_pp.mean())},
              "maiores_surpresas": a.reindex(a.surpresa_pp.abs().sort_values(ascending=False).index).head(8)[
                  ["data_reuniao", "meta_anterior", "meta_nova", "mediana_focus", "surpresa_pp", "variacao_cambio_pct"]].astype(str).to_dict("records")}
    salvar_json(resumo, TABELAS / "etapa2c_resumo.json")
    log("Etapa 2c concluída.")
    pd.set_option("display.width", 250)
    print(reg.round(4).to_string())
    print(json.dumps({k: v for k, v in resumo.items() if k != "checagem_numeracao"}, ensure_ascii=False, indent=1, default=str))
    bad = {k: v for k, v in resumo["checagem_numeracao"].items() if v["reunioes_copom"] != v["max_k_focus"]}
    print("anos com numeração divergente:", bad)
