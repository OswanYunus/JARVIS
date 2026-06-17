from urllib import request
import json
from typing import Any, Dict, Optional


class Planner:
    def __init__(self, ollama_url: str):
        self.ollama_url = ollama_url

    def ollama_json(self, path: str, payload: Optional[Dict[str, Any]] = None, method: str = "GET") -> Dict[str, Any]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(f"{self.ollama_url}{path}", data=data, headers=headers, method=method)
        with request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))

    def plan_tool_call(
        self,
        message: str,
        model: str,
        preferences: Optional[Dict[str, Any]] = None,
        routines: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        memory_context = {
            "preferences": preferences or {},
            "routines": routines or {},
        }
        memory_prompt = ""
        if preferences or routines:
            memory_prompt = (
                "Known user memory (preferences and routines):\n"
                + json.dumps(memory_context, indent=2)
                + "\n"
            )

        planner_messages = [
            {
                "role": "system",
                "content": (
                    "You are the tool planner for a local personal assistant. "
                    "Return only valid JSON. No markdown. No explanation. "
                    + memory_prompt
                    + "Available tools:\n"
                    + '{"tool":"push_project_to_github","message":"..."}\n'
                    + '{"tool":"create_github_repo","name":"...","visibility":"public"}\n'
                    + '{"tool":"create_file","path":"...","content":"..."}\n'
                    + '{"tool":"open_browser_tab","url":"https://..."}\n'
                    + '{"tool":"taskbar_search","query":"..."}\n'
                    + '{"tool":"switch_window","title":"..."}\n'
                    + '{"tool":"type_text","text":"..."}\n'
                    + '{"tool":"press_keys","keys":"ctrl+t"}\n'
                    + '{"tool":"close_app","app":"appname.exe"}\n'
                    + '{"tool":"uninstall_app","app":"qbittorrent"}\n'
                    + '{"tool":"close_browser_tab","title":"youtube"}\n'
                    + '{"tool":"whatsapp_message","contact":"Name","text":"message"}\n'
                    + 'If no tool is needed, return {"tool":null}.'
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
        result = self.ollama_json("/api/chat", payload, method="POST")
        return self.parse_tool_call(result.get("message", {}).get("content", ""))

    def parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
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
            "close_app", "close_browser_tab", "uninstall_app", "whatsapp_message"
        ):
            return payload
        return None
