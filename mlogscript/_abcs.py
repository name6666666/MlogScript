from __future__ import annotations
from abc import ABC, abstractmethod
from typing import NamedTuple


class ExprCode(NamedTuple):
    previous_code: list[str]
    reference: str

class Expr(ABC):
    @abstractmethod
    def expr_code(self, var_name: str) -> ExprCode:
        ...

class Stmt(ABC):
    @abstractmethod
    def generate(self, *args: Expr) -> list[str]:
        ...
