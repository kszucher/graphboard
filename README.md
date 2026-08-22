# Graphboard

A personal R&D project: a visual canvas and AI Copilot for designing, compiling, and running **LangGraph** workflows in Python.

### 🚀 Project Evolution
Second iteration of this idea, building directly on **Mapboard** (a previous client-side visual graph builder in Nest.js/Node.js). Graphboard shifts to a backend-first architecture — the graph is owned and mutated exclusively by the server, with the AI Copilot as the primary interface for modifications: multi-stage planning, dry-run validation, and human-in-the-loop checkpoints before committing any changes. The visual canvas is now a read-only inspector; manual node editing has been removed in favour of the agentic model.

---

<img width="1980" height="1080" alt="Image" src="https://github.com/user-attachments/assets/f4f48fd8-b8b0-465b-b254-2f7efea56cd4" />

---

## 🌟 Core Engineering Highlights
* **Agentic LangGraph Copilot:** Orchestrates modifications using a single-call Planner and deterministic translation LangGraph workflow with human-in-the-loop validation checkpoints.
* **Real-time AST Compiler:** Dynamically compiles the visual graph schema directly into native Python LangGraph code.
* **Transactional Patch Protocol:** Modifies graph topology programmatically via structured `GraphOperation` patches, ensuring referential integrity and cascading updates.
* **Isolated Subprocess Sandbox:** Runs compiled user workflows inside a dedicated spawned subprocess with a hard 5-second timeout, terminating it explicitly to protect the main FastAPI server from infinite loops.

## 💡 How It Works

1. **Natural Language Requests**: The user prompts the Copilot to modify the graph logic (e.g., *"Add a fifty-fifty lifeline"*).
2. **Agentic Patch Generation**: The AI Copilot uses a multi-stage LangGraph workflow to generate a plan, which is executed as a series of structured `GraphOperation` patches (`upsert_node`, `delete_node`, `connect`, etc.).
3. **Strict Schema Integrity Guard**: Before patches are committed, the backend runs dry-run validations, managing cascading variable renames or blocking invalid operations.
4. **LangGraph Code Compiler**: The backend compiles the new graph structure into executable Python code using standard `LangGraph` primitives (`StateGraph`, `add_conditional_edges`, `interrupt`).
5. **WebSocket-Triggered UI Sync**: On patch commit, the backend emits a `GRAPH_UPDATED` event over a WebSocket broker, which triggers the frontend canvas to re-fetch and render the updated graph topology and Python code.

---

## 🧩 Visual Node Roles & Code Mapping

| Node Type | Category | Role | Generated Python Representation |
| :--- | :--- | :--- | :--- |
| **START** | Sentinel | Entry point of execution flow | Mapped to `START` sentinel: `workflow.add_edge(START, "first_step")` |
| **END** | Sentinel | Exit point / state machine termination | Mapped to `END` sentinel: `workflow.add_edge("last_step", END)` |
| **LOGICAL_ASSIGNER** | Computation | Performs deterministic inline variable assignments | Generated Python function returning updated state dictionary |
| **AGENTIC_ASSIGNER** | Computation | Invokes LLM agents for structured state mutations | Generated Python function calling Groq LLM with Pydantic response format |
| **RAG_RETRIEVER** | Computation | Queries Neon Postgres vector database using Hugging Face embeddings | Generated Python function calling `retrieve_documents(...)` |
| **LOGICAL_SWITCH** | Routing | Evaluates deterministic expression branching logic | Router function evaluating AST expressions, registered via `workflow.add_conditional_edges(...)` |
| **AGENTIC_SWITCH** | Routing | LLM-driven decision routing across slot options | Router function parsing LLM choice output to select outgoing branch |
| **INTERRUPT** | Human & Control | Pauses workflow execution for user payload | Generated Python function calling `langgraph.types.interrupt(...)` |

### Node Vocabulary Design Rationale
The six primitive types form a deliberate **2×2 grid, plus one control primitive, plus memory retrieval**:

| | Deterministic | AI-Driven |
| :--- | :--- | :--- |
| **Computation** | `LOGICAL_ASSIGNER` | `AGENTIC_ASSIGNER` |
| **Routing** | `LOGICAL_SWITCH` | `AGENTIC_SWITCH` |
| **Control** | `INTERRUPT` | — |
| **Memory** | `RAG_RETRIEVER` | — |

