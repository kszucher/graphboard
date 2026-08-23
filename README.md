# Graphboard

A personal R&D project: a visual canvas and AI Copilot for designing, compiling, and running **LangGraph** workflows in Python.

### 🚀 Project Evolution
Second iteration of this idea, building directly on **Mapboard** (a previous client-side visual graph builder in Nest.js/Node.js). Graphboard shifts to a backend-first architecture — the graph is owned and mutated exclusively by the server, with the AI Copilot as the primary interface for modifications: single-call planning, deterministic schema translation, dry-run validation, and self-correction reflection before committing any changes. The visual canvas is now a read-only inspector; manual node editing has been removed in favour of the agentic model.

---

<img width="1980" height="1080" alt="Image" src="https://github.com/user-attachments/assets/f4f48fd8-b8b0-465b-b254-2f7efea56cd4" />

---

## 🌟 Core Engineering Highlights
* **Agentic LangGraph Copilot:** Orchestrates modifications using a single-call Planner, deterministic translation, and dry-run validation with an automated self-correction retry loop.
* **Real-time AST Compiler:** Dynamically compiles the visual graph schema directly into native Python LangGraph code.
* **Transactional Patch Protocol:** Modifies graph topology programmatically via structured `GraphUpdateInput` patches, ensuring referential integrity and cascading updates.
* **Isolated Subprocess Sandbox:** Runs compiled user workflows inside a dedicated spawned subprocess with a hard 5-second timeout, terminating it explicitly to protect the main FastAPI server from infinite loops.

## 💡 How It Works

1. **Natural Language Requests**: The user prompts the Copilot to modify the graph logic (e.g., *"Add a fifty-fifty lifeline"*).
2. **Agentic Patch Generation**: The AI Copilot generates an atomic plan using a structured 5-tool schema (`upsert_variable`, `upsert_node`, `upsert_switch_branch`, `delete_entity`, `rename_entity`), which is deterministically translated into transactional backend patches (`GraphUpdateInput`).
3. **Strict Schema & AST Integrity Guard**: Before patches are committed, the backend runs dry-run validations, checking delta application, topological completeness (`assert_flow_is_complete`), and LangGraph AST compilation with reflection retry on failures.
4. **LangGraph Code Compiler**: The backend compiles the new graph structure into executable Python code using standard `LangGraph` primitives (`StateGraph`, `add_conditional_edges`, `interrupt`).
5. **WebSocket-Triggered UI Sync**: On patch commit, the backend emits a `GRAPH_UPDATED` event over a WebSocket broker, which triggers the frontend canvas to re-fetch and render the updated graph topology and Python code.

---

## 🧩 Visual Node Roles & Code Mapping

| Node Type | Category | Role | Generated Python Representation |
| :--- | :--- | :--- | :--- |
| **START** | Sentinel | Entry point of execution flow | Mapped to `START` sentinel: `workflow.add_edge(START, "first_step")` |
| **END** | Sentinel | Exit point / state machine termination | Mapped to `END` sentinel: `workflow.add_edge("last_step", END)` |
| **LOGICAL_ASSIGNER** | Computation | Performs deterministic inline variable assignments | Generated Python function returning updated state dictionary |
| **AGENTIC_ASSIGNER** | Computation | Invokes LLM agents for structured state mutations | Generated Python function calling Google Gemini with Pydantic response format |
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
* **Subprocess Isolation**: Compiled scripts run in a dedicated spawned subprocess with piped `stdin` communication and hard timeout, preventing infinite loops from hanging the main API thread without Windows command-length restrictions.

### Phase 3: Modular Node Handlers & AST Expression Compilation
* **Unified Node Handlers**: Decomposed mutations into modular, type-safe node handlers under `app/modules/graphs/operations/handlers.py` orchestrated by a functional pipeline.
* **Direct Inlined Expressions**: Expressions are embedded directly on node assignments and switch branches without lookup indirection or entity table stores.
* **AST Expressions Consolidation**: Centralized expression-to-code synthesis, variable tracking, and cascading renames into `app/modules/graphs/schemas/` and `app/modules/graphs/operations/`.


### Phase 4: Agentic Copilot & Flow Engineering (Active R&D)
* **Single-Call Planner + Deterministic Translation**: A single `planner_node` LLM call produces a fully-specified operation checklist with pre-filled params for every mutation (`ApplyGraphPlan`). A deterministic `translate_plan_node` converts params directly to Pydantic-validated operations (`GraphUpdateInput`) — no intermediate LLM calls, zero hallucination surface.
* **Streamlined Pipeline & Dry-Run Validation**: Direct linear execution (`planner_node` $\rightarrow$ `translate_plan_node` $\rightarrow$ `validation_node`). Planner-generated patches are validated against the backend's operations engine and AST compiler before being committed. The Copilot is constrained to emit structured operations rather than raw code specifically so this validation step is deterministic and reliable.
* **Design Note**: This constraint (structured ops vs. free-form code) is a deliberate architectural choice — it makes agent output atomically versionable, dry-run-testable, and compiler-safe, at the cost of a fixed primitive vocabulary. The earlier multi-agent (planner → 3 sub-agent LLMs) design was abandoned because sub-agents consistently hallucinated argument values and swapped tool parameters despite receiving pre-filled params.

