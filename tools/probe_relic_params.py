"""Read-only verification of the local CT's NR param layout against our mod.

The AOB and numeric structure observations are reference facts, not executed CT
scripts. No third-party script code, remote calls or memory writes are used.
"""
import argparse
import ctypes
from ctypes import wintypes as W
import json
from pathlib import Path
import re
import struct

from relic_presets import ROOT, load
from relic_launch import verify_package
from probe_relic_work_values import MBI

PARAM_AOB = ("48 8B ? ? ? ? ? 48 85 ? 75 ? 48 8D ? ? ? ? ? E8 ? ? ? ? "
             "4C 8B ? 4C 8D ? ? ? ? ? BA ? ? ? ? 48 8D ? ? ? ? ? E8 ? ? ? ? "
             "48 8B ? ? ? ? ? 45 33 ? 41 8D ? ? E8 ? ? ? ? 48 85 ? 0F 84 ? ? ? ? "
             "48 8B ? ? ? ? ? 48 8B ? ? ? ? ? 48 8D ? ? ? ? ? 48 89 ? ? 48 89")


class ModuleInfo(ctypes.Structure):
    _fields_=[("base",ctypes.c_void_p),("size",W.DWORD),("entry",ctypes.c_void_p)]


class ReadOnlyGame:
    def __init__(self,pid,exe):
        self.k=ctypes.WinDLL("kernel32",use_last_error=True);k=self.k
        k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
        k.CloseHandle.argtypes=[W.HANDLE]
        k.ReadProcessMemory.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
        k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
        k.K32EnumProcessModulesEx.argtypes=[W.HANDLE,ctypes.c_void_p,W.DWORD,ctypes.POINTER(W.DWORD),W.DWORD]
        k.K32GetModuleInformation.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.POINTER(ModuleInfo),W.DWORD]
        k.VirtualQueryEx.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.POINTER(MBI),ctypes.c_size_t]
        k.VirtualQueryEx.restype=ctypes.c_size_t
        self.handle=k.OpenProcess(0x410,False,pid)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        path=ctypes.create_unicode_buffer(32768);size=W.DWORD(len(path))
        if not k.QueryFullProcessImageNameW(self.handle,0,path,ctypes.byref(size)) or Path(path.value).resolve()!=Path(exe).resolve():
            self.close();raise ValueError("Unexpected game executable")

    def close(self):
        if self.handle:self.k.CloseHandle(self.handle);self.handle=None

    def read(self,address,size):
        if not 0x10000<=address<0x7FFFFFFFFFFF or not 0<size<=32*1024*1024:
            raise ValueError("Invalid read bounds")
        buffer=ctypes.create_string_buffer(size);got=ctypes.c_size_t()
        if not self.k.ReadProcessMemory(self.handle,ctypes.c_void_p(address),buffer,size,ctypes.byref(got)) or got.value!=size:
            raise OSError("Incomplete game read")
        return buffer.raw

    def pointer(self,address):
        value=struct.unpack("<Q",self.read(address,8))[0]
        if not 0x10000<=value<0x7FFFFFFFFFFF:raise ValueError("Invalid native pointer")
        return value

    def main_module(self):
        modules=(ctypes.c_void_p*1024)();needed=W.DWORD()
        if not self.k.K32EnumProcessModulesEx(self.handle,modules,ctypes.sizeof(modules),ctypes.byref(needed),2):
            raise ctypes.WinError(ctypes.get_last_error())
        info=ModuleInfo()
        if not self.k.K32GetModuleInformation(self.handle,modules[0],ctypes.byref(info),ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return info.base,info.size

    def signature(self,pattern):
        raw=b"".join(b"." if x=="?" else re.escape(bytes([int(x,16)])) for x in pattern.split())
        regex=re.compile(raw,re.DOTALL)
        base,size=self.main_module();address=base;end=base+size;found=set();tail=b"";tail_end=None
        while address<end:
            region=MBI()
            if not self.k.VirtualQueryEx(self.handle,ctypes.c_void_p(address),ctypes.byref(region),ctypes.sizeof(region)):break
            stop=min(end,(region.BaseAddress or 0)+region.RegionSize)
            if stop<=address:raise ValueError("Non-progressing image region")
            if region.State==0x1000 and not (region.Protect & 0x101):
                while address<stop:
                    amount=min(1024*1024,stop-address)
                    try:chunk=self.read(address,amount)
                    except OSError:tail=b"";tail_end=None;address+=amount;continue
                    if tail_end!=address:tail=b""
                    combined=tail+chunk
                    found.update(address-len(tail)+m.start() for m in regex.finditer(combined))
                    tail=combined[-len(pattern.split()):];address+=amount;tail_end=address
            else:address=stop;tail=b"";tail_end=None
        if len(found)!=1:raise ValueError("Param repository AOB is not unique: "+str(len(found)))
        return next(iter(found))

    def param(self,wanted):
        match=self.signature(PARAM_AOB)
        code=self.read(match,7)
        if code[:2]!=b"\x48\x8b" or code[2]&0xc7!=5:
            raise ValueError("Not a RIP-relative 64-bit MOV")
        singleton=self.pointer(match+7+struct.unpack("<i",code[3:])[0])
        matches=[]
        for index in range(256):
            try:
                descriptor=self.pointer(singleton+0x88+index*72)
                text=self.pointer(descriptor+24)
                raw=self.read(text,128)
                name=raw.decode("utf-16-le",errors="strict").split("\0",1)[0]
                if name!=wanted:continue
                table=self.pointer(self.pointer(descriptor+0x80)+0x80)
                count=struct.unpack("<H",self.read(table+10,2))[0]
                if not 0<count<60000:raise ValueError("Implausible param row count")
                rows={}
                headers=self.read(table+64,count*24)
                for j in range(count):
                    row_id=struct.unpack_from("<i",headers,j*24)[0]
                    offset=struct.unpack_from("<Q",headers,j*24+8)[0]
                    if not count*24+64<=offset<32*1024*1024:
                        raise ValueError("Implausible param row offset")
                    if row_id in rows:raise ValueError("Duplicate ID in unique param table")
                    rows[row_id]=table+offset
                matches.append(dict(index=index,table=table,rows=rows))
            except (ValueError,OSError,UnicodeError):
                continue
        if len(matches)!=1:raise ValueError("Expected exactly one validated "+wanted+" table")
        return matches[0]


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--pid",type=int,required=True)
    args=parser.parse_args()
    folder=Path(load(args.root/"local/runtime-probe-package.json")["path"])
    verify_package(folder,args.root)
    plan=load(folder/"editor-plan.json")
    game=ReadOnlyGame(args.pid,Path(load(args.root/"local/runtime.json")["game"])/"nightreign.exe")
    try:
        table=game.param("EquipParamAntique")
        expected={p["relic_id"] for p in plan["products"]}
        if not expected.issubset(table["rows"]):raise ValueError("Probe product rows not loaded")
        report=dict(status="READ_ONLY_PARAM_LAYOUT_OBSERVED",pid=args.pid,
            repository_index=table["index"],table_address=hex(table["table"]),
            rows=len(table["rows"]),custom_rows_found=len(expected),
            sample_rows={str(i):hex(table["rows"][i]) for i in sorted(expected)[:4]},
            runtime_write_enabled=False,adapter_verified=False)
        (folder/"param-observation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2))
    finally:game.close()
