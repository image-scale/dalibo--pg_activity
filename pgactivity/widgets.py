"""UI widgets module."""
from __future__ import annotations

from blessed import Terminal


def boxed(
    term: Terminal,
    text: str,
    *,
    border: bool = True,
    center: bool = False,
) -> str:
    """Create a box around text.

    >>> from blessed import Terminal
    >>> term = Terminal(force_styling=None)
    >>> print(boxed(term, "hello, world"), end="")
    ┌──────────────┐
    │ hello, world │
    └──────────────┘
    >>> print(boxed(term, "hello, world", border=False), end="")
    <BLANKLINE>
    hello, world
    >>> print(boxed(term, "hello, world", center=True), end="")  # doctest: +NORMALIZE_WHITESPACE
    ...
    """
    if not border:
        return f"\n{text}\n"

    # Box drawing characters
    tl, tr, bl, br = "┌", "┐", "└", "┘"
    h, v = "─", "│"

    width = len(text) + 2  # padding on each side
    top = f"{tl}{h * width}{tr}"
    middle = f"{v} {text} {v}"
    bottom = f"{bl}{h * width}{br}"

    result = f"{top}\n{middle}\n{bottom}\n"

    if center:
        # Center each line
        lines = result.split("\n")
        centered_lines = []
        for line in lines:
            if line:
                centered_lines.append(term.center(line))
            else:
                centered_lines.append(line)
        result = "\n".join(centered_lines)

    return result
