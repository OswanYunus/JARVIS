from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib import error, request
import json
import difflib
import mimetypes
import re
import sqlite3
import subprocess
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / "Desktop"
FRONTEND = ROOT / "frontend"
DB_PATH = ROOT / "jarvis.db"
RULES_PATH = ROOT / "rules.md"
STATE_PATH = ROOT / "jarvis_state.json"
OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.2:3b"
SAFEWORD = "underoos"

# ──────────────────────────────────────────────────────────────────────────────
# Optional system-control imports (graceful fallback if not installed)
# ──────────────────────────────────────────────────────────────────────────────
try:
    import pyautogui
    import pygetwindow as gw
    SYSTEM_CONTROL = True
    pyautogui.FAILSAFE = True   # move mouse to top-left corner to abort
    pyautogui.PAUSE = 0.08
except ImportError:
    SYSTEM_CONTROL = False

try:
    import webbrowser
    WEB_BROWSER = True
except ImportError:
    WEB_BROWSER = False

TOOL_INSTRUCTIONS = """

Tool access:
You can ask the local app to create files inside the project workspace or on the user's Desktop.
When you need to create a file, respond with only this JSON and no extra text:
{"tool": "create_file", "path": "relative/path/or/name.txt", "content": "file contents"}
When you need to create a GitHub repository, respond with only this JSON and no extra text:
{"tool": "create_github_repo", "name": "repo-name", "visibility": "public"}
When you need to commit and push this project to GitHub, respond with only this JSON and no extra text:
{"tool": "push_project_to_github", "message": "commit message"}

System control tools (Windows only, requires pyautogui):
When you need to open a new browser tab or URL, respond with only this JSON:
{"tool": "open_browser_tab", "url": "https://example.com"}
When you need to search the Windows taskbar / Start search, respond with only this JSON:
{"tool": "taskbar_search", "query": "search text"}
When you need to switch to a running window by name, respond with only this JSON:
{"tool": "switch_window", "title": "partial window title"}
When you need to type text into the currently focused window, respond with only this JSON:
{"tool": "type_text", "text": "text to type"}
When you need to press a keyboard shortcut, respond with only this JSON:
{"tool": "press_keys", "keys": "ctrl+t"}

When you need to close or kill a running application, respond with only this JSON:
{"tool": "close_app", "app": "blender"}
When you need to close a browser tab, website, or page, respond with only this JSON:
{"tool": "close_browser_tab", "title": "youtube"}
When you need to send a WhatsApp message to someone, respond with only this JSON:
{"tool": "whatsapp_message", "contact": "Contact Name", "text": "your message here"}

Rules for tool use:
- Use a relative path only, unless the user explicitly asks for Desktop.
- For Desktop files, use "Desktop/filename.ext".
- Do not use drive letters.
- Do not use absolute paths.
- Do not use .. path traversal.
- If the user asks for a file called JARVIS, use path "JARVIS".
- For GitHub repositories, use only letters, numbers, dots, underscores, and hyphens in the name.
- For pushing to GitHub, use a short commit message.
- For open_browser_tab: always include https:// in the URL.
- For taskbar_search: use the exact words the user wants to search.
- For switch_window: use a partial title that uniquely identifies the window.
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
            "SELECT role, content, model, created_at FROM messages ORDER BY id DESC LIMIT ?",
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


APP_ALIASES = {
    "edge": "msedge.exe",
    "ms edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "microsoftedge": "msedge.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "mozilla firefox": "firefox.exe",
    "brave": "brave.exe",
    "brave browser": "brave.exe",
    "opera": "opera.exe",
    "blender": "blender.exe",
    "notepad": "notepad.exe",
    "whatsapp": "WhatsApp.exe",
}

WEB_TARGETS = {
    "youtube", "youtube.com", "netflix", "netflix.com", "gmail", "mail",
    "google", "google.com", "facebook", "instagram", "x", "twitter",
    "spotify", "github", "whatsapp web", "web whatsapp",
}


def normalize_app_exe(app):
    cleaned = re.sub(r"\s+", " ", str(app).strip().lower())
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"\b(?:app|program|application|window|browser)\b", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        raise ValueError("No app name provided.")
    if cleaned in APP_ALIASES:
        return APP_ALIASES[cleaned]
    fuzzy = difflib.get_close_matches(cleaned, APP_ALIASES.keys(), n=1, cutoff=0.78)
    if fuzzy:
        return APP_ALIASES[fuzzy[0]]
    if cleaned.endswith(".exe"):
        return Path(cleaned).name
    return Path(cleaned + ".exe").name


def clean_close_target(text):
    target = re.sub(r"\b(?:tab|website|site|page|window)\b", "", str(text), flags=re.IGNORECASE)
    target = re.sub(r"\b(?:on|in|from)\s+(?:the\s+)?(?:browser|edge|chrome|firefox|brave)\b", "", target, flags=re.IGNORECASE)
    target = re.sub(r"\s+", " ", target).strip(" .,")
    return target


# ──────────────────────────────────────────────────────────────────────────────
# System control tool runners
# ──────────────────────────────────────────────────────────────────────────────
def run_open_browser_tab(tool_call):
    url = str(tool_call.get("url", "")).strip()
    if not url:
        raise ValueError("No URL provided.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open_new_tab(url)
    return {"tool": "open_browser_tab", "url": url, "message": f"Opened {url} in a new browser tab."}


def run_taskbar_search(tool_call):
    if not SYSTEM_CONTROL:
        raise RuntimeError("pyautogui is not installed. Run: pip install pyautogui pygetwindow")
    query = str(tool_call.get("query", "")).strip()
    launch = bool(tool_call.get("launch", False))  # if True, press Enter to open top result
    if not query:
        raise ValueError("No search query provided.")
    pyautogui.hotkey("win", "s")
    time.sleep(0.8)                          # wait for search box to appear
    pyautogui.typewrite(query, interval=0.06)
    if launch:
        time.sleep(1.2)                      # wait for search results to populate
        pyautogui.press("enter")             # open the top result
        action = f"Searched for '{query}' and opened the top result."
    else:
        action = f"Opened Windows search and typed: {query}"
    return {"tool": "taskbar_search", "query": query, "message": action}


def run_switch_window(tool_call):
    if not SYSTEM_CONTROL:
        raise RuntimeError("pyautogui is not installed. Run: pip install pyautogui pygetwindow")
    title = str(tool_call.get("title", "")).strip()
    if not title:
        raise ValueError("No window title provided.")
    windows = gw.getWindowsWithTitle(title)
    if not windows:
        raise RuntimeError(f"No window found matching: {title}")
    windows[0].activate()
    return {"tool": "switch_window", "title": title, "message": f"Switched to window: {windows[0].title}"}


def run_type_text(tool_call):
    if not SYSTEM_CONTROL:
        raise RuntimeError("pyautogui is not installed. Run: pip install pyautogui pygetwindow")
    text = str(tool_call.get("text", ""))
    if not text:
        raise ValueError("No text provided.")
    time.sleep(0.3)
    pyautogui.typewrite(text, interval=0.04)
    return {"tool": "type_text", "text": text, "message": f"Typed: {text[:60]}{'...' if len(text)>60 else ''}"}


def run_press_keys(tool_call):
    if not SYSTEM_CONTROL:
        raise RuntimeError("pyautogui is not installed. Run: pip install pyautogui pygetwindow")
    keys = str(tool_call.get("keys", "")).strip()
    if not keys:
        raise ValueError("No keys provided.")
    # Allow common safe shortcuts only
    safe_patterns = re.compile(
        r"^(ctrl|alt|shift|win)\+[a-z0-9]$|^(enter|escape|tab|backspace|delete|f[1-9]|f1[0-2])$",
        re.IGNORECASE
    )
    if not safe_patterns.match(keys):
        raise ValueError(f"Key combination not allowed: {keys}. Use simple combos like ctrl+t, ctrl+w, alt+tab.")
    parts = keys.lower().split("+")
    if len(parts) > 1:
        pyautogui.hotkey(*parts)
    else:
        pyautogui.press(parts[0])
    return {"tool": "press_keys", "keys": keys, "message": f"Pressed: {keys}"}


def run_close_app(tool_call):
    """Kill a Windows process by name using taskkill — no GUI clicking."""
    exe = normalize_app_exe(tool_call.get("app", ""))
    result = subprocess.run(
        ["taskkill", "/F", "/IM", exe],
        capture_output=True, text=True
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0 and "not found" in output.lower():
        raise RuntimeError(f"No running process found matching '{exe}'.")
    return {"tool": "close_app", "app": exe, "message": f"Closed {exe}. {output}".strip()}


def run_close_browser_tab(tool_call):
    if not SYSTEM_CONTROL:
        raise RuntimeError("pyautogui is not installed. Run: pip install pyautogui pygetwindow")
    title = clean_close_target(tool_call.get("title") or tool_call.get("target") or "")
    if not title:
        raise ValueError("No browser tab title provided.")

    browser_names = ("edge", "chrome", "firefox", "brave", "opera")
    title_lower = title.lower()
    browser_windows = []
    matches = []
    for win in gw.getAllWindows():
        win_title = (win.title or "").strip()
        lowered = win_title.lower()
        if not win_title:
            continue
        if any(name in lowered for name in browser_names):
            browser_windows.append(win)
        if title_lower in lowered:
            matches.append(win)

    if not matches and title_lower.endswith(".com"):
        short_title = title_lower[:-4]
        matches = [win for win in browser_windows if short_title in (win.title or "").lower()]

    if not matches:
        raise RuntimeError(f"No open browser tab/window found matching '{title}'.")

    win = matches[0]
    win.activate()
    if getattr(win, "isMinimized", False):
        win.restore()
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "w")
    return {"tool": "close_browser_tab", "title": title, "message": f"Closed browser tab/window matching: {title}"}


def run_whatsapp_message(tool_call):
    """
    Open WhatsApp Web, search for a contact by keyboard shortcut, and send a message.
    Uses Ctrl+Alt+/ to open search — no coordinate clicking needed.
    Requires: pyautogui, pyperclip. Browser must already be logged in to WhatsApp Web.
    """
    if not SYSTEM_CONTROL:
        raise RuntimeError("pyautogui is not installed. Run: pip install pyautogui pyperclip")
    try:
        import pyperclip
    except ImportError:
        raise RuntimeError("pyperclip is not installed. Run: pip install pyperclip")

    contact = str(tool_call.get("contact", "")).strip()
    message_text = str(tool_call.get("message") or tool_call.get("text") or "").strip()
    if not contact:
        raise ValueError("No contact name provided.")
    if not message_text:
        raise ValueError("No message text provided.")

    # ── Step 1: Open WhatsApp Web ─────────────────────────────────────────────
    webbrowser.open("https://web.whatsapp.com")

    # ── Step 2: Wait for WhatsApp Web to fully load ───────────────────────────
    # We wait up to 30 s. The page is considered ready when the window title
    # changes from the bare URL to include "WhatsApp". We check every second.
    deadline = time.time() + 60
    whatsapp_window = None
    while time.time() < deadline:
        time.sleep(1)
        # Look for a browser window whose title contains "WhatsApp"
        for win in gw.getAllWindows():
            if "whatsapp" in win.title.lower():
                whatsapp_window = win
                win.activate()   # bring the browser to the foreground
                if getattr(win, "isMinimized", False):
                    win.restore()
                time.sleep(1.0)  # let the focus settle
                break
        if whatsapp_window:
            break

    if not whatsapp_window:
        # Fallback: just wait 15 s flat and hope it loaded
        time.sleep(15)
        # Try to focus any browser window
        for title_hint in ("chrome", "firefox", "edge", "brave", "opera"):
            wins = [w for w in gw.getAllWindows() if title_hint in w.title.lower()]
            if wins:
                whatsapp_window = wins[0]
                whatsapp_window.activate()
                if getattr(whatsapp_window, "isMinimized", False):
                    whatsapp_window.restore()
                time.sleep(1.0)
                break

    if not whatsapp_window:
        raise RuntimeError("Could not find a browser window for WhatsApp Web.")

    screen_width, screen_height = pyautogui.size()
    left = max(0, whatsapp_window.left)
    top = max(0, whatsapp_window.top)
    width = max(1, min(whatsapp_window.width, screen_width - left))
    height = max(1, min(whatsapp_window.height, screen_height - top))

    # ── Step 3: Open the search box with the WhatsApp Web keyboard shortcut ───
    pyautogui.click(left + int(width * 0.18), top + int(height * 0.16))
    time.sleep(0.8)   # wait for the search box to focus
    pyautogui.hotkey("ctrl", "a")

    # ── Step 4: Paste the contact name (clipboard handles any Unicode) ─────────
    pyperclip.copy(contact)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(2.5)   # wait for search results to populate

    # ── Step 5: Select the first result ──────────────────────────────────────
    # Click using the browser window geometry. This adapts to the current
    # screen resolution and avoids hard-coded absolute coordinates.
    pyautogui.click(left + int(width * 0.18), top + int(height * 0.30))
    time.sleep(1.8)   # wait for the chat to open

    # ── Step 6: Paste and send the message ────────────────────────────────────
    pyautogui.click(left + int(width * 0.68), top + int(height * 0.94))
    time.sleep(0.4)
    pyperclip.copy(message_text)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)
    pyautogui.press("enter")   # send

    return {
        "tool": "whatsapp_message",
        "contact": contact,
        "message": f"Sent WhatsApp message to {contact}: \"{message_text[:60]}{'...' if len(message_text)>60 else ''}\"",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Inference helpers
# ──────────────────────────────────────────────────────────────────────────────
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
        message, flags=re.IGNORECASE,
    )
    content = "Created by J.A.R.V.I.S."
    if content_match:
        extracted = content_match.group(1).strip(" .\"'")
        if extracted and extracted.lower() not in ("inside", "in it", "there"):
            content = extracted
    return {"tool": "create_file", "path": path, "content": content}


def infer_browser_tool(message):
    """
    Smart URL builder. Handles patterns like:
      - "go to youtube and search for Baby by Rema"  → YouTube search URL
      - "search spotify for Tame Impala"             → Spotify search URL
      - "open github.com"                            → direct URL
      - "go to youtube.com"                          → direct URL
    """
    lowered = message.lower()

    TRIGGER_PHRASES = (
        "open tab", "new tab", "open a tab", "open browser",
        "go to", "navigate to", "open website", "open url",
        "search on", "search in", "search youtube", "search spotify",
        "find on youtube", "play on youtube", "look up on",
    )
    if not any(p in lowered for p in TRIGGER_PHRASES):
        return None

    # ── Site-specific search patterns ────────────────────────────────────────
    SITE_SEARCH_PATTERNS = [
        # "go to youtube and search for X" / "search youtube for X"
        (r"(?:youtube).*?(?:search|find|look up|play)\s+(?:for\s+)?(.+)", "https://www.youtube.com/results?search_query={}"),
        (r"(?:search|find|look up)\s+(?:on\s+)?youtube\s+(?:for\s+)?(.+)",  "https://www.youtube.com/results?search_query={}"),
        # Spotify
        (r"(?:spotify).*?(?:search|find|play)\s+(?:for\s+)?(.+)",           "https://open.spotify.com/search/{}"),
        (r"(?:search|find|play)\s+(?:on\s+)?spotify\s+(?:for\s+)?(.+)",     "https://open.spotify.com/search/{}"),
        # Google Maps
        (r"(?:maps?|google maps?).*?(?:search|find|navigate to|directions? to)\s+(.+)", "https://www.google.com/maps/search/{}"),
        # Wikipedia
        (r"(?:wikipedia).*?(?:search|look up|find)\s+(.+)",                 "https://en.wikipedia.org/wiki/Special:Search?search={}"),
        # GitHub
        (r"(?:github).*?(?:search|find)\s+(.+)",                            "https://github.com/search?q={}"),
        # Reddit
        (r"(?:reddit).*?(?:search|find)\s+(.+)",                            "https://www.reddit.com/search/?q={}"),
    ]

    for pattern, url_template in SITE_SEARCH_PATTERNS:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            query = match.group(1).strip().rstrip(".")
            encoded = query.replace(" ", "+")
            return {"tool": "open_browser_tab", "url": url_template.format(encoded)}

    # ── Direct URL (contains a domain) ───────────────────────────────────────
    url_match = re.search(
        r"(https?://\S+|(?:www\.)[\w.-]+(?:/\S*)?|[\w-]+\.(?:com|org|net|io|dev|co|ke|gg|tv|app)\S*)",
        message, re.IGNORECASE
    )
    if url_match:
        url = url_match.group(1)
        if not url.startswith("http"):
            url = "https://" + url
        return {"tool": "open_browser_tab", "url": url}

    # ── Fallback: Google search for whatever was said ─────────────────────────
    q_match = re.search(
        r"(?:open tab|new tab|go to|navigate to|search for|look up)\s+(.+)",
        message, re.IGNORECASE
    )
    if q_match:
        query = q_match.group(1).strip()
        encoded = query.replace(" ", "+")
        return {"tool": "open_browser_tab", "url": f"https://www.google.com/search?q={encoded}"}

    return None


def infer_taskbar_tool(message):
    """
    Detects requests to search & open apps via Windows taskbar search.
    If the user says 'open' or 'launch', sets launch=True so Enter is pressed.
    Examples:
      "search qbittorrent on my computer and open it" → search + launch
      "find notepad in taskbar"                       → search + launch
      "open vlc from taskbar"                         → search + launch
    """
    lowered = message.lower()

    # Detect intent to launch (not just search)
    launch_words = ("open", "launch", "run", "start", "open it", "and open")
    wants_launch = any(w in lowered for w in launch_words)

    patterns = [
        # "search X on my computer and open it"
        r"search\s+(\w[\w\s.-]*?)\s+(?:on|in|from|via|using)\s+(?:my\s+)?(?:computer|pc|taskbar|start|windows)",
        # "open X from taskbar / start / windows"
        r"(?:open|launch|run|start)\s+([\w][\w\s.-]*?)\s+(?:from|via|using|in|on)\s+(?:taskbar|start|windows|my computer|pc)",
        # "search taskbar for X"
        r"(?:taskbar|start)\s+search\s+(?:for\s+)?([\w][\w\s.-]+)",
        r"search\s+(?:in|on|using|the)?\s*(?:taskbar|start|windows search|search bar)\s+(?:for\s+)?([\w][\w\s.-]+)",
        # "find X in taskbar"
        r"(?:find|look for)\s+([\w][\w\s.-]+?)\s+(?:in|on)\s+(?:taskbar|start|windows)",
    ]
    for pat in patterns:
        match = re.search(pat, message, re.IGNORECASE)
        if match:
            query = match.group(1).strip().rstrip(".,")
            return {"tool": "taskbar_search", "query": query, "launch": wants_launch}

    # Natural shorthand: "open qbittorrent" / "launch notepad" with no URL or file intent
    if any(w in lowered for w in ("open", "launch", "run")):
        # Only if no URL-like content and no file keyword
        if not re.search(r"https?://|\.com|\.org|\.net", lowered):
            if "file" not in lowered and "folder" not in lowered and "github" not in lowered:
                app_match = re.search(
                    r"(?:open|launch|run|start)\s+([\w][\w\s.-]{1,30}?)(?:\s+(?:app|program|application|software))?\s*$",
                    message, re.IGNORECASE
                )
                if app_match:
                    query = app_match.group(1).strip()
                    return {"tool": "taskbar_search", "query": query, "launch": True}

    return None


def infer_window_tool(message):
    lowered = message.lower()
    patterns = [
        r"(?:switch to|go to|focus|open)\s+(?:the\s+)?(?:window\s+)?(?:called\s+)?(.+?)\s+(?:window|tab|app|application)",
        r"(?:bring up|show)\s+(.+?)\s+(?:window|app)",
    ]
    for pat in patterns:
        match = re.search(pat, message, re.IGNORECASE)
        if match:
            return {"tool": "switch_window", "title": match.group(1).strip()}
    return None


def try_parse_tool_call(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and payload.get("tool") in (
        "create_file", "create_github_repo", "push_project_to_github",
        "open_browser_tab", "taskbar_search", "switch_window", "type_text", "press_keys",
        "close_app", "close_browser_tab", "whatsapp_message"
    ):
        return payload
    return None


def run_tool(tool_call):
    t = tool_call.get("tool")
    if t == "push_project_to_github":
        return push_project_to_github(tool_call)
    if t == "create_github_repo":
        return create_github_repo(tool_call)
    if t == "open_browser_tab":
        return run_open_browser_tab(tool_call)
    if t == "taskbar_search":
        return run_taskbar_search(tool_call)
    if t == "switch_window":
        return run_switch_window(tool_call)
    if t == "type_text":
        return run_type_text(tool_call)
    if t == "press_keys":
        return run_press_keys(tool_call)
    if t == "close_app":
        app_target = clean_close_target(tool_call.get("app", "")).lower()
        if app_target in WEB_TARGETS:
            return run_close_browser_tab({"tool": "close_browser_tab", "title": app_target})
        return run_close_app(tool_call)
    if t == "close_browser_tab":
        return run_close_browser_tab(tool_call)
    if t == "whatsapp_message":
        # map "text" key -> "message" key internally
        tool_call = dict(tool_call)
        if "text" in tool_call and "message" not in tool_call:
            tool_call["message"] = tool_call.pop("text")
        return run_whatsapp_message(tool_call)
    if t == "create_file":
        target, display_path = safe_file_path(str(tool_call.get("path", "")))
        content = str(tool_call.get("content", ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"tool": "create_file", "path": str(display_path), "message": f"Created {display_path}."}
    raise ValueError(f"Unknown tool: {t}")


def run_command(args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=120)
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
        raise RuntimeError("No git remote named origin is configured.")
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
    return {"tool": "push_project_to_github", "branch": branch,
            "message": f"Pushed J.A.R.V.I.S to GitHub on branch {branch}. {push_output}".strip()}


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
        raise RuntimeError("GitHub CLI is not installed. Install gh and run gh auth login.")
    try:
        run_command(["gh", "auth", "status"])
    except RuntimeError:
        raise RuntimeError("GitHub CLI is not logged in. Run gh auth login.")
    if not (ROOT / ".git").exists():
        run_command(["git", "init"])
    url = run_command(["gh", "repo", "create", name, f"--{visibility}", "--source", str(ROOT), "--remote", "origin"])
    return {"tool": "create_github_repo", "name": name, "visibility": visibility,
            "message": f"Created GitHub repo {name} and set it as origin. {url}".strip()}


def infer_github_tool(message):
    lowered = message.lower()
    if "github" not in lowered or "repo" not in lowered:
        return None
    if not any(word in lowered for word in ("create", "make", "new")):
        return None
    match = re.search(r"(?:called|named|name)\s+([A-Za-z0-9._-]+)", message, flags=re.IGNORECASE)
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
    match = re.search(r"(?:commit message|message)\s*[:=]?\s*[\"']?([^\"'\n]+)", message, flags=re.IGNORECASE)
    commit_message = match.group(1).strip() if match else "Update JARVIS project"
    return {"tool": "push_project_to_github", "message": commit_message}



def infer_close_app_tool(message):
    """
    Detects requests to close/quit/kill an app.
    Examples:
      "close Blender"         -> close_app blender.exe
      "kill chrome"           -> close_app chrome.exe
      "quit notepad"          -> close_app notepad.exe
    """
    lowered = message.lower()
    close_words = ("close", "kill", "quit", "exit", "force close", "terminate", "end", "shut down")
    if not any(w in lowered for w in close_words):
        return None
    if any(w in lowered for w in ("file", "folder", "github", "repo", "tab", "browser")):
        return None
    pat = (
        r"(?:close|kill|quit|exit|force close|terminate|end|shut down)\s+"
        r"(?:(?:the|my)\s+)?(?:(?:app|program|application)\s+)?(?:called\s+)?"
        r"([\w][\w\s.-]{0,40}?)"
        r"(?:\s+(?:app|program|application|window))?"
        r"(?:\s+(?:in|on|from)\s+(?:the\s+)?(?:my\s+)?(?:task\s*bar|taskbar|start\s+menu))?"
        r"\s*$"
    )
    match = re.search(pat, message, re.IGNORECASE)
    if not match:
        return None
    app = match.group(1).strip().rstrip(".,")
    app = re.sub(r"\b(?:app|program|application|window)$", "", app, flags=re.IGNORECASE).strip()
    if app:
        return {"tool": "close_app", "app": app}
    return None


def infer_close_browser_tab_tool(message):
    lowered = message.lower()
    close_words = ("close", "kill", "quit", "exit", "terminate", "end", "shut down")
    if not any(w in lowered for w in close_words):
        return None
    if any(w in lowered for w in ("file", "folder", "github", "repo")):
        return None

    match = re.search(
        r"(?:close|kill|quit|exit|terminate|end|shut down)\s+"
        r"(?:(?:the|my)\s+)?(.+?)"
        r"(?:\s+(?:tab|website|site|page|window))?"
        r"(?:\s+(?:in|on|from)\s+(?:the\s+)?(?:browser|edge|chrome|firefox|brave))?"
        r"\s*$",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None

    target = clean_close_target(match.group(1))
    if not target:
        return None

    normalized = re.sub(r"\s+", " ", target.lower()).strip()
    explicit_browser_target = any(word in lowered for word in ("tab", "website", "site", "page"))
    looks_like_domain = bool(re.search(r"\.(?:com|org|net|io|dev|co|ke|gg|tv|app)\b", normalized))
    known_web_target = normalized in WEB_TARGETS
    known_app_target = normalized in APP_ALIASES

    if explicit_browser_target or looks_like_domain or (known_web_target and not known_app_target):
        return {"tool": "close_browser_tab", "title": target}
    return None


def infer_whatsapp_tool(message):
    """
    Detects requests to send a WhatsApp message.
    Examples:
      "text Ushindi on WhatsApp hello"
      "send WhatsApp message to Ushindi saying hi"
      "open WhatsApp and text Ushindi hey"
    """
    lowered = message.lower()
    if "whatsapp" not in lowered:
        return None
    if not any(w in lowered for w in ("text", "message", "send", "tell", "say", "write")):
        return None

    contact = None
    contact_patterns = [
        r"(?:send\s+(?:a\s+)?(?:whatsapp\s+)?message\s+to|send\s+to|text|message|tell)\s+([A-Za-z][\w\s]{1,30}?)\s+(?:on whatsapp|saying|:|that\b|hello|hi\b|hey\b)",
        r"whatsapp\s+and\s+(?:send\s+(?:a\s+)?message\s+to|text|message|tell)\s+([A-Za-z][\w\s]{1,30}?)\s+(?:saying|:|that\b|hello|hi\b|hey\b)",
        r"(?:text|message|send to|tell|whatsapp)\s+([A-Za-z][\w\s]{1,30}?)\s+(?:on whatsapp|saying|:|that\b|hello|hi\b|hey\b)",
        r"(?:to|for)\s+([A-Za-z][\w\s]{1,30}?)\s+(?:saying|on whatsapp|:|that\b)",
        r"whatsapp\s+(?:message\s+to\s+|text\s+)?([A-Za-z][\w\s]{1,30}?)(?:\s+saying|\s*:|\s+that\b)",
        r"(?:text|message)\s+([A-Za-z][\w]{1,20})",
    ]
    for pat in contact_patterns:
        m = re.search(pat, message, re.IGNORECASE)
        if m:
            contact = m.group(1).strip().rstrip(" ,.")
            break

    if not contact:
        return None

    msg_text = ""
    msg_patterns = [
        r"(?:saying|say|:\s*|message\s+is\s+|that\s+)(.+)$",
        r"(?:text|message)\s+\w[\w\s]{1,20}\s+(.+)$",
    ]
    for pat in msg_patterns:
        m = re.search(pat, message, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip().strip("\"'")
            if len(candidate) > 1 and "whatsapp" not in candidate.lower():
                msg_text = candidate
                break

    if not msg_text:
        msg_text = "Hey!"

    return {"tool": "whatsapp_message", "contact": contact, "text": msg_text}


def choose_tool(message, model):
    # Priority order: whatsapp > browser tab close > app close > git push > github > browser > taskbar > window > file
    whatsapp_tool = infer_whatsapp_tool(message)
    if whatsapp_tool:
        return whatsapp_tool
    close_tab_tool = infer_close_browser_tab_tool(message)
    if close_tab_tool:
        return close_tab_tool
    close_tool = infer_close_app_tool(message)
    if close_tool:
        return close_tool
    git_push_tool = infer_git_push_tool(message)
    if git_push_tool:
        return git_push_tool
    github_tool = infer_github_tool(message)
    if github_tool:
        return github_tool
    browser_tool = infer_browser_tool(message)
    if browser_tool:
        return browser_tool
    taskbar_tool = infer_taskbar_tool(message)
    if taskbar_tool:
        return taskbar_tool
    window_tool = infer_window_tool(message)
    if window_tool:
        return window_tool
    file_tool = infer_file_tool(message)
    if file_tool:
        return file_tool

    # LLM planner fallback
    planner_messages = [
        {
            "role": "system",
            "content": (
                "You are the tool planner for a local personal assistant. "
                "Return only valid JSON. No markdown. No explanation. "
                "Available tools:\n"
                '{"tool":"push_project_to_github","message":"..."}\n'
                '{"tool":"create_github_repo","name":"...","visibility":"public"}\n'
                '{"tool":"create_file","path":"...","content":"..."}\n'
                '{"tool":"open_browser_tab","url":"https://..."}\n'
                '{"tool":"taskbar_search","query":"..."}\n'
                '{"tool":"switch_window","title":"..."}\n'
                '{"tool":"type_text","text":"..."}\n'
                '{"tool":"press_keys","keys":"ctrl+t"}\n'
                '{"tool":"close_app","app":"appname.exe"}\n'
                '{"tool":"close_browser_tab","title":"youtube"}\n'
                '{"tool":"whatsapp_message","contact":"Name","text":"message"}\n'
                'If no tool is needed, return {"tool":null}.'
            ),
        },
        {"role": "user", "content": message},
    ]
    payload = {
        "model": model,
        "messages": planner_messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_ctx": 1024},
    }
    result = ollama_json("/api/chat", payload, method="POST")
    try:
        tool_call = json.loads(result["message"]["content"])
    except json.JSONDecodeError:
        return None
    if isinstance(tool_call, dict) and tool_call.get("tool") in (
        "create_file", "create_github_repo", "push_project_to_github",
        "open_browser_tab", "taskbar_search", "switch_window", "type_text", "press_keys",
        "close_app", "close_browser_tab", "whatsapp_message"
    ):
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
        "options": {"temperature": 0.7, "num_ctx": 4096},
    }
    result = ollama_json("/api/chat", payload, method="POST")
    reply = result["message"]["content"]
    tool_call = try_parse_tool_call(reply)
    if not tool_call:
        return reply

    tool_result = run_tool(tool_call)
    messages.append({"role": "assistant", "content": reply})
    messages.append({
        "role": "user",
        "content": "Tool result: " + json.dumps(tool_result) + "\nNow tell me briefly what you did.",
    })
    final_payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7, "num_ctx": 4096},
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
            sc_status = "available" if SYSTEM_CONTROL else "install pyautogui"
            self.send_json(200, {**load_state(), "system_control": sc_status})
            return
        if self.path.startswith("/api/capabilities"):
            self.send_json(200, {
                "system_control": SYSTEM_CONTROL,
                "web_browser": WEB_BROWSER,
                "platform": sys.platform,
            })
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
    if SYSTEM_CONTROL:
        print("System control: ENABLED (pyautogui, pygetwindow)")
    else:
        print("System control: DISABLED — run: pip install pyautogui pygetwindow")
    server = ThreadingHTTPServer(("127.0.0.1", 8000), JarvisHandler)
    print("J.A.R.V.I.S is running at http://127.0.0.1:8000")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
