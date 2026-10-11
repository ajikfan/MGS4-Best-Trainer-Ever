"""MGS4Live : son du jeu (FMOD) et alerte forcee."""
import struct
import threading

from mgs4trainer.core.gamedata import ALERT_STATE_RVA
from mgs4trainer.core.winproc import MEM_COMMIT, PAGE_READWRITE, kernel32
from mgs4trainer.ui.profiles import _beep


class SoundAlertMixin:
    """Son du jeu (FMOD) et alerte forcee."""

    # Son du « ! » (repere par un soldat) joue par le jeu lui-meme
    # (2026-10-09) : FMOD Studio est integre a l'exe. La classe son du jeu
    # (176C10) fait System::getEvent(systeme, chemin, &description) ->
    # EventDescription::createInstance -> EventInstance::start -> release ;
    # systeme FMOD Studio = [mgs4+22A8F90]. Son joue : le « GO » de Snake
    # quand le Pistolet solaire est charge (voix : dossier selon la langue
    # des voix), sinon le « ! » de repere (banque commune, 3 canaux joues
    # ensemble). Noms releves via bplog sur 176C10 : "{ansi@[rcx+28]}".
    # Chemin et sorties dans un petit tampon alloue dans le jeu
    # (VirtualAllocEx, un par processus).
    FMOD_SYSTEM_PTR_RVA = 0x22A8F90
    FMOD_FUNCS = {
        "get_event": (0x2C0740, "4053555641564881ec48010000"),
        "create_instance": (0x2B7050, "48895c24185556574881ec6001"),
        "start": (0x2CEFA0, "48895c24104889742418574881ec"),
        "release": (0x2CAD90, "48895c24104889742418574881ec"),
    }
    PROFILE_SOUND_CANDIDATES = (
        ("event:/SPC/ENG/sna_on_unq_vram/E_8906_v_087_snav",),
        ("event:/SPC/JPN/sna_on_unq_vram/E_8906_v_087_snav",),
        tuple(f"event:/SSP/ENG/mgs4int/E_0_s_bikkuri_new_1_{channel}" for channel in ("Lf", "Lm", "Rm")),
    )

    def _sound_buffer(self) -> int:
        if getattr(self, "_sound_buffer_pid", None) != self.pid:
            buf = kernel32.VirtualAllocEx(self.proc.handle, None, 0x1000, MEM_COMMIT | 0x2000, PAGE_READWRITE)
            self._sound_buffer_addr = buf or 0
            self._sound_buffer_pid = self.pid if buf else None
        return self._sound_buffer_addr

    def play_alert_sound(self) -> bool:
        """Joue le « ! » du jeu (fil separe : un appel par image). Faux si
        impossible (pas accroche, appel generique absent, autre version)."""
        if not (self.connected and self.sane and self.speed.main_loop_hook_installed()):
            return False
        try:
            funcs = self._live_funcs(self.FMOD_FUNCS)
            system = struct.unpack("<Q", self.proc.read_bytes(self.base + self.FMOD_SYSTEM_PTR_RVA, 8))[0]
            buf = self._sound_buffer()
        except OSError:
            return False
        if funcs is None or not system or not buf:
            return False
        threading.Thread(target=self._play_alert_sound, args=(funcs, system, buf), daemon=True).start()
        return True

    def _play_alert_sound(self, funcs: dict[str, int], system: int, buf: int) -> None:
        call = self.speed.game_call
        try:
            for events in self.PROFILE_SOUND_CANDIDATES:
                instances = []
                for index, path in enumerate(events):
                    path_addr = buf + 0x100 + index * 0x100
                    out = buf + index * 0x10
                    self.proc.write_bytes(path_addr, path.encode() + b"\0")
                    self.proc.write_bytes(out, bytes(16))
                    # FMOD_RESULT (int) : 0 = FMOD_OK ; None = appel non execute.
                    result = call(funcs["get_event"], system, path_addr, out)
                    if result is None:
                        raise OSError("jeu fige")
                    if result & 0xFFFFFFFF:
                        continue  # evenement absent (banque non chargee, autre langue)
                    description = struct.unpack("<Q", self.proc.read_bytes(out, 8))[0]
                    result = call(funcs["create_instance"], description, out + 8)
                    if result is None or result & 0xFFFFFFFF:
                        continue
                    instances.append(struct.unpack("<Q", self.proc.read_bytes(out + 8, 8))[0])
                if instances:
                    for instance in instances:
                        call(funcs["start"], instance)
                    for instance in instances:
                        call(funcs["release"], instance)  # libere a la fin du son
                    return
            raise OSError("aucun son trouve")
        except OSError:
            _beep()

    # Vraie alerte (2026-10-09, validee en jeu) : forcer l'etat seul (court-
    # circuit de B5FA90) laissait le compte a rebours a 0.00 et rien a
    # reprendre pour le jeu. Le compte a rebours = gestionnaire d'alerte
    # ([mgs4+23F0B5B0]) +0x78 (frames, x900 -> mgs4+1D77ABC, 6000 = 99.99),
    # recopie a chaque image du max des minuteries des soldats (soldat
    # +0x461C, +0x4618 = 10800000), que leur IA decompte. On fait donc
    # donner l'alerte par un soldat : B43750(soldat, index cible) = le soldat
    # qui repere Snake (position transmise a son unite [soldat+0x4578],
    # signalement, minuteries). Soldats : gestionnaire +0x30 nombre, +0x38
    # tableau (pas 0x10, pointeur a +8).
    ALERT_MANAGER_PTR_RVA = 0x23F0B5B0
    SOLDIER_REPORT_FUNC = {"report": (0xB43750, "48895c2408574883ec40488bb9784500")}
    ALERT_FULL_FRAMES = 6000
    ALERT_SECOND_TIMER = 10800000

    def _alert_manager(self) -> int:
        return struct.unpack("<Q", self.proc.read_bytes(self.base + self.ALERT_MANAGER_PTR_RVA, 8))[0]

    def _alert_soldier(self, manager: int) -> int:
        """Un soldat actif de la zone (unite presente), 0 si aucun."""
        count = struct.unpack("<i", self.proc.read_bytes(manager + 0x30, 4))[0]
        table = struct.unpack("<Q", self.proc.read_bytes(manager + 0x38, 8))[0]
        if not table or not 0 < count < 512:
            return 0
        block = self.proc.read_bytes(table, count * 0x10)
        for index in range(count):
            soldier = struct.unpack_from("<Q", block, index * 0x10 + 8)[0]
            if not soldier:
                continue
            # Present dans la zone : unite, +0x4624 = 1 et +0x45AC = 0 (8 =
            # soldat d'une autre partie de la zone, que le jeu ne met pas a
            # jour - son alerte ne prend pas).
            unit = struct.unpack("<Q", self.proc.read_bytes(soldier + 0x4578, 8))[0]
            active = struct.unpack("<i", self.proc.read_bytes(soldier + 0x4624, 4))[0]
            absent = struct.unpack("<i", self.proc.read_bytes(soldier + 0x45AC, 4))[0]
            if unit and active == 1 and absent == 0:
                return soldier
        return 0

    def trigger_real_alert(self) -> bool:
        """Fait donner l'alerte par un soldat (fil separe). Faux si aucun
        soldat ou appel impossible ; le maintien de l'affichage marche quand meme."""
        if not (self.connected and self.sane and self.speed.main_loop_hook_installed()):
            return False
        try:
            funcs = self._live_funcs(self.SOLDIER_REPORT_FUNC)
            manager = self._alert_manager()
            soldier = self._alert_soldier(manager) if manager else 0
            target = struct.unpack("<i", self.proc.read_bytes(self.base + self.PLAYER_INDEX_RVA, 4))[0]
        except OSError:
            return False
        self._alert_holder = soldier
        if funcs is None or not soldier:
            return False
        threading.Thread(target=self.speed.game_call, args=(funcs["report"], soldier, target), daemon=True).start()
        return True

    def hold_alert_timer(self) -> None:
        """Alerte forcee : compte a rebours maintenu a 99.99 (gestionnaire +
        soldat qui a donne l'alerte), le jeu reprend la main quand on arrete."""
        manager = self._alert_manager()
        if not manager:
            return
        self.proc.write_bytes(manager + 0x74, struct.pack("<ii", self.ALERT_SECOND_TIMER, self.ALERT_FULL_FRAMES))
        soldier = getattr(self, "_alert_holder", 0)
        if soldier:
            self.proc.write_bytes(soldier + 0x4618, struct.pack("<ii", self.ALERT_SECOND_TIMER, self.ALERT_FULL_FRAMES))

    def read_alert_state(self) -> int:
        """Lecture seule - l'ecriture ne tient pas (voir ALERT_STATE_RVA)."""
        return int.from_bytes(self.proc.read_bytes(self.base + ALERT_STATE_RVA, 4), "little")
