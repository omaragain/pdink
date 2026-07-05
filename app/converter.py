from __future__ import annotations

"""
Pdink conversion engine.

The user interface imports convert_file(...) from this module.
It always runs locally: MarkItDown for documents and local Tesseract OCR for
images or scanned PDF pages.
"""

import argparse
import io
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import fitz  # PyMuPDF
import pytesseract
from markitdown import MarkItDown
from PIL import Image


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
PDF_SUFFIX = ".pdf"
SUPPORTED_OUTPUT_FORMATS = {".md", ".txt"}


class ConversionError(RuntimeError):
    """Raised when a source file cannot be converted safely."""


@dataclass(frozen=True)
class ConversionResult:
    source_path: Path
    output_path: Path
    converter_used: str
    ocr_pages: int = 0


ProgressCallback = Callable[[str], None]


def desktop_folder() -> Path:
    """Return the actual Desktop folder, including redirected Desktop folders."""
    from PySide6.QtCore import QStandardPaths

    desktop = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DesktopLocation
    )
    return Path(desktop) if desktop else Path.home() / "Desktop"


def project_root() -> Path:
    """Return the Pdink project folder in development and packaged builds."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def normalize_languages(languages: str | Iterable[str]) -> list[str]:
    """Accept 'eng,deu,ara', 'eng+deu', or an iterable of language codes."""
    parts = (
        re.split(r"[,+\s]+", languages.strip())
        if isinstance(languages, str)
        else list(languages)
    )

    selected: list[str] = []
    for part in parts:
        code = str(part).strip()
        if code and code not in selected:
            selected.append(code)

    if not selected:
        raise ConversionError("Choose at least one OCR language.")

    return selected


def normalize_output_format(output_format: str) -> str:
    """Return either '.md' or '.txt'."""
    extension = output_format.strip().casefold()
    if not extension.startswith("."):
        extension = f".{extension}"

    if extension not in SUPPORTED_OUTPUT_FORMATS:
        raise ConversionError(
            "Unsupported output format. Choose Markdown (.md) or plain text (.txt)."
        )

    return extension


def find_tesseract_executable() -> Path:
    """
    Prefer Pdink's bundled future runtime. During development, use the locally
    installed Tesseract executable.
    """
    candidates = [
        project_root() / "runtime" / "tesseract" / "tesseract.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Tesseract-OCR"
        / "tesseract.exe",
    ]

    on_path = shutil.which("tesseract")
    if on_path:
        candidates.append(Path(on_path))

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise ConversionError(
        "Tesseract OCR was not found. Install it or include it in Pdink's runtime."
    )


def possible_tessdata_directories(tesseract_exe: Path) -> list[Path]:
    """
    Search runtime locations first. The MarkItDown directory is only a temporary
    development fallback and is not used by the final standalone installer.
    """
    directories = [
        project_root() / "runtime" / "tesseract" / "tessdata",
        project_root() / "language-packs",
        Path.home() / "MarkItDown" / "tessdata",
        tesseract_exe.parent / "tessdata",
    ]

    env_tessdata = os.environ.get("TESSDATA_PREFIX")
    if env_tessdata:
        directories.insert(0, Path(env_tessdata))

    unique: list[Path] = []
    for directory in directories:
        if directory not in unique:
            unique.append(directory)

    return unique


def find_tessdata_directory(languages: list[str], tesseract_exe: Path) -> Path:
    """Find one tessdata directory containing all selected language packs."""
    checked: list[str] = []

    for directory in possible_tessdata_directories(tesseract_exe):
        if not directory.is_dir():
            continue

        missing = [
            language
            for language in languages
            if not (directory / f"{language}.traineddata").is_file()
        ]

        if not missing:
            return directory

        checked.append(f"{directory} (missing: {', '.join(missing)})")

    detail = "\n".join(checked) or "No tessdata directory was found."
    raise ConversionError(
        "The selected OCR language packs are not installed together.\n\n"
        f"Selected: {', '.join(languages)}\n\n"
        f"Checked:\n{detail}"
    )


def configure_tesseract(languages: list[str]) -> tuple[str, str]:
    """
    Configure pytesseract and return (language expression, Tesseract config).

    TESSDATA_PREFIX avoids fragile command-line quoting on Windows paths.
    """
    executable = find_tesseract_executable()
    tessdata = find_tessdata_directory(languages, executable)

    pytesseract.pytesseract.tesseract_cmd = str(executable)
    os.environ["TESSDATA_PREFIX"] = str(tessdata)

    return "+".join(languages), "--psm 3"


def clean_markdown(text: str) -> str:
    """Normalize line breaks without damaging Markdown structure."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized = re.sub(r"\n{4,}", "\n\n\n", normalized)
    return normalized + "\n"


