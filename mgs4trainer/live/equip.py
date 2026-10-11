"""MGS4Live : equipement en direct : armes, tenues, visages, gilets, OctoCamo."""
import struct
import threading
import time

import mgs4save


class EquipMixin:
    """Equipement en direct : armes, tenues, visages, gilets, OctoCamo."""

    # OctoCamo (2026-10-03, voir mgs4save.OCTOCAMO_TABLE_OFFSET) : memes
    # offsets dans linkvarbuf que dans MGS4.SAV. Un motif de la table de 20
    # entrees y figure par son code (24 bits + octet de drapeaux), avec 6
    # caracteristiques (mots de 16 bits, 1000 chacune sur toutes les saves)
    # dans des tables paralleles indexees par emplacement. Seuls ces 6
    # motifs y vivent (les 14 autres sont charges par le jeu, hors save) :
    # code -> (emplacement habituel, drapeaux). Cadavre : bit 0x10 =
    # "nouveau", comme au deblocage reel.
    OCTOCAMO_STAT_TABLES = (0x4CB8, 0x4D38, 0x4DB8, 0x4E38, 0x4EB8, 0x4F38)
    OCTOCAMO_EDITABLE = {
        mgs4save.OCTOCAMO_CODES["Olive"]: (11, 0x02),
        mgs4save.OCTOCAMO_CODES["Tigré"]: (12, 0x02),
        mgs4save.OCTOCAMO_CODES["Forêt"]: (13, 0x02),
        mgs4save.OCTOCAMO_CODES["3 Couleurs Désert"]: (14, 0x02),
        mgs4save.OCTOCAMO_CODES["Marpat"]: (15, 0x02),
        mgs4save.OCTOCAMO_CODES["Cadavre"]: (16, 0x12),
    }
    OCTOCAMO_LOCKED = 65535  # meme convention que les FaceCamo/Gilets (binary_lock_value)
    # Bonus lies au compte/PC (2026-10-03) : le menu OctoCamo (mgs4+4F3789)
    # n'ajoute Dore/Precommande que si ces octets valent 1, positionnes au
    # demarrage (Precommande = possession du contenu Steam 3397310 ; Dore =
    # reglage charge au demarrage, tres probablement le bonus Master
    # Collection Vol.1 du lanceur). Lecture seule : les forcer reviendrait
    # a contourner un contenu payant. RVA de la version actuelle, sans
    # MODULE_PATCH_SHIFT.
    OCTOCAMO_ACCOUNT_FLAG_RVAS = {
        mgs4save.OCTOCAMO_CODES["Précommande"]: 0x1D7AB30,
        mgs4save.OCTOCAMO_CODES["Doré"]: 0x1D7AB31,
    }

    def read_equipped_octocamo_code(self) -> int:
        raw = self.proc.read_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_EQUIPPED_OFFSET, 4)
        return struct.unpack("<I", raw)[0] & 0xFFFFFF

    def _octocamo_table(self) -> list[int]:
        raw = self.proc.read_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_TABLE_OFFSET,
                                   4 * mgs4save.OCTOCAMO_TABLE_SLOTS)
        return list(struct.unpack(f"<{mgs4save.OCTOCAMO_TABLE_SLOTS}I", raw))

    def read_octocamo_state(self, code: int) -> int:
        """1 (obtenu) ou OCTOCAMO_LOCKED. Motifs de la partie : presence
        dans la table ; Dore/Precommande : octet du jeu (lie au compte) ;
        tous les autres sont donnes d'office par le menu du jeu."""
        if code in self.OCTOCAMO_EDITABLE:
            present = any((entry & 0xFFFFFF) == code for entry in self._octocamo_table())
            return 1 if present else self.OCTOCAMO_LOCKED
        rva = self.OCTOCAMO_ACCOUNT_FLAG_RVAS.get(code)
        if rva is not None:
            return 1 if self.proc.read_bytes(self.base + rva, 1)[0] else self.OCTOCAMO_LOCKED
        # Motifs ajoutes d'office par le menu : "verrouille" = masque par le
        # hook du trainer (install_octocamo_hide_hook), effet de session.
        return self.OCTOCAMO_LOCKED if code in self.speed.read_octocamo_hidden() else 1

    # Emplacements 0-9 de la table : motifs captures sur une surface puis
    # memorises par le joueur (categorie 1, ex. "Beton" -> 114C3A3E avec
    # ses propres caracteristiques 350/350/350/500/500/500). Les
    # emplacements 10-19 sont les motifs obtenus (categorie 2).
    OCTOCAMO_SAVED_SLOTS = range(10)

    def read_octocamo_slot_code(self, slot: int) -> int:
        return self._octocamo_table()[slot] & 0xFFFFFF

    def read_octocamo_slot_state(self, slot: int) -> int:
        return 1 if self._octocamo_table()[slot] else self.OCTOCAMO_LOCKED

    def write_octocamo_slot_state(self, slot: int, value: int) -> None:
        """Verrouille = oublie le motif memorise (vide l'emplacement et ses
        caracteristiques). Obtenu ne fait rien : un motif capture ne
        s'invente pas."""
        if value != self.OCTOCAMO_LOCKED or slot not in self.OCTOCAMO_SAVED_SLOTS:
            return
        for table_offset in self.OCTOCAMO_STAT_TABLES:
            self.proc.write_bytes(self.linkvarbuf + table_offset + slot * 2, struct.pack("<H", 0))
        self.proc.write_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_TABLE_OFFSET + slot * 4, struct.pack("<I", 0))

    # Visage porte : linkvarbuf+0xB27 = indice interne du jeu (0 = aucun),
    # +0xB26 = autre parametre de la meme fonction, repasse tel quel.
    # Indices releves en equipant chaque visage dans le menu (2026-10-03) :
    # ID d'objet -> indice. 3 n'est utilise par aucun visage du menu ;
    # 16/17 = Dore / FaceCamo Dore (bonus lies au compte, non equipables
    # depuis le trainer).
    FACECAMO_EQUIP_OFFSET = 0xB27
    FACECAMO_EQUIP_INDEX = {
        0x1F: 1,   # FaceCamo
        0x20: 2,   # Jeune Snake
        0x22: 4,   # Laughing Beauty
        0x23: 5,   # Raging Beauty
        0x24: 6,   # Crying Beauty
        0x21: 7,   # Screaming Beauty
        0x25: 8,   # Jeune Snake avec bandana
        0x28: 9,   # Big Boss
        0x27: 10,  # Campbell
        0x26: 11,  # Otacon
        0x29: 12,  # Drebin
        0x2A: 13,  # MGS1
        0x2B: 14,  # Raiden - Visiere fermee
        0x2C: 15,  # Raiden - Visiere ouverte
    }

    def read_equipped_facecamo_id(self) -> int | None:
        index = self.proc.read_bytes(self.linkvarbuf + self.FACECAMO_EQUIP_OFFSET, 1)[0]
        return next((i for i, idx in self.FACECAMO_EQUIP_INDEX.items() if idx == index), None)

    # Gilet porte : linkvarbuf+0xB3C = ID d'objet - 0x2D (Kaki 0 ... Brun 9 ;
    # 0, 1, 2 et 7 confirmes en jeu le 2026-10-03). Le jeu
    # (9004E0, appele a chaque image) repeint le gilet d'apres cet octet :
    # il suffit de l'ecrire, effet immediat. La valeur 10 (remise a 0 par
    # le jeu dans certains cas, tres probablement le gilet Dore lie au
    # compte) n'est pas proposee.
    VEST_EQUIP_OFFSET = 0xB3C
    VEST_FIRST_ID = 0x2D
    VEST_EQUIP_IDS = range(0x2D, 0x37)

    def read_equipped_vest_id(self) -> int | None:
        index = self.proc.read_bytes(self.linkvarbuf + self.VEST_EQUIP_OFFSET, 1)[0]
        item_id = self.VEST_FIRST_ID + index
        return item_id if item_id in self.VEST_EQUIP_IDS else None

    def equip_vest(self, item_id: int) -> bool:
        if not (self.connected and self.sane) or item_id not in self.VEST_EQUIP_IDS:
            return False
        self.proc.write_bytes(self.linkvarbuf + self.VEST_EQUIP_OFFSET, bytes([item_id - self.VEST_FIRST_ID]))
        return True

    # Arme en main (2026-10-03) : linkvarbuf+0xAC4 = ID de l'arme equipee
    # (u16), +0xACC = la precedente. set_weapon (6D2D0, rcx = entree de
    # l'arme dans la table du jeu, mgs4+1D82580 + ID*0x50 - meme table que
    # weapon_state_rva) ecrit les deux et marque l'arme comme changee :
    # Snake la prend en main tout de suite.
    # Seules les armes du sous-menu rapide ont leur modele charge : nombre
    # de places en +0xA9C (5), ID u16 en +0xAA4 (8 places en memoire, mais
    # le menu plante a l'affichage au-dela de 5). Equiper une arme absente
    # du sous-menu a plante le jeu (M4). On fait donc comme le menu pause :
    # jeu en pause, l'arme est placee dans une place libre du sous-menu,
    # sinon dans la DERNIERE place (choix de l'utilisateur : les autres ne
    # sont jamais touchees), preload_weapons (6D490 : compare le sous-menu
    # aux modeles charges, charge/decharge la difference), attente, puis
    # set_weapon et reprise.
    WEAPON_EQUIP_OFFSET = 0xAC4
    WEAPON_QUICK_COUNT_OFFSET = 0xA9C
    WEAPON_QUICK_IDS_OFFSET = 0xAA4
    WEAPON_TABLE_RVA = 0x1D82580
    WEAPON_TABLE_STRIDE = 0x50
    # preload_weapons est synchrone : il demande le chargement (128DB0),
    # boucle sur 129090 jusqu'a la fin puis active le modele (128BD0)
    # avant de rendre la main. Juste quelques images de marge ensuite.
    WEAPON_LOAD_WAIT = 0.1  # secondes de pause apres le chargement
    WEAPON_RELEASE_WAIT = 0.3  # secondes (jeu non fige) pour lacher l'arme en main
    WEAPON_LIVE_FUNCS = {
        "set_weapon": (0x6D2D0, "33c0488bd14885c9"),
        "preload_weapons": (0x6D490, "40554883ec20488d6c2420"),
    }

    def read_quick_weapon_ids(self) -> list[int]:
        """Sous-menu rapide des armes, places vides comprises (0)."""
        count = struct.unpack("<i", self.proc.read_bytes(self.linkvarbuf + self.WEAPON_QUICK_COUNT_OFFSET, 4))[0]
        if not 0 < count <= 8:
            return []
        raw = self.proc.read_bytes(self.linkvarbuf + self.WEAPON_QUICK_IDS_OFFSET, 2 * count)
        return list(struct.unpack(f"<{count}h", raw))

    def read_equipped_weapon_id(self) -> int:
        return struct.unpack("<H", self.proc.read_bytes(self.linkvarbuf + self.WEAPON_EQUIP_OFFSET, 2))[0]

    def read_equippable_weapon_ids(self) -> list[int]:
        """Armes possedees (etat 1 ou 2 du tableau d'etat) : equipables,
        quitte a passer par la derniere place du sous-menu."""
        return [i for i in range(1, mgs4save.WEAPON_STATE_COUNT) if self.read_weapon(i) in (1, 2)]

    def equip_weapon(self, weapon_id: int) -> bool:
        if not (self.connected and self.sane) or weapon_id not in self.read_equippable_weapon_ids():
            return False
        return self._start_equip(self._equip_weapon_live, weapon_id)

    def _equip_weapon_live(self, weapon_id: int) -> bool:
        funcs = self._live_funcs(self.WEAPON_LIVE_FUNCS)
        model_funcs = self._live_funcs(self.MODEL_LIVE_FUNCS)
        quick = self.read_quick_weapon_ids()
        if funcs is None or model_funcs is None or not quick:
            return False
        call = self.speed.game_call
        entry = self.base + self.WEAPON_TABLE_RVA + weapon_id * self.WEAPON_TABLE_STRIDE
        if weapon_id in quick:
            return call(funcs["set_weapon"], entry) is not None
        slot = quick.index(0) if 0 in quick else len(quick) - 1
        # L'arme remplacee est en main : preload_weapons dechargerait le
        # modele tenu et le jeu plante (vu 2 fois le 2026-10-03, y compris
        # en passant d'abord a "aucune arme" jeu en pause : le modele en
        # main ne change qu'a la mise a jour de Snake, figee par la pause).
        # On passe donc d'abord a "aucune arme" jeu NON fige, et on laisse
        # quelques images a Snake pour lacher l'arme.
        if quick[slot] and quick[slot] == self.read_equipped_weapon_id():
            if call(funcs["set_weapon"], self.base + self.WEAPON_TABLE_RVA) is None:
                return False
            time.sleep(self.WEAPON_RELEASE_WAIT)
        state = call(model_funcs["state"])
        if state is None:
            return False
        pause = not (state & 6)
        if pause:
            call(model_funcs["pause_set"], self.MODEL_PAUSE_FLAG)
        try:
            self.proc.write_bytes(self.linkvarbuf + self.WEAPON_QUICK_IDS_OFFSET + 2 * slot,
                                  struct.pack("<h", weapon_id))
            if call(funcs["preload_weapons"], timeout=10.0) is None:
                return False
            time.sleep(self.WEAPON_LOAD_WAIT)
            ok = call(funcs["set_weapon"], entry) is not None
            time.sleep(0.1)
            return ok
        finally:
            if pause:
                call(model_funcs["pause_clear"], self.MODEL_PAUSE_FLAG)

    # Tenue (linkvarbuf+0xB26) et visage (+0xB27) en direct, sans menu
    # (2026-10-03). Les deux passent par la meme fonction du jeu,
    # equip_model (8FCC70, ecx = tenue, edx = visage), appelee par le menu
    # (4F6BF0) : elle n'agit que jeu en pause et lance le rechargement du
    # modele ([gestionnaire+0x108] = 2, decompte par image jusqu'a -1, puis
    # chargement suivi par les bits 0-1 de [gestionnaire+0xC0]). Si Snake
    # est mis a jour pendant ce rechargement, le jeu plante : on met donc
    # le jeu en pause avec sa propre fonction (pause_set(2), comme le menu
    # mais sans l'afficher), on equipe, on attend la fin du rechargement
    # (~0,1-0,2 s) puis pause_clear(2). Si un menu est deja ouvert, on n'y
    # touche pas. Comme le menu, le visage passe a 0 si la tenue ne
    # l'autorise pas (8FCEF0(motif, tenue, visage) == 0, ex. Altair).
    MODEL_MANAGER_PTR_RVA = 0x23EB5F58
    MODEL_LIVE_FUNCS = {
        "state": (0x73FDC0, "8b05????????c3"),
        "pause_set": (0x73FE60, "4883ec288b05????????8bd183e220"),
        "pause_clear": (0x73FDD0, "4883ec28448b0d????????4485c9"),
        "equip": (0x8FCC70, "40535741554883ec204c8b2d"),
        "face_allowed": (0x8FCEF0, "4883ec48488b05"),
    }
    MODEL_PAUSE_FLAG = 2
    OUTFIT_EQUIP_OFFSET = 0xB26
    # ID d'objet -> valeur de B26, verifies en jeu (2026-10-03). 0 =
    # combinaison OctoCamo (sans objet). Le menu ne propose les deguisements
    # de rebelle et de civil que dans leur acte, mais les forcer ailleurs
    # fonctionne (teste hors de leur acte).
    OUTFIT_EQUIP_INDEX = {
        0x1A: 1,  # Deguisement de milicien du Moyen-Orient
        0x1B: 2,  # Deguisement de rebelle d'Amerique du Sud
        0x1C: 3,  # Deguisement civil de l'Europe de l'Est
        0x1E: 4,  # Costume de Snake
        0x1D: 7,  # Costume d'Altair
    }

    def _live_funcs(self, table: dict[str, tuple[int, str]]) -> dict[str, int] | None:
        """Adresses des fonctions du jeu de la table, ou None si l'une
        n'a pas les octets attendus (autre version du jeu)."""
        funcs = {}
        for name, (rva, signature) in table.items():
            expected = signature.replace("??", "..")
            actual = self.proc.read_bytes(self.base + rva, len(signature) // 2).hex()
            if not all(e == "." or e == a for e, a in zip(expected, actual)):
                return None
            funcs[name] = self.base + rva
        return funcs

    def _start_equip(self, action, *args) -> bool:
        """Lance action(*args) dans un fil separe (les appels au jeu se
        font une image a la fois). Un seul equipement en direct a la fois."""
        if not (self.connected and self.sane and self.pid and self.speed.ensure_injected(self.pid)):
            return False
        if not self._equip_lock.acquire(blocking=False):
            return False
        threading.Thread(target=self._equip_worker, args=(action, *args), daemon=True).start()
        return True

    def _equip_worker(self, action, *args) -> None:
        try:
            action(*args)
        except OSError:
            pass
        finally:
            self._equip_lock.release()

    def read_equipped_outfit_id(self) -> int | None:
        index = self.proc.read_bytes(self.linkvarbuf + self.OUTFIT_EQUIP_OFFSET, 1)[0]
        return next((i for i, idx in self.OUTFIT_EQUIP_INDEX.items() if idx == index), None)

    def equip_outfit(self, item_id: int) -> bool:
        if item_id not in self.OUTFIT_EQUIP_INDEX:
            return False
        return self._start_equip(self._equip_model_live, self.OUTFIT_EQUIP_INDEX[item_id], None)

    def equip_facecamo(self, item_id: int | None) -> bool:
        """Lance le changement de visage en direct (None = aucun)."""
        if item_id is not None and item_id not in self.FACECAMO_EQUIP_INDEX:
            return False
        index = 0 if item_id is None else self.FACECAMO_EQUIP_INDEX[item_id]
        return self._start_equip(self._equip_model_live, None, index)

    def _equip_model_live(self, outfit: int | None, face: int | None) -> bool:
        """Tenue et/ou visage (None = garder l'actuel)."""
        funcs = self._live_funcs(self.MODEL_LIVE_FUNCS)
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.MODEL_MANAGER_PTR_RVA, 8))[0]
        if funcs is None or not manager:
            return False
        # Pas de controleur de jeu = cinematique : recharger le modele du
        # Snake de cinematique fait planter le jeu (constate le 2026-10-03).
        if not self._octocamo_controller():
            return False
        current_outfit, current_face = self.proc.read_bytes(self.linkvarbuf + self.OUTFIT_EQUIP_OFFSET, 2)
        outfit = current_outfit if outfit is None else outfit
        face = current_face if face is None else face
        if (outfit, face) == (current_outfit, current_face):
            return True
        call = self.speed.game_call
        state = call(funcs["state"])
        if state is None:
            return False
        pause = not (state & 6)
        if pause:
            call(funcs["pause_set"], self.MODEL_PAUSE_FLAG)
        try:
            pattern = struct.unpack("<I", self.proc.read_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_EQUIPPED_OFFSET, 4))[0]
            if face and not (call(funcs["face_allowed"], pattern, outfit, face) or 0) & 0xFFFFFFFF:
                face = 0
            if (call(funcs["equip"], outfit, face) or 0) & 0xFFFFFFFF != 0:
                return False
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                countdown = struct.unpack("<i", self.proc.read_bytes(manager + 0x108, 4))[0]
                loading = self.proc.read_bytes(manager + 0xC0, 1)[0] & 3
                if countdown <= 0 and not loading:
                    break
                time.sleep(0.02)
            time.sleep(0.1)  # quelques images de marge
            return True
        finally:
            if pause:
                call(funcs["pause_clear"], self.MODEL_PAUSE_FLAG)

    # Motif OctoCamo en direct, sans menu (2026-10-03) : on pilote le
    # controleur d'auto-camouflage du joueur (celui qui change la
    # combinaison contre un mur), pointe par OCTOCAMO_CONTROLLER_PTR_RVA.
    # Il tient un "enregistrement" de motif de 0x12D0 octets pour le motif
    # porte (+0xA0) et un pour le motif en attente (+0x1370) : code a +0,
    # 6 teintes en flottants (= les 6 tables de caracteristiques / 1000,
    # 3 couleurs puis 3 autres ; 0 = combinaison noire) a OCTOCAMO_TINT_OFFSETS,
    # drapeaux a +0x10D8 (recopies chaque image dans linkvarbuf+0xB38, B28
    # recevant le code). Drapeau 0x1000 = motif force (Olive, Cadavre,
    # speciaux...) : le controleur ne le remplace plus au contact d'un mur.
    # Etat +0x98 (0 aucun, 1 apparition, 2 stable, 3 disparition, 4
    # transition) et fondu +0x9C (0..1) ; la combinaison n'est redessinee
    # que si le fondu varie dans l'image ou si le bit 1 de +0x39A8 est mis.
    # Sequence (fonctions du jeu appelees dans son fil, via game_call) :
    # demande de chargement de la texture, attente qu'elle soit prete,
    # bascule du double tampon de textures, construction de
    # l'enregistrement en attente, teintes, copie vers le motif porte puis
    # apparition en fondu (motif auto) ou redessin direct (motif force).
    OCTOCAMO_CONTROLLER_PTR_RVA = 0x23EB5F50
    OCTOCAMO_LIVE_FUNCS = {
        # nom : (RVA, premiers octets attendus) - verifies avant tout appel.
        "load": (0xA1060, "405356574883ec40488b1d"),
        "ready": (0xA0240, "488b05????????4885c07506"),
        "flip": (0xA15F0, "48895c24084889742410574883ec20"),
        "build": (0x9FC10, "4055574881ecb80100008bea488bf9"),
        "memcpy": (0xD25800, "ff25"),
        "memset": (0x7513C0, "4c8bc233d2e9"),
        "apply_pattern": (0xA0E70, "48895c2408574883ec20498bf9"),
        "apply_fade": (0xA0ED0, "40534883ec300f297424200f28f3"),
        "cutscene_update": (0xE80960, "40564883ec50f30f1081b8000000"),
    }
    # En cinematique (2026-10-04), le controleur de jeu n'existe pas
    # (pointeur nul) : le Snake de cinematique a sa propre tache de
    # camouflage, creee au debut de la sequence a partir de B28. Taches
    # chainees dans une liste circulaire (sentinelle mgs4+3B49340 ; noeud :
    # +0 suivant, +8 fonction de mise a jour, +0x20 precedent) ; la notre
    # se reconnait a sa fonction de mise a jour (E80960). Objet : +0xA0
    # modele du corps, +0xA8 modele du visage, +0xF4 fondu, +0xF8 minuteur
    # de fondu (le clic du stick gauche le lance vers 0, motifs auto
    # seulement), enregistrement de motif a +0x100 (meme format que le
    # controleur). Le rendu ne relit pas l'enregistrement : il faut
    # appliquer le motif aux modeles (apply_pattern, A0E70) puis le fondu
    # (apply_fade, A0ED0, flottant en 4e argument - xmm3).
    CUTSCENE_TASK_LIST_RVA = 0x3B49340
    CUTSCENE_TASK_MAX = 2000
    OCTOCAMO_RECORD_SIZE = 0x12D0
    OCTOCAMO_TINT_OFFSETS = (0x1248, 0x124C, 0x1250, 0x1258, 0x125C, 0x1260)
    OCTOCAMO_FLAG_FORCED = 0x1000
    OCTOCAMO_FLAG_OWN_TINTS = 0x1

    def _octocamo_tints(self, code: int) -> list[int]:
        """Teintes du motif : celles de la table de la partie s'il y est
        (motifs obtenus ou memorises), sinon neutres (1000)."""
        for slot, entry in enumerate(self._octocamo_table()):
            if entry and (entry & 0xFFFFFF) == code:
                return [struct.unpack("<H", self.proc.read_bytes(self.linkvarbuf + table + slot * 2, 2))[0]
                        for table in self.OCTOCAMO_STAT_TABLES]
        return [1000] * 6

    def equip_octocamo(self, code: int) -> bool:
        """Lance le changement de motif en direct (fil separe, ~0,1-0,5 s
        le temps que la texture charge). Faux si refuse d'emblee."""
        if not (self.connected and self.sane):
            return False
        # Dore/Precommande : seulement si le jeu les a debloques (contenu lie
        # au compte - ne pas le contourner).
        rva = self.OCTOCAMO_ACCOUNT_FLAG_RVAS.get(code)
        if rva is not None and not self.proc.read_bytes(self.base + rva, 1)[0]:
            return False
        return self._start_equip(self._equip_octocamo_live, code)

    def _equip_octocamo_live(self, code: int) -> bool:
        # Autre tenue portee : le controleur se remet a zero a chaque image
        # (linkvarbuf+0xB26 != 0) - on remet d'abord la combinaison OctoCamo.
        if self.proc.read_bytes(self.linkvarbuf + self.OUTFIT_EQUIP_OFFSET, 1)[0]:
            if not self._equip_model_live(0, None):
                return False
        funcs = self._live_funcs(self.OCTOCAMO_LIVE_FUNCS)
        if funcs is None:
            return False
        ctrl = self._octocamo_controller()
        if not ctrl:
            return self._equip_octocamo_cutscene(funcs, code)
        call = self.speed.game_call
        current, pending = ctrl + 0xA0, ctrl + 0x1370
        if code == 0:
            # Infiltration : aucun motif.
            if call(funcs["memset"], current, self.OCTOCAMO_RECORD_SIZE) is None:
                return False
            self._octocamo_show(ctrl, forced=True, fade_value=0.0, state=0)
            return True
        if not self._octocamo_build(funcs, pending, code):
            return False
        call(funcs["memcpy"], current, pending, self.OCTOCAMO_RECORD_SIZE)
        call(funcs["memset"], pending, self.OCTOCAMO_RECORD_SIZE)
        flags = struct.unpack("<I", self.proc.read_bytes(current + 0x10D8, 4))[0]
        if flags & self.OCTOCAMO_FLAG_FORCED:
            self._octocamo_show(ctrl, forced=True, fade_value=1.0, state=2)
        else:
            self._octocamo_show(ctrl, forced=False, fade_value=0.0, state=1)
        return True

    def _octocamo_controller(self) -> int:
        """Controleur d'auto-camouflage du jeu, 0 en cinematique."""
        return struct.unpack("<Q", self.proc.read_bytes(self.base + self.OCTOCAMO_CONTROLLER_PTR_RVA, 8))[0]

    def _cutscene_camo_task(self, update_fn: int) -> int:
        """Tache de camouflage du Snake de cinematique, 0 si absente."""
        sentinel = self.base + self.CUTSCENE_TASK_LIST_RVA
        node = struct.unpack("<Q", self.proc.read_bytes(sentinel, 8))[0]
        for _ in range(self.CUTSCENE_TASK_MAX):
            if not node or node == sentinel:
                return 0
            head = self.proc.read_bytes(node, 16)
            if struct.unpack_from("<Q", head, 8)[0] == update_fn:
                return node
            node = struct.unpack_from("<Q", head, 0)[0]
        return 0

    def _equip_octocamo_cutscene(self, funcs: dict[str, int], code: int) -> bool:
        task = self._cutscene_camo_task(funcs["cutscene_update"])
        if not task:
            return False
        call = self.speed.game_call
        record = task + 0x100
        body, face = struct.unpack("<QQ", self.proc.read_bytes(task + 0xA0, 16))
        if code == 0:
            if call(funcs["memset"], record, self.OCTOCAMO_RECORD_SIZE) is None:
                return False
            fade = 0.0
        else:
            if not self._octocamo_build(funcs, record, code):
                return False
            if call(funcs["apply_pattern"], body, face, 0, record) is None:
                return False
            fade = 1.0
        self.proc.write_bytes(task + 0xF4, struct.pack("<f", fade))
        self.proc.write_bytes(task + 0xF8, struct.pack("<f", 0.0))
        fade_bits = struct.unpack("<I", struct.pack("<f", fade))[0]
        if call(funcs["apply_fade"], body, face, 0, fade_bits) is None:
            return False
        # Meme motif dans la partie : repris par la cinematique suivante et
        # par le controleur de jeu au retour en jeu (8FACA0 lit B28).
        tints = [round(struct.unpack("<f", self.proc.read_bytes(record + o, 4))[0] * 1000)
                 for o in self.OCTOCAMO_TINT_OFFSETS]
        flags = struct.unpack("<I", self.proc.read_bytes(record + 0x10D8, 4))[0]
        self.proc.write_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_EQUIPPED_OFFSET,
                              struct.pack("<I6HI", code, *[max(0, min(t, 0xFFFF)) for t in tints], flags))
        return True

    def _octocamo_build(self, funcs: dict[str, int], record: int, code: int) -> bool:
        """Charge la texture du motif et construit l'enregistrement (teintes
        comprises) a l'adresse record."""
        call = self.speed.game_call
        if call(funcs["load"], code) is None:
            return False
        deadline = time.monotonic() + 5.0
        while (call(funcs["ready"], code) or 0) & 0xFFFFFFFF != 1:
            if time.monotonic() > deadline:
                return False
            time.sleep(0.05)
        call(funcs["flip"], code)
        if (call(funcs["build"], record, code) or 0) & 0xFFFFFFFF != 1:
            return False
        # Bit 0 des drapeaux (+0x10D8) : le motif a ses propres teintes, que la
        # construction recopie deja (+0x18.. -> +0x1248.., A1890/9FFD0) -
        # Cadavre, motifs speciaux. Les ecraser par celles de la table (1000
        # pour Cadavre) donnait un rendu delave (2026-10-11).
        flags = struct.unpack("<I", self.proc.read_bytes(record + 0x10D8, 4))[0]
        if not flags & self.OCTOCAMO_FLAG_OWN_TINTS:
            for offset, tint in zip(self.OCTOCAMO_TINT_OFFSETS, self._octocamo_tints(code)):
                self.proc.write_bytes(record + offset, struct.pack("<f", tint / 1000))
        return True

    def _octocamo_show(self, ctrl: int, forced: bool, fade_value: float, state: int) -> None:
        self.proc.write_bytes(ctrl + 0x9C, struct.pack("<f", fade_value))
        self.proc.write_bytes(ctrl + 0x98, struct.pack("<I", state))
        if forced:
            redraw = self.proc.read_bytes(ctrl + 0x39A8, 1)[0] | 1
            self.proc.write_bytes(ctrl + 0x39A8, bytes([redraw]))

    def equip_octocamo_slot(self, slot: int) -> bool:
        code = self.read_octocamo_slot_code(slot)
        return self.equip_octocamo(code) if code else False

    def write_octocamo_state(self, code: int, value: int) -> None:
        unlocked = value != self.OCTOCAMO_LOCKED
        if code not in self.OCTOCAMO_EDITABLE:
            # Motif ajoute d'office par le menu : masque/demasque via le
            # hook (injecte la DLL au besoin, comme les autres reglages).
            # Jamais pour Dore/Precommande (lignes en lecture seule).
            if code in self.OCTOCAMO_ACCOUNT_FLAG_RVAS or code == 0:
                return
            if not (self.connected and self.sane and self.pid and self.speed.ensure_injected(self.pid)):
                return
            hidden = [c for c in self.speed.read_octocamo_hidden() if c != code]
            if not unlocked:
                hidden.append(code)
            self.speed.write_octocamo_hidden(hidden)
            return
        table = self._octocamo_table()
        slots = [i for i, entry in enumerate(table) if (entry & 0xFFFFFF) == code]
        if unlocked:
            if slots or code not in self.OCTOCAMO_EDITABLE:
                return
            free = [i for i, entry in enumerate(table) if entry == 0]
            if not free:
                return
            usual_slot, flags = self.OCTOCAMO_EDITABLE[code]
            slot = usual_slot if usual_slot in free else free[0]
            entry, stat = (flags << 24) | code, 1000
            targets = [slot]
        else:
            entry, stat = 0, 0
            targets = slots
        for slot in targets:
            for table_offset in self.OCTOCAMO_STAT_TABLES:
                self.proc.write_bytes(self.linkvarbuf + table_offset + slot * 2, struct.pack("<H", stat))
            self.proc.write_bytes(self.linkvarbuf + mgs4save.OCTOCAMO_TABLE_OFFSET + slot * 4,
                                  struct.pack("<I", entry))
