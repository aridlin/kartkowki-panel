import time,fcntl,sys
AUTHOR_ONLY="--author-only" in sys.argv
from paper_workflow import *
init()
lock=(FILES/('author-worker.lock' if AUTHOR_ONLY else 'worker.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
# Recover work interrupted by a container restart, without resubmitting completed scans.
with db() as c:
 c.execute("UPDATE paper_author_jobs SET status='failed',error='Generowanie przerwane; rozpocznij nową propozycję' WHERE status='generating'") if AUTHOR_ONLY else None
 if not AUTHOR_ONLY:c.execute("UPDATE paper_jobs SET status='queued' WHERE status='processing'")
 if not AUTHOR_ONLY:c.execute("UPDATE paper_scans SET status='waiting_auth' WHERE status='grading'")
auth=False;last_auth=0
while True:
 try:
  if AUTHOR_ONLY:
   with db() as c:author=c.execute("SELECT id FROM paper_author_jobs WHERE status='queued' ORDER BY updated LIMIT 1").fetchone()
   if author:
    try:
     from paper_authoring import process_author_job
     process_author_job(author['id'])
    except Exception as e:
     with db() as c:c.execute('UPDATE paper_author_jobs SET status=?,error=?,updated=? WHERE id=?',('failed','Nie udało się przygotować poprawnej propozycji: '+(str(e)[:250] if isinstance(e,ValueError) else type(e).__name__),now(),author['id']))
   time.sleep(2);continue
  with db() as c:job=c.execute("SELECT id FROM paper_jobs WHERE status='queued' ORDER BY updated LIMIT 1").fetchone()
  if job:
   try:process_job(job['id'])
   except Exception as e:
    with db() as c:c.execute('UPDATE paper_jobs SET status=?,error=?,updated=? WHERE id=?',('needs_review',str(e)[:500],now(),job['id']))
  if time.monotonic()-last_auth>20:auth=oauth_status()['logged_in'];last_auth=time.monotonic()
  if auth:
   with db() as c:scan=c.execute("SELECT id FROM paper_scans WHERE status='waiting_auth' ORDER BY id LIMIT 1").fetchone()
   if scan:
    try:grade_scan(scan['id'])
    except Exception:
     with db() as c:c.execute('UPDATE paper_scans SET status=?,description=?,updated=? WHERE id=?',('needs_review','Automatyczna ocena nie powiodła się. Sprawdź stan OAuth i ponów ocenianie.',now(),scan['id']))
  time.sleep(2)
 except Exception as e:print('Worker error:',type(e).__name__,flush=True);time.sleep(5)
