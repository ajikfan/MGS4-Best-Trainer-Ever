"""MGS4Live : accrochage au processus, controle de coherence."""
import struct
import threading

import mgs4save

from mgs4trainer.core.gamedata import LINKVARBUF_POINTER_RVA, PROCESS_NAME, VARBUF_POINTER_RVA
from mgs4trainer.core.i18n import tr
from mgs4trainer.core.speedhack import SpeedController
from mgs4trainer.core.winproc import ProcessHandle, find_module_base, find_pid


class LiveBase:
    """Accrochage au processus, controle de coherence."""
    def __init__(self):
        self.proc: ProcessHandle | None = None
        self.pid: int | None = None
        self.base: int | None = None
        self.linkvarbuf: int | None = None
        self.varbuf: int | None = None
        self.sane = False
        self.status = tr("status.not_connected")
        self.speed = SpeedController()
        self._equip_lock = threading.Lock()  # un equipement en direct a la fois
        self._custom_menu_refresh_pending = False

    def attach(self) -> bool:
        self.detach()
        pid = find_pid(PROCESS_NAME)
        if pid is None:
            self.status = tr("status.process_not_found", process=PROCESS_NAME)
            return False
        self.pid = pid
        base = find_module_base(pid, PROCESS_NAME)
        if base is None:
            self.status = tr("status.module_not_found")
            return False
        try:
            self.proc = ProcessHandle(pid)
            self.base = base
            self.linkvarbuf = struct.unpack("<Q", self.proc.read_bytes(base + LINKVARBUF_POINTER_RVA, 8))[0]
            self.varbuf = struct.unpack("<Q", self.proc.read_bytes(base + VARBUF_POINTER_RVA, 8))[0]
            if self.varbuf == 0:
                self.status = tr("status.null_varbuf")
                return False
        except OSError as e:
            self.status = str(e)
            return False
        return self._sanity_check()

    def _sanity_check(self) -> bool:
        try:
            for item_id in sorted(mgs4save.STRUCTURAL_ITEM_IDS):
                raw = self.read_item(item_id)
                if raw != 0:
                    self.sane = False
                    self.status = tr("status.check_failed", item_id=f"{item_id:#04x}", raw=raw)
                    return False
        except OSError as e:
            self.sane = False
            self.status = tr("status.check_error", error=e)
            return False
        self.sane = True
        self.status = tr("status.connected", varbuf=f"{self.varbuf:#x}")
        return True

    def detach(self):
        if self.proc:
            self.proc.close()
            self.proc = None
        self.pid = None
        self.base = None
        self.linkvarbuf = None
        self.varbuf = None
        self.sane = False

    def check_alive(self) -> bool:
        """A appeler avant chaque rafraichissement : le statut ne se
        remettait jamais a jour tout seul si le jeu etait ferme apres une
        connexion reussie (les lectures echouent silencieusement, "sane"
        restait vrai indefiniment). Fait une lecture legere pour verifier
        que le process repond toujours ; sinon se detache proprement et
        met a jour le statut."""
        if not self.connected:
            return False
        try:
            self.proc.read_bytes(self.base, 2)
        except OSError:
            self.detach()
            self.status = tr("status.process_lost", process=PROCESS_NAME)
            return False
        return True

    @property
    def connected(self) -> bool:
        return self.proc is not None and self.varbuf is not None
