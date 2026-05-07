# Tangelo

Your office work, handled by one app. Tell it what you need in plain English and it figures out the rest — whether that means building a spreadsheet, drafting a report, composing an email, or writing code.

No cloud. No subscriptions. Everything runs on your machine using [Ollama](https://ollama.com).

---

## Why does this exist?

Every office task lives in a different program. Excel has its own logic. Word works differently. Outlook is its own world. PowerPoint is yet another thing to learn. If you just want to "make a sales summary from this data and email it to my manager," you're jumping between three apps, reformatting, copy-pasting, and wasting time on things that should take seconds.

Tangelo removes that friction. You describe what you want, and it handles the tool-switching for you.

---

## What it actually does

- **Takes any input** — paste text, attach a `.docx`, `.xlsx`, `.csv`, `.txt`, image, or whatever you've got.
- **Produces any output** — Word documents, Excel spreadsheets with charts, PDFs, code files, emails with attachments. Mix and match.
- **Understands natural language** — "Create a spreadsheet of the top 5 banks in India with their market cap, then write a one-page summary document and email both to finance@company.com" is a valid prompt.
- **Runs fully offline** — powered by Ollama and local LLMs. Your data never leaves your computer. Not even a little bit.

---

## How it works under the hood

This isn't a simple wrapper around an LLM. Tangelo uses a multi-step agentic architecture:

```
You say something
    ↓
Intent classifier decides: is this a task or just a question?
    ↓
If task → Planner generates a structured JSON execution plan
    ↓
Orchestrator runs each step: Think → Act → Observe → Update
    ↓
Sub-agents (Word, Excel, Outlook, VS Code) do the actual work
    ↓
Results land on your desktop
```

### The agentic loop (built on LangGraph)

The orchestrator doesn't just fire-and-forget. After each step, it checks what happened. If something failed — say Outlook wasn't open, or a file path was wrong — it calls the planner again to revise the remaining steps. This self-correcting behavior means it can recover from errors mid-execution instead of crashing out.

### Variable chaining between steps

Steps can reference outputs from earlier steps using `$stepN.output`. So if step 1 creates a spreadsheet and step 3 sends an email, the email attachment automatically resolves to the file path from step 1. The planner handles this natively — no manual wiring needed.

### Short-term memory

Each task execution maintains its own memory context: what files were created, which steps passed or failed, how long things took, recent errors. This context gets injected back into the LLM prompt during replanning, so the model has awareness of what already happened.

---

## Architecture

```
tangelo/
├── main.py                 # Entry point — starts API server + GUI
├── config.py               # Central configuration (env-var overrides)
├── requirements.txt
│
├── agent/
│   ├── orchestrator.py     # LangGraph state machine — the brain
│   ├── planner.py          # JSON plan generation + replanning via Ollama
│   └── memory.py           # Per-task short-term memory and file tracking
│
├── agents/
│   ├── base_agent.py       # Abstract base class + AgentResult dataclass
│   ├── word_agent.py       # Word doc creation, tables, PDF export
│   ├── excel_agent.py      # Spreadsheets, charts, formatting
│   ├── outlook_agent.py    # Email via Outlook COM
│   └── vscode_agent.py     # Code file creation, editor launch, execution
│
├── api/
│   └── server.py           # FastAPI backend (sync + async endpoints)
│
├── gui/
│   └── app.py              # CustomTkinter desktop UI
│
└── tools/
    └── registry.py         # Auto-discovers agents, dispatches actions
```

---

## The sub-agents

### Word Agent
Creates `.docx` files with proper heading hierarchy, bullet points, styled tables, and timestamps. Parses markdown-like syntax in the content (headings with `#`, bullets with `-`). Can export to PDF through Word's COM interface.

### Excel Agent
Builds `.xlsx` workbooks with formatted headers, alternating row colors, auto-filters, and frozen panes out of the box. Supports bar, line, and pie charts. Data gets styled automatically — dark header rows, accent borders, proper column widths.

### Outlook Agent
Sends emails with attachments through Microsoft Outlook's COM automation. Lazy-loads the Outlook connection so it doesn't block startup if Outlook isn't running. Handles multiple recipients (comma-separated) and multiple file attachments.

### VS Code Agent
Creates source files in 20+ languages (Python, JavaScript, TypeScript, Go, Rust, Java, etc.), opens them in VS Code, and can execute scripts with captured output. Organizes generated code into a `code/` subdirectory.

---

## The GUI

A two-panel desktop interface built with CustomTkinter:

- **Left panel** — chat-style conversation with the agent. User messages and agent responses appear as styled bubbles. Files created during execution show up as clickable buttons that open the file directly.
- **Right panel** — live execution plan viewer (shows each step's status with icons: ⏳ pending, 🔄 running, ✅ done, ❌ failed) and a scrollable execution log.
- **Bottom bar** — text input with file attachment support. Drag in a document and the agent reads its contents before processing your request.
- **Header** — shows connection status to Ollama (model name + online/offline indicator).

File attachment works for `.docx`, `.xlsx`, `.txt`, `.csv`, `.py`, `.md`, `.json`, and more. The agent extracts the content, truncates to 4000 characters if needed, and includes it in the prompt context.

---

## Getting started

### Prerequisites

- **Windows 10/11** (uses COM automation for Outlook and Word PDF export)
- **Python 3.11+**
- **Ollama** installed and running locally — [get it here](https://ollama.com/download)
- **A model pulled** — e.g. `ollama pull llama3`
- Microsoft Office (for Outlook email and Word PDF export — the rest works without it)

### Setup

```bash
# Clone the repo
git clone https://github.com/Ra1617/Tangelo.git
cd Tangelo

# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Make sure Ollama is running with a model
ollama serve
ollama pull llama3
```

### Run

```bash
python main.py
```

This starts the FastAPI server on `localhost:8000` in a background thread, then opens the GUI. The status indicator in the top-right turns green when Ollama is connected.

### Configuration

All settings live in `config.py` and can be overridden with environment variables:

| Variable | Default | What it does |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434/api/chat` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3` | Which model to use |
| `API_HOST` | `127.0.0.1` | FastAPI bind address |
| `API_PORT` | `8000` | FastAPI port |
| `OUTPUT_DIR` | Desktop/Ideaphilip | Where generated files land |

---

## Things worth noting

- The planner asks the LLM to generate valid JSON execution plans. If the JSON parse fails (models sometimes add commentary), it falls back to a single chat-response step instead of throwing an error.
- Intent classification happens before every request. Greetings and questions get routed to a simple chat mode. Anything that sounds like "create," "make," "send," "build," or "generate" triggers the full agentic pipeline.
- PDF export uses `win32com` to open Word silently, save as PDF, and close. It's not pretty but it produces real, properly-formatted PDFs — not html-to-pdf conversions.
- The tool registry is designed for extension. Adding a new agent means writing a class that inherits from `BaseAgent`, implementing the `execute` method, and registering it in `registry.py`. That's it.
- Every action returns a standardized `AgentResult` with success/failure, a message, an optional output file path, and optional structured data. The orchestrator doesn't need to know how each agent works internally.

---

## API

The FastAPI server exposes three endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Connection check + Ollama status |
| `POST` | `/execute` | Async execution — returns `task_id`, poll `/status/{task_id}` |
| `POST` | `/execute_sync` | Blocking execution — waits and returns full result |

The GUI uses `/execute_sync` for simplicity. External integrations can use the async route.

---

## License

Do whatever you want with it.