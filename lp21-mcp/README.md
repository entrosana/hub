# lp21-mcp

Lehrplan 21 (Bern cantonal edition) as a citable reference — on the command
line and as an MCP server for language models.

The first tool in the entrosana learning hub.

## The problem it solves

Anyone writing lesson plans, module descriptions or education research in
Switzerland ends up quoting the Lehrplan 21. Two things go wrong routinely: the
competency code is misremembered, and the wording is paraphrased and then
presented as a quotation. Both are invisible in the finished text.

`lp21` looks up the exact competency, the exact wording of each level, and
produces the citation according to the official Zitierhilfe — including the
stable permalink. `lp21 pruefe` goes the other way: hand it a `.docx` or `.md`
file and it checks every code and every `«…»` quotation in it against the
curriculum, and reports the ones that do not hold.

Over MCP, a model can do this while it writes, instead of a human doing it
afterwards.

## Requirements

Python 3.7 or newer. **No dependencies** — standard library only, for both the
command line tool and the MCP server. Nothing to install, no virtual
environment, no SDK.

## Setup

This repository ships **no curriculum content**. The index is built on your own
machine, from the public site, on first use:

```bash
python lp21.py index
```

That walks about 474 pages with a 0.4 s pause between requests — measured at
roughly eight minutes. It writes `index.json` and `ueberfachlich.json` next to
the script; both are ignored by git.

A subject-area prefix limits what gets **stored**, not what gets **fetched**:

```bash
python lp21.py index MA          # stores Mathematik only
```

This does **not** make the first run faster. The competency code is not visible
in the page address — it only appears on the page itself — so every page has to
be fetched and read before the filter can decide. `index MA` therefore makes
exactly the same number of requests as `index`. It is useful for keeping the
index small, not for being gentle on the source. The pages do land in the local
cache, so a later run with a different prefix costs nothing.

Afterwards every other command works offline. Check the state any time:

```bash
python lp21.py status
```

## Command line

```bash
python lp21.py zeige ERG.5.6        # full competency: wording, levels, links
python lp21.py zitat ERG.5.6.d      # citation for one competency level
python lp21.py suche Konflikt       # full-text search
python lp21.py baum MA              # navigate by subject area
python lp21.py ueberfachlich        # the code-less cross-curricular competencies
python lp21.py pruefe planung.docx  # verify codes and quotations in a document
python lp21.py export               # the whole corpus as Markdown, one file per area
python lp21.py hilfe
```

Exit code is `0` on success and `1` on failure — a missing code, an unknown
level, an absent file. Safe to use in scripts.

## MCP server

```bash
python server.py
```

Speaks JSON-RPC 2.0 over stdin/stdout. Eight tools:

| Tool | What it does |
|---|---|
| `lp21_status` | is the index present and complete |
| `lp21_index` | build the index (the only tool that needs the network) |
| `lp21_zeige` | one competency in full |
| `lp21_zitat` | citation per the official Zitierhilfe |
| `lp21_suche` | full-text search |
| `lp21_baum` | navigate the structure |
| `lp21_ueberfachlich` | cross-curricular competencies |
| `lp21_pruefe` | verify codes and quotations in a file |

`export` is deliberately **not** exposed over MCP. It writes the entire corpus
to disk, which is a bulk extraction of third-party content and belongs in a
deliberate human command, not in a tool a model can trigger in passing.

Failures are reported with `isError: true` so a model can tell a miss from an
answer.

See [claude/](claude/) for wiring it into Claude Desktop and Claude Code.

## About the content

**No Lehrplan 21 text is distributed in this repository.** The tool retrieves it
from `be.lehrplan.ch` onto your machine when you run `lp21.py index`.

Rights to the content of the Lehrplan 21 belong to the Erziehungsdirektion des
Kantons Bern and the D-EDK, not to entrosana. The AGPL-3.0 below covers this
software only. If you want to redistribute the retrieved content, or build it
into a product, you need permission from the rights holders — this tool neither
grants it nor replaces it.

The tool reads the public web frontend. It is deliberately unhurried: 0.4 s
between requests and a disk cache, so a repeated run costs the site nothing. An
official data interface exists at `api.lehrplan.ch` and is the better long-term
path; it requires a usage agreement.

## Licence

AGPL-3.0-or-later. See [LICENSE](LICENSE).

Copyright (C) 2026 entrosana
