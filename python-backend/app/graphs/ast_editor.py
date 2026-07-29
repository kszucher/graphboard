import ast


class CodeASTEditor:
    """Helper class to perform robust AST-guided modifications on the Python script."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.lines = code.splitlines()
        try:
            self.tree: ast.Module | None = ast.parse(code)
        except Exception:
            self.tree = None

    def rename_function(self, old_name: str, new_name: str) -> bool:
        """Finds a function definition via AST and renames it in the source lines."""
        if not self.tree:
            return False

        for node in self.tree.body:
            match node:
                case ast.FunctionDef(name=name) if name == old_name:
                    line_idx = node.lineno - 1
                    self.lines[line_idx] = self.lines[line_idx].replace(f"def {old_name}", f"def {new_name}", 1)
                    self.code = "\n".join(self.lines)
                    try:
                        self.tree = ast.parse(self.code)
                    except Exception:
                        self.tree = None
                    return True
        return False

    def get_code(self) -> str:
        return "\n".join(self.lines)
