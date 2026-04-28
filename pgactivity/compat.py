"""Compatibility utilities module."""
from __future__ import annotations

from typing import Any

import attr
from blessed import Terminal


def gt(bound: int) -> Any:
    """Validator for values greater than bound.

    This is a compatibility wrapper for attr.validators.gt.

    >>> @attr.s
    ... class Test:
    ...     value: int = attr.ib(validator=gt(0))
    >>> Test(5)
    Test(value=5)
    >>> Test(0)  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    ValueError: ...
    """
    try:
        # Try to use attrs' built-in gt validator (attrs >= 21.3.0)
        return attr.validators.gt(bound)
    except AttributeError:
        # Fallback for older attrs versions
        @attr.validators.instance_of(int)
        def _gt(instance: Any, attrib: attr.Attribute, value: int) -> None:
            if value <= bound:
                raise ValueError(
                    f"'{attrib.name}' must be greater than {bound}, got {value}"
                )

        return _gt


def link(term: Terminal, url: str, text: str) -> str:
    """Create a clickable terminal hyperlink.

    >>> from blessed import Terminal
    >>> term = Terminal(force_styling=None)
    >>> link(term, "https://example.com", "Example")
    'Example'
    """
    # Use OSC 8 escape sequence for clickable links if terminal supports it
    # Format: ESC ] 8 ; ; URL ST text ESC ] 8 ; ; ST
    # Where ST is either BEL (\\a) or ESC \\
    try:
        if term.does_styling:
            return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\"
    except (AttributeError, TypeError):
        pass
    return text


def fields_dict(cls: type) -> dict[str, attr.Attribute]:
    """Return a dictionary of attr fields for a class.

    >>> import attr
    >>> @attr.s
    ... class Person:
    ...     name: str = attr.ib()
    ...     age: int = attr.ib()
    >>> sorted(fields_dict(Person).keys())
    ['age', 'name']
    """
    return {f.name: f for f in attr.fields(cls)}
