"""Adresses et tables du jeu (chaine de pointeurs, objets, armes, vitals)."""
# ---------------------------------------------------------------------------
# Specifique MGS4 : chaine de pointeurs + tables objets/armes.
# Source de la RVA : zexk/bbtracker, docs/mgs4_research.md (licence MIT).
# ---------------------------------------------------------------------------

PROCESS_NAME = "mgs4.exe"
# 4 pointeurs documentes par zexk/bbtracker a ces RVA. "linkvarbuf" a la
# meme disposition interne que MGS4.SAV (d'ou la reutilisation directe de
# ITEM_STATE_OFFSET/WEAPON_STATE_OFFSET pour le tableau objets/armes tel
# que serialise dans la save). MAIS teste en direct (2026-09-22/23) : ni
# linkvarbuf, ni varbuf (linkvarbuf-0x2800), ni les 2 "snapshots" ne
# suivent le stock de Ration en temps reel (tous restent figes pendant
# qu'un ramassage/consommation change reellement le stock affiche en jeu).
# Ces 4 buffers restent utilises pour items/armes (aucune meilleure piste
# pour l'instant), mais avec une grosse reserve de fiabilite - voir
# CONFIRMED_LIVE_RVAS ci-dessous pour les champs realmenet verifies en
# direct par scan memoire (technique Cheat Engine, pas la chaine de
# pointeurs documentee).
LINKVARBUF_POINTER_RVA = 0x1C28B28
VARBUF_POINTER_RVA = 0x1C28B38

# Mise a jour du jeu le 2026-09-24 : toutes les adresses trouvees le
# 2026-09-23 (table objets ET armes) se sont decalees d'un montant
# UNIFORME - confirme par test (Ration retombe exactement sur la bonne
# valeur avec ce decalage, item[0x00]/item[0x13] restent a 0, 5 armes
# confirmees revues par l'utilisateur en jeu). PAS applique a
# LINKVARBUF_POINTER_RVA/VARBUF_POINTER_RVA ci-dessus, qui eux n'ont pas
# bouge (sanity_check passe sans ce decalage). Si une future mise a jour
# decale a nouveau tout d'un bloc, chercher le meme genre de decalage
# constant avant de tout rescanner individuellement - beaucoup plus
# rapide (voir notes.md, session 2026-09-24).
MODULE_PATCH_SHIFT = 0x20

# Table objets (99 entrees) : formule FIXE et validee, trouvee dans
# MGS4.CT (table Cheat Engine communautaire de RMLSNK, non redistribuee
# ici, voir la section "Credits et sources" du README) via deux fonctions assembleur
# differentes du jeu ("objSongs"/6CEAC et "objItems"/900AE6) qui lisent
# toutes les deux [base_struct+0x14] apres avoir localise le struct d'un
# item par id (bound check "cmp ecx,62" = 0x62 = notre ITEM_STATE_COUNT-1
# exactement). Base statique a l'interieur de l'image du module (donc
# stable d'un lancement a l'autre, pas de pointeur a suivre) :
#   struct_base(id) = 0x1D84310 + id*0x48
#   etat(id)         = struct_base(id) + 0x14   (u16, meme convention
#                       0/1/65535 que le fichier de save)
# Valide le 2026-09-23 : correspond EXACTEMENT a l'adresse de Ration
# retrouvee independamment par scan memoire "valeur exacte" sur 5
# changements reels en jeu (0x1D8436C = 0x1D84310 + 1*0x48 + 0x14).
ITEM_STRUCT_BASE_RVA = 0x1D84310
ITEM_STRUCT_STRIDE = 0x48
ITEM_STRUCT_STATE_OFFSET = 0x14


def item_state_rva(item_id: int) -> int:
    return ITEM_STRUCT_BASE_RVA + item_id * ITEM_STRUCT_STRIDE + ITEM_STRUCT_STATE_OFFSET + MODULE_PATCH_SHIFT


# Table armes (95 entrees, WEAPON_STATE_OFFSET dans le fichier de save) :
# formule lineaire trouvee le 2026-09-24 (voir notes.md), sur le meme
# principe que la table objets ci-dessus mais avec une foulee differente
# et PAS de structure imbriquee (u16 directement, pas de sous-champ) :
#   etat(id) = 0x1D8258A + id*0x50   (u16, convention 0/1/2 : non
#              possedee/verrouillee/utilisable)
# Validee sur les 11 RVA deja confirmees individuellement par scan
# memoire/isolation manuelle (CONFIRMED_WEAPON_RVAS ci-dessous) : 9
# collaient exactement, les 2 restantes (0x0a/0x0b, lot Otacon) collaient
# apres un echange qui a ensuite ete confirme par double test en jeu de
# l'utilisateur (voir notes.md, correction WEAPON_NAMES dans
# mgs4save.py). Remplace donc l'ancienne piste MGS4.CT ("Weapons",
# foulee 0x18, testee et infirmee le 2026-09-23 - numerotation differente
# de nos ID de fichier de save, valeurs absurdes hors MK.17).
# CONFIRMED_WEAPON_RVAS ci-dessous est conserve comme trace d'audit : la
# liste des IDs dont l'identite reelle (quelle arme se cache derriere ce
# numero) a ete confirmee par observation en jeu, independamment de la
# formule - la formule donne un RVA fiable pour N'IMPORTE QUEL id, mais
# ne dit rien sur la fiabilite du NOM attribue a cet id dans
# mgs4save.py.WEAPON_NAMES (voir les commentaires "confiance basse"
# restants la-bas, notamment pour le lot Otacon : Mk.2 Pistol vs
# Operator, DSR-1, Sachet a gaz somnifere - Tanegashima confirme le
# 2026-09-24 grace a cette meme formule, bascule d'etat + verification en
# jeu).
WEAPON_ETAT_BASE_RVA = 0x1D8258A
WEAPON_ETAT_STRIDE = 0x50


