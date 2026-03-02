Reset all RAG data, metrics, and stats to zero for a clean baseline.

Run this Python script to perform the full reset:

```bash
python3 -c "
import subprocess as sp, os, signal, pathlib, time, urllib.request, json

# 1. Kill stats server / dashboard on port 9473
result = sp.run(['lsof', '-ti', ':9473'], capture_output=True, text=True)
for pid in result.stdout.strip().split():
    try: os.kill(int(pid), signal.SIGKILL)
    except: pass

# 2. Truncate Postgres tables (cascades memory_chunks)
sp.run(['psql', '-h', 'localhost', '-p', os.environ.get('PGPORT', '5433'),
        '-U', 'postgres', '-d', 'claude_rag',
        '-c', 'TRUNCATE memory_sources CASCADE;'],
       env={**os.environ, 'PGPASSWORD': 'postgres'}, capture_output=True)

# 3. Wipe metrics files
metrics = pathlib.Path.home() / '.claude-rag' / 'metrics'
metrics.mkdir(parents=True, exist_ok=True)
for f in ['events.jsonl', 'activity.jsonl']:
    (metrics / f).write_text('')
(metrics / 'counters.json').write_text('{}')

# 4. Wipe dedup cache
(pathlib.Path.home() / '.claude-rag' / 'dedup_cache.json').write_text('{}')

# 5. Delete hook queue
hq = pathlib.Path.home() / '.claude-rag' / 'hook_queue.db'
if hq.exists(): hq.unlink()

# 6. Clear staging directory
staging = pathlib.Path.home() / '.claude-rag' / 'staging'
if staging.exists():
    for f in staging.iterdir():
        f.unlink()

# 7. Start fresh stats server
sp.Popen(['python3', '-m', 'claude_rag.monitoring.stats_server'],
         env={**os.environ, 'PGPASSWORD': 'postgres',
              'PGPORT': os.environ.get('PGPORT', '5433'),
              'PYTHONPATH': 'claude-rag/src'},
         stdout=sp.DEVNULL, stderr=sp.DEVNULL, start_new_session=True)

time.sleep(3)

# 8. Verify
resp = urllib.request.urlopen('http://localhost:9473/stats')
d = json.loads(resp.read())
w, r = d['write'], d['read']
print(f'chunks:    {w[\"chunks_total\"]}')
print(f'files:     {w[\"files_indexed\"]}')
print(f'hooks:     {w[\"hooks_total\"]}')
print(f'searches:  {r[\"searches_total\"]}')
print(f'relevance: {r[\"avg_relevance\"]}')
print(f'rag_first: {r[\"rag_first_pct\"]}%')
print(f'fallback:  {r[\"fallback_rate_pct\"]}%')
print('ALL ZEROED')
"
```

Report the results to confirm everything is at zero.