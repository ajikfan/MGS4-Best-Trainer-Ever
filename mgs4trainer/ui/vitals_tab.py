"""Onglet Etat de jeu (reglages en direct, jauges, profils)."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QScrollArea, QSlider, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

import mgs4save

from mgs4trainer.core.gamedata import ALERT_STATE_NAMES, VITALS
from mgs4trainer.core.i18n import alert_state_name, tr, vital_display_name
from mgs4trainer.live import MGS4Live
from mgs4trainer.ui.common import AMMO_LOCK_REFRESH_MS, warn_dialog
from mgs4trainer.ui.photo_help import PhotoControlsDialog


class VitalsTab(QWidget):
    """Onglet "Etat de jeu" : Sante/Stamina/Stress/Batterie Solid
    Eye/Sante Metal Gear REX (live.read_vital_percent/write_vital_percent,
    voir VITALS) via un curseur 0-100% (pas la valeur brute - la vraie
    borne max de chaque champ est lue en live et sert a convertir), avec
    une case "Verrouiller" par ligne (reecrit le pourcentage a chaque
    rafraichissement - "vie infinie" etc.), plus l'etat d'alerte en
    lecture seule (l'ecriture ne tient pas, voir ALERT_STATE_RVA)."""

    # Mapping asymetrique centre sur 0 = vitesse normale (1.0x) : moitie
    # gauche du curseur (-100..0) va de 10% a 100%, moitie droite (0..100)
    # de 100% a 300% - le curseur reste visuellement symetrique (demande
    # explicite de l'utilisateur : "au milieu pour la vitesse normale")
    # meme si la plage de vitesses couverte ne l'est pas.
    SPEED_SLIDER_RANGE = (-100, 100)
    SPEED_SLOWDOWN_FLOOR = 0.1  # multiplicateur au bout gauche (-100)
    SPEED_BOOST_CEILING = 3.0  # multiplicateur au bout droit (+100)

    @classmethod
    def _speed_from_slider(cls, value: int) -> float:
        if value <= 0:
            return 1.0 + (value / 100) * (1.0 - cls.SPEED_SLOWDOWN_FLOOR)
        return 1.0 + (value / 100) * (cls.SPEED_BOOST_CEILING - 1.0)

    def __init__(self, live: MGS4Live):
        super().__init__()
        self.live = live
        self.value_labels: dict[str, QLabel] = {}
        self.sliders: dict[str, QSlider] = {}
        self.lock_checks: dict[str, QCheckBox] = {}
        self.locked_percents: dict[str, float] = {}
        # Maximum de chaque jauge du joueur (grip, oxygene), voir
        # PLAYER_GAUGE_ROWS.
        self._gauge_max = {name: self.PLAYER_GAUGE_MAX for name in self.PLAYER_GAUGE_ROWS}
        # "Munitions infinies" : drapeau d'arme du jeu (MGS4Live.
        # set_infinite_ammo) depuis le 2026-10-04, plus de reecriture des
        # reserves (l'ancienne boucle faisait ramer le trainer).

        # Difficulte d'un profil choisi avant l'accrochage, ecrite par
        # sync_to_game (la liste se recale sur le jeu a chaque rafraichissement).
        self._pending_difficulty: int | None = None

        layout = QVBoxLayout(self)

        # Regroupement en QGroupBox par theme (demande utilisateur
        # 2026-10-01 : l'onglet devenait trop charge en controles empiles
        # a plat) - purement visuel, aucun changement de comportement des
        # widgets eux-memes (meme noms, memes connexions).
        speed_group = QGroupBox(tr("vitals.speed_group"))
        speed_layout = QVBoxLayout(speed_group)

        speed_row = QHBoxLayout()
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(*self.SPEED_SLIDER_RANGE)
        self.speed_slider.setValue(0)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self.speed_slider, 1)
        self.speed_value_label = QLabel("100 %")
        self.speed_value_label.setMinimumWidth(60)
        speed_row.addWidget(self.speed_value_label)
        self.pause_check = QCheckBox(tr("vitals.pause"))
        self.pause_check.toggled.connect(self._on_pause_toggled)
        speed_row.addWidget(self.pause_check)
        self.timer_freeze_check = QCheckBox(tr("vitals.timer_freeze"))
        self.timer_freeze_check.setToolTip(tr("vitals.timer_freeze_tooltip"))
        self.timer_freeze_check.toggled.connect(self._on_timer_freeze_toggled)
        speed_row.addWidget(self.timer_freeze_check)
        speed_layout.addLayout(speed_row)

        difficulty_row = QHBoxLayout()
        difficulty_row.addWidget(QLabel(tr("vitals.difficulty")))
        self.difficulty_combo = QComboBox()
        for score in sorted(mgs4save.DIFFICULTY_NAMES):
            self.difficulty_combo.addItem(tr(f"difficulty.{score}"), score)
        self.difficulty_combo.setToolTip(tr("vitals.difficulty_tooltip"))
        self.difficulty_combo.activated.connect(self._on_difficulty_changed)
        difficulty_row.addWidget(self.difficulty_combo)
        difficulty_row.addStretch(1)
        speed_layout.addLayout(difficulty_row)
        layout.addWidget(speed_group)

        # Outils de partie (2026-10-24) : mode photo et boutons d'action,
        # sortis du groupe Vitesse (trop charge).
        tools_group = QGroupBox(tr("vitals.tools_group"))
        tools_row = QHBoxLayout(tools_group)
        # Mode photo (2026-10-23) : la case est pilotee par TrainerWindow
        # (raccourcis clavier, camera libre ; voir live/camera.py) ; ses
        # commandes sont dans une fenetre a part (ui/photo_help.py).
        self.photo_check = QCheckBox(tr("vitals.photo_mode"))
        self.photo_check.setToolTip(tr("vitals.photo_mode_tooltip"))
        tools_row.addWidget(self.photo_check)
        photo_help_btn = QPushButton(tr("vitals.photo_controls"))
        photo_help_btn.clicked.connect(lambda: PhotoControlsDialog(self).exec())
        tools_row.addWidget(photo_help_btn)
        tools_separator = QFrame()
        tools_separator.setFrameShape(QFrame.VLine)
        tools_separator.setFrameShadow(QFrame.Sunken)
        tools_row.addWidget(tools_separator)
        # Salle blanche (2026-10-23) : MGS4Live.beauty_to_white_room.
        self.white_room_btn = QPushButton(tr("vitals.white_room"))
        self.white_room_btn.setToolTip(tr("vitals.white_room_tooltip"))
        self.white_room_btn.clicked.connect(self._on_white_room)
        tools_row.addWidget(self.white_room_btn)
        # Retour au menu principal (2026-10-23) : MGS4Live.return_to_title.
        self.title_btn = QPushButton(tr("vitals.return_to_title"))
        self.title_btn.setToolTip(tr("vitals.return_to_title_tooltip"))
        self.title_btn.clicked.connect(self._on_return_to_title)
        tools_row.addWidget(self.title_btn)
        tools_row.addStretch(1)
        layout.addWidget(tools_group)

        alert_group = QGroupBox(tr("vitals.alert_group"))
        alert_layout = QVBoxLayout(alert_group)

        alert_row = QHBoxLayout()
        alert_row.addWidget(QLabel(tr("vitals.alert_real_state")))
        self.alert_label = QLabel("?")
        self.alert_label.setStyleSheet("font-weight: bold;")
        alert_row.addWidget(self.alert_label)
        alert_row.addStretch(1)
        alert_layout.addLayout(alert_row)

        force_row = QHBoxLayout()
        force_row.addWidget(QLabel(tr("vitals.alert_force")))
        self.alert_force_combo = QComboBox()
        self.alert_force_combo.addItem(tr("vitals.alert_auto"))
        for state_value in sorted(ALERT_STATE_NAMES):
            self.alert_force_combo.addItem(alert_state_name(state_value))
        self.alert_force_combo.setToolTip(tr("vitals.alert_force_tooltip"))
        self.alert_force_combo.activated.connect(self._on_alert_force_changed)
        force_row.addWidget(self.alert_force_combo)
        force_row.addStretch(1)
        alert_layout.addLayout(force_row)

        self.no_alerts_check = QCheckBox(tr("vitals.no_alerts"))
        self.no_alerts_check.setToolTip(tr("vitals.no_alerts_tooltip"))
        self.no_alerts_check.toggled.connect(self._on_no_alerts_toggled)
        alert_layout.addWidget(self.no_alerts_check)
        layout.addWidget(alert_group)

        # Toute la zone (2026-10-13) : sommeil et emotions sur tous les
        # soldats eveilles, voir MGS4Live.zone_action.
        zone_group = QGroupBox(tr("vitals.zone_group"))
        zone_group.setToolTip(tr("vitals.zone_tooltip"))
        zone_layout = QVBoxLayout(zone_group)
        zone_row = QHBoxLayout()
        zone_layout.addLayout(zone_row)
        zone_row.addWidget(QLabel(tr("vitals.zone_target")))
        self.zone_target_combo = QComboBox()
        for target in self.live.ZONE_TARGETS:
            self.zone_target_combo.addItem(tr(f"vitals.zone_target_{target}"), target)
        zone_row.addWidget(self.zone_target_combo)
        self.zone_buttons = [self.zone_target_combo]
        for action in ("kill", "knockout", "sleep", "laugh", "cry", "rage", "scream"):
            button = QPushButton(tr(f"vitals.zone_{action}"))
            button.setToolTip(tr("vitals.zone_tooltip"))
            button.clicked.connect(lambda _checked=False, a=action: self._on_zone_action(a))
            zone_row.addWidget(button)
            self.zone_buttons.append(button)
        zone_row.addStretch(1)
        # Attitude des rebelles (maintenue dans refresh, voir
        # MGS4Live.maintain_rebel_attitude).
        rebels_row = QHBoxLayout()
        self.rebels_check = QCheckBox(tr("vitals.rebels"))
        self.rebels_check.setToolTip(tr("vitals.rebels_tooltip"))
        rebels_row.addWidget(self.rebels_check)
        pill, self.rebels_neutral_btn, self.rebels_hostile_btn, self._rebels_group = self._build_pill_toggle(
            tr("vitals.rebels_neutral"), tr("vitals.rebels_hostile")
        )
        rebels_row.addWidget(pill)
        rebels_row.addStretch(1)
        zone_layout.addLayout(rebels_row)
        self.zone_buttons += [self.rebels_check, self.rebels_neutral_btn, self.rebels_hostile_btn]
        layout.addWidget(zone_group)

        weapons_group = QGroupBox(tr("vitals.weapons_group"))
        weapons_layout = QVBoxLayout(weapons_group)

        weapons_row = QHBoxLayout()
        self.infinite_ammo_check = QCheckBox(tr("vitals.infinite_ammo"))
        self.infinite_ammo_check.setToolTip(tr("vitals.infinite_ammo_tooltip"))
        self.infinite_ammo_check.toggled.connect(self._on_infinite_ammo_toggled)
        weapons_row.addWidget(self.infinite_ammo_check)
        self.no_reload_check = QCheckBox(tr("vitals.no_reload"))
        self.no_reload_check.setToolTip(tr("vitals.no_reload_tooltip"))
        self.no_reload_check.toggled.connect(self._on_no_reload_toggled)
        weapons_row.addWidget(self.no_reload_check)
        self.infinite_silencer_check = QCheckBox(tr("vitals.infinite_silencer"))
        self.infinite_silencer_check.setToolTip(tr("vitals.infinite_silencer_tooltip"))
        self.infinite_silencer_check.toggled.connect(self._on_infinite_silencer_toggled)
        weapons_row.addWidget(self.infinite_silencer_check)
        self.instant_kill_check = QCheckBox(tr("vitals.instant_kill"))
        self.instant_kill_check.setToolTip(tr("vitals.instant_kill_tooltip"))
        self.instant_kill_check.toggled.connect(self._apply_instant_kill_mode)
        weapons_row.addWidget(self.instant_kill_check)
        pill, self.lethal_btn, self.non_lethal_btn, self._lethal_group = self._build_pill_toggle(
            tr("vitals.lethal"), tr("vitals.non_lethal")
        )
        self.lethal_btn.setToolTip(tr("vitals.lethal_tooltip"))
        self.non_lethal_btn.setToolTip(tr("vitals.non_lethal_tooltip"))
        self.lethal_btn.toggled.connect(self._apply_instant_kill_mode)
        self.non_lethal_btn.toggled.connect(self._apply_instant_kill_mode)
        weapons_row.addWidget(pill)
        weapons_row.addStretch(1)
        weapons_layout.addLayout(weapons_row)

        self.railgun_charge_check = QCheckBox(tr("vitals.railgun_charge"))
        self.railgun_charge_check.setToolTip(tr("vitals.railgun_charge_tooltip"))
        self.railgun_charge_check.toggled.connect(self._on_railgun_charge_toggled)
        weapons_layout.addWidget(self.railgun_charge_check)
        layout.addWidget(weapons_group)

        snake_group = QGroupBox(tr("vitals.snake_group"))
        snake_layout = QHBoxLayout(snake_group)
        self.untouchable_check = QCheckBox(tr("vitals.untouchable"))
        self.untouchable_check.setToolTip(tr("vitals.untouchable_tooltip"))
        self.untouchable_check.toggled.connect(self._on_untouchable_toggled)
        snake_layout.addWidget(self.untouchable_check)
        self.invisible_check = QCheckBox(tr("vitals.invisible"))
        self.invisible_check.setToolTip(tr("vitals.invisible_tooltip"))
        self.invisible_check.toggled.connect(self._on_invisible_toggled)
        snake_layout.addWidget(self.invisible_check)
        self.no_back_pain_check = QCheckBox(tr("vitals.no_back_pain"))
        self.no_back_pain_check.setToolTip(tr("vitals.no_back_pain_tooltip"))
        self.no_back_pain_check.toggled.connect(self._on_no_back_pain_toggled)
        snake_layout.addWidget(self.no_back_pain_check)
        snake_layout.addSpacing(24)
        # Evenements (2026-10-17) : MGS4Live.SNAKE_EVENTS, un choix par liste.
        snake_layout.addWidget(QLabel(tr("vitals.snake_event")))
        self.snake_event_combo = QComboBox()
        for event in self.live.SNAKE_EVENTS:
            self.snake_event_combo.addItem(tr(f"vitals.snake_event_{event}"), event)
        for motion in self.live.SNAKE_MOTIONS:
            self.snake_event_combo.addItem(tr("vitals.snake_motion", name=tr(f"motion.{motion:#x}"),
                                              motion=f"{motion:#X}".replace("0X", "0x")), motion)
        self.snake_event_combo.setMaxVisibleItems(20)
        self.snake_event_combo.setToolTip(tr("vitals.snake_event_tooltip"))
        snake_layout.addWidget(self.snake_event_combo)
        self.snake_event_button = QPushButton(tr("vitals.snake_event_trigger"))
        self.snake_event_button.setToolTip(tr("vitals.snake_event_tooltip"))
        self.snake_event_button.clicked.connect(self._on_snake_event)
        snake_layout.addWidget(self.snake_event_button)

        snake_layout.addStretch(1)
        layout.addWidget(snake_group)

        layout.addStretch(1)
        self._build_gauges_page()

        # Minuteur dedie (AMMO_LOCK_REFRESH_MS, plus rapide que le cycle
        # general REFRESH_MS) pour "Munitions infinies"/"Pas de
        # rechargement" - voir _reassert_ammo_locks.
        self.ammo_lock_timer = QTimer(self)
        self.ammo_lock_timer.timeout.connect(self._reassert_ammo_locks)
        self.ammo_lock_timer.start(AMMO_LOCK_REFRESH_MS)

    @staticmethod
    def _build_pill_toggle(left_text: str, right_text: str):
        """2 QPushButton cochables regroupes (exclusif) stylises en une
        seule "pilule" scindee en deux (coins arrondis uniquement sur les
        bords exterieurs, pas de bordure au milieu) - demande utilisateur
        2026-09-26, plus lisible qu'une paire de cases a cocher separees
        pour un choix mutuellement exclusif. Retourne (widget conteneur,
        bouton gauche, bouton droit, le QButtonGroup - a garder en vie
        c'est deja fait via le parent Qt, mais utile si l'appelant veut
        y toucher)."""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        left_btn = QPushButton(left_text)
        right_btn = QPushButton(right_text)
        base = (
            "QPushButton {{ {radius} border: 1px solid #808080;"
            " background: #808080; color: white; padding: 4px 10px; }}"
            " QPushButton:checked {{ background: #2ea3ff; border-color: #2ea3ff; }}"
        )
        left_btn.setStyleSheet(base.format(
            radius="border-top-left-radius: 13px; border-bottom-left-radius: 13px;"
                   " border-top-right-radius: 0px; border-bottom-right-radius: 0px;"
        ))
        right_btn.setStyleSheet(base.format(
            radius="border-top-right-radius: 13px; border-bottom-right-radius: 13px;"
                   " border-top-left-radius: 0px; border-bottom-left-radius: 0px;"
        ))
        for btn in (left_btn, right_btn):
            btn.setCheckable(True)
            btn.setMinimumHeight(26)
        group = QButtonGroup(container)
        group.setExclusive(True)
        group.addButton(left_btn)
        group.addButton(right_btn)
        left_btn.setChecked(True)
        row.addWidget(left_btn)
        row.addWidget(right_btn)
        return container, left_btn, right_btn, group

    # Onglet "Jauges" (2026-10-16 : le tableau unique devenait trop long et
    # cassait l'affichage d'"Etat de jeu") : toutes les jauges toujours
    # visibles (un verrou pose a l'avance sert quand on s'agrippe, plonge...),
    # rangees par groupe, page defilante. Grip, Oxygene, vehicules, allies :
    # pas dans linkvarbuf (voir MGS4Live.read_player_gauge).
    GAUGE_GROUPS = (
        ("gauges.snake_group", ("Sante", "Stamina", "Grip", "Oxygene", "Stress", "Batterie Solid Eye")),
        ("gauges.vehicles_group", ("Drebin 893", "Van", "Sante Metal Gear REX")),
        ("gauges.allies_group", ("Vie de Meryl", "Endurance de Meryl", "Vie de Johnny", "Endurance de Johnny",
                                 "Vie de Jonathan", "Endurance de Jonathan", "Vie d'Ed", "Endurance d'Ed")),
    )

    def _gauge_table(self, names, header: bool = True) -> QTableWidget:
        table = QTableWidget(len(names), 3)
        table.setHorizontalHeaderLabels([tr("table.field"), tr("table.live_value"), tr("table.lock")])
        table.horizontalHeader().setVisible(header)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setMinimumSectionSize(60)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for row, name in enumerate(names):
            self._build_row(table, row, name)
        return table

    @staticmethod
    def _fit_tables(tables, lock_width: int | None = None):
        """Memes largeurs de colonnes ; chaque tableau a la hauteur de ses
        lignes (c'est la page qui defile, pas lui)."""
        name_width = max(t.sizeHintForColumn(0) for t in tables) + 16
        lock_width = lock_width or max(t.horizontalHeader().sectionSizeHint(2) for t in tables)
        for table in tables:
            table.setColumnWidth(0, name_width)
            table.setColumnWidth(2, lock_width)
            header = 0 if table.horizontalHeader().isHidden() else table.horizontalHeader().sizeHint().height()
            table.setFixedHeight(header + sum(table.rowHeight(r) for r in range(table.rowCount()))
                                 + 2 * table.frameWidth())
        return lock_width

    def _build_gauges_page(self):
        """Page de l'onglet "Jauges", ajoutee par la fenetre principale
        (self.gauges_page) ; la logique reste dans cet onglet."""
        content = QWidget()
        content_layout = QVBoxLayout(content)
        tables, ally_tables = [], []
        for title, names in self.GAUGE_GROUPS:
            group = QGroupBox(tr(title))
            if title == "gauges.allies_group":
                group.setLayout(self._build_ally_boxes(ally_tables))
            else:
                group_layout = QVBoxLayout(group)
                table = self._gauge_table(names)
                group_layout.addWidget(table)
                tables.append(table)
            content_layout.addWidget(group)
        content_layout.addWidget(self._build_liquid_box())
        content_layout.addStretch(1)
        lock_width = self._fit_tables(tables)
        if ally_tables:
            self._fit_tables(ally_tables, lock_width)
        self.gauges_page = QScrollArea()
        self.gauges_page.setWidgetResizable(True)
        self.gauges_page.setFrameShape(QFrame.NoFrame)
        self.gauges_page.setWidget(content)

    # Rat Patrol (2026-10-18) : un encadre par membre en grille 2x2 : en tete
    # son etat en direct et le changement d'etat (MGS4Live.ally_status /
    # ally_set_state), dessous ses deux jauges ("Vie", "Endurance").
    ALLY_NAMES = {"meryl": "Meryl", "johnny": "Johnny", "jonathan": "Jonathan", "ed": "Ed"}

    def _build_ally_boxes(self, ally_tables: list) -> QGridLayout:
        grid = QGridLayout()
        self.ally_status_labels: dict[str, QLabel] = {}
        self.ally_action_combos: dict[str, QComboBox] = {}
        self.ally_action_buttons: dict[str, QPushButton] = {}
        for index, (ally, label) in enumerate(self.ALLY_NAMES.items()):
            box = QGroupBox(label)
            box_layout = QVBoxLayout(box)
            head = QHBoxLayout()
            status = QLabel("?")
            status.setStyleSheet("font-weight: bold;")
            head.addWidget(status, 1)
            combo = QComboBox()
            for action in self.live.ALLY_ACTIONS:
                combo.addItem(tr(f"ally.action.{action}"), action)
            head.addWidget(combo)
            button = QPushButton(tr("ally.apply"))
            button.clicked.connect(lambda _checked=False, a=ally: self._on_ally_action(a))
            head.addWidget(button)
            box_layout.addLayout(head)
            life_row, stamina_row = self.ALLY_LOCK_ROWS[ally]
            table = self._gauge_table((life_row, stamina_row), header=False)
            table.item(0, 0).setText(tr("gauges.ally_life"))
            table.item(1, 0).setText(tr("gauges.ally_stamina"))
            box_layout.addWidget(table)
            ally_tables.append(table)
            grid.addWidget(box, index // 2, index % 2)
            self.ally_status_labels[ally], self.ally_action_combos[ally] = status, combo
            self.ally_action_buttons[ally] = button
        return grid

    # Combat final contre Liquid Ocelot (2026-10-24) : phase en direct et
    # changement de phase (MGS4Live.liquid_status / liquid_set_phase).
    # « 3 derniers coups » : sequence finale (transition 9 du jeu).
    LIQUID_TARGETS = (1, 2, 3, 4, "last3")

    def _build_liquid_box(self) -> QGroupBox:
        box = QGroupBox(tr("gauges.liquid_group"))
        box_layout = QVBoxLayout(box)
        self.liquid_status_label = QLabel(tr("liquid.absent"))
        self.liquid_status_label.setStyleSheet("font-weight: bold;")
        box_layout.addWidget(self.liquid_status_label)
        row = QHBoxLayout()
        self.liquid_buttons: dict = {}
        for target in self.LIQUID_TARGETS:
            key = "liquid.last3" if target == "last3" else "liquid.phase"
            button = QPushButton(tr(key, number=target))
            button.setToolTip(tr(key + "_tooltip"))
            button.clicked.connect(lambda _checked=False, t=target: self._on_liquid_phase(t))
            button.setEnabled(False)
            row.addWidget(button)
            self.liquid_buttons[target] = button
        row.addStretch(1)
        box_layout.addLayout(row)
        return box

    def _on_liquid_phase(self, target):
        try:
            done = self.live.liquid_set_phase(target)
        except OSError:
            done = False
        if not done:
            warn_dialog(self, tr("gauges.liquid_group"), tr("liquid.failed"))
        self._refresh_liquid()

    def _refresh_liquid(self):
        try:
            status = self.live.liquid_status()
        except OSError:
            status = None
        if status is None:
            self.liquid_status_label.setText(tr("liquid.absent"))
        else:
            phase = status["phase"]
            name = (tr("liquid.status.phase", number=phase) if isinstance(phase, int)
                    else tr(f"liquid.status.{phase or 'other'}"))
            self.liquid_status_label.setText(tr("liquid.status", phase=name, life=status["life"],
                                                life_max=status["life_max"], stamina=status["stamina"],
                                                stamina_max=status["stamina_max"]))
        # Actifs en phase et pendant l'echange de coups final, pas pendant
        # une transition.
        phase = status["phase"] if status else None
        for target, button in self.liquid_buttons.items():
            button.setEnabled(isinstance(phase, int) or (phase == "final" and target != "last3"))

    def _on_ally_action(self, ally: str):
        try:
            self.live.ally_set_state(ally, self.ally_action_combos[ally].currentData())
        except OSError:
            pass

    def _refresh_ally_states(self):
        for ally, label in self.ally_status_labels.items():
            try:
                status = self.live.ally_status(ally)
            except OSError:
                status = "absent"
            if status.startswith("state:"):
                label.setText(tr("ally.status.state", value=status[6:]))
            else:
                label.setText(tr(f"ally.status.{status}"))
            self.ally_action_buttons[ally].setEnabled(status != "absent")

    def _build_row(self, table: QTableWidget, row: int, name: str):
        name_item = QTableWidgetItem(vital_display_name(name))
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        table.setItem(row, 0, name_item)

        control = QWidget()
        control_layout = QHBoxLayout(control)
        control_layout.setContentsMargins(4, 0, 4, 0)
        control_layout.setSpacing(6)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.valueChanged.connect(lambda value, n=name: self._on_slider_changed(n, value))
        control_layout.addWidget(slider, 1)
        self.sliders[name] = slider
        value_label = QLabel("? %")
        value_label.setMinimumWidth(90)
        control_layout.addWidget(value_label)
        self.value_labels[name] = value_label
        control.setLayout(control_layout)
        table.setCellWidget(row, 1, control)

        lock = QCheckBox()
        lock.toggled.connect(lambda checked, n=name: self._on_lock_toggled(n, checked))
        lock_wrap = QWidget()
        lock_layout = QHBoxLayout(lock_wrap)
        lock_layout.setContentsMargins(0, 0, 0, 0)
        lock_layout.addWidget(lock)
        lock_layout.setAlignment(Qt.AlignCenter)
        table.setCellWidget(row, 2, lock_wrap)
        self.lock_checks[name] = lock

    # Lignes du tableau -> jauge MGS4Live.PLAYER_GAUGES (actives seulement
    # suspendu / sous l'eau). Maximum : 2000 (valeur de depart constatee,
    # et des champs voisins), ou la plus haute valeur vue si plus grande.
    PLAYER_GAUGE_ROWS = {"Grip": "grip", "Oxygene": "oxygen", "Drebin 893": "drebin", "Van": "van",
                         "Vie de Meryl": "meryl", "Endurance de Meryl": "meryl_stamina",
                         "Vie de Johnny": "johnny", "Endurance de Johnny": "johnny_stamina",
                         "Vie de Jonathan": "jonathan", "Endurance de Jonathan": "jonathan_stamina",
                         "Vie d'Ed": "ed", "Endurance d'Ed": "ed_stamina"}
    PLAYER_GAUGE_MAX = 2000

    def _on_lock_toggled(self, name: str, checked: bool):
        if checked:
            if name in self.PLAYER_GAUGE_ROWS and self._player_gauge_inactive(name):
                # Curseur fige sur la derniere valeur vue (il ne suit la jauge
                # que quand elle est active) : verrouiller a 100 % plutot que
                # sur ce reste, sinon la jauge baisse jusqu'a lui (2026-10-10).
                slider = self.sliders[name]
                slider.blockSignals(True)
                slider.setValue(100)
                slider.blockSignals(False)
            self.locked_percents[name] = self.sliders[name].value()
        else:
            self.locked_percents.pop(name, None)
        if name in self.GAUGE_FREEZE_PATCHES:
            self._apply_gauge_freezes()

    # Jauge verrouillee : le jeu ne l'ecrit plus du tout (patch de code, voir
    # MGS4Live.CODE_PATCHES), le trainer y ecrit la valeur verrouillee - plus
    # de petites variations entre deux reecritures.
    GAUGE_FREEZE_PATCHES = {
        "Sante": "health_freeze", "Stamina": "stamina_freeze",
        "Stress": "stress_freeze", "Batterie Solid Eye": "battery_freeze",
        "Drebin 893": "drebin_freeze", "Van": "drebin_freeze",
        "Sante Metal Gear REX": "rex_freeze",
    }

    def _apply_gauge_freezes(self):
        # Un patch peut servir a plusieurs lignes (Drebin 893 et Van) : pose
        # si au moins une de ses lignes est verrouillee.
        wanted: dict[str, bool] = {}
        for name, patch in self.GAUGE_FREEZE_PATCHES.items():
            if name in self.lock_checks:
                wanted[patch] = wanted.get(patch, False) or self.lock_checks[name].isChecked()
        for patch, enabled in wanted.items():
            try:
                self.live.set_code_patch(patch, enabled)
            except OSError:
                pass

    def _on_slider_changed(self, name: str, value: int):
        if not (self.live.connected and self.live.sane):
            return
        if name in self.PLAYER_GAUGE_ROWS:
            # Sans effet quand la jauge n'est pas active (pas suspendu, hors de l'eau).
            gauge = self.PLAYER_GAUGE_ROWS[name]
            try:
                current = self.live.read_player_gauge(gauge)
                if current is not None and current >= 0:
                    self.live.write_player_gauge(gauge, round(value / 100 * self._gauge_max[name]))
            except OSError:
                pass
            if name in self.locked_percents:
                self.locked_percents[name] = value
            return
        try:
            self.live.write_vital_percent(name, value)
        except OSError:
            self.value_labels[name].setText("erreur")
            return
        if name in self.locked_percents:
            self.locked_percents[name] = value

    SPEED_STEP_PERCENT = 10

    def speed_percent(self) -> int:
        return round(self._speed_from_slider(self.speed_slider.value()) * 100)

    def set_speed_percent(self, percent: int) -> int:
        """Regle la vitesse (10-300 %) via le curseur ; renvoie la valeur retenue."""
        percent = max(10, min(300, percent))
        speed = percent / 100
        if speed <= 1.0:
            value = (speed - 1.0) / (1.0 - self.SPEED_SLOWDOWN_FLOOR) * 100
        else:
            value = (speed - 1.0) / (self.SPEED_BOOST_CEILING - 1.0) * 100
        self.speed_slider.setValue(round(value))
        return self.speed_percent()

    def _on_speed_changed(self, value: int):
        speed = self._speed_from_slider(value)
        self.speed_value_label.setText(f"{round(speed * 100)} %")
        if not (self.live.connected and self.live.sane):
            return
        self.live.set_game_speed(speed)

    def _on_pause_toggled(self, checked: bool):
        if not (self.live.connected and self.live.sane):
            return
        self.live.set_paused(checked)

    def _on_timer_freeze_toggled(self, checked: bool):
        try:
            self.live.set_code_patch("timer_freeze", checked)
        except OSError:
            pass

    def _on_white_room(self):
        try:
            done = self.live.beauty_to_white_room()
        except OSError:
            done = False
        if not done:
            warn_dialog(self, tr("vitals.white_room"), tr("vitals.white_room_none"))

    def _on_return_to_title(self):
        if not self.live.in_game():
            warn_dialog(self, tr("vitals.return_to_title"), tr("vitals.return_to_title_not_in_game"))
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("vitals.return_to_title"))
        box.setText(tr("vitals.return_to_title_confirm"))
        yes = box.addButton(tr("button.yes"), QMessageBox.AcceptRole)
        box.addButton(tr("button.no"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        try:
            done = self.live.return_to_title()
        except OSError:
            done = False
        if not done:
            warn_dialog(self, tr("vitals.return_to_title"), tr("vitals.return_to_title_failed"))

    def sync_to_game(self):
        """La DLL reste dans le jeu apres la fermeture du trainer, avec ses
        drapeaux (constate 2026-10-04 : "Pas de rechargement" encore actif
        au lancement suivant, case decochee). A chaque accrochage, on lui
        renvoie l'etat reel des cases."""
        if not (self.live.connected and self.live.sane):
            return
        if self._pending_difficulty is not None:
            try:
                if self.live.write_difficulty(self._pending_difficulty):
                    self._pending_difficulty = None
            except OSError:
                pass
        self._on_speed_changed(self.speed_slider.value())
        self._on_pause_toggled(self.pause_check.isChecked())
        self._on_timer_freeze_toggled(self.timer_freeze_check.isChecked())
        self._on_no_reload_toggled(self.no_reload_check.isChecked())
        self._on_infinite_ammo_toggled(self.infinite_ammo_check.isChecked())
        self._on_infinite_silencer_toggled(self.infinite_silencer_check.isChecked())
        self._on_no_alerts_toggled(self.no_alerts_check.isChecked())
        self._on_railgun_charge_toggled(self.railgun_charge_check.isChecked())
        self._on_untouchable_toggled(self.untouchable_check.isChecked())
        self._on_invisible_toggled(self.invisible_check.isChecked())
        self._on_no_back_pain_toggled(self.no_back_pain_check.isChecked())
        self._apply_gauge_freezes()
        self._on_alert_force_changed(self.alert_force_combo.currentIndex())
        self._apply_instant_kill_mode()

    def _apply_instant_kill_mode(self):
        """Appele par la case a cocher maitresse ET par le bouton pilule
        Letal/Non letal (les deux doivent se recalculer ensemble) - un
        seul des deux effets actif a la fois cote DLL, jamais les deux."""
        if not (self.live.connected and self.live.sane):
            return
        active = self.instant_kill_check.isChecked()
        lethal = self.lethal_btn.isChecked()
        # Soldats : patchs de code soldier_* depuis le 2026-10-13 ; l'ancien
        # hook de la DLL (motif "aob Damage") reste toujours eteint.
        self.live.set_one_shot_kill(False)
        self.live.set_non_lethal(False)
        # Ce qui n'a pas d'endurance (Gekko, tanks, vehicules, helicopteres,
        # mini Gekko, objets destructibles) est detruit dans les deux modes.
        self.live.set_machine_kill(active)
        try:
            self.live.set_code_patch("vehicles_one_shot_kill", active)
            self.live.set_code_patch("liquid_final_kill", active)
            # Les patchs Letal / Non letal partagent des sites (Crying Wolf) :
            # retirer d'abord ceux du mode inactif, puis poser ceux du mode actif.
            lethal_patches = ("soldier_one_shot_kill", "gekko_dart_kill", "minigekko_lethal", "boss_one_shot_kill")
            non_lethal_patches = ("soldier_non_lethal_kill", "gekko_non_lethal_sleep", "minigekko_non_lethal",
                                  "boss_non_lethal_kill")
            wanted = lethal_patches if active and lethal else non_lethal_patches if active else ()
            for name in lethal_patches + non_lethal_patches:
                if name not in wanted:
                    self.live.set_code_patch(name, False)
            for name in wanted:
                self.live.set_code_patch(name, True)
            self.live.set_code_patch("destructibles_one_shot_kill", active)
        except OSError:
            pass

    def _on_infinite_ammo_toggled(self, checked: bool):
        try:
            self.live.set_infinite_ammo(checked)
            self.live.set_code_patch("rex_infinite_missiles", checked)
        except OSError:
            pass

    def _on_no_reload_toggled(self, checked: bool):
        if not (self.live.connected and self.live.sane):
            return
        # Drapeau "chargeur infini" du jeu depuis le 2026-10-12 (reasserte
        # dans _reassert_ammo_locks) ; l'ancien hook de la DLL (motif "No
        # Reload") reste toujours eteint.
        self.live.set_no_reload(False)
        try:
            self.live.set_infinite_magazines(checked)
            self.live.set_code_patch("rex_gun_no_heat", checked)
        except OSError:
            pass

    def _on_zone_action(self, action: str):
        if self.live.connected and self.live.sane:
            self.live.zone_action(action, self.zone_target_combo.currentData())

    def _on_no_alerts_toggled(self, checked: bool):
        if not (self.live.connected and self.live.sane):
            return
        # Patch de code "no_alerts" depuis le 2026-10-12 ; l'ancien court-
        # circuit de la DLL (motif "aob No Alerts") reste toujours eteint.
        self.live.set_no_alerts(False)
        try:
            self.live.set_code_patch("no_alerts", checked)
        except OSError:
            pass

    def _player_gauge_inactive(self, name: str) -> bool:
        if not (self.live.connected and self.live.sane):
            return True
        try:
            value = self.live.read_player_gauge(self.PLAYER_GAUGE_ROWS[name])
        except OSError:
            return True
        return value is None or value < 0

    # Jauge d'allie verrouillee : le jeu ne l'ecrit plus (MGS4Live.
    # set_ally_write_locks, une garde par instruction d'ecriture). L'ancienne
    # invulnerabilite "coup entier" (les deux cases) n'est plus utilisee ; ses
    # listes sont videes si elle est encore posee dans le jeu.
    ALLY_LOCK_ROWS = {"meryl": ("Vie de Meryl", "Endurance de Meryl"),
                      "johnny": ("Vie de Johnny", "Endurance de Johnny"),
                      "jonathan": ("Vie de Jonathan", "Endurance de Jonathan"),
                      "ed": ("Vie d'Ed", "Endurance d'Ed")}

    def _reassert_player_gauges(self):
        self._refresh_ally_states()
        self._refresh_liquid()
        self.live.set_allies_invulnerable(set())
        self.live.set_ally_write_locks(
            {ally for ally, (life, _stamina) in self.ALLY_LOCK_ROWS.items() if life in self.locked_percents},
            {ally for ally, (_life, stamina) in self.ALLY_LOCK_ROWS.items() if stamina in self.locked_percents})
        for name, gauge in self.PLAYER_GAUGE_ROWS.items():
            label = self.value_labels[name]
            slider = self.sliders[name]
            value = self.live.read_player_gauge(gauge)
            if value is None:
                label.setText("?")
                continue
            if value < 0:
                label.setText(tr(f"vitals.{gauge}_inactive"))
                continue
            real_max = self.live.player_gauge_max(gauge)
            maxi = self._gauge_max[name] = real_max or max(self._gauge_max[name], value)
            if name in self.locked_percents:
                target = round(self.locked_percents[name] / 100 * maxi)
                if value < target:
                    self.live.write_player_gauge(gauge, target)
                    value = target
            percent = value / maxi * 100
            label.setText(f"{value} / {maxi} ({percent:.1f}%)")
            if not slider.isSliderDown():
                slider.blockSignals(True)
                slider.setValue(round(percent))
                slider.blockSignals(False)

    def _on_infinite_silencer_toggled(self, checked: bool):
        try:
            self.live.set_code_patch("infinite_silencer", checked)
        except OSError:
            pass

    def _on_untouchable_toggled(self, checked: bool):
        try:
            self.live.set_code_patch("untouchable", checked)
        except OSError:
            pass

    def _on_invisible_toggled(self, checked: bool):
        try:
            self.live.set_code_patch("invisible", checked)
        except OSError:
            pass

    def _on_no_back_pain_toggled(self, checked: bool):
        try:
            self.live.set_code_patch("no_back_pain", checked)
        except OSError:
            pass

    def _on_snake_event(self):
        try:
            self.live.trigger_snake_event(self.snake_event_combo.currentData())
        except OSError:
            pass

    def _on_railgun_charge_toggled(self, checked: bool):
        if not (self.live.connected and self.live.sane):
            return
        self.live.set_railgun_force_charge(checked)
        try:
            self.live.set_code_patch("rex_laser_full_charge", checked)
        except OSError:
            pass

    # Profils (2026-10-09) : toute la configuration de l'onglet sauf la
    # pause - vitesse, difficulte, alerte, cases, Letal/Non letal, cible et
    # attitude des rebelles du groupe "Toute la zone" (2026-10-13), et pour
    # chaque jauge son verrou et le niveau verrouille.
    PROFILE_CHECKS = (
        "no_alerts", "infinite_ammo", "no_reload", "infinite_silencer", "instant_kill",
        "railgun_charge", "untouchable", "invisible", "no_back_pain", "rebels",
        "timer_freeze",
    )

    def profile_settings(self) -> dict:
        settings = {
            "speed": self.speed_slider.value(),
            "difficulty": self.difficulty_combo.currentData(),
            "alert_force": self.alert_force_combo.currentIndex(),
            "lethal": self.lethal_btn.isChecked(),
            "rebels_hostile": self.rebels_hostile_btn.isChecked(),
            "zone_target": self.zone_target_combo.currentData(),
            "gauges": {name: {"locked": self.lock_checks[name].isChecked(),
                              "percent": round(self.locked_percents.get(name, self.sliders[name].value()))}
                       for name in self.sliders},
        }
        for key in self.PROFILE_CHECKS:
            settings[key] = getattr(self, f"{key}_check").isChecked()
        return settings

    def apply_profile(self, settings: dict):
        """Remplit l'onglet avec le profil puis le renvoie au jeu (tout de
        suite si accroche, sinon a l'accrochage via sync_to_game). Une cle
        absente vaut desactive."""
        widgets = [self.speed_slider, self.alert_force_combo, self.lethal_btn, self.non_lethal_btn]
        widgets += [getattr(self, f"{key}_check") for key in self.PROFILE_CHECKS]
        for widget in widgets:
            widget.blockSignals(True)
        self.speed_slider.setValue(int(settings.get("speed", 0)))
        self.speed_value_label.setText(f"{round(self._speed_from_slider(self.speed_slider.value()) * 100)} %")
        self.alert_force_combo.setCurrentIndex(max(0, min(int(settings.get("alert_force", 0)),
                                                          self.alert_force_combo.count() - 1)))
        (self.lethal_btn if settings.get("lethal", True) else self.non_lethal_btn).setChecked(True)
        (self.rebels_hostile_btn if settings.get("rebels_hostile") else self.rebels_neutral_btn).setChecked(True)
        target = self.zone_target_combo.findData(settings.get("zone_target", "enemies"))
        self.zone_target_combo.setCurrentIndex(max(0, target))
        for key in self.PROFILE_CHECKS:
            getattr(self, f"{key}_check").setChecked(bool(settings.get(key, False)))
        for widget in widgets:
            widget.blockSignals(False)

        gauges = settings.get("gauges", {})
        for name, slider in self.sliders.items():
            gauge = gauges.get(name, {})
            lock = self.lock_checks[name]
            if gauge.get("locked"):
                percent = max(0, min(int(gauge.get("percent", 100)), 100))
                if name in self.PLAYER_GAUGE_ROWS and percent == 0:
                    # Profil enregistre jauge inactive (curseur a 0) : un verrou
                    # a 0 % ne remonterait jamais la jauge (2026-10-10).
                    percent = 100
                slider.blockSignals(True)
                slider.setValue(percent)
                slider.blockSignals(False)
                lock.setChecked(True)
                self.locked_percents[name] = percent  # reecrit au prochain rafraichissement
            else:
                lock.setChecked(False)

        difficulty = settings.get("difficulty")
        self._pending_difficulty = difficulty if difficulty in mgs4save.DIFFICULTY_NAMES else None
        if self._pending_difficulty is not None:
            self.difficulty_combo.setCurrentIndex(self.difficulty_combo.findData(self._pending_difficulty))
        self.sync_to_game()

    def _on_difficulty_changed(self, index: int):
        try:
            self.live.write_difficulty(self.difficulty_combo.itemData(index))
        except OSError:
            pass

    def _on_alert_force_changed(self, index: int):
        """Liste : Automatique, puis les etats dans l'ordre de
        ALERT_STATE_NAMES (index - 1). Le jeu est place dans l'etape voulue
        de son propre deroule et maintenu par _reassert_ammo_locks (voir
        MGS4Live.hold_alert_state) ; en Automatique, plus aucune ecriture."""
        if not (self.live.connected and self.live.sane):
            return
        # Ancien forcage par court-circuit de la fonction de calcul (B5F120,
        # motif "Alert -- Ignore") : toujours desactive depuis le 2026-10-12.
        self.live.set_alert_mode_override(None)
        if index:
            try:
                self.live.hold_alert_state(index - 1)
            except OSError:
                pass

    def _reassert_ammo_locks(self):
        """Cycle dedie (AMMO_LOCK_REFRESH_MS, independant du
        rafraichissement general de l'UI) : certaines armes tirent assez
        vite pour vider plusieurs coups entre deux cycles a REFRESH_MS
        (750ms) avant correction, visible/genant (demande utilisateur
        2026-09-26)."""
        if not (self.live.connected and self.live.sane):
            return
        if self.infinite_ammo_check.isChecked():
            # Le jeu peut reconstruire la table des armes (chargement de
            # zone) : on reverifie le drapeau (une lecture, ecriture rare).
            try:
                self.live.set_infinite_ammo(True)
            except OSError:
                pass
        try:
            self._reassert_player_gauges()
        except OSError:
            pass
        if self.alert_force_combo.currentIndex():
            try:
                self.live.hold_alert_state(self.alert_force_combo.currentIndex() - 1)
            except OSError:
                pass
        if self.no_reload_check.isChecked():
            # Meme raison que les munitions infinies : table reconstruite
            # au chargement d'une zone.
            try:
                self.live.set_infinite_magazines(True)
            except OSError:
                pass

    def set_advanced(self, advanced: bool):
        pass  # pas de mode simple/avance distinct ici

    def refresh(self):
        if not (self.live.connected and self.live.sane):
            for label in self.value_labels.values():
                label.setText("?")
            self.alert_label.setText("?")
            self.speed_slider.setEnabled(False)
            self.pause_check.setEnabled(False)
            self.timer_freeze_check.setEnabled(False)
            self.white_room_btn.setEnabled(False)
            self.title_btn.setEnabled(False)
            self.photo_check.setEnabled(False)
            self.infinite_ammo_check.setEnabled(False)
            self.no_reload_check.setEnabled(False)
            self.infinite_silencer_check.setEnabled(False)
            self.no_alerts_check.setEnabled(False)
            self.railgun_charge_check.setEnabled(False)
            self.untouchable_check.setEnabled(False)
            self.invisible_check.setEnabled(False)
            self.no_back_pain_check.setEnabled(False)
            self.snake_event_button.setEnabled(False)
            self.alert_force_combo.setEnabled(False)
            self.difficulty_combo.setEnabled(False)
            self.instant_kill_check.setEnabled(False)
            self.lethal_btn.setEnabled(False)
            self.non_lethal_btn.setEnabled(False)
            for button in self.zone_buttons:
                button.setEnabled(False)
            return
        self.difficulty_combo.setEnabled(True)
        if not self.difficulty_combo.view().isVisible():
            try:
                index = self.difficulty_combo.findData(self.live.read_difficulty())
            except OSError:
                index = -1
            self.difficulty_combo.setCurrentIndex(index)
        self.speed_slider.setEnabled(True)
        self.pause_check.setEnabled(True)
        self.timer_freeze_check.setEnabled(True)
        self.white_room_btn.setEnabled(True)
        self.title_btn.setEnabled(True)
        self.photo_check.setEnabled(True)
        self.infinite_ammo_check.setEnabled(True)
        self.no_reload_check.setEnabled(True)
        self.infinite_silencer_check.setEnabled(True)
        self.no_alerts_check.setEnabled(True)
        self.railgun_charge_check.setEnabled(True)
        self.untouchable_check.setEnabled(True)
        self.invisible_check.setEnabled(True)
        self.no_back_pain_check.setEnabled(True)
        self.snake_event_button.setEnabled(True)
        self.alert_force_combo.setEnabled(True)
        self.instant_kill_check.setEnabled(True)
        self.lethal_btn.setEnabled(True)
        self.non_lethal_btn.setEnabled(True)
        for button in self.zone_buttons:
            button.setEnabled(True)
        if self.rebels_check.isChecked():
            try:
                self.live.maintain_rebel_attitude("hostile" if self.rebels_hostile_btn.isChecked() else "neutral")
            except OSError:
                pass

        for name in VITALS:
            # Jauge verrouillee : le patch de gel (GAUGE_FREEZE_PATCHES)
            # empeche deja le jeu d'ecrire ; on n'ecrit que si la valeur s'est
            # ecartee (2026-10-18 : plus de reecriture a chaque rafraichissement).
            if name in self.locked_percents:
                try:
                    target = round(self.live.read_vital_max(name) * self.locked_percents[name] / 100)
                    if self.live.read_vital(name) != target:
                        self.live.write_vital(name, target)
                except OSError:
                    pass
            label = self.value_labels[name]
            slider = self.sliders[name]
            try:
                raw = self.live.read_vital(name)
                maxi = self.live.read_vital_max(name)
                percent = (raw / maxi * 100) if maxi else 0.0
            except OSError:
                label.setText("?")
                continue
            label.setText(f"{raw} / {maxi} ({percent:.1f}%)")
            if not slider.isSliderDown():
                slider.blockSignals(True)
                slider.setValue(round(percent))
                slider.blockSignals(False)

        try:
            alert = self.live.read_alert_state()
            self.alert_label.setText(alert_state_name(alert) if alert in ALERT_STATE_NAMES else tr("alert.unknown", value=alert))
        except OSError:
            self.alert_label.setText("?")
