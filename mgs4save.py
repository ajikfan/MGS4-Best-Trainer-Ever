"""Lecture (seule) des saves Metal Gear Solid 4 (portage PC Steam).

Statut : reverse engineering en cours. Voir notes.md pour la méthode et les
offsets déjà identifiés. Aucune fonction d'écriture volontairement : cet
outil ne doit jamais modifier un fichier de save.
"""

import argparse
import struct

XOR_KEY = bytes.fromhex(
    "6b6a6479654169776f47736b6c636d667539336c7773454e6637383435676877"
    "353233696630756c37506b6a30686e39656a776b73535645387477663033746536"
    "323344413834327263346f69514c"
)

# Offsets confirmés (par corrélation, puis recoupés et complétés avec la
# documentation externe zexk/bbtracker citée dans notes.md - meme cle XOR,
# donc meme build). name -> (offset, struct_format)
STATS = {
    "continues": (0x158, "<H"),
    "alertes": (0x16e, "<H"),
    "kills_total": (0x178, "<H"),
    "objets_speciaux_bitmask": (0x17a, "<H"),  # bits individuels identifies, voir SPECIAL_ITEM_USE_BITS
    "cqc": (0x180, "<H"),
    "headshots": (0x182, "<H"),
    "knife_kills": (0x184, "<H"),
    "knife_knockouts": (0x186, "<H"),
    "roulades_cote": (0x188, "<H"),
    "roulades_avant": (0x18a, "<H"),
    "combat_high": (0x18c, "<H"),
    "weapon_pickups": (0x18e, "<H"),
    "item_pickups": (0x190, "<H"),
    "holdups": (0x192, "<H"),
    "body_searches": (0x194, "<H"),
    "praises": (0x196, "<H"),
    # RE-CONFIRME (2026-08-31) apres un aller-retour : voir notes.md
    # section "objets_donnes_milices, deuxieme revirement". Ce champ
    # (MGS4.SAV, 0x198) est bien "objets donnes aux milices" - test isole
    # propre, transition exacte 0->2 correspondant a 2 dons reels en jeu.
    # A NE PAS CONFONDRE avec le champ du meme nom dans METADATA.SAV
    # (0x40, cle "progression_menu_sauvegarde" de read_metadata_summary) :
    # ce sont deux compteurs INDEPENDANTS malgre le nom similaire, et
    # c'est CELUI DE METADATA.SAV qui se comporte bizarrement (deja a 1
    # apres 156 secondes de jeu) - pas celui-ci.
    "objets_donnes_milices": (0x198, "<H"),
    "syringe_uses": (0x19a, "<H"),
    "scanning_plug_uses": (0x19c, "<H"),
    "playboy_pages": (0x19e, "<H"),
    "emotion_magazine_pages": (0x1a0, "<H"),
    "drebin_actuel": (0x1c0, "<I"),
    "drebin_total_ventes": (0x1c4, "<I"),
    "flashbacks_vues": (0x5a34, "<H"),
    "soins_utilises": (0x0ae0, "<H"),
    # Stats de temps continu, en "frames" a framerate variable (~55-62 fps
    # observe). Ne se flushent qu'au changement de zone/checkpoint, jamais
    # sur une simple sauvegarde manuelle. Pas de conversion exacte en
    # secondes possible (framerate non fixe), voir notes.md.
    "temps_accroupi_frames": (0x1a8, "<H"),
    # INCERTAIN (2026-09-09) : confirme par un test isole le 2026-09-05
    # (seule transition exacte 0->1 entre deux saves, sur un offset
    # jusque-la inutilise), mais reste bloque a 0 malgre un poster "Akina"
    # regarde le 2026-09-09 (confirme par l'utilisateur, avec succes Steam
    # dedie a l'appui) - ce test n'etait pas isole (changement de zone
    # entre les deux saves), donc pas de nouvelle transition observable
    # ailleurs non plus, mais ce champ ne semble pas suivre CE type de
    # poster. Peut-etre un compteur pour un autre type d'affiche (PMC ?),
    # ou un mecanisme different (bitmask par poster plutot qu'un compteur
    # cumulatif). A revalider avec un vrai test isole. Total confirme par
    # l'utilisateur (2026-09-09) : 4 posters "Akina" a trouver dans le jeu,
    # donc si ce champ est le bon, l'affichage cible serait "X/4".
    "posters_vus": (0x1aa, "<H"),
    "temps_allonge_frames": (0x1ac, "<H"),
    "temps_mur_frames": (0x1b4, "<H"),
    "temps_boite_carton_frames": (0x1b8, "<I"),
    "temps_baril_frames": (0x1bc, "<I"),
    "temps_jeu_frames": (0x168, "<I"),  # alternative a read_playtime_seconds(), moins precis (framerate variable)
}

# Total confirme par l'utilisateur (2026-09-09) : 4 posters "Akina" a
# trouver dans le jeu - affiche "X/4" independamment de la fiabilite du
# champ posters_vus lui-meme (voir commentaire "INCERTAIN" ci-dessus).
POSTERS_MAX = 4

# Bitmask des images de flashback individuelles vues au moins une fois
# (CONFIANCE HAUTE, voir notes.md "Bitmask des flashbacks confirmé
# bit-par-image" et "Total réel confirmé via le trophée Flashback
# Mania"). Un bit = une image de flashback (pas une scène narrative :
# un flashback "au sens large" contient plusieurs images/bits).
# Contrairement a `flashbacks_vues` (0x5a34, compteur d'OCCURRENCES qui
# grimpe a chaque revisionnage, meme d'une image deja vue), ce bitmask
# ne compte chaque image qu'une seule fois - c'est la vraie mesure de
# progression "combien de flashbacks distincts ai-je vus".
# Zone bornee confirmee le 2026-09-19 : tout ce qui suit 0x5a64 est a 0.
FLASHBACK_BITMASK_OFFSET = 0x5a44
FLASHBACK_BITMASK_LENGTH = 33  # octets = 264 emplacements de bits
# Total reel confirme le 2026-09-19 via le trophee Steam "Flashback
# Mania" (tous les flashbacks vus) : 238 bits actifs sur 264 sur la save
# la plus avancee de l'utilisateur juste apres l'obtention du trophee,
# et ce total ne peut plus augmenter. Les 26 bits jamais actives forment
# un motif stable (deux octets entierement a zero + trois octets
# partiels), cohérent avec du padding structurel plutot que des
# flashbacks restants. Remplace l'estimation non officielle de ~245
# (forum MGS) et la premiere estimation erronee de 65.
FLASHBACK_IMAGES_TOTAL = 238

# Stats affichees en jeu comme une seule valeur mais stockees comme la somme
# de deux champs distincts (confirme via zexk/bbtracker, voir notes.md).
# name -> (champ1, champ2)
DERIVED_STATS = {
    "ko_couteau": ("knife_kills", "knife_knockouts"),
    "armes_objets_acquis": ("weapon_pickups", "item_pickups"),
    "seringue_scanning_plug": ("syringe_uses", "scanning_plug_uses"),
    "pages_magazine_tournees": ("playboy_pages", "emotion_magazine_pages"),
    "temps_carton_frames": ("temps_boite_carton_frames", "temps_baril_frames"),
}


def decrypt(data: bytes) -> bytes:
    return bytes(b ^ XOR_KEY[i % len(XOR_KEY)] for i, b in enumerate(data))


def read_playtime_seconds(metadata_path: str) -> int:
    """Lit le temps de jeu total depuis METADATA.SAV (non chiffre, contrairement
    a MGS4.SAV). Precision approximative : +/- 30s par rapport a l'affichage
    en jeu (le compteur en jeu continue de tourner un peu apres l'ecriture du
    fichier), voir notes.md."""
    with open(metadata_path, "rb") as f:
        data = f.read()
    return struct.unpack_from("<I", data, 0x34)[0]


def read_playthrough_number(metadata_path: str) -> int:
    """Numero de partie affiche par l'etoile dans le menu de chargement du jeu
    (1 = premiere completion, etc). Depuis METADATA.SAV, non chiffre."""
    with open(metadata_path, "rb") as f:
        data = f.read()
    return struct.unpack_from("<I", data, 0x38)[0]


# Score de difficulte -> nom affiche en jeu. Seuls 3 points connus pour
# l'instant (voir notes.md) ; les difficultes plus dures ne sont pas mappees.
DIFFICULTY_NAMES = {
    20: "LIQUID FACILE",
    30: "NAKED NORMAL",
    35: "SOLID NORMAL",
    40: "BIG BOSS DIFFICILE",
    50: "THE BOSS EXTREME",
}


def read_difficulty_score(metadata_path: str) -> int:
    """Score de difficulte brut depuis METADATA.SAV. Utiliser DIFFICULTY_NAMES
    pour le nom affiche en jeu (mapping incomplet, voir notes.md)."""
    with open(metadata_path, "rb") as f:
        data = f.read()
    return struct.unpack_from("<I", data, 0x30)[0]


# Code de stage interne -> lieu affiche en jeu (source zexk/bbtracker,
# extrait de common/stage/select/scenerio.gcx). Un nom combine signifie
# qu'un seul code de stage couvre plusieurs lieux visibles en jeu.
STAGE_NAMES = {
    "s00a00l": "Prologue : cimetière", "s00a10l": "Épilogue : cimetière",
    "s01a00l": "Infiltration Moyen-Orient", "s01a05l": "Infiltration Moyen-Orient",
    "s01a10l": "Zone rouge", "s01a20l": "Planque de la milice",
    "s01a30l": "Ruines urbaines", "s01a40l": "Palais de l'Avent",
    "s01a50l": "Crescent Meridian", "s01a55l": "Crescent Meridian",
    "s01a57l": "Millennium Park", "s01a60l": "Campement de Liquid",
    "s02a10l": "Village de Cove Valley", "s02a20l": "Centrale électrique",
    "s02a25l": "Centrale électrique", "s02a30l": "Centre de détention",
    "s02a40l": "Manoir Vista", "s02a50l": "Laboratoire de recherche",
    "s02a60l": "Sentier de montagne / Rivière", "s02a70l": "Embuscade de Vamp",
    "s02a73l": "Fuite de Stryker", "s02a75l": "Fuite de Stryker", "s02a78l": "Fuite de Stryker",
    "s02a80l": "Route des hauts bois", "s02a85l": "Entrée du marché",
    "s02a90l": "Marché", "s02a95l": "Place du marché",
    "s03a00l": "Gare d'Europe de l'Est", "s03a10l": "Centre-ville : la traque",
    "s03a15l": "Centre-ville : la traque", "s03a16l": "Centre-ville : les canaux",
    "s03a20l": "Centre-ville : la place", "s03a25l": "Centre-ville : secteur nord",
    "s03a30l": "Cour de l'église", "s03a35l": "Poursuite à moto",
    "s03a40l": "Poursuite à moto", "s03a60l": "Poursuite à moto",
    "s03a50l": "Embuscade de Raging Raven", "s03a65l": "Balise d'Echo", "s03a70l": "Balise d'Echo",
    "s03a90l": "Rivière Volta", "s04a05l": "Flashback Metal Gear Solid",
    "s04a10l": "Champ de neige / Héliport / Hangar", "s04a20l": "Stockage d'ogives nucléaires",
    "s04a30l": "Champ de neige / Tour de communication", "s04a40l": "Haut-fourneau / Fonderie",
    "s04a50l": "Base souterraine", "s04a60l": "Tunnel de ravitaillement souterrain",
    "s04a65l": "Fuite de REX", "s04a68l": "Zone portuaire",
    "s04a70l": "Zone portuaire : REX vs RAY", "s04a75l": "Arrivée à Outer Haven",
    "s05a10l": "Proue du navire", "s05a20l": "Centre de commandement / Hangar à missiles",
    "s05a30l": "Couloir micro-ondes", "s05a40l": "GW",
    "s05a45l": "Liquid Ocelot : prélude", "s05a50l": "Liquid Ocelot",
    "s05a55l": "Liquid Ocelot : aftermath",
    "s10a10l": "Briefing (Nomad)", "s10a20l": "Briefing Amérique du Sud",
    "s10a30l": "Briefing Europe de l'Est", "s10a40l": "Briefing Shadow Moses",
    "s20a00l": "USS Missouri", "s20a10l": "USS Missouri vs Outer Haven",
    "s20a20l": "Salle de Campbell", "s30a00l": "Mariage", "s30a10l": "Hôpital",
}

# progress (0x0054, u32) -> Acte (source zexk/bbtracker)
ACT_RANGES = [
    (0, 50, "Acte 1"), (51, 100, "Acte 2"), (101, 162, "Acte 3"),
    (163, 222, "Acte 4"), (223, 261, "Acte 5"), (262, 291, "Épilogue"),
]


def act_from_progress(progress: int) -> str:
    for lo, hi, name in ACT_RANGES:
        if lo <= progress <= hi:
            return name
    return f"inconnu ({progress})"


def read_progress_info(path: str) -> dict:
    """Lieu et acte actuels, depuis MGS4.SAV (source zexk/bbtracker)."""
    with open(path, "rb") as f:
        data = decrypt(f.read())
    stage_code = data[0x34:0x3b].decode("ascii", errors="replace")
    progress = struct.unpack_from("<I", data, 0x54)[0]
    return {
        "stage_code": stage_code,
        "lieu": STAGE_NAMES.get(stage_code, f"inconnu ({stage_code})"),
        "acte": act_from_progress(progress),
    }


def read_metadata_summary(metadata_path: str) -> dict:
    """Resume rapide d'un slot depuis METADATA.SAV seul (pas de dechiffrement
    necessaire) : suffisant pour un ecran de liste sans ouvrir MGS4.SAV."""
    with open(metadata_path, "rb") as f:
        data = f.read()
    difficulty_score = struct.unpack_from("<I", data, 0x30)[0]
    return {
        "playtime_secondes": struct.unpack_from("<I", data, 0x34)[0],
        "numero_partie": struct.unpack_from("<I", data, 0x38)[0],
        "difficulte_score": difficulty_score,
        "difficulte_nom": DIFFICULTY_NAMES.get(difficulty_score, f"inconnu ({difficulty_score})"),
        "drebin_actuel": struct.unpack_from("<I", data, 0x3c)[0],
        "progression_menu_sauvegarde": struct.unpack_from("<I", data, 0x40)[0],
    }


def read_stats(path: str) -> dict:
    with open(path, "rb") as f:
        data = decrypt(f.read())
    values = {
        name: struct.unpack_from(fmt, data, offset)[0]
        for name, (offset, fmt) in STATS.items()
    }
    for name, (field_a, field_b) in DERIVED_STATS.items():
        values[name] = values[field_a] + values[field_b]
    flashback_zone = data[FLASHBACK_BITMASK_OFFSET:FLASHBACK_BITMASK_OFFSET + FLASHBACK_BITMASK_LENGTH]
    values["flashback_images_vues"] = sum(bin(b).count("1") for b in flashback_zone)
    return values


def count_acquired_weapons(path: str) -> int:
    """Nombre d'armes acquises (etat 1 ou 2), IDs 1..73 en excluant l'ID 11
    (1911 Custom, optionnel) - formule exacte pour l'emblème LITTLE GRAY,
    source zexk/bbtracker. Tableau complet a 0x1d4 (u16[95], IDs 0..94)."""
    with open(path, "rb") as f:
        data = decrypt(f.read())
    count = 0
    for weapon_id in range(1, 74):
        if weapon_id == 11:
            continue
        state = struct.unpack_from("<H", data, 0x1d4 + 2 * weapon_id)[0]
        if state in (1, 2):
            count += 1
    return count


# Les 40 formules d'emblemes de fin de partie (source zexk/bbtracker,
# docs/mgs4_research.md, section "Emblem predicates" - extraite du script
# ww/stage/stage00/s00a10l/cache/00180720.gcx). Le jeu ne les evalue
# reellement qu'a l'ecran de resultats final ; ici on calcule l'etat par
# rapport aux stats actuelles. Chaque condition recoit un contexte : stats
# (dict de read_stats()), playtime_h (heures), difficulty_score (0x30 de
# METADATA.SAV), weapon_count (count_acquired_weapons()).
#
# Chaque condition est taguee MAX ou MIN car toutes nos stats ne font
# qu'augmenter pendant une partie :
#   MAX = plafond a ne pas depasser ("moins de X", "= 0", difficulte fixe).
#         Vrai = encore dans les clous. Faux = franchi, donc impossible
#         pour le reste de cette partie (ne peut plus redevenir vrai).
#   MIN = seuil a atteindre ("plus de X"). Faux = pas encore atteint mais
#         toujours possible plus tard. Vrai = atteint, et le reste pour
#         toujours (la stat ne redescend jamais).
MAX, MIN = "max", "min"

# Chaque condition est (description, kind, seuil, value_fn, check) :
#   seuil     = valeur de reference affichee dans la popup (cote droit du "x/y").
#   value_fn  = lit la valeur actuelle correspondante dans le contexte (cote
#               gauche du "x/y"), independamment de check() ci-dessous.
#   check     = booleen de reussite, inchange depuis la version d'origine.
def _alertes(c): return c["stats"]["alertes"]
def _kills(c): return c["stats"]["kills_total"]
def _continues(c): return c["stats"]["continues"]
def _soins(c): return c["stats"]["soins_utilises"]
def _difficulte(c): return DIFFICULTY_NAMES.get(c["difficulty_score"], str(c["difficulty_score"]))
def _playtime(c): return c["playtime_h"]
def _objets_speciaux(c): return c["stats"]["objets_speciaux_bitmask"]


