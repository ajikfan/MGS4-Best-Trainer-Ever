"""MGS4Live : jauges de vie et d'endurance du boss present."""
import struct
import time


class BossGaugeMixin:
    """Vie et endurance du boss de la zone (onglet Jauges)."""

    # Boss (2026-10-25) : l'exe garde les RTTI MSVC (nom de classe .?AVNOM@@
    # retrouve depuis la vtable : [vtable-8] = COL, dword COL+12 = RVA du
    # descripteur, nom a descripteur+0x10). Le boss est un objet de la liste
    # des taches en cours (tache+0x90, ou en place a tache+0xC0 pour les
    # Beauty), reconnu par le nom de sa classe. Son objet de vie (plugin de
    # degats NPC_PLG_DAMAGE ou propre a la classe, meme forme que celui des
    # soldats : vie +0x314, max +0x318, endurance +0x31C, max +0x320) est a
    # boss+0x1E8 et renvoie au boss en +0x8. Valide sur Raging Raven
    # (BOSS_RAVEN, 20000 / 20000) ; les autres noms de classe viennent des
    # RTTI, a confirmer boss par boss.
    BOSS_CLASSES = {
        "BOSS_RAVEN": "Raging Raven",
        "OCTOPUS": "Laughing Octopus",
        "BBC_WOLF": "Crying Wolf",
        "MANTIS": "Screaming Mantis",
        "BEAUTY": "Beauty",
        "VAMP": "Vamp",
        "OCELOT": "Liquid Ocelot",
        "RY_RAY": "Metal Gear RAY",
    }
    BOSS_TASK_POINTER = 0x90
    BOSS_TASK_INLINE = 0xC0
    BOSS_DAMAGE = 0x1E8
    BOSS_GAUGES = {"boss": 0x314, "boss_stamina": 0x31C}
    BOSS_SCAN_INTERVAL = 1.0
    # Barres du boss a l'ecran : le jeu ne les recopie qu'a un coup. Leur
    # structure (Raging Raven : pointee par boss+0x7E0) porte vie (max
    # +0x10C, valeur +0x110, puis affichage et trainee qui la rejoignent
    # seuls) et endurance (max +0x144, valeur +0x148). Valide en jeu : ecrire
    # la valeur fait bouger la barre. Retrouvee parmi les pointeurs des
    # BOSS_HUD_SCAN premiers octets du boss par ses deux maximums, egaux a
    # ceux de l'objet de vie.
    BOSS_HUD = {"boss": (0x10C, 0x110), "boss_stamina": (0x144, 0x148)}
    BOSS_HUD_SCAN = 0x1000

    def _rtti_name(self, vtable: int) -> str | None:
        """Nom de classe (sans .?AV ni @@) d'une vtable du module, sinon None."""
        cache = getattr(self, "_rtti_cache", None)
        if cache is None or cache.get(None) != self.base:
            cache = self._rtti_cache = {None: self.base}
        if vtable in cache:
            return cache[vtable]
        name = None
        if self.base < vtable < self.base + 0x2000000:
            try:
                locator = struct.unpack("<Q", self.proc.read_bytes(vtable - 8, 8))[0]
                if self.base < locator < self.base + 0x2000000:
                    descriptor = struct.unpack("<I", self.proc.read_bytes(locator + 12, 4))[0]
                    raw = self.proc.read_bytes(self.base + descriptor + 0x10, 64).split(b"\0")[0]
                    if raw.startswith(b".?AV") and raw.endswith(b"@@"):
                        name = raw[4:-2].decode("ascii", "replace")
            except OSError:
                name = None
        cache[vtable] = name
        return name

    def _boss_damage_valid(self, boss: int, damage: int) -> bool:
        try:
            vtable, owner = struct.unpack("<QQ", self.proc.read_bytes(damage, 16))
            life_max = struct.unpack("<i", self.proc.read_bytes(damage + 0x318, 4))[0]
        except OSError:
            return False
        name = self._rtti_name(vtable) or ""
        return owner == boss and name.endswith("PLG_DAMAGE") and life_max > 0

    def _boss_scan(self) -> tuple[str, int, int] | None:
        head = self.base + self.ZONE_TASK_LIST_RVA
        task = struct.unpack("<Q", self.proc.read_bytes(head + self.ZONE_TASK_NEXT, 8))[0]
        for _ in range(0x1000):
            if not task or task == head:
                break
            pointer = struct.unpack("<Q", self.proc.read_bytes(task + self.BOSS_TASK_POINTER, 8))[0]
            for boss in (pointer, task + self.BOSS_TASK_INLINE):
                try:
                    vtable = struct.unpack("<Q", self.proc.read_bytes(boss, 8))[0] if boss else 0
                except OSError:
                    continue
                name = self._rtti_name(vtable) if vtable else None
                if name in self.BOSS_CLASSES:
                    damage = struct.unpack("<Q", self.proc.read_bytes(boss + self.BOSS_DAMAGE, 8))[0]
                    if damage and self._boss_damage_valid(boss, damage):
                        return self.BOSS_CLASSES[name], boss, damage
            task = struct.unpack("<Q", self.proc.read_bytes(task + self.ZONE_TASK_NEXT, 8))[0]
        return None

    def _boss(self) -> tuple[str, int, int] | None:
        """(nom affiche, boss, objet de vie) du boss present, sinon None
        (nouvelle recherche au plus toutes les BOSS_SCAN_INTERVAL secondes)."""
        if not (self.connected and self.sane):
            return None
        found = getattr(self, "_boss_found", None)
        if found and found[3] == self.pid and self._boss_damage_valid(found[1], found[2]):
            return found[:3]
        if time.monotonic() - getattr(self, "_boss_scan_at", -1e9) < self.BOSS_SCAN_INTERVAL:
            return None
        self._boss_scan_at = time.monotonic()
        try:
            result = self._boss_scan()
        except OSError:
            result = None
        self._boss_found = (*result, self.pid) if result else None
        return result

    def _boss_hud_matches(self, hud: int, damage: int) -> bool:
        try:
            for gauge, (max_offset, _value) in self.BOSS_HUD.items():
                real_max = struct.unpack("<i", self.proc.read_bytes(damage + self.BOSS_GAUGES[gauge] + 4, 4))[0]
                if struct.unpack("<i", self.proc.read_bytes(hud + max_offset, 4))[0] != real_max or real_max <= 0:
                    return False
        except OSError:
            return False
        return True

    def _boss_hud(self, boss: int, damage: int) -> int:
        """Structure des barres du boss a l'ecran, 0 si introuvable."""
        cached = getattr(self, "_boss_hud_cache", (0, 0))
        if cached[0] == boss and cached[1] and self._boss_hud_matches(cached[1], damage):
            return cached[1]
        hud = 0
        try:
            data = self.proc.read_bytes(boss, self.BOSS_HUD_SCAN)
        except OSError:
            data = b""
        for offset in range(8, len(data), 8):
            pointer = struct.unpack_from("<Q", data, offset)[0]
            if 0x10000 < pointer < 0x7FF000000000 and pointer not in (boss, damage)                     and self._boss_hud_matches(pointer, damage):
                hud = pointer
                break
        self._boss_hud_cache = (boss, hud)
        return hud

    def boss_name(self) -> str | None:
        boss = self._boss()
        return boss[0] if boss else None

    def read_boss_gauge(self, gauge: str) -> int:
        """Valeur de la jauge `gauge` (BOSS_GAUGES) ; -1 sans boss."""
        boss = self._boss()
        if not boss:
            return -1
        return struct.unpack("<i", self.proc.read_bytes(boss[2] + self.BOSS_GAUGES[gauge], 4))[0]

    def boss_gauge_max(self, gauge: str) -> int | None:
        boss = self._boss()
        if not boss:
            return None
        return struct.unpack("<i", self.proc.read_bytes(boss[2] + self.BOSS_GAUGES[gauge] + 4, 4))[0] or None

    def write_boss_gauge(self, gauge: str, value: int) -> bool:
        """Ecrit la jauge, au moins 1 : vie ou endurance a 0 ecrite de
        l'exterieur laisse le boss dans un etat que le jeu ne traite pas (la
        mise a mort passe par Un coup, un mort)."""
        boss = self._boss()
        if not boss:
            return False
        value = struct.pack("<i", max(1, value))
        self.proc.write_bytes(boss[2] + self.BOSS_GAUGES[gauge], value)
        hud = self._boss_hud(boss[1], boss[2])
        if hud:
            self.proc.write_bytes(hud + self.BOSS_HUD[gauge][1], value)
        return True
