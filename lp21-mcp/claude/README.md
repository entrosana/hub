# Using lp21 with Claude

The server speaks MCP over stdin/stdout and needs nothing installed — Python
3.7 or newer is enough.

Replace `/absolute/path/to/lp21-mcp` below with the real path on your machine.
It must be absolute: the client starts the server from an unrelated working
directory.

## Claude Code

```bash
claude mcp add -s user lp21 -- python3 /absolute/path/to/lp21-mcp/server.py
```

`-s user` registers the server for your account. Without it the default scope is
`local`, which binds the server to the directory you happened to be in — it then
disappears the moment you work anywhere else.

Check it came up:

```bash
claude mcp list
```

## Claude Desktop

Add the block from [`config.example.json`](config.example.json) to your
`claude_desktop_config.json`:

- macOS `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows `%APPDATA%\Claude\claude_desktop_config.json`
- Linux `~/.config/Claude/claude_desktop_config.json` (Claude Desktop is not
  officially released for Linux; this path applies to community builds)

On Windows, `python3` is not a reliable command — the PATH entry is optional and
without it the Store redirect swallows the call. Use `py` or the full
interpreter path there. On macOS an app launched from the Dock inherits a very
short PATH, so a Homebrew or pyenv interpreter will not be found; use the full
path from `which python3`.

Restart Claude Desktop afterwards. If the file already has an `mcpServers`
object, add `lp21` inside it rather than replacing the object.

## First run

The tools need an index. Ask Claude to call `lp21_status`; if it reports the
index missing, build it once:

```bash
python3 /absolute/path/to/lp21-mcp/lp21.py index
```

That takes about eight minutes — roughly 474 pages with a 0.4 s pause between
them. `lp21_index` does the same thing from inside Claude, but a client will
almost certainly time out first, so the command line is the right place for the
first run.

Adding a subject-area prefix does **not** shorten it. The filter can only be
applied after each page has been fetched and read, so `index MA` makes the same
number of requests as `index` — it just stores less. If you build a partial
index this way, be aware of two consequences: lookups outside that subject area
will fail, and `lp21_status` will keep reporting an error, because it expects
around 360 competencies. Repair a partial or damaged index with:

```bash
python3 /absolute/path/to/lp21-mcp/lp21.py index --frisch
```

The index is written next to the script, inside the checkout, as `index.json`
and `ueberfachlich.json` — about 890 kB together. That directory has to be
writable. Both files are listed in `.gitignore` and will not be committed.

After a full run, everything else works offline.

One thing to know before pasting output anywhere public: `lp21_status` reports
the machine name, the absolute script path and the cache location, which
contains your user name. Nothing of that is stored in the repository — it is
produced at runtime — but it does travel to the model, and into any issue you
paste it into.

## Getting good answers

Two habits make the difference:

**Search before quoting.** Codes are easy to misremember and a plausible-looking
code is often wrong. `lp21_suche` first, then `lp21_zeige` on the code it
returns.

**Never let the model compose the citation.** `lp21_zitat` produces it according
to the official Zitierhilfe, with the stable permalink. A hand-written citation
looks the same and is frequently wrong about the edition or the date.

`lp21_pruefe` closes the loop: point it at a finished `.docx` or `.md` and it
reports every code that does not exist and every `«…»` quotation that does not
match the curriculum wording.

A failed lookup comes back with `isError: true`, so a wrong code reads as a
failure rather than as an answer.

## Note on content

No curriculum text ships with this repository. `lp21.py index` retrieves it from
`be.lehrplan.ch` onto your own machine. Rights to the content belong to the
Erziehungsdirektion des Kantons Bern and the D-EDK. See the main
[README](../README.md).
