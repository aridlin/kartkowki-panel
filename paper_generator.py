from pathlib import Path
from fractions import Fraction as F
import json,uuid,random,csv,sys,os,secrets
from seeded_generator import manifest as seeded_manifest,default_recipe,fixed_manifest,verify_manifest
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parent))
from points_marks import geometry
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
from pypdf import PdfReader
SET=int(os.environ.get('QUIZ_SET','1'));COUNT=int(os.environ.get('QUIZ_COUNT','30'))
OUT=Path.cwd()/'output';TMP=OUT/'tmp'
OUT=Path(os.environ.get('QUIZ_OUT',str(OUT)))
OUT.mkdir(exist_ok=True,parents=True)
META=OUT/'zadania_i_kody.json'
for name,path in [('DV','DejaVuSans.ttf'),('DVB','DejaVuSans-Bold.ttf')]:
 font=next((base/path for base in [Path(__file__).resolve().parent/'fonts',Path('/usr/share/fonts/TTF'),Path('/usr/share/fonts/truetype/dejavu')] if (base/path).exists()),None)
 if font is None:raise RuntimeError('Missing DejaVu font')
 pdfmetrics.registerFont(TTFont(name,str(font)))
W,H=595.2756,841.8898;HH=H/2;M=22;MX,MY=24,24
DICT=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_250)
rng=random.Random(20261014+SET)
P=sorted({F(a,d) for d in range(2,11) for a in range(1,d)})
def leaf(x):return {'op':'value','n':x.numerator,'d':x.denominator}
def sub(a,b):return {'op':'sub','a':a,'b':b}
def add(a,b):return {'op':'add','a':a,'b':b}
def mul(a,b):return {'op':'mul','a':a,'b':b}
def div(a,b):return {'op':'div','a':a,'b':b}
def val(t):
 if t['op']=='value':return F(t['n'],t['d'])
 if t['op']=='paren':return val(t['a'])
 a,b=val(t['a']),val(t['b'])
 return {'sub':lambda:a-b,'add':lambda:a+b,'mul':lambda:a*b,'div':lambda:a/b}[t['op']]()
def fmt(q):
 sign='−' if q<0 else '';q=abs(q);k,r=divmod(q.numerator,q.denominator)
 return sign+(str(k) if not r else f'{k} {r}/{q.denominator}')
def plain(t):
 if t['op']=='value':
  q=F(t['n'],t['d']);return str(q.numerator) if q.denominator==1 else f'({q.numerator}/{q.denominator})'
 if t['op']=='paren':return '('+plain(t['a'])+')'
 return '('+plain(t['a'])+{'sub':' − ','add':' + ','mul':' · ','div':' / '}[t['op']]+plain(t['b'])+')'
def generate(kind,want_integer):
 for attempt in range(200000):
  if kind=='g2':
   a,b,c=rng.choices(P,k=3)
   t=sub(leaf(rng.randint(1,3)+a),{'op':'paren','a':add(leaf(-F(rng.randint(1,3))-b),leaf(c))})
  elif kind=='h2':
   a,b,c=rng.choices(P,k=3);t=sub(sub(leaf(rng.randint(1,4)+a),leaf(rng.randint(1,4)+b)),leaf(c))
  elif kind=='i2':
   a,b,c,d=rng.choices(P,k=4);t=sub(sub(leaf(a),leaf(b)),{'op':'paren','a':sub(leaf(c),leaf(d))})
  elif kind=='f':
   a,b,c,d=rng.choices(P,k=4)
   t=div(sub(leaf(a),leaf(b)),sub(leaf(c),leaf(1+d)))
  elif kind=='g':
   a,b,c,d=rng.choices(P,k=4)
   t=div(sub(leaf(rng.randint(1,3)+a),leaf(rng.randint(1,3)+b)),add(leaf(c),leaf(d)))
  else:
   a,b,c,d=rng.choices(P,k=4)
   t=div(sub(leaf(rng.randint(1,4)+a),mul(leaf(F(rng.randint(2,3))),leaf(b))),sub(mul(leaf(rng.randint(1,3)+c),leaf(d)),leaf(F(rng.randint(1,3)))))
  try:q=val(t)
  except ZeroDivisionError:continue
  if not F(1)<=abs(q)<=4 or q.denominator>9:continue
  if (q.denominator==1)!=want_integer:continue
  if kind=='f' and q<0:continue
  if kind=='g' and q>0:continue
  if t['op']=='div' and abs(val(t['b']))<F(1,8):continue
  signature=json.dumps(t,sort_keys=True)
  if signature in seen:continue
  seen.add(signature);return t,q
 raise RuntimeError('Insufficient candidates')