### Phase 5: Autonomous Evaluation Harness & Self-Healing Telemetry (Active R&D)
* **10-Tier Millionaire Benchmark**: A graduated 1–10 difficulty evaluation suite based on the default trivia graph, testing progressive game mechanics (Game length, cash prize tracking, walk-away routing, 50:50 lifelines, dynamic difficulty tiers, single-use lifeline enforcement, question switching, guaranteed safety net checkpoints, interactive host interrupts, and full game engine overhaul).
* **ID-Agnostic Topological Grading**: Evaluates mutations deterministically via graph invariant properties (connectivity, branch count deltas, AST comparison expressions, and state variable schemas) without asserting arbitrary LLM-generated node IDs.
* **Self-Healing Telemetry**: Tracks Pass@1 vs. Pass@k recovery rates when compiler/validation errors trigger the reflection feedback loop.
* **CLI Runner & Scorecards**: Run sweeps across models with automatic Markdown reports (`uv run python tests/evals/run_evals.py --model gemini-3.5-flash-lite`).

#### 📊 Baseline Model Scorecard (`gemini-3.5-flash-lite`)

| Level | Difficulty / Focus | Natural User Prompt | Result | Attempts | Duration |
| :---: | :--- | :--- | :---: | :---: | :---: |
| **1** | **Game Length** | *"Let's make the game longer: the player should need 15 correct answers to win instead of 5."* | ✅ **PASS** | 1 (Pass@1) | ~5.5s |
| **2** | **Prize Tracking** | *"Let's add prize money tracking so each correct answer increases the player's cash earnings."* | ✅ **PASS** | 1 (Pass@1) | ~7.7s |
| **3** | **Walk Away Option** | *"Give the player an option to walk away with their current money instead of answering or picking a lifeline."* | ✅ **PASS** | 1 (Pass@1) | ~9.6s |
| **4** | **50:50 Lifeline** | *"Let's add a fifty fifty lifeline."* | ✅ **PASS** | 1 (Pass@1) | ~9.9s |
| **5** | **Difficulty Tiers** | *"Make the questions get progressively harder: easy for the first 4 questions, medium from question 5 to 9, and hard for question 10 and above."* | ✅ **PASS** | 1 (Pass@1) | ~15.6s |
| **6** | **Single-Use Lifelines** | *"Make lifelines single-use so once the player uses phone-a-friend or ask-the-audience, they can't use it again."* | ✅ **PASS** | **2 (Self-Healed)** | ~23.2s |
| **7** | **Switch Question** | *"Add a 'Switch the Question' lifeline that discards the current question and gives the player a brand new one without losing their progress."* | ✅ **PASS** | **2 (Self-Healed)** | ~18.2s |
| **8** | **Guaranteed Safety Nets** | *"Let's account for guaranteed wins after question 5 and 10 while 15 is max win."* | ❌ **FAIL** | 3 (JSON array format) | ~105.8s |
| **9** | **Interactive Host** | *"Add an 'Ask the Host' lifeline where the contestant can ask the host for a tip, receive the host's response, and then return to answer the question."* | ✅ **PASS** | 1 (Pass@1) | ~7.2s |
| **10** | **Full Millionaire Engine** | *"Turn this into the complete Millionaire game: 15 questions to win, guaranteed safety nets after questions 5 and 10, a walk-away option, and three one-time lifelines (50:50, Phone a Friend, Ask the Audience)."* | ❌ **FAIL** | 3 (JSON array format) | ~43.9s |

**Baseline Summary**: **8/10 Passed (80.0%)** | **Pass@1**: 6/10 (60.0%) | **Self-Healing (Pass@2)**: 2/10 (20.0%) | **Avg Duration**: ~12.7s


### 🧠 Copilot Tooling & Architecture Decision Space

GraphBoard's AI Copilot uses a single-turn planner with deterministic translation and dry-run validation. The choice of how the LLM views and mutates the graph was selected after rigorous analysis of architectural paradigms:

