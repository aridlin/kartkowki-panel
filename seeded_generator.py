"""Frozen seed protocol v1. Pure stdlib: a barcode + the original recipe recreate a work.

Do not change v1 sampling/canonicalisation semantics; introduce a new protocol version.
Criteria belong in the recipe (shared source), never in the barcode or an LLM response.
"""
import argparse,copy,hashlib,json,re,secrets,sys
from fractions import Fraction
from datetime import datetime,timezone
from pathlib import Path
VERSION=1
TAG='9101'
MAX_SEED=2**32-1

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
def recipe_hash(recipe):return hashlib.sha256(canonical(recipe)).hexdigest()
def recipe_id(recipe):return int(recipe_hash(recipe)[:10],16)
def barcode(recipe,seed,group):
 if type(seed) is not int or not 0<=seed<=MAX_SEED or type(group) is not int or not 1<=group<=30:raise ValueError('Invalid seed or group')
 body=f'{group:03d}{TAG}{recipe_id(recipe):013d}{seed:010d}'
 return body+f'{98-int(body+"00")%97:02d}'
def decode(code):
 if not isinstance(code,str) or not re.fullmatch(r'[0-9]{32}',code) or code[3:7]!=TAG:raise ValueError('Not a supported v1 seed barcode (legacy codes need their original database)')
 if int(code)%97!=1:raise ValueError('Barcode checksum does not match; scan it again')
 result={'version':VERSION,'group':int(code[:3]),'recipe_id':int(code[7:20]),'seed':int(code[20:30])}
 if not 1<=result['group']<=30 or result['recipe_id']>=2**40 or result['seed']>MAX_SEED:raise ValueError('Invalid barcode fields')
 return result

class RandomV1:
 """SHA256 counter stream + rejection sampling, independent of Python's random module."""
 def __init__(self,seed,group,task):self.key=f'kartkowki-v1:{seed}:{group}:{task}:'.encode();self.counter=0
 def below(self,n):
  if n<1:raise ValueError('Empty sampling domain')
  limit=2**256-(2**256%n)
  while True:
   value=int.from_bytes(hashlib.sha256(self.key+str(self.counter).encode()).digest(),'big');self.counter+=1
   if value<limit:return value%n

def fraction(value):
 n,d=value.get('n'),value.get('d')
 if type(n) is not int or type(d) is not int or abs(n)>10000 or not 1<=d<=1000:raise ValueError('Invalid fraction in recipe')
 return Fraction(n,d)
def instantiate(node,rng,depth=0):
 if depth>10 or not isinstance(node,dict):raise ValueError('Invalid expression template')
 op=node.get('op')
 if op=='sample':
  values=node.get('values')
  if not isinstance(values,list) or not 2<=len(values)<=128:raise ValueError('A sampled number needs 2..128 explicit possible values')
  q=fraction(values[rng.below(len(values))]);return {'op':'value','n':q.numerator,'d':q.denominator}
 if op=='value':q=fraction(node);return {'op':op,'n':q.numerator,'d':q.denominator}
 if op=='paren':return {'op':op,'a':instantiate(node['a'],rng,depth+1)}
 if op not in ['add','sub','mul','div']:raise ValueError('Unsupported expression operator')
 return {'op':op,'a':instantiate(node['a'],rng,depth+1),'b':instantiate(node['b'],rng,depth+1)}
def evaluate(node):
 op=node['op']
 if op=='value':return fraction(node)
 if op=='paren':return evaluate(node['a'])
 a,b=evaluate(node['a']),evaluate(node['b'])
 return {'add':lambda:a+b,'sub':lambda:a-b,'mul':lambda:a*b,'div':lambda:a/b}[op]()
def expression_text(node):
 if node['op']=='value':return str(fraction(node)) if node['d']==1 else '('+str(fraction(node))+')'
 if node['op']=='paren':return '('+expression_text(node['a'])+')'
 return '('+expression_text(node['a'])+{'sub':' − ','add':' + ','mul':' · ','div':' / '}[node['op']]+expression_text(node['b'])+')'