def weapon_state_rva(weapon_id: int) -> int:
    return WEAPON_ETAT_BASE_RVA + weapon_id * WEAPON_ETAT_STRIDE + MODULE_PATCH_SHIFT


# Munitions dans le chargeur (pas la reserve) : +6 octets par rapport a
# l'etat, dans le meme struct par arme - voir MGS4Live.read_weapon_magazine.
WEAPON_MAGAZINE_OFFSET = 6
# Capacite max du chargeur (+8, juste apres le courant) - confirme
# 2026-09-26 : reste a 7 pendant qu'un tir fait descendre +6 de 7 a 6,
# meme technique que les paires courant/max de VITALS.
WEAPON_MAGAZINE_MAX_OFFSET = 8

# Objet special actuellement equipe (Bandana=0x0f, Camouflage optique=
# 0x10, 0=aucun) - PAS un flag booleen, un vrai ID d'objet lu par le
# moteur du jeu en temps reel (confirme 2026-09-26 : l'ecrire equipe
# reellement l'objet en jeu, pas seulement en memoire - le HUD et le
# comportement suivent). Trouve par scan exact (15 puis 16 en alternant
# Bandana/Camouflage optique, cf. la methode habituelle) apres l'echec
# d'une premiere piste booleen (corrélée mais pas causale, voir notes.md).
# PAS utilise par "Munitions infinies" (VitalsTab) au final : forcer le
# Bandana ne marche que si le joueur le possede reellement (sinon le jeu
# rejette silencieusement), et entre en conflit avec un autre objet
# special reellement equipe (ex. Camouflage optique) - trop fragile pour
# un usage general, voir notes.md. Constante gardee en audit trail (RE
# confirmee) au cas ou une future fonctionnalite dediee au Bandana en
# aurait besoin.
SPECIAL_ITEM_EQUIPPED_RVA = 0x23FED44A
BANDANA_ITEM_ID = 0x0f


def special_item_equipped_rva() -> int:
    return SPECIAL_ITEM_EQUIPPED_RVA + MODULE_PATCH_SHIFT


