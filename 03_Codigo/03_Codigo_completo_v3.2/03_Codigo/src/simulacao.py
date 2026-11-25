"""Simulação de Monte Carlo da duração da capacidade de intervenção (CLAUDE.md, seção 6.4).

Unidade de tempo: 1 mês = 1 bloco de 20 dias úteis (aproximação; média ≈ 21 dias úteis/mês).
Gasto do mês = λ × gasto de um bloco histórico sorteado (bootstrap de blocos contíguos do mesmo episódio).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Blocos:
    avista: np.ndarray      # venda à vista líquida (US$ bi; negativo = compras)
    temporario: np.ndarray  # vendas brutas com recompra + empréstimos/compromissadas (US$ bi, ≥ 0)
    swap: np.ndarray        # variação líquida do estoque de swaps (US$ bi)
    prazo_meses: np.ndarray # meses até a devolução das vendas com recompra
    inicio_ep: np.ndarray   # índice do 1º bloco de cada episódio
    n_ep: np.ndarray        # nº de blocos de cada episódio
    idx_extremo: int        # bloco de maior gasto total (ritmo extremo)

    @classmethod
    def de_tabela(cls, bl: pd.DataFrame) -> "Blocos":
        ok = bl[bl["status"] != "descartado (<10 dias)"].copy()
        prazo_global = float(ok.groupby("episodio")["linha_prazo_mediano_dias_episodio"].first().median())
        ok["prazo_dias"] = ok["linha_prazo_mediano_dias_episodio"].fillna(prazo_global)
        ok = ok.reset_index(drop=True)
        eps = ok["episodio"].drop_duplicates().tolist()
        ini = np.array([ok.index[ok.episodio == e][0] for e in eps])
        n = np.array([(ok.episodio == e).sum() for e in eps])
        return cls(avista=ok["avista_usd_bi"].to_numpy(),
                   temporario=(ok["linha_venda_bruta_usd_bi"] + ok["outros_ida_bruta_usd_bi"]).to_numpy(),
                   swap=ok["swap_usd_bi"].to_numpy(),
                   prazo_meses=np.ceil(ok["prazo_dias"].to_numpy() / 30.4).astype(int),
                   inicio_ep=ini, n_ep=n, idx_extremo=int(ok["gasto_total_usd_bi"].idxmax()))


def sortear_sequencias(b: Blocos, n: int, h: int, rng: np.random.Generator,
                       pi_corrida: float = 0.0, k_corrida: int = 0) -> np.ndarray:
    """Devolve matriz (n, h) com o índice do bloco usado em cada mês de cada trajetória."""
    p_ep = b.n_ep / b.n_ep.sum()
    ep = rng.choice(len(b.n_ep), size=n, p=p_ep)
    pos = (rng.random(n) * b.n_ep[ep]).astype(int)
    em_corrida = np.zeros(n, dtype=int)
    idx = np.empty((n, h), dtype=int)
    u_corrida = rng.random((n, h))
    for t in range(h):
        normal = b.inicio_ep[ep] + pos
        if pi_corrida > 0:
            novo = (em_corrida == 0) & (u_corrida[:, t] < pi_corrida)
            em_corrida[novo] = k_corrida
        idx[:, t] = np.where(em_corrida > 0, b.idx_extremo, normal)
        em_corrida = np.maximum(em_corrida - 1, 0)
        pos += 1
        acabou = pos >= b.n_ep[ep]
        if acabou.any():
            k = int(acabou.sum())
            ep[acabou] = rng.choice(len(b.n_ep), size=k, p=p_ep)
            pos[acabou] = 0
    return idx


def simular(b: Blocos, idx: np.ndarray, lam: np.ndarray, r0: float, piso: float, s0: float, smax: float,
            substituivel: bool, aporte_mes: int | None = None, aporte_valor: float = 0.0,
            entradas: np.ndarray | None = None, limiar_material: float = 1.0, trajetorias: bool = False) -> dict:
    """Evolui reservas e swaps mês a mês. lam: vetor (h,) com λ efetivo de cada mês.

    Retorna, por trajetória, os meses até: T_R (reservas no piso), T_S (swaps no teto), T_C (capacidade total).
    Valor 0 = já esgotado na data de referência; np.inf = não esgota no horizonte simulado.
    entradas: vetor (h,) de entradas determinísticas nas reservas no início de cada mês (ex.: devolução das linhas
    já em aberto na data de referência). T_F_material: 1º mês com demanda não atendida >= limiar_material (US$ bi).
    """
    n, h = idx.shape
    R = np.full(n, r0, dtype=float)
    S = np.full(n, s0, dtype=float)
    devol = np.zeros((n, h + 60))
    tR = np.full(n, np.inf)
    tS = np.full(n, np.inf)
    tC = np.full(n, np.inf)
    tFm = np.full(n, np.inf)
    if trajetorias:
        R_path, S_path = np.empty((n, h)), np.empty((n, h))
    tol = 1e-9
    # piso escalar (padrão) ou trajetória (n, h) por caminho (ARA dinâmica, v3)
    piso_mat = np.asarray(piso, dtype=float)
    dinamico = piso_mat.ndim == 2
    if dinamico:
        piso = piso_mat[:, 0]
    if np.all(r0 <= piso + tol):
        tR[:] = 0
    if s0 >= smax - tol:
        tS[:] = 0
    if substituivel and np.all(r0 <= piso + tol) and s0 >= smax - tol:
        tC[:] = 0
    for t in range(h):
        mes = t + 1
        if dinamico:
            piso = piso_mat[:, t]
        R += devol[:, t]
        if entradas is not None:
            R += entradas[t]
        if aporte_mes is not None and mes == aporte_mes:
            R += aporte_valor
        bi = idx[:, t]
        a = lam[t] * b.avista[bi]
        tmp = lam[t] * b.temporario[bi]
        s = lam[t] * b.swap[bi]
        dem_res = a + tmp                       # demanda sobre reservas (negativa = compra)
        livre_res = np.maximum(R - piso, 0.0)
        exec_res = np.where(dem_res > 0, np.minimum(dem_res, livre_res), dem_res)
        falta_res = np.where(dem_res > 0, dem_res - exec_res, 0.0)
        livre_sw = np.maximum(smax - S, 0.0)
        exec_sw = np.where(s > 0, np.minimum(s, livre_sw), s)
        falta_sw = np.where(s > 0, s - exec_sw, 0.0)
        if substituivel:
            # o que não coube num instrumento passa para o outro
            extra_sw = np.minimum(falta_res, np.maximum(livre_sw - np.maximum(exec_sw, 0), 0.0))
            extra_res = np.minimum(falta_sw, np.maximum(livre_res - np.maximum(exec_res, 0), 0.0))
            falta_total = (falta_res - extra_sw) + (falta_sw - extra_res)
            exec_sw = exec_sw + extra_sw
            exec_res = exec_res + extra_res
            novo_c = (falta_total > 1e-6) & np.isinf(tC)
            tC[novo_c] = mes
        else:
            falta_total = falta_res + falta_sw
        novo_m = (falta_total >= limiar_material) & np.isinf(tFm)
        tFm[novo_m] = mes
        # parte temporária executada volta depois do prazo de recompra
        frac_tmp = np.where(dem_res > 0, np.clip(tmp / np.where(dem_res > 0, dem_res, 1), 0, 1), 0.0)
        tmp_exec = np.minimum(np.maximum(exec_res, 0) * frac_tmp, tmp)
        destino = t + b.prazo_meses[bi]
        ok = destino < devol.shape[1]
        devol[np.arange(n)[ok], destino[ok]] += tmp_exec[ok]
        R -= exec_res
        S += exec_sw
        novo_r = ((falta_res > 1e-6) | (R <= piso + 1e-6)) & np.isinf(tR)
        tR[novo_r] = mes
        novo_s = ((falta_sw > 1e-6) | (S >= smax - 1e-6)) & np.isinf(tS)
        tS[novo_s] = mes
        if trajetorias:
            R_path[:, t], S_path[:, t] = R, S
    if not substituivel:
        tC = np.maximum(tR, tS)  # sem substituição, a capacidade total acaba quando os dois instrumentos acabam
        tF = np.minimum(tR, tS)  # primeira falha: o primeiro instrumento deixa de atender a demanda
    else:
        tF = tC                  # com substituição, a primeira demanda não atendida é o próprio T_C
    out = {"T_R": tR, "T_S": tS, "T_C": tC, "T_F": tF, "T_F_material": tFm, "R_final": R, "S_final": S}
    if trajetorias:
        out["R_path"], out["S_path"] = R_path, S_path
    return out


def resumir(t: np.ndarray, h: int) -> dict:
    """Estatísticas de T no horizonte h (trajetórias com T > h são censuradas)."""
    esg = t[t <= h]
    n = len(t)
    cens = 1 - len(esg) / n
    out = {"p_esgotar_ate_H": len(esg) / n, "prop_censurada": cens,
           "ja_esgotado_na_data_ref": float(np.mean(t == 0)),
           "mediana_entre_esgotadas": float(np.median(esg)) if len(esg) else np.nan,
           "p10_entre_esgotadas": float(np.percentile(esg, 10)) if len(esg) else np.nan,
           "p90_entre_esgotadas": float(np.percentile(esg, 90)) if len(esg) else np.nan,
           "media_entre_esgotadas": float(np.mean(esg)) if len(esg) else np.nan}
    # mediana incondicional só se < 50% censurado
    out["mediana_incondicional"] = float(np.median(np.minimum(t, h + 1))) if cens < 0.5 else np.nan
    return out


def meses_prazo(dias: float) -> int:
    return int(math.ceil(dias / 30.4))


# ----------------------------------------------------------------------------------------------------
# v3 (auditoria de 24/11/2026): persistência por episódios
# ----------------------------------------------------------------------------------------------------
def anexar_blocos(b: Blocos, avista: np.ndarray, temporario: np.ndarray, swap: np.ndarray, prazo_meses: np.ndarray) -> tuple[Blocos, np.ndarray]:
    """Devolve um novo Blocos com blocos extras no fim (não são episódios) e os índices dos blocos anexados."""
    n0 = len(b.avista)
    nb = Blocos(avista=np.concatenate([b.avista, avista]), temporario=np.concatenate([b.temporario, temporario]),
                swap=np.concatenate([b.swap, swap]), prazo_meses=np.concatenate([b.prazo_meses, prazo_meses]).astype(int),
                inicio_ep=b.inicio_ep, n_ep=b.n_ep, idx_extremo=b.idx_extremo)
    return nb, np.arange(n0, n0 + len(avista))


def sequencia_replay(b: Blocos, ep: int, h: int, idx_calma: int) -> np.ndarray:
    """Um episódio histórico reproduzido na ordem original a partir do mês 1; depois, calmaria (bloco idx_calma)."""
    seq = np.full(h, idx_calma, dtype=int)
    k = min(int(b.n_ep[ep]), h)
    seq[:k] = b.inicio_ep[ep] + np.arange(k)
    return seq[None, :]


def sortear_episodios(b: Blocos, n: int, h: int, rng: np.random.Generator, hazard_mensal: float,
                      calma: np.ndarray, pesos: str = "iguais") -> np.ndarray:
    """Episódio no mês 1 (choque da política); ao fim de cada episódio, calmaria até a próxima chegada.

    Na calmaria, a cada mês um novo episódio começa com probabilidade hazard_mensal (processo de Bernoulli).
    Episódio sorteado com pesos iguais (cada episódio histórico é uma observação) ou proporcionais à duração.
    Mês de calmaria = bloco sorteado uniformemente em `calma` (um único índice = calmaria determinística).
    Episódios são reproduzidos na ordem original dos blocos.
    """
    p = np.full(len(b.n_ep), 1 / len(b.n_ep)) if pesos == "iguais" else b.n_ep / b.n_ep.sum()
    idx = np.empty((n, h), dtype=int)
    ep = rng.choice(len(b.n_ep), size=n, p=p)
    pos = np.zeros(n, dtype=int)
    em_ep = np.ones(n, dtype=bool)
    u = rng.random((n, h))
    novos = rng.choice(len(b.n_ep), size=(n, h), p=p)
    cal = calma[rng.integers(0, len(calma), size=(n, h))]
    for t in range(h):
        # quem está em calmaria pode iniciar episódio neste mês
        inicia = (~em_ep) & (u[:, t] < hazard_mensal)
        ep[inicia] = novos[inicia, t]
        pos[inicia] = 0
        em_ep |= inicia
        idx[:, t] = np.where(em_ep, b.inicio_ep[ep] + pos, cal[:, t])
        pos[em_ep] += 1
        acabou = em_ep & (pos >= b.n_ep[ep])
        em_ep[acabou] = False
    return idx


def entradas_linhas_abertas(atuacoes: pd.DataFrame, data_ref: str, h: int) -> tuple[np.ndarray, pd.DataFrame]:
    """Devolução contratual das operações temporárias em aberto na data de referência (mês do vencimento)."""
    dref = pd.Timestamp(data_ref)
    ab = atuacoes[atuacoes.instrumento.isin(["Venda com Recompra", "Empréstimo", "Operação Compromissada"]) &
                  (atuacoes.data_liquidacao <= dref) & (atuacoes.data_vencimento > dref)].copy()
    ab["mes"] = (ab.data_vencimento.dt.year - dref.year) * 12 + ab.data_vencimento.dt.month - dref.month
    ent = np.zeros(h)
    for _, r in ab.iterrows():
        if 1 <= r.mes <= h:
            ent[int(r.mes) - 1] += r.volume_aceito_usd_bi
    return ent, ab
