"""MGS4Live : entree « Charger » dans le menu pause (Mk. II) de la partie."""
import struct
import time


class LoadMenuMixin:
    """Charger une sauvegarde depuis le menu Mk. II, sans repasser par le menu
    principal (2026-10-24, valide en jeu).

    L'entree 5 du menu (Base de donnees, masquee en partie par le bit 5 de
    mgs4+3B7C0E0) devient « Charger », placee juste au-dessus de Sauvegarder :
      - 4E3A2A / 4D7E74 : le constructeur de la liste (4E3A20) et le
        compactage des libelles (4D7E60) lisent les entrees masquees sans le
        bit 5 (le jeu le repose a chaque ouverture et a chaque chargement) ;
      - 4E34FA : action de l'entree 5 = ecran de chargement du jeu,
        4C5150(couche) (celui du menu principal) ;
      - 4E3AB3 (fin du constructeur, table des actions en +0x1E4) et 4D8039
        (fin du compactage : textes 438DD0/439E40, icones 437580/437B40 des
        lignes, cles par ligne en 1C2CFE8/1C2D008/1C2D048/1C2D068) : meme
        rotation, la ligne de Charger passe avant Sauvegarder et les
        suivantes remontent ; le nom de Charger est pose a cette occasion ;
      - 4E37B7 (description du bas, 4D5C10(entree)) : entree 5 -> notre texte.
    Rotation desactivee si Codec ou Sauvegarder est masque (bits 0 et 8).

    Apres l'ecran de chargement (tache 4C2C80, etat +0xA0 : un chargement passe
    par 3, 4, 5 = « chargement termine », 7 puis 8 une ou deux images ; une
    annulation par 2, 6, 7), le chargement n'est qu'en memoire : le trainer ferme le menu
    (sortie normale du sous-menu Mk. II, 4D40A0(sous-menu+0x90, 3)), attend
    que le menu pause soit entierement ferme (mgs4+3B7C8B0 a 0 ; avant, la
    couche d'interface reste cassee jusqu'au redemarrage du jeu) puis lance
    « Continuer » du game over, 5BCB0(0), compteur de Continues (5BD6A)
    neutralise. Le fondu du jeu meurt avec le menu pause : le trainer pose son
    propre rideau noir pendant la fermeture (load_menu_poll -> evenements).

    Le code des detours est un bloc independant de sa position (assemble une
    fois, voir LM_CODE) : adresses du jeu dans une table en tete de page."""

    LM_SITES = {
        # rva : octets d'origine (remis a la fermeture du trainer)
        0x4E34FA: bytes.fromhex("e85137ffff8bc8e8fa007f00e8555a0100eb44"),
        0x4E3A2A: bytes.fromhex("488b3daf866903"),
        0x4D7E74: bytes.fromhex("8b3d66426a03"),
        0x4D8039: bytes.fromhex("44896c2468"),
        0x4E3AB3: bytes.fromhex("b9ffffffff"),
        0x4E37B7: bytes.fromhex("e85424ffff"),
    }
    # call 4D6D10 ; mov ecx,eax ; call 4C5150 ; nop x5 ; jmp 4E3551
    LM_ACTION = bytes.fromhex("e81138ffff8bc8e84a1cfeff9090909090eb44")
    LM_FUNCS = {
        0x438C00: "448b8170010000448bda4c8b", 0x438DD0: "4885c97418f7010000080074",
        0x439E40: "48895c240857448b89700100", 0x437580: "4885d274368b020fbae01273",
        0x437B40: "4c8bc14885c9744e448b0941", 0x4D5C10: "40534883ec2085c9790433db",
        0x432790: "894c24084c8bdc5641564157", 0x4D40A0: "33c089511048894130c3",
        0x5BCB0: "48895c240848896c24104889", 0x1C2CFE8: "efee2e00efee2f00efee3000",
    }
    LM_CONTINUE_COUNT, LM_COUNT_ORIGINAL = 0x5BD6A, bytes.fromhex("66898a58010000")
    LM_FLAGS, LM_PAUSE, LM_DATA_TASK = 0x3B7C0E0, 0x3B7C8B0, 0x4C2C80
    LM_TEXTS = 0x17BA49  # descriptions du menu : 432790(groupe, numero), langue du jeu
    # Table du bloc : FLAGS, IMG, FIND, GETTXT, SETTXT, GETIMG, SETIMG, DESCFN,
    # DESCBODY, retours LBL, BLD, BFL, LFL ; nom en +0x80, description en +0xC0.
    LM_TABLE = (None, None, 0x438C00, 0x438DD0, 0x439E40, 0x437580, 0x437B40, 0x4D5C10, 0x4D5C2D,
                0x4D803E, 0x4E3AB8, 0x4E3A31, 0x4D7E7A)
    LM_ENTRY = {0x4D8039: 0x200, 0x4E3AB3: 0x45A, 0x4E37B7: 0x4E7, 0x4E3A2A: 0x504, 0x4D7E74: 0x518}
    LM_CODE = bytes.fromhex(
        "44896c246850515241504151415241535657554154415641574883ec284c8b3de4fdffff488b05d5fdffff8b00a901010000"
        "755589c1f7d183e11ef3440fb8e141ffc4458d75ff4539f47d3d4489e1e86e01000089c54489e64439f67d198d4e01e89101"
        "00004189d14989c089f2e834000000ffc6ebe24489f24c8d05fffdffff4189e9e81e0000004883c428415f415e415c5d5f5e"
        "415b415a415941585a5958ff25a1fdffff4154415541564883ec204189d44d89c54589ce4d85ed7460488b8bb8010000438b"
        "94a7e8cfc2014d89e8ff1549fdffff488b8bc0010000438b94a7e8cfc2014d89e8ff1531fdffff488b8bb8010000438b94a7"
        "08d0c2014d89e8ff1519fdffff488b8bc0010000438b94a708d0c2014d89e8ff1501fdffff488b8bb8010000438b94a748d0"
        "c201ff15dcfcffff4885c0740c4889c14489f2ff15ebfcffff488b8bb8010000438b94a768d0c201ff15b6fcffff4885c074"
        "0c4889c14489f2ff15c5fcffff488b8bc0010000438b94a748d0c201ff1590fcffff4885c0740c4889c14489f2ff159ffcff"
        "ff488b8bc0010000438b94a768d0c201ff156afcffff4885c0740c4889c14489f2ff1579fcffff4883c420415e415d415cc3"
        "41544883ec204189cc488b8bb8010000438b94a748d0c201ff1530fcffff4889c2488b8bb8010000ff1538fcffff4883c420"
        "415cc34154415541564883ec204189cc488b8bb8010000438b94a7e8cfc201ff15f7fbffff4889c1ff15f6fbffff4989c548"
        "8b8bb8010000438b94a748d0c201ff15d6fbffff4889c2488b8bb8010000ff15defbffff89c24c89e84883c420415e415d41"
        "5cc3f7c701010000757a8b83e001000083f8037c6f448d40ff4283bc83e401000008756041ffc831d283bc93e40100000574"
        "09ffc24439c27cefeb484189d14439c27d128b8c93e8010000898c93e4010000ffc2ebe942c78483e4010000050000008b8b"
        "dc0100004439c975054489c1eb0c4439c97c0d4439c17f08ffc9898bdc010000b9ffffffffff2569fbffff83f9057406ff25"
        "46fbffff534883ec20488d1dc2fbffffff253cfbffff488b3df5faffff488b3f4883e7dfff2540fbffff488b3de1faffff8b"
        "3f83e7dfff2536fbffff")
    # Langue du jeu reconnue a la description native de l'entree 5 ; nom
    # (police du Mk. II, Latin-1) et description de « Charger ».
    LM_LANGUAGES = {
        "View the Database.": ("Load", "Load a saved game."),
        "Consulter la base de données.": ("Charger", "Charger une sauvegarde."),
        "Die Datenbank aufrufen.": ("Laden", "Spielstand laden."),
        "Visualizza il Database.": ("Carica", "Carica un salvataggio."),
        "Mira la Base de Datos.": ("Cargar", "Cargar una partida."),
        "Ver o Banco de Dados.": ("Carregar", "Carregar um jogo."),
    }
    LM_CURTAIN_TIME = 0.55   # s : rideau du trainer opaque avant la fermeture du menu
    LM_UNCURTAIN_DELAY = 1.0  # s apres « Continuer » : zone dechargee, ecran noir du jeu
    LM_TIMEOUT = 5.0
    HANDLE_MASK = 0xFFFFFFFFFFFFF

    def load_menu_install(self) -> bool:
        state = getattr(self, "_lm", None)
        if state and state["pid"] == self.pid:
            return True
        if not (self.connected and self.sane):
            return False
        b, proc = self.base, self.proc
        if not self._lm_restore_leftover():
            return False
        for rva, sig in self.LM_FUNCS.items():
            if proc.read_bytes(b + rva, len(sig) // 2).hex() != sig:
                return False
        if proc.read_bytes(b + self.LM_CONTINUE_COUNT, 7) != self.LM_COUNT_ORIGINAL:
            return False
        if not (self.pid and self.speed.ensure_injected(self.pid)):
            return False
        native = self.game_menu_text(5)
        if native is None:
            return False
        name, desc = self.LM_LANGUAGES.get(native, self.LM_LANGUAGES["View the Database."])
        page = proc.alloc_near(b + 0x4D8039, 0x1000)
        if not page:
            return False
        table = [b + self.LM_FLAGS, b] + [b + rva for rva in self.LM_TABLE[2:]]
        proc.write_bytes(page, struct.pack("<%dQ" % len(table), *table))
        proc.write_bytes(page + 0x80, name.encode("latin-1", "replace")[:63] + b"\0")
        proc.write_bytes(page + 0xC0, desc.encode("utf-8")[:255] + b"\0")
        proc.write_bytes(page + 0x200, self.LM_CODE)
        proc.write_bytes(b + 0x4E34FA, self.LM_ACTION)
        for rva, entry in self.LM_ENTRY.items():
            site, target = b + rva, page + entry
            opcode = b"\xe8" if rva == 0x4E37B7 else b"\xe9"
            patch = opcode + struct.pack("<i", target - (site + 5))
            proc.write_bytes(site, patch + b"\x90" * (len(self.LM_SITES[rva]) - 5))
        self._lm = {"pid": self.pid, "page": page, "phase": "idle", "since": 0.0, "data": 0, "data_state": None}
        return True

    def _lm_restore_leftover(self) -> bool:
        """Vrai si les sites sont d'origine. Un detour laisse par un trainer
        ferme sans nettoyage (tue, plantage) est reconnu (sauts vers une page
        portant LM_CODE, octets de l'action) et retire ; autre contenu : faux."""
        b, proc = self.base, self.proc
        current = {rva: proc.read_bytes(b + rva, len(original)) for rva, original in self.LM_SITES.items()}
        if all(current[rva] == original for rva, original in self.LM_SITES.items()):
            return True
        for rva, original in self.LM_SITES.items():
            data = current[rva]
            if data == original:
                continue
            if rva == 0x4E34FA:
                if data != self.LM_ACTION:
                    return False
                continue
            if data[0] not in (0xE8, 0xE9) or rva not in self.LM_ENTRY:
                return False
            page = b + rva + 5 + struct.unpack_from("<i", data, 1)[0] - self.LM_ENTRY[rva]
            try:
                if proc.read_bytes(page + 0x200, 32) != self.LM_CODE[:32]:
                    return False
            except OSError:
                return False
        for rva, original in self.LM_SITES.items():
            if current[rva] != original:
                proc.write_bytes(b + rva, original)
        return True

    def load_menu_remove(self) -> None:
        state = getattr(self, "_lm", None)
        self._lm = None
        if not (state and state["pid"] == self.pid and self.proc):
            return
        try:
            for rva, original in self.LM_SITES.items():
                self.proc.write_bytes(self.base + rva, original)
            self.proc.write_bytes(self.base + self.LM_CONTINUE_COUNT, self.LM_COUNT_ORIGINAL)
        except OSError:
            pass

    def game_menu_text(self, number: int) -> str | None:
        """Texte numero `number` des descriptions du menu, dans la langue du jeu."""
        address = self.speed.game_call(self.base + 0x432790, self.LM_TEXTS, number)
        if not address:
            return None
        raw = b""
        while len(raw) < 256:
            try:
                chunk = self.proc.read_bytes(address + len(raw), 16)
            except OSError:
                break
            raw += chunk
            if b"\0" in chunk:
                break
        return raw.split(b"\0")[0].decode("utf-8", "replace")

    def _lm_task(self, handle: int) -> int:
        obj = handle & self.HANDLE_MASK
        try:
            return obj if handle and struct.unpack("<Q", self.proc.read_bytes(obj + 0x30, 8))[0] == handle else 0
        except OSError:
            return 0

    def load_menu_poll(self) -> str | None:
        """Fait avancer la sequence apres un chargement ; renvoie "curtain"
        (le trainer doit poser son rideau noir) ou "uncurtain" (le retirer)."""
        state = getattr(self, "_lm", None)
        if not (state and state["pid"] == self.pid):
            return None

        def q(address: int) -> int:
            return struct.unpack("<Q", self.proc.read_bytes(address, 8))[0]

        def d(address: int) -> int:
            return struct.unpack("<i", self.proc.read_bytes(address, 4))[0]

        b, now, phase = self.base, time.monotonic(), state["phase"]
        pause = self._lm_task(q(b + self.LM_PAUSE))
        menu = self._lm_task(q(pause + 0x2C8)) if pause else 0
        if phase == "idle":
            child = self._lm_task(q(menu + 0x1B8)) if menu else 0
            if child and q(child + 8) == b + self.LM_DATA_TASK:
                if child != state["data"]:
                    state["data"], state["data_state"] = child, None
                if d(child + 0xA0) in (5, 8):
                    state["data_state"] = "loaded"
            elif state["data"]:
                state["data"] = 0
                if state["data_state"] == "loaded":
                    state["phase"], state["since"] = "curtain", now
                    return "curtain"
            return None
        if phase == "curtain":
            if now - state["since"] < self.LM_CURTAIN_TIME:
                return None
            if menu and not self._lm_task(q(menu + 0x1B8)) and d(menu + 0xA0) == 1:
                self.speed.game_call(b + 0x4D40A0, menu + 0x90, 3)
                state["phase"], state["since"] = "closing", now
            elif now - state["since"] > self.LM_TIMEOUT:
                state["phase"] = "idle"
                return "uncurtain"
            return None
        if phase == "closing":
            if pause:
                if now - state["since"] > self.LM_TIMEOUT:
                    state["phase"] = "idle"
                    return "uncurtain"
                return None
            count = b + self.LM_CONTINUE_COUNT
            self.proc.write_bytes(count, b"\x90" * 7)
            try:
                self.speed.game_call(b + 0x5BCB0, 0)
            finally:
                self.proc.write_bytes(count, self.LM_COUNT_ORIGINAL)
            state["phase"], state["since"] = "continued", now
            return None
        if phase == "continued" and now - state["since"] >= self.LM_UNCURTAIN_DELAY:
            state["phase"] = "idle"
            return "uncurtain"
        return None
