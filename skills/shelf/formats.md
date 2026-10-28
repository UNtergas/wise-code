# Shelf formats

Records live in the shelf repo's learning graph and go through `wise.py --root
"<shelf>"` only (see [../learn/materials.md](../learn/materials.md)). Dates are
`YYYY-MM-DD`. Page numbers are PDF page numbers (what `pdftotext -f` takes);
`printed` holds the printed page range when it differs.

## Project config: `<state>/shelf.md`

The learner writes this file in each project that uses the shelf. Its presence
turns the shelf on for that project.

```md
# Shelf
Repo: UNtergas/wise-code-shelf
Project: job-tracking
Folders: job-tracking
```

- `Repo`: exact `owner/name` of the private shelf repo.
- `Project`: the project's stable name. Required: every shelf record carries it,
  so it must survive renaming the folder or cloning on another machine.
- `Folders`: comma-separated top-level folders of the shelf this project may
  read. Usually just the project's own folder. `shared` is always added.
- Optional `Mode: shelf` marks the shelf repo itself when its `origin` can't be read.
- Optional `LFS prompt: off` stops the Git LFS install prompt.

## Shelf repo layout

```
wise-code-shelf/
  shared/                  any project may read
  <folder>/                only projects listing <folder> may read
  .wise-code/
    graph/
      nodes.jsonl          books, sections, citations, reads, explain-backs,
      edges.jsonl          and the shelf's own questions, cards and Q/A
      .gitattributes       *.jsonl merge=union
```

Book slug: file name without extension, lowercase, spaces and underscores to `-`.
Supported files: `.pdf` with a text layer, `.md`, `.txt`.

## Nodes

| Type | ID | Fields | Edges |
|---|---|---|---|
| `book` | `BK-<book-slug>` (stable) | `slug`, `title`, `file`, `folder`, `pages`, `l1` (outline date), `projects` (every project that cited it, kept by the script) | |
| `section` | `SEC-<book-slug>-<number>` (stable; `1` a chapter, `1.2` a section) | `book`, `number`, `title`, `pages` (`32-40`), `printed`, `concepts` (key concepts), `l2` (detail date) | `of` → book; `covers` → concept |
| `citation` | `CIT-YYYYMMDD-xxxx` | `project`, `question`, `quote`, `page`, `status`: `sent` → `understood` \| `partial` \| `misread`, or `skipped-read` | `on` → section |
| `read` | `RD-…` | `project`, `verdict`, `evidence` | `on` → section, `for` → citation |
| `explainback` | `EB-…` | `project`, `text` (gist of the learner's explanation, never a transcript), `verdict` | `on` → section, `for` → citation |

Stable book and section IDs mean every project names the same section the same
way; adding one again updates it. The shelf's own questions and cards point to
their section with `from`.

## Queries

- `wise.py --root "<shelf>" list book`, `list section --where book=<slug> --limit 40`
- `find <words> --type section`: match a question against the index
- `impact [<book-slug>]`: books ranked by use; per project: citations, sections,
  understood vs not yet; for one book, the concepts its sections cover
- `list citation --where status=sent` (or `partial`), `list citation --where project=<Project>`
- `due`: book questions to quiz in the shelf repo

The project side keeps only pointers: a concept's `shelf` list holds section IDs,
and a `shelf` QA names the citation. `wise.py check --shelf <shelf folder>` warns
about IDs the shelf no longer has.
