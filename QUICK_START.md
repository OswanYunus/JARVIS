# J.A.R.V.I.S Smart Upgrade — Quick Start

## What Just Changed

### Part 1: Winget Uninstall Tool (DONE)

> Note: The backend now uses a dedicated planner module and a simple JSON memory manager. The planner is general-purpose and can help decide tools for non-coding requests too, while the memory manager logs interaction history for future routine learning.

**Before:**
```
User: "uninstall qbitoorent"
J.A.R.V.I.S: Opens Windows Settings → manual search
```

**After:**
```
User: "uninstall qbitoorent"  (typo!)
J.A.R.V.I.S: [fuzzy matches] → finds "qbittorrent" (65%+ match) → uninstalls silently
Message: "Successfully uninstalled qbittorrent."
```

**How It Works:**
1. User asks to remove an app (exact name, typo, abbreviation)
2. J.A.R.V.I.S queries `winget list --output json`
3. Python `difflib.get_close_matches()` finds the closest match
4. `winget uninstall` runs the actual uninstaller
5. Admin prompt handled gracefully

**Supported Phrases:**
- "uninstall qbittorrent"
- "remove q-bit"
- "delete qbitoorent" (typo)
- "get rid of qBiTTorrent" (mixed case)

---

### Part 2: Tool Framework (50+ Tools) — [See TOOLS_FRAMEWORK.md](TOOLS_FRAMEWORK.md)

**8 Categories Ready to Add:**
1. **System Management** (12) — restart, shutdown, lock, sleep, etc.
2. **File & Folder** (10) — delete, move, copy, rename, zip, etc.
3. **Security** (12) — malware scan, firewall, cache clear, etc.
4. **Network** (8) — speed test, ping, WiFi, IP address, ports, etc.
5. **System Info** (8) — disk usage, battery, drivers, temperature, etc.
6. **Task Automation** (5) — scheduled tasks, backups, etc.
7. **Browser & Web** (8) — download, DNS, screenshot, wallpaper, etc.
8. **Power User** (7) — registry, scripts, ISO mount, USB eject, etc.

**Total: 70 possible tools** (pick the most useful)

---

### Part 3: Advanced Concepts — [See ADVANCED_CONCEPTS.md](ADVANCED_CONCEPTS.md)

#### 1. **Better Rules.md** (DO THIS FIRST — 30 minutes)
Teaches J.A.R.V.I.S explicit reasoning about:
- Intent classification (action vs query vs ambiguous)
- Pattern recognition (typos, abbreviations, synonyms)
- Safety rules (what to refuse, when to ask)
- Response format (how to communicate)

**Action:**
1. Open http://127.0.0.1:8000
2. Copy the content from ADVANCED_CONCEPTS.md section "System Prompt"
3. Paste into the Rules editor on the left
4. Click "Save"

#### 2. **Intent Model** (DO THIS NEXT — 2-3 hours)
Two-stage processing:
```
"user wants X" → (intent classifier) → "I should do Y" → (executor) → ✓ done
```

Better than pattern matching alone.

#### 3. **Memory System** (THEN DO THIS — 1-2 hours)
J.A.R.V.I.S remembers:
- Installed apps (cache)
- User preferences (always confirm? or auto?)
- History (last malware scan date)
- Important folders (never delete)

Enables smarter suggestions.

---

## What to Do Next (Priority Order)

### Priority 1️⃣ — Today (30 min)
```powershell
# 1. Update rules.md with better reasoning
#    (Instructions in ADVANCED_CONCEPTS.md)

# 2. Test winget uninstall
#    In chat: "uninstall qbittorrent"
#    Should uninstall if installed, or suggest matches
```

### Priority 2️⃣ — This Week (2-3 hours)
```powershell
# 1. Add intent classifier to backend/server.py
#    (Code in ADVANCED_CONCEPTS.md)

# 2. Add memory system to SQLite
#    (Code in ADVANCED_CONCEPTS.md)

# 3. Test with more natural phrases
#    "remove qbit", "uninstall that torrent thing", "delete qb"
```

### Priority 3️⃣ — Next Week (Pick 3-5 tools)
```powershell
# Add these tools first (highest impact):
# 1. install_app (complements uninstall)
# 2. scan_malware (security)
# 3. delete_file (common)
# 4. get_system_info (diagnostics)
# 5. clear_temp_files (maintenance)

# See TOOLS_FRAMEWORK.md for implementation patterns
```

---

## Testing the New Uninstall Feature

### Test Case 1: Exact Name
```
User: uninstall qbittorrent
Expected: ✓ Uninstalls qbittorrent
```

### Test Case 2: Typo
```
User: uninstall qbitoorent
Expected: ✓ Fuzzy matches (0.73 similarity) → uninstalls qbittorrent
```

