import pymupdf4llm

md_text = pymupdf4llm.to_markdown("input.pdf")
with open("output.md", "w", encoding="utf-8") as f:
    f.write(md_text)

print("done")
