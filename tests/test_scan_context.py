"""Outside-marker handwriting survives rectification; grading coordinates stay fixed."""
import io,tempfile,unittest
from pathlib import Path
import cv2,numpy as np
from PIL import Image
from scan_geometry import crop_works,DICT,W,H,CONTEXT_MARGIN
from points_marks import annotate,detect,geometry
class ContextTests(unittest.TestCase):
 def test_writing_beyond_markers_and_sheet(self):
  scale=3;width,height=round(W*scale),round(H*scale);border=90
  image=np.full((2*height+2*border,width+2*border,3),255,np.uint8)
  for group in range(2):
   ox,oy=border,border+group*height
   for index,(x,y) in enumerate([(24,24),(W-46,24),(W-46,H-46),(24,H-46)]):
    marker=cv2.aruco.generateImageMarker(DICT,group*4+index,66)
    px,py=ox+round(x*scale),oy+round(y*scale);image[py:py+66,px:px+66]=cv2.cvtColor(marker,cv2.COLOR_GRAY2BGR)
   # Red writing beyond the nominal A5 edge, green writing outside markers but on the sheet.
   cv2.circle(image,(ox-18,oy+height//2),6,(0,0,255),-1)
   cv2.circle(image,(ox+30,oy+height//2),6,(0,180,0),-1)
  works=crop_works(image,216);self.assertEqual([p['group'] for p in works],[1,2])
  for work in works:
   pad=round(CONTEXT_MARGIN*scale);context=work['context_image'];core=work['image']
   self.assertEqual(work['content_frame'],[pad,pad,core.shape[1],core.shape[0]])
   self.assertTrue(np.any((context[:,:,2]>200)&(context[:,:,0]<60)&(context[:,:,1]<60)))
   self.assertFalse(np.any((core[:,:,2]>200)&(core[:,:,0]<60)&(core[:,:,1]<60)))
   self.assertTrue(np.any((core[:,:,1]>120)&(core[:,:,0]<60)&(core[:,:,2]<60)))
 def test_point_overlay_uses_canonical_frame(self):
  scale=3;core=np.full((round(H*scale),round(W*scale),3),255,np.uint8);pad=36
  tasks=[{'max_points':3,'grading_mark':geometry(i,3)} for i in range(3)]
  for task in tasks:
   for polygon in task['grading_mark']['polygons_pt']+task['grading_mark']['fraction_polygons_pt']:cv2.polylines(core,[np.rint(np.array(polygon)*scale).astype(np.int32)],True,(0,0,0),2)
  context=cv2.copyMakeBorder(core,pad,pad,pad,pad,cv2.BORDER_CONSTANT,value=(255,255,255));context[4:12,4:12]=(0,0,255)
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'context.png';cv2.imwrite(str(path),context)
   output=annotate(path,tasks,[2.5,1.25,3],frame=[pad,pad,core.shape[1],core.shape[0]])
   result=cv2.imdecode(np.frombuffer(output,np.uint8),cv2.IMREAD_COLOR)
   np.testing.assert_array_equal(result[:pad],context[:pad])
   marks=detect(result[pad:pad+core.shape[0],pad:pad+core.shape[1]],tasks)
   self.assertFalse(marks['uncertain']);self.assertEqual([v['points'] for v in marks['points']],[2.5,1.25,3])
