
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import BRUTOS, HOJE, agora, baixar, log, registrar, sha256  # noqa: E402

URL = ("https://api.imf.org/external/sdmx/2.1/data/IMF.STA,WPFXI/"
       ".FXI_BROAD_PROXY_GDP+FXI_BROAD_PROXY_USD+FXI_BROAD_PUB_USD+FXI_SPOT_PUB_USD.M")
URL_PORTAL = "https://data.imf.org/ (dataset IMF.STA:WPFXI, versão 1.0.2, exportação CSV)"
ARQ_ORIGINAL_PORTAL = "dataset_2026-11-24T14_23_20.195789772Z_DEFAULT_INTEGRATION_IMF.STA_WPFXI_1.0.2.csv"
REFERENCIA = "Adler, Chang, Mano e Shao (2021, IMF WP 21/47; 2024, JMCB). 124 países, 2000–2024. Proxies quando não há dado oficial."


def _linhas(caminho: Path) -> int:
    with caminho.open(encoding="utf-8-sig") as f:
        return sum(1 for _ in f) - 1


def via_api() -> Path:
    destino = BRUTOS / f"FMI_WPFXI_intervencao_cambial_mensal_{HOJE}.csv"
    # baixar(): cache do dia, 3 tentativas com espera e log (CLAUDE.md §4)
    baixar(URL, destino, params={"detail": "dataonly"}, refresh="--refresh" in sys.argv, timeout=300,
           headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"})
    n = _linhas(destino)
    registrar(id_interno="fmi_wpfxi_mensal", nome_na_fonte="Working Paper Foreign Exchange Intervention (WPFXI)",
              fonte="FMI — data.imf.org (API SDMX)", url_ou_endpoint=URL, codigo="IMF.STA:WPFXI",
              unidade="% do PIB (média móvel de 3 anos) e US$ milhões; negativo = venda de moeda estrangeira",
              frequencia="mensal", data_hora_acesso=agora(), arquivo_bruto=destino.name, sha256=sha256(destino),
              n_observacoes=str(n), observacoes="CSV longo (uma linha por observação). " + REFERENCIA)
    return destino


def via_portal() -> Path | None:
    achados = sorted(BRUTOS.glob("FMI-portal_WPFXI_*.csv"))
    if not achados:
        return None
    f = achados[-1]
    registrar(id_interno="fmi_wpfxi_mensal", nome_na_fonte="Working Paper Foreign Exchange Intervention (WPFXI), IMF.STA:WPFXI(1.0.2)",
              fonte="FMI — data.imf.org, exportado manualmente pelo Pedro", url_ou_endpoint=URL_PORTAL, codigo="IMF.STA:WPFXI(1.0.2)",
              unidade="% do PIB (média móvel de 3 anos) e US$ milhões; negativo = venda de moeda estrangeira",
              frequencia="mensal e trimestral (usa-se só a mensal)", periodo_inicio="2000-01", periodo_fim="2024-12",
              data_hora_acesso="2026-11-24 11:23", arquivo_bruto=f.name, sha256=sha256(f), n_observacoes=str(_linhas(f)),
              observacoes=("CSV largo (uma linha por série, colunas por período; n_observacoes = nº de séries), todos os 15 indicadores e 124 países. "
                           f"Nome original do download: {ARQ_ORIGINAL_PORTAL}; renomeado e movido sem alterar bytes. "
                           "Usado porque api.imf.org teve o TLS reiniciado pela rede em 24/11/2026. " + REFERENCIA))
    log(f"OK WPFXI (exportação manual do portal): {f.name}")
    return f


if __name__ == "__main__":
    try:
        f = via_api()
        log(f"OK WPFXI (API): {f.name}")
    except Exception as e:  # noqa: BLE001
        log(f"API do FMI indisponível: {e}")
        if via_portal() is None:
            log("PENDENCIA WPFXI: API inacessível e sem exportação manual. Baixe em data.imf.org (dataset WPFXI, CSV) e "
                f"salve em {BRUTOS} como FMI-portal_WPFXI_intervencao_cambial_largo_AAAA-MM-DD.csv")
            sys.exit(1)
