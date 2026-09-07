import hashlib, json, os, shutil

SRC="data/history_10y.json"
OUT="data/history_shards"
INDEX="data/history_index.json"

with open(SRC,"r",encoding="utf-8") as f:
    rows=json.load(f)

groups={}
for r in rows:
    league=str(r.get("league") or "").strip()
    if not league:
        continue
    groups.setdefault(league,[]).append(r)

if os.path.isdir(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT,exist_ok=True)

files={}
for league,items in sorted(groups.items()):
    key=hashlib.sha1(league.encode("utf-8")).hexdigest()[:12]
    rel=f"history_shards/{key}.json"
    path=os.path.join("data",rel)
    with open(path,"w",encoding="utf-8") as f:
        json.dump(items,f,ensure_ascii=False,separators=(",",":"))
    files[league]={"file":"./data/"+rel,"matches":len(items)}

payload={"ok":True,"matches":len(rows),"leagues":len(files),"files":files}
with open(INDEX,"w",encoding="utf-8") as f:
    json.dump(payload,f,ensure_ascii=False,separators=(",",":"))
print("history shards:",len(files),"matches:",len(rows))
