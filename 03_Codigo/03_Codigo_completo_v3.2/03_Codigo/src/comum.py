"""Funções comuns: caminhos, download com registro, dicionário de dados."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

# Console do Windows usa cp1252 e quebra em caracteres como ≤ e ≠ nos prints das tabelas.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[2]
BRUTOS = RAIZ / "02_Dados" / "01_brutos"
TRATADOS = RAIZ / "02_Dados" / "02_tratados"
DICIONARIO = RAIZ / "02_Dados" / "03_dicionario" / "dicionario_series.csv"
LOGS = RAIZ / "03_Codigo" / "logs"
RESULTADOS = RAIZ / "04_Resultados"
TABELAS = RESULTADOS / "tabelas"
FIGURAS = RESULTADOS / "figuras"
CONFIG = RAIZ / "03_Codigo" / "config" / "parametros.yaml"

for p in (BRUTOS, TRATADOS, DICIONARIO.parent, LOGS, TABELAS, FIGURAS, RESULTADOS / "historico"):
    p.mkdir(parents=True, exist_ok=True)

CAMPOS_DIC = [
    "id_interno", "nome_na_fonte", "fonte", "url_ou_endpoint", "codigo", "unidade",
    "frequencia", "periodo_inicio", "periodo_fim", "data_hora_acesso", "arquivo_bruto",
    "sha256", "n_observacoes", "observacoes",
]

HOJE = dt.date.today().isoformat()
_LOG = LOGS / f"{dt.datetime.now():%Y-%m-%d_%H%M}_download.log"
HEADERS = {"User-Agent": "Mozilla/5.0 (pesquisa academica; Pedro)"}


def log(msg: str) -> None:
    linha = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(linha)
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(url: str, destino: Path, params: dict | None = None, refresh: bool = False,
           tentativas: int = 3, timeout: int = 90, headers: dict | None = None) -> Path:
    """Baixa url para destino (cache: não baixa de novo se já existe, salvo refresh)."""
    if destino.exists() and not refresh:
        log(f"CACHE {destino.name}")
        return destino
    ultimo_erro = None
    for i in range(1, tentativas + 1):
        try:
            r = requests.get(url, params=params, headers={**HEADERS, **(headers or {})}, timeout=timeout)
            log(f"GET {r.url} -> {r.status_code} ({len(r.content)} bytes)")
            r.raise_for_status()
            destino.write_bytes(r.content)
            log(f"SALVO {destino.name} sha256={sha256(destino)}")
            return destino
        except Exception as e:  # noqa: BLE001
            ultimo_erro = e
            log(f"ERRO tentativa {i}/{tentativas} {url}: {e}")
            time.sleep(3 * i)
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")


def registrar(**campos) -> None:
    """Insere ou substitui a linha do id_interno no dicionário de dados."""
    linhas = []
    if DICIONARIO.exists():
        with open(DICIONARIO, encoding="utf-8") as f:
            linhas = [l for l in csv.DictReader(f) if l["id_interno"] != campos["id_interno"]]
    linha = {k: campos.get(k, "") for k in CAMPOS_DIC}
    linhas.append(linha)
    linhas.sort(key=lambda l: l["id_interno"])
    with open(DICIONARIO, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_DIC)
        w.writeheader()
        w.writerows(linhas)


def agora() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def salvar_json(obj, caminho: Path) -> None:
    caminho.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
