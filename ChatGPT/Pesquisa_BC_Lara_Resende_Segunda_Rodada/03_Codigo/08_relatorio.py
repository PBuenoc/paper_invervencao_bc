"""Monta 04_Resultados/RELATORIO_RESULTADOS.md a partir das tabelas salvas (CLAUDE.md, seção 9)."""
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
P100 = f"100% ARA ({AG})"

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
verif.append({"verificacao": "Estoque de swaps reconstruído × série oficial", "valor_referencia": np.nan, "fonte": "BCB",
              "valor_obtido": r1["swap_em_aberto_usd_bi"], "dif_abs": np.nan, "dif_pct": np.nan, "tolerancia_pct": np.nan,
              "status": "pendência", "obs": "série oficial diária de estoque não localizada em API pública; ver Pendências"})
soma = comp["contrib_exportacoes"] + comp[f"contrib_moeda_{AG.lower()}"] + comp["contrib_dcp"] + comp["contrib_outros_passivos"]
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
A("> **Status:** primeira rodada completa. As grades de hipótese (λ, π, f, δ) são as iniciais do `parametros.yaml` e "
  "**ainda precisam da confirmação do Pedro** antes da versão final. Nada aqui é efeito causal.")
A("")

# 1 Resumo
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
A("**Escolha do agregado monetário.** O agregado que melhor reproduz a razão publicada pelo FMI (2019–2025) foi escolhido como principal; os outros ficam como sensibilidade. "
  "A nota do FMI diz 'M2', mas o 'broad money' das estatísticas do FMI para o Brasil não coincide com o M2 do BCB.")
A("")
A(tabela(esc, {"agregado": "Agregado", "erro_abs_medio_pp": "Erro absoluto médio vs FMI (p.p.)", "anos_comparados": "Anos", "escolhido": "Escolhido"},
         fmt={"escolhido": lambda v: "sim" if v else "não"}))
A("")
cols_c = {"data_referencia": "Data", "reservas_usd_bi": "Reservas", "export_12m_usd_bi": "Export. 12m", f"{AG.lower()}_usd_bi": f"{AG} (US$)",
          "dcp_residual_usd_bi": "DCP residual", "pil_usd_bi": "Pass. carteira", "oil_usd_bi": "Outros invest.", "outros_passivos_usd_bi": "Outros passivos",
          "ara_recalculada_usd_bi": "ARA recalc.", "razao_recalculada": "Razão recalc.", "razao_fmi": "Razão FMI", "dif_razao_pp": "Dif. (p.p.)",
          "metodo_dcp": "Método DCP"}
A(f"**Componentes por data (US$ bi; agregado {AG}).** Razão FMI de 2022 em diante = estimativa do FMI.")
A("")
A(tabela(comp, cols_c, "relatorio_t5_componentes.csv", fmt={"razao_recalculada": lambda v: f(v, 3), "razao_fmi": lambda v: f(v, 3)}))
A("")
cols_k = {"data_referencia": "Data", "contrib_exportacoes": "0,05 × Export.", f"contrib_moeda_{AG.lower()}": f"0,05 × {AG}", "contrib_dcp": "0,30 × DCP",
          "contrib_outros_passivos": "0,15 × Outros pass.", "ara_recalculada_usd_bi": "ARA", "cambio_brl_usd": "Câmbio (R$/US$)",
          "razao_m2": "Razão M2", "razao_m3": "Razão M3", "razao_m4": "Razão M4"}
A("**Contribuições e sensibilidade ao agregado.**")
A("")
A(tabela(comp.dropna(subset=["ara_recalculada_usd_bi"]), cols_k, "relatorio_t5b_contribuicoes.csv",
         fmt={"razao_m2": lambda v: f(v, 3), "razao_m3": lambda v: f(v, 3), "razao_m4": lambda v: f(v, 3), "cambio_brl_usd": lambda v: f(v, 4)}))
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
A(f"Venda com recompra em aberto na data de referência: US$ {f(r1['linha_em_aberto_usd_bi'])} bi (volta às reservas no vencimento; não incluída na folga).")
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

# 9 Etapa 4
A("## 9. Etapa 4 — Cenários institucionais")
A("")
b4, c4 = e4["cenario_b"], e4["cenario_c"]
A(f"**(b) Dólares de exportadores (lei nova).** Natureza: {b4['natureza']}. Fonte: {b4['fonte']}. Reservas em {b4['data_reservas']}: US$ {f(b4['reservas_na_data_da_afirmacao_usd_bi'])} bi, "
  f"logo estoque implícito ≥ US$ {f(b4['estoque_implicito_minimo_usd_bi'])} bi. Aporte = f × esse valor no mês de entrada. {b4['requisito_legal']}.")
A("")
A(f"**(c) Desindexação das LFTs.** Participação das LFTs na DPMFi em mercado em {c4['mes']}: {f(100 * c4['participacao_lft_data_ref'], 2, True)} ({c4['fonte_atual']}); "
  f"alvo {f(100 * c4['participacao_alvo'], 0, True)} ({c4['fonte_alvo']}); δ_max = {f(c4['delta_max'], 4)}. λ × (1 − δ) a partir do mês {c4['mes_inicio']}.")
