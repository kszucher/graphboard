from app.graphs.ast_editor import CodeASTEditor


def test_rename_function_success():
    code = """def old_func(state):
    return state

def other_func():
    pass"""
    editor = CodeASTEditor(code)

    # Rename old_func -> new_func
    assert editor.rename_function("old_func", "new_func") is True

    # Verify modification
    updated_code = editor.get_code()
    assert "def new_func(state):" in updated_code
    assert "def old_func" not in updated_code
    assert "def other_func():" in updated_code  # Unmodified


def test_rename_function_not_found():
    code = """def my_func():
    pass"""
    editor = CodeASTEditor(code)

    # Attempt to rename non-existent function
    assert editor.rename_function("non_existent", "new_func") is False
    assert editor.get_code().strip() == code.strip()


def test_rename_function_invalid_syntax():
    # Code with syntax error
    code = """def broken_func(
    pass"""
    editor = CodeASTEditor(code)

    # AST parsing should fail, making tree None and returning False
    assert editor.tree is None
    assert editor.rename_function("broken_func", "fixed_func") is False
    assert editor.get_code().strip() == code.strip()
