FROM search-swe-base:gpu-cu13.0-py3.12-1.0.0-codex-npm-0.152.0

# The judge uses the Codex CLI endpoint, not LiteLLM's remote pricing map.
# Keep verifier startup/build deterministic and avoid an unrelated GitHub fetch.
ENV LITELLM_LOCAL_MODEL_COST_MAP=true

RUN /opt/conda/bin/python -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --timeout 120 --retries 10 --resume-retries 10 \
    "harbor-rewardkit==0.1.7" \
    && test -x /opt/conda/bin/rewardkit

RUN useradd --create-home --uid 10001 --shell /bin/bash submission

COPY --chmod=755 test.sh run_evaluation.sh finalize_reward.py /tests/
COPY --chmod=644 grader.py /tests/grader.py
COPY --chmod=555 starter/ /tests/starter/
COPY --chmod=600 data/queries.jsonl data/ground_truth.jsonl /tests/data/
COPY jailbreak_judge/ /tests/jailbreak_judge/

RUN mkdir -p /task/data /task/models \
    && chmod 700 /tests /tests/data \
    && chmod 555 /task /task/data /task/models
