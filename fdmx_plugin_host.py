"""FDMX isolated plugin worker. JSON-lines IPC protocol."""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

MAX_MESSAGE_BYTES = 1024 * 1024
EVENTS = {"app.started", "download.completed", "download.failed"}

def send(message):
    raw = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES: raise ValueError("IPC message exceeds 1 MiB")
    sys.stdout.write(raw + "\n"); sys.stdout.flush()

class WorkerAPI:
    def __init__(self, plugin_id, permissions):
        self.plugin_id, self.permissions, self.hooks, self.next_id = plugin_id, set(permissions), {}, 1
        self.pending_responses = {}
    def _rpc(self, method, **values):
        rid = self.next_id; self.next_id += 1
        send({"type":"rpc","id":rid,"method":method,**values})
        if rid in self.pending_responses:
            response = self.pending_responses.pop(rid)
            if not response.get("ok"): raise PermissionError(response.get("error", "RPC denied"))
            return
        while True:
            line = sys.stdin.readline()
            if not line: raise EOFError("FDMX closed plugin IPC")
            if len(line.encode("utf-8", errors="replace")) > MAX_MESSAGE_BYTES: raise ValueError("IPC message exceeds 1 MiB")
            response = json.loads(line)
            if response.get("type") == "event":
                event_name, payload = response.get("name"), response.get("payload", {})
                if event_name in EVENTS and isinstance(payload, dict):
                    self.dispatch(event_name, payload)
                if rid in self.pending_responses:
                    pending = self.pending_responses.pop(rid)
                    if not pending.get("ok"): raise PermissionError(pending.get("error", "RPC denied"))
                    return
                continue
            if response.get("type") == "shutdown":
                raise EOFError("Plugin worker is shutting down")
            if response.get("type") == "rpc_result":
                response_id = response.get("id")
                if response_id == rid:
                    if not response.get("ok"): raise PermissionError(response.get("error", "RPC denied"))
                    return
                if isinstance(response_id, int):
                    self.pending_responses[response_id] = response
    def log(self, message):
        if "app.log" not in self.permissions: raise PermissionError("Missing app.log")
        self._rpc("log", message=str(message)[:1000])
    def notify(self, title, message):
        if "ui.notifications" not in self.permissions: raise PermissionError("Missing ui.notifications")
        self._rpc("notify", title=str(title)[:120], message=str(message)[:1000])
    def on(self, event_name, callback):
        if "app.events" not in self.permissions: raise PermissionError("Missing app.events")
        if event_name not in EVENTS or not callable(callback): raise ValueError("Unsupported event or callback")
        self.hooks.setdefault(event_name, []).append(callback)
    def dispatch(self, name, payload):
        for callback in tuple(self.hooks.get(name, ())): callback(dict(payload))

def main():
    if len(sys.argv) != 5: return 2
    folder, entrypoint, pid = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    permissions = json.loads(sys.argv[4]); entry = folder / entrypoint
    if entry.parent.resolve() != folder.resolve() or not entry.is_file(): raise ValueError("Invalid plugin entrypoint")
    spec = importlib.util.spec_from_file_location("fdmx_worker_plugin", entry)
    if spec is None or spec.loader is None: raise ImportError("Cannot load plugin entrypoint")
    module = importlib.util.module_from_spec(spec); api = WorkerAPI(pid, permissions)
    try:
        spec.loader.exec_module(module)
        register = getattr(module, "register", None)
        if not callable(register): raise TypeError("Plugin must define register(api)")
        register(api); send({"type":"ready"})
    except Exception as exc:
        send({"type":"startup_error","message":f"{type(exc).__name__}: {exc}"}); return 1
    while True:
        line = sys.stdin.readline()
        if not line: break
        if len(line.encode("utf-8", errors="replace")) > MAX_MESSAGE_BYTES:
            send({"type":"fatal","message":"Incoming IPC exceeds 1 MiB"}); break
        try:
            msg = json.loads(line)
            if msg.get("type") == "shutdown":
                shutdown = getattr(module, "shutdown", None)
                if callable(shutdown): shutdown()
                break
            if msg.get("type") == "event" and msg.get("name") in EVENTS and isinstance(msg.get("payload"), dict):
                api.dispatch(msg["name"], msg["payload"])
        except Exception as exc:
            send({"type":"fatal","message":f"{type(exc).__name__}: {exc}"}); return 1
    return 0

if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        try: send({"type":"fatal","message":f"{type(exc).__name__}: {exc}"})
        except Exception: pass
        raise
