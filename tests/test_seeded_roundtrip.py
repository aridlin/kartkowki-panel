"""An original source ZIP + one scanned barcode reproduce the clean sheet offline."""
import json,os,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader
from seeded_generator import default_recipe,manifest
from paper_authoring import render_bundle
class OfflineRoundTripTests(unittest.TestCase):
 def test_offline_package_and_database_free_route(self):
  import app,paper_workflow as p
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);recipe=default_recipe(1,2,'integer',edition='offline-roundtrip')
   original=render_bundle(manifest(recipe,314159),root/'original');code=original['groups'][1]['barcode_value']
   archive_before=(root/'original/Generator_z_kryteriami.zip').read_bytes()
   qid=p.import_bundle(root/'original')
   self.assertEqual((root/'original/Generator_z_kryteriami.zip').read_bytes(),archive_before)
   source=root/'shared-original-code';source.mkdir()
   with zipfile.ZipFile(root/'original/Generator_z_kryteriami.zip') as archive:
    self.assertIn('recipe.json',archive.namelist());self.assertIn('fonts/DejaVuSans.ttf',archive.namelist());self.assertNotIn('zadania_i_kody.json',archive.namelist());archive.extractall(source)
   output=root/'restored'
   env=dict(os.environ,KARTKOWKI_DATA='/database-must-not-be-opened',KARTKOWKI_PROVIDER='unavailable')
   subprocess.run([sys.executable,str(source/'seeded_generator.py'),code,'--output',str(output),'--render'],env=env,capture_output=True,check=True,timeout=120)
   restored=json.loads((output/'zadania_i_kody.json').read_text())
   self.assertEqual(restored['groups'][0],original['groups'][1])
   self.assertAlmostEqual(float(PdfReader(output/'Arkusz.pdf').pages[0].mediabox.height),420.9449,places=3)
   for label,pdf in [('original',p.safe_file(f'papers/{qid}/group-002.pdf')),('restored',output/'Arkusz.pdf')]:
    subprocess.run(['pdftoppm','-r','150','-singlefile','-png',str(pdf),str(root/label)],capture_output=True,check=True,timeout=30)
    decoded=subprocess.run(['zbarimg','--quiet','--raw',str(root/(label+'.png'))],capture_output=True,text=True,timeout=20).stdout.splitlines()
    self.assertEqual(decoded,[code])
   # The server regenerates from the source-file registry without querying its quiz DB.
   with patch.object(p,'db',side_effect=AssertionError('Reconstruction tried to open a quiz DB')):self.assertTrue(p.regenerate_work(code).is_file())
   client=app.APP.test_client()
   with client.session_transaction() as session:session['teacher']=True
   with client.get(f'/papers/{qid}/generator.zip') as response:self.assertEqual(response.status_code,200)
   with client.get(f'/papers/recreate/{code}.pdf') as response:self.assertEqual(response.status_code,200)
   # The source archive detects an accidental change of its frozen criteria.
   (source/'recipe.json').write_text('{}')
   failed=subprocess.run([sys.executable,str(source/'seeded_generator.py'),code,'--output',str(root/'bad')],env=env,capture_output=True,text=True,timeout=30)
   self.assertNotEqual(failed.returncode,0);self.assertIn('source package has changed',failed.stderr)
if __name__=='__main__':unittest.main()