This covers every fundamental pattern in an agentic state machine: transforming state (deterministically or via LLM), making routing decisions (by expression or by LLM classification), yielding control back to a human, and retrieving grounded context. The vocabulary is intentionally small — small enough that the AI Copilot can reliably generate valid operations, and small enough that each primitive maps cleanly to a known LangGraph construct. Future extensions (e.g. `TOOL_CALL`, `PARALLEL_FAN_OUT`) would fit the same deterministic/agentic axis.

---

## 📈 R&D Progress Tracker

### Phase 1: Auto-Layout Canvas & Persistence
* **ELK-Driven Positioning**: Configured React Flow with programmatically managed node coordinates driven by the ELK (Eclipse Layout Kernel) layout engine.
* **Unified Persistence**: Integrated a FastAPI Unit of Work transaction manager that saves graph snapshots sequentially as a version history, enabling version browsing on the frontend.

### Phase 2: Direct Compiler & Sandbox
* **Discriminated Union Schema**: Structured `NodeRead` into per-type models discriminated by `node_type`, containing only relevant primitive properties.
* **Direct AST Synthesis**: Created a python AST compiler mapping visual nodes directly into Python statements.
* **Subprocess Isolation**: Compiled scripts run in a dedicated spawned subprocess with a hard timeout, preventing infinite loops from hanging the main API thread.

### Phase 3: Coarse-Grained Patch Mutations & Type Safety
* **Consolidated mutations**: Unified topology and operations alterations under the `operations` package (`app/graphs/operations/`) driven by a central pipeline.
* **Discriminator Config Union**: Refactored `UpsertNodeOp` configuration payloads to be dynamically parsed and validated into strongly-typed config models (`LogicalAssignerConfig`, etc.) via Pydantic model validators.
* **AST Expressions Consolidation**: Centralized expression-to-code, variable tracking, and cascading renames into the expression module, deleting duplicate recursive traversals across the codebase.

### Phase 4: Agentic Copilot & Flow Engineering (Active R&D)
* **Single-Call Planner + Deterministic Translation**: A single `planner_node` LLM call produces a fully-specified operation checklist with pre-filled params for every `GraphOperation`. A deterministic `translate_plan_node` converts params directly to Pydantic-validated operations — no intermediate LLM calls, zero hallucination surface.
* **Human-in-the-Loop Interruption**: Configured LangGraph state interrupts (`wait_for_plan_node`, `wait_for_apply_node`) to pause execution at each stage for user review before committing changes.
* **Dry-Run Validation**: Planner-generated patches are validated against the backend's operations engine and AST compiler before being committed. The Copilot is constrained to emit structured operations rather than raw code specifically so this validation step is deterministic and reliable.
* **Design Note**: This constraint (structured ops vs. free-form code) is a deliberate architectural choice — it makes agent output atomically versionable, dry-run-testable, and compiler-safe, at the cost of a fixed primitive vocabulary. The earlier multi-agent (planner → 3 sub-agent LLMs) design was abandoned because sub-agents consistently hallucinated argument values and swapped tool parameters despite receiving pre-filled params.

### 🧠 Copilot Tooling & Architecture Decision Space

GraphBoard's AI Copilot uses a single-turn planner with deterministic translation and dry-run validation. The choice of how the LLM views and mutates the graph was selected after rigorous analysis of architectural paradigms:

