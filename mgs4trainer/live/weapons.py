"""MGS4Live : armes, munitions, accessoires et silencieux."""
import struct
import threading
import time

from mgs4trainer.core.gamedata import (
    CONFIRMED_WEAPON_AMMO_RVAS, MODULE_PATCH_SHIFT, WEAPON_MAGAZINE_MAX_OFFSET, WEAPON_MAGAZINE_OFFSET,
    item_state_rva, weapon_state_rva,
)


class WeaponsMixin:
    """Armes, munitions, accessoires et silencieux."""

    def read_item(self, item_id: int) -> int:
        return struct.unpack("<H", self.proc.read_bytes(self.base + item_state_rva(item_id), 2))[0]

    def write_item(self, item_id: int, value: int) -> None:
        self.proc.write_bytes(self.base + item_state_rva(item_id), struct.pack("<H", value & 0xFFFF))

    def read_weapon(self, weapon_id: int) -> int:
        return struct.unpack("<H", self.proc.read_bytes(self.base + weapon_state_rva(weapon_id), 2))[0]

    def write_weapon(self, weapon_id: int, value: int) -> None:
        self.proc.write_bytes(self.base + weapon_state_rva(weapon_id), struct.pack("<H", value & 0xFFFF))
        self.refresh_weapon_custom_menu()

    # Menu de personnalisation d'arme (2026-10-09) : il lit les etats des
    # accessoires une seule fois a l'ouverture (getter 6EA40) et garde sa
    # copie. C'est une tache de la liste circulaire de tete mgs4+23CF9EE0
    # (+0 suivant, +8 fonction de mise a jour = 51E720 pour ce menu). Quand
    # on (des)equipe un accessoire dans le menu, le jeu (521330) appelle
    # build_list (51F7A0, reconstruit les listes +0x278 + n*0xE8) puis
    # redraw (522F10, categorie affichee = +0x7EC) : on fait pareil.
    CUSTOM_MENU_TASK_LIST_RVA = 0x23CF9EE0
    CUSTOM_MENU_FUNCS = {
        "update": (0x51E720, "48895c24084889742410574883ec"),
        "build_list": (0x51F7A0, "48894c2408535556574154415541"),
        "redraw": (0x522F10, "4c8bdc55415441554881ece00000"),
    }

    def _weapon_custom_menu(self, update_fn: int) -> int:
        """Tache du menu de personnalisation d'arme, 0 s'il est ferme."""
        head = self.base + self.CUSTOM_MENU_TASK_LIST_RVA
        node = struct.unpack("<Q", self.proc.read_bytes(head, 8))[0]
        for _ in range(self.CUTSCENE_TASK_MAX):
            if not node or node == head:
                return 0
            entry = self.proc.read_bytes(node, 16)
            if struct.unpack_from("<Q", entry, 8)[0] == update_fn:
                return node
            node = struct.unpack_from("<Q", entry, 0)[0]
        return 0

    def refresh_weapon_custom_menu(self) -> None:
        """Si le menu de personnalisation est ouvert, lui fait relire les
        etats (fil separe : l'appel attend l'image suivante du jeu)."""
        if self._custom_menu_refresh_pending or not self.speed.main_loop_hook_installed():
            return
        try:
            funcs = self._live_funcs(self.CUSTOM_MENU_FUNCS)
            if funcs is None or not self._weapon_custom_menu(funcs["update"]):
                return
        except Exception:
            return
        self._custom_menu_refresh_pending = True
        threading.Thread(target=self._refresh_weapon_custom_menu, args=(funcs,), daemon=True).start()

    def _refresh_weapon_custom_menu(self, funcs: dict[str, int]) -> None:
        try:
            time.sleep(0.05)  # regroupe les changements faits d'affilee
            self._custom_menu_refresh_pending = False
            menu = self._weapon_custom_menu(funcs["update"])
            if menu and self.speed.game_call(funcs["build_list"], menu) is not None:
                self.speed.game_call(funcs["redraw"], menu)
        except Exception:
            self._custom_menu_refresh_pending = False

    def read_weapon_ammo(self, weapon_id: int) -> int | None:
        """None = adresse munitions pas encore trouvee pour cette arme
        (voir CONFIRMED_WEAPON_AMMO_RVAS - a completer arme par arme par
        scan memoire, meme methode que pour l'etat/possession)."""
        rva = CONFIRMED_WEAPON_AMMO_RVAS.get(weapon_id)
        if rva is None:
            return None
        return struct.unpack("<H", self.proc.read_bytes(self.base + rva + MODULE_PATCH_SHIFT, 2))[0]

    # Munitions infinies "d'origine" (2026-10-04) : chaque arme de la
    # table du jeu (mgs4+1D82580 + ID*0x50, comme set_weapon) a des
    # drapeaux a +0x40 ; bit 0 = la reserve ne baisse jamais (la fonction
    # de tir 6E1BE le teste a cote du test du Bandana), bit 1 = chargeur
    # infini. D'origine : Pistolet solaire = 1, Patriot = 3, le reste 0.
    # Activer le bit 0 donne la reserve infinie ET le symbole infini du
    # HUD, sans toucher a l'objet special equipe (valide en jeu sur
    # l'Operator ; faire pointer l'objet equipe sur le Bandana coupait le
    # Solid Eye et n'affichait pas le symbole).
    WEAPON_FLAGS_OFFSET = 0x40
    WEAPON_FLAG_INFINITE_RESERVE = 0x1
    # Pistolet solaire : pas de vraie reserve, sa "jauge" est le chargeur
    # (200, recharge au soleil). Bit 1 (chargeur infini, comme le Patriot)
    # le fige... a sa valeur du moment, recharge solaire comprise : on le
    # remplit donc au maximum en meme temps (+0x30 courant, +0x32 max).
    SOLAR_GUN_ID = 0x0D
    WEAPON_FLAG_INFINITE_MAGAZINE = 0x2
    WEAPON_MAGAZINE_ENTRY_OFFSET = 0x30
    NATIVE_INFINITE_WEAPON_IDS = frozenset({0x0D, 0x16})
    INFINITE_AMMO_WEAPON_IDS = tuple(sorted(set(CONFIRMED_WEAPON_AMMO_RVAS) - {0x0D, 0x16}))

    def set_infinite_ammo(self, enabled: bool) -> bool:
        """Pose (ou retire) le bit 0 sur toutes les armes a munitions ; une
        lecture de la table, une ecriture par arme seulement si besoin -
        rappele a chaque cycle, le jeu peut reconstruire la table (chargement)."""
        if not (self.connected and self.sane):
            return False
        table = self.base + self.WEAPON_TABLE_RVA
        last = self.INFINITE_AMMO_WEAPON_IDS[-1]
        block = self.proc.read_bytes(table, (last + 1) * self.WEAPON_TABLE_STRIDE)
        for weapon_id in self.INFINITE_AMMO_WEAPON_IDS:
            offset = weapon_id * self.WEAPON_TABLE_STRIDE + self.WEAPON_FLAGS_OFFSET
            flags = struct.unpack_from("<I", block, offset)[0]
            wanted = (flags | self.WEAPON_FLAG_INFINITE_RESERVE) if enabled                 else (flags & ~self.WEAPON_FLAG_INFINITE_RESERVE)
            if wanted != flags:
                self.proc.write_bytes(table + offset, struct.pack("<I", wanted))
        solar = table + self.SOLAR_GUN_ID * self.WEAPON_TABLE_STRIDE
        flags = struct.unpack("<I", self.proc.read_bytes(solar + self.WEAPON_FLAGS_OFFSET, 4))[0]
        wanted = (flags | self.WEAPON_FLAG_INFINITE_MAGAZINE) if enabled             else (flags & ~self.WEAPON_FLAG_INFINITE_MAGAZINE)
        if enabled:
            current, maximum = struct.unpack("<hh", self.proc.read_bytes(solar + self.WEAPON_MAGAZINE_ENTRY_OFFSET, 4))
            if 0 < maximum != current:
                self.proc.write_bytes(solar + self.WEAPON_MAGAZINE_ENTRY_OFFSET, struct.pack("<h", maximum))
        if wanted != flags:
            self.proc.write_bytes(solar + self.WEAPON_FLAGS_OFFSET, struct.pack("<I", wanted))
        return True

    def write_weapon_ammo(self, weapon_id: int, value: int) -> bool:
        """Retourne False sans rien ecrire si l'adresse munitions de cette
        arme n'est pas encore connue."""
        rva = CONFIRMED_WEAPON_AMMO_RVAS.get(weapon_id)
        if rva is None:
            return False
        self.proc.write_bytes(self.base + rva + MODULE_PATCH_SHIFT, struct.pack("<H", value & 0xFFFF))
        return True

    # Silencieux (2026-10-09, valide en jeu) : pas un nombre mais une
    # reserve d'usure en tirs, dans la table des munitions du jeu
    # (mgs4+1D81F20 + index*0x18 : +0x10 reserve, +0x12 maximum, u16).
    # Index = 6A3B0(ID) ; nombre affiche = reserve / tirs par silencieux,
    # arrondi au-dessus (414 tirs a 30 = 14) ; maximum = 99 silencieux.
    AMMO_TABLE_RVA = 0x1D81F20
    AMMO_ENTRY_SIZE = 0x18
    SILENCER_AMMO_INDEX = {0x4D: 0x3D, 0x4E: 0x3E, 0x4F: 0x3F, 0x50: 0x40, 0x51: 0x41, 0x52: 0x42, 0x53: 0x43}
    SILENCER_MAX = 99

    def _silencer_reserve(self, weapon_id: int) -> tuple[int, int, int] | None:
        """(adresse, reserve, tirs par silencieux), None si pas un silencieux."""
        index = self.SILENCER_AMMO_INDEX.get(weapon_id)
        if index is None:
            return None
        addr = self.base + self.AMMO_TABLE_RVA + index * self.AMMO_ENTRY_SIZE + 0x10
        reserve, maximum = struct.unpack("<HH", self.proc.read_bytes(addr, 4))
        shots = maximum // self.SILENCER_MAX
        return (addr, reserve, shots) if shots else None

    def read_silencer_count(self, weapon_id: int) -> int | None:
        entry = self._silencer_reserve(weapon_id)
        if entry is None:
            return None
        _addr, reserve, shots = entry
        return -(-reserve // shots)

    def write_silencer_count(self, weapon_id: int, count: int) -> bool:
        """Ecrit `count` silencieux neufs."""
        entry = self._silencer_reserve(weapon_id)
        if entry is None:
            return False
        addr, _reserve, shots = entry
        count = max(0, min(count, self.SILENCER_MAX))
        self.proc.write_bytes(addr, struct.pack("<H", count * shots))
        self.refresh_weapon_custom_menu()
        return True

    # Accessoires montes (2026-10-09, valide en jeu, arme rangee ou en
    # main - le modele suit tout seul) : champ de bits u32 a +0x2C de
    # l'entree de l'arme (table WEAPON_TABLE_RVA ; getter 6A380, setter
    # 72A20 ; bit 0 = silencieux, teste par la fonction de tir). Bits
    # permis par arme : table fixe mgs4+1B00F34 + ID*0x38 (6A390), seuls
    # les bits 0-9 sont des accessoires. Le menu les range en 5
    # emplacements (masques mgs4+1848B20), un accessoire par emplacement.
    # Bit -> accessoire : 6E5F0, reproduit dans accessory_for_bit.
    WEAPON_ACCESSORIES_OFFSET = 0x2C
    WEAPON_ALLOWED_ACCESSORIES_RVA = 0x1B00F34
    WEAPON_ALLOWED_STRIDE = 0x38
    ACCESSORY_SLOTS = (
        ("silencer", 0x001), ("light", 0x100), ("laser", 0x200), ("optics", 0x006), ("underbarrel", 0x0F8),
    )
    SILENCER_BY_WEAPON = {0x03: 0x4D, 0x04: 0x4E, 0x0B: 0x4F, 0x13: 0x50, 0x14: 0x51, 0x18: 0x52, 0x2A: 0x53}
    ACCESSORY_BY_BIT = {0x004: 0x54, 0x010: 0x4A, 0x020: 0x5A, 0x040: 0x5B, 0x080: 0x59, 0x100: 0x57, 0x200: 0x58}
    LAUNCHER_BY_WEAPON = {0x18: 0x4B, 0x1F: 0x4B, 0x19: 0x4C, 0x1B: 0x4C}  # XM320 / GP-30
    # Armes avec au moins un emplacement (table fixe de l'exe 1.4.1).
    CUSTOMIZABLE_WEAPON_IDS = {0x03, 0x04, 0x06, 0x07, 0x0B, 0x0F, 0x11, 0x13, 0x14, 0x18, 0x19, 0x1B,
                               0x1E, 0x1F, 0x20, 0x23, 0x25, 0x2A, 0x2E}

    @classmethod
    def accessory_for_bit(cls, weapon_id: int, bit: int) -> int:
        """Accessoire du bit pour cette arme (0 = aucun), comme 6E5F0."""
        if bit == 0x001:
            return cls.SILENCER_BY_WEAPON.get(weapon_id, 0)
        if bit == 0x002:
            return 0x56 if weapon_id == 0x11 else 0x55  # point rouge MP7 / M4
        if bit == 0x008:
            return cls.LAUNCHER_BY_WEAPON.get(weapon_id, 0)
        return cls.ACCESSORY_BY_BIT.get(bit, 0)

    def _weapon_entry(self, weapon_id: int) -> int:
        return self.base + self.WEAPON_TABLE_RVA + weapon_id * self.WEAPON_TABLE_STRIDE

    def weapon_accessory_slots(self, weapon_id: int) -> list[tuple[str, int, list[tuple[int, int]]]]:
        """[(emplacement, masque, [(bit, accessoire), ...]), ...] permis
        pour cette arme, dans l'ordre du menu du jeu."""
        allowed = struct.unpack("<I", self.proc.read_bytes(
            self.base + self.WEAPON_ALLOWED_ACCESSORIES_RVA + weapon_id * self.WEAPON_ALLOWED_STRIDE, 4))[0]
        slots = []
        for slot, mask in self.ACCESSORY_SLOTS:
            choices = [(1 << k, self.accessory_for_bit(weapon_id, 1 << k))
                       for k in range(10) if mask & allowed & (1 << k)]
            choices = [(bit, acc) for bit, acc in choices if acc]
            if choices:
                slots.append((slot, mask, choices))
        return slots

    def read_weapon_accessories(self, weapon_id: int) -> int:
        return struct.unpack("<I", self.proc.read_bytes(
            self._weapon_entry(weapon_id) + self.WEAPON_ACCESSORIES_OFFSET, 4))[0]

    def set_weapon_accessory(self, weapon_id: int, slot_mask: int, bit: int) -> bool:
        """Monte l'accessoire `bit` (0 = aucun) dans l'emplacement."""
        if not (self.connected and self.sane):
            return False
        current = self.read_weapon_accessories(weapon_id)
        wanted = (current & ~slot_mask) | (bit & slot_mask)
        if wanted != current:
            self.proc.write_bytes(self._weapon_entry(weapon_id) + self.WEAPON_ACCESSORIES_OFFSET,
                                  struct.pack("<I", wanted))
            self.refresh_weapon_custom_menu()
        return True

    def read_all_weapon_accessories(self) -> dict[int, int]:
        """Accessoires montes (bits 0-9) de chaque arme personnalisable."""
        return {weapon_id: self.read_weapon_accessories(weapon_id) & 0x3FF
                for weapon_id in sorted(self.CUSTOMIZABLE_WEAPON_IDS)}

    def apply_weapon_accessories(self, wanted: dict[int, int]) -> bool:
        """Monte les accessoires d'un profil, selon ce que la partie permet :
        arme non possedee = ignoree ; accessoire du profil non possede = pas
        monte (l'emplacement garde l'actuel s'il est possede, sinon vide)."""
        if not (self.connected and self.sane):
            return False
        changed = False
        for weapon_id, wanted_mask in wanted.items():
            if weapon_id not in self.CUSTOMIZABLE_WEAPON_IDS or self.read_weapon(weapon_id) == 0:
                continue
            current = self.read_weapon_accessories(weapon_id)
            result = current
            for _slot, mask, choices in self.weapon_accessory_slots(weapon_id):
                owned = {bit for bit, accessory in choices if self.read_weapon(accessory) != 0}
                want = wanted_mask & mask
                want &= -want  # un seul accessoire par emplacement
                have = current & mask
                if want in owned:
                    new = want
                elif not want:
                    new = 0
                else:
                    new = have if have and (have & -have) in owned else 0
                result = (result & ~mask) | new
            if result != current:
                self.proc.write_bytes(self._weapon_entry(weapon_id) + self.WEAPON_ACCESSORIES_OFFSET,
                                      struct.pack("<I", result))
                changed = True
        if changed:
            self.refresh_weapon_custom_menu()
        return True

    def read_accessory_amount(self, weapon_id: int) -> int | None:
        """Colonne des accessoires : silencieux = nombre, sinon munitions."""
        if weapon_id in self.SILENCER_AMMO_INDEX:
            return self.read_silencer_count(weapon_id)
        return self.read_weapon_ammo(weapon_id)

    def write_accessory_amount(self, weapon_id: int, value: int) -> bool:
        if weapon_id in self.SILENCER_AMMO_INDEX:
            return self.write_silencer_count(weapon_id, value)
        return self.write_weapon_ammo(weapon_id, value)

    def read_weapon_magazine(self, weapon_id: int) -> int:
        """Munitions dans le chargeur (distinct de la reserve ci-dessus -
        se vide en tirant, declenche le rechargement a 0). Trouve le
        2026-09-26 par scan exact (7->5->3 confirme par l'utilisateur en
        tirant sur l'Operator, 4 candidats restants dont un seul dans la
        table d'etat des armes deja connue) : meme table que weapon_state_
        rva (WEAPON_MAGAZINE_OFFSET octets plus loin dans le meme struct
        par arme, stride 0x50) - formule non re-testee individuellement
        sur chaque arme, extrapolee de la formule d'etat deja confirmee
        fiable pour toutes."""
        return struct.unpack("<H", self.proc.read_bytes(self.base + weapon_state_rva(weapon_id)
                                                          + WEAPON_MAGAZINE_OFFSET, 2))[0]

    def write_weapon_magazine(self, weapon_id: int, value: int) -> None:
        self.proc.write_bytes(self.base + weapon_state_rva(weapon_id) + WEAPON_MAGAZINE_OFFSET,
                               struct.pack("<H", value & 0xFFFF))

    def read_weapon_magazine_max(self, weapon_id: int) -> int:
        return struct.unpack("<H", self.proc.read_bytes(self.base + weapon_state_rva(weapon_id)
                                                          + WEAPON_MAGAZINE_MAX_OFFSET, 2))[0]