EMBLEMS = [
    (1, "BIG BOSS", [
        ("Difficulté : The Boss Extrême", MAX, None, _difficulte, lambda c: c["difficulty_score"] == 50),
        ("0 alerte", MAX, 0, _alertes, lambda c: c["stats"]["alertes"] == 0),
        ("0 kill", MAX, 0, _kills, lambda c: c["stats"]["kills_total"] == 0),
        ("0 continue", MAX, 0, _continues, lambda c: c["stats"]["continues"] == 0),
        ("0 objet de soin utilisé", MAX, 0, _soins, lambda c: c["stats"]["soins_utilises"] == 0),
        ("Moins de 5 heures de jeu", MAX, 5, _playtime, lambda c: c["playtime_h"] <= 5),
        ("Aucun objet spécial utilisé", MAX, 0, _objets_speciaux, lambda c: c["stats"]["objets_speciaux_bitmask"] == 0),
    ]),
    (2, "FOX HOUND", [
        ("Difficulté : Big Boss Difficile ou plus", MAX, None, _difficulte, lambda c: c["difficulty_score"] >= 40),
        ("Moins de 3 alertes", MAX, 3, _alertes, lambda c: c["stats"]["alertes"] <= 3),
        ("0 kill", MAX, 0, _kills, lambda c: c["stats"]["kills_total"] == 0),
        ("0 continue", MAX, 0, _continues, lambda c: c["stats"]["continues"] == 0),
        ("0 objet de soin utilisé", MAX, 0, _soins, lambda c: c["stats"]["soins_utilises"] == 0),
        ("Moins de 5h30 de jeu", MAX, 5.5, _playtime, lambda c: c["playtime_h"] <= 5.5),
        ("Aucun objet spécial utilisé", MAX, 0, _objets_speciaux, lambda c: c["stats"]["objets_speciaux_bitmask"] == 0),
    ]),
    (3, "FOX", [
        ("Difficulté : Solid Normal ou plus", MAX, None, _difficulte, lambda c: c["difficulty_score"] >= 35),
        ("Moins de 5 alertes", MAX, 5, _alertes, lambda c: c["stats"]["alertes"] <= 5),
        ("0 kill", MAX, 0, _kills, lambda c: c["stats"]["kills_total"] == 0),
        ("0 continue", MAX, 0, _continues, lambda c: c["stats"]["continues"] == 0),
        ("0 objet de soin utilisé", MAX, 0, _soins, lambda c: c["stats"]["soins_utilises"] == 0),
        ("Moins de 6 heures de jeu", MAX, 6, _playtime, lambda c: c["playtime_h"] <= 6),
        ("Aucun objet spécial utilisé", MAX, 0, _objets_speciaux, lambda c: c["stats"]["objets_speciaux_bitmask"] == 0),
    ]),
    (4, "HOUND", [
        ("Difficulté : Naked Normal ou plus", MAX, None, _difficulte, lambda c: c["difficulty_score"] >= 30),
        ("Moins de 10 alertes", MAX, 10, _alertes, lambda c: c["stats"]["alertes"] <= 10),
        ("0 kill", MAX, 0, _kills, lambda c: c["stats"]["kills_total"] == 0),
        ("0 continue", MAX, 0, _continues, lambda c: c["stats"]["continues"] == 0),
        ("0 objet de soin utilisé", MAX, 0, _soins, lambda c: c["stats"]["soins_utilises"] == 0),
        ("Moins de 6h30 de jeu", MAX, 6.5, _playtime, lambda c: c["playtime_h"] <= 6.5),
        ("Aucun objet spécial utilisé", MAX, 0, _objets_speciaux, lambda c: c["stats"]["objets_speciaux_bitmask"] == 0),
    ]),
    (5, "MANTIS", [
        ("0 alerte", MAX, 0, _alertes, lambda c: c["stats"]["alertes"] == 0),
        ("0 continue", MAX, 0, _continues, lambda c: c["stats"]["continues"] == 0),
        ("0 objet de soin utilisé", MAX, 0, _soins, lambda c: c["stats"]["soins_utilises"] == 0),
        ("Moins de 5 heures de jeu", MAX, 5, _playtime, lambda c: c["playtime_h"] <= 5),
    ]),
    (6, "WOLF", [
        ("0 continue", MAX, 0, _continues, lambda c: c["stats"]["continues"] == 0),
        ("0 objet de soin utilisé", MAX, 0, _soins, lambda c: c["stats"]["soins_utilises"] == 0),
    ]),
    (7, "RAVEN", [
        ("Moins de 5 heures de jeu", MAX, 5, _playtime, lambda c: c["playtime_h"] <= 5),
    ]),
    (8, "OCTOPUS", [
        ("0 alerte", MAX, 0, _alertes, lambda c: c["stats"]["alertes"] == 0),
    ]),
    (9, "BEAR", [
        ("Plus de 100 utilisations de CQC", MIN, 100, lambda c: c["stats"]["cqc"], lambda c: c["stats"]["cqc"] >= 100),
    ]),
    (10, "EAGLE", [
        ("Plus de 150 headshots", MIN, 150, lambda c: c["stats"]["headshots"], lambda c: c["stats"]["headshots"] >= 150),
    ]),
    (11, "ASSASSIN", [
        ("Plus de 50 neutralisations au couteau", MIN, 50, lambda c: c["stats"]["ko_couteau"], lambda c: c["stats"]["ko_couteau"] >= 50),
        ("Plus de 50 utilisations de CQC", MIN, 50, lambda c: c["stats"]["cqc"], lambda c: c["stats"]["cqc"] >= 50),
        ("Moins de 25 alertes", MAX, 25, _alertes, lambda c: c["stats"]["alertes"] <= 25),
    ]),
    (12, "PIGEON", [
        ("0 kill", MAX, 0, _kills, lambda c: c["stats"]["kills_total"] == 0),
    ]),
    (13, "BLUE BIRD", [
        ("Plus de 50 objets donnés aux milices", MIN, 50, lambda c: c["stats"]["objets_donnes_milices"], lambda c: c["stats"]["objets_donnes_milices"] >= 50),
    ]),
    (14, "HAWK", [
        ("Plus de 25 compliments reçus", MIN, 25, lambda c: c["stats"]["praises"], lambda c: c["stats"]["praises"] >= 25),
    ]),
    (15, "LITTLE GRAY", [
        ("Plus de 69 armes acquises (sur 73, hors 1911 Custom)", MIN, 69, lambda c: c["weapon_count"], lambda c: c["weapon_count"] >= 69),
    ]),
    (16, "ANT", [
        ("Plus de 50 fouilles corporelles", MIN, 50, lambda c: c["stats"]["body_searches"], lambda c: c["stats"]["body_searches"] >= 50),
    ]),
    (17, "GIBBON", [
        ("Plus de 50 hold-ups", MIN, 50, lambda c: c["stats"]["holdups"], lambda c: c["stats"]["holdups"] >= 50),
    ]),
    (18, "TORTOISE", [
        ("Plus de 60 minutes dans un carton ou un baril", MIN, 60, lambda c: c["stats"]["temps_carton_frames"] / 3600, lambda c: c["stats"]["temps_carton_frames"] / 3600 >= 60),
    ]),
    (19, "RABBIT", [
        ("Plus de 100 pages de magazine tournées", MIN, 100, lambda c: c["stats"]["pages_magazine_tournees"], lambda c: c["stats"]["pages_magazine_tournees"] >= 100),
    ]),
    (20, "BEE", [
        ("Plus de 50 utilisations de seringue ou Scanning Plug", MIN, 50, lambda c: c["stats"]["seringue_scanning_plug"], lambda c: c["stats"]["seringue_scanning_plug"] >= 50),
    ]),
    (21, "GECKO", [
        ("Plus de 60 minutes contre un mur", MIN, 60, lambda c: c["stats"]["temps_mur_frames"] / 3600, lambda c: c["stats"]["temps_mur_frames"] / 3600 >= 60),
    ]),
    (22, "SCARAB", [
        ("Plus de 100 roulades de côté", MIN, 100, lambda c: c["stats"]["roulades_cote"], lambda c: c["stats"]["roulades_cote"] >= 100),
    ]),
    (23, "FROG", [
        ("Plus de 200 roulades en avant", MIN, 200, lambda c: c["stats"]["roulades_avant"], lambda c: c["stats"]["roulades_avant"] >= 200),
    ]),
    (24, "INCH WORM", [
        ("Plus de 60 minutes allongé ou à ramper", MIN, 60, lambda c: c["stats"]["temps_allonge_frames"] / 3600, lambda c: c["stats"]["temps_allonge_frames"] / 3600 >= 60),
    ]),
    (25, "LOBSTER", [
        ("Plus de 150 minutes accroupi", MIN, 150, lambda c: c["stats"]["temps_accroupi_frames"] / 3600, lambda c: c["stats"]["temps_accroupi_frames"] / 3600 >= 150),
    ]),
    (26, "HYENA", [
        ("Plus de 400 armes ou objets ramassés", MIN, 400, lambda c: c["stats"]["armes_objets_acquis"], lambda c: c["stats"]["armes_objets_acquis"] >= 400),
    ]),
    (27, "HOG", [
        ("Plus de 10 poussées d'adrénaline", MIN, 10, lambda c: c["stats"]["combat_high"], lambda c: c["stats"]["combat_high"] >= 10),
    ]),
    (28, "PIG", [
        ("Plus de 40 objets de soin utilisés", MIN, 40, _soins, lambda c: c["stats"]["soins_utilises"] >= 40),
    ]),
    (29, "COW", [
        ("Plus de 100 alertes", MIN, 100, _alertes, lambda c: c["stats"]["alertes"] >= 100),
    ]),
    (30, "CROCODILE", [
        ("Plus de 400 kills", MIN, 400, _kills, lambda c: c["stats"]["kills_total"] >= 400),
    ]),
    (31, "GIANT PANDA", [
        ("Plus de 30 heures de jeu", MIN, 30, _playtime, lambda c: c["playtime_h"] >= 30),
    ]),
    (32, "SCORPION", [
        ("Moins de 75 alertes", MAX, 75, _alertes, lambda c: c["stats"]["alertes"] <= 75),
        ("Moins de 250 kills", MAX, 250, _kills, lambda c: c["stats"]["kills_total"] <= 250),
        ("Moins de 25 continues", MAX, 25, _continues, lambda c: c["stats"]["continues"] <= 25),
    ]),
    (33, "TARANTULA", [
        ("Moins de 75 alertes", MAX, 75, _alertes, lambda c: c["stats"]["alertes"] <= 75),
        ("Plus de 250 kills", MIN, 250, _kills, lambda c: c["stats"]["kills_total"] > 250),
        ("Moins de 25 continues", MAX, 25, _continues, lambda c: c["stats"]["continues"] <= 25),
    ]),
    (34, "CENTIPEDE", [
        ("Moins de 75 alertes", MAX, 75, _alertes, lambda c: c["stats"]["alertes"] <= 75),
        ("Moins de 250 kills", MAX, 250, _kills, lambda c: c["stats"]["kills_total"] <= 250),
        ("Plus de 25 continues", MIN, 25, _continues, lambda c: c["stats"]["continues"] > 25),
    ]),
    (35, "SPIDER", [
        ("Moins de 75 alertes", MAX, 75, _alertes, lambda c: c["stats"]["alertes"] <= 75),
        ("Plus de 250 kills", MIN, 250, _kills, lambda c: c["stats"]["kills_total"] > 250),
        ("Plus de 25 continues", MIN, 25, _continues, lambda c: c["stats"]["continues"] > 25),
    ]),
    (36, "JAGUAR", [
        ("Plus de 75 alertes", MIN, 75, _alertes, lambda c: c["stats"]["alertes"] > 75),
        ("Moins de 250 kills", MAX, 250, _kills, lambda c: c["stats"]["kills_total"] <= 250),
        ("Moins de 25 continues", MAX, 25, _continues, lambda c: c["stats"]["continues"] <= 25),
    ]),
    (37, "PANTHER", [
        ("Plus de 75 alertes", MIN, 75, _alertes, lambda c: c["stats"]["alertes"] > 75),
        ("Plus de 250 kills", MIN, 250, _kills, lambda c: c["stats"]["kills_total"] > 250),
        ("Moins de 25 continues", MAX, 25, _continues, lambda c: c["stats"]["continues"] <= 25),
    ]),
    (38, "LEOPARD", [
        ("Plus de 75 alertes", MIN, 75, _alertes, lambda c: c["stats"]["alertes"] > 75),
        ("Moins de 250 kills", MAX, 250, _kills, lambda c: c["stats"]["kills_total"] <= 250),
        ("Plus de 25 continues", MIN, 25, _continues, lambda c: c["stats"]["continues"] > 25),
    ]),
    (39, "PUMA", [
        ("Plus de 75 alertes", MIN, 75, _alertes, lambda c: c["stats"]["alertes"] > 75),
        ("Plus de 250 kills", MIN, 250, _kills, lambda c: c["stats"]["kills_total"] > 250),
        ("Plus de 25 continues", MIN, 25, _continues, lambda c: c["stats"]["continues"] > 25),
    ]),
    (40, "CHICKEN", [
        ("Plus de 150 alertes", MIN, 150, _alertes, lambda c: c["stats"]["alertes"] >= 150),
        ("Plus de 500 kills", MIN, 500, _kills, lambda c: c["stats"]["kills_total"] >= 500),
        ("Plus de 50 continues", MIN, 50, _continues, lambda c: c["stats"]["continues"] >= 50),
        ("Plus de 50 objets de soin utilisés", MIN, 50, _soins, lambda c: c["stats"]["soins_utilises"] >= 50),
        ("Plus de 35 heures de jeu", MIN, 35, _playtime, lambda c: c["playtime_h"] >= 35),
    ]),
]


# Recompenses associees a certains emblemes (liste utilisateur, 2026-09-06).
# Les 32 autres emblemes ne donnent pas de recompense individuelle connue -
# ils comptent surtout pour la collection complete des 40, qui debloque a
# elle seule la chanson iPod "Snake Eater" (non liee a un emblème precis,
# affichee separement - voir EmblemsPanel).
EMBLEM_REWARDS = {
    "BIG BOSS": "Patriot + FaceCamo Big Boss + chanson iPod \"Big Boss\".",
    "FOX HOUND": "Thor .45-70.",
    "FOX": "Desert Eagle Long Barrel.",
    "HOUND": "Type 17.",
    "OCTOPUS": "Camouflage optique (Stealth Camouflage).",
    "ASSASSIN": "Tenue d'Altaïr (Assassin's Creed).",
    "PIGEON": "Bandana.",
    "LITTLE GRAY": "Lié à la collection d'armes complète - pas de récompense matérielle propre connue.",
    "CHICKEN": "Camouflage Cadavre (Octocamo).",
}


EMBLEM_BITMASK_OFFSET = 0x18  # u8[5], 40 bits, LSB=emblem 1, carry-forward cumulatif


def read_obtained_emblems(mgs4_sav_path: str) -> set[int]:
    """Registre reel et persistant des emblemes deja obtenus, lu directement
    depuis MGS4.SAV (bitmask 5 octets a 0x18, bit0=embleme1). Trouve par
    correlation directe : l'utilisateur a donne la liste exacte de ses 22
    emblemes obtenus, le bitmask calcule a partir de cette liste correspond
    OCTET POUR OCTET a ce qui est stocke a cet offset - confirme sur les 5
    slots disponibles, y compris la progression cumulative entre parties
    successives (voir notes.md). Aucun besoin de recalculer les predicats
    pour ce qui est deja obtenu : c'est ecrit tel quel dans le fichier."""
    with open(mgs4_sav_path, "rb") as f:
        data = decrypt(f.read())
    value = int.from_bytes(data[EMBLEM_BITMASK_OFFSET:EMBLEM_BITMASK_OFFSET + 5], "little")
    return {i + 1 for i in range(40) if value & (1 << i)}



ENDING_STAGE_CODE = "s00a10l"  # "Epilogue : cimetiere" - seul stage atteint par une partie terminee


