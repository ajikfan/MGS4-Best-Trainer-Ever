"""Version, aide et historique des versions."""
from PySide6.QtWidgets import (
    QDialog, QFrame, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from mgs4trainer.core.i18n import CHANGELOG_STRINGS, tr


TRAINER_VERSION = "V2.6.0"

TRAINER_HELP_TEXT = tr("help.text")

# Chargelog charge depuis locales/<langue>/changelog.json (dict {version:
# {date, description}}) plutot que code en dur - meme structure
# symetrique FR/EN que le reste de l'i18n (demande utilisateur
# 2026-10-01, V2.0). Ordre d'affichage = ordre d'insertion du JSON
# (Python 3.7+ garde l'ordre des dicts), donc le plus recent doit rester
# en premier dans le fichier source.
TRAINER_CHANGELOG = [
    (version_label, entry["date"], entry["description"])
    for version_label, entry in CHANGELOG_STRINGS.items()
]


class HelpDialog(QDialog):
    """Popup d'aide : explication rapide, compatibilite, avertissements,
    changelog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("window.help"))
        self.setMinimumSize(480, 420)
        layout = QVBoxLayout(self)

        version = QLabel(f"MGS4 Trainer — {TRAINER_VERSION}")
        version_font = version.font()
        version_font.setBold(True)
        version_font.setPointSize(version_font.pointSize() + 2)
        version.setFont(version_font)
        layout.addWidget(version)

        help_text = QLabel(TRAINER_HELP_TEXT)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        changelog_title = QLabel(tr("help.changelog_title"))
        changelog_title_font = changelog_title.font()
        changelog_title_font.setBold(True)
        changelog_title.setFont(changelog_title_font)
        layout.addWidget(changelog_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)
        for version_label, date, description in TRAINER_CHANGELOG:
            entry = QFrame()
            entry.setFrameShape(QFrame.StyledPanel)
            entry_layout = QVBoxLayout(entry)
            header = QLabel(f"{version_label} — {date}")
            header_font = header.font()
            header_font.setBold(True)
            header.setFont(header_font)
            entry_layout.addWidget(header)
            desc = QLabel(description)
            desc.setWordWrap(True)
            entry_layout.addWidget(desc)
            content_layout.addWidget(entry)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close_btn = QPushButton(tr("button.close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
