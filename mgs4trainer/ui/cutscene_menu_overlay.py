"""Ligne QUITTER dessinee par-dessus le menu pause des cinematiques (voir
live/cutscene_menu.py : le jeu gere la navigation et la barre, le trainer
dessine seulement le texte de la 3e ligne)."""
import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter
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


class GameCurtain(QWidget):
    """Rideau noir par-dessus la zone client du jeu, en fondu : couvre la
    fermeture du menu pause apres « Charger » (le fondu du jeu meurt avec le
    menu) et le retour au menu principal depuis une cinematique."""

    STEP_MS = 16

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._pid = None
        self._target = 0.0
        self._step = 0.0
        self._on_done = None
        self._timer = QTimer(self)
        self._timer.setInterval(self.STEP_MS)
        self._timer.timeout.connect(self._tick)

    def fade_in(self, pid: int, seconds: float = 0.5, on_done=None) -> None:
        self._pid, self._on_done = pid, on_done
        if not self._place():
            if on_done:
                on_done()
            return
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            HWND_TOPMOST, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = -1, 0x1, 0x2, 0x10, 0x40
            ctypes.WinDLL("user32").SetWindowPos(wintypes.HWND(int(self.winId())), wintypes.HWND(HWND_TOPMOST),
                                                  0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        self._start(1.0, seconds)

    def fade_out(self, seconds: float = 0.3) -> None:
        self._on_done = None
        if self.isVisible():
            self._start(0.0, seconds)

    def _start(self, target: float, seconds: float) -> None:
        self._target = target
        self._step = (target - self.windowOpacity()) * self.STEP_MS / max(1.0, seconds * 1000)
        self._timer.start()

    def _place(self) -> bool:
        rect = _game_client_rect(self._pid) if self._pid else None
        if rect is None:
            return False
        left, top, width, height, _hwnd = rect
        ratio = QGuiApplication.primaryScreen().devicePixelRatio() or 1.0
        self.setGeometry(round(left / ratio), round(top / ratio), round(width / ratio), round(height / ratio))
        return True

    def _tick(self) -> None:
        self._place()
        opacity = self.windowOpacity() + self._step
        if (self._step >= 0 and opacity >= self._target) or (self._step < 0 and opacity <= self._target) or not self._step:
            opacity = self._target
            self._timer.stop()
        self.setWindowOpacity(opacity)
        if self._timer.isActive():
            return
        if opacity <= 0.0:
            self.hide()
        elif self._on_done:
            done, self._on_done = self._on_done, None
            done()

    def paintEvent(self, _event):
        QPainter(self).fillRect(self.rect(), Qt.black)


class CutsceneQuitOverlay(QWidget):
    """Texte de la 3e ligne, aux proportions du menu du jeu (mesurees sur une
    zone client 16:9 : lignes a 53,2 % / 57,3 % de la hauteur, 3e a 61,75 %).
    Fenetre au premier plan (rattachee a celle du jeu, elle passait dessous :
    proprietaire entre processus sans effet), masquee si une autre fenetre
    recouvre le jeu (voir _foreground_allows)."""

    LINE_Y = 0.6175       # centre de la 3e ligne (part de la hauteur)
    BAND_W, BAND_H = 0.80, 0.05
    TEXT_W = 0.42         # largeur maximale du texte, part de la hauteur (barre de selection : ~0,44)
    FONT_PX = 0.027       # taille de police (part de la hauteur)
    STRETCH = 1.75        # police elargie comme celle du jeu
    DIM, BRIGHT = QColor(100, 100, 100), QColor(240, 240, 240)
    SHADED = QColor(38, 38, 38)  # sous la fenetre de confirmation du jeu
    FADE_IN = 0.15        # s, apparition du texte a l'ouverture du menu

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._selected = False
        self._height = 900
        self._text = None
        self._shaded = False
        self._shown_at = 0.0

    def update_menu(self, pid: int | None, menu_open: bool, cursor: int | None, text: str | None = None,
                    shaded: bool = False) -> None:
        """`text` : libelle du jeu (« RETOURNER A L'ECRAN TITRE » dans sa
        langue), sinon le texte du trainer ; `shaded` : fenetre de
        confirmation ouverte, le menu est assombri dessous."""
        if text != self._text or shaded != self._shaded:
            self._text, self._shaded = text, shaded
            self.update()
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
            # Apparition en fondu, comme le menu du jeu (opacite suivie a
            # chaque sondage, voir plus bas).
            self._shown_at = time.monotonic()
            self.setWindowOpacity(0.0)
            self.show()
            HWND_TOPMOST, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = -1, 0x1, 0x2, 0x10, 0x40
            ctypes.WinDLL("user32").SetWindowPos(wintypes.HWND(int(self.winId())), wintypes.HWND(HWND_TOPMOST),
                                                  0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        if self.windowOpacity() < 1.0:
            self.setWindowOpacity(min(1.0, (time.monotonic() - self._shown_at) / self.FADE_IN))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = QFont("Bahnschrift")
        font.setWeight(QFont.Medium)
        font.setPixelSize(max(8, round(self._height * self.FONT_PX)))
        font.setLetterSpacing(QFont.AbsoluteSpacing, font.pixelSize() * 0.02)
        painter.setFont(font)
        text = self._text or tr("cutscene_menu.quit")
        # Police elargie : on dessine dans un repere etire horizontalement ;
        # un texte long (libelle du jeu) est moins etire pour tenir dans la
        # largeur de la barre de selection du jeu.
        fit = self._height * self.TEXT_W
        stretch = min(self.STRETCH, fit / max(1.0, QFontMetricsF(font).horizontalAdvance(text)))
        painter.translate(self.width() / 2, 0)
        painter.scale(stretch, 1.0)
        area = QRectF(-self.width() / (2 * stretch), 0, self.width() / stretch, self.height())
        if self._shaded:
            painter.setPen(self.SHADED)
            painter.drawText(area, Qt.AlignCenter, text)
            return
        painter.setPen(QColor(0, 0, 0, 160))
        painter.drawText(area.translated(1, 1), Qt.AlignCenter, text)
        painter.setPen(self.BRIGHT if self._selected else self.DIM)
        painter.drawText(area, Qt.AlignCenter, text)
