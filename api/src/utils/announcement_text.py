"""The text of a notice an admin writes (Notificaciones → Redactar aviso): a small subset of Markdown, drawn for Telegram
(HTML, which is the one Telegram parse mode whose escaping is simple and safe) or as plain text for the app's push
notifications and inbox, which cannot show any format.

What is understood (everything else is plain text, and anything that looks like HTML is escaped, never interpreted):

  # Heading            a bold line (any level)
  **bold**  __bold__   bold
  *italic*  _italic_   italic (a `_` inside a word, as in snake_case, is left alone)
  ~~struck~~           struck through
  `code`               inline code        ```...```  a code block
  [text](https://...)  a link (only http and https; any other address leaves just the text)
  - item  * item  + item   a bullet (two spaces of indentation per nesting level, up to two)
  1. item              a numbered item, kept as written
  > quote              a quote
  ---                  a separator line

The same rules are drawn in the admin panel's preview (front/js/lib/announce-format.js): change one, change the other.
"""
import html
import re

TITLE_MAX = 80
BODY_MAX = 3000  # what an admin writes; Telegram allows 4096 characters in a message once it is drawn
MESSAGE_MAX = 4000  # of the drawn text, title included (a bit under Telegram's 4096)

FENCE = re.compile(r"^\s*```")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
NUMBERED = re.compile(r"^(\s*)(\d{1,3}[.)])\s+(.*)$")
QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")
RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
RULE_LINE = "──────────"
BULLETS = ["•", "◦", "▪"]
INDENT = " "  # an em space: Telegram keeps it where it would trim ordinary spaces

CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
ITALIC_STAR = re.compile(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])")
ITALIC_UNDERSCORE = re.compile(r"(?<![_\w])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![_\w])")


def _safe_url(url: str) -> str | None:
    return url if re.match(r"^https?://", url, re.IGNORECASE) else None


def _inline(text: str, as_html: bool) -> str:
    """One line of text: the inline marks as Telegram HTML, or taken off for plain text."""
    saved: list[str] = []

    def keep(markup: str) -> str:
        saved.append(markup)
        return f"\x00{len(saved) - 1}\x00"

    def code(match):
        return keep(f"<code>{html.escape(match.group(1), quote=False)}</code>" if as_html else match.group(1))

    def link(match):
        label, url = match.group(1), _safe_url(match.group(2))
        if not as_html or url is None:
            return keep(html.escape(label, quote=False) if as_html else label)
        return keep(f'<a href="{html.escape(url, quote=True)}">{html.escape(label, quote=False)}</a>')

    text = CODE_SPAN.sub(code, text)
    text = LINK.sub(link, text)
    if as_html:
        text = html.escape(text, quote=False)
        for pattern, tag in ((BOLD, "b"), (STRIKE, "s"), (ITALIC_STAR, "i"), (ITALIC_UNDERSCORE, "i")):
            text = pattern.sub(lambda m, tag=tag: f"<{tag}>{m.group(m.lastindex)}</{tag}>", text)
    else:
        for pattern in (BOLD, STRIKE, ITALIC_STAR, ITALIC_UNDERSCORE):
            text = pattern.sub(lambda m: m.group(m.lastindex), text)
    return re.sub(r"\x00(\d+)\x00", lambda m: saved[int(m.group(1))], text)


def _render(markdown: str, as_html: bool) -> str:
    lines = (markdown or "").replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    out: list[str] = []
    quote: list[str] = []
    code: list[str] | None = None

    def flush_quote():
        if quote:
            text = "\n".join(_inline(line, as_html) for line in quote)
            out.append(f"<blockquote>{text}</blockquote>" if as_html else text)
            quote.clear()

    for raw in lines:
        line = raw.rstrip()
        if FENCE.match(line):
            flush_quote()
            if code is None:
                code = []
            else:
                body = "\n".join(code)
                out.append(f"<pre>{html.escape(body, quote=False)}</pre>" if as_html else body)
                code = None
            continue
        if code is not None:
            code.append(raw.rstrip("\n"))
            continue
        quoted = QUOTE.match(line)
        if quoted:
            quote.append(quoted.group(1))
            continue
        flush_quote()
        if not line.strip():
            if out and out[-1] != "":
                out.append("")
        elif RULE.match(line):
            out.append(RULE_LINE)
        elif HEADING.match(line):
            text = re.sub(r"\*\*|__", "", HEADING.match(line).group(1))
            out.append(f"<b>{_inline(text, True)}</b>" if as_html else _inline(text, False))
        elif BULLET.match(line):
            indent, text = BULLET.match(line).groups()
            level = min(len(indent.expandtabs(2)) // 2, len(BULLETS) - 1)
            out.append(f"{INDENT * level}{BULLETS[level]} {_inline(text, as_html)}")
        elif NUMBERED.match(line):
            indent, number, text = NUMBERED.match(line).groups()
            level = min(len(indent.expandtabs(2)) // 2, 2)
            out.append(f"{INDENT * level}{number} {_inline(text, as_html)}")
        else:
            out.append(_inline(line.strip(), as_html))
    flush_quote()
    if code is not None:  # a block that was never closed still shows what it holds
        body = "\n".join(code)
        out.append(f"<pre>{html.escape(body, quote=False)}</pre>" if as_html else body)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def to_telegram_html(markdown: str) -> str:
    """The text as Telegram HTML (the parse mode `HTML`)."""
    return _render(markdown, True)


def to_plain(markdown: str) -> str:
    """The text with its marks taken off, bullets and quotes kept as plain lines."""
    return _render(markdown, False)


def telegram_message(title: str, body: str | None) -> tuple[str, str]:
    """(HTML, plain): the notice as Telegram takes it, and the same without marks for when Telegram cannot parse it."""
    title = (title or "").strip()
    drawn = to_telegram_html(body or "")
    plain = to_plain(body or "")
    head = f"<b>{html.escape(title, quote=False)}</b>"
    return (head + "\n\n" + drawn if drawn else head), (title + "\n\n" + plain if plain else title)


def too_long(title: str, body: str | None) -> bool:
    """Whether the notice, drawn, would not fit in one Telegram message."""
    return len((title or "").strip()) + 2 + len(to_plain(body or "")) > MESSAGE_MAX


def push_body(body: str | None, limit: int | None = None) -> str | None:
    """The message for the app's inbox: plain text in one line (the bullets taken off, the lines joined with a dot),
    cut at a word with an ellipsis when it is longer than `limit`."""
    lines = (re.sub(rf"^[{INDENT}\s]*[{''.join(BULLETS)}]\s+", "", line.strip()) for line in to_plain(body or "").splitlines())
    text = " · ".join(line for line in lines if line)
    if limit and len(text) > limit:
        cut = text[: limit - 1]
        if " " in cut and text[limit - 1] != " ":
            cut = cut.rsplit(" ", 1)[0]
        text = cut.rstrip(" ·,;:") + "…"
    return text or None