def mixed(q):
 sign='−' if q<0 else '';whole,remainder=divmod(abs(q.numerator),q.denominator)
 return sign+(str(whole) if not remainder else f'{whole} {remainder}/{q.denominator}')
def accepted(answer,criteria):
 kind=criteria.get('answer_kind','mixed_or_integer')
 if kind not in ['integer','mixed_or_integer']:raise ValueError('Unknown answer criterion')
 if kind=='integer' and answer.denominator!=1:return False
 if kind=='mixed_or_integer' and answer.denominator!=1 and abs(answer)<1:return False
 if not Fraction(str(criteria.get('min_abs',0)))<=abs(answer)<=Fraction(str(criteria.get('max_abs',20))):return False
 if answer.denominator>criteria.get('max_denominator',12):return False
 sign=criteria.get('sign','any')
 if sign not in ['any','positive','negative']:raise ValueError('Unknown sign criterion')
 return sign=='any' or (sign=='positive' and answer>0) or (sign=='negative' and answer<0)
def has_sample(node):return isinstance(node,dict) and (node.get('op')=='sample' or any(has_sample(v) for v in node.values()))

def validate_template(node,depth=0):
 if depth>10 or not isinstance(node,dict):raise ValueError('Invalid expression template')
 op=node.get('op')
 if op=='sample':
  values=node.get('values')
  if not isinstance(values,list) or not 2<=len(values)<=128:raise ValueError('A sampled number needs 2..128 explicit possible values')
  for value in values:fraction(value)
 elif op=='value':fraction(node)
 elif op=='paren':validate_template(node['a'],depth+1)
 elif op in ['add','sub','mul','div']:validate_template(node['a'],depth+1);validate_template(node['b'],depth+1)
 else:raise ValueError('Unsupported expression operator')

def validate_recipe(recipe):
 if recipe.get('version')!=VERSION or recipe.get('mode') not in ['sampled','fixed']:raise ValueError('Unsupported recipe version/mode')
 if type(recipe.get('count')) is not int or not 1<=recipe['count']<=30:raise ValueError('Invalid group count')
 slots=recipe.get('templates') if recipe['mode']=='sampled' else recipe.get('groups')
 if not isinstance(slots,list) or (len(slots)!=3 if recipe['mode']=='sampled' else len(slots)!=recipe['count']):raise ValueError('Invalid task templates')
 groups=[slots] if recipe['mode']=='sampled' else [g['tasks'] for g in slots]
 for tasks in groups:
  if len(tasks)!=3:raise ValueError('Each group needs exactly three tasks')
  for task in tasks:
   if type(task.get('max_points')) is not int or task['max_points'] not in [3,4]:raise ValueError('Each task needs 3 or 4 points')
   if recipe['mode']=='sampled' and not has_sample(task['expression']):raise ValueError('New randomized tasks need sampled numbers')
   validate_template(task['expression'])
 return recipe

def groups_from_seed(recipe,seed,through=None):
 validate_recipe(recipe)
 if type(seed) is not int or not 0<=seed<=MAX_SEED:raise ValueError('Invalid seed')
 through=recipe['count'] if through is None else through
 if not 1<=through<=recipe['count']:raise ValueError('Group is outside this source recipe')
 groups=[];seen=set()
 for group in range(1,through+1):
  templates=recipe['templates'] if recipe['mode']=='sampled' else recipe['groups'][group-1]['tasks'];tasks=[]
  for slot,template in enumerate(templates,1):
   rng=RandomV1(seed,group,slot)
   for attempt in range(10000):
    tree=instantiate(template['expression'],rng)
    try:answer=evaluate(tree)
    except ZeroDivisionError:continue
    signature=canonical(tree)
    if not accepted(answer,template.get('criteria',{})):continue
    if signature in seen and recipe['mode']=='sampled':continue
    seen.add(signature)
    tasks.append({'expression':tree,'expression_text':expression_text(tree),'answer_numerator':answer.numerator,'answer_denominator':answer.denominator,'answer_mixed':mixed(answer),'max_points':template['max_points'],'rubric':template.get('rubric',''),'source_type':'seed-v1'})
    break
   else:raise ValueError(f'Criteria cannot be satisfied for group {group}, task {slot}; broaden the domains or correct the template')
  code=barcode(recipe,seed,group);groups.append({'group':group,'submission_id':code,'barcode_value':code,'marker_ids':list(range((group-1)*4,group*4)),'tasks':tasks})
 return groups

