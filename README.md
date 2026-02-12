# PDF Compressor (Offline) — macOS CLI

A simple offline command-line tool to compress PDF files on macOS using Ghostscript (preferred) with a safe fallback using pikepdf.
It supports compressing a single PDF or batch processing a folder, writes results to an output folder, and skips outputs that are not smaller than the original.

--------------------------------------------------------------------------------
FEATURES
--------------------------------------------------------------------------------
- Offline compression (no cloud uploads)
- Compress one file or all PDFs in a folder (batch)
- Output goes to a dedicated folder (no overwrite unless you use --overwrite)
- Ghostscript quality presets: --quality screen | ebook | printer | prepress
- Shows before/after sizes and percentage saved
- Skips a file if compressed output is not smaller
- Clear logging + basic error handling (corrupt PDF, permission issues, etc.)
- --dry-run mode (no files written)
- Optional --recursive folder scan

--------------------------------------------------------------------------------
REQUIREMENTS
--------------------------------------------------------------------------------
- macOS
- Python 3.10+
- (Recommended) Ghostscript installed via Homebrew for best compression

--------------------------------------------------------------------------------
INSTALLATION
--------------------------------------------------------------------------------
1) Create the project folder and place the files:
   - main.py
   - requirements.txt

2) Create and activate a virtual environment:
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -U pip

3) Install the Python dependency (fallback):
   pip install -r requirements.txt

4) (Recommended) Install Ghostscript via Homebrew:
   brew install ghostscript

   Verify:
   gs --version

Optional (not required): install qpdf
   brew install qpdf

Note: This tool currently uses pikepdf as the fallback. qpdf is not invoked by default.

--------------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------------
Run from the project directory:
   python main.py [options]

Compress a single PDF:
   python main.py --file "/path/in.pdf" --out "/path/output" --quality ebook

Compress all PDFs in a folder (batch):
   python main.py --folder "/path/pdfs" --out "/path/output" --quality screen

Recursive folder scan:
   python main.py --folder "/path/pdfs" --out "/path/output" --recursive --quality ebook

Dry run (no files written):
   python main.py --folder "/path/pdfs" --out "/path/output" --dry-run --recursive

Overwrite outputs if they already exist:
   python main.py --file "/path/in.pdf" --out "/path/output" --overwrite

--------------------------------------------------------------------------------
QUALITY PRESETS (GHOSTSCRIPT)
--------------------------------------------------------------------------------
The --quality option maps to Ghostscript’s -dPDFSETTINGS presets:

- screen   -> smallest size, lowest image quality (good for quick previews)
- ebook    -> balanced default for documents
- printer  -> higher quality, moderate compression
- prepress -> highest quality, least compression

Tip:
- For scanned PDFs, try screen or ebook.
- For slides with graphics, try ebook or printer.

--------------------------------------------------------------------------------
OUTPUT BEHAVIOR
--------------------------------------------------------------------------------
No overwrite by default:
- If the destination file already exists, the tool will skip it unless you use --overwrite.

Skip if not smaller:
- If compression produces a file that is not smaller than the original, the tool will not write the output and will report SKIP.

Batch mode preserves folder structure:
- When using --folder, the output path preserves the same relative subfolder structure under --out.

Example:
Input:
  /input/a.pdf
  /input/sub/b.pdf

Output:
  /output/a.pdf
  /output/sub/b.pdf

--------------------------------------------------------------------------------
EXAMPLE OUTPUT
--------------------------------------------------------------------------------
[OK] report.pdf -> report.pdf | ghostscript(ebook) | 12.30 MB -> 4.85 MB | saved: 7.45 MB (60.57%)
INFO: report.pdf: Compressed with Ghostscript.

[SKIP] scan.pdf -> scan.pdf | ghostscript(ebook) | 1.20 MB -> 1.25 MB | saved: 0 B (0.00%)
INFO: scan.pdf: Skipped: output not smaller (1.25 MB >= 1.20 MB). Compressed with Ghostscript.

[OK] slides.pdf -> slides.pdf | pikepdf(optimize) | 6.10 MB -> 5.80 MB | saved: 0.30 MB (4.92%)
INFO: slides.pdf: Optimized with pikepdf (structure/streams).

--------------------------------------------------------------------------------
HOW IT WORKS
--------------------------------------------------------------------------------
Preferred method: Ghostscript
- If gs is available, the tool uses Ghostscript to rewrite and compress the PDF:
  - PDF rewriting (pdfwrite)
  - font compression/subsetting
  - duplicate image detection
  - quality preset control via -dPDFSETTINGS

This is typically the most effective way to reduce file size, especially for image-heavy PDFs.

Fallback method: pikepdf (offline)
- If Ghostscript is not available or fails for a file, the tool falls back to pikepdf, which can:
  - optimize internal PDF structure
  - compress streams (when possible)
  - remove unused resources

Limitation:
- pikepdf usually does not aggressively downsample images the way Ghostscript does.
  For image-heavy PDFs, the size reduction may be smaller than Ghostscript.

--------------------------------------------------------------------------------
TROUBLESHOOTING
--------------------------------------------------------------------------------
Ghostscript (gs) not found
- Install it:
  brew install ghostscript

Permission denied when writing output
- Make sure you have write access to the output folder.
- Try an output directory under your home folder.

PDF is corrupted / fails to open
- The tool will report a failed/skip entry for that file.
- Try opening the PDF manually to confirm it is valid.

--------------------------------------------------------------------------------
NOTES / SAFETY
--------------------------------------------------------------------------------
- This tool is offline and does not transmit any files anywhere.
- Avoid PDFs with sensitive data if you plan to share the output files.
- For best results on scanned documents, use --quality screen or --quality ebook.

--------------------------------------------------------------------------------
ROADMAP (OPTIONAL IDEAS)
--------------------------------------------------------------------------------
- Add an installable command: pdfcompress ... (packaging + entrypoint)
- Add optional --max-dpi for more controlled image downsampling
- Add progress bar + richer summary reporting

--------------------------------------------------------------------------------
LICENSE
--------------------------------------------------------------------------------
Choose one (recommended for code): MIT or Apache-2.0.
(Add a LICENSE file to the repository.)

--------------------------------------------------------------------------------
CONTACT
--------------------------------------------------------------------------------
If you want improvements (e.g., Windows/Linux support, GUI wrapper, or tighter control over image compression), open an issue or extend the script.