"""Onglet tableau generique (objets, armes)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

import mgs4save

from mgs4trainer.core.i18n import tr
from mgs4trainer.live import MGS4Live


class TableTab(QWidget):
    """Un onglet (une categorie du tableau objets, ou le tableau armes) :
    tableau ID/Nom/Etat + controles d'ecriture par ligne, un par ID de
    `ids` (pas forcement une plage continue). `reader`/`writer` donnent
    acces a la case memoire correspondante, `quick_states` est la liste des
    etats proposes dans le menu deroulant [(label, valeur), ...] - choisir
    une entree ecrit immediatement, pas besoin de bouton "OK" separe.
    La valeur brute et le controle "definir une valeur arbitraire" sont
    reserves au mode avance (masques par defaut, voir set_advanced) ; les
    munitions restent toujours visibles (simple quantite a editer, pas une
    fonctionnalite "avancee")."""

    def __init__(self, live: MGS4Live, ids: list[int], names: dict[int, str], placeholder: str,
                 reader, writer, quick_states: list[tuple[str, int]],
                 ammo_reader=None, ammo_writer=None, quantity_ids: set[int] | None = None,
                 binary_lock_value: int | None = None, battery_link: tuple[int, int] | None = None,
                 confirmed_ids: set[int] | None = None, show_filter: bool = True, fit_height: bool = False,
                 advanced_only_ids: set[int] | None = None, readonly_ids: set[int] | None = None,
                 equip_action=None, equip_ids: set[int] | None = None, equip_available=None,
                 ammo_header: str | None = None, ammo_max: int = 0xFFFF,
                 customize_action=None, customize_ids: set[int] | None = None):
        super().__init__()
        self.live = live
        # Colonne "Accessoires" (bouton par ligne) pour les ID de
        # customize_ids : customize_action(item_id, parent) ouvre la
        # personnalisation de l'arme.
        self.customize_action = customize_action
        self.customize_ids = customize_ids or set()
        self.customize_buttons: dict[int, QPushButton] = {}
        # Colonne "Munitions" reutilisable pour une autre quantite par
        # ligne (ex. nombre de silencieux, section Accessoires).
        self.ammo_header = ammo_header or tr("table.ammo")
        self.ammo_max = ammo_max
        # Colonne "Equiper" (bouton par ligne) pour les ID de equip_ids :
        # equip_action(item_id) demande l'equipement en direct (voir
        # MGS4Live._start_equip). equip_available() (optionnel) renvoie les
        # ID equipables en ce moment : les autres boutons sont grises a
        # chaque rafraichissement (ex. armes absentes de la liste du jeu).
        self.equip_action = equip_action
        self.equip_ids = equip_ids or set()
        self.equip_available = equip_available
        self.equip_buttons: dict[int, QPushButton] = {}
        # ID affiches avec leur vraie valeur mais non modifiables (menu Etat
        # et controle brut grises) - ex. motifs OctoCamo donnes d'office par
        # le jeu, ou lies au compte (voir OctoCamoTab).
        self.readonly_ids = readonly_ids or set()
        self.ids = ids
        self.names = names
        self.placeholder = placeholder
        self.reader = reader
        self.writer = writer
        # ID masques en mode simple, visibles seulement en mode avance -
        # sert a cacher les entrees dangereuses (ex. "Destabil.SOP" 0x44,
        # qui fait planter le jeu si equipe, voir notes.md 2026-09-24) a
        # un utilisateur non averti, tout en gardant l'acces pour la
        # recherche. self._advanced/self._filter_text suivent l'etat
        # courant pour que _apply_filter() puisse recombiner les deux
        # conditions (filtre texte ET verrou avance) a chaque appel.
        self.advanced_only_ids = advanced_only_ids or set()
        self._advanced = False
        self._filter_text = ""
        # Mecanisme generique herite de l'epoque ou seuls certains ID
        # d'armes avaient une adresse d'etat fiable (avant la decouverte
        # de weapon_state_rva(), voir notes.md 2026-09-24) : si defini,
        # les ID hors de cet ensemble ont leur menu Etat/controle "Definir
        # (brut)" desactives et laisses vides plutot que d'afficher une
        # valeur potentiellement trompeuse. Plus utilise pour l'onglet
        # Armes (toujours None desormais), garde au cas ou une future
        # table aurait le meme besoin.
        self.confirmed_ids = confirmed_ids
        # Si defini : TOUTES les lignes de cet onglet utilisent un menu a
        # exactement 2 etats (Verrouille/Deverrouille) au lieu du systeme
        # quick_states+"Autre" - Deverrouille = n'importe quelle valeur
        # differente de binary_lock_value, pas une correspondance exacte
        # figee (utile pour les objets, ou meme les booleens ont une seule
        # valeur "obtenu"=1 alors que les quantites peuvent valoir autre
        # chose). Les armes (3 etats reels : non possedee/verrouillee/
        # utilisable) n'utilisent PAS ce mode, elles gardent quick_states.
        self.binary_lock_value = binary_lock_value
        self.quick_states = quick_states
        self.ammo_reader = ammo_reader
        self.ammo_writer = ammo_writer
        self.has_ammo = ammo_reader is not None
        # IDs "a quantite" (ex. Ration/Nouilles/Regain...) : pas de valeur
        # "Obtenu" fixe qui aurait sens (une ration ne s'"obtient" pas a une
        # valeur precise, elle s'empile) - dropdown reduit a "Verrouille"
        # pour ces lignes, avec une colonne Quantite toujours visible a la
        # place (memes reader/writer que la valeur brute, juste affichee en
        # priorite et sans etre reservee au mode avance).
        self.quantity_ids = quantity_ids or set()
        # Cas particulier Batterie (Solid Eye) : (id_batterie, id_solid_eye).
        # La batterie n'a pas d'etat verrouille/deverrouille a elle - elle
        # suit celui du Solid Eye (pas de Solid Eye = pas de batterie du
        # tout, meme "de base"). Affichage 1-6 (jamais 0 : une batterie de
        # base est toujours installee), stockage brut 0-5 (+1 pour
        # l'affichage, -1 a l'ecriture) - meme convention que
        # read_battery_count()/BATTERY_MAX dans mgs4save.py.
        self.battery_link = battery_link
        if battery_link is not None:
            self.quantity_ids = self.quantity_ids | {battery_link[0]}
        self.has_quantity = bool(self.quantity_ids)
        self.state_combos: dict[int, QComboBox] = {}
        self.value_items: dict[int, QTableWidgetItem] = {}
        self.spin_items: dict[int, QSpinBox] = {}
        # Une seule colonne pour les lignes a quantite/munitions (le
        # spinbox affiche deja la valeur courante - pas besoin d'une
        # colonne d'affichage separee en plus, c'etait redondant).
        self.ammo_controls: dict[int, tuple[QSpinBox, QPushButton]] = {}
        self.quantity_controls: dict[int, tuple[QSpinBox, QPushButton]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.filter_edit = QLineEdit()
        if show_filter:
            filter_row = QHBoxLayout()
            filter_row.addWidget(QLabel(tr("table.filter_id_name")))
            self.filter_edit.textChanged.connect(self._apply_filter)
            filter_row.addWidget(self.filter_edit)
            layout.addLayout(filter_row)

        headers = [tr("table.id"), tr("table.name"), tr("table.state"), tr("table.raw_value")]
        headers.append(tr("table.set_raw"))
        if self.has_quantity:
            headers.append(tr("table.quantity"))
        if self.has_ammo:
            headers.append(self.ammo_header)
        if self.equip_action is not None:
            headers.append(tr("table.equip"))
        if self.customize_action is not None:
            headers.append(tr("table.customize"))
        self.col_state = 2
        self.col_value = 3
        self.col_control = 4
        col = 5
        self.col_control_quantity = col if self.has_quantity else None
        col += 1 if self.has_quantity else 0
        self.col_control_ammo = col if self.has_ammo else None
        col += 1 if self.has_ammo else 0
        self.col_equip = col if self.equip_action is not None else None
        col += 1 if self.equip_action is not None else 0
        self.col_customize = col if self.customize_action is not None else None
        # Colonnes masquees par defaut (mode simple) - voir set_advanced.
        # Quantite/Munitions restent toujours visibles (edition normale,
        # pas "avancee").
        self.advanced_columns = [self.col_value, self.col_control]

        self.table = QTableWidget(len(ids), len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        # Garde-fou : sans ca, une colonne large peut ecraser "Nom" a
        # quasi 0 (deja vu). "Nom" est en Stretch, donc profite de tout
        # l'espace rendu disponible par ce plancher sur les autres colonnes.
        self.table.horizontalHeader().setMinimumSectionSize(90)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        for row, item_id in enumerate(ids):
            self._build_row(row, item_id)
            if self.col_equip is not None and item_id in self.equip_ids:
                equip_btn = QPushButton(tr("equip.button"))
                equip_btn.clicked.connect(lambda _checked=False, i=item_id: self._on_equip(i))
                self.table.setCellWidget(row, self.col_equip, equip_btn)
                self.equip_buttons[item_id] = equip_btn
            if self.col_customize is not None and item_id in self.customize_ids:
                custom_btn = QPushButton(tr("customize.button"))
                custom_btn.clicked.connect(lambda _checked=False, i=item_id: self._on_customize(i))
                self.table.setCellWidget(row, self.col_customize, custom_btn)
                self.customize_buttons[item_id] = custom_btn

        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(3)
        self._cap_column_width(self.col_control, 300)
        if self.has_quantity:
            self._cap_column_width(self.col_control_quantity, 220)
        if self.has_ammo:
            self._cap_column_width(self.col_control_ammo, 220)

        self.set_advanced(False)

        if fit_height:
            # Utilise dans une section empilee (GroupedWeaponsTab) : la
            # table adopte exactement la hauteur de ses lignes, c'est le
            # QScrollArea englobant qui gere le defilement global plutot
            # que chaque petite table individuellement.
            row_h = self.table.rowHeight(0) if len(ids) else 30
            total_h = self.table.horizontalHeader().height() + row_h * len(ids) + 2 * self.table.frameWidth() + 4
            self.table.setFixedHeight(total_h)
            self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def _on_equip(self, item_id: int):
        if not (self.live.connected and self.live.sane):
            return
        try:
            self.equip_action(item_id)
        except OSError:
            pass

    def _on_customize(self, item_id: int):
        if not (self.live.connected and self.live.sane):
            return
        self.customize_action(item_id, self)

    def set_advanced(self, advanced: bool):
        self._advanced = advanced
        for col in self.advanced_columns:
            self.table.setColumnHidden(col, not advanced)
        if self.advanced_only_ids:
            self._apply_filter(self._filter_text)

    def _cap_column_width(self, col: int, max_width: int):
        self.table.resizeColumnToContents(col)
        if self.table.columnWidth(col) > max_width:
            self.table.setColumnWidth(col, max_width)

    def _build_row(self, row: int, item_id: int):
        id_item = QTableWidgetItem(f"{item_id:#04x}")
        id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, id_item)

        name = self.names.get(item_id, self.placeholder.format(item_id))
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 1, name_item)

        is_quantity_row = item_id in self.quantity_ids
        is_battery_row = self.battery_link is not None and item_id == self.battery_link[0]
        is_unconfirmed_row = self.confirmed_ids is not None and item_id not in self.confirmed_ids
        combo = QComboBox()
        if self.binary_lock_value is not None:
            # Exactement 2 etats, pas de "Autre" : sentinelle (verrouille/
            # non possede) ou n'IMPORTE quelle autre valeur (deverrouille/
            # utilisable - une ration a 15 ou 42 en stock est tout autant
            # "deverrouille" qu'un objet simplement "obtenu", pas une
            # correspondance exacte figee ; idem pour une arme a 1 ou 2,
            # voir BINARY_CATEGORIES). Libelles et valeur d'ecriture pris
            # dans quick_states (index 0 = sentinelle, index 1 = le reste).
            combo.addItem(self.quick_states[0][0], self.binary_lock_value)
            combo.addItem(self.quick_states[1][0], self.quick_states[1][1])
        else:
            for label, value in self.quick_states:
                combo.addItem(label, value)
            # Pas d'entree "Autre" grisee (inutile, jamais choisissable) -
            # si la valeur ne correspond a aucun etat connu, le menu reste
            # simplement vide (setCurrentIndex(-1) dans refresh()), la
            # vraie valeur restant visible via "Valeur brute".
        combo.currentIndexChanged.connect(
            lambda idx, i=item_id, c=combo: self._on_combo_changed(i, c)
        )
        if is_battery_row:
            # Pas d'etat propre - reflet en lecture seule de celui du
            # Solid Eye, mis a jour dans refresh().
            combo.setEnabled(False)
        if is_unconfirmed_row:
            # confirmed_ids defini et cet ID en dehors - menu laisse vide
            # plutot que trompeur (voir commentaire sur self.confirmed_ids).
            combo.setEnabled(False)
        if item_id in self.readonly_ids:
            combo.setEnabled(False)
        self.table.setCellWidget(row, self.col_state, combo)
        self.state_combos[item_id] = combo

        value_item = QTableWidgetItem("?")
        value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.col_value, value_item)
        self.value_items[item_id] = value_item

        control = QWidget()
        control_layout = QHBoxLayout(control)
        control_layout.setContentsMargins(2, 0, 2, 0)
        control_layout.setSpacing(4)
        spin = QSpinBox()
        spin.setRange(0, 0xFFFF)
        spin.setMinimumWidth(65)
        control_layout.addWidget(spin)
        self.spin_items[item_id] = spin
        apply_btn = QPushButton(tr("button.ok"))
        apply_btn.clicked.connect(lambda _checked=False, i=item_id, s=spin: self._write(i, s.value()))
        control_layout.addWidget(apply_btn)
        control.setLayout(control_layout)
        control.adjustSize()
        if is_unconfirmed_row or item_id in self.readonly_ids:
            spin.setEnabled(False)
            apply_btn.setEnabled(False)
        self.table.setCellWidget(row, self.col_control, control)

        if self.has_quantity:
            qty_control = QWidget()
            qty_layout = QHBoxLayout(qty_control)
            qty_layout.setContentsMargins(2, 0, 2, 0)
            qty_layout.setSpacing(4)
            qty_spin = QSpinBox()
            if is_battery_row:
                # Affichage 1-BATTERY_MAX (jamais 0, une batterie de base
                # est toujours installee) - voir read_battery_count() dans
                # mgs4save.py. Ecriture avec le decalage -1 (stockage brut
                # 0-based).
                qty_spin.setRange(1, mgs4save.BATTERY_MAX)
                qty_ok = QPushButton(tr("button.ok"))
                qty_ok.clicked.connect(lambda _checked=False, i=item_id, s=qty_spin: self._write(i, s.value() - 1))
            else:
                qty_spin.setRange(0, 0xFFFF)
                qty_ok = QPushButton(tr("button.ok"))
                qty_ok.clicked.connect(lambda _checked=False, i=item_id, s=qty_spin: self._write(i, s.value()))
            qty_spin.setMinimumWidth(65)
            qty_layout.addWidget(qty_spin)
            qty_layout.addWidget(qty_ok)
            qty_control.setLayout(qty_layout)
            qty_control.adjustSize()
            self.table.setCellWidget(row, self.col_control_quantity, qty_control)
            self.quantity_controls[item_id] = (qty_spin, qty_ok)
            if not is_quantity_row:
                qty_spin.setEnabled(False)
                qty_ok.setEnabled(False)

        if self.has_ammo:
            ammo_control = QWidget()
            ammo_layout = QHBoxLayout(ammo_control)
            ammo_layout.setContentsMargins(2, 0, 2, 0)
            ammo_layout.setSpacing(4)
            ammo_spin = QSpinBox()
            ammo_spin.setRange(0, self.ammo_max)
            ammo_spin.setMinimumWidth(65)
            ammo_layout.addWidget(ammo_spin)
            ammo_ok = QPushButton(tr("button.ok"))
            ammo_ok.clicked.connect(lambda _checked=False, i=item_id, s=ammo_spin: self._write_ammo(i, s.value()))
            ammo_layout.addWidget(ammo_ok)
            ammo_control.setLayout(ammo_layout)
            ammo_control.adjustSize()
            self.table.setCellWidget(row, self.col_control_ammo, ammo_control)
            self.ammo_controls[item_id] = (ammo_spin, ammo_ok)

    def _on_combo_changed(self, item_id: int, combo: QComboBox):
        value = combo.currentData()
        if value is None:  # "Autre" (place-tenant) ou signal declenche par le refresh
            return
        self._write(item_id, value)

    def _write(self, item_id: int, value: int):
        if not (self.live.connected and self.live.sane):
            return
        try:
            self.writer(item_id, value)
        except OSError:
            self.value_items[item_id].setText("erreur ecriture")
        # La correction munitions 65535 -> 10 pour une arme "Utilisable"
        # est geree dans refresh() (rattrape aussi les armes deja
        # debloquees avant ce correctif, pas seulement au moment du clic) -
        # inutile de la dupliquer ici, le prochain tick (750ms) s'en charge.

    def _write_ammo(self, item_id: int, value: int):
        if not (self.live.connected and self.live.sane):
            return
        try:
            self.ammo_writer(item_id, value)
        except OSError:
            pass

    def _refresh_battery_row(self, item_id: int, raw_battery_value: int):
        _, solid_eye_id = self.battery_link
        try:
            solid_eye_value = self.reader(solid_eye_id)
        except OSError:
            return
        solid_eye_locked = solid_eye_value == self.binary_lock_value

        combo = self.state_combos.get(item_id)
        if combo is not None and not combo.view().isVisible():
            idx = 0 if solid_eye_locked else 1
            if combo.currentIndex() != idx:
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)

        qty_ctrl = self.quantity_controls.get(item_id)
        if qty_ctrl is None:
            return
        qty_spin, qty_btn = qty_ctrl
        qty_spin.setEnabled(not solid_eye_locked)
        qty_btn.setEnabled(not solid_eye_locked)
        if not solid_eye_locked and not qty_spin.hasFocus():
            displayed = 1 if raw_battery_value == 65535 else min(raw_battery_value + 1, mgs4save.BATTERY_MAX)
            qty_spin.blockSignals(True)
            qty_spin.setValue(displayed)
            qty_spin.blockSignals(False)

    def refresh(self):
        for custom_btn in self.customize_buttons.values():
            custom_btn.setEnabled(bool(self.live.connected and self.live.sane))
        if not (self.live.connected and self.live.sane):
            for item in self.value_items.values():
                item.setText("?")
            return
        if self.equip_available is not None and self.equip_buttons:
            try:
                available = set(self.equip_available())
            except OSError:
                available = set()
            for item_id, equip_btn in self.equip_buttons.items():
                equip_btn.setEnabled(item_id in available)
        state_by_id: dict[int, int] = {}
        for item_id, item in self.value_items.items():
            try:
                value = self.reader(item_id)
            except OSError:
                item.setText("?")
                continue
            state_by_id[item_id] = value
            item.setText(str(value))
            spin = self.spin_items.get(item_id)
            # Ne pas ecraser ce que l'utilisateur est en train de taper/
            # ajuster dans la molette (sinon impossible de cliquer sur les
            # fleches +/- sans que le rafraichissement live ne remette la
            # valeur d'origine entre-temps).
            if spin is not None and not spin.hasFocus():
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)

            if self.battery_link is not None and item_id == self.battery_link[0]:
                # Cas special : pas d'etat propre (suit le Solid Eye), pas
                # de correspondance directe raw<->affiche (decalage +1).
                self._refresh_battery_row(item_id, value)
                continue

            if self.confirmed_ids is not None and item_id not in self.confirmed_ids:
                # ID hors de confirmed_ids - "Valeur brute" reste visible
                # pour reference mais le menu Etat reste vide, jamais une
                # correspondance qui donnerait une fausse impression de
                # certitude.
                combo = self.state_combos.get(item_id)
                if combo is not None and combo.currentIndex() != -1:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(-1)
                    combo.blockSignals(False)
                continue

            qty_ctrl = self.quantity_controls.get(item_id)
            if qty_ctrl is not None:
                qty_spin, qty_btn = qty_ctrl
                # Verrouille (sentinelle habituelle 65535) = pas de stock a
                # ajuster tant que ce n'est pas deverrouille via le menu.
                is_quantity_row = item_id in self.quantity_ids and value != 65535
                qty_spin.setEnabled(is_quantity_row)
                qty_btn.setEnabled(is_quantity_row)
                if is_quantity_row and not qty_spin.hasFocus():
                    qty_spin.blockSignals(True)
                    qty_spin.setValue(value)
                    qty_spin.blockSignals(False)

            combo = self.state_combos.get(item_id)
            if combo is not None and not combo.view().isVisible():
                if self.binary_lock_value is not None:
                    # Binaire par construction : verrouille (sentinelle) ou
                    # deverrouille (tout le reste), pas de correspondance
                    # exacte sur une valeur figee - voir _build_row.
                    idx = 0 if value == self.binary_lock_value else 1
                else:
                    # -1 = aucun etat connu ne correspond -> menu vide,
                    # plutot qu'une entree "Autre" grisee inutile.
                    idx = combo.findData(value)
                if combo.currentIndex() != idx:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(idx)
                    combo.blockSignals(False)

        if not self.has_ammo:
            return
        for item_id, (ammo_spin, ammo_btn) in self.ammo_controls.items():
            try:
                ammo_value = self.ammo_reader(item_id)
            except OSError:
                ammo_spin.setEnabled(False)
                ammo_btn.setEnabled(False)
                continue
            if ammo_value is None:
                # Adresse munitions pas encore trouvee pour cette arme -
                # desactivee plutot que trompeuse (voir
                # CONFIRMED_WEAPON_AMMO_RVAS, a completer au fil des tests).
                ammo_spin.setEnabled(False)
                ammo_btn.setEnabled(False)
                continue
            # Arme pas "Utilisable" (Non poss./Verrouillee) : munitions
            # masquees (grisees) plutot que d'afficher la sentinelle 65535
            # habituelle sur un champ jamais initialise en jeu, qui
            # ressemble a tort a un etat "verrouille" (demande utilisateur
            # 2026-09-25). "Utilisable" est toujours la derniere entree de
            # quick_states par construction - voir _build_row.
            weapon_state = state_by_id.get(item_id)
            is_unlocked = weapon_state is None or weapon_state == self.quick_states[-1][1]
            ammo_spin.setEnabled(is_unlocked)
            ammo_btn.setEnabled(is_unlocked)
            if is_unlocked and ammo_value == 65535:
                # Meme correction que dans _write() au moment du
                # deblocage, mais ici pour les armes deja "Utilisable" au
                # moment ou ce controle est apparu (partie deja avancee,
                # deblocage arrive avant l'existence de ce correctif...) -
                # rattrape en continu plutot qu'une seule fois au clic
                # (demande utilisateur 2026-09-25). Idempotent : une fois
                # corrige a 10, ce test ne redeclenche plus rien au tour
                # suivant.
                try:
                    self.ammo_writer(item_id, 10)
                    ammo_value = 10
                except OSError:
                    pass
            if is_unlocked and not ammo_spin.hasFocus():
                ammo_spin.blockSignals(True)
                ammo_spin.setValue(ammo_value)
                ammo_spin.blockSignals(False)

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        self._filter_text = text
        for row in range(self.table.rowCount()):
            if self.ids[row] in self.advanced_only_ids and not self._advanced:
                self.table.setRowHidden(row, True)
                continue
            if not text:
                self.table.setRowHidden(row, False)
                continue
            id_text = self.table.item(row, 0).text().lower()
            name_text = self.table.item(row, 1).text().lower()
            self.table.setRowHidden(row, text not in id_text and text not in name_text)
