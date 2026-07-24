# Deck Builder App — User Guide

Deck Builder turns a spreadsheet plus a short instruction into a slide-by-slide
outline.

## How to use it

1. (Optional) Pick a user from the **User** dropdown in the sidebar — this
   identity is forwarded to the Daxa gateway in Safe Infer mode.
2. Upload a spreadsheet (`.xlsx`) using the file uploader next to the message
   box. This is optional — you can also just type instructions.
3. Type what kind of deck you want, e.g. "Summarize this data into a 5-slide
   investor update."
4. Click **🚀 Generate Outline**.
5. The assistant streams back a Markdown outline: one heading and a few
   bullet points per slide.

## Modes

- **Safe Infer** — routed through the Daxa/Proxima SafeInfer gateway, with
  Pebblo user/group headers attached.
- **Insecure Inference** — calls the configured model directly, bypassing the
  gateway entirely. Useful for comparing behavior with and without the
  safety layer.

## Tips

- Multiple sheets in one workbook are all included, labeled by sheet name.
- Very large sheets are truncated to keep the request a reasonable size —
  keep sample files focused on the data you want summarized.
- If you upload a file that isn't a spreadsheet, the app will still send your
  typed instructions, just without any file content.
