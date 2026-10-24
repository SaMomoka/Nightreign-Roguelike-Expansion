"""Build isolated training test package on the verified full relic package."""
import argparse,json,shutil,struct,subprocess,sys,time,uuid
from datetime import datetime
from pathlib import Path
from relic_presets import ROOT,load
from relic_launch import verify_package,sha,launch
from training_buff_menu import compile_menu,catalog,FLAG
from training_buff_catalog import build_catalog

def event_plan():
    def instr(bank,op,fmt,*args):return dict(bank=bank,id=op,hex=struct.pack(fmt,*args).hex())
    return [instr(2003,66,'<B3xIB3x',0,FLAG,0),instr(3,0,'<bBBxI',0,1,0,FLAG),
            instr(2004,37,'<I',10000980),instr(2003,66,'<B3xIB3x',0,FLAG,0),instr(1000,4,'<B3x',1)]

def audit(plan):
    nodes={s['id']:s for s in plan['states']}
    if len(nodes)!=len(plan['states']):raise ValueError('Repeated state')
    done=set();active=set()
    def walk(n):
        if n==2:return
        if n not in nodes:raise ValueError('Missing state target')
        if nodes[n]['modal'] or n in done:return
        if n in active:raise ValueError('Menu busy cycle')
        active.add(n)
        for c in nodes[n]['conditions']:walk(c['target'])
        active.remove(n);done.add(n)
    for n,s in nodes.items():
        for c in s['conditions']:
            if c['target']!=2 and c['target'] not in nodes:raise ValueError('Missing target')
        walk(n)
    return dict(graph_checked=True,states=len(nodes))

def build(root,shell):
    source=Path(load(root/'local/full-relic-package.json')['path']);meta=verify_package(source,root)
    if meta['kind']!='full_relic_editor':raise ValueError('Expected full editor source')
    folder=root/'local/packages'/('training_buffs_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]);folder.mkdir()
    for relative in meta['sha256']:
        p=folder/relative;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/relative,p)
    native_catalog=build_catalog(root)
    plan=compile_menu(catalog(load(root/'data/phase1_native_buffs.json'),native_catalog['entries']))
    plan['catalog_audit']=native_catalog['audit']
    plan.update(event_instructions=event_plan(),event_init=struct.pack('<iII',0,FLAG,0).hex(),audit=audit(plan))
    (folder/'training-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    result=subprocess.run([shell,'-NoProfile','-File',str(root/'tools/build_training_buffs.ps1'),'-Package',str(folder),'-ProjectRoot',str(root)],capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (folder/'training-build.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode:raise ValueError('Build rejected: '+str(folder/'training-build.log'))
    save='NRE_'+folder.name+'.sl2'
    for n in ('generate.me3','play.me3'):
        p=folder/n;p.write_text(p.read_text(encoding='utf-8').replace(meta['savefile'],save),encoding='utf-8')
    manifest=load(folder/'manifest.json');manifest.update(training_test=True,training_game_verified=False,training_source=source.name)
    manifest['limitations']+=['Training drop generation, repeat generation and buff cleanup require game testing.','Training selector does not change expedition boss rewards.']
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    files=set(meta['sha256'])|{'training-plan.json','training-layout.json','training-build-report.json','mod/map/mapstudio/m10_00_00_00.msb.dcx','mod/event/m10_00_00_00.emevd.dcx'}
    meta.update(savefile=save,training_extension=True,sha256={n:sha(folder/n) for n in sorted(files)},training_tool_hashes={n:sha(root/'tools'/n) for n in ('training_buff_menu.py','training_buff_runtime.py','numeric_reward.py')})
    (folder/'package.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');verify_package(folder,root)
    (root/'local/training-package.json').write_text(json.dumps(dict(path=str(folder)),ensure_ascii=False),encoding='utf-8')
    return folder

def start(root):
    folder=Path(load(root/'local/training-package.json')['path']);meta=verify_package(folder,root)
    if not meta.get('training_extension'):raise ValueError('Not a training package')
    for n,h in meta['training_tool_hashes'].items():
        if sha(root/'tools'/n)!=h:raise ValueError('Rebuild training code first')
    started=time.time();game=launch(folder,True,root);pids=[]
    for script,log in (('relic_runtime.py','runtime.log'),('training_buff_runtime.py','training-runtime.log')):
        with (folder/log).open('ab') as f:
            p=subprocess.Popen([sys.executable,str(root/'tools'/script),'--root',str(root),'--package',str(folder),'--launched-after',str(started)],stdout=f,stderr=f,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));pids.append(p.pid)
    return dict(game=game,helpers=pids)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=('build','launch'));p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--pwsh',default=shutil.which('pwsh'));a=p.parse_args()
    print(build(a.root,a.pwsh) if a.action=='build' else start(a.root))
