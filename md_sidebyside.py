"""MD Side By Side: live Markdown preview beside the source, in the editor.

The preview is a Sublime HtmlSheet drawn with minihtml, so there is no browser
and no dependency. minihtml has no <table>, so tables render as aligned
monospace blocks.
"""

import os
import re
import traceback

try:
    import sublime
    import sublime_plugin
except ImportError:  # lets render_markdown be tested outside Sublime
    sublime = None
    sublime_plugin = None


CSS = """
<style>
    body { padding: 0.4rem 1rem; }
    h1 { font-size: 1.7rem; margin-top: 0.9rem; margin-bottom: 0.4rem; padding-bottom: 0.2rem; border-bottom: 1px solid #8884; }
    h2 { font-size: 1.4rem; margin-top: 0.9rem; margin-bottom: 0.4rem; padding-bottom: 0.2rem; border-bottom: 1px solid #8884; }
    h3 { font-size: 1.15rem; margin-top: 0.8rem; margin-bottom: 0.3rem; }
    h4 { font-size: 1.0rem; margin-top: 0.7rem; margin-bottom: 0.3rem; }
    h5 { font-size: 1.0rem; margin-top: 0.7rem; margin-bottom: 0.3rem; }
    h6 { font-size: 1.0rem; margin-top: 0.7rem; margin-bottom: 0.3rem; }
    p { margin-top: 0.2rem; margin-bottom: 0.5rem; }
    ul { margin-top: 0.2rem; margin-bottom: 0.4rem; }
    ol { margin-top: 0.2rem; margin-bottom: 0.4rem; }
    a { color: var(--bluish); }
    code { background-color: #8833; padding: 0 0.2rem; border-radius: 3px; }
    div.pre { background-color: #8822; padding: 0.5rem; margin-top: 0.3rem; margin-bottom: 0.6rem; border-radius: 4px; }
    div.quote { border-left: 3px solid #8886; padding-left: 0.7rem; margin-top: 0.3rem; margin-bottom: 0.5rem; }
    div.hr { border-bottom: 1px solid #8886; margin-top: 0.6rem; margin-bottom: 0.6rem; }
    div.fm { color: #888c; font-size: 0.9rem; margin-bottom: 0.6rem; padding-bottom: 0.4rem; border-bottom: 1px solid #8884; }
</style>
"""


# --------------------------------------------------------------------------
# inline
# --------------------------------------------------------------------------

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text):
    codes = []

    def stash(m):
        codes.append("<code>" + esc(m.group(1)) + "</code>")
        return "\x00%d\x00" % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", stash, text)
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])", r"<em>\1</em>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: '<a href="%s">%s</a>' % (m.group(2).replace('"', "%22"), m.group(1)),
        text,
    )
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


# --------------------------------------------------------------------------
# blocks
# --------------------------------------------------------------------------

RE_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RE_HR = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
RE_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
RE_FENCE = re.compile(r"^\s*(```|~~~)")
RE_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def render_table(rows, seps):
    aligns = []
    for s in seps:
        s = s.strip()
        if s.startswith(":") and s.endswith(":"):
            aligns.append("c")
        elif s.endswith(":"):
            aligns.append("r")
        else:
            aligns.append("l")
    plain = [[re.sub(r"\*\*|`", "", c) for c in r] for r in rows]
    ncol = max(len(r) for r in plain)
    for r in plain:
        r.extend([""] * (ncol - len(r)))
    aligns.extend(["l"] * (ncol - len(aligns)))
    widths = [max(len(r[i]) for r in plain) for i in range(ncol)]

    def fmt(r):
        cells = []
        for i, c in enumerate(r):
            if aligns[i] == "r":
                cells.append(c.rjust(widths[i]))
            elif aligns[i] == "c":
                cells.append(c.center(widths[i]))
            else:
                cells.append(c.ljust(widths[i]))
        return "| " + " | ".join(cells) + " |"

    lines = [fmt(plain[0]), "|-" + "-|-".join("-" * w for w in widths) + "-|"]
    lines.extend(fmt(r) for r in plain[1:])
    return pre_block("\n".join(lines))


def pre_block(text):
    return (
        '<div class="pre" style="white-space: pre"><tt style="white-space: pre">'
        + esc(text)
        + "</tt></div>"
    )


def task(text):
    if text.startswith("[ ] "):
        return "☐ " + text[4:]
    if text[:4].lower() == "[x] ":
        return "☑ " + text[4:]
    return text


