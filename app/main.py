from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from converter import ConversionError, convert_file


APP_NAME = "Pdink"
GITHUB_PROJECT_URL = "https://github.com/omaragain/pdink"
WINDOWS_APP_USER_MODEL_ID = "OmarMannaa.Pdink"
MAX_OCR_LANGUAGES_PER_CONVERSION = 3

# Friendly display names for commonly available Tesseract language packs.
# Any installed pack that is not listed here remains usable and is shown by code.
LANGUAGE_NAMES = {
    "afr": "Afrikaans", "amh": "Amharic", "ara": "Arabic",
    "asm": "Assamese", "aze": "Azerbaijani", "aze_cyrl": "Azerbaijani (Cyrillic)",
    "bel": "Belarusian", "ben": "Bengali", "bod": "Tibetan",
    "bos": "Bosnian", "bre": "Breton", "bul": "Bulgarian",
    "cat": "Catalan", "ceb": "Cebuano", "ces": "Czech",
    "chi_sim": "Chinese Simplified", "chi_tra": "Chinese Traditional",
    "chr": "Cherokee", "cos": "Corsican", "cym": "Welsh",
    "dan": "Danish", "deu": "German", "deu_latf": "German Fraktur", "div": "Dhivehi",
    "dzo": "Dzongkha", "ell": "Greek", "eng": "English",
    "enm": "English, Middle", "epo": "Esperanto", "est": "Estonian",
    "eus": "Basque", "fas": "Persian", "fao": "Faroese", "fil": "Filipino",
    "fin": "Finnish", "fra": "French", "frk": "Frankish",
    "frm": "French, Middle", "fry": "Frisian", "gla": "Scottish Gaelic",
    "gle": "Irish", "glg": "Galician", "grc": "Greek, Ancient",
    "guj": "Gujarati", "hat": "Haitian Creole", "heb": "Hebrew",
    "hin": "Hindi", "hrv": "Croatian", "hun": "Hungarian",
    "hye": "Armenian", "iku": "Inuktitut", "ind": "Indonesian",
    "isl": "Icelandic", "ita": "Italian", "ita_old": "Italian, Old",
    "jav": "Javanese", "jpn": "Japanese", "kan": "Kannada",
    "kat": "Georgian", "kat_old": "Georgian, Old", "kaz": "Kazakh",
    "khm": "Khmer", "kir": "Kyrgyz", "kmr": "Kurdish (Kurmanji)", "kor": "Korean", "kor_vert": "Korean (Vertical)",
    "kur": "Kurdish", "lao": "Lao", "lat": "Latin",
    "lav": "Latvian", "lit": "Lithuanian", "ltz": "Luxembourgish",
    "mal": "Malayalam", "mar": "Marathi", "mkd": "Macedonian",
    "mlt": "Maltese", "mon": "Mongolian", "mri": "Maori",
    "msa": "Malay", "mya": "Myanmar", "nep": "Nepali",
    "nld": "Dutch", "nor": "Norwegian", "oci": "Occitan",
    "ori": "Odia", "pan": "Punjabi", "pol": "Polish",
    "por": "Portuguese", "pus": "Pashto", "que": "Quechua",
    "ron": "Romanian", "rus": "Russian", "san": "Sanskrit",
    "sin": "Sinhala", "slk": "Slovak", "slv": "Slovenian",
    "snd": "Sindhi", "spa": "Spanish", "spa_old": "Spanish, Old",
    "sqi": "Albanian", "srp": "Serbian", "srp_latn": "Serbian (Latin)",
    "sun": "Sundanese", "swa": "Swahili", "swe": "Swedish",
    "syr": "Syriac", "tam": "Tamil", "tat": "Tatar",
    "tel": "Telugu", "tgk": "Tajik", "tha": "Thai",
    "tir": "Tigrinya", "ton": "Tonga", "tur": "Turkish",
    "uig": "Uyghur", "ukr": "Ukrainian", "urd": "Urdu",
    "uzb": "Uzbek", "uzb_cyrl": "Uzbek (Cyrillic)",
    "vie": "Vietnamese", "yid": "Yiddish", "yor": "Yoruba",
}


def desktop_folder() -> Path:
    desktop = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DesktopLocation
    )
    return Path(desktop) if desktop else Path.home() / "Desktop"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_icon_path() -> Path:
    """Return Pdink's .ico file in development and packaged builds."""
    return app_root() / "assets" / "Pdink.ico"


