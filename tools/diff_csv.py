"""Read-only row/field diff; no binary patching. Pass the actual Smithbox ID column."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

def load(path, key, delimiter):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames or key not in reader.fieldnames:
            raise ValueError("ID column missing")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Duplicate columns")
        rows = {}
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Malformed CSV row")
            if not row[key] or row[key] in rows:
                raise ValueError("Empty or duplicate row ID")
            rows[row[key]] = row
        return reader.fieldnames, rows

def compare(before, after, key, delimiter=","):
    cols_a, a = load(before, key, delimiter)
    cols_b, b = load(after, key, delimiter)
    if cols_a != cols_b:
        raise ValueError("Schema/column order changed; migration required")
    changes = []
    for rid in sorted(a.keys() | b.keys()):
        if rid not in a or rid not in b:
            changes.append({"row": rid, "operation": "add" if rid not in a else "delete"})
        else:
            for col in cols_a:
                if a[rid][col] != b[rid][col]:
                    changes.append({"row":rid,"field":col,"before":a[rid][col],"after":b[rid][col]})
    return {"before_sha256":hashlib.sha256(Path(before).read_bytes()).hexdigest(),
            "after_sha256":hashlib.sha256(Path(after).read_bytes()).hexdigest(),"changes":changes}

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--key", required=True)
    p.add_argument("--delimiter", default=",")
    args = p.parse_args()
    try:
        print(json.dumps(compare(args.before,args.after,args.key,args.delimiter),ensure_ascii=False,indent=2))
    except (ValueError, OSError) as e:
        p.exit(2, str(e)+"\n")
