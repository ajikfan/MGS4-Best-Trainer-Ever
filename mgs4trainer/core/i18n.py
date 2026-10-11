"""Reglages persistants, langue (FR/EN) et textes traduits."""
import json
import os
import sys

import mgs4save

from mgs4trainer.core.paths import SETTINGS_FILE, _bundled_path


# ---------------------------------------------------------------------------
# Internationalisation (FR/EN, demande utilisateur 2026-10-01, V2.0) -
# fichiers JSON embarques (_bundled_path, comme l'icone) plutot que des
# dictionnaires en dur dans ce fichier deja volumineux. Changement de
# langue = redemarrage automatique du process (pas de retraduction a
# chaud des widgets deja construits - bien plus simple, choix explicite
# de l'utilisateur plutot que de doubler la complexite pour un gain mineur
# sur un outil solo). Choix persiste dans SETTINGS_FILE (a cote de l'exe,
# comme teleport_points.json), pas dans le dossier temporaire PyInstaller.
DEFAULT_LANGUAGE = "fr"
SUPPORTED_LANGUAGES = {"fr": "Français", "en": "English"}


def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_settings(settings: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def current_language() -> str:
    lang = _load_settings().get("language", DEFAULT_LANGUAGE)
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    settings = _load_settings()
    settings["language"] = lang
    _save_settings(settings)


def restart_trainer() -> None:
    """Relance le process a l'identique (meme exe/script, memes
    arguments) - utilise apres un changement de langue. os.execv
    remplace le process en place (meme PID), fonctionne aussi bien en
    mode developpement (sys.executable = python.exe) qu'empaquete
    (sys.executable = l'exe du trainer, voir _writable_data_path)."""
    os.execv(sys.executable, [sys.executable] + sys.argv)


def _load_locale_file(category: str, lang: str) -> dict:
    """locales/<lang>/<category>.json - structure symetrique : chaque
    langue a exactement les memes fichiers (pas de "francais en dur dans
    le code, anglais en overlay" - les deux viennent de JSON, demande
    utilisateur 2026-10-01)."""
    path = _bundled_path("locales", lang, f"{category}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def load_locale_category(category: str) -> dict:
    """Charge un fichier de locales/<langue active>/<category>.json, avec
    repli sur le francais si la langue active n'a pas (encore) ce fichier
    ou certaines de ses cles - jamais de texte brut en dur en remplacement,
    uniquement un autre fichier JSON."""
    data = _load_locale_file(category, _LANG)
    if _LANG == DEFAULT_LANGUAGE:
        return data
    fallback = _load_locale_file(category, DEFAULT_LANGUAGE)
    merged = dict(fallback)
    merged.update(data)
    return merged


_LANG = current_language()
_STRINGS = load_locale_category("strings")
CHANGELOG_STRINGS = load_locale_category("changelog")
_WEAPON_NAMES_LOCALE = load_locale_category("weapons")
_ITEM_NAMES_LOCALE = load_locale_category("items")
_FIGURES_LOCALE = load_locale_category("figures")
_FACECAMO_LOCALE = load_locale_category("facecamo")
_VESTS_LOCALE = load_locale_category("vests")
_OUTFITS_LOCALE = load_locale_category("outfits")
_OCTOCAMO_LOCALE = load_locale_category("octocamo")
_STAGES_LOCALE = load_locale_category("stages")


def stage_display_name(code: str) -> str:
    return _STAGES_LOCALE.get(code, code)


def act_number(progress: int) -> int | None:
    """Acte depuis la progression (bornes de mgs4save.ACT_RANGES : 1 a 5,
    6 = epilogue)."""
    for index, (lo, hi, _name) in enumerate(mgs4save.ACT_RANGES, start=1):
        if lo <= progress <= hi:
            return index
    return None


def act_display_name(act: int | None) -> str:
    if act is None:
        return "?"
    return tr("teleport.epilogue") if act > 5 else tr("teleport.act", n=act)

# Cles stables (pas d'ID numerique reel pour les motifs OctoCamo, voir
# mgs4save.OCTOCAMO_INFO) - doit rester synchronise avec les cles de
# locales/*/octocamo.json.
OCTOCAMO_SLUGS = {
    "Infiltration": "infiltration", "Olive": "olive", "Tigré": "tiger_stripe",
    "Forêt": "forest", "3 Couleurs Désert": "desert_3color", "Marpat": "marpat",
    "Cadavre": "corpse", "Pleurs": "crying", "Digit. B": "digital_b",
    "Digit. R": "digital_r", "Mouche": "fly", "Gear": "gear", "Haven": "haven",
    "Rire": "laughing", "Metal": "metal", "Snake": "snake", "Rage": "raging",
    "Hurler": "screaming", "Beauté": "beauty", "Précommande": "preorder", "Doré": "golden",
}


def weapon_name(weapon_id: int) -> str:
    entry = _WEAPON_NAMES_LOCALE.get(str(weapon_id))
    return entry if entry else mgs4save.WEAPON_NAMES.get(weapon_id, f"Arme #{weapon_id}")


def item_name(item_id: int) -> str:
    entry = _ITEM_NAMES_LOCALE.get(str(item_id))
    return entry if entry else mgs4save.GENERAL_ITEM_NAMES.get(item_id, f"Objet #{item_id:02d}")


def figure_name(figure_id: int) -> str:
    entry = _FIGURES_LOCALE.get(str(figure_id))
    return entry["name"] if entry else mgs4save.FIGURE_NAMES.get(figure_id, f"#{figure_id}")


def figure_condition(figure_id: int) -> str:
    entry = _FIGURES_LOCALE.get(str(figure_id))
    return entry["condition"] if entry else ""


def facecamo_name(facecamo_id: int) -> str:
    entry = _FACECAMO_LOCALE.get(str(facecamo_id))
    return entry["name"] if entry else mgs4save.FACECAMO_NAMES.get(facecamo_id, f"#{facecamo_id}")


def facecamo_condition(facecamo_id: int) -> str:
    entry = _FACECAMO_LOCALE.get(str(facecamo_id))
    return entry["condition"] if entry else ""


def vest_name(vest_id: int) -> str:
    entry = _VESTS_LOCALE.get(str(vest_id))
    return entry["name"] if entry else mgs4save.VEST_NAMES.get(vest_id, f"#{vest_id}")


def vest_condition(vest_id: int) -> str:
    entry = _VESTS_LOCALE.get(str(vest_id))
    return entry["condition"] if entry else ""


def outfit_name(outfit_id: int) -> str:
    entry = _OUTFITS_LOCALE.get(str(outfit_id))
    return entry["name"] if entry else mgs4save.OUTFIT_NAMES.get(outfit_id, f"#{outfit_id}")


def outfit_condition(outfit_id: int) -> str:
    entry = _OUTFITS_LOCALE.get(str(outfit_id))
    return entry["condition"] if entry else ""


def octocamo_name(fr_key: str) -> str:
    slug = OCTOCAMO_SLUGS.get(fr_key)
    entry = _OCTOCAMO_LOCALE.get(slug) if slug else None
    return entry["name"] if entry else fr_key


def octocamo_description(fr_key: str) -> str:
    slug = OCTOCAMO_SLUGS.get(fr_key)
    entry = _OCTOCAMO_LOCALE.get(slug) if slug else None
    return entry["description"] if entry else mgs4save.OCTOCAMO_INFO.get(fr_key, "")


# Cles stables pour les categories d'armes (mgs4save.WEAPON_GROUP_ORDER) -
# meme principe que OCTOCAMO_SLUGS.
WEAPON_GROUP_SLUGS = {
    "Arme de poing": "handgun", "Fusil d'assaut": "assault_rifle",
    "Fusil Sniper": "sniper_rifle", "Fusil à pompe": "shotgun",
    "Pistolet-mitrailleur": "smg", "Lance-grenade": "grenade_launcher",
    "Mitrailleuse": "machine_gun", "Lance-roquette": "rocket_launcher",
    "Grenade": "grenade", "Explosif": "explosive", "Magazine": "magazine",
    "Autre": "other", "Accessoire": "accessory", "Non identifiée": "unidentified",
}
_WEAPON_GROUPS_LOCALE = load_locale_category("weapon_groups")


def weapon_group_label(fr_name: str) -> str:
    slug = WEAPON_GROUP_SLUGS.get(fr_name)
    return _WEAPON_GROUPS_LOCALE.get(slug, fr_name) if slug else fr_name


def alert_state_name(value: int) -> str:
    return tr(f"alert.state_{value}")


_VITALS_LOCALE = load_locale_category("vitals")


def vital_display_name(internal_name: str) -> str:
    """internal_name reste la cle stable (VITALS, read_vital/write_vital...)
    - seul l'affichage est traduit."""
    return _VITALS_LOCALE.get(internal_name, internal_name)


def tr(key: str, **kwargs) -> str:
    """Traduction par cle plate (ex. "window.title") - la cle elle-meme
    sert de repli ultime si elle manque des deux langues (repere
    visuellement les oublis pendant le developpement plutot qu'un crash
    ou un texte vide)."""
    text = _STRINGS.get(key, key)
    return text.format(**kwargs) if kwargs else text
