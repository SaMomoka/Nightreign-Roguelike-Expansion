"""Linear-size selection state for the full native catalog.

This module does not claim a runtime adapter. It owns drafts and validates
requests; native payment/item delivery is allowed only after an adapter exists.
"""
import copy
import hashlib
import json
import uuid


class RelicSelection:
    def __init__(self, catalog):
        self.entries = {e["effect_id"]: e for e in catalog["entries"]}
        self.session = uuid.uuid4().hex
        self.version = 0
        self.drafts = [[dict(effect_id=None, curse_id=None) for _ in range(3)] for _ in range(4)]
        self.pending = None
        self.prepared = None
        self.colors = [3] * 4

    def choose_color(self, editor, color):
        self.kind(editor)
        if type(color) is not int or color not in range(4):
            raise ValueError("Invalid native relic color")
        if self.pending is not None:
            raise ValueError("Finish or cancel the pending negative selection")
        self.colors[editor] = color
        self._changed()

    @staticmethod
    def kind(editor):
        if type(editor) is not int or not 0 <= editor < 4:
            raise ValueError("Invalid editor")
        return "normal" if editor < 2 else "deep"

    def _position(self, editor, slot):
        self.kind(editor)
        if type(slot) is not int or not 0 <= slot < 3:
            raise ValueError("Invalid effect slot")

    def candidates(self, editor, negative=False):
        kind = self.kind(editor)
        if negative and kind != "deep":
            return []
        return sorted(e["effect_id"] for e in self.entries.values()
            if kind in e["selectable_modes"] and e["is_negative"] == negative
            and (kind == "normal" or (e["curse_random"] if negative else e["deep_random"])))

    def page(self, editor, page=0, negative=False, page_size=6):
        if type(page_size) is not int or not 1 <= page_size <= 6:
            raise ValueError("Native menu pages allow up to six choices plus navigation")
        candidates = self.candidates(editor, negative)
        count = max(1, (len(candidates) + page_size - 1) // page_size)
        if type(page) is not int or not 0 <= page < count:
            raise ValueError("Invalid page")
        choices = []
        for effect_id in candidates[page * page_size:(page + 1) * page_size]:
            e = self.entries[effect_id]
            label = e["names"].get("zhocn") or e["names"].get("engus")
            if not label:
                raise ValueError("Missing native display name")
            choices.append(dict(effect_id=effect_id, label=label.strip(),
                requires_curse=e["curse_requirement"] == "required",
                allowed_characters=e["allowed_characters"]))
        return dict(page=page, pages=count, choices=choices,
                    previous=page-1 if page else None,
                    next=page+1 if page+1 < count else None, back=True)

    def _changed(self):
        self.version += 1
        self.prepared = None

    def _compatible(self, values):
        """Allow repeated identical IDs; retain conflicts between distinct effects."""
        for field in ("compatibility_id","exclusivity_id"):
            seen=set()
            for value in set(values):
                if value is None:continue
                group=self.entries[value].get(field,-1)
                if group>=0:
                    if group in seen:raise ValueError("Conflicting native "+field)
                    seen.add(group)

    def _others(self, editor, slot):
        return [value for i,b in enumerate(self.drafts[editor]) if i!=slot
                for value in (b["effect_id"],b["curse_id"]) if value is not None]

    def choose_positive(self, editor, slot, effect_id):
        self._position(editor, slot)
        if effect_id not in self.candidates(editor):
            raise ValueError("Effect is not a selectable positive relic effect")
        self._compatible(self._others(editor,slot)+[effect_id])
        entry = self.entries[effect_id]
        self._changed()
        if self.kind(editor) == "deep" and entry["curse_requirement"] == "required":
            # Keep the old committed bundle until a negative is selected. Cancel
            # restores the prior pair rather than leaving an invalid half-draft.
            self.pending = dict(editor=editor, slot=slot, effect_id=effect_id)
            return "choose_negative"
        self.pending = None
        self.drafts[editor][slot] = dict(effect_id=effect_id, curse_id=None)
        return "editor"

    def choose_negative(self, negative_id):
        if self.pending is None:
            raise ValueError("No positive effect awaiting a negative")
        pending = self.pending
        editor, slot = pending["editor"], pending["slot"]
        if negative_id not in self.candidates(editor, negative=True):
            raise ValueError("Invalid negative relic effect")
        self._compatible(self._others(editor,slot)+[pending["effect_id"],negative_id])
        self.drafts[editor][slot] = dict(effect_id=pending["effect_id"], curse_id=negative_id)
        self.pending = None
        self._changed()
        return "editor"

    def cancel_negative(self):
        self.pending = None
        self._changed()

    def clear(self, editor, slot):
        self._position(editor, slot)
        self.drafts[editor][slot] = dict(effect_id=None, curse_id=None)
        self.pending = None
        self._changed()

    def review(self, editor):
        kind = self.kind(editor)
        if self.pending is not None:
            raise ValueError("Finish or cancel the pending negative selection")
        bundles = copy.deepcopy(self.drafts[editor])
        for b in bundles:
            if b["effect_id"] is None:
                raise ValueError("Select all three positive effects")
            e = self.entries[b["effect_id"]]
            required = kind == "deep" and e["curse_requirement"] == "required"
            if required != (b["curse_id"] is not None):
                raise ValueError("Invalid positive/negative binding")
        self._compatible([value for b in bundles for value in (b["effect_id"],b["curse_id"])])
        bundles.sort(key=lambda b: (self.entries[b["effect_id"]]["order"], b["effect_id"]))
        return dict(kind=kind, color=self.colors[editor], bundles=bundles, price=1, currency_cost_type=4,
                    editor=editor, session=self.session, version=self.version)

    def request(self, editor):
        """An immutable request only. No debit or grant is performed here."""
        result = self.review(editor)
        result["request_id"] = uuid.uuid4().hex
        result["sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        self.prepared = copy.deepcopy(result)
        return result

    def verify_ack(self, ack):
        """Stale/duplicate acknowledgements must never open a changed shop."""
        request = self.prepared
        if request is None or self.pending is not None:
            raise ValueError("No current craft request")
        for field in ("session", "version", "request_id", "sha256", "editor"):
            if ack.get(field) != request[field]:
                raise ValueError("Stale or mismatched craft acknowledgement")
        if request["version"] != self.version:
            raise ValueError("Draft changed since craft request")
        if ack.get("runtime_verified") is not True or type(ack.get("shop_id")) is not int:
            raise ValueError("Runtime preparation is not verified")
        self.prepared = None
        return ack["shop_id"]


def menu_blueprint(catalog):
    """A bounded selection specification, deliberately not a runnable ESD."""
    model = RelicSelection(catalog)
    pickers = []
    for editor in range(4):
        for negative in (False, True):
            if negative and editor < 2:
                continue
            first = model.page(editor, negative=negative)
            pickers.append(dict(editor=editor, negative=negative,
                pages=[model.page(editor, p, negative) for p in range(first["pages"])]))
    return dict(schema_version=1, kind="selection_blueprint_not_game_package",
        runtime_bound=False, runtime_adapter=None,
        editor_entries=["positive_slot_1", "positive_slot_2", "positive_slot_3", "craft_for_one_murk", "back"],
        pickers=pickers, drafts_retained_between_editors=True,
        required_flow="positive_then_negative_only_when_required",
        purchase_policy="native_shop_after_verified_preparation",
        limitations=["This blueprint cannot be launched as a game package.",
                     "Native draft transport and runtime product preparation remain unbound."])
