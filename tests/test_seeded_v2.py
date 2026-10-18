"""New multipart seed recipes must preserve v1, keys, print codes and offline recovery."""
import copy,json,tempfile,unittest,os,subprocess,sys,zipfile
from pathlib import Path
from unittest.mock import patch
from fractions import Fraction
from pypdf import PdfReader
import cv2
from seeded_generator import manifest,reconstruct,decode,verify_manifest,evaluate
from examples.dzialania_na_liczbach import build
class SeedV2Tests(unittest.TestCase):
 def recipe(self):
  return build()
 def test_uniform_keys_and_seed_identity(self):
  recipe=self.recipe();meta=manifest(recipe,123456);verify_manifest(meta);self.assertEqual(len(meta['groups']),32)
  signatures=set()
  for group in meta['groups']:
   self.assertEqual(decode(group['barcode_value'])['version'],2);self.assertTrue(group['barcode_value'].startswith(f'{group["group"]:03d}'))
   self.assertEqual([t['max_points'] for t in group['tasks']],[3,4,4])
   self.assertEqual([len(t['parts']) for t in group['tasks']],[1,2,2])
   for task in group['tasks']:
    for part in task['parts']:
     sig=json.dumps(part['expression'],sort_keys=True);self.assertNotIn(sig,signatures);signatures.add(sig)
     self.assertEqual(evaluate(part['expression']),Fraction(part['answer_numerator'],part['answer_denominator']))
   self.assertEqual(reconstruct(group['barcode_value'],recipe)['groups'][0],group)
  self.assertEqual(len(signatures),160)
  damaged=copy.deepcopy(meta);damaged['groups'][0]['tasks'][1]['parts'][1]['answer_numerator']+=1
  with self.assertRaises(ValueError):verify_manifest(damaged)
 def test_render_import_offline_and_doc_code_filter(self):
  import paper_workflow as p
  from paper_authoring import render_bundle
  from scan_geometry import crop_works
  recipe=self.recipe();recipe['count']=2
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);meta=render_bundle(manifest(recipe,123456),root/'original');code=meta['groups'][1]['barcode_value']
   self.assertEqual(len(PdfReader(root/'original/Kartkowka_ulamki_30_grup.pdf').pages),1)
   old=p.DATA,p.DB,p.FILES;p.DATA=root;p.DB=root/'test.sqlite3';p.FILES=root/'papers';p.FILES.mkdir();p.init()
   try:
    from paper_authoring import process_author_job
    job=p.start_author({'count':2,'instructions':'Uniform multipart source-authored quiz','recipe':recipe,'seed':123456})
    with patch('model._run_codex',side_effect=AssertionError('Validated source recipes must not be replaced by an LLM')):process_author_job(job['id'])
    with p.db() as c:
     authored=c.execute('SELECT status,proposal FROM paper_author_jobs WHERE id=?',(job['id'],)).fetchone();self.assertEqual(authored[0],'draft');self.assertEqual(json.loads(authored[1])['groups'][0]['barcode_value'],meta['groups'][0]['barcode_value'])
    qid=p.import_bundle(root/'original')
    with self.assertRaisesRegex(ValueError,'podpunkty'):p.start_author({'count':2,'source_quiz_id':qid,'instructions':'Correct one task','randomize':False})
    subprocess.run(['pdftoppm','-r','220','-singlefile','-png',str(root/'original/Kartkowka_ulamki_30_grup.pdf'),str(root/'page')],check=True,capture_output=True)
    rawcodes=subprocess.run(['zbarimg','--quiet','--raw',str(root/'page.png')],capture_output=True,text=True).stdout.splitlines();self.assertEqual(set(rawcodes),{g['barcode_value'] for g in meta['groups']});self.assertFalse(any(code.startswith('@$') for code in rawcodes))
    parts=crop_works(cv2.imread(str(root/'page.png')));self.assertEqual([w['group'] for w in parts],[1,2])
    from points_marks import detect
    for part in parts:
     marks=detect(part['image'],meta['groups'][part['group']-1]['tasks']);self.assertFalse(marks['uncertain']);self.assertTrue(marks['present'])
     cv2.imwrite(str(root/'crop.png'),part['image']);self.assertEqual(p.read_barcodes(root/'crop.png'),[meta['groups'][part['group']-1]['barcode_value']])
    capture=p.enqueue((root/'page.png').read_bytes());scans=p.process_job(capture['id'])
    with p.db() as c:
     c.execute("UPDATE paper_quizzes SET class_name='1bb BSISnr7',grading_profile='zs33-bs'")
     c.execute('INSERT INTO paper_assignments VALUES(?,?,?,?)',(scans[0]['barcode'],'1bb BSISnr7','fixture',p.now()))
    observation={'student_name':'','name_confidence':1.0,'tasks':[{'question_id':str(i),'answer_text':'a i b sprawdzone','points':n,'uncertain':False,'comment':'Poprawne oba podpunkty'} for i,n in enumerate([3,4,4],1)],'comment':'Kompletna praca'}
    with patch('model._run_codex',return_value=observation) as call:p.grade_scan(scans[0]['scan_id'])
    self.assertIn('parts',call.call_args.args[0]);self.assertIn('WSZYSTKIE podpunkty',call.call_args.args[0])
    with p.db() as c:self.assertEqual(tuple(c.execute('SELECT points,maximum,grade FROM paper_scans WHERE id=?',(scans[0]['scan_id'],)).fetchone()),(11,11,'5'))
    source=root/'source';source.mkdir()
    with zipfile.ZipFile(root/'original/Generator_z_kryteriami.zip') as archive:archive.extractall(source)
    subprocess.run([sys.executable,str(source/'seeded_generator.py'),code,'--render','--output',str(root/'restored')],check=True,capture_output=True,env=dict(os.environ,KARTKOWKI_DATA='/unavailable-database'))
    restored=json.loads((root/'restored/zadania_i_kody.json').read_text());self.assertEqual(restored['groups'][0],meta['groups'][1])
    self.assertEqual(PdfReader(root/'restored/Arkusz.pdf').metadata.subject,'Work '+code)
    with patch.object(p,'db',side_effect=AssertionError('DB access during reconstruction')):self.assertTrue(p.regenerate_work(code).is_file())
   finally:p.DATA,p.DB,p.FILES=old
