"""Errors the person using the app is meant to read.

An HTTPException carries one sentence, and that sentence is English. The interface
shows it verbatim, so "Username already exists" appeared in the middle of an Arabic
form - the one place in the product where the language simply stopped.

Translating on the server would mean the API answered differently depending on who
asked, and would put the interface's wording behind a deploy. So the error carries an
identifier as well as the sentence: `{"detail": "Username already exists", "code":
"username_taken"}`. The interface translates the code and falls back to the sentence
when it does not recognise one, which is what keeps the uncoded errors - the ones
carrying a column name or a parser's complaint - working exactly as before.

Adding a code here without a matching entry in the locale files would put an
untranslated string back on screen, so the two are kept in step by a test: see
tests/test_error_codes.py.
"""

from typing import Optional

from fastapi import HTTPException


class ApiError(HTTPException):
    """An HTTPException that also says which error this is, not just what it reads."""

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        headers: Optional[dict] = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
