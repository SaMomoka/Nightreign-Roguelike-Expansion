"""BUFF-001 reference rules. No game-memory or engine adapter is implemented.

The native adapter must supply verified attack identity and weapon instance.
An accepted hit counts once per attack/target, not once per animation frame.
"""
from dataclasses import dataclass,field

ELEMENTS=('magic','fire','lightning','holy')

@dataclass(frozen=True)
class Hit:
    run: str
    owner: str
    weapon: str
    target: str
    attack: str
    time: float
    direct: bool=True
    equipped: bool=True
    damage: float=1

@dataclass
class ComboRules:
    threshold: int=3
    mark_seconds: float=12
    cooldown_seconds: float=8
    version: int=1
    run: str=''
    counters: dict=field(default_factory=dict)
    rotations: dict=field(default_factory=dict)
    marks: dict=field(default_factory=dict)
    cooldowns: dict=field(default_factory=dict)
    seen: set=field(default_factory=set)
    last_time: float=-1

    def __post_init__(self):
        if self.threshold<1 or self.mark_seconds<=0 or self.cooldown_seconds<=0:
            raise ValueError('Invalid combo configuration')

    def start_run(self,run):
        if not run:raise ValueError('Missing run identity')
        self.run=run;self.counters.clear();self.rotations.clear()
        self.marks.clear();self.cooldowns.clear();self.seen.clear();self.last_time=-1

    def unequip(self,owner,weapon):
        # Conservative first design: swapping away discards charged progress.
        self.counters.pop((owner,weapon),None)
        self.rotations.pop((owner,weapon),None)

    def remove_target(self,target):
        for key in list(self.marks):
            if key[1]==target:del self.marks[key]
        self.cooldowns.pop(target,None)

    def hit(self,h):
        if h.run!=self.run or not self.run or not all((h.owner,h.weapon,h.target,h.attack)):
            return []
        if h.time<self.last_time or not h.direct or not h.equipped or h.damage<=0:
            return []
        self.last_time=h.time
        key=(h.owner,h.weapon,h.target,h.attack)
        if key in self.seen:return []
        self.seen.add(key)
        weapon=(h.owner,h.weapon)
        n=self.counters.get(weapon,0)
        if n<self.threshold:
            self.counters[weapon]=n+1;return []
        self.counters[weapon]=0
        rotation=self.rotations.get(weapon,0)
        element=ELEMENTS[rotation%len(ELEMENTS)]
        self.rotations[weapon]=rotation+1
        out=[dict(kind='element_hit',element=element,target=h.target,owner=h.owner,weapon=h.weapon)]
        # One target-wide cooldown prevents simultaneous players from
        # resolving the same target repeatedly. Marks remain owner scoped.
        if h.time<self.cooldowns.get(h.target,0):return out
        key=(h.owner,h.target)
        marks={e:t for e,t in self.marks.get(key,{}).items() if t>h.time}
        marks[element]=h.time+self.mark_seconds;self.marks[key]=marks
        if len(marks)<3:return out
        combination=tuple(sorted(marks))
        self.cooldowns[h.target]=h.time+self.cooldown_seconds
        for mk in list(self.marks):
            if mk[1]==h.target:del self.marks[mk]
        out.append(dict(kind='combo',elements=combination,target=h.target,owner=h.owner,
                        idempotency=(self.version,self.run,h.owner,h.target,h.attack)))
        return out
