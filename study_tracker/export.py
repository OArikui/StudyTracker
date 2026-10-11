from __future__ import annotations
import csv
from openpyxl import Workbook
from .models import COLUMNS


def export_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow(r.table_values())


def export_xlsx(rows, aliases, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "学習記録"
    ws.append(COLUMNS)
    for r in rows:
        ws.append(r.table_values())

    alias_ws = wb.create_sheet("学習単位エイリアス")
    alias_ws.append(["タイトル", "Docstring"])
    for a in aliases:
        alias_ws.append([a["title"], a["docstring"]])

    wb.save(path)
