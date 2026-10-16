"""Builtins de sistema, control de flujo, errores, evaluación y ayuda."""

from __future__ import annotations

import fnmatch
import re
import time
from pathlib import Path
from typing import Any

import numpy as np

from backend.matlab.errors import MatlabError
from backend.matlab.library_strings import _printf_atoms, chars_of, format_printf
from backend.matlab.registry import builtin, cellstr_of, is_text, nargchk, text
from backend.matlab.values import MFunc, MStruct, class_of, make_char, truthy

MATLAB_KEYWORDS = [
    "break", "case", "catch", "classdef", "continue", "else", "elseif", "end", "for", "function",
    "global", "if", "otherwise", "parfor", "persistent", "return", "spmd", "switch", "try", "while",
]
VERSION_TEXT = "26.2.0.3386108 (R2026b)"
IDENTIFIER_RE = re.compile(r"^[^\s:]+(:[^\s:]+)+$")


# ---------- consola y sistema ----------

@builtin("clc")
def bi_clc(I: Any, args: list[Any], nargout: int) -> Any:
    I.events.append({"type": "clc"})
    return None


@builtin("more", "commandwindow", "commandhistory", "home", "drawnow", "beep")
def bi_noop(I: Any, args: list[Any], nargout: int) -> Any:
    return None


@builtin("format")
def bi_format(I: Any, args: list[Any], nargout: int) -> Any:
    if not args:
        I.fmt.numeric, I.fmt.spacing = "short", "loose"
        return None
    for arg in args:
        token = text(arg).lower()
        if token in ("short", "long", "shorte", "longe", "shortg", "longg",
                     "shorteng", "longeng", "rat", "hex", "bank"):
            I.fmt.numeric = token
        elif token in ("+", "plus"):
            I.fmt.numeric = "plus"
        elif token == "eng" and I.fmt.numeric in ("short", "long"):
            I.fmt.numeric = I.fmt.numeric + "eng"
        elif token in ("compact", "loose"):
            I.fmt.spacing = token
        elif token == "g" and I.fmt.numeric in ("short", "long"):
            I.fmt.numeric = I.fmt.numeric + "g"
        elif token == "e" and I.fmt.numeric in ("short", "long"):
            I.fmt.numeric = I.fmt.numeric + "e"
        else:
            raise MatlabError(f"Unrecognized format option '{text(arg)}'.")
    return None


@builtin("pwd")
def bi_pwd(I: Any, args: list[Any], nargout: int) -> Any:
    return make_char(str(I.folder))


@builtin("cd")
def bi_cd(I: Any, args: list[Any], nargout: int) -> Any:
    if not args:
        return make_char(str(I.folder))
    raw = text(args[0])
    base = Path(raw)
    target = (base if base.is_absolute() else (I.folder / base)).resolve()
    if not target.is_dir():
        raise MatlabError(
            f"Unable to change current folder to '{raw}' (Name is nonexistent or not a folder).",
            "MATLAB:cd:NonExistentFolder",
        )
    root = I.folder.resolve()
    if target != root and root not in target.parents:
        raise MatlabError("Cannot change directory outside the project scripts folder.")
    I.folder = target
    return None


def _m_files(I: Any) -> list[str]:
    return sorted(p.stem for p in Path(I.folder).glob("*.m"))


@builtin("ls", "dir", "what")
def bi_ls(I: Any, args: list[Any], nargout: int) -> Any:
    names = _m_files(I)
    if nargout:
        return cellstr_of(names)
    I.write("  ".join(f"{n}.m" for n in names) + "\n" if names else "")
    return None