def compute_emblems(mgs4_sav_path: str, metadata_path: str) -> list[dict]:
    """Retourne les 40 emblemes avec leur etat par rapport aux stats de CE
    slot precisement (le jeu ne les evalue reellement qu'a l'ecran de
    resultats final - voir notes.md) :
      unlocked   : toutes les conditions sont deja vraies (serait obtenu
                   maintenant, ou l'a deja ete si la partie est terminee).
      impossible : soit une condition MAX a deja ete franchie (ne peut plus
                   redevenir vraie), soit la partie est deja TERMINEE (elle
                   ne progressera plus jamais, donc tout ce qui n'est pas
                   deja acquis est definitivement hors de portee pour ELLE).
      (ni l'un ni l'autre = partie encore en cours et encore possible avec
      plus de progression)
    """
    stats = read_stats(mgs4_sav_path)
    meta = read_metadata_summary(metadata_path)
    is_completed = read_progress_info(mgs4_sav_path)["stage_code"] == ENDING_STAGE_CODE
    context = {
        "stats": stats,
        "playtime_h": meta["playtime_secondes"] / 3600,
        "difficulty_score": meta["difficulte_score"],
        "weapon_count": count_acquired_weapons(mgs4_sav_path),
    }
    results = []
    for eid, name, conditions in EMBLEMS:
        satisfied = [
            (f"{desc} ({_format_emblem_detail(value_fn(context), threshold)})", kind, bool(check(context)))
            for desc, kind, threshold, value_fn, check in conditions
        ]
        unlocked = all(ok for _, _, ok in satisfied)
        if is_completed:
            impossible = not unlocked
            # Partie terminee : plus aucune progression possible, une
            # condition MIN pas encore atteinte est donc tout aussi morte
            # qu'une condition MAX depassee.
            dead = lambda kind, ok: not ok
        else:
            impossible = any(kind == MAX and not ok for _, kind, ok in satisfied) and not unlocked
            # Partie en cours : seule une condition MAX depassee est
            # definitivement morte (ne peut plus redevenir vraie) - une
            # condition MIN pas encore atteinte reste possible plus tard.
            dead = lambda kind, ok: kind == MAX and not ok
        # Une condition MIN ("plus de X") repart a zero a chaque nouvelle
        # partie - si elle est vraie maintenant, c'est forcement grace aux
        # progres de CETTE partie. Une condition MAX ("moins de X", "0 X")
        # est en revanche souvent trivialement vraie des le tout debut de
        # n'importe quelle partie (ex. RAVEN, "moins de 5h de jeu") - sa
        # verite actuelle ne prouve rien sur QUAND elle a ete remplie. Sert
        # a distinguer "obtenu sur cette partie" (fiable) de "obtenu sur une
        # partie precedente" (gui_app.py) quand un embleme deja obtenu n'a
        # que des conditions MAX.
        has_reliable_min_condition = any(kind == MIN for _, kind, _ in satisfied)
        results.append({
            "id": eid,
            "name": name,
            "requirement": [
                {"text": desc, "exceeded": dead(kind, ok)} for desc, kind, ok in satisfied
            ],
            "unlocked": unlocked,
            "impossible": impossible,
            "completed": is_completed,
            "has_reliable_min_condition": has_reliable_min_condition,
            "reward": EMBLEM_REWARDS.get(name, ""),
        })
    return results


def _format_emblem_value(value) -> str:
    """Formate une valeur de condition d'embleme pour l'affichage "x/y" :
    entier tel quel, flottant arrondi a l'entier s'il est tres proche (temps
    convertis depuis des frames), sinon avec 1 decimale (temps de jeu en
    heures)."""
    if isinstance(value, float):
        if abs(value - round(value)) < 0.05:
            return str(round(value))
        return f"{value:.1f}"
    return str(value)


def _format_emblem_detail(value, threshold) -> str:
    """Cas des conditions de difficulte (threshold=None) : le seuil est deja
    nomme dans la description elle-meme ("Difficulte : X ou plus"), afficher
    le seuil a cote ferait doublon - on montre juste la difficulte actuelle,
    en Title Case pour la lisibilite dans la phrase (les noms sont stockes en
    MAJUSCULES dans DIFFICULTY_NAMES, comme affiches en jeu)."""
    if threshold is None:
        return value.title() if isinstance(value, str) else _format_emblem_value(value)
    return f"{_format_emblem_value(value)}/{_format_emblem_value(threshold)}"


# Tableau d'etat des objets (camouflages, costumes, statuettes, chansons
# iPod...), source zexk/bbtracker pour l'offset/la taille (u16[99], IDs 0 a
# 98), noms d'ID recoupes depuis une table Cheat Engine communautaire
# (MGS4.CT) puis VERIFIES par nous-memes par diff temporel sur nos propres
# saves (voir notes.md, section "Tableau objets"). Deux conventions de
# "verrou" coexistent selon l'objet (0 ou 65535 selon les cas) mais la
# valeur "possede" est toujours exactement 1 pour tout ce qui est liste ici
# (costumes/camouflages/statuettes/chansons) - jamais 2 ni une autre valeur,
# contrairement au tableau d'armes. Les 5 premiers IDs (rations, nouilles,
# etc.) et quelques autres sont des COMPTEURS (quantite en stock), pas des
# booleens - non repris ici, ce n'est pas le sujet des nouveaux onglets.
ITEM_STATE_OFFSET = 0x0526
ITEM_STATE_COUNT = 99

# Objets "generaux" : IDs 0x00-0x13, la seule zone du tableau d'objets pas
# encore couverte par un autre groupe (Tenues/FaceCamo/Gilet/Statuettes/
# Chansons). Noms reels quand confirmes par test isole ; sinon nom
# generique "Objet #NN" (meme convention que "Arme #NN" pour les armes non
# identifiees) - affiche quand meme, comme demande, plutot que masque.
GENERAL_ITEM_NAMES = {i: f"Objet #{i:02d}" for i in range(0x14)}
GENERAL_ITEM_NAMES.update({
    # 2026-09-02 : "Baril" (0x02) INFIRME par l'utilisateur - le Baril est
    # limite a 1 exemplaire (booleen, pas une quantite), or item[0x02]
    # continue de s'incrementer normalement (14->15 puis 15 en ramassant
    # des nouilles). Reassigne a "Nouilles". Vrai ID du Baril inconnu,
    # probablement booleen comme iPod/Seringue (cf. tache differee sur
    # Baril/Boite en carton).
    # 2026-09-02 : capture d'ecran du sac a dos "Guerison" en jeu (8 objets
    # de soin avec leurs quantites exactes) - a permis de confirmer par
    # elimination "Ration" (les 3 objets a 15 dans ce sac sont Ration/
    # Nouilles/Regain ; Nouilles et Regain deja confirmes par diff isole
    # ailleurs, donc le 3e ID a 15 - 0x01 - est forcement Ration) et par
    # correspondance numerique unique "Compresse" (seul objet a 14).
    0x01: "Ration",
    0x02: "Nouilles",
    0x03: "Regain",
    0x04: "Pentazémine",
    0x05: "Compresse Arsenal",  # nom exact confirme par popup d'acquisition (2026-09-02)
    # "Boite en carton" (0x09) : RETABLI (2026-09-02). Avait ete retire car
    # sa valeur (25) restait figee sur toute la chronologie d'une autre
    # partie sans jamais varier, ce qui ressemblait a une valeur
    # structurelle plutot qu'un vrai objet. Test isole sur cette partie
    # fraiche : popup d'acquisition "Boite en carton" au moment exact ou
    # item[0x09] passe de 65535 a 25. Donc c'est bien le bon ID - la valeur
    # fixe "25" n'est pas une quantite, juste la facon dont le jeu encode
    # "possede" pour cet objet (comme iPod encode "possede" avec 1) ;
    # "toujours 25" sur l'autre partie voulait juste dire qu'elle avait ete
    # ramassee avant le premier echantillon disponible. Comportement
    # booleen confirme par l'utilisateur (max 1 exemplaire) - voir
    # BOOLEAN_GENERAL_ITEMS plus bas.
    0x09: "Boîte en carton",
    # CONFIANCE BASSE : Solid Eye et Metal Gear Mk. II obtenus ensemble
    # (meme evenement Otacon, Acte 1) - 2 cases flushent en meme temps
    # (0x06, 0x07), attribution par ordre d'apparition/convention (comme
    # Operator/1911 Modifie/Thor .45-70) mais SANS certitude sur qui est
    # qui.
    0x06: "Solid Eye",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'objets. Batterie pour le Solid Eye
    # (voir notes.md, section sur le decalage des chansons +1 - deja
    # repere a l'epoque mais jamais formalise ici).
    0x3c: "Batterie (Solid Eye)",
    0x07: "Metal Gear Mk. II",
    # Baril : enfin trouve (2026-09-02) apres plusieurs faux departs (0x02,
    # 0x09). Test isole propre : item[0x0a] seul objet qui change (65535 a
    # 1) au moment exact du popup "Baril". Comportement booleen confirme
    # (valeur 1, pas une grosse quantite comme la Boite en carton).
    0x0a: "Baril",
    0x08: "Appareil Photo",
    # 2026-09-02 : "iPod" (0x0a) INFIRME - l'utilisateur confirme (avec
    # insistance) que l'iPod est disponible DES LE DEBUT du jeu, avec la
    # Ration. Or item[0x0a] ne passe a 1 que vers s01a57l (fin de la
    # premiere zone rouge), alors qu'item[0x0b] vaut 1 sur absolument
    # TOUTES les saves disponibles, y compris la toute premiere du jeu
    # (s00a10l) - c'est donc lui qui correspond a l'iPod (dispo des le
    # debut, comme la Ration), pas 0x0a. Reassigne. Vrai role de 0x0a
    # de nouveau inconnu (transition reelle vers s01a57l a expliquer).
    0x0b: "iPod",
    # 2026-09-02 : confirme via la chronologie complete des saves - entre le
    # tout debut du jeu (s01a00l) et l'etape suivante (s01a10l), item[0x0d]
    # est le seul qui passe de 65535 a 1, et reste acquis ensuite sur
    # toutes les saves posterieures. Correspond a l'obtention des
    # cigarettes rapportee par l'utilisateur a ce moment precis.
    0x0d: "Cigarettes",
    0x0c: "Intercepteur de signal",
    0x0e: "Muña",  # voir notes.md : anciennement etiquete "Camouflage furtif" par erreur - confiance haute, reconfirme par test isole 2026-09-05
    # Confiance haute (2026-09-05) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'objets.
    0x11: "Seringue",
    # Confirme par test isole (partie fraiche) : seul item qui change entre
    # deux saves consecutives, en meme temps que le Mk.2 Pistol/silencieux.
    # Nom exact recupere via screenshot in-jeu (menu Objets) : "PRISE
    # SCANNER" (nom FR du "Scanning Plug").
    # Anomalie observee (2026-09-04) : en rechargeant l'ancienne save ou
    # item[0x12] vaut 65535 dans le fichier (fichier verifie inchange), la
    # Prise Scanner apparaissait deja dans l'inventaire en jeu. Ecart entre
    # etat fichier et etat affiche en jeu, mecanique exacte non comprise
    # (peut-etre un objet fourni au chargement pour ce segment de mission,
    # independamment du flag persistant) - mais l'identification de l'ID
    # lui-meme reste bonne (test isole propre, nom confirme par screenshot).
    0x12: "Prise Scanner",
    # Trouves (2026-09-04) grace au fichier MGS4.CT (table Cheat Engine)
    # fourni par l'utilisateur : categorie "Gadgets", indices bases sur un
    # decalage constant de +1 par rapport a notre propre numerotation
    # (confirme sur plusieurs entrees deja connues : Solid Eye CT=5/nous=6,
    # Muna CT=D/nous=E, Seringue CT=10/nous=11). Applique aux deux entrees
    # "objets speciaux" du CT (Bandana=E, Stealth=F) -> nous 0x0f/0x10.
    # Camouflage furtif confirme a 100% sur 4 saves connues (verrouille/
    # debloque) + verifie a valeur binaire propre (65535 ou 1 seulement)
    # sur toutes les saves disponibles. Bandana coherent avec le CT (jamais
    # vu a 1 sur nos echantillons, mais pas encore de confirmation positive
    # directe).
    0x0f: "Bandana",
    0x10: "Camouflage optique",
})

# Note : pas d'entree pour "ENVG" ici (integre au Solid Eye, pas un item a
# part - remarque de l'utilisateur).
#
# Correction (utilisateur) : les 10 couleurs 0x2c-0x35 ne sont PAS des
# patterns Octocamo mais des couleurs de GILET (vest). Renommees en
# consequence.
#
# Les vrais camouflages "lies a l'Octocamo" sont les 5 camouflages
# speciaux/caches documentes par le site Metal Gear Generation (section
# "Camouflages speciaux" de camos.php, voir plus haut dans notes.md) : Camo
# Cadavre (41+ mort a la fin du jeu), Camo Digit R, Camo Digit B, Camo
# Rire, Camo Rage (ces 3 derniers via le menu Extra/DLC, disponibilite sur
# le portage PC inconnue). Hypothese : ce sont les ID 0x14-0x18, qui
# valaient tous 0 sur tous nos echantillons quand on pensait qu'il
# s'agissait de FaceCamo/ENVG/Kerotan/Ga-Ko/Octocamo de base (tous
# invalides - voir plus haut). Contrairement a ces derniers (qui DEVRAIENT
# valoir 1 tot dans toute partie avancee), les camouflages speciaux sont
# rares/optionnels (personne dans notre echantillon n'a ete tue 41+ fois),
# donc rester a 0 partout ne les contredit pas. Correspondance de compte
# exacte (5 camouflages speciaux documentes = 5 ID toujours a 0) mais
# **ORDRE NON VERIFIE** (aucun de nos echantillons ne les a jamais
# debloques, donc aucune transition observable) - a confirmer si un jour
# quelqu'un debloque un de ces camouflages.
# INFIRME : voir notes.md "Camo Cadavre introuvable". Garde pour memoire
# (et pour ne pas re-proposer ces memes ID par erreur plus tard), mais plus
# utilise nulle part (voir CAMO_GROUPS ci-dessous).
SPECIAL_CAMO_NAMES = {
    0x14: "Camo Cadavre",
    0x15: "Camo Digit R",
    0x16: "Camo Digit B",
    0x17: "Camo Rire",
    0x18: "Camo Rage",
}

# 2026-09-02 : nouvelle correction suite a l'epilogue (jeu termine), qui a
# debloque 5 nouvelles couleurs (Vert/Bleu/Rouge/Orange/Brun) confirmees a
# la fois par capture d'ecran du menu "Veste tactique" (5 lignes tagees
# "NOUVEAU", dans cet ordre precis) ET par diff isole (item[0x32] a 0x36
# passent de 65535 a 1 ensemble, exactement 5 cases). Ca revele que
# l'ancien "0x2c = Vert" etait FAUX : 0x2c reste a 65535 (jamais obtenu)
# avant ET apres ce deblocage - ce n'est donc aucune des 5 couleurs deja
# possedees (Kaki/Olive/Noir/Gris/Bleu marine, qui elles ne bougent pas et
# correspondent bien a 0x2d-0x31) ni une des 5 nouvelles (0x32-0x36).
# Hypothese "0x2c = Doré" INFIRMEE (2026-09-02) : test isole montre
# item[0x2c] passant de 65535 a 1 suite a l'obtention du FaceCamo "Cyborg
# Raiden - Visiere ouverte" - rien a voir avec un gilet. Retire d'ici,
# vraie position de "Gilet - Doré" de nouveau inconnue (voir FACECAMO_NAMES
# pour la vraie identite de 0x2c).
VEST_NAMES = {
    # CORRIGE (2026-09-25) : l'ancienne attribution 0x2d/0x2e/0x2f/0x30 =
    # Olive/Noir/Gris/Bleu marine etait fausse - jamais confirmee par
    # isolation individuelle a l'origine, juste deduite par ordre suppose.
    # Test isole propre par l'utilisateur (les 5 forcees a verrouille,
    # puis debloquees une par une en gardant les precedentes actives -
    # methode cumulative plutot que "une seule a la fois puis
    # reverrouiller") : 0x2e=Olive, 0x2f=Noir, 0x30=Gris confirmes.
    # 0x31 confirme par l'utilisateur = Bleu marine (pas Kaki comme
    # suppose un temps). Comme Kaki, reste portable meme verrouille
    # (65535) - meme phenomene que le Masterkey/plusieurs silencieux
    # (voir DREBIN_LOCK_EXCEPTIONS) : probablement une couleur de depart
    # que le jeu ne revalide jamais via ce flag.
    # 0x2d ne fait jamais apparaitre de couleur nouvelle lors des tests
    # (teste 2 fois) - MAIS ce resultat est indecidable pour une couleur
    # deja visible en permanence : Kaki (comme Bleu marine) est deja
    # affichee des le debut du test quel que soit son etat reel, donc
    # rien ne permet de distinguer "0x2d = Kaki" de "0x2d = role inconnu
    # sans rapport". Kaki reste donc le candidat le plus probable pour
    # 0x2d (seul nom du groupe encore sans ID confirme), mais CONFIANCE
    # BASSE - pas confirmable par cette methode.
    0x2d: "Gilet - Kaki",
    0x2e: "Gilet - Olive",
    0x2f: "Gilet - Noir",
    0x30: "Gilet - Gris",
    0x31: "Gilet - Bleu marine",
    # Les 5 suivantes confirmees par le lot NOUVEAU ci-dessus, dans l'ordre
    # exact affiche par le menu (correspond a l'ordre croissant des ID).
    0x32: "Gilet - Vert",
    0x33: "Gilet - Bleu",
    0x34: "Gilet - Rouge",
    0x35: "Gilet - Orange",
    0x36: "Gilet - Brun",
}

