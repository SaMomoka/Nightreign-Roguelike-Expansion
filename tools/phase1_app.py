"""Windows workbench for actual native reward packages, without simulated gameplay."""
import copy
import json
import queue
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from phase1_rewards import ROOT, read_json, load_tables, compile_manifest
from phase1_package import build
from relic_launch import verify_package, launch

MODES = {
    "数值权重：保留原奖励类型": "weighted",
    "三选一研究：共用潜在力量池": "three_choices_probe",
    "分类三选一：生存 / 攻击 / 防御": "distinct_choices",
    "分层三选一：独立池 + 普通 / 稀有": "tiered_choices",
}


class Workbench:
    def __init__(self, window):
        self.window, self.folder = window, None
        self.events = queue.Queue()
        self.template = read_json(ROOT / "data/phase1_native_buffs.json")
        self.tables = load_tables(ROOT)
        self.busy = False
        window.title("NRE · 局内 Buff 配置")
        window.geometry("960x760")
        window.minsize(820, 700)
        outer = ttk.Frame(window, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="局内 Buff · 原生奖励实验", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(outer, text="配置奖励出现权重，保留原生效果数值。单人隔离实验；菜单、叠加和清理尚待实机验证。",
                  wraplength=880).pack(anchor="w", pady=(8,16))
        controls = ttk.Frame(outer)
        controls.pack(fill="x")
        ttk.Label(controls, text="实验模式").grid(row=0,column=0,sticky="w",padx=(0,12))
        self.mode = tk.StringVar(value=list(MODES)[2])
        ttk.Combobox(controls,textvariable=self.mode,values=list(MODES),state="readonly",width=46).grid(row=0,column=1,sticky="w")
        grid = ttk.LabelFrame(outer,text="候选权重（1–65535；其余原生候选保留原权重）",padding=12)
        grid.pack(fill="x",pady=16)
        self.weights = {}
        self.inputs = []
        for index, entry in enumerate(self.template["buffs"]):
            row, col = divmod(index, 2)
            ttk.Label(grid,text=entry["name"],width=14).grid(row=row,column=col*2,padx=(0,12),pady=6,sticky="w")
            var = tk.StringVar(value=str(entry["weight"]))
            self.weights[entry["id"]] = var
            widget = ttk.Spinbox(grid,from_=1,to=65535,textvariable=var,width=14)
            widget.grid(row=row,column=col*2+1,padx=(0,50),pady=6,sticky="w")
            self.inputs.append(widget)
        rarity=ttk.Frame(outer)
        rarity.pack(fill="x",pady=(0,10))
        self.rarity={}
        for key,label,default in (("normal","普通权重",75),("rare","稀有权重",25)):
            ttk.Label(rarity,text=label).pack(side="left",padx=(0,8))
            self.rarity[key]=tk.StringVar(value=str(default))
            ttk.Spinbox(rarity,from_=0,to=65535,textvariable=self.rarity[key],width=8).pack(side="left",padx=(0,20))
        ttk.Label(rarity,text="仅“分层三选一”使用；至少一档大于0").pack(side="left")
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        for text, callback in (("检查配置",self.preview),("保存预设",self.save),("载入预设",self.load),
                               ("打开已有实验包",self.open_package)):
            ttk.Button(buttons,text=text,command=lambda f=callback:self.guard(f)).pack(side="left",padx=(0,8))
        actions = ttk.Frame(outer)
        actions.pack(fill="x",pady=12)
        self.build_button = ttk.Button(actions,text="生成隔离实验包",command=lambda:self.guard(self.build))
        self.build_button.pack(side="left",padx=(0,8))
        self.run_button = ttk.Button(actions,text="启动：加载局内 Buff",state="disabled",command=lambda:self.guard(lambda:self.start(True)))
        self.run_button.pack(side="left",padx=(0,8))
        self.rollback_button = ttk.Button(actions,text="启动：无补丁对照",state="disabled",command=lambda:self.guard(lambda:self.start(False)))
        self.rollback_button.pack(side="left")
        self.status = tk.StringVar(value="就绪。实机验证暂缓，生成实验包不会自动启动游戏。")
        ttk.Label(outer,textvariable=self.status,wraplength=880).pack(anchor="w",pady=(0,8))
        ttk.Label(outer,text="每个包使用独立 NRE 副本。修改权重后请重新生成；启动按钮只加载当前已生成包。",
                  wraplength=880).pack(side="bottom",anchor="w",pady=(10,0))
        self.output = tk.Text(outer,wrap="word",height=10,font=("Microsoft YaHei UI",10),state="disabled")
        self.output.pack(fill="both",expand=True)
        self.preview()
        window.after(150,self.poll)

    def guard(self, callback):
        try:
            if self.busy:
                raise ValueError("正在构建，请等待完成。")
            callback()
        except Exception as error:
            messagebox.showerror("操作未完成",str(error),parent=self.window)

    def config(self):
        value=copy.deepcopy(self.template)
        for entry in value["buffs"]:
            text=self.weights[entry["id"]].get().strip()
            if not text.isdecimal():
                raise ValueError("权重必须是正整数："+entry["name"])
            entry["weight"]=int(text)
        value["rarity_weights"]={}
        for key,var in self.rarity.items():
            if not var.get().strip().isdecimal():raise ValueError("稀有度权重必须是非负整数")
            value["rarity_weights"][key]=int(var.get().strip())
        return value

    def show(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0","end")
        self.output.insert("1.0",text)
        self.output.configure(state="disabled")

    def preview(self):
        plan=compile_manifest(self.config(),self.tables,MODES[self.mode.get()])
        lines=["配置校验通过。",f"声明修改 {len(plan['changes'])} 个字段；不改原生效果数值。",
               "六项：生命 +10%、FP +10%、精力 +10%、物理攻击 +6%、物理/属性减伤 12%。"]
        if plan.get("additions"):
            lines[1]=f"新增 {len(plan['additions'])} 条原生模板副本，修改 {len(plan['changes'])} 处奖励引用；原有候选池不变。"
            lines[2]="含普通与稀有版原生效果；权重只影响出现比例，不改效果数值。"
            tiers=plan["rarity_weights"];total=sum(tiers.values())
            lines.append(f"每个候选的参数权重占比：普通 {tiers['normal']/total:.1%} / 稀有 {tiers['rare']/total:.1%}（非实测概率）。")
        if plan["choice_families"]:
            lines+=["候选池按生存、攻击、防御分开，物品及效果集合均不交叉。",
                    "原生池候选数："+ " / ".join(str(f["native_members"]) for f in plan["choice_families"])]
        else:
            lines+=["共用潜在力量池，不能保证同轮候选不重复。"]
        reference_count=sum(p["enemy_lot_reference_count"] for p in plan["reward_scope"]["before_patch"])
        lines += (["使用项目专用池；原有共享候选池保持不变。"] if plan.get("additions") else
                  [f"修改前，这些池有 {reference_count} 处敌人掉落表直接引用；共享池改权重会影响所有调用者。"])
        lines+=["\n边界：","• 三条奖励记录是否对应三个选项，仍需实机确认。",
                "• 不等同于按玩家动态权重、机制去重或可配置叠层上限。",
                "• 本模式每次运行需加载补丁；无补丁启动仅用于回滚对照。",
                "• 已生成包固定保存当时的配置，编辑框不会直接改变该包。"]
        self.show("\n".join(lines))

    def save(self):
        value=self.config()
        compile_manifest(value,self.tables,MODES[self.mode.get()])
        directory=ROOT/"local/phase1/presets"
        directory.mkdir(parents=True,exist_ok=True)
        path=filedialog.asksaveasfilename(parent=self.window,initialdir=str(directory),defaultextension=".json",
                                         filetypes=[("JSON预设","*.json")])
        if path:
            Path(path).write_text(json.dumps({"schema_version":1,"mode":MODES[self.mode.get()],
                                             "config":value},ensure_ascii=False,indent=2),encoding="utf-8")
            self.status.set("已保存预设："+Path(path).name)

    def load(self):
        path=filedialog.askopenfilename(parent=self.window,filetypes=[("JSON预设","*.json")])
        if path:
            preset=read_json(path)
            if preset.get("schema_version")!=1 or preset.get("mode") not in MODES.values():
                raise ValueError("不是受支持的局内 Buff 预设")
            self.apply_config(preset["config"],preset["mode"])
            self.status.set("已载入预设；需要重新生成才能应用。")

    def apply_config(self,config,mode):
        compile_manifest(config,self.tables,mode)
        for entry in config["buffs"]:
            self.weights[entry["id"]].set(str(entry["weight"]))
        for key,var in self.rarity.items():
            var.set(str(config.get("rarity_weights",{"normal":75,"rare":25})[key]))
        self.mode.set(next(k for k,v in MODES.items() if v==mode))
        self.preview()

    def set_package(self,folder):
        metadata=verify_package(folder)
        if metadata.get("kind")!="native_rewards":
            raise ValueError("请选择局内奖励实验包，不能载入遗物生成包")
        manifest=read_json(folder/"manifest.json")
        mode=manifest["experiment"].removeprefix("PHASE1-")
        if mode not in MODES.values():
            raise ValueError("未知实验模式")
        # Current packages carry a hashed configuration. Old packages reconstruct
        # only weights from their audited manifest, keeping the reviewed template.
        config=read_json(folder/"config.json") if "config.json" in metadata["sha256"] else copy.deepcopy(self.template)
        if "config.json" not in metadata["sha256"]:
            for change in manifest["changes"]:
                if change["table"]=="ItemTableParam" and change["field"]=="chanceWeight":
                    for entry in config["buffs"]:
                        if entry["goods_id"]==change["guard"]["itemId"]:entry["weight"]=change["after"]
        self.apply_config(config,mode)
        self.folder=folder
        self.run_button.configure(state="normal")
        self.rollback_button.configure(state="normal")
        self.status.set("当前实验包："+folder.name)

    def open_package(self):
        path=filedialog.askdirectory(parent=self.window,initialdir=str(ROOT/"local/packages"))
        if path:self.set_package(Path(path))

    def build(self):
        config=self.config()
        mode=MODES[self.mode.get()]
        compile_manifest(config,self.tables,mode)
        shell=shutil.which("pwsh")
        if not shell:raise ValueError("找不到 PowerShell7")
        self.busy=True
        self.build_button.configure(state="disabled")
        self.run_button.configure(state="disabled")
        self.rollback_button.configure(state="disabled")
        self.status.set("正在生成并回读全部参数，请稍候……")
        def work():
            try:self.events.put(("ok",build(ROOT,mode,shell,config)))
            except Exception as error:self.events.put(("error",str(error)))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            kind,result=self.events.get_nowait()
            self.busy=False
            self.build_button.configure(state="normal")
            if kind=="ok":self.guard(lambda:self.set_package(result))
            else:
                self.status.set("构建未通过，未启动游戏。")
                messagebox.showerror("构建失败",result,parent=self.window)
        except queue.Empty:pass
        self.window.after(150,self.poll)

    def start(self,enabled):
        result=launch(self.folder,enabled)
        self.status.set("已启动独立副本："+result["savefile"])


if __name__=="__main__":
    window=tk.Tk()
    try:
        Workbench(window)
    except Exception as error:
        window.withdraw()
        messagebox.showerror("无法启动局内 Buff 配置器",str(error))
        window.destroy()
    else:
        window.mainloop()
