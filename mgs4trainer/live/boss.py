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
    # RTTI (BB + initiale du boss : BBC_WOLF bete de Crying Wolf, BBx_BTY
    # Beauty de chacun), a confirmer boss par boss.
    # BOSS_CLASSES : classe -> cle (boss_forme), voir BOSS_ROSTER de l'onglet Boss.
    BOSS_CLASSES = {
        "OCTOPUS": "octopus_beast", "BBL_BTY": "octopus_beauty",
        "BOSS_RAVEN": "raven_beast", "BBR_BTY": "raven_beauty",
        "BBC_WOLF": "wolf_beast", "BBC_BTY": "wolf_beauty",
        "MANTIS": "mantis_beast", "BBS_BTY": "mantis_beauty",
        "VAMP": "vamp", "RY_RAY": "ray", "OCELOT": "liquid",
    }
    BOSS_TASK_POINTER = 0x90
    BOSS_TASK_INLINE = 0xC0
    BOSS_DAMAGE = 0x1E8
    BOSS_GAUGES = {"life": 0x314, "stamina": 0x31C}
    BOSS_SCAN_INTERVAL = 1.0
    # Barres du boss a l'ecran : le jeu ne les recopie qu'a un coup. Leur
    # structure (Raging Raven : pointee par boss+0x7E0) porte vie (max
    # +0x10C, valeur +0x110, puis affichage et trainee qui la rejoignent
    # seuls) et endurance (max +0x144, valeur +0x148). Valide en jeu : ecrire
    # la valeur fait bouger la barre. Retrouvee par ses deux maximums, egaux a
    # ceux de l'objet de vie : parmi les pointeurs des BOSS_HUD_SCAN premiers
    # octets du boss, sinon dans BOSS_HUD_WINDOW octets de part et d'autre du
    # boss (Laughing Octopus : boss-0x4FA0, aucun pointeur depuis le boss).
    BOSS_HUD = {"life": (0x10C, 0x110), "stamina": (0x144, 0x148)}
    BOSS_HUD_SCAN = 0x1000
    BOSS_HUD_WINDOW = 0x40000
    # Plancher a 1 (2026-10-25, choix de l'utilisateur) pour les boss dont la
    # vie rythme des phases ou des scripts : vie ou endurance a 0 ecrite de
    # l'exterieur n'y est pas traitee comme un coup. Ailleurs, 0 = le coup
    # suivant l'acheve par le chemin normal du jeu.
    BOSS_FLOOR_ONE = {"octopus_beast", "mantis_beast", "vamp", "liquid"}

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
        """(cle, boss, objet de vie) du boss present, sinon None
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
        if not hud:
            hud = self._boss_hud_near(boss, damage)
        self._boss_hud_cache = (boss, hud)
        return hud

    def _boss_hud_near(self, boss: int, damage: int) -> int:
        """Structure des barres cherchee par sa forme autour du boss."""
        life_max, stamina_max = (struct.unpack("<i", self.proc.read_bytes(damage + self.BOSS_GAUGES[g] + 4, 4))[0]
                                 for g in ("life", "stamina"))
        if life_max <= 0 or stamina_max <= 0:
            return 0
        (life_at, _), (stamina_at, _) = self.BOSS_HUD["life"], self.BOSS_HUD["stamina"]
        pattern_gap = stamina_at - life_at
        start = boss - self.BOSS_HUD_WINDOW
        for chunk in range(start, boss + self.BOSS_HUD_WINDOW, 0x10000):
            try:
                data = self.proc.read_bytes(chunk, 0x10000 + pattern_gap + 4)
            except OSError:
                continue
            wanted = struct.pack("<i", life_max)
            index = data.find(wanted)
            while 0 <= index < 0x10000:
                if index % 4 == 0 and data[index + pattern_gap:index + pattern_gap + 4] == struct.pack("<i", stamina_max):
                    hud = chunk + index - life_at
                    if hud != damage - life_at and self._boss_hud_matches(hud, damage):
                        return hud
                index = data.find(wanted, index + 1)
        return 0

    def boss_key(self) -> str | None:
        """Cle (BOSS_CLASSES) du boss present, sinon None."""
        boss = self._boss()
        return boss[0] if boss else None

    def _boss_for(self, gauge: str) -> tuple[int, int, str] | None:
        """(boss, objet de vie, "life"/"stamina") si la jauge "boss:<cle>:<jauge>"
        est celle du boss present, sinon None."""
        _prefix, key, which = gauge.split(":")
        boss = self._boss()
        return (boss[1], boss[2], which) if boss and boss[0] == key else None

    def read_boss_gauge(self, gauge: str) -> int:
        """Valeur de la jauge "boss:<cle>:life|stamina" ; -1 si ce boss est absent."""
        found = self._boss_for(gauge)
        if not found:
            return -1
        return struct.unpack("<i", self.proc.read_bytes(found[1] + self.BOSS_GAUGES[found[2]], 4))[0]

    def boss_gauge_max(self, gauge: str) -> int | None:
        found = self._boss_for(gauge)
        if not found:
            return None
        return struct.unpack("<i", self.proc.read_bytes(found[1] + self.BOSS_GAUGES[found[2]] + 4, 4))[0] or None

    def write_boss_gauge(self, gauge: str, value: int) -> bool:
        """Ecrit la jauge (au moins 1 pour BOSS_FLOOR_ONE) et sa barre."""
        found = self._boss_for(gauge)
        if not found:
            return False
        boss, damage, which = found
        floor = 1 if gauge.split(":")[1] in self.BOSS_FLOOR_ONE else 0
        value = struct.pack("<i", max(floor, value))
        self.proc.write_bytes(damage + self.BOSS_GAUGES[which], value)
        hud = self._boss_hud(boss, damage)
        if hud:
            self.proc.write_bytes(hud + self.BOSS_HUD[which][1], value)
        return True
