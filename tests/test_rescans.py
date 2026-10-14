"""Rescans retain originals; delivery retries and pupil URLs remain stable."""
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
import numpy as np
from PIL import Image
class RescanTests(unittest.TestCase):
 def test_versions_and_links(self):
  import app,paper_workflow as p
  with tempfile.TemporaryDirectory() as directory:
   old=p.DATA,p.DB,p.FILES;p.DATA=Path(directory);p.DB=p.DATA/'test.sqlite3';p.FILES=p.DATA/'papers';p.FILES.mkdir();p.init()
   try:
    code='001ABCDEF123456'
    with p.db() as c:
     c.execute('INSERT INTO paper_quizzes(id,title,manifest,pdf_path,key_path,created) VALUES(?,?,?,?,?,?)',('test','Test','{}','blank','key',p.now()))
     c.execute('INSERT INTO paper_variants VALUES(?,?,?,?,?,?)',(code,'test',1,json.dumps([{'max_points':3}]*3),'[]','blank'))
    data=io.BytesIO();Image.new('RGB',(20,20),'white').save(data,'PNG');raw=data.getvalue()
    first_job=p.enqueue(raw,capture_id='capture1');self.assertEqual(first_job,p.enqueue(raw,capture_id='capture1'))
    with self.assertRaises(ValueError):p.enqueue(raw+b'changed',capture_id='capture1')
    parts=[{'group':1,'image':np.full((20,20,3),255,np.uint8)}]*2
    with patch('scan_geometry.crop_works',return_value=parts),patch.object(p,'read_barcodes',return_value=[code]):
     scans=p.process_job(first_job['id']);self.assertEqual(len({s['scan_id'] for s in scans}),2);self.assertEqual(scans,p.process_job(first_job['id']))
    first,second=[s['scan_id'] for s in scans];client=app.APP.test_client()
    with client.session_transaction() as session:session['teacher']=True
    link=client.post(f'/api/papers/scans/{first}/share').json['url'];url=urlsplit(link)
    self.assertEqual(link,client.post(f'/api/papers/scans/{second}/share').json['url'])
    new_job=p.enqueue(raw);self.assertNotEqual(first_job['id'],new_job['id'])
    with patch('scan_geometry.crop_works',return_value=parts[:1]),patch.object(p,'read_barcodes',return_value=[code]):third=p.process_job(new_job['id'])[0]['scan_id']
    with p.db() as c:
     self.assertEqual(p.latest_scan(c,code)['id'],third);c.execute('UPDATE paper_scans SET updated=? WHERE id=?',(p.now(),first));self.assertEqual(p.latest_scan(c,code)['id'],third)
    self.assertEqual(link,client.post(f'/api/papers/scans/{third}/share').json['url'])
    with patch.object(p,'scan_response',side_effect=lambda sid:app.APP.response_class(str(sid))):self.assertEqual(client.get(url.path+'?'+url.query).data,str(third).encode())
    client.delete(f'/api/papers/scans/{third}/share');self.assertEqual(client.get(url.path+'?'+url.query).status_code,404)
    # Upgrade a legacy table while retaining scans and share foreign keys.
    with p.db() as c:
     c.execute('PRAGMA foreign_keys=OFF');c.execute('BEGIN IMMEDIATE');c.execute('DELETE FROM paper_scans WHERE id<>?',(first,));c.execute('INSERT INTO paper_shares VALUES(?,?,?)',(first,'legacy-hash',p.now()))
     schema=c.execute("SELECT sql FROM sqlite_master WHERE name='paper_scans'").fetchone()[0]
     names=','.join(r[1] for r in c.execute('PRAGMA table_info(paper_scans)') if r[1] not in ['received_at','occurrence'])
     start=schema.index('received_at TEXT');end=schema.index('UNIQUE(job_id,occurrence)',start)
     legacy=schema[:start]+'UNIQUE(job_id,barcode)'+schema[end+len('UNIQUE(job_id,occurrence)'):]
     c.execute('CREATE TABLE legacy'+legacy[legacy.index('('):]);c.execute(f'INSERT INTO legacy({names}) SELECT {names} FROM paper_scans');c.execute('DROP TABLE paper_scans');c.execute('ALTER TABLE legacy RENAME TO paper_scans')
    p.init()
    with p.db() as c:
     self.assertEqual(c.execute('SELECT COUNT(*) FROM paper_shares').fetchone()[0],1);self.assertEqual(c.execute('SELECT id FROM paper_scans').fetchone()[0],first);self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
   finally:p.DATA,p.DB,p.FILES=old
if __name__=='__main__':unittest.main()