def render_bullets(items):
    out = []
    stack = []  # (indent, tag)
    for indent, ordered, text, _marker in items:
        tag = "ol" if ordered else "ul"
        while stack and indent < stack[-1][0]:
            out.append("</li></%s>" % stack.pop()[1])
        if stack and indent == stack[-1][0]:
            out.append("</li>")
        else:
            out.append("<%s>" % tag)
            stack.append((indent, tag))
        out.append("<li>" + inline(task(text)))
    while stack:
        out.append("</li></%s>" % stack.pop()[1])
    return "".join(out)


def render_mixed(items):
    """Lists containing numbered items. minihtml shows <ol> items with bullets,
    so every item is a plain block with an explicit marker and a depth indent."""
    out = ['<div style="margin-top: 0.2rem; margin-bottom: 0.4rem">']
    stack = []  # [indent, counter, level_is_numbered]
    for indent, ordered, text, marker in items:
        while stack and indent < stack[-1][0]:
            stack.pop()
        if not stack or indent > stack[-1][0]:
            stack.append([indent, int(marker[:-1]) if ordered else 0, ordered])
        elif ordered:
            stack[-1][1] += 1
        depth = len(stack) - 1
        if ordered:
            label = "%d." % stack[-1][1]
        else:
            # like browsers: glyph follows how many bullet levels sit above
            bullet_levels = sum(1 for lvl in stack if not lvl[2]) - 1
            label = "\u2022" if bullet_levels % 2 == 0 else "\u25e6"
        out.append(
            '<div style="margin-left: %.1frem; margin-bottom: 0.15rem">%s %s</div>'
            % (0.5 + 1.4 * depth, label, inline(task(text)))
        )
    out.append("</div>")
    return "".join(out)


def render_list(items):
    if any(it[1] for it in items):
        return render_mixed(items)
    return render_bullets(items)


def starts_block(line, nxt):
    return bool(
        RE_HEADING.match(line)
        or RE_HR.match(line)
        or RE_LIST.match(line)
        or RE_FENCE.match(line)
        or line.lstrip().startswith(">")
        or ("|" in line and nxt is not None and RE_TABLE_SEP.match(nxt))
    )


def render_blocks(lines):
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < n else None

        if not line.strip():
            i += 1
            continue

        if RE_FENCE.match(line):
            fence = RE_FENCE.match(line).group(1)
            i += 1
            buf = []
            while i < n and not lines[i].lstrip().startswith(fence):
                buf.append(lines[i])
                i += 1
            i += 1  # closing fence
            out.append(pre_block("\n".join(buf)))
            continue

        m = RE_HEADING.match(line)
        if m:
            lvl = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (lvl, inline(m.group(2)), lvl))
            i += 1
            continue

        if RE_HR.match(line):
            out.append('<div class="hr"></div>')
            i += 1
            continue

        if "|" in line and nxt is not None and RE_TABLE_SEP.match(nxt):
            rows = [split_row(line)]
            seps = split_row(nxt)
            i += 2
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1
            out.append(render_table(rows, seps))
            continue

        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append('<div class="quote">' + render_blocks(buf) + "</div>")
            continue

        m = RE_LIST.match(line)
        if m:
            items = []
            while i < n:
                lm = RE_LIST.match(lines[i])
                if lm:
                    ind = len(lm.group(1).expandtabs(4))
                    ordered = lm.group(2)[0].isdigit()
                    # same level, different list type -> a new list starts
                    if items and ind <= items[0][0] and ordered != items[0][1]:
                        break
                    items.append([ind, ordered, lm.group(3), lm.group(2)])
                    i += 1
                    continue
                if not lines[i].strip():
                    j = i
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and RE_LIST.match(lines[j]):
                        i = j
                        continue
                    break
                if lines[i][:1] in (" ", "\t") and items:
                    items[-1][2] += " " + lines[i].strip()  # continuation
                    i += 1
                    continue
                break
            out.append(render_list(items))
            continue

        buf = []
        while i < n and lines[i].strip():
            nx = lines[i + 1] if i + 1 < n else None
            if buf and starts_block(lines[i], nx):
                break
            buf.append(lines[i])
            i += 1
        parts = []
        for k, b in enumerate(buf):
            br = b.endswith("  ") and k < len(buf) - 1
            parts.append(inline(b.strip()) + ("<br>" if br else ""))
        out.append("<p>" + " ".join(parts) + "</p>")
    return "".join(out)


