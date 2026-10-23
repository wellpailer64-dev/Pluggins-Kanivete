"""Pastas do KaniCode: execução normal e verificações nunca compartilham os dados."""
import os
from pathlib import Path


def pasta_dados():
    if os.environ.get("KANICODE_TESTE") == "1":
        base = Path("D:/kanivete_testes").resolve()
        pasta = Path(os.environ.get("KANICODE_DADOS_TESTE") or base / "kanicode_dados").resolve()
        if not pasta.is_relative_to(base):
            raise ValueError("dados de teste devem ficar em D:/kanivete_testes")
        return pasta
    return Path(Path(__file__).resolve().anchor) / "Kanivete" / "KaniCode"

