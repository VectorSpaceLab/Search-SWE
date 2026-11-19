"""Run agy with a loopback Gemini API backed by one OpenRouter chat model.

The bridge is uploaded to the agent container and uses only its Python standard
library. It follows the container's existing egress policy.
"""

import base64
from collections import defaultdict, deque
from http import HTTPStatus
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
import signal
import subprocess
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_REQUEST_BYTES = 64 * 1024 * 1024
FINISH_REASONS = {
    "stop": "STOP", "tool_calls": "STOP", "length": "MAX_TOKENS",
    "content_filter": "SAFETY",
}


def encode(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def content_part(part):
    if "text" in part:
        return {"type": "text", "text": part["text"]}
    if data := part.get("inlineData"):
        mime = data.get("mimeType", "")
        if mime.startswith("image/"):
            return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data['data']}"}}
    raise ValueError("Unsupported Gemini content part")


def chat_messages(request):
    messages = []
    if system := request.get("systemInstruction"):
        messages.append({"role": "system", "content": [content_part(p) for p in system["parts"]]})
    pending_calls = defaultdict(deque)
    for turn in request["contents"]:
        parts = turn["parts"]
        # agy sends tool results as model-role turns on its built-in path and
        # may also use the Gemini API's usual user-role tool result format.
        tool_turn = any("functionResponse" in part for part in parts)
        if turn["role"] == "model" and not tool_turn:
            assistant = {"role": "assistant", "content": None}
            text, calls, reasoning = [], [], []
            pending_calls.clear()
            for part in parts:
                if signature := part.get("thoughtSignature"):
                    reasoning.extend(json.loads(base64.b64decode(signature, validate=True)))
                if call := part.get("functionCall"):
                    name = call["name"]
                    call_id = call.get("id") or f"call_{len(messages)}_{len(calls)}"
                    pending_calls[name].append(call_id)
                    calls.append({"id": call_id, "type": "function",
                                  "function": {"name": name, "arguments": encode(call.get("args", {}))}})
                elif "text" in part and not part.get("thought"):
                    text.append(part["text"])
            assistant["content"] = "".join(text) or None
            if calls:
                assistant["tool_calls"] = calls
            if reasoning:
                assistant["reasoning_details"] = reasoning
            messages.append(assistant)
        elif turn["role"] == "user" or tool_turn:
            # Some agy tools include media alongside their function responses.
            # OpenRouter expects the tool messages before the user media message.
            user_parts = []
            for part in parts:
                if result := part.get("functionResponse"):
                    queue = pending_calls[result["name"]]
                    call_id = result.get("id") or (queue[0] if queue else None)
                    if call_id not in queue:
                        raise ValueError("Gemini tool result has no matching call")
                    queue.remove(call_id)
                    messages.append({"role": "tool", "tool_call_id": call_id,
                                     "content": encode(result["response"])})
                    user_parts.extend(content_part(media) for media in result.get("parts", []))
                else:
                    user_parts.append(content_part(part))
            if user_parts:
                messages.append({"role": "user", "content": user_parts})
        else:
            raise ValueError("Unsupported Gemini message role")
    return messages


def openrouter_request(request, model):
    body = {"model": model, "messages": chat_messages(request)}
    tools = []
    for group in request.get("tools", []):
        if set(group) != {"functionDeclarations"}:
            raise ValueError("Only Gemini function declarations are supported")
        for function in group["functionDeclarations"]:
            declaration = {k: function[k] for k in ("name", "description") if k in function}
            declaration["parameters"] = function.get("parametersJsonSchema", function.get("parameters", {}))
            tools.append({"type": "function", "function": declaration})
    if tools:
        body["tools"] = tools
        config = request.get("toolConfig", {}).get("functionCallingConfig", {})
        mode = config.get("mode", "AUTO")
        if allowed := config.get("allowedFunctionNames"):
            body["tools"] = [tool for tool in tools if tool["function"]["name"] in allowed]
            if not body["tools"]:
                raise ValueError("No matching tool declarations")
        body["tool_choice"] = {"AUTO": "auto", "ANY": "required", "NONE": "none"}[mode]

    config = request.get("generationConfig", {})
    for src, dst in (("maxOutputTokens", "max_tokens"), ("temperature", "temperature"),
                     ("topP", "top_p"), ("topK", "top_k"), ("stopSequences", "stop"),
                     ("seed", "seed")):
        if src in config:
            body[dst] = config[src]
    if config.get("responseMimeType") == "application/json":
        if schema := config.get("responseJsonSchema", config.get("responseSchema")):
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "response", "schema": schema}}
        else:
            body["response_format"] = {"type": "json_object"}
    if effort := config.get("thinkingConfig", {}).get("thinkingLevel"):
        body["reasoning"] = {"effort": effort.lower()}
    return body


