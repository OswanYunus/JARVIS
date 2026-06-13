const messagesEl = document.querySelector("#messages");
const formEl = document.querySelector("#chatForm");
const inputEl = document.querySelector("#messageInput");
const sendButtonEl = document.querySelector("#sendButton");
const modelSelectEl = document.querySelector("#modelSelect");
const rulesEditorEl = document.querySelector("#rulesEditor");
const saveRulesEl = document.querySelector("#saveRules");
const clearChatEl = document.querySelector("#clearChat");
const toolStatusEl = document.querySelector("#toolStatus");

function addMessage(role, content) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = content;
  messagesEl.appendChild(node);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Something went wrong.");
  }
  return data;
}

async function loadModels() {
  try {
    const data = await api("/api/models");
    modelSelectEl.innerHTML = "";

    const models = data.models.length ? data.models : [data.default];
    for (const model of models) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      modelSelectEl.appendChild(option);
    }
  } catch (err) {
    addMessage("system", `Ollama problem: ${err.message}`);
    modelSelectEl.innerHTML = `<option value="llama3.2:3b">llama3.2:3b</option>`;
  }
}

async function loadHistory() {
  const data = await api("/api/history");
  messagesEl.innerHTML = "";

  if (!data.messages.length) {
    addMessage("system", "Ready. Pull a model, pick it here, and ask me something.");
    return;
  }

  for (const message of data.messages) {
    addMessage(message.role, message.content);
  }
}

async function loadRules() {
  const data = await api("/api/rules");
  rulesEditorEl.value = data.rules;
}

async function loadState() {
  const data = await api("/api/state");
  const enabled = Boolean(data.tools_enabled);
  toolStatusEl.textContent = enabled ? "Enabled" : "Locked";
  toolStatusEl.classList.toggle("locked", !enabled);
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = inputEl.value.trim();
  if (!message) return;

  inputEl.value = "";
  addMessage("user", message);
  sendButtonEl.disabled = true;
  sendButtonEl.textContent = "Thinking";

  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        model: modelSelectEl.value,
      }),
    });
    addMessage("assistant", data.reply);
  } catch (err) {
    addMessage("system", err.message);
  } finally {
    sendButtonEl.disabled = false;
    sendButtonEl.textContent = "Send";
    await loadState();
    inputEl.focus();
  }
});

saveRulesEl.addEventListener("click", async () => {
  saveRulesEl.disabled = true;
  saveRulesEl.textContent = "Saving";
  try {
    await api("/api/rules", {
      method: "POST",
      body: JSON.stringify({ rules: rulesEditorEl.value }),
    });
    addMessage("system", "Rules saved. New replies will use them.");
  } catch (err) {
    addMessage("system", err.message);
  } finally {
    saveRulesEl.disabled = false;
    saveRulesEl.textContent = "Save";
  }
});

clearChatEl.addEventListener("click", async () => {
  await api("/api/clear", { method: "POST", body: "{}" });
  messagesEl.innerHTML = "";
  addMessage("system", "Chat cleared.");
});

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    formEl.requestSubmit();
  }
});

await loadModels();
await loadRules();
await loadState();
await loadHistory();