# Hypothese INFIRMEE (voir notes.md, section "Camo Cadavre introuvable") :
# l'utilisateur confirme le Camo Cadavre debloque en jeu sur le slot 91DA17,
# alors que TOUS les ID 0x14-0x18 y valent 0 - donc SPECIAL_CAMO_NAMES ne
# correspond a rien de reel. Tableau d'objets scanne integralement (0x00 a
# 0x62, les 99 entrees) sur ce meme slot : aucun autre ID inexplique ne
# vaut 1 non plus. Retire de l'affichage en attendant de retrouver le bon
# emplacement (probablement MGS4SYS.SAV, le fichier partage entre slots,
# vu que le declencheur - 41 morts "a la fin du jeu" - sonne comme un bonus
# global plutot que par sauvegarde). Ordre d'affichage voulu par
# l'utilisateur (Octocamo en premier, Gilet ensuite) conserve pour le jour
# ou le bon ID sera trouve.
# Les 5 statuettes (Beauty and the Beast Unit), chacune obtenue en vainquant
# l'unite correspondante. CONFIANCE BASSE sur la correspondance ID<->nom :
# on sait qu'il s'agit de ces 5 unites (confirme par recherche web), mais
# PAS dans quel ordre le jeu les range dans ce tableau - ordre A-E ci-dessous
# choisi arbitrairement (ordre d'apparition dans l'histoire), a corriger
# des qu'un ID precis sera confirme en jeu (ex: le joueur obtient une
# statuette precise, on regarde quel ID passe a 1).
# Noms B-E (Raging Raven/Crying Wolf/Screaming Mantis) retires 2026-09-01 :
# un test isole a montre que "Laughing Octopus" etait en realite a 0x38
# (etiquete "Raging Raven"), pas 0x36 - notre ordre A-E devine par lettre
# alphabetique etait donc faux. Seuls Unite FROG (0x37) et Laughing
# Octopus (0x38) sont confirmes individuellement pour l'instant. Les 3
# autres ID restent affiches (pour garder le compte "X/5") mais sous un
# nom generique plutot que de re-deviner un ordre sans preuve - a
# completer au fur et a mesure que l'utilisateur obtient chacune sur une
# partie fraiche.
FIGURE_NAMES = {
    0x37: "Unité FROG",
    0x38: "Laughing Octopus",
    0x39: "Raging Raven",
    0x3a: "Crying Wolf",
    # INFIRME (2026-09-02) : 0x36 avait ete deduit par elimination (seule
    # case du groupe 0x36-0x3a restant a 65535 sur une save ou les 4 autres
    # etaient deja obtenues) - jamais teste directement. Sur cette partie
    # fraiche, l'obtention de Screaming Mantis n'a PAS fait bouger 0x36
    # (reste 65535) mais a fait passer 0x3b de 65535 a 1 - test isole,
    # confirmation directe. Vrai ID : 0x3b. Le sens reel de 0x36 est
    # de nouveau inconnu.
    0x3b: "Screaming Mantis",
}

# Condition d'obtention affichee au clic (voir gui_app.CollectionPanel,
# mode "show_detail"). Sources : recherche web (guides de completion MGS4),
# pas verifie directement par nous.
FIGURE_CONDITIONS = {
    "Unité FROG": (
        "Vaincre l'unité FROG avec des armes non létales, Acte 1 (Palais "
        "de l'Avent). Cas particulier : contrairement aux 4 autres, la "
        "statuette se trouve après le combat."
    ),
    "Laughing Octopus": (
        "Vaincre Laughing Octopus avec des armes non létales, Acte 2 "
        "(station de recherche, Amérique du Sud)."
    ),
    "Raging Raven": (
        "Vaincre Raging Raven avec des armes non létales, Acte 3 (tour de "
        "pierre, Prague, Europe de l'Est)."
    ),
    "Crying Wolf": (
        "Vaincre Crying Wolf avec des armes non létales, Acte 4 (champ de "
        "neige, Shadow Moses)."
    ),
    "Screaming Mantis": "Vaincre Screaming Mantis, Acte 5 (Outer Haven).",
}

# Camouflages faciaux (Facecamos) et tenues (Tenues), deux categories que
# le jeu distingue et qui etaient auparavant regroupees a tort dans
# CAMO_NAMES. Noms et conditions de deblocage confirmes par une source
# externe francophone independante (site fan Metal Gear Generation,
# http://metalgeargeneration.free.fr/mgs4/camos.php, page "Camouflages" de
# la section MGS4), qui documente une classification en 3 groupes :
# Facecamos / Tenues / Camouflages speciaux.
#
# Deux corrections apportees APRES verification directe par l'utilisateur
# en jeu (plus fiable que nos propres deductions) :
#   - 0x1c/0x1d : la table Cheat Engine d'origine les etiquetait "Altair"/
#     "Suit", dans le mauvais ordre. L'utilisateur confirme avoir le
#     Costume de Snake mais PAS le costume d'Altair - inverse de ce que
#     lisaient nos donnees avec l'etiquetage d'origine. Corrige : 0x1c =
#     Costume de Snake, 0x1d = Costume d'Altair.
#   - FaceCamo de base : la table d'origine le mettait a 0x14, qui vaut 0
#     (non obtenu) sur tous nos slots alors que l'utilisateur confirme
#     l'avoir. C'est en realite 0x1e (etiquete "Face Camo (dup?)" par la
#     table d'origine, jamais utilise jusqu'ici) qui vaut 1 partout et
#     correspond donc au vrai FaceCamo. Le role reel de 0x14 reste inconnu.
#
# Les 4 "Beauty" facecamos (S/L/R/C dans la table Cheat Engine d'origine)
# sont supposees correspondre aux initiales Screaming/Laughing/Raging/
# Crying par ordre alphabetique - plausible mais pas verifie par diff
# temporel (les 4 valent deja 1 sur tous nos slots disponibles).
# Corrections 2026-09-01 (test isole sur partie fraiche, plus fiable que
# l'ancienne "preuve" par recoupement sur des parties deja avancees - meme
# lecon que Camouflage furtif/Muna) :
#   - FaceCamo (de base) est en realite a 0x1f, pas 0x1e. L'ancien "Jeune
#     Snake" qui occupait 0x1f est donc FAUX - sa vraie position est
#     inconnue, retire de la liste en attendant.
#   - Laughing Beauty est en realite a 0x22, pas 0x21 (l'hypothese des
#     initiales S/L/R/C de la table Cheat Engine d'origine est donc
#     infirmee, au moins pour celle-ci). L'ancien "Raging Beauty" qui
#     occupait 0x22 est donc FAUX aussi - retire en attendant. Crying/
#     Screaming Beauty et "Jeune Snake avec bandana" restent affiches mais
#     avec une confiance revue a la baisse (meme famille de suspicion,
#     pas encore d'evidence directe pour les corriger).
# 2026-09-01 : test isole confirme 0x20="Jeune Snake" et 0x25="Jeune Snake
# avec bandana" (pas Screaming Beauty / Roy Campbell comme suppose avant -
# ce dernier avait ete complete par elimination suite au swap Otacon/
# Campbell, jamais reellement isole individuellement). Roy Campbell et
# Screaming Beauty retires, position reelle de nouveau inconnue. L'ancien
# 0x24 "Jeune Snake avec bandana" etait donc aussi faux, retire.
FACECAMO_NAMES = {
    # Confiance haute (2026-09-05) : test isole propre sur une partie
    # differente, seul cet ID a bouge dans tout le tableau d'objets.
    0x1f: "FaceCamo",
    0x20: "Jeune Snake",
    0x25: "Jeune Snake avec bandana",
    0x26: "Otacon",
    # 2026-09-02 : "Raiden B" (0x2a) INFIRME - l'utilisateur confirme via le
    # menu en jeu (capture d'ecran "Visage") qu'il n'y a bien qu'UNE seule
    # entree Raiden dans la liste, pas deux. Or 0x2a valait 1 sur une save
    # de reprise (Acte 1, tout deja debloque en NG+/carry-over) - c'est en
    # realite "MGS1", l'entree visible dans ce menu juste apres
    # "Jeune Snake avec bandana", dont la position reelle etait inconnue
    # depuis son retrait precedent (voir plus haut). Coherent avec sa
    # condition "obtenu automatiquement au debut de l'Acte 4" (deja vraie
    # sur une partie qui a fini le jeu au moins une fois).
    0x2a: "MGS1",
    # Nom complet demande par l'utilisateur plutot que "Raiden A/B" - repris
    # de sa description au moment de l'obtention reelle ("Cyborg Raiden -
    # Visiere fermee"). Seule entree Raiden confirmee, l'ancienne "Raiden A"
    # correspondait au meme ID que celle-ci (test isole 2026-09-01).
    0x2b: "Raiden - Visière fermée",
    # Confirme par test isole 2026-09-02 - a fait tomber au passage
    # l'hypothese "Gilet - Doré" a ce meme ID (voir VEST_NAMES).
    0x2c: "Raiden - Visière ouverte",
    # Corrige (2026-09-05) : l'ancien "0x28" (jamais confirme par test
    # isole, repris tel quel de la table Cheat Engine d'origine) restait
    # verrouille meme apres obtention en jeu du FaceCamo Drebin. Test isole
    # propre : c'est item[0x29] qui passe de 65535 a 1. Identite reelle de
    # 0x28 de nouveau inconnue.
    0x29: "Drebin",
    0x22: "Laughing Beauty",
    0x23: "Raging Beauty",  # confirme par test isole 2026-09-01 (etait "Crying Beauty")
    0x24: "Crying Beauty",  # confirme par test isole 2026-09-01, consecutif a 0x22/0x23
    # 2026-09-02 : "Big Boss" (0x27) INFIRME - test isole (partie fraiche,
    # Acte 1) montre 0x27 passant de 65535 a 1 suite a l'obtention du
    # FaceCamo Campbell, alors que le rang Big Boss est impossible a ce
    # stade du jeu. Reassigne a "Campbell". Vrai ID de "Big Boss" de
    # nouveau inconnu.
    0x27: "Campbell",
    0x21: "Screaming Beauty",  # confirme par test isole 2026-09-02
    # Big Boss (0x28) : identite enfin retrouvee (2026-09-25) via le
    # nouvel onglet "FaceCamo" du trainer - force a 1 en memoire live,
    # confirme en jeu par l'utilisateur. Resout l'ancien "Vrai ID de Big
    # Boss de nouveau inconnu" (voir commentaire sur Campbell ci-dessus).
    0x28: "Big Boss",
}

# Ordre d'affichage reel du menu "Visage" en jeu (2026-09-25, confirme par
# 2 captures d'ecran successives de l'utilisateur - NE correspond PAS a
# l'ordre croissant des ID). "Aucun" (pas de FaceCamo equipe) n'a pas de
# vrai ID, pas dans ce dict. Meme mecanisme que WEAPON_SORT_ORDER plus
# bas pour les armes (position de tri explicite plutot que tri par ID).
FACECAMO_SORT_ORDER: dict[int, int] = {
    0x1f: 0,   # FaceCamo
    0x20: 1,   # Jeune Snake
    0x25: 2,   # Jeune Snake avec bandana
    0x2a: 3,   # MGS1
    0x22: 4,   # Laughing Beauty
    0x23: 5,   # Raging Beauty
    0x24: 6,   # Crying Beauty
    0x21: 7,   # Screaming Beauty
    0x27: 8,   # Campbell
    0x26: 9,   # Otacon
    0x2b: 10,  # Raiden - Visiere fermee (= "Raiden A" en jeu)
    0x2c: 11,  # Raiden - Visiere ouverte (= "Raiden B" en jeu)
    0x29: 12,  # Drebin
    0x28: 13,  # Big Boss
}

# "Doré"/"FaceCamo Doré" (bonus precommande/edition speciale, vus dans le
# menu "Visage") retires le temps de decider comment les compter (voir
# discussion utilisateur 2026-09-02) - pas de vrai ID de save connu pour
# l'instant de toute facon.

# Conditions d'obtention (source : site Metal Gear Generation, voir plus
# haut dans notes.md), affichees au clic comme pour les statuettes.
FACECAMO_CONDITIONS = {
    "FaceCamo": "Obtenu automatiquement après avoir vaincu Laughing Octopus, Acte 2. Augmente le pourcentage de camouflage.",
    "Jeune Snake": "Obtenu automatiquement au début de l'Acte 3.",
    "Jeune Snake avec bandana": "Obtenu automatiquement au début de l'Acte 3 (comme Jeune Snake, avec un bandana en plus).",
    "MGS1": "Obtenu automatiquement au début de l'Acte 4.",
    "Campbell": "Le percuter avec le Mk.II pendant le briefing de mission interactif n°1.",
    "Otacon": "Le percuter avec le Mk.II pendant n'importe quel briefing de mission interactif.",
    "Raiden - Visière fermée": "Percuter Sunny avec le Mk.II pendant un briefing de mission interactif (par élimination, à confirmer).",
    "Raiden - Visière ouverte": "Percuter Naomi avec le Mk.II pendant un briefing de mission interactif (confirmé par l'utilisateur).",
    "Drebin": "Avoir au moins 60 armes.",
    "Laughing Beauty": "Vaincre Laughing Octopus avec des armes non létales.",
    "Raging Beauty": "Vaincre Raging Raven avec des armes non létales.",
    "Crying Beauty": "Vaincre Crying Wolf avec des armes non létales.",
    "Screaming Beauty": "Vaincre Screaming Mantis.",
    # Orpheline depuis l'infirmation de 0x27 (voir FACECAMO_NAMES) - gardee
    # de cote pour reutilisation si la vraie case est retrouvee un jour.
    "Big Boss (position inconnue)": "Avoir le rang BIG BOSS.",
    # Confirme par l'utilisateur (2026-09-05) + coherent avec le diff isole
    # documente plus haut (VEST_NAMES) : les 5 premieres sont disponibles
    # des le debut de la partie, les 5 suivantes se debloquent
    # automatiquement en terminant le jeu une premiere fois.
    "Gilet - Olive": "Disponible dès le début de la partie.",
    "Gilet - Noir": "Disponible dès le début de la partie.",
    "Gilet - Gris": "Disponible dès le début de la partie.",
    "Gilet - Bleu marine": "Disponible dès le début de la partie.",
    "Gilet - Kaki": "Disponible dès le début de la partie.",
    "Gilet - Vert": "Débloqué automatiquement en terminant le jeu une première fois.",
    "Gilet - Bleu": "Débloqué automatiquement en terminant le jeu une première fois.",
    "Gilet - Rouge": "Débloqué automatiquement en terminant le jeu une première fois.",
    "Gilet - Orange": "Débloqué automatiquement en terminant le jeu une première fois.",
    "Gilet - Brun": "Débloqué automatiquement en terminant le jeu une première fois.",
}

# Les 21 motifs OctoCamo (liste complete recompteee par l'utilisateur,
# 2026-09-06 - ordre officiel du jeu). PAS RELIES A LA VRAIE SAVE : on a
# prouve que nos anciens ID d'origine (0x14-0x18, ex section "Camouflages
# speciaux") sont faux (l'utilisateur a confirme le Camo Cadavre debloque
# alors que ces ID valaient tous 0 - voir notes.md), et on n'a pas retrouve
# les vrais emplacements pour aucun des 21. Affiches ici a titre indicatif
# uniquement (toujours "non suivi", jamais dore), avec leur effet special
# au clic quand il y en a un - pas un vrai etat obtenu/verrouille.
OCTOCAMO_INFO = {
    "Infiltration": "Motif de camouflage standard, sans effet spécial.",
    "Olive": "Motif de camouflage standard, sans effet spécial.",
    "Tigré": "Motif de camouflage standard, sans effet spécial.",
    "Forêt": "Motif de camouflage standard, sans effet spécial.",
    "3 Couleurs Désert": "Motif de camouflage standard, sans effet spécial.",
    "Marpat": "Motif de camouflage standard, sans effet spécial.",
    "Cadavre": "Obtenu en étant tué plus de 41 fois au cours d'une même partie. Permet de se faire passer pour un cadavre : les soldats, et même certaines armes sans pilote, peuvent s'y méprendre lorsque Snake reste allongé au sol.",
    "Pleurs": "Fait pleurer les ennemis lorsqu'ils repèrent Snake.",
    "Digit. B": "Motif imitant l'eau : camouflage optimal dans ou à proximité de l'eau.",
    "Digit. R": "Motif de camouflage rouge, sans effet spécial.",
    "Mouche": "Effet très puissant en combat rapproché, lié à l'odeur qui attire les mouches — augmente en contrepartie le stress de Snake.",
    "Gear": "Réduit les pertes de Psyché et améliore l'efficacité du camouflage.",
    "Haven": "Porte le Camo Index à 99 % tant que Snake reste immobile, mais accélère la dégradation de sa vie et de sa Psyché.",
    "Rire": "Fait rire les ennemis lorsqu'ils repèrent Snake.",
    "Metal": "Réduit de moitié les pertes de vie et de Psyché, au prix de −10 % de Camo Index.",
    "Snake": "Assomme les soldats normaux en un seul coup et atténue certains effets de stress et de douleur, au prix de −10 % de Camo Index.",
    "Rage": "Fait entrer les ennemis en rage lorsqu'ils repèrent Snake.",
    "Hurler": "Fait hurler et paniquer les ennemis lorsqu'ils repèrent Snake.",
    "Beauté": "Absorbe la Psyché de l'ennemi en combat rapproché ; le stress de Snake double en plein soleil.",
    "Précommande": "Obtenu en précommandant Metal Gear Solid: Master Collection Vol. 2.",
    "Doré": "Obtenu en ayant une sauvegarde de Metal Gear Solid: Master Collection Vol. 1.",
}

# Seuls ces 3 motifs OctoCamo ont une vraie condition a remplir - les 18
# autres sont disponibles d'office pour tout le monde des le debut
# (confirme par l'utilisateur, 2026-09-06).
OCTOCAMO_CONDITIONAL = {"Cadavre", "Précommande", "Doré"}

# Onglet fusionne "OctoCamo" (demande utilisateur) : sections Camouflages
# faciaux + Gilet + Camouflages speciaux dans un seul onglet, comme pour
# les armes.
CAMO_GROUPS = [
    ("FaceCamo", FACECAMO_NAMES),
    ("Gilet", VEST_NAMES),
]