def gemini_response(response):
    choice = response["choices"][0]
    message = choice["message"]
    parts = []
    if thought := message.get("reasoning"):
        parts.append({"text": thought, "thought": True})
    if content := message.get("content"):
        parts.append({"text": content})
    calls = []
    for tool in message.get("tool_calls") or []:
        function = tool["function"]
        args = json.loads(function["arguments"])
        if not isinstance(args, dict):
            raise ValueError("OpenRouter tool arguments must be an object")
        calls.append({"functionCall": {"name": function["name"], "args": args, "id": tool["id"]}})
    if details := message.get("reasoning_details"):
        # agy round-trips this opaque field on the matching assistant turn.
        # Preserve OpenRouter's original IDs, ordering and encrypted data.
        signed = calls[0] if calls else parts[-1] if parts else {"text": ""}
        signed["thoughtSignature"] = base64.b64encode(encode(details).encode()).decode()
        if not (calls or parts):
            parts.append(signed)
    result = {
        "candidates": [{"index": 0, "content": {"role": "model", "parts": parts + calls},
                        "finishReason": FINISH_REASONS[choice["finish_reason"]]}],
        "modelVersion": response["model"],
    }
    if usage := response.get("usage"):
        thoughts = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        result["usageMetadata"] = {
            "promptTokenCount": usage["prompt_tokens"],
            "candidatesTokenCount": max(0, usage["completion_tokens"] - thoughts),
            "thoughtsTokenCount": thoughts,
            "totalTokenCount": usage["total_tokens"],
            "cachedContentTokenCount": (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0,
        }
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def call_openrouter(body, api_key):
    request = Request(OPENROUTER_URL, data=encode(body).encode(), headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
    })
    with build_opener(NoRedirect()).open(request, timeout=600) as response:
        return json.load(response)


class GeminiHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        # agy can carry the loopback token in its URL. Do not log it or prompts.
        pass

    def reply(self, status, payload, *, stream=False):
        data = encode(payload).encode()
        if stream:
            data = b"data: " + data + b"\n\n"
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream" if stream else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, message):
        self.reply(status, {"error": {"code": status, "message": message,
                                      "status": HTTPStatus(status).name}})

    def do_POST(self):
        path = urlsplit(self.path)
        token = self.headers.get("x-goog-api-key") or parse_qs(path.query).get("key", [""])[0]
        if not secrets.compare_digest(token.encode(), self.server.loopback_key.encode()):
            self.error(401, "Invalid bridge credential")
            return
        match = re.fullmatch(r"/v1(?:beta)?/models/([^/]+):(generateContent|streamGenerateContent)", path.path)
        if not match or match[1] != self.server.model.split("/")[-1]:
            self.error(404, "Gemini endpoint or model is unavailable on this bridge")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_REQUEST_BYTES:
                raise ValueError("Invalid request length")
            body = openrouter_request(json.loads(self.rfile.read(length)), self.server.model)
        except (KeyError, TypeError, ValueError) as error:
            # Only our field names and static error messages go into agy logs.
            self.error(400, f"Unsupported Gemini request ({type(error).__name__})")
            return
        try:
            result = gemini_response(call_openrouter(body, self.server.api_key))
        except HTTPError as error:
            error.close()
            status = error.code if error.code in {400, 401, 402, 403, 404, 413, 422, 429, 503, 504} else 502
            detail = f"OpenRouter returned HTTP {error.code}"
        except (HTTPException, IndexError, KeyError, TypeError, ValueError, OSError) as error:
            status = 502
            detail = f"OpenRouter request or response failed ({type(error).__name__})"
        else:
            self.reply(200, result, stream=match[2] == "streamGenerateContent")
            return
        self.error(status, detail)


def run_agy(model, command, api_key):
    with ThreadingHTTPServer(("127.0.0.1", 0), GeminiHandler) as server:
        server.model = model
        server.api_key = api_key
        server.loopback_key = secrets.token_urlsafe(24)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        env = dict(os.environ)
        env.pop("AGENT_OPENROUTER_API_KEY", None)
        env["GEMINI_API_KEY"] = server.loopback_key
        env["GOOGLE_GEMINI_BASE_URL"] = f"http://127.0.0.1:{server.server_port}"
        bypass = env.get("no_proxy") or env.get("NO_PROXY") or ""
        env["NO_PROXY"] = env["no_proxy"] = ",".join(filter(None, (bypass, "127.0.0.1", "localhost")))
        try:
            with subprocess.Popen(command, env=env) as child:
                # Container teardown also closes in-flight HTTP connections.
                def stop(_signum, _frame):
                    child.terminate()

                previous = signal.signal(signal.SIGTERM, stop)
                try:
                    status = child.wait()
                    return status if status >= 0 else 128 - status
                finally:
                    signal.signal(signal.SIGTERM, previous)
        finally:
            server.shutdown()
            worker.join()


if __name__ == "__main__":
    if not (api_key := os.environ.get("AGENT_OPENROUTER_API_KEY")):
        sys.exit("Antigravity OpenRouter requires AGENT_OPENROUTER_API_KEY")
    sys.exit(run_agy(sys.argv[1], sys.argv[2:], api_key))
