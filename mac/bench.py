"""HumanEval tasks (OpenAI, MIT licence): prompts, visible docstring examples and hidden tests.

Agents only ever see ``prompt`` and the examples already written inside it. The hidden
``test`` function is used exclusively by the final scorer.
"""

from __future__ import annotations

import doctest
import gzip
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA = Path("data/HumanEval.jsonl.gz")
SHA256 = "b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef"


@dataclass
class Task:
    task_id: str
    prompt: str
    entry_point: str
    test: str

    @property
    def prefix(self) -> str:
        """Imports and helper functions that precede the function to implement."""
        idx = self.prompt.find(f"def {self.entry_point}(")
        return self.prompt[:idx] if idx > 0 else ""

    def visible_examples(self) -> list[doctest.Example]:
        return doctest.DocTestParser().get_examples(self.prompt)


def load(limit: int | None = None) -> list[Task]:
    blob = DATA.read_bytes()
    if hashlib.sha256(blob).hexdigest() != SHA256:
        raise ValueError("HumanEval file does not match the pinned checksum")
    rows = [json.loads(line) for line in gzip.decompress(blob).decode().splitlines() if line.strip()]
    tasks = [Task(r["task_id"], r["prompt"], r["entry_point"], r["test"]) for r in rows]
    return tasks[:limit] if limit else tasks


def extract_code(text: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    code = max(blocks, key=len) if blocks else text
    return code.strip() + "\n"


def program(task: Task, code: str) -> str:
    return task.prefix + "\n" + code


def doctest_program(task: Task, code: str) -> str | None:
    """Program that runs only the examples visible in the prompt's docstring."""
    examples = task.visible_examples()
    if not examples:
        return None
    def clean(want: str) -> str:
        # the final example's expected output can swallow the docstring's closing quotes
        return "\n".join(l for l in want.splitlines() if l.strip() not in ('"""', "'''")).strip()

    cases = [(e.source.strip(), clean(e.want)) for e in examples]
    return program(task, code) + f"""

import ast as _ast
_failures = []
for _src, _want in {cases!r}:
    try:
        try:
            _got = eval(compile(_src, "<example>", "eval"), globals())
        except SyntaxError:
            exec(compile(_src, "<example>", "exec"), globals())
            _got = None
    except Exception as _e:
        _failures.append(f"{{_src}}\\n  raised {{type(_e).__name__}}: {{_e}}")
        continue
    if not _want:
        _ok = _got is None or _got is True  # e.g. ">>> f(x) == 3" written without an expected line
    else:
        try:
            _ok = _got == _ast.literal_eval(_want)
        except (ValueError, SyntaxError):
            _ok = " ".join(repr(_got).split()) == " ".join(_want.split()) or str(_got) == _want
    if not _ok:
        _failures.append(f"{{_src}}\\n  expected {{_want or 'True'}}\\n  got {{_got!r}}")
if _failures:
    print("\\n".join(_failures))
    raise SystemExit(1)
print("visible examples passed")
"""


def hidden_test_program(task: Task, code: str) -> str:
    # Keep checker helpers in a separate namespace. Candidate code may define a
    # helper with the same name without changing the independent expected result.
    return (f"_candidate_ns = {{}}\nexec(compile({program(task,code)!r}, '<candidate>', 'exec'), _candidate_ns)\n"
            f"_checker_ns = {{}}\nexec(compile({(task.prefix + chr(10) + task.test)!r}, '<checker>', 'exec'), _checker_ns)\n"
            f"_checker_ns['check'](_candidate_ns[{task.entry_point!r}])\n")
