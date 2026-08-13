from __future__ import annotations

import ast

from app.exceptions import ValidationError
from app.graphs.expressions.schemas import ComparisonExpression as ComparisonExpression
from app.graphs.expressions.schemas import Expression as Expression


class ExpressionValidator(ast.NodeVisitor):
    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id not in {"str", "int", "float", "bool", "len"}:
                raise ValidationError(
                    f"Function call '{node.func.id}' is not allowed. "
                    "Only str, int, float, bool, len, random.choice, random.sample are allowed."
                )
        elif isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "random"
                and node.func.attr in {"choice", "sample"}
            ):
                pass
            else:
                raise ValidationError("Only random.choice and random.sample module calls are allowed.")
        else:
            raise ValidationError("Unsupported function call structure.")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id == "random" and node.attr in {"choice", "sample"}:
            pass
        else:
            raise ValidationError(f"Attribute access '{ast.unparse(node)}' is not allowed.")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        allowed_ops = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)
        if not isinstance(node.op, allowed_ops):
            raise ValidationError(f"Operator '{type(node.op).__name__}' is not allowed in basic arithmetic.")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        allowed_ops = (ast.Eq, ast.NotEq, ast.Lt, ast.Gt, ast.LtE, ast.GtE)
        for op in node.ops:
            if not isinstance(op, allowed_ops):
                raise ValidationError(f"Comparison operator '{type(op).__name__}' is not allowed.")
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        allowed_ops = (ast.Not, ast.USub, ast.UAdd)
        if not isinstance(node.op, allowed_ops):
            raise ValidationError(f"Unary operator '{type(node.op).__name__}' is not allowed.")
        self.generic_visit(node)


def is_comparison_node(node: ast.AST) -> bool:
    if isinstance(node, (ast.Compare, ast.BoolOp)):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return True
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return True
    return False


def parse_expression(expr_str: str | None) -> str | None:
    """Parses a Python expression string to validate its syntax and safety constraints."""
    if expr_str is None:
        return None

    clean_str = expr_str.strip()
    if not clean_str:
        return None

    try:
        tree = ast.parse(clean_str, mode="eval")
        ExpressionValidator().visit(tree)
        return clean_str
    except SyntaxError as e:
        raise ValidationError(f"Invalid expression syntax in '{clean_str}': {e.msg}")
    except ValueError as e:
        raise ValidationError(str(e))


def parse_comparison_expression(expr_str: str | None) -> str | None:
    """Parses and validates that the expression is a comparison or boolean-routing expression."""
    expr = parse_expression(expr_str)
    if expr is None:
        return None

    tree = ast.parse(expr, mode="eval")
    root = tree.body
    if not is_comparison_node(root):
        raise ValidationError(
            f"Expression '{expr_str}' is not a valid comparison expression (must evaluate to a boolean/comparison)."
        )
    return expr


class NameTransformer(ast.NodeTransformer):
    def __init__(self, valid_keys: set[str]):
        self.valid_keys = valid_keys

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id in self.valid_keys:
            return ast.Call(
                func=ast.Attribute(value=ast.Name(id="state", ctx=ast.Load()), attr="get", ctx=ast.Load()),
                args=[ast.Constant(value=node.id)],
                keywords=[],
            )
        return node


def expression_to_code(expr_str: str | None, valid_keys: set[str], fallback: str = "True") -> str:
    """Converts expression string to Python code, wrapping state variables in state.get() calls."""
    if not expr_str:
        return fallback

    try:
        tree = ast.parse(expr_str.strip(), mode="eval")
        transformer = NameTransformer(valid_keys)
        transformed_tree = transformer.visit(tree)
        return ast.unparse(transformed_tree).strip()
    except Exception:
        return fallback


def get_expression_variables(expr_str: str | None) -> set[str]:
    """Parses the expression string and returns all referenced variable names."""
    if not expr_str:
        return set()
    try:
        tree = ast.parse(expr_str, mode="eval")
        BUILTINS = {"True", "False", "None"}
        variables = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id not in BUILTINS:
                # Exclude module random from variable list
                if node.id != "random":
                    variables.add(node.id)
        return variables
    except Exception:
        return set()


class RenameTransformer(ast.NodeTransformer):
    def __init__(self, old_key: str, new_key: str):
        self.old_key = old_key
        self.new_key = new_key

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id == self.old_key:
            return ast.copy_location(ast.Name(id=self.new_key, ctx=node.ctx), node)
        return node


def rename_expression_variables(expr_str: str | None, old_key: str, new_key: str) -> str | None:
    """Parses the expression string, renames references of old_key to new_key, and returns the updated string."""
    if not expr_str:
        return expr_str
    try:
        tree = ast.parse(expr_str, mode="eval")
        transformer = RenameTransformer(old_key, new_key)
        new_tree = transformer.visit(tree)
        return ast.unparse(new_tree).strip()
    except Exception:
        return expr_str