def markdown_to_plain_text(markdown: str) -> str:
    """
    Make a readable .txt export from generated Markdown.

    It intentionally preserves paragraphs, tables, and lists as text rather
    than trying to reformat content destructively.
    """
    text = clean_markdown(markdown)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+", "", text)
    text = re.sub(r"(?m)^[ \t]*>[ \t]?", "", text)
    text = re.sub(r"(?m)^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$", "", text)
    text = text.replace("```", "").replace("`", "")
    text = text.replace("**", "").replace("__", "").replace("~~", "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text + "\n"


def make_unique_output_path(
    output_directory: Path,
    source_path: Path,
    extension: str,
) -> Path:
    """
    Preserve the original filename stem and never overwrite a previous result:
    report.pdf -> report.md -> report (2).md.
    """
    output_directory.mkdir(parents=True, exist_ok=True)

    candidate = output_directory / f"{source_path.stem}{extension}"
    index = 2

    while candidate.exists():
        candidate = output_directory / f"{source_path.stem} ({index}){extension}"
        index += 1

    return candidate


def has_meaningful_pdf_text(text: str) -> bool:
    """Return True if a PDF page contains enough direct text to skip OCR."""
    return len(re.sub(r"\s+", "", text)) >= 40


def ocr_pil_image(image: Image.Image, languages: list[str]) -> str:
    """Run local Tesseract OCR on a Pillow image."""
    language_expression, config = configure_tesseract(languages)

    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")

    return pytesseract.image_to_string(
        image,
        lang=language_expression,
        config=config,
    ).strip()


def render_pdf_page(page: fitz.Page, scale: float = 2.0) -> Image.Image:
    """Render a PDF page at roughly 144 DPI for local OCR."""
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)

    with Image.open(io.BytesIO(pixmap.tobytes("png"))) as rendered:
        return rendered.convert("RGB")


def convert_scanned_or_mixed_pdf(
    source_path: Path,
    languages: list[str],
    progress: ProgressCallback | None = None,
) -> tuple[str, int]:
    """Extract text pages directly and OCR only scanned PDF pages."""
    try:
        document = fitz.open(source_path)
    except Exception as exc:
        raise ConversionError(f"Could not open PDF: {source_path.name}") from exc

    sections: list[str] = []
    ocr_pages = 0

    try:
        page_count = len(document)

        for index, page in enumerate(document, start=1):
            if progress:
                progress(f"Reading PDF page {index} of {page_count}: {source_path.name}")

            extracted = page.get_text("text").strip()

            if has_meaningful_pdf_text(extracted):
                page_content = extracted
            else:
                if progress:
                    progress(
                        f"Running OCR on page {index} of {page_count}: "
                        f"{source_path.name}"
                    )

                page_content = ocr_pil_image(render_pdf_page(page), languages)
                ocr_pages += 1

            if not page_content:
                page_content = "No readable text found on this page."

            sections.append(f"## Page {index}\n\n{page_content}")
    finally:
        document.close()

    markdown = f"# {source_path.stem}\n\n" + "\n\n---\n\n".join(sections)
    return clean_markdown(markdown), ocr_pages


def convert_pdf(
    source_path: Path,
    languages: list[str],
    progress: ProgressCallback | None = None,
) -> tuple[str, str, int]:
    """
    Use MarkItDown for text PDFs. If any page is scanned, use page-level
    extraction so scanned pages receive local OCR.
    """
    try:
        document = fitz.open(source_path)
        page_text = [page.get_text("text").strip() for page in document]
        document.close()
    except Exception as exc:
        raise ConversionError(f"Could not inspect PDF: {source_path.name}") from exc

    needs_ocr = any(not has_meaningful_pdf_text(text) for text in page_text)

    if not needs_ocr:
        if progress:
            progress(f"Converting PDF: {source_path.name}")

        try:
            converted = MarkItDown().convert(str(source_path)).text_content
            if converted and converted.strip():
                return clean_markdown(converted), "MarkItDown PDF", 0
        except Exception:
            # A page-level fallback is more useful than stopping here.
            pass

    markdown, ocr_pages = convert_scanned_or_mixed_pdf(
        source_path,
        languages,
        progress,
    )
    return markdown, "PyMuPDF + local Tesseract OCR", ocr_pages


