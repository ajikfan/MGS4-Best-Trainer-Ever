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

    # Pause (2026-10-24, validee en jeu) : la pause interne du jeu
    # (pause_set(2), celle du changement de visage, voir
    # EquipMixin.MODEL_LIVE_FUNCS) fige le monde mais le jeu continue de
    # dessiner la scene a chaque image (camera libre du mode photo
    # utilisable). Partagee par la touche Pause et le mode photo : levee
    # quand plus personne ne la demande. Si un menu a deja mis le jeu en
    # pause, on n'y touche pas.
    def set_game_pause(self, owner: str, paused: bool) -> bool:
        if getattr(self, "_game_pause_pid", None) != self.pid:
            self._game_pause_pid, self._game_pause_owners = self.pid, set()
        owners = self._game_pause_owners
        if paused:
            if owners:
                owners.add(owner)
                return True
            funcs = self._live_funcs(self.MODEL_LIVE_FUNCS)
            if funcs is None:
                return False
            call = self.speed.game_call
            state = call(funcs["state"])
            if state is None or state & 6:
                return False
            if call(funcs["pause_set"], self.MODEL_PAUSE_FLAG) is None:
                return False
            owners.add(owner)
            return True
        if owner not in owners:
            return False
        owners.discard(owner)
        if owners:
            return True
        funcs = self._live_funcs(self.MODEL_LIVE_FUNCS)
        return funcs is not None and self.speed.game_call(funcs["pause_clear"], self.MODEL_PAUSE_FLAG) is not None

    def set_paused(self, paused: bool) -> bool:
        """Touche Pause : pause du jeu en partie ; ailleurs (menus, ou
        si elle echoue), gel du processus comme avant."""
        if not (self.connected and self.sane and self.pid):
            return False
        if paused:
            try:
                if self.in_game() and self.speed.ensure_injected(self.pid) and self.set_game_pause("key", True):
                    return True
            except OSError:
                pass
            return SpeedController.set_paused(self.pid, True)
        try:
            if self.set_game_pause("key", False):
                return True
        except OSError:
            pass
        return SpeedController.set_paused(self.pid, False)

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
