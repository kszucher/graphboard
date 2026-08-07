from __future__ import annotations

import ast

from app.exceptions import ValidationError


def parse_expression(expr_str: str | None) -> str | None:
    """Parses a Python expression string to validate its syntax.

    Returns the clean string or None. Raises ValidationError if syntax is invalid.
    """
    if expr_str is None:
        return None

    clean_str = expr_str.strip()
    if not clean_str:
        return None

    try:
        ast.parse(clean_str, mode="eval")
        return clean_str
    except SyntaxError as e:
        raise ValidationError(f"Invalid expression syntax in '{clean_str}': {e.msg}")
    except ValueError as e:
        raise ValidationError(str(e))


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
