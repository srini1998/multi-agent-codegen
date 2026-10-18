import sys
from pathlib import Path

import pytest

from mac import bench, sandbox

TASKS = {t.task_id: t for t in bench.load()}


def test_humaneval_is_pinned_and_complete():
    assert len(TASKS) == 164


def test_canonical_style_solution_passes_hidden_tests_and_wrong_one_fails():
    task = TASKS["HumanEval/0"]  # has_close_elements
    good = (
        "def has_close_elements(numbers, threshold):\n"
        "    return any(abs(a - b) < threshold for i, a in enumerate(numbers) for b in numbers[i + 1:])\n"
    )
    bad = "def has_close_elements(numbers, threshold):\n    return False\n"
    assert sandbox.run_python(bench.hidden_test_program(task, good)).ok
    assert not sandbox.run_python(bench.hidden_test_program(task, bad)).ok


def test_visible_examples_come_from_the_prompt_only():
    task = TASKS["HumanEval/0"]
    assert task.visible_examples(), "HumanEval/0 has >>> examples in its docstring"
    wrong = "def has_close_elements(numbers, threshold):\n    return True\n"
    r = sandbox.run_python(bench.doctest_program(task, wrong))
    assert not r.ok and "expected" in r.output
    assert "check(" not in bench.doctest_program(task, wrong)  # hidden tests never leak into feedback


def test_helper_functions_in_the_prompt_are_kept():
    task = TASKS["HumanEval/38"]  # decode_cyclic relies on encode_cyclic defined in the prompt
    assert "def encode_cyclic" in task.prefix
    code = (
        "def decode_cyclic(s):\n"
        "    return encode_cyclic(encode_cyclic(s))\n"
    )
    assert sandbox.run_python(bench.hidden_test_program(task, code)).ok


def test_extract_code_takes_the_fenced_block():
    text = "Here you go:\n```python\ndef f():\n    return 1\n```\nHope it helps"
    assert bench.extract_code(text) == "def f():\n    return 1\n"


def test_sandbox_enforces_timeout():
    r = sandbox.run_python("while True:\n    pass\n", timeout=2)
    assert not r.ok and (r.timed_out or "CPU" in r.output or r.output == "")


def test_container_blocks_network_and_outside_writes(tmp_path):
    target = Path.home() / "mac-sandbox-should-not-exist.txt"
    r = sandbox.run_python(f"open({str(target)!r}, 'w').write('x')\n")
    assert not r.ok and not target.exists()
    r = sandbox.run_python(
        "import socket\ns = socket.create_connection(('1.1.1.1', 80), timeout=3)\n"
    )
    assert not r.ok
    assert sandbox.run_python("open('inside.txt', 'w').write('ok')\nprint(open('inside.txt').read())\n").ok


def test_visible_examples_accept_a_correct_solution():
    """Regression: the last docstring example used to include the closing quotes in its expected output."""
    task = TASKS["HumanEval/0"]
    good = (
        "def has_close_elements(numbers, threshold):\n"
        "    return any(abs(a - b) < threshold for i, a in enumerate(numbers) for b in numbers[i + 1:])\n"
    )
    assert sandbox.run_python(bench.doctest_program(task, good)).ok


def test_generated_code_cannot_read_an_outside_host_canary(tmp_path):
    canary=tmp_path/"host-canary.txt";canary.write_text("AUTHORED_NON_SECRET_CANARY")
    r=sandbox.run_python(f"print(open({str(canary)!r}).read())")
    assert not r.ok and "AUTHORED_NON_SECRET_CANARY" not in r.output

def test_stdout_is_bounded_before_collecting_it_all():
    r=sandbox.run_python("print('x'*200000)")
    assert not r.ok and r.category=="output_limit"
    assert len(r.output)<4000

def test_missing_container_runtime_never_falls_back_to_host(monkeypatch,tmp_path):
    target=tmp_path/"must-not-exist.txt"
    monkeypatch.setattr(sandbox,"_docker",lambda:None)
    r=sandbox.run_python(f"open({str(target)!r},'w').write('x')")
    assert r.category=="infrastructure" and not target.exists()


def test_candidate_cannot_replace_the_checker_helper():
    task=TASKS["HumanEval/32"]
    bad="def poly(xs,x):\n    return 0\ndef find_zero(xs):\n    return 0\n"
    assert not sandbox.run_python(bench.hidden_test_program(task,bad)).ok
