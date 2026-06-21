# Project Overview

## Purpose

This project builds a basic AI-assisted application pipeline with a clear repository structure, testable Python environment, and OpenSpec-driven development workflow.

The initial goal is to establish a minimal but extensible Python project scaffold so that future features can be implemented safely and incrementally.

## Development Principles

- Follow OpenSpec before implementing features.
- Keep implementation small and verifiable.
- Prefer simple Python modules before introducing complex architecture.
- Every phase must define clear tasks and done criteria.
- Every feature should be testable through `pytest`.

## Repository Conventions

Expected base structure:

```txt
.
├── AGENTS.md
├── README.md
├── requirements.txt
├── src/
│   └── __init__.py
├── data/
├── outputs/
├── tests/
└── openspec/