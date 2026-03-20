import sys
from pathlib import Path

import pymupdf4llm


def convert_pdf_folder(input_dir: str, output_dir: str) -> None:
    in_path = Path(input_dir).expanduser().resolve()
    out_path = Path(output_dir).expanduser().resolve()

    if not in_path.exists():
        raise FileNotFoundError(f"Input folder not found: {in_path}")

    if not in_path.is_dir():
        raise NotADirectoryError(f"Input path is not a folder: {in_path}")

    out_path.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(in_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found under: {in_path}")
        return

    success = 0
    failed = 0

    for pdf_file in pdf_files:
        md_file = out_path / f"{pdf_file.stem}.md"
        try:
            print(f"Converting: {pdf_file.name}")
            md_text = pymupdf4llm.to_markdown(str(pdf_file))
            md_file.write_text(md_text, encoding="utf-8")
            print(f"Generated:  {md_file}")
            success += 1
        except Exception as e:
            print(f"Failed:     {pdf_file.name} -> {e}")
            failed += 1

    print("")
    print(f"Done. success={success}, failed={failed}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python pdf.py <input_pdf_folder> <output_md_folder>")
        sys.exit(1)

    convert_pdf_folder(sys.argv[1], sys.argv[2])
