"""Fenetre de mise a jour : version disponible, nouveautes, telechargement
des fichiers modifies (core/updater.py, dans un fil separe), puis
redemarrage immediat ou au prochain lancement."""
import threading
import webbrowser

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QTextBrowser, QVBoxLayout,
)

from mgs4trainer.core import updater
from mgs4trainer.core.i18n import set_update_check, tr, update_check_enabled


class UpdateWorker(QObject):
    """Lance une fonction de core/updater dans un fil separe ; les signaux
    reviennent dans le fil de l'interface."""
    finished = Signal(object, object)  # resultat, erreur (UpdateError) ou None
    progress = Signal(int, int)

    def run(self, function, *args) -> None:
        def target():
            try:
                result, error = function(*args), None
            except updater.UpdateError as exc:
                result, error = None, exc
            self.finished.emit(result, error)
        threading.Thread(target=target, daemon=True).start()


class UpdateDialog(QDialog):
    def __init__(self, current_version: str, release: dict | None = None, restart=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("update.title"))
        self.setMinimumSize(520, 420)
        self.current_version = current_version
        self.release = release
        self.manifest = None
        self.restart = restart
        layout = QVBoxLayout(self)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        layout.addWidget(self.notes, 1)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)

        self.auto_check = QCheckBox(tr("update.check_at_launch"))
        self.auto_check.setChecked(update_check_enabled())
        self.auto_check.toggled.connect(set_update_check)
        layout.addWidget(self.auto_check)

        buttons = QHBoxLayout()
        self.check_btn = QPushButton(tr("update.check"))
        self.check_btn.clicked.connect(self.check)
        self.update_btn = QPushButton(tr("update.install"))
        self.update_btn.clicked.connect(self.install)
        self.page_btn = QPushButton(tr("update.open_page"))
        self.page_btn.clicked.connect(self._open_page)
        self.restart_btn = QPushButton(tr("update.restart_now"))
        self.restart_btn.clicked.connect(self._restart)
        self.close_btn = QPushButton(tr("button.close"))
        self.close_btn.clicked.connect(self.accept)
        for button in (self.check_btn, self.update_btn, self.page_btn, self.restart_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)

        self.worker = UpdateWorker()
        self.worker.progress.connect(self._on_progress)
        self.restart_btn.hide()
        if release is None:
            self.check()
        else:
            self._show_release()

    # -- etapes --------------------------------------------------------
    def check(self) -> None:
        self._busy(tr("update.checking"))
        self.worker.finished.connect(self._on_checked)
        self.worker.run(updater.fetch_latest_release)

    def _on_checked(self, release, error) -> None:
        self.worker.finished.disconnect(self._on_checked)
        if error is not None:
            self._idle(tr("update.error", error=error))
            return
        self.release = release
        self._show_release()

    def _show_release(self) -> None:
        version = self.release["version"]
        self.notes.setMarkdown(self.release["notes"])
        if not updater.is_newer(version, self.current_version):
            self._idle(tr("update.up_to_date", version=self.current_version))
            return
        if updater.launcher_version() is None:
            self._idle(tr("update.available_dev", version=version, current=self.current_version), page=True)
            return
        self._idle(tr("update.available", version=version, current=self.current_version), install=True)

    def install(self) -> None:
        self._busy(tr("update.downloading"))
        self.progress.setRange(0, 0)
        self.progress.show()
        self.worker.finished.connect(self._on_installed)
        self.worker.run(self._download)

    def _download(self) -> dict:
        manifest = updater.fetch_manifest(self.release)
        return updater.prepare_update(self.release, manifest,
                                      lambda done, total, _path: self.worker.progress.emit(done, total))

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)

    def _on_installed(self, result, error) -> None:
        self.worker.finished.disconnect(self._on_installed)
        self.progress.hide()
        if error is not None:
            self._idle(tr("update.error", error=error), page=True)
            return
        if not (result["files"] or result["removed"]):
            self._idle(tr("update.nothing_to_do"))
            return
        text = tr("update.ready", count=len(result["files"]), version=self.release["version"])
        if result["dll_changed"]:
            text += "\n\n" + tr("update.dll_changed")
        self._idle(text)
        self.restart_btn.show()
        self.close_btn.setText(tr("update.later"))

    # -- etat des boutons ----------------------------------------------
    def _busy(self, text: str) -> None:
        self.status.setText(text)
        for button in (self.check_btn, self.update_btn, self.page_btn):
            button.setEnabled(False)

    def _idle(self, text: str, install: bool = False, page: bool = False) -> None:
        self.status.setText(text)
        self.check_btn.setEnabled(True)
        self.update_btn.setVisible(install)
        self.update_btn.setEnabled(install)
        self.page_btn.setVisible(page)
        self.page_btn.setEnabled(page)

    def _open_page(self) -> None:
        webbrowser.open((self.release or {}).get("page_url") or updater.RELEASES_PAGE_URL)

    def _restart(self) -> None:
        self.accept()
        if self.restart:
            self.restart()
