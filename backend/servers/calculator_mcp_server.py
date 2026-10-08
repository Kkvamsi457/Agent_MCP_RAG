import ast
import math
import operator as op

from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Calculator")


class CalculatorResult(BaseModel):
    expression: str
    result: str
    status: str


_ALLOWED_BINOPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.Mod: op.mod,
}
_ALLOWED_UNARY = {ast.UAdd: op.pos, ast.USub: op.neg}
_ALLOWED_FUNCS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "exp": math.exp,
}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
        return _ALLOWED_UNARY[type(node.op)](_eval(node.operand))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _ALLOWED_FUNCS
    ):
        return _ALLOWED_FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("Unsupported calculator expression")


@mcp.tool()
def calculate_expression(expression: str) -> CalculatorResult:
    """Safely evaluate a supported arithmetic or mathematical expression."""
    tree = ast.parse(expression, mode="eval")
    value = _eval(tree)
    return CalculatorResult(
        expression=expression,
        result=str(value),
        status="success",
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
