#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

# Optional dependency for fallback
try:
    import pikepdf  # type: ignore
except Exception:
    pikepdf = None  # noqa: N816


QUALITY_MAP = {
    "screen": "/screen",
    "ebook": "/ebook",
    "printer": "/printer",
    "prepress": "/prepress",
}

LOG = logging.getLogger("pdfcompress")


@dataclass
class CompressResult:
    src: Path
    dst: Path
    method: str
    before_bytes: int
    after_bytes: int
    saved_bytes: int
    saved_pct: float
    skipped: bool
    message: str


def human_bytes(n: int) -> str:
    # Simple human-readable bytes formatter
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.2f} {u}" if u != "B" else f"{int(size)} {u}"
        size /= 1024
    return f"{n} B"


def find_pdfs_in_folder(folder: Path, recursive: bool) -> Iterable[Path]:
    if recursive:
        yield from folder.rglob("*.pdf")
        yield from folder.rglob("*.PDF")
    else:
        yield from folder.glob("*.pdf")
        yield from folder.glob("*.PDF")


def ensure_output_path(
    src: Path,
    input_root: Optional[Path],
    out_dir: Path,
) -> Path:
    """
    Preserve relative path when batch-processing a folder:
    out_dir / (relative path from input_root) / filename.pdf
    """
    if input_root is None:
        return out_dir / src.name

    try:
        rel = src.relative_to(input_root)
    except Exception:
        rel = src.name  # fallback
    return out_dir / rel


