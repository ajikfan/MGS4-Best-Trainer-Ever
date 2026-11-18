"""Assemble le detour d'enregistrement des modeles de Snake (MODEL_LOAD_CODE
de mgs4trainer/live/equip.py). Keystone requis (pas le trainer : le code
est integre en hexadecimal, sans adresse du jeu).

Detour a l'entree de l'enregistrement des ressources (1.4.2 532220 :
rcx donnees, edx cle, r8d drapeaux, r9d taille). Pour une cle et une taille
de la table : drapeaux sans 0x10 (chargement de zone, le jeu convertit le
fichier sur place) -> copie neuve du modele de remplacement dans son tampon ;
avec 0x10 (cinematique : tampon deja converti, bit 31 sur la cle) -> le
meme tampon s'il a deja ete converti. Avant, les txn du modele absents sont
enregistres (copie neuve, nom de zone echange) s'il y a assez de places de
textures, sinon le jeu garde son modele.

Page (rdx de chaque champ) :
  +0x00 enregistrement (534600)   +0x08 recherche (534210)
  +0x10 reprise (532225)          +0x18 adresse du pointeur linkvarbuf
  +0x20 table des textures        +0x28 nom de zone sauve (16 octets)
  +0x38 nombre d'entrees          +0x3C actif
  +0x40 entrees de 0x40 : +0 cle (sans bit 31), +4 taille d'origine
        (0 = toute taille, cle sans bit 31 seulement : corps de la tenue
        chargee, jamais la version residente du paquet commun, 128 os,
        plantage 75FFDD quand elle etait remplacee, 2026-11-18),
        +8 taille du remplacement, +0xC converti, +0x10 tampon,
        +0x18 copie intacte, +0x20 liste des txn, +0x28 nombre de txn,
        +0x2C textures necessaires
  txn de 0x20 : +0 cle, +4 taille, +8 tampon, +0x10 copie intacte,
        +0x18 nom de sa zone (8 octets ; couches d'autres zones, 2026-11-16)
  +0x800 code (entree du detour)

    python tools/build_model_hook.py
"""
from keystone import KS_ARCH_X86, KS_MODE_64, Ks

PLACEHOLDER = 0x1122334455667788
TEXTURE_SLOTS, TEXTURE_ENTRY = 0x1421, 0x70
ZONE_FIRST, ZONE_SECOND = 0x34, 0x44

SOURCE = f"""
entry:
    push rbx
    push rsi
    push rdi
    push r12
    push r13
    push r14
    push r15
    push rbp
    push rcx
    push rdx
    push r8
    push r9
    sub rsp, 0x28
    movabs rbp, {PLACEHOLDER:#x}
    cmp dword ptr [rbp + 0x3c], 0
    je done
    mov eax, dword ptr [rsp + 0x38]
    and eax, 0x7fffffff
    lea rbx, [rbp + 0x40]
    mov ecx, dword ptr [rbp + 0x38]
find:
    test ecx, ecx
    jz done
    cmp eax, dword ptr [rbx]
    jne next_entry
    mov edx, dword ptr [rsp + 0x28]
    cmp dword ptr [rbx + 4], 0
    je any_size
    cmp edx, dword ptr [rbx + 4]
    je match
    jmp next_entry
any_size:
    test byte ptr [rsp + 0x3b], 0x80
    jz match
next_entry:
    add rbx, 0x40
    dec ecx
    jmp find
match:
    test byte ptr [rsp + 0x30], 0x10
    jnz reuse
    call textures
    test eax, eax
    jz done
    mov rdi, qword ptr [rbx + 0x10]
    mov rsi, qword ptr [rbx + 0x18]
    mov ecx, dword ptr [rbx + 8]
    rep movsb
    mov dword ptr [rbx + 0xc], 1
    jmp substitute
reuse:
    cmp dword ptr [rbx + 0xc], 0
    je done
    call textures
    test eax, eax
    jz done
substitute:
    mov rax, qword ptr [rbx + 0x10]
    mov qword ptr [rsp + 0x40], rax
    mov eax, dword ptr [rbx + 8]
    mov qword ptr [rsp + 0x28], rax
done:
    mov rax, qword ptr [rbp + 0x10]
    add rsp, 0x28
    pop r9
    pop r8
    pop rdx
    pop rcx
    pop rbp
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbx
    mov qword ptr [rsp + 0x18], rbx
    jmp rax

textures:
    sub rsp, 0x28
    mov r12d, dword ptr [rbx + 0x2c]
    test r12d, r12d
    jz tex_ok
    mov r8, qword ptr [rbp + 0x20]
    xor eax, eax
    mov ecx, 1
count_loop:
    cmp ecx, {TEXTURE_SLOTS:#x}
    jae count_end
    imul rdx, rcx, {TEXTURE_ENTRY:#x}
    cmp qword ptr [r8 + rdx + 8], 0
    jne count_next
    cmp word ptr [r8 + rdx + 0x34], 0xffff
    jne count_next
    inc eax
count_next:
    inc ecx
    jmp count_loop
count_end:
    cmp eax, r12d
    jb tex_fail
    mov rax, qword ptr [rbp + 0x18]
    mov rax, qword ptr [rax]
    mov rcx, qword ptr [rax + {ZONE_FIRST:#x}]
    mov qword ptr [rbp + 0x28], rcx
    mov rcx, qword ptr [rax + {ZONE_SECOND:#x}]
    mov qword ptr [rbp + 0x30], rcx
    mov r13, qword ptr [rbx + 0x20]
    mov r14d, dword ptr [rbx + 0x28]
txn_loop:
    test r14d, r14d
    jz txn_end
    mov ecx, dword ptr [r13]
    call qword ptr [rbp + 8]
    test rax, rax
    jnz txn_next
    mov rdi, qword ptr [r13 + 8]
    mov rsi, qword ptr [r13 + 0x10]
    mov ecx, dword ptr [r13 + 4]
    rep movsb
    mov rax, qword ptr [rbp + 0x18]
    mov rax, qword ptr [rax]
    mov rcx, qword ptr [r13 + 0x18]
    mov qword ptr [rax + {ZONE_FIRST:#x}], rcx
    mov qword ptr [rax + {ZONE_SECOND:#x}], rcx
    mov rcx, qword ptr [r13 + 8]
    mov edx, dword ptr [r13]
    mov r8d, 1
    mov r9d, dword ptr [r13 + 4]
    call qword ptr [rbp]
txn_next:
    add r13, 0x20
    dec r14d
    jmp txn_loop
txn_end:
    mov rax, qword ptr [rbp + 0x18]
    mov rax, qword ptr [rax]
    mov rcx, qword ptr [rbp + 0x28]
    mov qword ptr [rax + {ZONE_FIRST:#x}], rcx
    mov rcx, qword ptr [rbp + 0x30]
    mov qword ptr [rax + {ZONE_SECOND:#x}], rcx
tex_ok:
    mov eax, 1
    add rsp, 0x28
    ret
tex_fail:
    xor eax, eax
    add rsp, 0x28
    ret
"""


def main() -> None:
    code, _count = Ks(KS_ARCH_X86, KS_MODE_64).asm(SOURCE, 0x800)
    code = bytes(code)
    marker = PLACEHOLDER.to_bytes(8, "little")
    assert code.count(marker) == 1
    print(f"MODEL_LOAD_BASE_AT = {code.index(marker):#x}")
    for i in range(0, len(code), 32):
        print(f'        "{code[i:i + 32].hex()}"')


if __name__ == "__main__":
    main()
