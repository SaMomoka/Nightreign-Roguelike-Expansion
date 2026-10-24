"""Headless adapter: native menu requests -> owned relic rows -> native shop.

The adapter does not debit currency, grant inventory, execute remote code or
edit saves. Native ESD and shop code own all player interaction and purchases.
"""
import argparse
import csv
import ctypes
from ctypes import wintypes as W
import io
import json
from pathlib import Path
import struct
import subprocess
import time

from full_relic_menu import MARKERS,MAGIC,SHOP_BASE
from relic_presets import ROOT,load
from relic_launch import verify_package
from relic_selection import RelicSelection
from relic_filters import EDITORS, product_index
from probe_relic_work_values import scan,MBI
from probe_relic_params import ReadOnlyGame


def row_bytes(original,offsets,bundles,entries):
    if len(original)!=48 or offsets!=[16,20,24,32,36,40] or len(bundles)!=3:
        raise ValueError("Unverified native row layout")
    values=[]
    for polarity in ("effect_id","curse_id"):
        for b in bundles:
            effect=b[polarity]
            value=-1 if effect is None else entries[effect]["deterministic_pool"]
            if type(value) is not int or (polarity=="effect_id" and value<0):
                raise ValueError("Missing deterministic effect pool")
            values.append(value)
    result=bytearray(original)
    for offset,value in zip(offsets,values):struct.pack_into("<i",result,offset,value)
    return bytes(result)


class OwnedGame(ReadOnlyGame):
    def __init__(self,pid,exe,layout):
        super().__init__(pid,exe)
        self.close()
        self.handle=self.k.OpenProcess(0x438,False,pid) # query/read/write/VM_OPERATION; no thread rights
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        self.k.WriteProcessMemory.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
        self.layout={r["id"]:r for r in layout["rows"]}
        if set(self.layout)!=set(range(9000000,9000008)):
            self.close();raise ValueError("Unapproved runtime row set")
        self.row_addresses={};self.last_written={};self.mailbox=None

    def guarded_write(self,address,expected,value):
        allowed=(self.mailbox is not None and address==self.mailbox+12 and len(value)==4)
        allowed=allowed or (address in self.row_addresses.values() and len(value)==48)
        if not allowed or len(expected)!=len(value):raise ValueError("Write outside owned regions")
        region=MBI()
        if not self.k.VirtualQueryEx(self.handle,ctypes.c_void_p(address),ctypes.byref(region),ctypes.sizeof(region)):
            raise OSError("Missing writable region")
        if region.State!=0x1000 or region.Type!=0x20000 or region.Protect!=0x04 or address+len(value)>(region.BaseAddress or 0)+region.RegionSize:
            raise ValueError("Owned region layout changed")
        if self.read(address,len(expected))!=expected:raise ValueError("Runtime value changed before write")
        buffer=ctypes.create_string_buffer(value);written=ctypes.c_size_t()
        if not self.k.WriteProcessMemory(self.handle,ctypes.c_void_p(address),buffer,len(value),ctypes.byref(written)) or written.value!=len(value):
            raise OSError("Incomplete owned-data write")
        if self.read(address,len(value))!=value:raise OSError("Owned-data write readback failed")

    def prepare(self,editor,request,entries):
        index=product_index(editor,request['color'])
        table=self.param("EquipParamAntique")  # Re-resolve after potential map/resource changes.
        addresses={i:table["rows"].get(i) for i in self.layout}
        if any(a is None for a in addresses.values()):raise ValueError("Full editor rows not loaded")
        for i,address in addresses.items():
            current=self.read(address,48);original=bytes.fromhex(self.layout[i]["initial_hex"])
            if current not in (original,self.last_written.get(i)):
                raise ValueError("Another mod or reload changed an owned row")
        self.row_addresses=addresses
        row_id=9000000+index;row=self.layout[row_id];address=addresses[row_id]
        original=bytes.fromhex(row["initial_hex"]);current=self.read(address,48)
        value=row_bytes(original,row["field_offsets"],request["bundles"],entries)
        self.guarded_write(address,current,value)
        self.last_written[row_id]=value
        return SHOP_BASE+index

    def respond(self,snapshot,value):
        if self.mailbox is None or len(snapshot)!=16 or struct.unpack_from("<i",snapshot)[0]!=MAGIC:
            raise ValueError("No owned mailbox")
        if self.read(self.mailbox,16)!=snapshot:raise ValueError("Native request changed")
        self.guarded_write(self.mailbox+12,snapshot[12:],struct.pack("<i",value))


