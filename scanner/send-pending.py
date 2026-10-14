#!/usr/bin/python3
"""Send scans to the local coded-paper queue; never upload via binup."""
import fcntl,json,os,datetime,urllib.request
from pathlib import Path
os.umask(0o077);b=Path('/var/lib/paperless-scanner');lock=(b/'send.lock').open('a')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit(0)
token=(b/'assessment-ingest-token').read_text().strip()
for p in sorted((b/'send-pending').glob('*.json')):
 job=json.loads(p.read_text());file=(b/job['file']).resolve()
 if file.parent!=b/'originals' or file.suffix!='.png':raise ValueError('Invalid scan path')
 try:
  req=urllib.request.Request('http://127.0.0.1:8768/internal/papers/ingest',data=file.read_bytes(),headers={'Content-Type':'image/png','X-Scanner-Token':token},method='POST')
  with urllib.request.urlopen(req,timeout=40) as response:result=json.load(response)
 except Exception:print('Send import unavailable; scan retained for retry',flush=True);break
 dest=b/'send-results'/p.name;tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps({'file':job['file'],'imported':datetime.datetime.now(datetime.timezone.utc).isoformat(),'job':result}));tmp.replace(dest);p.unlink()
 print('Send scan added to assessment queue:',file.name,flush=True)