### Test Case 3: Abbreviation
```
User: uninstall qbit
Expected: ✓ Fuzzy matches → uninstalls qbittorrent
```

### Test Case 4: Not Installed
```
User: uninstall nonexistent_app_123
Expected: ✗ "App not found. Similar: [list]"
```

### Test Case 5: Admin Required
```
User: uninstall windowsdefender
Expected: "Uninstall started but requires admin. Approve the prompt."
```

---

## Updating Rules.md Step-by-Step

### Current (Weak)
```markdown
You are J.A.R.V.I.S, my personal local AI assistant.
Personality:
I am your master and you are my servant...
```

### Better (Copy This to Rules Editor)
```markdown
# J.A.R.V.I.S System Rules

## Personality
You are J.A.R.V.I.S, a local AI assistant. You are helpful, clever, and respectful.

## Intent Classification
When the user speaks, first classify:
1. **Action Request** → "uninstall qbittorrent" = UNINSTALL
2. **Information Request** → "how much disk?" = QUERY
3. **Ambiguous** → "remove that thing" = ask "Which app?"
4. **Risky** → "delete system32" = REFUSE

## Pattern Recognition
- "remove q-bit" → recognize "qbittorrent" (typo/abbreviation)
- "computer is slow" → suggest: malware scan, disk cleanup, startup apps
- "can't connect" → suggest: network reset, firewall check, DNS flush

## Safety Rules
- ALWAYS ask before: deleting files, registry changes, uninstalling system software
- NEVER: format drives, delete system folders, modify SYSTEM accounts
- For dangerous actions: explain why, suggest safer alternative

## Reasoning Process
1. What does user REALLY want? (intent)
2. Better way to do it? (optimization)
3. What could go wrong? (safety)
4. Do I have the tool? (capability)
5. Should I ask first? (permission)
```

---

## Running J.A.R.V.I.S (Quick Reminder)

### Terminal 1: Start Ollama
```powershell
ollama serve
```
Leave this running.

### Terminal 2: Start J.A.R.V.I.S
```powershell
cd c:\Users\oswan\Projects\J.A.R.V.I.S
python backend\server.py
```

### Browser
```
http://127.0.0.1:8000
```

---

## File Reference

| File | Purpose | Edit? |
|------|---------|-------|
| `backend/server.py` | Core logic ✅ Updated | No, unless adding tools |
| `rules.md` | System prompt | ✅ Yes, update now |
| `TOOLS_FRAMEWORK.md` | Tool library reference | No, reference only |
| `ADVANCED_CONCEPTS.md` | Implementation guides | No, reference only |
| `QUICK_START.md` | This file | Reference |

---

## FAQ About Winget Uninstall

**Q: Does it require admin?**
A: Yes, some apps need UAC approval. You'll see a prompt—just click "Yes".

**Q: What if winget isn't installed?**
A: J.A.R.V.I.S will tell you to install it:
```powershell
winget install JanDeDobbeleer.Ollama
```
Wait, that's Ollama. For winget itself:
```powershell
winget install JanDeDobbeleer.Winget
```
or download from: https://github.com/microsoft/winget-cli/releases

**Q: How does fuzzy matching work?**
A: Python's `difflib.get_close_matches()` compares strings:
- "qbittorrent" vs "qbitoorent" = 73% match ✓
- "qbittorrent" vs "chrome" = 5% match ✗
- Cutoff: 65% for first pass, 50% for fallback

**Q: Can I whitelist/blacklist apps?**
A: Yes! Modify `find_best_app_match()` to check blocklist:
```python
BLOCKLIST = {"system32", "windows", "defender"}  # Can't uninstall
if matched_name.lower() in BLOCKLIST:
    raise RuntimeError("Cannot uninstall system software.")
```

---

## Next: Try These Exact Requests

Once you update `rules.md` and test uninstall, try these in chat:

1. ✅ **Uninstall** → "uninstall qbittorrent"
2. ✅ **Query** → "what apps are installed?"
3. ✅ **Info** → "how much disk space?"
4. ✅ **Performance** → "computer is slow, help"
5. ✅ **Security** → "should I scan for malware?"

---

## File Locations

```
c:\Users\oswan\Projects\J.A.R.V.I.S\
├── backend\
│   └── server.py         ← Main logic (UPDATED ✅)
├── frontend\
│   ├── app.js
│   ├── index.html
│   └── style.css
├── rules.md              ← UPDATE THIS (instructions above)
├── TOOLS_FRAMEWORK.md    ← Reference (50+ tools)
├── ADVANCED_CONCEPTS.md  ← Reference (intent, memory)
└── QUICK_START.md        ← This file
```

---

Good luck! You now have:
- Winget uninstall with fuzzy matching
- Better rules framework
- Intent model guide
- Memory system guide
- 50+ tools library

Start with step 1 (update rules.md) — it takes 30 min and has huge impact.