# "Tenues" : deguisements complets (pas de simples camouflages faciaux).
# Moyen-Orient/Amerique du Sud inverses par rapport a la table Cheat Engine
# d'origine (meme famille d'erreur que Altair/Suit) - confirme par test
# isole sur partie fraiche : le seul deguisement obtenu (Moyen-Orient) est
# a 0x1a, pas 0x19.
# Correction 2026-09-01 : "Amerique du Sud" deplace de 0x19 vers 0x1b,
# confirme par un test isole ou l'utilisateur obtient ce deguisement
# exactement au moment ou l'histoire entre au Village de Cove Valley
# (debut Acte 2) - correspond exactement a la description du site source.
# 0x19 etait deja obtenu bien avant (Acte 1), donc ce n'etait pas le bon
# ID. "Europe de l'Est" (qui occupait 0x1b) et l'identite reelle de 0x19
# retires en attendant de les retrouver.
# 2026-09-01 : "Costume de Snake" a 0x1c infirme - deblocage reel "apres
# avoir fini le jeu", impossible sur une partie fraiche encore en Acte 3.
# Test isole montre que 0x1c est en realite le Deguisement civil d'Europe
# de l'Est (changement de zone exact vers le centre-ville d'Europe de
# l'Est au meme moment). L'ancienne "confirmation" de Costume de Snake
# etait une coincidence : sur la save avancee utilisee a l'epoque, les
# deux etaient probablement deja vrais en meme temps. Costume de Snake et
# Costume d'Altair retires, positions reelles de nouveau inconnues.
OUTFIT_CONDITIONS = {
    "Déguisement de milicien du Moyen-Orient": (
        "Acte 1, dans le refuge de la milice, secteur nord-est du sous-sol "
        "(un casier de rangement). Utilisable uniquement pendant l'Acte 1."
    ),
    "Déguisement de rebelle d'Amérique du Sud": (
        "Acte 2, village de la vallée de la Cove, dans le bâtiment fermé "
        "près du mur de départ (faire du bruit pour attirer le soldat "
        "caché à l'intérieur et le maîtriser). Utilisable uniquement "
        "pendant l'Acte 2."
    ),
    "Déguisement civil de l'Europe de l'Est": (
        "Fourni automatiquement au tout début de l'Acte 3. Utilisable "
        "uniquement pendant l'Acte 3."
    ),
    "Costume de Snake": "Terminer le jeu une première fois.",
    "Costume d'Altaïr": "Obtenir l'emblème ASSASSIN.",
}

OUTFIT_NAMES = {
    0x1a: "Déguisement de milicien du Moyen-Orient",  # nom exact confirme par popup d'acquisition (2026-09-02)
    0x1b: "Déguisement de rebelle d'Amérique du Sud",  # confiance haute, reconfirme par test isole 2026-09-05
    0x1c: "Déguisement civil de l'Europe de l'Est",
    # Confiance haute (2026-09-10) : test isole propre, seule case du
    # tableau d'items a bouger (65535 -> 1) entre les deux saves
    # comparees, pile entre les 3 deguisements ci-dessus et le Costume
    # de Snake (0x1e) - ID reel enfin retrouve (voir notes.md, "Costume
    # d'Altair retires" pour l'historique de la case indicative).
    0x1d: "Costume d'Altaïr",
    # Nouvelle position trouvee suite a l'epilogue (jeu termine) - coherent
    # avec la condition reelle "apres avoir fini le jeu" qui avait invalide
    # l'ancienne position 0x1c (voir plus haut).
    0x1e: "Costume de Snake",
}


# Liste des chansons iPod. Noms originaux (pas de traduction, ce sont des
# titres de morceaux/albums de la serie MGS et d'autres jeux Kojima).
# Decalage de +1 corrige (2026-09-01) : la table Cheat Engine d'origine
# plaçait les chansons juste apres les 5 statuettes (0x3c), mais il y a en
# realite une case "Batterie" intercalee a 0x3c (confirmee par test isole -
# l'utilisateur obtient une batterie, pas une chanson, et c'est bien 0x3c
# qui se debloque). Ça decale TOUTES les chansons de +1 par rapport a
# l'ancienne table. Confirme independamment par 2 tests isoles distincts :
# "Theme of Tara" trouve a 0x54 (ancienne table : 0x53), "Level 3 Warning"
# trouve a 0x59 (ancienne table : 0x58) - les deux ecarts sont coherents
# avec un decalage uniforme de +1, pas des echanges isoles (le "correctif"
# precedent qui echangeait juste 2 noms adjacents etait insuffisant/faux,
# corrige ici en decalant toute la liste).
# Titres et orthographe alignes sur metalgeargeneration.free.fr/mgs4/ipod.php
# (2026-09-02), qui liste aussi les morceaux "disponibles des le debut"
# (Takin' on the Shagohod, Backyard Blues, Sea Breeze, Calling to the Night,
# Oishii Chuhan Seikatsu, Metal Gear 20 Years History Part.1, Who am I
# really?, Test Subject Burns, MGS4 Integral Podcast 01) : aucun ne
# correspond a une case de notre tableau (ils sont sans doute deja
# marques "possede" par defaut, donc jamais vus "flush" dans un diff -
# pas d'ID connu pour eux, non ajoutes ici.
#
# A l'origine 5 entrees ABSENTES de cette page de reference malgre une
# recherche complete (y compris la section "telecharges") : Metal Gear
# Solid Main Theme (0x3f, confirme en confiance haute le 2026-09-09 par
# popup en jeu au deblocage - voir commentaire dedie plus bas), Gekko
# (0x5f), Desperate Chase (0x60), Midnight Shadow (0x61), Mobs Alive
# (0x62). Probablement des erreurs heritees de la table Cheat Engine
# d'origine (comme d'autres cas similaires, voir notes.md) - a verifier
# par test isole si l'occasion se presente pour celles qui restent, pas
# retirees pour l'instant faute de mieux.
SONG_NAMES = {
    0x3d: "Warhead Storage",
    0x3e: "Yell \"Dead Cell\"",
    # Confiance haute (2026-09-09) : nom confirme par popup en jeu au
    # deblocage, a l'endroit attendu (Acte 5, Outer Haven, sous la trappe -
    # voir SONG_CONDITIONS). Absente de la source externe de reference,
    # mais confirmee directement, pas besoin de test isole supplementaire.
    0x3f: "Metal Gear Solid Main Theme",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'objets.
    0x40: "On Alert",
    0x41: "Bon Dance",
    0x42: "Sailor",
    0x43: "Show Time",
    0x44: "Open Title Old L.A. 2040",
    0x45: "\"Policenauts\" End Title",
    0x46: "MGS4 Love Theme (Action Version)",
    0x47: "Lunar Knights Main Theme",
    0x48: "Flowing Destiny",
    0x49: "Beyond the Bounds",
    0x4a: "Inori no Uta",
    0x4b: "Bio Hazard",
    # ID confirme en confiance haute (2026-09-23) : force a 1 en memoire
    # live (voir live_trainer.py) sur une save fraiche, la chanson apparait
    # bien dans l'iPod en jeu - le mapping 0x4c est correct. En revanche la
    # condition d'obtention ci-dessous (SONG_CONDITIONS) est infirmee, voir
    # ce dict plus bas et notes.md.
    0x4c: "One Night in Neo Kobe City",
    0x4d: "Theme of Solid Snake",
    0x4e: "Zanzibarland Breeze",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'objets (nom exact deja confirme par
    # popup le 2026-09-04).
    0x4f: "Metal Gear 20 Years History Part.2",
    0x50: "Metal Gear 20 Years History Part.3",
    0x51: "Big Boss",
    0x52: "The Essence of Vince",
    0x53: "Test Subjects Duality",
    0x54: "Theme of Tara",
    0x55: "Subsistence Action",
    0x56: "Shin Bokura no Taiyou Theme",
    0x57: "MPO+ Theme",
    0x58: "The Fury",
    0x59: "Level 3 Warning",
    0x5a: "The Best Is Yet To Come",
    0x5b: "Rock Me Baby",
    0x5c: "Destiny's Call",  # titre exact incertain, voir SONG_CONDITIONS
    0x5d: "Boktai 2 Theme",
    0x5e: "Snake Eater",
    0x5f: "Gekko",  # suspect, voir commentaire au-dessus
    0x60: "Desperate Chase",  # suspect, voir commentaire au-dessus
    0x61: "Midnight Shadow",  # suspect, voir commentaire au-dessus
    0x62: "Mobs Alive",  # suspect, voir commentaire au-dessus
}

# Emplacement/condition d'obtention + effet en CQC, source : page ci-dessus
# (paraphrase, pas une citation). Affiches au clic comme pour les
# statuettes/facecamos.
SONG_CONDITIONS = {
    "Warhead Storage": "Acte 4, près de l'héliport (conduit de ventilation après les escaliers).",
    'Yell "Dead Cell"': "Acte 4, juste après les tapis roulants, avant la sortie de la zone.",
    "On Alert": "Acte 3, dans l'impasse où s'engage le dernier soldat accompagné du rebelle déguisé en SMP.",
    "Bon Dance": "Acte 2, place du marché, dans les décombres d'un étal détruit par un Gekko. Effet : fait rire les soldats maîtrisés en CQC.",
    "Sailor": "Acte 2, entre un container et le mur est de l'enceinte du manoir. Effet : accélère la récupération de vie.",
    "Show Time": "Débloquée en aidant les miliciens (Actes 1/2, leur donner un objet de soin). Effet : effraie les soldats maîtrisés en CQC.",
    "Open Title Old L.A. 2040": "Bonus : dans le labo d'Otacon (Acte 4), entrer le mot de passe 78925. Effet : calme les tremblements de mains.",
    "\"Policenauts\" End Title": "Bonus : dans le labo d'Otacon (Acte 4), entrer le mot de passe 13462. Effet : endort les soldats maîtrisés en CQC.",
    "MGS4 Love Theme (Action Version)": "Débloquée en aidant les miliciens (Actes 1/2). Effet : fait pleurer les soldats maîtrisés en CQC.",
    "Lunar Knights Main Theme": "Disponible dans la cuisine du Nomad dès l'Acte 1.",
    "Midnight Shadow": "Acte 2, en prenant une photo de la radio qui diffuse les faux appels au secours de Naomi.",
    "Mobs Alive": "Acte 1, en NG+, en photographiant l'aile cybernétique dans le repaire des rebelles.",
    "Desperate Chase": "Acte 2, en suivant la piste de Naomi : prendre en photo le mouchoir/foulard bleu posé au sol sur son trajet.",
    "Gekko": "Acte 5, en photographiant la carte du monde 3D dans le passage menant vers l'arène de Screaming Mantis.",
    "Metal Gear Solid Main Theme": "Acte 5, Outer Haven, dès la première zone : sous une trappe sur la gauche.",
    "Flowing Destiny": "Acte 4, au canyon près du centre de stockage des ogives nucléaires. Effet : fait pleurer les soldats maîtrisés en CQC.",
    "Beyond the Bounds": "Acte 4, hangar à tanks, après que le Mk.III ait déverrouillé la porte vers le champ de neige.",
    "Inori no Uta": "Disponible dans la cuisine du Nomad dès l'Acte 1.",
    "Bio Hazard": "Acte 3, fouiller un membre de la résistance après l'avoir braqué. Effet : effraie les soldats maîtrisés en CQC.",
    # Condition INFIRMEE (2026-09-23) : l'utilisateur confirme avoir fouille
    # un SMP apres l'avoir braque sur sa save la plus avancee (action
    # repetee plusieurs fois), or la chanson reste non obtenue en jeu et en
    # memoire live (voir live_trainer.py) - ce n'est donc pas (ou pas
    # seulement) le bon declencheur. Condition ci-dessous gardee affichee
    # a titre indicatif (source externe non verifiee, comme a l'origine)
    # mais a corriger des qu'un vrai declencheur est trouve. Vraie
    # condition encore inconnue - a chercher en jouant.
    "One Night in Neo Kobe City": "Acte 3, fouiller un SMP après l'avoir braqué (condition non confirmée, probablement fausse - voir commentaire dans le code). Effet : fait rire les soldats maîtrisés en CQC.",
    "Theme of Solid Snake": "Acte 1, après la cinématique de l'attaque de la Beauty and the Beast Unit contre les miliciens.",
    "Zanzibarland Breeze": "Acte 1, zone secrète du bâtiment en ruines, juste avant de descendre vers la sortie.",
    "Metal Gear 20 Years History Part.2": "Acte 4, 2e sous-sol du centre de stockage des ogives nucléaires.",
    "Metal Gear 20 Years History Part.3": "Acte 2, centre de détention, sur un lit du dortoir.",
    "Big Boss": "Bonus : débloquer le rang Big Boss. Effets : effraie les soldats en CQC, accélère la régénération de vie, calme les tremblements de mains, augmente les dégâts d'endurance.",
    "The Essence of Vince": "Acte 3, combat contre Raging Raven, en haut de la tour, sur le balcon.",
    "Test Subjects Duality": "Acte 3, juste à droite de l'arrivée, avant l'apparition d'un membre de la résistance.",
    "Theme of Tara": "Acte 1, refuge de la milice, petite chambre après la salle des blessés.",
    # Condition corrigee (2026-09-10) suite a des retours recents (source
    # externe, pas un test isole personnel) : ce n'est pas un bonus MGO,
    # mais une photo prise en jeu.
    "Subsistence Action": "Acte 3, photographier le membre de la Résistance en train d'uriner dans le parc. Effets : fait rager les soldats en CQC, calme les tremblements de mains.",
    "Shin Bokura no Taiyou Theme": "Disponible dans la cuisine du Nomad dès l'Acte 1.",
    "MPO+ Theme": "Débloquée en aidant les miliciens (Actes 1/2). Effet : fait rire les soldats maîtrisés en CQC.",
    "The Fury": "Acte 2, maison incendiée du village de la vallée de la Cove. Effet : fait rager les soldats maîtrisés en CQC.",
    "Level 3 Warning": "Acte 1, deuxième étage du palais Advent.",
    "The Best Is Yet To Come": "Acte 4, juste avant l'entrée du haut fourneau, après avoir vaincu Crying Wolf.",
    "Rock Me Baby": "Acte 2, centre de détention, petite île au centre de l'étang. Effet : accélère la récupération de vie.",
    "Destiny's Call": "Débloquée en aidant les miliciens (Actes 1/2). Effet : fait rager les soldats maîtrisés en CQC. (Titre exact incertain sur la source.)",
    "Boktai 2 Theme": "Disponible dans la cuisine du Nomad dès l'Acte 1.",
    "Snake Eater": "Bonus : débloquer les 40 rangs. Effets : endort les soldats en CQC, accélère la régénération de vie, calme les tremblements de mains, augmente les dégâts d'endurance.",
}


BATTERY_ITEM_ID = 0x3c  # decouvert par test isole (voir notes.md), pas une chanson

# Source : recherche web (non verifie directement par nous) - une batterie
# recuperable a chaque briefing de mission (via le Mk.II, dans le Nomad),
# pour un total de 6 avec celle de base deja installee.
BATTERY_MAX = 6
BATTERY_CONDITION = (
    "Une batterie supplémentaire peut être récupérée à chaque briefing de "
    "mission (via le Mk.II ou Mk.III)."
)


def read_battery_count(path: str) -> int:
    """Nombre de batteries pour le Solid Eye. Toujours valeur+1 (la
    batterie de base toujours installee - un appareil a 0 batterie ne
    fonctionnerait pas - plus les batteries collectees en plus). 65535
    (verrou, mecanisme pas encore initialise) traite comme 0 collectee,
    donc affiche 1 (pas 0). Confirme par l'utilisateur sur plusieurs
    saves (verrou->1, 1->2, 4->5)."""
    states = read_item_states(path)
    raw = states.get(BATTERY_ITEM_ID, 65535)
    collected = 0 if raw == 65535 else raw
    return collected + 1


def read_item_states(path: str) -> dict[int, int]:
    """Lit la valeur brute de chaque case du tableau d'objets (0x0526,
    u16[99]) sans interpretation. Voir CAMO_GROUPS/FIGURE_NAMES/SONG_NAMES
    pour les IDs identifies."""
    with open(path, "rb") as f:
        data = decrypt(f.read())
    return {
        i: struct.unpack_from("<H", data, ITEM_STATE_OFFSET + 2 * i)[0]
        for i in range(ITEM_STATE_COUNT)
    }


def _item_owned(value: int) -> bool:
    return value == 1


def _read_item_collection(path: str, id_names: dict[int, str]) -> list[dict]:
    states = read_item_states(path)
    return [
        {"id": item_id, "name": name, "owned": _item_owned(states.get(item_id, 0))}
        for item_id, name in id_names.items()
    ]


# Objets a comportement booleen (possede / pas possede, comme iPod ou
# Seringue) malgre une valeur brute qui n'est pas 0/1 - PAS une vraie
# quantite de stock, donc le nombre ne doit pas etre affiche. Confirme pour
# la Boite en carton (0x09, encodee "25") - l'utilisateur precise qu'on ne
# peut en avoir qu'une seule.
BOOLEAN_GENERAL_ITEMS = {"Boîte en carton"}

