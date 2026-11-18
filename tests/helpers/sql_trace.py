# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Helpers for recording SQL statements issued through an engine."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from sqlalchemy import Engine, event


@dataclass
class SelectTrace:
    """SELECT statements captured while the context manager is active.

    Attributes:
        statements: Raw SQL text of every SELECT, in execution order.
    """

    statements: list[str] = field(default_factory=list)


@contextmanager
def count_selects(engine: Engine) -> Iterator[SelectTrace]:
    """Record SELECT statements executed on ``engine``.

    Args:
        engine: SQLAlchemy engine to listen on.

    Yields:
        Trace collecting the statements issued inside the block.
    """
    trace = SelectTrace()

    def record(conn, cursor, statement, parameters, context, executemany):
        del conn, cursor, parameters, context, executemany
        if statement.lstrip().upper().startswith("SELECT"):
            trace.statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield trace
    finally:
        event.remove(engine, "before_cursor_execute", record)
