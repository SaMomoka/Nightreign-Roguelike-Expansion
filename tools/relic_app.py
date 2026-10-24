"""Local Windows preset editor; no network service or save editing."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import json
import threading
import queue
import re


def label(effect):
    name=effect["Name"]
    attributes={"Vigor":"生命力","Mind":"集中力","Endurance":"耐力","Strength":"力气",
                "Dexterity":"灵巧","Intelligence":"智力","Faith":"信仰","Arcane":"感应"}
    match=re.search(r"\b(Vigor|Mind|Endurance|Strength|Dexterity|Intelligence|Faith|Arcane) \+(\d+)$",name)
    if match:
        return attributes[match[1]]+" +"+match[2]+" / "+name
    aliases={6001400:"物理攻击力提升 +3",6830000:"力气与智力降低",6003000:"抗毒提升 +1"}
    prefix=aliases.get(int(effect["ID"]))
    return prefix+" / "+name if prefix else name
from relic_presets import Planner, CHARACTERS, ROOT, load


class App:
    def __init__(self, window):
        self.window = window
        self.planner = Planner(load(ROOT/"local/evidence/relic-catalog.json"),
                               load(ROOT/"data/relic_budgets.json"))
        self.preset = self.planner.new()
        window.title("NRE 遗物预设 · 本地实验版")
        window.geometry("1100x720")
        self.character = tk.StringVar(value="Ironeye")
        self.mode = tk.StringVar(value="normal")
        self.depth = tk.StringVar(value="1")
        self.query = tk.StringVar()
        self.kind = tk.StringVar(value="普通词条")
        self.build_results=queue.Queue()
        self.package_folder=None
        top = ttk.Frame(window, padding=12); top.pack(fill="x")
        ttk.Label(top, text="NRE 遗物预设", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(top, text="选择词条、保存预设并生成隔离实验包。普通六词条已实测；深夜游戏应用仍在验证。").pack(anchor="w", pady=6)
        controls = ttk.Frame(top); controls.pack(fill="x")
        for label, variable, values in [
            ("职业", self.character, CHARACTERS), ("模式", self.mode, ["normal", "deep"]),
            ("深度", self.depth, ["1","2","3","4","5"]), ("选择类型", self.kind, ["普通词条","深夜词条","深夜完整模板"])]:
            ttk.Label(controls, text=label).pack(side="left", padx=(8,3))
            box=ttk.Combobox(controls,textvariable=variable,values=values,state="readonly",width=14)
            box.pack(side="left")
            box.bind("<<ComboboxSelected>>", self.refresh)
        search=ttk.Frame(top); search.pack(fill="x",pady=10)
        ttk.Label(search,text="搜索名称或 ID").pack(side="left",padx=5)
        ttk.Entry(search,textvariable=self.query).pack(side="left",fill="x",expand=True)
        self.query.trace_add("write",self.refresh)
        panes=ttk.Panedwindow(window,orient="horizontal"); panes.pack(fill="both",expand=True,padx=12)
        left=ttk.Frame(panes);right=ttk.Frame(panes);panes.add(left,weight=3);panes.add(right,weight=2)
        self.available=ttk.Treeview(left,columns=("id","name"),show="headings",selectmode="browse")
        self.available.heading("id",text="ID");self.available.heading("name",text="原生名称（工具名称库）")
        self.available.column("id",width=95,stretch=False);self.available.column("name",width=440)
        scroll=ttk.Scrollbar(left,orient="vertical",command=self.available.yview)
        self.available.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right",fill="y")
        self.available.pack(fill="both",expand=True)
        ttk.Button(left,text="添加所选项 →",command=self.add).pack(fill="x",pady=8)
        self.selected=ttk.Treeview(right,columns=("kind","id","name"),show="headings",selectmode="browse")
        for col,title,width in [("kind","类型",65),("id","ID",90),("name","已选配置",220)]:
            self.selected.heading(col,text=title);self.selected.column(col,width=width)
        self.selected.pack(fill="both",expand=True)
        ttk.Button(right,text="移除所选项",command=self.remove).pack(fill="x",pady=8)
        bottom=ttk.Frame(window,padding=12);bottom.pack(fill="x")
        self.status=tk.StringVar()
        ttk.Label(bottom,textvariable=self.status,wraplength=1040).pack(anchor="w")
        buttons=ttk.Frame(bottom);buttons.pack(fill="x",pady=10)
        ttk.Button(buttons,text="保存新预设",command=self.save).pack(side="left",padx=4)
        ttk.Button(buttons,text="载入预设",command=self.open).pack(side="left",padx=4)
        ttk.Button(buttons,text="清空",command=self.clear).pack(side="left",padx=4)
        ttk.Button(buttons,text="导出实验清单",command=self.export_experiment).pack(side="left",padx=16)
        self.build_button=ttk.Button(buttons,text="生成隔离实验包",command=self.build)
        self.build_button.pack(side="left",padx=4)
        launchers=ttk.Frame(bottom);launchers.pack(fill="x",pady=4)
        ttk.Button(launchers,text="打开已有实验包",command=self.open_package).pack(side="left",padx=4)
        ttk.Button(launchers,text="启动：生成遗物",command=lambda:self.launch(True)).pack(side="left",padx=4)
        ttk.Button(launchers,text="启动：正常使用（不加载生成补丁）",command=lambda:self.launch(False)).pack(side="left",padx=4)
        ttk.Label(bottom,text="深夜保留原生负面，单件正负已实测；完整混合组合仍属实验。额度为任务书设计值。").pack(anchor="w")
        try:
            recent=load(ROOT/"local/last-package.json")
            from relic_launch import verify_package
            verify_package(recent["path"])
            candidate=load(Path(recent["path"])/"preset.json")
            if self.planner.validate(candidate)["valid_draft"]:
                self.preset=candidate;self.package_folder=Path(recent["path"])
                self.character.set(candidate["character"]);self.mode.set(candidate["mode"])
                self.depth.set(str(candidate["depth"] or 1))
        except (OSError,ValueError,KeyError,TypeError):
            pass
        self.refresh()
        self.window.after(200,self.poll_build)

    def sync(self):
        self.preset.update(character=self.character.get(),mode=self.mode.get(),
                           depth=int(self.depth.get()) if self.mode.get()=="deep" else None)

    def refresh(self,*_):
        self.sync()
        self.available.delete(*self.available.get_children())
        q=self.query.get().casefold()
        if self.kind.get()=="普通词条":
            candidates=[(key,label(self.planner.effects[key])) for key in sorted(self.planner.normal)
                        if self.planner.effects[key].get("allow"+self.character.get())=="1"]
        elif self.kind.get()=="深夜词条":
            candidates=[(key,("【必须绑定负面】" if key in self.planner.curse_required else "")+
                         label(self.planner.effects[key])) for key in sorted(self.planner.deep)
                         if self.planner.effects[key].get("allow"+self.character.get())=="1"]
        else:
            candidates=[]
            for key,t in self.planner.templates.items():
                try:
                    self.planner.deep_effects(key)
                    candidates.append((key,t["name"]))
                except ValueError:
                    pass
        for key,name in candidates:
            if q in (str(key)+" "+name).casefold():
                self.available.insert("", "end",iid=str(key),values=(key,name))
        self.selected.delete(*self.selected.get_children())
        for field,kind in [("normal_effects","普通"),("deep_templates","深夜")]:
            for i,key in enumerate(self.preset[field]):
                obj=self.planner.effects.get(key) if field=="normal_effects" else self.planner.templates.get(key)
                name=((label(obj) if field=="normal_effects" else obj["name"]) if obj else "未知引用")
                self.selected.insert("","end",iid=f"{field}:{i}",values=(kind,key,name))
        for i,bundle in enumerate(self.preset.get("deep_bundles",[])):
            key=bundle["effect_id"];curse=bundle["curse_id"]
            name=label(self.planner.effects[key])
            if curse is not None:name+=" / "+label(self.planner.effects[curse])
            self.selected.insert("","end",iid=f"deep_bundles:{i}",values=("深夜绑定",key,name))
        result=self.planner.validate(self.preset)
        budget=result.get("budget",{})
        text=f"普通 {result.get('normal_used',0)}/{budget.get('normal',0)} · 深夜正面 {result.get('deep_used',0)}/{budget.get('deep',0)}"
        text+="  |  "+("配置检查通过；生成包仅供隔离测试" if result["valid_draft"] else "；".join(result["errors"]))
        self.status.set(text)

    def add(self):
        selection=self.available.selection()
        if not selection:return
        if self.kind.get()=="深夜词条":
            key=int(selection[0])
            if key in self.planner.curse_required:
                self.choose_curse(key)
            else:
                self.add_bundle(key,None)
            return
        field="normal_effects" if self.kind.get()=="普通词条" else "deep_templates"
        self.preset[field].append(int(selection[0]))
        result=self.planner.validate(self.preset)
        if not result["valid_draft"]:
            self.preset[field].pop()
            messagebox.showerror("无法添加","；".join(result["errors"]))
        self.refresh()

    def add_bundle(self,key,curse):
        self.preset.setdefault("deep_bundles",[]).append({"effect_id":key,"curse_id":curse})
        result=self.planner.validate(self.preset)
        if not result["valid_draft"]:
            self.preset["deep_bundles"].pop()
            messagebox.showerror("无法添加","；".join(result["errors"]))
        self.refresh()

    def choose_curse(self,key):
        dialog=tk.Toplevel(self.window);dialog.title("绑定原生负面词条");dialog.geometry("700x400")
        ttk.Label(dialog,text="该正面词条必须保留一个负面效果；不能只添加正面。").pack(pady=12)
        choices=ttk.Treeview(dialog,columns=("id","name"),show="headings",selectmode="browse")
        choices.heading("id",text="ID");choices.heading("name",text="负面效果")
        choices.column("id",width=90,stretch=False);choices.column("name",width=560)
        choices.pack(fill="both",expand=True,padx=12)
        for curse in sorted(self.planner.curses):
            e=self.planner.effects[curse]
            if e.get("allow"+self.character.get())=="1":
                choices.insert("","end",iid=str(curse),values=(curse,label(e)))
        def confirm():
            selected=choices.selection()
            if selected:
                self.add_bundle(key,int(selected[0]));dialog.destroy()
        ttk.Button(dialog,text="绑定并添加",command=confirm).pack(pady=12)
        dialog.transient(self.window);dialog.grab_set()

    def remove(self):
        selection=self.selected.selection()
        if selection:
            field,index=selection[0].split(":");self.preset[field].pop(int(index));self.refresh()

    def save(self):
        self.sync()
        folder=ROOT/"local/presets";folder.mkdir(exist_ok=True)
        path=filedialog.asksaveasfilename(initialdir=folder,defaultextension=".json",filetypes=[("JSON","*.json")])
        if path:
            try:self.planner.save(self.preset,path)
            except (ValueError,OSError) as exc:messagebox.showerror("保存失败",str(exc));return
            self.status.set("已保存："+str(path)+"；状态：配置草稿")

    def open(self):
        path=filedialog.askopenfilename(initialdir=ROOT/"local/presets",filetypes=[("JSON","*.json")])
        if not path:return
        try:
            candidate=load(path);result=self.planner.validate(candidate)
            if not result["valid_draft"]:raise ValueError("；".join(result["errors"]))
            self.preset=candidate
            self.character.set(candidate["character"]);self.mode.set(candidate["mode"])
            self.depth.set(str(candidate["depth"] or 1));self.refresh()
        except (ValueError,OSError,KeyError,TypeError) as exc:messagebox.showerror("无法载入",str(exc))

    def clear(self):
        self.preset["normal_effects"]=[];self.preset["deep_templates"]=[];self.preset["deep_bundles"]=[];self.refresh()

    def export_experiment(self):
        self.sync()
        try:
            import csv
            with (ROOT/"local/evidence/ShopLineupParam.csv").open(encoding="utf-8-sig") as stream:
                shops=list(csv.DictReader(stream))
            manifest=self.planner.experimental_combined_manifest(self.preset,shops)
        except ValueError as exc:
            messagebox.showerror("无法导出",str(exc));return
        path=filedialog.asksaveasfilename(initialdir=ROOT/"local/presets",
            defaultextension=".json",filetypes=[("实验清单","*.json")])
        if not path:return
        try:
            with Path(path).open("x",encoding="utf-8") as stream:
                json.dump(manifest,stream,ensure_ascii=False,indent=2)
        except OSError as exc:
            messagebox.showerror("导出失败",str(exc));return
        self.status.set("已导出随机遗物实验清单。入口：小壶商店绿色三词条遗物；仅用于隔离存档。")

    def build(self):
        self.sync()
        preset=json.loads(json.dumps(self.preset))
        self.build_button.configure(state="disabled")
        self.status.set("正在生成并回读校验实验包……")
        def work():
            try:
                from relic_package import build_package
                result=str(build_package(preset))
                self.build_results.put((True,result))
            except Exception as exc:
                self.build_results.put((False,str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def poll_build(self):
        try:
            ok,result=self.build_results.get_nowait()
            self.build_button.configure(state="normal")
            self.status.set(("实验包已生成：" if ok else "构建失败：")+result)
            if ok:
                self.package_folder=Path(result)
                (ROOT/"local/last-package.json").write_text(json.dumps({"path":result},ensure_ascii=False),encoding="utf-8")
            if not ok:messagebox.showerror("构建失败",result)
        except queue.Empty:
            pass
        self.window.after(200,self.poll_build)

    def open_package(self):
        folder=filedialog.askdirectory(initialdir=ROOT/"local/packages")
        if not folder:return
        try:
            from relic_launch import verify_package
            verify_package(folder)
        except (ValueError,OSError,KeyError) as exc:
            messagebox.showerror("无法打开",str(exc));return
        self.package_folder=Path(folder)
        self.status.set("当前实验包："+str(folder))

    def launch(self,generation):
        if self.package_folder is None:
            messagebox.showerror("尚未选择实验包","请先生成或打开实验包。");return
        try:
            from relic_launch import launch
            result=launch(self.package_folder,generation)
            self.status.set("已启动："+result["mode"]+"；隔离存档："+result["savefile"])
        except (ValueError,OSError,KeyError) as exc:
            messagebox.showerror("无法启动",str(exc))


if __name__=="__main__":
    window=tk.Tk();App(window);window.mainloop()