# Bitmask "objet special utilise" (MGS4.SAV, source zexk/bbtracker, doc
# elle-meme marquee "sans echantillon live positif" - confirme de notre
# cote via le fichier MGS4.CT de l'utilisateur, entree "Special Items Used"
# avec dropdown "2:Stealth Camo" correspondant exactement au bit 1).
# Bit = 1 des que l'objet a ete equipe/utilise au moins une fois PENDANT
# cette partie - independant de la possession permanente (0x0f/0x10 dans
# GENERAL_ITEM_NAMES), qui elle est le sujet de cette conversation.
# CONFIANCE HAUTE (2026-09-10) : test isole propre par l'utilisateur -
# bit 1 (Camouflage optique) deja actif seul (0b10), puis bit 0
# (Bandana) qui s'active a son tour apres utilisation (0b11), sans
# aucun autre changement entre les deux saves comparees.
SPECIAL_ITEM_USE_OFFSET = 0x017a
SPECIAL_ITEM_USE_BITS = {"Bandana": 0, "Camouflage optique": 1}


def read_special_item_used(path: str, name: str) -> bool:
    with open(path, "rb") as f:
        data = decrypt(f.read())
    mask = struct.unpack_from("<H", data, SPECIAL_ITEM_USE_OFFSET)[0]
    bit = SPECIAL_ITEM_USE_BITS.get(name)
    return bit is not None and bool((mask >> bit) & 1)


def read_objects(path: str) -> list[dict]:
    """Objets generaux (0x00-0x13, IDs reels de la save, dont beaucoup pas
    encore identifies). Anciennement une 2e section "Objets speciaux" pour
    Bandana/Camouflage furtif a titre indicatif (IDs inconnus) - plus
    necessaire depuis leur identification (0x0f/0x10, voir
    GENERAL_ITEM_NAMES).

    La plupart sont des QUANTITES (0, 5, 25...), pas des booleens comme les
    camouflages/tenues : "connu" = valeur != 65535 (le verrou), 0 inclus
    (objet deja trouve mais stock actuellement vide, ex. rations
    consommees). La quantite reelle est affichee entre parentheses a cote
    du nom quand elle n'est pas triviale (0 ou 1) - sauf pour
    BOOLEAN_GENERAL_ITEMS, dont le nombre brut n'est pas une vraie
    quantite et n'est jamais affiche."""
    states = read_item_states(path)
    # Metal Gear Mk.II / Mk.III : le jeu ne suit qu'un seul flag brut
    # (item[0x07]) pour "as-tu un robot compagnon", sans distinguer la
    # version - confirme par l'utilisateur (2026-09-06), Mk.III remplace
    # Mk.II a partir de l'Acte 4 (jamais les deux a la fois, pas 2 objets
    # de collection independants - une seule tuile dont le nom change
    # selon l'acte, pas 2 tuiles separees).
    mk_owned = states.get(0x07, 65535) != 65535
    is_mk3_era = read_progress_info(path)["acte"] in {"Acte 4", "Acte 5", "Épilogue"}
    entries = []
    for item_id, name in GENERAL_ITEM_NAMES.items():
        if item_id in STRUCTURAL_ITEM_IDS:
            continue
        if item_id == BATTERY_ITEM_ID:
            continue  # affichee sur l'onglet Stats (read_battery_count), pas ici
        if item_id == 0x07:
            mk_name = "Metal Gear Mk. III" if is_mk3_era else "Metal Gear Mk. II"
            entries.append({"id": item_id, "name": mk_name, "owned": mk_owned})
            continue
        raw = states.get(item_id, 65535)
        owned = raw != 65535
        show_count = owned and raw not in (0, 1) and name not in BOOLEAN_GENERAL_ITEMS
        label = f"{name} ({raw})" if show_count else name
        entry = {"id": item_id, "name": label, "owned": owned}
        if name in SPECIAL_ITEM_USE_BITS:
            used = read_special_item_used(path, name)
            entry["condition"] = f"Utilisé pendant cette partie : {'Oui' if used else 'Non'}."
        entries.append(entry)
    return entries


def read_camo(path: str) -> list[dict]:
    """Comme _read_item_collection, mais chaque entree porte en plus une cle
    "group" (affichage en sections : Camouflages faciaux, Gilet, puis
    Octocamo) et "condition" (texte affiche au clic). La section
    "Octocamo" n'est PAS reliee a un etat reel de la save (voir
    OCTOCAMO_INFO) - toujours "owned": False, a titre indicatif
    seulement."""
    states = read_item_states(path)
    entries = [
        {
            "id": item_id,
            "name": name,
            "owned": _item_owned(states.get(item_id, 0)),
            "group": group_name,
            "condition": FACECAMO_CONDITIONS.get(name, ""),
        }
        for group_name, id_names in CAMO_GROUPS
        for item_id, name in id_names.items()
    ]
    # FaceCamo/Gilet dont l'ID reel n'a jamais ete retrouve (voir
    # notes.md) - tuiles indicatives uniquement, toujours affichees
    # verrouillees.
    entries.append({
        "id": None,
        "name": "Big Boss (position inconnue)",
        "owned": False,
        "group": "FaceCamo",
        "condition": FACECAMO_CONDITIONS.get("Big Boss (position inconnue)", ""),
    })
    entries.append({
        "id": None,
        "name": "Doré",
        "owned": False,
        "group": "FaceCamo",
        "condition": "Obtenu en ayant une sauvegarde de Metal Gear Solid: Master Collection Vol. 1.",
    })
    entries.append({
        "id": None,
        "name": "FaceCamo Doré",
        "owned": False,
        "group": "FaceCamo",
        "condition": "Obtenu en ayant une sauvegarde de Metal Gear Solid: Master Collection Vol. 1.",
    })
    entries.append({
        "id": None,
        "name": "Gilet - Doré",
        "owned": False,
        "group": "Gilet",
        "condition": "Obtenu en ayant une sauvegarde de Metal Gear Solid: Master Collection Vol. 1.",
    })
    entries.extend(
        {
            "id": None,
            # Seuls Cadavre/Precommande/Dore sont de vraies conditions a
            # remplir - les 18 autres motifs sont disponibles d'office pour
            # tout le monde des le debut (confirme par l'utilisateur,
            # 2026-09-06), donc affiches "obtenus" par defaut.
            "name": name,
            "owned": name not in OCTOCAMO_CONDITIONAL,
            "group": "Octocamo",
            "condition": condition,
        }
        for name, condition in OCTOCAMO_INFO.items()
    )
    return entries


def read_outfits(path: str) -> list[dict]:
    entries = _read_item_collection(path, OUTFIT_NAMES)
    for entry in entries:
        entry["condition"] = OUTFIT_CONDITIONS.get(entry["name"], "")
    return entries


def read_figurines(path: str) -> list[dict]:
    entries = _read_item_collection(path, FIGURE_NAMES)
    for entry in entries:
        entry["condition"] = FIGURE_CONDITIONS.get(entry["name"], "")
    return entries


def read_songs(path: str) -> list[dict]:
    entries = _read_item_collection(path, SONG_NAMES)
    for entry in entries:
        entry["condition"] = SONG_CONDITIONS.get(entry["name"], "")
    return entries