| Paradigm / Decision | Status | Technical Rationale |
| :--- | :--- | :--- |
| **Polymorphic Delta Tools with Surgical Switch Patching** | ✅ **CHOSEN (Gold Standard)** | **Optimal.** Consolidates graph mutations into a minimal 5-tool suite: 3 core mutation tools (`upsert_variable`, `upsert_node`, `upsert_switch_branch`) + 2 entity managers (`delete_entity`, `rename_entity`). Supports lightweight partial retargeting (`upsert_node(id, target)`) and graph entrypoint definition (`upsert_node(id="start", target)`), eliminating separate routing tools while providing **surgical branch patching** (`upsert_switch_branch`) to prevent array-erasure failure modes. Cuts schema token overhead by >80% and ensures $O(1)$ atomic updates. |
| **Isomorphic YAML Serializer (1:1 Tool Parity)** | ✅ **CHOSEN** | **Optimal.** The prompt serializes current graph state in compact, structured YAML matching the exact fields and shapes of `upsert_node` and `upsert_switch_branch`, providing in-context few-shot learning and zero translation loss in the LLM's context window. |
| **Orthogonal Data Transformation Expression Algebra** | ✅ **CHOSEN** | **Optimal.** Enriches `LOGICAL_ASSIGNER` with an orthogonal suite of pure deterministic data transformations (Math arithmetic/functions, String template format/join/split, Collections sample/choice/remove/append/length/slice, and Random numbers) without embedding branching/control flow (preserving strict separation where all conditional decisions remain exclusively in Switch nodes). |
| **Free-Form Code Generation** | ❌ **REJECTED** | Non-deterministic AST parsing; high risk of hallucinating arbitrary Python standard library functions or third-party packages; breaks reliable bidirectional sync with visual canvas React Flow nodes. |
| **Whole-Graph JSON Snapshot Regeneration** | ❌ **REJECTED** | $O(N)$ token scaling on graph size; on complex 15+ node flows, LLMs suffer from context truncation and frequently drop or corrupt unmentioned nodes/edges. |
| **Disconnected Micro-CRUD Primitives (`connect` + `disconnect` + raw `upsert`)** | ❌ **REJECTED** | Primitive explosion (required 15 tool calls for a 3-node change); high risk of edge handle desynchronization, forgotten branch links, and dangling orphan nodes. |
| **Full-Array Switch Overwrites** | ❌ **REJECTED** | Forcing models to reconstruct all existing switch branches (e.g. 5 lifelines) just to append a new branch causes frontier LLMs to silently drop or rename existing branches. |
| **Open-Key AST Dictionaries (`{"score": {"equals": 10}}`)** | ❌ **REJECTED** | Open dictionary keys (`additionalProperties: true`) leak through JSON Schema to Gemini, causing constrained decoding errors and nested key hallucinations. |
| **Self-Correction Reflection Recovery Loop** | ✅ **CHOSEN** | **Optimal.** Routes compiler, schema translation, and dry-run validation error tracebacks back into the LangGraph state machine with automatic conversational feedback turns, enabling the LLM planner to auto-correct operation failures across at most 1 retry attempt. |

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
    Planner -->|"apply_graph_plan (Atomic tool)"| Translator["⚡ Translation Node"]
    Translator -->|"GraphUpdateInput patches"| Validator["✅ Dry-run Validator<br/>(Delta + Integrity + AST Compile)"]
    Validator -->|"Self-Correction Retry (attempt <= 1)<br/>Structured Diagnostic Hint"| Planner
    Validator -->|"Validation passed"| Operations["⚙️ operations/pipeline.py"]
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
* **Atomic Plan Generation**: The Copilot Planner is bound to exactly one atomic tool (`apply_graph_plan`) with `mode=ANY`. All graph operations (variables, nodes, switch branches, renames, deletions) are generated as a single atomic JSON transaction, eliminating multi-tool list cutoffs.
* **Validation & Retry Pipeline**: The Copilot validation loop sequentially runs delta patch application, full topological integrity verification (`assert_flow_is_complete`), and LangGraph AST compilation before committing. If any gate fails, structured diagnostic feedback is routed back to the Planner for self-correction.
* **Mutation Tolerance vs. Execution Completeness**: The backend mutation engine tolerates intermediate graph topology states (e.g., unlinked nodes during staged programmatic operations), while graph execution and Copilot output strictly require full topological completeness (`assert_flow_is_complete`).
* **UoW Transaction Timing**: Endpoints mutating data must manage transaction boundaries using `async with uow:` blocks to ensure SQL writes and event brokers finish before returning HTTP responses.

---

## 🛠️ Tech Stack

* **Frontend**: React 19, TypeScript, React Flow (@xyflow/react), ELKjs, CodeMirror 6, TanStack Query v5, Radix UI.
* **Backend**: Python 3.11+, FastAPI, LangGraph, SQLAlchemy 2.0, Pydantic v2, Google GenAI SDK.
