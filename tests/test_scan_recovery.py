"""Visible but undecoded corners must not discard papers or overwrite reviewed scans."""
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
from PIL import Image
from scan_geometry import crop_works,DICT,W,H
class RecoveryTests(unittest.TestCase):
 def test_rotated_papers_recover_from_one_and_two_decoded_corners(self):
  scale=3;width,height=round(W*scale),round(H*scale)
  sheets=[]
  for group,visible in [(1,[2,3]),(2,[3])]:
   sheet=np.full((height,width,3),255,np.uint8)
   for corner in visible:
    x,y=[(24,24),(W-46,24),(W-46,H-46),(24,H-46)][corner]
    marker=cv2.aruco.generateImageMarker(DICT,(group-1)*4+corner,66)
    x,y=round(x*scale),round(y*scale);sheet[y:y+66,x:x+66]=cv2.cvtColor(marker,cv2.COLOR_GRAY2BGR)
   # A distinguishable task mark verifies orientation and extrapolated location.
   cv2.circle(sheet,(700,400),20,(0,0,255),-1)
   sheets.append(cv2.rotate(sheet,cv2.ROTATE_180))
  scan=cv2.copyMakeBorder(np.vstack(sheets),80,80,80,80,cv2.BORDER_CONSTANT,value=(255,255,255))
  turn=cv2.getRotationMatrix2D((scan.shape[1]/2,scan.shape[0]/2),2,1)
  scan=cv2.warpAffine(scan,turn,(scan.shape[1],scan.shape[0]),borderValue=(255,255,255))
  works=crop_works(scan,216);self.assertEqual([p['group'] for p in works],[1,2])
  self.assertEqual([p['inferred_corners'] for p in works],[2,3])
  for p in works:
   self.assertGreater(p['image'][400,700,2],200);self.assertLess(p['image'][400,700,0],50)
 def test_partial_import_retry_and_preserved_review(self):
  import paper_workflow as p
  with tempfile.TemporaryDirectory() as directory:
   old=p.DATA,p.DB,p.FILES;p.DATA=Path(directory);p.DB=p.DATA/'test.sqlite3';p.FILES=p.DATA/'papers';p.FILES.mkdir();p.init()
   try:
    codes=['001ABCDEF123456','002ABCDEF123456']
    with p.db() as c:
     c.execute('INSERT INTO paper_quizzes(id,title,manifest,pdf_path,key_path,created) VALUES(?,?,?,?,?,?)',('test','Test','{}','blank','key',p.now()))
     for i,code in enumerate(codes,1):c.execute('INSERT INTO paper_variants VALUES(?,?,?,?,?,?)',(code,'test',i,json.dumps([{'max_points':3}]*3),'[]','blank'))
    buf=io.BytesIO();Image.new('RGB',(20,20),'white').save(buf,'PNG');job=p.enqueue(buf.getvalue())['id']
    parts=[{'group':i,'image':np.full((20,20,3),255,np.uint8)} for i in [1,2]]
    with patch('scan_geometry.crop_works',return_value=parts),patch.object(p,'read_barcodes',side_effect=[[],[codes[1]]]):
     result=p.process_job(job);self.assertEqual(len(result),1)
    with p.db() as c:
     self.assertEqual(c.execute('SELECT status FROM paper_jobs').fetchone()[0],'needs_review')
     c.execute("UPDATE paper_scans SET status='reviewed',points=7,grade='4',evaluation='{}'")
    with patch('scan_geometry.crop_works',return_value=parts),patch.object(p,'read_barcodes',side_effect=[[codes[0]],[codes[1]]]):result=p.process_job(job)
    self.assertEqual(len(result),2)
    with p.db() as c:
     self.assertEqual(c.execute('SELECT COUNT(*) FROM paper_scans').fetchone()[0],2)
     self.assertEqual(c.execute('SELECT status FROM paper_jobs').fetchone()[0],'cropped')
     original=dict(c.execute('SELECT * FROM paper_scans WHERE barcode=?',(codes[1],)).fetchone())
    with patch('scan_geometry.crop_works',return_value=parts),patch.object(p,'read_barcodes',side_effect=[[codes[0]],[codes[1]]]):p.process_job(job,refresh_existing=True)
    with p.db() as c:
     current=c.execute('SELECT * FROM paper_scans WHERE barcode=?',(codes[1],)).fetchone()
     self.assertEqual((current['status'],current['points'],current['grade']),('reviewed',7,'4'))
     self.assertNotEqual(current['crop_path'],original['crop_path']);self.assertTrue(p.safe_file(original['crop_path']).is_file())
     self.assertTrue(c.execute("SELECT COUNT(*) FROM paper_audit WHERE action='recrop'").fetchone()[0])
   finally:p.DATA,p.DB,p.FILES=old