CONFIRMED_WEAPON_RVAS: dict[int, int] = {
    # MK.17 (0x1e) : confirme le 2026-09-23, scan sur transition reelle
    # verrouille(1)->utilisable(2) apres deverrouillage chez Drebin. Seul
    # candidat survivant dans la zone stable de l'image du module apres
    # intersection avec le scan initial (2 894 191 -> 410 -> 1).
    # CONFIANCE MAXIMALE : contrairement a CONFIRMED_WEAPON_AMMO_RVAS
    # ci-dessous, l'ecriture a ete verifiee visuellement en jeu (forcer a
    # verrouille/utilisable change reellement l'etat dans la roue
    # d'equipement), pas juste une relecture memoire.
    0x1e: 0x1D82EEA,
    # Couteau paralysant (0x01) : RVA 0x1D825DA, confirme le 2026-09-23 par
    # isolation manuelle (10 candidats "deja utilisables" forces a
    # verrouille sauf un a la fois, utilisateur confirme quelle arme
    # redevient utilisable a chaque tour). Effet verifie visuellement en
    # jeu par construction de la methode elle-meme.
    0x01: 0x1D825DA,
    # Mk.2 Pistol (0x02) : RVA 0x1D8262A, confirme le 2026-09-23 par la
    # meme methode d'isolation - resout enfin l'ambiguite du "lot Otacon"
    # (0x02/0x03/0x0a/0x0b/0x4d, jamais isole individuellement avant, voir
    # notes.md). Reconfirme independamment le 2026-09-24 par bascule
    # d'etat via weapon_state_rva (comme pour 0x1d/Tanegashima).
    0x02: 0x1D8262A,
    # Operator (0x03) : RVA 0x1D8267A, confirme le 2026-09-23, meme methode
    # d'isolation - lot Otacon.
    0x03: 0x1D8267A,
    # Thor .45-70 (0x0a) : RVA 0x1D828AA, confirme le 2026-09-23, meme
    # methode d'isolation - lot Otacon. IDs 0x0a/0x0b corriges le
    # 2026-09-24 : la formule lineaire du tableau d'etat (voir plus haut,
    # RVA = 0x1D8258A + id*0x50 + MODULE_PATCH_SHIFT) predisait un
    # echange par rapport a l'attribution initiale, confirme par double
    # test en jeu de l'utilisateur (verrouiller cette adresse verrouille
    # bien le Thor .45-70, pas le 1911). Voir notes.md.
    0x0a: 0x1D828AA,
    # 1911 Modifie (0x0b) : RVA 0x1D828FA, confirme le 2026-09-23, meme
    # methode d'isolation - lot Otacon. ID corrige le 2026-09-24 (voir
    # commentaire ci-dessus).
    0x0b: 0x1D828FA,
    # M4 (0x18) : RVA 0x1D82D0A, confirme le 2026-09-23, meme methode
    # d'isolation. Munitions deja connues (partagees avec AK-102).
    0x18: 0x1D82D0A,
    # AK-102 (0x19) : RVA 0x1D82D5A, confirme le 2026-09-23, meme methode
    # d'isolation. Munitions deja connues (partagees avec M4).
    0x19: 0x1D82D5A,
    # Mine a gaz somnifere (0x41) : RVA 0x1D839DA, confirme le 2026-09-23,
    # meme methode d'isolation. Munitions deja connues.
    0x41: 0x1D839DA,
    # Magazine Playboy (0x45) : RVA 0x1D83B1A, confirme le 2026-09-23, meme
    # methode d'isolation. Munitions deja connues.
    0x45: 0x1D83B1A,
    # Grenade paralysante (0x36) : confirme le 2026-09-23, scan sur
    # transition reelle verrouillee(1)->utilisable(2) apres deverrouillage
    # chez Drebin (2 870 831 -> 512 -> 1 candidat stable). Ecriture testee
    # en aller-retour (relecture memoire uniquement, pas encore verifiee
    # visuellement en jeu pour celle-ci specifiquement).
    0x36: 0x1D8366A,
    # Tanegashima (0x1d) : RVA 0x1D82E9A (= weapon_state_rva(0x1d), pas de
    # scan necessaire), confirme le 2026-09-24 en basculant l'etat via le
    # trainer et en observant en jeu que c'est bien le Tanegashima qui se
    # verrouille/deverrouille - resout la "confiance basse" historique de
    # cet ID (voir WEAPON_NAMES dans mgs4save.py et notes.md).
    0x1d: 0x1D82E9A,
    # Masterkey (0x4a) : RVA 0x1D83CAA (= weapon_state_rva(0x4a), pas de
    # scan necessaire), confirme le 2026-09-24 - forcer l'etat a 0 rend
    # bien le Masterkey indisponible/non equipable en jeu. 1 et 2 se
    # comportent pareil (pas de palier "verrouille chez Drebin" pour cette
    # arme a declencheur scenaristique unique - contrairement aux armes
    # achetees), d'ou l'absence d'effet observee au premier essai (etat
    # force a 1 au lieu de 0).
    0x4a: 0x1D83CAA,
    # Silencieux Operator (0x4d) : RVA 0x1D83D9A (=
    # weapon_state_rva(0x4d), pas de scan necessaire), confirme le
    # 2026-09-24 - meme test que le Masterkey (forcer l'etat a 0, pas 1)
    # : le silencieux devient bien indisponible en jeu. Resout enfin le
    # dernier morceau du lot Otacon (0x02/0x03/0x0a/0x0b/0x4d).
    0x4d: 0x1D83D9A,
    # Silencieux Mk.23 (0x4e) : RVA 0x1D83DEA (= weapon_state_rva(0x4e),
    # pas de scan necessaire), confirme le 2026-09-24 - tous les
    # accessoires forces a 0 puis rachetes un par un chez Drebin,
    # seul 0x4e est repasse a 2 au moment de racheter le Silencieux
    # Mk.23. Resout la "confiance basse" historique sur cette identite.
    0x4e: 0x1D83DEA,
    # Silencieux 1911 (0x4f) : RVA 0x1D83E3A (= weapon_state_rva(0x4f)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute depuis un test isole du 2026-09-05).
    0x4f: 0x1D83E3A,
    # Silencieux P90 (0x51) : RVA 0x1D83EDA (= weapon_state_rva(0x51)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute depuis un test isole du 2026-09-05).
    0x51: 0x1D83EDA,
    # Visee laser (M4) (0x58) : RVA 0x1D8410A (= weapon_state_rva(0x58)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute depuis un test isole du 2026-09-06).
    0x58: 0x1D8410A,
    # Lumiere Fusil (M4) (0x57) : RVA 0x1D840BA (= weapon_state_rva(0x57)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (nom exact deja confirme par capture d'ecran, 2026-09-02).
    0x57: 0x1D840BA,
    # Silencieux M10 (0x50) : RVA 0x1D83E8A (= weapon_state_rva(0x50)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute depuis un test isole du 2026-09-05).
    0x50: 0x1D83E8A,
    # Visee point rouge (MP7) (0x56) : RVA 0x1D8406A (=
    # weapon_state_rva(0x56)), reconfirme le 2026-09-24 par le meme
    # rachat un par un chez Drebin (deja confirmee, test isole propre sur
    # partie fraiche).
    0x56: 0x1D8406A,
    # Lunette de fusil (0x54) : RVA 0x1D83FCA (= weapon_state_rva(0x54)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute).
    0x54: 0x1D83FCA,
    # GP-30 (0x4c) : RVA 0x1D83D4A (= weapon_state_rva(0x4c)), reconfirme
    # le 2026-09-24 par le meme rachat un par un chez Drebin (deja
    # confiance haute).
    0x4c: 0x1D83D4A,
    # Visee point rouge (M4) (0x55) : RVA 0x1D8401A (=
    # weapon_state_rva(0x55)), reconfirme le 2026-09-24 par le meme
    # rachat un par un chez Drebin (deja confirmee).
    0x55: 0x1D8401A,
    # Silencieux M4 (0x52) : RVA 0x1D83F2A (= weapon_state_rva(0x52)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute - voir aussi DREBIN_LOCK_EXCEPTIONS dans
    # mgs4save.py pour son comportement "faux verrouille" connu).
    0x52: 0x1D83F2A,
    # XM320 (0x4b) : RVA 0x1D83CFA (= weapon_state_rva(0x4b)), reconfirme
    # le 2026-09-24 par le meme rachat un par un chez Drebin (deja
    # confiance haute).
    0x4b: 0x1D83CFA,
    # Poignee avant A. (0x5a) : RVA 0x1D841AA (= weapon_state_rva(0x5a)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute).
    0x5a: 0x1D841AA,
    # Poignee avant B. (0x5b) : RVA 0x1D841FA (= weapon_state_rva(0x5b)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute).
    0x5b: 0x1D841FA,
    # Silencieux M14EBR (0x53) : RVA 0x1D83F7A (= weapon_state_rva(0x53)),
    # reconfirme le 2026-09-24 par le meme rachat un par un chez Drebin
    # (deja confiance haute). Dernier accessoire de la plage 0x4a-0x5b a
    # etre reconfirme individuellement - les 18 sont desormais tous
    # confirmes.
    0x53: 0x1D83F7A,
    # Desert Eagle (Canon Long) (0x09) : RVA 0x1D8285A (=
    # weapon_state_rva(0x09)), decouvert via le trainer le 2026-09-24
    # (ID auparavant sans nom).
    0x09: 0x1D8285A,
    # Type 17 (0x10) : RVA 0x1D82A8A (= weapon_state_rva(0x10)),
    # decouvert via le trainer le 2026-09-24 (ID auparavant sans nom).
    # Etat actuel = 1 malgre 878 munitions en stock (pool .45 ACP
    # partage) - possible cas de "faux verrouille" comme les silencieux
    # (voir DREBIN_LOCK_EXCEPTIONS dans mgs4save.py), pas encore
    # confirme par un test dedie.
    0x10: 0x1D82A8A,
    # Patriot (0x16) : RVA 0x1D82C6A (= weapon_state_rva(0x16)),
    # decouvert via le trainer le 2026-09-24 (ID auparavant sans nom).
    # Arme bonus a munitions illimitees, pas de pool de munitions a
    # suivre dans CONFIRMED_WEAPON_AMMO_RVAS. Etat actuel = 1 malgre
    # possession confirmee - meme pattern que le Type 17 (0x10).
    0x16: 0x1D82C6A,
    # "Destabil.SOP" (0x44) : RVA 0x1D83ACA (= weapon_state_rva(0x44)),
    # decouvert via le trainer le 2026-09-24 - objet inedit "POSER" (pas
    # une arme), jamais documente ailleurs. Etat=2 (possede) au moment de
    # la decouverte.
    0x44: 0x1D83ACA,
}

