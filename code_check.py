"""
code_check.py  -  look over a student's program before it is saved or run.

    problems = check(source)      # [] means OK

Reads the code without running it and refuses anything a turtle drawing
does not need: other modules, files, eval/exec, and the back doors into
Python and Tk.  This stops accidents and casual mischief; it is not a
sandbox.  On the Pi, student programs also run as a user who can't touch
the plotter or the project files, with a time limit.
"""

import ast

ALLOWED_MODULES = ("turtle", "math", "random", "time", "colorsys")

# Built-ins that reach files, other code, or anything by name.
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "getattr",
                "setattr", "delattr", "globals", "locals", "vars",
                "breakpoint", "getcanvas"}

# Attributes that lead out of turtle into Tk (and from there anywhere).
BANNED_ATTRS = {"getcanvas", "cv", "tk", "TK", "sys", "os", "modules",
                "inspect", "types", "system"}

ALLOWED_DUNDERS = {"__name__"}


def _import_problem(line, name):
    return ("Line %d: plotter programs can only import %s (not %s)."
            % (line, ", ".join(ALLOWED_MODULES), name))


def _not_allowed(line, what):
    return "Line %d: %s is not allowed in plotter programs." % (line, what)


def _underscore(line, name):
    return ("Line %d: names starting with an underscore (%s) are not "
            "allowed in plotter programs." % (line, name))


def _problems(node):
    line = getattr(node, "lineno", 0)
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.split(".")[0] not in ALLOWED_MODULES:
                yield _import_problem(line, alias.name)
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if node.level or module.split(".")[0] not in ALLOWED_MODULES:
            yield _import_problem(line, "." * node.level + module)
        for alias in node.names:
            if alias.name in BANNED_NAMES or alias.name in BANNED_ATTRS:
                yield _not_allowed(line, alias.name)
            elif alias.name.startswith("_"):
                yield _underscore(line, alias.name)
    elif isinstance(node, ast.Name):
        if node.id in BANNED_NAMES:
            yield _not_allowed(line, node.id)
        elif node.id.startswith("__") and node.id not in ALLOWED_DUNDERS:
            yield _underscore(line, node.id)
    elif isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            yield _underscore(line, node.attr)
        elif node.attr in BANNED_ATTRS:
            yield _not_allowed(line, "." + node.attr)


def check(source):
    """Problems with a student's program, as plain sentences.  [] = OK."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ["Line %d: Python can't read this line (%s)."
                % (e.lineno or 0, e.msg)]
    found = set()
    for node in ast.walk(tree):
        for text in _problems(node):
            found.add((getattr(node, "lineno", 0), text))
    return [text for _, text in sorted(found)]
