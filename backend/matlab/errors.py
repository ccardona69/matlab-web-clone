"""Errores del lenguaje con los mensajes e identificadores que usa MATLAB."""

from __future__ import annotations


class MatlabError(Exception):
    """Error en tiempo de ejecución visible para el usuario (equivale a MException)."""

    def __init__(self, message: str, identifier: str = "", where: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.identifier = identifier
        self.where = where

    def render(self) -> str:
        if self.where:
            return f"Error using {self.where}\n{self.message}"
        return self.message


class MatlabSyntaxError(MatlabError):
    def __init__(self, message: str, line: int = 0, col: int = 0, identifier: str = "MATLAB:parse") -> None:
        super().__init__(message, identifier)
        self.line = line
        self.col = col

    def render(self) -> str:
        return f"Error: {self.message}"


def unrecognized(name: str) -> MatlabError:
    return MatlabError(f"Unrecognized function or variable '{name}'.", "MATLAB:UndefinedFunction")


def incompatible_sizes() -> MatlabError:
    return MatlabError("Arrays have incompatible sizes for this operation.", "MATLAB:sizeDimensionsMustMatch")


def matmul_dims() -> MatlabError:
    return MatlabError(
        "Incorrect dimensions for matrix multiplication. Check that the number of columns in the first "
        "matrix matches the number of rows in the second matrix. To operate on each element of the matrix "
        "individually, use TIMES (.*) for elementwise multiplication.",
        "MATLAB:innerdim",
    )


def index_exceeds(limit: int, position: int | None = None) -> MatlabError:
    if position is None:
        return MatlabError(
            f"Index exceeds the number of array elements. Index must not exceed {limit}.",
            "MATLAB:badsubscript",
        )
    return MatlabError(
        f"Index in position {position} exceeds array bounds. Index must not exceed {limit}.",
        "MATLAB:badsubscript",
    )


def bad_index() -> MatlabError:
    return MatlabError(
        "Array indices must be positive integers or logical values.", "MATLAB:badsubscript"
    )


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


class ReturnSignal(Exception):
    pass
