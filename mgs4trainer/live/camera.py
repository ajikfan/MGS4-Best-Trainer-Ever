"""MGS4Live : mode photo (camera libre)."""
import math
import struct


class CameraMixin:
    """Camera libre du mode photo."""

    # Camera du jeu (2026-10-23, valide en jeu) : matrice monde en adresse
    # fixe mgs4+1DDDC70, 4 lignes de 4 flottants : droite, bas (la 2e ligne
    # pointe vers le bas de l'ecran), regard, position (w = 1). La matrice
    # de vue suit (+0x40) puis la projection. A chaque image, le controleur
    # de camera calcule une matrice sur la pile et appelle B9B70 (regler la
    # camera) qui la recopie ici (4 movups B9C03..B9C2C) puis en deduit vue
    # et projection. Le patch "free_camera" neutralise ces 4 recopies : la
    # camera garde ce qu'on y ecrit, le jeu continue d'en tirer la vue.
    CAMERA_RVA = 0x1DDDC70

    # Manette virtuelle (2026-10-23, validee en jeu) : le jeu reunit clavier,
    # souris et manette (Steam Input) dans une manette au format PS3, en deux
    # exemplaires fixes : A = mgs4+23D2AEA0, B = mgs4+23D2AF50 (+0 boutons,
    # 2e octet L2 01 R2 02 L1 04 R1 08 triangle 10 rond 20 croix 40 carre 80 ;
    # +4/+5 stick droit X/Y, +6/+7 stick gauche X/Y, 0x80 au centre ; +8..
    # pressions). La manette est remplie par 746300 (lea rdi, B+4 en 746347)
    # et le clavier/la souris ajoutes par 74FF10 (adresses fixes de A et B).
    # En mode photo, ces 60 champs de deplacement sont rediriges vers une
    # copie allouee par le trainer (meme disposition) : le jeu ne voit plus
    # que A et B au neutre, le trainer lit la copie pour piloter la camera.
    # (rva du champ de deplacement, valeur d'origine)
    PHOTO_PAD_A_RVA = 0x23D2AEA0
    PHOTO_PAD_B_RVA = 0x23D2AF50
    PHOTO_PAD_LO = PHOTO_PAD_A_RVA - 0x40
    PHOTO_PAD_SIZE = 0x400
    PHOTO_PAD_SITES = (
        (0x75000f, 0x235daeb2), (0x750018, 0x235daea0), (0x75001f, 0x235dae9d), (0x750025, 0x235daf43),
        (0x75002c, 0x235daf40), (0x750101, 0x235dadc0), (0x75010a, 0x235dadb2), (0x750111, 0x235dada7),
        (0x750117, 0x235dae55), (0x75011e, 0x235dae4a), (0x7501f1, 0x235dacd0), (0x7501fa, 0x235daca2),
        (0x750200, 0x235dad4c), (0x75021a, 0x235daca7), (0x750346, 0x235dacb6), (0x750360, 0x235dac9c),
        (0x750374, 0x235dabf8), (0x75037a, 0x235dabee), (0x750380, 0x235dabcc), (0x750390, 0x235dabc4),
        (0x750398, 0x235dabbd), (0x75039f, 0x235dabb7), (0x7503a6, 0x235dabb1), (0x7503ad, 0x235dabab),
        (0x7503b5, 0x235daba4), (0x7503bd, 0x235dab9d), (0x7503c5, 0x235dab96), (0x7503cd, 0x235dab8f),
        (0x7503d4, 0x235dac58), (0x750410, 0x235dab4d), (0x75041c, 0x235dab42), (0x750428, 0x235dab37),
        (0x75043c, 0x235dab18), (0x75044c, 0x235daa6c), (0x750469, 0x235daa4f), (0x750470, 0x235daa4c),
        (0x75048d, 0x235daa2f), (0x750494, 0x235daa08), (0x7504b1, 0x235da9eb), (0x7504cb, 0x235daa9d),
        (0x7504e8, 0x235daa84), (0x750502, 0x235daa4a), (0x75073b, 0x235da761), (0x750745, 0x235da807),
        (0x750913, 0x235da58f), (0x750919, 0x235da639), (0x750926, 0x235da57d), (0x75092c, 0x235da627),
        (0x750939, 0x235da567), (0x75093f, 0x235da611), (0x750945, 0x235da60c), (0x750952, 0x235da54f),
        (0x750958, 0x235da5f9), (0x750972, 0x235da53a), (0x75097c, 0x235da5e0), (0x750986, 0x235da52a),
        (0x750990, 0x235da5d0), (0x75099a, 0x235da529), (0x7509a1, 0x235da5d2), (0x74634a, 0x235e4c06),
    )

    def _camera_rows(self) -> list[list[float]]:
        raw = struct.unpack("<16f", self.proc.read_bytes(self.base + self.CAMERA_RVA, 64))
        return [list(raw[i * 4:i * 4 + 4]) for i in range(4)]

    def _write_camera_rows(self, rows: list[list[float]]) -> None:
        self.proc.write_bytes(self.base + self.CAMERA_RVA, struct.pack("<16f", *(v for row in rows for v in row)))

    # Pilotage (fait par la DLL a chaque image, voir photo_frame dans
    # native/speedhack.c) : stick gauche deplacer, stick droit orienter,
    # R1-R2/L1-L2 monter/descendre, carre maintenu = rapide.
    PHOTO_STEP = 50.0       # unites du jeu par image du jeu, stick a fond
    PHOTO_FAST = 5.0
    PHOTO_TURN = 0.06       # radians par image du jeu, stick droit a fond
    # Le jeu applique deja sa zone morte aux sticks (746300) ; la souris
    # arrive dans le stick droit par petites valeurs, qu'une zone morte de
    # 15 % ignorait (rotation a la souris trop lente).
    PHOTO_DEADZONE = 0.03
    # En cinematique, ZQSD et la souris n'arrivent plus dans la manette
    # virtuelle (la manette, si) : la DLL les lit elle-meme (photo_direct).
    PHOTO_MOUSE = 0.0008    # radians par pixel (valide en jeu)
    # Stick droit en cinematique : la moitie suffit (valide en jeu, la
    # vitesse de partie y etait bien trop rapide).
    PHOTO_TURN_CINEMATIC = 0.03
    # HUD masque (2026-10-24, valide en jeu) : chaque element du HUD teste un
    # mot de drapeaux global (mgs4+1D77AA8, ou avec +1D77AAC) ; bit 4 =
    # radar et indice de camouflage, les autres bits de l'octet = le reste.
    # La DLL les reimpose a chaque image (le jeu en efface certains) ; a la
    # sortie, les bits que le jeu n'avait pas sont retires.
    HUD_FLAGS_RVA = 0x1D77AA8
    HUD_HIDE_MASK = 0xFF

    def photo_mode_available(self) -> bool:
        """La DLL injectee sait piloter la camera (sinon : relancer le jeu
        pour charger la nouvelle DLL)."""
        return bool(self.pid and self.speed.ensure_injected(self.pid) and self.speed.photo_supported())

    def set_photo_mode(self, enabled: bool) -> bool:
        """Libere la camera, detourne la manette virtuelle et confie la
        camera a la DLL (ou rend tout au jeu)."""
        if not (self.connected and self.sane):
            return False
        if enabled:
            if not self.photo_mode_available():
                return False
            if not self._redirect_pad(True):
                return False
            if not self.set_code_patch("free_camera", True):
                self._redirect_pad(False)
                return False
            zoom_var = self._freeze_zoom(True)
            if zoom_var:
                self.speed.set_photo_zoom(zoom_var, self.PHOTO_ZOOM_RATE)
            pad = self._photo_shadow + (self.PHOTO_PAD_B_RVA - self.PHOTO_PAD_LO)
            hud = self.base + self.HUD_FLAGS_RVA
            self._photo_hud_before = struct.unpack("<I", self.proc.read_bytes(hud, 4))[0] & self.HUD_HIDE_MASK
            self.speed.set_photo(True, pad, self.base + self.CAMERA_RVA, self.PHOTO_STEP,
                                 self.PHOTO_FAST, self.PHOTO_TURN, self.PHOTO_DEADZONE,
                                 hud, self.HUD_HIDE_MASK)
            return True
        self.speed.set_photo(False)
        self.speed.set_photo_direct(False)
        self._photo_direct = None
        hud = self.base + self.HUD_FLAGS_RVA
        flags = struct.unpack("<I", self.proc.read_bytes(hud, 4))[0]
        keep = getattr(self, "_photo_hud_before", 0)
        self.proc.write_bytes(hud, struct.pack("<I", (flags & ~self.HUD_HIDE_MASK) | keep))
        self.speed.set_photo_zoom(0, 0.0)
        self._freeze_zoom(False)
        ok = self.set_code_patch("free_camera", False)
        return self._redirect_pad(False) and ok

    def teleport_to_camera(self) -> bool:
        """Place Snake a la position de la camera (mode photo) ; refuse en
        cinematique (pas de controleur de jeu). Il retombe au sol si la
        camera est en l'air."""
        try:
            if not self._octocamo_controller():
                return False
            x, y, z = struct.unpack("<3f", self.proc.read_bytes(self.base + self.CAMERA_RVA + 48, 12))
            return self.set_player_position(x, y, z)
        except OSError:
            return False

    def update_photo_direct(self) -> None:
        """Appelee regulierement pendant le mode photo : signale a la DLL
        si une cinematique est en cours (pas de controleur de jeu)."""
        try:
            cinematic = not self._octocamo_controller()
        except OSError:
            return
        if cinematic != getattr(self, "_photo_direct", None):
            self._photo_direct = cinematic
            self.speed.set_photo_direct(cinematic, self.PHOTO_MOUSE,
                                        self.PHOTO_TURN_CINEMATIC if cinematic else self.PHOTO_TURN)

    # Zoom du mode photo (2026-10-24, valide en jeu) : B9B70 recoit le zoom
    # en argument (xmm2, recopie dans xmm4 en B9B88), le range a
    # camera+0x380 et s'en sert aussitot depuis le registre ; les
    # cinematiques le font varier. Objet camera : mgs4+1DDDC70 en partie
    # (~4 appels par image, zoom 1DDDFF0), un autre en cinematique (1DDD9B0
    # probablement) ; camera+0x380 est reecrit par ailleurs en partie. Detour
    # en B9B88 vers un bout de code (page de la copie de manette, +0x800) :
    # l'argument est remplace, pour toutes les cameras, par une variable a
    # nous (+0x808) que la DLL modifie (croix, molette) ; a 0, elle prend
    # d'abord le zoom en cours (partie ou cinematique).
    ZOOM_HOOK_RVA = 0xB9B88
    ZOOM_HOOK_ORIGINAL = bytes.fromhex("0f28e2"      # movaps xmm4,xmm2
                                       "440f2940b8")  # movaps [rax-48h],xmm8
    ZOOM_CAVE_OFFSET = 0x800  # +8 zoom, +0x10 code
    PHOTO_ZOOM_RATE = 0.02    # par image : croix maintenue ~x3 par seconde

    @classmethod
    def _zoom_cave_code(cls, code_at: int, zoom_var: int, back: int) -> bytes:
        def rip(at_end: int) -> bytes:
            return struct.pack("<i", zoom_var - at_end)
        code = bytearray(b"\x0f\x57\xe4")                                  # xorps xmm4,xmm4
        code += b"\x0f\x2e\x25" + rip(code_at + len(code) + 7)             # ucomiss xmm4,[zoom]
        code += b"\x75\x08"                                                 # jne +8 (deja pris)
        code += b"\xf3\x0f\x11\x15" + rip(code_at + len(code) + 8)        # movss [zoom],xmm2
        code += b"\xf3\x0f\x10\x15" + rip(code_at + len(code) + 8)        # movss xmm2,[zoom]
        code += cls.ZOOM_HOOK_ORIGINAL
        code += b"\xe9" + struct.pack("<i", back - (code_at + len(code) + 5))  # jmp retour
        return bytes(code)

    def _freeze_zoom(self, enabled: bool) -> int:
        """Pose (ou retire) le detour ; renvoie l'adresse de la variable de
        zoom (0 si rien n'est pose)."""
        site = self.base + self.ZOOM_HOOK_RVA
        current = self.proc.read_bytes(site, len(self.ZOOM_HOOK_ORIGINAL))
        if not enabled:
            if current != self.ZOOM_HOOK_ORIGINAL and current[0] == 0xE9:
                self.proc.write_bytes(site, self.ZOOM_HOOK_ORIGINAL)
            return 0
        if current != self.ZOOM_HOOK_ORIGINAL and current[0] != 0xE9:
            return 0
        data = self._pad_shadow() + self.ZOOM_CAVE_OFFSET
        zoom_var, code_at = data + 8, data + 0x10
        self.proc.write_bytes(zoom_var, b"\0" * 4)  # reprendre le zoom en cours
        if current == self.ZOOM_HOOK_ORIGINAL:
            back = site + len(self.ZOOM_HOOK_ORIGINAL)
            self.proc.write_bytes(code_at, self._zoom_cave_code(code_at, zoom_var, back))
            self.proc.write_bytes(site, b"\xe9" + struct.pack("<i", code_at - (site + 5)) + b"\x90" * 3)
        return zoom_var

    def _pad_shadow(self) -> int:
        """Copie de la manette (une par processus, pres du code du jeu)."""
        if getattr(self, "_photo_shadow_pid", None) != self.pid:
            self._photo_shadow = self.proc.alloc_near(self.base + self.PHOTO_PAD_SITES[0][0], 0x1000)
            self._photo_shadow_pid = self.pid
        return self._photo_shadow

    def _redirect_pad(self, enabled: bool) -> bool:
        shadow = self._pad_shadow()
        if not shadow:
            return False
        delta = shadow - (self.base + self.PHOTO_PAD_LO)
        current = [struct.unpack("<I", self.proc.read_bytes(self.base + rva, 4))[0] for rva, _ in self.PHOTO_PAD_SITES]
        redirected = [(orig + delta) & 0xFFFFFFFF for _, orig in self.PHOTO_PAD_SITES]
        originals = [orig for _, orig in self.PHOTO_PAD_SITES]
        if enabled:
            if current == redirected:
                return True
            if current != originals:
                return False  # autre version du jeu
            self.proc.write_bytes(shadow, self.proc.read_bytes(self.base + self.PHOTO_PAD_LO, self.PHOTO_PAD_SIZE))
            for (rva, _), value in zip(self.PHOTO_PAD_SITES, redirected):
                self.proc.write_bytes(self.base + rva, struct.pack("<I", value))
            neutral = b"\0" * 4 + b"\x80" * 4 + b"\0" * 12
            for pad in (self.PHOTO_PAD_A_RVA, self.PHOTO_PAD_B_RVA):
                self.proc.write_bytes(self.base + pad, neutral)
            return True
        if current == originals:
            return True
        if current != redirected:
            return False
        for rva, orig in self.PHOTO_PAD_SITES:
            self.proc.write_bytes(self.base + rva, struct.pack("<I", orig))
        return True

    def read_photo_pad(self) -> tuple[int, int, int, int, int] | None:
        """(boutons du 2e octet, stick gauche X, Y, stick droit X, Y) de la
        manette detournee, valeurs brutes 0..255 (0x80 au centre)."""
        shadow = getattr(self, "_photo_shadow", None)
        if not shadow:
            return None
        pad = self.proc.read_bytes(shadow + (self.PHOTO_PAD_B_RVA - self.PHOTO_PAD_LO), 8)
        return pad[1], pad[6], pad[7], pad[4], pad[5]

    @staticmethod
    def _normalize(v):
        n = math.sqrt(sum(c * c for c in v)) or 1.0
        return [c / n for c in v]

    @staticmethod
    def _cross(a, b):
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

    @staticmethod
    def _rotate(v, axis, angle):
        """Rotation de v autour de l'axe unitaire axis (Rodrigues)."""
        c, s = math.cos(angle), math.sin(angle)
        dot = sum(v[i] * axis[i] for i in range(3))
        cross = CameraMixin._cross(axis, v)
        return [v[i] * c + cross[i] * s + axis[i] * dot * (1 - c) for i in range(3)]

    def move_photo_camera(self, right: float, up: float, forward: float, yaw: float, pitch: float) -> bool:
        """Deplace la camera libre dans son propre repere (unites du jeu) et
        la tourne (radians : yaw autour de la verticale du monde, pitch
        autour de son axe droit)."""
        if not (self.connected and self.sane):
            return False
        rows = self._camera_rows()
        r, down, look, pos = (rows[i][:3] for i in range(4))
        if yaw:
            world_up = [0.0, 1.0, 0.0]
            r, down, look = (self._rotate(v, world_up, yaw) for v in (r, down, look))
        if pitch:
            axis = self._normalize(r)
            down, look = (self._rotate(v, axis, pitch) for v in (down, look))
        look = self._normalize(look)
        r = self._normalize(self._cross(look, [-c for c in down]))
        down = self._normalize(self._cross(look, r))
        # Garder le sens d'origine des axes (le cross peut inverser "bas").
        if sum(down[i] * rows[1][i] for i in range(3)) < 0:
            down = [-c for c in down]
        if sum(r[i] * rows[0][i] for i in range(3)) < 0:
            r = [-c for c in r]
        pos = [pos[i] + r[i] * right - down[i] * up + look[i] * forward for i in range(3)]
        self._write_camera_rows([r + [0.0], down + [0.0], look + [0.0], pos + [1.0]])
        return True