# Table d'armes tres partielle (5 IDs sur 95 confirmes), source table Cheat
# Engine communautaire (section marquee "WIP" par son propre auteur), IDs
# verifies par nous-memes par correlation temporelle (apparition simultanee
# avec d'autres armes/objets connus lors d'un meme "flush" de sauvegarde -
# voir notes.md). Les autres armes du tableau 0x1d4 restent affichees sous
# forme generique "Arme #NN" faute de table complete disponible.
#
# INFIRME (2026-09-02) : `0x19` a longtemps ete etiquete "MK.2 Pistol" (voir
# ancienne methode ci-dessous, gardee pour memoire) suite a une comparaison
# entre une save "avant remise d'equipement" (944D92, s01a00l, 0x19=0) et
# une save plus avancee (91DA17, s01a10l "Zone rouge", 0x19=2). On avait
# suppose que ce "avant/apres" correspondait a la cinematique de remise
# d'equipement d'Otacon (qui donne le Mk.2 Pistol). L'utilisateur confirme
# desormais que la vraie sequence d'ouverture est : arrivee au Moyen-Orient
# -> on avance un peu -> scene "prologue" au cimetiere -> retour au
# Moyen-Orient - et que `0x19` (confirme par capture d'ecran, arme nommee
# "AK-102" dans le menu en jeu) est obtenu PENDANT cette toute premiere
# progression, avant meme le Mk.2 Pistol qui "arrive apres". Donc le
# "avant/apres" qu'on mesurait correspondait en fait a l'obtention de
# l'AK-102, pas a la remise du Mk.2 Pistol. Reassigne. Vrai ID du Mk.2
# Pistol de nouveau inconnu.
#
# Ancienne methode (conservee pour tracer le raisonnement, desormais
# appliquee a l'AK-102 et non au Mk.2 Pistol) : premiere tentative (0x01,
# basee sur "vaut 2 des le premier echantillon disponible du slot 91DA17")
# INFIRMEE par l'utilisateur via 2 saves ("944D92"/"944EE9", Big Boss
# Difficile/The Boss Extreme) **explicitement sauvegardees avant la
# cinematique de remise d'equipement** - or `weapon[0x01]` y valait deja 2,
# ce qui en faisait un candidat structurel plutot qu'une vraie acquisition
# (correction ulterieure, 2026-09-02 : 0x01 est en fait le Couteau
# paralysant, une arme de depart bien reelle - voir WEAPON_NAMES). Nouvelle
# comparaison a l'epoque : 944D92 (s01a00l, avant progression) vs 91DA17
# premier echantillon avance (141536, s01a10l "Zone rouge") - **une seule
# difference** sur les 95 entrees du tableau d'armes : `0x19` passe de 0 a
# 2. Verifie sur toutes les saves disponibles a l'epoque : 0 sur les saves
# "avant remise" (944D92, 944EE9), 2 partout ailleurs - signature nette et
# sans exception, mais mal interpretee (voir plus haut).
#
# Correction Stun Grenades (2026-08-31) : methode "partie toute fraiche"
# (utilisateur a demarre une partie a zero, pas en NG+, justement pour
# eviter le probleme du carry-over/flush retarde). Save juste avant
# d'obtenir les grenades paralysantes vs save juste apres (meme partie,
# aucune autre arme touchee entre les deux) : **une seule case change**,
# `0x36` (0 -> 1). L'ancien ID `0x2A` (trouve via l'evenement de "gros
# flush" bruyant sur 91DA17, avec des dizaines de changements simultanes -
# correlation bien plus fragile) reste a 0 dans ce test isole, donc etait
# probablement une coincidence de timing, pas la bonne case. `0x2A` finit
# tout de meme par valoir 1 sur les parties avancees/terminees - role reel
# inconnu (peut-etre un flag "utilisee au moins une fois" plutot que
# "possedee", a l'image du sens encore flou de 1 vs 2 pour ce tableau).
#
# Correction MK.17 (2026-08-31), meme methode et meme constat : save juste
# avant/apres obtention du MK.17 sur la partie fraiche, une seule case
# change, `0x1e` (0 -> 1). L'ancien ID `0x11`... pardon, `0x14` (lui aussi
# issu du "gros flush" bruyant) reste a 0 dans ce test isole - donc faux
# lui aussi, meme mecanisme que Stun Grenades. A ce stade, les 3 ID trouves
# via le gros flush bruyant (MK.17, Stun Grenades, et par extension AK102
# `0x11` - pas encore reverifie par un test isole) sont suspects par
# principe ; seuls les ID retrouves par un test isole propre (`0x19`,
# Stun Grenades `0x36`, MK.17 `0x1e`) sont de confiance haute (voir plus
# haut pour la correction 2026-09-02 de l'identite de `0x19`).
WEAPON_NAMES = {
    # Confirme par test isole 2026-09-05 (diff avant/apres obtention, seul
    # ID du tableau armes a bouger, 0->2).
    0x27: "VSS",
    0x15: "PP-19 Bizon",  # confirme par test isole 2026-09-05, meme methode
    0x21: "HK21E",  # confirme par test isole 2026-09-05, meme methode
    0x12: "MP5SD2",  # confirme par test isole 2026-09-05, meme methode
    0x26: "Saiga-12",  # confirme par test isole 2026-09-05, meme methode
    0x28: "M82A2",  # confirme par test isole 2026-09-05, meme methode
    0x1c: "FAL",  # confirme par test isole 2026-09-05, meme methode
    0x20: "Mk.46 MOD1",  # confirme par test isole 2026-09-05, meme methode
    0x51: "Silencieux P90",  # confirme par test isole 2026-09-05, meme methode
    0x50: "Silencieux M10",  # confirme par test isole 2026-09-05, meme methode
    # Confirme par test isole 2026-09-05. Les grenades fumigenes semblent
    # avoir un ID d'arme distinct par couleur (l'entree generique existante
    # "0x38: Grenades fumigenes" ne precise pas laquelle) - identite exacte
    # de 0x38 et des variantes Rouge/Jaune encore inconnue, voir notes.md.
    0x3c: "Grenade fumigène (Bleue)",
    0x3a: "Grenade fumigène (Verte)",  # confirme par test isole 2026-09-05, meme methode
    # 2026-09-02 : confirme sur une toute nouvelle partie (Acte 1, tout
    # debut) - seule arme possedee, en meme temps que Ration+iPod. Arme de
    # depart classique de la serie, presente des la premiere save du jeu.
    0x01: "Couteau paralysant",  # nom exact confirme par capture d'ecran (2026-09-02)
    # AK-102 : confirme par capture d'ecran (2026-09-02), obtenu tres tot en
    # Acte 1 (juste apres l'arrivee au Moyen-Orient, avant le Mk.2 Pistol).
    # Anciennement etiquete a tort "MK.2 Pistol" - voir le long commentaire
    # au-dessus pour l'historique complet de cette correction.
    0x19: "AK-102",
    # 0x11 INFIRME comme AK102 (2026-09-01) : l'utilisateur confirme avoir
    # obtenu l'AK102 comme toute premiere arme du jeu, avant meme le don
    # d'Otacon - or weapon[0x11] restait a 0 meme APRES ce don sur notre
    # partie fraiche (verifie sur toute la serie temporelle). L'AK102 est
    # finalement retrouve ailleurs (0x19, voir plus haut) - RESOLU
    # (2026-09-02).
    # "Masterkey" (0x11) EGALEMENT INFIRME (2026-09-02) : cette identite
    # venait du meme "gros flush bruyant" que MP7/DSR-1 (methode fragile,
    # deja signalee comme suspecte). L'utilisateur confirme ne pas avoir le
    # Masterkey ni sur l'ancienne save ni sur celle-ci, alors que
    # weapon[0x11] y vaut 1 - preuve directe que l'identification est
    # fausse. Retire.
    # INVERSE (2026-09-05) : l'ancienne resolution du 2026-09-02 (0x30=MP7,
    # 0x11=Lunette de fusil par elimination, via recoupement munitions -
    # methode desormais suspecte, cf. tableau 0x352 non stable d'une partie
    # a l'autre) etait fausse. Test isole propre sur une partie differente :
    # weapon[0x30] passe de 0 a 1 pendant que weapon[0x11] reste a 0,
    # l'utilisateur confirme avoir la Lunette de fusil et PAS le MP7 - a
    # l'epoque attribue a 0x30. RE-INVERSE (2026-09-07) : test isole
    # encore plus propre (achat du Sachet a gaz somnifere sur une partie
    # fraiche ou aucun des deux n'etait possede) montre que c'est en fait
    # weapon[0x54] qui passe de 0 a 2, weapon[0x30] restant a 0 - donc
    # 0x54 est la vraie Lunette de fusil. Hypothese : le test de 2026-09-05
    # avait probablement debloque les deux objets simultanement sans que
    # le changement sur 0x54 soit remarque a l'epoque. Confiance haute.
    0x54: "Lunette de fusil",
    # Confiance haute (2026-09-05) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x11: "MP7",
    # INFIRME (2026-09-06) : l'ancienne resolution du 2026-09-02 (recoupement
    # munitions, methode desormais suspecte) etait fausse. Test isole propre
    # sur une partie differente : c'est weapon[0x4a] (etiquete "DSR-1"
    # jusque-la) qui bouge au moment ou l'utilisateur obtient reellement le
    # Masterkey, pas weapon[0x29] qui reste verrouille. Reassigne, voir
    # 0x4a plus bas. Vrai ID de 0x29 de nouveau inconnu.
    # CONFIANCE HAUTE (2026-09-24, corrige la "confiance basse" ci-dessous) :
    # confirme via le trainer live (weapon_state_rva) en basculant l'etat
    # de 0x29 et en observant en jeu que c'est bien le DSR-1 qui se
    # verrouille/deverrouille.
    #
    # Historique - CONFIANCE BASSE (2026-09-06) : D.E. et DSR-1 obtenus
    # ensemble a l'epoque (0x08 et 0x29 flushaient en meme temps),
    # impossible de les isoler individuellement a ce moment-la.
    # Attribution par convention a la demande de l'utilisateur.
    0x29: "DSR-1",
    # CONFIANCE HAUTE desormais (2026-09-09) pour le D.E. : test isole
    # propre, seul 0x08 bouge (0x29/DSR-1 reste inchange) parmi les
    # transitions non deja expliquees par ailleurs sur cette fenetre.
    0x08: "D.E.",
    # Desert Eagle (Canon Long) (0x09) : decouvert via le trainer live
    # (2026-09-24) - variante canon long du D.E. (0x08), partage le meme
    # pool de munitions (calibre identique, seule la longueur du canon
    # change), confirme par correspondance directe.
    0x09: "Desert Eagle (Canon Long)",
    # Type 17 (0x10) : decouvert via le trainer live (2026-09-24) -
    # partage le pool .45 ACP (Operator/1911/Mk.23/M-10/GSR), confirme
    # par correspondance directe (878).
    0x10: "Type 17",
    # Patriot (0x16) : decouvert via le trainer live (2026-09-24) -
    # confirme par l'utilisateur (arme bonus emblematique de Big Boss,
    # munitions illimitees, pas de pool de munitions a suivre).
    0x16: "Patriot",
    # "Destabil.SOP" (0x44) : decouvert via le trainer live (2026-09-24) -
    # objet inedit, jamais documente ailleurs a la connaissance de
    # l'utilisateur. Categorie en jeu "POSER" (objet a poser, pas une
    # arme), poids 3.0kg. Nom exact tronque a l'ecran ("DESTABIL.SOP") -
    # confiance basse sur l'orthographe/le nom complet, a confirmer.
    0x44: "Déstabil. SOP",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x1b: "AN94",
    # CONFIANCE HAUTE (2026-09-24, corrige le "confiance basse" ci-dessous) :
    # confirme via le trainer live (voir live_trainer.py, weapon_state_rva)
    # en basculant l'etat de 0x1d et en observant en jeu que c'est bien le
    # Tanegashima qui se verrouille/deverrouille.
    #
    # Historique - CONFIANCE BASSE (2026-09-09) : pari de l'utilisateur,
    # PAS un test isole a l'epoque. 0x1d est un bonus lie a la 2e fin de
    # partie ou plus (identite inconnue jusqu'ici, confirme comme n'etant
    # PAS le Race Gun), et se trouve pile au milieu d'un bloc continu de
    # fusils d'assaut (M4 0x18 a XM8 0x1f, sans autre trou) - coherent
    # avec le Tanegashima, arme bonus de completion connue du jeu.
    0x1d: "Tanegashima",
    0x1e: "MK.17",
    # Confiance haute : test isole propre en 2 etapes (2026-09-05) - save
    # avec uniquement "Grenade au phosphore blanc" possedee dans le groupe
    # Grenades, puis nouvelle save juste apres avec en plus "Grenade
    # paralysante" - aucun autre ID du groupe n'a bouge entre les 2.
    0x36: "Grenade paralysante",
    # Trouve par test isole (partie fraiche, une seule case changee entre
    # 2 saves consecutives) : "White Phosphorus Grenades".
    0x35: "Grenade au phosphore blanc",
    # Idem. Classe dans le tableau "armes" (roue d'armes) et non "objets",
    # contrairement a l'intuition - la separation armes/objets du jeu ne
    # correspond pas forcement a celle qu'on imaginerait.
    0x45: "Magazine Playboy",
    # Confirme (2026-09-04) : seule arme non identifiee possedee au moment
    # de l'obtention du "Mag Emo" (popup en jeu). Distinct du Playboy -
    # correspond au champ stats "emotion_magazine_pages" deja suivi
    # separement de "playboy_pages".
    0x46: "Magazine Émotion",
    # CONFIANCE HAUTE pour 0x0a/0x0b (2026-09-24, corrige la convention
    # "confiance basse" ci-dessous) : le trainer live a revele que le
    # tableau d'etat des armes en memoire suit une formule lineaire
    # stricte RVA(id) = base + id*0x50 (voir live_trainer.py,
    # CONFIRMED_WEAPON_RVAS), verifiee sur 9 armes deja confirmees
    # independamment. Cette formule predisait que 0x0a et 0x0b etaient
    # INVERSES par rapport a l'attribution par convention ci-dessous.
    # Double confirmation en jeu par l'utilisateur : desactiver l'adresse
    # predite pour 0x0a verrouille bien le Thor .45-70, et celle predite
    # pour 0x0b verrouille bien le 1911 Modifie. Voir notes.md.
    #
    # CONFIANCE HAUTE pour 0x02 et 0x03 (2026-09-24) : confirmes via le
    # trainer live (weapon_state_rva) en basculant l'etat de chacun et en
    # observant en jeu que c'est bien le Mk.2 Pistol (0x02) puis
    # l'Operator (0x03) qui se verrouille/deverrouille.
    #
    # Lot Otacon desormais entierement resolu (2026-09-24) : le
    # Silencieux Operator (0x4d, voir plus bas dans ce dictionnaire) est
    # le dernier morceau confirme, en forcant l'etat a 0 (comme pour le
    # Masterkey - ces accessoires n'ont pas de palier "verrouille chez
    # Drebin" intermediaire, 1 et 2 se comportent pareil, seul 0 a un
    # effet visible) : le silencieux devient bien indisponible en jeu.
    0x02: "Mk.2 Pistol",
    0x03: "Operator",
    0x0a: "Thor .45-70",
    0x0b: "1911 Modifié",
    # RPG-7 de base : toujours obtenu sur toutes les parties (y compris
    # terminees) - confiance haute.
    0x32: "RPG-7",
    # CONFIANCE HAUTE (2026-09-24) : confirme via le trainer live en
    # forcant l'etat a 0 (voir commentaire plus haut sur le lot Otacon) -
    # le silencieux devient bien indisponible en jeu. Dernier morceau du
    # lot Otacon (0x02/0x03/0x0a/0x0b/0x4d) a etre isole individuellement.
    0x4d: "Silencieux Operator",
    # Confirmes par tests isoles (partie fraiche).
    # Confiance haute (2026-09-05) : test isole propre, save avec
    # Phosphore blanc + Paralysante possedees dans le groupe Grenades,
    # puis nouvelle save juste apres avec en plus "Grenade fumigene" -
    # seul cet ID a bouge entre les 2. Identite de couleur toujours non
    # precisee (voir notes.md), mais l'ID lui-meme est desormais solide.
    0x38: "Grenade fumigène",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x39: "Grenade fumigène (Rouge)",
    # Confiance haute (2026-09-05) : test isole propre (seuls 0x07 et 0x18
    # ont bouge dans tout le tableau d'armes a l'obtention de GSR+M4) +
    # recoupement munitions - l'utilisateur rapporte 70 munitions sur son
    # GSR en jeu, qui correspond exactement a l'emplacement 11 du tableau
    # 0x352 (pool .45 ACP partage avec Operator/1911 Modifie, cf. plus
    # haut), confirmant que 0x07 correspond bien a une arme .45 ACP.
    0x07: "GSR",
    # Confiance haute (2026-09-05) : meme sequence de test isole que pour
    # Grenade fumigene (0x38) ci-dessus - seul cet ID a bouge a l'etape
    # suivante, aucun autre du groupe Grenades.
    0x34: "Grenade",
    # Confiance haute (2026-09-05) : meme test isole que GSR ci-dessus,
    # seuls 0x07 et 0x18 ont bouge dans le tableau d'armes.
    0x18: "M4",
    # Confirmes par tests isoles (partie fraiche).
    0x3d: "Cocktail Molotov",
    # Confiance haute (2026-09-05) : test isole propre (seuls 0x2a, 0x45 et
    # 0x59 ont bouge dans le tableau d'armes a l'obtention simultanee de
    # M14EBR/Magazine Playboy/Lumiere pour pistolet).
    0x2a: "M14EBR",
    # Confiance haute (2026-09-05) : test isole propre, seuls 0x05 (PMM) et
    # 0x40 ont bouge dans tout le tableau d'armes a l'obtention simultanee
    # des deux.
    0x40: "Claymore",
    0x05: "PMM",
    0x13: "M-10",  # confirme par test isole 2026-09-05, meme methode
    0x53: "Silencieux M14EBR",  # confirme par test isole 2026-09-05, meme methode
    # Confiance haute (2026-09-05) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x41: "Mine à gaz somnifère",
    # Confiance haute (2026-09-05) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x24: "Double canon",
    0x42: "C4",
    # CONFIANCE HAUTE (2026-09-24, corrige la "confiance basse" ci-dessous) :
    # confirme via le trainer live (weapon_state_rva) en basculant l'etat
    # de 0x43 et en observant en jeu que c'est bien le Sachet a gaz
    # somnifere qui se verrouille/deverrouille.
    #
    # Historique - CONFIANCE BASSE (2026-09-09) : attribution par
    # convention/deduction, PAS un test isole a l'epoque. 0x43 est
    # immediatement adjacent au bloc continu d'explosifs/grenades/
    # lance-roquettes 0x2e-0x42 (Claymore, Mine a gaz somnifere, C4, puis
    # ce slot juste apres) - identite plausible mais pas encore confirmee
    # a l'epoque (voir 0x30 plus haut pour l'historique complet du
    # FIM-92A).
    0x43: "Sachet à gaz somnifère",
    0x1a: "G3A3",
    # Confiance haute (2026-09-09) : test isole propre, seul cet ID a
    # bouge parmi les transitions non deja expliquees par ailleurs sur
    # cette fenetre (jamais teste isolement auparavant).
    0x23: "M60E4",
    # Confiance haute (2026-09-05) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x4b: "XM320",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x33: "M72A3",
    # Confiance haute (2026-09-05) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x5b: "Poignée avant B.",
    # Confiance haute (2026-09-05) : test isole propre, seuls 0x25 (M870
    # Modifie) et 0x52 ont bouge dans tout le tableau d'armes.
    0x52: "Silencieux M4",
    0x25: "M870 Modifié",
    0x57: "Lumière Fusil (M4)",  # nom exact confirme par capture d'ecran (2026-09-02)
    0x4f: "Silencieux 1911",
    # CONFIANCE HAUTE (2026-09-24, corrige la "confiance basse" ci-dessous) :
    # confirme via le trainer live - tous les accessoires forces a 0 puis
    # rachetes un par un chez Drebin par l'utilisateur (voir notes.md),
    # seul 0x4e est repasse a 2 au moment de racheter le Silencieux Mk.23.
    #
    # Historique - CONFIANCE BASSE (2026-09-09) : pari de l'utilisateur,
    # PAS un test isole a l'epoque. 0x4e est un bonus lie a la 1ere fin de
    # partie (identite inconnue jusque-la, ni Race Gun ni 1911 Modifie),
    # pile entre le Silencieux Operator (0x4d) et le Silencieux 1911
    # (0x4f) dans le bloc continu d'accessoires 0x4a-0x5b.
    0x4e: "Silencieux Mk.23",
    # Confiance haute (2026-09-05) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x5a: "Poignée avant A.",
    # "MP7" (0x29) INFIRME (2026-09-02) : reste a 0 avant ET apres que
    # l'utilisateur obtienne reellement le MP7 (popup en jeu) sur sa partie
    # fraiche - preuve directe que ce n'est pas la bonne case. Retire. Vrai
    # ID du MP7 inconnu - meme situation que Masterkey ci-dessus (candidat
    # possible 0x11 ou 0x30, a confirmer).
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes (nom exact deja confirme par
    # capture d'ecran le 2026-09-02).
    0x17: "Vz. 83",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes (P90 a change de valeur au meme
    # moment, 1->2, mais deja possede - probablement juste equipe).
    0x2e: "MGL-140",
    # Confirme par test isole (partie fraiche) - lance-grenades sous-canon
    # pour l'AK-102.
    0x4c: "GP-30",
    # "Grenade a particules metalliques" INFIRME a 0x04 (2026-09-02) : reste
    # a 0 alors que l'utilisateur vient de l'obtenir (popup en jeu) - c'est
    # en realite weapon[0x37] (etiquete "Mk.23" jusqu'ici) qui bouge a ce
    # moment precis. Reassigne. Vrai ID du Mk.23 de nouveau inconnu.
    0x37: "Grenade à particules métalliques",
    # Confirme (2026-09-04) : seule arme non identifiee possedee au moment
    # de l'obtention du Mk.23 (popup en jeu) sur la nouvelle partie de
    # reference. Vrai ID retrouve apres l'ancienne confusion avec 0x37.
    0x04: "Mk.23",
    0x56: "Visée point rouge (MP7)",
    # Confirme par test isole (partie fraiche) - distinct de la variante MP7.
    0x55: "Visée point rouge (M4)",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a bouge
    # dans tout le tableau d'armes. Vrai ID enfin retrouve apres les deux
    # INFIRME precedents (voir plus haut, ex-PSS puis ex-Lunette de fusil).
    0x58: "Visée laser (M4)",
    # Confiance haute (2026-09-06) : seul ID inconnu ayant bouge dans la
    # fenetre de temps juste avant que l'utilisateur signale l'obtention
    # de la grenade fumigene jaune (capture entre deux backups rapproches,
    # pas un diff strictement isole cette fois, mais aucun autre candidat).
    0x3b: "Grenade fumigène (Jaune)",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x2c: "SVD",
    # INVERSE (2026-09-06) : "XM25"/"Rail Gun" etaient bien attribues, mais
    # aux mauvais ID. Test isole propre (obtention automatique du Rail Gun
    # apres avoir vaincu Crying Wolf, confirme par l'utilisateur) : c'est
    # weapon[0x2d] qui bouge, pas 0x2f. Vrai ID du XM25 de nouveau inconnu.
    # Confiance haute.
    0x2d: "Rail Gun",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x2f: "XM25",
    # Confiance haute (2026-09-06) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x2b: "Mosin-Nagant",
    # Confiance haute (2026-09-05) : meme test isole que M14EBR ci-dessus.
    # Reconfirme independamment le 2026-09-24 : parti de tous les
    # accessoires forces a 0 (voir notes.md), l'utilisateur a rachete la
    # Lumiere pour pistolet chez Drebin - seul 0x59 est repasse a 2.
    0x59: "Lumière pour pistolet",
    # Confiance haute (2026-09-06) : test isole propre sur une partie
    # differente, seul cet ID a bouge dans tout le tableau d'armes au
    # moment ou l'utilisateur obtient le Masterkey. Corrige l'ancienne
    # etiquette "DSR-1" (jamais confirmee individuellement), vrai ID du
    # DSR-1 de nouveau inconnu.
    # Reconfirme independamment le 2026-09-24 via weapon_state_rva : forcer
    # l'etat a 0 (Non possedee) rend bien le Masterkey indisponible/non
    # equipable en jeu (1 et 2 se comportent pareil - pas de palier
    # "verrouille chez Drebin" pour cette arme trouvee via declencheur
    # scenaristique, contrairement aux armes achetees).
    0x4a: "Masterkey",
    # Lot de 4 armes obtenues ensemble, departagees via le tableau de
    # munitions 0x352 (methode desormais suspecte, voir plus bas) : les 4
    # nouvelles cases de ce tableau (dans l'ordre d'apparition)
    # correspondent aux 4 nouvelles cases du tableau d'armes (aussi dans
    # l'ordre d'apparition). "Confirme" a l'epoque par un test de tir
    # controle (FIM-92A: 3 munitions, 2 tirees, 1 restante) et par les
    # valeurs exactes donnees par l'utilisateur (PSS: 2 balles, Sachet: 3).
    # PSS INFIRME (2026-09-02) : test isole sur partie fraiche montre
    # weapon[0x30] restant a 0 au moment ou l'utilisateur obtient reellement
    # le PSS (popup en jeu) - donc au moins un ID de ce lot de 4 est faux.
    # Vrai ID du PSS inconnu a l'epoque, retrouve depuis (voir plus bas).
    # "Lunette de fusil" (0x0e) egalement INFIRME dans la foulee (2026-09-02) -
    # reassigne a l'epoque a "Visee Laser (M4)" par elimination, PUIS
    # RE-INFIRME (2026-09-05) : test isole propre sur une partie differente
    # montre 0x0e passant de 0 a 2 au moment ou l'utilisateur obtient
    # reellement le PSS (popup en jeu) - pas de Visee Laser (M4) cette
    # fois-ci, et weapon[0x58] (l'ancien "PSS") restait a 0. Donc 0x0e est
    # le vrai PSS. Vrai ID de "Visee Laser (M4)" et de la Lunette de fusil
    # de nouveau inconnus tous les deux. Confiance haute.
    0x0e: "PSS",
    # INVERSE (2026-09-09) : anciennement etiquete "Sachet a gaz
    # somnifere" par erreur (deja attribue par elimination/convention le
    # 2026-09-07 lors du swap avec la Lunette de fusil - confiance basse
    # des le depart, jamais confirme independamment). Confiance haute
    # desormais : l'utilisateur deverrouille volontairement le FIM-92A en jeu
    # (etat verrouille -> utilisable) ; sur cette fenetre, 3 armes
    # passent de 1 a 2 dans le fichier (0x07 GSR, 0x0f G18C, 0x30), mais
    # GSR et G18C ont deja ete deverrouilles et confirmes independamment
    # par l'utilisateur sur d'autres saves - seul 0x30 est une transition
    # nouvelle et inexpliquee sur cette save, coincidant exactement avec
    # le deverrouillage du FIM-92A. Vraie identite du Sachet a gaz
    # somnifere de nouveau inconnue (l'ancien 0x43, jamais confirme
    # individuellement, etait deja marque comme herite tel quel de la
    # table Cheat Engine d'origine).
    0x30: "FIM-92A",
    # XM8/Javelin : meme methode (ordre d'apparition dans les 2 tableaux),
    # confirme par les munitions exactes (777 et 13).
    # Confiance haute (2026-09-05) : test isole propre sur une partie
    # differente, seul cet ID a bouge dans tout le tableau d'armes -
    # reconfirme independamment de l'ancien recoupement munitions (methode
    # desormais suspecte).
    0x1f: "XM8",
    # Confiance haute (2026-09-05) : test isole propre sur une partie
    # differente, seul cet ID a bouge dans tout le tableau d'armes -
    # reconfirme independamment de l'ancien recoupement munitions.
    0x31: "FGM-148 Javelin",
    0x22: "PKM",
    # Confirme par test isole (partie fraiche). 2 armes obtenues ensemble,
    # departagees par la table de munitions (0x350) : la grosse reserve
    # (596 munitions) correspond au P90, coherent avec un pistolet-
    # mitrailleur ; l'autre (4 munitions) est confirmee par l'utilisateur
    # comme le Chargeur (objet a lancer pour distraire les ennemis, pas
    # une vraie arme - voir categorie "Autre").
    0x14: "P90",
    0x3e: "Chargeur",
    # Confirme par test isole (partie fraiche).
    0x0f: "G18C",
    # Confiance haute (2026-09-05) : test isole propre, seul cet ID a
    # bouge dans tout le tableau d'armes.
    0x06: "Five-Seven",
    # Confirme par test isole (partie fraiche). Particularite : passe
    # directement a 2 (et non 1 comme les autres armes) au moment du flush -
    # raison non identifiee, valeur brute conservee telle quelle.
    0x47: "Poupée Mantis",
    0x48: "Poupée Sorrow",
    # Bonus post-jeu (epilogue), 2 nouvelles armes flushees ensemble -
    # attribution par ordre d'apparition (moins fiable, lot noisy).
    0x0c: "Arme de chasse",
    0x0d: "Pistolet solaire",
}

# Categories d'armes pour affichage groupe (voir gui_app.CollectionPanel).
# Uniquement les armes identifiees ci-dessus ; tout ID absent de ce dict
# tombe dans le groupe "Non identifiees" par defaut.
WEAPON_CATEGORIES = {
    0x01: "Autre",  # Couteau - seule arme corps a corps, pas de categorie dediee
    0x19: "Fusil d'assaut",  # AK-102 - etait classe a tort en Pistolets
    0x02: "Arme de poing",
    0x03: "Arme de poing",
    0x07: "Arme de poing",  # GSR = SIG Sauer GSR, pistolet .45 ACP - PAS un fusil de precision
    0x1e: "Fusil d'assaut",
    0x18: "Fusil d'assaut",
    0x2a: "Fusil Sniper",  # M14EBR : fusil semi-automatique de precision
    0x28: "Fusil Sniper",  # M82A2
    0x24: "Fusil à pompe",  # Double canon
    0x26: "Fusil à pompe",  # Saiga-12
    0x25: "Fusil à pompe",  # M870 Modifie
    0x1a: "Fusil d'assaut",  # G3A3
    0x1c: "Fusil d'assaut",  # FAL
    0x1d: "Fusil d'assaut",  # Tanegashima
    0x1b: "Fusil d'assaut",  # AN94
    0x32: "Lance-roquette",
    0x36: "Grenade",
    0x35: "Grenade",
    0x38: "Grenade",
    0x39: "Grenade",  # Grenade fumigene (Rouge)
    0x3c: "Grenade",  # Grenade fumigene (Bleue)
    0x3a: "Grenade",  # Grenade fumigene (Verte)
    0x3b: "Grenade",  # Grenade fumigene (Jaune)
    0x34: "Grenade",
    0x3d: "Grenade",  # Cocktail Molotov, arme de lancer similaire
    0x40: "Explosif",  # Claymore
    0x41: "Explosif",  # Mine a gaz somnifere
    0x42: "Explosif",  # C4
    0x43: "Explosif",  # Sachet a gaz somnifere
    0x54: "Accessoire",  # Lunette de fusil
    0x45: "Magazine",  # Magazine Playboy
    0x46: "Magazine",  # Magazine Emotion
    0x5b: "Accessoire",  # Poignee avant B. (accessoire M4)
    0x0e: "Arme de poing",  # PSS
    0x52: "Accessoire",  # Silencieux M4
    0x53: "Accessoire",  # Silencieux M14EBR
    0x51: "Accessoire",  # Silencieux P90
    0x50: "Accessoire",  # Silencieux M10
    0x57: "Accessoire",  # Lumiere pour arme d'epaule
    0x4f: "Accessoire",  # Silencieux 1911
    0x4e: "Accessoire",  # Silencieux Mk.23 (confiance basse)
    0x0a: "Arme de poing",  # Thor .45-70 - reclasse avec les pistolets (liste utilisateur, 2026-09-06)
    0x0b: "Arme de poing",  # 1911 Modifie
    0x5a: "Accessoire",  # Poignee avant A.
    0x17: "Pistolet-mitrailleur",  # Vz-83
    0x15: "Pistolet-mitrailleur",  # PP-19 Bizon
    0x12: "Pistolet-mitrailleur",  # MP5SD2
    0x13: "Pistolet-mitrailleur",  # M-10
    0x30: "Lance-roquette",  # FIM-92A
    0x11: "Pistolet-mitrailleur",  # MP7
    0x2e: "Lance-grenade",  # MGL-140
    0x4c: "Accessoire",  # GP-30 (lance-grenades sous-canon pour AK-102)
    0x37: "Grenade",  # Grenade a particules metalliques
    0x04: "Arme de poing",  # Mk.23
    0x05: "Arme de poing",  # PMM (Makarov PMM)
    0x08: "Arme de poing",  # D.E.
    0x09: "Arme de poing",  # Desert Eagle (Canon Long)
    0x10: "Arme de poing",  # Type 17
    0x16: "Pistolet-mitrailleur",  # Patriot
    0x29: "Fusil Sniper",  # DSR-1
    0x56: "Accessoire",  # Visee point rouge (MP7)
    0x55: "Accessoire",  # Visee point rouge (M4)
    0x58: "Accessoire",  # Visee laser (M4)
    0x2c: "Fusil Sniper",  # SVD
    0x27: "Fusil Sniper",  # VSS
    0x2d: "Fusil Sniper",  # Rail Gun
    0x2f: "Lance-grenade",  # XM25
    0x2b: "Fusil Sniper",  # Mosin-Nagant
    0x59: "Accessoire",  # Lumiere pour pistolet
    0x4a: "Accessoire",  # Masterkey
    0x1f: "Fusil d'assaut",  # XM8
    0x31: "Lance-roquette",  # FGM-148 Javelin
    0x22: "Mitrailleuse",  # PKM
    0x21: "Mitrailleuse",  # HK21E
    0x20: "Mitrailleuse",  # Mk.46 MOD1
    0x14: "Pistolet-mitrailleur",  # P90
    0x3e: "Autre",  # Chargeur (objet de diversion, pas une arme)
    0x44: "Autre",  # Destabil.SOP (objet "POSER", pas une arme)
    0x23: "Mitrailleuse",  # M60E4
    0x4b: "Accessoire",  # XM320 (lance-grenades sous-canon, accessoire pas arme autonome)
    0x33: "Lance-roquette",  # M72A3 (LAW)
    0x4d: "Accessoire",  # Silencieux Operator
    0x0f: "Arme de poing",  # G18C
    0x06: "Arme de poing",  # Five-Seven
    0x47: "Autre",  # Poupee Mantis (objet cle, pas une vraie arme)
    0x48: "Autre",  # Poupee Sorrow (idem)
    0x0c: "Arme de poing",  # Arme de chasse (bonus post-jeu) - reclassee (2026-09-09), liste utilisateur
    0x0d: "Arme de poing",  # Pistolet solaire - reclasse avec les pistolets (liste utilisateur, 2026-09-06)
}

# Ordre d'affichage des sections dans l'onglet Armes.
WEAPON_GROUP_ORDER = [
    "Arme de poing",
    "Fusil d'assaut",
    "Fusil Sniper",
    "Fusil à pompe",
    "Pistolet-mitrailleur",
    "Lance-grenade",
    "Mitrailleuse",
    "Lance-roquette",
    "Grenade",
    "Explosif",
    "Magazine",
    "Autre",
    "Accessoire",
    "Non identifiée",
]

# Au sein d'une categorie, l'ordre d'affichage suit par defaut l'ID brut
# de l'arme - mais certaines familles (ex. couleurs de grenade fumigene)
# doivent rester groupees visuellement meme si leurs ID reels sont
# eparpilles. Override explicite : ID -> position de tri (flottant pour
# pouvoir s'intercaler sans renumeroter). Absent de ce dict = trie par ID.
WEAPON_SORT_OVERRIDE = {
    0x38: 100.0,  # Grenades fumigenes (generique, couleur non precisee)
    0x3a: 100.1,  # Grenade fumigene (Verte)
    0x3c: 100.2,  # Grenade fumigene (Bleue)
    0x3b: 100.3,  # Grenade fumigene (Jaune)
    0x39: 100.4,  # Grenade fumigene (Rouge)
}

# Sous-ensemble de WEAPON_SORT_OVERRIDE qui doit en plus demarrer une
# nouvelle ligne d'affichage (pas juste se reordonner au sein de la meme
# ligne) - voir gui_app.py WeaponsPanel._add_group.
WEAPON_ROW_BREAK_IDS = {0x38, 0x39, 0x3a, 0x3b, 0x3c}

WEAPON_STATE_OFFSET = 0x1d4
WEAPON_STATE_COUNT = 95


def read_weapon_states(path: str) -> dict[int, int]:
    with open(path, "rb") as f:
        data = decrypt(f.read())
    return {
        i: struct.unpack_from("<H", data, WEAPON_STATE_OFFSET + 2 * i)[0]
        for i in range(WEAPON_STATE_COUNT)
    }


# IDs confirmes comme des artefacts structurels du tableau, pas de vraies
# armes/objets acquis - masques entierement (ni affiches, ni comptes) pour
# ne pas fausser les compteurs "X/Y acquis" avec des cases qui n'ont jamais
# represente une vraie trouvaille en jeu.
# - 0x5c/0x5d/0x5e (armes) : comportement incoherent d'une partie a
#   l'autre (deja "obtenu" des la toute premiere sauvegarde sur certaines
#   parties, apparait plus tard sur d'autres) - pas un vrai declencheur de
#   scenario identifiable. Reconfirme (2026-09-05) : deja a 2 sur une
#   partie neuve (155s de jeu, encore Acte 1, seul le couteau possede cote
#   armes identifiees) - coherent avec le cas "deja obtenu des le debut".
STRUCTURAL_WEAPON_IDS = {0x5c, 0x5d, 0x5e}
# - 0x00/0x13 (objets generaux) : valent 0 (jamais 65535) sur absolument
#   toutes les saves disponibles, y compris la toute premiere du jeu.
#   0x00 reconfirme (2026-09-23) : force a 1 en memoire live (voir
#   live_trainer.py), aucun effet visible en jeu (inventaire, HUD, menu
#   pause) - pas un vrai objet.
STRUCTURAL_ITEM_IDS = {0x00, 0x13}


# Exceptions au sens habituel de l'etat 1 ("acquise mais verrouillee chez
# Drebin, pas utilisable"). Confirme par l'utilisateur (2026-09-07,
# plusieurs tests) : le Silencieux M4 reste bloque a 1 sur certaines
# parties tout en etant deja monte et fonctionnel sur son M4 en jeu -
# donc le point rouge "verrouille" serait un faux positif pour cet ID.
# Silencieux Mk.23 (0x4e, identite desormais confiance haute - voir
# WEAPON_NAMES) ajoute par precaution/analogie le 2026-09-09, meme
# situation potentielle qu'avec le Silencieux M4 - toujours pas confirme
# par un test dedie sur ce point precis (le comportement "faux
# verrouille" specifiquement), meme si l'identite elle-meme l'est
# desormais.
# 2e confirmation directe le 2026-09-24 : Silencieux Operator (0x4d) lit
# etat=1 (weapon_state_rva) alors que l'utilisateur en possede et en
# utilise activement une vingtaine (HUD en jeu "SIL 26"/"SIL 25" pendant
# le tir) - meme phenomene que le Silencieux M4, pas une preuve que l'ID
# 0x4d est incorrect. Renforce l'hypothese que ce "faux verrouille" est
# un comportement general des accessoires a durabilite/stock consommable
# (silencieux qui s'usent et se remplacent automatiquement), pas un cas
# isole du M4.
DREBIN_LOCK_EXCEPTIONS = {0x52, 0x4e, 0x4d}  # Silencieux M4, Mk.23, Operator


def read_weapons(path: str) -> list[dict]:
    """Retourne les 95 entrees du tableau d'armes (moins STRUCTURAL_WEAPON_IDS,
    masquees), groupees par categorie (voir WEAPON_CATEGORIES/
    WEAPON_GROUP_ORDER) pour un affichage en sections. Etat 0 = non
    acquise, 1 ou 2 = acquise. Sens de 1 vs 2 CONFIRME (2026-09-06, retour
    utilisateur) : certaines armes ramassees sur le terrain sont
    verrouillees (1, necessitent un deverrouillage via Drebin avant de
    pouvoir etre utilisees) puis passent a 2 une fois deverrouillees - pas
    "possedee" vs "equipee" comme suppose avant. On traite les deux comme
    "possedee" (owned=True) ici, la distinction verrouillee/deverrouillee
    n'est pas affichee separement pour l'instant. Nom generique
    "Arme #NN" quand l'ID n'est pas dans WEAPON_NAMES (grande majorite
    pour l'instant)."""
    states = read_weapon_states(path)
    by_group: dict[str, list[dict]] = {g: [] for g in WEAPON_GROUP_ORDER}
    for weapon_id, state in states.items():
        if weapon_id in STRUCTURAL_WEAPON_IDS:
            continue
        group = WEAPON_CATEGORIES.get(weapon_id, "Non identifiée")
        by_group[group].append({
            "id": weapon_id,
            "name": WEAPON_NAMES.get(weapon_id, f"Arme #{weapon_id:02d}"),
            "owned": state in (1, 2),
            "drebin_locked": state == 1 and weapon_id not in DREBIN_LOCK_EXCEPTIONS,
            "identified": weapon_id in WEAPON_NAMES,
            "group": group,
        })
    for group in by_group:
        by_group[group].sort(key=lambda e: WEAPON_SORT_OVERRIDE.get(e["id"], e["id"]))
    return [entry for group in WEAPON_GROUP_ORDER for entry in by_group[group]]


def find_value(data: bytes, value: int, region: tuple[int, int] | None = None):
    """Cherche `value` encodé en u8/u16/u32/i32 (LE et BE) dans `data`.

    Utilisé pour la corrélation manuelle : on connaît une valeur affichée en
    jeu, on cherche à quel(s) offset(s) elle apparaît dans le fichier
    déchiffré.
    """
    lo, hi = region or (0, len(data))
    hits = []
    for fmt in ("B", "<H", ">H", "<I", ">I", "<i", ">i"):
        size = struct.calcsize(fmt)
        for offset in range(lo, hi - size + 1):
            if struct.unpack_from(fmt, data, offset)[0] == value:
                hits.append((offset, fmt))
    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_dump = sub.add_parser("dump", help="Déchiffre et affiche en hexa")
    p_dump.add_argument("save_path")
    p_dump.add_argument("--start", type=lambda x: int(x, 0), default=0)
    p_dump.add_argument("--length", type=lambda x: int(x, 0), default=0x100)

    p_find = sub.add_parser("find", help="Cherche une valeur connue (corrélation)")
    p_find.add_argument("save_path")
    p_find.add_argument("value", type=int)
    p_find.add_argument("--start", type=lambda x: int(x, 0), default=0)
    p_find.add_argument("--end", type=lambda x: int(x, 0), default=None)

    p_stats = sub.add_parser("stats", help="Affiche les stats déjà identifiées")
    p_stats.add_argument("save_path")
    p_stats.add_argument(
        "--metadata", help="Chemin vers METADATA.SAV (pour le temps de jeu total)"
    )

    args = parser.parse_args()

    if args.command == "dump":
        with open(args.save_path, "rb") as f:
            data = decrypt(f.read())
        chunk = data[args.start : args.start + args.length]
        for i in range(0, len(chunk), 16):
            row = chunk[i : i + 16]
            hexpart = " ".join(f"{b:02x}" for b in row)
            asciipart = "".join(chr(b) if 0x20 <= b < 0x7f else "." for b in row)
            print(f"{args.start + i:06x}  {hexpart:<47}  {asciipart}")

    elif args.command == "find":
        with open(args.save_path, "rb") as f:
            data = decrypt(f.read())
        end = args.end if args.end is not None else len(data)
        hits = find_value(data, args.value, (args.start, end))
        if not hits:
            print("Aucune correspondance.")
        for offset, fmt in hits:
            print(f"offset=0x{offset:04x} ({offset})  format={fmt}")

    elif args.command == "stats":
        if not STATS:
            print("Aucun offset confirmé pour l'instant (voir notes.md).")
            return
        for name, value in read_stats(args.save_path).items():
            print(f"{name}: {value}")
        if args.metadata:
            seconds = read_playtime_seconds(args.metadata)
            print(f"playtime_secondes (approx +/-30s): {seconds}")
            print(f"numero_partie: {read_playthrough_number(args.metadata)}")
            diff_score = read_difficulty_score(args.metadata)
            diff_name = DIFFICULTY_NAMES.get(diff_score, f"inconnu (score {diff_score})")
            print(f"difficulte: {diff_name}")


if __name__ == "__main__":
    main()
