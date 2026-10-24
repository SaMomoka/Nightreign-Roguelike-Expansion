"""Headless native-menu adapter; writes only three owned deterministic pool rows."""
import argparse,ctypes,json,struct,time
from pathlib import Path
from ctypes import wintypes as W
from probe_relic_params import ReadOnlyGame,PARAM_AOB
from probe_relic_work_values import scan,MBI
from relic_runtime import created_at,game_pid
from relic_presets import load
from relic_launch import verify_package,sha
from training_buff_menu import MAGIC,MARKERS,POOL_IDS,encode_pool

class TrainingGame(ReadOnlyGame):
    def __init__(self,pid,exe,layout,allowed):
        super().__init__(pid,exe);self.close()
        self.handle=self.k.OpenProcess(0x438,False,pid)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        self.k.WriteProcessMemory.argtypes=[W.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
        self.allowed=frozenset(allowed);self.layout={x['id']:x for x in layout};self.addresses={};self.last={};self.mailbox=None
        if set(self.layout)!=set(POOL_IDS):raise ValueError('Wrong owned pools')
    def write(self,address,old,new,mailbox_snapshot=None):
        response=address==self.mailbox+12 and len(new)==4
        if not (response or address in self.addresses.values() and len(new)==36):raise ValueError('Outside owned data')
        region=MBI()
        if not self.k.VirtualQueryEx(self.handle,ctypes.c_void_p(address),ctypes.byref(region),ctypes.sizeof(region)):raise OSError('Missing region')
        if (region.State,region.Type,region.Protect)!=(0x1000,0x20000,4) or address+len(new)>(region.BaseAddress or 0)+region.RegionSize:raise ValueError('Changed region')
        if self.read(address,len(old))!=old:raise ValueError('Data changed before write')
        written=ctypes.c_size_t();buf=ctypes.create_string_buffer(new)
        if not self.k.WriteProcessMemory(self.handle,address,buf,len(new),ctypes.byref(written)) or written.value!=len(new):raise OSError('Write incomplete')
        if self.read(address,len(new))!=new:
            current=self.read(self.mailbox,16) if response else None
            if not consumed_response(mailbox_snapshot,current):raise OSError('Owned data readback failed')
    def respond(self,snapshot,value):
        if self.read(self.mailbox,16)!=snapshot:raise ValueError('Request changed')
        self.write(self.mailbox+12,snapshot[12:],struct.pack('<i',value),snapshot)
    def prepare(self,goods):
        table=self.training_param();self.addresses={i:table['rows'].get(i) for i in POOL_IDS}
        if any(a is None for a in self.addresses.values()):raise ValueError('Training pools not loaded')
        changes=[]
        for i,g in zip(POOL_IDS,goods):
            r=self.layout[i];old=self.read(self.addresses[i],36);original=bytes.fromhex(r['initial_hex'])
            if old not in (original,self.last.get(i)):raise ValueError('Training pool modified elsewhere')
            changes.append((i,old,encode_pool(original,r['item_offset'],g,self.allowed)))
        for i,old,new in changes:self.write(self.addresses[i],old,new);self.last[i]=new

    def training_param(self):
        match=self.signature(PARAM_AOB);code=self.read(match,7)
        if code[:2]!=b'\x48\x8b' or code[2]&0xc7!=5:raise ValueError('Changed repository signature')
        singleton=self.pointer(match+7+struct.unpack('<i',code[3:])[0]);matches=[]
        for index in range(256):
            try:
                descriptor=self.pointer(singleton+0x88+index*72)
                name=self.read(self.pointer(descriptor+24),128).decode('utf-16-le').split('\0',1)[0]
                if name!='ItemTableParam':continue
                table=self.pointer(self.pointer(descriptor+0x80)+0x80)
                count=struct.unpack('<H',self.read(table+10,2))[0]
                if not 0<count<60000:raise ValueError('Invalid pool count')
                headers=self.read(table+64,count*24);rows={}
                for j in range(count):
                    rid=struct.unpack_from('<i',headers,j*24)[0]
                    if rid not in POOL_IDS:continue  # Native pools legitimately repeat IDs.
                    offset=struct.unpack_from('<Q',headers,j*24+8)[0]
                    if rid in rows or not count*24+64<=offset<32*1024*1024:raise ValueError('Ambiguous owned pool')
                    rows[rid]=table+offset
                if set(rows)!=set(POOL_IDS):raise ValueError('Missing owned pools')
                matches.append(dict(rows=rows))
            except (ValueError,OSError,UnicodeError):continue
        if len(matches)!=1:raise ValueError('Expected one validated owned pool table')
        return matches[0]

def consumed_response(before,after):
    if before is None or after is None or len(before)!=16 or len(after)!=16:return False
    a=struct.unpack('<4i',before);b=struct.unpack('<4i',after)
    # Native ESD consumes the reply before clearing it for a different valid request.
    return a[0]==b[0]==MAGIC and b[3]==0 and b[1] in (10,11,12,100,101,102,200) and a[1:3]!=b[1:3]

def run(root,folder,launched_after):
    meta=verify_package(folder,root)
    for n,h in meta['training_tool_hashes'].items():
        if sha(root/'tools'/n)!=h:raise ValueError('Rebuild training package after code changes')
    plan=load(folder/'training-plan.json');layout=load(folder/'training-layout.json')
    deadline=time.monotonic()+120
    while not game_pid() and time.monotonic()<deadline:time.sleep(1)
    pid=game_pid()
    if not pid:raise ValueError('Game did not start')
    exe=Path(load(root/'local/runtime.json')['game'])/'nightreign.exe';game=TrainingGame(pid,exe,layout,[e['goods_id'] for e in plan['entries']])
    try:
        if created_at(game)<launched_after-2:raise ValueError('Game predates launch')
        log=folder/'generate-launch.log'
        while True:
            content=log.read_text(encoding='utf-8',errors='replace') if log.exists() else ''
            if meta['savefile'] in content and str(folder) in content:break
            if game_pid()!=pid:raise ValueError('Game exited');
            time.sleep(1)
        print(json.dumps(dict(event='waiting_for_training_menu',pid=pid)),flush=True)
        while game_pid()==pid:
            found=scan(pid,exe,MARKERS,exact_only=True)['matches']
            if len(found)>1:raise ValueError('Ambiguous training mailbox')
            if found:game.mailbox=int(found[0]['address'],16);break
            time.sleep(2)
        if game.mailbox is None:return
        selected=[0,1,2]
        while game_pid()==pid:
            snapshot=game.read(game.mailbox,16);v=struct.unpack('<4i',snapshot)
            if v==MARKERS:game.respond(snapshot,1)
            elif v[0]==MAGIC and v[3]==0 and v[1]!=0:
                op,payload=v[1:3];reply=-1
                if op in (10,11,12):reply=plan['labels'][f'{op-10}:{selected[op-10]}']
                elif op in (100,101,102) and 0<=payload<len(plan['entries']):selected[op-100]=payload;reply=1
                elif op==200:
                    goods=[plan['entries'][i]['goods_id'] for i in selected]
                    game.prepare(goods);reply=1
                    print(json.dumps(dict(event='training_reward_prepared',goods=goods)),flush=True)
                game.respond(snapshot,reply)
            time.sleep(.02)
    finally:game.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--package',type=Path,required=True);p.add_argument('--launched-after',type=float,required=True);a=p.parse_args()
    run(a.root,a.package,a.launched_after)
