"""Onglet Armes et fenetre de personnalisation des accessoires."""
from PySide6.QtWidgets import (
    QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from mgs4trainer.core.i18n import tr
from mgs4trainer.live import MGS4Live
from mgs4trainer.ui.table_tab import TableTab


class WeaponAccessoryDialog(QDialog):
    """Accessoires montes sur une arme : une liste par emplacement du menu
    du jeu (Aucun + accessoires permis), ecrite des qu'on choisit. Les
    accessoires non possedes sont grises, comme dans le jeu."""

    def __init__(self, live: MGS4Live, weapon_id: int, names: dict[int, str], parent=None):
        super().__init__(parent)
        self.live = live
        self.weapon_id = weapon_id
        self.setWindowTitle(tr("customize.title", weapon=names.get(weapon_id, f"{weapon_id:#04x}")))
        layout = QVBoxLayout(self)
        form = QGridLayout()
        layout.addLayout(form)
        mounted = live.read_weapon_accessories(weapon_id)
        for row, (slot, mask, choices) in enumerate(live.weapon_accessory_slots(weapon_id)):
            form.addWidget(QLabel(tr(f"customize.slot_{slot}")), row, 0)
            combo = QComboBox()
            combo.addItem(tr("customize.none"), 0)
            for bit, accessory in choices:
                combo.addItem(names.get(accessory, f"{accessory:#04x}"), bit)
                if live.read_weapon(accessory) == 0:
                    combo.model().item(combo.count() - 1).setEnabled(False)
            current = mounted & mask
            combo.setCurrentIndex(max(combo.findData(current & -current), 0) if current else 0)
            combo.currentIndexChanged.connect(lambda _i, m=mask, c=combo: self._on_changed(m, c))
            form.addWidget(combo, row, 1)
        hint = QLabel(tr("customize.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        close_btn = QPushButton(tr("button.close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _on_changed(self, mask: int, combo: QComboBox):
        try:
            self.live.set_weapon_accessory(self.weapon_id, mask, combo.currentData() or 0)
        except OSError:
            pass


class GroupedWeaponsTab(QWidget):
    """Un seul onglet "Armes", sections empilees par categorie (meme
    regroupement que WeaponsPanel dans gui_app.py : WEAPON_CATEGORIES/
    WEAPON_GROUP_ORDER) plutot que des onglets separes par categorie -
    demande explicite de l'utilisateur pour coller a l'appli principale.
    Un seul champ de filtre en haut, qui filtre chaque section et masque
    celles qui n'ont plus aucune ligne visible."""

    # Categories dont l'etat 1 ("Verrouillee") n'a aucun effet observable
    # distinct de 2 ("Utilisable") - confirme (2026-09-24) sur le
    # Masterkey puis tous les accessoires (0x4a-0x5b) : seul 0 change
    # vraiment quelque chose en jeu. Menu reduit a 2 choix pour ces
    # categories plutot que 3, sur le meme mecanisme binaire que
    # binary_lock_value (deja utilise pour les objets).
    BINARY_CATEGORIES = {"accessory"}  # slug stable, voir WEAPON_GROUP_SLUGS

    # ID masques en mode simple (visibles seulement en mode avance) car
    # dangereux a manipuler par un utilisateur non averti - voir
    # advanced_only_ids sur TableTab. "Destabil.SOP" (0x44) fait PLANTER
    # le jeu s'il est equipe (confirme 2 fois, 2026-09-24) - objet
    # probablement pas prevu pour etre reellement utilise en solo, voir
    # notes.md.
    DANGEROUS_IDS = {0x44}

    def __init__(self, live: MGS4Live, category_ids: list[tuple[str, str, list[int]]],
                 names: dict[int, str], reader, writer, quick_states: list[tuple[str, int]],
                 ammo_reader, ammo_writer, equip_action=None, equip_available=None):
        super().__init__()
        self.live = live
        self.names = names
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
        for slug, label, ids in category_ids:
            if not ids:
                continue
            header = QLabel(f"{label} ({len(ids)})")
            header.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 6px;")
            inner_layout.addWidget(header)
            is_binary = slug in self.BINARY_CATEGORIES
            section_quick_states = (
                [(tr("weapon.state_unowned"), 0), (tr("weapon.state_usable"), 2)] if is_binary else quick_states
            )
            tab = TableTab(
                live, ids, names, tr("weapon.unclassified_format"), reader, writer, section_quick_states,
                # Accessoires : munitions des lance-grenades/Masterkey, et
                # nombre de silencieux dans la meme colonne.
                ammo_reader=live.read_accessory_amount if is_binary else ammo_reader,
                ammo_writer=live.write_accessory_amount if is_binary else ammo_writer,
                ammo_header=tr("table.ammo_quantity") if is_binary else None,
                binary_lock_value=0 if is_binary else None,
                show_filter=False, fit_height=True,
                advanced_only_ids=self.DANGEROUS_IDS,
                # Bouton "Equiper" (arme en main) sauf accessoires.
                equip_action=None if is_binary else equip_action,
                equip_ids=None if is_binary else set(ids) - self.DANGEROUS_IDS,
                equip_available=None if is_binary else equip_available,
                customize_action=None if is_binary else self._open_customize,
                customize_ids=None if is_binary else set(ids) & live.CUSTOMIZABLE_WEAPON_IDS,
            )
            inner_layout.addWidget(tab)
            self.sub_tabs.append((header, tab))
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def set_advanced(self, advanced: bool):
        for _header, tab in self.sub_tabs:
            tab.set_advanced(advanced)

    def _open_customize(self, weapon_id: int, parent: QWidget):
        try:
            dialog = WeaponAccessoryDialog(self.live, weapon_id, self.names, parent)
        except OSError:
            return
        dialog.exec()

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
