"""Onglet Teleportation."""
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from mgs4trainer.core.i18n import act_display_name, act_number, stage_display_name, tr
from mgs4trainer.core.paths import DEFAULT_TELEPORT_POINTS_FILE, TELEPORT_POINTS_FILE
from mgs4trainer.live import MGS4Live
from mgs4trainer.ui.common import warn_dialog


class TeleportTab(QWidget):
    """Points de teleportation pour Snake - experimental (2026-09-27),
    voir notes.md. Repose sur coord_actor (native/speedhack.c,
    install_coord_tracker_hook) : un hook de lecture seule sur une routine
    generique de calcul de distance entre deux acteurs, qui capture le
    pointeur de Snake (confirme stable pendant le deplacement + veritable
    teleportation validee en jeu). Coordonnees absolues (pas relatives a
    l'orientation du joueur) - +0x10 X, +0x14 Y (hauteur, le jeu peut
    rejeter une position invalide sous le sol), +0x18 Z."""

    def __init__(self, live: MGS4Live):
        super().__init__()
        self.live = live
        self.points: list[dict] = self._load_points()
        # Code de stage actuel (MGS4Live.read_location) : les coordonnees
        # n'ont de sens que dans leur stage, chaque point garde donc le
        # sien ("stage") et la liste n'affiche que ceux du stage actuel
        # (plus les anciens points sans stage, tant qu'ils ne sont pas
        # rattaches).
        self.current_stage: str | None = None
        self.current_act: int | None = None
        self.row_points: list[int] = []

        layout = QVBoxLayout(self)

        warning = QLabel(tr("teleport.warning"))
        warning.setWordWrap(True)
        layout.addWidget(warning)

        location_row = QHBoxLayout()
        location_row.addWidget(QLabel(tr("teleport.location")))
        self.location_label = QLabel(tr("teleport.location_unknown"))
        self.location_label.setStyleSheet("font-weight: bold;")
        location_row.addWidget(self.location_label)
        location_row.addStretch(1)
        self.show_all_check = QCheckBox(tr("teleport.show_all_zones"))
        self.show_all_check.toggled.connect(self._rebuild_table)
        location_row.addWidget(self.show_all_check)
        layout.addLayout(location_row)

        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel(tr("teleport.current_position")))
        self.current_pos_label = QLabel("?")
        pos_row.addWidget(self.current_pos_label)
        pos_row.addStretch(1)
        save_btn = QPushButton(tr("teleport.save_here"))
        save_btn.clicked.connect(self._save_current_position)
        pos_row.addWidget(save_btn)
        layout.addLayout(pos_row)

        # Edition manuelle des 3 axes - ne se resynchronise PAS toute
        # seule pendant que l'utilisateur tape (uniquement via le bouton
        # "Actualiser"), sinon le cycle de rafraichissement general
        # (REFRESH_MS) ecraserait la saisie en cours.
        edit_row = QHBoxLayout()
        self.axis_spins: dict[str, QDoubleSpinBox] = {}
        for axis in ("X", "Y", "Z"):
            edit_row.addWidget(QLabel(f"{axis} :"))
            spin = QDoubleSpinBox()
            spin.setRange(-1_000_000.0, 1_000_000.0)
            spin.setDecimals(2)
            spin.setSingleStep(10.0)
            edit_row.addWidget(spin)
            self.axis_spins[axis] = spin
        refresh_pos_btn = QPushButton(tr("teleport.refresh_from_game"))
        refresh_pos_btn.clicked.connect(self._pull_current_position)
        edit_row.addWidget(refresh_pos_btn)
        apply_pos_btn = QPushButton(tr("teleport.teleport_here"))
        apply_pos_btn.clicked.connect(self._apply_manual_position)
        edit_row.addWidget(apply_pos_btn)
        edit_row.addStretch(1)
        layout.addLayout(edit_row)

        file_row = QHBoxLayout()
        export_btn = QPushButton(tr("teleport.export"))
        export_btn.clicked.connect(self._export_points)
        file_row.addWidget(export_btn)
        import_btn = QPushButton(tr("teleport.import"))
        import_btn.clicked.connect(self._import_points)
        file_row.addWidget(import_btn)
        file_row.addStretch(1)
        layout.addLayout(file_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("table.name"), tr("teleport.zone_column"), "X", "Y", "Z"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        # Zone : toujours assez large pour le nom complet (jamais coupe).
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.doubleClicked.connect(self._teleport_selected)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        teleport_btn = QPushButton(tr("teleport.teleport_to_selected"))
        teleport_btn.clicked.connect(self._teleport_selected)
        action_row.addWidget(teleport_btn)
        delete_btn = QPushButton(tr("teleport.delete_selected"))
        delete_btn.clicked.connect(self._delete_selected)
        action_row.addWidget(delete_btn)
        assign_btn = QPushButton(tr("teleport.assign_zone"))
        assign_btn.setToolTip(tr("teleport.assign_zone_tooltip"))
        assign_btn.clicked.connect(self._assign_selected_to_current_stage)
        action_row.addWidget(assign_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self._rebuild_table()

    # Fichier de points, format 2 (2026-10-04) : range par acte puis par
    # code de stage, uniquement des valeurs du jeu (aucun nom traduit, le
    # meme fichier sert en francais et en anglais) :
    #   {"format": 2,
    #    "acts": {"1": {"s01a40l": [{"name", "x", "y", "z"}, ...]}},
    #    "unassigned": [{"name", "x", "y", "z"}, ...]}
    # En memoire : liste plate, chaque point portant "act"/"stage" s'il est
    # rattache. L'ancien format (liste plate de {name, x, y, z}) se lit
    # toujours, ses points arrivent dans "unassigned".
    POINTS_FORMAT = 2

    @staticmethod
    def _valid_point(p) -> bool:
        return isinstance(p, dict) and isinstance(p.get("name"), str) and all(
            isinstance(p.get(k), (int, float)) for k in ("x", "y", "z"))

    @classmethod
    def _points_from_json(cls, data) -> list[dict]:
        """Format 2 ou ancienne liste plate -> liste plate ; ValueError si
        le contenu ne ressemble a aucun des deux."""
        def clean(p, act=None, stage=None):
            point = {"name": p["name"], "x": float(p["x"]), "y": float(p["y"]), "z": float(p["z"])}
            if stage:
                point["act"], point["stage"] = act, stage
            return point

        if isinstance(data, list):
            if not all(cls._valid_point(p) for p in data):
                raise ValueError(tr("teleport.unexpected_format"))
            return [clean(p, p.get("act"), p.get("stage")) for p in data]
        if not isinstance(data, dict) or data.get("format") != cls.POINTS_FORMAT:
            raise ValueError(tr("teleport.unexpected_format"))
        points = []
        for act_key, stages in (data.get("acts") or {}).items():
            act = int(act_key) if str(act_key).isdigit() else None
            if not isinstance(stages, dict):
                raise ValueError(tr("teleport.unexpected_format"))
            for stage, stage_points in stages.items():
                if not isinstance(stage_points, list) or not all(cls._valid_point(p) for p in stage_points):
                    raise ValueError(tr("teleport.unexpected_format"))
                points += [clean(p, act, stage) for p in stage_points]
        unassigned = data.get("unassigned") or []
        if not isinstance(unassigned, list) or not all(cls._valid_point(p) for p in unassigned):
            raise ValueError(tr("teleport.unexpected_format"))
        points += [clean(p) for p in unassigned]
        return points

    @classmethod
    def _points_to_json(cls, points: list[dict]) -> dict:
        acts: dict[str, dict[str, list]] = {}
        unassigned = []
        for p in points:
            entry = {"name": p["name"], "x": p["x"], "y": p["y"], "z": p["z"]}
            if p.get("stage"):
                act_key = str(p["act"]) if p.get("act") else "?"
                acts.setdefault(act_key, {}).setdefault(p["stage"], []).append(entry)
            else:
                unassigned.append(entry)
        ordered = {k: dict(sorted(acts[k].items())) for k in sorted(acts)}
        return {"format": cls.POINTS_FORMAT, "acts": ordered, "unassigned": unassigned}

    @classmethod
    def _load_points(cls) -> list[dict]:
        """Fichier personnel (a cote de l'exe) ; a defaut, les points
        fournis avec le trainer (assets/default_teleport_points.json,
        embarque dans l'exe). Le fichier personnel est cree au premier
        enregistrement et prend ensuite le relais."""
        for path in (TELEPORT_POINTS_FILE, DEFAULT_TELEPORT_POINTS_FILE):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return cls._points_from_json(json.load(f))
            except FileNotFoundError:
                continue
            except (json.JSONDecodeError, OSError, ValueError):
                return []
        return []

    def _save_points(self):
        try:
            with open(TELEPORT_POINTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._points_to_json(self.points), f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def _point_visible(self, point: dict) -> bool:
        stage = point.get("stage")
        return self.show_all_check.isChecked() or not stage or stage == self.current_stage

    def _rebuild_table(self):
        self.row_points = [i for i, point in enumerate(self.points) if self._point_visible(point)]
        self.table.setRowCount(len(self.row_points))
        for row, index in enumerate(self.row_points):
            point = self.points[index]
            stage = point.get("stage")
            self.table.setItem(row, 0, QTableWidgetItem(point["name"]))
            zone = (f"{act_display_name(point.get('act'))} - {stage_display_name(stage)}"
                    if stage else tr("teleport.no_zone"))
            for column, text in enumerate((zone, f"{point['x']:.1f}", f"{point['y']:.1f}", f"{point['z']:.1f}"), start=1):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)

    def _save_current_position(self):
        pos = self.live.player_position()
        if pos is None:
            warn_dialog(self, tr("teleport.position_not_found_title"),
                                 tr("teleport.position_not_found_body"))
            return
        name, ok = QInputDialog.getText(self, tr("teleport.point_name_title"), tr("teleport.point_name_body"))
        if not ok or not name.strip():
            return
        x, y, z = pos
        point = {"name": name.strip(), "x": x, "y": y, "z": z}
        if self.current_stage:
            point["act"], point["stage"] = self.current_act, self.current_stage
        self.points.append(point)
        self._save_points()
        self._rebuild_table()

    def _pull_current_position(self):
        pos = self.live.player_position()
        if pos is None:
            warn_dialog(self, tr("teleport.position_not_found_title"),
                                 tr("teleport.position_not_found_body"))
            return
        x, y, z = pos
        self.axis_spins["X"].setValue(x)
        self.axis_spins["Y"].setValue(y)
        self.axis_spins["Z"].setValue(z)

    def _apply_manual_position(self):
        x = self.axis_spins["X"].value()
        y = self.axis_spins["Y"].value()
        z = self.axis_spins["Z"].value()
        if not self.live.set_player_position(x, y, z):
            warn_dialog(self, tr("teleport.teleport_failed_title"), tr("teleport.snake_pointer_not_found"))

    def _export_points(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("teleport.export_dialog_title"), "", "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._points_to_json(self.points), f, indent=2, ensure_ascii=False)
        except OSError as exc:
            warn_dialog(self, tr("teleport.export_failed_title"), str(exc))

    def _import_points(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("teleport.import_dialog_title"), "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                imported = self._points_from_json(json.load(f))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            warn_dialog(self, tr("teleport.import_failed_title"), str(exc))
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("teleport.import_title"))
        box.setText(tr("teleport.import_confirm", count=len(imported)))
        yes_btn = box.addButton(tr("button.yes"), QMessageBox.YesRole)
        box.addButton(tr("button.no"), QMessageBox.NoRole)
        box.exec()
        if box.clickedButton() == yes_btn:
            self.points = imported
        else:
            self.points.extend(imported)
        self._save_points()
        self._rebuild_table()

    def _selected_row(self) -> int | None:
        """Indice dans self.points (pas la ligne affichee, la liste est
        filtree par stage)."""
        rows = self.table.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self.row_points):
            return None
        return self.row_points[rows[0].row()]

    def _assign_selected_to_current_stage(self):
        row = self._selected_row()
        if row is None or not self.current_stage:
            return
        self.points[row]["act"] = self.current_act
        self.points[row]["stage"] = self.current_stage
        self._save_points()
        self._rebuild_table()

    def _teleport_selected(self):
        row = self._selected_row()
        if row is None:
            return
        point = self.points[row]
        if not self.live.set_player_position(point["x"], point["y"], point["z"]):
            warn_dialog(self, tr("teleport.teleport_failed_title"), tr("teleport.snake_pointer_not_found"))

    def _delete_selected(self):
        row = self._selected_row()
        if row is None:
            return
        del self.points[row]
        self._save_points()
        self._rebuild_table()

    def set_advanced(self, advanced: bool):
        pass  # pas de mode simple/avance distinct ici

    def refresh(self):
        if not (self.live.connected and self.live.sane):
            self.current_pos_label.setText("?")
            self.location_label.setText(tr("teleport.location_unknown"))
            self.setEnabled(False)
            return
        self.setEnabled(True)
        try:
            location = self.live.read_location()
        except OSError:
            location = None
        if location is None:
            self.location_label.setText(tr("teleport.location_unknown"))
            stage = None
        else:
            stage, progress = location
            self.current_act = act_number(progress)
            self.location_label.setText(f"{act_display_name(self.current_act)} - {stage_display_name(stage)} ({stage})")
        if stage != self.current_stage:
            self.current_stage = stage
            self._rebuild_table()
        pos = self.live.player_position()
        if pos is None:
            self.current_pos_label.setText(tr("teleport.not_captured_yet"))
        else:
            x, y, z = pos
            self.current_pos_label.setText(f"X={x:.1f}  Y={y:.1f}  Z={z:.1f}")
