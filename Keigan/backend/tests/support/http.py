"""Type of the ``auth_headers`` fixture: ``await auth_headers(upn)`` → ``{"Authorization": "Bearer ..."}``."""

from collections.abc import Awaitable, Callable

AuthHeaders = Callable[[str], Awaitable[dict[str, str]]]
