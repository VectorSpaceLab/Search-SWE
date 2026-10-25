# Task long-document-reranking private verifier

The hidden query and ground truth files under `data/` are verifier-only.
`test.sh` protects them and invokes `grader.py`, which builds the submitted
`/app` system from the supplied corpus, runs the hidden queries twice, checks
top-5 candidate validity and deterministic scores, and writes the evaluation
report.

The outer verifier window is 13,200 seconds: 1,800 seconds for the build,
two query runs of 3,600 seconds each, 3,600 seconds for the trajectory judge,
and a 600-second setup/cleanup allowance. The build and query limits are
enforced independently by `grader.py`; the judge timeout is configured in
`jailbreak_judge/codex.toml`.

After the task-specific grader finishes, `test.sh` invokes the verifier-side
AgentJudge configured in `jailbreak_judge/codex.toml`. `finalize_reward.py`
applies that result as a hard gate: a valid `Accuracy@5` score is retained only
when the recorded trajectory is present and the AgentJudge accepts the
submission.
