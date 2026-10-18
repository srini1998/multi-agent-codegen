"""Planner, Coder and Reviewer roles, and the three strategies compared in the benchmark.

single         one Coder call
exec-feedback  Coder, then revise (up to N times) when the prompt's visible examples fail
full           Planner -> Coder -> Reviewer (visible examples + LLM review) -> revise up to N times
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import httpx

from . import bench, llm, sandbox

PLANNER_SYSTEM = (
    "You are a senior Python engineer. Read the function specification and plan the implementation "
    "before anyone writes code. List concrete implementation steps and the edge cases the code must "
    "handle (empty inputs, negatives, ties, ordering, types). At most 6 steps and 6 edge cases, one short "
    "sentence each. Do not write code."
)
PLAN_SCHEMA = {
    "type": "object",
    "properties": {"steps": {"type": "array", "items": {"type": "string"}},
                   "edge_cases": {"type": "array", "items": {"type": "string"}}},
    "required": ["steps", "edge_cases"],
}
CODER_SYSTEM = (
    "You are an expert Python programmer. Implement the requested function completely and correctly. "
    "Return one ```python code block containing the full function definition (with any imports or "
    "helpers it needs) and nothing else. Do not include tests or example usage."
)
REVIEWER_SYSTEM = (
    "You are a meticulous code reviewer. Check the implementation against the specification and the "
    "listed edge cases. Approve only if you find no bug. If you reject, list each concrete bug and the "
    "input that triggers it. At most 5 issues, one sentence each."
)
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"issues": {"type": "array", "items": {"type": "string"}}, "approve": {"type": "boolean"}},
    "required": ["issues", "approve"],
}


@dataclass
class Attempt:
    code: str
    visible_ok: bool | None
    visible_output: str = ""
    review: dict | None = None


@dataclass
class Outcome:
    task_id: str
    strategy: str
    final_code: str
    approved: bool | None
    plan: dict | None = None
    attempts: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)


def _visible(task: bench.Task, code: str) -> tuple[bool | None, str]:
    prog = bench.doctest_program(task, code)
    if prog is None:
        return None, "no visible examples in the prompt"
    r = sandbox.run_python(prog)
    if r.category == "infrastructure":
        raise RuntimeError("Code execution infrastructure unavailable; candidate was not scored")
    return r.ok, r.output


def _coder_prompt(task: bench.Task, plan: dict | None, previous: Attempt | None) -> str:
    parts = [f"Specification:\n```python\n{task.prompt}\n```"]
    if plan:
        parts.append("Plan:\n" + "\n".join(f"- {s}" for s in plan["steps"]) +
                     "\nEdge cases:\n" + "\n".join(f"- {s}" for s in plan["edge_cases"]))
    if previous:
        parts.append(f"Your previous implementation:\n```python\n{previous.code}```")
        if previous.visible_ok is False:
            parts.append(f"It failed the examples from the docstring:\n{previous.visible_output}")
        if previous.review and not previous.review["approve"]:
            parts.append("Reviewer found these problems:\n" + "\n".join(f"- {i}" for i in previous.review["issues"]))
        parts.append("Fix every problem and return the corrected full function.")
    return "\n\n".join(parts)


def solve(task: bench.Task, strategy: str, model: str, max_revisions: int = 2) -> Outcome:
    usage = llm.Usage()
    plan = None
    if strategy == "full":
        try:
            plan = json.loads(llm.chat(model, "planner", PLANNER_SYSTEM, f"```python\n{task.prompt}\n```", usage,
                                       schema=PLAN_SCHEMA, max_tokens=900))
        except (json.JSONDecodeError, httpx.HTTPError):
            plan = {"steps": [], "edge_cases": [], "malformed": True}  # recorded, and the coder proceeds without a plan
    attempts: list[Attempt] = []
    previous = None
    approved = None
    for round_ in range(1 + (0 if strategy == "single" else max_revisions)):
        code = bench.extract_code(llm.chat(model, "coder", CODER_SYSTEM, _coder_prompt(task, plan, previous), usage))
        attempt = Attempt(code, None)
        if strategy == "single":
            attempts.append(attempt)
            break
        attempt.visible_ok, attempt.visible_output = _visible(task, code)
        if strategy == "full":
            review_input = (f"Specification:\n```python\n{task.prompt}\n```\n\nEdge cases to check:\n" +
                            "\n".join(f"- {e}" for e in plan["edge_cases"]) +
                            f"\n\nImplementation:\n```python\n{code}```\n\nDocstring examples: " +
                            ("passed" if attempt.visible_ok else "none" if attempt.visible_ok is None
                             else "FAILED\n" + attempt.visible_output))
            try:
                attempt.review = json.loads(llm.chat(model, "reviewer", REVIEWER_SYSTEM, review_input, usage,
                                                     schema=REVIEW_SCHEMA, max_tokens=700))
            except (json.JSONDecodeError, httpx.HTTPError):
                attempt.review = {"approve": False, "issues": ["reviewer output was malformed"], "malformed": True}
            approved = attempt.visible_ok is not False and attempt.review["approve"]
        else:
            approved = attempt.visible_ok is not False
        attempts.append(attempt)
        if approved:
            break
        previous = attempt
    return Outcome(task.task_id, strategy, attempts[-1].code, approved, plan,
                   [asdict(a) for a in attempts], asdict(usage))


def score(task: bench.Task, code: str) -> dict:
    r = sandbox.run_python(bench.hidden_test_program(task, code))
    if r.category == "infrastructure":
        raise RuntimeError("Code execution infrastructure unavailable; candidate was not scored")
    return {"passed": r.ok, "timed_out": r.timed_out, "category": r.category, "profile": r.profile, "image": r.image, "harness_version": "separate-oracle-v2", "error": None if r.ok else r.output[-400:]}
