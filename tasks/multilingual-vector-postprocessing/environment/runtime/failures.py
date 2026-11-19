"""Distinguish submission violations from unverifiable measurements."""


class ContractViolation(RuntimeError):
    """A verifier input or invariant did not satisfy its contract."""


class SubmissionViolation(ContractViolation):
    """The submission violated a rule that awards a measured zero."""


# Older collectors recorded these fixed rejection reasons without a failure kind.
LEGACY_COLLECTION_REJECTIONS = frozenset({
    "Submission root must be a real directory",
    "Linked or non-directory submission entry",
    "Linked or non-regular submission entry",
    "Missing transform.py",
    "Submission exceeds the total storage limit",
    "100 GiB total task storage exceeded",
})