def installed_language_codes() -> list[str]:
    """
    The final installer will place selected .traineddata files in the runtime
    folder. The MarkItDown path is only a development fallback.
    """
    folders = [
        app_root() / "runtime" / "tesseract" / "tessdata",
        app_root() / "language-packs",
        Path.home() / "MarkItDown" / "tessdata",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Tesseract-OCR"
        / "tessdata",
    ]

    codes: set[str] = set()
    for folder in folders:
        if folder.is_dir():
            codes.update(
                path.stem
                for path in folder.glob("*.traineddata")
                if path.stem not in {"osd", "equ"}
            )

    if not codes:
        codes = {"eng", "deu", "ara"}

    return sorted(
        codes,
        key=lambda code: LANGUAGE_NAMES.get(code, code).casefold(),
    )


def language_label(code: str) -> str:
    return f"{LANGUAGE_NAMES.get(code, code.upper())} ({code})"


class ConversionWorker(QThread):
    """Runs file conversions outside the GUI thread."""

    progress = Signal(str)
    file_succeeded = Signal(str, str)
    file_failed = Signal(str, str)
    batch_finished = Signal(int, int)

    def __init__(
        self,
        files: list[Path],
        output_directory: Path,
        languages: list[str],
        output_format: str,
        parent=None,
    ):
        super().__init__(parent)
        self.files = files
        self.output_directory = output_directory
        self.languages = languages
        self.output_format = output_format

    def run(self) -> None:
        successful = 0
        failed = 0
        total = len(self.files)

        for index, source in enumerate(self.files, start=1):
            self.progress.emit(f"Converting {index} of {total}: {source.name}")

            try:
                result = convert_file(
                    source_path=source,
                    output_directory=self.output_directory,
                    languages=self.languages,
                    output_format=self.output_format,
                    progress=lambda message, i=index, n=total: self.progress.emit(
                        f"{i} of {n} — {message}"
                    ),
                )
            except ConversionError as exc:
                failed += 1
                self.file_failed.emit(str(source), str(exc))
            except Exception as exc:
                failed += 1
                self.file_failed.emit(str(source), f"Unexpected error: {exc}")
            else:
                successful += 1
                self.file_succeeded.emit(str(source), str(result.output_path))

        self.batch_finished.emit(successful, failed)


class AppDropSurface(QWidget):
    """Makes the whole visible Pdink window a valid drop target."""

    def __init__(self, drag_started, drag_finished, files_dropped):
        super().__init__()
        self.drag_started = drag_started
        self.drag_finished = drag_finished
        self.files_dropped = files_dropped
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.drag_started()
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drag_finished()
        event.accept()

    def dropEvent(self, event):
        files = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if Path(url.toLocalFile()).is_file()
        ]
        self.drag_finished()

        if files:
            self.files_dropped(files, dropped=True)

        event.acceptProposedAction()