def render_markdown(text):
    lines = text.replace("\r\n", "\n").split("\n")
    front = ""
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                fm = "\n".join(lines[1:j])
                front = ('<div class="fm" style="white-space: pre">'
                         + esc(fm) + "</div>")
                lines = lines[j + 1:]
                break
    return '<body id="md-sidebyside">' + CSS + front + render_blocks(lines) + "</body>"


# --------------------------------------------------------------------------
# Sublime glue
# --------------------------------------------------------------------------

SETTINGS_FILE = "MdSideBySide.sublime-settings"
MD_SELECTOR = "text.html.markdown"
MD_EXTS = (".md", ".markdown", ".mdown", ".mkd")

# source view id -> {"sheet": preview sheet id, "layout": layout to restore or None}
_state = {}
# source view id -> latest edit counter (debounce)
_tick = {}


def is_markdown(view):
    if view is None:
        return False
    if view.match_selector(0, MD_SELECTOR):
        return True
    return (view.file_name() or "").lower().endswith(MD_EXTS)


def render(view):
    try:
        return render_markdown(view.substr(sublime.Region(0, view.size())))
    except Exception:
        return ('<body id="md-sidebyside">' + CSS
                + pre_block(traceback.format_exc()) + "</body>")


def preview_name(view):
    path = view.file_name()
    return "Preview: " + (os.path.basename(path) if path else (view.name() or "untitled"))


def find_sheet(window, sheet_id):
    for sheet in window.sheets():
        if sheet.id() == sheet_id:
            return sheet
    return None


def refresh(view):
    st = _state.get(view.id())
    window = view.window()
    if st is None or window is None:
        return False
    sheet = find_sheet(window, st["sheet"])
    if sheet is None:
        return False
    sheet.set_contents(render(view))
    return True


def refresh_if_current(view, tick):
    if _tick.get(view.id()) == tick:
        refresh(view)


def close_preview(view):
    st = _state.pop(view.id(), None)
    _tick.pop(view.id(), None)
    window = view.window()
    if st is None or window is None:
        return
    sheet = find_sheet(window, st["sheet"])
    if sheet is not None:
        sheet.close()
    if st["layout"] is not None:
        window.set_layout(st["layout"])


if sublime is not None:

    class MdSideBySideCommand(sublime_plugin.TextCommand):
        """Toggle: open the preview beside this Markdown file, or close it."""

        def is_enabled(self):
            return is_markdown(self.view)

        def is_visible(self):
            return is_markdown(self.view)

        def run(self, edit):
            view = self.view
            window = view.window()
            if window is None:
                return

            st = _state.get(view.id())
            if st is not None and find_sheet(window, st["sheet"]) is not None:
                close_preview(view)
                return

            # Layout to restore on close. Carry it over if an earlier preview
            # of ours was closed by hand and left the split behind.
            restore = st["layout"] if st is not None else None
            if window.num_groups() >= 2:
                group = (window.active_group() + 1) % window.num_groups()
            else:
                restore = window.layout()
                ratio = float(sublime.load_settings(SETTINGS_FILE).get("split_ratio", 0.5))
                ratio = min(0.8, max(0.2, ratio))
                window.set_layout({
                    "cols": [0.0, ratio, 1.0],
                    "rows": [0.0, 1.0],
                    "cells": [[0, 0, 1, 1], [1, 0, 2, 1]],
                })
                group = 1

            sheet = window.new_html_sheet(preview_name(view), render(view), group=group)
            _state[view.id()] = {"sheet": sheet.id(), "layout": restore}
            window.focus_view(view)

    class MdSideBySideRefreshCommand(sublime_plugin.TextCommand):
        """Re-render the preview now."""

        def is_enabled(self):
            return self.view.id() in _state

        def run(self, edit):
            refresh(self.view)

    class MdSideBySideListener(sublime_plugin.EventListener):
        def on_modified_async(self, view):
            if view.id() not in _state:
                return
            delay = int(sublime.load_settings(SETTINGS_FILE).get("debounce_ms", 150))
            tick = _tick.get(view.id(), 0) + 1
            _tick[view.id()] = tick
            sublime.set_timeout_async(lambda: refresh_if_current(view, tick), delay)

        def on_activated_async(self, view):
            # Sublime fires no close event for HTML sheets, so detect a preview
            # closed by hand (tab x) here and undo the split we created.
            st = _state.get(view.id())
            window = view.window()
            if st is None or window is None:
                return
            if find_sheet(window, st["sheet"]) is None:
                close_preview(view)

        def on_pre_close(self, view):
            if view.id() in _state:
                close_preview(view)
