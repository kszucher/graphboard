# ⚡ Graphboard
### Visual State Machine Canvas & Self-Healing LangGraph Copilot

A visual canvas and agentic development environment for designing, compiling, validating, and executing **LangGraph** state machines in Python.

---

<img width="1980" height="1080" alt="Graphboard Visual Canvas & Copilot" src="https://github.com/user-attachments/assets/f4f48fd8-b8b0-465b-b254-2f7efea56cd4" />

---

## 🎯 The Core Problem & Solution

* **The Challenge with LLM Code Generation:** Asking LLMs to generate raw LangGraph Python scripts leads to high error rates — hallucinated imports, desynchronized state keys, dangling conditional branches, and unparseable ASTs that cannot reliably sync back to a visual canvas.
* **Graphboard's Solution:** A **declarative visual schema** paired with an **agentic single-call Copilot**, a **deterministic AST compiler**, and an **autonomous dry-run validation loop**. Mutations are planned as structured operations, validated against topological invariants, and compiled into idiomatic LangGraph code.

---

## 🌟 Key Engineering Highlights

* **🧠 Single-Call Atomic Copilot:** The Copilot Planner is bound to a single atomic tool (`apply_graph_plan`) with `mode=ANY`. It generates the complete, multi-node modification batch (variables, nodes, surgical switch branches, renames, deletions) in a single turn — eliminating multi-tool selection cutoffs, sub-agent hallucinations, and token overhead.
* **🛡️ Dry-Run Validation & Self-Healing:** Validates delta application, topological integrity (`assert_flow_is_complete`), and Python AST compilation *before* committing. If a gate fails, diagnostic tracebacks feed into an automated reflection loop to self-heal.
* **⚡ Real-time AST Compiler:** Dynamically compiles the visual graph schema directly into native, executable Python LangGraph code (`StateGraph`, `add_conditional_edges`, `interrupt`).
* **📦 Subprocess Sandbox:** Executes compiled user workflows inside a dedicated spawned subprocess with piped I/O and strict timeouts, protecting the main API from runaway loops.
* **🔄 Unidirectional Canvas Sync:** The server acts as the single source of truth. Changes commit via a transactional Unit of Work and stream over WebSockets to update the React Flow canvas and CodeMirror viewer.

---

## 🏗️ System Architecture

```mermaid
graph TD
    %% Styling
    classDef default fill:#1e1e2e,stroke:#cdd6f4,stroke-width:1px,color:#cdd6f4;
    classDef ui fill:#181825,stroke:#cba6f7,stroke-width:1px,color:#cba6f7;
    classDef copilot fill:#181825,stroke:#f9e2af,stroke-width:1.5px,color:#f9e2af;
    classDef backend fill:#181825,stroke:#89b4fa,stroke-width:1px,color:#89b4fa;
    classDef store fill:#181825,stroke:#a6e3a1,stroke-width:1px,color:#a6e3a1;

    User([👤 User]) -->|"Natural language intent"| Planner["🧠 Planner Node"]
    Planner -->|"apply_graph_plan (Atomic tool)"| Translator["⚡ Translation Node"]
    Translator -->|"GraphUpdateInput patches"| Validator["✅ Dry-Run Validator<br/>(Delta + Topological Integrity + AST)"]
    Validator -->|"Self-Correction Retry (<= 1)<br/>Diagnostic Error Traceback"| Planner
    Validator -->|"Validation Passed"| Operations["⚙️ operations/pipeline.py"]
    Operations -->|"New Snapshot"| History[("🗄️ Version History")]
    History -->|"Compile"| Compiler["📝 AST Compiler"]
    Compiler -->|"Python Script"| Canvas["💻 React Flow Canvas"]
    History -.->|"GRAPH_UPDATED via WebSocket"| Canvas

    class Planner,Translator copilot;
    class Validator,Operations,Compiler backend;
    class History store;
    class Canvas ui;
    class User default;
```

---

## 💡 Key Architectural Decisions & Trade-offs

| Design Area | Standard / Naive Approach | Graphboard Architecture | Engineering Advantage |
| :--- | :--- | :--- | :--- |
| **Graph Mutation** | Multi-agent chain or Free-form code gen | **Single Atomic Tool (`apply_graph_plan`) + Deterministic Translation** | Generates all state variables, nodes, and surgical branches in a single atomic transaction; eliminates multi-tool list cutoffs and intermediate agent hallucinations. |
| **Branch Routing** | Full-array overwrite on switches | **Surgical Branch Patching (`upsert_switch_branch`)** | Prevents the model from accidentally dropping or renaming unmentioned branches on complex decision nodes. |
| **Validation** | Post-execution error logging | **Pre-Commit Dry-Run + Reflection Loop** | Catches topological disconnections and compiler syntax errors *before* database commit, self-healing automatically. |
| **Canvas Sync** | Bidirectional AST parsing | **Unidirectional Server State + WebSocket Broker** | Guarantees deterministic graph state; visual canvas acts as a pure reactive inspector driven by ELK auto-layout. |
| **Script Execution** | In-process `exec()` / `eval()` | **Isolated Subprocess Sandbox** | Isolates long-running or looping workflows with hard timeout enforcement and piped `stdin`/`stdout`. |

---

## 🧩 Visual Node Vocabulary (2×2 Orthogonal Matrix)

The state machine primitives form a deliberate **2×2 grid**, plus **human control** and **memory retrieval**:

