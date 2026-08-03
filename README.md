# Graphboard

**Graphboard** is a visual, logic-driven graph editor for building, compiling, and running **LangGraph** workflows in Python.

Instead of writing complex state machine code manually, Graphboard provides a visual canvas where you design logic using connected nodes and simple conditional rules. Graphboard automatically generates clean, executable Python scripts in real time and validates them instantly on the backend.

### 🚀 Project Status & R&D Evolution
This repository serves as a personal, non-commercial full-stack R&D exploration and engineering showcase for full-stack AI system design. It builds directly upon ideas from a previous project (**Mapboard**), introducing two core architectural evolutions:
* **Backend Stack:** Migrated from Nest.js/Node.js to a Python/FastAPI ecosystem.
* **Execution Strategy:** Direct 1-Layer Node-to-LangGraph AST translation mapping visual primitives 1:1 to executable LangGraph state machines.

*This project serves as a showcase of advanced conversational state control, real-time visual-to-code translation layer design, and complex React/FastAPI architecture.*

---

<img width="1980" height="1080" alt="Graphboard Interface Preview" src="https://github.com/user-attachments/assets/6dcd5b60-4cdf-41ae-8310-8e19c698dc59" />

---

## 💡 How It Works

1. **Build Visually**: Arrange execution nodes (`LOGICAL_ASSIGNER`, `AGENTIC_ASSIGNER`, `LOGICAL_SWITCH`, `AGENTIC_SWITCH`, `INTERRUPT`, `START`, `END`) on an auto-layout canvas.
2. **Define Logic via Expressions**: Assign AST expression conditions to decision slots and state updates to assigner nodes.
3. **Inspect Generated Python Code**: Graphboard deterministically compiles your visual graph into clean Python code using standard `LangGraph` primitive calls (`StateGraph`, `add_node`, `add_conditional_edges`) and `TypedDict` state definitions.
4. **Strict Schema Integrity & Topological Guard**: State variable renames cascade automatically to all referencing nodes/expressions, and variable deletions are strictly blocked if they are referenced. A pre-execution guard validates topological completeness (unset expressions or unconnected nodes) before running the graph.

---

## 🧩 Visual Node Roles & Code Mapping

| Node Type | Category | Role | Generated Python Representation |
| :--- | :--- | :--- | :--- |
| **START** | Sentinel | Entry point of execution flow | Mapped to `START` sentinel: `workflow.add_edge(START, "first_step")` |
| **END** | Sentinel | Exit point / state machine termination | Mapped to `END` sentinel: `workflow.add_edge("last_step", END)` |
| **LOGICAL_ASSIGNER** | Computation | Performs deterministic inline variable assignments | Generated Python function returning updated state dictionary |
| **AGENTIC_ASSIGNER** | Computation | Invokes LLM agents for structured state mutations | Generated Python function calling Groq LLM with Pydantic response format |
| **LOGICAL_SWITCH** | Routing | Evaluates deterministic expression branching logic | Router function evaluating AST expressions, registered via `workflow.add_conditional_edges(...)` |
| **AGENTIC_SWITCH** | Routing | LLM-driven decision routing across slot options | Router function parsing LLM choice output to select outgoing branch |
| **INTERRUPT** | Human & Control | Pauses workflow execution for user payload | Generated Python function calling `langgraph.types.interrupt(...)` |

---

## 📈 Project Progress Tracker (Incremental Phase Backstory)

### Phase 1: Auto-Layout Graph Canvas
* **Programmatic Positioning**: Configured React Flow with disabled manual node dragging, delegating all coordinate calculations to the ELK (Eclipse Layout Kernel) engine.
* **Detour Routing**: Programmatically detected back-edges (feedback loops) and routed connections around node borders to avoid layout distortion.
* **Dynamic Slot Rendering**: Implemented reactive output handles on Switch nodes that sync dynamically via `updateNodeInternals` when slot structures change.

### Phase 2: Specialized Node Operations & State Schemas
* **State Schema Definitions**: Managed workflow state definitions via a dedicated Radix UI state schema editor.
* **Extensible Operations Containers**: Structured execution nodes using decoupled domain models (`definer`, `logical`, `agentic`, `switch`) linked by reference IDs.

### Phase 3: Server Persistence & WebSocket Sync
* **TanStack Query Sync**: Synchronized visual node mutations and layout states with the FastAPI database asynchronously.
* **Unit of Work Event Buffering**: Implemented a FastAPI Unit of Work transaction manager that buffers WebSocket updates to prevent broadcasting data before database commits complete.
* **Canvas Snapshot History**: Added sequential snapshot models to database history rows enabling persistent, server-backed undo/redo actions.

### Phase 4: LangGraph Code Compiler & Runtime
* **Deterministic Code Synthesis**: Created a python AST compilation engine that parses visual nodes and slots into native LangGraph code (`StateGraph`, `START`, `END`, conditional routing).
* **Safe Sandbox Runtime**: Configured a process pool executor to safely execute compiled python workflows on the FastAPI backend, returning terminal execution results.

