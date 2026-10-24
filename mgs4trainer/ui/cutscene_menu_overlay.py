"""Ligne QUITTER dessinee par-dessus le menu pause des cinematiques (voir
live/cutscene_menu.py : le jeu gere la navigation et la barre, le trainer
dessine seulement le texte de la 3e ligne)."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from mgs4trainer.core.i18n import tr


def _game_client_rect(pid: int) -> tuple[int, int, int, int, int] | None:
    """(gauche, haut, largeur, hauteur) de la zone client de la fenetre du jeu
    (pixels physiques) et la fenetre ; None si le jeu est reduit."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found: list[tuple[int, int]] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            if user32.GetClientRect(hwnd, ctypes.byref(rect)):
                found.append((rect.right * rect.bottom, hwnd))
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    if not found:
        return None
    hwnd = max(found)[1]
    if user32.IsIconic(hwnd):
        return None
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right, rect.bottom, hwnd


# Outils de capture d'ecran : ils prennent le focus pendant la capture, la
# ligne doit rester visible.
_CAPTURE_TOOLS = {"snippingtool.exe", "screenclippinghost.exe", "sharex.exe", "obs64.exe", "lightshot.exe",
                  "greenshot.exe"}


def _foreground_allows(game_hwnd: int, game_rect: tuple[int, int, int, int]) -> bool:
    """La ligne peut rester affichee : jeu au premier plan, outil de capture
    actif, ou fenetre active qui ne recouvre pas le jeu (autre ecran...)."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fg = user32.GetForegroundWindow()
    if not fg or fg == game_hwnd:
        return True
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if handle:
        try:
            name = ctypes.create_unicode_buffer(520)
            size = wintypes.DWORD(len(name))
            if kernel32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
                if name.value.rsplit("\\", 1)[-1].lower() in _CAPTURE_TOOLS:
                    return True
        finally:
            kernel32.CloseHandle(handle)
    rect = wintypes.RECT()
    if not user32.GetWindowRect(fg, ctypes.byref(rect)):
        return True
    left, top, width, height = game_rect
    return rect.right <= left or rect.left >= left + width or rect.bottom <= top or rect.top >= top + height


class CutsceneQuitOverlay(QWidget):
    """Texte de la 3e ligne, aux proportions du menu du jeu (mesurees sur une
    zone client 16:9 : lignes a 53,2 % / 57,3 % de la hauteur, 3e a 61,75 %).
    Fenetre au premier plan (rattachee a celle du jeu, elle passait dessous :
    proprietaire entre processus sans effet), masquee si une autre fenetre
    recouvre le jeu (voir _foreground_allows)."""

    LINE_Y = 0.6175       # centre de la 3e ligne (part de la hauteur)
    BAND_W, BAND_H = 0.40, 0.05
    FONT_PX = 0.027       # taille de police (part de la hauteur)
    STRETCH = 1.75        # police elargie comme celle du jeu
    DIM, BRIGHT = QColor(100, 100, 100), QColor(240, 240, 240)

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._selected = False
        self._height = 900

    def update_menu(self, pid: int | None, menu_open: bool, cursor: int | None) -> None:
        rect = _game_client_rect(pid) if (pid and menu_open) else None
        if rect is None:
            self.hide()
            return
        left, top, width, height, game_hwnd = rect
        if not _foreground_allows(game_hwnd, (left, top, width, height)):
            self.hide()
            return
        ratio = QGuiApplication.primaryScreen().devicePixelRatio() or 1.0
        band_w, band_h = width * self.BAND_W, height * self.BAND_H
        x = left + (width - band_w) / 2
        y = top + height * self.LINE_Y - band_h / 2
        self.setGeometry(round(x / ratio), round(y / ratio), round(band_w / ratio), round(band_h / ratio))
        self._height = height / ratio
        selected = cursor == 2
        if selected != self._selected:
            self._selected = selected
            self.update()
        if not self.isVisible():
            self.show()
            HWND_TOPMOST, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = -1, 0x1, 0x2, 0x10, 0x40
            ctypes.WinDLL("user32").SetWindowPos(wintypes.HWND(int(self.winId())), wintypes.HWND(HWND_TOPMOST),
                                                  0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = QFont("Bahnschrift")
        font.setWeight(QFont.Medium)
        font.setPixelSize(max(8, round(self._height * self.FONT_PX)))
        font.setLetterSpacing(QFont.AbsoluteSpacing, font.pixelSize() * 0.02)
        painter.setFont(font)
        # Police elargie : on dessine dans un repere etire horizontalement.
        painter.translate(self.width() / 2, 0)
        painter.scale(self.STRETCH, 1.0)
        area = QRectF(-self.width() / (2 * self.STRETCH), 0, self.width() / self.STRETCH, self.height())
        text = tr("cutscene_menu.quit")
        painter.setPen(QColor(0, 0, 0, 160))
        painter.drawText(area.translated(1, 1), Qt.AlignCenter, text)
        painter.setPen(self.BRIGHT if self._selected else self.DIM)
        painter.drawText(area, Qt.AlignCenter, text)