def convert_image(
    source_path: Path,
    languages: list[str],
    progress: ProgressCallback | None = None,
) -> tuple[str, str, int]:
    """Convert an image using local Tesseract OCR."""
    if progress:
        progress(f"Running OCR: {source_path.name}")

    try:
        with Image.open(source_path) as image:
            text = ocr_pil_image(image.copy(), languages)
    except Exception as exc:
        raise ConversionError(f"Could not OCR image: {source_path.name}") from exc

    if not text:
        text = "No readable text found in this image."

    return clean_markdown(f"# {source_path.stem}\n\n{text}"), "Local Tesseract OCR", 1


def convert_document(
    source_path: Path,
    progress: ProgressCallback | None = None,
) -> tuple[str, str, int]:
    """Convert a standard document through MarkItDown."""
    if progress:
        progress(f"Converting document: {source_path.name}")

    try:
        converted = MarkItDown().convert(str(source_path)).text_content
    except Exception as exc:
        raise ConversionError(
            f"MarkItDown could not convert: {source_path.name}"
        ) from exc

    if not converted or not converted.strip():
        raise ConversionError(
            f"No readable content was produced for: {source_path.name}"
        )

    return clean_markdown(converted), "MarkItDown", 0


def convert_file(
    source_path: str | Path,
    output_directory: str | Path,
    languages: str | Iterable[str] = ("eng",),
    output_format: str = ".md",
    progress: ProgressCallback | None = None,
) -> ConversionResult:
    """
    Convert one local source file to Markdown (.md) or readable plain text (.txt).

    The original source file is never changed.
    """
    source = Path(source_path).expanduser().resolve()
    output = Path(output_directory).expanduser().resolve()
    selected_languages = normalize_languages(languages)
    extension = normalize_output_format(output_format)

    if not source.is_file():
        raise ConversionError(f"Input file does not exist: {source}")

    suffix = source.suffix.casefold()

    if suffix == PDF_SUFFIX:
        content, converter, ocr_pages = convert_pdf(
            source,
            selected_languages,
            progress,
        )
    elif suffix in IMAGE_SUFFIXES:
        content, converter, ocr_pages = convert_image(
            source,
            selected_languages,
            progress,
        )
    else:
        content, converter, ocr_pages = convert_document(source, progress)

    output_content = content if extension == ".md" else markdown_to_plain_text(content)
    output_path = make_unique_output_path(output, source, extension)
    output_path.write_text(output_content, encoding="utf-8")

    if progress:
        progress(f"Saved: {output_path.name}")

    return ConversionResult(
        source_path=source,
        output_path=output_path,
        converter_used=converter,
        ocr_pages=ocr_pages,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert one local file with Pdink."
    )
    parser.add_argument("source", help="Path to the source file")
    parser.add_argument(
        "--output",
        "-o",
        default=str(desktop_folder() / "Pdink Files"),
        help="Folder for the generated file",
    )
    parser.add_argument(
        "--languages",
        "-l",
        default="eng",
        help="OCR languages, for example eng,deu,ara",
    )
    parser.add_argument(
        "--format",
        "-f",
        default=".md",
        choices=sorted(SUPPORTED_OUTPUT_FORMATS),
        help="Output format: .md or .txt",
    )
    args = parser.parse_args()

    try:
        result = convert_file(
            source_path=args.source,
            output_directory=args.output,
            languages=args.languages,
            output_format=args.format,
            progress=print,
        )
    except ConversionError as exc:
        print(f"\nConversion failed:\n{exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\nUnexpected error:\n{exc}", file=sys.stderr)
        return 1

    print("\nConversion complete")
    print(f"Output: {result.output_path}")
    print(f"Method: {result.converter_used}")
    print(f"OCR pages: {result.ocr_pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