class GlobalDropOverlay(QFrame):
    """A short visual confirmation while files hover over Pdink."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("globalDropOverlay")
        self.setAcceptDrops(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        title = QLabel("Drop files anywhere")
        title.setObjectName("globalDropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("They will be added to Input")
        subtitle.setObjectName("globalDropSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(subtitle)


class LanguageDialog(QDialog):
    """Searchable OCR-language selector with a strict maximum of three choices."""

    def __init__(self, available_codes: list[str], selected_codes: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Languages")
        self.setMinimumSize(460, 500)
        self.resize(510, 560)

        self.checkboxes: dict[str, QCheckBox] = {}
        self.limit_reached = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(11)

        title = QLabel("Choose languages")
        title.setObjectName("dialogTitle")

        description = QLabel(
            "Choose up to 3 languages for each conversion. "
            "Keeping the selection small improves OCR speed and accuracy."
        )
        description.setObjectName("dialogNote")
        description.setWordWrap(True)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search languages")
        self.search_box.textChanged.connect(self.filter_languages)

        actions = QHBoxLayout()
        select_visible = QPushButton("Select visible")
        clear_selection = QPushButton("Clear selection")
        select_visible.clicked.connect(self.select_visible)
        clear_selection.clicked.connect(self.clear_selection)
        actions.addWidget(select_visible)
        actions.addWidget(clear_selection)
        actions.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("languageScroll")
        scroll.setWidgetResizable(True)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_layout.setSpacing(6)

        selected_set = set(
            selected_codes[:MAX_OCR_LANGUAGES_PER_CONVERSION]
        )

        # Keep checked languages at the top. Both groups preserve the normal
        # alphabetical order supplied by installed_language_codes().
        ordered_codes = (
            [code for code in available_codes if code in selected_set]
            + [code for code in available_codes if code not in selected_set]
        )

        for code in ordered_codes:
            checkbox = QCheckBox(language_label(code))
            checkbox.setChecked(code in selected_set)
            checkbox.toggled.connect(
                lambda checked, language_code=code: self.handle_toggle(
                    language_code,
                    checked,
                )
            )
            self.checkboxes[code] = checkbox
            body_layout.addWidget(checkbox)

        body_layout.addStretch()
        scroll.setWidget(body)

        self.selection_summary = QLabel()
        self.selection_summary.setObjectName("selectionSummary")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        buttons.rejected.connect(self.reject)
        buttons.button(
            QDialogButtonBox.StandardButton.Apply
        ).clicked.connect(self.apply_selection)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self.search_box)
        layout.addLayout(actions)
        layout.addWidget(scroll)
        layout.addWidget(self.selection_summary)
        layout.addWidget(buttons)

        self.update_summary()
        self.setStyleSheet(
            """
            QDialog {
                background: #171c24;
                color: #f4f7fb;
                font-family: "Segoe UI";
                font-size: 13px;
            }
            QLabel { color: #f4f7fb; }
            #dialogTitle { font-size: 20px; font-weight: 700; }
            #dialogNote, #selectionSummary { color: #aab5c4; }
            QLineEdit {
                background: #222a35;
                border: 1px solid #3d4a5b;
                border-radius: 7px;
                color: #f4f7fb;
                padding: 9px 10px;
            }
            QScrollArea#languageScroll {
                background: #202734;
                border: 1px solid #354153;
                border-radius: 8px;
            }
            QCheckBox {
                color: #edf3fd;
                spacing: 8px;
                padding: 4px 2px;
            }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QPushButton {
                background: #2a3340;
                border: 1px solid #455365;
                border-radius: 7px;
                color: #f4f7fb;
                font-weight: 600;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background: #344153;
                border-color: #63758d;
            }
            """
        )

    def filter_languages(self, text: str) -> None:
        query = text.casefold().strip()
        for code, checkbox in self.checkboxes.items():
            checkbox.setVisible(
                not query or query in language_label(code).casefold()
            )

    def handle_toggle(self, code: str, checked: bool) -> None:
        if (
            checked
            and len(self.selected_codes()) > MAX_OCR_LANGUAGES_PER_CONVERSION
        ):
            checkbox = self.checkboxes[code]
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)
            self.limit_reached = True
        elif not checked:
            self.limit_reached = False
        else:
            self.limit_reached = False

        self.update_summary()

    def select_visible(self) -> None:
        self.limit_reached = False

        for checkbox in self.checkboxes.values():
            if (
                checkbox.isVisible()
                and not checkbox.isChecked()
                and len(self.selected_codes()) < MAX_OCR_LANGUAGES_PER_CONVERSION
            ):
                checkbox.setChecked(True)

        if any(
            checkbox.isVisible() and not checkbox.isChecked()
            for checkbox in self.checkboxes.values()
        ) and len(self.selected_codes()) >= MAX_OCR_LANGUAGES_PER_CONVERSION:
            self.limit_reached = True

        self.update_summary()

    def clear_selection(self) -> None:
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(False)
        self.limit_reached = False
        self.update_summary()

    def selected_codes(self) -> list[str]:
        return [
            code
            for code, checkbox in self.checkboxes.items()
            if checkbox.isChecked()
        ]

    def update_summary(self) -> None:
        count = len(self.selected_codes())

        if self.limit_reached:
            self.selection_summary.setText(
                "Maximum reached: choose no more than 3 languages per conversion."
            )
            self.selection_summary.setStyleSheet("color: #f7be6a;")
            return

        self.selection_summary.setStyleSheet("")
        self.selection_summary.setText(
            "No language selected. Choose 1–3 languages."
            if count == 0
            else f"{count} of {MAX_OCR_LANGUAGES_PER_CONVERSION} languages selected."
        )

    def apply_selection(self) -> None:
        selected = self.selected_codes()

        if not selected:
            QMessageBox.warning(
                self,
                "Languages",
                "Select at least one language.",
            )
            return

        if len(selected) > MAX_OCR_LANGUAGES_PER_CONVERSION:
            # Defensive guard: the UI prevents this, but keep the rule intact.
            self.limit_reached = True
            self.update_summary()
            return

        self.accept()


class DropFileBox(QFrame):
    """One surface for drag/drop, click-to-add, and the selected file queue."""

    def __init__(self, files_added, choose_files, drag_started, drag_finished):
        super().__init__()
        self.files_added = files_added
        self.choose_files = choose_files
        self.drag_started = drag_started
        self.drag_finished = drag_finished

        self.setAcceptDrops(True)
        self.setObjectName("dropFileBox")
        self.setMinimumHeight(150)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        self.empty_state = QWidget()
        self.empty_state.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )

        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(5)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Drop files here")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("or click anywhere in this area to choose files")
        subtitle.setObjectName("dropSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_layout.addWidget(title)
        empty_layout.addWidget(subtitle)

        self.file_list = QListWidget()
        self.file_list.setObjectName("fileList")
        self.file_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.file_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.file_list.hide()

        layout.addWidget(self.empty_state)
        layout.addWidget(self.file_list)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self.file_list.isVisible()
        ):
            self.choose_files()
            event.accept()
            return
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.drag_started()
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drag_finished()
        event.accept()

    def dropEvent(self, event):
        files = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if Path(url.toLocalFile()).is_file()
        ]
        self.drag_finished()

        if files:
            self.files_added(files, dropped=True)

        event.acceptProposedAction()

    def add_file(self, path: Path) -> None:
        item = QListWidgetItem(path.name)
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setToolTip(str(path))
        self.file_list.addItem(item)
        self.refresh_state()

    def remove_path(self, path: Path) -> None:
        resolved = str(path.resolve())

        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == resolved:
                self.file_list.takeItem(index)
                break

        self.refresh_state()

    def clear_all(self) -> None:
        self.file_list.clear()
        self.refresh_state()

    def selected_rows(self) -> list[int]:
        return sorted(
            {self.file_list.row(item) for item in self.file_list.selectedItems()},
            reverse=True,
        )

    def remove_rows(self, rows: list[int]) -> None:
        for row in rows:
            self.file_list.takeItem(row)
        self.refresh_state()

    def refresh_state(self) -> None:
        has_files = self.file_list.count() > 0
        self.empty_state.setVisible(not has_files)
        self.file_list.setVisible(has_files)
        self.setCursor(
            Qt.CursorShape.ArrowCursor
            if has_files
            else Qt.CursorShape.PointingHandCursor
        )


class PdinkWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QSettings("Pdink", "Pdink")
        self.selected_files: list[Path] = []
        self.available_languages = installed_language_codes()
        self.selected_languages = self.load_selected_languages()
        self.output_directory = self.load_output_directory()
        self.last_input_directory = self.load_last_input_directory()
        self.output_format = self.load_output_format()
        self.worker: ConversionWorker | None = None
        self.conversion_errors: list[tuple[str, str]] = []
        self._pulse_id = 0

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(600, 500)
        self.resize(900, 700)

        self.build_ui()
        self.apply_style()
        self.refresh_output_path()
        self.refresh_language_summary()
        self.refresh_actions()

    def load_selected_languages(self) -> list[str]:
        saved = self.settings.value("ocr_languages", [])
        if isinstance(saved, str):
            saved = [saved]

        available = set(self.available_languages)
        selected = [code for code in saved if code in available]
        if selected:
            return selected[:MAX_OCR_LANGUAGES_PER_CONVERSION]

        defaults = [code for code in ("eng", "deu", "ara") if code in available]
        return (defaults or self.available_languages[:1])[:MAX_OCR_LANGUAGES_PER_CONVERSION]

    def load_output_directory(self) -> Path:
        saved = self.settings.value("output_directory", "", type=str)
        return Path(saved) if saved else desktop_folder() / "Pdink Files"

    def load_last_input_directory(self) -> Path:
        saved = self.settings.value("last_input_directory", "", type=str)
        directory = Path(saved) if saved else Path.home()
        return directory if directory.is_dir() else Path.home()

    def load_output_format(self) -> str:
        saved = self.settings.value("output_format", ".md", type=str).casefold()
        return saved if saved in {".md", ".txt"} else ".md"

    def build_ui(self) -> None:
        self.central = AppDropSurface(
            self.begin_global_drop,
            self.end_global_drop,
            self.add_files,
        )
        self.central.setObjectName("central")
        self.setCentralWidget(self.central)

        outer = QVBoxLayout(self.central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("mainScroll")
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        outer.addWidget(self.scroll_area)

        page = QWidget()
        page.setObjectName("page")
        page.setMinimumHeight(0)
        self.scroll_area.setWidget(page)

        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(16, 12, 16, 10)
        main_layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)

        self.github_icon_button = QPushButton()
        self.github_icon_button.setObjectName("headerIconButton")
        self.github_icon_button.setToolTip("Open Pdink on GitHub")
        self.github_icon_button.setAccessibleName("Open Pdink on GitHub")
        self.github_icon_button.setFixedSize(38, 38)

        icon_path = bundled_icon_path()
        if icon_path.is_file():
            self.github_icon_button.setIcon(QIcon(str(icon_path)))
            self.github_icon_button.setIconSize(QSize(30, 30))

        self.github_icon_button.clicked.connect(self.open_github_project)

        title = QLabel("Pdink")
        title.setObjectName("appTitle")

        subtitle = QLabel("Document to Markdown converter")
        subtitle.setObjectName("appSubtitle")

        header.addWidget(self.github_icon_button)
        header.addWidget(title)
        header.addWidget(subtitle)
        header.addStretch()
        main_layout.addLayout(header)

        # INPUT: primary working area, with stretch to fill free vertical space.
        input_card = QFrame()
        input_card.setObjectName("sectionCard")
        input_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(14, 12, 14, 12)
        input_layout.setSpacing(8)

        input_heading = QHBoxLayout()
        input_title = QLabel("Input")
        input_title.setObjectName("sectionTitle")

        self.file_count_label = QLabel("0 files")
        self.file_count_label.setObjectName("countLabel")

        input_heading.addWidget(input_title)
        input_heading.addStretch()
        input_heading.addWidget(self.file_count_label)
        input_layout.addLayout(input_heading)

        self.drop_box = DropFileBox(
            self.add_files,
            self.choose_files,
            self.begin_global_drop,
            self.end_global_drop,
        )
        input_layout.addWidget(self.drop_box, 1)

        file_actions = QHBoxLayout()
        file_actions.setSpacing(8)

        self.add_files_button = QPushButton("Add Files")
        self.add_files_button.setObjectName("accentSecondaryButton")
        self.add_files_button.clicked.connect(self.choose_files)

        self.remove_selected_button = QPushButton("Remove Selected")
        self.remove_selected_button.clicked.connect(self.remove_selected)

        self.clear_files_button = QPushButton("Clear Files")
        self.clear_files_button.clicked.connect(self.clear_files)

        file_actions.addWidget(self.add_files_button)
        file_actions.addWidget(self.remove_selected_button)
        file_actions.addWidget(self.clear_files_button)
        file_actions.addStretch()
        input_layout.addLayout(file_actions)

        language_strip = QFrame()
        language_strip.setObjectName("languageStrip")
        language_layout = QHBoxLayout(language_strip)
        language_layout.setContentsMargins(10, 8, 10, 8)
        language_layout.setSpacing(8)

        language_title = QLabel("Languages")
        language_title.setObjectName("stripLabel")

        self.language_summary_label = QLabel()
        self.language_summary_label.setObjectName("languageSummary")

        self.change_languages_button = QPushButton("Change")
        self.change_languages_button.setObjectName("compactButton")
        self.change_languages_button.clicked.connect(self.choose_languages)

        language_layout.addWidget(language_title)
        language_layout.addWidget(self.language_summary_label)
        language_layout.addWidget(self.change_languages_button)
        language_layout.addStretch()

        input_layout.addWidget(language_strip)

        # OUTPUT: compact controls, always visible without consuming the Input area.
        output_card = QFrame()
        output_card.setObjectName("sectionCard")
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(14, 11, 14, 11)
        output_layout.setSpacing(7)

        output_title = QLabel("Output")
        output_title.setObjectName("sectionTitle")
        output_layout.addWidget(output_title)

        control_row = QHBoxLayout()
        control_row.setSpacing(8)

        self.convert_button = QPushButton("Start Conversion")
        self.convert_button.setObjectName("convertButton")
        self.convert_button.clicked.connect(self.start_conversion)

        self.open_folder_button = QPushButton("Open Output Folder")
        self.open_folder_button.clicked.connect(self.open_output_folder)

        format_label = QLabel("Format")
        format_label.setObjectName("stripLabel")

        self.output_format_combo = QComboBox()
        self.output_format_combo.setObjectName("outputFormatCombo")
        self.output_format_combo.setMinimumWidth(145)
        self.output_format_combo.addItem("Markdown (.md)", ".md")
        self.output_format_combo.addItem("Plain text (.txt)", ".txt")

        format_index = self.output_format_combo.findData(self.output_format)
        self.output_format_combo.setCurrentIndex(
            format_index if format_index >= 0 else 0
        )
        self.output_format_combo.currentIndexChanged.connect(
            self.save_output_format
        )

        control_row.addWidget(self.convert_button)
        control_row.addWidget(self.open_folder_button)
        control_row.addStretch(1)
        control_row.addWidget(format_label)
        control_row.addWidget(self.output_format_combo)
        output_layout.addLayout(control_row)

        save_row = QHBoxLayout()
        save_row.setSpacing(8)

        save_to = QLabel("Save to")
        save_to.setObjectName("stripLabel")

        self.output_path_button = QPushButton()
        self.output_path_button.setObjectName("outputPathButton")
        self.output_path_button.setToolTip("Click to change the output folder")
        self.output_path_button.clicked.connect(self.choose_output_folder)

        save_row.addWidget(save_to)
        save_row.addWidget(self.output_path_button, 1)
        output_layout.addLayout(save_row)

        # This label serves as the normal status line and the compact green
        # success confirmation after a completed conversion.
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(False)
        self.status_label.setMaximumHeight(26)
        self.status_label.setToolTip("")
        output_layout.addWidget(self.status_label)

        main_layout.addWidget(input_card, 1)
        main_layout.addWidget(output_card, 0)

        credits_label = QLabel(
            'Pdink © 2026 · '
            '<a href="https://github.com/omaragain" '
            'style="color:#83adff; text-decoration:none;">Omar Mannaa</a>'
            ' · All rights reserved.'
        )
        credits_label.setObjectName("creditsLabel")
        credits_label.setTextFormat(Qt.TextFormat.RichText)
        credits_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        credits_label.setOpenExternalLinks(True)
        credits_label.setWordWrap(False)
        credits_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credits_label.setMaximumHeight(18)
        main_layout.addWidget(credits_label)

        self.drop_overlay = GlobalDropOverlay(self.central)
        self.drop_overlay.hide()

    def apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#central, QScrollArea#mainScroll,
            QScrollArea#mainScroll > QWidget > QWidget {
                background: #14181f;
            }

            QWidget#central, QWidget#page {
                color: #f4f7fb;
                font-family: "Segoe UI";
                font-size: 13px;
            }

            QLabel { color: #f4f7fb; }

            #headerIconButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 9px;
                padding: 2px;
            }

            #headerIconButton:hover {
                background: #263446;
                border-color: #40556f;
            }

            #headerIconButton:pressed {
                background: #1d2938;
            }

            #appTitle {
                color: #ffffff;
                font-size: 27px;
                font-weight: 700;
            }

            #appSubtitle {
                color: #9faabd;
                font-size: 13px;
                padding-top: 5px;
            }

            #sectionCard {
                background: #1a2029;
                border: 1px solid #2e3846;
                border-radius: 12px;
            }

            #sectionTitle {
                color: #ffffff;
                font-size: 17px;
                font-weight: 700;
            }

            #countLabel {
                color: #a8b4c5;
                background: #222b38;
                border-radius: 9px;
                padding: 3px 8px;
            }

            #stripLabel {
                color: #d7deea;
                font-weight: 600;
            }

            #dropFileBox {
                background: #202734;
                border: 2px dashed #5b8ff9;
                border-radius: 12px;
            }

            #dropFileBox[dragActive="true"] {
                background: #24384e;
                border: 2px solid #83adff;
            }

            #dropFileBox[dropSuccess="true"] {
                background: #1f3b39;
                border: 2px solid #56c89d;
            }

            #dropTitle {
                color: #ffffff;
                font-size: 22px;
                font-weight: 700;
            }

            #dropSubtitle {
                color: #aeb8c8;
                font-size: 13px;
            }

            #fileList {
                background: transparent;
                color: #edf3fd;
                border: none;
                outline: none;
            }

            #fileList::item {
                background: #273243;
                border: 1px solid #37455a;
                border-radius: 7px;
                margin: 2px 0;
                padding: 8px 10px;
            }

            #fileList::item:selected {
                background: #3e63a1;
                border: 1px solid #6396ff;
                color: white;
            }

            #languageStrip {
                background: #202734;
                border: 1px solid #354153;
                border-radius: 8px;
            }

            #languageSummary {
                color: #aeb8c8;
                padding-left: 4px;
            }

            QPushButton {
                background: #2a3340;
                border: 1px solid #455365;
                border-radius: 7px;
                color: #f4f7fb;
                font-weight: 600;
                padding: 8px 13px;
            }

            QPushButton:hover {
                background: #344153;
                border-color: #63758d;
            }

            QPushButton:disabled {
                background: #222933;
                border-color: #323b49;
                color: #7c8797;
            }

            #compactButton {
                padding: 6px 11px;
            }

            #accentSecondaryButton {
                background: #304d7d;
                border-color: #4d7bd0;
            }

            #accentSecondaryButton:hover {
                background: #39609c;
            }

            #convertButton {
                background: #4d8df7;
                border-color: #4d8df7;
                color: white;
                font-weight: 700;
            }

            #convertButton:hover {
                background: #397ae8;
                border-color: #397ae8;
            }

            #outputPathButton {
                background: #202734;
                border: 1px solid #354153;
                border-radius: 7px;
                color: #aeb8c8;
                padding: 9px 10px;
                text-align: left;
            }

            #outputPathButton:hover {
                background: #273243;
                border-color: #5274a8;
                color: #eef3fb;
            }

            #statusLabel {
                color: #9fadbf;
                min-height: 20px;
                padding-top: 1px;
            }

            #statusLabel[success="true"] {
                background: #173d33;
                border: 1px solid #3ea77f;
                border-radius: 6px;
                color: #d9f7e8;
                font-weight: 600;
                padding: 4px 8px;
            }

            #creditsLabel {
                color: #7f8da2;
                font-size: 11px;
                padding-top: 0px;
            }

            #globalDropOverlay {
                background: rgba(20, 33, 51, 235);
                border: 3px dashed #82abff;
                border-radius: 14px;
            }

            #globalDropTitle {
                color: #ffffff;
                font-size: 26px;
                font-weight: 700;
            }

            #globalDropSubtitle {
                color: #c2d2ec;
                font-size: 15px;
            }

            QComboBox#outputFormatCombo {
                background: #202734;
                border: 1px solid #354153;
                border-radius: 7px;
                color: #e8edf6;
                padding: 6px 9px;
            }

            QComboBox#outputFormatCombo:hover {
                border-color: #5274a8;
            }

            QComboBox#outputFormatCombo::drop-down {
                border: none;
                width: 26px;
            }

            QComboBox#outputFormatCombo QAbstractItemView {
                background: #202734;
                border: 1px solid #455365;
                color: #edf3fd;
                selection-background-color: #3e63a1;
            }

            QScrollBar:vertical {
                background: #14181f;
                width: 10px;
                margin: 2px;
            }

            QScrollBar::handle:vertical {
                background: #3b4758;
                border-radius: 5px;
                min-height: 26px;
            }

            QScrollBar::handle:vertical:hover {
                background: #526176;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "drop_overlay"):
            self.drop_overlay.setGeometry(self.central.rect())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "drop_overlay"):
            self.drop_overlay.setGeometry(self.central.rect())

    @staticmethod
    def restyle(widget, property_name: str, value: str) -> None:
        widget.setProperty(property_name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def begin_global_drop(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.restyle(self.drop_box, "dragActive", "true")
        self.drop_overlay.setGeometry(self.central.rect())
        self.drop_overlay.show()
        self.drop_overlay.raise_()

    def end_global_drop(self) -> None:
        self.restyle(self.drop_box, "dragActive", "false")
        self.drop_overlay.hide()

    def pulse_input_box(self) -> None:
        self._pulse_id += 1
        pulse_id = self._pulse_id
        self.restyle(self.drop_box, "dropSuccess", "true")

        def finish_pulse():
            if pulse_id == self._pulse_id:
                self.restyle(self.drop_box, "dropSuccess", "false")

        QTimer.singleShot(700, finish_pulse)

    def choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select files",
            str(self.last_input_directory),
            (
                "Supported files (*.pdf *.docx *.xlsx *.xls *.pptx "
                "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;"
                "All files (*.*)"
            ),
        )

        if files:
            self.remember_input_directory(Path(files[0]).parent)
            self.add_files([Path(path) for path in files])

    def add_files(self, files: list[Path], dropped: bool = False) -> None:
        if self.worker and self.worker.isRunning():
            return

        added = 0
        for file in files:
            resolved = file.resolve()
            if resolved not in self.selected_files:
                self.selected_files.append(resolved)
                self.drop_box.add_file(resolved)
                added += 1

        if added:
            self.remember_input_directory(files[0].resolve().parent)
            self.hide_success_banner()
            self.update_input_state()
            self.refresh_actions()

            if dropped:
                self.pulse_input_box()
                self.status_label.setText(
                    f"{added} file(s) added. {len(self.selected_files)} ready to convert."
                )

    def remove_selected(self) -> None:
        rows = self.drop_box.selected_rows()

        if not rows:
            self.status_label.setText("Select one or more files to remove.")
            return

        for row in rows:
            self.selected_files.pop(row)

        self.drop_box.remove_rows(rows)
        self.update_input_state()
        self.refresh_actions()

    def clear_files(self) -> None:
        self.selected_files.clear()
        self.drop_box.clear_all()
        self.update_input_state()
        self.refresh_actions()

    def update_input_state(self) -> None:
        count = len(self.selected_files)
        self.file_count_label.setText(f"{count} file{'' if count == 1 else 's'}")
        if not (self.worker and self.worker.isRunning()):
            self.status_label.setText(
                f"{count} file(s) ready to convert" if count else "Ready"
            )

    def refresh_actions(self) -> None:
        busy = self.worker is not None and self.worker.isRunning()
        has_files = bool(self.selected_files)

        self.drop_box.setEnabled(not busy)
        self.add_files_button.setEnabled(not busy)
        self.remove_selected_button.setEnabled(not busy and has_files)
        self.clear_files_button.setEnabled(not busy and has_files)
        self.change_languages_button.setEnabled(not busy)
        self.output_path_button.setEnabled(not busy)
        self.output_format_combo.setEnabled(not busy)
        self.convert_button.setEnabled(not busy and has_files)
        self.open_folder_button.setEnabled(True)

        self.convert_button.setText("Converting..." if busy else "Start Conversion")

    def refresh_language_summary(self) -> None:
        labels = [
            LANGUAGE_NAMES.get(code, code.upper())
            for code in self.selected_languages
        ]
        if len(labels) <= MAX_OCR_LANGUAGES_PER_CONVERSION:
            summary = " + ".join(labels)
        else:
            summary = (
                f"{MAX_OCR_LANGUAGES_PER_CONVERSION} languages selected"
            )

        self.language_summary_label.setText(summary)
        self.language_summary_label.setToolTip(
            "\n".join(language_label(code) for code in self.selected_languages)
        )

    def choose_languages(self) -> None:
        dialog = LanguageDialog(
            self.available_languages,
            self.selected_languages,
            self,
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_languages = dialog.selected_codes()
            self.settings.setValue("ocr_languages", self.selected_languages)
            self.settings.sync()
            self.refresh_language_summary()
            self.hide_success_banner()
            self.status_label.setText("Languages updated")

    def remember_input_directory(self, directory: Path) -> None:
        if directory.is_dir():
            self.last_input_directory = directory
            self.settings.setValue("last_input_directory", str(directory))

    def save_output_format(self) -> None:
        selected = self.output_format_combo.currentData()
        self.output_format = selected if selected in {".md", ".txt"} else ".md"
        self.settings.setValue("output_format", self.output_format)
        self.hide_success_banner()
        self.status_label.setText(f"Output format: {self.output_format}")

    def refresh_output_path(self) -> None:
        self.output_path_button.setText(str(self.output_directory))
        self.output_path_button.setToolTip(
            "Click to change the output folder\n" + str(self.output_directory)
        )

    def choose_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose output folder",
            str(self.output_directory),
        )

        if folder:
            self.output_directory = Path(folder)
            self.settings.setValue("output_directory", str(self.output_directory))
            self.refresh_output_path()
            self.hide_success_banner()
            self.status_label.setText("Output folder updated")

    def open_output_folder(self) -> None:
        self.output_directory.mkdir(parents=True, exist_ok=True)
        os.startfile(self.output_directory)

    def open_github_project(self) -> None:
        QDesktopServices.openUrl(QUrl(GITHUB_PROJECT_URL))

    def hide_success_banner(self) -> None:
        self.restyle(self.status_label, "success", "false")

    def show_success_banner(self, successful: int) -> None:
        noun = "file" if successful == 1 else "files"
        self.status_label.setText(
            f"✓ Conversion complete — {successful} {noun} converted successfully."
        )
        self.restyle(self.status_label, "success", "true")

    def start_conversion(self) -> None:
        if not self.selected_files:
            return

        self.hide_success_banner()
        self.conversion_errors.clear()

        self.worker = ConversionWorker(
            files=list(self.selected_files),
            output_directory=self.output_directory,
            languages=list(self.selected_languages),
            output_format=self.output_format,
            parent=self,
        )
        self.worker.progress.connect(self.status_label.setText)
        self.worker.file_succeeded.connect(self.handle_file_success)
        self.worker.file_failed.connect(self.handle_file_failure)
        self.worker.batch_finished.connect(self.finish_conversion)
        self.worker.finished.connect(self.worker.deleteLater)

        self.refresh_actions()
        self.status_label.setText(
            f"Preparing {len(self.selected_files)} file(s) for conversion..."
        )
        self.worker.start()

    def handle_file_success(self, source_text: str, output_text: str) -> None:
        source = Path(source_text)
        try:
            self.selected_files.remove(source)
        except ValueError:
            pass

        self.drop_box.remove_path(source)
        self.file_count_label.setText(
            f"{len(self.selected_files)} file{'' if len(self.selected_files) == 1 else 's'}"
        )
        self.status_label.setText(f"Saved: {Path(output_text).name}")

    def handle_file_failure(self, source_text: str, error: str) -> None:
        source_name = Path(source_text).name
        self.conversion_errors.append((source_name, error))
        self.status_label.setText(f"Could not convert: {source_name}")

    def finish_conversion(self, successful: int, failed: int) -> None:
        self.worker = None
        self.refresh_actions()
        self.update_input_state()

        if failed == 0:
            self.status_label.setText(
                f"Complete: {successful} file(s) converted successfully."
            )
            self.show_success_banner(successful)
            return

        error_lines = "\n\n".join(
            f"{name}\n{error}"
            for name, error in self.conversion_errors[:3]
        )
        extra = (
            f"\n\nPlus {failed - 3} more failed file(s)."
            if failed > 3
            else ""
        )

        self.hide_success_banner()
        self.status_label.setText(
            f"Finished: {successful} converted, {failed} failed."
        )
        QMessageBox.warning(
            self,
            APP_NAME,
            f"Finished with errors.\n\n"
            f"Converted: {successful}\n"
            f"Failed: {failed}\n\n"
            f"{error_lines}{extra}",
        )

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(
                self,
                APP_NAME,
                "Conversion is still running. Wait for it to finish before closing Pdink.",
            )
            event.ignore()
            return
        super().closeEvent(event)


def set_windows_app_user_model_id() -> None:
    """Give Windows a stable identity so the taskbar uses Pdink's icon."""
    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            WINDOWS_APP_USER_MODEL_ID
        )
    except Exception:
        pass


def main() -> None:
    set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")

    icon_path = bundled_icon_path()
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = PdinkWindow()
    if not app.windowIcon().isNull():
        window.setWindowIcon(app.windowIcon())
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
