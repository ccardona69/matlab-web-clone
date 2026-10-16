"""WO-01/WS-1: aceptación contra las capturas doradas de MATLAB R2026b.

- docs/acceptance/golden-output.txt: set AC-01..AC-20 (F1, consola base).
- docs/acceptance/golden-catalogs.txt: catálogo CT-xx/FM-xx (errores, warnings y formatos).

La verdad canónica de errores/warnings son los marcadores <ERROR>/<WARN>; el ruido de la
consola batch ("[Warning: ...]", "[> In ...", "]") se descarta. La comparación de salida es
por líneas exactas (incluidos espacios finales) y solo se recortan las líneas en blanco del
inicio y del final del bloque.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from backend.mvm_engine import MatlabVirtualMachine

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "docs" / "acceptance"

# Casos del catálogo aún no soportados por el motor (WO-01). xfail no estricto: si alguno pasa,
# pytest no falla; se van retirando de esta lista al implementarlos.
#   CT-42: ode45 debe reproducir el número exacto de pasos adaptativos de MATLAB (1x11 vs 17x1).
#   CT-60: fzero sin intervalo con signo debe imprimir el punto exacto de su búsqueda (algoritmo).
PENDING_CATALOG: set[str] = {"CT-42", "CT-60"}


@dataclass
class GoldenCase:
    case_id: str
    code: str
    lines: list[str]
    error: tuple[str, str] | None = None
    warnings: list[tuple[str, str]] = field(default_factory=list)


def _clean(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def load_cases(path: Path) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    case_id: str | None = None
    code = ""
    lines: list[str] = []
    error: tuple[str, str] | None = None
    warnings: list[tuple[str, str]] = []

    for raw in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"<CASE (\S+)>", raw)
        if m:
            case_id, code, error = m.group(1), "", None
            lines, warnings = [], []
            continue
        if case_id is None:
            continue
        m = re.match(r"<CODE (.*)>", raw)
        if m:
            code = m.group(1)
            continue
        m = re.match(r"<ERROR ([^|]*) \| (.*)>", raw)
        if m:
            error = (m.group(1).strip(), m.group(2))
            continue
        m = re.match(r"<WARN ([^|]*) \| (.*)>", raw)
        if m:
            warnings.append((m.group(1).strip(), m.group(2)))
            continue
        if re.match(r"<END ", raw):
            cases.append(GoldenCase(case_id, code, _clean(lines), error, warnings))
            case_id = None
            continue
        if raw.startswith("[") or raw.startswith("]"):
            continue  # ruido de la consola batch (aviso + pila de llamadas)
        lines.append(raw)
    return cases


AC_CASES = load_cases(GOLDEN_DIR / "golden-output.txt")
CATALOG_CASES = load_cases(GOLDEN_DIR / "golden-catalogs.txt")


def execute_case(case: GoldenCase) -> None:
    vm = MatlabVirtualMachine()
    res = vm.execute(case.code)
    if case.error is not None:
        expected_id, expected_msg = case.error
        assert res["ok"] is False, f"{case.case_id}: debía fallar y no falló. Salida: {res['output']!r}"
        assert res.get("error_id") == expected_id, (
            f"{case.case_id}: identificador de error {res.get('error_id')!r} != {expected_id!r}"
        )
        last = (res["error"] or "").splitlines()[-1] if res["error"] else ""
        assert last == expected_msg, f"{case.case_id}: mensaje {last!r} != {expected_msg!r}"
        return
    assert res["ok"] is True, f"{case.case_id}: error inesperado: {res['error']!r}"
    expected = list(case.lines)
    for _wid, msg in case.warnings:
        expected = [f"Warning: {msg}", ""] + expected
    expected = _clean(expected)
    actual = _clean(res["output"].split("\n"))
    if actual != expected:
        detail = [f"{case.case_id}: salida distinta (E=esperado, A=actual)"]
        for i in range(max(len(expected), len(actual))):
            e = expected[i] if i < len(expected) else None
            a = actual[i] if i < len(actual) else None
            flag = " " if e == a else ">"
            detail.append(f"{flag} {i:3d} E={e!r}")
            if e != a:
                detail.append(f"      A={a!r}")
        pytest.fail("\n".join(detail))
    got_warnings = [(w["id"], w["message"]) for w in res.get("warnings", [])]
    assert got_warnings == case.warnings, f"{case.case_id}: warnings {got_warnings!r} != {case.warnings!r}"


def _ids(cases: list[GoldenCase]) -> list[str]:
    return [c.case_id for c in cases]


@pytest.mark.parametrize("case", AC_CASES, ids=_ids(AC_CASES))
def test_acceptance_core(case: GoldenCase) -> None:
    execute_case(case)


_IMPLEMENTED = [c for c in CATALOG_CASES if c.case_id not in PENDING_CATALOG]
_PENDING = [c for c in CATALOG_CASES if c.case_id in PENDING_CATALOG]


@pytest.mark.parametrize("case", _IMPLEMENTED, ids=_ids(_IMPLEMENTED))
def test_acceptance_catalog(case: GoldenCase) -> None:
    execute_case(case)


@pytest.mark.xfail(reason="catálogo: pendiente en el motor (WO-01 en progreso)", strict=False)
@pytest.mark.parametrize("case", _PENDING, ids=_ids(_PENDING))
def test_acceptance_catalog_pending(case: GoldenCase) -> None:
    execute_case(case)
