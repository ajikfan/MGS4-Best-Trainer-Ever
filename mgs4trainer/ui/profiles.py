"""Profils F1-F11 : fichiers, fenetres et bandeau par-dessus le jeu."""
import ctypes
import json
import os
from ctypes import wintypes

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from mgs4trainer.core.i18n import tr
from mgs4trainer.core.paths import DEFAULT_PROFILES_FILE, PROFILES_FILE


PROFILE_KEYS = [f"F{n}" for n in range(1, 12)]  # F12 = capture d'ecran Steam


def _beep() -> None:
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK)
    except (ImportError, RuntimeError):
        pass


def load_profiles() -> dict[str, dict]:
    """{"F1": {"name": ..., "settings": {...}}, ...} - profils fournis si le
    fichier de l'utilisateur n'existe pas encore, vide s'il est illisible."""
    path = PROFILES_FILE if os.path.exists(PROFILES_FILE) else DEFAULT_PROFILES_FILE
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
    return {k: v for k, v in profiles.items()
            if k in PROFILE_KEYS and isinstance(v, dict) and isinstance(v.get("settings"), dict)}


def save_profiles(profiles: dict[str, dict]) -> bool:
    ordered = {k: profiles[k] for k in PROFILE_KEYS if k in profiles}
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump({"format": 1, "profiles": ordered}, f, ensure_ascii=False, indent=2)
    except OSError:
        return False
    return True


def profile_label(key: str, profile: dict) -> str:
    return f"{key} - {profile.get('name') or key}"


class ProfileChooserDialog(QDialog):
    """Choix du profil au lancement : un bouton par profil + Aucun."""

    def __init__(self, profiles: dict[str, dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("profile.choose_title"))
        self.chosen: str | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("profile.choose_body")))
        for key in PROFILE_KEYS:
            if key in profiles:
                btn = QPushButton(profile_label(key, profiles[key]))
                btn.clicked.connect(lambda _checked=False, k=key: self._choose(k))
                layout.addWidget(btn)
        none_btn = QPushButton(tr("profile.none"))
        none_btn.clicked.connect(self.reject)
        layout.addWidget(none_btn)

    def _choose(self, key: str):
        self.chosen = key
        self.accept()


class ProfileSaveDialog(QDialog):
    """Enregistre la configuration actuelle sous une touche F1-F11 (ou
    supprime le profil de cette touche)."""

    def __init__(self, profiles: dict[str, dict], current: str | None, parent=None):
        super().__init__(parent)
        self.profiles = profiles
        self.action: str | None = None  # "save" / "delete"
        self.setWindowTitle(tr("profile.save_title"))
        layout = QVBoxLayout(self)
        form = QGridLayout()
        form.addWidget(QLabel(tr("profile.key")), 0, 0)
        self.key_combo = QComboBox()
        for key in PROFILE_KEYS:
            label = profile_label(key, profiles[key]) if key in profiles else f"{key} - {tr('profile.empty')}"
            self.key_combo.addItem(label, key)
        if current in PROFILE_KEYS:
            self.key_combo.setCurrentIndex(PROFILE_KEYS.index(current))
        else:
            free = [k for k in PROFILE_KEYS if k not in profiles]
            self.key_combo.setCurrentIndex(PROFILE_KEYS.index(free[0]) if free else 0)
        form.addWidget(self.key_combo, 0, 1)
        form.addWidget(QLabel(tr("profile.name")), 1, 0)
        self.name_edit = QLineEdit()
        form.addWidget(self.name_edit, 1, 1)
        layout.addLayout(form)
        hint = QLabel(tr("profile.save_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        save_btn = QPushButton(tr("profile.save"))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        buttons.addWidget(save_btn)
        self.delete_btn = QPushButton(tr("profile.delete"))
        self.delete_btn.clicked.connect(self._delete)
        buttons.addWidget(self.delete_btn)
        cancel_btn = QPushButton(tr("button.cancel"))
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        self.key_combo.currentIndexChanged.connect(self._on_key_changed)
        self._on_key_changed()

    @property
    def key(self) -> str:
        return self.key_combo.currentData()

    @property
    def name(self) -> str:
        return self.name_edit.text().strip() or self.key

    def _on_key_changed(self, _index: int = 0):
        existing = self.profiles.get(self.key)
        self.name_edit.setText(existing.get("name", "") if existing else "")
        self.delete_btn.setEnabled(existing is not None)

    def _confirm(self, text: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(tr("profile.save_title"))
        box.setText(text)
        yes_btn = box.addButton(tr("button.yes"), QMessageBox.YesRole)
        box.addButton(tr("button.no"), QMessageBox.NoRole)
        box.exec()
        return box.clickedButton() == yes_btn

    def _save(self):
        existing = self.profiles.get(self.key)
        if existing and not self._confirm(tr("profile.overwrite", profile=profile_label(self.key, existing))):
            return
        self.action = "save"
        self.accept()

    def _delete(self):
        existing = self.profiles.get(self.key)
        if existing and self._confirm(tr("profile.delete_confirm", profile=profile_label(self.key, existing))):
            self.action = "delete"
            self.accept()


def _game_window_rect(pid: int | None) -> tuple[int, int, int, int] | None:
    """Rectangle (pixels physiques) de la plus grande fenetre visible du jeu."""
    if not pid:
        return None
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found: list[tuple[int, tuple[int, int, int, int]]] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                area = (rect.right - rect.left) * (rect.bottom - rect.top)
                found.append((area, (rect.left, rect.top, rect.right, rect.bottom)))
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return max(found)[1] if found else None


class ProfileOverlay(QWidget):
    """Bandeau affiche ~2 s par-dessus le jeu quand un raccourci F1-F11
    (de)active un profil : fenetre transparente, toujours au premier plan,
    sans focus ni clics (le jeu garde le clavier). Visible en fenetre / plein
    ecran fenetre ; un plein ecran exclusif peut la masquer."""

    DURATION_MS = 2200

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    STYLE = ("QLabel {{ background: rgba(10, 14, 12, 215); color: #e8f5e9; border: 2px solid {color};"
             " border-radius: 10px; padding: 10px 26px; font-size: 22px; font-weight: bold; }}")

    def show_message(self, text: str, active: bool, pid: int | None):
        self.label.setStyleSheet(self.STYLE.format(color="#6fbf73" if active else "#c97b63"))
        self.label.setText(text)
        self.adjustSize()
        # Centre en haut de la fenetre du jeu (pixels physiques -> logiques),
        # sinon de l'ecran principal.
        screen = QGuiApplication.primaryScreen()
        rect = _game_window_rect(pid)
        if rect is not None:
            left, top, right, _bottom = rect
            ratio = screen.devicePixelRatio() or 1.0
            x = round((left + right) / 2 / ratio - self.width() / 2)
            y = round(top / ratio) + 60
        else:
            area = screen.geometry()
            x = area.center().x() - self.width() // 2
            y = area.top() + 60
        self.move(x, y)
        self.show()
        # Au-dessus du jeu meme s'il est lui-meme "topmost", sans l'activer.
        HWND_TOPMOST, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = -1, 0x1, 0x2, 0x10, 0x40
        ctypes.WinDLL("user32").SetWindowPos(wintypes.HWND(int(self.winId())), wintypes.HWND(HWND_TOPMOST),
                                              0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        self.hide_timer.start(self.DURATION_MS)
