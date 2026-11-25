"""Etapa 2 — Episódios de estresse (descritivo) e blocos de 20 dias úteis (CLAUDE.md, seção 6.2)."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import FIGURAS, TABELAS, TRATADOS, log, salvar_json  # noqa: E402

at = pd.read_csv(TRATADOS / "atuacoes_cambio.csv", parse_dates=["data", "data_liquidacao", "data_vencimento"])
res = pd.read_csv(TRATADOS / "reservas_diarias.csv", parse_dates=["data"]).set_index("data")["reservas_usd_bi"]
cam = pd.read_csv(TRATADOS / "cambio_diario.csv", parse_dates=["data"]).set_index("data")["cambio_brl_usd"]
est = pd.read_csv(TRATADOS / "estoques_swap_linha_diario.csv", parse_dates=["data"]).set_index("data")
embi = pd.read_csv(TRATADOS / "embi_diario.csv", parse_dates=["data"]).set_index("data")["embi_pb"]

# Dias úteis = datas com cotação de câmbio publicada (SGS 1)
DU = cam.index
v = at["volume_aceito_usd_bi"].fillna(0)

# ---------------------------------------------------------------- oferta diária de dólares pelo BC, por instrumento
def por_dia(mask, col_data, sinal=1.0):
    s = (sinal * v[mask]).groupby(at.loc[mask, col_data]).sum()
    return s.reindex(DU, fill_value=0.0) if len(s) else pd.Series(0.0, index=DU)


def alinhar(s: pd.Series) -> pd.Series:
    """Move eventos em datas não úteis para o dia útil seguinte e reindexa nos dias úteis."""
    s = s.groupby(level=0).sum()
    idx = DU.searchsorted(s.index)
    ok = idx < len(DU)
    out = pd.Series(0.0, index=DU)
    np.add.at(out.values, idx[ok], s.values[ok])
    return out


ins = at["instrumento"]
avista = alinhar(pd.concat([
    v[ins == "Venda a Vista"].groupby(at.loc[ins == "Venda a Vista", "data"]).sum(),
    -v[ins.isin(["Compra a Vista", "Compra a Termo"])].groupby(at.loc[ins.isin(["Compra a Vista", "Compra a Termo"]), "data"]).sum(),
]))
m_linha = ins == "Venda com Recompra"
linha_venda = alinhar(v[m_linha].groupby(at.loc[m_linha, "data"]).sum())
linha_recompra = alinhar(v[m_linha & at["data_vencimento"].notna()].groupby(at.loc[m_linha & at["data_vencimento"].notna(), "data_vencimento"]).sum())
m_outros = ins.isin(["Empréstimo", "Operação Compromissada"])
outros_ida = alinhar(v[m_outros].groupby(at.loc[m_outros, "data"]).sum()) if m_outros.any() else pd.Series(0.0, index=DU)
outros_volta = alinhar(v[m_outros & at["data_vencimento"].notna()].groupby(at.loc[m_outros & at["data_vencimento"].notna(), "data_vencimento"]).sum()) if m_outros.any() else pd.Series(0.0, index=DU)
sw_estoque = est["swap_liquido_usd_bi"].reindex(DU, method="ffill").fillna(0)
swap_var = sw_estoque.diff().fillna(0)
# swaps: também volumes brutos novos (para separar rolagem)
m_swt = (ins == "Swap Cambial") & (at["modalidade"] == "Tradicional")
swap_bruto_novo = alinhar(v[m_swt].groupby(at.loc[m_swt, "data"]).sum())

diario = pd.DataFrame({
    "avista_liquido": avista,
    "linha_venda": linha_venda, "linha_recompra": linha_recompra,
    "linha_liquido": linha_venda - linha_recompra,
    "outros_liquido": outros_ida - outros_volta, "outros_ida": outros_ida,
    "swap_var_estoque": swap_var, "swap_tradicional_bruto": swap_bruto_novo,
})
diario["oferta_liquida_total"] = diario[["avista_liquido", "linha_liquido", "outros_liquido", "swap_var_estoque"]].sum(axis=1)
diario.to_csv(TABELAS / "etapa2_oferta_diaria_bc.csv", index_label="data")

semanal = diario.resample("W-FRI").sum()

# ---------------------------------------------------------------- episódios
EPISODIOS = [
    # nome, âncora, como a âncora foi definida
    ("2002", ("max_cambio", "2002-01-01", "2002-12-31"), "data do câmbio máximo em 2002 (crise de confiança pré-eleitoral)"),
    ("2008", ("max_cambio", "2008-09-01", "2008-12-31"), "data do câmbio máximo em set–dez/2008 (crise financeira global)"),
    ("2013", ("data", "2013-08-22"), "anúncio do programa de swaps (22/08/2013)"),
    ("2015", ("max_cambio", "2015-01-01", "2015-12-31"), "data do câmbio máximo em 2015 (deterioração fiscal e rebaixamentos)"),
    ("mar/2020", ("max_cambio", "2020-03-01", "2020-03-31"), "data do câmbio máximo em mar/2020 (choque da pandemia)"),
    ("dez/2024", ("data", "2024-12-12"), "início dos leilões em 12/12/2024"),
]


def ancora(defn):
    if defn[0] == "data":
        return pd.Timestamp(defn[1])
    s = cam.loc[defn[1]:defn[2]]
    return s.idxmax()


def janela_episodio(anc: pd.Timestamp, serie=semanal["oferta_liquida_total"], gap_max=2, busca=4):
    sem = serie.index
    i = sem.searchsorted(anc)
    pos = serie.values > 1e-9
    # se a semana da âncora não tem oferta positiva, procurar a mais próxima com oferta positiva (±busca semanas)
    if not pos[i]:
        cand = [j for d in range(1, busca + 1) for j in (i - d, i + d) if 0 <= j < len(pos) and pos[j]]
        if not cand:
            return None
        i = cand[0]
    ini = fim = i
    while True:  # expandir para trás juntando lacunas de até gap_max semanas
        j = ini - 1
        lac = 0
        while j >= 0 and not pos[j] and lac < gap_max:
            j -= 1
            lac += 1
        if j >= 0 and pos[j] and lac <= gap_max:
            ini = j
        else:
            break
    while True:
        j = fim + 1
        lac = 0
        while j < len(pos) and not pos[j] and lac < gap_max:
            j += 1
            lac += 1
        if j < len(pos) and pos[j] and lac <= gap_max:
            fim = j
        else:
            break
    d_ini = sem[ini] - pd.Timedelta(days=6)
    d_fim = sem[fim]
    du = DU[(DU >= d_ini) & (DU <= d_fim)]
    return du[0], du[-1], fim - ini + 1


def valor_em(s, d, depois=False):
    s = s.dropna()
    if depois:
        x = s.loc[d:]
        return (x.index[0], float(x.iloc[0])) if len(x) else (None, np.nan)
    x = s.loc[:d]
    return (x.index[-1], float(x.iloc[-1])) if len(x) else (None, np.nan)


linhas, blocos = [], []
for nome, defn, desc in EPISODIOS:
    anc = ancora(defn)
    jan = janela_episodio(anc)
    if jan is None:
        linhas.append({"episodio": nome, "ancora": anc.date(), "regra_ancora": desc, "observacao": "sem oferta líquida positiva perto da âncora"})
        continue
    ini, fim, nsem = jan
    d = diario.loc[ini:fim]
    du = len(d)
    r_ini_d, r_ini = valor_em(res, ini - pd.Timedelta(days=1))
    r_fim_d, r_fim = valor_em(res, fim)
    c_ini_d, c_ini = valor_em(cam, ini - pd.Timedelta(days=1))
    c_fim_d, c_fim = valor_em(cam, fim)
    c_max = float(cam.loc[ini:fim].max())
    e_ini_d, e_ini = valor_em(embi, ini - pd.Timedelta(days=1))
    e_fim_d, e_fim = valor_em(embi, fim)
    e_pico = float(embi.loc[ini:fim].max()) if len(embi.loc[ini:fim]) else np.nan
    mask_l = m_linha & (at["data"] >= ini) & (at["data"] <= fim)
    prazo_linha = (at.loc[mask_l, "data_vencimento"] - at.loc[mask_l, "data_liquidacao"]).dt.days
    deprec = 100 * (c_fim / c_ini - 1)
    gasto = float(d["oferta_liquida_total"].sum())
    embi_disp = not np.isnan(e_ini) and e_ini_d is not None and (ini - e_ini_d).days < 10
    linhas.append({
        "episodio": nome, "ancora": anc.date(), "regra_ancora": desc, "inicio": ini.date(), "fim": fim.date(),
        "dias_uteis": du, "semanas": nsem,
        "venda_avista_liquida_usd_bi": float(d["avista_liquido"].sum()),
        "linha_vendas_brutas_usd_bi": float(d["linha_venda"].sum()), "linha_recompras_usd_bi": float(d["linha_recompra"].sum()),
        "linha_liquida_usd_bi": float(d["linha_liquido"].sum()),
        "swap_tradicional_bruto_usd_bi": float(d["swap_tradicional_bruto"].sum()),
        "swap_var_estoque_liquido_usd_bi": float(d["swap_var_estoque"].sum()),
        "swap_rolado_aprox_usd_bi": float(d["swap_tradicional_bruto"].sum() - max(d["swap_var_estoque"].sum(), 0)),
        "emprestimos_compromissadas_liquido_usd_bi": float(d["outros_liquido"].sum()),
        "oferta_liquida_total_usd_bi": gasto,
        "reservas_inicio_usd_bi": r_ini, "reservas_inicio_data": r_ini_d.date() if r_ini_d is not None else None,
        "reservas_fim_usd_bi": r_fim, "reservas_fim_data": r_fim_d.date() if r_fim_d is not None else None,
        "reservas_variacao_usd_bi": r_fim - r_ini,
        "cambio_inicio": c_ini, "cambio_fim": c_fim, "cambio_variacao_pct": deprec,
        "cambio_max_no_episodio": c_max, "maior_desvalorizacao_pct": 100 * (c_max / c_ini - 1),
        "embi_inicio_pb": e_ini if embi_disp else np.nan, "embi_fim_pb": e_fim if embi_disp else np.nan,
        "embi_pico_pb": e_pico if embi_disp else np.nan,
        "embi_disponivel": embi_disp,
        "gasto_por_pp_desvalorizacao_usd_bi": gasto / deprec if deprec > 0 else np.nan,
        "linha_prazo_medio_dias": float(prazo_linha.mean()) if len(prazo_linha) else np.nan,
        "linha_prazo_mediano_dias": float(prazo_linha.median()) if len(prazo_linha) else np.nan,
    })
    # blocos de 20 dias úteis não sobrepostos
    n = len(d)
    for b, k in enumerate(range(0, n, 20), start=1):
        sub = d.iloc[k:k + 20]
        nd = len(sub)
        if nd < 10:
            blocos.append({"episodio": nome, "bloco": b, "inicio": sub.index[0].date(), "fim": sub.index[-1].date(),
                           "dias_uteis": nd, "status": "descartado (<10 dias)"})
            continue
        f = 20 / nd
        blocos.append({
            "episodio": nome, "bloco": b, "inicio": sub.index[0].date(), "fim": sub.index[-1].date(), "dias_uteis": nd,
            "status": "reescalado" if nd < 20 else "completo", "fator_escala": f,
            "gasto_total_usd_bi": f * float(sub["oferta_liquida_total"].sum()),
            "avista_usd_bi": f * float(sub["avista_liquido"].sum()),
            "linha_usd_bi": f * float(sub["linha_liquido"].sum()),
            "swap_usd_bi": f * float(sub["swap_var_estoque"].sum()),
            "outros_usd_bi": f * float(sub["outros_liquido"].sum()),
            "linha_venda_bruta_usd_bi": f * float(sub["linha_venda"].sum()),
            "outros_ida_bruta_usd_bi": f * float(sub["outros_ida"].sum()),
            "linha_prazo_mediano_dias_episodio": float(prazo_linha.median()) if len(prazo_linha) else np.nan,
        })

ep = pd.DataFrame(linhas)
bl = pd.DataFrame(blocos)
ep.to_csv(TABELAS / "etapa2_episodios.csv", index=False)
bl.to_csv(TABELAS / "episodios_blocos.csv", index=False)

ok = bl[bl["status"] != "descartado (<10 dias)"]
g = ok["gasto_total_usd_bi"]
ritmos = {
    "n_blocos_validos": int(len(ok)), "n_blocos_reescalados": int((ok.status == "reescalado").sum()),
    "n_blocos_descartados": int((bl.status == "descartado (<10 dias)").sum()),
    "moderado_mediana_usd_bi": float(g.median()), "forte_p75_usd_bi": float(g.quantile(.75)),
    "extremo_max_usd_bi": float(g.max()), "media_usd_bi": float(g.mean()), "desvio_padrao_usd_bi": float(g.std()),
    "minimo_usd_bi": float(g.min()),
    "por_episodio": ok.groupby("episodio")["gasto_total_usd_bi"].agg(["count", "mean", "median", "max", "std"]).round(4).to_dict("index"),
    "k_meses_episodio_mais_longo": int(ok.groupby("episodio").size().max()),
    "episodio_mais_longo": ok.groupby("episodio").size().idxmax(),
}
salvar_json(ritmos, TABELAS / "etapa2_ritmos.json")

# figura: oferta semanal e câmbio por episódio
fig, axes = plt.subplots(3, 2, figsize=(12, 10))
for ax, (_, r) in zip(axes.flat, ep.dropna(subset=["inicio"]).iterrows()):
    a, b = pd.Timestamp(r.inicio) - pd.Timedelta(days=60), pd.Timestamp(r.fim) + pd.Timedelta(days=60)
    w = semanal.loc[a:b]
    ax.bar(w.index, w["avista_liquido"], width=5, color="#1f3a5f", label="à vista")
    ax.bar(w.index, w["linha_liquido"], width=5, bottom=w["avista_liquido"], color="#7fa7d9", label="linha")
    ax.bar(w.index, w["swap_var_estoque"], width=5, bottom=w["avista_liquido"] + w["linha_liquido"], color="#e67e22", label="swap (var. estoque)")
    ax.axvspan(pd.Timestamp(r.inicio), pd.Timestamp(r.fim), color="grey", alpha=.12)
    ax.set_title(f"{r.episodio}: {r.inicio} a {r.fim}", fontsize=9)
    ax.set_ylabel("US$ bi por semana", fontsize=8)
    ax2 = ax.twinx()
    ax2.plot(cam.loc[a:b].index, cam.loc[a:b].values, color="#c0392b", lw=1)
    ax2.set_ylabel("R$/US$", fontsize=8, color="#c0392b")
    ax.tick_params(labelsize=7)
    ax2.tick_params(labelsize=7)
axes.flat[0].legend(fontsize=7)
fig.suptitle("Oferta líquida semanal de dólares pelo BC nos episódios de estresse (área cinza) e câmbio")
fig.text(0.01, 0.005, "Fonte: BCB, base de atuações no câmbio e SGS 1. Acesso: 23/11/2026. Descritivo; não indica efeito causal.", fontsize=7)
fig.tight_layout(rect=(0, 0.02, 1, 0.97))
fig.savefig(FIGURAS / "etapa2_episodios.png", dpi=300)

log("Etapa 2 concluída.")
pd.set_option("display.width", 250)
print(ep[["episodio", "ancora", "inicio", "fim", "dias_uteis", "venda_avista_liquida_usd_bi", "linha_liquida_usd_bi", "swap_var_estoque_liquido_usd_bi",
          "oferta_liquida_total_usd_bi", "reservas_variacao_usd_bi", "cambio_variacao_pct", "embi_disponivel"]].round(2).to_string())
print(bl.round(2).to_string())
print({k: v for k, v in ritmos.items() if k != "por_episodio"})
