#!/usr/bin/env python3
"""
DeckExtract.py — PDF card image extractor for prompt cards in PDF

Three extraction modes:

  default  All images from all pages.
           Named: {page:04d}_{pos:02d}.ext  (e.g. 0000_01.jpeg)

  1sided   Even pages only (0, 2, 4, …) extracted like default.
           Odd pages: one unique copy of each distinct back image.
           Backs named: back_{n:02d}.ext

  2sided   Even pages = fronts, following odd page = backs.
           Rows align between front and back, but columns mirror/swap.
           Named: {even_page:04d}_{pos:02d}F.ext  (front)
                  {even_page:04d}_{pos:02d}B.ext  (back, column-swapped)

Usage:
    python DeckExtract.py cards.pdf
    python DeckExtract.py cards.pdf --mode 1sided --out ./extracted
    python DeckExtract.py cards.pdf --mode 2sided --out ./extracted --cols 2

Requires: pymupdf
    pip install pymupdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def make_output_dir(pdf_path: Path, out_root: Optional[Path]) -> Path:
    out_dir = out_root if out_root else Path.cwd() / "output" / pdf_path.stem
    safe_mkdir(out_dir)
    return out_dir


def get_image_occurrences(page: fitz.Page) -> List[Dict[str, Any]]:
    """
    Return image occurrences on a page, each with at least {xref, bbox}.
    Prefers get_image_info (includes bbox/position); falls back to get_images.
    """
    if hasattr(page, "get_image_info"):
        try:
            infos = page.get_image_info(xrefs=True)  # type: ignore[attr-defined]
        except TypeError:
            try:
                infos = page.get_image_info()  # type: ignore[attr-defined]
            except Exception:
                infos = None
        except Exception:
            infos = None

        if infos is not None:
            result = []
            for inf in infos:
                xref = inf.get("xref")
                if not xref:
                    continue
                result.append({"xref": int(xref), "bbox": inf.get("bbox")})
            return result

    # Fallback — no position info available
    return [
        {"xref": int(img[0]), "bbox": None}
        for img in page.get_images(full=True)
        if img[0]
    ]


def sort_by_position(occurrences: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort occurrences top-to-bottom, left-to-right using bbox (y_top, x_left)."""
    def key(o: Dict[str, Any]):
        bbox = o.get("bbox")
        return (bbox[1], bbox[0]) if bbox else (0, 0)
    return sorted(occurrences, key=key)


def swapped_col_pos(front_pos: int, num_cols: int) -> int:
    """
    Given a 1-based grid position with num_cols columns, return the position
    that has the same row but the column mirrored (left↔right swap).

    Example with 2 cols:
      pos 1 (top-left)  → 2 (top-right)
      pos 2 (top-right) → 1 (top-left)
      pos 3 (mid-left)  → 4 (mid-right)
      …
    """
    col = (front_pos - 1) % num_cols
    row = (front_pos - 1) // num_cols
    mirrored_col = num_cols - 1 - col
    return row * num_cols + mirrored_col + 1


