"""MGS4Live : jauges de vie et d'endurance du boss present."""
import math
import struct
import threading
import time

from mgs4trainer.core.winproc import MEM_COMMIT, PAGE_EXECUTE_READWRITE, kernel32


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
    # vie rythme des phases ou des scripts non encore maitrises : jauge a 0 =
    # pas d'achevement (boss_kill). Ailleurs, 0 = achevement par un tir de
    # Snake (bete d'Octopus : phases sautees d'abord, voir _boss_skip_phases).
    BOSS_FLOOR_ONE = {"mantis_beast", "vamp", "liquid"}

    # Toucher le boss (2026-10-25) : une jauge mise a 0 de l'exterieur n'a
    # aucun effet avant un coup (le jeu ne juge la vie qu'a un impact), et le
    # code des coups des Beauty (1172930) ignore tout coup si vie, endurance
    # ou sommeil est deja <= 0. B88260 (methode 3 de NPC_PLG_DAMAGE, appelee
    # a chaque image) efface puis reconstruit le coup en cours depuis les
    # impacts reels : on l'enveloppe. Apres elle :
    #  - enregistrement : si l'objet de vie est celui de la place +0x40 et
    #    porte un vrai coup, ce coup (+0x80 a +0x170) est copie dans le
    #    modele (+0x200), drapeau +0x48 ;
    #  - toucher : si l'objet de vie figure dans les BOSS_TOUCH_SLOTS places,
    #    la place est liberee et un coup y est pose : le modele (par defaut
    #    BOSS_TOUCH_MODEL_DATA ; sans lui, les seuls champs recopies en
    #    "dernier coup", BOSS_TOUCH_HIT, ne font aucun degat), projectile
    #    +0xD0 efface, attaquant +0xC8 = entree du joueur (8DA180), +0x68 bit 0.
    # Bloc : places (+0x00), magie (+0x20), rax sauve (+0x28), prologue
    # deplace (+0x30), enregistrement (+0x40), modele pret (+0x48),
    # surveillance (+0x50 : objet de vie dont les impacts sont comptes en
    # +0x58, voir mantis_one_hit_tick), code (+0x60), modele (+0x200).
    BOSS_TOUCH_RVA = 0xB88260
    BOSS_TOUCH_PROLOGUE = bytes.fromhex("4053574155" "4883ec60")  # push rbx/rdi/r13 ; sub rsp,60
    BOSS_TOUCH_MAGIC = b"MGS4TCH4"
    BOSS_TOUCH_CODE = 0x60
    BOSS_TOUCH_OLD_CODE = (0x40,)  # versions precedentes (code a +0x40)
    BOSS_TOUCH_SLOTS = 4
    BOSS_TOUCH_MODEL = (0x200, 0x80, 0xF0)  # (place dans le bloc, debut du coup, taille)
    # Modele par defaut : vrai tir de pistolet enregistre sur la Beauty de
    # Laughing Octopus (630 degats), attaquant et projectile effaces.
    BOSS_TOUCH_MODEL_DATA = bytes.fromhex(
        "00000000000000000b0000009600000003000000000000000000000000000000"
        "96bf2d47e4297744a3f577490000000000000000b88680440000000000000000"
        "e803500000000000000000000000000000000000000000000000000000000000"
        "020000000000004000000000000000002e7b34470bb4c544fa4779490000803f"
        "000000000000000011000000030200105e010000000000000000000000000000"
        "ca102d473ad467449ad377490000803f1668033ff90bef3ee657383f04000000"
        "80361cc40c525bc3005cf3c460020000c2929bbe286cdabdea5c72bf00000000"
        "00000000000000000000000000000000"
    )
    BOSS_PLAYER_ENTRY = (0x8DA180, "8b05caaf5d23488d0dd3af5d23ffc048")
    BOSS_TOUCH_HIT = ((0x108, 4), (0x10C, 0x10000203), (0x110, 0x15E), (0xC0, 0x5003E8),
                      (0x88, 1), (0x8C, 0x96), (0x1A8, 0x40021E), (0x160, 0))

    def _boss_touch_code(self, block: int, player_entry: int) -> bytes:
        site = self.base + self.BOSS_TOUCH_RVA

        def rel(end: int, target: int) -> bytes:
            return struct.pack("<i", target - end)
        code_at, save = block + self.BOSS_TOUCH_CODE, block + 0x28
        record, ready = block + 0x40, block + 0x48
        model_at, hit_start, hit_size = self.BOSS_TOUCH_MODEL
        model = block + model_at
        code = bytearray()
        labels, fixups = {}, []

        def emit(raw: bytes, rip_target: int | None = None, tail: bytes = b""):
            # instruction rip-relative : opcode + disp32 (+ tail) ; disp calcule sur la fin
            if rip_target is None:
                code.extend(raw)
            else:
                end = code_at + len(code) + len(raw) + 4 + len(tail)
                code.extend(raw + rel(end, rip_target) + tail)

        def jump(opcode: int, label: str):  # saut court vers une etiquette
            code.extend(bytes([opcode, 0]))
            fixups.append((len(code) - 1, label))

        def mark(label: str):
            labels[label] = len(code)

        def copy(source_rip: int | None, destination_rip: int | None):
            # rep movsb de hit_size octets entre l'objet de vie (rcx) et le modele
            emit(bytes.fromhex("5657"))                                         # push rsi ; push rdi
            if source_rip is None:
                emit(bytes.fromhex("488db1") + struct.pack("<I", hit_start))    # lea rsi,[rcx+debut]
            else:
                emit(bytes.fromhex("488d35"), source_rip)                       # lea rsi,[modele]
            if destination_rip is None:
                emit(bytes.fromhex("488db9") + struct.pack("<I", hit_start))    # lea rdi,[rcx+debut]
            else:
                emit(bytes.fromhex("488d3d"), destination_rip)                  # lea rdi,[modele]
            emit(bytes.fromhex("51b9") + struct.pack("<I", hit_size) + bytes.fromhex("f3a4595f5e"))
            # push rcx ; mov ecx,taille ; rep movsb ; pop rcx ; pop rdi ; pop rsi

        emit(bytes.fromhex("514883ec20"))                                  # push rcx ; sub rsp,20
        emit(bytes.fromhex("e8"), block + 0x30)                            # call prologue deplace
        emit(bytes.fromhex("4883c42059"))                                  # add rsp,20 ; pop rcx
        emit(bytes.fromhex("488905"), save)                                # mov [sauve],rax
        emit(bytes.fromhex("483b0d"), record)                              # cmp rcx,[enregistrement]
        jump(0x75, "watch")
        emit(bytes.fromhex("f74168b72fe301"))                              # test [rcx+68],coups
        jump(0x75, "record")
        emit(bytes.fromhex("83796c00"))                                    # cmp dword [rcx+6c],0
        jump(0x74, "watch")
        mark("record")
        copy(None, model)
        emit(bytes.fromhex("48c705"), record, struct.pack("<I", 0))        # enregistrement libere
        emit(bytes.fromhex("48c705"), ready, struct.pack("<I", 1))         # modele pret
        mark("watch")
        emit(bytes.fromhex("483b0d"), block + 0x50)                        # cmp rcx,[surveillance]
        jump(0x75, "slots")
        emit(bytes.fromhex("f74168b72fe301"))                              # test [rcx+68],coups
        jump(0x75, "count")
        emit(bytes.fromhex("83796c00"))                                    # cmp dword [rcx+6c],0
        jump(0x74, "slots")
        mark("count")
        emit(bytes.fromhex("48ff05"), block + 0x58)                        # inc qword [impacts]
        mark("slots")
        for slot in range(self.BOSS_TOUCH_SLOTS):
            emit(bytes.fromhex("483b0d"), block + 8 * slot)                 # cmp rcx,[place]
            jump(0x75, f"next{slot}")
            emit(bytes.fromhex("48c705"), block + 8 * slot, struct.pack("<I", 0))  # place liberee
            jump(0xEB, "inject")
            mark(f"next{slot}")
        emit(bytes.fromhex("488b05"), save)                                # mov rax,[sauve]
        emit(bytes.fromhex("c3"))
        mark("inject")
        emit(bytes.fromhex("534889cb4883ec20"))                            # push rbx ; mov rbx,rcx ; sub rsp,20
        emit(bytes.fromhex("48833d"), ready, bytes(1))                     # cmp qword [pret],0
        jump(0x74, "default")
        copy(model, None)
        jump(0xEB, "common")
        mark("default")
        for offset, value in self.BOSS_TOUCH_HIT:
            emit(bytes.fromhex("c783") + struct.pack("<II", offset, value))  # mov dword [rbx+off],valeur
        mark("common")
        emit(bytes.fromhex("48c783d000000000000000"))                      # projectile efface
        emit(bytes.fromhex("48b8") + struct.pack("<Q", player_entry) + bytes.fromhex("ffd0"))
        emit(bytes.fromhex("488b00488983c8000000"))                        # attaquant = Snake
        emit(bytes.fromhex("834b6801"))                                    # or [rbx+68],1
        emit(bytes.fromhex("4883c4205b"))                                  # add rsp,20 ; pop rbx
        emit(bytes.fromhex("488b05"), save)                                # mov rax,[sauve]
        emit(bytes.fromhex("c3"))
        for at, label in fixups:
            distance = labels[label] - (at + 1)
            if not -128 <= distance <= 127:
                raise ValueError(label)
            code[at] = distance & 0xFF
        trampoline = self.BOSS_TOUCH_PROLOGUE + bytes.fromhex("e9") + rel(
            block + 0x30 + len(self.BOSS_TOUCH_PROLOGUE) + 5, site + len(self.BOSS_TOUCH_PROLOGUE))
        head = (bytes(8 * self.BOSS_TOUCH_SLOTS) + self.BOSS_TOUCH_MAGIC + bytes(8)
                + trampoline.ljust(0x10, bytes.fromhex("cc")) + bytes(8) + struct.pack("<Q", 1) + bytes(0x10))
        body = head + bytes(code)
        if len(body) > model_at:
            raise ValueError("code du detour trop long")
        return body.ljust(model_at, bytes(1)) + self.BOSS_TOUCH_MODEL_DATA

    def _boss_touch_block(self) -> int:
        """Bloc du detour de B88260 (pose une fois par processus, retrouve
        apres un redemarrage du trainer ; un bloc d'une version precedente est
        remplace par un nouveau), 0 si impossible."""
        cache = getattr(self, "_boss_touch_cache", (0, None))
        if cache[1] == self.pid and cache[0]:
            return cache[0]
        site = self.base + self.BOSS_TOUCH_RVA
        current = self.proc.read_bytes(site, len(self.BOSS_TOUCH_PROLOGUE))
        block = 0
        if current[0] == 0xE9:
            target = site + 5 + struct.unpack_from("<i", current, 1)[0]
            known = False
            for code_offset in (self.BOSS_TOUCH_CODE, *self.BOSS_TOUCH_OLD_CODE):
                try:
                    magic = self.proc.read_bytes(target - code_offset + 0x20, 8)
                except OSError:
                    continue
                if magic.startswith(b"MGS4TCH"):
                    known = True
                    if magic == self.BOSS_TOUCH_MAGIC and code_offset == self.BOSS_TOUCH_CODE:
                        block = target - code_offset
                    break
            if not known:
                return 0
        elif current != self.BOSS_TOUCH_PROLOGUE:
            return 0
        if not block:
            funcs = self._live_funcs({"player_entry": self.BOSS_PLAYER_ENTRY})
            block = self.proc.alloc_near(site) if funcs else 0
            if not block:
                return 0
            self.proc.write_bytes(block, self._boss_touch_code(block, funcs["player_entry"]))
            jump = struct.pack("<i", block + self.BOSS_TOUCH_CODE - (site + 5))
            if current[0] == 0xE9:
                self.proc.write_bytes(site + 1, jump)  # une seule ecriture de 4 octets
            else:
                self.proc.write_bytes(site, bytes.fromhex("e9") + jump
                                      + bytes.fromhex("90") * (len(self.BOSS_TOUCH_PROLOGUE) - 5))
        self._boss_touch_cache = (block, self.pid)
        return block

    def boss_record_hit(self, gauge: str) -> bool:
        """Le prochain vrai coup recu par le boss de la jauge servira de
        modele aux coups du trainer."""
        found = self._boss_for(gauge)
        block = self._boss_touch_block() if found else 0
        if not block:
            return False
        self.proc.write_bytes(block + 0x40, struct.pack("<Q", found[1]))
        return True

    def boss_hit_model_ready(self) -> bool:
        block = self._boss_touch_block()
        return bool(block) and struct.unpack("<Q", self.proc.read_bytes(block + 0x48, 8))[0] != 0

    def boss_touch(self, gauge: str) -> bool:
        """Fait toucher le boss de la jauge "boss:<cle>:..." par Snake a
        l'image suivante (le jeu juge alors vie et endurance)."""
        found = self._boss_for(gauge)
        if not found:
            return False
        block = self._boss_touch_block()
        if not block:
            return False
        slots = struct.unpack(f"<{self.BOSS_TOUCH_SLOTS}Q", self.proc.read_bytes(block, 8 * self.BOSS_TOUCH_SLOTS))
        damage = found[1]
        if damage in slots:
            return True
        if 0 not in slots:
            return False
        self.proc.write_bytes(block + 8 * slots.index(0), struct.pack("<Q", damage))
        return True

    # Achever le boss depuis l'onglet (2026-10-25) : un coup ordinaire ne fait
    # pas descendre une Beauty sous 2 % de sa vie max (1173D5E), les autres
    # boss ont leurs paliers ; seul le chemin "mise a mort" passe outre, celui
    # que pose Un coup, un mort (CODE_PATCHES["boss_one_shot_kill"]). Vie a
    # BOSS_KILL_LIFE du max (le code des coups ignore un boss deja a 0, et
    # sous 2 % il ramene les degats a presque rien), patch pose le temps du
    # coup s'il ne l'etait pas, coup de Snake (boss_touch), puis patch remis.
    # Valide sur la Beauty de Laughing Octopus (elle meurt).
    BOSS_KILL_LIFE = 0.05
    BOSS_KILL_TIMEOUT = 10.0

    def _code_patch_applied(self, name: str) -> bool:
        for rva, original, patch in self.CODE_PATCHES[name]:
            if self.proc.read_bytes(self.base + rva, len(patch)) != patch:
                return False
        return True

    # Beauty dans la salle blanche (2026-10-25) : machine 0 du script dans
    # l'etat 4 ; le code des coups (1172A91) n'y applique les degats que si
    # Beauty+0x68 vaut 0x60 (releve sur de vrais tirs : seuls ceux portes
    # quand elle est dans sa phase vulnerable comptent). Le temps du coup du
    # trainer, ce test est saute (jne 1172A99 -> jmp), demande utilisateur :
    # la jauge a 0 l'acheve quelle que soit sa phase. Meme chose pour l'etat
    # 0xB de la machine 0 (coups ignores, je 1172AB2 -> nop ; un premier essai
    # dans l'arene n'avait rien fait).
    BOSS_KILL_FORCE = ((0x1172A99, bytes.fromhex("750a837b68600f85"), bytes.fromhex("eb")),
                       (0x1172AB2, bytes.fromhex("0f84920800008b87"), bytes.fromhex("909090909090")))

    def _boss_kill_force(self, enabled: bool) -> None:
        for rva, original, patch in self.BOSS_KILL_FORCE:
            current = self.proc.read_bytes(self.base + rva, len(original))
            wanted = patch + original[len(patch):] if enabled else original
            if current in (original, patch + original[len(patch):]) and current != wanted:
                self.proc.write_bytes(self.base + rva, wanted[:len(patch)])

    # Jauge relachee a 0 : vie -> mise a mort (patch Letal), endurance -> K.O.
    # (patch Non letal : tout coup passe par le chemin endurance et la vide).
    # Les deux patchs modifient le meme site (1173BC7) : l'oppose est retire
    # le temps du coup, puis chacun retrouve son etat d'avant.
    BOSS_FINISH_PATCHES = {"life": ("boss_one_shot_kill", "boss_non_lethal_kill"),
                           "stamina": ("boss_non_lethal_kill", "boss_one_shot_kill")}

    def boss_kill(self, gauge: str) -> bool:
        """Acheve le boss de la jauge "boss:<cle>:life" (mort) ou
        "boss:<cle>:stamina" (K.O.) par le chemin du jeu (fil a part : un coup
        de Snake a la fois, jusqu'au resultat ou BOSS_KILL_TIMEOUT) ; faux si
        impossible."""
        found = self._boss_for(gauge)
        key = gauge.split(":")[1]
        if not found or key in self.BOSS_FLOOR_ONE or getattr(self, "_boss_killing", False):
            return False
        boss, damage, which = found
        block = self._boss_touch_block()
        if not block:
            return False
        if key == "octopus_beast":
            self._boss_skip_phases(boss)  # sinon le coup s'arrete au palier de la phase
        wanted_patch, opposite_patch = self.BOSS_FINISH_PATCHES[which]
        initial = {name: self._code_patch_applied(name) for name in (wanted_patch, opposite_patch)}
        offset = self.BOSS_GAUGES[which]
        gauge_max = struct.unpack("<i", self.proc.read_bytes(damage + offset + 4, 4))[0]
        finish_value = max(2, math.ceil(gauge_max * self.BOSS_KILL_LIFE))
        # Le curseur a pu mettre la jauge a 0 en glissant : le jeu ignorerait
        # le coup (et la boucle croirait le resultat atteint). La barre a
        # l'ecran reste a 0 (le jeu la recopie au coup).
        self.write_boss_gauge(gauge, finish_value, hud=False)
        self._boss_killing = True
        self.boss_finishing = gauge  # l'onglet affiche 0 pendant l'achevement

        def pending() -> bool:
            slots = struct.unpack(f"<{self.BOSS_TOUCH_SLOTS}Q", self.proc.read_bytes(block, 8 * self.BOSS_TOUCH_SLOTS))
            return damage in slots

        def run():
            try:
                started = time.monotonic()
                while time.monotonic() - started < self.BOSS_KILL_TIMEOUT:
                    if self._boss_for(gauge) is None:
                        break  # boss parti (mort, cinematique)
                    value = struct.unpack("<i", self.proc.read_bytes(damage + offset, 4))[0]
                    if value <= 0:
                        break
                    if pending():
                        time.sleep(0.01)
                        continue
                    self._boss_kill_force(True)
                    if self._code_patch_applied(opposite_patch):
                        self.set_code_patch(opposite_patch, False)  # meme site : retire le temps du coup
                    if not self._code_patch_applied(wanted_patch):
                        self.set_code_patch(wanted_patch, True)
                    if value > finish_value:
                        self.write_boss_gauge(gauge, finish_value, hud=False)
                    self.boss_touch(gauge)
                    time.sleep(0.1)  # coup consomme puis traite a l'image suivante
                if pending():
                    slots = struct.unpack(f"<{self.BOSS_TOUCH_SLOTS}Q",
                                          self.proc.read_bytes(block, 8 * self.BOSS_TOUCH_SLOTS))
                    self.proc.write_bytes(block + 8 * slots.index(damage), bytes(8))  # coup annule
                time.sleep(0.1)
            except OSError:
                pass
            finally:
                try:
                    self._boss_kill_force(False)
                    for name in (wanted_patch, opposite_patch):  # l'un apres l'autre : meme site
                        if not initial[name] and self._code_patch_applied(name):
                            self.set_code_patch(name, False)
                    for name in (wanted_patch, opposite_patch):
                        if initial[name] and not self._code_patch_applied(name):
                            self.set_code_patch(name, True)
                except OSError:
                    pass
                self.boss_finishing = None
                self._boss_killing = False
        threading.Thread(target=run, daemon=True).start()
        return True

    # Un coup, un mort sur la bete de Laughing Octopus (2026-10-25, valide :
    # premier tir -> vie a 0, machine 0 du script en etat 6 = defaite, puis la
    # Beauty). 1435110 bloque la vie au palier de la premiere phase non jouee
    # (drapeaux +0x267D0, +0x267D4, +0x267D8/+0x267E0, +0x267DC, +0x43F8 ;
    # paliers 7200, 6000, 4800, 3600, 2400) et chaque palier lance une
    # transition scriptee. Toutes les phases marquees jouees : aucun palier,
    # le jeu enchaine sa propre fin de combat.
    OCTOPUS_PHASE_FLAGS = ((0x267D0, 5), (0x43F8, 1))

    def boss_one_hit_tick(self, one_hit: bool) -> None:
        """A appeler souvent : Un coup, un mort sur les boss a phases."""
        if not one_hit:
            return
        boss = self._boss()
        if boss and boss[0] == "octopus_beast":
            self._boss_skip_phases(boss[1])

    def _boss_skip_phases(self, boss: int) -> None:
        """Phases de la bete de Laughing Octopus marquees jouees."""
        for offset, count in self.OCTOPUS_PHASE_FLAGS:
            wanted = struct.pack(f"<{count}i", *[1] * count)
            if self.proc.read_bytes(boss + offset, 4 * count) != wanted:
                self.proc.write_bytes(boss + offset, wanted)

    # Ficelles de Screaming Mantis : composant PL_PLG_MANTIS de Snake, dans la
    # liste des composants du joueur (tete au composant joueur +0x1F50,
    # suivant +0x08) ; drapeau "attache" +0x60 bit 0 (voir CODE_PATCHES
    # "untouchable"). L'effacer fait comme la seringue (seul champ change).
    MANTIS_STRINGS_VTABLE_RVA = 0x1904DA0
    PLAYER_PLUGIN_HEAD = 0x1F50
    MANTIS_STRINGS_FLAG = (0x60, 1)

    def mantis_strings_tick(self, free: bool) -> None:
        """A appeler souvent : avec Intouchable, Snake ne reste pas attache
        par les ficelles de Mantis."""
        if not free:
            return
        component = self._grip_component()
        plugin = struct.unpack("<Q", self.proc.read_bytes(component + self.PLAYER_PLUGIN_HEAD, 8))[0] if component else 0
        vtable = self.base + self.MANTIS_STRINGS_VTABLE_RVA
        for _ in range(64):
            if not plugin:
                return
            if struct.unpack("<Q", self.proc.read_bytes(plugin, 8))[0] == vtable:
                offset, bit = self.MANTIS_STRINGS_FLAG
                flags = struct.unpack("<I", self.proc.read_bytes(plugin + offset, 4))[0]
                if flags & bit:
                    self.proc.write_bytes(plugin + offset, struct.pack("<I", flags & ~bit))
                return
            plugin = struct.unpack("<Q", self.proc.read_bytes(plugin + 8, 8))[0]

    # Un coup, un mort sur Screaming Mantis (2026-10-25) : ses balles ne lui
    # font rien, seule la poupee Mantis secouee dans sa phase (etat 0x2BD)
    # retire de l'endurance (mise a jour F08CF0). Sa defaite est le bloc
    # F0903E-F0917B : endurance 0, message 0x1E001C au joueur, vitesse de
    # chute (+0x5810, +0x57C0..+0x57E0, +0x5820), animation EE9690, ralenti,
    # puis B0F9B0(Mantis, [Mantis+0x2AC], 0x2BF) - machine 2 (etats 700 a
    # 703), [+0x2AC] ne vaut 2 que dans cette phase (-1 sinon : B0F9B0 passe
    # alors une machine nulle, PLANTAGE constate). Un petit code refait le
    # prologue de F08CF0 (rdi = Mantis, rsi = 0, xmm6 = 0, xmm7 = 1.0, rax =
    # objet de vie) et saute dans le bloc, qui rend la main par l'epilogue
    # F09241 ; +0x2AC mis a 2 le temps de l'appel. Valide : fin du combat,
    # cinematique. Declenche quand l'objet de vie de Mantis recoit un impact
    # (place de surveillance du detour de B88260).
    MANTIS_DEFEAT = {
        "prologue": (0xF08CF0, "48895c24084889742410574883ec50"),
        "block": (0xF0903E, "f30f10058a9d900089b01c0300000f2f"),
        "epilogue": (0xF09241, "488b5c2460488b7424680f287424400f287c24304883c4505fc3"),
        "machine_goto": (0xB0F9B0, "448b51344533c9488b49384585d27e17"),
    }
    MANTIS_DEFEAT_MACHINE = (0x2AC, 2)

    def _mantis_defeat_stub(self, funcs: dict[str, int]) -> int:
        if getattr(self, "_mantis_stub_pid", None) == self.pid:
            return self._mantis_stub_addr
        code = (bytes.fromhex("48895c2408488974241057" "4883ec50" "0f29742440" "0f297c2430")  # prologue de F08CF0
                + bytes.fromhex("4889cf" "0f57f6" "b80000803f" "660f6ef8" "31f6")       # rdi, xmm6, xmm7 = 1.0, esi
                + bytes.fromhex("488b87b8420000")                                      # rax = objet de vie
                + bytes.fromhex("48b9") + struct.pack("<Q", funcs["block"]) + bytes.fromhex("ffe1"))
        stub = kernel32.VirtualAllocEx(self.proc.handle, None, 0x1000, MEM_COMMIT | 0x2000, PAGE_EXECUTE_READWRITE)
        if not stub:
            return 0
        self.proc.write_bytes(stub, code)
        self._mantis_stub_addr, self._mantis_stub_pid = stub, self.pid
        return stub

    def mantis_defeat(self) -> bool:
        """Lance la defaite de Screaming Mantis (bete) par le code du jeu."""
        boss = self._boss()
        if not boss or boss[0] != "mantis_beast" or not self.speed.main_loop_hook_installed():
            return False
        mantis = boss[1]
        funcs = self._live_funcs(self.MANTIS_DEFEAT)
        offset, machine_id = self.MANTIS_DEFEAT_MACHINE
        count = struct.unpack("<i", self.proc.read_bytes(mantis + 0x34, 4))[0]
        machines = struct.unpack("<Q", self.proc.read_bytes(mantis + 0x38, 8))[0]
        ids = [struct.unpack("<i", self.proc.read_bytes(machines + i * 0x130 + 0x128, 4))[0]
               for i in range(min(max(count, 0), 16))] if machines else []
        if funcs is None or machine_id not in ids:
            return False
        stub = self._mantis_defeat_stub(funcs)
        if not stub:
            return False
        saved = self.proc.read_bytes(mantis + offset, 4)
        self.proc.write_bytes(mantis + offset, struct.pack("<i", machine_id))
        try:
            done = self.speed.game_call(stub, mantis) is not None
        finally:
            self.proc.write_bytes(mantis + offset, saved)
        return done

    def mantis_one_hit_tick(self, one_hit: bool) -> None:
        """A appeler souvent : avec Un coup, un mort, le premier impact recu
        par Screaming Mantis (bete) la fait perdre."""
        boss = self._boss() if one_hit else None
        block = self._boss_touch_block() if boss and boss[0] == "mantis_beast" else 0
        if not block:
            return
        watched, hits = struct.unpack("<QQ", self.proc.read_bytes(block + 0x50, 16))
        if watched != boss[2]:
            self.proc.write_bytes(block + 0x50, struct.pack("<QQ", boss[2], 0))
            self._mantis_hits = 0
            return
        if hits != getattr(self, "_mantis_hits", 0):
            self._mantis_hits = hits
            if not getattr(self, "_mantis_defeating", False):
                self._mantis_defeating = True

                def run():
                    try:
                        self.mantis_defeat()
                    except OSError:
                        pass
                    finally:
                        time.sleep(1.0)
                        self._mantis_defeating = False
                threading.Thread(target=run, daemon=True).start()

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

    def write_boss_gauge(self, gauge: str, value: int, hud: bool = True) -> bool:
        """Ecrit la jauge (au moins 1 pour BOSS_FLOOR_ONE) et, si `hud`, sa barre."""
        found = self._boss_for(gauge)
        if not found:
            return False
        boss, damage, which = found
        floor = 1 if gauge.split(":")[1] in self.BOSS_FLOOR_ONE else 0
        value = struct.pack("<i", max(floor, value))
        self.proc.write_bytes(damage + self.BOSS_GAUGES[which], value)
        bars = self._boss_hud(boss, damage) if hud else 0
        if bars:
            self.proc.write_bytes(bars + self.BOSS_HUD[which][1], value)
        return True
