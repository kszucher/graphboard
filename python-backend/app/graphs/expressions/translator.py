from __future__ import annotations

import ast

from app.exceptions import ValidationError


class PolarsToPythonTransformer(ast.NodeTransformer):
    """AST Transformer to compile Polars-style expression strings into Python expression strings."""

    def __init__(self, valid_variables: set[str] | None = None):
        self.valid_variables = valid_variables

    def visit_Call(self, node: ast.Call) -> ast.AST:
        # 1. Handle col("var_name") variable references
        if isinstance(node.func, ast.Name) and node.func.id == "col":
            if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                raise ValidationError(
                    "col() must be called with a single string argument representing the variable name."
                )
            var_name = node.args[0].value
            if self.valid_variables is not None and var_name not in self.valid_variables:
                raise ValidationError(f"Variable '{var_name}' is not defined in the graph state.")
            return ast.Name(id=var_name, ctx=ast.Load())

        # 2. Handle chained methods: col("x").eq(5) or col("x").len()
        if isinstance(node.func, ast.Attribute):
            left_node = self.visit(node.func.value)
            method = node.func.attr

            comparison_ops = {
                "eq": ast.Eq,
                "ne": ast.NotEq,
                "lt": ast.Lt,
                "gt": ast.Gt,
                "lte": ast.LtE,
                "gte": ast.GtE,
                "is_in": ast.In,
            }
            if method in comparison_ops:
                if len(node.args) != 1:
                    raise ValidationError(f"Method '{method}' requires exactly one argument.")
                right_node = self.visit(node.args[0])
                return ast.Compare(left=left_node, ops=[comparison_ops[method]()], comparators=[right_node])

            if method == "len":
                if node.args:
                    raise ValidationError("Method 'len' does not accept arguments.")
                return ast.Call(func=ast.Name(id="len", ctx=ast.Load()), args=[left_node], keywords=[])

            if method in {"str", "int", "float", "bool"}:
                if node.args:
                    raise ValidationError(f"Method '{method}' does not accept arguments.")
                return ast.Call(func=ast.Name(id=method, ctx=ast.Load()), args=[left_node], keywords=[])

            # Allow choice / sample calls on random: random.choice(...)
            if method in {"choice", "sample"} and isinstance(left_node, ast.Name) and left_node.id == "random":
                return ast.Call(
                    func=ast.Attribute(value=ast.Name(id="random", ctx=ast.Load()), attr=method, ctx=ast.Load()),
                    args=[self.visit(arg) for arg in node.args],
                    keywords=[],
                )

            raise ValidationError(f"Unsupported method or attribute call: '.{method}()'")

        # 3. Handle allowed top-level function calls: str(), len(), etc.
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in {"str", "int", "float", "bool", "len"}:
                return ast.Call(
                    func=ast.Name(id=func_name, ctx=ast.Load()),
                    args=[self.visit(arg) for arg in node.args],
                    keywords=[],
                )

        raise ValidationError("Unsupported function call structure.")

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        # Convert bitwise operators to logical operators
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.BitOr):
            return ast.BoolOp(op=ast.Or(), values=[left, right])
        if isinstance(node.op, ast.BitAnd):
            return ast.BoolOp(op=ast.And(), values=[left, right])

        # Allow basic arithmetic operators
        allowed_ops = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)
        if type(node.op) in allowed_ops:
            return ast.BinOp(left=left, op=node.op, right=right)

        raise ValidationError(f"Operator '{type(node.op).__name__}' is not allowed.")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Invert):  # ~ operator
            return ast.UnaryOp(op=ast.Not(), operand=operand)
        if type(node.op) in (ast.USub, ast.UAdd):
            return ast.UnaryOp(op=node.op, operand=operand)

        raise ValidationError(f"Unary operator '{type(node.op).__name__}' is not allowed.")

    def visit_Name(self, node: ast.Name) -> ast.AST:
        # Only allow names that represent constants or specific whitelisted modules
        if node.id in {"True", "False", "None", "random"}:
            return node
        raise ValidationError(f"Variable '{node.id}' must be referenced using col('{node.id}').")


def translate_polars_to_python(polars_str: str, valid_variables: set[str] | None = None) -> str:
    """Parses a Polars-style expression and compiles/translates it to standard Python syntax.

    Raises ValidationError if any syntax or semantic constraints are violated.
    """
    if not polars_str.strip():
        raise ValidationError("Expression cannot be empty.")

    try:
        tree = ast.parse(polars_str.strip(), mode="eval")
        transformer = PolarsToPythonTransformer(valid_variables)
        new_tree = transformer.visit(tree)
        return ast.unparse(new_tree).strip()
    except SyntaxError as e:
        raise ValidationError(f"Invalid Polars expression syntax: {e.msg}")
    except Exception as e:
        if isinstance(e, ValidationError):
            raise e
        raise ValidationError(f"Error compiling Polars expression: {str(e)}")