def write_image(doc: fitz.Document, xref: int, dest_stem: Path) -> bool:
    """
    Extract image by xref and write it to dest_stem with the correct extension.
    dest_stem should have no extension (e.g. Path('/out/0000_01')).
    Returns True on success.
    """
    try:
        img_info = doc.extract_image(xref)
    except Exception as e:
        print(f"  WARNING: extract_image xref={xref} failed: {e}", file=sys.stderr)
        return False

    ext = img_info.get("ext", "bin")
    img_bytes = img_info.get("image", b"")
    dest = dest_stem.with_suffix(f".{ext}")
    try:
        dest.write_bytes(img_bytes)
        return True
    except Exception as e:
        print(f"  WARNING: write failed for {dest}: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Extraction modes
# ---------------------------------------------------------------------------

def mode_default(doc: fitz.Document, out_dir: Path) -> int:
    """All images from all pages, named {page:04d}_{pos:02d}.ext"""
    count = 0
    for pno in range(doc.page_count):
        occs = sort_by_position(get_image_occurrences(doc.load_page(pno)))
        for pos, occ in enumerate(occs, start=1):
            if write_image(doc, occ["xref"], out_dir / f"{pno:04d}_{pos:02d}"):
                count += 1
    return count


def mode_1sided(doc: fitz.Document, out_dir: Path) -> int:
    """
    Even pages (0, 2, 4, …): extract all images as in default mode.
    Odd pages (1, 3, 5, …): extract each unique back image once.
    """
    count = 0

    # Even pages — same naming as default
    for pno in range(0, doc.page_count, 2):
        occs = sort_by_position(get_image_occurrences(doc.load_page(pno)))
        for pos, occ in enumerate(occs, start=1):
            if write_image(doc, occ["xref"], out_dir / f"{pno:04d}_{pos:02d}"):
                count += 1

    # Odd pages — unique backs only (deduplicated by xref)
    seen_xrefs: Set[int] = set()
    back_n = 1
    for pno in range(1, doc.page_count, 2):
        occs = sort_by_position(get_image_occurrences(doc.load_page(pno)))
        for occ in occs:
            xref = occ["xref"]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            if write_image(doc, xref, out_dir / f"back_{back_n:02d}"):
                count += 1
                back_n += 1

    return count


def mode_2sided(doc: fitz.Document, out_dir: Path, num_cols: int = 2) -> int:
    """
    Even pages = fronts, next odd page = backs.
    Rows align but columns mirror between front and back pages.
    Fronts: {even_page:04d}_{pos:02d}F.ext
    Backs:  {even_page:04d}_{pos:02d}B.ext  (column-swapped position on the back page)
    """
    count = 0

    for even_pno in range(0, doc.page_count, 2):
        odd_pno = even_pno + 1

        front_occs = sort_by_position(get_image_occurrences(doc.load_page(even_pno)))

        back_occs: List[Dict[str, Any]] = []
        if odd_pno < doc.page_count:
            back_occs = sort_by_position(get_image_occurrences(doc.load_page(odd_pno)))

        # Write fronts
        for front_pos, occ in enumerate(front_occs, start=1):
            if write_image(doc, occ["xref"], out_dir / f"{even_pno:04d}_{front_pos:02d}F"):
                count += 1

        # Write backs — look up column-swapped position on the back page
        for front_pos in range(1, len(front_occs) + 1):
            back_pos = swapped_col_pos(front_pos, num_cols)
            if 1 <= back_pos <= len(back_occs):
                xref = back_occs[back_pos - 1]["xref"]
                if write_image(doc, xref, out_dir / f"{even_pno:04d}_{front_pos:02d}B"):
                    count += 1

    return count


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract card images from a PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
MODES
  default  All pages, all images. Output: 0000_01.ext, 0000_02.ext, …
  1sided   Even pages (fronts) + unique backs from odd pages.
           Output: 0000_01.ext, …, back_01.ext, …
  2sided   Paired fronts and backs; columns mirror across page pairs.
           Output: 0000_01F.ext, 0000_01B.ext, …

EXAMPLES
  python DeckExtract.py cards.pdf
  python DeckExtract.py cards.pdf --mode 1sided --out ./cards
  python DeckExtract.py cards.pdf --mode 2sided --out ./cards --cols 2
""",
    )
    parser.add_argument("pdf", nargs="?", help="Path to the PDF file")
    parser.add_argument(
        "--mode",
        choices=["default", "1sided", "2sided"],
        default="default",
        help="Extraction mode (default: default)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory (default: ./output/<pdf_stem>/)",
    )
    parser.add_argument(
        "--cols",
        type=int,
        default=2,
        help="Columns per page used for 2sided column-swap (default: 2)",
    )

    args = parser.parse_args(argv)

    if not args.pdf:
        parser.error("pdf argument is required")

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    out_root = Path(args.out).expanduser().resolve() if args.out else None
    out_dir = make_output_dir(pdf_path, out_root)

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"ERROR: Failed to open PDF: {e}", file=sys.stderr)
        return 2

    print(f"PDF   : {pdf_path.name}  ({doc.page_count} pages)")
    print(f"Mode  : {args.mode}")
    print(f"Output: {out_dir}")

    if args.mode == "default":
        count = mode_default(doc, out_dir)
    elif args.mode == "1sided":
        count = mode_1sided(doc, out_dir)
    else:  # 2sided
        count = mode_2sided(doc, out_dir, num_cols=args.cols)

    print(f"Done  : {count} image(s) written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
