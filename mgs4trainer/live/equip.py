"""MGS4Live : equipement en direct : armes, tenues, visages, gilets, OctoCamo."""
import struct
import threading
import time

import mgs4save
from mgs4trainer.live.spawn import PAGE_READWRITE


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

    def _model_fail(self, reason: str) -> bool:
        """Echec d'un changement de modele, note dans le journal (l'action
        tourne dans un fil, rien ne remonte a l'interface)."""
        self._equip_log(f"modele : echec ({reason})")
        self.equip_error = reason
        return False

    @staticmethod
    def _equip_log(text: str) -> None:
        import os
        try:
            with open(os.path.join(os.environ.get("TEMP", "."), "mgs4trainer_equip.log"), "a", encoding="utf-8") as log:
                log.write(time.strftime("%H:%M:%S ") + text + "\n")
        except OSError:
            pass

    # Raison du dernier echec d'un equipement en direct (None = reussi),
    # lue par l'interface une fois le fil termine.
    equip_error = None

    def _equip_worker(self, action, *args) -> None:
        self.equip_error = None
        try:
            result = action(*args)
            if result is False:
                self._equip_log(f"{getattr(action, '__name__', action)} : False")
        except OSError as error:
            self.equip_error = repr(error)
            self._equip_log(f"{getattr(action, '__name__', action)} : {error!r}")
        except AttributeError:
            # jeu ferme pendant l'operation : detach() a vide self.proc
            if self.proc is not None:
                import traceback
                self._equip_log(traceback.format_exc())
                raise
        except Exception as error:
            import traceback
            self.equip_error = repr(error)
            self._equip_log(traceback.format_exc())
            raise
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
                self._model_pause_clear(funcs)

    # Corps et visage de Snake (2026-11-14, valide en 1.4.2 : corps du
    # deguisement de milicien sur la combinaison). Le gestionnaire de modele
    # charge le corps et le visage dans deux slots (+0xB0/+0xB8) d'apres une
    # variante : table +0x90 (nombre +0x98) pour le corps, +0xA0 (+0xA8)
    # pour le visage, entrees de 12 octets (variante, paquet ww/stage/slot,
    # pages). La variante voulue vient de la fonction pointee par +0xE0
    # (corps) / +0xE8 (visage) (sinon 62E680 / 62E970 en 1.4.2, d'apres
    # linkvarbuf+0xB26/B27) ; la tache de rechargement 62F730 ne charge que
    # si elle differe de la variante chargee (+0xC4 / +0xC8), au bout du
    # decompte +0x108. Variante imposee = petite fonction "mov eax, N ;
    # ret" a la place du pointeur ; None = pointeur d'origine.
    MODEL_VARIANT_TABLES = {"body": (0x90, 0x98, 0xE0), "face": (0xA0, 0xA8, 0xE8)}
    # Fonctions du jeu pointees d'origine par +0xE0 / +0xE8 (1.4.2 62E710 /
    # 62EA60) : remises si le pointeur est encore une de nos fonctions (trainer
    # ferme sans "Automatique" : sinon on les prendrait pour celles du jeu).
    MODEL_DEFAULT_PICKERS = {"body": 0x8F9940, "face": 0x8F9C90}
    MODEL_RELOAD_COUNTDOWN = 0x108
    MODEL_RELOAD_LOADING = 0xC0

    def model_variants(self, part: str) -> list[tuple[int, int]]:
        """[(variante, paquet)] de la table du corps ou du visage."""
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.MODEL_MANAGER_PTR_RVA, 8))[0]
        if not manager:
            return []
        table_offset, count_offset, _pick = self.MODEL_VARIANT_TABLES[part]
        count = struct.unpack("<i", self.proc.read_bytes(manager + count_offset, 4))[0]
        table = struct.unpack("<Q", self.proc.read_bytes(manager + table_offset, 8))[0]
        if not table or not 0 < count < 64:
            return []
        raw = self.proc.read_bytes(table, count * 12)
        return [struct.unpack_from("<II", raw, i * 12) for i in range(count)]

    # Compatibilite corps / visage (2026-11-14) : un visage accroche ses
    # pieces a des points du corps (fichiers eqpp du paquet du visage ->
    # identifiants du cnp du corps : nombre +8, entrees de 0x40 a +0x10,
    # identifiant en +0, grand-boutiste). Point absent = 95F1F0 renvoie nul,
    # plantage en 5D1B6F (corps 4 + visage de la combinaison). Visage
    # associe par le jeu a chaque corps de tenue (62E970, sans FaceCamo).
    MODEL_PAIRED_FACE = {1: 4, 2: 5, 3: 6, 4: 7, 5: 0x12, 0xB: 4}
    # eqpp reclames au visage : l'equipement de la TENUE PORTEE (B26) cherche
    # par 5CD3E0 les eqpp de son visage naturel (combinaison : visage 0,
    # 0x8F595F et 0xBEB70) ; absent = nul, plantage en 47AE97 (2026-11-14 :
    # visage 4 sans eqpp ; costume + visage 2, r14 = 0xBEB70). Le visage
    # choisi doit donc fournir les eqpp du visage naturel (charge quand rien
    # n'est impose, memorise par model_natural_face).

    def _model_attach_points(self) -> dict | None:
        """{"body": {variante: points}, "face": {variante: points demandes}}."""
        cache = getattr(self, "_model_attach_cache", None)
        if cache and cache[0] == self.pid:
            return cache[1]
        from mgs4trainer.core.vpak import StageFiles
        root = self._spawn_game_root()
        if not root:
            return None
        files = getattr(self, "_spawn_files", None) or StageFiles(root)
        self._spawn_files = files

        def pack_files(pack: int):
            marker = f"/slot/{pack:08x}/"
            return [(p.rsplit("/", 1)[-1], p) for p in files.entries if marker in p]

        bodies, faces = self.model_variants("body"), self.model_variants("face")
        body_points = {}
        for variant, pack in bodies:
            points = set()
            for name, path in pack_files(pack):
                if name.endswith(".cnp"):
                    data = files.read(path)
                    count = min(struct.unpack_from(">I", data, 8)[0], (len(data) - 0x10) // 0x40)
                    points |= {struct.unpack_from(">I", data, 0x10 + 0x40 * i)[0] for i in range(count)}
            body_points[variant] = points
        # identifiants d'attache sur 24 bits ; le paquet commun 0x1 (corps 3)
        # apporte des valeurs parasites (0x1000000 -> Otacon et Raiden grises)
        known = {i for i in set().union(*body_points.values()) if 0 < i < 0x1000000} if body_points else set()
        face_needs, face_eqpp = {}, {}
        for variant, pack in faces:
            needs, eqpp = set(), set()
            for name, path in pack_files(pack):
                if name.endswith(".eqpp"):
                    eqpp.add(int(name[:8], 16))
                    data = files.read(path)
                    needs |= {struct.unpack_from(">I", data, o)[0] for o in range(0, len(data) - 3, 4)} & known
            face_needs[variant], face_eqpp[variant] = needs, eqpp
        result = {"body": body_points, "face": face_needs, "face_eqpp": face_eqpp}
        self._model_attach_cache = (self.pid, result)
        return result

    # Visage -> FaceCamo porte (linkvarbuf+0xB27) qui le donne (62E970, 1.4.2).
    # Ces visages passent par l'equipement normal du FaceCamo : les eqpp
    # reclames suivent alors ce visage (OctoCamo + Big Boss, comme le menu).
    MODEL_FACECAMO_INDEX = {0x2: 1, 0x3: 2, 0xA: 4, 0xB: 5, 0xC: 6, 0xD: 7, 0x11: 8, 0x14: 9,
                            0x15: 10, 0x16: 11, 0x17: 12, 0x18: 13, 0x19: 14, 0x1C: 15}

    def model_face_compatible(self, body: int, face: int, natural: int | None = -1) -> bool:
        """natural : visage naturel deja lu (-1 = le lire)."""
        points = self._model_attach_points()
        if not points or body not in points["body"] or face not in points["face"]:
            return False
        if face in self.MODEL_FACECAMO_INDEX:
            return points["face"][face] <= points["body"][body]
        if natural == -1:
            natural = self.model_natural_face()
        # inconnu (trainer relance avec un visage impose) : visage de la combinaison
        required = points["face_eqpp"].get(0 if natural is None else natural, set())
        if not required <= points["face_eqpp"][face]:
            return False
        return points["face"][face] <= points["body"][body]

    # Corps d'un autre personnage (ESSAI 2026-11-14) : geometrie d'un modele
    # de la zone (ex. PMC 0x313917 en s01a57l) sur le squelette du corps de
    # Snake (mgs4trainer.core.mdn.build_hybrid), convertie par le jeu sous une
    # cle de rechange puis branchee dans le noeud du dictionnaire du mdn du
    # corps (+0x14 taille, +0x20 donnees) ; Snake reconstruit son modele au
    # message 0x1E0002 (envoye par la tache de rechargement 62F730 aux
    # joueurs : table des joueurs, objet en +0, puis 4 objets a +0x110).
    # Le cnp et le rdv de Snake restent (points d'attache).
    MODEL_REBUILD_MESSAGE = 0x1E0002
    MODEL_PLAYER_SLOTS = 0x18
    MODEL_EXTRA_RECEIVERS = (0x110, 4)
    MODEL_SWAP_XOR = 0xA5A5A5
    # Tete masquee (ESSAI 2026-11-15) : la plupart des modeles des PNJ ont
    # leur tete (137 du catalogue sur 187 animent des os du visage), celle de
    # Snake est a part (paquet du visage : 0x03A157, bandana, Solid Eye). Copie
    # de chaque mdn du paquet aux triangles aplatis (core/mdn.hidden),
    # branchee comme le corps hybride.
    MODEL_HIDE_XOR = 0x3C3C3C
    MODEL_REAL_XOR = 0x5A5A5A  # cle de rechange du vrai corps rendu
    # Table de 0x1421 places de 0x70 (allocateur 677C80, 1.4.2 4D1060) :
    # chaque texture enregistree en prend une ; table pleine = indice -1 et
    # ecriture avant la table (plantage 4D1122 en s01a05l, 2026-11-15 : 0
    # place libre dans cette zone avant tout ajout). Place libre : qword +8
    # nul et mot +0x34 = 0xFFFF. Nombre de textures d'un txn : u32 BE en +8.
    MODEL_TEXTURE_TABLE_RVA = 0x23BE75F0
    MODEL_TEXTURE_SLOTS = 0x1421
    MODEL_TEXTURE_ENTRY = 0x70

    def model_swap_textures(self, source: int) -> tuple[int, int] | None:
        """(textures a ajouter pour ce modele, places libres), None si inconnu."""
        location = self.read_location()
        found = self._model_swap_source(source, location[0]) if location else None
        if found is None:
            return None
        present = {key & 0x7FFFFFFF for key in self._spawn_resource_nodes()}
        files = self._model_files()
        needed = sum(struct.unpack_from(">I", files.read(path), 8)[0]
                     for key, path in found[2] if key not in present)
        return needed, self._model_texture_free()

    # Memoire des textures ajoutees (2026-11-17) : un txn enregistre pese ses
    # pixels HD ; certains modeles n'ont leurs textures que dans le txn de
    # toute leur zone d'origine (0x341738f : 177 Mo). Rien n'est libere avant
    # le prochain chargement : 1 Go ajoute en s01a57l, menu pause degrade.
    MODEL_TEXTURE_BUDGET = 300 * 2 ** 20

    def model_added_textures(self) -> int:
        """Octets de textures (txn) presents dans la zone sans faire partie de
        sa liste : ceux des modeles appliques."""
        location = self.read_location()
        if location is None:
            return 0
        here = {key & 0x7FFFFFFF for key, _path in self._model_files().zone_resources(location[0])}
        total = 0
        for key, node in self._spawn_resource_nodes().items():
            if (key >> 24) & 0x7F == 0x03 and (key & 0x7FFFFFFF) not in here:
                total += struct.unpack("<I", self.proc.read_bytes(node + 0x14, 4))[0]
        return total

    def _model_texture_free(self) -> int:
        table = self.base + self.MODEL_TEXTURE_TABLE_RVA
        data = self.proc.read_bytes(table, self.MODEL_TEXTURE_SLOTS * self.MODEL_TEXTURE_ENTRY)
        return sum(1 for i in range(1, self.MODEL_TEXTURE_SLOTS)
                   if not struct.unpack_from("<Q", data, i * self.MODEL_TEXTURE_ENTRY + 8)[0]
                   and struct.unpack_from("<H", data, i * self.MODEL_TEXTURE_ENTRY + 0x34)[0] == 0xFFFF)
    MODEL_SWAP_SETTLE = 1.0  # s laissees a Snake pour se reconstruire (hors pause)

    def _model_body_skeleton(self) -> tuple[int, bytes] | None:
        """(identifiant, fichier mdn) du corps charge, lu dans son paquet."""
        loaded = self.model_loaded_variants()
        if loaded is None:
            return None
        pack = dict(self.model_variants("body")).get(loaded[0])
        if pack is None:
            return None
        files = self._model_files()
        marker = f"/slot/{pack:08x}/cache/"
        names = {p.rsplit("/", 1)[-1]: p for p in files.entries if marker in p}
        for name, path in names.items():
            if name.endswith(".mdn") and name[:8] + ".cnp" in names:
                return int(name[:8], 16), files.read(path)
        return None

    def _model_files(self):
        from mgs4trainer.core.vpak import StageFiles
        if getattr(self, "_spawn_files", None) is None:
            self._spawn_files = StageFiles(self._spawn_game_root())
        return self._spawn_files

    def model_swap_candidates(self) -> list[int]:
        """Modeles de la zone dont le squelette est contenu dans celui du corps."""
        from mgs4trainer.core import mdn
        location = self.read_location()
        skeleton = self._model_body_skeleton()
        if location is None or skeleton is None:
            return []
        files = self._model_files()
        out = []
        for key, path in files.zone_resources(location[0]):
            if key >> 24 != 0x0D or (key & 0xFFFFFF) == skeleton[0]:
                continue
            try:
                data = files.read(path)
                if mdn.MdnHeader(data).bone_count >= 20 and mdn.skeleton_compatible(data, skeleton[1]):
                    out.append(key & 0xFFFFFF)
            except (ValueError, struct.error, IndexError):
                continue
        return out

    # Modeles d'autres zones (ESSAI 2026-11-15) : catalogue genere par
    # tools/build_model_catalog.py (zone d'origine, txn decrivant ses
    # textures). Comme pour l'apparition d'ennemis, les txn et le modele sont
    # enregistres sous le nom de leur zone : le jeu en deduit le dossier des
    # textures HD (sous un autre nom : modele noir).
    def model_swap_catalog(self) -> dict[int, tuple[str, int, tuple[int, ...], tuple[int, ...], tuple[int, ...]]]:
        """identifiant -> (zone, os, txn, pieces liees, couches automatiques)."""
        from mgs4trainer.core.model_catalog import MODELS
        return MODELS

    def _model_swap_source(self, source: int, zone: str):
        """(zone d'enregistrement, chemin du mdn, [(cle, chemin) des txn
        a enregistrer]) ; zone courante d'abord, sinon le catalogue."""
        files = self._model_files()
        resources = files.zone_resources(zone)
        path = next((p for k, p in resources if k == 0x0D000000 | source), None)
        entry = self.model_swap_catalog().get(source)
        if path is not None:
            # txn du catalogue quand meme (pieces liees) : seuls les absents
            # du dictionnaire sont enregistres
            here = dict(resources)
            return zone, path, [(t, here[t]) for t in (entry[2] if entry else ()) if t in here]
        if entry is None:
            # couche d'une autre zone hors catalogue (couteaux de Mantis)
            from mgs4trainer.core.model_catalog import LAYER_SOURCES
            if source not in LAYER_SOURCES:
                return None
            entry = (LAYER_SOURCES[source][0], 0, LAYER_SOURCES[source][1])
        other, txns = entry[0], entry[2]
        resources = files.zone_resources(other)
        paths = dict(resources)
        path = paths.get(0x0D000000 | source)
        if path is None or any(t not in paths for t in txns):
            return None
        return other, path, [(t, paths[t]) for t in txns]

    def model_linked_pieces(self, source: int) -> list[int]:
        """Pieces liees que le catalogue fusionne au modele (manteau, queue de cheval)."""
        entry = self.model_swap_catalog().get(source)
        return list(entry[3]) if entry else []

    def model_auto_layers(self, source: int) -> list[int]:
        """Couches que le catalogue associe au modele (cheveux, foulard)."""
        entry = self.model_swap_catalog().get(source)
        return list(entry[4]) if entry else []

    def _model_layer_source(self, layer: int, owner: int):
        """Couche absente du catalogue (petits modeles : cheveux) : prise dans
        la zone du modele qu'elle accompagne, avec les txn de celui-ci."""
        entry = self.model_swap_catalog().get(owner)
        if entry is None:
            return None
        resources = dict(self._model_files().zone_resources(entry[0]))
        path = resources.get(0x0D000000 | layer)
        if path is None:
            return None
        return entry[0], path, [(t, resources[t]) for t in entry[2] if t in resources]

    def _model_source_data(self, source: int, path: str, zone: str, pieces=None) -> bytes:
        """Le mdn du modele, avec ses pieces liees fusionnees (catalogue :
        pans de blouse de Naomi, ailes de Raging Raven...), prises dans la
        zone d'enregistrement ou, a defaut, dans la zone du catalogue."""
        from mgs4trainer.core import mdn
        files = self._model_files()
        data = files.read(path)
        entry = self.model_swap_catalog().get(source)
        wanted = entry[3] if entry is not None and pieces is None else tuple(pieces or ())
        if entry is None or not wanted:
            return data
        places = [dict(files.zone_resources(zone))]
        if entry[0] != zone:
            places.append(dict(files.zone_resources(entry[0])))
        cnp = self._model_cnp(source, zone)
        for piece in wanted:
            piece_path = next((place[0x0D000000 | piece] for place in places if 0x0D000000 | piece in place), None)
            if piece_path is not None:
                data = mdn.merge(data, files.read(piece_path), cnp)
        return data

    def _model_cnp(self, model: int, zone: str) -> bytes | None:
        """.cnp du modele (points d'attache des pieces sans os commun : queue
        de cheval et cables de Raven, cheveux de Big Mama), zone donnee puis
        zone du catalogue."""
        files = self._model_files()
        entry = self.model_swap_catalog().get(model)
        for place in (zone, entry[0] if entry else None):
            if place:
                path = dict(files.zone_resources(place)).get(0x11000000 | model)
                if path:
                    return files.read(path)
        return None

    def set_body_model(self, source: int | None, hide_head: bool = False, layers=(), pieces=None) -> bool:
        """Corps de Snake = geometrie du modele source (None = son modele) ;
        hide_head : tete de Snake (paquet du visage) invisible, pour un
        modele qui a la sienne ; layers : modeles ajoutes par-dessus (le
        foulard 0x6C29C2 et les cheveux de Naomi en noir 0x2DA964 sont des
        modeles a part, sur le meme squelette, lies par aucun fichier :
        2026-11-16)."""
        # pieces : pieces liees gardees (None = toutes celles du catalogue)
        return self._start_equip(self._apply_model_live, source, hide_head, tuple(layers),
                                 None if pieces is None else tuple(pieces))

    # Modele et apparence s'excluent (2026-11-18) : un modele rend d'abord au
    # jeu le corps et le visage imposes ; une apparence retire le modele.
    def _apply_model_live(self, source, hide_head, layers, pieces) -> bool:
        if source is not None and self._octocamo_controller() and (
                self._model_forced_variant("body") is not None or self._model_forced_variant("face") is not None):
            if not self._set_model_variants_live(None, None):
                return self._model_fail("apparence")
            time.sleep(self.MODEL_SWAP_SETTLE)
        # tete de Snake masquee sous un FaceCamo : FaceCamo retire d'abord. Ses
        # modeles (paquet commun, residents) ne passent pas par le detour et
        # revenaient au changement de zone (visage d'une Beauty sur Vamp) ;
        # le visage normal, lui, reste masque.
        facecamo = self.proc.read_bytes(self.linkvarbuf + self.FACECAMO_EQUIP_OFFSET, 1)[0]
        if source is not None and hide_head and facecamo and self._octocamo_controller():
            if not self._equip_model_live(None, 0):
                return self._model_fail("facecamo")
            time.sleep(self.MODEL_SWAP_SETTLE)
        return self._set_body_model_live(source, hide_head, layers, pieces)

    def apply_appearance(self, body: int | None, face: int | None) -> bool:
        """Corps et visage imposes (None = automatique), modele applique retire."""
        return self._start_equip(self._apply_appearance_live, body, face)

    def _apply_appearance_live(self, body, face) -> bool:
        if not self._set_model_variants_live(body, face):
            return self._model_fail("apparence")
        time.sleep(self.MODEL_SWAP_SETTLE)
        # vrai corps et vrai visage de la variante chargee, detour coupe
        return self._set_body_model_live(None, False, ())

    def _set_body_model_live(self, source: int | None, hide_head: bool = False, layers=(), pieces=None) -> bool:
        from mgs4trainer.core import mdn
        funcs = self._live_funcs(self.MODEL_LIVE_FUNCS)
        spawn_funcs = self._live_funcs(self.SPAWN_FUNCS)
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.MODEL_MANAGER_PTR_RVA, 8))[0]
        location = self.read_location()
        skeleton = self._model_body_skeleton()
        if None in (funcs, spawn_funcs, location, skeleton) or not manager:
            return self._model_fail("etape 1")
        # modele sans tete dont la tete est un visage de Snake (FaceCamo) :
        # visage impose AVANT le corps (ce rechargement reconstruit Snake
        # d'apres le dictionnaire, ou le corps d'origine est remis apres le
        # changement : fait apres, il rendait la tenue de Snake, 2026-11-16)
        face = self.MODEL_SWAP_FACES.get(source)
        if face is not None and not hide_head and self._octocamo_controller():
            if self._set_model_variants_live(self._model_forced_variant("body"), face):
                skeleton = self._model_body_skeleton() or skeleton
        body_id, skeleton_data = skeleton
        nodes = self._spawn_resource_nodes()
        target = self._model_node(nodes, body_id)
        if not target:
            return self._model_fail("etape 2")
        files = self._model_files()
        present = {key & 0x7FFFFFFF for key in nodes}
        redirects = []  # (noeud, cle de rechange, contenu, zone)
        missing = {}    # zone -> [(cle, donnees)]
        persist = []    # entrees du detour des chargements (_model_load_set)
        if source is not None:
            # modele puis couches ajoutees par-dessus (foulard, cheveux...) :
            # fusionnes avant le modele hybride ; txn de chacun sous sa zone
            catalog = self.model_swap_catalog()
            datas, load_txns, zone = [], {}, None
            for model in (source, *layers):
                found = self._model_swap_source(model, location[0])
                if found is None and model != source:
                    found = self._model_layer_source(model, source)
                if found is None:
                    return self._model_fail("etape 3")
                model_zone, path, txns = found
                zone = zone or model_zone
                try:
                    datas.append(self._model_source_data(model, path, model_zone, pieces if model == source else None))
                except (ValueError, struct.error, IndexError):
                    return self._model_fail("etape 4")
                waiting = {key for key, _data in missing.get(model_zone, [])}
                missing.setdefault(model_zone, []).extend(
                    (key, files.read(p)) for key, p in txns if key not in present and key not in waiting)
                # aux chargements : toujours les txn du catalogue (une
                # cinematique ou une autre zone ne les a pas)
                entry = catalog.get(model)
                if entry is not None:
                    paths = dict(files.zone_resources(entry[0]))
                    for key in entry[2]:
                        if key in paths and key not in load_txns:
                            load_txns[key] = (files.read(paths[key]), entry[0])
                else:
                    for key, p in txns:
                        load_txns.setdefault(key, (files.read(p), model_zone))
            try:
                data = datas[0]
                cnp = self._model_cnp(source, zone)
                for layer in datas[1:]:
                    data = mdn.merge(data, layer, cnp)
                hybrid = mdn.build_hybrid(data, skeleton_data)
            except (ValueError, struct.error, IndexError):
                return self._model_fail("etape 5")
            redirects.append((target, self._model_alias(source ^ body_id ^ self.MODEL_SWAP_XOR), hybrid, zone,
                              0x0D000000 | body_id))
            # taille 0 = toute taille : la tenue chargee peut changer d'une
            # zone a l'autre (corps torse nu impose perdu au chargement : corps
            # normal de 389456 octets, 359792 attendus, Snake sans tete)
            txn_list = [(key, txn, txn_zone) for key, (txn, txn_zone) in load_txns.items()]
            # 1) toute taille, chargements non residents seulement (tenue
            #    chargee) ; 2) taille exacte, derniere (c'est elle que
            #    l'enregistrement ci-dessous convertit) : cinematiques, cle a
            #    bit 31. La version residente du paquet commun (128 os, autre
            #    taille) n'est jamais remplacee (plantage 75FFDD).
            persist.append((0x0D000000 | body_id, 0, hybrid, txn_list))
            persist.append((0x0D000000 | body_id, len(skeleton_data), hybrid, txn_list))
        else:
            # Corps rendu (2026-11-18) : apres un chargement, le detour a mis
            # notre modele a la place du corps dans le dictionnaire ; Snake s'y
            # reconstruisait avec. Le vrai fichier du corps de sa tenue
            # actuelle (paquet charge) est enregistre et branche comme un
            # modele de rechange, puis le detour est coupe.
            redirects.append((target, self._model_alias(body_id ^ self.MODEL_REAL_XOR), skeleton_data, location[0],
                              0x0D000000 | body_id))
            persist.append((0x0D000000 | body_id, len(skeleton_data), skeleton_data, []))
            # meme chose pour le visage (masque par le detour aux chargements :
            # Snake restait sans tete, 2026-11-18)
            if not hide_head:
                for face_id, face_data in self._model_face_files():
                    node = self._model_node(nodes, face_id)
                    if node:
                        redirects.append((node, self._model_alias(face_id ^ self.MODEL_REAL_XOR), face_data,
                                          location[0], 0x0D000000 | face_id))
                        persist.append((0x0D000000 | face_id, len(face_data), face_data, []))
        if hide_head:
            for face_id, face_data in self._model_face_files():
                hidden = mdn.hidden(face_data)
                # tete residente (cle a bit 31, gardee d'une zone a l'autre)
                # confiee au detour aussi : il ne recopie jamais un resident
                # (cheveux figes puis plantage 75FFDD quand il le faisait,
                # 2026-11-18), il reprend seulement le tampon deja converti
                # (tete de Snake revenue apres un changement de zone, 2026-11-20)
                persist.append((0x0D000000 | face_id, len(face_data), hidden, []))
                node = self._model_node(nodes, face_id)
                if node:
                    redirects.append((node, self._model_alias(face_id ^ self.MODEL_HIDE_XOR), hidden, location[0],
                                      0x0D000000 | face_id))
        textures = sum(struct.unpack_from(">I", data, 8)[0]
                       for entries in missing.values() for key, data in entries if key >> 24 == 0x03)
        if textures and textures > self._model_texture_free():
            return self._model_fail("textures")
        # tampons du detour des chargements : le modele de rechange y est
        # converti par le jeu (drapeaux du chargeur de paquets), puis repris
        # tel quel au chargement d'une cinematique
        if not self._model_wait_loader_idle():
            return self._model_fail("chargement en cours")
        # journal des enregistrements (plantage au deuxieme changement en
        # cinematique : objet du premier modele libere, 2026-11-20)
        try:
            self._equip_log(
                f"modele {source if source is None else hex(source)} cinematique {not self._octocamo_controller()} : "
                f"rechanges {[(hex(alias), zone, hex(load_key)) for _n, alias, _d, zone, load_key in redirects]} ; "
                f"txn {({zone: [hex(key) for key, _d in entries] for zone, entries in missing.items()})}")
        except OSError:
            pass
        load = self._model_load_set(persist)
        if load is None:
            return self._model_fail("etape 7")
        for zone, entries in missing.items():
            if entries and not self._spawn_register_entries(spawn_funcs, zone, entries):
                return self._model_fail("etape 8")
        for _node, alias, data, zone, load_key in redirects:
            if load_key not in load:
                # pas dans le detour (tete residente) : enregistrement simple
                if not self._spawn_register_entries(spawn_funcs, zone, [(alias, data)]):
                    return self._model_fail("etape 9")
                continue
            work, entry = load[load_key]
            self._spawn_blobs[alias] = work
            if not self._spawn_register_entries(spawn_funcs, zone, [(alias, data)], self.MODEL_LOAD_FLAGS):
                return self._model_fail("etape 9")
            self.proc.write_bytes(entry + 0xC, struct.pack("<I", 1))  # converti
        nodes = self._spawn_resource_nodes()
        if any(alias not in nodes for _n, alias, _d, _z, _k in redirects):
            return self._model_fail("etape 10")
        # (noeud, taille et donnees d'origine, taille et donnees de rechange)
        writes = [(node, self.proc.read_bytes(node + 0x14, 4), self.proc.read_bytes(node + 0x20, 8),
                   self.proc.read_bytes(nodes[alias] + 0x14, 4), self.proc.read_bytes(nodes[alias] + 0x20, 8))
                  for node, alias, _d, _z, _k in redirects]
        # cinematique : son Snake ne recoit pas le message ; ses instances
        # sont reconstruites sur place pendant la pause
        changes, instances = [], {}
        if not self._octocamo_controller():
            changes = [(load_key & 0xFFFFFF, struct.unpack("<Q", old)[0], struct.unpack("<Q", new)[0])
                       for (_n, _a, _d, _z, load_key), (_node, _s, old, _ns, new) in zip(redirects, writes)]
            instances = self._model_find_instances(changes)
        call = self.speed.game_call
        state = call(funcs["state"])
        if state is None:
            return self._model_fail("etape 11")
        pause = not (state & 6)
        if pause:
            call(funcs["pause_set"], self.MODEL_PAUSE_FLAG)
        try:
            try:
                for node, _size, _data, size, data in writes:
                    self.proc.write_bytes(node + 0x20, data)
                    self.proc.write_bytes(node + 0x14, size)
                receivers = []
                for i in range(self.MODEL_PLAYER_SLOTS):
                    entry = self.base + self.PLAYER_TABLE_RVA + (i + 1) * self.PLAYER_ENTRY_SIZE
                    receivers.append(struct.unpack("<Q", self.proc.read_bytes(entry, 8))[0])
                offset, count = self.MODEL_EXTRA_RECEIVERS
                receivers += [struct.unpack("<Q", self.proc.read_bytes(manager + offset + 8 * i, 8))[0] for i in range(count)]
                send = self.base + self.LIQUID_SEND_MESSAGE
                for receiver in receivers:
                    if receiver:
                        call(send, receiver, self.MODEL_REBUILD_MESSAGE, 0)
                if changes:
                    self._model_rebuild_instances(changes, instances)
                time.sleep(0.1)
            finally:
                if pause:
                    self._model_pause_clear(funcs)
            # Noeuds rendus APRES la reconstruction (Snake traite le message a
            # sa mise a jour, donc hors pause : rendus 0,3 s apres, en pause,
            # Snake se reconstruisait avec son propre corps). Rendus ensuite
            # parce que le modele de rechange a des structures dans la memoire
            # de la zone, liberees au changement de zone, alors que le slot du
            # corps survit (copie en 7B0F8A depuis un pointeur libere,
            # 2026-11-14). Le Snake construit garde ce modele jusqu'a sa
            # prochaine reconstruction.
            time.sleep(self.MODEL_SWAP_SETTLE)
        finally:
            ours = getattr(self, "_model_work_buffers", set())
            for node, size, data, _size, _data in writes:
                # corps rendu : un noeud qui pointait sur notre modele (mis par
                # le detour au dernier chargement) garde le vrai corps (notre
                # tampon aussi, qui dure) jusqu'au prochain chargement
                if source is None and struct.unpack("<Q", data)[0] in ours:
                    continue
                # Noeud toujours rendu : le jeu retrouve ce qu'il libere d'apres
                # les donnees du noeud. Garder notre modele laissait l'entree
                # d'origine orpheline dans sa table d'objets (18852D0), objet
                # deja libere : plantage 4E0C36 / 10E697 au retour au menu, a
                # la fin d'un acte ou au chargement d'une sauvegarde
                # (2026-11-20, essai du 2026-11-19 annule).
                self.proc.write_bytes(node + 0x20, data)
                self.proc.write_bytes(node + 0x14, size)
        if source is None:
            self._model_load_set([])  # detour coupe : le jeu reprend ses chargements
        return True

    # Modele d'un PNJ (ESSAI 2026-11-23, demande : Meryl sur un rebelle qui
    # prend les echelles). Meme recette que le Snake de cinematique : modele
    # hybride (geometrie du source sur le squelette du PNJ, meme table d'os),
    # enregistre et converti par le jeu, puis A9080(instance, donnees) sur
    # l'instance du PNJ, jeu en pause. Rien ne le garde aux chargements.
    NPC_MODEL_RADIUS = 3000.0   # mm autour de Snake
    NPC_MODEL_MIN_BONES = 30    # personnages (decor : 8 os au plus)
    NPC_MODEL_LOD_OFFSETS = (0x158, 0x160)  # instances des niveaux moyen et simplifie

    def set_npc_model(self, source: int, layers=(), pieces=None) -> bool:
        """Le PNJ le plus proche de Snake prend l'apparence du modele source."""
        return self._start_equip(self._set_npc_model_live, source, tuple(layers),
                                 None if pieces is None else tuple(pieces))

    def _npc_model_instance(self, snake, zone: str) -> tuple[int, int, bytes] | None:
        """(instance, identifiant du mdn, mdn) du personnage le plus proche de
        Snake (os racine, matrice en +0x1E0). Autour de Snake il y a d'abord
        ses pieces (visage a 7 cm, equipement a 25 cm) et du decor anime
        (releve s02a20l, 2026-11-23) : seul compte un modele d'au moins
        NPC_MODEL_MIN_BONES os ; le corps de Snake (a 0 cm) est exclu."""
        from mgs4trainer.core import mdn
        files = self._model_files()
        here = dict(files.zone_resources(zone))
        candidates = []
        count = self.MODEL_INSTANCE_LIST_SLOTS
        table = struct.unpack(f"<{count}Q", self.proc.read_bytes(self.base + self.MODEL_INSTANCE_LIST_RVA, count * 8))
        for pointer in table:
            if not 0x10000 <= pointer < 0x7FF000000000:
                continue
            try:
                ident = struct.unpack("<I", self.proc.read_bytes(pointer + self.MODEL_INSTANCE_ID, 4))[0]
                bone = struct.unpack("<16f", self.proc.read_bytes(pointer + 0x1E0, 64))
            except OSError:
                continue
            x, y, z = bone[12], bone[13], bone[14]
            if not all(v == v and abs(v) < 1e7 for v in (x, y, z)) or not self._model_instance_alive(pointer):
                continue
            d = ((x - snake[0]) ** 2 + (z - snake[2]) ** 2) ** 0.5
            if d < 150 or d > self.NPC_MODEL_RADIUS or abs(y - snake[1]) > 2500:
                continue  # Snake (son modele est a sa place) ou trop loin
            candidates.append((d, pointer, ident & 0xFFFFFF))
        for _d, pointer, ident in sorted(candidates):
            key = 0x0D000000 | ident
            path = here.get(key) or next((p for p in files.entries if p.endswith(f"/{ident:08x}.mdn")), None)
            if path is None:
                continue
            try:
                data = files.read(path)
                if mdn.MdnHeader(data).bone_count >= self.NPC_MODEL_MIN_BONES:
                    return pointer, ident, data
            except (OSError, ValueError, struct.error):
                continue
        return None

    def _set_npc_model_live(self, source: int, layers, pieces) -> bool:
        from mgs4trainer.core import mdn
        funcs = self._live_funcs(self.MODEL_LIVE_FUNCS)
        spawn_funcs = self._live_funcs(self.SPAWN_FUNCS)
        rebuild = self._live_funcs(self.MODEL_INSTANCE_FUNCS)
        location = self.read_location()
        snake = self.player_position()
        if None in (funcs, spawn_funcs, rebuild, location, snake):
            return self._model_fail("PNJ etape 1")
        found = self._npc_model_instance(snake, location[0])
        if found is None:
            return self._model_fail("aucun PNJ a moins de 3 m")
        instance, target_id, skeleton = found
        files = self._model_files()
        nodes = self._spawn_resource_nodes()
        present = {key & 0x7FFFFFFF for key in nodes}
        datas, missing, zone = [], {}, None
        for model in (source, *layers):
            found = self._model_swap_source(model, location[0])
            if found is None and model != source:
                found = self._model_layer_source(model, source)
            if found is None:
                return self._model_fail("PNJ etape 3")
            model_zone, model_path, txns = found
            zone = zone or model_zone
            try:
                datas.append(self._model_source_data(model, model_path, model_zone, pieces if model == source else None))
            except (ValueError, struct.error, IndexError):
                return self._model_fail("PNJ etape 4")
            waiting = {key for key, _data in missing.get(model_zone, [])}
            missing.setdefault(model_zone, []).extend(
                (key, files.read(p)) for key, p in txns if key not in present and key not in waiting)
        try:
            data = datas[0]
            cnp = self._model_cnp(source, zone)
            for layer in datas[1:]:
                data = mdn.merge(data, layer, cnp)
            if not mdn.npc_compatible(data, skeleton):
                return self._model_fail(f"squelettes trop differents ({source:06x} sur {target_id:06x})")
            hybrid = mdn.build_hybrid(data, skeleton, 0.0)
        except (ValueError, struct.error, IndexError):
            return self._model_fail("PNJ etape 5")
        textures = sum(struct.unpack_from(">I", d, 8)[0]
                       for entries in missing.values() for key, d in entries if key >> 24 == 0x03)
        if textures and textures > self._model_texture_free():
            return self._model_fail("textures")
        if not self._model_wait_loader_idle():
            return self._model_fail("chargement en cours")
        alias = self._model_alias(source ^ target_id ^ self.MODEL_SWAP_XOR)
        self._equip_log(f"modele PNJ : {source:06x} sur {target_id:06x} (instance {instance:#x}), cle {alias:#x}, "
                        f"txn {({z: [hex(k) for k, _d in e] for z, e in missing.items()})}")
        for txn_zone, entries in missing.items():
            if entries and not self._spawn_register_entries(spawn_funcs, txn_zone, entries):
                return self._model_fail("PNJ etape 8")
        if not self._spawn_register_entries(spawn_funcs, zone, [(alias, hybrid)]):
            return self._model_fail("PNJ etape 9")
        nodes = self._spawn_resource_nodes()
        if alias not in nodes:
            return self._model_fail("PNJ etape 10")
        new = struct.unpack("<Q", self.proc.read_bytes(nodes[alias] + 0x20, 8))[0]
        # instance toujours la meme (le PNJ a pu disparaitre pendant l'enregistrement)
        if (struct.unpack("<I", self.proc.read_bytes(instance + self.MODEL_INSTANCE_ID, 4))[0] & 0xFFFFFF != target_id
                or not self._model_instance_alive(instance) or not new):
            return self._model_fail("PNJ disparu")
        # niveaux de detail : instances a part, hors du tableau global, accrochees
        # a l'instance principale (+0x158 moyen, +0x160 simplifie ; donnees en
        # +0x70 = celles de reb_def_mid / reb_def_low ; identifiant +0x14 vide).
        # Sans elles, le PNJ reprenait son apparence de loin (2026-11-23).
        datas = {struct.unpack("<Q", self.proc.read_bytes(node + 0x20, 8))[0] for node in nodes.values()}
        lods = []
        for offset in self.NPC_MODEL_LOD_OFFSETS:
            sub = struct.unpack("<Q", self.proc.read_bytes(instance + offset, 8))[0]
            if not 0x10000 <= sub < 0x7FF000000000:
                continue
            shown = struct.unpack("<Q", self.proc.read_bytes(sub + self.MODEL_INSTANCE_DATA, 8))[0]
            if shown in datas and shown != new:
                lods.append(sub)
        call = self.speed.game_call
        state = call(funcs["state"])
        if state is None:
            return self._model_fail("PNJ etape 11")
        pause = not (state & 6)
        if pause:
            call(funcs["pause_set"], self.MODEL_PAUSE_FLAG)
        try:
            result = call(rebuild["rebuild"], instance, new)
            lod_done = sum(1 for sub in lods if call(rebuild["rebuild"], sub, new) == sub) if result == instance else 0
            time.sleep(0.1)
        finally:
            if pause:
                self._model_pause_clear(funcs)
        if result != instance:
            return self._model_fail("reconstruction refusee")
        self._equip_log(f"modele PNJ : instance refaite, niveaux de detail {lod_done}/{len(lods)}")
        self.equip_error = None
        return True

    # Modele -> variante de visage de Snake qui lui donne sa tete (2026-11-16) :
    # camouflage lave de Raging Raven (0x0F874D, sans tete) + visage 0xB,
    # celui du FaceCamo Raging Beauty (objet 0x23).
    MODEL_SWAP_FACES = {0x0F874D: 0xB}

    def _model_forced_variant(self, part: str) -> int | None:
        """Variante imposee par le trainer (fonction "mov eax, N ; ret"), sinon None."""
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.MODEL_MANAGER_PTR_RVA, 8))[0]
        pointer = struct.unpack("<Q", self.proc.read_bytes(manager + self.MODEL_VARIANT_TABLES[part][2], 8))[0]
        if not self._model_pick_is_ours(pointer):
            return None
        return struct.unpack("<I", self.proc.read_bytes(pointer + 1, 4))[0]

    # Snake de cinematique (ESSAI 2026-11-15) : cree par 99B170 (objet,
    # identifiant, drapeaux) -> A98C0(donnees) ; ne recoit pas 0x1E0002.
    # Instance du modele : +0x14 identifiant du mdn, +0x70 donnees
    # converties. A9080(instance, donnees) la reconstruit sur place (le
    # Snake jouable s'en sert en 69A70A) et la rend, 0 si echec (instance
    # liberee). Meme table d'os (corps hybride, visage masque) : meme taille.
    MODEL_INSTANCE_FUNCS = {
        "rebuild": (0xC37E0, "48895c240848896c2410488974241848897c242041564883ec20488bf2488bd9"),  # 1.4.2 A9080
    }
    MODEL_INSTANCE_ID, MODEL_INSTANCE_DATA = 0x14, 0x70
    # Tableau global des instances de modele (1.4.2 0x18D2C10, lu par
    # C6E52) : celles du Snake de cinematique, de sa tete et du Snake
    # jouable y sont (399 pointeurs en s01a60l). Taille max inconnue :
    # 0x400 places lues, chaque pointeur verifie par son identifiant.
    MODEL_INSTANCE_LIST_RVA = 0x1F83410
    MODEL_INSTANCE_LIST_SLOTS = 0x400
    MODEL_SCAN_REGION_MAX = 0x40000000

    def _model_instances(self, models) -> dict[int, list[int]]:
        """{identifiant: [instances]} d'apres le tableau global des instances."""
        count = self.MODEL_INSTANCE_LIST_SLOTS
        table = self.proc.read_bytes(self.base + self.MODEL_INSTANCE_LIST_RVA, count * 8)
        found = {model: [] for model in models}
        for pointer in struct.unpack(f"<{count}Q", table):
            if not 0x10000 <= pointer < 0x7FF000000000:
                continue
            try:
                ident = struct.unpack("<I", self.proc.read_bytes(pointer + self.MODEL_INSTANCE_ID, 4))[0]
            except OSError:
                continue
            if ident in found and pointer not in found[ident]:
                found[ident].append(pointer)
        return found

    def _model_find_instances(self, changes) -> dict[int, list[int]]:
        """Instances a reconstruire, cherchees avant la pause : tableau global
        (instantane), sinon balayage de la memoire (une dizaine de secondes)
        sur les donnees qu'elles peuvent afficher (celles du dictionnaire, ou
        un modele deja donne par le trainer). Snake du briefing quand on
        pilote le Mk.II : instance hors du tableau (s10a20l, 2026-11-15)."""
        found = self._model_instances({model for model, _old, _new in changes})
        if getattr(self, "_model_shown_pid", None) != self.pid:
            self._model_shown_pid, self._model_shown = self.pid, {}
        missing = [(model, old) for model, old, _new in changes if not found[model]]
        if missing:
            wanted = {}
            for model, old in missing:
                for data in {old} | self._model_shown.get(model, set()):
                    wanted[data] = model
            for data, hits in self._model_scan_instances(wanted).items():
                found[wanted[data]] += [h for h in hits if h not in found[wanted[data]]]
        return found

    def _model_scan_instances(self, wanted: dict[int, int]) -> dict[int, list[int]]:
        """wanted : {donnees: identifiant} -> {donnees: [instances]}."""
        found = {data: [] for data in wanted}
        # par la DLL (une fraction de seconde au lieu de 10 a 30), sinon ici
        hits = self.speed.scan_qwords(list(wanted), self.MODEL_SCAN_REGION_MAX)
        if hits is not None:
            for data, addresses in hits.items():
                for at in addresses:
                    instance = at - self.MODEL_INSTANCE_DATA
                    try:
                        ident = struct.unpack("<I", self.proc.read_bytes(instance + self.MODEL_INSTANCE_ID, 4))[0]
                    except OSError:
                        continue
                    if ident == wanted[data]:
                        found[data].append(instance)
            return found
        needles = {struct.pack("<Q", data): (data, model) for data, model in wanted.items()}
        for region, size in self.proc._writable_regions():
            if size > self.MODEL_SCAN_REGION_MAX:
                continue
            try:
                chunk = self.proc.read_bytes(region, size)
            except OSError:
                continue
            for needle, (data, model) in needles.items():
                at = chunk.find(needle)
                while at >= 0:
                    if not at % 8 and at >= self.MODEL_INSTANCE_DATA:
                        ident = struct.unpack_from("<I", chunk, at - self.MODEL_INSTANCE_DATA + self.MODEL_INSTANCE_ID)[0]
                        if ident == model:
                            found[data].append(region + at - self.MODEL_INSTANCE_DATA)
                    at = chunk.find(needle, at + 1)
        return found

    def _model_rebuild_instances(self, changes, instances: dict[int, list[int]]) -> int:
        """changes : [(identifiant, anciennes donnees, nouvelles)] ; nombre
        d'instances reconstruites (celles qui affichent deja les nouvelles
        donnees, ou dont l'identifiant a change, sont laissees)."""
        funcs = self._live_funcs(self.MODEL_INSTANCE_FUNCS)
        if funcs is None:
            return 0
        done = 0
        for model, _old, new in changes:
            for instance in instances.get(model, ()):
                head = self.proc.read_bytes(instance + self.MODEL_INSTANCE_ID, 4)
                # copie perimee (deja liberee, memoire reutilisee) laissee :
                # la reconstruire ecrivait dans un objet libre (tache du jeu
                # ecrasee, plantage 52B07B au retour au menu apres deux
                # changements en cinematique, 2026-11-20)
                if struct.unpack("<I", head)[0] != model or not self._model_instance_alive(instance):
                    continue
                if struct.unpack("<Q", self.proc.read_bytes(instance + self.MODEL_INSTANCE_DATA, 8))[0] == new:
                    continue
                if self.speed.game_call(funcs["rebuild"], instance, new) == instance:
                    done += 1
            if getattr(self, "_model_shown_pid", None) != self.pid:
                self._model_shown_pid, self._model_shown = self.pid, {}
            self._model_shown.setdefault(model, set()).add(new)
        return done

    # Table des objets de ressources du jeu (compteur ; entrees de 0x20 juste
    # apres : cle, donnees, objet). Elle se remplit pendant un chargement.
    MODEL_OBJECT_COUNT_RVA = 0x1F35AC0  # 1.4.2 18852C0
    MODEL_LOADER_QUIET, MODEL_LOADER_MAX_WAIT = 1.5, 15.0

    def _model_wait_loader_idle(self) -> bool:
        """Attend que le jeu ait fini de charger (table des objets stable
        MODEL_LOADER_QUIET s). Enregistrer pendant que le chargeur du jeu
        enregistre lui aussi (debut d'une cinematique) ecrasait des objets
        en service : plantage au changement suivant (A4E85, AFEC7, B96D9 ;
        cinq essais du 2026-11-20, plantage seulement quand le premier
        changement suivait de 3-4 s le debut de la cinematique)."""
        counter = self.base + self.MODEL_OBJECT_COUNT_RVA
        deadline = time.monotonic() + self.MODEL_LOADER_MAX_WAIT
        last, since = None, time.monotonic()
        while time.monotonic() < deadline:
            count = struct.unpack("<i", self.proc.read_bytes(counter, 4))[0]
            if count != last:
                last, since = count, time.monotonic()
            elif time.monotonic() - since >= self.MODEL_LOADER_QUIET:
                return True
            time.sleep(0.1)
        self._equip_log("modele : le jeu charge encore, changement annule")
        return False

    def _model_instance_alive(self, instance: int) -> bool:
        """Instance trouvee en memoire plausible : premiere matrice d'os =
        rotation (une copie perimee, deja liberee, peut garder l'identifiant
        et les donnees, 2026-11-19)."""
        try:
            m = struct.unpack("<12f", self.proc.read_bytes(instance + 0x1E0, 48))
        except OSError:
            return False
        return all(abs(sum(m[r * 4 + i] ** 2 for i in range(3)) - 1.0) < 0.05 for r in range(3))

    def _model_alias(self, seed: int) -> int:
        """Cle de rechange neuve a chaque application (un tampon neuf est
        enregistre a chaque fois ; une cle deja presente serait doublee)."""
        self._model_alias_serial = getattr(self, "_model_alias_serial", 0) + 1
        return 0x0D000000 | ((seed ^ self._model_alias_serial * 0x010307) & 0xFFFFFF)

    @staticmethod
    def _model_node(nodes: dict[int, int], model: int) -> int:
        """Noeud du mdn ; la cle peut porter le bit 31 (s03a70l : 0x8D413AA8),
        que la recherche du jeu (534210) ignore ("btr r8d,0x1f")."""
        key = 0x0D000000 | model
        return nodes.get(key) or nodes.get(key | 0x80000000) or 0

    # Modele garde aux chargements (ESSAI 2026-11-15) : un chargement (zone,
    # cinematique) reenregistre le corps et le visage depuis le tampon de
    # leur paquet (x64dbg : 532220 appele par le chargeur de paquets ED4E4,
    # drapeaux 0x61 a la zone -> fichier converti sur place ; 0x70 a la
    # cinematique -> tampon deja converti, bit 31 sur la cle). Detour a
    # l'entree de cet enregistrement (tools/build_model_hook.py) : meme cle
    # et meme taille -> notre tampon, rempli d'une copie neuve a la zone,
    # repris tel quel a la cinematique, apres ses txn si la table des
    # textures a la place (sinon le jeu garde son modele).
    MODEL_LOAD_FUNCS = {
        "core": (0x749CC0, "48895c241844894c2420"),   # 1.4.2 532220
        "lookup": (0x74C0B0, "8bc1448bc148c1e803"),   # 1.4.2 534210, cle -> noeud
    }
    MODEL_LOAD_SITE_ORIG = bytes.fromhex("48895c2418")  # mov [rsp+0x18], rbx
    MODEL_LOAD_CODE = bytes.fromhex(
        "5356574154415541564157555152415041514883ec2848bd8877665544332211"
        "837d3c000f84850000008b44243825ffffff7f488d5d408b4d3885c974713b03"
        "75188b542428837b040074073b53047411eb07f644243b8074084883c340ffc9"
        "ebd8f6442430107526f644243b80753fe85b00000085c07436488b7b10488b73"
        "188b4b08f3a4c7430c01000000eb0f837b0c00741ae83600000085c07411488b"
        "431048894424408b43084889442428488b45104883c428415941585a595d415f"
        "415e415d415c5f5e5b48895c2418ffe04883ec28448b632c4585e40f84bd0000"
        "004c8b452031c0b90100000081f921140000731b486bd17049837c100800750b"
        "6641837c1034ff7502ffc0ffc1ebdd4439e00f8290000000488b4518488b0048"
        "8b483448894d28488b484448894d304c8b6b20448b73284585f6744b418b4d00"
        "ff55084885c07536498b7d08498b7510418b4d04f3a4488b4518488b00498b4d"
        "184889483448894844498b4d08418b550041b801000000458b4d04ff55004983"
        "c52041ffceebb0488b4518488b00488b4d2848894834488b4d3048894844b801"
        "0000004883c428c331c04883c428c3"
    )
    MODEL_LOAD_BASE_AT = 0x18   # imm64 de "movabs rbp, page" dans le code
    MODEL_LOAD_CODE_AT = 0x800
    MODEL_LOAD_TXN_AT = 0x400
    MODEL_LOAD_MAX_ENTRIES, MODEL_LOAD_MAX_TXNS = 8, 32

    @staticmethod
    def _model_resident(nodes, model: int) -> bool:
        """Modele charge en resident (cle a bit 31 seulement)."""
        key = 0x0D000000 | model
        return (key | 0x80000000) in nodes and key not in nodes

    def _model_hook_page(self, site: int) -> int:
        """Page du detour en place, quelle que soit sa version (0 sinon)."""
        head = self.proc.read_bytes(site, 5)
        if head[0] != 0xE9:
            return 0
        page = site + 5 + struct.unpack_from("<i", head, 1)[0] - self.MODEL_LOAD_CODE_AT
        try:
            resume = struct.unpack("<Q", self.proc.read_bytes(page + 0x10, 8))[0]
        except OSError:
            return 0
        return page if resume == site + 5 else 0

    def _model_load_page(self, funcs: dict[str, int]) -> int:
        """Page du detour, installe au besoin (repris s'il est deja la)."""
        site = funcs["core"]
        head = self.proc.read_bytes(site, 5)
        if head[0] == 0xE9:
            page = site + 5 + struct.unpack_from("<i", head, 1)[0] - self.MODEL_LOAD_CODE_AT
            code = self.proc.read_bytes(page + self.MODEL_LOAD_CODE_AT, len(self.MODEL_LOAD_CODE))
            mine = bytearray(self.MODEL_LOAD_CODE)
            mine[self.MODEL_LOAD_BASE_AT:self.MODEL_LOAD_BASE_AT + 8] = struct.pack("<Q", page)
            if code == bytes(mine):
                return page
            # detour d'une version precedente du trainer (meme reprise) :
            # coupe, puis remplace par une page neuve (2026-11-18)
            resume = struct.unpack("<Q", self.proc.read_bytes(page + 0x10, 8))[0]
            if resume != site + 5:
                return 0
            self.proc.write_bytes(page + 0x3C, bytes(4))
        elif head != self.MODEL_LOAD_SITE_ORIG:
            return 0
        page = self.proc.alloc_near(site)
        if not page:
            return 0
        code = bytearray(self.MODEL_LOAD_CODE)
        code[self.MODEL_LOAD_BASE_AT:self.MODEL_LOAD_BASE_AT + 8] = struct.pack("<Q", page)
        header = struct.pack("<6Q", self._live_funcs(self.SPAWN_FUNCS)["register"], funcs["lookup"],
                             site + 5, self.base + self.SPAWN_LINKVARBUF_RVA,
                             self.base + self.MODEL_TEXTURE_TABLE_RVA, 0)
        self.proc.write_bytes(page, header + bytes(0x10))   # +0x38 : 0 entree, inactif
        self.proc.write_bytes(page + self.MODEL_LOAD_CODE_AT, bytes(code))
        jump = page + self.MODEL_LOAD_CODE_AT - (site + 5)
        self.proc.write_bytes(site, b"\xE9" + struct.pack("<i", jump))
        return page

    MODEL_LOAD_FLAGS = 0x61  # drapeaux du chargeur de paquets au chargement d'une zone

    def _model_load_set(self, entries) -> dict[int, tuple[int, int]] | None:
        """entries : [(cle, taille d'origine, remplacement, [(cle, txn, zone du txn)])]
        ; vide = detour inactif (le jeu reprend ses modeles au chargement)."""
        # le debut de "core" est notre saut une fois le detour pose
        site = self.base + self.MODEL_LOAD_FUNCS["core"][0]
        installed = self.proc.read_bytes(site, 1) == b"\xE9"
        funcs = self._live_funcs({name: value for name, value in self.MODEL_LOAD_FUNCS.items()
                                  if not (installed and name == "core")})
        if funcs is None:
            return None if entries else {}
        funcs["core"] = site
        if not entries:
            page = self._model_hook_page(site)
            if page:
                self.proc.write_bytes(page + 0x3C, bytes(4))
            return {}
        if "lookup" not in funcs or len(entries) > self.MODEL_LOAD_MAX_ENTRIES:
            return None
        if sum(len(e[3]) for e in entries) > self.MODEL_LOAD_MAX_TXNS:
            return None
        page = self._model_load_page(funcs)
        if not page:
            return None
        self.proc.write_bytes(page + 0x3C, bytes(4))  # inactif pendant l'ecriture
        if getattr(self, "_spawn_blob_pid", None) != self.pid:
            self._spawn_blob_pid, self._spawn_blobs = self.pid, {}
            self._spawn_arena, self._spawn_arena_left = 0, 0

        def buffers(data: bytes) -> tuple[int, int]:
            # tampon neuf a chaque fois : l'ancien peut etre celui du
            # dictionnaire de la zone (converti, en service)
            work = self._spawn_blob(len(data))
            pristine = self._spawn_alloc(len(data), PAGE_READWRITE)
            if not work or not pristine:
                raise OSError("place")
            self.proc.write_bytes(pristine, data)
            # tampons ou le detour fait convertir nos modeles aux chargements
            self._model_work_buffers = getattr(self, "_model_work_buffers", set()) | {work}
            return work, pristine

        table, txn_items, out = b"", b"", {}
        txn_at = page + self.MODEL_LOAD_TXN_AT
        for key, original, data, txns in entries:
            work, pristine = buffers(data)
            out[key] = (work, page + 0x40 + len(table))
            items = b""
            needed = 0
            for txn_key, txn, txn_zone in txns:
                txn_work, txn_pristine = buffers(txn)
                # nom de la zone du txn (couches venues d'autres zones)
                items += struct.pack("<IIQQ", txn_key, len(txn), txn_work, txn_pristine) \
                    + txn_zone.encode()[:7].ljust(8, b"\0")
                needed += struct.unpack_from(">I", txn, 8)[0]
            table += struct.pack("<IIIIQQQII", key & 0x7FFFFFFF, original, len(data), 0, work, pristine,
                                 txn_at + len(txn_items) if items else 0, len(txns), needed) + bytes(16)
            txn_items += items
        self.proc.write_bytes(page + self.MODEL_LOAD_TXN_AT, txn_items or bytes(1))
        self.proc.write_bytes(page + 0x40, table)
        self.proc.write_bytes(page + 0x38, struct.pack("<II", len(entries), 1))
        return out

    def model_load_release(self) -> None:
        """Fermeture du trainer : detour retire (le modele en place reste
        jusqu'au prochain chargement)."""
        if not (self.connected and self.sane):
            return
        try:
            site = self.base + self.MODEL_LOAD_FUNCS["core"][0]
            page = self._model_hook_page(site)
            if page:
                self.proc.write_bytes(page + 0x3C, bytes(4))
                self.proc.write_bytes(site, self.MODEL_LOAD_SITE_ORIG)
        except OSError:
            pass

    def _model_face_files(self) -> list[tuple[int, bytes]]:
        """[(identifiant, fichier)] des mdn du paquet du visage charge (visage
        0x03A157, bandana, Solid Eye...)."""
        loaded = self.model_loaded_variants()
        if loaded is None:
            return []
        pack = dict(self.model_variants("face")).get(loaded[1])
        if pack is None:
            return []
        files = self._model_files()
        # Modeles de tete de Snake : ceux des paquets de visage (0x03A157,
        # 0x58B84A, 0x79B16E...), pris la ou le jeu les a charges. Certains
        # visages (Otacon, variante 22) viennent du paquet commun 00000001
        # (~600 modeles : echec a l'etape 7), et 0x58B84A y est une piece de
        # 11 os sur le crane, pas sur le cou (2026-11-18).
        if getattr(self, "_model_face_ids", None) is None:
            ids = set()
            for _variant, face_pack in self.model_variants("face"):
                marker = f"/slot/{face_pack:08x}/cache/"
                found = {int(p.rsplit("/", 1)[1][:8], 16) for p in files.entries if marker in p and p.endswith(".mdn")}
                if len(found) <= self.MODEL_FACE_FILES_MAX:
                    ids |= found
            self._model_face_ids = ids
        loaded = {key & 0xFFFFFF for key in self._spawn_resource_nodes() if (key >> 24) & 0x7F == 0x0D}
        marker = f"/slot/{pack:08x}/cache/"
        out = []
        for path in files.entries:
            if marker not in path or not path.endswith(".mdn"):
                continue
            ident = int(path.rsplit("/", 1)[1][:8], 16)
            if ident in loaded and ident in self._model_face_ids:
                out.append((ident, files.read(path)))
        return out[:self.MODEL_FACE_FILES_MAX]

    MODEL_FACE_FILES_MAX = 4

    def model_variants_release(self) -> None:
        """Fermeture du trainer : les fonctions du jeu reprennent le choix des
        variantes (le modele actuel reste jusqu'au prochain changement)."""
        if not (self.connected and self.sane):
            return
        try:
            manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.MODEL_MANAGER_PTR_RVA, 8))[0]
            if not manager:
                return
            for part, (_t, _c, pick) in self.MODEL_VARIANT_TABLES.items():
                current = struct.unpack("<Q", self.proc.read_bytes(manager + pick, 8))[0]
                if self._model_pick_is_ours(current):
                    original = getattr(self, "_model_pick_originals", {}).get(
                        part, struct.pack("<Q", self.base + self.MODEL_DEFAULT_PICKERS[part]))
                    self.proc.write_bytes(manager + pick, original)
        except OSError:
            pass

    def _model_pick_is_ours(self, pointer: int) -> bool:
        """Notre fonction "mov eax, N ; ret" (B8 xx xx xx xx C3) ?"""
        try:
            code = self.proc.read_bytes(pointer, 6) if pointer else b""
        except OSError:
            return False
        return len(code) == 6 and code[0] == 0xB8 and code[5] == 0xC3

    def model_natural_face(self) -> int | None:
        """Visage que le jeu choisit pour la tenue portee : le visage charge
        tant que le pointeur +0xE8 est celui du jeu (memorise), sinon le
        dernier releve (tenue changee depuis : inconnu, None)."""
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.MODEL_MANAGER_PTR_RVA, 8))[0]
        if not manager:
            return None
        pick = struct.unpack("<Q", self.proc.read_bytes(manager + self.MODEL_VARIANT_TABLES["face"][2], 8))[0]
        outfit = self.proc.read_bytes(self.linkvarbuf + self.OUTFIT_EQUIP_OFFSET, 2)
        if not self._model_pick_is_ours(pick):
            face = struct.unpack("<i", self.proc.read_bytes(manager + 0xC8, 4))[0]
            self._model_natural = (self.pid, outfit, face)
            return face
        cached = getattr(self, "_model_natural", None)
        return cached[2] if cached and cached[:2] == (self.pid, outfit) else None

    def model_loaded_variants(self) -> tuple[int, int] | None:
        """(corps, visage) charges."""
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.MODEL_MANAGER_PTR_RVA, 8))[0]
        if not manager:
            return None
        return struct.unpack("<ii", self.proc.read_bytes(manager + 0xC4, 8))

    def set_model_variants(self, body: int | None, face: int | None) -> bool:
        """Impose (ou rend au jeu, None) la variante de corps et de visage."""
        return self._start_equip(self._set_model_variants_live, body, face)

    def _set_model_variants_live(self, body: int | None, face: int | None) -> bool:
        funcs = self._live_funcs(self.MODEL_LIVE_FUNCS)
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.MODEL_MANAGER_PTR_RVA, 8))[0]
        if funcs is None or not manager or not self._octocamo_controller():
            return False
        for part, value in (("body", body), ("face", face)):
            if value is not None and value not in {v for v, _ in self.model_variants(part)}:
                return False
        # Visage compatible avec le corps (voir MODEL_PAIRED_FACE) : visage
        # automatique incompatible -> visage associe, sinon le premier qui va.
        loaded = self.model_loaded_variants()
        if loaded is None:
            return False
        body_target = body if body is not None else loaded[0]
        face_target = face if face is not None else loaded[1]
        if not self.model_face_compatible(body_target, face_target):
            if face is not None:
                return False
            candidates = [self.MODEL_PAIRED_FACE.get(body_target)] + [v for v, _ in self.model_variants("face")]
            face = next((v for v in candidates if v is not None and self.model_face_compatible(body_target, v)), None)
            if face is None:
                return False
        if getattr(self, "_model_pick_pid", None) != self.pid:
            stubs = self.proc.alloc_near(self.base, 0x1000)
            if not stubs:
                return False
            self._model_pick_pid, self._model_pick_originals, self._model_pick_stubs = self.pid, {}, stubs
        # Pointeur du jeu releve tant qu'il n'est pas une de nos fonctions
        # (reconnues a leur contenu, meme laissees par un trainer precedent) ;
        # sinon, fonction d'origine connue.
        for part, (_t, _c, pick) in self.MODEL_VARIANT_TABLES.items():
            current = self.proc.read_bytes(manager + pick, 8)
            if self._model_pick_is_ours(struct.unpack("<Q", current)[0]):
                self._model_pick_originals.setdefault(
                    part, struct.pack("<Q", self.base + self.MODEL_DEFAULT_PICKERS[part]))
            else:
                self._model_pick_originals[part] = current
        call = self.speed.game_call
        state = call(funcs["state"])
        if state is None:
            return False
        pause = not (state & 6)
        if pause:
            call(funcs["pause_set"], self.MODEL_PAUSE_FLAG)
        try:
            outfit, worn_face = self.proc.read_bytes(self.linkvarbuf + self.OUTFIT_EQUIP_OFFSET, 2)
            facecamo = self.MODEL_FACECAMO_INDEX.get(face) if face is not None else None
            if facecamo is not None:
                # visage d'un FaceCamo : on porte ce FaceCamo (B27), pointeur du jeu
                pattern = struct.unpack("<I", self.proc.read_bytes(
                    self.linkvarbuf + mgs4save.OCTOCAMO_EQUIPPED_OFFSET, 4))[0]
                if not (call(funcs["face_allowed"], pattern, outfit, facecamo) or 0) & 0xFFFFFFFF:
                    return False
                worn_face, face = facecamo, None
            for index, (part, value) in enumerate((("body", body), ("face", face))):
                pick = self.MODEL_VARIANT_TABLES[part][2]
                if value is None:
                    pointer = self._model_pick_originals[part]
                else:
                    stub = self._model_pick_stubs + index * 0x10
                    self.proc.write_bytes(stub, b"\xB8" + struct.pack("<I", value) + b"\xC3")
                    pointer = struct.pack("<Q", stub)
                self.proc.write_bytes(manager + pick, pointer)
            # Rechargement par la fonction d'equipement du jeu, tenue et visage
            # inchanges : elle calcule les variantes (donc les notres), pose le
            # decompte ET previent Snake (message 0x1E0001) avant que le tampon
            # soit ecrase ; decompte ecrit seul = rendu sur l'ancien modele,
            # plantage en C5EB3 (2026-11-14).
            if (call(funcs["equip"], outfit, worn_face) or 0) & 0xFFFFFFFF != 0:
                return False
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                countdown = struct.unpack("<i", self.proc.read_bytes(manager + self.MODEL_RELOAD_COUNTDOWN, 4))[0]
                loading = self.proc.read_bytes(manager + self.MODEL_RELOAD_LOADING, 1)[0] & 3
                if countdown <= 0 and not loading:
                    break
                time.sleep(0.02)
            time.sleep(0.1)
            return True
        finally:
            if pause:
                self._model_pause_clear(funcs)

    def reset_snake_appearance(self) -> bool:
        """Snake neutre (2026-11-18) : tenue et visage rendus au jeu,
        combinaison OctoCamo sans FaceCamo, vrai corps et vrai visage."""
        return self._start_equip(self._reset_appearance_live)

    def _reset_appearance_live(self) -> bool:
        funcs = self._live_funcs(self.MODEL_LIVE_FUNCS)
        manager = struct.unpack("<Q", self.proc.read_bytes(self.base + self.MODEL_MANAGER_PTR_RVA, 8))[0]
        # en cinematique (pas de controleur) recharger Snake fait planter le
        # jeu : seulement le corps et le visage
        if funcs is not None and manager and self._octocamo_controller():
            self.model_variants_release()  # choix du corps et du visage rendus au jeu
            call = self.speed.game_call
            state = call(funcs["state"])
            if state is None:
                return self._model_fail("neutre")
            pause = not (state & 6)
            if pause:
                call(funcs["pause_set"], self.MODEL_PAUSE_FLAG)
            try:
                # combinaison OctoCamo (0), sans FaceCamo (0) ; rechargement
                # meme si deja portes (variantes imposees rendues)
                if (call(funcs["equip"], 0, 0) or 0) & 0xFFFFFFFF != 0:
                    return self._model_fail("neutre")
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    countdown = struct.unpack("<i", self.proc.read_bytes(manager + self.MODEL_RELOAD_COUNTDOWN, 4))[0]
                    loading = self.proc.read_bytes(manager + self.MODEL_RELOAD_LOADING, 1)[0] & 3
                    if countdown <= 0 and not loading:
                        break
                    time.sleep(0.02)
                time.sleep(0.1)
            finally:
                if pause:
                    self._model_pause_clear(funcs)
            time.sleep(self.MODEL_SWAP_SETTLE)
        return self._set_body_model_live(None, False, ())

    def _model_pause_clear(self, funcs: dict[str, int]) -> None:
        """Leve la pause du modele ; si l'appel echoue (delai), le drapeau
        est retire directement (jeu reste fige sinon, 2026-11-14)."""
        if self.speed.game_call(funcs["pause_clear"], self.MODEL_PAUSE_FLAG) is not None:
            return
        code = self.proc.read_bytes(funcs["state"], 6)  # mov eax, [rip + disp] ; ret
        flags = funcs["state"] + 6 + struct.unpack_from("<i", code, 2)[0]
        value = struct.unpack("<I", self.proc.read_bytes(flags, 4))[0]
        self.proc.write_bytes(flags, struct.pack("<I", value & ~self.MODEL_PAUSE_FLAG))

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
