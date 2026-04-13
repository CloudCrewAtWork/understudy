set shell := ["bash", "-cu"]

default:
    @just --list

install:
    uv sync --all-extras
    uv run playwright install chromium

lint:
    uv run ruff check .
    uv run ruff format --check .

fmt:
    uv run ruff check --fix .
    uv run ruff format .

types:
    uv run basedpyright

test:
    uv run pytest -q

audit:
    uv run pip-audit
    uv run bandit -r understudy

eval:
    uv run python evals/run_eval.py

record url task:
    uv run understudy record --url "{{url}}" --task "{{task}}"

induce trajectory:
    uv run understudy induce "{{trajectory}}"

ci: lint types test audit
