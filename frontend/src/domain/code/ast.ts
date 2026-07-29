import { foldEffect, syntaxTree, unfoldEffect } from '@codemirror/language';
import { EditorState, type StateEffect } from '@codemirror/state';

// Helper to collect fold/unfold effects for all functions based on selectedNodeId
export function getFoldEffectsForFunctions(
  state: EditorState,
  selectedNodeId: string | null
): StateEffect<unknown>[] {
  const docStr = state.doc.toString();
  const effects: StateEffect<unknown>[] = [];
  syntaxTree(state).iterate({
    enter(node) {
      if (node.name === 'FunctionDefinition') {
        const nameNode = node.node.getChild('VariableName');
        if (nameNode) {
          const fnName = docStr.slice(nameNode.from, nameNode.to);
          const body = node.node.getChild('Body');
          if (body) {
            const isSelected = fnName === selectedNodeId;
            if (isSelected) {
              effects.push(unfoldEffect.of({ from: body.from, to: body.to }));
            } else {
              effects.push(foldEffect.of({ from: body.from, to: body.to }));
            }
          }
        }
      }
    }
  });
  return effects;
}

// Helper to find a function definition enclosing a specific position
export function findFunctionAt(state: EditorState, pos: number): { name: string; from: number; to: number } | null {
  let result: { name: string; from: number; to: number } | null = null;
  const docStr = state.doc.toString();
  syntaxTree(state).iterate({
    enter(node) {
      if (node.name === 'FunctionDefinition') {
        if (pos >= node.from && pos <= node.to) {
          const nameNode = node.node.getChild('VariableName');
          if (nameNode) {
            result = {
              name: docStr.slice(nameNode.from, nameNode.to),
              from: node.from,
              to: node.to
            };
          }
        }
      }
    }
  });
  return result;
}

function findFunctionByName(state: EditorState, name: string): { from: number; to: number } | null {
  let result: { from: number; to: number } | null = null;
  const docStr = state.doc.toString();
  const lowerName = name.toLowerCase();

  syntaxTree(state).iterate({
    enter(node) {
      if (node.name === 'FunctionDefinition') {
        const nameNode = node.node.getChild('VariableName');
        if (nameNode && docStr.slice(nameNode.from, nameNode.to) === name) {
          result = { from: node.from, to: node.to };
        }
      } else if (node.name === 'ClassDefinition' && (lowerName === 'definer' || lowerName.startsWith('definer'))) {
        const nameNode = node.node.getChild('VariableName');
        if (nameNode && docStr.slice(nameNode.from, nameNode.to) === 'State') {
          result = { from: node.from, to: node.to };
        }
      }
    }
  });
  return result;
}

// Helper to resolve the line highlights range for an editable function range
export function resolveHighlightLineRange(
  state: EditorState,
  nodeId: string
): { highlightStart: number; highlightEnd: number } | null {
  const fn = findFunctionByName(state, nodeId);
  if (!fn) return null;

  const startLine = state.doc.lineAt(fn.from).number;
  const endLine = state.doc.lineAt(fn.to).number;
  return { highlightStart: startLine, highlightEnd: endLine };
}
