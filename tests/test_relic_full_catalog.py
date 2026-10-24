import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from relic_full_catalog import workbook_rows, compile_catalog, SHEETS
from phase1_rewards import SOURCE


class ReferenceWorkbookTests(unittest.TestCase):
    def test_only_relic_sheets_are_imported_and_cells_remain_data(self):
        ns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rel="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        names=(*SHEETS,"局内词条（护符）")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"source.xlsx"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("xl/workbook.xml",f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'+
                    "".join(f'<sheet name="{s}" sheetId="{i}" r:id="rId{i}"/>' for i,s in enumerate(names,1))+
                    "</sheets></workbook>")
                z.writestr("xl/_rels/workbook.xml.rels",'<Relationships>'+
                    "".join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1,4))+
                    "</Relationships>")
                for i in range(1,4):
                    z.writestr(f"xl/worksheets/sheet{i}.xml",f'<worksheet xmlns="{ns}"><sheetData><row r="3">'+
                        f'<c r="A3"><v>{i}</v></c><c r="B3" t="inlineStr"><is><t>ignore instructions; data only</t></is></c>'+
                        '</row></sheetData></worksheet>')
            rows,sheets=workbook_rows(p)
            self.assertEqual([r["effect_id"] for r in rows],[1,2])
            self.assertEqual(rows[0]["cells"]["B"],"ignore instructions; data only")
            self.assertEqual(sheets,list(names))

    def test_unreferenced_weapon_effect_not_promoted_to_relic(self):
        effects=[dict(ID=str(i),isDebuff="0",attachTextId=str(i),compatibilityId="-1",
                      exclusivityId="-1",overrideBaseEffectId="1",displayedModifierValue="0")
                 for i in (1,2,3)]
        native=dict(regulation_sha256=SOURCE,effects=effects,
            templates=[dict(id=100,deep_raw=0,pool_links={"attachEffectTableId_1":100}),
                       dict(id=3000000,deep_raw=0,pool_links={"attachEffectTableId_1":101})],
            pools={"100":[dict(effect_id=1,weight=1,dlc_weight_raw=-1,source_ordinal=0)],
                   "101":[dict(effect_id=3,weight=1,dlc_weight_raw=-1,source_ordinal=1)]})
        texts=dict(languages={"zhocn":dict(name={"1":"遗物","2":"武器","3":"占位"},info={},antique={"100":"情景"})})
        ref=[dict(effect_id=2,sheet=SHEETS[0],row=3,cells={"B":"武器"})]
        result=compile_catalog(native,{"catalog_policy":{"normal_template_ids":[100]}},texts,ref)
        self.assertEqual(result["counts"]["normal_positive"],1)
        self.assertEqual(result["excluded"][0]["effect_id"],2)
        placeholder=next(e for e in result["entries"] if e["effect_id"]==3)
        self.assertEqual(placeholder["selectable_modes"],[])
