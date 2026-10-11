"""Donnees et constantes partagees par les onglets."""
from PySide6.QtWidgets import QMessageBox

import mgs4save

from mgs4trainer.core.i18n import (
    _STRINGS, facecamo_name, figure_name, item_name,
    outfit_name, tr, vest_name,
)


def warn_dialog(parent, title: str, text: str) -> None:
    """Equivalent de QMessageBox.warning() avec un bouton OK traduit -
    le bouton standard de Qt s'affiche sinon dans la langue par defaut
    de Qt, pas la notre (meme souci que Oui/Non sur QMessageBox.question(),
    voir TrainerWindow._on_language_changed)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.addButton(tr("button.ok"), QMessageBox.AcceptRole)
    box.exec()


# Categories du tableau d'objets partage (0x0526), calquees sur les onglets
# de gui_app.py plutot que sur un unique gros tableau - chaque dict source
# est confirme comme indexant ce meme tableau via les appels a
# _read_item_collection/read_camo/read_objects dans mgs4save.py.
# Onglet "OctoCamo" fusionne (2026-09-25, demande explicite de
# l'utilisateur) : sous-sections FaceCamo/Gilet/Octocamo empilees dans
# UN SEUL onglet (via GroupedItemsTab), meme logique que CAMO_GROUPS
# dans gui_app.py plutot que des onglets separes comme la veille (a
# quand meme permis de retrouver "Big Boss" 0x28 le 2026-09-24-25,
# coince entre Campbell 0x27 et Drebin 0x29). La section "Octocamo" ne
# lit PAS ce tableau : motifs stockes dans une table a part de linkvarbuf
# (2026-10-03, voir MGS4Live.OCTOCAMO_EDITABLE et OctoCamoTab).
_FACECAMO_NAMES_VISIBLE: dict[int, str] = {i: facecamo_name(i) for i in mgs4save.FACECAMO_NAMES}
_FACECAMO_IDS_ORDERED: list[int] = sorted(
    _FACECAMO_NAMES_VISIBLE, key=lambda i: mgs4save.FACECAMO_SORT_ORDER.get(i, 999)
)
_VEST_NAMES_VISIBLE: dict[int, str] = {k: vest_name(k) for k in mgs4save.VEST_NAMES if isinstance(k, int)}

_CLASSIFIED_IDS = (
    set(mgs4save.GENERAL_ITEM_NAMES) | set(_VEST_NAMES_VISIBLE) | set(_FACECAMO_NAMES_VISIBLE)
    | set(mgs4save.OUTFIT_NAMES) | set(mgs4save.FIGURE_NAMES) | set(mgs4save.SONG_NAMES)
)
def item_unclassified_format() -> str:
    """Gabarit de format positionnel brut (ex. "Objet #{:02d}") - pas via
    tr() qui attend des arguments nommes, celui-ci est applique avec
    .format(id) a l'appel (voir TableTab, qui l'utilise aussi pour les
    ID absents de son dict names)."""
    return _STRINGS.get("item.unclassified_format", "Objet #{:02d}")


_NON_CLASSES_NAMES: dict[int, str] = {
    i: item_unclassified_format().format(i)
    for i in range(mgs4save.ITEM_STATE_COUNT) if i not in _CLASSIFIED_IDS
}

# Objets generaux confirmes structurels (jamais un vrai objet, voir
# STRUCTURAL_ITEM_IDS dans mgs4save.py - 0x00 reconfirme le 2026-09-23,
# force a 1 en live sans aucun effet visible en jeu) - masques ici aussi,
# comme deja fait pour l'onglet Objets de l'appli principale, pour ne pas
# polluer les tests "a l'aveugle" avec des cases qui ne font jamais rien.
_GENERAL_ITEMS_VISIBLE = {
    k: item_name(k) for k in mgs4save.GENERAL_ITEM_NAMES if k not in mgs4save.STRUCTURAL_ITEM_IDS
}

# Objets empilables (quantite en stock), pas de sens "Obtenu"=1 fige - voir
# mgs4save.py ligne ~616 ("les 5 premiers IDs ... sont des COMPTEURS").
GENERAL_ITEM_QUANTITY_IDS = {0x01, 0x02, 0x03, 0x04, 0x05}  # Ration/Nouilles/Regain/Pentazemine/Compresse

# (label d'onglet, dict id->nom, IDs verrouilles a 65535/obtenus a 1 comme
# les chansons/statuettes/tenues/camos - PAS le tableau d'armes, qui a sa
# propre convention 0/1/2, voir TrainerWindow)
# FaceCamo/Gilet ne sont plus ici : fusionnes dans l'onglet "OctoCamo"
# dedie (GroupedItemsTab), construit a part dans TrainerWindow.
# (cle stable - jamais traduite, sert aux comparaisons logiques en aval -,
# libelle affiche, dict id->nom) - la cle stable evite de comparer du
# texte traduit dans la logique (fragile, casserait selon la langue).
ITEM_CATEGORIES: list[tuple[str, str, dict[int, str]]] = [
    ("items", tr("tab.items"), _GENERAL_ITEMS_VISIBLE),
    ("outfits", tr("tab.outfits"), {i: outfit_name(i) for i in mgs4save.OUTFIT_NAMES}),
    ("figures", tr("tab.figures"), {i: figure_name(i) for i in mgs4save.FIGURE_NAMES}),
    ("songs", tr("tab.songs"), mgs4save.SONG_NAMES),
    ("unclassified", tr("tab.unclassified"), _NON_CLASSES_NAMES),
]


# ---------------------------------------------------------------------------
# Interface Qt
# ---------------------------------------------------------------------------

REFRESH_MS = 750
# Cycle dedie, plus rapide que REFRESH_MS, pour la reassertion des
# verrous munitions (VitalsTab) : certaines armes tirent assez vite pour
# vider plusieurs coups entre deux cycles a 750ms avant correction,
# visible/genant (demande utilisateur 2026-09-26). Independant du
# rafraichissement general de l'UI (que ralentir ferait inutilement
# tout ralentir) - juste de la lecture/ecriture memoire brute, pas de
# repaint Qt, donc un cycle rapide reste tres peu couteux.
AMMO_LOCK_REFRESH_MS = 50