# Table MUNITIONS par arme (separee de la table possession/etat ci-dessus -
# coherent avec le tableau 0x352 "munitions par emplacement d'equipement"
# deja documente dans notes.md pour le fichier de save). PAS reliee au
# flag "possedee" : poser toutes ses mines n'a fait bouger aucun des
# candidats de la table etat/possession (voir notes.md, session
# 2026-09-23) - la possession reste vraie une fois obtenue, seul le stock
# varie ici.
# ATTENTION - RAFRAICHISSEMENT DIFFERE, PAS INSTANTANE : l'ecriture est
# bien la bonne adresse (confirme par l'utilisateur, 2026-09-23), mais le
# HUD/inventaire ne se met a jour qu'au moment d'EQUIPER l'arme concernee
# - pas en continu ni immediatement apres l'ecriture. Premiere impression
# "l'ecriture ne fait rien" corrigee : juste besoin d'equiper l'arme pour
# forcer le rafraichissement de l'affichage.
#   - Mine a gaz somnifere (arme 0x41) : RVA 0x1D82420, confirme par scan
#     "valeur exacte" sur un achat de 36 puis pose de 2 (36->34), seul
#     candidat stable dans l'image du module apres intersection
#     (248 089 -> 3 -> 1).
#   - AK-102 (0x19) / M4 (0x18) : meme adresse (RVA 0x1D820C0) pour les
#     deux, confirme (2026-09-23) - pool de munitions .5.56mm PARTAGE entre
#     armes du meme calibre, comme deja documente dans notes.md pour le
#     fichier de save (tableau 0x352). Scan "valeur exacte" 278->270 :
#     11 014 -> 33 candidats stables -> 1 seul apres le changement reel.
CONFIRMED_WEAPON_AMMO_RVAS: dict[int, int] = {
    0x41: 0x1D82420,
    0x18: 0x1D820C0,
    0x19: 0x1D820C0,
    # XM8 (0x1f) et Mk.46 MOD1 (0x20) partagent le MEME pool 5,56mm (avec
    # M4/AK-102) - confirme (2026-09-24) via capture d'ecran du menu
    # "boutique" affichant ces armes a la meme valeur (829), qui
    # correspondait exactement a la valeur deja lue en memoire, pas de
    # scan separe necessaire.
    0x1f: 0x1D820C0,
    0x20: 0x1D820C0,
    # AN-94 (0x1b) : RVA 0x1D820A8, confirme (2026-09-24) - scan "valeur
    # exacte" sur 180 (calibre 5,45x39mm propre, non partage avec une
    # arme deja connue), filtre zone proche connue -> 1 seul candidat
    # direct.
    0x1b: 0x1D820A8,
    # Tanegashima (0x1d, identite desormais confiance haute - confirmee le
    # 2026-09-24 via weapon_state_rva, voir WEAPON_NAMES dans mgs4save.py)
    # : RVA 0x1D82198, confirme (2026-09-24) - scan "valeur exacte" sur
    # 300 (balle plomb, calibre propre), filtre zone proche connue -> 1
    # seul candidat direct.
    0x1d: 0x1D82198,
    # DSR-1 (0x29, identite exacte confiance basse - jamais confirmee
    # individuellement, voir WEAPON_NAMES dans mgs4save.py) : RVA
    # 0x1D82180, confirme (2026-09-24) - scan "valeur exacte" sur 365
    # (7,62x67mm, calibre propre), filtre zone proche connue -> 1 seul
    # candidat direct.
    0x29: 0x1D82180,
    # SVD (0x2c) : RVA 0x1D82120, confirme (2026-09-24) - scan "valeur
    # exacte" sur 936 (7,62x54mm R, calibre propre), filtre zone proche
    # connue -> 1 seul candidat direct. PKM (0x22) partage le MEME pool -
    # confirme via capture d'ecran boutique (936, correspondance directe),
    # pas de scan separe necessaire.
    0x2c: 0x1D82120,
    0x22: 0x1D82120,
    # Mosin-Nagant (0x2b) : RVA 0x1D81FA0, confirme (2026-09-24) - scan
    # "valeur exacte" sur 320 (fleche anesthesiante 7,62mm, calibre
    # propre), filtre zone proche connue -> 1 seul candidat direct.
    0x2b: 0x1D81FA0,
    # VSS (0x27) : RVA 0x1D82168, confirme (2026-09-24) par scan "valeur
    # exacte" sur 110 (9x39mm), 2 candidats stables -> 1 seul confirme par
    # une vraie consommation (110->104), l'autre candidat restant fige a
    # 110.
    0x27: 0x1D82168,
    # M82A2 (0x28) : RVA 0x1D82078, confirme (2026-09-24) par scan "valeur
    # exacte" sur 80 (.50 BMR), 3 candidats stables -> 1 seul confirme par
    # une vraie consommation (80->70), les 2 autres restes figes a 80.
    0x28: 0x1D82078,
    # Rail Gun (0x2d) : RVA 0x1D824B0, confirme (2026-09-24) par scan
    # "valeur exacte" sur 100 (munitions Rail Gun), 8 candidats stables ->
    # 1 seul confirme par une vraie consommation (100->98), les 7 autres
    # restes figes a 100.
    0x2d: 0x1D824B0,
    # Double canon (0x24) : RVA 0x1D821B0, confirme (2026-09-24) - scan
    # "valeur exacte" sur 152 (12GA chevrotine 00, calibre propre), filtre
    # zone proche connue -> 1 seul candidat direct. M870 Modifie (0x25) et
    # Saiga-12 (0x26) partagent le MEME pool - confirme via capture
    # d'ecran boutique (152, correspondance directe pour les 3 armes),
    # pas de scan separe necessaire.
    0x24: 0x1D821B0,
    0x25: 0x1D821B0,
    0x26: 0x1D821B0,
    # Masterkey (0x4a) : meme pool 12GA - confirme (2026-09-24) par
    # correspondance directe (152) puis vraie consommation simultanee
    # sur le pool (152->148).
    0x4a: 0x1D821B0,
    # MGL-140 (0x2e) : RVA 0x1D82210, confirme (2026-09-24) par scan
    # "valeur exacte" sur 63 (40mm GRD), 2 candidats stables -> 1 seul
    # confirme par une vraie consommation (63->60), l'autre reste fige.
    # XM320 (0x4b) partage le MEME pool 40mm - confirme par une vraie
    # consommation simultanee sur les deux (65->61).
    0x2e: 0x1D82210,
    0x4b: 0x1D82210,
    # GP-30 (0x4c) : RVA 0x1D821F8, confirme (2026-09-24) par scan
    # "valeur exacte" sur 65, 2 candidats stables -> 1 seul confirme par
    # une vraie consommation (65->63), l'autre reste fige a 65.
    0x4c: 0x1D821F8,
    # RPG-7 (0x32) : RVA 0x1D822B8, confirme (2026-09-24) par scan "valeur
    # exacte" sur 64, 12 candidats stables -> 1 seul confirme par une
    # vraie consommation (64->63), les 11 autres restes figes a 64.
    0x32: 0x1D822B8,
    # XM25 (0x2f) : RVA 0x1D82270, confirme (2026-09-24) par scan "valeur
    # exacte" sur 2 (valeur tres basse, 132 candidats stables initiaux) ->
    # affine via 2 consommations reelles successives (2->1 puis 1->51,
    # rechargement) -> 1 seul candidat survivant a chaque etape.
    0x2f: 0x1D82270,
    # FIM-92A (0x30) : RVA 0x1D82288, confirme (2026-09-24) par scan
    # "valeur exacte" sur 54, 2 candidats stables -> 1 seul confirme par
    # une vraie consommation (54->51), l'autre reste fige a 54.
    0x30: 0x1D82288,
    # FGM-148 Javelin (0x31) : RVA 0x1D822A0, confirme (2026-09-24) par
    # scan "valeur exacte" sur 36, 2 candidats stables -> 1 seul confirme
    # par une vraie consommation (36->34), l'autre reste fige a 36. Notee
    # convergence de valeur avec M72A3 (les deux terminent a 34) mais
    # adresses distinctes suivies independamment depuis des valeurs de
    # depart differentes (35 vs 36) - pas un pool partage, coincidence.
    0x31: 0x1D822A0,
    # M72A3 (0x33) : RVA 0x1D822D0, confirme (2026-09-24) par scan "valeur
    # exacte" sur 35, 2 candidats stables -> 1 seul confirme par une
    # vraie consommation (35->34), l'autre reste fige a 35.
    0x33: 0x1D822D0,
    # Grenade (0x34) : RVA 0x1D822E8, confirme (2026-09-24) par scan
    # "valeur exacte" sur 85, 2 candidats stables -> 1 seul confirme par
    # une vraie consommation (85->84), l'autre reste fige a 85.
    0x34: 0x1D822E8,
    # Cocktail Molotov (0x3d) : RVA 0x1D823C0, confirme (2026-09-24) par
    # scan "valeur exacte" sur 60, 8 candidats stables -> 1 seul confirme
    # par une vraie consommation (60->57), les 7 autres restes figes a 60.
    0x3d: 0x1D823C0,
    # Grenade au phosphore blanc (0x35) : RVA 0x1D82300, confirme
    # (2026-09-24) par scan "valeur exacte" sur 75, 2 candidats stables ->
    # 1 seul confirme par une vraie consommation (75->70), l'autre reste
    # fige a 75.
    0x35: 0x1D82300,
    # Grenade a particules metalliques / "Electro" (0x37) : RVA 0x1D82330,
    # confirme (2026-09-24) par scan "valeur exacte" sur 22, 3 candidats
    # stables -> 1 seul confirme par une vraie consommation (22->18), les
    # 2 autres restes figes a 22.
    0x37: 0x1D82330,
    # Grenade fumigene generique (0x38) : RVA 0x1D82348, confirme
    # (2026-09-24) par scan "valeur exacte" sur 77, 2 candidats stables ->
    # 1 seul confirme par une vraie consommation (77->75), l'autre reste
    # fige a 77.
    0x38: 0x1D82348,
    # Grenade fumigene (Jaune) (0x3b) : RVA 0x1D82390, confirme
    # (2026-09-24) par scan "valeur exacte" sur 28, 6 candidats stables ->
    # 1 seul confirme par une vraie consommation (28->27), les 5 autres
    # restes figes a 28.
    0x3b: 0x1D82390,
    # Grenade fumigene (Rouge) (0x39) : RVA 0x1D82360, confirme
    # (2026-09-24) par scan "valeur exacte" sur 7, 9 candidats stables ->
    # 1 seul confirme par une vraie consommation (7->5), les 8 autres
    # restes figes a 7.
    0x39: 0x1D82360,
    # Grenade fumigene (Bleue) (0x3c) : RVA 0x1D823A8, confirme
    # (2026-09-24) par scan "valeur exacte" sur 35, 2 candidats stables ->
    # 1 seul confirme par une vraie consommation (35->32), l'autre reste
    # fige a 35.
    0x3c: 0x1D823A8,
    # Grenade fumigene (Verte) (0x3a) : RVA 0x1D82378, confirme
    # (2026-09-24) par scan "valeur exacte" sur 70, 2 candidats stables ->
    # 1 seul confirme par une vraie consommation (70->66), l'autre etait
    # un faux positif coincidant avec l'adresse deja connue du M82A2
    # (0x1D82078), reste fige a 70.
    0x3a: 0x1D82378,
    # Claymore (0x40) : RVA 0x1D82408, confirme (2026-09-24) par scan
    # "valeur exacte" sur 59, 2 candidats stables -> 1 seul confirme par
    # une vraie consommation (59->58), l'autre reste fige a 59.
    0x40: 0x1D82408,
    # C4 (0x42) : RVA 0x1D82438, confirme (2026-09-24) par scan "valeur
    # exacte" sur 18, 7 candidats stables -> 1 seul confirme par une
    # vraie consommation (18->17), les 6 autres restes figes a 18
    # (dont 0x1D82330, coincidence avec l'adresse deja connue de la
    # grenade Electro).
    0x42: 0x1D82438,
    # Sachet a gaz somnifere (0x43, identite confiance basse - voir
    # WEAPON_NAMES dans mgs4save.py) : RVA 0x1D82450, confirme
    # (2026-09-24) par scan "valeur exacte" sur 12, 10 candidats stables
    # -> 1 seul confirme par une vraie consommation (12->11), les 9
    # autres restes figes a 12.
    0x43: 0x1D82450,
    # Chargeur (0x3e, objet de diversion, pas une arme) : RVA 0x1D823D8,
    # confirme (2026-09-24) - scan "valeur exacte" sur 110, filtre zone
    # proche connue -> 1 seul candidat direct.
    0x3e: 0x1D823D8,
    # Magazine Emotion (0x46) : RVA 0x1D82498, confirme (2026-09-24) par
    # scan "valeur exacte" sur 19, 5 candidats stables -> 1 seul confirme
    # par une vraie consommation (19->18), les 4 autres restes figes a
    # 19.
    0x46: 0x1D82498,
    # "Destabil.SOP" (0x44) : RVA 0x1D82468, calcule via la formule
    # lineaire du bloc explosifs/etc (0x1D81E08 + id*0x18, voir
    # commentaire plus haut sur ce bloc) plutot que scanne - confirme
    # (2026-09-24) : lisait bien 0 (l'utilisateur n'en avait aucun),
    # ecrit a 10 pour permettre un test en jeu.
    # ATTENTION DANGER (2026-09-24) : tenter d'EQUIPER/UTILISER cet objet
    # en jeu (meme avec un stock force via cette adresse) a fait PLANTER
    # le jeu (fatal error, dump genere). Objet probablement pas prevu
    # pour etre reellement utilise en solo. Lire/ecrire cette valeur en
    # memoire reste sans danger en soi - c'est l'usage EN JEU qui pose
    # probleme. Voir notes.md.
    0x44: 0x1D82468,
    # Magazine Playboy (0x45) : RVA 0x1D82480, confirme (2026-09-23) par
    # scan "valeur exacte" sur un vrai changement de stock (2->11), filtre
    # zone proche connue puis intersection - 1 seul survivant direct.
    0x45: 0x1D82480,
    # Grenade paralysante (0x36) : RVA 0x1D82318, confirme (2026-09-23) par
    # scan "valeur exacte" sur une vraie consommation (5->4), filtre zone
    # proche connue puis intersection - 1 seul survivant direct.
    0x36: 0x1D82318,
    # MK.17 (0x1e) : RVA 0x1D82108, confirme (2026-09-23) par scan "valeur
    # exacte" sur une vraie consommation (37->29), filtre zone proche
    # connue - 2 candidats, 1 seul confirme par le vrai changement.
    # G3A3 (0x1a), FAL (0x1c), M14EBR (0x2a), HK21E (0x21) et M60E4 (0x23)
    # partagent le MEME pool 7,62x51mm - confirme (2026-09-24) via capture
    # d'ecran du menu "boutique" affichant ces armes a la meme valeur
    # (2214), qui correspondait exactement a la valeur deja lue en
    # memoire pour MK.17, pas de scan separe necessaire.
    0x1e: 0x1D82108,
    0x1a: 0x1D82108,
    0x1c: 0x1D82108,
    0x2a: 0x1D82108,
    0x21: 0x1D82108,
    0x23: 0x1D82108,
    # Thor .45-70 (0x0a, ID corrige le 2026-09-24 - voir CONFIRMED_WEAPON_RVAS
    # et notes.md) : RVA 0x1D82048, confirme (2026-09-23) par scan "valeur
    # exacte" sur une vraie consommation (10->8), filtre zone proche
    # connue - 7 candidats, 1 seul confirme. Munition propre (.45-70
    # Government, distincte du .45 ACP), coherent avec le fait que cette
    # adresse ne partage PAS le pool avec Operator/1911/Mk.23.
    0x0a: 0x1D82048,
    # Mk.2 Pistol (0x02) : RVA 0x1D81F28, confirme (2026-09-23) - scan
    # "valeur exacte" sur 95, filtre zone proche connue -> 1 seul candidat
    # directement (pas besoin de transition supplementaire).
    0x02: 0x1D81F28,
    # Operator (0x03) : RVA 0x1D82030, confirme (2026-09-23) - scan "valeur
    # exacte" sur 98, filtre zone proche connue -> 1 seul candidat direct.
    # 1911 Modifie (0x0b, ID corrige le 2026-09-24 - voir notes.md) partage
    # le MEME pool (.45 ACP) - confirme par l'utilisateur (tir avec
    # Operator, 98->97 visible aussi sur le 1911), pas de scan separe
    # necessaire. Mk.23 (0x04) aussi confirme dans le
    # meme pool (2026-09-24) : scan sur 933, meme adresse.
    # M-10 (0x13) : aussi dans le pool .45 ACP - confirme par l'utilisateur
    # (938, correspondance directe avec la valeur deja lue), pas de scan
    # separe necessaire. GSR (0x07, SIG Sauer GSR .45 ACP) : idem,
    # confirme (2026-09-24) par correspondance directe (938).
    0x03: 0x1D82030,
    0x0b: 0x1D82030,
    0x04: 0x1D82030,
    0x13: 0x1D82030,
    0x07: 0x1D82030,
    # Type 17 (0x10) : aussi dans le pool .45 ACP - confirme (2026-09-24)
    # par correspondance directe (878), pas de scan separe necessaire.
    0x10: 0x1D82030,
    # Five-Seven (0x06) : RVA 0x1D820D8, confirme (2026-09-24, post mise a
    # jour) - scan "valeur exacte" sur 2062, filtre zone proche connue ->
    # 1 seul candidat direct. P90 (0x14) partage le MEME pool (5.7x28mm,
    # coherent avec le calibre reel partage entre ces deux armes) -
    # confirme par l'utilisateur (2058->2038 visible sur les deux a la
    # fois), pas de scan separe necessaire.
    0x06: 0x1D820D8,
    0x14: 0x1D820D8,
    # PMM (0x05) : RVA 0x1D82138, confirme (2026-09-24, post mise a jour) -
    # scan "valeur exacte" sur 494, filtre zone proche connue -> 1 seul
    # candidat direct. Vz. 83 (0x17) et PP-19 Bizon (0x15) partagent le
    # MEME pool (9x18mm Makarov) - confirme par l'utilisateur (490->484
    # visible sur les trois a la fois ; le tout premier scan sur 490 avait
    # d'abord ete ecarte par prudence car identique a la valeur PMM du
    # moment), pas de scan separe necessaire.
    0x05: 0x1D82138,
    0x17: 0x1D82138,
    0x15: 0x1D82138,
    # PSS (0x0e) : RVA 0x1D820F0, confirme (2026-09-24) - scan "valeur
    # exacte" sur une vraie consommation (77->75), 3 candidats -> 1 seul
    # confirme par le vrai changement.
    0x0e: 0x1D820F0,
    # G18C (0x0f) : RVA 0x1D82150, confirme (2026-09-24) - scan "valeur
    # exacte" sur 210, filtre zone proche connue -> 1 seul candidat direct.
    # MP5SD2 (0x12) partage le MEME pool (9x19mm Parabellum) - confirme par
    # l'utilisateur (188 visible sur les deux a la fois, premier scan sur
    # 210 avait d'abord ete ecarte par prudence car identique a la valeur
    # G18C du moment), pas de scan separe necessaire.
    0x0f: 0x1D82150,
    0x12: 0x1D82150,
    # Arme de chasse (0x0c) : RVA 0x1D82018, confirme (2026-09-24) par 4
    # changements reels (18->15->14->7->37). Un 2e candidat (0x1D82950)
    # etait reste synchronise sur les 3 premiers tours (coincidence), puis
    # a diverge au 4e (reste bloque a 7 pendant que 0x1D82018 passait a
    # 37) - confirme que ce n'etait qu'un faux positif, pas un pool
    # partage. Identite de 0x1D82950 non poursuivie (sans interet).
    0x0c: 0x1D82018,
    # D.E. / Desert Eagle (0x08) : RVA 0x1D82060, confirme (2026-09-24) par
    # scan sur une vraie consommation (11->8), 3 candidats -> 1 seul
    # confirme par le vrai changement. Desert Eagle (Canon Long) (0x09)
    # partage le MEME pool (variante canon long, meme calibre) -
    # confirme par l'utilisateur (correspondance directe, 8), pas de scan
    # separe necessaire.
    0x08: 0x1D82060,
    0x09: 0x1D82060,
    # MP7 (0x11) : RVA 0x1D82090, confirme (2026-09-24) - scan "valeur
    # exacte" sur 953, filtre zone proche connue -> 1 seul candidat direct.
    0x11: 0x1D82090,
}


