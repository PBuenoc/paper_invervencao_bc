"""Testes das funções centrais (v3.2). Rodar: python -m pytest 03_Codigo/tests -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "03_Codigo"))
from src.simulacao import Blocos, anexar_blocos, sequencia_replay, simular, sortear_episodios  # noqa: E402

sys.path.insert(0, str(RAIZ / "03_Codigo"))


def blocos(avista, temp=None, swap=None, prazo=None, n_ep=None):
    k = len(avista)
    temp = np.zeros(k) if temp is None else np.asarray(temp, float)
    swap = np.zeros(k) if swap is None else np.asarray(swap, float)
    prazo = np.ones(k, int) if prazo is None else np.asarray(prazo, int)
    n_ep = np.array([k]) if n_ep is None else np.asarray(n_ep)
    ini = np.concatenate([[0], np.cumsum(n_ep)[:-1]])
    return Blocos(avista=np.asarray(avista, float), temporario=temp, swap=swap, prazo_meses=prazo,
                  inicio_ep=ini, n_ep=n_ep, idx_extremo=int(np.argmax(avista)))


def rodar(b, seq, piso=90.0, r0=100.0, s0=0.0, smax=10.0, subst=True, **kw):
    idx = np.asarray(seq)[None, :]
    return simular(b, idx, np.ones(idx.shape[1]), r0, piso, s0, smax, subst, **kw)


def test_sem_demanda_nunca_falha():
    o = rodar(blocos([0.0]), [0, 0, 0])
    assert np.isinf(o["T_F"][0]) and o["R_final"][0] == 100


def test_demanda_igual_a_folga_nao_falha_e_um_a_mais_falha():
    assert np.isinf(rodar(blocos([10.0, 0.0]), [0, 1], smax=0.0)["T_C"][0])
    assert rodar(blocos([10.5]), [0], smax=0.0)["T_F"][0] == 1


def test_substituicao_leva_excesso_para_swaps():
    o = rodar(blocos([15.0]), [0], smax=10.0, subst=True)
    assert np.isinf(o["T_F"][0]) and o["S_final"][0] == pytest.approx(5.0) and o["R_final"][0] == pytest.approx(90.0)
    o2 = rodar(blocos([15.0]), [0], smax=10.0, subst=False)
    assert o2["T_F"][0] == 1


def test_linha_volta_apos_prazo():
    b = blocos([0.0, 0.0], temp=[5.0, 0.0], prazo=[2, 1])
    o = rodar(b, [0, 1, 1], trajetorias=True)
    assert o["R_path"][0, 0] == pytest.approx(95.0)
    assert o["R_path"][0, 2] == pytest.approx(100.0)


def test_compra_aumenta_reservas():
    o = rodar(blocos([-3.0]), [0, 0])
    assert o["R_final"][0] == pytest.approx(106.0)


def test_entradas_e_piso_dinamico_escalar_equivalente():
    b = blocos([4.0])
    o1 = rodar(b, [0, 0, 0], entradas=np.array([1.0, 0, 0]))
    o2 = simular(b, np.zeros((1, 3), int), np.ones(3), 100.0, np.full((1, 3), 90.0), 0.0, 10.0, True, entradas=np.array([1.0, 0, 0]))
    assert o1["T_F"][0] == o2["T_F"][0] and o1["R_final"][0] == pytest.approx(o2["R_final"][0])


def test_replay_e_episodios():
    b = blocos([1, 2, 3, 4, 5], n_ep=[2, 3])
    bz, z = anexar_blocos(b, np.zeros(1), np.zeros(1), np.zeros(1), np.ones(1, int))
    seq = sequencia_replay(bz, 1, 6, int(z[0]))[0]
    assert list(seq) == [2, 3, 4, 5, 5, 5]
    idx = sortear_episodios(bz, 500, 12, np.random.default_rng(1), 0.0, np.array([int(z[0])]))
    assert set(idx[:, 0]) <= {0, 2}                       # todo caminho começa no 1º bloco de um episódio
    assert all((row[row != 5] == np.arange(len(row[row != 5]))).all() or (row[row != 5] == np.arange(2, 2 + len(row[row != 5]))).all()
               for row in idx)                            # sem taxa de chegada: um episódio e depois só calmaria


def test_soma_contribuicoes_ara():
    c = pd.read_csv(RAIZ / "04_Resultados" / "tabelas" / "etapa1_componentes_ara.csv")
    s = c.contrib_exportacoes + c.contrib_moeda_esp + c.contrib_dcp_esp + c.contrib_outros_passivos_esp
    assert (s - c.ara_recalculada_usd_bi).abs().max() < 1e-9


def test_estoque_swaps_igual_serie_oficial():
    v = pd.read_csv(RAIZ / "04_Resultados" / "tabelas" / "validacao_estoques_oficiais.csv")
    assert (v.dif_swap.abs() > 0.01).sum() <= 1