@builtin("type")
def bi_type(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    path = I.folder / f"{text(args[0])}.m"
    if not path.is_file():
        raise MatlabError(f"'{text(args[0])}' not found.")
    content = path.read_text(encoding="utf-8", errors="replace")
    if nargout:
        return make_char(content)
    I.write(content if content.endswith("\n") else content + "\n")
    return None


@builtin("edit", "open")
def bi_edit(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    I.events.append({"type": "edit", "file": text(args[0])})
    return None


@builtin("run")
def bi_run(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    name = text(args[0])
    if not (I.folder / name).is_file():
        raise MatlabError(f"{name} not found.", "MATLAB:run:FileNotFound")
    stem = name[:-2] if name.lower().endswith(".m") else name
    I.call_named(stem, [], 0)
    return None


@builtin("delete")
def bi_delete(I: Any, args: list[Any], nargout: int) -> Any:
    for a in args:
        name = text(a)
        path = I.folder / name
        if path.is_file():
            path.unlink()
        elif not path.exists():
            I.warn(f"File '{name}' not found.", "MATLAB:DELETE:FileNotFound")
    return None


@builtin("load")
def bi_load(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    name = text(args[0])
    if not (I.folder / name).is_file():
        raise MatlabError(f'Unable to find file or directory "{name}".', "MATLAB:load:couldNotReadFile")
    raise MatlabError(
        f'Reading MAT-files is not implemented in the clone yet ("{name}").',
        "MATLAB:load:couldNotReadFile",
    )


@builtin("version", "ver")
def bi_version(I: Any, args: list[Any], nargout: int) -> Any:
    return make_char(VERSION_TEXT)


@builtin("computer")
def bi_computer(I: Any, args: list[Any], nargout: int) -> Any:
    return make_char("PCWIN64")


@builtin("ispc")
def bi_ispc(I: Any, args: list[Any], nargout: int) -> Any:
    return True


@builtin("isunix", "ismac")
def bi_isunix(I: Any, args: list[Any], nargout: int) -> Any:
    return False


@builtin("which")
def bi_which(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    path = I.folder / f"{text(args[0])}.m"
    if path.is_file():
        return make_char(str(path))
    if text(args[0]) in I.builtins:
        return make_char(f"built-in ({text(args[0])})")
    return make_char("")


def _help_text(I: Any, name: str) -> str:
    path = I.folder / f"{name}.m"
    if path.is_file():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        block = []
        started = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("%"):
                started = True
                block.append(stripped.lstrip("%").strip())
            elif started or stripped:
                break
        if block:
            return "\n".join(block) + "\n"
    return f"'{name}' documentation is not available in this clon yet.\n"


@builtin("help", "doc")
def bi_help(I: Any, args: list[Any], nargout: int) -> Any:
    if not args:
        I.write("Documentation is not available in this clon yet.\n")
        return None
    I.write(_help_text(I, text(args[0])))
    return None


@builtin("lookfor")
def bi_lookfor(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    return None


# ---------- tiempo ----------

@builtin("tic")
def bi_tic(I: Any, args: list[Any], nargout: int) -> Any:
    I.tic_time = time.perf_counter()
    if nargout:
        return np.array([[float(time.time_ns() // 1000)]], dtype=np.uint64)
    return None


@builtin("toc")
def bi_toc(I: Any, args: list[Any], nargout: int) -> Any:
    elapsed = time.perf_counter() - I.tic_time
    if nargout:
        return elapsed
    I.write(f"Elapsed time is {elapsed:.6f} seconds.\n")
    return None


@builtin("clock")
def bi_clock(I: Any, args: list[Any], nargout: int) -> Any:
    now = time.localtime()
    seconds = now.tm_sec + (time.time() % 1)
    return np.array([[float(now.tm_year), float(now.tm_mon), float(now.tm_mday), float(now.tm_hour),
                      float(now.tm_min), seconds]])


@builtin("pause")
def bi_pause(I: Any, args: list[Any], nargout: int) -> Any:
    if args:
        seconds = float(np.real(args[0].ravel()[0]))
        if 0 < seconds <= 2:
            time.sleep(seconds)
    return None


@builtin("input", "keyboard")
def bi_input(I: Any, args: list[Any], nargout: int) -> Any:
    raise MatlabError("input: interactive input is not available in this clon; assign the value in the script.")


# ---------- variables ----------

@builtin("clear", "clearvars")
def bi_clear(I: Any, args: list[Any], nargout: int) -> Any:
    names = [text(a) for a in args]
    if not names or names[0] in ("all", "-all", "-v", "variables"):
        I.vars.clear()
        return None
    for pattern in names:
        for name in [k for k in list(I.vars.keys()) if fnmatch.fnmatchcase(k, pattern)]:
            del I.vars[name]
    return None


@builtin("who")
def bi_who(I: Any, args: list[Any], nargout: int) -> Any:
    names = sorted(I.vars.keys())
    if nargout:
        return cellstr_of(names)
    if names:
        I.write("Your variables are:\n\n" + "  ".join(names) + "\n\n")
    return None


@builtin("whos")
def bi_whos(I: Any, args: list[Any], nargout: int) -> Any:
    from backend.matlab.values import bytes_of, shape_of
    names = sorted(I.vars.keys())
    if args:
        wanted = {text(a) for a in args}
        names = [n for n in names if n in wanted]
    if not names:
        return None
    namew = max(10, max(len(n) for n in names) + 2)
    # Geometría de columnas capturada de MATLAB R2026b (AC-20)
    header = "  " + "Name".ljust(namew) + "Size".ljust(10) + "Bytes".rjust(11) + "  " + "Class".ljust(10) + "Attributes".ljust(10)
    lines = [header, ""]
    for name in names:
        value = I.vars[name]
        r, c = shape_of(value)
        row = ("  " + name.ljust(namew) + f"{r}x{c}".ljust(10) + str(bytes_of(value)).rjust(11)
               + "  " + class_of(value).ljust(10) + " " * 10)
        lines.append(row)
    I.write("\n".join(lines) + "\n\n")
    return None


@builtin("exist")
def bi_exist(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    name = text(args[0])
    if name in I.vars:
        return 1.0
    if (I.folder / f"{name}.m").is_file() or name in I.functions:
        return 2.0
    if name in I.builtins:
        return 5.0 if name.islower() else 2.0
    return 0.0


@builtin("isvarname")
def bi_isvarname(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    if not is_text(args[0]):
        return False
    name = text(args[0])
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name)) and name not in MATLAB_KEYWORDS


@builtin("iskeyword")
def bi_iskeyword(I: Any, args: list[Any], nargout: int) -> Any:
    if not args:
        return cellstr_of(MATLAB_KEYWORDS, column=True)
    return text(args[0]) in MATLAB_KEYWORDS


@builtin("nargin")
def bi_nargin(I: Any, args: list[Any], nargout: int) -> Any:
    return float(I.vars.nargin)


@builtin("nargout")
def bi_nargout(I: Any, args: list[Any], nargout: int) -> Any:
    return float(I.vars.nargout)


@builtin("deal")
def bi_deal(I: Any, args: list[Any], nargout: int) -> Any:
    count = max(nargout, 1)
    if len(args) == 1:
        return [args[0]] * count
    if len(args) != count:
        raise MatlabError("deal: nargin > 1 and nargin != nargout")
    return list(args)


# ---------- errores ----------

def _error_parts(args: list[Any]) -> tuple[str, str]:
    if len(args) == 1 and isinstance(args[0], MStruct):
        d = args[0].data.flat[0]
        return text(d.get("message", make_char(""))), text(d.get("identifier", make_char("")))
    if not args:
        raise MatlabError("Not enough input arguments.", "MATLAB:minrhs")
    first = chars_of(args[0])
    if len(args) > 1 and IDENTIFIER_RE.match(first):
        return format_printf(chars_of(args[1]), _printf_atoms(args[2:])), first
    if len(args) == 1:
        return first, ""
    return format_printf(first, _printf_atoms(args[1:])), ""


@builtin("error")
def bi_error(I: Any, args: list[Any], nargout: int) -> Any:
    message, identifier = _error_parts(args)
    raise MatlabError(message, identifier)


@builtin("warning")
def bi_warning(I: Any, args: list[Any], nargout: int) -> Any:
    if not args:
        return None
    first = chars_of(args[0])
    if first in ("on", "off", "query", "error", "backtrace") or (len(args) == 2 and first in ("on", "off")):
        return None
    if len(args) > 1 and IDENTIFIER_RE.match(first):
        I.warn(format_printf(chars_of(args[1]), _printf_atoms(args[2:])), first)
    else:
        I.warn(format_printf(first, _printf_atoms(args[1:])) if len(args) > 1 else first)
    return None


@builtin("lastwarn")
def bi_lastwarn(I: Any, args: list[Any], nargout: int) -> Any:
    return make_char(I.lastwarn)


@builtin("assert")
def bi_assert(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    if truthy(args[0]):
        return None
    if len(args) == 1:
        raise MatlabError("Assertion failed.", "")
    if len(args) == 2:
        raise MatlabError(chars_of(args[1]), "")
    raise MatlabError(format_printf(chars_of(args[1]), _printf_atoms(args[2:])), "")


@builtin("MException")
def bi_mexception(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 2)
    identifier = chars_of(args[0])
    message = format_printf(chars_of(args[1]), _printf_atoms(args[2:]))
    return MStruct.scalar({
        "identifier": make_char(identifier),
        "message": make_char(message),
        "stack": MStruct.scalar({"file": make_char(""), "name": make_char(""), "line": np.array([[0.0]])}),
    })


@builtin("rethrow", "throw", "throwAsCaller")
def bi_rethrow(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    message, identifier = _error_parts(args)
    raise MatlabError(message, identifier)


# ---------- evaluación y funciones ----------

@builtin("feval")
def bi_feval(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1)
    return I.call_function(args[0], list(args[1:]), nargout)


@builtin("func2str")
def bi_func2str(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 1)
    f = args[0]
    if not isinstance(f, MFunc):
        raise MatlabError("func2str: FCN_HANDLE argument must be a valid function handle.")
    return make_char(f.text if f.body is not None else (f.name or ""))


@builtin("str2func")
def bi_str2func(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    source = chars_of(args[0])
    if source.startswith("@"):
        return I.eval_text_value(source)
    return MFunc(source)


@builtin("eval")
def bi_eval(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    source = chars_of(args[0])
    if nargout > 0:
        return I.eval_text_value(source)
    try:
        I.run_source(source)
    except MatlabError:
        if len(args) < 2:
            raise
        I.run_source(chars_of(args[1]))
    return None


@builtin("evalc")
def bi_evalc(I: Any, args: list[Any], nargout: int) -> Any:
    nargchk(args, 1, 2)
    saved = I.segments
    I.segments = []
    try:
        I.run_source(chars_of(args[0]))
        captured = "".join(seg["text"] for seg in I.segments if seg["kind"] != "err")
    finally:
        I.segments = saved
    return make_char(captured)

