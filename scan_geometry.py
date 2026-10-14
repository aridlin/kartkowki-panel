"""Detect four inward ArUco corners, group them by paper, and rectify an A5 work."""
import cv2
import numpy as np
W,H=595.2756,841.8898/2
MARGIN=24
DICT=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_250)
def crop_works(image,dpi=220):
 detector=cv2.aruco.ArucoDetector(DICT,cv2.aruco.DetectorParameters())
 corners,ids,_=detector.detectMarkers(image)
 if ids is None:return []
 entries=[(int(mid),pts.reshape(4,2)) for pts,mid in zip(corners,ids.flatten()) if 0<=int(mid)<120]
 out=[];used=set()
 for index,(mid,points) in enumerate(entries):
  if mid%4 or index in used:continue
  center=points.mean(axis=0);right=points[1]-points[0];down=points[3]-points[0]
  rw=float(np.linalg.norm(right));dh=float(np.linalg.norm(down));right=right/rw;down=down/dh
  expected_right=(W-2*MARGIN-22)/22*rw
  expected_down=(H-2*MARGIN-22)/22*dh
  def choose(marker,expected,scale):
   candidates=[]
   for j,(candidate,quad) in enumerate(entries):
    if candidate!=marker or j in used:continue
    distance=float(np.linalg.norm(quad.mean(axis=0)-expected))
    if distance<scale*.42:candidates.append((distance,j,quad))
   return min(candidates,key=lambda x:x[0]) if candidates else None
  tr=choose(mid+1,center+right*expected_right,expected_right)
  bl=choose(mid+3,center+down*expected_down,expected_down)
  if not tr or not bl:raise ValueError(f'Group {mid//4+1:03d}: incomplete corner markers; preserve the scan for review')
  expected_br=tr[2].mean(axis=0)+bl[2].mean(axis=0)-center
  br=choose(mid+2,expected_br,max(expected_right,expected_down))
  if not br:raise ValueError(f'Group {mid//4+1:03d}: incomplete corner markers; preserve the scan for review')
  selected=[index,tr[1],br[1],bl[1]]
  if len(set(selected))!=4:raise ValueError('Ambiguous corner markers')
  used.update(selected);group=mid//4+1;markers={0:points,1:tr[2],2:br[2],3:bl[2]}
  # ArUco corner order rotates with the marker, preserving orientation of the whole work.
  src=np.float32([markers[0][0],markers[1][1],markers[2][2],markers[3][3]])
  scale=dpi/72;target=np.float32([[MARGIN,MARGIN],[W-MARGIN,MARGIN],[W-MARGIN,H-MARGIN],[MARGIN,H-MARGIN]])*scale
  transform=cv2.getPerspectiveTransform(src,target)
  crop=cv2.warpPerspective(image,transform,(round(W*scale),round(H*scale)),borderValue=(255,255,255))
  out.append({'group':group,'position':(float(center[1]),float(center[0])),'image':crop,'marker_ids':[4*(group-1)+i for i in range(4)]})
 if len(used)!=len(entries):raise ValueError("Some corner markers could not be paired; preserve the original scan")
 return sorted(out,key=lambda work:work['position'])
