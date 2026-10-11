"""MGS4Live : vie et endurance des boss suivis."""
import struct


class BossMixin:
    """Vie et endurance des boss suivis."""

    def raven_hp(self) -> int | None:
        """Vie de Raging Raven (offsets differents de Laughing Octopus,
        boss_hp/boss_stamina) : boss_actor+0xB0, confirme fonctionnel en
        jeu (2026-09-27) - meme pointeur que boss_actor() (hook generique
        "Bosses 1/2", pas boss_actor2 qui ne s'est jamais declenche pour
        ce boss). Les deux groupes (voir set_raven_hp) restent synchronises
        par le jeu lui-meme, donc la lecture d'un seul suffit."""
        addr = self.boss_actor()
        if not addr:
            return None
        return struct.unpack("<i", self.proc.read_bytes(addr + 0xB0, 4))[0]

    # Deuxieme groupe d'adresses (vie/stamina), separe de boss_actor, a un
    # ecart fixe mais negatif par rapport a lui - trouve par scan exact
    # (2026-09-27). Ecrire UNIQUEMENT dans boss_actor+0xB0/+0xE8 n'avait
    # aucun effet durable (le jeu re-synchronisait depuis ce second groupe
    # au coup suivant, jamais touche) - confirme qu'il faut ecrire les DEUX
    # pour que ca tienne reellement en jeu.
    RAVEN_SECOND_GROUP_OFFSET = -0x1576C

    # Crying Wolf : meme principe (+0xB0/+0xE8 confirmes fonctionnels en
    # lecture, mais ecrire uniquement la n'a pas suffi non plus) - second
    # groupe repere par elimination (candidat tombe a 0 pile au moment de
    # sa mort, 2026-09-27) mais PAS confirme causalement (combat termine
    # avant de pouvoir tester une ecriture). Ecart trouve : -0xB09C par
    # rapport a boss_actor - a valider sur un prochain combat avant de
    # cabler en dur comme RAVEN_SECOND_GROUP_OFFSET (l'ecart semble
    # specifique a chaque boss, pas une constante universelle : celui de
    # Raging Raven ne s'appliquait pas du tout ici).
    CRYING_WOLF_SECOND_GROUP_OFFSET_UNCONFIRMED = -0xB09C

    def set_raven_hp(self, value: int) -> bool:
        addr = self.boss_actor()
        if not addr:
            return False
        self.proc.write_bytes(addr + 0xB0, struct.pack("<i", value))
        self.proc.write_bytes(addr + self.RAVEN_SECOND_GROUP_OFFSET, struct.pack("<i", value))
        return True

    def raven_stamina(self) -> int | None:
        """Stamina de Raging Raven : boss_actor+0xE8, voir raven_hp."""
        addr = self.boss_actor()
        if not addr:
            return None
        return struct.unpack("<i", self.proc.read_bytes(addr + 0xE8, 4))[0]

    def set_raven_stamina(self, value: int) -> bool:
        addr = self.boss_actor()
        if not addr:
            return False
        self.proc.write_bytes(addr + 0xE8, struct.pack("<i", value))
        self.proc.write_bytes(addr + self.RAVEN_SECOND_GROUP_OFFSET + 8, struct.pack("<i", value))
        return True

    # Detection automatique du boss actif pour "Un coup, un mort" cote
    # boss (VitalsTab._reassert_boss_staged_damage) : deux boss testes a
    # ce jour, deux jeux d'offsets differents selon lequel des deux hooks
    # de tracking se declenche (2026-09-27) - Laughing Octopus passe par
    # boss_actor2 (+0x314/+0x31C), Raging Raven seulement par boss_actor
    # (+0xB0/+0xE8, boss_actor2 ne s'est jamais declenche pour elle).
    # Pas de mapping par niveau/acte (champ non mirroré de façon
    # exploitable dans varbuf, teste et abandonne) - on essaie juste les
    # deux hooks dans l'ordre et on garde celui qui repond.

    def active_boss_addr(self) -> int | None:
        return self.boss_actor2() or self.boss_actor()

    def active_boss_kind(self) -> str | None:
        """"octopus" (boss_actor2, connu multi-phases - voir notes.md,
        le forcage direct a 0 y a deja bloque un combat) ou "raven"
        (boss_actor seul, pas de phase connue - 2026-09-27) - permet de
        varier le comportement de _reassert_boss_staged_damage sans
        avoir besoin d'identifier le niveau/boss par son nom."""
        if self.boss_actor2():
            return "octopus"
        if self.boss_actor():
            return "raven"
        return None

    def active_boss_hp(self) -> int | None:
        return self.boss_hp() if self.boss_actor2() else self.raven_hp()

    def set_active_boss_hp(self, value: int) -> bool:
        return self.set_boss_hp(value) if self.boss_actor2() else self.set_raven_hp(value)

    def active_boss_stamina(self) -> int | None:
        return self.boss_stamina() if self.boss_actor2() else self.raven_stamina()

    def set_active_boss_stamina(self, value: int) -> bool:
        return self.set_boss_stamina(value) if self.boss_actor2() else self.set_raven_stamina(value)

    def boss_stamina(self) -> int | None:
        """Stamina/alerte du boss suivi (+0x31C) - mecanisme distinct de
        la vie (+0x314), constate actif sur au moins une phase (2026-09-26,
        ou tirer a balles reelles ne faisait pas baisser la vie mais les
        munitions non letales faisaient bien baisser la stamina - meme
        logique "assommer" que les soldats standards de MGS4). Offset
        corrige le meme jour : +0x320 (documente par le CE table communautaire
        comme "+31C+4") ne bougeait jamais en temps reel malgre des degats
        reels visibles - un scan par valeur exacte a montre que c'est
        +0x31C qui suit vraiment les degats, +0x320 restant fige (probable
        copie/reference statique voisine)."""
        addr = self.boss_actor2()
        if not addr:
            return None
        return struct.unpack("<i", self.proc.read_bytes(addr + 0x31C, 4))[0]

    def set_boss_stamina(self, value: int) -> bool:
        addr = self.boss_actor2()
        if not addr:
            return False
        self.proc.write_bytes(addr + 0x31C, struct.pack("<i", value))
        return True
