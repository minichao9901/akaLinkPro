import os, re, subprocess, sys

SDK_ENV = os.environ.get("HPM_SDK_ENV_DIR", r"E:\sdk_env_v1.11.0")
TOOL = os.path.join(SDK_ENV, r"toolchains\rv32imac_zicsr_zifencei_multilib_b_ext-win\bin\riscv32-unknown-elf-")
ELF = sys.argv[1]

secs = subprocess.run([TOOL + "readelf.exe", "-S", "-W", ELF], capture_output=True, text=True).stdout
nm = subprocess.run([TOOL + "nm.exe", "-S", "--defined-only", ELF], capture_output=True, text=True).stdout
data = open(ELF, "rb").read()

sec_list = []
for line in secs.splitlines():
    m = re.match(r"\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)", line)
    if m:
        sec_list.append((m.group(1), int(m.group(3), 16), int(m.group(4), 16), int(m.group(5), 16)))

def read_at(addr, n):
    for _n, a, off, size in sec_list:
        if a <= addr and addr + n <= a + size:
            s = off + (addr - a)
            return data[s:s + n]
    return None

syms = {}
for line in nm.splitlines():
    p = line.split()
    if len(p) >= 4:
        try:
            syms[p[3]] = (int(p[0], 16), int(p[1], 16))
        except ValueError:
            pass

u16 = lambda b, o: b[o] | (b[o + 1] << 8)
u32 = lambda b, o: b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)
safe = lambda s: s.encode("ascii", "backslashreplace").decode()

addr, size = syms["USBD_WinUSBDescriptorSetDescriptor"]
ms = read_at(addr, size)
print("emitted MSOS 2.0 set: {} bytes".format(size))
problems = []

hdr_wl, hdr_ty = u16(ms, 0), u16(ms, 2)
set_total = u16(ms, 8)
print("set header: wLength={} type={} dwWindowsVersion=0x{:08X} wDescriptorSetTotalLength={}".format(
    hdr_wl, hdr_ty, u32(ms, 4), set_total))
if hdr_wl != 10:
    problems.append("set header wLength != 10")
if set_total != size:
    problems.append("wDescriptorSetTotalLength {} != emitted {}".format(set_total, size))

off = hdr_wl
while off < min(set_total, size):
    f_wl, f_ty = u16(ms, off), u16(ms, off + 2)
    if f_ty == 2:  # function subset header
        first_if, sub_len = ms[off + 4], u16(ms, off + 6)
        print("subset @{}: wLength={} bFirstInterface={} wSubsetLength={}".format(off, f_wl, first_if, sub_len))
        if f_wl != 8:
            problems.append("subset header wLength != 8")
        inner, end = off + f_wl, off + sub_len
        while inner < min(end, size):
            i_wl, i_ty = u16(ms, inner), u16(ms, inner + 2)
            if i_ty == 3:
                cid = ms[inner + 4:inner + 12].split(bytes([0]))[0].decode(errors="replace")
                scid = ms[inner + 12:inner + 20]
                print("  compat-id @{}: wLength={} CompatibleId={!r} SubCompatibleId={}".format(
                    inner, i_wl, cid, " ".join("{:02X}".format(x) for x in scid)))
                if i_wl != 20:
                    problems.append("compatible-id wLength != 20")
            elif i_ty == 4:
                dt, name_len = u16(ms, inner + 4), u16(ms, inner + 6)
                name_bytes = ms[inner + 8:inner + 8 + name_len]
                name = name_bytes.decode("utf-16-le", errors="replace").rstrip("\x00")
                dlen_off = inner + 8 + name_len
                dlen = u16(ms, dlen_off)
                pdata = ms[dlen_off + 2:dlen_off + 2 + dlen]
                pstr = pdata.decode("utf-16-le", errors="replace").rstrip("\x00")
                declared_end = inner + i_wl
                print("  property @{}: wLength={} type={} dataType={} nameLen={} name={!r}".format(
                    inner, i_wl, i_ty, dt, name_len, name))
                print("      wPropertyDataLength={} data={!r}".format(dlen, pstr))
                print("      declared feature end = {}   actual bytes available = {}".format(declared_end, size - inner))
                # a well-formed writer emits exactly: 8 + nameLen + 2 + dlen
                expect = 8 + name_len + 2 + dlen
                if i_wl != expect:
                    problems.append("property wLength {} != 8+nameLen({})+2+dataLen({}) = {}".format(i_wl, name_len, dlen, expect))
                if declared_end > size:
                    problems.append("property @{} declared end {} exceeds emitted {}".format(inner, declared_end, size))
                if not name.isprintable() or "DeviceInterfaceGUIDs" not in name:
                    problems.append("property name does not decode to 'DeviceInterfaceGUIDs' (got {!r})".format(name))
                if not re.fullmatch(r"\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}", pstr):
                    problems.append("property data does not decode to a valid GUID string (got {!r})".format(pstr))
                if len(pdata) != dlen:
                    problems.append("property data truncated: got {} of {}".format(len(pdata), dlen))
            else:
                print("  ? @{}: wLength={} type={}".format(inner, i_wl, i_ty))
            if i_wl == 0:
                break
            inner += i_wl
        if inner != end:
            problems.append("subset @{} walk ended at {} but wSubsetLength says {}".format(off, inner, end))
    else:
        print("? @{}: wLength={} type={}".format(off, f_wl, f_ty))
    if f_wl == 0:
        break
    off += f_wl

print()
if problems:
    print("PROBLEMS ({}):".format(len(problems)))
    for p in problems:
        print("  -", p)
else:
    print("OK: every declared length matches the emitted bytes; name and GUID decode cleanly.")