def manifest(recipe,seed):
 return {'schema_version':2,'quiz_id':hashlib.sha256(canonical({'recipe':recipe_hash(recipe),'seed':seed})).hexdigest()[:32],'title':recipe['title'],'created_date':recipe['created_date'],'set_number':recipe.get('set_number',1),'is_test':recipe.get('is_test',False),'instruction':recipe.get('instruction','Oblicz. Wyniki zapisz jako liczby całkowite lub liczby mieszane.'),'barcode_format':'CODE128','aruco_dictionary':'DICT_5X5_250','generation':{'version':VERSION,'recipe_id':recipe_id(recipe),'recipe_sha256':recipe_hash(recipe),'seed':seed,'recipe':recipe},'groups':groups_from_seed(recipe,seed)}
def fixed_manifest(meta,seed=None):
 """Freeze explicitly approved questions (e.g. a correction/clone) without mutating them."""
 recipe={'version':VERSION,'mode':'fixed','edition':secrets.token_hex(8),'count':len(meta['groups']),'title':meta['title'],'created_date':meta.get('created_date','2026-01-01'),'set_number':meta.get('set_number',1),'is_test':meta.get('is_test',False),'instruction':meta.get('instruction','Oblicz. Wyniki zapisz jako liczby całkowite lub liczby mieszane.'),'groups':[{'tasks':[{'expression':t['expression'],'max_points':t.get('max_points',3),'rubric':t.get('rubric',''),'criteria':{}} for t in g['tasks']]} for g in meta['groups']]}
 result=manifest(recipe,secrets.randbelow(2**32) if seed is None else seed)
 for key in ['parent_quiz_id','author_model','author_instructions']:
  if key in meta:result[key]=meta[key]
 return result

def verify_manifest(meta):
 generation=meta.get('generation')
 if not generation:return
 recipe=generation['recipe'];seed=generation['seed']
 if generation['recipe_sha256']!=recipe_hash(recipe) or generation['recipe_id']!=recipe_id(recipe):raise ValueError('Generation recipe has changed')
 expected=groups_from_seed(recipe,seed)
 by_group={g['group']:g for g in expected}
 for work in meta['groups']:
  original=by_group.get(work['group'])
  if not original or work['barcode_value']!=original['barcode_value']:raise ValueError('Seed barcode does not match its source')
  for actual,rebuilt in zip(work['tasks'],original['tasks']):
   for field in ['expression','answer_numerator','answer_denominator','max_points','rubric']:
    if actual.get(field,'' if field=='rubric' else None)!=rebuilt[field]:raise ValueError('Seed reconstruction differs from stored question/key')
  if len(work['tasks'])!=3:raise ValueError('Incomplete task list')

def reconstruct(code,recipe):
 fields=decode(code)
 if fields['recipe_id']!=recipe_id(recipe):raise ValueError('This barcode needs a different original generator recipe')
 if fields['group']>recipe['count']:raise ValueError('Group is outside this source recipe')
 result=manifest(recipe,fields['seed']);result['groups']=[result['groups'][fields['group']-1]];return result

