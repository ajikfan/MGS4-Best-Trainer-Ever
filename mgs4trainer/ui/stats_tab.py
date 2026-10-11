"""Onglet Stats."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

import mgs4save

from mgs4trainer.core.i18n import item_name, tr
from mgs4trainer.live import MGS4Live


# Meme convention que gui_app.py (FRAMES_PER_SECOND) : framerate reel
# variable (~55-62 fps selon le champ, voir notes.md), 60 est la meilleure
# approximation disponible - pas de conversion exacte possible.
FRAMES_PER_SECOND = 60


def _frames_to_hms_parts(frames: int) -> tuple[int, int, int]:
    total_seconds = frames // FRAMES_PER_SECOND
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return h, m, s


# Regroupement thematique + libelle FR des champs de mgs4save.STATS, pour
# l'onglet Stats du trainer (voir StatsTab). Purement cosmetique : aucun
# impact sur la fiabilite/l'ecriture, qui reste au cas par cas (voir note
# affichee en haut de l'onglet). Doit couvrir tous les noms de STATS sauf
# drebin_actuel/drebin_total_ventes (deja exclus en amont, UI dediee).
STATS_TRAINER_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (tr("stat_group.combat"), [
        ("kills_total", tr("stat.kills_total")),
        ("headshots", tr("stat.headshots")),
        ("knife_kills", tr("stat.knife_kills")),
        ("knife_knockouts", tr("stat.knife_knockouts")),
        ("cqc", tr("stat.cqc")),
        ("combat_high", tr("stat.combat_high")),
    ]),
    (tr("stat_group.infiltration"), [
        ("alertes", tr("stat.alertes")),
        ("continues", tr("stat.continues")),
        ("holdups", tr("stat.holdups")),
        ("body_searches", tr("stat.body_searches")),
        ("praises", tr("stat.praises")),
    ]),
    (tr("stat_group.movement"), [
        ("roulades_avant", tr("stat.roulades_avant")),
        ("roulades_cote", tr("stat.roulades_cote")),
    ]),
    (tr("stat_group.items"), [
        ("soins_utilises", tr("stat.soins_utilises")),
        ("objets_speciaux_bitmask", tr("stat.objets_speciaux_bitmask")),
        ("objets_donnes_milices", tr("stat.objets_donnes_milices")),
        ("weapon_pickups", tr("stat.weapon_pickups")),
        ("item_pickups", tr("stat.item_pickups")),
        ("syringe_uses", tr("stat.syringe_uses")),
        ("scanning_plug_uses", tr("stat.scanning_plug_uses")),
        ("playboy_pages", tr("stat.playboy_pages")),
        ("emotion_magazine_pages", tr("stat.emotion_magazine_pages")),
        ("posters_vus", tr("stat.posters_vus")),
    ]),
    (tr("stat_group.flashbacks"), [
        ("flashbacks_vues", tr("stat.flashbacks_vues")),
    ]),
    (tr("stat_group.time"), [
        ("temps_jeu_frames", tr("stat.temps_jeu_frames")),
        ("temps_accroupi_frames", tr("stat.temps_accroupi_frames")),
        ("temps_allonge_frames", tr("stat.temps_allonge_frames")),
        ("temps_mur_frames", tr("stat.temps_mur_frames")),
        ("temps_boite_carton_frames", tr("stat.temps_boite_carton_frames")),
        ("temps_baril_frames", tr("stat.temps_baril_frames")),
    ]),
]


class StatsTab(QWidget):
    """Onglet Stats : un champ par entree de mgs4save.STATS (cle textuelle,
    pas un ID numerique - kills, CQC, temps divers...), lu/ecrit via
    live.read_stat/write_stat (linkvarbuf). Une mini-table par theme
    (STATS_TRAINER_GROUPS, meme convention que GroupedWeaponsTab/
    GroupedItemsTab : en-tete + table dimensionnee a son contenu, empilees
    dans un QScrollArea commun) - pas de valeur affichee en double a cote
    d'un spinbox qui la montre deja (retour utilisateur 2026-09-25).
    Ecriture immediate (pas de bouton "OK", juge inutile) : au changement
    de selection pour le select "Objets speciaux", et pour les spinbox a
    chaque pas de fleche/molette ou a la validation d'une saisie clavier
    (setKeyboardTracking(False) - evite d'ecrire une valeur intermediaire
    incomplete pendant la frappe)."""

    # Les 4 combinaisons possibles des 2 bits identifies de
    # objets_speciaux_bitmask (voir mgs4save.SPECIAL_ITEM_USE_BITS :
    # Bandana=bit0, Camouflage optique=bit1) - valeur = bitmask a ecrire
    # telle quelle dans le champ u16.
    SPECIAL_ITEMS_STATES = [
        (tr("stats.special_items_none"), 0),
        (item_name(0x0f), 1),
        (item_name(0x10), 2),
        (tr("stats.special_items_both"), 3),
    ]

    def __init__(self, live: MGS4Live, names: list[str]):
        super().__init__()
        self.live = live
        self.names = names
        self.spin_items: dict[str, QSpinBox] = {}
        self.time_items: dict[str, tuple[QSpinBox, QSpinBox, QSpinBox]] = {}
        self.special_items_combo: QComboBox | None = None
        self.sections: list[tuple[QLabel, QTableWidget, list[str]]] = []

        layout = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(tr("table.filter_name")))
        self.filter_edit = QLineEdit()
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit)
        layout.addLayout(filter_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)

        remaining = set(names)
        for group_label, fields in STATS_TRAINER_GROUPS:
            fields = [(n, lbl) for n, lbl in fields if n in remaining]
            if not fields:
                continue
            self._add_section(inner_layout, group_label, fields)
            remaining -= {n for n, _ in fields}

        # Filet de securite : tout champ de STATS non couvert par
        # STATS_TRAINER_GROUPS (ne devrait pas arriver, voir commentaire du
        # dict) atterrit quand meme quelque part plutot que de disparaitre.
        if remaining:
            self._add_section(inner_layout, tr("stats.other_group"), [(n, n) for n in names if n in remaining])

        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def _add_section(self, inner_layout: QVBoxLayout, label: str, fields: list[tuple[str, str]]):
        header = QLabel(f"{label} ({len(fields)})")
        header.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 6px;")
        inner_layout.addWidget(header)

        # Legende H:M:S dans l'en-tete pour les sections 100% "_frames"
        # (3 spinbox cote a cote sans autre indication - demande
        # utilisateur 2026-09-25) plutot qu'un "Valeur" generique ambigu.
        all_time_fields = all(name.endswith("_frames") for name, _ in fields)
        value_header = tr("stats.value_hms") if all_time_fields else tr("stats.value")

        table = QTableWidget(len(fields), 2)
        table.setHorizontalHeaderLabels([tr("table.field"), value_header])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)

        for row, (name, display) in enumerate(fields):
            self._build_row(table, row, name, display)

        table.resizeColumnToContents(1)
        # Meme technique que fit_height dans TableTab : la table prend
        # exactement la hauteur de ses lignes, le QScrollArea englobant
        # gere le defilement global plutot que chaque petite table.
        row_h = table.rowHeight(0) if fields else 30
        total_h = table.horizontalHeader().height() + row_h * len(fields) + 2 * table.frameWidth() + 4
        table.setFixedHeight(total_h)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner_layout.addWidget(table)
        self.sections.append((header, table, [n for n, _ in fields]))

    def _build_row(self, table: QTableWidget, row: int, name: str, display: str):
        offset, fmt = mgs4save.STATS[name]
        name_item = QTableWidgetItem(display)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        name_item.setToolTip(f"{name} - offset {offset:#06x} ({'u32' if fmt == '<I' else 'u16'})")
        table.setItem(row, 0, name_item)

        if name == "objets_speciaux_bitmask":
            # Seulement 2 bits identifies (voir SPECIAL_ITEM_USE_BITS) sur
            # ce champ u16 - un select des 4 combinaisons possibles est
            # plus naturel qu'un spinbox brut pour l'edition (demande
            # explicite de l'utilisateur, 2026-09-25).
            combo = QComboBox()
            for label, value in self.SPECIAL_ITEMS_STATES:
                combo.addItem(label, value)
            combo.currentIndexChanged.connect(
                lambda _idx, n=name, c=combo: self._write(n, c.currentData())
            )
            table.setCellWidget(row, 1, combo)
            self.special_items_combo = combo
            return

        if name.endswith("_frames"):
            # Stocke en frames a framerate variable (voir notes.md), mais
            # un compteur "HH:MM:SS" est bien plus lisible/editable qu'un
            # nombre de frames brut (retour utilisateur 2026-09-25) - 3
            # spinbox H/M/S plutot que QTimeEdit, dont le plafond de 23h59
            # ne conviendrait pas a des compteurs de temps de jeu total
            # pouvant largement depasser 24h (champs u32).
            table.setCellWidget(row, 1, self._build_time_widget(name))
            return

        spin = QSpinBox()
        # QSpinBox est limite a un int signe 32 bits (max ~2.1 milliards),
        # ne peut pas couvrir tout un u32 (jusqu'a ~4.3 milliards) - marge
        # large mais pas la plage entiere pour les champs u32.
        spin.setRange(0, 2_000_000_000 if fmt == "<I" else 0xFFFF)
        spin.setMinimumWidth(110)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(lambda value, n=name: self._write(n, value))
        table.setCellWidget(row, 1, spin)
        self.spin_items[name] = spin

    def _build_time_widget(self, name: str) -> QWidget:
        container = QWidget()
        row_layout = QHBoxLayout(container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(2)
        spins = []
        for i, (maximum, tooltip) in enumerate(
            ((99999, tr("stats.hours")), (59, tr("stats.minutes")), (59, tr("stats.seconds")))
        ):
            spin = QSpinBox()
            spin.setRange(0, maximum)
            spin.setButtonSymbols(QSpinBox.NoButtons)  # 3 champs cote a cote, fleches inutiles/encombrantes
            spin.setToolTip(tooltip)
            spin.setAlignment(Qt.AlignCenter)
            spin.setMinimumWidth(50 if i == 0 else 36)
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(lambda _v, n=name: self._write_time(n))
            row_layout.addWidget(spin)
            if i < 2:
                row_layout.addWidget(QLabel(":"))
            spins.append(spin)
        self.time_items[name] = tuple(spins)
        return container

    def _write(self, name: str, value: int):
        if not (self.live.connected and self.live.sane):
            return
        try:
            self.live.write_stat(name, value)
        except OSError:
            pass  # refresh() reaffichera l'etat "deconnecte" au prochain cycle si le process a disparu

    def _write_time(self, name: str):
        if not (self.live.connected and self.live.sane):
            return
        h, m, s = self.time_items[name]
        total_seconds = h.value() * 3600 + m.value() * 60 + s.value()
        frames = total_seconds * FRAMES_PER_SECOND
        _, fmt = mgs4save.STATS[name]
        frames = min(frames, 0xFFFFFFFF if fmt == "<I" else 0xFFFF)
        try:
            self.live.write_stat(name, frames)
        except OSError:
            pass  # refresh() reaffichera l'etat "deconnecte" au prochain cycle si le process a disparu

    def set_advanced(self, advanced: bool):
        pass  # pas de mode simple/avance distinct ici, deja tout en "brut"

    def refresh(self):
        connected = self.live.connected and self.live.sane
        for name in self.names:
            try:
                value = self.live.read_stat(name) if connected else None
            except OSError:
                value = None

            if name == "objets_speciaux_bitmask":
                combo = self.special_items_combo
                combo.setEnabled(connected)
                if value is not None and not combo.hasFocus():
                    combo.blockSignals(True)
                    combo.setCurrentIndex(combo.findData(value))  # -1 si bits inconnus actifs
                    combo.blockSignals(False)
                continue

            if name.endswith("_frames"):
                h, m, s = self.time_items[name]
                for spin in (h, m, s):
                    spin.setEnabled(connected)
                if value is not None and not (h.hasFocus() or m.hasFocus() or s.hasFocus()):
                    for spin, part in zip((h, m, s), _frames_to_hms_parts(value)):
                        spin.blockSignals(True)
                        spin.setValue(part)
                        spin.blockSignals(False)
                continue

            spin = self.spin_items[name]
            spin.setEnabled(connected)
            if value is not None and not spin.hasFocus():
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        for header, table, field_names in self.sections:
            any_visible = False
            for row, name in enumerate(field_names):
                display = table.item(row, 0).text()
                visible = not text or text in display.lower() or text in name.lower()
                table.setRowHidden(row, not visible)
                any_visible = any_visible or visible
            header.setVisible(any_visible)
            table.setVisible(any_visible)
