import sys
sys.path.insert(0, r"D:\Documents\GitHub\MGS4-Trainer")
from mgs4trainer.core.winproc import *
import mgs4trainer.core.winproc as w
from mgs4trainer.live import MGS4Live
l = MGS4Live(); print("attach", l.attach(), "base", hex(l.base))
out = bytearray()
for off in range(0x1000, 0x1801000, 0x10000):
    try: out += l.proc.read_bytes(l.base + off, 0x10000)
    except OSError: out += bytes(0x10000)
open("1.4.2/image_rva1000.bin", "wb").write(out)
print(len(out), out[:16].hex())