seen=set()
if os.environ.get('QUIZ_TEMPLATE'):
 from copy import deepcopy
 data=deepcopy(json.loads(Path(os.environ['QUIZ_TEMPLATE']).read_text()));data['quiz_id']=uuid.uuid4().hex
 if COUNT>len(data['groups']):raise ValueError('Za mało grup w szablonie')
 data['groups']=data['groups'][:COUNT]
 for number,g in enumerate(data['groups'],1):g['group']=number;g['marker_ids']=list(range((number-1)*4,number*4))
elif META.exists():data=json.loads(META.read_text())
else:
 recipe=default_recipe(SET,COUNT,os.environ.get('QUIZ_ANSWER_KIND','mixed_or_integer'))
 recipe['title']=os.environ.get('QUIZ_TITLE',recipe['title']);recipe['is_test']=os.environ.get('KARTKOWKI_SANDBOX')=='1'
 data=seeded_manifest(recipe,int(os.environ['QUIZ_SEED']) if 'QUIZ_SEED' in os.environ else secrets.randbelow(2**32))
# Preserve the quiz identity while changing barcode prefix to the requested group code.
if os.environ.get('QUIZ_TEMPLATE'):data=fixed_manifest(data)
verify_manifest(data)
if not data.get('generation'):
 for g in data['groups']:g['barcode_value']=g['submission_id']=f"{g['group']:03d}{data['quiz_id'][:12].upper()}"
data['set_number']=SET
data['is_test']=data.get('is_test',os.environ.get('KARTKOWKI_SANDBOX')=='1' or data.get('title','').startswith('TEST'))
data['layout_revision']='points-shapes-quarters-v2';data.pop('manual_grading_checkbox_pt',None)
for g in data['groups']:
 for index,task in enumerate(g['tasks']):task['max_points']=task.get('max_points',3);task['grading_mark']=geometry(index,task['max_points'])
data['title']=os.environ.get('QUIZ_TITLE','Kartkówka z ułamków zwykłych'+(' i nawiasów' if SET==2 else ''))
META.write_text(json.dumps(data,ensure_ascii=False,indent=2))
if data.get('generation'):(OUT/'recipe.json').write_text(json.dumps(data['generation']['recipe'],ensure_ascii=False,indent=2))
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
def grid(c,x,top,w,h):
 c.saveState();c.setStrokeColor(HexColor('#D8DDE2'));c.setLineWidth(.25)
 step=4*72/25.4
 for i in range(int(w/step)+1):c.line(x+i*step,top,x+i*step,top-h)
 for i in range(int(h/step)+1):c.line(x,top-i*step,x+w,top-i*step)
 c.restoreState()
def draw_work(c,g,top):
 def yy(t):return top-t
 marker_positions=[(MX,MY),(W-MX-M,MY),(W-MX-M,HH-MY-M),(MX,HH-MY-M)]
 for mid,(x,y) in zip(g['marker_ids'],marker_positions):
  pic=Image.fromarray(cv2.aruco.generateImageMarker(DICT,mid,280))
  c.drawImage(ImageReader(pic),x,yy(y+M),width=M,height=M,mask=None)
 c.setFillColorRGB(0,0,0);c.setFont('DVB',14);c.drawString(58,yy(35),'KARTKÓWKA · TEST' if data.get('is_test') else 'KARTKÓWKA')
 c.setFont('DV',10);c.drawString(58,yy(52),f'Ułamki'+(' i nawiasy' if SET==2 else ' zwykłe')+f' · Grupa {g["group"]:03d}')
 b=Code128(g['barcode_value'],barWidth=1.0,barHeight=25,quiet=True,lquiet=10,rquiet=10)
 assert b.width<=235,b.width
 bx=W-54-b.width;b.drawOn(c,bx,yy(49))
 c.setFont('DV',7.4);c.drawCentredString(bx+b.width/2,yy(61),g['barcode_value'])
 c.setFont('DV',9.5);c.drawString(58,yy(79),'Nazwisko i imię:');c.setLineWidth(.5);c.line(141,yy(81),365,yy(81))
 c.drawString(378,yy(79),'Klasa:');c.line(410,yy(81),450,yy(81));c.drawString(465,yy(79),'Ocena:');c.line(501,yy(81),537,yy(81))
 c.setFont('DV',9);c.drawString(58,yy(98),data.get('instruction','Oblicz. Wyniki zapisz jako liczby całkowite lub liczby mieszane.'))
 for i,task in enumerate(g['tasks']):
  center=147+i*99
  c.setFont('DVB',11);c.drawString(55,yy(center+4),f'{i+1}.')
  eq=box(task['expression'],13.5)
  factor=min(1,165/eq.w,79/eq.h)
  if factor<1:eq=box(task['expression'],13.5*factor)
  if 13.5*factor<9:raise ValueError('Wyrażenie jest zbyt duże do czytelnego wydruku')
  assert eq.w<=205,eq.w
  eq.draw(c,110+(170-eq.w)/2,yy(center))
  grid(c,292,yy(center-40),244,79)
  c.setStrokeColorRGB(0,0,0);c.setLineWidth(.7)
  for polygon in task['grading_mark']['polygons_pt']+task['grading_mark']['fraction_polygons_pt']:
   path=c.beginPath();path.moveTo(polygon[0][0],yy(polygon[0][1]))
   for x,y in polygon[1:]:path.lineTo(x,yy(y))
   path.close();c.drawPath(path,stroke=1,fill=0)
  c.setFont('DV',5.5);c.drawString(82,yy(center+37),'¼ pkt')
  c.setFont('DV',6.5);c.drawString(54,yy(center+46),f"/{task['max_points']} pkt")


