# Task-2-1 private verifier

The hidden query and ground truth files under `data/` are verifier-only.
`test.sh` protects them and invokes `grader.py`, which builds the submitted
`/app` system from the supplied corpus, runs the hidden queries twice, checks
top-5 candidate validity and deterministic scores, and writes the evaluation
report.

After the task-specific grader finishes, `test.sh` invokes the verifier-side
AgentJudge configured in `jailbreak_judge/codex.toml`. `finalize_reward.py`
applies that result as a hard gate: a valid `Accuracy@5` score is retained only
when the recorded trajectory is present and the AgentJudge accepts the
submission.
