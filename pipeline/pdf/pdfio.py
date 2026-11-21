"""Shared input and output steps of the single-document PDF readers
(reader_ausdruck.py, reader_angebot.py): page text with Poppler's pdftotext,
the manifest entry and the two output files. reader_79222.py keeps its own."""

import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import reader_79222  # noqa: E402


def pdftotext_is_poppler(exe=None):
    """True when the pdftotext on PATH is Poppler's (xpdf gives another layout)."""
    exe = exe or shutil.which("pdftotext")
    if not exe:
        return False
    res = subprocess.run([exe, "-v"], capture_output=True)
    return b"poppler" in (res.stdout + res.stderr).lower()


def extract_text(pdf_path):
    """`pdftotext -layout` text of one PDF; "=== PAGE n ===" starts page n."""
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("pdftotext not found on PATH")
    res = subprocess.run([exe, "-layout", "-enc", "UTF-8", pdf_path, "-"],
                         capture_output=True, check=True)
    out = []
    for i, chunk in enumerate(res.stdout.decode("utf-8").split("\f"), 1):
        out.append("=== PAGE %d ===" % i)
        out.append(chunk.rstrip("\n"))
    return "\n".join(out) + "\n"


def read_source(path):
    """Return (text, file name, sha256 of that file) for a PDF or for a text
    file with page markers."""
    name = os.path.basename(path)
    digest = reader_79222.sha256_file(path)
    if name.lower().endswith(".pdf"):
        return extract_text(path), name, digest
    with open(path, encoding="utf-8") as f:
        return f.read(), name, digest


def doc_from_file(name):
    """Document id: the file name without its extension."""
    return os.path.splitext(os.path.basename(name))[0]


def manifest_entry(doc, file_name, digest, stage, pages, records, unparsed,
                   warnings):
    return {
        "doc": doc, "file": file_name, "sha256": digest,
        "format": "pdf", "stage": stage, "pages": pages,
        "items": sum(1 for r in records if r["quantity"] is not None),
        "headings": sum(1 for r in records if r["kind"] == "heading"),
        "preliminary_notes": sum(1 for r in records
                                 if r["kind"] == "preliminary_note"),
        "unparsed_lines": unparsed, "warnings": warnings,
    }


def write_outputs(out_dir, records, manifest):
    os.makedirs(out_dir, exist_ok=True)
    for fname, data in (("items.json", records), ("manifest.json", manifest)):
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8",
                  newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")


def run_reader(parser_class, source, out_dir=None, doc=None):
    """Read one document with a DocParser subclass. Returns (records, manifest)."""
    text, file_name, digest = read_source(source)
    doc = doc or doc_from_file(file_name)
    parser = parser_class(doc, text)
    records, pages = parser.parse()
    manifest = [manifest_entry(doc, file_name, digest, parser_class.STAGE,
                               pages, records, parser.unparsed,
                               parser.warnings)]
    if out_dir:
        write_outputs(out_dir, records, manifest)
    return records, manifest


def main(parser_class, usage, argv):
    if len(argv) not in (2, 3):
        sys.stderr.write(usage)
        return 2
    records, manifest = run_reader(parser_class, *argv)
    m = manifest[0]
    print("doc=%s entries=%d items=%d pages=%d warnings=%d unparsed=%d" % (
        m["doc"], len(records), m["items"], m["pages"], len(m["warnings"]),
        m["unparsed_lines"]))
    return 0
