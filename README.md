# MD Side By Side

Live Markdown preview beside your source, inside Sublime Text. No browser, no
dependencies. The preview is a native HTML sheet drawn with Sublime's minihtml
engine and follows your color scheme.

## Use

Open a Markdown file, then any of:

- **Windows / Linux:** `Ctrl+Alt+M`
- **macOS:** `Cmd+Alt+M`
- Command Palette: `MD Side By Side: Toggle Preview`
- Right-click in the editor: `Toggle Markdown Side-by-Side Preview`

Run it again to close the preview and restore your previous layout. If your
window already has two or more groups, the preview opens in the next group and
your layout is left alone. Closing the preview tab with its x also restores the
layout, once you click back into the source tab.

Other command: `MD Side By Side: Refresh Preview`.

## Supported Markdown

Front matter (shown as a dim header), headings, paragraphs and hard breaks,
bold, italic, inline code, links, fenced code blocks, nested bullet / numbered /
task lists, block quotes, horizontal rules, and pipe tables.

## Limits

- **Tables** render as aligned monospace blocks, because minihtml has no
  `<table>`. Wide tables scroll sideways instead of wrapping.
- **No scroll sync.** Sublime's API exposes no scroll control for HTML sheets
  ([sublimehq/sublime_text#6434](https://github.com/sublimehq/sublime_text/issues/6434)).
- Images are not rendered.
- Numbered lists are drawn with explicit numbers, because minihtml shows `<ol>` items
  as bullets. Wrapped lines sit under the number instead of hanging.
- The whole document re-renders after each pause in typing; very large files
  will lag. Raise `debounce_ms` if so.

## Settings

`Preferences > Package Settings > MD Side By Side > Settings`

| Key | Default | Meaning |
|---|---|---|
| `debounce_ms` | `150` | Wait after the last keystroke before re-rendering |
| `split_ratio` | `0.5` | Source pane width when a fresh split is created (0.2 to 0.8) |

## Requirements

Sublime Text build 4088 or newer (uses `Sheet.close()`).

## License

MIT. See `LICENSE`.
