"""Print format v2: uniform multipart tasks, photocopy grid and assessment identities."""
from pathlib import Path
from fractions import Fraction as F
from copy import deepcopy
import json,csv,re
import cv2
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
from points_marks import geometry
W,H=595.2756,841.8898;HH=H/2
class Box:
 def __init__(self,w,h,draw):self.w,self.h,self.draw=w,h,draw

def box_value(q,s):
 q=F(q);whole,rem=divmod(abs(q.numerator),q.denominator)
 if q.denominator==1:
  txt=str(q.numerator);w=pdfmetrics.stringWidth(txt,'DV',s)
  def draw(c,x,y):c.setFont('DV',s);c.drawString(x,y-s*.33,txt)
  return Box(w,s*1.2,draw)
 ns=str(rem if whole else abs(q.numerator));ds=str(q.denominator);fs=s*.8
 fw=max(pdfmetrics.stringWidth(ns,'DV',fs),pdfmetrics.stringWidth(ds,'DV',fs))+4
 prefix=('−' if q<0 else '')+(str(whole)+' ' if whole else '')
 pw=pdfmetrics.stringWidth(prefix,'DV',s)
 def draw(c,x,y):
  c.setFont('DV',s);c.drawString(x,y-s*.33,prefix);c.setFont('DV',fs)
  c.drawCentredString(x+pw+fw/2,y+3,ns);c.drawCentredString(x+pw+fw/2,y-fs-3,ds)
  c.setLineWidth(.65);c.line(x+pw,y,x+pw+fw,y)
 return Box(pw+fw,fs*2+10,draw)
def box(t,s=13):
 if t['op']=='value':return box_value(F(t['n'],t['d']),s)
 if t['op']=='paren':
  a=box(t['a'],s);pw=pdfmetrics.stringWidth('(','DV',s*1.7)
  def draw(c,x,y):
   c.setFont('DV',s*1.7);c.drawString(x,y-s*.54,'(');a.draw(c,x+pw+2,y);c.setFont('DV',s*1.7);c.drawString(x+pw+4+a.w,y-s*.54,')')
  return Box(a.w+pw*2+6,a.h,draw)
 if t['op']=='quot':
  a,b=box(t['a'],s),box(t['b'],s);gap=s*.6;ow=pdfmetrics.stringWidth(':','DV',s)
  def draw(c,x,y):
   a.draw(c,x,y);c.setFont('DV',s);c.drawString(x+a.w+gap,y-s*.33,':');b.draw(c,x+a.w+2*gap+ow,y)
  return Box(a.w+b.w+ow+2*gap,max(a.h,b.h),draw)
 if t['op']=='div':
  a,b=box(t['a'],s*.94),box(t['b'],s*.94);w=max(a.w,b.w)+12;h=a.h+b.h+13
  def draw(c,x,y):
   a.draw(c,x+(w-a.w)/2,y+7+a.h/2);b.draw(c,x+(w-b.w)/2,y-7-b.h/2)
   c.setLineWidth(.85);c.line(x,y,x+w,y)
  return Box(w,h,draw)
 def printable(child,side):
  op=child['op'];wrap=(t['op']=='mul' and op in ['add','sub']) or (t['op']=='sub' and side=='right' and op in ['add','sub']) or (side=='right' and t['op'] in ['add','sub','mul'] and op=='value' and child['n']<0)
  return {'op':'paren','a':child} if wrap else child
 a,b=box(printable(t['a'],'left'),s),box(printable(t['b'],'right'),s);op={'sub':'−','add':'+','mul':'·'}[t['op']];gap=s*.6;ow=pdfmetrics.stringWidth(op,'DV',s)
 def draw(c,x,y):
  a.draw(c,x,y);c.setFont('DV',s);c.drawString(x+a.w+gap,y-s*.33,op);b.draw(c,x+a.w+gap+ow+gap,y)
 return Box(a.w+b.w+ow+2*gap,max(a.h,b.h),draw)

def metadata(c,title):
 c.setCreator('Kartkowki');c.setSubject('Assessment work identifiers');c.setTitle(title)
