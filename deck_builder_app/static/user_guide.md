# Deck Builder App — User Guide

Deck Builder turns a file (spreadsheet or Word document) plus a short
instruction into a slide-by-slide outline.

## How to use it

1. (Optional) Pick a user from the **User** dropdown in the sidebar — this
   identity is forwarded to the Daxa gateway in Safe Infer mode.
2. Optionally upload a file (`.xlsx`, `.xlsm`, or `.docx`) under **📎 Upload a
   file (optional)**. If you don't upload anything, the app automatically
   processes every supported file already sitting in the source-files folder
   instead (see below) — you can also just type instructions with neither.
3. Type what kind of deck you want, e.g. "Summarize this data into a 5-slide
   investor update."
4. Click **🚀 Generate Outline**.
5. The assistant streams back a Markdown outline: one heading and a few
   bullet points per slide. If `DEBUG=true` is set, a `⏱ Timing` line showing
   where the time went is appended too (off by default).

## Uploading vs. the source-files folder

- **Upload a file** → only that file is used for this turn.
- **Don't upload anything** → every supported file in the source-files folder
  (listed in the sidebar under "Documents", clickable) is used instead, in one
  of two ways depending on how the app is configured (`ENABLE_MULTI_PASS`):
  - **Single pass (default)** — all files are combined into one prompt and
    answered in a single call. Fastest, but if that one call errors or gets
    blocked, the whole turn fails.
  - **Multi pass** — each file is processed on its own, then combined into a
    final outline. Slower, but if Safe Infer blocks a particular file's
    content, only that file is skipped — the rest still comes through, and
    the final answer notes what was excluded.
- Files named with "employee" or "client" in them are treated as employee
  details / client details respectively, so the outline labels those
  sections correctly.
- If the app is configured with topic hints for specific files (e.g. "this
  file is about board meetings"), a question that clearly matches one topic
  will only use that file — other files sitting in the folder are skipped
  for that turn, not just ignored in the answer. If your question doesn't
  clearly match, all files are used as normal.

## Modes

- **Safe Infer** — routed through the Daxa/Proxima SafeInfer gateway, with
  Pebblo user/group headers attached.
- **Insecure Inference** — calls the configured model directly, bypassing the
  gateway entirely. Useful for comparing behavior with and without the
  safety layer.

## Tips

- Multiple sheets in a workbook, or all paragraphs/tables in a Word doc, are
  included in full (labeled by sheet name for spreadsheets).
- Very large files are truncated to keep the request a reasonable size —
  keep sample files focused on the data you want summarized.
- If you upload a file that isn't a spreadsheet or Word document, the app
  will still send your typed instructions, just without any file content.
- With `DEBUG=true`, a `⏱ Timing` line at the end of every response is
  computed by the app, not the model — use it to see whether file parsing,
  the per-file calls, or the final combining call is the slow part.
