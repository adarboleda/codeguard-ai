"""Two small runs with known numbers, shared by the comparison tests.

Templates: 6 proposals (2 defective seeds), 4 valid, 100 % coverage, mutants 3/3 detected.
Groq:      5 proposals, 3 valid (WRONG_EXPECTATION + GENERATION_ERROR), mutants 2/3 detected.
"""

from pathlib import Path

from run_factory import LlmCall, make_run

from codeguard.domain import ProposalSourceKind, RejectionReason

TEMPLATE = ProposalSourceKind.TEMPLATE
SEED = ProposalSourceKind.DEFECTIVE_SEED
GROQ = ProposalSourceKind.GROQ

MUTANTS_TEMPLATES = {
    "M01": ("weighted_mean", "KILLED"),
    "M02": ("weighted_mean", "KILLED"),
    "M03": ("clamp", "EQUIVALENT"),
    "M04": ("clamp", "KILLED"),
}
MUTANTS_GROQ = {**MUTANTS_TEMPLATES, "M02": ("weighted_mean", "SURVIVED")}


def templates_run(out: Path, run_id: str = "tpl") -> Path:
    return make_run(
        out,
        run_id,
        proposals=[
            ("wm-1", TEMPLATE, "weighted_mean", None),
            ("wm-2", TEMPLATE, "weighted_mean", None),
            ("cl-1", TEMPLATE, "clamp", None),
            ("cl-2", TEMPLATE, "clamp", None),
            ("seed-syntax", SEED, "weighted_mean", RejectionReason.SYNTAX_ERROR),
            ("seed-taut", SEED, "clamp", RejectionReason.TAUTOLOGICAL_ASSERTION),
        ],
        passed=4,
        coverage=(54, 54, 30, 30),
        mutants=MUTANTS_TEMPLATES,
        seed=42,
    )


def groq_run(out: Path, run_id: str = "gq", *, replayed_from: str | None = None) -> Path:
    return make_run(
        out,
        run_id,
        proposals=[
            ("groq-wm-01", GROQ, "weighted_mean", None),
            ("groq-wm-02", GROQ, "weighted_mean", None),
            ("groq-wm-03", GROQ, "weighted_mean", RejectionReason.WRONG_EXPECTATION),
            ("groq-cl-01", GROQ, "clamp", None),
            ("groq-cl-error", GROQ, "clamp", RejectionReason.GENERATION_ERROR),
        ],
        passed=3,
        coverage=(53, 54, 29, 30),
        mutants=MUTANTS_GROQ,
        llm_calls=[
            LlmCall("weighted_mean", tokens=1000, replayed_from=replayed_from),
            LlmCall("clamp", failed=True, replayed_from=replayed_from),
        ],
    )