def render(data,out):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 for name,fontname in [('DV','DejaVuSans.ttf'),('DVB','DejaVuSans-Bold.ttf')]:
  font=next((p/fontname for p in [Path(__file__).parent/'fonts',Path('/usr/share/fonts/TTF'),Path('/usr/share/fonts/truetype/dejavu')] if (p/fontname).is_file()),None)
  pdfmetrics.registerFont(TTFont(name,str(font)))
 dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_250)
 for group in data['groups']:
  for i,t in enumerate(group['tasks']):t['grading_mark']=geometry(i,t['max_points'])
 def draw_work(c,g,top):
  yy=lambda y:top-y
  for mid,(x,y) in zip(g['marker_ids'],[(24,24),(W-46,24),(W-46,HH-46),(24,HH-46)]):
   image=Image.fromarray(cv2.aruco.generateImageMarker(dictionary,mid,280));c.drawImage(ImageReader(image),x,yy(y+22),22,22)
  c.setFillColorRGB(0,0,0);c.setFont('DVB',13);c.drawString(58,yy(35),'KARTKÓWKA')
  c.setFont('DV',9.5);c.drawString(58,yy(52),data['title']+' · '+f'Grupa {g["group"]:03d}')
  b=Code128(g['barcode_value'],barWidth=1,barHeight=25,quiet=True,lquiet=10,rquiet=10)
  if b.width>235:raise ValueError('Work barcode too wide')
  x=W-54-b.width;b.drawOn(c,x,yy(49));c.setFont('DV',7.2);c.drawCentredString(x+b.width/2,yy(61),g['barcode_value'])
  c.setFont('DV',9.5);c.drawString(58,yy(79),'Nazwisko i imię:');c.setLineWidth(.5);c.line(141,yy(81),365,yy(81));c.drawString(378,yy(79),'Klasa: 1bb');c.drawString(465,yy(79),'Ocena:');c.line(501,yy(81),537,yy(81))
  c.setFont('DV',8.2);c.drawString(58,yy(98),data['instruction'])
  for i,task in enumerate(g['tasks']):
   center=147+i*99;c.setFont('DVB',11);c.drawString(55,yy(center+4),str(i+1)+'.')
   for pi,part in enumerate(task['parts']):
    y=center if len(task['parts'])==1 else center-20+pi*40
    tree=deepcopy(part['expression'])
    if part.get('division_style')=='inline' and tree['op']=='div':tree['op']='quot'
    eq=box(tree,12.5);factor=min(1,170/eq.w,36/eq.h)
    if factor<1:eq=box(tree,12.5*factor)
    if 12.5*factor<9:raise ValueError('Unreadable expression')
    if part['label']:c.setFont('DV',10);c.drawString(105,yy(y+3),part['label']+')')
    eq.draw(c,130 if len(task['parts'])>1 else 115,yy(y))
   c.saveState();c.setStrokeColor(HexColor('#999999'));c.setLineWidth(.5);step=4*72/25.4;x=292;gridtop=yy(center-40)
   for line in range(int(244/step)+1):c.line(x+line*step,gridtop,x+line*step,gridtop-79)
   for line in range(int(79/step)+1):c.line(x,gridtop-line*step,x+244,gridtop-line*step)
   c.restoreState();c.setLineWidth(.7);c.setStrokeColorRGB(0,0,0)
   for polygon in task['grading_mark']['polygons_pt']+task['grading_mark']['fraction_polygons_pt']:
    path=c.beginPath();path.moveTo(polygon[0][0],yy(polygon[0][1]))
    for px,py in polygon[1:]:path.lineTo(px,yy(py))
    path.close();c.drawPath(path,stroke=1,fill=0)
   c.setFont('DV',5.5);c.drawString(82,yy(center+37),'¼ pkt');c.setFont('DV',6.5);c.drawString(54,yy(center+46),f'/{task["max_points"]} pkt')
 target=out/'Kartkowka_ulamki_30_grup.pdf';c=canvas.Canvas(str(target),pagesize=(W,H),invariant=True)
 metadata(c,data['title'])
 for index in range(0,len(data['groups']),2):
  draw_work(c,data['groups'][index],H)
  if index+1<len(data['groups']):draw_work(c,data['groups'][index+1],HH)
  c.setDash(4,4);c.setStrokeColor(HexColor('#777777'));c.setLineWidth(.5);c.line(18,HH,W-18,HH);c.setDash();c.showPage()
 c.save()
 key=canvas.Canvas(str(out/'Klucz_odpowiedzi.pdf'),pagesize=(W,H),invariant=True);metadata(key,'Klucz — '+data['title'])
 perpage=16
 for offset in range(0,len(data['groups']),perpage):
  key.setFont('DVB',14);key.drawString(35,H-35,'Klucz odpowiedzi · '+data['title']);key.setFont('DV',9);key.drawString(35,H-52,'Klasa 1bb · 11 pkt: zadanie 1 — 3 pkt; zadania 2 i 3 — po 4 pkt (2 + 2).')
  key.setFont('DVB',9)
  for x,label in [(35,'Grupa'),(90,'Zadanie 1'),(170,'Zadanie 2'),(265,'Zadanie 3'),(365,'Kod pracy')]:key.drawString(x,H-76,label)
  for row,g in enumerate(data['groups'][offset:offset+perpage]):
   top=89+row*42
   if row%2==0:key.setFillColor(HexColor('#EEEEEE'));key.rect(30,H-top-39,W-60,42,stroke=0,fill=1)
   key.setFillColorRGB(0,0,0);key.setFont('DV',9);key.drawString(35,H-top-19,f'{g["group"]:03d}')
   for x,task in zip([90,170,265],g['tasks']):
    for pi,part in enumerate(task['parts']):
     text=(part['label']+') ' if part['label'] else '')+part['answer_mixed'];key.setFont('DV',9);key.drawString(x,H-top-12-pi*17,text)
   key.setFont('DV',7);key.drawString(365,H-top-19,g['barcode_value'])
  key.showPage()
 key.save()
 (out/'zadania_i_kody.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
 (out/'recipe.json').write_text(json.dumps(data['generation']['recipe'],ensure_ascii=False,indent=2))
 with (out/'Powiazania_prac.csv').open('w',newline='',encoding='utf-8-sig') as stream:
  writer=csv.writer(stream);writer.writerow(['grupa','barcode','document_identity'])
  for g in data['groups']:writer.writerow([g['group'],g['barcode_value'],g['document_identity']])
 print(f'Created {len(data["groups"])} groups in protocol v2')