def default_recipe(set_number=1,count=30,answer_kind='mixed_or_integer',edition=None,created_date=None):
 proper=sorted({Fraction(n,d) for d in range(2,11) for n in range(1,d)})
 def value(q):q=Fraction(q);return {'op':'value','n':q.numerator,'d':q.denominator}
 def sample(values):return {'op':'sample','values':[{'n':q.numerator,'d':q.denominator} for q in values]}
 def operation(op,a,b):return {'op':op,'a':a,'b':b}
 def sub(a,b):return operation('sub',a,b)
 def add(a,b):return operation('add',a,b)
 def mul(a,b):return operation('mul',a,b)
 def div(a,b):return operation('div',a,b)
 small=lambda:sample(proper)
 mixed_number=lambda:sample([whole+q for whole in range(1,4) for q in proper])
 if set_number==1:
  trees=[div(sub(small(),small()),sub(small(),sample([1+q for q in proper]))),div(sub(mixed_number(),mixed_number()),add(small(),small())),div(sub(mixed_number(),mul(sample([Fraction(2),Fraction(3)]),small())),sub(mul(mixed_number(),small()),sample([Fraction(1),Fraction(2),Fraction(3)])))]
 else:
  trees=[sub(mixed_number(),{'op':'paren','a':add(sample([-whole-q for whole in range(1,4) for q in proper]),small())}),sub(sub(mixed_number(),mixed_number()),small()),sub(sub(small(),small()),{'op':'paren','a':sub(small(),small())})]
 return {'version':VERSION,'mode':'sampled','edition':edition or secrets.token_hex(8),'count':count,'title':'Kartkówka z ułamków zwykłych'+(' i nawiasów' if set_number==2 else ''),'created_date':created_date or datetime.now(timezone.utc).date().isoformat(),'set_number':set_number,'instruction':'Oblicz. Wyniki zapisz jako liczby całkowite.' if answer_kind=='integer' else 'Oblicz. Wyniki zapisz jako liczby całkowite lub liczby mieszane.','templates':[{'expression':tree,'max_points':3,'rubric':'1 pkt za przekształcenia, 1 pkt za obliczenia, 1 pkt za poprawny wynik.','criteria':{'answer_kind':answer_kind,'min_abs':1,'max_abs':8 if set_number==2 else 4,'max_denominator':9,'sign':'any'}} for tree in trees]}

def main():
 parser=argparse.ArgumentParser(description='Recreate one clean work offline from its seed barcode and original generator recipe.')
 parser.add_argument('barcode');parser.add_argument('--recipe',type=Path,default=Path(__file__).with_name('recipe.json'));parser.add_argument('--output',type=Path,default=Path('recreated'));parser.add_argument('--render',action='store_true');args=parser.parse_args()
 proof=Path(__file__).with_name('SOURCE_SHA256.json')
 if proof.is_file():
  for name,expected in json.loads(proof.read_text(encoding='utf-8')).items():
   item=(proof.parent/name).resolve()
   if not item.is_relative_to(proof.parent.resolve()) or hashlib.sha256(item.read_bytes()).hexdigest()!=expected:raise ValueError('Original generator source package has changed: '+name)
 recipe=json.loads(args.recipe.read_text(encoding='utf-8'));meta=reconstruct(args.barcode,recipe);args.output.mkdir(parents=True,exist_ok=True);(args.output/'zadania_i_kody.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
 if args.render:
  import os,subprocess
  env=dict(os.environ,QUIZ_OUT=str(args.output.resolve()),QUIZ_COUNT='1',QUIZ_TITLE=meta['title'],QUIZ_SET=str(meta['set_number']))
  subprocess.run([sys.executable,str(Path(__file__).with_name('paper_generator.py'))],env=env,check=True)
  from pypdf import PdfReader,PdfWriter
  page=PdfReader(args.output/'Kartkowka_ulamki_30_grup.pdf').pages[0];page.mediabox.lower_left=(0,float(page.mediabox.height)/2);page.cropbox=page.mediabox;writer=PdfWriter();writer.add_page(page)
  with (args.output/'Arkusz.pdf').open('wb') as f:writer.write(f)
 print(json.dumps({'group':decode(args.barcode)['group'],'recipe_id':recipe_id(recipe),'output':str(args.output),'database_required':False,'ai_required':False}))
if __name__=='__main__':main()