c=canvas.Canvas(str(OUT/'Kartkowka_ulamki_30_grup.pdf'),pagesize=(W,H),invariant=bool(data.get('generation')))
c.setTitle(f'{data["title"]} · {COUNT} grup')
for page in range((COUNT+1)//2):
 draw_work(c,data['groups'][2*page],H)
 if 2*page+1<COUNT:draw_work(c,data['groups'][2*page+1],HH)
 c.setStrokeColor(HexColor('#9DA3A9'));c.setLineWidth(.5);c.setDash(4,4);c.line(18,HH,W-18,HH);c.setDash()
 c.showPage()
c.save()
# Matching compact answer key.
k=canvas.Canvas(str(OUT/'Klucz_odpowiedzi.pdf'),pagesize=(W,H),invariant=bool(data.get('generation')));k.setTitle('Klucz odpowiedzi kartkówka z ułamków')
k.setFont('DVB',14);k.drawString(35,H-38,f'Klucz odpowiedzi · {COUNT} grup')
k.setFont('DV',8);k.drawString(35,H-54,'Kartkówka z ułamków · zadania typu '+('f, g, h' if SET==1 else 'g, h, i'))
cols=[35,90,178,266,364];heads=['Grupa','Zadanie 1','Zadanie 2','Zadanie 3','Kod pracy']
k.setFont('DVB',9)
for x,t in zip(cols,heads):k.drawString(x,H-78,t)
for i,g in enumerate(data['groups']):
 top=89+i*23
 if i%2==0:k.setFillColor(HexColor('#F2F4F6'));k.rect(30,H-top-20,W-60,23,stroke=0,fill=1)
 k.setFillColorRGB(0,0,0);k.setFont('DV',9);k.drawString(cols[0],H-top-10,f'{g["group"]:02d}')
 for x,t in zip(cols[1:4],g['tasks']):
  eq=box_value(F(t['answer_numerator'],t['answer_denominator']),9);eq.draw(k,x,H-top-7)
 k.setFont('DV',7.6);k.drawString(cols[4],H-top-10,g['barcode_value'])
k.setFont('DV',7);k.drawString(35,25,'Klucz odpowiada identyfikatorom prac z dołączonego pliku CSV.');k.save()
with (OUT/'Powiazania_prac.csv').open('w',newline='',encoding='utf-8-sig') as f:
 fields=['quiz_id','submission_id','grupa','student_id','nazwisko_imie','klasa','ocena','opis','barcode_format','marker_ids']
 wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader()
 for g in data['groups']:wr.writerow({'quiz_id':data['quiz_id'],'submission_id':g['submission_id'],'grupa':g['group'],'barcode_format':'CODE128','marker_ids':','.join(map(str,g['marker_ids']))})
assert len(PdfReader(OUT/'Kartkowka_ulamki_30_grup.pdf').pages)==(COUNT+1)//2
assert len(PdfReader(OUT/'Klucz_odpowiedzi.pdf').pages)==1
assert len({g['barcode_value'] for g in data['groups']})==COUNT
assert all(len(g['tasks'])==3 for g in data['groups'])
print(f'Created {(COUNT+1)//2} pages, {COUNT} groups, {COUNT*3} tasks')
