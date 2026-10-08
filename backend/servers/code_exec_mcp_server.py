import ast
import contextlib
import io
import math
import operator as op
from typing import Optional

from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Python-Code-Sandbox")


class ExecutionResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    status: str
    return_code: Optional[int] = None
    result: str = ""


_FORBIDDEN = (
    ast.Import,
    ast.ImportFrom,
    ast.With,
    ast.AsyncWith,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.Global,
    ast.Nonlocal,
)

_SAFE_BUILTINS = {
    "print": print,
    "len": len,
    "range": range,
    "sum": sum,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
}


def _validate(tree):
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN):
            raise ValueError(
                "Imports, classes, functions, and context managers are not allowed."
            )
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Dunder names are not allowed.")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Dunder attributes are not allowed.")


@mcp.tool()
def execute_python_code(code: str) -> ExecutionResult:
    """Execute restricted Python code and return stdout, stderr, status, and result."""
    stdout = io.StringIO()
    stderr = io.StringIO()

    try:
        tree = ast.parse(code, mode="exec")
        _validate(tree)

        env = {"math": math}
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(
                compile(tree, "<safe-python>", "exec"),
                {"__builtins__": _SAFE_BUILTINS},
                env,
            )

        visible = {k: v for k, v in env.items() if k != "math"}
        return ExecutionResult(
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
            status="success",
            return_code=0,
            result=str(visible),
        )

    except Exception as exc:
        return ExecutionResult(
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue() or str(exc),
            status="error",
            return_code=1,
            result="",
        )


if __name__ == "__main__":
    mcp.run(transport="stdio")