A("")
sel4 = mc4[(mc4.piso == P100) & (mc4.medida == "T_F")]
A(f"Piso {P100}, T_F. Tabela completa (todos os pisos e medidas): `tabelas/etapa4_cenarios_resultados.csv`.")
A("")
A(tabela(sel4.sort_values(["cenario", "lambda", "versao", "f", "mes_entrada", "delta", "horizonte_meses"]),
         {"cenario": "Cenário", "lambda": "λ", "versao": "Versão", "f": "f", "mes_entrada": "Mês entrada", "aporte_usd_bi": "Aporte (US$ bi)",
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
    ["π (prob. mensal de corrida)", "0; 0,02; 0,05", "hipótese", P["corrida"]["justificativa"], "parametros.yaml"],
    ["k (duração da corrida)", f"{e3['k_corrida']} meses", "calculado", "episódio histórico mais longo em blocos", "etapa 2"],
    ["f (fração dos dólares de exportadores)", "0,10; 0,25; 0,50", "hipótese", "sensibilidade; sem dado oficial", "parametros.yaml"],
    ["m_b (mês de entrada)", "1; 6; 12", "hipótese", "tempo para aprovar lei nova", "parametros.yaml"],
    ["δ (redução da pressão pós-desindexação)", f"{f(0.5 * c4['delta_max'], 4)}; {f(c4['delta_max'], 4)}", "hipótese ancorada em dado",
     "δ_max = 1 − alvo/participação atual das LFTs", "Tesouro + De Bolle p. 8"],
    ["Horizontes", "12, 24, 36, 48 meses", "parâmetro da proposta", "12 meses (Vescovi p. 3, sobre o 'Eu Acuso'); 2–4 anos (Lara Resende, nota de 16/11, p. 3)", "PDFs na bibliografia"],
    ["Pisos", "100%, 120%, 150% ARA; Greenspan-Guidotti", "metodologia", "FMI Guidance Note p. 25 (faixa 100–150%)", "PDF na bibliografia"],
    ["S_max (teto de swaps)", f"US$ {f(r1['swap_max_usd_bi'])} bi ({r1['swap_max_data']})", "calculado", "pico do estoque reconstruído", "etapa 1"],
    ["Agregado monetário da ARA", AG, "calculado", "menor erro contra a razão publicada pelo FMI", "etapa 1"],
    ["1 mês = 20 dias úteis", "—", "aproximação", "blocos de 20 dias úteis (média ≈ 21 dias úteis/mês)", "metodologia"],
]
A(tabela(pd.DataFrame(hip, columns=["nome", "valor", "tipo", "justificativa", "origem"]),
         {"nome": "Parâmetro", "valor": "Valor", "tipo": "Tipo", "justificativa": "Justificativa", "origem": "Origem"}))
A("")

# 11 Limitações
A("## 11. Limitações e alertas")
A("")
for t in [
    "A simulação supõe que a pressão de um episódio de estresse persiste todos os meses do horizonte. Não é previsão: responde 'quanto dura se a pressão for como nos piores momentos de 1999–2026, multiplicada por λ'.",
    "Razões do FMI de 2022 em diante são estimativas do FMI (DataMapper).",
    f"A escolha do agregado monetário ({AG}) é calibração contra a série do FMI, não definição confirmada em documento.",
    f"DCP de 2025-12 e 2026-06 usa aproximação que superestimou a parcela de longo prazo em {f(float(val.dif_pct.mean()))}% em média nos anos de validação (efeito ≈ US$ {f(0.15 * vies)} bi na ARA).",
    "A base de atuações não registra cancelamentos nem liquidações antecipadas (documentação do BCB); o estoque de swaps é reconstruído e não foi validado contra série oficial.",
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
    "**Fluxo cambial contratado:** não há série em API pública do catálogo do BCB; ficou fora das tabelas de episódios. Pedro pode baixar a planilha de câmbio contratado no site do BCB para `01_brutos`.",
    "**Estoque oficial de swaps:** a consulta 'Cronograma de vencimentos de instrumentos cambiais' (BCB/Demab) não respondeu de forma automatizável. Validar o estoque reconstruído manualmente com essa consulta.",
    "**VIX, Fed funds, dólar amplo (FRED):** acesso bloqueado neste ambiente; eram só contexto.",
    "**Surpresa do Copom por DI futuro:** dados históricos da B3 não obtidos; a etapa 2b usa decisão bruta.",
    "**Risco-país em dez/2024:** buscar fonte alternativa ao EMBI+ (ex.: CDS de 5 anos), se Pedro tiver acesso.",
    "**Recursos de exportadores no exterior:** sem série oficial; o cenário (b) usa afirmação de terceiro.",
    "**'Eu Acuso' original:** não está na pasta; o horizonte de 12 meses vem da descrição de Vescovi (p. 3).",
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
