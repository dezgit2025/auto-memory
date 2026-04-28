import subprocess, time, statistics, sys, json, os
env = os.environ.copy(); env["PYTHONPATH"]="src"
def t(args, n=5):
    times=[]
    for _ in range(n):
        s=time.perf_counter()
        subprocess.run([sys.executable,"-m","session_recall",*args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        times.append((time.perf_counter()-s)*1000)
    return round(statistics.median(times),1), round(max(times),1), round(min(times),1)
results={}
for label,args in [("list", ["list","--json","--limit","10"]),
                   ("files", ["files","--json","--limit","10"]),
                   ("search", ["search","test","--json","--limit","5"])]:
    med,mx,mn=t(args); results[label]={"median_ms":med,"max_ms":mx,"min_ms":mn}
print(json.dumps(results, indent=2))
