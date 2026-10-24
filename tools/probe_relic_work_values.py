"""Read-only inspection of four project-owned ESD work values in Nightreign.

No injection, remote execution, memory writes, currency changes, or save edits.
Only matching marker metadata is recorded, never arbitrary memory contents.
"""
import argparse
import ctypes
from ctypes import wintypes as W
import json
from pathlib import Path
import struct

from relic_presets import ROOT, load
from relic_launch import verify_package


class MBI(ctypes.Structure):
    _fields_=[("BaseAddress",ctypes.c_void_p),("AllocationBase",ctypes.c_void_p),
              ("AllocationProtect",W.DWORD),("PartitionId",W.WORD),
              ("RegionSize",ctypes.c_size_t),("State",W.DWORD),("Protect",W.DWORD),("Type",W.DWORD)]


def marker_matches(data, markers):
    """Identify layouts as observations, not as an authorized write contract."""
    for fmt in ("<i","<q","<f","<d"):
        parts=[struct.pack(fmt,value) for value in markers]
        # Floats cannot distinguish these consecutive large integers; reject
        # the ambiguous representation instead of reporting false precision.
        if len(set(parts))!=4:
            continue
        for stride in (4,8,16,24,32,64):
            if stride<len(parts[0]):
                continue
            pos=data.find(parts[0])
            while pos>=0:
                if all(data[pos+i*stride:pos+i*stride+len(part)]==part for i,part in enumerate(parts)):
                    yield pos,fmt,stride
                pos=data.find(parts[0],pos+1)


def scan(pid, expected_exe, markers, exact_only=False):
    k=ctypes.WinDLL("kernel32",use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.CloseHandle.argtypes=[W.HANDLE]
    k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
    k.VirtualQueryEx.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.POINTER(MBI),ctypes.c_size_t]
    k.VirtualQueryEx.restype=ctypes.c_size_t
    k.ReadProcessMemory.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
    handle=k.OpenProcess(0x0400|0x10,False,pid)  # QUERY_INFORMATION + VM_READ only
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    found=set();read_bytes=0;regions=0
    try:
        path=ctypes.create_unicode_buffer(32768);size=W.DWORD(len(path))
        if not k.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        if Path(path.value).resolve()!=Path(expected_exe).resolve():
            raise ValueError("PID does not identify the configured Nightreign executable")
        address=0
        while address<0x7FFFFFFF0000:
            region=MBI()
            if not k.VirtualQueryEx(handle,ctypes.c_void_p(address),ctypes.byref(region),ctypes.sizeof(region)):
                break
            base=region.BaseAddress or 0;length=region.RegionSize
            if not length or base+length<=address:
                raise ValueError("Non-progressing memory region")
            # Only committed writable private data. Do not read unrelated apps,
            # executable image sections, or mapped files.
            if region.State==0x1000 and region.Type==0x20000 and region.Protect in (0x04,0x08):
                regions+=1;offset=0;tail=b""
                while offset<length:
                    amount=min(1024*1024,length-offset)
                    buffer=ctypes.create_string_buffer(amount);got=ctypes.c_size_t()
                    ok=k.ReadProcessMemory(handle,ctypes.c_void_p(base+offset),buffer,amount,ctypes.byref(got))
                    if ok and got.value:
                        chunk=tail+buffer.raw[:got.value]
                        origin=base+offset-len(tail)
                        if exact_only:
                            needle=struct.pack("<4i",*markers)
                            position=chunk.find(needle)
                            while position>=0:
                                found.add((origin+position,"<i",4))
                                position=chunk.find(needle,position+1)
                        else:
                            for position,fmt,stride in marker_matches(chunk,markers):
                                found.add((origin+position,fmt,stride))
                        tail=chunk[-256:]
                        read_bytes+=got.value
                    else:
                        tail=b""
                    offset+=amount
            address=base+length
    finally:
        k.CloseHandle(handle)
    return dict(matches=[dict(address=hex(a),format=f,stride=s) for a,f,s in sorted(found)],
                bytes_read=read_bytes,private_regions=regions)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--pid",type=int,required=True)
    args=parser.parse_args()
    folder=Path(load(args.root/"local/runtime-probe-package.json")["path"])
    verify_package(folder,args.root)
    probe=load(folder/"runtime-probe.json")
    if probe["kind"]!="read_only_work_value_probe" or probe["runtime_write_enabled"]:
        raise ValueError("Unexpected probe configuration")
    game=Path(load(args.root/"local/runtime.json")["game"])/"nightreign.exe"
    result=scan(args.pid,game,probe["markers"])
    result.update(status="OBSERVATIONS_ONLY",pid=args.pid,runtime_write_enabled=False,
                  adapter_verified=False)
    (folder/"work-value-observation.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