class Dispatcher:
    def __init__(self,catalog,plan,prepare):
        self.model=RelicSelection(catalog);self.labels=plan["labels"];self.prepare=prepare
        self.color_labels=plan['color_labels']

    def dispatch(self,operation,payload):
        if operation in (600,602):
            self.model.choose_color(operation-600,payload);return 1
        if operation in (700,702):
            return self.color_labels[str(self.model.colors[operation-700])]
        if 100<=operation<112:
            editor,slot=divmod(operation-100,3)
            b=self.model.drafts[editor][slot]
            key=f"{self.model.kind(editor)}:{slot}:{b['effect_id'] or 0}:{b['curse_id'] or 0}"
            return self.labels[key]
        if 200<=operation<212:
            editor,slot=divmod(operation-200,3)
            route=self.model.choose_positive(editor,slot,payload)
            return 2 if route=="choose_negative" else 1
        if 300<=operation<312:
            editor,slot=divmod(operation-300,3)
            pending=self.model.pending
            if pending is None or (pending["editor"],pending["slot"])!=(editor,slot):
                raise ValueError("Negative response belongs to another slot")
            self.model.choose_negative(payload);return 1
        if operation==400:
            self.model.cancel_negative();return 1
        if operation in (500,502):
            editor=operation-500;request=self.model.request(editor)
            shop=self.prepare(editor,request,self.model.entries)
            if shop!=SHOP_BASE+product_index(editor,request['color']):raise ValueError("Wrong prepared shop")
            return self.model.verify_ack(dict(request,shop_id=shop,runtime_verified=True))
        raise ValueError("Unknown native request operation")


def game_pid():
    result=subprocess.run(["tasklist","/FI","IMAGENAME eq nightreign.exe","/FO","CSV","/NH"],
        capture_output=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    rows=list(csv.reader(io.StringIO(result.stdout.decode(errors="replace"))))
    ids=[int(r[1]) for r in rows if len(r)>1 and r[0].lower()=="nightreign.exe"]
    if len(ids)>1:raise ValueError("Multiple game processes")
    return ids[0] if ids else None


def created_at(game):
    game.k.GetProcessTimes.argtypes=[W.HANDLE,ctypes.POINTER(W.FILETIME),ctypes.POINTER(W.FILETIME),
                                  ctypes.POINTER(W.FILETIME),ctypes.POINTER(W.FILETIME)]
    values=[W.FILETIME() for _ in range(4)]
    if not game.k.GetProcessTimes(game.handle,*[ctypes.byref(v) for v in values]):
        raise ctypes.WinError(ctypes.get_last_error())
    return ((values[0].dwHighDateTime<<32)|values[0].dwLowDateTime)/10000000-11644473600


def run(root,folder,launched_after):
    metadata=verify_package(folder,root)
    if metadata["kind"]!="full_relic_editor":raise ValueError("Wrong runtime package")
    catalog=load(folder/"runtime-catalog.json");plan=load(folder/"full-menu-plan.json")
    layout=load(folder/"runtime-layout.json")
    exe=Path(load(root/"local/runtime.json")["game"])/"nightreign.exe"
    deadline=time.monotonic()+120
    pid=None
    while time.monotonic()<deadline:
        pid=game_pid()
        if pid:break
        time.sleep(1)
    if not pid:raise ValueError("Game did not start")
    game=OwnedGame(pid,exe,layout)
    try:
        if created_at(game)<launched_after-2:raise ValueError("Game predates this isolated launch")
        # The verified launcher profile is the sole way this helper is started.
        # Confirm ME3 actually intercepted this package's isolated save before
        # permitting any response or parameter write.
        log=folder/"generate-launch.log"
        while True:
            content=log.read_text(encoding="utf-8",errors="replace") if log.exists() else ""
            if metadata["savefile"] in content and str(folder) in content:break
            if game_pid()!=pid:raise ValueError("Game exited while waiting for isolated save")
            time.sleep(1)
        dispatcher=Dispatcher(catalog,plan,game.prepare)
        print(json.dumps(dict(event="waiting_for_native_menu",pid=pid)),flush=True)
        while game_pid()==pid:
            observed=scan(pid,exe,MARKERS,exact_only=True)
            if len(observed["matches"])==1:
                game.mailbox=int(observed["matches"][0]["address"],16)
                break
            if len(observed["matches"])>1:raise ValueError("Native mailbox is ambiguous")
            time.sleep(2)
        if game.mailbox is None:return
        print(json.dumps(dict(event="mailbox_bound",address=hex(game.mailbox))),flush=True)
        while True:
            snapshot=game.read(game.mailbox,16)
            values=struct.unpack("<4i",snapshot)
            if values==MARKERS:
                if dispatcher.model.pending:dispatcher.model.cancel_negative()
                game.respond(snapshot,1)
                print(json.dumps(dict(event="native_menu_ready")),flush=True)
            elif values[0]==MAGIC and values[3]==0 and values[1]!=0:
                try:
                    result=dispatcher.dispatch(values[1],values[2])
                except ValueError as exc:
                    print(json.dumps(dict(event="selection_rejected",reason=str(exc))),flush=True)
                    result=-1
                game.respond(snapshot,result)
                print(json.dumps(dict(event="request",operation=values[1],payload=values[2],response=result)),flush=True)
            time.sleep(0.02)
    finally:game.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--package",type=Path,required=True)
    parser.add_argument("--launched-after",type=float,required=True)
    args=parser.parse_args()
    try:run(args.root,args.package,args.launched_after)
    except (ValueError,OSError) as exc:
        print(json.dumps(dict(event="adapter_stopped",reason=str(exc))),flush=True)
        raise
