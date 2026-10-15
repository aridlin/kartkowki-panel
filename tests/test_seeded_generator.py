"""Frozen protocol vectors, exact criteria and reconstruction without database/AI."""
import copy,json,unittest
from seeded_generator import *
class SeedTests(unittest.TestCase):
 def test_golden_protocol_and_all_groups(self):
  recipe=default_recipe(1,30,'integer',edition='stable-test',created_date='2026-10-15')
  # A code/sampler change requires a new version, never silently changing these vectors.
  meta=manifest(recipe,42)
  self.assertEqual(meta['groups'][29]['barcode_value'],'03091010330118490769000000004204')
  self.assertEqual(groups_from_seed(recipe,42),meta['groups'])
  for original in meta['groups']:
   self.assertEqual(decode(original['barcode_value'])['group'],original['group'])
   for task in original['tasks']:self.assertEqual(task['answer_denominator'],1)
  self.assertEqual(reconstruct(meta['groups'][29]['barcode_value'],recipe)['groups'][0],meta['groups'][29])
  self.assertNotEqual(meta['groups'],manifest(recipe,43)['groups'])
 def test_reject_wrong_source_and_damaged_scan(self):
  recipe=default_recipe(1,2,edition='protocol-test');code=barcode(recipe,1234,1)
  for index in range(32):
   changed=code[:index]+str((int(code[index])+1)%10)+code[index+1:]
   with self.assertRaises(ValueError):decode(changed)
  other=copy.deepcopy(recipe);other['templates'][0]['criteria']['answer_kind']='integer'
  with self.assertRaises(ValueError):reconstruct(code,other)
  with self.assertRaises(ValueError):decode('001DC70A89783E7')
 def test_fixed_clone_preserves_math_with_new_identity(self):
  source=manifest(default_recipe(2,3,edition='source'),990)
  fixed=fixed_manifest(source,77)
  for a,b in zip(source['groups'],fixed['groups']):
   self.assertNotEqual(a['barcode_value'],b['barcode_value'])
   for x,y in zip(a['tasks'],b['tasks']):self.assertEqual(x['expression'],y['expression']);self.assertEqual(x['answer_mixed'],y['answer_mixed'])
  verify_manifest(fixed)
  broken=copy.deepcopy(fixed);broken['groups'][0]['tasks'][0]['answer_numerator']+=1
  with self.assertRaises(ValueError):verify_manifest(broken)
 def test_impossible_criteria_fail_without_printing(self):
  recipe=default_recipe(1,1,edition='impossible')
  recipe['templates'][0]['expression']={'op':'sample','values':[{'n':1,'d':2},{'n':1,'d':3}]}
  recipe['templates'][0]['criteria']['answer_kind']='integer'
  with self.assertRaisesRegex(ValueError,'Criteria cannot'):manifest(recipe,1)
if __name__=='__main__':unittest.main()
