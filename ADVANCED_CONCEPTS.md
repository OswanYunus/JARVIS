# Making J.A.R.V.I.S Smarter: Three Advanced Concepts

---

## 1. **System Prompt (Rules.md) — Make Behavior Explicit**

### What It Does
The system prompt is J.A.R.V.I.S's personality and constraints. It tells the AI:
- What it should do and NOT do
- How to reason about requests
- When to ask for confirmation
- Priority of safety vs convenience

### Current (Weak)
```markdown
You are J.A.R.V.I.S, my personal local AI assistant.
You are my servant...
```
**Problem:** Too vague. Doesn't teach intent reasoning.

### Stronger Version

Edit `rules.md` to this:

```markdown
# J.A.R.V.I.S System Rules

## Personality
You are J.A.R.V.I.S, a local AI assistant. You are helpful, clever, and respectful.
You follow commands but also think about consequences.

## Intent Classification
When the user speaks, first classify the request:
1. **Action Request** → "uninstall qbittorrent" = classify as UNINSTALL
2. **Information Request** → "how much disk space?" = classify as QUERY
3. **Clarification Needed** → "remove that thing" = AMBIGUOUS, ask "Which app?"
4. **Potentially Risky** → "delete all files in system32" = REFUSE

## Pattern Recognition Examples
- User says "remove q-bit" → recognize "qbittorrent" (typo/abbreviation)
- User says "my hard drive is full" → suggest clearing temp files, cache
- User says "computer is slow" → suggest malware scan, disk check, startup apps
- User says "can't connect" → suggest network reset, firewall check, DNS flush

## Safety Rules
- ALWAYS ask before: deleting files, modifying registry, uninstalling system software
- NEVER: format drives, delete system folders, modify SYSTEM or ADMIN accounts
- REQUIRE admin confirmation for: system restarts, shutdowns, firewall changes
- OPTIONAL confirmation for: temp file cleanup, cache clearing, uninstalling user apps

## Reasoning Process
When a user asks something, think:
1. What does the user REALLY want? (intent)
2. Is there a better way to do it? (optimization)
3. What could go wrong? (safety)
4. Do I have the right tool? (capability)
5. Should I ask first? (permission)

## Response Format
- FOR ACTION: Confirm what you'll do, do it, report result
- FOR QUERY: Provide clear information with options
- FOR AMBIGUOUS: Ask clarifying questions
- FOR RISKY: Explain why and suggest safer alternative
```

### How to Use It
1. Open http://127.0.0.1:8000
2. Click the "Rules" text area on the left sidebar
3. Paste the content above
4. Click "Save"

**Result:** J.A.R.V.I.S will now reason better and ask for confirmation before dangerous actions.

---

## 2. **Intent Model — Separate Understanding from Action**

### The Problem
Currently, J.A.R.V.I.S does this:
```
User input → Pattern match → Run tool
```

This breaks if the pattern doesn't match exactly.

### The Solution: Two-Stage Processing
```
User input → [INTENT CLASSIFIER] → "user wants to uninstall software"
                                ↓
                          [ACTION PLANNER] → "use winget uninstall"
                                ↓
                          [EXECUTOR] → runs command
```

### How to Implement

**Stage 1: Add Intent Classification (Add to backend/server.py)**

```python
def classify_intent(message, model):
    """
    Classify what the user WANTS, separate from HOW to do it.
    Examples:
      "uninstall qbittorrent" → intent: UNINSTALL_APP
      "my computer is slow" → intent: DIAGNOSE_PERFORMANCE
      "what's my IP" → intent: GET_INFO
    """
    classifier_prompt = [
        {
            "role": "system",
            "content": (
                "Classify the user's intent. Return JSON with 'intent' and 'confidence' (0-1). "
                "Possible intents: UNINSTALL_APP, INSTALL_APP, DELETE_FILE, QUERY_INFO, DIAGNOSE, "
                "SECURITY_SCAN, NETWORK_CHECK, SYSTEM_CONFIG, SCHEDULE_TASK, BACKUP, HELP.\n"
                'Return: {"intent": "UNINSTALL_APP", "confidence": 0.95, "target": "qbittorrent"}'
            ),
        },
        {"role": "user", "content": message},
    ]
    
    payload = {
        "model": model,
        "messages": classifier_prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.3, "num_ctx": 512},
    }
    
    result = ollama_json("/api/chat", payload, method="POST")
    try:
        return json.loads(result["message"]["content"])
    except:
        return {"intent": "HELP", "confidence": 0}
```

**Stage 2: Use Intent in Tool Selection**

```python
def choose_tool_by_intent(message, model):
    intent_info = classify_intent(message, model)
    intent = intent_info.get("intent", "HELP")
    
    if intent == "UNINSTALL_APP":
        target = intent_info.get("target", "")
        return {"tool": "uninstall_app", "app": target}
    
    elif intent == "DIAGNOSE_PERFORMANCE":
        # Multiple tools: scan malware, check disk, check startup apps, etc.
        return [
            {"tool": "scan_malware"},
            {"tool": "clear_temp_files"},
            {"tool": "get_system_info"}
        ]
    
    elif intent == "QUERY_INFO":
        topic = intent_info.get("topic", "")
        return {"tool": "get_system_info", "topic": topic}
    
    # ... handle other intents
    return None
```

### Why This Matters

**Before Intent Model:**
```
User: "remove q-bit"
J.A.R.V.I.S: "I don't understand. Did you mean 'uninstall qbittorrent'?"
```

**After Intent Model:**
```
User: "remove q-bit"
J.A.R.V.I.S: "I'll uninstall qbittorrent."
[Actually uninstalls it]
```

---

## 3. **Memory — Learn from Sessions**

