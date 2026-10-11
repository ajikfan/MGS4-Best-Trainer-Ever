"""MGS4Live : statistiques, difficulte, lieu, points Drebin."""
import re
import struct

import mgs4save

from mgs4trainer.core.gamedata import special_item_equipped_rva


class GameStateMixin:
    """Statistiques, difficulte, lieu, points Drebin."""

    def read_special_item_equipped(self) -> int:
        return struct.unpack("<H", self.proc.read_bytes(self.base + special_item_equipped_rva(), 2))[0]

    def write_special_item_equipped(self, item_id: int) -> None:
        self.proc.write_bytes(self.base + special_item_equipped_rva(), struct.pack("<H", item_id & 0xFFFF))

    def read_stat(self, name: str) -> int:
        """Lit un champ de mgs4save.STATS via linkvarbuf (meme offset que
        le fichier de save, format u16 ou u32 selon l'entree). Fiabilite
        en lecture ET ecriture confirmee individuellement seulement pour
        drebin_actuel (2026-09-23) - les autres champs sont exposes pour
        exploration/test, pas encore verifies un par un."""
        offset, fmt = mgs4save.STATS[name]
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.proc.read_bytes(self.linkvarbuf + offset, size))[0]

    def write_stat(self, name: str, value: int) -> None:
        offset, fmt = mgs4save.STATS[name]
        size = struct.calcsize(fmt)
        max_value = (1 << (size * 8)) - 1
        self.proc.write_bytes(self.linkvarbuf + offset, struct.pack(fmt, value & max_value))

    # Difficulte (2026-10-04) : linkvarbuf+0x6 = score s16 (20/30/35/40/50,
    # meme valeur que METADATA.SAV 0x30, voir mgs4save.DIFFICULTY_NAMES).
    # Trouve via la sauvegarde : 4B1730 recopie [lv+6] dans la structure
    # ecrite sur disque. Ecrire 35 puis sauvegarder donne SOLID NORMAL.
    DIFFICULTY_OFFSET = 0x6

    # Lieu actuel (2026-10-04) : linkvarbuf reprend la disposition de
    # MGS4.SAV (mgs4save.read_progress_info) - code de stage ASCII a +0x34
    # (ex. "s01a50l"), progression u32 a +0x54 (-> acte, ACT_RANGES).
    STAGE_CODE_OFFSET = 0x34
    PROGRESS_OFFSET = 0x54

    def read_location(self) -> tuple[str, int] | None:
        """(code de stage, progression), None si illisible."""
        raw = self.proc.read_bytes(self.linkvarbuf + self.STAGE_CODE_OFFSET, 8)
        code = raw.split(b"\0")[0].decode("ascii", errors="replace")
        if not re.fullmatch(r"s\d\da\d\d\w", code):
            return None
        progress = struct.unpack("<I", self.proc.read_bytes(self.linkvarbuf + self.PROGRESS_OFFSET, 4))[0]
        return code, progress

    def read_difficulty(self) -> int:
        return struct.unpack("<h", self.proc.read_bytes(self.linkvarbuf + self.DIFFICULTY_OFFSET, 2))[0]

    def write_difficulty(self, score: int) -> bool:
        if not (self.connected and self.sane) or score not in mgs4save.DIFFICULTY_NAMES:
            return False
        self.proc.write_bytes(self.linkvarbuf + self.DIFFICULTY_OFFSET, struct.pack("<h", score))
        return True

    # Points Drebin : "actuel" (solde depensable) et "total_ventes" (cumul
    # historique) sont deux champs distincts de STATS, confirmes fiables
    # (2026-09-23) via linkvarbuf. Invariant impose ici a la demande de
    # l'utilisateur (pas necessairement la logique exacte du jeu, mais une
    # garde-fou d'edition sensee) : actuel >= total_ventes toujours, aucun
    # des deux negatif. Modifier total_ventes repercute la meme difference
    # sur actuel (gagner plus de ventes historiques augmente d'autant le
    # solde courant).
    def read_drebin_actuel(self) -> int:
        return self.read_stat("drebin_actuel")

    def read_drebin_total_ventes(self) -> int:
        return self.read_stat("drebin_total_ventes")

    def write_drebin_actuel(self, value: int) -> bool:
        """False sans rien ecrire si value < total_ventes ou < 0."""
        if value < 0 or value < self.read_stat("drebin_total_ventes"):
            return False
        self.write_stat("drebin_actuel", value)
        return True

    def write_drebin_total_ventes(self, value: int) -> bool:
        """False sans rien ecrire si value < 0 ou si la repercussion sur
        actuel le ferait passer sous 0."""
        if value < 0:
            return False
        old_ventes = self.read_stat("drebin_total_ventes")
        new_actuel = self.read_stat("drebin_actuel") + (value - old_ventes)
        if new_actuel < 0:
            return False
        self.write_stat("drebin_total_ventes", value)
        self.write_stat("drebin_actuel", new_actuel)
        return True
