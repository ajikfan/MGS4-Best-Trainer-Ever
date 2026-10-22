"""MGS4Live : patchs de code (CODE_PATCHES) et leur application."""
class CodePatchesMixin:
    """Patchs de code (CODE_PATCHES) et leur application."""

    # Patchs de code ecrits directement (pas de DLL) : RVA -> (octets
    # d'origine, octets du patch). Signature complete verifiee avant
    # toute ecriture (rien n'est ecrit sur une autre version du jeu).
    #  - Intouchable (2026-10-04) : 96C0B0 traite la liste des coups recus
    #    par Snake pendant l'image (degats vie/endurance, reaction,
    #    projection ; seul appelant 975232, retour ignore). "ret" a son
    #    entree : insensible a tout impact, letal ou non - valide en jeu
    #    (balles, explosions, mines, corps a corps).
    #    Metal Gear REX (2026-10-22, valide contre Ray) : sa mise a jour
    #    (136F3E0, table 1908A08) parcourt sa liste de coups (objet+0x58 :
    #    premier coup D41AC0, en 136F5B6) et pour chacun cumule les degats
    #    (+0x80, retires de linkvarbuf+0xB70), joue son, secousse et effets,
    #    arme une invulnerabilite (+0x78) ; D41AA0 vide ensuite la liste.
    #    "call D41AC0" -> "xor eax,eax" : aucun coup lu, liste videe quand
    #    meme -> ni degats ni reaction (les poussees physiques, Ray qui le
    #    bouscule, restent).
    #  - Invisible (2026-10-04) : 89360 renvoie l'exposition de Snake
    #    (0 = invisible, 1 = bien visible) a partir de l'indice de
    #    camouflage ; le Camouflage furtif (etat joueur 0xA9) la force a 0.
    #    Utilisee par le code des soldats et par le HUD (F4D770). La faire
    #    renvoyer 0 ("xorps xmm0,xmm0 ; ret") : les soldats ne voient plus
    #    Snake, meme debout devant eux, sans le rendre transparent - valide
    #    en jeu. Le HUD affiche 99 % (plafond hors Camouflage furtif).
    #    89410 = meme calcul sans le test du Camouflage furtif (autres
    #    ennemis). Certains soldats (Millennium Park) testent en plus
    #    directement l'etat 0xA9 via 8DA980 ("un joueur a-t-il cet etat ?") :
    #    les 14 appels "mov ecx,0xA9 ; call 8DA980" deviennent "mov eax,1".
    #    Snake ne devient pas transparent pour autant - valide en jeu.
    _STEALTH_CHECK_CALLS = {
        0xB25504: "e87754dbff", 0xB25B26: "e8554edbff", 0xB264F3: "e88844dbff",
        0xB29D9C: "e8df0bdbff", 0xB3554B: "e83054daff", 0xB355C0: "e8bb53daff",
        0xB3AA9F: "e8dcfed9ff", 0xB3AC14: "e867fdd9ff", 0xB3ADE5: "e896fbd9ff",
        0xB46F20: "e85b3ad9ff", 0xB4E48A: "e8f1c4d8ff", 0x1002017: "e864898dff",
        0x1012AC1: "e8ba7e8cff", 0x134B1C2: "e8b9f758ff",
    }
    #  - Mini Gekko (2026-10-04, valide en jeu) : 11FBE10 traite leurs
    #    coups (vie +0x12DC, 2 balles), puis appelle 11DB320 (destruction)
    #    si elle est <= 0. Le "jg" (11FBF86) est neutralise : chaque coup
    #    recu declenche la destruction par le jeu.
    #  - Un coup, un mort sur les vehicules (2026-10-04, valide en jeu) :
    #    102D9C0 = rappel de collision d'un vehicule (Millennium Park) avec
    #    liste blanche M82A2/Rail Gun : le "jne" de rejet (102DAF3) est
    #    neutralise. Helicopteres : vie a objet+0x1068 (max +0x106C), mise
    #    a jour 1352770 ; 13532A0 filtre les types d'attaque (lance-
    #    roquettes, explosifs, M82A2, Rail Gun seulement) -> accepte tout ;
    #    le bit 12 du coup ("mise a mort" = degats = vie max, test a
    #    13528F1) est considere toujours present.
    #  - Un coup, un mort sur Laughing Octopus (2026-10-04, valide en jeu) :
    #    1434701 applique un coup a sa vie (objet 18BC1B0, +0x314) ; un
    #    degat de 0x7FFFFFFF y vaut "mise a mort" (degat = vie actuelle).
    #    Neutraliser le "jne" (1434D26) traite chaque coup ainsi ; la vie
    #    est ensuite corrigee par le jeu (1435110) aux seuils de phase :
    #    un tir par phase, transitions et fin geres par le jeu.
    #    Forme Beauty (1173BB1) : un coup ordinaire ne peut pas descendre
    #    sous 2 % de la vie max (seul un coup marque, r15b, passe outre) ;
    #    "sub r8d,ebx" (1173D8D) -> "xor r8d,r8d" : vie a 0 au premier coup
    #    (valide en jeu sur Laughing Beauty, elle meurt).
    #    Raging Raven (13F8A6C, vraie vie = objet 18BC1B0 [acteur+0x42E8] ;
    #    acteur+0xB0 n'est que la jauge du HUD recopiee par E3B740) : meme
    #    sentinelle 0x7FFFFFFF ; "cmovne eax,esi" (13F8C0D) neutralise ->
    #    chaque coup = mise a mort (valide en jeu, morte en un tir).
    #    Crying Wolf (FE7D80, vraie vie = objet de type mgs4+18EA598 a
    #    [acteur+0xE20], +0x314 ; jauge HUD recopiee a F6E311) : six
    #    branches "vie - degat" selon le type d'attaque ; chaque "sub
    #    ecx,eax" -> "xor ecx,ecx" (vie a 0). Endurance (+0x31C) non
    #    touchee. Valide en jeu.
    #    Vamp (1123110, vie objet +0x314, 15000) : "sub eax,edi" (1123568)
    #    -> "xor eax,eax" : a terre au premier tir ; la seringue reste
    #    necessaire pour le vaincre (mecanique du combat, non contournee).
    #    Metal Gear RAY (138D270, vie objet 18BC1B0 +0x314, 60000, juste
    #    avant sa liste de coups) : meme sentinelle 0x7FFFFFFF ; "jne"
    #    (138D493) neutralise -> mort au premier coup (valide en jeu).
    #    Screaming Mantis, forme bete (F08CF0, vie objet [acteur+0x42B8]) :
    #    sentinelle 0x7FFFFFFF (jne F08FC2 neutralise) ; mais la vie est
    #    plancher a 50 (F09018) : seule l'endurance (+0x31C) a 0 lance la
    #    defaite. Le "jg" (F09038) qui la saute tant que l'endurance est
    #    positive est neutralise : le jeu met lui-meme l'endurance a 0 et
    #    lance la sequence de defaite a chaque coup (vie + endurance
    #    videes ensemble, demande utilisateur). Non encore teste en jeu
    #    (patch de vie seul valide).
    #    Liquid Ocelot, combat final (11270E0, vie objet +0x314, 1000) :
    #    vie = max(vie - degat, plancher de la phase) ; "sub edx,edi"
    #    (112717A) -> "xor edx,edx" : chaque coup amene au plancher, le
    #    suivant lance la phase suivante (transitions par le jeu, valide).
    #  - Objets destructibles (portails a deux portes detruits au canon de
    #    tank, 2026-10-04, valide en jeu) : 12637B0 applique un impact a
    #    l'objet (vie +0x34, 80000 par porte ; degat de l'impact +0x40) puis
    #    la borne au minimum du niveau ([rsi+0x248], verrou de scenario
    #    eventuel, conserve). "mov eax,[rdi+40] ; sub [rdi+34],eax"
    #    (126385F) -> "xor eax,eax ; mov [rdi+34],eax" : detruit au premier
    #    impact. Pas un objet de vie 18BC1B0 ni la liste de coups D41940.
    #  - Silencieux illimites (2026-10-09) : la fonction de tir 6E1BE,
    #    si un silencieux est monte (bit 0 de [arme+0x2C]), retire 1 a son
    #    compteur courant (dec [silencieux+0x30], 6E2AA) et 1 a sa reserve
    #    (dec [table munitions+idx*0x18+0x10], 6E2B2) : les deux en NOP.
    #  - Stress fige (2026-10-09) : la mise a jour du stress (971690) ecrit
    #    linkvarbuf+0xB50 trois fois par image (gain 1 plafonne 971AC1,
    #    gain 2 plafonne 971B34, baisse naturelle 971B8F) : les trois en NOP
    #    quand la ligne Stress est verrouillee (sinon 0 -> 0.1 -> 0 entre deux
    #    reecritures). Le stress reste a la valeur verrouillee.
    #  - Vie / endurance / batterie figees (2026-10-10) : meme principe, la
    #    mise a jour de Snake ecrit chaque jauge a chaque image (vie : 96C53B
    #    degats dans 96C207, 96D146/96D1B7/96D21F dans 96CF1B ; endurance :
    #    96C60D, 96D39C ; batterie Solid Eye : A46117), plus les autres
    #    ecritures de la mise a jour de Snake (96xxxx/97xxxx) trouvees en
    #    cherchant tous les "mov word [reg+0xB48/0xB4C]" ; les fonctions
    #    utilitaires (8DAxxx, 14Bxxxx : objets, chargement) restent libres.
    #  - Un coup, un mort Non letal sur les boss (2026-10-10) : B800B0 retire
    #    de l'endurance (+0x31C) a un objet de vie ; un degat de 0x7FFFFFFF
    #    la vide (meme sentinelle que la vie). Le "jne" (B800CC) neutralise
    #    traite chaque coup non letal ainsi ; les seuils de phase restent
    #    geres par le jeu (Laughing Octopus : un coup par phase, valide en
    #    jeu ; Raging Raven et Screaming Mantis bete passent aussi par
    #    B800B0, comme des fonctions de soldats). Forme Beauty (1173BB1,
    #    commune aux quatre) : "sub ecx,ebx" (1173CF9) -> "xor ecx,ecx",
    #    endurance a 0 au premier coup (valide sur Laughing Beauty). Crying
    #    Wolf (FE7D80) : voir les entrees dediees plus bas.
    #    Armes letales en Non letal (comme les soldats : la vie n'est jamais
    #    touchee, le coup vide l'endurance) : Octopus bete, passage force par
    #    B800B0 ("jle" 1434BCF) et ecriture de vie 1434D68 neutralisee ;
    #    Beauty, "je" vers le chemin vie (1173BC7) neutralise - valides en
    #    jeu. Raging Raven : chemin vie redirige vers l'appel d'endurance
    #    (13F8BFF -> jmp 13F8C6D), valide en jeu au M4 (2026-10-12) ;
    #    Screaming Mantis bete : ecriture de vie F08FF0 neutralisee
    #    (l'endurance a 0 lance la defaite) - non teste.
    #  - Mini Gekko (2026-10-10, comme les soldats) : 1216B90 choisit la
    #    reaction apres un coup ; type 0x37 ou bit 15 (flechette) -> 0x15
    #    (paralysie), meme si le drapeau "mort" (+0x1308 bit 1, pose par
    #    11DB320) est la ; sinon 0x11/0x13 (mort) ou 0x10/0x14.
    #    Letal : destruction au premier coup (jg 11FBF86), flechette
    #    enregistree comme un coup (11DBFE0 la rangeait en simple contact :
    #    bts 11DC059 neutralise) et plus de paralysie (jb 1216CC9 neutralise).
    #    Non letal : aucun degat (sub 11FBF78 neutralise) et la paralysie pour
    #    tout coup (1216D74), sauf :
    #     - mini Gekko deja marque mort (r8 = [+0x1308], bit 1) : reaction
    #       normale (1216D45, mort 0x13) ;
    #     - contact de Snake qui marche dessus (type 0x68, sans enregistrement
    #       de coup, a chaque image) : sursaut normal (1216CD4, reaction 0x16).
    #    La paralysie relancee a chaque image sur plusieurs mini Gekko laissait
    #    des taches liberees dans la liste des taches (plantage 2026-10-11,
    #    73F5EB, taches 11FD310 voisines abimees).
    #    1216CBF : "test r8b,2 ; jne 1216D45" ;
    #    1216CC9 : "cmp eax,0x68 ; je 1216CD4 ; jmp 1216D74".
    #  - Pas d'alerte (2026-10-12, notre propre analyse) : l'etat d'alerte
    #    (mgs4+1D77AB8) est ecrit par la mise a jour B5C2C7 a partir de
    #    B5FA90, qui parcourt les unites de soldats (entrees de 0xE0) :
    #    etat propose par l'unite (+0xC8, garde dans ebx a B5FC33), max de
    #    leurs minuteries (+0xB4/+0xB8 -> esi/ebp, cmovl B5FC0F/B5FC14)
    #    recopie dans le gestionnaire (+0x74/+0x78). Ces trois prises
    #    neutralisees : la fonction tourne toujours (comptes de soldats)
    #    mais renvoie Normal, minuteries a 0. Meme fonction que le script
    #    "aob No Alerts" de MGS4.CT (qui la court-circuitait a l'entree),
    #    retrouvee independamment depuis l'ecriture de l'etat.
    #  - Un coup, un mort sur les soldats (2026-10-13, notre propre analyse,
    #    trouve par point d'arret materiel sur la vie d'un soldat) : C52190
    #    applique un coup a l'objet de vie d'un soldat (18BC1B0 : +0x314 vie,
    #    +0x31C endurance, +0x324 sommeil). Elle charge r9d = 0x7FFFFFFF,
    #    la "mise a mort" du jeu, et l'utilise comme degats dans certains cas
    #    (C5225F) ; puis aiguille : coups d'endurance/etourdissement vers
    #    C52458, flechettes (bit 15) vers C52297, sinon C523B9 : etat 0x4000
    #    -> sommeil (B80300, qui reconnait aussi 0x7FFFFFFF : jauge videe),
    #    autrement vie (C523D4). C5223E : "mov ebp,r9d ; jmp C523B9" (tout
    #    coup = mise a mort, quel que soit son type), puis C523C3 :
    #    Letal -> "jmp" vers la vie (mort), Non letal -> NOP vers le sommeil
    #    (endormi, Z). Valide en jeu (balles, flechettes, deux modes).
    #    Remplace le hook DLL repris du script "aob Damage" de MGS4.CT.
    CODE_PATCHES = {
        # Site C5223E commun aux deux (jamais poses ensemble, voir
        # VitalsTab._apply_instant_kill_mode).
        # Gekko, Letal : 1048160 prend tout coup d'etat 0x4000 (flechettes du
        # Mk.2) pour un tranquillisant. Son test (1048188 "jae") devient
        # "jmp" : la flechette va au gestionnaire des balles (1047EF0), donc
        # a la mise a mort B21FF0.
        "gekko_dart_kill": [
            # Signature ancree sur le "bt eax,0xe" precedent : elle ne doit pas
            # deborder sur le site de gekko_non_lethal_sleep (104818E).
            (0x1048184, bytes.fromhex("0fbae00e0f830d020000"), bytes.fromhex("0fbae00ee90e02000090")),
        ],
        # Gekko, Non letal (2026-10-13) : une flechette endort un Gekko quand
        # ses deux jauges de tranquillisant (objet de vie, mots +0x33C et
        # +0x340) tombent a 0, mais seulement touche a la jambe (104818E :
        # drapeaux du coup +0x88 & 0x240 ou 0x210). Tout coup est pris par
        # 1048160 (test de l'etat 0x4000 neutralise, site partage avec
        # gekko_dart_kill), le test de jambe devient "drapeaux de jambe poses"
        # (or [rbx+0x88],0x240), le coup est reecrit en flechette du Mk.2
        # (type +0x10C = 0x10008202 : sans ca, une balle fait seulement
        # s'accroupir le Gekko) et les quatre calculs de jauge ("add cx,dx"
        # avant chaque ecriture) donnent 0 : endormi au premier coup, toute
        # arme, ou qu'on le touche (valide a l'Operator et au Mk.2).
        "gekko_non_lethal_sleep": [
            (0x1048184, bytes.fromhex("0fbae00e0f830d020000"), bytes.fromhex("0fbae00e909090909090")),
            (0x104818E, bytes.fromhex("8b93880000008bc225400200003d400200000f95c181e21002000081fa100200000f95c084c80f85cf010000"),
             bytes.fromhex("818b8800000040020000" + "c7830c01000002820010" + "90" * 24)),
            (0x1048243, bytes.fromhex("6603ca66898b4003"), bytes.fromhex("31c990")),
            (0x10482A1, bytes.fromhex("6603ca9983e207"), bytes.fromhex("31c990")),
            (0x104831A, bytes.fromhex("6603ca66898b4003"), bytes.fromhex("31c990")),
            (0x1048362, bytes.fromhex("6603ca66898b3c03"), bytes.fromhex("31c990")),
        ],
        "soldier_one_shot_kill": [
            (0xC5223E, bytes.fromhex("85ed7e218b83ac45"), bytes.fromhex("4489cde973010000")),
            (0xC523C3, bytes.fromhex("740f8bd5488bcfe8"), bytes.fromhex("eb0f")),
        ],
        "soldier_non_lethal_kill": [
            (0xC5223E, bytes.fromhex("85ed7e218b83ac45"), bytes.fromhex("4489cde973010000")),
            (0xC523C3, bytes.fromhex("740f8bd5488bcfe8"), bytes.fromhex("9090")),
        ],
        "minigekko_lethal": [
            (0x11FBF86, bytes.fromhex("7f08488bcbe890f3"), bytes.fromhex("9090")),
            (0x11DC059, bytes.fromhex("410fbaea1841f7c2"), bytes.fromhex("9090909090")),
            (0x1216CC9, bytes.fromhex("0f82a500000083f868"), bytes.fromhex("909090909090")),
        ],
        "minigekko_non_lethal": [
            (0x11FBF78, bytes.fromhex("29b3dc1200008b83dc"), bytes.fromhex("909090909090")),
            (0x1216CBF, bytes.fromhex("0f84af0000000fbae10f"), bytes.fromhex("41f6c0020f857c000000")),
            # Site partage avec minigekko_lethal (les deux ne sont jamais poses
            # ensemble : _apply_instant_kill_mode retire d'abord l'autre).
            (0x1216CC9, bytes.fromhex("0f82a500000083f8687508"), bytes.fromhex("83f8687406e9a1000000")),
        ],
        "boss_non_lethal_kill": [
            (0xB800CC, bytes.fromhex("756f448b891c030000"), bytes.fromhex("9090")),
            (0x1173CF9, bytes.fromhex("2bcb4863c148f7d8"), bytes.fromhex("31c9")),
            # Armes letales -> endurance, comme les soldats (vie jamais touchee).
            (0x1434BCF, bytes.fromhex("0f8ef20000008bd049"), bytes.fromhex("909090909090")),
            (0x1434D68, bytes.fromhex("41899614030000e89c03"), bytes.fromhex("90909090909090")),
            (0x1173BC7, bytes.fromhex("0f845d010000448b8d"), bytes.fromhex("909090909090")),
            (0x13F8BFF, bytes.fromhex("81feffffff7f8b8d14"), bytes.fromhex("e96900000090")),
            (0xF08FF0, bytes.fromhex("41898814030000e884"), bytes.fromhex("90909090909090")),
            # Crying Wolf (FE7D80, son propre calcul) : chaque "endurance -
            # degat" -> 0 ; les branches "vie" (coups letaux) mettent aussi 0
            # (memes "sub" que le patch Letal) mais l'ecriture est redirigee
            # vers l'endurance (+0x314 -> +0x31C) : la vie n'est jamais touchee.
            (0xFE7E21, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE7E9E, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE7FB7, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE805F, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE80B4, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8157, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8425, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE84E0, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE85BD, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8864, bytes.fromhex("2bca4863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE89FC, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8A96, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8B30, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE823C, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE835B, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8654, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE87A7, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE88F3, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE896A, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE824F, bytes.fromhex("8983140300008bc5"), bytes.fromhex("89831c030000")),
            (0xFE836C, bytes.fromhex("8983140300008d42"), bytes.fromhex("89831c030000")),
            (0xFE8665, bytes.fromhex("8983140300008d42"), bytes.fromhex("89831c030000")),
            (0xFE87B8, bytes.fromhex("898314030000e84d"), bytes.fromhex("89831c030000")),
            (0xFE8901, bytes.fromhex("898314030000e945"), bytes.fromhex("89831c030000")),
            (0xFE897B, bytes.fromhex("898314030000e88a"), bytes.fromhex("89831c030000")),
        ],
        "health_freeze": [
            (0x96C53B, bytes.fromhex("66418989480b00004489a7"), bytes.fromhex("9090909090909090")),
            (0x96D146, bytes.fromhex("66418989480b0000488b07"), bytes.fromhex("9090909090909090")),
            (0x96D1B7, bytes.fromhex("66418989480b0000488b07"), bytes.fromhex("9090909090909090")),
            (0x96D21F, bytes.fromhex("66418989480b0000488bcf"), bytes.fromhex("9090909090909090")),
            (0x96C933, bytes.fromhex("66418989480b0000f68704"), bytes.fromhex("9090909090909090")),
            (0x96CA3B, bytes.fromhex("66458982480b0000e818d9"), bytes.fromhex("9090909090909090")),
            (0x96D469, bytes.fromhex("66458982480b0000e8eace"), bytes.fromhex("9090909090909090")),
            (0x9763B5, bytes.fromhex("66418988480b0000c3cccc"), bytes.fromhex("9090909090909090")),
        ],
        "stamina_freeze": [
            (0x96C60D, bytes.fromhex("664189884c0b000048c787"), bytes.fromhex("9090909090909090")),
            (0x96D39C, bytes.fromhex("664189884c0b0000488bcf"), bytes.fromhex("9090909090909090")),
            (0x96C996, bytes.fromhex("664189894c0b0000488b07"), bytes.fromhex("9090909090909090")),
            (0x9700AE, bytes.fromhex("6641898a4c0b00004883c4"), bytes.fromhex("9090909090909090")),
            (0x9764A5, bytes.fromhex("664189884c0b0000c3cccc"), bytes.fromhex("9090909090909090")),
        ],
        # Drebin 893 : 1030096 applique un coup (vie = bornee(vie - degat)),
        # "mov [rdi+0x18],ecx" (10301CE) en NOP quand la ligne est verrouillee.
        "drebin_freeze": [
            (0x10301CE, bytes.fromhex("894f18c7473001000000"), bytes.fromhex("909090")),
        ],
        # Metal Gear REX (linkvarbuf+0xB70, u32) : degats 136F8F9, regeneration
        # 136F5A4 et autres ecritures de son code (136F2C3, 136F467, 1374BB2).
        "rex_freeze": [
            (0x136F2C3, bytes.fromhex("8988700b0000488d4b"), bytes.fromhex("909090909090")),
            (0x136F467, bytes.fromhex("8998700b00008d41f6"), bytes.fromhex("909090909090")),
            (0x136F5A4, bytes.fromhex("8988700b000033d248"), bytes.fromhex("909090909090")),
            (0x136F8F9, bytes.fromhex("8988700b0000c78780"), bytes.fromhex("909090909090")),
            (0x1374BB2, bytes.fromhex("8988700b0000b92100"), bytes.fromhex("909090909090")),
        ],
        # Mitrailleuse de REX (2026-10-10) : chaleur int32 a objet+0x850
        # (max 0xFA0, % affiche a +0x854). 138209E la relit, ajoute le tir,
        # borne a 0xFA0 et l'ecrit (1382167) puis surchauffe si eax = 0xFA0 ;
        # ecriture en NOP -> la chaleur reste a son niveau (le refroidissement
        # 138109D la ramene a 0) et le seuil n'est jamais atteint.
        "rex_gun_no_heat": [
            (0x1382167, bytes.fromhex("8986500800003da00f0000"), bytes.fromhex("909090909090")),
        ],
        # Missiles de REX (2026-10-10) : 15 tubes, minuteur de rechargement
        # par tube a objet+0x85C..+0x894 (0 = pret) ; +0x858 = tubes prets,
        # recompte a chaque image (138130E). Un tir decremente +0x858
        # (138209E) et arme le minuteur du tube (13820C6) : les deux en NOP
        # -> tubes toujours prets, 15/15.
        "rex_infinite_missiles": [
            (0x138209E, bytes.fromhex("ff8e58080000488d1555"), bytes.fromhex("909090909090")),
            (0x13820C6, bytes.fromhex("428984a65c080000e85d"), bytes.fromhex("9090909090909090")),
        ],
        # Laser de REX (2026-10-10) : charge int32 a +0x8C d'un objet de tir,
        # plafonnee par la reserve +0x84 (le "x/100" du HUD, max +0x88 =
        # 10000 ; niveaux 1-5 deduits de charge/+0x88). En charge, 137556A
        # fait charge = min(charge + vitesse*2, reserve) : lea et cmp/cmovle
        # neutralises, il reste "mov eax,[rsi+0x84]" -> charge pleine des la
        # premiere image. Au tir, 137582B retire la meme quantite a la charge
        # et a la reserve : ecriture de la reserve (1375871) en NOP -> elle
        # reste pleine, le rayon garde sa duree normale.
        "rex_laser_full_charge": [
            (0x1375578, bytes.fromhex("8d0c688b86840000003bc80f4ec1"), bytes.fromhex("9090908b86840000009090909090")),
            (0x1375871, bytes.fromhex("898684000000410f49c9"), bytes.fromhex("909090909090")),
        ],
        "battery_freeze": [
            (0xA46117, bytes.fromhex("66418988520b0000c3c200"), bytes.fromhex("9090909090909090")),
        ],
        "stress_freeze": [
            (0x971AC1, bytes.fromhex("66418981500b0000488b06"), bytes.fromhex("9090909090909090")),
            (0x971B34, bytes.fromhex("66418981500b000039ae38"), bytes.fromhex("9090909090909090")),
            (0x971B8F, bytes.fromhex("66418988500b0000488b05"), bytes.fromhex("9090909090909090")),
        ],
        "infinite_silencer": [
            (0x6E2AA, bytes.fromhex("66ff4830488d1449"), bytes.fromhex("90909090")),
            (0x6E2B2, bytes.fromhex("66ff8cd7a0000000"), bytes.fromhex("9090909090909090")),
        ],
        # Le plancher de scenario ([rsi+0x248], 1263870) est conserve : le
        # contourner detruisait un portail avant son declencheur de script
        # et bloquait la progression (constate 2026-10-10).
        "destructibles_one_shot_kill": [
            (0x126385F, bytes.fromhex("8b47402947348b4734"), bytes.fromhex("31c089473490")),
            # 12632A0 enregistre un coup sur l'objet ; filtres leves pour que
            # toute arme compte : liste noire de types (1263364), et le bit
            # 0x8000 (flechettes du Mk.2, drapeaux 0x10008202) retire du masque
            # de rejet 0xD8000 (1263342). Le filtre d'impact 0x3200 (126341F)
            # reste : il ecarte les rayons de visee (drapeaux 0x58).
            (0x1263342, bytes.fromhex("f7c100800d000f8556"), bytes.fromhex("f7c100000d00")),
            (0x1263364, bytes.fromhex("0f823a0100000fbae1"), bytes.fromhex("909090909090")),
        ],
        "boss_one_shot_kill": [
            (0x1434D26, bytes.fromhex("7503448bc0412bc0"), bytes.fromhex("9090")),
            (0x1173D8D, bytes.fromhex("442bc34963c048f7"), bytes.fromhex("4531c0")),
            (0x13F8C0D, bytes.fromhex("0f45c62bc84863c1"), bytes.fromhex("909090")),
            (0xFE823C, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE835B, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8654, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE87A7, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE88F3, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE896A, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0x1123568, bytes.fromhex("2bc74863c848f7d9"), bytes.fromhex("31c0")),
            (0x138D493, bytes.fromhex("750c448b85140300"), bytes.fromhex("9090")),
            (0xF08FC2, bytes.fromhex("75028bd82bc34898"), bytes.fromhex("9090")),
            (0xF09038, bytes.fromhex("0f8f42010000f30f"), bytes.fromhex("909090909090")),
            # Toute arme tue (comme les soldats), aussi les coups d'endurance
            # (flechettes...) : Crying Wolf, branches endurance -> 0 et ecriture
            # redirigee vers la vie ; Octopus, chemin vie force avec la valeur
            # de mise a mort (1434CC7, jle 1434CCE neutralise) ; Beauty, tout
            # coup par le chemin vie (1173BC7 jmp) ; Raven, chemin endurance
            # redirige vers le chemin vie (13F8C6D jmp 13F8BFF).
            (0xFE7E21, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE7E9E, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE7FB7, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE805F, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE80B4, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8157, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8425, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE84E0, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE85BD, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8864, bytes.fromhex("2bca4863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE89FC, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8A96, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE8B30, bytes.fromhex("2bc84863c148f7d8"), bytes.fromhex("31c9")),
            (0xFE7E2F, bytes.fromhex("89831c03000085c0"), bytes.fromhex("898314030000")),
            (0xFE7EAC, bytes.fromhex("89831c0300008d42"), bytes.fromhex("898314030000")),
            (0xFE7FC8, bytes.fromhex("89831c030000e8bd"), bytes.fromhex("898314030000")),
            (0xFE8070, bytes.fromhex("89831c030000e815"), bytes.fromhex("898314030000")),
            (0xFE80C2, bytes.fromhex("89831c0300000f8f"), bytes.fromhex("898314030000")),
            (0xFE816A, bytes.fromhex("89831c0300008bc5"), bytes.fromhex("898314030000")),
            (0xFE8435, bytes.fromhex("89831c0300008d42"), bytes.fromhex("898314030000")),
            (0xFE84F1, bytes.fromhex("89831c0300008d42"), bytes.fromhex("898314030000")),
            (0xFE85CB, bytes.fromhex("89831c0300008d42"), bytes.fromhex("898314030000")),
            (0xFE8872, bytes.fromhex("89831c0300007f1a"), bytes.fromhex("898314030000")),
            (0xFE8A0D, bytes.fromhex("89831c030000e8d8"), bytes.fromhex("898314030000")),
            (0xFE8AA7, bytes.fromhex("89831c0300008d42"), bytes.fromhex("898314030000")),
            (0xFE8B3E, bytes.fromhex("89831c030000488b"), bytes.fromhex("898314030000")),
            (0x1434CCE, bytes.fromhex("0f8e67010000496386"), bytes.fromhex("909090909090")),
            (0x1434CC7, bytes.fromhex("448b456f4585c0"), bytes.fromhex("41b8ffffff7f90")),
            (0x1173BC7, bytes.fromhex("0f845d010000448b8d"), bytes.fromhex("e95e01000090")),
            (0x13F8C6D, bytes.fromhex("8bd6488bcde8397478"), bytes.fromhex("e98dffffff")),
        ],
        "vehicles_one_shot_kill": [
            (0x102DAF3, bytes.fromhex("755e488d4c2430"), bytes.fromhex("9090")),
            (0x13532A0, bytes.fromhex("f7c10000050075"), bytes.fromhex("b801000000c3")),
            (0x13528F5, bytes.fromhex("730b660f6e83"), bytes.fromhex("9090")),
            # Helico : coups au bit 15 (0x8000, flechettes du Mk.2) ignores
            # (13528C1 "bt edi,0xf ; jb") -> acceptes.
            (0x13528C5, bytes.fromhex("727d8bc725004001"), bytes.fromhex("9090")),
            # Tanks (gestionnaire de coups FF9290) : coups au bit 15 (Mk.2)
            # ignores (FF9387 "bt edx,0xf ; jb") -> acceptes.
            (0xFF938B, bytes.fromhex("0f82ba0000000fbae2"), bytes.fromhex("909090909090")),
            # Gekko et tanks (2026-10-13, notre propre analyse) : B21FF0 retire
            # de la vie a un objet de vie ; un degat de 0x7FFFFFFF y vaut deja
            # "mise a mort" (degat = vie restante). "cmove eax,r8d" (B2200E)
            # -> "mov eax,r8d" et "jne" (B22042) neutralise : tout coup est une
            # mise a mort. Remplace le hook DLL repris du script "aob Damage
            # Gecko" de MGS4.CT. Appelee aussi par quelques effets continus
            # sur les soldats (gaz, feu), comme l'ancien hook.
            (0xB2200E, bytes.fromhex("410f44c04863c8"), bytes.fromhex("418bc090")),
            (0xB22042, bytes.fromhex("750c458b91"), bytes.fromhex("9090")),
            # Balles tranquillisantes du Mosin-Nagant (2026-10-12, drapeaux
            # 0x84082B) : 10483B0 tient tout coup au bit 23 pour traite sans
            # degats (10483EB "bt eax,0x17 ; jb 1048522") -> le saut est
            # neutralise, la balle suit le chemin des autres coups.
            (0x10483EF, bytes.fromhex("0f822d01000025ff03"), bytes.fromhex("909090909090")),
            # Metal Gear RAY (2026-10-10, 60000 de vie, aucune endurance) : sa
            # propre fonction de degats 138D270 calcule vie - degat puis
            # l'ecrit (138D4DA) ; "add ecx,edx" (138D4D8) -> "xor ecx,ecx" :
            # vie a 0 au premier coup, en Letal comme en Non letal.
            (0x138D4D8, bytes.fromhex("03ca898d14030000"), bytes.fromhex("31c9")),
        ],
        # Liquid Ocelot, combat final (2026-10-10) : au corps a corps dans les
        # deux modes. 11270E0 fait vie = max(vie - coup, plancher de phase)
        # (112717A) puis endurance = max(endurance - coup, plancher) (1127255) ;
        # les deux "sub" -> "xor" : vie et endurance au plancher au premier
        # coup, le suivant lance la phase suivante (transitions par le jeu).
        "liquid_final_kill": [
            (0x112717A, bytes.fromhex("2bd74963c84863c2"), bytes.fromhex("31d2")),
            (0x1127255, bytes.fromhex("2bd74863ce4863c2"), bytes.fromhex("31d2")),
        ],
        "no_alerts": [
            (0xB5FC0D, bytes.fromhex("3bf20f4cf23be90f4ce98bcb"), bytes.fromhex("3bf29090903be9909090")),
            (0xB5FC33, bytes.fromhex("418bd833c04503d2"), bytes.fromhex("909090")),
        ],
        # Pas de mal de dos (2026-10-17, valide en jeu). Deux animations :
        #  - apres une chute : la reception (A050C0, action speciale de Snake
        #    a composant joueur+0x1C10) choisit selon la hauteur (xmm6) :
        #    >= 13000 et >= 8000 (sous 11000) -> A05B20 (mal de dos, ~2 s) ;
        #    les deux "lea rax,[A05B20]" visent la reception normale A05490
        #    ([rbx+0x90], degats ou duree de la chute, inchange) ;
        #  - accroupi immobile : la mise a jour de l'etat accroupi (9DF1E0,
        #    etat principal a composant+0x1270) choisit 9DD440 (~3,5 s,
        #    interrompu en se relevant ou en bougeant) quand rien d'autre ne
        #    s'applique (9DFC6F) ; on saute l'affectation (jmp 9DFC7A), Snake
        #    reste accroupi.
        # Le compteur d'accroupissement (composant+0x270, fonction du stress
        # 971690) n'est PAS le declencheur (force a 19700 : rien). Aucun autre
        # reglage du trainer ne bloque le mal de dos (teste).
        "no_back_pain": [
            (0xA053EB, bytes.fromhex("488d052e070000eb6a"), bytes.fromhex("488d059e000000")),
            (0xA0543C, bytes.fromhex("488d05dd060000eb19"), bytes.fromhex("488d054d000000")),
            (0x9DFC6F, bytes.fromhex("488d05cad7ffff48894768"), bytes.fromhex("eb099090909090")),
        ],
        # Compte a rebours (2026-10-22, fuite de Metal Gear REX, acte 4) :
        # temps restant en ms a mgs4+23FAF6E0 (5:00 = 300000 ; seuils des
        # bips 20000..1000 testes en 14D49EC..). Tant que [23FAF6F4] (en
        # cours) est vrai, 14D4573 fait temps = max(temps - ecoule, 0) et
        # l'ecrit en 14D4596 ; ecriture en NOP -> le chrono reste fige,
        # il repart de la meme valeur une fois la case decochee.
        # Combat contre une Beauty (2026-10-22, salle blanche) : le chrono a
        # l'ecran n'est qu'une copie. Le combat a son propre compte a rebours,
        # un flottant en secondes a boss+0x4694 ; 116CCF0 le recopie dans
        # l'affichage (14D4DC0) puis 116CDE3 fait max(t - ecoule, 0) et
        # l'ecrit en 116CE05 (fin du combat a 0). Ecriture en NOP.
        "timer_freeze": [
            (0x14D4596, bytes.fromhex("890d44b1ad2239b3ac00"), bytes.fromhex("909090909090")),
            (0x116CE05, bytes.fromhex("f30f118b94460000f30f5ed0"), bytes.fromhex("0f1f840000000000")),
        ],
        "untouchable": [
            (0x96C0B0, bytes.fromhex("488bc455535657488d68a1"), bytes.fromhex("c3")),
            (0x136F5B6, bytes.fromhex("e805259dff4c8bf04885"), bytes.fromhex("31c00f1f00")),
        ],
        "invisible": [
            (0x89360, bytes.fromhex("48895c2408488974"), bytes.fromhex("0f57c0c3")),
            (0x89410, bytes.fromhex("4883ec28e8a71100"), bytes.fromhex("0f57c0c3")),
            # Lasers des mini Gekko (2026-10-10) : 11FC775 recupere ce que touche
            # le laser (11D48E0) ; si c'est Snake (je 11FC7A5), "Snake touche"
            # puis, s'il bouge, "cible reperee" (+0x1308 bit 0x40000) -> alerte.
            # "je" -> "jmp 11FC7D3" : le laser ne reconnait plus Snake.
            (0x11FC7A5, bytes.fromhex("740ae874540200"), bytes.fromhex("eb2c")),
            # Meme fonction, autre declencheur ([+0x838] bit 1, contact ou
            # proximite, Snake immobile au milieu d'eux) : "je" 11FC72E -> "jmp".
            (0x11FC72E, bytes.fromhex("7424838b10130000"), bytes.fromhex("eb24")),
            # Autres declencheurs de la meme fonction (le "!" quand Snake reste
            # immobile au milieu d'eux) : proximite (11FC2AE, 11FC2CE), contact
            # laser avec d'autres cibles du joueur (11FC7E3, 11FC807), drapeau de
            # contact 0x2000 (11FC857) -> tous sautes.
            (0x11FC2AE, bytes.fromhex("7212838b10130000"), bytes.fromhex("eb12")),
            (0x11FC2CE, bytes.fromhex("7712838b10130000"), bytes.fromhex("eb12")),
            (0x11FC7E3, bytes.fromhex("7512838b10130000"), bytes.fromhex("eb12")),
            (0x11FC807, bytes.fromhex("7512838b10130000"), bytes.fromhex("eb12")),
            (0x11FC857, bytes.fromhex("7307838b10130000"), bytes.fromhex("eb07")),
            # Tirs sans alerte (2026-10-11, valide en jeu) : les bruits vont dans
            # une table globale de 64 entrees (mgs4+1DA99F0, 0x40 octets : id,
            # duree, valeur, position, type, puissance) que les soldats parcourent
            # (875D0). 87750 l'alimente pour les tirs (position + origine) : il
            # sort aussitot, un tir ne fait plus passer en alerte. 87680 (chocs,
            # coups contre un mur, pas, sons d'animation via D3DEB0) reste actif :
            # le couper bloquait aussi le hold-up (le « Freeze » de Snake).
            (0x87750, bytes.fromhex("48895c241048896c2418"), bytes.fromhex("c3")),
        ] + [(rva, bytes.fromhex(original), bytes.fromhex("b801000000"))
             for rva, original in _STEALTH_CHECK_CALLS.items()],
    }

    def set_code_patch(self, name: str, enabled: bool) -> bool:
        """Applique ou retire tous les sites d'un patch ; rien n'est ecrit
        si un seul site ne correspond ni a l'original ni au patch."""
        if not (self.connected and self.sane):
            return False
        sites = []
        for rva, original, patch in self.CODE_PATCHES[name]:
            address = self.base + rva
            current = self.proc.read_bytes(address, len(original))
            patched = patch + original[len(patch):]
            if current not in (original, patched):
                return False
            sites.append((address, current, patched if enabled else original, len(patch)))
        for address, current, wanted, size in sites:
            if current != wanted:
                self.proc.write_bytes(address, wanted[:size])
        return True
