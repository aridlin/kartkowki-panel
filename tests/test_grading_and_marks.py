import unittest,tempfile
from pathlib import Path
import numpy as np,cv2
from grade_rules import school_grade
from points_marks import geometry,detect,annotate,W,H
class GradingTests(unittest.TestCase):
 def test_fractional_boundary(self):
  self.assertEqual(school_grade(34,100,'zs33-tech'),'1');self.assertEqual(school_grade('34.000001',100,'zs33-tech'),'2')
 def test_bonus(self):
  self.assertEqual(school_grade(9,9,'sp263'),'6');self.assertEqual(school_grade(9,9,'zs33-tech'),'5');self.assertEqual(school_grade(9,9,'zs33-tech',.5,1),'6')
 def test_website_marks_and_quarters(self):
  scale=3;image=np.full((round(H*scale),round(W*scale),3),255,np.uint8);tasks=[{'max_points':3 if i<2 else 4,'grading_mark':geometry(i,3 if i<2 else 4)} for i in range(3)]
  for task in tasks:
   for polygon in task['grading_mark']['polygons_pt']+task['grading_mark']['fraction_polygons_pt']:cv2.polylines(image,[np.rint(np.array(polygon)*scale).astype(np.int32)],True,(0,0,0),2)
  self.assertFalse(detect(image,tasks)['confirmed'])
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'paper.png';cv2.imwrite(str(p),image);p.write_bytes(annotate(p,tasks,[2.5,1.25,4]));result=detect(cv2.imread(str(p)),tasks);self.assertTrue(result['confirmed']);self.assertFalse(result['uncertain']);self.assertEqual([x['points'] for x in result['points']],[2.5,1.25,4])
if __name__=='__main__':unittest.main()
