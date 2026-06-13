# J.A.R.V.I.S Local AI

A small local AI chat app for Ollama. It has no login, saves chat history in SQLite, and lets you edit the assistant rules from the browser.

## 1. Check Ollama

If `ollama` works in PowerShell:

```powershell
ollama --version
```

If PowerShell says `ollama` is not recognized, use the full path:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" --version
```

## 2. Download a free model

Start with this small model:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull llama3.2:3b
```

If your laptop is stronger, you can later try:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull qwen2.5:7b
```

## 3. Start the app

From this project folder:

```powershell
python backend\server.py
```

Then open:

```text
http://127.0.0.1:8000
```

## 4. Use it

- Type a message and press Enter.
- Use Shift+Enter for a new line.
- Edit the rules on the left and click Save.
- Chat history is stored in `jarvis.db`.
- The assistant behavior comes from `rules.md`.

## 5. Stop it

Press Ctrl+C in the terminal running the server.

## GitHub repo creation

J.A.R.V.I.S can create a GitHub repository through GitHub CLI.

Install GitHub CLI:

```powershell
winget install --id GitHub.cli
```

Log in once:

```powershell
gh auth login
```

Then ask J.A.R.V.I.S:

```text
Create a GitHub repository called Jarvis
```

The app will:

- create the GitHub repo
- skip README/license/gitignore
- initialize local git if needed
- set the remote as `origin`

## Push this project to GitHub

If `origin` is already configured, ask J.A.R.V.I.S:

```text
Push this JARVIS project to GitHub with commit message Initial JARVIS project
```

The app will:

- run `git add .`
- commit changes if there are changes
- push the current branch to `origin`

## Next upgrades

- Stream replies token by token.
- Add document upload and RAG.
- Add long-term memory notes.
- Add voice input/output.
- Add project-specific tools.
