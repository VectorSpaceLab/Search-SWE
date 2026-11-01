"""Convert Pi's JSON event stream to an auditable ATIF trajectory."""

from datetime import datetime, timezone
import hashlib
import json


def _content(content):
    """Separate visible content from reasoning and structured tool calls."""
    if isinstance(content, str):
        return content
    parts = []
    for part in content or []:
        kind = part.get("type") if isinstance(part, dict) else None
        if kind == "text":
            parts.append({"type": "text", "text": part["text"]})
        elif (kind == "image" and part.get("mimeType") in
              ("image/png", "image/jpeg", "image/gif", "image/webp")
              and isinstance(part.get("data"), str)):
            parts.append({"type": "image", "source": {
                "media_type": part["mimeType"],
                "path": f"data:{part['mimeType']};base64,{part['data']}",
            }})
        elif kind not in ("thinking", "toolCall"):
            # Keep unknown content visible rather than silently discarding it.
            parts.append({"type": "text", "text": json.dumps(part, ensure_ascii=False)})
    if any(part["type"] == "image" for part in parts):
        return parts
    return "\n".join(part["text"] for part in parts)


def _metrics(usage):
    metrics = {}
    # Pi reports uncached input, cache reads and cache writes separately.
    inputs = ("input", "cacheRead", "cacheWrite")
    if any(usage.get(key) is not None for key in inputs):
        metrics["prompt_tokens"] = sum(usage.get(key) or 0 for key in inputs)
    for source, target in (("output", "completion_tokens"), ("cacheRead", "cached_tokens")):
        if usage.get(source) is not None:
            metrics[target] = usage[source]
    cost = (usage.get("cost") or {}).get("total")
    if cost is not None:
        metrics["cost_usd"] = cost
    if usage.get("reasoning") is not None:
        # Reasoning tokens are already included in output; do not count twice.
        metrics["extra"] = {"reasoning_tokens": usage["reasoning"]}
    return metrics


def convert_events(text, instruction, model_name, version):
    steps = []
    session_id = None
    calls = {}
    last_assistant = None
    retry_error = None
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # CLI diagnostics are interleaved with JSON events.
        if not isinstance(event, dict):
            continue
        if event.get("type") == "session":
            identity = event.get("id")
            if isinstance(identity, str) and identity.strip():
                if session_id is not None and session_id != identity:
                    raise ValueError("Pi event stream contains multiple session IDs")
                session_id = identity
        if event.get("type") == "auto_retry_end":
            retry_error = None if event.get("success") else event.get("finalError", "retry failed")
        if event.get("type") != "message_end":
            continue
        message = event.get("message", {})
        role = message.get("role")
        if role == "toolResult":
            call_id = message.get("toolCallId")
            if call_id not in calls:
                raise ValueError(f"Pi tool result has no matching call: {call_id}")
            step = calls[call_id]
            step.setdefault("observation", {"results": []})["results"].append({
                "source_call_id": call_id,
                "content": _content(message.get("content", [])),
                "extra": {"pi_message": message},
            })
            continue
        if role not in ("assistant", "user", "system"):
            continue
        step = {"source": "agent" if role == "assistant" else role,
                "message": _content(message.get("content", [])),
                "extra": {"pi_message": message}}
        timestamp = message.get("timestamp")
        if timestamp is not None:
            if isinstance(timestamp, (int, float)):
                timestamp = datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat(
                    timespec="milliseconds").replace("+00:00", "Z")
            step["timestamp"] = timestamp
        if role == "assistant":
            last_assistant = message
            reasoning = []
            if message.get("model"):
                step["model_name"] = "/".join(filter(None, (message.get("provider"), message["model"])))
            metrics = _metrics(message.get("usage") or {})
            if metrics:
                step["metrics"] = metrics
            for part in message.get("content", []):
                if isinstance(part, dict) and part.get("type") == "thinking":
                    reasoning.append(part.get("thinking", ""))
                if isinstance(part, dict) and part.get("type") == "toolCall":
                    step.setdefault("tool_calls", []).append({
                        "tool_call_id": part["id"], "function_name": part["name"],
                        "arguments": part.get("arguments", {}),
                    })
                    calls[part["id"]] = step
            if any(reasoning):
                step["reasoning_content"] = "\n".join(reasoning)
        steps.append(step)
    # Pi emits the actual user prompt. Only synthesize one for incomplete logs;
    # never deduplicate genuine user turns, even when their text is identical.
    if not any(step["source"] == "user" for step in steps):
        steps.insert(0, {"source": "user", "message": instruction,
                         "extra": {"instruction_fallback": True}})
    for number, step in enumerate(steps, 1):
        step["step_id"] = number
    error = retry_error
    if last_assistant is None:
        error = error or "Pi produced no assistant messages"
    elif last_assistant.get("stopReason") in ("error", "aborted"):
        error = error or last_assistant.get("errorMessage", "Pi aborted")
    elif last_assistant.get("stopReason") == "toolUse":
        error = error or "Pi ended before completing its final turn"
    trajectory = {
        "schema_version": "ATIF-v1.7",
        "agent": {"name": "pi", "version": version, "model_name": model_name},
        "steps": steps,
    }
    if session_id is not None:
        trajectory["session_id"] = session_id
    else:
        # A failed/truncated log may lack Pi's session header. Identify the
        # document deterministically without inventing a native session ID.
        payload = json.dumps([text, instruction, model_name, version], ensure_ascii=False)
        trajectory["trajectory_id"] = "pi-log-" + hashlib.sha256(payload.encode()).hexdigest()
        trajectory["notes"] = (
            "Pi session header unavailable; trajectory_id is a deterministic "
            "content hash, not a native session ID."
        )
    totals = {"total_steps": len(steps)}
    for key in ("prompt_tokens", "completion_tokens", "cached_tokens", "cost_usd"):
        values = [step["metrics"][key] for step in steps if key in step.get("metrics", {})]
        if values:
            totals[f"total_{key}"] = sum(values)
    trajectory["final_metrics"] = totals
    return trajectory, error
