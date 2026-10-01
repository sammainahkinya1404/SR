"""CSV / XLSX downloads for reports (spec Part A §11: every report can be exported)."""

import csv
import io
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from fastapi import Response
from openpyxl import Workbook


class Format(StrEnum):
    JSON = "json"
    CSV = "csv"
    XLSX = "xlsx"


def ksh(cents: int | None) -> Decimal | None:
    """Money columns in exports are KSh, not cents, so they read naturally in Excel."""
    return None if cents is None else Decimal(cents) / 100


def table(fmt: Format, filename: str, headers: Sequence[str], rows: Sequence[Sequence]) -> Response:
    disposition = {"Content-Disposition": f'attachment; filename="{filename}.{fmt}"'}
    if fmt is Format.CSV:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        return Response(buffer.getvalue(), media_type="text/csv", headers=disposition)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = filename[:31]
    sheet.append(list(headers))
    for row in rows:
        sheet.append([float(v) if isinstance(v, Decimal) else v for v in row])
    out = io.BytesIO()
    workbook.save(out)
    return Response(
        out.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=disposition,
    )
