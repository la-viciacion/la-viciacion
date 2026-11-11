"""Who a log line belongs to: the request being served (an id, the player and the address it came from).

The middleware opens a context per request; the login check fills in the player. It is a mutable holder, not a
value set from the check itself: sync dependencies run in a worker thread, whose changes to a ContextVar do not
reach the request. Background tasks run inside the request's context, so their lines carry it too."""
import contextvars
import secrets

_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar("request_context", default=None)


def begin(ip: str | None) -> contextvars.Token:
    return _current.set({"id": secrets.token_hex(3), "user": None, "ip": ip})


def end(token: contextvars.Token) -> None:
    _current.reset(token)


def set_user(username: str) -> None:
    ctx = _current.get()
    if ctx is not None:
        ctx["user"] = username


def tag() -> str:
    """`[a3f9c1 jose 203.0.113.5] ` for the log line prefix; empty outside a request (scheduler, start-up)."""
    ctx = _current.get()
    if ctx is None:
        return ""
    return f"[{ctx['id']} {ctx['user'] or '-'} {ctx['ip'] or '-'}] "
