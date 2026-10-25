"""MGS4Live : acces au jeu en cours, assemble a partir des mixins de ce paquet."""
from mgs4trainer.live.base import LiveBase
from mgs4trainer.live.camera import CameraMixin
from mgs4trainer.live.cutscene_menu import CutsceneMenuMixin
from mgs4trainer.live.code_patches import CodePatchesMixin
from mgs4trainer.live.equip import EquipMixin
from mgs4trainer.live.hooks import HooksMixin
from mgs4trainer.live.liquid_fight import LiquidFightMixin
from mgs4trainer.live.load_menu import LoadMenuMixin
from mgs4trainer.live.player import PlayerMixin
from mgs4trainer.live.sound_alert import SoundAlertMixin
from mgs4trainer.live.state import GameStateMixin
from mgs4trainer.live.weapons import WeaponsMixin
from mgs4trainer.live.zone import ZoneMixin


class MGS4Live(LiveBase, HooksMixin, PlayerMixin, WeaponsMixin, CodePatchesMixin, SoundAlertMixin, GameStateMixin, EquipMixin, ZoneMixin, CameraMixin, CutsceneMenuMixin, LoadMenuMixin, LiquidFightMixin):
    """Acces au jeu en cours : reunit les mixins de mgs4trainer.live."""
