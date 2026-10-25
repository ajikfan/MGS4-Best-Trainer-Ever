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
      - 4C0DC1 : validation curseur 2 -> compteur, le menu reste ouvert (le
        trainer ouvre la confirmation du jeu, voir plus bas) ;
      - 4C0B80 : note la tache a chaque image (menu ouvert, curseur), et
        saute la mise a jour du menu tant que le trainer a ouvert la fenetre
        de confirmation (octet page+0x20 ; pas le bit 0x2000 de mgs4+3B7C0E0,
        qui peut rester leve et figeait alors la cinematique) : seule la
        fenetre reagit.
    La scene n'a que 2 lignes : la 3e est dessinee par le trainer
    (CutsceneQuitOverlay). Curseur sur QUITTER : la barre du jeu descend d'une
    ligne (decalage 0x3C0, 1/16 px de 720p) et PASSER/CONTINUER passent en
    gris (0x80808040), reecrits tant que le curseur y reste.

    Confirmation (2026-10-24, validee en jeu) : la vraie fenetre « Retourner
    a l'ecran titre ? » OUI / NON du menu Sauvegarder (tache creee par
    526980, scene 0x15E2AE). Elle a besoin du paquet de ressources du menu
    pause, charge par 4EE0C0(0x38118E) (tache de chargement a terminer
    ensuite : laissee vivante, elle bloque le menu pause suivant), et d'une
    couche d'affichage : 4D6D10 la lit dans le gestionnaire du menu pause
    (absent ici, plantage) -> l'appel en 4D5F7E est remplace par « mov
    eax,1 » le temps de la creation (couche du menu des cinematiques ; 4 =
    couche du menu pause, plante hors de lui). Elle est rattachee au menu
    (740D30) dont la racine (noeud 0x2A4634) est masquee avant (sinon le
    menu reste dessine devant). Elle ne se termine pas seule (elle attend une
    tache de fondu absente) : le trainer la termine (740A90). Sur OUI, sa
    sequence de sortie (drapeaux globaux, fondu, 83830) est court-circuitee
    (5268DE) et le trainer ramene au menu principal (return_to_title)."""

    CSM_ENTRY, CSM_CONFIRM, CSM_COUNT, CSM_TABLE_LEA = 0x4C0B80, 0x4C0DC1, 0x4C0D09, 0x4C0DE4
    CSM_CONTINUE, CSM_SKIP, CSM_NOOP = 0x4C0DAE, 0x4C0DCA, 0x4C0DFA
    CSM_ORIGINAL = {
        CSM_ENTRY: bytes.fromhex("40534883ec30"),        # push rbx ; sub rsp,30h
        CSM_CONFIRM: bytes.fromhex("83bba00000000075e4"),  # cmp [rbx+A0h],0 ; jne continuer
        CSM_COUNT: bytes.fromhex("ba02000000"),          # mov edx,2
        CSM_TABLE_LEA: bytes.fromhex("488d0d25bc7601"),  # lea rcx,[table]
    }
    CSM_HIGHLIGHTS = (0x4A2371, 0x4AA371, 0)
    CSM_OPEN_DELAY = 0.3  # s sans mise a jour du menu -> ferme
    # Etat du menu (+0xB0) : 1 deplacement, 2 validation, 3 annulation. En
    # validation ou annulation, le jeu fait disparaitre le menu en fondu : la
    # ligne du trainer disparait aussitot (2026-10-25 : elle restait visible
    # pendant le fondu, et parfois pendant un appel Codec).
    CSM_STATE = 0xB0
    CSM_CLOSING_STATES = (2, 3)
    # CONTINUER (+0xA8) ou PASSER (+0xAC) demande : menu ferme, meme si sa
    # tache continue de tourner (vu pendant un Codec apres PASSER : tache
    # mise a jour a chaque image, +0xAC = 1, ligne restee affichee).
    CSM_CLOSE_REQUESTS = (0xA8, 0xAC)
    CSM_TASK_UPDATE_RVA = 0x4C0B80
    # Enregistrement du texte PASSER dans la scene (type 0x0A, cle, noeud
    # 0x17, parent 0x16) ; decalages relatifs a sa cle.
    CSM_TEXT_RECORD = bytes.fromhex("0a004e0345155800" "17001600")
    CSM_BAR_NODE = ((-0x148, 0x3C0), (-0x144, 0x3C00000), (-0x10C, 0x3C00000))
    CSM_TEXT_COLORS = (-0x28, -0x10, 0x88, 0xA0)
    # Liste d'affichage : commande couleur clignotante de la barre (repere),
    # copies de la position de la barre et couleurs affichees des textes.
    # Commande = code sur 1 octet (0x14, 0x16), les 3 octets suivants et le
    # mot suivant portent des parametres variables (16 0e e9 bb...). Liste propre a la scene
    # (scene+0x148, taille +0x150 ; vu : barre a liste+0x660), allouee a part :
    # sa distance au texte varie, la chercher autour faisait des faux reperes.
    CSM_LIST_ANCHOR = re.compile(rb"\x14...........\x00\x00\x00\x01"
                                 rb"\x16.......[\x00-\x80]\x80\x80\x80", re.S)
    CSM_ANCHOR_RETRY = 0.15  # s entre deux recherches de la liste
    CSM_COLOR_CMD = b"\x00\x00\x00\x01\x16"
    CSM_LIST_BAR, CSM_LIST_TEXT = (-0x50, -0x10), (0x138, 0x1D8)
    CSM_DIM = 0x80808040
    # Confirmation du jeu : fonctions (signatures verifiees) et patchs.
    CSM_DLG_FUNCS = {
        "create": (0x526980, "48895c2408574883ec2048bf"),
        "load": (0x4EE0C0, "48895c240848897424105748"),
        "attach": (0x740D30, "4883ec284c8bd14885d20f84"),
        "end": (0x740A90, "4885c90f84df000000534883"),
        "node": (0x438C00, "448b8170010000448bda4c8b"),
        "noop": (0x4C0DFA, "48c783b000000000000000"),
    }
    CSM_LAYER_CALL, CSM_LAYER_ORIGINAL = 0x4D5F7E, bytes.fromhex("e88d0d0000")
    # Liste de rendu de la couche (objet de rendu de la scene, +0x24) : le
    # menu des cinematiques est en liste 2, la fenetre serait creee en liste 1
    # (dessinee avant, donc dessous) -> « mov edx,2 » le temps de la creation.
    CSM_LIST_PARAM, CSM_LIST_ORIGINAL, CSM_LIST_MENU = 0x4D5F83, bytes.fromhex("ba01000000"), bytes.fromhex("ba02000000")
    CSM_HIDE_MENU = False
    CSM_YES_PATH, CSM_YES_ORIGINAL, CSM_YES_SKIP = 0x5268DE, bytes.fromhex("4881"), bytes.fromhex("ebca")
    CSM_DLG_LAYER = 1
    CSM_PACKAGE, CSM_DLG_RESOURCE = 0x38118E, 0x5F15E2AE
    CSM_RESOURCE_ROOTS = 0x23D2F6D0   # arbres des ressources chargees (74C0B0)
    CSM_UI_FLAGS = 0x3B7C0E0          # bit 0x2000 = fenetre de confirmation ouverte
    CSM_MENU_ROOT = 0x2A4634          # noeud racine de la scene du menu
    CSM_HIDE_DELAY, CSM_NO_DELAY, CSM_LOAD_TIMEOUT = 0.12, 0.6, 5.0
    HANDLE_MASK = 0xFFFFFFFFFFFFF

    def cutscene_quit_install(self) -> bool:
        state = getattr(self, "_csm", None)
        if state and state["pid"] == self.pid:
            return True
        if not (self.connected and self.sane):
            return False
        if not self._csm_restore_leftover():
            return False
        b = self.base
        confirm_ok = all(self.proc.read_bytes(b + rva, len(sig) // 2).hex() == sig
                         for rva, sig in self.CSM_DLG_FUNCS.values())
        confirm_ok = (confirm_ok and self.proc.read_bytes(b + self.CSM_LAYER_CALL, 5) == self.CSM_LAYER_ORIGINAL
                      and self.proc.read_bytes(b + self.CSM_LIST_PARAM, 5) == self.CSM_LIST_ORIGINAL
                      and self.proc.read_bytes(b + self.CSM_YES_PATH, 2) == self.CSM_YES_ORIGINAL)
        page = self.proc.alloc_near(b + self.CSM_ENTRY, 0x1000)
        if not page:
            return False
        table, task, tick, quit_count = page, page + 0x10, page + 0x18, page + 0x1C
        frozen = page + 0x20  # 1 = fenetre de confirmation ouverte : menu fige

        def rel(target: int, end: int) -> bytes:
            return struct.pack("<i", target - end)

        self.proc.write_bytes(table, struct.pack("<3I", *self.CSM_HIGHLIGHTS))
        entry = page + 0x40
        code = bytearray(b"\x48\x89\x0d" + rel(task, entry + 7))       # mov [tache],rcx
        code += b"\xff\x05" + rel(tick, entry + len(code) + 6)          # inc [images]
        # Octet du trainer et non le bit 0x2000 du jeu : resté levé une fois,
        # il figeait la cinematique jusqu'a la fermeture du trainer.
        code += b"\x80\x3d" + rel(frozen, entry + len(code) + 7) + b"\x00"   # cmp byte [fige],0
        code += b"\x74\x01\xc3"                                          # jz +1 ; ret (fenetre ouverte)
        code += self.CSM_ORIGINAL[self.CSM_ENTRY]
        code += b"\xe9" + rel(b + self.CSM_ENTRY + 6, entry + len(code) + 5)
        self.proc.write_bytes(entry, bytes(code))
        confirm = page + 0x80
        code = bytearray(b"\x83\xbb\xa0\x00\x00\x00\x02\x75\x0b")      # cmp [rbx+A0h],2 ; jne +0Bh
        code += b"\xff\x05" + rel(quit_count, confirm + len(code) + 6)  # inc [quitter]
        code += b"\xe9" + rel(b + (self.CSM_NOOP if confirm_ok else self.CSM_CONTINUE), confirm + len(code) + 5)
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
                     "task": None, "key": None, "anchor": None, "anchor_try": 0.0,
                     "confirm_ok": confirm_ok, "confirm": None,
                     "title": False, "label": None}
        return True

    def cutscene_title_request(self) -> bool:
        """Vrai une fois apres QUITTER confirme : le trainer pose son rideau
        noir puis ramene au menu principal (return_to_title)."""
        state = getattr(self, "_csm", None)
        if not (state and state["pid"] == self.pid and state["title"]):
            return False
        state["title"] = False
        return True

    def cutscene_quit_label(self) -> str | None:
        """Texte de la ligne QUITTER dans la langue du jeu : la description
        « Retourner a l'ecran titre. » du menu pause (numero 31), en
        majuscules comme les autres lignes ; None si indisponible."""
        state = getattr(self, "_csm", None)
        if not (state and state["pid"] == self.pid):
            return None
        if state["label"] is None:
            text = self.game_menu_text(31) if self.speed.ensure_injected(self.pid) else None
            state["label"] = text.strip().rstrip(".。").upper() if text else ""
        return state["label"] or None

    def _csm_restore_leftover(self) -> bool:
        """Vrai si les sites sont d'origine. Un detour laisse par un trainer
        ferme sans nettoyage (tue, plantage) est reconnu (sauts vers le code de
        la page : mov [tache],rcx en +0x40, cmp [rbx+A0h],2 en +0x80 ; 3
        entrees ; lea vers la page) et retire ; autre contenu : faux."""
        b, proc = self.base, self.proc
        current = {rva: proc.read_bytes(b + rva, len(original)) for rva, original in self.CSM_ORIGINAL.items()}
        if all(current[rva] == original for rva, original in self.CSM_ORIGINAL.items()):
            return True
        try:
            for rva, data in current.items():
                if data == self.CSM_ORIGINAL[rva]:
                    continue
                if rva == self.CSM_COUNT:
                    ours = data == bytes.fromhex("ba03000000")
                elif rva == self.CSM_TABLE_LEA:
                    ours = data[:3] == bytes.fromhex("488d0d")
                else:
                    target = b + rva + 5 + struct.unpack_from("<i", data, 1)[0]
                    expected = bytes.fromhex("48890d") if rva == self.CSM_ENTRY else bytes.fromhex("83bba000000002")
                    ours = data[0] == 0xE9 and proc.read_bytes(target, len(expected)) == expected
                if not ours:
                    return False
        except OSError:
            return False
        for rva, original in self.CSM_ORIGINAL.items():
            if current[rva] != original:
                proc.write_bytes(b + rva, original)
        return True

    def cutscene_quit_remove(self) -> None:
        state = getattr(self, "_csm", None)
        self._csm = None
        if not (state and state["pid"] == self.pid and self.proc):
            return
        try:
            if state.get("confirm"):
                self._csm_confirm_cleanup(state, show_menu=True)
            for rva, original in self.CSM_ORIGINAL.items():
                self.proc.write_bytes(self.base + rva, original)
        except OSError:
            pass

    def cutscene_menu_poll(self) -> tuple[bool, int | None, bool]:
        """(menu ouvert, curseur, confirmation en cours). Fait avancer la
        confirmation ; sans elle (autre version du jeu), QUITTER ramene
        directement au menu principal."""
        state = getattr(self, "_csm", None)
        if not (state and state["pid"] == self.pid):
            return False, None, False
        page = state["page"]
        task, tick, quit_count = struct.unpack("<QII", self.proc.read_bytes(page + 0x10, 16))
        now = time.monotonic()
        self._csm_late_loader(state, now)
        confirm = state["confirm"]
        if tick != state["tick"]:
            state["tick"], state["seen"] = tick, now
        quit_requested = quit_count != state["quit"]
        state["quit"] = quit_count
        # Menu fige pendant la confirmation (sa mise a jour est sautee) :
        # le compteur d'images continue, le menu reste "ouvert".
        # Tache du menu terminee a sa fermeture : le texte disparait tout de
        # suite (le delai ne sert que si elle survivait).
        alive = bool(task) and self._csm_alive(struct.unpack("<Q", self.proc.read_bytes(task + 0x30, 8))[0])
        # Toujours la tache du menu des cinematiques (memoire non reutilisee
        # par une autre tache, le Codec par exemple) : sa mise a jour 4C0B80.
        update = struct.unpack("<Q", self.proc.read_bytes(task + 0x08, 8))[0] if alive else 0
        alive = alive and update == self.base + self.CSM_TASK_UPDATE_RVA
        menu_open = alive and now - state["seen"] <= self.CSM_OPEN_DELAY
        if confirm:
            # Pas de delai ici : jeu sans le focus = boucle arretee, compteur
            # fige, mais la confirmation est toujours la.
            if not alive:
                self._csm_confirm_cleanup(state, show_menu=False)
                return False, None, False
            self._csm_confirm_step(state, now)
            confirm = state["confirm"]
            return True, 2, bool(confirm and confirm["stage"] in ("open", "closing"))
        if not menu_open:
            return False, None, False
        if quit_requested:
            if state["confirm_ok"]:
                self._csm_confirm_start(state, task, now)
                return True, 2, False
            state["title"] = True
        if struct.unpack("<i", self.proc.read_bytes(task + self.CSM_STATE, 4))[0] in self.CSM_CLOSING_STATES:
            return False, None, False  # fondu de fermeture du jeu
        if any(struct.unpack("<i", self.proc.read_bytes(task + offset, 4))[0] for offset in self.CSM_CLOSE_REQUESTS):
            return False, None, False  # CONTINUER ou PASSER deja choisi
        cursor = struct.unpack("<i", self.proc.read_bytes(task + 0xA0, 4))[0]
        if cursor == 2:
            self._csm_highlight_quit(state, task)
        return True, cursor, False

    # --- confirmation du jeu ---

    def _csm_alive(self, handle: int | None) -> bool:
        if not handle:
            return False
        try:
            return struct.unpack("<Q", self.proc.read_bytes((handle & self.HANDLE_MASK) + 0x30, 8))[0] == handle
        except OSError:
            return False

    def _csm_resource_loaded(self, key: int) -> bool:
        def q(address: int) -> int:
            return struct.unpack("<Q", self.proc.read_bytes(address, 8))[0]

        node = q(self.base + self.CSM_RESOURCE_ROOTS + ((key >> 3) & 0xF) * 8)
        wanted = key & 0x7FFFFFFF
        for _ in range(64):
            if not node:
                return False
            current = struct.unpack("<I", self.proc.read_bytes(node + 0x10, 4))[0] & 0x7FFFFFFF
            if current == wanted:
                return True
            node = q(node) if wanted < current else q(node + 8)
        return False

    def _csm_menu_root(self, show: bool, root: int | None) -> None:
        if not root:
            return
        flags = struct.unpack("<I", self.proc.read_bytes(root, 4))[0]
        # bit 22 = voulu affiche, bit 28 = masque, bit 30 = a recalculer
        flags = (flags | 0x400000) if show else (flags & ~0x400000)
        self.proc.write_bytes(root, struct.pack("<I", flags | 0x40000000))

    def _csm_confirm_start(self, state: dict, task: int, now: float) -> None:
        call, b = self.speed.game_call, self.base
        scene = struct.unpack("<Q", self.proc.read_bytes(task + 0x98, 8))[0]
        root = None
        if self.CSM_HIDE_MENU:
            root = call(b + self.CSM_DLG_FUNCS["node"][0], scene, self.CSM_MENU_ROOT) if scene else None
            self._csm_menu_root(False, root)
        state["confirm"] = {"stage": "hide", "since": now, "task": task, "root": root,
                            "loader": None, "dialog": None}

    def _csm_confirm_step(self, state: dict, now: float) -> None:
        c, call, b = state["confirm"], self.speed.game_call, self.base
        stage = c["stage"]
        if stage == "hide" and now - c["since"] >= self.CSM_HIDE_DELAY:
            if not self._csm_resource_loaded(self.CSM_DLG_RESOURCE):
                c["loader"] = call(b + self.CSM_DLG_FUNCS["load"][0], self.CSM_PACKAGE)
            c["stage"], c["since"] = "load", now
        elif stage == "load":
            if self._csm_resource_loaded(self.CSM_DLG_RESOURCE):
                self.proc.write_bytes(b + self.CSM_YES_PATH, self.CSM_YES_SKIP)
                self.proc.write_bytes(b + self.CSM_LAYER_CALL, b"\xb8" + struct.pack("<I", self.CSM_DLG_LAYER))
                self.proc.write_bytes(b + self.CSM_LIST_PARAM, self.CSM_LIST_MENU)
                try:
                    dialog = call(b + self.CSM_DLG_FUNCS["create"][0])
                finally:
                    self.proc.write_bytes(b + self.CSM_LAYER_CALL, self.CSM_LAYER_ORIGINAL)
                    self.proc.write_bytes(b + self.CSM_LIST_PARAM, self.CSM_LIST_ORIGINAL)
                if not self._csm_alive(dialog):
                    self._csm_confirm_cleanup(state, show_menu=True)
                    return
                call(b + self.CSM_DLG_FUNCS["attach"][0], c["task"], dialog)
                self.proc.write_bytes(state["page"] + 0x20, b"\x01")  # menu fige
                c["dialog"], c["stage"] = dialog, "open"
            elif now - c["since"] > self.CSM_LOAD_TIMEOUT:
                self._csm_confirm_cleanup(state, show_menu=True)
        elif stage == "open":
            dialog = c["dialog"]
            if not self._csm_alive(dialog):
                self._csm_confirm_cleanup(state, show_menu=True)
                return
            cursor, closing = struct.unpack("<ii", self.proc.read_bytes((dialog & self.HANDLE_MASK) + 0x98, 8))
            if closing:
                if cursor == 0:  # OUI
                    self._csm_confirm_cleanup(state, show_menu=False, to_title=True)
                    state["title"] = True
                else:
                    c["stage"], c["since"] = "closing", now
        elif stage == "closing" and now - c["since"] >= self.CSM_NO_DELAY:
            self._csm_confirm_cleanup(state, show_menu=True)

    def _csm_confirm_cleanup(self, state: dict, show_menu: bool, to_title: bool = False) -> None:
        c, call, b = state["confirm"], self.speed.game_call, self.base
        state["confirm"] = None
        if not c:
            return
        if self._csm_alive(c["dialog"]):
            call(b + self.CSM_DLG_FUNCS["end"][0], c["dialog"] & self.HANDLE_MASK)
        self.proc.write_bytes(state["page"] + 0x20, b"\x00")  # menu libere
        if not self._csm_alive(c["dialog"]):  # bit « fenetre ouverte » du jeu, s'il est reste leve
            flags = struct.unpack("<Q", self.proc.read_bytes(b + self.CSM_UI_FLAGS, 8))[0]
            if flags & 0x2000:
                self.proc.write_bytes(b + self.CSM_UI_FLAGS, struct.pack("<Q", flags & ~0x2000))
        self.proc.write_bytes(b + self.CSM_YES_PATH, self.CSM_YES_ORIGINAL)
        # Tache de chargement terminee seulement une fois le paquet charge :
        # la couper en pleine lecture peut corrompre la memoire (plantage
        # du 2026-10-25 dans la lecture 128DD0, apres le mode photo) ; sinon
        # elle est terminee plus tard (_csm_late_loader).
        # Retour au titre (OUI) : la tache n'est pas terminee par le trainer.
        # Liberer le paquet juste avant le chargement des paquets du titre
        # plantait dans la meme lecture 128DD0 (2026-10-25, deux fois, apres
        # Liquid vaincu puis retour au titre) ; le retour au titre detruit de
        # toute facon les taches de la partie. Hypothese, a confirmer.
        if self._csm_alive(c["loader"]) and not to_title:
            if self._csm_resource_loaded(self.CSM_DLG_RESOURCE):
                call(b + self.CSM_DLG_FUNCS["end"][0], c["loader"] & self.HANDLE_MASK)
            else:
                state["late_loader"] = (c["loader"], time.monotonic())
        if show_menu:
            self._csm_menu_root(True, c["root"])

    CSM_LATE_LOADER_TIMEOUT = 20.0  # s ; au-dela, la tache se termine seule (delai du jeu)

    def _csm_late_loader(self, state: dict, now: float) -> None:
        """Termine une tache de chargement laissee en cours au nettoyage, une
        fois le paquet charge."""
        late = state.get("late_loader")
        if not late:
            return
        loader, since = late
        if not self._csm_alive(loader) or now - since > self.CSM_LATE_LOADER_TIMEOUT:
            state["late_loader"] = None
        elif self._csm_resource_loaded(self.CSM_DLG_RESOURCE):
            state["late_loader"] = None
            self.speed.game_call(self.base + self.CSM_DLG_FUNCS["end"][0], loader & self.HANDLE_MASK)

    def _csm_highlight_quit(self, state: dict, task: int) -> None:
        now = time.monotonic()
        if state["task"] != task:
            state["task"], state["key"], state["anchor"], state["anchor_try"] = task, None, None, 0.0
            scene = struct.unpack("<Q", self.proc.read_bytes(task + 0x98, 8))[0]
            state["scene"] = scene
            if not scene:
                return
            low = scene - 0x1000
            data = self.proc.read_bytes(low, 0x21000)
            found = data.find(self.CSM_TEXT_RECORD)
            if found < 0:
                return
            state["key"] = low + found + 4
        key = state["key"]
        # Repere cherche dans la liste d'affichage de la scene (adresse en
        # scene+0x148, taille en +0x150) ; nouvel essai tant qu'il manque.
        if key and not state["anchor"] and now - state["anchor_try"] >= self.CSM_ANCHOR_RETRY:
            state["anchor_try"] = now
            scene = state["scene"]
            start = struct.unpack("<Q", self.proc.read_bytes(scene + 0x148, 8))[0]
            size = struct.unpack("<I", self.proc.read_bytes(scene + 0x150, 4))[0]
            area = self.proc.read_bytes(start, min(size, 0x10000)) if start and size else b""
            # Couleur d'un texte = commande 0x16 precedee de 00000001. Un autre
            # element (titre) a la meme forme, couleurs fixes 80808080 : la
            # barre est celle qui clignote, sinon la derniere.
            found = [match.end() - 4 for match in self.CSM_LIST_ANCHOR.finditer(area)
                     if all(area[match.end() - 4 + off - 12:match.end() - 4 + off - 7] == self.CSM_COLOR_CMD
                            for off in self.CSM_LIST_TEXT)]
            if found:
                blinking = [a for a in found if area[a] != 0x80]
                state["anchor"] = start + (blinking or found)[-1]
        anchor = state["anchor"]
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
