"""
Static check for the website's JS modules: no module may CALL a function that
another module exports unless it imports (or defines) that name itself.

This catches "ReferenceError: x is not defined" bugs that `node --check` and
loading the module cannot see, because they only blow up when the call runs.

Run:  python -m unittest discover -s web/tests -v      (from the project folder)
"""
import re
import unittest

from harness import WEB

JS_DIR = WEB / "static"   # app.js and everything in js/

# One pass over the source: comments and strings are matched together so that
# a "//" inside a string (like "http://") is not mistaken for a comment.
COMMENT_OR_STRING = re.compile(
    r"""
      //[^\n]*                  # line comment
    | /\*.*?\*/                 # block comment
    | "(?:\\.|[^"\\\n])*"       # double-quoted string
    | '(?:\\.|[^'\\\n])*'       # single-quoted string
    | `(?:\\.|[^`\\])*`         # template literal
    """,
    re.VERBOSE | re.DOTALL,
)

EXPORT_DECL = re.compile(r"export\s+(?:async\s+)?(?:function\*?|const|let|class)\s+([A-Za-z_$][\w$]*)")
EXPORT_LIST = re.compile(r"export\s*\{([^}]*)\}")
IMPORT = re.compile(r"import\s*\{([^}]*)\}\s*from")
IMPORT_OTHER = re.compile(r"import\s+(?:\*\s+as\s+)?([A-Za-z_$][\w$]*)")
DEFINED = re.compile(r"\b(?:function\*?|const|let|var|class)\s+([A-Za-z_$][\w$]*)")
# Parameters: function f(a, b) / (a, b) => / a =>  (approximate, good enough here)
PARAM_LISTS = re.compile(r"\(([^()]*)\)\s*(?:=>|\{)|\b([A-Za-z_$][\w$]*)\s*=>")
DESTRUCTURED = re.compile(r"\b(?:const|let|var)\s*[\[{]([^\]}]*)[\]}]")
IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")


TEMPLATE_CODE = re.compile(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")   # the code inside ${...}


def blank(match):
    """Replace a comment or string with an empty string literal / a space.
    Template literals keep the code inside their ${...}, because calls hide there too."""
    text = match.group(0)
    if text[0] == "`":
        return '"" ' + " ; ".join(TEMPLATE_CODE.findall(text))
    return '""' if text[0] in "\"'" else " "


def strip_comments_and_strings(source):
    return COMMENT_OR_STRING.sub(blank, source)


def strip_comments_only(source):
    # Keep strings (import paths live there), drop comments.
    def keep_strings(match):
        text = match.group(0)
        return text if text[0] in "\"'`" else " "
    return COMMENT_OR_STRING.sub(keep_strings, source)


def names_in_list(text):
    """'a, b as c' -> names a and c (the local names)."""
    names = set()
    for part in text.split(","):
        words = part.split()
        if words:
            names.add(words[-1])
    return names


def exported_names(source):
    names = set(EXPORT_DECL.findall(source))
    for body in EXPORT_LIST.findall(source):
        names |= {part.split()[0] for part in body.split(",") if part.split()}
    return names


def imported_names(source):
    names = set()
    for body in IMPORT.findall(source):
        names |= names_in_list(body)
    names |= set(IMPORT_OTHER.findall(source))
    return names


def locally_defined_names(source):
    names = set(DEFINED.findall(source))
    for params, single in PARAM_LISTS.findall(source):
        names |= set(IDENTIFIER.findall(params))
        if single:
            names.add(single)
    for body in DESTRUCTURED.findall(source):
        names |= set(IDENTIFIER.findall(body))
    return names


def called_names(source):
    """Names used like X( -- but not .X( property calls."""
    return set(re.findall(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", source))


class JsImportsTestCase(unittest.TestCase):
    def test_no_module_calls_an_export_it_did_not_import(self):
        files = sorted(JS_DIR.rglob("*.js"))
        self.assertTrue(files, "no JS files found")

        with_comments_gone = {f: strip_comments_only(f.read_text(encoding="utf-8")) for f in files}
        code_only = {f: strip_comments_and_strings(f.read_text(encoding="utf-8")) for f in files}
        exports = {f: exported_names(code_only[f]) for f in files}

        offenders = []
        for file in files:
            others = set().union(*(exports[o] for o in files if o != file))
            available = imported_names(with_comments_gone[file]) | locally_defined_names(code_only[file])
            for name in sorted((called_names(code_only[file]) & others) - available):
                offenders.append(f"{file.relative_to(WEB.parent)}: {name}")

        self.assertEqual(offenders, [], "called but never imported or defined:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
