"""Apparition d'un soldat PMC devant Snake (prototype, 2026-10-31).

Le jeu cree ses acteurs par des commandes de script. On rejoue ces commandes
avec nos propres arguments, apres avoir enregistre les ressources du soldat
(modeles, animations...) dans le dictionnaire de ressources. Le nom de zone
est echange le temps de cet enregistrement : le jeu en deduit le dossier des
textures HD (textures/PC_TXN_UP/stageNN/<zone>/...) et les lit lui-meme.

Prototype : les ressources viennent de spawn_data/pmc (capture de l'acte 1,
hors du depot car ce sont des donnees du jeu)."""
import json
import os
import struct
import threading

from mgs4trainer.core.paths import _writable_data_path
from mgs4trainer.core.speedhack import kernel32

MEM_COMMIT_RESERVE = 0x3000
PAGE_READWRITE = 0x04
PAGE_EXECUTE_READWRITE = 0x40


def _mov_rax(value: int) -> bytes:
    return b"\x48\xB8" + struct.pack("<Q", value)


def _mov_rcx(value: int) -> bytes:
    return b"\x48\xB9" + struct.pack("<Q", value)


class SpawnMixin:
    SPAWN_FUNCS = {
        "register": (0x74C9B0, "4883ec48"),
        "chara": (0x5C4D0, "40564883ec20"),
        "chara_named": (0x5C440, "48895c241857"),
        "args_end_push": (0x3EEF20, "488b05"),
        "args_set": (0x3EEF10, "48890d"),
        "args_end_pop": (0x3EEFC0, "48832d"),
        "warp": (0xB39C90, "48895c2408"),
        "start": (0xB4BBC0, "4057"),
    }
    SPAWN_LINKVARBUF_RVA = 0x1C28B28
    SPAWN_ZONE_OFFSETS = (0x34, 0x44)  # nom de zone (voir 5C900)
    SPAWN_RESOURCES_RVA = 0x23D2F6D0  # 16 arbres : +0 gauche, +8 droite, +0x10 cle
    SPAWN_ARGS_RVA = 0x23FFAC20  # pointeur d'arguments de l'interpreteur de script
    SPAWN_CURRENT_UNIT_RVA = 0x23F0B5B8
    SPAWN_MANAGER_RVA = 0x23F0B5B0  # ENE_MANAGER : +0x20 nombre de groupes
    SPAWN_TASK_LIST_RVA = 0x23D044D0
    SPAWN_UNIT_VTABLE_RVA = 0x18BA610
    SPAWN_PMC_VTABLE_RVA = 0x18C31B8
    SPAWN_START_VTABLE_OFFSET = 0x1C8
    SPAWN_START_FLAGS = 0x45B0
    SPAWN_START_BIT = 0x200000
    # Fiches de route (3 de 5 entiers) et groupes de routes, repris d'un acteur
    # de la zone : une route absente de la zone plante le jeu (B66A10).
    SPAWN_ROUTE_RECORD = 0x4640
    SPAWN_ROUTE_RECORD_SIZE = 0x3C
    SPAWN_ROUTE_GROUPS = 0x46EC
    SPAWN_ROUTE_GROUPS_SIZE = 8
    SPAWN_ZONE = b"s01a57l\x00"  # dossier de textures du soldat
    SPAWN_DISTANCE = 2000.0  # 2 m vers +X
    SPAWN_GROUND_OFFSET = -100.0

    # Arguments de script, parametres de procedure deja remplaces par leur
    # valeur (relevee en acte 1). Le 2e argument (nom de l'acteur) est en
    # +5, sur 4 octets. Retirees : les options qui lancent une procedure du
    # script de l'acte 1 (0x89F065 sur l'escouade, 0x39D643 sur le soldat :
    # plantage a la mort) et le nom de l'escouade (0x84E412, chaine du script).
    SPAWN_UNIT_ARGS = bytes.fromhex(
        "0679690709000000005873e5303b065a1e975d0d62efca9e065e2cea09901e22"
        "00597465f23b0904000000000000")
    SPAWN_SOLDIER_ARGS = bytes.fromhex(
        "063e2d3e0900000000586585a301190002c0586892a035190002c45868a3a54a"
        "190002c8586ec5ca38190002cc5c6c25b1371900030c19000310587317a16719"
        "0003145d18690d5d3608540102640855010264085601026408570102645976cc"
        "309909000000005977424f820930910000556596618ac45565b5362fe1556d91"
        "2c3ec15565498b83915d0e72ec625909e2cfcc0009000000005d0e63d7cb8b09"
        "2ecdec0009000000005d0e67aa12ac09567d48000970170000586813ee2d1200"
        "02bd586edf26ed1200033a0000")
    SPAWN_POSITIONAL_SIZE = 9  # fin des arguments positionnels, debut des options
    SPAWN_NAME_OFFSET = 5
    SPAWN_FIRST_NAME = 0x7A7A0000
    SPAWN_DATA_DIR = _writable_data_path("spawn_data", "pmc")

    def spawn_available(self) -> bool:
        return os.path.isfile(os.path.join(self.SPAWN_DATA_DIR, "meta.json"))

    def spawn_soldier(self) -> bool:
        """Lance l'apparition dans un fil separe (les appels au jeu se font
        une image a la fois). Une seule a la fois."""
        if getattr(self, "_spawn_busy", False) or not self.spawn_available():
            return False
        if not (self.connected and self.sane and self.pid and self.speed.ensure_injected(self.pid)):
            return False
        if not self.speed.main_loop_hook_installed():
            return False
        self._spawn_busy = True
        threading.Thread(target=self._spawn_run, daemon=True).start()
        return True

    def _spawn_run(self) -> None:
        try:
            self._spawn_soldier()
        except (OSError, struct.error, ValueError):
            pass
        finally:
            self._spawn_busy = False

    def _spawn_q(self, address: int) -> int:
        return struct.unpack("<Q", self.proc.read_bytes(address, 8))[0]

    def _spawn_soldier(self) -> bool:
        funcs = self._live_funcs(self.SPAWN_FUNCS)
        position = self.player_position()
        manager = self._spawn_q(self.base + self.SPAWN_MANAGER_RVA)
        if funcs is None or position is None or not manager:
            return False
        # Sans groupe, l'inscription de l'escouade (B54070) lit un pointeur nul.
        if struct.unpack("<i", self.proc.read_bytes(manager + 0x20, 4))[0] <= 0:
            return False
        if self._spawn_q(self.base + self.SPAWN_CURRENT_UNIT_RVA):
            return False  # un script de creation est en cours
        if not self._spawn_register(funcs):
            return False
        self._spawn_names = getattr(self, "_spawn_names", self.SPAWN_FIRST_NAME) + 2
        units = self._spawn_tasks(self.SPAWN_UNIT_VTABLE_RVA)
        unit_args = self._spawn_named(self.SPAWN_UNIT_ARGS, self._spawn_names)
        if self._spawn_command(unit_args, funcs["chara_named"]) is None:
            return False
        created = self._spawn_tasks(self.SPAWN_UNIT_VTABLE_RVA) - units
        if len(created) != 1:
            return False
        soldiers = self._spawn_tasks(self.SPAWN_PMC_VTABLE_RVA)
        soldier_args = self._spawn_named(self.SPAWN_SOLDIER_ARGS, self._spawn_names + 1)
        if self._spawn_command(soldier_args, funcs["chara"], created.pop()) is None:
            return False
        created = self._spawn_tasks(self.SPAWN_PMC_VTABLE_RVA) - soldiers
        if len(created) != 1:
            return False
        soldier = created.pop()
        # Tout de suite : ne au point (0, 0, 0), il tomberait sous la carte.
        target = self._spawn_alloc(0x100, PAGE_READWRITE)
        x, y, z = position
        self.proc.write_bytes(target, struct.pack(
            "<4f", x + self.SPAWN_DISTANCE, y + self.SPAWN_GROUND_OFFSET, z, 1.0))
        if self.speed.game_call(funcs["warp"], soldier, target, 0, timeout=10.0) is None:
            return False
        vtable = self._spawn_q(soldier)
        if self._spawn_q(vtable + self.SPAWN_START_VTABLE_OFFSET) != funcs["start"]:
            return False
        self._spawn_copy_route(soldier)
        flags =struct.unpack("<I", self.proc.read_bytes(soldier + self.SPAWN_START_FLAGS, 4))[0]
        self.proc.write_bytes(soldier + self.SPAWN_START_FLAGS, struct.pack("<I", flags | self.SPAWN_START_BIT))
        return self.speed.game_call(funcs["start"], soldier, timeout=10.0) is not None

    def _spawn_copy_route(self, soldier: int) -> None:
        """Reprend la route d'un acteur de la zone, s'il y en a un : sans
        acteur a copier, le soldat garde ses fiches vides."""
        for actor, _life, _gauges in self._zone_soldiers():
            record = self.proc.read_bytes(actor + self.SPAWN_ROUTE_RECORD, self.SPAWN_ROUTE_RECORD_SIZE)
            if actor != soldier and struct.unpack_from("<i", record, 8)[0] > 0:
                groups = self.proc.read_bytes(actor + self.SPAWN_ROUTE_GROUPS, self.SPAWN_ROUTE_GROUPS_SIZE)
                self.proc.write_bytes(soldier + self.SPAWN_ROUTE_RECORD, record)
                self.proc.write_bytes(soldier + self.SPAWN_ROUTE_GROUPS, groups)
                return

    def _spawn_named(self, args: bytes, name: int) -> bytes:
        end = self.SPAWN_NAME_OFFSET + 4
        return args[:self.SPAWN_NAME_OFFSET] + struct.pack("<I", name) + args[end:]

    def _spawn_alloc(self, size: int, protection: int) -> int:
        address = kernel32.VirtualAllocEx(self.proc.handle, None, size, MEM_COMMIT_RESERVE, protection)
        if not address:
            raise OSError("allocation impossible")
        return address

    def _spawn_tasks(self, vtable_rva: int) -> set[int]:
        vtable = self.base + vtable_rva
        head = self.base + self.SPAWN_TASK_LIST_RVA
        node = self._spawn_q(head + 0x20)
        seen = set()
        found = set()
        while node and node != head and node not in seen:
            seen.add(node)
            for actor in (self._spawn_q(node + 0x90), node + 0xC0):
                try:
                    if actor and self._spawn_q(actor) == vtable:
                        found.add(actor)
                except OSError:
                    pass
            node = self._spawn_q(node + 0x20)
        return found

    def _spawn_present_keys(self) -> set[int]:
        keys = set()
        tree = self.base + self.SPAWN_RESOURCES_RVA
        stack = [self._spawn_q(tree + i * 8) for i in range(16)]
        while stack:
            node = stack.pop()
            if node:
                keys.add(struct.unpack("<I", self.proc.read_bytes(node + 0x10, 4))[0])
                stack += [self._spawn_q(node), self._spawn_q(node + 8)]
        return keys

    def _spawn_register(self, funcs: dict[str, int]) -> bool:
        """Enregistre les ressources absentes. Le dictionnaire est vide a
        chaque changement de zone ; les tampons du trainer sont reutilises,
        et recopies car le jeu peut les modifier."""
        with open(os.path.join(self.SPAWN_DATA_DIR, "meta.json"), encoding="utf-8") as handle:
            resources = json.load(handle)
        present = self._spawn_present_keys()
        missing = [m for m in resources if m["key"] not in present]
        if not missing:
            return True
        if getattr(self, "_spawn_blob_pid", None) != self.pid:
            self._spawn_blob_pid, self._spawn_blobs = self.pid, {}
        entries = b""
        for resource in missing:
            key = resource["key"]
            with open(os.path.join(self.SPAWN_DATA_DIR, f"{key:08x}.bin"), "rb") as handle:
                data = handle.read()
            if key not in self._spawn_blobs:
                self._spawn_blobs[key] = self._spawn_alloc(len(data) + 0x100, PAGE_READWRITE)
            self.proc.write_bytes(self._spawn_blobs[key], data)
            entries += struct.pack("<QIII", self._spawn_blobs[key], key, resource["r8"], len(data)) + bytes(4)
        table = self._spawn_alloc(0x1000 + len(entries), PAGE_EXECUTE_READWRITE)
        self.proc.write_bytes(table + 0x1000, entries)
        stub = self._spawn_register_stub(table, table + 0x1000, len(missing), funcs["register"])
        self.proc.write_bytes(table + 0x100, stub)
        return self.speed.game_call(table + 0x100, timeout=30.0) is not None

    def _spawn_register_stub(self, saved: int, entries: int, count: int, register: int) -> bytes:
        """Echange le nom de zone, appelle register sur chaque entree
        {tampon, cle, indicateur, taille}, restaure le nom. saved : 16 octets."""
        lvb = self.base + self.SPAWN_LINKVARBUF_RVA
        first, second = self.SPAWN_ZONE_OFFSETS
        zone = struct.unpack("<Q", self.SPAWN_ZONE)[0]
        head = (
            b"\x53\x56\x57\x48\x83\xEC\x20"            # push rbx/rsi/rdi ; sub rsp, 0x20
            + b"\x48\xBB" + struct.pack("<Q", saved)   # mov rbx, saved
            + _mov_rax(lvb) + b"\x48\x8B\x00"          # mov rax, [rax]
            + bytes((0x48, 0x8B, 0x48, first))         # mov rcx, [rax + first]
            + b"\x48\x89\x0B"                          # mov [rbx], rcx
            + bytes((0x48, 0x8B, 0x48, second))        # mov rcx, [rax + second]
            + b"\x48\x89\x4B\x08"                      # mov [rbx + 8], rcx
            + _mov_rcx(zone)
            + bytes((0x48, 0x89, 0x48, first))         # mov [rax + first], rcx
            + bytes((0x48, 0x89, 0x48, second))        # mov [rax + second], rcx
            + b"\x48\xBE" + struct.pack("<Q", entries)  # mov rsi, entries
            + b"\xBF" + struct.pack("<I", count)       # mov edi, count
        )
        body = (
            b"\x48\x8B\x0E"                            # mov rcx, [rsi]
            + b"\x8B\x56\x08"                          # mov edx, [rsi + 8]
            + b"\x44\x8B\x46\x0C"                      # mov r8d, [rsi + 0xC]
            + b"\x44\x8B\x4E\x10"                      # mov r9d, [rsi + 0x10]
            + _mov_rax(register) + b"\xFF\xD0"         # call rax
            + b"\x48\x83\xC6\x18"                      # add rsi, 0x18
            + b"\xFF\xCF"                              # dec edi
        )
        # nxt: test edi, edi ; jz fin ; body ; jmp nxt
        loop = b"\x85\xFF\x74" + bytes((len(body) + 2,)) + body
        loop += b"\xEB" + struct.pack("<b", -(len(loop) + 2))
        tail = (
            _mov_rax(lvb) + b"\x48\x8B\x00"
            + b"\x48\x8B\x0B"                          # mov rcx, [rbx]
            + bytes((0x48, 0x89, 0x48, first))
            + b"\x48\x8B\x4B\x08"                      # mov rcx, [rbx + 8]
            + bytes((0x48, 0x89, 0x48, second))
            + b"\x48\x83\xC4\x20\x5F\x5E\x5B\xC3"      # add rsp, 0x20 ; pop ; ret
        )
        return head + loop + tail

    def _spawn_command(self, args: bytes, command: int, unit: int = 0) -> int | None:
        """Execute une commande de creation comme l'interpreteur de script :
        fin des arguments empilee, pointeur d'arguments, appel, depilage."""
        funcs = self._live_funcs(self.SPAWN_FUNCS)
        if funcs is None:
            return None
        memory = self._spawn_alloc(0x1000, PAGE_EXECUTE_READWRITE)
        buffer, code = memory + 0x100, memory + 0x600
        self.proc.write_bytes(buffer, args)
        stub = self._spawn_command_stub(buffer, command, unit, funcs)
        self.proc.write_bytes(code, stub)
        return self.speed.game_call(code, timeout=10.0)

    def _spawn_command_stub(self, buffer: int, command: int, unit: int, funcs: dict[str, int]) -> bytes:
        args_pointer = self.base + self.SPAWN_ARGS_RVA
        current_unit = self.base + self.SPAWN_CURRENT_UNIT_RVA
        code = (
            b"\x53\x56\x48\x83\xEC\x28"                # push rbx/rsi ; sub rsp, 0x28
            + _mov_rax(current_unit) + b"\x48\x8B\x30"  # mov rsi, [rax]
            + _mov_rax(args_pointer) + b"\x48\x8B\x18"  # mov rbx, [rax]
        )
        if unit:
            code += _mov_rax(current_unit) + _mov_rcx(unit) + b"\x48\x89\x08"  # mov [rax], rcx
        code += (
            _mov_rcx(buffer + self.SPAWN_POSITIONAL_SIZE)
            + _mov_rax(funcs["args_end_push"]) + b"\xFF\xD0"
            + _mov_rcx(buffer)
            + _mov_rax(funcs["args_set"]) + b"\xFF\xD0"
            + _mov_rax(command) + b"\xFF\xD0"
            + _mov_rax(funcs["args_end_pop"]) + b"\xFF\xD0"
            + _mov_rax(args_pointer) + b"\x48\x89\x18"  # mov [rax], rbx
            + _mov_rax(current_unit) + b"\x48\x89\x30"  # mov [rax], rsi
            + b"\x48\x83\xC4\x28\x5E\x5B\xC3"          # add rsp, 0x28 ; pop ; ret
        )
        return code
