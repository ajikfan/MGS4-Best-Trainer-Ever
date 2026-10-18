"""MGS4Live : position de Snake, jauges du joueur et des vehicules, vitals."""
import struct
import threading
import time

from mgs4trainer.core.gamedata import VITALS
from mgs4trainer.core.winproc import MEM_COMMIT, PAGE_EXECUTE_READWRITE, kernel32


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

    # Evenements de Snake (2026-10-17). Deux machines a etats a partir du
    # composant joueur (meme disposition : vtable, etat courant +0x60, etat
    # demande +0x68 ; le jeu y ecrit lui-meme ses transitions) :
    #  - principale, composant+0x1210 (vtable 18B1518) : debout immobile
    #    9E4FC0, accroupi immobile 9DF1E0 ; mal de dos accroupi = demande
    #    9DD440 depuis 9DF1E0 (~3,5 s ; se relever ou bouger l'interrompt) ;
    #  - actions speciales, composant+0x1BB0 (vtable 18B1EC8), en veille quand
    #    [m+0x50] == 1. Le gestionnaire des machines (90A350(gestionnaire =
    #    [m+0x38], machine)) appelle la surveillance de la machine en veille
    #    (vtable+0x10, 9F35D0, qui se demande par ex. A050C0 a une chute) ; si
    #    elle renvoie 1, il verifie les conflits, suspend les machines en
    #    conflit (l'etat principal passe a 0) et active la machine. Ecrire la
    #    demande seule ne fait rien : un petit code (une fois par processus)
    #    refait le prologue de 90A350 et saute en 90A380, comme si la
    #    surveillance avait dit oui, puis le jeu fait le reste (valide).
    #  - mal de dos debout = A05B20 demande directement (sans A050C0 qui joue
    #    la chute), [m+0x90] = 0 (degats de chute appliques par A05B20 : aucun).
    #    A05B20 joue a son entree le mouvement 0x3F8F1 (impact + se tenir le
    #    dos, ~1,9 s ; immediat de "mov qword [rsp+0x80], 0x3F8F1" en A05DDB)
    #    et emet un bruit pour les soldats (87680).
    #  - mouvements : meme chemin, l'immediat d'A05DDB remplace le temps de
    #    l'animation puis remis. SNAKE_MOTIONS = mouvements que le code des
    #    etats de Snake utilise lui-meme (immediats 0x3F000-0x40FFF releves
    #    dans 900000-B00000), pas d'identifiants au hasard (un mouvement
    #    absent peut planter le jeu). Joues debout ; ceux d'une autre posture
    #    peuvent donner un resultat etrange. Releves en jeu : 0x3F8F1 mal de
    #    dos (impact + dos), 0x3F8F2 s'accroupit et se tape le dos, 0x3F8F3
    #    s'ecrase au sol sur le dos, 0x3F8F4 squat rapide, 0x3F8B0 passe
    #    par-dessus une caisse, 0x3F8B1 petit saut en avant. Catalogue complet
    #    decrit par l'utilisateur (locales "motion.0x..."). 40 de plus le
    #    2026-10-17 (autres encodages : mov dword / registre, dans le code
    #    des actions de Snake 900000-A50000, dont 0x1BF802/803/0x1BFC02
    #    accroupis) a decouvrir (recherche du vomissement).
    SNAKE_MACHINE_OFFSET = 0x1210
    SNAKE_MACHINE_VTABLE_RVA = 0x18B1518
    SNAKE_SPECIAL_OFFSET = 0x1BB0
    SNAKE_SPECIAL_VTABLE_RVA = 0x18B1EC8
    SNAKE_STAND_STATE = 0x9E4FC0
    SNAKE_CROUCH_STATE = 0x9DF1E0
    SNAKE_CROUCH_BACK_PAIN = 0x9DD440
    # Posture reprise apres une action speciale (2026-10-17, valide en jeu) :
    # A05B20 impose "debout" (9E4FC0) comme etat de reprise de la machine
    # principale, au dernier moment (le maintenir pendant l'action ne sert a
    # rien). On redemande donc l'etat d'avant des que le jeu rend la main
    # debout ; transitions propres en jeu. Seulement ces postures immobiles :
    # accroupi 9DF1E0, allonge 9D4FE0, face contre le sol 9D54D0, sur le dos
    # (pas completement etale) 9E9850, sur le dos etale 9E9D30 (reprendre un etat en mouvement
    # ou une transition n'a pas de sens).
    SNAKE_RESUME_STATES = (0x9DF1E0, 0x9D4FE0, 0x9D54D0, 0x9E9850, 0x9E9D30)
    SNAKE_STAND_BACK_PAIN = 0xA05B20
    SNAKE_ACTIVATE = (0x90A350, "48895c241048896c2418574883ec20837a5001488bfa488be90f85")
    SNAKE_ACTIVATE_RESUME = (0x90A380, "488b47184885c0")
    SNAKE_MOTION_SITE = (0xA05DDB, bytes.fromhex("48c7842480000000f1f80300"))
    # Son joue par A05B20 pendant l'animation : call 97C690(..., 7) en A05C7E
    # (valide en jeu : coupe, plus de son ; ni l'entree 8DAFA0 0x53/0x55 ni
    # l'animation). Coupe le temps des actions du trainer, remis ensuite ;
    # une vraie chute garde son son.
    SNAKE_SOUND_SITE = (0xA05C7E, bytes.fromhex("e80d6af7ff"), bytes.fromhex("0f1f440000"))
    # "vomit" : 0x3F84C debout, 0x3F84D accroupi (choisi selon la posture).
    SNAKE_EVENTS = ("fall_pain", "back_pain", "vomit")
    SNAKE_VOMIT = (0x3F84C, 0x3F84D)
    SNAKE_MOTIONS = (
        0x3F12F, 0x3F130, 0x3F131, 0x3F403, 0x3F408, 0x3F409, 0x3F506, 0x3F801, 0x3F82F, 0x3F830,
        0x3F831, 0x3F833, 0x3F834, 0x3F847, 0x3F848, 0x3F849, 0x3F84A, 0x3F84B, 0x3F84C, 0x3F84D,
        0x3F855, 0x3F856, 0x3F857, 0x3F858, 0x3F859, 0x3F85A, 0x3F85B, 0x3F85D, 0x3F85E, 0x3F861,
        0x3F862, 0x3F863, 0x3F864, 0x3F865, 0x3F866, 0x3F867, 0x3F869, 0x3F86A, 0x3F86C, 0x3F86D,
        0x3F86E, 0x3F86F, 0x3F870, 0x3F871, 0x3F872, 0x3F873, 0x3F87C, 0x3F882, 0x3F883, 0x3F884,
        0x3F885, 0x3F888, 0x3F889, 0x3F89E, 0x3F8A0, 0x3F8A1, 0x3F8A3, 0x3F8A8, 0x3F8AA, 0x3F8AB,
        0x3F8B0, 0x3F8B1, 0x3F8B3, 0x3F8B4, 0x3F8B5, 0x3F8B6, 0x3F8B7, 0x3F8B9, 0x3F8BA, 0x3F8BB,
        0x3F8BD, 0x3F8BE, 0x3F8BF, 0x3F8C0, 0x3F8C1, 0x3F8C2, 0x3F8C3, 0x3F8C4, 0x3F8C5, 0x3F8C6,
        0x3F8C7, 0x3F8C8, 0x3F8C9, 0x3F8D2, 0x3F8D3, 0x3F8D4, 0x3F8D6, 0x3F8D7, 0x3F8D8, 0x3F8DA,
        0x3F8DD, 0x3F8E5, 0x3F8E7, 0x3F8E8, 0x3F8EA, 0x3F8EF, 0x3F8F1, 0x3F8F2, 0x3F8F3, 0x3F8F4,
        0x3F8F5, 0x3F8F7, 0x3F8F9, 0x3F8FA, 0x3F8FB, 0x3F8FC, 0x3F8FD, 0x3F8FE, 0x3F8FF, 0x3F900,
        0x3F901, 0x3F902, 0x3F904, 0x3F905, 0x3F907, 0x3F909, 0x3F90A, 0x3F90B, 0x3F90C, 0x3F90D,
        0x3F90E, 0x3F90F, 0x3F910, 0x3F913, 0x3F914, 0x3F915, 0x3F916, 0x3F917, 0x3F918, 0x3F919,
        0x3F91A, 0x3F91B, 0x3F91C, 0x3FA03, 0x3FA04, 0x3FA05, 0x3FA06, 0x3FA07, 0x3FA08, 0x3FA09,
        0x3FA0A, 0x3FA0B, 0x3FA8E, 0x3FA8F, 0x3FA94, 0x3FA95, 0x3FA96, 0x3FA97, 0x3FAAF, 0x3FAB3,
        0x3FAB7, 0x3FAB9, 0x3FC01, 0x3FC26, 0x3FC28, 0x3FC51, 0x3FC52, 0x3FC53, 0x3FC54, 0x3FC62,
        0x3FC63, 0x3FC6B, 0x3FC74, 0x3FC75, 0x3FC76, 0x3FC77, 0x3FC78, 0x3FC79, 0x3FC7A, 0x3FC7B,
        0x3FC80, 0x3FC81, 0x3FC86, 0x3FC87, 0x3FC9F, 0x3FCA2, 0x3FCA4, 0x3FCA5, 0x3FCA6, 0x3FCA7,
        0x3FCA9, 0x3FCB2, 0x3FCB8, 0x3FCBC, 0x3FCD5, 0x3FCD9, 0x3FCDB, 0x3FCDC, 0x3FCE6, 0x3FCE9,
        0x3FCEB, 0x3FCEC, 0x3FCED, 0x3FCEE, 0x3FCF0, 0x3FCF6, 0x3FCF8, 0x3FD03, 0x3FD06, 0x3FD11,
        0x3FD12, 0x3FD1D, 0x3FD1E, 0x3FD1F, 0x3FD20, 0x3FD21, 0x3FD26, 0x3FD83, 0x3FD86, 0x3FEB8,
        0x3FEBA, 0x1BF802, 0x1BF803, 0x1BFC02,
    )

    def _snake_machines(self) -> tuple[int, int] | None:
        """(machine principale, machine des actions speciales) de Snake."""
        component = self._grip_component()
        if component is None:
            return None
        main, special = component + self.SNAKE_MACHINE_OFFSET, component + self.SNAKE_SPECIAL_OFFSET
        if (struct.unpack("<Q", self.proc.read_bytes(main, 8))[0] != self.base + self.SNAKE_MACHINE_VTABLE_RVA
                or struct.unpack("<Q", self.proc.read_bytes(special, 8))[0] != self.base + self.SNAKE_SPECIAL_VTABLE_RVA):
            return None
        return main, special

    def _snake_activate_stub(self) -> int:
        """Code qui active la machine passee en rdx comme si sa surveillance
        avait renvoye 1 (prologue de 90A350 puis saut en 90A380)."""
        if getattr(self, "_snake_stub_pid", None) == self.pid and self._snake_stub_addr:
            return self._snake_stub_addr
        if self._live_funcs({"activate": self.SNAKE_ACTIVATE, "resume": self.SNAKE_ACTIVATE_RESUME}) is None:
            return 0
        stub = kernel32.VirtualAllocEx(self.proc.handle, None, 0x1000, MEM_COMMIT | 0x2000, PAGE_EXECUTE_READWRITE)
        if not stub:
            return 0
        self.proc.write_bytes(stub, bytes.fromhex("48895c2410" "48896c2418" "57" "4883ec20"   # prologue de 90A350
                                                  "488bfa" "488be9" "ff2500000000")           # mov rdi,rdx ; mov rbp,rcx ; jmp
                              + struct.pack("<Q", self.base + self.SNAKE_ACTIVATE_RESUME[0]))
        self._snake_stub_addr, self._snake_stub_pid = stub, self.pid
        return stub

    def _snake_restore_motion(self) -> None:
        """Remet le mouvement et le son d'origine d'A05B20."""
        rva, original = self.SNAKE_MOTION_SITE
        current = self.proc.read_bytes(self.base + rva, len(original))
        if current != original and current[:8] == original[:8]:
            self.proc.write_bytes(self.base + rva, original)
        rva, original, muted = self.SNAKE_SOUND_SITE
        if self.proc.read_bytes(self.base + rva, len(original)) == muted:
            self.proc.write_bytes(self.base + rva, original)

    def _snake_play_special(self, main: int, special: int, state: int, motion: int | None) -> bool:
        """Lance l'etat `state` sur la machine speciale en veille, par le
        chemin d'activation du jeu ; `motion` remplace le temps de l'action
        le mouvement joue par A05B20 (remis ensuite, dans un fil). Snake
        reprend ensuite sa posture (SNAKE_RESUME_STATES)."""
        # En veille et sans action en cours. Une demande peut rester en attente
        # (ex. A050C0 laisse par le jeu au chargement d'une zone, Snake apparu
        # un peu en l'air) : elle ne part qu'a une activation, qui l'ecrase.
        if (struct.unpack("<i", self.proc.read_bytes(special + 0x50, 4))[0] != 1
                or struct.unpack("<Q", self.proc.read_bytes(special + 0x60, 8))[0]):
            return False
        if getattr(self, "_snake_event_busy", False) or not self.speed.main_loop_hook_installed():
            return False
        stub = self._snake_activate_stub()
        if not stub:
            return False
        rva, original = self.SNAKE_MOTION_SITE
        sound_rva, sound_original, sound_muted = self.SNAKE_SOUND_SITE
        if (self.proc.read_bytes(self.base + rva, len(original))[:8] != original[:8]
                or self.proc.read_bytes(self.base + sound_rva, 5) not in (sound_original, sound_muted)):
            return False
        manager = struct.unpack("<Q", self.proc.read_bytes(special + 0x38, 8))[0]
        before = struct.unpack("<Q", self.proc.read_bytes(main + 0x60, 8))[0]
        self._snake_event_busy = True

        def run():
            try:
                if motion is not None:
                    self.proc.write_bytes(self.base + rva + 8, struct.pack("<I", motion))
                self.proc.write_bytes(self.base + sound_rva, sound_muted)
                self.proc.write_bytes(special + 0x90, struct.pack("<i", 0))
                self.proc.write_bytes(special + 0x68, struct.pack("<Q", self.base + state))
                self.speed.game_call(stub, manager, special)
                # attendre la fin de l'action avant de remettre le mouvement
                # (pas d'activation au bout d'1 s : abandon)
                started, active = time.monotonic(), False
                while time.monotonic() - started < 15:
                    current = struct.unpack("<Q", self.proc.read_bytes(special + 0x60, 8))[0]
                    active = active or bool(current)
                    if (active and not current) or (not active and time.monotonic() - started > 1):
                        break
                    time.sleep(0.02)
                if struct.unpack("<Q", self.proc.read_bytes(special + 0x68, 8))[0] == self.base + state:
                    self.proc.write_bytes(special + 0x68, struct.pack("<Q", 0))  # demande non prise
                elif active and before - self.base in self.SNAKE_RESUME_STATES:
                    returned = time.monotonic()
                    while time.monotonic() - returned < 1:
                        current, request = struct.unpack("<QQ", self.proc.read_bytes(main + 0x60, 16))
                        if current:
                            if current == self.base + self.SNAKE_STAND_STATE and not request:
                                self.proc.write_bytes(main + 0x68, struct.pack("<Q", before))
                            break
                        time.sleep(0.002)
            except (OSError, AttributeError, TypeError):
                pass
            finally:
                try:
                    self._snake_restore_motion()
                except (OSError, AttributeError, TypeError):
                    pass
                self._snake_event_busy = False
        threading.Thread(target=run, daemon=True).start()
        return True

    def trigger_snake_event(self, name: str) -> bool:
        """"fall_pain" (reception d'une chute de haut, mouvement 0x3F8F1),
        "back_pain" (mal de dos accroupi, 9DD440 / mouvement 0x1BF801,
        accroupi immobile seulement) ou un mouvement de SNAKE_MOTIONS
        (entier). Actions speciales depuis n'importe quel etat principal."""
        if not (self.connected and self.sane):
            return False
        machines = self._snake_machines()
        if machines is None:
            return False
        main, special = machines
        current, request = struct.unpack("<QQ", self.proc.read_bytes(main + 0x60, 16))
        if request:
            return False
        if name == "back_pain":
            if current != self.base + self.SNAKE_CROUCH_STATE:
                return False
            self.proc.write_bytes(main + 0x68, struct.pack("<Q", self.base + self.SNAKE_CROUCH_BACK_PAIN))
            return True
        # Actions speciales : depuis n'importe quel etat principal (le jeu
        # suspend lui-meme l'etat en cours, comme pour un coup recu).
        if not current:
            return False
        if name == "vomit":
            motion = self.SNAKE_VOMIT[current == self.base + self.SNAKE_CROUCH_STATE]
        else:
            motion = None if name == "fall_pain" else name
        if motion is not None and motion not in self.SNAKE_MOTIONS:
            return False
        return self._snake_play_special(main, special, self.SNAKE_STAND_BACK_PAIN, motion)

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

    # Allies (2026-10-16, combat contre Screaming Mantis, Meryl et Johnny
    # presents) : objet de vie comme les soldats (vtable mgs4+18BC1B0 : vie
    # +0x314, max +0x318, endurance +0x31C, max +0x320, sommeil +0x324), a
    # acteur+0x42B0 et +0x1E8, et l'objet pointe son acteur a +0x8. Reconnus
    # par leur classe d'acteur et acteur+0xC08 (stable endormi comme eveille,
    # sans doute un hache de modele) ; les deux changent selon l'acte, d'ou
    # une signature par acte, chacune confirmee en jeu (soin par le trainer
    # visible a l'ecran) :
    # - Meryl, acte 5 : classe 190EF18, 0xF13930 (vie 2000). Sa classe compte
    #   aussi 6 places d'equipe inactives (0x7137F2, place acteur+0x43D0 de 0
    #   a 5 ; Meryl 6). Acte 1 : classe 18E65C8, meme 0xF13930 (vie 30000).
    # - Johnny, acte 5 : classe 18E4FA8, 0x86A795 (vie 1000 ; endormi,
    #   sommeil -90000). Acte 1 : meme classe, 0xC13869 (vie 30000). Dans la
    #   liste du gestionnaire d'alerte, comme les soldats.
    # - Jonathan (acte 1) : classe 18E5870, 0xF1379E ; Ed (acte 1) : classe
    #   18E5EF8, 0x213715 (2026-10-18 : vie de 18E5870 baissee a moitie, vue
    #   en jeu sur Jonathan ; Ed par elimination). Vie 30000 ou 12000 selon
    #   le moment. Meme machine a etats que Johnny/Meryl acte 1 (+0xE8D0,
    #   etat 6 EB13F0).
    # Pieges : acteur+0x68 (et la fiche +0x40) est un etat (0x1C endormie, 1
    # eveillee), pas un numero de personnage ; le "Rat01" du Solid Eye est le
    # nom de l'unite ; le hache de l'objet de script [+0x38]-0x10 change a
    # chaque rechargement ; une place inactive de la classe de Meryl a eu sa
    # jauge a 0 au moment ou Johnny dormait (fausse piste, 1re version).
    # Aucun pointeur fixe vers eux : on cherche les objets dans l'allocation
    # du tas des acteurs (celle de l'acteur de Snake, ~360 Mo, ~1 s) dans un
    # fil a part, puis on garde les adresses tant qu'elles restent valides.
    # ALLIES : nom -> signatures (classe, +0xC08). ALLY_DEATH_CLASSES :
    # classes dont la mort par appels directs (ci-dessous) est connue ; voir
    # aussi ALLY_HIT_STATES.
    ALLIES = {
        "meryl": {(0x190EF18, 0xF13930), (0x18E65C8, 0xF13930)},
        "johnny": {(0x18E4FA8, 0x86A795), (0x18E4FA8, 0xC13869)},
        "jonathan": {(0x18E5870, 0xF1379E)},
        "ed": {(0x18E5EF8, 0x213715)},
    }
    ALLY_ID_OFFSET = 0xC08
    ALLY_DEATH_CLASSES = {0x190EF18}
    ALLY_GAUGES = {"meryl": ("meryl", 0x314), "meryl_stamina": ("meryl", 0x31C),
                   "johnny": ("johnny", 0x314), "johnny_stamina": ("johnny", 0x31C),
                   "jonathan": ("jonathan", 0x314), "jonathan_stamina": ("jonathan", 0x31C),
                   "ed": ("ed", 0x314), "ed_stamina": ("ed", 0x31C)}
    ALLY_SCAN_INTERVAL = 3.0
    # Vie a 0 seule ne tue pas (2026-10-16) : le jeu ne verifie la vie
    # qu'au moment d'un coup (14B0130, ecriture 14B038D). Si vie <= 0 :
    # endurance 0 (sauf acteur+0x43D4 == 1, "important", cas de Meryl), puis
    # 144A020(acteur) (previent un gestionnaire si +0x43DC), 144A5A0(acteur)
    # (mort : +0x43D8 = 2, message 0x44000E si +0x43D4 == 1, animation) et
    # 149C0F0(acteur) (cri, voix 0x197C si +0x43D4 == 1), puis des compteurs
    # de stats (non reproduits). On rejoue le meme chemin.
    ALLY_DEATH_FUNCS = {
        "notify": (0x144A020, "4883ec2883b9dc4300000074"),
        "die": (0x144A5A0, "40534883ec20c781d8430000"),
        "cry": (0x149C0F0, "4883ec3883b9d44300000175"),
    }
    ALLY_DEAD_STATE = (0x43D8, 2)
    ALLY_IMPORTANT = (0x43D4, 1)

    # Allie invulnerable (2026-10-16), ses deux jauges verrouillees : on
    # detourne l'entree de la fonction des coups de sa classe vers un petit
    # code qui sort sans degats si l'acteur touche est l'un de ceux ecrits en
    # tete du code (ALLY_GUARD_SLOTS places, 0 = libre), sinon refait les
    # octets remplaces et revient. Fonctions partagees avec les autres acteurs
    # de la classe : seuls les acteurs designes sont concernes.
    # - Classe de Meryl (190EF18) : 14AFB10, acteur dans rsi. Son test
    #   d'invulnerabilite (14AFBC1 : mov edx,0x100000 ; call 144A8E0 = test
    #   [acteur+0x4408] ; jne 14B05B5 = sortie sans degats) : poser ce bit de
    #   l'exterieur ne tient pas (le jeu recalcule +0x4408), on detourne le
    #   "mov edx" (5 octets) et on sort par 14B05B5.
    # - Classe de Johnny (18E4FA8) : fonction des coups des soldats C52190
    #   (acteur dans rdx, objet de vie r8 ; ecriture de la vie C5244D, trouvee
    #   par point d'arret materiel). Pas de test d'invulnerabilite : on
    #   detourne le premier "mov [rsp+8],rbx" (5 octets) et on sort par un
    #   ret (aucun appelant n'utilise la valeur de retour). Les sites de
    #   "Un coup, un mort" (C5223E, C523C3) sont plus loin, sans chevauchement.
    # Chaque garde : magie a +0x20 (la retrouver apres un redemarrage du
    # trainer), code a +0x30. ALLY_GUARDS : nom -> (site, octets d'origine
    # verifies, cmp reg,[rip+x] (3 octets), sortie (rva) ou None = ret,
    # magie, classes).
    ALLY_GUARD_SLOTS = 4
    ALLY_GUARD_CODE = 0x30
    ALLY_GUARDS = {
        "ally_class": (0x14AFBC1, bytes.fromhex("ba00001000488bcee812adf9ff85c00f85df090000"),
                       bytes.fromhex("483b35"), 0x14B05B5, b"MGS4ALLY", {0x190EF18}),
        "soldier_class": (0xC52190, bytes.fromhex("48895c240848896c241848897424205741544155"),
                          bytes.fromhex("483b15"), None, b"MGS4SOLD", {0x18E4FA8, 0x18E65C8, 0x18E5870, 0x18E5EF8}),
    }
    # Premiere version de la garde de Meryl (une place a +0, magie a +8, code
    # a +0x10) : retiree et remplacee si on la retrouve dans le jeu.
    ALLY_GUARD_LEGACY = (8, b"MGS4MRYL", 0x10)

    def _ally_guard(self, name: str, install: bool) -> int:
        """Adresse de la garde `name` (posee une fois par processus si
        `install`, retrouvee apres un redemarrage du trainer), 0 sinon."""
        rva, original, compare, exit_rva, magic, _classes = self.ALLY_GUARDS[name]
        site = self.base + rva
        cache = getattr(self, "_ally_guard_cache", {})
        if cache.get(name, (0, None))[1] == self.pid:
            return cache[name][0]
        current = self.proc.read_bytes(site, len(original))
        if current[0] == 0xE9 and current[5:] == original[5:]:
            target = site + 5 + struct.unpack("<i", current[1:5])[0]
            magic_at, legacy_magic, legacy_code = self.ALLY_GUARD_LEGACY
            try:
                if self.proc.read_bytes(target - self.ALLY_GUARD_CODE + 0x20, 8) == magic:
                    guard = target - self.ALLY_GUARD_CODE
                elif self.proc.read_bytes(target - legacy_code + magic_at, 8) == legacy_magic:
                    self.proc.write_bytes(site, original[:5])
                    return self._ally_guard(name, install)
                else:
                    return 0
            except OSError:
                return 0
        elif current == original and install:
            guard = self.proc.alloc_near(site)
            if not guard:
                return 0
            code_start = guard + self.ALLY_GUARD_CODE

            def rel(source_end: int, destination: int) -> bytes:
                return struct.pack("<i", destination - source_end)
            exit_stub = code_start + self.ALLY_GUARD_SLOTS * 13 + 10
            code = bytearray()
            for slot in range(self.ALLY_GUARD_SLOTS):
                code += compare + rel(code_start + len(code) + 7, guard + 8 * slot)  # cmp reg,[place]
                code += bytes.fromhex("0f84") + rel(code_start + len(code) + 6, exit_stub)  # je sortie
            code += original[:5] + b"\xe9" + rel(code_start + len(code) + 10, site + 5)  # octets remplaces ; jmp
            if exit_rva is None:
                code += b"\xc3"                                                      # sortie : ret
            else:
                code += b"\xe9" + rel(code_start + len(code) + 5, self.base + exit_rva)  # sortie : jmp
            self.proc.write_bytes(guard, bytes(8 * self.ALLY_GUARD_SLOTS) + magic
                                  + bytes(self.ALLY_GUARD_CODE - 0x28) + bytes(code))
            self.proc.write_bytes(site, b"\xe9" + rel(site + 5, code_start))
        else:
            return 0
        cache[name] = (guard, self.pid)
        self._ally_guard_cache = cache
        return guard

    # Verrou d'une jauge d'allie (2026-10-18, demande utilisateur : plus de
    # reecriture permanente) : le jeu n'ecrit plus cette jauge, pour cet allie
    # seulement. Une garde par instruction d'ecriture : si l'objet de vie (le
    # registre de l'instruction) figure dans la liste de la jauge, l'ecriture
    # est sautee, sinon elle se fait. Sites (instruction deplacee dans le code
    # de garde ; la suite ne lit pas les indicateurs : jmp, ret ou neg) :
    #  - vie : C5244D (coups des soldats : Johnny, Ed, Jonathan, Meryl acte 1,
    #    rdi), C528A7 (sous-fonction C52810, r9), 14B038D (coups de Meryl
    #    acte 5, r14) ;
    #  - endurance : B800B0 (retrait generique, r8) en B80109 et B80135 (K.O.,
    #    valeur tres negative) et B801B3 (baisse normale), 14B0160 (Meryl
    #    acte 5, r14).
    # Un seul bloc pres du module : listes vie (+0x00) et endurance (+0x40),
    # ALLY_LOCK_SLOTS objets chacune (0 = libre), magie a +0x80, codes a
    # +0x100 (0x80 chacun, dans l'ordre d'ALLY_WRITE_SITES).
    ALLY_LOCK_SLOTS = 8
    ALLY_LOCK_MAGIC = b"MGS4FRZ1"
    ALLY_WRITE_SITES = (
        # (site, octets d'origine (instruction + suite verifiee), longueur de
        #  l'instruction, "cmp reg,[rip+x]", liste)
        (0xC5244D, bytes.fromhex("898f14030000e94d030000"), 6, bytes.fromhex("483b3d"), 0),
        (0xC528A7, bytes.fromhex("41898914030000c3"), 7, bytes.fromhex("4c3b0d"), 0),
        (0x14B038D, bytes.fromhex("41898614030000f7d8"), 7, bytes.fromhex("4c3b35"), 0),
        (0xB80109, bytes.fromhex("4189801c030000c3"), 7, bytes.fromhex("4c3b05"), 1),
        (0xB80135, bytes.fromhex("4189801c030000c3"), 7, bytes.fromhex("4c3b05"), 1),
        (0xB801B3, bytes.fromhex("4189881c030000c3"), 7, bytes.fromhex("4c3b05"), 1),
        (0x14B0160, bytes.fromhex("4189861c030000f7d8"), 7, bytes.fromhex("4c3b35"), 1),
    )

    def _ally_lock_block(self, install: bool) -> int:
        """Bloc des gardes d'ecriture (pose une fois par processus si
        `install`, retrouve apres un redemarrage du trainer), 0 sinon."""
        cache = getattr(self, "_ally_lock_cache", (0, None))
        if cache[1] == self.pid and cache[0]:
            return cache[0]
        block, missing = 0, []
        for index, (rva, original, length, _compare, _list) in enumerate(self.ALLY_WRITE_SITES):
            site = self.base + rva
            current = self.proc.read_bytes(site, len(original))
            if current[0] == 0xE9 and current[length:] == original[length:]:
                found = site + 5 + struct.unpack("<i", current[1:5])[0] - (0x100 + 0x80 * index)
                try:
                    if self.proc.read_bytes(found + 0x80, 8) != self.ALLY_LOCK_MAGIC:
                        return 0
                except OSError:
                    return 0
                if block and found != block:
                    return 0
                block = found
            elif current == original:
                missing.append(index)
            else:
                return 0
        if missing and (block or install):
            if not block:
                block = self.proc.alloc_near(self.base + self.ALLY_WRITE_SITES[0][0])
                if not block:
                    return 0
                self.proc.write_bytes(block, bytes(0x80) + self.ALLY_LOCK_MAGIC)

            def rel(source_end: int, destination: int) -> bytes:
                return struct.pack("<i", destination - source_end)
            for index in missing:
                rva, original, length, compare, which = self.ALLY_WRITE_SITES[index]
                site, code_start = self.base + rva, block + 0x100 + 0x80 * index
                back = site + length
                code = bytearray()
                for slot in range(self.ALLY_LOCK_SLOTS):
                    code += compare + rel(code_start + len(code) + 7, block + 0x40 * which + 8 * slot)  # cmp reg,[liste]
                    code += bytes.fromhex("0f84") + rel(code_start + len(code) + 6,
                                                      code_start + self.ALLY_LOCK_SLOTS * 13 + length + 5)  # je saute
                code += original[:length] + b"\xe9" + rel(code_start + len(code) + length + 5, back)  # ecriture ; retour
                code += b"\xe9" + rel(code_start + len(code) + 5, back)                            # saute : retour
                self.proc.write_bytes(code_start, bytes(code))
                self.proc.write_bytes(site, b"\xe9" + rel(site + 5, code_start) + b"\x90" * (length - 5))
        if not block:
            return 0
        self._ally_lock_cache = (block, self.pid)
        return block

    def set_ally_write_locks(self, life: set[str], stamina: set[str]) -> bool:
        """Le jeu n'ecrit plus la vie des allies `life` ni l'endurance des
        allies `stamina` ; a reappeler a chaque rafraichissement (objets
        recrees a chaque chargement de zone)."""
        if not (self.connected and self.sane):
            return False
        lists = []
        for names in (life, stamina):
            objects = [obj for obj in (self._ally_life_object(name) for name in sorted(names)) if obj]
            lists.append(objects[:self.ALLY_LOCK_SLOTS])
        block = self._ally_lock_block(install=any(lists))
        if not block:
            return not any(lists)
        for which, objects in enumerate(lists):
            wanted = struct.pack(f"<{self.ALLY_LOCK_SLOTS}Q", *objects, *[0] * (self.ALLY_LOCK_SLOTS - len(objects)))
            if self.proc.read_bytes(block + 0x40 * which, len(wanted)) != wanted:
                self.proc.write_bytes(block + 0x40 * which, wanted)
        return True

    def set_allies_invulnerable(self, allies: set[str]) -> bool:
        """Le jeu ignore les coups portes aux allies `allies` (aucune
        ecriture de leurs jauges) ; a reappeler a chaque rafraichissement
        (ils sont recrees a chaque chargement de zone)."""
        if not (self.connected and self.sane):
            return False
        ok = True
        for guard_name, (*_spec, classes) in self.ALLY_GUARDS.items():
            actors = []
            for name in sorted(allies):
                life = self._ally_life_object(name)
                if not life:
                    continue
                actor = struct.unpack("<Q", self.proc.read_bytes(life + 8, 8))[0]
                if struct.unpack("<Q", self.proc.read_bytes(actor, 8))[0] - self.base in classes:
                    actors.append(actor)
            actors = actors[:self.ALLY_GUARD_SLOTS]
            guard = self._ally_guard(guard_name, install=bool(actors))
            if not guard:
                ok = ok and not actors
                continue
            wanted = struct.pack(f"<{self.ALLY_GUARD_SLOTS}Q", *actors, *[0] * (self.ALLY_GUARD_SLOTS - len(actors)))
            if self.proc.read_bytes(guard, len(wanted)) != wanted:
                self.proc.write_bytes(guard, wanted)
        return ok

    # Classes de l'acte 1 (Johnny 18E4FA8, Meryl 18E65C8 ; 2026-10-16) :
    # vie ou endurance a 0 seule n'a pas d'effet avant un coup. Comme les
    # soldats ("Toute la zone"), c'est leur machine a etats qui juge : etat 6
    # "touche" (entree EB13F0 = entree des soldats C7EF70, qui evalue vie /
    # endurance / sommeil par C7D1F0 et enchaine mort, K.O. ou sommeil, puis
    # E98D00 s'il est encore en vie), machine a acteur+0xE8D0 (soldats
    # +0xE7D0 ; +0x50 = acteur, etats +0x20). Les tests "encore actif ?"
    # EAE7C0 / EC25A0 (lus a chaque image) ne declenchent rien. Le chemin
    # "endurance vide" de la fonction des coups (B84AB0 = endurance remise
    # au max, puis [vtable+0x370] = B4D960, vide) ne sert pas.
    # ALLY_HIT_STATES : classe -> (machine, etat, entree attendue).
    ALLY_HIT_STATES = {klass: (0xE8D0, 6, 0xEB13F0) for klass in (0x18E4FA8, 0x18E65C8, 0x18E5870, 0x18E5EF8)}

    def _ally_hit_state(self, actor: int, klass: int) -> tuple[int, int]:
        """(machine, etat "touche") si tout a la forme attendue, (0, 0) sinon."""
        offset, index, enter_rva = self.ALLY_HIT_STATES[klass]
        machine = struct.unpack("<Q", self.proc.read_bytes(actor + offset, 8))[0]
        if not machine or struct.unpack("<Q", self.proc.read_bytes(machine + 0x50, 8))[0] != actor:
            return 0, 0
        states = struct.unpack("<Q", self.proc.read_bytes(machine + 0x20, 8))[0]
        state = struct.unpack("<Q", self.proc.read_bytes(states + index * 8, 8))[0]
        if not state:
            return 0, 0
        enter = struct.unpack("<Q", self.proc.read_bytes(struct.unpack("<Q", self.proc.read_bytes(state, 8))[0] + 8, 8))[0]
        return (machine, index) if enter - self.base == enter_rva else (0, 0)

    def _ally_react(self, life: int, offset: int) -> None:
        """Jauge `offset` d'un allie mise a 0 ou moins par le trainer : le
        jeu en tire les consequences comme apres un coup (fil a part : les
        appels au jeu passent une image a la fois)."""
        if getattr(self, "_ally_reacting", False) or not self.speed.main_loop_hook_installed():
            return
        actor = struct.unpack("<Q", self.proc.read_bytes(life + 8, 8))[0]
        klass = struct.unpack("<Q", self.proc.read_bytes(actor, 8))[0] - self.base
        if klass in self.ALLY_HIT_STATES:
            machine, state = self._ally_hit_state(actor, klass)
            funcs = self._live_funcs({"state_goto": self.ZONE_FUNCS["state_goto"]}) if machine else None
            if funcs is None:
                return
            calls = [(funcs["state_goto"], machine, state)]
        elif klass in self.ALLY_DEATH_CLASSES and offset == 0x314:
            dead_offset, dead = self.ALLY_DEAD_STATE
            if struct.unpack("<i", self.proc.read_bytes(actor + dead_offset, 4))[0] == dead:
                return
            funcs = self._live_funcs(self.ALLY_DEATH_FUNCS)
            if funcs is None:
                return
            important_offset, important = self.ALLY_IMPORTANT
            if struct.unpack("<i", self.proc.read_bytes(actor + important_offset, 4))[0] != important:
                self.proc.write_bytes(life + 0x31C, struct.pack("<i", 0))
            calls = [(funcs[name], actor) for name in ("notify", "die", "cry")]
        else:
            return
        self._ally_reacting = True

        def run():
            try:
                for function, *args in calls:
                    if self.speed.game_call(function, *args) is None:
                        break
            finally:
                self._ally_reacting = False
        threading.Thread(target=run, daemon=True).start()

    # Etat d'un allie (2026-10-18, Rat Patrol acte 1, releve en jeu) : objet de
    # vie +0x78 = etat au sol : 0 ou 1 actif (1 apres un reveil), 2 endormi
    # (fleche), 9 endormi (jauge de sommeil +0x324 videe), 5 puis 4 puis 3 assomme a mesure que la jauge remonte (5 = chute
    # et inconscience profonde, 4 apres
    # ~20 s ; corps a corps ; jauge +0x31C tres negative qui
    # remonte) ; autres valeurs inconnues (le code teste les plages 2-6 et
    # 7-10). Machine a etats en 6 = vient d'etre touche (a chaque coup).
    # Dernier coup recu : +0x174 type, +0x180 drapeaux, +0x198 zone ; un K.O.
    # au corps a corps de Johnny : 0x1206B / 0xA06B / 0x11. Le jeu choisit
    # endormi ou assomme d'apres ce dernier coup quand la jauge +0x31C est
    # vide (sans coup : endormi).
    # Actions : reveiller = +0x31C et sommeil +0x324 au maximum (le jeu le
    # releve seul en quelques secondes, valide) ; endormir = dernier coup
    # +0x31C au maximum puis sommeil +0x324 vide, etat "touche" (valide : +0x78
    # = 9, chute lente, des "Z", un equipier peut le reveiller ; vider +0x31C
    # donnait un K.O.) ; assommer = dernier coup de
    # corps a corps, +0x31C tres negatif, etat "touche" (valide : tombe
    # assomme, un equipier peut le reveiller) ; tuer = vie a 0 (voir
    # _ally_react).
    ALLY_DOWN_OFFSET = 0x78
    ALLY_DOWN_STATES = {0: "active", 1: "active", 2: "asleep", 3: "ko", 4: "ko", 5: "ko", 9: "asleep"}
    ALLY_LAST_HIT = (0x174, 0x180, 0x198)
    ALLY_KO_HIT = (0x1206B, 0xA06B, 0x11)
    # Jauge +0x31C ecrite pour endormir / assommer : tres negative comme le
    # jeu (Johnny assomme : -53605), sinon l'allie se releve presque aussitot.
    ALLY_DOWN_GAUGE = -60000
    # Sommeil (+0x324) ecrit pour endormir (Johnny endormi : -36000 ; le jeu
    # le porte lui-meme a -90000, +0x78 = 9, chute lente comme une flechette).
    ALLY_SLEEP_GAUGE = -36000
    ALLY_ACTIONS = ("wake", "sleep", "knockout", "kill")

    def ally_status(self, name: str) -> str:
        """"absent", "dead", "asleep", "ko", "hit", "active" ou "state:<n>"."""
        if not (self.connected and self.sane):
            return "absent"
        life = self._ally_life_object(name)
        if life is None:
            return "absent"
        hp = struct.unpack("<i", self.proc.read_bytes(life + 0x314, 4))[0]
        if hp <= 0:
            return "dead"
        down = struct.unpack("<I", self.proc.read_bytes(life + self.ALLY_DOWN_OFFSET, 4))[0]
        status = self.ALLY_DOWN_STATES.get(down, f"state:{down}")
        if status == "active":
            actor = struct.unpack("<Q", self.proc.read_bytes(life + 8, 8))[0]
            klass = struct.unpack("<Q", self.proc.read_bytes(actor, 8))[0] - self.base
            if klass in self.ALLY_HIT_STATES:
                machine, state = self._ally_hit_state(actor, klass)
                if machine and struct.unpack("<i", self.proc.read_bytes(machine + 8, 4))[0] == state:
                    return "hit"
        return status

    def ally_set_state(self, name: str, action: str) -> bool:
        """Change l'etat de l'allie `name` (ALLY_ACTIONS)."""
        if not (self.connected and self.sane):
            return False
        life = self._ally_life_object(name)
        if life is None:
            return False
        if action == "wake":
            for offset in (0x31C, 0x324):
                self.proc.write_bytes(life + offset, self.proc.read_bytes(life + offset + 4, 4))
            return True
        if action == "kill":
            self.proc.write_bytes(life + 0x314, struct.pack("<i", 0))
            self._ally_react(life, 0x314)
            return True
        if action == "sleep":
            # Endormi = jauge de sommeil (+0x324) videe ; la jauge +0x31C remise
            # au maximum d'abord, sinon il garde les etoiles d'un K.O.
            self.proc.write_bytes(life + 0x31C, self.proc.read_bytes(life + 0x320, 4))
            self.proc.write_bytes(life + 0x324, struct.pack("<i", self.ALLY_SLEEP_GAUGE))
            self._ally_react(life, 0x324)
            return True
        for offset, value in zip(self.ALLY_LAST_HIT, self.ALLY_KO_HIT):
            self.proc.write_bytes(life + offset, struct.pack("<I", value))
        self.proc.write_bytes(life + 0x31C, struct.pack("<i", self.ALLY_DOWN_GAUGE))
        self._ally_react(life, 0x31C)
        return True

    def _ally_life_valid(self, name: str, life: int) -> bool:
        try:
            vtable, actor = struct.unpack("<QQ", self.proc.read_bytes(life, 16))
            if vtable != self.base + self.ZONE_LIFE_OBJECT_VTABLE_RVA or not actor:
                return False
            klass = struct.unpack("<Q", self.proc.read_bytes(actor, 8))[0] - self.base
            kind = struct.unpack("<I", self.proc.read_bytes(actor + self.ALLY_ID_OFFSET, 4))[0]
            back = struct.unpack("<Q", self.proc.read_bytes(actor + 0x1E8, 8))[0]
        except OSError:
            return False
        return (klass, kind) in self.ALLIES[name] and back == life

    def _ally_scan(self):
        found: dict[str, int] = {}
        try:
            index = struct.unpack("<i", self.proc.read_bytes(self.base + self.PLAYER_INDEX_RVA, 4))[0]
            entry = self.base + self.PLAYER_TABLE_RVA + (index + 1) * self.PLAYER_ENTRY_SIZE
            snake = struct.unpack("<Q", self.proc.read_bytes(entry, 8))[0] & 0xFFFFFFFFFFFF
            if snake:
                pattern = struct.pack("<Q", self.base + self.ZONE_LIFE_OBJECT_VTABLE_RVA)
                for address, data in self.proc.allocation_blocks(snake):
                    i = data.find(pattern)
                    while i != -1 and len(found) < len(self.ALLIES):
                        if i % 8 == 0:
                            for name in self.ALLIES:
                                if name not in found and self._ally_life_valid(name, address + i):
                                    found[name] = address + i
                        i = data.find(pattern, i + 1)
                    if len(found) == len(self.ALLIES):
                        break
        except (OSError, AttributeError, TypeError):
            pass  # jeu ferme ou detache pendant la recherche
        self._ally_lives = found
        self._ally_scan_at = time.monotonic()
        self._ally_scanning = False

    def _ally_life_object(self, name: str) -> int | None:
        """Objet de vie de l'allie `name` s'il est dans la zone, sinon None
        (une recherche est alors lancee en arriere-plan, au plus toutes les
        ALLY_SCAN_INTERVAL secondes)."""
        life = getattr(self, "_ally_lives", {}).get(name)
        if life is not None and self._ally_life_valid(name, life):
            return life
        if (not getattr(self, "_ally_scanning", False)
                and time.monotonic() - getattr(self, "_ally_scan_at", -1e9) >= self.ALLY_SCAN_INTERVAL):
            self._ally_scanning = True
            threading.Thread(target=self._ally_scan, daemon=True).start()
        return None

    def player_gauge_max(self, gauge: str) -> int | None:
        """Maximum reel d'une jauge quand le jeu le stocke (Drebin 893, allies)."""
        if gauge in self.ALLY_GAUGES and self.connected and self.sane:
            ally, offset = self.ALLY_GAUGES[gauge]
            life = self._ally_life_object(ally)
            if life is None:
                return None
            return struct.unpack("<i", self.proc.read_bytes(life + offset + 4, 4))[0] or None
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
        if gauge in self.ALLY_GAUGES:
            ally, offset = self.ALLY_GAUGES[gauge]
            life = self._ally_life_object(ally)
            if life is None:
                return -1
            return struct.unpack("<i", self.proc.read_bytes(life + offset, 4))[0]
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
        if gauge in self.ALLY_GAUGES:
            ally, offset = self.ALLY_GAUGES[gauge]
            life = self._ally_life_object(ally)
            if life is None:
                return False
            self.proc.write_bytes(life + offset, struct.pack("<i", value))
            if value <= 0:
                self._ally_react(life, offset)
            return True
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
