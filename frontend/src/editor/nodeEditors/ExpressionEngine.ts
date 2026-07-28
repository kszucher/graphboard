import type { ASTExpression } from '../../canvas/types';

export type DraftStep = 'target' | 'operand_type_choice' | 'operand_input' | 'operator_or_save';

export type DraftToken =
  | { kind: 'var'; varKey: string }
  | { kind: 'val'; value: unknown; valType?: 'string' | 'number' | 'boolean' | 'float' }
  | { kind: 'op'; op: string };

export const ARITHMETIC_OPERATORS: Array<'+' | '-' | '*' | '/'> = ['+', '-', '*', '/'];
export const COMPARISON_OPERATORS: Array<'==' | '!=' | '>' | '<' | '>=' | '<='> = [
  '==',
  '!=',
  '>',
  '<',
  '>=',
  '<=',
];

export const PYTHON_KEYWORDS = new Set([
  'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
  'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import',
  'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
]);

/**
 * Validates variable keys against Python syntax and reserved keywords.
 */
export function validateVariableName(key: string, existingKeys: Set<string>): string | null {
  const trimmed = key.trim();
  if (!trimmed) return 'Variable name cannot be empty.';
  if (!/^[a-z_][a-z0-9_]*$/.test(trimmed)) {
    return 'Must be valid snake_case (lowercase letters, numbers, underscores).';
  }
  if (PYTHON_KEYWORDS.has(trimmed)) {
    return `'${trimmed}' is a Python reserved keyword.`;
  }
  if (existingKeys.has(trimmed)) {
    return `Variable '${trimmed}' already exists in graph state schema.`;
  }
  return null;
}

/**
 * Coerces raw string input into typed values based on state schema variable type.
 */
export function coerceTypedValue(
  type: 'boolean' | 'string' | 'number' | 'float',
  rawValue: string
): unknown {
  if (type === 'number') return parseInt(rawValue || '0', 10) || 0;
  if (type === 'float') return parseFloat(rawValue || '0.0') || 0.0;
  if (type === 'boolean') return rawValue === 'true';
  return rawValue;
}

/**
 * Computes chip styling matching CodeMirror 6 syntax color themes.
 */
export function getTokenStyle(chip: {
  kind: 'var' | 'op' | 'val';
  valType?: 'string' | 'number' | 'boolean' | 'float';
  value?: unknown;
}) {
  const common = {
    backgroundColor: 'transparent',
    color: '#ffffff',
    fontWeight: '600',
    borderRadius: '12px',
    padding: '2px 10px',
    fontSize: '12px',
    lineHeight: '16px',
    fontFamily: 'monospace',
    flexShrink: 0,
  };

  if (chip.kind === 'var') {
    return { ...common, border: '1.5px solid #e06c75' };
  }
  if (chip.kind === 'op') {
    return { ...common, border: '1.5px solid #61afef' };
  }
  const v = chip.value;
  if (typeof v === 'number' || chip.valType === 'number' || chip.valType === 'float') {
    return { ...common, border: '1.5px solid #e5a95d' };
  }
  return { ...common, border: '1.5px solid #98c379' };
}

export const TARGET_TOKEN_STYLE = {
  backgroundColor: 'transparent',
  border: '1.5px solid #e06c75',
  color: '#ffffff',
  fontWeight: '600',
  fontFamily: 'monospace',
  padding: '2px 10px',
  borderRadius: '12px',
  fontSize: '12px',
  flexShrink: 0,
};

/**
 * Formats an ASTExpression tree into static visual token chips for display.
 */
export function formatAstToChips(
  expr: ASTExpression | null | undefined
): Array<{ kind: 'var' | 'op' | 'val'; label: string; value?: unknown }> {
  if (!expr) return [];
  if (expr.kind === 'literal') {
    return [{ kind: 'val', label: String(expr.value ?? 0), value: expr.value }];
  }
  if (expr.kind === 'stateRef') {
    return [{ kind: 'var', label: expr.varKey }];
  }
  if (expr.kind === 'binaryOp') {
    const left = formatAstToChips(expr.left);
    const opChip = { kind: 'op' as const, label: expr.op };
    const right = formatAstToChips(expr.right);
    return [...left, opChip, ...right];
  }
  return [];
}

/**
 * Constructs a binaryOp / literal / stateRef ASTExpression tree from draft workbench tokens.
 */
export function tokensToAst(tokens: DraftToken[], defaultTargetKey: string): ASTExpression | null {
  if (tokens.length === 0) return null;

  const tokenToAstNode = (t: DraftToken): ASTExpression => {
    if (t.kind === 'var') {
      return { kind: 'stateRef', varKey: t.varKey || defaultTargetKey } as ASTExpression;
    }
    if (t.kind === 'val') {
      return { kind: 'literal', value: t.value } as ASTExpression;
    }
    return { kind: 'literal', value: 0 } as ASTExpression;
  };

  let leftAst = tokenToAstNode(tokens[0]);

  for (let i = 1; i < tokens.length; i++) {
    const token = tokens[i];
    if (token.kind === 'op') {
      const op = token.op;
      const nextOperandToken = tokens[i + 1];
      const rightAst = nextOperandToken
        ? tokenToAstNode(nextOperandToken)
        : ({ kind: 'literal', value: 0 } as ASTExpression);

      leftAst = {
        kind: 'binaryOp',
        op: op as Extract<ASTExpression, { kind: 'binaryOp' }>['op'],
        left: leftAst,
        right: rightAst,
      } as ASTExpression;

      if (nextOperandToken) i++;
    }
  }

  return leftAst;
}
