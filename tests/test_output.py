from __future__ import annotations

import csv
import json
from argparse import Namespace
from pathlib import Path

from group_finder import (
    CSV_HEADER,
    GroupLink,
    SearchReport,
    atomic_write_text,
    csv_safe,
    resolve_base_path,
    save_csv,
    save_json,
)


def make_args(**overrides: object) -> Namespace:
    values = {
        "output": "results",
        "output_dir": None,
        "timestamp": False,
        "append": False,
        "force": False,
        "csv_delimiter": ",",
        "stdout": False,
        "format": "both",
    }
    values.update(overrides)
    return Namespace(**values)


def test_csv_safe_blocks_formulas() -> None:
    assert csv_safe("=1+1") == "'=1+1"
    assert csv_safe("+SUM(A1)") == "'+SUM(A1)"
    assert csv_safe("-cmd") == "'-cmd"
    assert csv_safe("@import") == "'@import"
    assert csv_safe("texto normal") == "texto normal"
    assert csv_safe(None) == ""


def test_resolve_base_path_removes_extension() -> None:
    args = make_args(output="resultados.csv")
    assert resolve_base_path(args) == Path("resultados")


def test_resolve_base_path_uses_output_dir() -> None:
    args = make_args(output="resultados", output_dir="salida")
    assert resolve_base_path(args) == Path("salida") / "resultados"


def test_atomic_write_text(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "file.txt"
    atomic_write_text(path, "hola")
    assert path.read_text(encoding="utf-8") == "hola"
    assert not (tmp_path / "sub" / "file.txt.tmp").exists()


def test_save_json_with_metadata(tmp_path: Path) -> None:
    report = SearchReport(
        results={
            "telegram": [
                GroupLink(
                    platform="telegram",
                    title="Grupo",
                    link="https://t.me/sc_what_test_only",
                    description="Comunidad",
                    queries=["python"],
                )
            ]
        }
    )
    path = tmp_path / "results.json"
    save_json(report, path, {"queries": ["python"], "version": "1.0.0"})

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["meta"]["queries"] == ["python"]
    assert data["results"]["telegram"][0]["link"] == "https://t.me/sc_what_test_only"


def test_save_csv_is_excel_friendly(tmp_path: Path) -> None:
    report = SearchReport(
        results={
            "whatsapp": [
                GroupLink(
                    platform="whatsapp",
                    title="=Título con fórmula",
                    link="https://chat.whatsapp.com/00000000000000000000",
                    description="Línea 1\nLínea 2",
                    source_url="https://ejemplo.com",
                    queries=["cripto"],
                    member_count=42,
                )
            ]
        }
    )
    path = tmp_path / "results.csv"
    save_csv(report, path, ",")

    raw = path.read_text(encoding="utf-8-sig")
    assert "Línea 1" in raw
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == CSV_HEADER
    assert rows[1][0] == "WhatsApp"
    assert rows[1][1] == "'=Título con fórmula"
    assert rows[1][7] == "42"