# "Etat de jeu" (Vie/Endurance/Stress/Batterie Solid Eye/Metal Gear REX) -
# decouvert le 2026-09-25 via le fichier MGS4.CT (section "aob Statistics",
# PAS marquee WIP/Graveyard contrairement a d'autres pistes du meme fichier -
# utilisee pour de vraies triches "vie/endurance/batterie infinies", donc a
# priori fiable). Confirme : pStatistics (leur nom) = linkvarbuf (le notre) -
# meme pointeur mgs4.exe+1C28B28, et leurs offsets +0x34/+0x54/+0x1C0
# correspondent EXACTEMENT aux offsets deja etablis chez nous pour le
# fichier de save (zone/stage, scene/progression, Drebin actuel). Toutes
# les valeurs testees et confirmees par de vraies transitions en jeu (voir
# notes.md) : Vie/Endurance en dommages reels, Stress sur plusieurs valeurs
# distinctes avec correspondance precise a l'affichage HUD (brut/10 = %).
# (offset_actuel, offset_max_ou_None, taille en octets, max_fixe_si_pas_de_max_live)
# relatifs a linkvarbuf. Stress n'a pas de champ "max" en memoire (juste
# une plage fixe 0-1000 pour brut/10 = 0-100%).
VITALS: dict[str, tuple[int, int | None, int, int | None]] = {
    "Sante": (0xB48, 0xB4A, 2, None),
    "Stamina": (0xB4C, 0xB4E, 2, None),
    "Stress": (0xB50, None, 2, 1000),
    "Batterie Solid Eye": (0xB52, 0xB54, 2, None),
    "Sante Metal Gear REX": (0xB70, 0xB74, 4, None),
}

# Etat d'alerte : PAS relatif a linkvarbuf, adresse statique trouvee dans
# MGS4.CT (section "Alert -- Ignore", elle-meme WIP/Graveyard, mais
# l'adresse capturee a l'injection s'est revelee fiable EN LECTURE malgre
# tout - voir notes.md). PAS de MODULE_PATCH_SHIFT a appliquer (confirme :
# l'appliquer donne une valeur absurde). Confirme par transitions reelles
# successives : 0=Normal/non repere, 1=Alerte, 2=Evasion, 3=Prudence (le
# 4e etat manquant identifie le 2026-09-25 - lu en jeu pendant que
# l'utilisateur voyait "Prudence" affiche, valeur qui suit logiquement
# Evasion avant le retour a Normal, coherent avec la sequence habituelle
# des jeux MGS). L'ecriture ne "tient" pas (le jeu la recalcule en
# continu a partir de l'etat reel de l'IA), contrairement aux champs
# VITALS ci-dessus - lecture seule.
ALERT_STATE_RVA = 0x1D77AB8
ALERT_STATE_NAMES = {0: "Normal (non repere)", 1: "Alerte", 2: "Evasion", 3: "Prudence"}
