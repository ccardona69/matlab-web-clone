"""Pruebas del lenguaje MATLAB del clon: un caso por comportamiento, en una VM nueva cada vez."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pytest

from backend.matlab.values import MCell, MString, MStruct, char_to_str, class_of
from backend.mvm_engine import MatlabVirtualMachine

Check = Callable[[MatlabVirtualMachine, dict[str, Any]], None]


def run_ok(code: str) -> tuple[MatlabVirtualMachine, dict[str, Any]]:
    vm = MatlabVirtualMachine()
    res = vm.execute(code)
    assert res["ok"] is True, res["error"]
    return vm, res


def mat(vm: MatlabVirtualMachine, name: str, expected: Any) -> None:
    np.testing.assert_allclose(np.asarray(vm.workspace[name], dtype=float), np.asarray(expected, dtype=float))


def text_of(vm: MatlabVirtualMachine, name: str) -> str:
    return char_to_str(vm.workspace[name])


OK_CASES: list[tuple[str, str, Check]] = [
    ("char_display", "s = 'hola mundo'",
     lambda vm, r: (
         _assert_eq(class_of(vm.workspace["s"]), "char"),
         _assert_in("s =\n\n    'hola mundo'\n\n", r["output"]))),
    ("end_index", "v = [10 20 30]; a = v(end); b = v(end-1:end);",
     lambda vm, r: (mat(vm, "a", [[30]]), mat(vm, "b", [[20, 30]]))),
    ("column_transpose", "A = [1 2; 3 4]; t = A(:,1)';",
     lambda vm, r: mat(vm, "t", [[1, 3]])),
    ("complex_sqrt", "z = sqrt(-4); m = abs(z);",
     lambda vm, r: (_assert_eq(complex(vm.workspace["z"].flat[0]), 2j), mat(vm, "m", [[2]]))),
    ("if_else", "if 3 > 2, r = 1; else, r = 0; end", lambda vm, r: mat(vm, "r", [[1]])),
    ("for_fprintf", "for k = 1:3, fprintf('%d\\n', k); end",
     lambda vm, r: _assert_eq(r["output"], "1\n2\n3\n")),
    ("while_loop", "k = 0; while k < 5, k = k + 1; end", lambda vm, r: mat(vm, "k", [[5]])),
    ("struct_growth", "st.a = 1; st.b.c = 'x'; st.v(3) = 7;",
     lambda vm, r: (
         mat_struct_field(vm, "st", "v", [[0, 0, 7]]),
         _assert_eq(char_to_str(vm.workspace["st"].get("b").get("c")), "x"))),
    ("cell_growth", "c = {1, 'dos', [3 4]}; x = c{2}; c{5} = 9;",
     lambda vm, r: (
         _assert_eq(text_of(vm, "x"), "dos"),
         _assert_eq(vm.workspace["c"].shape, (1, 5)))),
    ("isempty_empty", "e = isempty([]);", lambda vm, r: _assert_eq(bool(vm.workspace["e"].flat[0]), True)),
    ("num2str_pi", "p = num2str(pi);", lambda vm, r: _assert_eq(text_of(vm, "p"), "3.1416")),
    ("any_vector", "a = any([0 1]);", lambda vm, r: _assert_eq(bool(vm.workspace["a"].flat[0]), True)),
    ("find_positions", "f = find([0 1 0 1]);", lambda vm, r: mat(vm, "f", [[2, 4]])),
    ("int32_rounding", "i = int32(7.5);",
     lambda vm, r: (mat(vm, "i", [[8]]), _assert_eq(class_of(vm.workspace["i"]), "int32"))),
    ("isnumeric_scalar", "n = isnumeric(5);", lambda vm, r: _assert_eq(bool(vm.workspace["n"].flat[0]), True)),
    ("strcat_trailing_space", "s = strcat('a ', 'b');", lambda vm, r: _assert_eq(text_of(vm, "s"), "ab")),
    ("upper_text", "u = upper('abc');", lambda vm, r: _assert_eq(text_of(vm, "u"), "ABC")),
    ("fprintf_matrix_recycling", "fprintf('%d %d\\n', [1 2; 3 4])",
     lambda vm, r: _assert_eq(r["output"], "1 3\n2 4\n")),
    ("mldivide_system", "x = [2 1; 1 3] \\ [1; 2];", lambda vm, r: mat(vm, "x", [[0.2], [0.6]])),
    ("sort_descend_indices", "[s, i] = sort([3 1 2], 'descend');",
     lambda vm, r: (mat(vm, "s", [[3, 2, 1]]), mat(vm, "i", [[1, 3, 2]]))),
    ("max_min_multi", "[m, idx] = max([3 9 2]); [~, j] = min([5 4 6]);",
     lambda vm, r: (mat(vm, "m", [[9]]), mat(vm, "idx", [[2]]), mat(vm, "j", [[2]]))),
    ("class_double", "c = class(5);", lambda vm, r: _assert_eq(text_of(vm, "c"), "double")),
    ("format_long_then_short", "format long\np = pi\nformat short\nq = pi",
     lambda vm, r: (_assert_in("3.141592653589793", r["output"]), _assert_in("3.1416", r["output"]))),
    ("function_recursion", "function r = fact(n)\n if n <= 1\n r = 1;\n else\n r = n * fact(n-1);\n end\nend\n y = fact(5);",
     lambda vm, r: mat(vm, "y", [[120]])),
    ("varargin_nargin", "function r = cnt(varargin)\n r = nargin;\nend\n n = cnt(1, 2, 3);",
     lambda vm, r: mat(vm, "n", [[3]])),
    ("closure_captures_value", "a = 2; f = @(x) a*x; a = 5; y = f(3);", lambda vm, r: mat(vm, "y", [[6]])),
    ("function_handle_builtin", "g = @sin; z = g(0);", lambda vm, r: mat(vm, "z", [[0]])),
    ("grow_by_index", "x = []; x(3) = 1;", lambda vm, r: mat(vm, "x", [[0, 0, 1]])),
    ("delete_elements", "v = 1:5; v([2 4]) = [];", lambda vm, r: mat(vm, "v", [[1, 3, 5]])),
    ("delete_column", "A = magic(4); A(:, 2) = [];", lambda vm, r: _assert_eq(vm.workspace["A"].shape, (4, 3))),
    ("logical_index", "v = 1:6; w = v(v > 3);", lambda vm, r: mat(vm, "w", [[4, 5, 6]])),
    ("row_assign_scalar", "A = magic(3); A(2,:) = 0;", lambda vm, r: mat(vm, "A", [[8, 1, 6], [0, 0, 0], [4, 9, 2]])),
    ("struct_array_assign", "s(2).name = 'b';", lambda vm, r: _assert_eq(vm.workspace["s"].shape, (1, 2))),
    ("switch_string_cell", "x = 'b'; switch x, case {'a','b'}, r = 1; case 'c', r = 2; otherwise, r = 3; end",
     lambda vm, r: mat(vm, "r", [[1]])),
    ("switch_number_otherwise", "switch 7, case 1, r = 1; otherwise, r = 9; end", lambda vm, r: mat(vm, "r", [[9]])),
    ("break_continue", "k = 0; for i = 1:10, if i == 2, continue; end; if i > 4, break; end; k = k + i; end",
     lambda vm, r: mat(vm, "k", [[8]])),
    ("line_comment", "x = 3 % comentario", lambda vm, r: mat(vm, "x", [[3]])),
    ("block_comment", "%{\nbloque\n%}\ny = 2;", lambda vm, r: mat(vm, "y", [[2]])),
    ("line_continuation", "t = 1 + ...\n 2;", lambda vm, r: mat(vm, "t", [[3]])),
    ("cellfun_length", "c1 = cellfun(@length, {'ab','c'});", lambda vm, r: mat(vm, "c1", [[2, 1]])),
    ("cellfun_uniform_false", "c2 = cellfun(@(x) x*2, {1,2}, 'UniformOutput', false);",
     lambda vm, r: (_assert_eq(class_of(vm.workspace["c2"]), "cell"),
                    np.testing.assert_allclose(vm.workspace["c2"].data[0, 1], [[4]]))),
    ("arrayfun_square", "a1 = arrayfun(@(x) x^2, [1 2 3]);", lambda vm, r: mat(vm, "a1", [[1, 4, 9]])),
    ("struct_cell_array", "s1 = struct('a', {1, 2});", lambda vm, r: _assert_eq(vm.workspace["s1"].data.shape, (1, 2))),
    ("ode45_decay", "[t, y] = ode45(@(t,y) -y, [0 1], 1); e = abs(y(end) - exp(-1));",
     lambda vm, r: _assert_lt(float(vm.workspace["e"].flat[0]), 1e-3)),
    ("integral_square", "q = integral(@(x) x.^2, 0, 1);",
     lambda vm, r: _assert_lt(abs(float(vm.workspace["q"].flat[0]) - 1 / 3), 1e-10)),
    ("fzero_sqrt2", "r = fzero(@(x) x^2-2, 1);",
     lambda vm, r: _assert_lt(abs(float(vm.workspace["r"].flat[0]) - np.sqrt(2)), 1e-8)),
    ("polyfit_line", "p = polyfit([1 2 3],[2 4 6],1);",
     lambda vm, r: np.testing.assert_allclose(vm.workspace["p"], [[2, 0]], atol=1e-9)),
    ("interp1_linear", "yi = interp1([1 2 3],[10 20 30],2.5);", lambda vm, r: mat(vm, "yi", [[25]])),
    ("display_scalar", "x = 5", lambda vm, r: _assert_eq(r["output"], "x =\n\n     5\n\n")),
    ("display_matrix", "A = [1 2; 3 4]",
     lambda vm, r: _assert_eq(r["output"], "A =\n\n     1     2\n     3     4\n\n")),
    ("display_compact", "format compact\nx = 5", lambda vm, r: _assert_eq(r["output"], "x =\n     5\n")),
    ("display_logical", "b = true", lambda vm, r: _assert_eq(r["output"], "b =\n\n  logical\n\n   1\n\n")),
    ("magic_even_singly", "M = magic(6); r1 = M(1,:); cs = sum(M);",
     lambda vm, r: (mat(vm, "r1", [[35, 1, 6, 26, 19, 24]]), mat(vm, "cs", [[111] * 6]))),
    ("eval_string", "eval('w = 4;'); v = eval('w + 1');", lambda vm, r: (mat(vm, "w", [[4]]), mat(vm, "v", [[5]]))),
    ("nested_function_handle_call", "h = @(v) v(end); z = h([4 5 6]);", lambda vm, r: mat(vm, "z", [[6]])),
]

ERROR_CASES: list[tuple[str, str, str]] = [
    ("unknown_identifier", "zz + 1", "Unrecognized function or variable 'zz'."),
    ("inner_dimension", "[1 2] * [3 4]",
     "Incorrect dimensions for matrix multiplication. Check that the number of columns in the first matrix "
     "matches the number of rows in the second matrix. To operate on each element of the matrix individually, "
     "use TIMES (.*) for elementwise multiplication."),
    ("index_out_of_bounds", "v = 1:3; v(5)",
     "Index exceeds the number of array elements. Index must not exceed 3."),
    ("input_not_interactive", "input('x')",
     "Error using input\ninput: interactive input is not available in this clon; assign the value in the script."),
]


def _assert_eq(a: Any, b: Any) -> None:
    assert a == b, f"{a!r} != {b!r}"


def _assert_in(needle: str, haystack: str) -> None:
    assert needle in haystack, f"{needle!r} not in {haystack!r}"


def _assert_lt(a: float, b: float) -> None:
    assert a < b, f"{a} >= {b}"


def mat_struct_field(vm: MatlabVirtualMachine, name: str, field: str, expected: Any) -> None:
    value = vm.workspace[name].get(field)
    np.testing.assert_allclose(np.asarray(value, dtype=float), np.asarray(expected, dtype=float))


@pytest.mark.parametrize("code,check", [(c, chk) for _, c, chk in OK_CASES], ids=[i for i, _, _ in OK_CASES])
def test_language_case_runs_and_checks_workspace(code: str, check: Check) -> None:
    vm, res = run_ok(code)
    check(vm, res)


@pytest.mark.parametrize("code,message", [(c, m) for _, c, m in ERROR_CASES], ids=[i for i, _, _ in ERROR_CASES])
def test_language_error_messages(code: str, message: str) -> None:
    vm = MatlabVirtualMachine()
    res = vm.execute(code)
    assert res["ok"] is False
    assert res["error"] == message


def test_try_catch_exposes_message_and_identifier() -> None:
    vm, res = run_ok("try, error('mi:id', 'fallo %d', 3); catch me, msg = me.message; id = me.identifier; end")
    assert text_of(vm, "msg") == "fallo 3"
    assert text_of(vm, "id") == "mi:id"


def test_unique_first_occurrence_by_default() -> None:
    vm, _ = run_ok("[u, ia] = unique([3 1 3 2]); [u2, il] = unique([3 1 3 2], 'last');")
    mat(vm, "ia", [[2], [4], [1]])
    mat(vm, "il", [[2], [4], [3]])


@pytest.mark.parametrize("code,expected", [
    # Anchos verificados contra MATLAB R2026b real (clases enteras: w + 3)
    ("q = int8([100 200 -300])", "q =\n\n  1×3 int8 row vector\n\n    100    127   -128\n\n"),
    ("q = int32([1 2 3])", "q =\n\n  1×3 int32 row vector\n\n   1   2   3\n\n"),
    ("q = uint8(5)", "q =\n\n  uint8\n\n   5\n\n"),
])
def test_integer_display_width(code: str, expected: str) -> None:
    _, res = run_ok(code)
    assert res["output"] == expected


def test_function_handle_and_string_types() -> None:
    vm, _ = run_ok("s = \"doble\"; c = {'x'}; t = struct('a', 1);")
    assert isinstance(vm.workspace["s"], MString)
    assert isinstance(vm.workspace["c"], MCell)
    assert isinstance(vm.workspace["t"], MStruct)