| Paradigm / Decision | Status | Technical Rationale |
| :--- | :--- | :--- |
| **Polymorphic Delta Tools with Surgical Switch Patching** | ✅ **CHOSEN (Gold Standard)** | **Optimal.** Consolidates graph operations into 4 core polymorphic tools (`upsert_variable`, `upsert_node`, `upsert_switch_branch`, `reroute_edge`) + `delete_entity`/`rename_entity`. Adds **surgical branch patching** (`upsert_switch_branch`) which eliminates the dangerous silent array erasure failure mode where LLMs omit existing branches when adding a single option. Cuts schema token overhead by 75% and ensures $O(1)$ atomic updates. |
| **Isomorphic YAML Serializer (1:1 Tool Parity)** | ✅ **CHOSEN** | **Optimal.** The prompt serializes current graph state in compact, structured YAML matching the exact fields and shapes of `upsert_node` and `upsert_switch_branch`, providing in-context few-shot learning and zero translation loss in the LLM's context window. |
| **Free-Form Code Generation** | ❌ **REJECTED** | Non-deterministic AST parsing; high risk of hallucinating arbitrary Python standard library functions or third-party packages; breaks reliable bidirectional sync with visual canvas React Flow nodes. |
| **Whole-Graph JSON Snapshot Regeneration** | ❌ **REJECTED** | $O(N)$ token scaling on graph size; on complex 15+ node flows, LLMs suffer from context truncation and frequently drop or corrupt unmentioned nodes/edges. |
| **Disconnected Micro-CRUD Primitives (`connect` + `disconnect` + raw `upsert`)** | ❌ **REJECTED** | Primitive explosion (required 15 tool calls for a 3-node change); high risk of edge handle desynchronization, forgotten branch links, and dangling orphan nodes. |
| **Full-Array Switch Overwrites** | ❌ **REJECTED** | Forcing models to reconstruct all existing switch branches (e.g. 5 lifelines) just to append a new branch causes frontier LLMs to silently drop or rename existing branches. |
| **Open-Key AST Dictionaries (`{"score": {"equals": 10}}`)** | ❌ **REJECTED** | Open dictionary keys (`additionalProperties: true`) leak through JSON Schema to Gemini, causing constrained decoding errors and nested key hallucinations. |
| **Self-Correction Reflection Recovery Loop** | ⏳ **DEFERRED** | Deferred to a subsequent phase to focus exclusively on achieving >95% first-shot zero-shot reliability. |
* **🔮 Next Steps / Active R&D**:
  * **Self-Correction Retry Loops**: Route compiler and dry-run traceback exceptions back into the LangGraph state machine so the LLM planner can auto-correct its operations on validation failure.
  * **Automated Agent Evals**: Set up regression-testing suites and an LLM-as-a-judge eval harness to measure planner accuracy across common graph editing scenarios.

---

## 🏗️ Architecture Overview

```mermaid
graph TD
    %% Styling Classes
    classDef default fill:#1e1e2e,stroke:#cdd6f4,stroke-width:1px,color:#cdd6f4;
    classDef ui fill:#181825,stroke:#cba6f7,stroke-width:1px,color:#cba6f7;
    classDef copilot fill:#181825,stroke:#f9e2af,stroke-width:1.5px,color:#f9e2af;
    classDef backend fill:#181825,stroke:#89b4fa,stroke-width:1px,color:#89b4fa;
    classDef store fill:#181825,stroke:#a6e3a1,stroke-width:1px,color:#a6e3a1;

    User([👤 User]) -->|"Natural language prompt"| Planner["🧠 Planner Node"]
    Planner -->|"Checklist"| Translator["⚡ Translation Node"]
    Translator -->|"GraphOperation patches"| Validator["✅ Dry-run Validator"]
    Validator -->|"Patch applied"| Operations["⚙️ operations/pipeline.py"]
    Operations -->|"New snapshot"| History[("🗄️ Snapshot History")]
    History -->|"Compile"| Compiler["📝 AST Compiler"]
    Compiler -->|"Python script"| Canvas["💻 React Flow Canvas"]
    History -.->|"GRAPH_UPDATED via WebSocket"| Canvas

    class Planner,Translator copilot;
    class Validator,Operations,Compiler backend;
    class History store;
    class Canvas ui;
    class User default;
```

### Key Technical Constraints
* **Transaction-Level Integrity**: Variable referential constraints are validated on every patch. Topological completeness (e.g., unconnected slots) is deferred to execution-time to allow users and AI agents to build graphs incrementally.
* **UoW Transaction Timing**: Endpoints mutating data must manage transaction boundaries using `async with uow:` blocks to ensure SQL writes and event brokers finish before returning HTTP responses.

---

## 🛠️ Tech Stack

* **Frontend**: React 19, TypeScript, React Flow (@xyflow/react), ELKjs, CodeMirror 6, TanStack Query v5, Radix UI.
* **Backend**: Python 3.12+, FastAPI, LangGraph, SQLAlchemy 2.0, Pydantic v2.
