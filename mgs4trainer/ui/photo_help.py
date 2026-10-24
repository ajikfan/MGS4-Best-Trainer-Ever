"""Fenetre des commandes du mode photo (clavier/souris a gauche, manette a
droite)."""
import re

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from mgs4trainer.core.i18n import tr

# Actions dans l'ordre d'affichage ; textes dans locales (photo_help.*).
# Les touches s'ecrivent entre crochets ("[Z] [Q] [S] [D]", "[A] ou [Maj]
# maintenu") : chaque crochet devient une etiquette facon touche.
PHOTO_ACTIONS = ("move", "look", "up", "down", "fast", "slow", "zoom", "time", "teleport", "exit")
_KEY_TOKEN = re.compile(r"\[([^\]]+)\]")


def _icon_pixmap(draw, width: int, height: int, color: QColor, ratio: float) -> QPixmap:
    pixmap = QPixmap(int(width * ratio), int(height * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, 2.0)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    draw(painter, color)
    painter.end()
    return pixmap


def _draw_keyboard_mouse(painter: QPainter, color: QColor) -> None:
    # Clavier : cadre arrondi, trois rangees de touches et une barre d'espace.
    painter.drawRoundedRect(QRectF(2, 10, 74, 38), 5, 5)
    for row, (count, offset) in enumerate(((8, 7), (7, 11), (7, 9))):
        for i in range(count):
            painter.drawRect(QRectF(offset + i * 8.2, 15 + row * 7.5, 4.5, 4))
    painter.drawRoundedRect(QRectF(22, 38.5, 34, 4), 1.5, 1.5)
    # Souris : corps arrondi, separation des boutons, molette.
    painter.drawRoundedRect(QRectF(88, 12, 22, 34), 11, 11)
    painter.drawLine(QPointF(99, 12), QPointF(99, 25))
    painter.drawLine(QPointF(88.5, 25), QPointF(109.5, 25))
    painter.drawLine(QPointF(99, 16), QPointF(99, 20))
    # Fil de la souris.
    path = QPainterPath(QPointF(99, 12))
    path.cubicTo(QPointF(99, 4), QPointF(92, 6), QPointF(90, 2))
    painter.drawPath(path)


def _draw_gamepad(painter: QPainter, color: QColor) -> None:
    # Corps de la manette (proportions d'une manette Xbox) et poignees.
    body = QPainterPath(QPointF(38, 5))
    body.lineTo(QPointF(74, 5))
    body.cubicTo(QPointF(87, 5), QPointF(93, 12), QPointF(96, 27))
    body.cubicTo(QPointF(99, 43), QPointF(95, 51), QPointF(87, 50))
    body.cubicTo(QPointF(82, 49), QPointF(78, 43), QPointF(72, 37))
    body.lineTo(QPointF(40, 37))
    body.cubicTo(QPointF(34, 43), QPointF(30, 49), QPointF(25, 50))
    body.cubicTo(QPointF(17, 51), QPointF(13, 43), QPointF(16, 27))
    body.cubicTo(QPointF(19, 12), QPointF(25, 5), QPointF(38, 5))
    painter.drawPath(body)
    # Stick gauche en haut, croix directionnelle en dessous.
    painter.drawEllipse(QPointF(32, 17), 5, 5)
    painter.drawLine(QPointF(41, 28), QPointF(49, 28))
    painter.drawLine(QPointF(45, 24), QPointF(45, 32))
    # Boutons A B X Y en haut, stick droit en dessous.
    for x, y in ((80, 13), (84.5, 17.5), (80, 22), (75.5, 17.5)):
        painter.drawEllipse(QPointF(x, y), 2.2, 2.2)
    painter.drawEllipse(QPointF(67, 28), 4.5, 4.5)


class PhotoControlsDialog(QDialog):
    """Commandes du mode photo : deux colonnes (clavier/souris, manette)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("photo_help.title"))
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        columns.addWidget(self._column("kbm", _draw_keyboard_mouse), 1)
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        columns.addWidget(separator)
        columns.addWidget(self._column("pad", _draw_gamepad), 1)
        layout.addLayout(columns)

        notes = QLabel(tr("photo_help.notes"))
        notes.setWordWrap(True)
        notes.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(notes)

        close_btn = QPushButton(tr("button.close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignRight)

    def _column(self, device: str, draw) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        color = self.palette().color(self.foregroundRole())
        icon = QLabel()
        icon.setPixmap(_icon_pixmap(draw, 112, 54, color, self.devicePixelRatioF()))
        icon.setAlignment(Qt.AlignHCenter)
        layout.addWidget(icon)
        title = QLabel(tr(f"photo_help.{device}"))
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignHCenter)
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        for row, action in enumerate(PHOTO_ACTIONS):
            label = QLabel(tr(f"photo_help.action.{action}"))
            grid.addWidget(label, row, 0, Qt.AlignLeft | Qt.AlignVCenter)
            grid.addWidget(self._binding(tr(f"photo_help.{device}.{action}")), row, 1, Qt.AlignLeft | Qt.AlignVCenter)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return column

    @staticmethod
    def _binding(text: str) -> QWidget:
        """Texte avec des [touches] : chaque touche en etiquette encadree."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        position = 0
        for match in _KEY_TOKEN.finditer(text):
            plain = text[position:match.start()].strip()
            if plain:
                row.addWidget(QLabel(plain))
            key = QLabel(match.group(1))
            key.setStyleSheet(
                "border: 1px solid palette(mid); border-bottom-width: 2px; border-radius: 4px;"
                " padding: 1px 6px; background: palette(button); font-weight: bold;")
            row.addWidget(key)
            position = match.end()
        rest = text[position:].strip()
        if rest:
            row.addWidget(QLabel(rest))
        row.addStretch(1)
        return widget
