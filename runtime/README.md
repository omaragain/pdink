# Generated runtime directory

This directory is intentionally not stored in Git because it contains the
Windows Tesseract runtime and a large collection of OCR language-data files.

For a release build:

1. Place the Windows Tesseract runtime under `runtime/tesseract/`.
2. Place language data under `runtime/tesseract/tessdata/`.
3. Run `installer/Download-All-Languages.ps1` to fetch the official
   `tessdata_fast` language packs.

The packaged Windows installer includes this directory, but the source
repository does not.
