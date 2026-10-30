"""Exact arithmetic for the assistant: "calculate" evaluates a plain expression with Decimal.

Only numbers, + - * / % **, parentheses and round/min/max/abs are allowed; anything else is refused.
The expression is parsed with `ast` and walked by hand; nothing is ever passed to eval().
"""
from __future__ import annotations

import ast
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation, localcontext

MAX_LENGTH = 300
MAX_EXPONENT = 100
MAX_NODES = 200
RESULT_PLACES = Decimal("0.000001")


class CalculationError(ValueError):
    pass


_BINARY = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Mod: lambda a, b: a % b,
}


def _round(x: Decimal, places: Decimal = Decimal(0)) -> Decimal:
    if places != places.to_integral_value() or not 0 <= places <= 10:
        raise CalculationError("round() places must be a whole number from 0 to 10.")
    return x.quantize(Decimal(1).scaleb(-int(places)), rounding=ROUND_HALF_UP)


_FUNCTIONS = {
    "round": (_round, 1, 2),
    "abs": (lambda x: abs(x), 1, 1),
    "min": (lambda *xs: min(xs), 1, 20),
    "max": (lambda *xs: max(xs), 1, 20),
}


def _eval(node) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow):
            if abs(right) > MAX_EXPONENT:
                raise CalculationError("Exponent is too large.")
            return left**right
        op = _BINARY.get(type(node.op))
        if op is None:
            raise CalculationError("Only + - * / % ** are allowed.")
        return op(left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        spec = _FUNCTIONS.get(node.func.id)
        if spec is None:
            raise CalculationError(f"Unknown function '{node.func.id}'. Use round, abs, min or max.")
        fn, lo, hi = spec
        if not lo <= len(node.args) <= hi:
            raise CalculationError(f"{node.func.id}() takes {lo} to {hi} values.")
        return fn(*[_eval(a) for a in node.args])
    raise CalculationError("Only numbers, + - * / % **, parentheses and round/abs/min/max are allowed.")


def calculate(expression: str) -> str:
    """The result as plain decimal text (never scientific notation), to at most 6 decimal places."""
    if not isinstance(expression, str) or not expression.strip():
        raise CalculationError("Give an expression, like (1200 + 350) * 1.2.")
    if len(expression) > MAX_LENGTH:
        raise CalculationError("That expression is too long.")
    # Commas separate function arguments, so numbers must be written without thousands separators.
    cleaned = expression.replace("×", "*").replace("÷", "/")
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError:
        raise CalculationError("That isn't a valid expression.")
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise CalculationError("That expression is too long.")
    with localcontext() as ctx:
        ctx.prec = 34
        ctx.traps[DivisionByZero] = True
        try:
            result = _eval(tree)
        except (DivisionByZero, ZeroDivisionError):
            raise CalculationError("Division by zero.")
        except InvalidOperation:
            raise CalculationError("That calculation isn't defined.")
        if not result.is_finite():
            raise CalculationError("The result isn't a finite number.")
        return format(result.quantize(RESULT_PLACES, rounding=ROUND_HALF_UP).normalize(), "f")
