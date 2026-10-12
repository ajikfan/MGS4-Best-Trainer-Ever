"""MGS4Live : pilotage de la DLL injectee : vitesse, hooks de combat, suivi des boss."""

from mgs4trainer.core.speedhack import SpeedController


class HooksMixin:
    """Pilotage de la DLL injectee : vitesse, hooks de combat, suivi des boss."""

    def set_game_speed(self, multiplier: float) -> bool:
        """multiplier=1.0 vitesse normale, <1.0 ralenti, >1.0 accelere -
        voir SpeedController. Injecte la DLL au premier appel (paresseux,
        pas au moment de la connexion : inutile de prendre ce risque tant
        que l'utilisateur ne touche pas au curseur)."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_speed(multiplier)

    def set_paused(self, paused: bool) -> bool:
        if not (self.connected and self.sane and self.pid):
            return False
        return SpeedController.set_paused(self.pid, paused)

    def set_one_shot_kill(self, enabled: bool) -> bool:
        """Injecte la DLL au premier appel (paresseux, comme set_game_speed) -
        voir SpeedController.set_one_shot_kill et native/speedhack.c."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_one_shot_kill(enabled)

    def one_shot_kill_hook_installed(self) -> bool | None:
        return self.speed.damage_hook_installed()

    def set_machine_kill(self, enabled: bool) -> bool:
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_machine_kill(enabled)

    def set_non_lethal(self, enabled: bool) -> bool:
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_non_lethal(enabled)

    def one_shot_kill_hook_error(self) -> int | None:
        return self.speed.damage_hook_error()

    def gecko_hook_installed(self) -> bool | None:
        """Diagnostic uniquement, voir install_gecko_one_shot_kill_hook
        dans native/speedhack.c - hook separe pour les Gecko, partage le
        flag one_shot_kill mais pas non_lethal (n'a pas de sens pour un
        robot)."""
        return self.speed.gecko_hook_installed()

    def gecko_hook_error(self) -> int | None:
        return self.speed.gecko_hook_error()

    def set_no_reload(self, enabled: bool) -> bool:
        """Injecte la DLL au premier appel (paresseux, comme
        set_game_speed) - voir SpeedController.set_no_reload."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_no_reload(enabled)

    def no_reload_hook_installed(self) -> bool | None:
        return self.speed.no_reload_hook_installed()

    def no_reload_hook_error(self) -> int | None:
        return self.speed.no_reload_hook_error()

    def set_no_alerts(self, enabled: bool) -> bool:
        """Injecte la DLL au premier appel (paresseux) - voir
        SpeedController.set_no_alerts."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_no_alerts(enabled)

    def no_alerts_hook_installed(self) -> bool | None:
        return self.speed.no_alerts_hook_installed()

    def no_alerts_hook_error(self) -> int | None:
        return self.speed.no_alerts_hook_error()

    def set_railgun_force_charge(self, enabled: bool) -> bool:
        """Injecte la DLL au premier appel (paresseux) - voir
        SpeedController.set_railgun_force_charge."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_railgun_force_charge(enabled)

    def force_charge_hook_installed(self) -> bool | None:
        return self.speed.force_charge_hook_installed()

    def force_charge_hook_error(self) -> int | None:
        return self.speed.force_charge_hook_error()

    def set_alert_mode_override(self, value: int | None) -> bool:
        """Injecte la DLL au premier appel (paresseux) - voir
        SpeedController.set_alert_mode_override."""
        if not (self.connected and self.sane and self.pid):
            return False
        if not self.speed.ensure_injected(self.pid):
            return False
        return self.speed.set_alert_mode_override(value)

    def alert_override_hook_installed(self) -> bool | None:
        return self.speed.alert_override_hook_installed()

    def alert_override_hook_error(self) -> int | None:
        return self.speed.alert_override_hook_error()

    def last_damaged_actor(self) -> int | None:
        """Diagnostic uniquement, voir SpeedController.last_damaged_actor."""
        return self.speed.last_damaged_actor()