### Phase 5: Interactive Code Inspector & Strict State Integrity
* **Bidirectional AST Selection**: Traversed CodeMirror 6 and visual canvas nodes to highlight code functions when clicking nodes, and select visual elements when clicking code regions.
* **Strict State Integrity**: Implemented cascading variable renames and blocked deletes of variables referenced in expressions, slots, and assignments.
* **Pre-Execution Completeness Guard**: Refactored the validation system to verify topological completeness (unconnected slots/nodes and unset expressions) only right before running the graph.
* **Read-Only Editor Lock**: Secured generated code viewer in CodeMirror to be read-only while keeping AST-based folding and navigation fully interactive.

### Phase 6: Direct 1-Layer 7-Primitive Compiler Simplification
* **Pydantic Discriminated Union Schema**: Refactored `NodeRead` into per-type models discriminated by `node_type`, containing strictly the 7 1:1 primitive node types (`START`, `END`, `LOGICAL_ASSIGNER`, `AGENTIC_ASSIGNER`, `LOGICAL_SWITCH`, `AGENTIC_SWITCH`, `INTERRUPT`).
* **Direct 1-Layer Compiler**: Simplified code generation into a single-pass `DirectLangGraphCompiler` mapping visual nodes directly into native Python AST statements (`StateGraph`, `add_node`, `add_conditional_edges`).
* **Clean Default Example Map**: Redesigned default trivia workflow to strictly showcase these 7 primitive node types.
* **Offline Spec Generator**: Automated `npm run generate:api` to extract OpenAPI JSON in-memory via `uv` without requiring a live server process.

---

## 🏗️ Architecture Overview

```mermaid
graph TD
    Canvas[Visual React Flow Canvas] -- "Node / Slot AST Mutations" --> API[FastAPI Backend]
    API -- "Enforces Variable Dependencies" --> Operations[Strict State Integrity]
    Canvas -- "Queries /code on Invalidation" --> CodeEP[GET /graphs/graph_id/code]
    CodeEP -- "Synthesizes Python Script" --> Compiler[Direct AST Generator]
    Compiler -- "Generated Code String" --> Sidebar[Read-Only Code Mirror Sidebar]
```

### Key Technical Choices
* **Pure Server State Architecture**: TanStack Query manages API mutations, caching, and server state, while React Flow manages canvas selection state natively.
* **Auto-Layout ONLY (No Drag-and-Drop)**: Coordinates `(x, y)` are computed on the fly by ELK in two phases: unmeasured initial load and deferred measuring on node dimension resizes.
* **String-Based Identifiers**: Node and slot IDs use human-readable strings (e.g. `"step_1"`, `"option_a"`), matching the execution keys in compiled LangGraph workflows.

---

## 🛠️ Tech Stack

* **Frontend**: React 19, TypeScript, React Flow (@xyflow/react), ELKjs, CodeMirror 6, TanStack Query v5, Radix UI.
* **Backend**: Python 3.12+, FastAPI, LangGraph, SQLAlchemy 2.0, Pydantic v2.

---

## 📌 Implementation Gotchas & Quirks

* **Handle Lifecycle (`updateNodeInternals`)**: When slots are added or removed dynamically on switch nodes, React Flow's cached handle locations become stale. We listen to `node.slots` changes in `FlowNode.tsx` to trigger `updateNodeInternals(id)` whenever slot structure updates.
* **CodeMirror Read-Only Guard**: Setting `EditorState.readOnly.of(true)` across CodeMirror locks typing while allowing `@codemirror/language` AST syntax tree iteration to continue driving bidirectional node highlighting and code folding.
* **Cascading Rename & Blocked Delete**: Renaming a defined variable key cascades renames to all referencing expressions (Switch slot expressions, logical assignments, and agentic inputs/outputs). Deleting a defined variable is strictly blocked with a 400 Bad Request error if any references remain in expressions or assignments.
* **State Schema Integration**: State schema variables are declared in a dedicated `state` section of the JSON graph data separate from the nodes/edges, allowing for a cleaner compilation from visual topology to executable LangGraph code.
* **UoW Transaction Timing & Context Manager**: FastAPI dependency teardown (after `yield`) runs after the HTTP response has been sent. To prevent race conditions where the client refetches data (like generated code) before the database commit completes, all mutating route endpoints must explicitly manage transaction boundaries using `async with uow:` context blocks to guarantee commits are complete before returning the response.
* **Discriminated Union Node Read Schema**: Node instances use a Pydantic `Annotated` discriminated union (`NodeRead = Annotated[StartNode | EndNode | LogicalAssignerNode | ..., Field(discriminator='node_type')]`). Each concrete type carries only relevant fields without nullables or sparse fields, and `slots` are strictly absent on sequential step types.
* **Direct 1-Layer Compiler Pipeline**: Compilation maps visual node models (`GraphFlowData`) directly to Python AST statements (`StateGraph`, `add_node`, `add_conditional_edges`). Node-to-Langgraph mapping is 1:1 without intermediate canonical transformations.
* **Generated OpenAPI Artifact (`openapi.json`)**: `openapi.json` is a transient intermediate artifact generated on the fly via `uv` during `npm run generate:api` to produce TypeScript definitions (`src/api/generated/schema.ts`). Never read, edit, or commit `openapi.json` manually; it is untracked in `.gitignore`.
