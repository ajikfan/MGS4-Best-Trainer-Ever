"""Onglets Objets et OctoCamo."""
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout,
    QWidget,
)

import mgs4save

from mgs4trainer.core.i18n import octocamo_name, tr
from mgs4trainer.live import MGS4Live
from mgs4trainer.ui.common import item_unclassified_format
from mgs4trainer.ui.table_tab import TableTab


class GroupedItemsTab(QWidget):
    """Version generalisee de GroupedWeaponsTab pour des categories
    d'objets (pas d'armes) qui doivent etre fusionnees en un seul onglet
    avec sous-sections - demande explicite de l'utilisateur (2026-09-25)
    pour que l'onglet "OctoCamo" du trainer suive la meme logique que
    CAMO_GROUPS dans gui_app.py (FaceCamo + Gilet + Octocamo empiles
    plutot que des onglets separes). Contrairement a GroupedWeaponsTab,
    pas de colonne munitions et une seule convention verrouille/obtenu
    (binary_lock_value) commune a toutes les sections - pas besoin des
    mecanismes specifiques aux armes (BINARY_CATEGORIES, DANGEROUS_IDS,
    etat 0/1/2)."""

    def __init__(self, live: MGS4Live, category_ids: list[tuple[str, list[int], dict[int, str]]],
                 reader, writer, quick_states: list[tuple[str, int]], binary_lock_value: int | None = None):
        super().__init__()
        self.sub_tabs: list[tuple[QLabel, TableTab]] = []

        layout = QVBoxLayout(self)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(tr("table.filter_id_name")))
        self.filter_edit = QLineEdit()
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit)
        layout.addLayout(filter_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        # Chaque section : (label, ids, names) ou (label, ids, names,
        # reader, writer[, readonly_ids[, equip_action, equip_ids]]) - lecteur
        # propre quand elle ne lit pas le tableau objets (ex. motifs
        # OctoCamo, voir MGS4Live.read_octocamo_state), bouton "Equiper".
        for label, ids, names, *extra in category_ids:
            if not ids:
                continue
            section_reader, section_writer = extra[:2] if extra else (reader, writer)
            section_readonly = extra[2] if len(extra) > 2 else None
            section_equip = extra[3] if len(extra) > 3 else None
            section_equip_ids = extra[4] if len(extra) > 4 else None
            header = QLabel(f"{label} ({len(ids)})")
            header.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 6px;")
            inner_layout.addWidget(header)
            tab = TableTab(
                live, ids, names, item_unclassified_format(), section_reader, section_writer, quick_states,
                binary_lock_value=binary_lock_value,
                show_filter=False, fit_height=True, readonly_ids=section_readonly,
                equip_action=section_equip, equip_ids=section_equip_ids,
            )
            inner_layout.addWidget(tab)
            self.sub_tabs.append((header, tab))
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def set_advanced(self, advanced: bool):
        for _header, tab in self.sub_tabs:
            tab.set_advanced(advanced)

    def refresh(self):
        for _header, tab in self.sub_tabs:
            tab.refresh()

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        for header, tab in self.sub_tabs:
            tab._apply_filter(text)
            visible_rows = sum(
                1 for row in range(tab.table.rowCount()) if not tab.table.isRowHidden(row)
            )
            header.setVisible(visible_rows > 0)
            tab.setVisible(visible_rows > 0)


class OctoCamoTab(GroupedItemsTab):
    """Onglet OctoCamo (2026-10-03) : sections FaceCamo/Gilet/Octocamo
    comme avant, plus une ligne "Equipe : ..." en haut (motif OctoCamo lu
    en direct). La section Octocamo ne liste que les 6 motifs stockes dans
    la partie (MGS4Live.OCTOCAMO_EDITABLE) ; changer de motif equipe reste
    du ressort du menu du jeu (la fonction qui l'applique doit tourner dans
    le fil du jeu, et les motifs speciaux ne sont charges que menu
    ouvert)."""

    def __init__(self, live: MGS4Live, *args, **kwargs):
        super().__init__(live, *args, **kwargs)
        self.live = live
        self._names_by_code = {code: name for name, code in mgs4save.OCTOCAMO_CODES.items()}
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("octocamo.equipped")))
        self.equipped_label = QLabel("?")
        self.equipped_label.setStyleSheet("font-weight: bold;")
        row.addWidget(self.equipped_label)
        row.addStretch(1)
        self.layout().insertLayout(0, row)

        # Boutons "Equiper" par ligne (voir TableTab.equip_action) : effet
        # immediat, sans menu (le visage fige le jeu une fraction de
        # seconde, le temps de recharger la tete).
        hint = QLabel(tr("equip.when_menu"))
        hint.setStyleSheet("color: gray;")
        row.insertWidget(row.count() - 1, hint)

    def _pattern_label(self, code: int) -> str:
        """Nom d'un motif : un des 21 du menu, un motif capture au nom
        connu (mgs4save.OCTOCAMO_CAPTURED_NAMES, avec son code), ou
        "motif capture (code)"."""
        name = self._names_by_code.get(code)
        if name:
            return octocamo_name(name)
        captured = mgs4save.OCTOCAMO_CAPTURED_NAMES.get(code)
        if captured:
            return f"{captured} ({code:06X})"
        return tr("octocamo.captured", code=f"{code:06X}")

    def refresh(self):
        super().refresh()
        if not (self.live.connected and self.live.sane):
            self.equipped_label.setText("?")
            return
        try:
            code = self.live.read_equipped_octocamo_code()
        except OSError:
            self.equipped_label.setText("?")
            return
        self.equipped_label.setText(self._pattern_label(code))
        # Section "Motifs memorises" (derniere) : nom de ligne mis a jour
        # en direct avec le code de l'emplacement et "porte" le cas echeant.
        _header, saved_tab = self.sub_tabs[-1]
        for row, slot in enumerate(MGS4Live.OCTOCAMO_SAVED_SLOTS):
            item = saved_tab.table.item(row, 1)
            if item is None:
                continue
            try:
                slot_code = self.live.read_octocamo_slot_code(slot)
            except OSError:
                continue
            label = tr("octocamo.slot", n=slot + 1)
            if not slot_code:
                text = f"{label} — {tr('octocamo.slot_empty')}"
            else:
                text = f"{label} — {self._pattern_label(slot_code)}"
                if slot_code == code:
                    text += f" ({tr('octocamo.slot_worn')})"
            if item.text() != text:
                item.setText(text)
