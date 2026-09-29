"""Credential-isolated access to Jina text embedding and reranking only."""
import requests
from llm_gateway import Gateway


class JinaGateway(Gateway):
    credential_name = "JINA_API_KEY"
    require_key = False  # Local-only submissions do not need this optional service.
    env_prefix = "TASK_JINA"
    service_name = "Jina retrieval"

    @staticmethod
    def validate(payload):
        if not isinstance(payload, dict) or set(payload) != {"operation", "body"}:
            raise ValueError("expected operation and body")
        operation, body = payload["operation"], payload["body"]
        if operation not in ("embeddings", "rerank") or not isinstance(body, dict):
            raise ValueError("only Jina embeddings and rerank are allowed")
        model = body.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("select a Jina model for the requested operation")
        texts = body.get("input") if operation == "embeddings" else body.get("documents")
        if isinstance(texts, str) and operation == "embeddings":
            texts = [texts]
        if not isinstance(texts, list) or not texts:
            raise ValueError("provide a nonempty list of texts")
        for text in texts:
            if isinstance(text, dict) and set(text) == {"text"}:
                text = text["text"]
            if not isinstance(text, str):
                raise ValueError("only text inputs are supported")
        if operation == "rerank" and not isinstance(body.get("query"), str):
            raise ValueError("rerank requires a text query")
        return payload

    def forward(self, payload):
        if not self.key:
            raise self.Error("JINA_API_KEY is required to use Jina")
        try:
            response = requests.post(
                "https://api.jina.ai/v1/" + payload["operation"],
                headers={"Authorization": "Bearer " + self.key},
                json=payload["body"], timeout=(10, 45), allow_redirects=False,
            )
            if response.status_code in (400, 413, 422):
                raise ValueError(f"Invalid Jina request: HTTP {response.status_code}")
            if response.status_code != 200:
                raise self.Error(f"Jina upstream HTTP {response.status_code}")
            try:
                return response.json()
            except ValueError:
                raise self.Error("Jina upstream invalid JSON") from None
        except requests.RequestException:
            raise self.Error("Jina upstream transport failure") from None
