"""Uniform candidate domains matching exercises 4b p14, 2f/h p16, 3c/d p17.
No pupil data. Assessment barcodes are sufficient; no secondary document barcodes are printed.
"""
import json,sys,secrets,itertools,math
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from seeded_generator import evaluate

def value(q):q=F(q);return {'op':'value','n':q.numerator,'d':q.denominator}
def op(name,a,b):return {'op':name,'a':a,'b':b}
def paren(a):return {'op':'paren','a':a}
def unique(items):
 result={json.dumps(tree,sort_keys=True):tree for tree in items}
 return [result[k] for k in sorted(result)]
def build(identities=None,count=32):
 integers=[];coprime=[];common=[];mixed_c=[];mixed_d=[]
 for a,b,c,d in itertools.product(range(2,10),range(2,10),range(2,13),range(2,6)):
  q=F(a+b+c,d)
  if q.denominator==1 and 3<=q<=10:
   tree=op('div',paren(op('add',paren(op('sub',value(a),paren(value(-b)))),value(c))),value(d));assert evaluate(tree)==q;integers.append(tree)
 for d1,d2 in [(5,11),(5,13),(7,11)]:
  for n1,n2 in itertools.product(range(1,d1),range(1,d2)):
   a,b=F(n1,d1),F(n2,d2)
   if a.denominator==d1 and b.denominator==d2 and -F(3,4)<=a-b<=-F(1,20):
    tree=op('sub',value(a),value(b));assert evaluate(tree)==a-b;coprime.append(tree)
 for d2 in [15,25,35]:
  for n1,n2 in itertools.product([1,3,7,9],range(1,d2)):
   a,b=F(n1,10),F(n2,d2)
   if b.denominator==d2 and -F(3,4)<=a-b<=-F(1,20):
    tree=op('sub',value(a),value(b));assert evaluate(tree)==a-b;common.append(tree)
 for whole in range(1,9):
  for d1,d2 in [(4,2),(3,2),(6,3),(8,4)]:
   for n1,n2 in itertools.product(range(1,d1),range(1,d2)):
    a,b=F(n1,d1),F(n2,d2)
    if a.denominator==d1 and b.denominator==d2 and a>b:
     x,y=whole+a,whole+1+b;tree=op('sub',value(x),value(y));assert evaluate(tree)==x-y;mixed_c.append(tree)
 for w1,w2,n1,n2 in itertools.product(range(1,4),range(1,4),[1,3],[1,2]):
  a,b=-w1-F(n1,4),w2+F(n2,3);tree=op('sub',value(a),value(b));assert evaluate(tree)==a-b;mixed_d.append(tree)
 def part(label,items,kind,maximum,maxden,sign,points=2,style='fraction'):
  return {'label':label,'candidates':unique(items),'criteria':{'answer_kind':kind,'min_abs':0,'max_abs':maximum,'max_denominator':maxden,'sign':sign},'max_points':points,'division_style':style,'rubric':'1 pkt za poprawne przekształcenia i wspólny mianownik; 1 pkt za poprawne obliczenia i skrócony wynik.'}
 p1=part('',integers,'integer',10,1,'positive',3,'inline');p1['rubric']='1 pkt za odjęcie liczby ujemnej; 1 pkt za obliczenie nawiasów; 1 pkt za poprawne dzielenie i wynik.'
 templates=[{'max_points':3,'rubric':p1['rubric'],'parts':[p1]}, {'max_points':4,'rubric':'Podpunkty a i b po 2 pkt: po 1 pkt za wspólny mianownik oraz poprawny, skrócony wynik. Oceniaj oba podpunkty osobno i zsumuj.','parts':[part('a',coprime,'proper_fraction',1,91,'negative'),part('b',common,'proper_fraction',1,70,'negative')]}, {'max_points':4,'rubric':'Podpunkty a i b po 2 pkt: po 1 pkt za poprawne przekształcenia liczb mieszanych i znak oraz za poprawny skrócony wynik. Oceniaj oba osobno i zsumuj.','parts':[part('a',mixed_c,'proper_fraction',1,8,'negative'),part('b',mixed_d,'mixed',8,12,'negative')]}]
 return {'version':2,'mode':'candidate_domains','edition':secrets.token_hex(8),'count':count,'title':'Działania na liczbach','class_name':'1bb BSISnr7','created_date':'2026-10-18','instruction':'Oblicz i skróć wyniki. Ułamki niewłaściwe zapisz jako liczby mieszane.','source_exercises':['ćw. 4b, s. 14','ćw. 2f i 2h, s. 16','ćw. 3c i 3d, s. 17'],'uniformity':{'same_structure_every_group':True,'points':[3,4,4],'parts':[1,2,2],'task1':'Wszystkie liczby całkowite; odjęcie ujemnej, dodanie i dokładne dzielenie; wynik 3..10.','task2a':'Odejmowanie właściwych, dodatnich, skróconych ułamków o względnie pierwszych mianownikach; ujemny wynik właściwy.','task2b':'Odejmowanie właściwych dodatnich ułamków; mianowniki mają NWD 5 i NWW 30..70; ujemny wynik właściwy.','task3a':'Dodatnia liczba mieszana minus większa dodatnia liczba mieszana; wynik ujemny właściwy, NWW 4..8.','task3b':'Ujemna liczba mieszana minus dodatnia liczba mieszana; mianowniki 4 i 3, wynik ujemny mieszany.'},'document_identities':{'bundle':identities['Dzialania_na_liczbach_1bb.pdf'],'key':identities['Klucz_odpowiedzi_1bb.pdf'],'groups':[identities[f'group-{i:03d}.pdf'] for i in range(1,count+1)]} if identities else {},'templates':templates}
if __name__=='__main__':
 identities=json.loads(Path(sys.argv[1]).read_text());recipe=build(identities);Path(sys.argv[2]).write_text(json.dumps(recipe,ensure_ascii=False,indent=2));print('Candidate counts:',[[len(p['candidates']) for p in t['parts']] for t in recipe['templates']])
