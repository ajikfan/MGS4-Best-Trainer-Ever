"""MGS4Live : ligne QUITTER ajoutee au menu pause des cinematiques."""
import re
import struct
import time


class CutsceneMenuMixin:
    """Menu pause des cinematiques (PASSER / CONTINUER) avec une 3e ligne
    QUITTER (2026-10-24, valide en jeu).

    Le menu est une tache du jeu (mise a jour 4C0B80) : +0x98 scene
    d'interface (chargee d'un fichier du jeu, non modifie), +0xA0 curseur,
    navigation 4D3A20(curseur, nombre d'entrees = 2 en dur), validation
    curseur 0 -> passer (0x20012), sinon continuer (0x20013) ; surbrillance =
    animation de scene choisie dans une table de 2 hachages (1C2CA10).
    Patchs (poses par le trainer, retires a sa fermeture) :
      - 4C0D09 : 3 entrees ;
      - 4C0DE4 : table de surbrillance a nous {PASSER, CONTINUER, 0} (le
        hachage 0 ne lance rien) ;
      - 4C0DC1 : validation curseur 2 -> compteur (le trainer ramene au
        menu principal), le menu se ferme comme pour CONTINUER ;
      - 4C0B80 : note la tache a chaque image (menu ouvert, curseur).
    La scene n'a que 2 lignes : la 3e est dessinee par le trainer
    (CutsceneQuitOverlay). Curseur sur QUITTER : la barre du jeu descend d'une
    ligne (decalage 0x3C0, 1/16 px de 720p) et PASSER/CONTINUER passent en
    gris (0x80808040), reecrits tant que le curseur y reste."""

    CSM_ENTRY, CSM_CONFIRM, CSM_COUNT, CSM_TABLE_LEA = 0x4C0B80, 0x4C0DC1, 0x4C0D09, 0x4C0DE4
    CSM_CONTINUE, CSM_SKIP = 0x4C0DAE, 0x4C0DCA
    CSM_ORIGINAL = {
        CSM_ENTRY: bytes.fromhex("40534883ec30"),        # push rbx ; sub rsp,30h
        CSM_CONFIRM: bytes.fromhex("83bba00000000075e4"),  # cmp [rbx+A0h],0 ; jne continuer
        CSM_COUNT: bytes.fromhex("ba02000000"),          # mov edx,2
        CSM_TABLE_LEA: bytes.fromhex("488d0d25bc7601"),  # lea rcx,[table]
    }
    CSM_HIGHLIGHTS = (0x4A2371, 0x4AA371, 0)
    CSM_OPEN_DELAY = 0.3  # s sans mise a jour du menu -> ferme
    # Enregistrement du texte PASSER dans la scene (type 0x0A, cle, noeud
    # 0x17, parent 0x16) ; decalages relatifs a sa cle.
    CSM_TEXT_RECORD = bytes.fromhex("0a004e0345155800" "17001600")
    CSM_BAR_NODE = ((-0x148, 0x3C0), (-0x144, 0x3C00000), (-0x10C, 0x3C00000))
    CSM_TEXT_COLORS = (-0x28, -0x10, 0x88, 0xA0)
    # Liste d'affichage : commande couleur clignotante de la barre (repere),
    # copies de la position de la barre et couleurs affichees des textes.
    CSM_LIST_ANCHOR = re.compile(rb"\x14\x00\x00\x00........\x00\x00\x00\x01"
                                 rb"\x16\x00\x00\x00\x00\x00\x00\x00.\x80\x80\x80", re.S)
    CSM_LIST_BAR, CSM_LIST_TEXT = (-0x50, -0x10), (0x138, 0x1D8)
    CSM_DIM = 0x80808040

    def cutscene_quit_install(self) -> bool:
        state = getattr(self, "_csm", None)
        if state and state["pid"] == self.pid:
            return True
        if not (self.connected and self.sane):
            return False
        for rva, original in self.CSM_ORIGINAL.items():
            if self.proc.read_bytes(self.base + rva, len(original)) != original:
                return False
        b = self.base
        page = self.proc.alloc_near(b + self.CSM_ENTRY, 0x1000)
        if not page:
            return False
        table, task, tick, quit_count = page, page + 0x10, page + 0x18, page + 0x1C

        def rel(target: int, end: int) -> bytes:
            return struct.pack("<i", target - end)

        self.proc.write_bytes(table, struct.pack("<3I", *self.CSM_HIGHLIGHTS))
        entry = page + 0x40
        code = bytearray(b"\x48\x89\x0d" + rel(task, entry + 7))       # mov [tache],rcx
        code += b"\xff\x05" + rel(tick, entry + len(code) + 6)          # inc [images]
        code += self.CSM_ORIGINAL[self.CSM_ENTRY]
        code += b"\xe9" + rel(b + self.CSM_ENTRY + 6, entry + len(code) + 5)
        self.proc.write_bytes(entry, bytes(code))
        confirm = page + 0x80
        code = bytearray(b"\x83\xbb\xa0\x00\x00\x00\x02\x75\x0b")      # cmp [rbx+A0h],2 ; jne +0Bh
        code += b"\xff\x05" + rel(quit_count, confirm + len(code) + 6)  # inc [quitter]
        code += b"\xe9" + rel(b + self.CSM_CONTINUE, confirm + len(code) + 5)
        code += b"\x83\xbb\xa0\x00\x00\x00\x00"                          # cmp [rbx+A0h],0
        code += b"\x0f\x85" + rel(b + self.CSM_CONTINUE, confirm + len(code) + 6)
        code += b"\xe9" + rel(b + self.CSM_SKIP, confirm + len(code) + 5)
        self.proc.write_bytes(confirm, bytes(code))
        self.proc.write_bytes(b + self.CSM_TABLE_LEA, b"\x48\x8d\x0d" + rel(table, b + self.CSM_TABLE_LEA + 7))
        self.proc.write_bytes(b + self.CSM_COUNT, b"\xba\x03\x00\x00\x00")
        self.proc.write_bytes(b + self.CSM_CONFIRM, b"\xe9" + rel(confirm, b + self.CSM_CONFIRM + 5) + b"\x90" * 4)
        self.proc.write_bytes(b + self.CSM_ENTRY, b"\xe9" + rel(entry, b + self.CSM_ENTRY + 5) + b"\x90")
        self._csm = {"pid": self.pid, "page": page, "tick": None, "seen": 0.0,
                     "quit": struct.unpack("<I", self.proc.read_bytes(quit_count, 4))[0],
                     "task": None, "key": None, "anchor": None}
        return True

    def cutscene_quit_remove(self) -> None:
        state = getattr(self, "_csm", None)
        self._csm = None
        if not (state and state["pid"] == self.pid and self.proc):
            return
        try:
            for rva, original in self.CSM_ORIGINAL.items():
                self.proc.write_bytes(self.base + rva, original)
        except OSError:
            pass

    def cutscene_menu_poll(self) -> tuple[bool, int | None, bool]:
        """(menu ouvert, curseur, QUITTER valide depuis le dernier appel)."""
        state = getattr(self, "_csm", None)
        if not (state and state["pid"] == self.pid):
            return False, None, False
        page = state["page"]
        task, tick, quit_count = struct.unpack("<QII", self.proc.read_bytes(page + 0x10, 16))
        now = time.monotonic()
        if tick != state["tick"]:
            state["tick"], state["seen"] = tick, now
        quit_requested = quit_count != state["quit"]
        state["quit"] = quit_count
        if not task or now - state["seen"] > self.CSM_OPEN_DELAY:
            return False, None, quit_requested
        cursor = struct.unpack("<i", self.proc.read_bytes(task + 0xA0, 4))[0]
        if cursor == 2:
            self._csm_highlight_quit(state, task)
        return True, cursor, quit_requested

    def _csm_highlight_quit(self, state: dict, task: int) -> None:
        if state["task"] != task:
            state["task"], state["key"], state["anchor"] = task, None, None
            scene = struct.unpack("<Q", self.proc.read_bytes(task + 0x98, 8))[0]
            if not scene:
                return
            low = scene - 0x1000
            data = self.proc.read_bytes(low, 0x21000)
            found = data.find(self.CSM_TEXT_RECORD)
            if found < 0:
                return
            key = low + found + 4
            area = self.proc.read_bytes(key, 0x4000)
            for match in self.CSM_LIST_ANCHOR.finditer(area):
                anchor = match.end() - 4
                # Couleur d'un texte = commande 0x16 precedee de 00000001.
                if all(area[anchor + off - 12:anchor + off - 4] == b"\x00\x00\x00\x01\x16\x00\x00\x00"
                       for off in self.CSM_LIST_TEXT):
                    state["anchor"] = key + anchor
                    break
            state["key"] = key
        key, anchor = state["key"], state["anchor"]
        if not key:
            return
        for offset, value in self.CSM_BAR_NODE:
            self.proc.write_bytes(key + offset, struct.pack("<I", value))
        for offset in self.CSM_TEXT_COLORS:
            self.proc.write_bytes(key + offset, struct.pack("<I", self.CSM_DIM))
        if anchor:
            for offset in self.CSM_LIST_BAR:
                self.proc.write_bytes(anchor + offset, struct.pack("<I", 0x3C00000))
            for offset in self.CSM_LIST_TEXT:
                self.proc.write_bytes(anchor + offset, struct.pack("<I", self.CSM_DIM))
