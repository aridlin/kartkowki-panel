"""One point per polygon; canonical A5 coordinates, shared by PDF, OCR and overlay."""
import math,io,json
import numpy as np
from PIL import Image,ImageDraw
W,H=595.2756,420.9449
def geometry(index,maximum=3):
 cy=147+index*99;x,y=52,cy+12
 if maximum==3:
  vertices=[[x+12,y],[x+24,y+23],[x,y+23]];center=[x+12,y+46/3]
  polygons=[[vertices[i],vertices[(i+1)%3],center] for i in range(3)]
 elif maximum==4:
  polygons=[[[x+dx,y+dy],[x+dx+12,y+dy],[x+dx+12,y+dy+12],[x+dx,y+dy+12]] for dy in [0,12] for dx in [0,12]]
 else:raise ValueError('Figury obsługują 3 lub 4 punkty')
 fraction=[[[82+dx,y+5+dy],[89+dx,y+5+dy],[89+dx,y+12+dy],[82+dx,y+12+dy]] for dy in [0,7] for dx in [0,7]]
 return {'maximum':maximum,'polygons_pt':polygons,'fraction_polygons_pt':fraction}
def _mask(shape,polygon,shrink=0):
 import cv2
 m=np.zeros(shape,np.uint8);cv2.fillPoly(m,[np.rint(polygon).astype(np.int32)],255)
 if shrink:m=cv2.erode(m,np.ones((shrink*2+1,shrink*2+1),np.uint8))
 return m.astype(bool)
def detect(image,tasks):
 import cv2
 gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY);h,w=gray.shape;scale=np.array([w/W,h/H]);dark=gray<155;values=[];seen=False
 for task in tasks:
  mark=task.get('grading_mark')
  if not mark:return {'confirmed':False,'present':False,'points':[],'uncertain':False}
  total=0;uncertain=False
  for polygon in mark['polygons_pt']:
   poly=np.array(polygon)*scale;allmask=_mask((h,w),poly);inside=_mask((h,w),poly,max(2,round(w/W*.8)));edge=allmask & ~inside
   # Borders distinguish a new empty grading figure from an older sheet without it.
   if not edge.any() or dark[edge].mean()<.30:uncertain=True
   else:seen=True
   ratio=float(dark[inside].mean()) if inside.any() else 0
   if ratio<=.12:point=0
   elif ratio>=.75:point=1
   else:point=0;uncertain=True
   total+=point
  for polygon in mark.get('fraction_polygons_pt',[]):
   poly=np.array(polygon)*scale;inside=_mask((h,w),poly,max(2,round(w/W*1.0)));ratio=float(dark[inside].mean()) if inside.any() else 0
   if ratio<=.12:point=0
   elif ratio>=.75:point=.25
   else:point=0;uncertain=True
   total+=point
  if total>mark['maximum']:uncertain=True
  values.append({'points':total,'uncertain':uncertain})
 confirmed=bool(seen and (any(x['points']>0 for x in values) or any(x['uncertain'] for x in values)))
 return {'confirmed':confirmed,'present':seen,'points':values,'uncertain':confirmed and (not seen or any(v['uncertain'] for v in values))}
def annotate(path,tasks,scores):
 im=Image.open(path).convert('RGB');layer=Image.new('RGBA',im.size);draw=ImageDraw.Draw(layer);sx,sy=im.width/W,im.height/H
 for task,score in zip(tasks,scores):
  whole=int(float(score));quarters=round((float(score)-whole)*4)
  polygons=task.get('grading_mark',{}).get('polygons_pt',[])[:whole]+task.get('grading_mark',{}).get('fraction_polygons_pt',[])[:quarters]
  for polygon in polygons:
   poly=[(x*sx,y*sy) for x,y in polygon];draw.polygon(poly,fill=(27,91,65,220))
 composed=Image.alpha_composite(im.convert('RGBA'),layer).convert('RGB');border=ImageDraw.Draw(composed)
 for task in tasks:
  for polygon in task.get('grading_mark',{}).get('polygons_pt',[])+task.get('grading_mark',{}).get('fraction_polygons_pt',[]):
   poly=[(x*sx,y*sy) for x,y in polygon];border.line(poly+[poly[0]],fill=(20,40,30),width=max(1,round(.7*sx)))
 out=io.BytesIO();composed.save(out,format='PNG');return out.getvalue()
