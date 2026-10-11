"""MGS4Live : position de Snake, jauges du joueur et des vehicules, vitals."""
import struct

from mgs4trainer.core.gamedata import VITALS


class PlayerMixin:
    """Position de Snake, jauges du joueur et des vehicules, vitals."""

    # Position de Snake (2026-10-04) : entree joueur de la table des
    # joueurs du jeu (8DA180 : mgs4+23EB5160 + (indice+1)*0x80, indice a
    # mgs4+23EB5150), objet a +8, X/Y/Z (Y = hauteur) a +0x10 - la position
    # que le jeu utilise lui-meme (lumiere de l'indice de camouflage, 8A5C0).
    # Ecrire la deplace reellement (valide en jeu). Remplace le pointeur
    # capture par la DLL (install_coord_tracker_hook, routine de distance
    # appelee seulement dans certaines situations) qui restait sur l'ancien
    # Snake apres un changement d'acte (position a 0 au debut de l'acte 2).
    PLAYER_INDEX_RVA = 0x23EB5150
    PLAYER_TABLE_RVA = 0x23EB5160
    PLAYER_ENTRY_SIZE = 0x80

    def _player_transform(self) -> int | None:
        index = struct.unpack("<i", self.proc.read_bytes(self.base + self.PLAYER_INDEX_RVA, 4))[0]
        entry = self.base + self.PLAYER_TABLE_RVA + (index + 1) * self.PLAYER_ENTRY_SIZE
        transform = struct.unpack("<Q", self.proc.read_bytes(entry + 8, 8))[0]
        return transform or None

    def player_position(self) -> tuple[float, float, float] | None:
        """Position (X, Y, Z, floats) de Snake ; Y = hauteur (le jeu
        annule une position invalide sous le sol), X/Z le plan horizontal
        en coordonnees absolues."""
        if not (self.connected and self.sane):
            return None
        addr = self._player_transform()
        if not addr:
            return None
        return struct.unpack("<fff", self.proc.read_bytes(addr + 0x10, 12))

    def set_player_position(self, x: float, y: float, z: float) -> bool:
        if not (self.connected and self.sane):
            return False
        addr = self._player_transform()
        if not addr:
            return False
        self.proc.write_bytes(addr + 0x10, struct.pack("<fff", x, y, z))
        return True

    # Jauge de grip (2026-10-04) : composant du joueur (acteur joueur = 6
    # octets bas de [entree joueur], cf. _player_transform ; composant a
    # acteur+0x110, type reconnu a sa table de fonctions mgs4+18AF720).
    # Jauge = int32 a +0x1E8, valable si le bit 0 de +0x1F8 est actif
    # (suspendu) - c'est ce que renvoie au HUD le gestionnaire du message
    # 0x2D0011 (9776DC). Le HUD n'en garde qu'une copie (tache joueur
    # +0x86C) : l'ecrire n'avait aucun effet. Ecrire +0x1E8 tient la barre
    # pleine (valide en jeu). Elle part de 2000 et baisse plus ou moins
    # vite selon le stress.
    # Le meme composant porte l'oxygene (2026-10-04) : int32 a +0x1EC,
    # active par le bit 0x4 de +0x1F8 (message 0x2D0012, celui que le HUD
    # consulte en premier) ; baisse d'environ 90/s sous l'eau. Troisieme
    # jauge du meme modele (+0x1F0, bit 0x10, message 0x2D0013) non
    # identifiee.
    GRIP_COMPONENT_OFFSET = 0x110
    GRIP_COMPONENT_VTABLE_RVA = 0x18AF720
    PLAYER_GAUGE_STATE_OFFSET = 0x1F8
    PLAYER_GAUGES = {"grip": (0x1E8, 0x1), "oxygen": (0x1EC, 0x4)}

    def _grip_component(self) -> int | None:
        index = struct.unpack("<i", self.proc.read_bytes(self.base + self.PLAYER_INDEX_RVA, 4))[0]
        entry = self.base + self.PLAYER_TABLE_RVA + (index + 1) * self.PLAYER_ENTRY_SIZE
        actor = struct.unpack("<Q", self.proc.read_bytes(entry, 8))[0] & 0xFFFFFFFFFFFF
        if not actor:
            return None
        component = struct.unpack("<Q", self.proc.read_bytes(actor + self.GRIP_COMPONENT_OFFSET, 8))[0]
        if not component:
            return None
        vtable = struct.unpack("<Q", self.proc.read_bytes(component, 8))[0]
        return component if vtable == self.base + self.GRIP_COMPONENT_VTABLE_RVA else None

    # Vehicule du joueur (2026-10-10, valide en jeu) : case dediee
    # mgs4+23F81090 -> composant ; vie int32 a composant+0x128, max +0x12C.
    # Drebin 893 (acte 2, vtable mgs4+18EB690, 6500, rappel de collision
    # 102F250) et van de l'acte 3 (vtable mgs4+18EB748, 6000). La jauge du
    # HUD n'en est qu'une copie (10302C5 -> 14D4020).
    VEHICLE_PTR_RVA = 0x23F81090
    VEHICLE_COMPONENT_VTABLE_RVAS = {"drebin": 0x18EB690, "van": 0x18EB748}
    VEHICLE_HP_OFFSET = 0x128

    def _vehicle_component(self, gauge: str) -> int | None:
        """Composant du vehicule `gauge` ("drebin", "van") s'il est actif."""
        component = struct.unpack("<Q", self.proc.read_bytes(self.base + self.VEHICLE_PTR_RVA, 8))[0]
        if not component:
            return None
        vtable = struct.unpack("<Q", self.proc.read_bytes(component, 8))[0]
        return component if vtable == self.base + self.VEHICLE_COMPONENT_VTABLE_RVAS[gauge] else None

    def player_gauge_max(self, gauge: str) -> int | None:
        """Maximum reel d'une jauge quand le jeu le stocke (Drebin 893)."""
        if gauge not in self.VEHICLE_COMPONENT_VTABLE_RVAS or not (self.connected and self.sane):
            return None
        component = self._vehicle_component(gauge)
        if component is None:
            return None
        return struct.unpack("<i", self.proc.read_bytes(component + self.VEHICLE_HP_OFFSET + 4, 4))[0] or None

    def read_player_gauge(self, gauge: str) -> int | None:
        """Jauge du joueur (PLAYER_GAUGES) quand elle est active (suspendu,
        sous l'eau, dans le Drebin 893) ; -1 sinon, None si introuvable."""
        if not (self.connected and self.sane):
            return None
        if gauge in self.VEHICLE_COMPONENT_VTABLE_RVAS:
            component = self._vehicle_component(gauge)
            if component is None:
                return -1
            return struct.unpack("<i", self.proc.read_bytes(component + self.VEHICLE_HP_OFFSET, 4))[0]
        component = self._grip_component()
        if component is None:
            return None
        offset, bit = self.PLAYER_GAUGES[gauge]
        value, = struct.unpack("<i", self.proc.read_bytes(component + offset, 4))
        state, = struct.unpack("<I", self.proc.read_bytes(component + self.PLAYER_GAUGE_STATE_OFFSET, 4))
        return value if state & bit else -1

    def write_player_gauge(self, gauge: str, value: int) -> bool:
        if not (self.connected and self.sane):
            return False
        if gauge in self.VEHICLE_COMPONENT_VTABLE_RVAS:
            component = self._vehicle_component(gauge)
            if component is None:
                return False
            self.proc.write_bytes(component + self.VEHICLE_HP_OFFSET, struct.pack("<i", value))
            return True
        component = self._grip_component()
        if component is None:
            return False
        self.proc.write_bytes(component + self.PLAYER_GAUGES[gauge][0], struct.pack("<i", value))
        return True

    def read_vital(self, name: str) -> int:
        offset, _max_offset, size, _fixed_max = VITALS[name]
        return int.from_bytes(self.proc.read_bytes(self.linkvarbuf + offset, size), "little")

    def write_vital(self, name: str, value: int) -> None:
        offset, _max_offset, size, _fixed_max = VITALS[name]
        max_value = (1 << (size * 8)) - 1
        self.proc.write_bytes(self.linkvarbuf + offset, (value & max_value).to_bytes(size, "little"))

    def read_vital_max(self, name: str) -> int:
        """Valeur max (live si un offset dedie existe, sinon la borne fixe
        de VITALS - ex. Stress, toujours 0-1000)."""
        _offset, max_offset, size, fixed_max = VITALS[name]
        if max_offset is None:
            return fixed_max
        return int.from_bytes(self.proc.read_bytes(self.linkvarbuf + max_offset, size), "little")

    def read_vital_percent(self, name: str) -> float:
        maxi = self.read_vital_max(name)
        return (self.read_vital(name) / maxi * 100) if maxi else 0.0

    def write_vital_percent(self, name: str, percent: float) -> None:
        maxi = self.read_vital_max(name)
        self.write_vital(name, round(maxi * percent / 100))