def run_ghostscript_compress(src: Path, tmp_out: Path, quality: str) -> Tuple[bool, str]:
    gs = shutil.which("gs")
    if not gs:
        return False, "Ghostscript (gs) not found."

    pdfsettings = QUALITY_MAP.get(quality)
    if not pdfsettings:
        return False, f"Unknown quality: {quality}"

    # Ghostscript command that often yields good compression
    cmd = [
        gs,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        f"-dPDFSETTINGS={pdfsettings}",
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        f"-sOutputFile={str(tmp_out)}",
        str(src),
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            msg = proc.stderr.strip() or proc.stdout.strip() or "Ghostscript failed."
            return False, msg
        return True, "Compressed with Ghostscript."
    except Exception as e:
        return False, f"Ghostscript execution error: {e}"


def run_pikepdf_optimize(src: Path, tmp_out: Path) -> Tuple[bool, str]:
    """
    Offline fallback:
    - pikepdf can rewrite/optimize structure and sometimes reduce size modestly
    - It usually won't aggressively downsample images (that’s why GS is preferred)
    """
    if pikepdf is None:
        return False, "pikepdf is not installed (fallback unavailable)."

    try:
        with pikepdf.open(str(src)) as pdf:
            # Basic optimizations: remove unused objects, compress streams where possible
            pdf.remove_unreferenced_resources()
            pdf.save(
                str(tmp_out),
                optimize_streams=True,
                compress_streams=True,
                linearize=False,
            )
        return True, "Optimized with pikepdf (structure/streams)."
    except Exception as e:
        return False, f"pikepdf failed: {e}"


def safe_write_output(
    tmp_out: Path,
    final_out: Path,
    overwrite: bool,
) -> Tuple[bool, str]:
    final_out.parent.mkdir(parents=True, exist_ok=True)

    if final_out.exists() and not overwrite:
        return False, f"Output exists (use --overwrite): {final_out}"

    try:
        shutil.move(str(tmp_out), str(final_out))
        return True, "Saved."
    except Exception as e:
        return False, f"Failed to save output: {e}"


def compress_one(
    src: Path,
    dst: Path,
    quality: str,
    overwrite: bool,
    dry_run: bool,
) -> CompressResult:
    before = src.stat().st_size
    method = "none"

    if dry_run:
        return CompressResult(
            src=src,
            dst=dst,
            method="dry-run",
            before_bytes=before,
            after_bytes=before,
            saved_bytes=0,
            saved_pct=0.0,
            skipped=True,
            message="Dry run: no file written.",
        )

    with tempfile.TemporaryDirectory(prefix="pdfcompress_") as td:
        tmp_out = Path(td) / (src.stem + ".compressed.pdf")

        # Prefer Ghostscript if available
        ok, msg = run_ghostscript_compress(src, tmp_out, quality)
        if ok:
            method = f"ghostscript({quality})"
        else:
            LOG.warning("Ghostscript unavailable/failed for %s: %s", src.name, msg)
            # Fallback: pikepdf optimize
            ok2, msg2 = run_pikepdf_optimize(src, tmp_out)
            if ok2:
                method = "pikepdf(optimize)"
                msg = msg2
            else:
                return CompressResult(
                    src=src,
                    dst=dst,
                    method="failed",
                    before_bytes=before,
                    after_bytes=before,
                    saved_bytes=0,
                    saved_pct=0.0,
                    skipped=True,
                    message=f"Compression failed. GS: {msg} | Fallback: {msg2}",
                )

        if not tmp_out.exists():
            return CompressResult(
                src=src,
                dst=dst,
                method="failed",
                before_bytes=before,
                after_bytes=before,
                saved_bytes=0,
                saved_pct=0.0,
                skipped=True,
                message="Compression produced no output file.",
            )

        after = tmp_out.stat().st_size

        # Skip if not smaller
        if after >= before:
            return CompressResult(
                src=src,
                dst=dst,
                method=method,
                before_bytes=before,
                after_bytes=after,
                saved_bytes=0,
                saved_pct=0.0,
                skipped=True,
                message=f"Skipped: output not smaller ({human_bytes(after)} >= {human_bytes(before)}). {msg}",
            )

        # Write final output
        ok_save, save_msg = safe_write_output(tmp_out, dst, overwrite=overwrite)
        if not ok_save:
            return CompressResult(
                src=src,
                dst=dst,
                method=method,
                before_bytes=before,
                after_bytes=after,
                saved_bytes=before - after,
                saved_pct=(before - after) / before * 100.0 if before else 0.0,
                skipped=True,
                message=save_msg,
            )

        saved = before - after
        pct = (saved / before * 100.0) if before else 0.0
        return CompressResult(
            src=src,
            dst=dst,
            method=method,
            before_bytes=before,
            after_bytes=after,
            saved_bytes=saved,
            saved_pct=pct,
            skipped=False,
            message=msg,
        )


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pdfcompress",
        description="Offline PDF compressor for macOS (Ghostscript preferred, pikepdf fallback).",
    )
    src_group = p.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--file", type=str, help="Path to a single PDF file")
    src_group.add_argument("--folder", type=str, help="Path to a folder containing PDFs")

    p.add_argument("--out", type=str, required=True, help="Output folder")
    p.add_argument("--quality", type=str, choices=list(QUALITY_MAP.keys()), default="ebook",
                   help="Compression quality (Ghostscript): screen|ebook|printer|prepress")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    p.add_argument("--recursive", action="store_true", help="Recursively scan subfolders (only with --folder)")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without writing files")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.file:
        src = Path(args.file).expanduser().resolve()
        if not src.exists():
            LOG.error("File not found: %s", src)
            return 2
        if src.suffix.lower() != ".pdf":
            LOG.error("Not a PDF: %s", src)
            return 2

        dst = ensure_output_path(src, None, out_dir)
        res = compress_one(src, dst, args.quality, args.overwrite, args.dry_run)
        print_result(res)
        return 0 if (not res.skipped) else 1

    # Folder mode
    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        LOG.error("Folder not found or not a directory: %s", folder)
        return 2

    pdfs = sorted(find_pdfs_in_folder(folder, args.recursive))
    if not pdfs:
        LOG.warning("No PDF files found in: %s", folder)
        return 0

    total_before = 0
    total_after = 0
    saved_files = 0
    skipped_files = 0
    failed_files = 0

    for src in pdfs:
        dst = ensure_output_path(src, folder, out_dir)
        res = compress_one(src, dst, args.quality, args.overwrite, args.dry_run)
        print_result(res)

        total_before += res.before_bytes
        if not res.skipped and not args.dry_run:
            total_after += res.after_bytes
            saved_files += 1
        else:
            # For dry-run, keep totals simple (no writes)
            if res.method == "failed":
                failed_files += 1
            else:
                skipped_files += 1

    if args.dry_run:
        LOG.info("Dry run complete. Files scanned: %d", len(pdfs))
        return 0

    # Summary
    if saved_files > 0:
        saved_bytes = (total_before - total_after) if total_after > 0 else 0
        pct = (saved_bytes / total_before * 100.0) if total_before else 0.0
        LOG.info(
            "Summary: saved=%d, skipped=%d, failed=%d | total: %s -> %s (saved %s, %.2f%%)",
            saved_files,
            skipped_files,
            failed_files,
            human_bytes(total_before),
            human_bytes(total_after),
            human_bytes(saved_bytes),
            pct,
        )
    else:
        LOG.info("Summary: no files were compressed (all skipped/failed).")

    return 0


def print_result(res: CompressResult) -> None:
    status = "SKIP" if res.skipped else "OK"
    print(
        f"[{status}] {res.src.name} -> {res.dst.name} | "
        f"{res.method} | {human_bytes(res.before_bytes)} -> {human_bytes(res.after_bytes)} | "
        f"saved: {human_bytes(res.saved_bytes)} ({res.saved_pct:.2f}%)"
    )
    if res.message:
        LOG.info("%s: %s", res.src.name, res.message)


if __name__ == "__main__":
    raise SystemExit(main())
