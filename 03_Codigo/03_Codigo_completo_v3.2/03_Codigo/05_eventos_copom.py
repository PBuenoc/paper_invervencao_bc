
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import TABELAS, TRATADOS, log, salvar_json  # noqa: E402

cop = pd.read_csv(TRATADOS / "copom_reunioes.csv", parse_dates=["data_reuniao", "inicio_vigencia"])
cam = pd.read_csv(TRATADOS / "cambio_diario.csv", parse_dates=["data"]).set_index("data")["cambio_brl_usd"].dropna()
DU = cam.index

# amostra: regime de metas de inflação / câmbio flutuante (a partir da 1ª meta Selic, mar/1999)
cop = cop[cop.data_reuniao >= "1999-03-01"].copy()
linhas = []
for _, r in cop.iterrows():
    d = r.data_reuniao
    pre = DU[DU <= d]
    pos = DU[DU > d]
    if not len(pre) or not len(pos):
        continue
    d0, d1 = pre[-1], pos[0]
    var = 100 * (cam[d1] / cam[d0] - 1)
    mud = r.mudanca_pp
    tipo = "manutenção" if abs(mud) < 1e-9 else ("corte" if mud < 0 else "alta")
    linhas.append({"reuniao": r.reuniao, "extraordinaria": r.ReuniaoExtraordinaria, "data_reuniao": d.date(),
                   "meta_anterior": r.meta_anterior, "meta_nova": r.meta_selic, "mudanca_pp": mud, "tipo": tipo,
                   "magnitude": "nenhuma" if tipo == "manutenção" else ("≤0,50 p.p." if abs(mud) <= 0.5 + 1e-9 else ">0,50 p.p."),
                   "regime_selic": "≥10%" if r.meta_anterior >= 10 else "<10%",
                   "dia_antes": d0.date(), "cambio_antes": cam[d0], "dia_depois": d1.date(), "cambio_depois": cam[d1],
                   "variacao_cambio_pct": var})
ev = pd.DataFrame(linhas)
ev.to_csv(TABELAS / "etapa2b_eventos_copom.csv", index=False)


def stats(g):
    x = g["variacao_cambio_pct"]
    return pd.Series({"n": len(x), "media_pct": x.mean(), "mediana_pct": x.median(), "desvio_pct": x.std(),
                      "min_pct": x.min(), "max_pct": x.max()})


grupos = []
for chave in (["tipo"], ["tipo", "magnitude"], ["tipo", "regime_selic"]):
    t = ev.groupby(chave).apply(stats, include_groups=False).reset_index()
    t.insert(0, "agrupamento", " × ".join(chave))
    grupos.append(t)
tab = pd.concat(grupos, ignore_index=True)
tab.to_csv(TABELAS / "etapa2b_estatisticas_copom.csv", index=False)

# resposta média por p.p. de corte, só como razão descritiva
cortes = ev[ev.tipo == "corte"]
razao = (cortes["variacao_cambio_pct"] / cortes["mudanca_pp"].abs())
ref_wps = {"fonte": "Vicente, Marins e Gaglianone (2021), BCB Working Paper 552",
           "arquivo": "01_Bibliografia/03_Working-Papers_Textos-para-Discussao/VicenteMarinsGaglianone_2021_BCB-WPS552.pdf",
           "estimativa": "surpresa de afrouxamento de 100 bp → depreciação de cerca de 3,4 p.p. (coeficiente −3,41, Modelo A, Tabela 1)",
           "paginas": "p. 8 e p. 14 do PDF",
           "ressalva": "com Selic de um dígito a surpresa não é significativa (Modelo C), com poucas observações (p. 15 do PDF)",
           "natureza": "surpresa medida por DI futuro; aqui usamos decisão bruta, que inclui a parte já esperada"}
resumo = {"n_decisoes": int(len(ev)), "periodo": [str(ev.data_reuniao.min()), str(ev.data_reuniao.max())],
          "n_cortes": int(len(cortes)), "var_media_por_pp_de_corte_pct": float(razao.mean()),
          "var_mediana_por_pp_de_corte_pct": float(razao.median()), "referencia_wps552": ref_wps,
          "surpresa_di": "não calculada: dados históricos de DI futuro da B3 não foram obtidos de forma pública e automatizável nesta rodada (pendência)"}
salvar_json(resumo, TABELAS / "etapa2b_resumo.json")
log("Etapa 2b concluída.")
print(tab.round(3).to_string())
print({k: v for k, v in resumo.items() if k != "referencia_wps552"})