### Why It Matters
Currently, every chat resets. J.A.R.V.I.S forgets:
- Which apps you have installed
- Which files you care about
- Your preferences (always auto-confirm? or always ask?)
- What you did before

### How to Implement

**Step 1: Add Memory Table to Database**

Add this to `backend/server.py` in `init_db()`:

```python
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        # Existing messages table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (...)
            """
        )
        
        # ADD THIS: Memory table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                created_at INTEGER,
                accessed_at INTEGER
            )
            """
        )
```

**Step 2: Add Memory Helpers**

```python
def save_memory(category, key, value):
    """Save to long-term memory."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO memory (category, key, value, created_at, accessed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (category, key, value, int(time.time()), int(time.time())),
        )

def get_memory(category, key):
    """Retrieve from memory."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT value FROM memory WHERE category = ? AND key = ?",
            (category, key),
        ).fetchone()
    return row[0] if row else None

def list_memory(category):
    """List all memories in a category."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT key, value FROM memory WHERE category = ? ORDER BY accessed_at DESC",
            (category,),
        ).fetchall()
    return {key: value for key, value in rows}
```

**Step 3: Save Installed Apps to Memory**

```python
def update_installed_apps_cache():
    """Cache installed apps so we don't query winget every time."""
    apps = get_installed_apps()
    save_memory("system", "installed_apps", json.dumps(apps))
    save_memory("system", "last_app_scan", str(int(time.time())))
```

**Step 4: Use Memory in Intent Classifier**

```python
def classify_intent(message, model):
    # Get recent memory
    installed_apps = json.loads(get_memory("system", "installed_apps") or "[]")
    user_preferences = list_memory("preferences")
    
    # Use this in the prompt!
    classifier_prompt = [
        {
            "role": "system",
            "content": (
                f"You know about these installed apps: {', '.join([a['name'] for a in installed_apps[:10]])}...\n"
                f"User preferences: {user_preferences}\n"
                "Now classify the intent..."
            ),
        },
        {"role": "user", "content": message},
    ]
    # ... rest of function
```

### Memory Categories (Examples)

| Category | Key | Value | Purpose |
|----------|-----|-------|---------|
| `system` | `installed_apps` | JSON list | Cache app list |
| `system` | `last_app_scan` | timestamp | Refresh cache every 1 hour |
| `preferences` | `auto_confirm_delete` | `false` | Always ask before deleting |
| `preferences` | `auto_confirm_restart` | `false` | Always ask before restart |
| `history` | `last_malware_scan` | timestamp | Remind if overdue |
| `history` | `favorite_tools` | JSON list | Most used tools |
| `files` | `important_folders` | JSON list | Folders to never delete |

### Accessing Memory in Chat

Add UI button to view memory:

```html
<button id="viewMemory">View Memory</button>
<script>
document.querySelector("#viewMemory").addEventListener("click", async () => {
  const data = await api("/api/memory");
  console.log("System memory:", data);
});
</script>
```

---

## 4. **Running the Script & Ollama Setup**

### First Time Setup

**Step 1: Install Ollama** (if not done)
```powershell
# Download from https://ollama.ai
# Or install via winget:
winget install JanDeDobbeleer.Ollama
```

**Step 2: Pull a Small Model** (Fast, for testing)
```powershell
ollama pull llama3.2:3b
```

**Step 3: Verify Ollama Runs**
```powershell
ollama list
```
You should see `llama3.2:3b` installed.

**Step 4: Start Ollama** (in background)
```powershell
ollama serve
```
Leave this terminal open.

**Step 5: In New Terminal, Run J.A.R.V.I.S** (this terminal, your current one)
```powershell
cd c:\Users\oswan\Projects\J.A.R.V.I.S
python backend\server.py
```

**Step 6: Open http://127.0.0.1:8000 in Browser**

### Run Every Time
```powershell
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Start J.A.R.V.I.S
cd c:\Users\oswan\Projects\J.A.R.V.I.S
python backend\server.py
```

---

## 5. **Summary: Making JARVIS Smarter**

| Concept | What It Does | Effort | Impact |
|---------|-------------|--------|--------|
| **Better Rules** | Teach explicit reasoning | 30 min | ⭐⭐⭐⭐ |
| **Intent Model** | Fuzzy intent recognition | 2-3 hours | ⭐⭐⭐⭐⭐ |
| **Memory** | Remember context across sessions | 1-2 hours | ⭐⭐⭐⭐ |
| **50+ Tools** | Expand capabilities | 1 week | ⭐⭐⭐⭐⭐ |
| **Stronger Model** | Use qwen2.5:7b instead of llama3.2:3b | 30 min | ⭐⭐⭐⭐ |

**Recommended Next Steps:**
1. Update `rules.md` (do now, 30 min)
2. Test winget uninstall (do now)
3. Add intent classifier (tomorrow)
4. Add memory system (later this week)
5. Add 50+ tools incrementally

---

## FAQ

**Q: How do I upgrade to a stronger model?**
```powershell
ollama pull qwen2.5:7b
# Then in J.A.R.V.I.S UI, select qwen2.5:7b from the Model dropdown
```

**Q: Can I run this without Ollama?**
No. J.A.R.V.I.S needs a local LLM. Alternatives:
- Ollama (recommended, free)
- LM Studio (slower)
- vLLM (for server setup)

**Q: Can I use OpenAI's API instead?**
Yes, but I'd need to change the backend. Want me to add that?

**Q: Is admin bypass possible?**
Windows admin prompts appear because `winget` needs elevation. You can:
1. Run PowerShell as Admin once, then prompts disappear for that session
2. Use `runas` command to auto-elevate (risky if misused)
3. Pre-approve via Group Policy (enterprise only)

For your use case, just approve the UAC prompt when it appears—it's a safety feature.
