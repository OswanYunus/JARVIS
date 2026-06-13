from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib import error, request
import json
import mimetypes
import re
import sqlite3
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / "Desktop"
FRONTEND = ROOT / "frontend"
DB_PATH = ROOT / "jarvis.db"
RULES_PATH = ROOT / "rules.md"
STATE_PATH = ROOT / "jarvis_state.json"
OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.2:3b"
SAFEWORD = "underoos"
TOOL_INSTRUCTIONS = """

Tool access:
You can ask the local app to create files inside the project workspace or on the user's Desktop.
When you need to create a file, respond with only this JSON and no extra text:
{"tool": "create_file", "path": "relative/path/or/name.txt", "content": "file contents"}
When you need to create a GitHub repository, respond with only this JSON and no extra text:
{"tool": "create_github_repo", "name": "repo-name", "visibility": "public"}
When you need to commit and push this project to GitHub, respond with only this JSON and no extra text:
{"tool": "push_project_to_github", "message": "commit message"}

Rules for tool use:
- Use a relative path only, unless the user explicitly asks for Desktop.
- For Desktop files, use "Desktop/filename.ext".
- Do not use drive letters.
- Do not use absolute paths.
- Do not use .. path traversal.
- If the user asks for a file called JARVIS, use path "JARVIS".
- For GitHub repositories, use only letters, numbers, dots, underscores, and hyphens in the name.
- For pushing to GitHub, use a short commit message.
"""


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                model TEXT,
                created_at INTEGER NOT NULL
            )
            """
        )


def save_message(role, content, model=None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO messages (role, content, model, created_at) VALUES (?, ?, ?, ?)",
            (role, content, model, int(time.time())),
        )


def load_messages(limit=30):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT role, content, model, created_at
            FROM messages
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in reversed(rows)]


def clear_messages():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM messages")


def load_state():
    if not STATE_PATH.exists():
        return {"tools_enabled": True}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"tools_enabled": True}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def disable_tools():
    state = load_state()
    state["tools_enabled"] = False
    save_state(state)
    return "Safeword accepted. All J.A.R.V.I.S tool privileges are now disabled."


def tools_enabled():
    return bool(load_state().get("tools_enabled", True))


def read_rules():
    if not RULES_PATH.exists():
        return "You are J.A.R.V.I.S, a helpful personal AI assistant."
    return RULES_PATH.read_text(encoding="utf-8") + TOOL_INSTRUCTIONS


def safe_file_path(relative_path):
    requested = relative_path.strip().replace("\\", "/")
    if not requested:
        raise ValueError("File path cannot be empty.")
    if requested.startswith("/") or ":" in requested:
        raise ValueError("Only relative workspace or Desktop paths are allowed.")

    parts = [part for part in requested.split("/") if part]
    if parts and parts[0].lower() == "desktop":
        target = (DESKTOP / Path(*parts[1:])).resolve()
        if DESKTOP.resolve() not in target.parents and target != DESKTOP.resolve():
            raise ValueError("Desktop path must stay inside the user's Desktop folder.")
        return target, target

    target = (ROOT / requested).resolve()
    if ROOT.resolve() not in target.parents and target != ROOT.resolve():
        raise ValueError("Path must stay inside the project workspace.")
    return target, target.relative_to(ROOT)


def infer_file_tool(message):
    lowered = message.lower()
    if not any(word in lowered for word in ("create", "make", "write", "save")):
        return None
    if "file" not in lowered:
        return None

    patterns = [
        r"(?:called|named)\s+([A-Za-z0-9_. -]+)",
        r"file\s+([A-Za-z0-9_. -]+)",
    ]
    filename = None
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            filename = match.group(1).strip()
            break

    if not filename:
        return None

    filename = re.split(r"\s+(?:on|in|with|containing)\b", filename, maxsplit=1, flags=re.IGNORECASE)[0]
    filename = filename.strip(" .\"'")
    if not filename:
        return None

    path = filename
    if "desktop" in lowered:
        path = f"Desktop/{filename}"

    content_match = re.search(
        r"(?:with|containing)\s+(?:any\s+)?(?:text\s+)?(?:inside\s*)?(.*)$",
        message,
        flags=re.IGNORECASE,
    )
    content = "Created by J.A.R.V.I.S."
    if content_match:
        extracted = content_match.group(1).strip(" .\"'")
        if extracted and extracted.lower() not in ("inside", "in it", "there"):
            content = extracted

    return {"tool": "create_file", "path": path, "content": content}


def try_parse_tool_call(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if isinstance(payload, dict) and payload.get("tool") == "create_file":
        return payload
    return None


def run_tool(tool_call):
    if tool_call["tool"] == "push_project_to_github":
        return push_project_to_github(tool_call)

    if tool_call["tool"] == "create_github_repo":
        return create_github_repo(tool_call)

    if tool_call["tool"] != "create_file":
        raise ValueError("Unknown tool.")

    target, display_path = safe_file_path(str(tool_call.get("path", "")))
    content = str(tool_call.get("content", ""))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return {
        "tool": "create_file",
        "path": str(display_path),
        "message": f"Created {display_path}.",
    }


def run_command(args):
    result = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(details or f"Command failed: {' '.join(args)}")
    return result.stdout.strip()


def git_output(args):
    return run_command(["git", *args])


def push_project_to_github(tool_call):
    commit_message = str(tool_call.get("message", "Update JARVIS project")).strip()
    if not commit_message:
        commit_message = "Update JARVIS project"

    if not (ROOT / ".git").exists():
        git_output(["init"])

    remotes = git_output(["remote"])
    if "origin" not in remotes.splitlines():
        raise RuntimeError("No git remote named origin is configured. Create a GitHub repo or set origin first.")

    status_before = git_output(["status", "--porcelain"])
    if status_before:
        git_output(["add", "."])
        staged = git_output(["diff", "--cached", "--name-only"])
        if staged:
            git_output(["commit", "-m", commit_message])

    branch = git_output(["branch", "--show-current"])
    if not branch:
        branch = "main"
        git_output(["checkout", "-B", branch])

    push_output = git_output(["push", "-u", "origin", branch])
    return {
        "tool": "push_project_to_github",
        "branch": branch,
        "message": f"Pushed J.A.R.V.I.S to GitHub on branch {branch}. {push_output}".strip(),
    }


def create_github_repo(tool_call):
    name = str(tool_call.get("name", "")).strip()
    visibility = str(tool_call.get("visibility", "public")).strip().lower()

    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", name):
        raise ValueError("GitHub repo name can only use letters, numbers, dots, underscores, and hyphens.")
    if visibility not in ("public", "private"):
        visibility = "public"

    try:
        run_command(["gh", "--version"])
    except (FileNotFoundError, RuntimeError):
        raise RuntimeError("GitHub CLI is not installed or not on PATH. Install gh and run gh auth login first.")

    try:
        run_command(["gh", "auth", "status"])
    except RuntimeError:
        raise RuntimeError("GitHub CLI is installed but not logged in. Run gh auth login first.")

    if not (ROOT / ".git").exists():
        run_command(["git", "init"])

    try:
        url = run_command(
            [
                "gh",
                "repo",
                "create",
                name,
                f"--{visibility}",
                "--source",
                str(ROOT),
                "--remote",
                "origin",
            ]
        )
    except RuntimeError as exc:
        details = str(exc)
        if "Resource not accessible by personal access token" in details:
            raise RuntimeError(
                "GitHub rejected the request because your GitHub CLI token cannot create repositories. "
                "Run: gh auth refresh -s repo"
            ) from exc
        raise

    return {
        "tool": "create_github_repo",
        "name": name,
        "visibility": visibility,
        "message": f"Created GitHub repo {name} and set it as origin. {url}".strip(),
    }


def infer_github_tool(message):
    lowered = message.lower()
    if "github" not in lowered or "repo" not in lowered:
        return None
    if not any(word in lowered for word in ("create", "make", "new")):
        return None

    match = re.search(
        r"(?:called|named|name)\s+([A-Za-z0-9._-]+)",
        message,
        flags=re.IGNORECASE,
    )
    name = match.group(1) if match else None
    if not name:
        match = re.search(r"github\s+repo(?:sitory)?\s+([A-Za-z0-9._-]+)", message, flags=re.IGNORECASE)
        name = match.group(1) if match else None
    if not name:
        return None

    visibility = "private" if "private" in lowered else "public"
    return {"tool": "create_github_repo", "name": name, "visibility": visibility}


def infer_git_push_tool(message):
    lowered = message.lower()
    wants_push = "push" in lowered and any(word in lowered for word in ("github", "remote", "repo", "repository"))
    wants_git_flow = "git add" in lowered or "commit" in lowered
    if not (wants_push or wants_git_flow):
        return None

    match = re.search(
        r"(?:commit message|message)\s*[:=]?\s*[\"']?([^\"'\n]+)",
        message,
        flags=re.IGNORECASE,
    )
    commit_message = match.group(1).strip() if match else "Update JARVIS project"
    return {"tool": "push_project_to_github", "message": commit_message}


def choose_tool(message, model):
    git_push_tool = infer_git_push_tool(message)
    if git_push_tool:
        return git_push_tool

    github_tool = infer_github_tool(message)
    if github_tool:
        return github_tool

    inferred = infer_file_tool(message)
    if inferred:
        return inferred

    planner_messages = [
        {
            "role": "system",
            "content": (
                "You are the tool planner for a local personal assistant. "
                "Return only valid JSON. No markdown. No explanation. "
                "If the user wants to git add, commit, and push this project to GitHub, return "
                "{\"tool\":\"push_project_to_github\",\"message\":\"Update JARVIS project\"}. "
                "If the user wants to create a GitHub repository, return "
                "{\"tool\":\"create_github_repo\",\"name\":\"REPO_NAME\",\"visibility\":\"public\"}. "
                "If the user wants to create, make, write, or save a file, return "
                "{\"tool\":\"create_file\",\"path\":\"FILENAME\",\"content\":\"CONTENT\"}. "
                "Use the filename requested by the user. If the user gives no content, "
                "use a short simple line of content. If no tool is needed, return {\"tool\":null}. "
                "Only relative paths are allowed."
            ),
        },
        {"role": "user", "content": message},
    ]

    payload = {
        "model": model,
        "messages": planner_messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_ctx": 1024,
        },
    }

    result = ollama_json("/api/chat", payload, method="POST")
    try:
        tool_call = json.loads(result["message"]["content"])
    except json.JSONDecodeError:
        return None

    if isinstance(tool_call, dict) and tool_call.get("tool") == "create_file":
        return tool_call
    return None


def summarize_tool_result(message, tool_result, model):
    return tool_result["message"]


def ollama_json(path, payload=None, method="GET"):
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(f"{OLLAMA_URL}{path}", data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def chat_with_ollama(message, model):
    if SAFEWORD in message.lower():
        return disable_tools()

    if not tools_enabled():
        return (
            "Tool privileges are disabled. I can still chat, explain, and help you plan, "
            "but I will not touch files or perform computer actions."
        )

    tool_call = choose_tool(message, model)
    if tool_call:
        tool_result = run_tool(tool_call)
        return summarize_tool_result(message, tool_result, model)

    recent = load_messages(limit=20)
    messages = [{"role": "system", "content": read_rules()}]
    messages.extend({"role": item["role"], "content": item["content"]} for item in recent)
    messages.append({"role": "user", "content": message})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_ctx": 4096,
        },
    }

    result = ollama_json("/api/chat", payload, method="POST")
    reply = result["message"]["content"]
    tool_call = try_parse_tool_call(reply)

    if not tool_call:
        return reply

    tool_result = run_tool(tool_call)
    messages.append({"role": "assistant", "content": reply})
    messages.append(
        {
            "role": "user",
            "content": (
                "Tool result: "
                + json.dumps(tool_result)
                + "\nNow tell me briefly what you did."
            ),
        }
    )

    final_payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_ctx": 4096,
        },
    }
    final_result = ollama_json("/api/chat", final_payload, method="POST")
    return final_result["message"]["content"]


class JarvisHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")

    def translate_path(self, path):
        clean_path = path.split("?", 1)[0].split("#", 1)[0]
        if clean_path == "/":
            clean_path = "/index.html"
        return str(FRONTEND / clean_path.lstrip("/"))

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        if self.path.startswith("/api/history"):
            self.send_json(200, {"messages": load_messages(limit=100)})
            return

        if self.path.startswith("/api/rules"):
            self.send_json(200, {"rules": read_rules()})
            return

        if self.path.startswith("/api/models"):
            try:
                data = ollama_json("/api/tags")
                models = [item["name"] for item in data.get("models", [])]
                self.send_json(200, {"models": models, "default": models[0] if models else DEFAULT_MODEL})
            except (error.URLError, TimeoutError) as exc:
                self.send_json(503, {"error": f"Ollama is not reachable: {exc}"})
            return

        if self.path.startswith("/api/state"):
            self.send_json(200, load_state())
            return

        guessed_type = mimetypes.guess_type(self.translate_path(self.path))[0]
        if guessed_type:
            self.extensions_map[Path(self.path).suffix] = guessed_type
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/chat":
            body = self.read_json()
            message = body.get("message", "").strip()
            model = body.get("model", DEFAULT_MODEL).strip() or DEFAULT_MODEL

            if not message:
                self.send_json(400, {"error": "Message cannot be empty."})
                return

            try:
                save_message("user", message, model)
                reply = chat_with_ollama(message, model)
                save_message("assistant", reply, model)
                self.send_json(200, {"reply": reply})
            except error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                self.send_json(exc.code, {"error": details})
            except (error.URLError, TimeoutError) as exc:
                self.send_json(503, {"error": f"Ollama is not reachable: {exc}"})
            except (RuntimeError, ValueError) as exc:
                self.send_json(400, {"error": str(exc)})
            return

        if self.path == "/api/clear":
            clear_messages()
            self.send_json(200, {"ok": True})
            return

        if self.path == "/api/rules":
            body = self.read_json()
            rules = body.get("rules", "").strip()
            if not rules:
                self.send_json(400, {"error": "Rules cannot be empty."})
                return
            RULES_PATH.write_text(rules + "\n", encoding="utf-8")
            self.send_json(200, {"ok": True})
            return

        self.send_json(404, {"error": "Not found"})


def main():
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), JarvisHandler)
    print("J.A.R.V.I.S is running at http://127.0.0.1:8000")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