| | Deterministic Logic | AI-Driven / Dynamic |
| :--- | :--- | :--- |
| **Computation** | `LOGICAL_ASSIGNER`<br/>*(Expressions, Math, Strings, Lists)* | `AGENTIC_ASSIGNER`<br/>*(Structured Gemini LLM generation)* |
| **Routing** | `LOGICAL_SWITCH`<br/>*(Deterministic AST Boolean expressions)* | `AGENTIC_SWITCH`<br/>*(LLM intent classification / branching)* |
| **Control** | `INTERRUPT`<br/>*(Human-in-the-loop pause & resume)* | — |
| **Memory** | `RAG_RETRIEVER`<br/>*(pgvector queries with Hugging Face)* | — |

* **Deterministic Assignment Algebra:** `LOGICAL_ASSIGNER` supports a safe, orthogonal expression set (arithmetic, string formatting, list sampling/slicing, and pseudo-random generation) without embedding branching logic, keeping control flow strictly inside Switch nodes.

---

## 📊 Autonomous Evaluation Benchmark

A major engineering goal of Graphboard is **token & compute efficiency** — enabling lightweight, fast, and cost-effective models (`gemini-3.5-flash-lite` with a 1024 thinking budget) to achieve production-grade reliability on complex graph mutations without needing slow, expensive frontier models.

> **💡 Token & Cost Efficiency:** By constraining the planner to an atomic transaction payload with deterministic translation, Graphboard achieves **90% Pass@1 on lightweight models** (~$0.15/M tokens), avoiding the 10x cost and 5x latency overhead of frontier models.

### 🧪 10-Tier Millionaire Benchmark Suite

The suite evaluates progressive state machine changes on the default trivia graph — from simple variable adjustments to complex branching, single-use constraints, interactive interrupts, and full ruleset overhauls:

| Tier | Focus / Capability Tested | Natural User Prompt | Result | Resolution | Latency | Tokens (In / Out) |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| **1** | **Game Length** | *"Make the game longer: 15 correct answers to win instead of 5."* | ✅ **PASS** | Pass@1 | ~6.1s | 4,808 / 125 |
| **2** | **Prize Tracking** | *"Add prize money tracking so each correct answer increases cash."* | ✅ **PASS** | Pass@1 | ~6.2s | 4,803 / 193 |
| **3** | **Walk-Away Option** | *"Allow the player to walk away with their current money."* | ✅ **PASS** | Pass@1 | ~9.5s | 4,804 / 41 |
| **4** | **50:50 Lifeline** | *"Add a fifty-fifty lifeline filtering wrong options."* | ✅ **PASS** | Pass@1 | ~9.2s | 4,793 / 213 |
| **5** | **Difficulty Tiers** | *"Questions get progressively harder: Easy (Q1-4), Med (Q5-9), Hard (Q10+)."* | ✅ **PASS** | Pass@1 | ~14.1s | 4,818 / 783 |
| **6** | **Single-Use Lifelines** | *"Make lifelines single-use so they cannot be reused once used."* | ✅ **PASS** | Pass@1 | ~14.6s | 4,815 / 581 |
| **7** | **Switch Question** | *"Add a 'Switch Question' lifeline that discards and draws a new one."* | ✅ **PASS** | Pass@1 | ~11.3s | 4,811 / 108 |
| **8** | **Safety Nets** | *"Account for guaranteed wins after questions 5 and 10."* | ✅ **PASS** | Pass@1 | ~15.5s | 4,807 / 737 |
| **9** | **Interactive Host** | *"Add an 'Ask Host' lifeline pausing for host response before resuming."* | ✅ **PASS** | Pass@1 | ~7.5s | 4,818 / 164 |
| **10** | **Full Engine Overhaul** | *"Full Millionaire ruleset: 15 questions, checkpoints, walk-away, 3 lifelines."* | ❌ **FAIL** | 3 attempts | ~31.0s | 9,736 / 2,270 |

### 🏆 Baseline Performance Highlights (`gemini-3.5-flash-lite`)

* **90.0% Pass@1 Accuracy (9 / 10 Tiers):** Demonstrates that structured schema constraints allow small, sub-second latency models to reliably execute multi-step graph refactoring.
* **ID-Agnostic Topological Grading:** Invariant-based grading verifies graph connectivity, branch count deltas, AST boolean expressions, and state schemas without brittle LLM node ID matching.
* **Fast & Cost-Efficient:** Average resolution time of **~10.4s** and under **350 output tokens** per mutation.
* **Self-Healing Telemetry:** Real-time logging of compiler error feedback and reflection retry loops.

---

## 🛠️ Tech Stack

* **Frontend:** React 19, TypeScript, React Flow (`@xyflow/react`), ELKjs Layout Engine, CodeMirror 6, TanStack Query v5, Radix UI.
* **Backend:** Python 3.11+, FastAPI, LangGraph, SQLAlchemy 2.0, Pydantic v2, Google GenAI SDK, Neon Postgres (pgvector).
* **Tooling:** `uv` package manager, Vite, Ruff, MyPy.

---

## 🚀 Quickstart

### Prerequisites
* Python 3.11+ with [`uv`](https://docs.astral.sh/uv/) installed
* Node.js 18+ and `npm`
* Gemini API Key (`GEMINI_API_KEY` in environment or `.env`)

### 1. Start Python Backend
```bash
cd python-backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

### 2. Start Frontend
```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser to start designing and running graphs.
