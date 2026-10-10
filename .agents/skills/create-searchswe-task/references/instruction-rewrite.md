# From structured specification to a realistic request

Use this process when creating or revising task instructions. The deliverables
are a structured `raw-instruction.md` and a complete prose `instruction.md` at
the task root. Harbor receives `instruction.md`.

## Preserve the source

Use `raw-instruction.md` as the structured authoring source. For a new task,
write that specification first. For an existing task, preserve its structured
source and record the Git revision or hash before editing. If the structured
source is missing, save the existing instruction byte for byte there before
organizing the specification. Keep the source organized enough to review paths,
interfaces, outputs, limits, scoring and restrictions precisely. For task
changes, update the source deliberately and regenerate the request; never
silently change a requirement during a stylistic rewrite.

Read the actual environment, resource documents and verifier before rewriting.
If the source conflicts with them, record the discrepancy and resolve the
contract explicitly. A typo correction is a semantic change to disclose, not
an opportunity to hide a new requirement in narrative. Retain the source revision
used for the rewrite so changes can be reviewed.

## Write the request

Write the request a user would give their coding agent while working on a
concrete problem. Begin with the work they need to do, the material or system
already available, and how they will use the result. The opening should make
the practical need clear, such as finding a passage to check its original
context, choosing which retrieved documents to read, or reducing the wait for
a complete search workload.

Keep this sense of use throughout the request. Connect the current data and
starting system, available resources, restrictions, deliverables and acceptance
criteria to the work as it progresses. Explain what counts as better using
the source's metric, baseline, quality gates and resource tradeoffs. Technical
interfaces and scoring details must remain exact, and the whole request should
read as one coherent commission. Adding a contextual opening alone is not
enough if the rest reads as a disconnected specification.

Use ordinary first-person task language when it fits, without a named requester
or a self-introduction such as "I'm Alex". For example, a PDF-localization task
could begin: "I need to look up passages in a long PDF repeatedly. Often I have
a description of the material I want to find and need to locate the original
pages so I can check the surrounding text." Choose context appropriate to each
task; there is no fixed opening template. A plain task description with "I need"
prepended is not sufficient to establish the work situation.

Ground the context in the actual task and resources. Do not invent identities,
organizations, biographies or decorative scenes. Do not claim an unsupported
dataset provenance, production deployment, measured defect or usage history.
Practical motivation must not add functionality or acceptance criteria: a
desire to check original pages, for example, does not require a PDF viewer or
a graphical interface unless the source specifies one. Include enough detail
to preserve the whole contract without padding it with a backstory.

Use no headings, enumerated requirements, bullet lists, tables, directory
trees or fenced code blocks in the final instruction. Exact commands, paths,
field names and JSON examples can appear inline within sentences. Turning
each old bullet into an isolated sentence does not complete the rewrite.
Connect requirements where they belong in the workflow so the request reads
naturally and remains unambiguous. Avoid deliberate obscurity, repetitive
reminders and decorative opening or closing paragraphs.

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

Do not add new deadlines, hardware, output fields, evaluation claims or solution
hints, or manufacture task requirements to make the request sound realistic.
Do not drop repeated conditions unless their full meaning survives elsewhere.
Keep the original language unless the requested rewrite includes translation.
Do not refer the agent to `raw-instruction.md` or copy it into the agent image
or mounts; doing so exposes an alternate structured prompt.

## Review before evaluation

Make a small author-only correspondence record: source condition or line range,
the request paragraph containing it, and any discrepancy. Review both ways:
every raw condition must appear in the prose, and every prose obligation must
come from the source or an explicitly resolved contract correction. Read the
whole request for natural flow after this check. Confirm that a concrete work
need and the intended use of the results are apparent, and remain connected
to the data, resources, constraints and measurable outcome through the body.
Check that there is no self-introduction, invented identity or extra obligation
introduced by the context. Removing a persona must not erase the work situation.

Literal comparisons of paths, flags, IDs and numbers catch omissions but cannot
prove semantic equivalence. Inspect negations, exceptions, time accounting,
cardinality and failure scope manually. Check the agent Docker context and
mounts to confirm the structured source and review notes are not exposed.

Then evaluate the final prose version using [model-evaluation.md](model-evaluation.md).
If the trajectory reveals ambiguity or a lost condition, repair the source or
rewrite as appropriate and identify which evaluated revision became obsolete.
Do not weaken the task or tune the prompt solely to obtain a desired score.
