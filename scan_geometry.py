"""Detect four inward ArUco corners, group them by paper, and rectify an A5 work."""
import cv2
import numpy as np
W,H=595.2756,841.8898/2
MARGIN=24
CONTEXT_MARGIN=12 # extra 4.2 mm beyond the whole A5 sheet, not just the markers
DICT=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_250)
def marker_quad(index):
 x,y=[(MARGIN,MARGIN),(W-MARGIN-22,MARGIN),(W-MARGIN-22,H-MARGIN-22),(MARGIN,H-MARGIN-22)][index]
 return np.float32([[x,y],[x+22,y],[x+22,y+22],[x,y+22]])

def crop_works(image,dpi=220):
 # Scan contrast and pen strokes can prevent decoding an otherwise visible corner.
 # Keep independent detections, then recover the sheet from the corners that decoded.
 gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image
 params=cv2.aruco.DetectorParameters()
 params.adaptiveThreshWinSizeMax=93
 params.errorCorrectionRate=1.0
 params.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
 detector=cv2.aruco.ArucoDetector(DICT,params);entries=[]
 for prepared in (gray,cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]):
  corners,ids,_=detector.detectMarkers(prepared)
  if ids is None:continue
  for pts,mid in zip(corners,ids.flatten()):
   mid=int(mid);quad=pts.reshape(4,2)
   if 0<=mid<240 and not any(mid==old and np.linalg.norm(quad.mean(axis=0)-other.mean(axis=0))<10 for old,other in entries):entries.append((mid,quad))
 out=[];used=set();scale=dpi/72
 for index,(mid,points) in enumerate(entries):
  if index in used:continue
  base=mid//4*4;canonical=marker_quad(mid%4)
  # A flatbed scan is a rotated/scaled sheet. A local marker also gives orientation
  # when the other corners cannot decode; the caller must still verify its barcode.
  local=cv2.getAffineTransform(canonical[:3],np.float32(points[:3]))
  selected={mid%4:(index,points)}
  for corner in range(4):
   expected=cv2.transform(marker_quad(corner)[None],local)[0].mean(axis=0)
   span=np.linalg.norm(points[1]-points[0])*min(W,H)/22
   candidates=[(float(np.linalg.norm(q.mean(axis=0)-expected)),j,q) for j,(candidate,q) in enumerate(entries) if candidate==base+corner and j not in used]
   candidates=[v for v in candidates if v[0]<span*.20]
   if candidates:
    _,j,q=min(candidates,key=lambda v:v[0]);selected[corner]=(j,q)
  src=np.concatenate([q for _,q in selected.values()]).astype(np.float32)
  dst=np.concatenate([marker_quad(k) for k in selected]).astype(np.float32)*scale
  if len(selected)==4:
   transform,_=cv2.findHomography(src,dst,cv2.RANSAC,3)
  else:
   affine,_=cv2.estimateAffinePartial2D(src,dst,method=cv2.LMEDS)
   transform=np.vstack([affine,[0,0,1]]) if affine is not None else None
  if transform is None:continue
  used.update(j for j,_ in selected.values())
  crop=cv2.warpPerspective(image,transform,(round(W*scale),round(H*scale)),borderValue=(255,255,255))
  pad=round(CONTEXT_MARGIN*scale)
  context_transform=np.array([[1,0,pad],[0,1,pad],[0,0,1]],dtype=np.float64) @ transform
  context=cv2.warpPerspective(image,context_transform,(crop.shape[1]+2*pad,crop.shape[0]+2*pad),borderValue=(255,255,255))
  center=cv2.perspectiveTransform(np.float32([[[W*scale/2,H*scale/2]]]),np.linalg.inv(transform))[0,0]
  out.append({'context_image':context,'content_frame':[pad,pad,crop.shape[1],crop.shape[0]],'group':base//4+1,'position':(float(center[1]),float(center[0])),'image':crop,'marker_ids':[base+k for k in sorted(selected)],'inferred_corners':4-len(selected)})
 return sorted(out,key=lambda work:work['position'])
