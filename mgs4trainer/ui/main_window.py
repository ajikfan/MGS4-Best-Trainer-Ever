"""Fenetre principale et point d'entree."""
import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

import mgs4save

from mgs4trainer.core.i18n import (
    SUPPORTED_LANGUAGES, WEAPON_GROUP_SLUGS, _LANG, octocamo_name,
    restart_trainer, set_language, tr, update_check_enabled, weapon_group_label,
    weapon_name,
)
from mgs4trainer.core.build import updates_available
from mgs4trainer.core.paths import PROFILES_FILE, TRAINER_ICON
from mgs4trainer.live import MGS4Live
from mgs4trainer.ui.cutscene_menu_overlay import CutsceneQuitOverlay, GameCurtain
from mgs4trainer.ui.common import (
    GENERAL_ITEM_QUANTITY_IDS, ITEM_CATEGORIES, REFRESH_MS, _FACECAMO_IDS_ORDERED,
    _FACECAMO_NAMES_VISIBLE, _VEST_NAMES_VISIBLE, item_unclassified_format, warn_dialog,
)
from mgs4trainer.ui.help import HelpDialog, TRAINER_VERSION
from mgs4trainer.ui.items_tab import OctoCamoTab
from mgs4trainer.ui.profiles import (
    PROFILE_KEYS, ProfileChooserDialog, ProfileOverlay, ProfileSaveDialog,
    _beep, load_profiles, profile_label, save_profiles,
)
from mgs4trainer.ui.stats_tab import StatsTab
from mgs4trainer.ui.table_tab import TableTab
from mgs4trainer.ui.teleport_tab import TeleportTab
from mgs4trainer.ui.vitals_tab import VitalsTab
from mgs4trainer.ui.weapons_tab import GroupedWeaponsTab


class TrainerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("window.title", version=TRAINER_VERSION))
        self.resize(1400, 640)
        self.live = MGS4Live()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top_row = QHBoxLayout()
        self.status_label = QLabel(tr("status.not_connected"))
        self.status_label.setWordWrap(True)
        top_row.addWidget(self.status_label, stretch=1)

        self.advanced_check = QCheckBox(tr("window.advanced_mode"))
        self.advanced_check.toggled.connect(self._on_advanced_toggled)
        top_row.addWidget(self.advanced_check)

        refresh_btn = QPushButton(tr("window.refresh_now"))
        refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(refresh_btn)
        reconnect_btn = QPushButton(tr("window.reconnect"))
        reconnect_btn.clicked.connect(self.try_attach)
        top_row.addWidget(reconnect_btn)
        # Mise a jour integree : absente du build Nexus (core/build.py).
        if updates_available():
            self.update_btn = QPushButton(tr("update.button"))
            self.update_btn.clicked.connect(self._open_update)
            top_row.addWidget(self.update_btn)
        self._latest_release: dict | None = None
        help_btn = QPushButton(tr("window.help"))
        help_btn.clicked.connect(lambda: HelpDialog(self).exec())
        top_row.addWidget(help_btn)

        # Profils (F1-F11, raccourcis globaux : voir register_profile_hotkeys).
        self.profiles = load_profiles()
        self.current_profile: str | None = None
        # Configuration d'avant le premier profil active, remise quand on
        # desactive (meme touche F une 2e fois) ; None si rien a remettre.
        self._saved_state: dict | None = None
        self._pending_accessories: dict[int, int] | None = None
        self.overlay = ProfileOverlay()
        # Ligne QUITTER du menu pause des cinematiques (live/cutscene_menu.py) :
        # patchs poses tant que le trainer est accroche, texte dessine par
        # CutsceneQuitOverlay ; sondage rapide, independant du rafraichissement.
        self.cutscene_overlay = CutsceneQuitOverlay()
        # Entree « Charger » du menu pause (live/load_menu.py) et rideau noir
        # du trainer (fermeture du menu apres chargement, retour au titre).
        self.curtain = GameCurtain()
        self._cutscene_timer = QTimer(self)
        self._cutscene_timer.setInterval(30)
        self._cutscene_timer.timeout.connect(self._cutscene_tick)
        self._cutscene_timer.start()
        self._hotkeys: list[int] = []
        self.profile_label = QLabel()
        self.profile_label.setToolTip(tr("profile.label_tooltip"))
        top_row.addWidget(self.profile_label)
        profile_btn = QPushButton(tr("profile.save_button"))
        profile_btn.clicked.connect(self._open_profile_save)
        top_row.addWidget(profile_btn)
        self._update_profile_label()

        self.language_combo = QComboBox()
        self._language_codes = list(SUPPORTED_LANGUAGES)
        for code in self._language_codes:
            self.language_combo.addItem(SUPPORTED_LANGUAGES[code])
        self.language_combo.setCurrentIndex(self._language_codes.index(_LANG))
        self.language_combo.activated.connect(self._on_language_changed)
        top_row.addWidget(self.language_combo)
        layout.addLayout(top_row)

        # Conteneur dedie (pas juste un layout) pour pouvoir desactiver tout
        # le bloc Drebin d'un coup si le jeu se ferme - voir refresh().
        self.drebin_container = QWidget()
        drebin_row = QHBoxLayout(self.drebin_container)
        drebin_row.setContentsMargins(0, 0, 0, 0)
        drebin_row.addWidget(QLabel(tr("window.drebin_current")))
        self.drebin_actuel_label = QLabel("?")
        self.drebin_actuel_label.setMinimumWidth(80)
        drebin_row.addWidget(self.drebin_actuel_label)
        self.drebin_actuel_spin = QSpinBox()
        self.drebin_actuel_spin.setRange(0, 2_000_000_000)
        self.drebin_actuel_spin.setMinimumWidth(110)
        drebin_row.addWidget(self.drebin_actuel_spin)
        drebin_actuel_ok = QPushButton(tr("button.ok"))
        drebin_actuel_ok.clicked.connect(self._write_drebin_actuel)
        drebin_row.addWidget(drebin_actuel_ok)

        drebin_row.addSpacing(20)
        drebin_row.addWidget(QLabel(tr("window.drebin_sales")))
        self.drebin_ventes_label = QLabel("?")
        self.drebin_ventes_label.setMinimumWidth(80)
        drebin_row.addWidget(self.drebin_ventes_label)
        self.drebin_ventes_spin = QSpinBox()
        self.drebin_ventes_spin.setRange(0, 2_000_000_000)
        self.drebin_ventes_spin.setMinimumWidth(110)
        drebin_row.addWidget(self.drebin_ventes_spin)
        drebin_ventes_ok = QPushButton(tr("button.ok"))
        drebin_ventes_ok.clicked.connect(self._write_drebin_ventes)
        drebin_row.addWidget(drebin_ventes_ok)
        drebin_row.addStretch(1)
        layout.addWidget(self.drebin_container)

        self.tabs = QTabWidget()
        self.item_tabs: list[TableTab | StatsTab | GroupedWeaponsTab] = []

        # Meme ordre d'onglets que MGS4SaveStats (gui_app.py) : Stats,
        # Armes, Objets, OctoCamo, Tenues, Statuettes, Chansons - puis
        # "Non classes" en dernier, propre a ce trainer (n'existe pas dans
        # l'appli principale).
        # drebin_actuel/drebin_total_ventes ont leur propre UI dediee et
        # validee (drebin_row ci-dessus) - exclus d'ici pour ne pas offrir
        # un 2e chemin d'edition qui contournerait la correlation/les
        # garde-fous (deja source de confusion une fois, voir notes.md).
        stats_names = [n for n in mgs4save.STATS if n not in ("drebin_actuel", "drebin_total_ventes")]
        stats_tab = StatsTab(self.live, stats_names)
        self.tabs.addTab(stats_tab, tr("tab.stats_count", count=len(stats_names)))
        self.item_tabs.append(stats_tab)

        vitals_tab = VitalsTab(self.live)
        self.vitals_tab = vitals_tab
        vitals_tab.photo_check.toggled.connect(self._on_photo_mode)
        vitals_tab.pause_check.toggled.connect(self._on_pause_overlay)
        # Mode photo : temps fige au depart (case Pause cochee), triangle (Y,
        # touche E) ou la touche Pause le relancent ou le refigent ; a la
        # sortie, la case Pause reprend son etat d'avant.
        self._photo_pause_before = False
        self._photo_toggles = 0
        self._photo_teleports = 0
        self._photo_timer = QTimer(self)
        self._photo_timer.setInterval(50)
        self._photo_timer.timeout.connect(self._photo_tick)
        self.tabs.addTab(vitals_tab, tr("tab.game_state"))
        self.tabs.addTab(vitals_tab.gauges_page, tr("tab.gauges"))
        self.tabs.addTab(vitals_tab.boss_page, tr("tab.boss"))
        self.item_tabs.append(vitals_tab)

        # Un seul onglet "Armes", sections empilees par categorie (meme
        # regroupement que WeaponsPanel dans gui_app.py : WEAPON_CATEGORIES/
        # WEAPON_GROUP_ORDER) plutot que des onglets separes par categorie
        # ou un seul gros tableau de 95 lignes. STRUCTURAL_WEAPON_IDS
        # (0x5c/0x5d/0x5e) exclus - confirmes comme jamais de vraies armes,
        # meme raison que STRUCTURAL_ITEM_IDS pour l'onglet Objets. IDs
        # sans nom dans WEAPON_NAMES (jamais identifies) exclus aussi
        # (2026-09-24, demande explicite de l'utilisateur) - la liste ne
        # montre plus que les armes confirmees, plus de lignes "Arme #NN"
        # bruyantes. Meme filtre applique cote MGS4SaveStats
        # (WeaponsPanel dans gui_app.py).
        # Plus de gating "confirmed_ids" depuis la decouverte de la formule
        # lineaire du tableau d'etat (weapon_state_rva, 2026-09-24) : l'etat
        # est desormais fiable pour TOUS les ID, pas seulement les 11
        # scannes individuellement avant. Voir notes.md.
        weapon_ids_by_group: dict[str, list[int]] = {g: [] for g in mgs4save.WEAPON_GROUP_ORDER}
        for weapon_id in range(mgs4save.WEAPON_STATE_COUNT):
            if weapon_id in mgs4save.STRUCTURAL_WEAPON_IDS:
                continue
            if weapon_id not in mgs4save.WEAPON_NAMES:
                continue
            group = mgs4save.WEAPON_CATEGORIES.get(weapon_id, "Non identifiée")
            weapon_ids_by_group[group].append(weapon_id)
        weapon_category_ids = [
            (WEAPON_GROUP_SLUGS.get(g, g), weapon_group_label(g), weapon_ids_by_group[g])
            for g in mgs4save.WEAPON_GROUP_ORDER
        ]
        weapon_names_localized = {i: weapon_name(i) for i in mgs4save.WEAPON_NAMES}

        weapons_tab = GroupedWeaponsTab(
            self.live, weapon_category_ids, weapon_names_localized,
            self.live.read_weapon, self.live.write_weapon,
            [(tr("weapon.state_unowned"), 0), (tr("weapon.state_locked"), 1), (tr("weapon.state_usable"), 2)],
            self.live.read_weapon_ammo, self.live.write_weapon_ammo,
            equip_action=self.live.equip_weapon, equip_available=self.live.read_equippable_weapon_ids,
        )
        total_weapons = sum(len(ids) for _s, _g, ids in weapon_category_ids)
        self.tabs.addTab(weapons_tab, tr("tab.weapons_count", count=total_weapons))
        self.item_tabs.append(weapons_tab)

        for key, label, names in ITEM_CATEGORIES:
            ids = sorted(names)
            tab = TableTab(
                self.live, ids, names, item_unclassified_format(),
                self.live.read_item, self.live.write_item,
                [(tr("item.state_locked"), 65535), (tr("item.state_owned"), 1)],
                quantity_ids=GENERAL_ITEM_QUANTITY_IDS if key == "items" else None,
                binary_lock_value=65535,
                battery_link=(mgs4save.BATTERY_ITEM_ID, 0x06) if key == "items" else None,
                equip_action=self.live.equip_outfit if key == "outfits" else None,
                equip_ids=set(MGS4Live.OUTFIT_EQUIP_INDEX) if key == "outfits" else None,
            )
            self.tabs.addTab(tab, f"{label} ({len(ids)})")
            self.item_tabs.append(tab)
            if key == "items":
                # Onglet "OctoCamo" fusionne juste apres "Objets" (meme
                # position qu'avant), sections FaceCamo/Gilet/Octocamo -
                # voir GroupedItemsTab et le commentaire sur
                # _FACECAMO_NAMES_VISIBLE plus haut.
                # Section Octocamo : les 21 motifs, identifies par leur code
                # (colonne ID), dans l'ordre du menu du jeu. Seuls les 6
                # stockes dans la partie sont modifiables (OCTOCAMO_EDITABLE).
                octocamo_names = {
                    code: octocamo_name(name) for name, code in mgs4save.OCTOCAMO_CODES.items()
                }
                # Lecture seule : Infiltration (= aucun motif) et les bonus
                # lies au compte (Dore/Precommande) ; les motifs donnes
                # d'office sont masquables du menu via le hook du trainer.
                octocamo_readonly = {0, *MGS4Live.OCTOCAMO_ACCOUNT_FLAG_RVAS}
                octocamo_sections = [
                    (tr("group.facecamo"), _FACECAMO_IDS_ORDERED, _FACECAMO_NAMES_VISIBLE,
                     self.live.read_item, self.live.write_item, None,
                     self.live.equip_facecamo, set(MGS4Live.FACECAMO_EQUIP_INDEX)),
                    (tr("group.vest"), sorted(_VEST_NAMES_VISIBLE), _VEST_NAMES_VISIBLE,
                     self.live.read_item, self.live.write_item, None,
                     self.live.equip_vest, set(MGS4Live.VEST_EQUIP_IDS)),
                    (tr("group.octocamo"), list(octocamo_names), octocamo_names,
                     self.live.read_octocamo_state, self.live.write_octocamo_state, octocamo_readonly,
                     self.live.equip_octocamo, set(octocamo_names)),
                    (tr("group.octocamo_saved"), list(MGS4Live.OCTOCAMO_SAVED_SLOTS),
                     {slot: tr("octocamo.slot", n=slot + 1) for slot in MGS4Live.OCTOCAMO_SAVED_SLOTS},
                     self.live.read_octocamo_slot_state, self.live.write_octocamo_slot_state, None,
                     self.live.equip_octocamo_slot, set(MGS4Live.OCTOCAMO_SAVED_SLOTS)),
                ]
                octocamo_tab = OctoCamoTab(
                    self.live, octocamo_sections,
                    self.live.read_item, self.live.write_item,
                    [(tr("item.state_locked"), 65535), (tr("item.state_owned"), 1)],
                    binary_lock_value=65535,
                )
                total_octocamo = sum(len(section[1]) for section in octocamo_sections)
                self.tabs.addTab(octocamo_tab, tr("tab.octocamo_count", count=total_octocamo))
                self.item_tabs.append(octocamo_tab)

        teleport_tab = TeleportTab(self.live)
        self.tabs.addTab(teleport_tab, tr("tab.teleport"))
        self.item_tabs.append(teleport_tab)

        layout.addWidget(self.tabs)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)

        self.try_attach()

    def try_attach(self):
        self.live.attach()
        # Injecte la DLL des l'accrochage (elle demarre a vitesse 1.0, sans
        # effet tant qu'aucun reglage n'est active) : les boutons "Equiper"
        # et les hooks sont prets sans avoir a toucher un reglage avant.
        if self.live.connected and self.live.sane and self.live.pid:
            if self.live.speed.ensure_injected(self.live.pid):
                self.vitals_tab.sync_to_game()
            self._apply_pending_accessories()
        self._apply_connection_state()

    def _apply_connection_state(self):
        """Active/desactive toute l'interface (sauf statut/Rafraichir/
        (Re)connecter) selon que le jeu repond encore ou non - avant ce
        correctif, le statut ne se remettait jamais a jour tout seul apres
        la fermeture du jeu (restait affiche "Connecte" indefiniment).
        Seul le CONTENU des onglets est desactive, pas la barre d'onglets
        (V2.1, demande utilisateur) : on peut parcourir l'interface et lire
        les infobulles sans etre accroche au jeu. Pas de risque : chaque
        ecriture reverifie elle-meme connected/sane avant d'agir."""
        self.status_label.setText(self.live.status)
        ok = self.live.connected and self.live.sane
        self.drebin_container.setEnabled(ok)
        for i in range(self.tabs.count()):
            self.tabs.widget(i).setEnabled(ok)

    def start_update_check(self):
        """Recherche discrete au lancement : rien n'est telecharge, le
        bouton signale seulement une nouvelle version."""
        if not updates_available():
            return
        from mgs4trainer.core import updater
        from mgs4trainer.ui.update_dialog import UpdateWorker
        self._update_worker = UpdateWorker()
        self._update_worker.finished.connect(self._on_update_checked)
        self._update_worker.run(updater.fetch_latest_release)

    def _on_update_checked(self, release, error):
        from mgs4trainer.core import updater
        if error is not None or not updater.is_newer(release["version"], TRAINER_VERSION):
            return
        self._latest_release = release
        self.update_btn.setText(tr("update.button_available", version=release["version"]))
        self.update_btn.setStyleSheet("font-weight: bold; color: #2e7d32;")

    def _open_update(self):
        from mgs4trainer.ui.update_dialog import UpdateDialog
        UpdateDialog(TRAINER_VERSION, self._latest_release, restart=self._restart_after_update, parent=self).exec()

    def _restart_after_update(self):
        self.close()  # closeEvent : raccourcis liberes, trainer detache du jeu
        restart_trainer()

    def _on_advanced_toggled(self, checked: bool):
        for tab in self.item_tabs:
            tab.set_advanced(checked)

    def _on_language_changed(self, index: int):
        code = self._language_codes[index]
        if code == _LANG:
            return
        # QMessageBox.question() affiche ses boutons Oui/Non standards dans
        # la langue par defaut de Qt (pas la notre) - boutons personnalises
        # via tr() pour eviter ce decalage.
        box = QMessageBox(self)
        box.setWindowTitle(tr("language.restart_title"))
        box.setText(tr("language.restart_body", language=SUPPORTED_LANGUAGES[code]))
        yes_btn = box.addButton(tr("button.yes"), QMessageBox.YesRole)
        box.addButton(tr("button.no"), QMessageBox.NoRole)
        box.exec()
        if box.clickedButton() != yes_btn:
            self.language_combo.setCurrentIndex(self._language_codes.index(_LANG))
            return
        set_language(code)
        restart_trainer()

    def refresh(self):
        # Menu pause des cinematiques ouvert : pas de rafraichissement des
        # onglets (il bloque l'interface jusqu'a 1-2 s et retardait la ligne
        # QUITTER et sa confirmation).
        if getattr(self, "_cutscene_menu_open", False):
            return
        if self.live.connected and not self.live.check_alive():
            self._apply_connection_state()
        for tab in self.item_tabs:
            tab.refresh()
        if not (self.live.connected and self.live.sane):
            self.drebin_actuel_label.setText("?")
            self.drebin_ventes_label.setText("?")
            return
        try:
            actuel = self.live.read_drebin_actuel()
            ventes = self.live.read_drebin_total_ventes()
        except OSError:
            self.drebin_actuel_label.setText("?")
            self.drebin_ventes_label.setText("?")
            return
        self.drebin_actuel_label.setText(str(actuel))
        self.drebin_ventes_label.setText(str(ventes))
        if not self.drebin_actuel_spin.hasFocus():
            self.drebin_actuel_spin.blockSignals(True)
            self.drebin_actuel_spin.setValue(actuel)
            self.drebin_actuel_spin.blockSignals(False)
        if not self.drebin_ventes_spin.hasFocus():
            self.drebin_ventes_spin.blockSignals(True)
            self.drebin_ventes_spin.setValue(ventes)
            self.drebin_ventes_spin.blockSignals(False)

    def _write_drebin_actuel(self):
        if not (self.live.connected and self.live.sane):
            return
        try:
            ok = self.live.write_drebin_actuel(self.drebin_actuel_spin.value())
        except OSError:
            self.drebin_actuel_label.setText("erreur ecriture")
            return
        if not ok:
            self.drebin_actuel_label.setText("invalide (< ventes)")

    def _write_drebin_ventes(self):
        if not (self.live.connected and self.live.sane):
            return
        try:
            ok = self.live.write_drebin_total_ventes(self.drebin_ventes_spin.value())
        except OSError:
            self.drebin_ventes_label.setText("erreur ecriture")
            return
        if not ok:
            self.drebin_ventes_label.setText("invalide (actuel < 0)")

    # Raccourcis globaux F1-F11 (RegisterHotKey) : seulement les touches
    # qui ont un profil, pour laisser les autres au jeu. WM_HOTKEY arrive
    # dans nativeEvent meme quand le jeu a le focus.
    WM_HOTKEY = 0x0312
    MOD_NOREPEAT = 0x4000
    VK_F1 = 0x70
    HOTKEY_ID_BASE = 0xB000
    # Touche Pause du clavier : coche/decoche la case Pause (toujours prise).
    VK_PAUSE = 0x13
    HOTKEY_ID_PAUSE = 0xB100
    # Pave numerique + / - / 0 : vitesse du jeu +10 %, -10 %, 100 %.
    SPEED_HOTKEYS = {0xB101: (0x6B, +1), 0xB102: (0x6D, -1), 0xB103: (0x60, 0)}
    # Mode photo (2026-10-23) : * du pave numerique l'active ou le coupe.
    # La camera se pilote avec les commandes du jeu (manette virtuelle
    # detournee, voir live/camera.py) ; c'est la DLL qui la deplace a chaque
    # image (une boucle Python etait bloquee par le reste du trainer).
    HOTKEY_ID_PHOTO = 0xB110
    VK_MULTIPLY = 0x6A
    # Touches que le jeu lit directement (hors manette virtuelle) : prises
    # par le trainer pendant le mode photo (une touche reservee par
    # RegisterHotKey n'arrive plus au jeu). Espace : Snake reagissait ; elle
    # sert a teleporter Snake a la camera (comme croix/A a la manette).
    PHOTO_BLOCKED_KEYS = {0xB111: 0x20}

    def register_profile_hotkeys(self):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = wintypes.HWND(int(self.winId()))
        for hotkey_id in self._hotkeys:
            user32.UnregisterHotKey(hwnd, hotkey_id)
        self._hotkeys = []
        for index, key in enumerate(PROFILE_KEYS):
            if key in self.profiles:
                hotkey_id = self.HOTKEY_ID_BASE + index
                if user32.RegisterHotKey(hwnd, hotkey_id, self.MOD_NOREPEAT, self.VK_F1 + index):
                    self._hotkeys.append(hotkey_id)
        if user32.RegisterHotKey(hwnd, self.HOTKEY_ID_PAUSE, self.MOD_NOREPEAT, self.VK_PAUSE):
            self._hotkeys.append(self.HOTKEY_ID_PAUSE)
        for hotkey_id, (vk, _step) in self.SPEED_HOTKEYS.items():
            if user32.RegisterHotKey(hwnd, hotkey_id, 0, vk):  # repetition autorisee (touche maintenue)
                self._hotkeys.append(hotkey_id)
        if user32.RegisterHotKey(hwnd, self.HOTKEY_ID_PHOTO, self.MOD_NOREPEAT, self.VK_MULTIPLY):
            self._hotkeys.append(self.HOTKEY_ID_PHOTO)

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG" or event_type == "windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == self.WM_HOTKEY:
                if msg.wParam in self.SPEED_HOTKEYS:
                    self._on_speed_hotkey(self.SPEED_HOTKEYS[msg.wParam][1])
                    return True, 0
                if msg.wParam in self.PHOTO_BLOCKED_KEYS:
                    self._photo_teleport()  # Espace, gardee loin du jeu pendant le mode photo
                    return True, 0
                if msg.wParam == self.HOTKEY_ID_PHOTO:
                    photo = self.vitals_tab.photo_check
                    if photo.isEnabled():
                        photo.setChecked(not photo.isChecked())
                    return True, 0
                if msg.wParam == self.HOTKEY_ID_PAUSE:
                    pause = self.vitals_tab.pause_check
                    if pause.isEnabled():
                        pause.setChecked(not pause.isChecked())
                    return True, 0
                index = msg.wParam - self.HOTKEY_ID_BASE
                if 0 <= index < len(PROFILE_KEYS):
                    self.apply_profile(PROFILE_KEYS[index], from_hotkey=True)
                    return True, 0
        return super().nativeEvent(event_type, message)

    def _on_photo_mode(self, enabled: bool):
        vitals = self.vitals_tab
        in_game = not enabled or self.live.in_game()
        try:
            ok = in_game and self.live.set_photo_mode(enabled)
        except OSError:
            ok = False
        if enabled and not ok:
            vitals.photo_check.blockSignals(True)
            vitals.photo_check.setChecked(False)
            vitals.photo_check.blockSignals(False)
            if not in_game:
                key = "vitals.photo_mode_not_in_game"
            elif self.live.photo_mode_available():
                key = "vitals.photo_mode_failed"
            else:
                key = "vitals.photo_mode_restart"
            warn_dialog(self, tr("vitals.photo_mode"), tr(key))
            return
        pause = vitals.pause_check
        if enabled:
            self._photo_pause_before = pause.isChecked()
            self._photo_toggles = self.live.speed.photo_toggles() or 0
            self._photo_teleports = self.live.speed.photo_teleports() or 0
            pause.setChecked(True)
            self._photo_timer.start()
        else:
            self._photo_timer.stop()
            pause.setChecked(self._photo_pause_before)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = wintypes.HWND(int(self.winId()))
        for hotkey_id, vk in self.PHOTO_BLOCKED_KEYS.items():
            user32.UnregisterHotKey(hwnd, hotkey_id)
            if hotkey_id in self._hotkeys:
                self._hotkeys.remove(hotkey_id)
            if enabled and user32.RegisterHotKey(hwnd, hotkey_id, 0, vk):
                self._hotkeys.append(hotkey_id)
        self.overlay.show_message(tr("overlay.photo_on" if enabled else "overlay.photo_off"), enabled, self.live.pid)

    def _on_pause_overlay(self, paused: bool):
        self.overlay.show_message(tr("overlay.pause_on" if paused else "overlay.pause_off"), not paused, self.live.pid)

    def _cutscene_tick(self):
        live = self.live
        if not (live.connected and live.sane):
            self.cutscene_overlay.hide()
            return
        try:
            if live.load_menu_install():
                event = live.load_menu_poll()
                if event == "curtain":
                    self.curtain.fade_in(live.pid)
                elif event == "uncurtain":
                    self.curtain.fade_out()
        except OSError:
            pass
        try:
            # Combat final : « Coups finaux » en attente, et premier coup qui
            # y met fin si « Un coup, un mort » est coche.
            live.liquid_tick(self.vitals_tab.instant_kill_check.isChecked())
        except OSError:
            pass
        try:
            live.boss_one_hit_tick(self.vitals_tab.instant_kill_check.isChecked())
            live.mantis_strings_tick(self.vitals_tab.untouchable_check.isChecked())
            live.mantis_one_hit_tick(self.vitals_tab.instant_kill_check.isChecked())
            live.vamp_one_hit_tick(self.vitals_tab.instant_kill_check.isChecked())
        except OSError:
            pass
        try:
            if not live.cutscene_quit_install():
                self.cutscene_overlay.hide()
                return
            menu_open, cursor, confirming = live.cutscene_menu_poll()
            if live.cutscene_title_request():
                self.curtain.fade_in(live.pid, on_done=self._curtain_to_title)
            label = live.cutscene_quit_label() if menu_open else None
        except OSError:
            self._cutscene_menu_open = False
            self.cutscene_overlay.hide()
            return
        self._cutscene_menu_open = menu_open
        # Pendant la confirmation du jeu, le menu reste dessine, assombri, sous
        # la fenetre : la 3e ligne aussi ; le rideau noir la couvre.
        show_line = menu_open and not self.curtain.isVisible()
        self.cutscene_overlay.update_menu(live.pid, show_line, cursor, label, shaded=confirming)

    def _curtain_to_title(self):
        """Rideau opaque : retour au menu principal, puis rideau retire une
        fois l'ecran titre en place."""
        try:
            self.live.return_to_title()
        except OSError:
            pass
        QTimer.singleShot(1500, self.curtain.fade_out)

    def _photo_teleport(self):
        photo = self.vitals_tab.photo_check
        if not photo.isChecked():
            return
        if self.live.teleport_to_camera():
            self.overlay.show_message(tr("overlay.photo_teleport"), True, self.live.pid)
        else:
            self.overlay.show_message(tr("overlay.photo_teleport_failed"), False, self.live.pid)

    def _photo_tick(self):
        teleports = self.live.speed.photo_teleports()
        if teleports is not None and teleports != self._photo_teleports:
            self._photo_teleports = teleports
            self._photo_teleport()
        self.live.update_photo_direct()
        toggles = self.live.speed.photo_toggles()
        if toggles is None or toggles == self._photo_toggles:
            return
        if (toggles - self._photo_toggles) % 2:
            pause = self.vitals_tab.pause_check
            pause.setChecked(not pause.isChecked())
        self._photo_toggles = toggles

    def _on_speed_hotkey(self, step: int):
        vitals = self.vitals_tab
        if not vitals.speed_slider.isEnabled():
            return
        if step == 0:
            percent = 100
        else:
            current = vitals.speed_percent()
            percent = (round(current / vitals.SPEED_STEP_PERCENT) + step) * vitals.SPEED_STEP_PERCENT
        percent = vitals.set_speed_percent(percent)
        self.overlay.show_message(tr("overlay.speed", percent=percent), percent >= 100, self.live.pid)

    def _capture_state(self) -> dict:
        """Configuration actuelle au format d'un profil (accessoires si accroche)."""
        settings = self.vitals_tab.profile_settings()
        if self.live.connected and self.live.sane:
            try:
                settings["weapon_accessories"] = {
                    f"{weapon_id:#04x}": mask for weapon_id, mask in self.live.read_all_weapon_accessories().items()}
            except OSError:
                pass
        return settings

    def _apply_settings(self, settings: dict):
        self.vitals_tab.apply_profile(settings)
        # Accessoires des armes : tout de suite si accroche, sinon a l'accrochage.
        self._pending_accessories = {int(k, 16): int(v) for k, v in
                                     settings.get("weapon_accessories", {}).items()} or None
        self._apply_pending_accessories()

    def apply_profile(self, key: str, from_hotkey: bool = False):
        """Active le profil ; la touche du profil deja actif le desactive
        (retour a la configuration d'avant le premier profil active)."""
        profile = self.profiles.get(key)
        if profile is None:
            return
        if key == self.current_profile:
            if self._saved_state is not None:
                self._apply_settings(self._saved_state)
            self._saved_state = None
            self.current_profile = None
            message, active = tr("overlay.off", fkey=key, name=profile.get("name") or key), False
        else:
            if self.current_profile is None:
                self._saved_state = self._capture_state()
            self._apply_settings(profile["settings"])
            self.current_profile = key
            message, active = tr("overlay.on", fkey=key, name=profile.get("name") or key), True
        self._update_profile_label()
        if from_hotkey:
            if not self.live.play_alert_sound():
                _beep()  # jeu pas accroche ou appel generique absent
            self.overlay.show_message(message, active, self.live.pid)

    def _apply_pending_accessories(self):
        if self._pending_accessories is None:
            return
        try:
            if self.live.apply_weapon_accessories(self._pending_accessories):
                self._pending_accessories = None
        except OSError:
            pass

    def choose_startup_profile(self):
        if not self.profiles:
            return
        dialog = ProfileChooserDialog(self.profiles, self)
        if dialog.exec() and dialog.chosen:
            self.apply_profile(dialog.chosen)

    def _update_profile_label(self):
        if self.current_profile in self.profiles:
            text = profile_label(self.current_profile, self.profiles[self.current_profile])
        else:
            text = tr("profile.none")
        self.profile_label.setText(tr("profile.current", profile=text))

    def _open_profile_save(self):
        dialog = ProfileSaveDialog(self.profiles, self.current_profile, self)
        if not dialog.exec():
            return
        key = dialog.key
        if dialog.action == "delete":
            self.profiles.pop(key, None)
            if self.current_profile == key:
                self.current_profile = None
                self._saved_state = None
        elif dialog.action == "save":
            settings = self.vitals_tab.profile_settings()
            if self.live.connected and self.live.sane:
                try:
                    settings["weapon_accessories"] = {
                        f"{weapon_id:#04x}": mask for weapon_id, mask in self.live.read_all_weapon_accessories().items()}
                except OSError:
                    pass
            elif key in self.profiles and "weapon_accessories" in self.profiles[key]["settings"]:
                settings["weapon_accessories"] = self.profiles[key]["settings"]["weapon_accessories"]
            self.profiles[key] = {"name": dialog.name, "settings": settings}
        if not save_profiles(self.profiles):
            QMessageBox.warning(self, tr("profile.save_title"), tr("profile.write_error", path=PROFILES_FILE))
        self.register_profile_hotkeys()
        self._update_profile_label()

    def closeEvent(self, event):
        if self.vitals_tab.photo_check.isChecked():
            self.vitals_tab.photo_check.setChecked(False)
        if self.vitals_tab.pause_check.isChecked():  # sinon le jeu resterait en pause
            self.vitals_tab.pause_check.setChecked(False)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        for hotkey_id in self._hotkeys:
            user32.UnregisterHotKey(wintypes.HWND(int(self.winId())), hotkey_id)
        self._cutscene_timer.stop()
        self.live.cutscene_quit_remove()
        self.live.load_menu_remove()
        self.cutscene_overlay.close()
        self.curtain.close()
        self.overlay.close()
        self.live.detach()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(TRAINER_ICON))
    window = TrainerWindow()
    window.setWindowIcon(QIcon(TRAINER_ICON))
    window.show()
    window.register_profile_hotkeys()
    window.choose_startup_profile()
    if update_check_enabled():
        window.start_update_check()
    sys.exit(app.exec())
