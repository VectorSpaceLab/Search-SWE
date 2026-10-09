# From structured specification to a realistic request

Use this process when creating or revising task instructions. The deliverables
are a structured `raw-instruction.md` and a complete prose `instruction.md` at
the task root. Harbor receives `instruction.md`.

## Preserve the source

For an existing task, first copy the original instruction byte for byte to
`raw-instruction.md`; record its Git revision or hash. For a new task, write the
structured specification there first. Keep the source organized enough to
review paths, interfaces, outputs, limits, scoring and restrictions precisely.
For later task changes, update the source deliberately and regenerate the
scenario; never silently change a requirement during a stylistic rewrite.

Read the actual environment, resource documents and verifier before rewriting.
If the source conflicts with them, record the discrepancy and resolve the
contract explicitly. A typo correction is a semantic change to disclose, not
an opportunity to hide a new requirement in narrative. Keep an original source
snapshot when migrating existing tasks.

## Write the request

Give the requester a name, a plausible role, a concrete physical workplace and
a reason to need this system. Write as that person explaining the problem to
their coding agent: a long, coherent natural-language request with connected
paragraphs, practical context and requirements woven into the story. The
setting should suit the supplied data; do not invent its provenance or claim
that a benchmark corpus contains a different kind of material.

Use no headings, enumerated requirements, bullet lists, tables, directory
trees or fenced code blocks in the final instruction. Exact commands, paths,
field names and JSON examples can appear inline within sentences. Turning
each old bullet into a paragraph or adding a story before the old checklist
does not complete the rewrite. The prose should require the agent to extract
and connect requirements across the request, while remaining unambiguous.

Preserve every source condition, including optional permissions and exceptions:

- The objective, supplied starting system, permitted changes and fixed parts.
- Exact input and artifact paths, flags, formats, field names and types;
  executable permissions, invocation order, service lifecycle and transfer.
- Cardinality, uniqueness, query coverage/order, ranking, tie-breaks and
  finite-value rules; retain exact examples when they define an interface.
- Numeric thresholds, units, inclusive/exclusive boundaries, timeouts,
  concurrency, shared versus individual budgets and queue-time treatment.
- Read/write permissions, CPU/GPU/network constraints, external resource
  allowlists, credential handling and disallowed shortcuts.
- Every visible validation file and referenced resource document, the hidden
  split boundary, metric/formula, failure behavior and scope of zero scores.

Narrative details are motivation, never extra acceptance criteria. Do not add
new deadlines, hardware, output fields, evaluation claims or solution hints.
Do not drop repeated conditions unless their full meaning survives elsewhere.
Keep the original language unless the requested rewrite includes translation.
Do not refer the agent to `raw-instruction.md` or copy it into the agent image
or mounts; doing so exposes an alternate structured prompt.

## Review before evaluation

Make a small author-only correspondence record: source condition or line range,
the scenario paragraph containing it, and any discrepancy. Review both ways:
every raw condition must appear in the prose, and every prose obligation must
come from the source or an explicitly resolved contract correction. Read the
whole request for natural flow after this check.

Literal comparisons of paths, flags, IDs and numbers catch omissions but cannot
prove semantic equivalence. Inspect negations, exceptions, time accounting,
cardinality and failure scope manually. Check the agent Docker context and
mounts to confirm the structured source and review notes are not exposed.

Then evaluate the final prose version using [model-evaluation.md](model-evaluation.md).
If the trajectory reveals ambiguity or a lost condition, repair the source or
rewrite as appropriate and identify which evaluated revision became obsolete.
Do not weaken the task or tune the prompt solely to obtain a desired score.
