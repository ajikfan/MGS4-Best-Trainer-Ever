"""MGS4Live : son du jeu (FMOD) et alerte forcee."""
import struct
import threading
import time

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

    # Alerte forcee (refonte 2026-10-12, mesuree en jeu) : plus de court-
    # circuit de la fonction de calcul (B5F120), on place le jeu dans
    # l'etape voulue de son propre deroule et on l'y maintient ; en
    # Automatique, on n'ecrit plus rien et le jeu reprend son decompte.
    # Chaque soldat de l'alerte a deux minuteries : +0x461C = compte a
    # rebours de l'Alerte (images, 6000 = 99.99), qui descend a 0 quand plus
    # personne ne voit Snake -> Evasion ; +0x4618 part alors de 10800000 et
    # descend : sous 5400000 -> Prudence, a 0 -> Normal. Le gestionnaire
    # d'alerte [mgs4+23F0B5B0] en recopie le max a chaque image (+0x74 et
    # +0x78) : ecrire seulement le gestionnaire ne tient pas une image.
    # Soldats : +0x30 nombre, +0x38 tableau (pas 0x10, pointeur a +8).
    # Pour entrer dans ce deroule depuis Normal, un soldat donne l'alerte :
    # B43750(soldat, index cible) = le soldat qui repere Snake.
    ALERT_MANAGER_PTR_RVA = 0x23F0B5B0
    SOLDIER_REPORT_FUNC = {"report": (0xB43750, "48895c2408574883ec40488bb9784500")}
    ALERT_FULL_FRAMES = 6000
    ALERT_SECOND_TIMER = 10800000
    # Prudence : juste sous le seuil Evasion -> Prudence (5400000).
    ALERT_CAUTION_TIMER = 5400000 - 900
    # Delai avant de redemander un signalement si le jeu est reste en
    # Normal (soldat qui n'a pas pu signaler, changement de zone).
    ALERT_RETRIGGER_S = 3.0

    def _alert_manager(self) -> int:
        return struct.unpack("<Q", self.proc.read_bytes(self.base + self.ALERT_MANAGER_PTR_RVA, 8))[0]

    def _alert_soldiers(self, manager: int) -> list[int]:
        count = struct.unpack("<i", self.proc.read_bytes(manager + 0x30, 4))[0]
        table = struct.unpack("<Q", self.proc.read_bytes(manager + 0x38, 8))[0]
        if not table or not 0 < count < 512:
            return []
        block = self.proc.read_bytes(table, count * 0x10)
        soldiers = [struct.unpack_from("<Q", block, i * 0x10 + 8)[0] for i in range(count)]
        return [s for s in soldiers if s]

    def _report_candidates(self, manager: int) -> list[int]:
        """Soldats avec une unite, les plus probables d'abord : drapeaux
        +0x45AC a 0, puis sans le bit 0x40 (0xC0/0xE0 = soldats d'une
        autre partie de la zone, constate en s01a57), puis les autres."""
        ranked = []
        for soldier in self._alert_soldiers(manager):
            if not struct.unpack("<Q", self.proc.read_bytes(soldier + 0x4578, 8))[0]:
                continue
            flags = struct.unpack("<i", self.proc.read_bytes(soldier + 0x45AC, 4))[0]
            ranked.append((0 if flags == 0 else 1 if not flags & 0x40 else 2, soldier))
        return [soldier for _, soldier in sorted(ranked, key=lambda r: r[0])]

    def trigger_real_alert(self) -> bool:
        """Fait donner l'alerte par un soldat (fil separe : essaie les
        candidats jusqu'a ce que le jeu passe en Alerte). Faux si aucun
        soldat ou appel impossible."""
        if not (self.connected and self.sane and self.speed.main_loop_hook_installed()):
            return False
        if getattr(self, "_alert_trigger_busy", False):
            return True
        try:
            funcs = self._live_funcs(self.SOLDIER_REPORT_FUNC)
            manager = self._alert_manager()
            candidates = self._report_candidates(manager) if manager else []
            target = struct.unpack("<i", self.proc.read_bytes(self.base + self.PLAYER_INDEX_RVA, 4))[0]
        except OSError:
            return False
        if funcs is None or not candidates:
            return False
        self._alert_trigger_busy = True
        threading.Thread(target=self._report_alert, args=(funcs["report"], candidates[:8], target),
                         daemon=True).start()
        return True

    def _report_alert(self, func: int, candidates: list[int], target: int) -> None:
        try:
            for soldier in candidates:
                if self.speed.game_call(func, soldier, target) is None:
                    return  # jeu en pause ou DLL absente : on reessaiera plus tard
                time.sleep(0.1)
                if self.read_alert_state() != 0:
                    return
        except OSError:
            pass
        finally:
            self._alert_trigger_busy = False

    def hold_alert_state(self, wanted: int) -> None:
        """Maintient l'etape `wanted` (0=Normal, 1=Alerte, 2=Evasion,
        3=Prudence, voir ALERT_STATE_NAMES) en reecrivant les compteurs du
        jeu - a appeler en boucle tant que le forcage est actif."""
        manager = self._alert_manager()
        if not manager:
            return
        state = self.read_alert_state()
        if (wanted != 0 and state == 0) or (wanted == 1 and state != 1):
            # Hors du deroule d'alerte, ou Alerte demandee depuis Evasion/
            # Prudence : un soldat donne l'alerte (comme un nouveau reperage).
            now = time.monotonic()
            if now - getattr(self, "_alert_last_trigger", 0.0) >= self.ALERT_RETRIGGER_S:
                self._alert_last_trigger = now
                self.trigger_real_alert()
            if state == 0:
                return
        timers = {0: (0, 0), 1: (self.ALERT_SECOND_TIMER, self.ALERT_FULL_FRAMES),
                  2: (self.ALERT_SECOND_TIMER, 0), 3: (self.ALERT_CAUTION_TIMER, 0)}[wanted]
        packed = struct.pack("<ii", *timers)
        for soldier in self._alert_soldiers(manager):
            # Seulement les soldats qui participent a l'alerte (+0x4618 non
            # nul) : les autres restent en dehors, comme dans le jeu.
            current = self.proc.read_bytes(soldier + 0x4618, 8)
            if current[:4] != bytes(4) and current != packed:
                self.proc.write_bytes(soldier + 0x4618, packed)
        self.proc.write_bytes(manager + 0x74, packed)

    def read_alert_state(self) -> int:
        """Lecture seule - l'ecriture ne tient pas (voir ALERT_STATE_RVA)."""
        return int.from_bytes(self.proc.read_bytes(self.base + ALERT_STATE_RVA, 4), "little")
