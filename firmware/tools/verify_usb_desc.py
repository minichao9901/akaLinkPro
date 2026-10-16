import os, re, subprocess, sys

SDK_ENV = os.environ.get("HPM_SDK_ENV_DIR", r"E:\sdk_env_v1.11.0")
TOOL = os.path.join(SDK_ENV, r"toolchains\rv32imac_zicsr_zifencei_multilib_b_ext-win\bin\riscv32-unknown-elf-")
ELF = sys.argv[1]

secs = subprocess.run([TOOL + "readelf.exe", "-S", "-W", ELF], capture_output=True, text=True).stdout
syms = subprocess.run([TOOL + "nm.exe", "-S", "--defined-only", ELF], capture_output=True, text=True).stdout
data = open(ELF, "rb").read()

sec_list = []
for line in secs.splitlines():
    m = re.match(r"\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)", line)
    if m:
        sec_list.append((m.group(1), int(m.group(3), 16), int(m.group(4), 16), int(m.group(5), 16)))

def read_at(addr, n):
    for name, a, off, size in sec_list:
        if a <= addr and addr + n <= a + size:
            s = off + (addr - a)
            return data[s:s + n]
    return None

symtab = {}
for line in syms.splitlines():
    p = line.split()
    if len(p) >= 4:
        try:
            symtab[p[3]] = (int(p[0], 16), int(p[1], 16))
        except ValueError:
            pass

def dump(name):
    if name not in symtab:
        print(f"[sym] {name}: NOT FOUND")
        return None
    addr, size = symtab[name]
    b = read_at(addr, size)
    print(f"[sym] {name}: addr=0x{addr:08X} size={size} (0x{size:X})")
    return b

def hx(b):
    return " ".join(f"{x:02X}" for x in b)

print("=== 1. symbol sizes ===")
for n in ("config_descriptor", "other_speed_config_descriptor", "device_descriptor",
          "USBD_WinUSBDescriptorSetDescriptor", "USBD_BinaryObjectStoreDescriptor",
          "USBD_WebUSBURLDescriptor", "hid_custom_report_desc"):
    dump(n)

print("\n=== 2. config descriptor chain walk ===")
cfg = read_at(symtab["config_descriptor"][0], symtab["config_descriptor"][1])
if cfg:
    wTotal = cfg[2] | (cfg[3] << 8)
    print(f"bLength={cfg[0]} bDescriptorType={cfg[1]} wTotalLength={wTotal} (symbol size={len(cfg)}) -> {'MATCH' if wTotal == len(cfg) else 'MISMATCH'}")
    print(f"bNumInterfaces={cfg[4]} bConfigurationValue={cfg[5]} iConfiguration={cfg[6]} bmAttributes=0x{cfg[7]:02X} bMaxPower={cfg[8] * 2}mA")
    off, total, intf, eps = 0, 0, [], []
    while off < len(cfg) and cfg[off]:
        ln, ty = cfg[off], cfg[off + 1]
        if ln == 0:
            break
        total += ln
        if ty == 0x02:
            print(f"  @{off:3d} bLength={ln} CONFIGURATION wTotalLength={cfg[off+2] | (cfg[off+3] << 8)} bNumInterfaces={cfg[off+4]}")
        elif ty == 0x04:
            print(f"  @{off:3d} bLength={ln} INTERFACE  num={cfg[off+2]} alt={cfg[off+3]} eps={cfg[off+4]} class=0x{cfg[off+5]:02X} sub=0x{cfg[off+6]:02X} proto=0x{cfg[off+7]:02X} iIntf={cfg[off+8]}")
            intf.append(cfg[off + 2])
        elif ty == 0x05:
            mps = cfg[off + 4] | (cfg[off + 5] << 8)
            print(f"  @{off:3d} bLength={ln} ENDPOINT   addr=0x{cfg[off+2]:02X} attr=0x{cfg[off+3]:02X} mps={mps} interval={cfg[off+6]}")
            eps.append(cfg[off + 2])
        elif ty == 0x0B:
            print(f"  @{off:3d} bLength={ln} IAD        first={cfg[off+2]} count={cfg[off+3]} class=0x{cfg[off+4]:02X} sub=0x{cfg[off+5]:02X} proto=0x{cfg[off+6]:02X}")
        elif ty == 0x24:
            print(f"  @{off:3d} bLength={ln} CS_INTERFACE subtype=0x{cfg[off+2]:02X}")
        elif ty == 0x21:
            print(f"  @{off:3d} bLength={ln} DFU_FUNCTIONAL  <-- should NOT exist")
        else:
            print(f"  @{off:3d} bLength={ln} type=0x{ty:02X} raw=[{hx(cfg[off:off+ln])}]")
        off += ln
    print(f"  chain total = {total} -> {'OK' if total == len(cfg) else 'MISMATCH'}")
    print(f"  interfaces = {intf}, endpoints = {[hex(e) for e in eps]}")

print("\n=== 3. MSOS 2.0 set + BOS ===")
ms = read_at(symtab["USBD_WinUSBDescriptorSetDescriptor"][0], symtab["USBD_WinUSBDescriptorSetDescriptor"][1])
if ms:
    print(f"wLength={ms[0] | (ms[1] << 8)} wDescriptorType={ms[2] | (ms[3] << 8)} dwWindowsVersion={hx(ms[4:8])}")
    print(f"wDescriptorSetTotalLength={ms[8] | (ms[9] << 8)} (symbol size={len(ms)}) -> {'MATCH' if (ms[8] | (ms[9] << 8)) == len(ms) else 'MISMATCH'}")
    wSub = ms[16] | (ms[17] << 8)
    print(f"subset: wLength={ms[10] | (ms[11] << 8)} type={ms[12] | (ms[13] << 8)} bFirstInterface={ms[14]} wSubsetLength={wSub}")
    cid = ms[22:30].split(b"\x00")[0].decode(errors="replace")
    print(f"CompatibleId={cid!r}  SubCompatibleId={hx(ms[30:38])}")
    print(f"guid property raw tail = {hx(ms[-12:])}")
bos = read_at(symtab["USBD_BinaryObjectStoreDescriptor"][0], symtab["USBD_BinaryObjectStoreDescriptor"][1])
if bos:
    print(f"BOS bLength={bos[0]} type={bos[1]} wTotalLength={bos[2] | (bos[3] << 8)} bNumDeviceCaps={bos[4]} (symbol size={len(bos)})")
    cap_uuid = hx(bos[9:25])
    print(f"cap bLength={bos[5]} bDescriptorType=0x{bos[6]:02X} bDevCapabilityType={bos[7]} uuid={cap_uuid}")
    known = {
        "d8dd60df-4589-4cc7-9cd2-659d9e648a9f": "MS OS 2.0 (WinUSB)",
        "3408b638-09a9-47a0-8bfd-a0768815b665": "WebUSB  <-- should NOT exist",
    }
    u = cap_uuid.split()
    g = f"{u[3]}{u[2]}{u[1]}{u[0]}-{u[5]}{u[4]}-{u[7]}{u[6]}-{u[8]}{u[9]}-{''.join(u[10:16])}"
    print(f"uuid decoded = {g}  -> {known.get(g, 'unknown')}")
