import { acceptCompletion } from '@codemirror/autocomplete';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { python } from '@codemirror/lang-python';
import { foldGutter, indentUnit } from '@codemirror/language';
import { type Diagnostic, linter, lintGutter } from '@codemirror/lint';
import { EditorState, Range, StateEffect, StateField } from '@codemirror/state';
import { oneDark } from '@codemirror/theme-one-dark';
import type { DecorationSet } from '@codemirror/view';
import { Decoration, drawSelection, EditorView, keymap, lineNumbers } from '@codemirror/view';
import { useEffect, useRef } from 'react';
import type { Diagnostic as BackendDiagnostic, StateVariable } from '../../canvas/types';
import {
  buildAutocompletionExtension,
  findFunctionAt,
  getFoldEffectsForFunctions,
  resolveHighlightLineRange,
} from '../../domain/code/ast';

const setSelectedItemEffect = StateEffect.define<string | null>();

const selectionField = StateField.define<string | null>({
  create: () => null,
  update: (value, tr) => {
    for (const effect of tr.effects) {
      if (effect.is(setSelectedItemEffect)) {
        return effect.value;
      }
    }
    return value;
  }
});

function buildDecorations(state: EditorState) {
  const nodeId = state.field(selectionField);
  if (!nodeId) return Decoration.none;

  const range = resolveHighlightLineRange(state, nodeId);
  if (!range) return Decoration.none;

  const { highlightStart, highlightEnd } = range;

  const decorations: Range<Decoration>[] = [];
  for (let l = highlightStart; l <= highlightEnd; l++) {
    const line = state.doc.line(l);
    const className = highlightStart === highlightEnd ? 'cm-editable-line-single'
      : l === highlightStart ? 'cm-editable-line-start'
        : l === highlightEnd ? 'cm-editable-line-end'
          : 'cm-editable-line-middle';

    decorations.push(
      Decoration.line({ attributes: { class: className } }).range(line.from)
    );
  }
  return Decoration.set(decorations, true);
}

const readOnlyField = StateField.define<DecorationSet>({
  create: (state) => buildDecorations(state),
  update: (value, tr) => {
    const oldSelection = tr.startState.field(selectionField);
    const newSelection = tr.state.field(selectionField);
    if (tr.docChanged || oldSelection !== newSelection) {
      return buildDecorations(tr.state);
    }
    return value.map(tr.changes);
  },
  provide: (f) => EditorView.decorations.from(f),
});

const editorTheme = EditorView.theme({
  '&': {
    height: '100%',
    flexGrow: 1,
    fontSize: '13px',
    fontFamily: 'Consolas, Menlo, Monaco, "Courier New", monospace',
    backgroundColor: '#1e1e1e !important',
  },
  '.cm-scroller': { overflow: 'auto' },
  '.cm-gutters': {
    backgroundColor: '#1e1e1e !important',
    borderRight: '1px solid var(--gray-5)',
  },
  '.cm-line': {
    borderLeft: '3px solid transparent',
    borderRight: '3px solid transparent',
    borderTop: '1px dashed transparent',
    borderBottom: '1px dashed transparent',
  },
  '.cm-editable-line-start, .cm-editable-line-middle, .cm-editable-line-end, .cm-editable-line-single': {
    borderLeftColor: 'var(--iris-9)',
    borderRightColor: 'var(--iris-9)',
    backgroundColor: 'rgba(59, 130, 246, 0.015) !important',
  },
});

interface UseCodeMirrorProps {
  code: string;
  variables: StateVariable[];
  selectedNodeId: string | null;
  diagnostics: BackendDiagnostic[];
  setSelectedNodeId: (nodeId: string | null) => void;
}

export function useCodeMirror({
  code,
  variables,
  selectedNodeId,
  diagnostics,
  setSelectedNodeId,
}: UseCodeMirrorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);

  useEffect(() => {
    if (viewRef.current) {
      const state = viewRef.current.state;
      if (state.doc.toString() !== code) {
        viewRef.current.dispatch({
          changes: { from: 0, to: state.doc.length, insert: code },
        });
      }
    }
  }, [code]);

  useEffect(() => {
    if (viewRef.current) {
      const currentSelection = viewRef.current.state.field(selectionField);

      if (currentSelection !== selectedNodeId) {
        viewRef.current.dispatch({
          effects: setSelectedItemEffect.of(selectedNodeId),
        });
      }

      const effects = getFoldEffectsForFunctions(viewRef.current.state, selectedNodeId);
      if (effects.length > 0) {
        viewRef.current.dispatch({ effects });
      }
    }
  }, [selectedNodeId]);

  useEffect(() => {
    if (!containerRef.current) return;

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.selectionSet) {
        const pos = update.state.selection.main.head;
        const activeFn = findFunctionAt(update.state, pos);
        const activeFnName = activeFn ? activeFn.name : null;

        setSelectedNodeId(activeFnName);
      }
    });

    const cmLinter = linter((view) => {
      const cmDiags: Diagnostic[] = [];
      for (const d of diagnostics) {
        try {
          const row = Math.max(1, Math.min(d.line, view.state.doc.lines));
          const line = view.state.doc.line(row);
          const col = Math.max(0, Math.min(d.column - 1, line.length));
          const from = line.from + col;
          cmDiags.push({
            from,
            to: Math.min(from + 1, line.to),
            severity: d.severity,
            message: `[${d.code}] ${d.message}`,
          });
        } catch {
          // ignore mapping bounds error
        }
      }
      return cmDiags;
    });

    const state = EditorState.create({
      doc: code,
      extensions: [
        EditorState.readOnly.of(true),
        lineNumbers(),
        history(),
        keymap.of([
          { key: 'Tab', run: acceptCompletion },
          indentWithTab,
          ...defaultKeymap,
          ...historyKeymap,
        ]),
        python(),
        drawSelection(),
        oneDark,
        foldGutter(),
        buildAutocompletionExtension(variables),
        cmLinter,
        lintGutter(),
        selectionField,
        readOnlyField,
        updateListener,
        EditorState.tabSize.of(4),
        indentUnit.of('    '),
        editorTheme,
      ],
    });

    const view = new EditorView({
      state,
      parent: containerRef.current,
    });

    viewRef.current = view;

    const initialEffects = getFoldEffectsForFunctions(view.state, selectedNodeId);
    if (initialEffects.length > 0) {
      view.dispatch({ effects: initialEffects });
    }

    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagnostics]);

  return {
    containerRef,
    viewRef,
  };
}
