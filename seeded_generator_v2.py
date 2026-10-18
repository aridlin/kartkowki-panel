"""Seed protocol 9102: three scored tasks, with one or more independently keyed parts.

V1 remains frozen. Candidate domains and criteria live in the source recipe, never
in the barcode. Sampling is a SHA256 counter stream, independent of Python random.
"""
import copy,hashlib,re
from fractions import Fraction
from seeded_generator import canonical,recipe_id,recipe_hash,RandomV1,evaluate,expression_text,validate_template
VERSION=2;TAG='9102'
class RandomV2(RandomV1):
 def __init__(self,seed,group,task,part):self.key=f'kartkowki-v2:{seed}:{group}:{task}:{part}:'.encode();self.counter=0

def barcode(recipe,seed,group):
 if type(seed) is not int or not 0<=seed<2**32 or type(group) is not int or not 1<=group<=60:raise ValueError('Invalid seed/group')
 body=f'{group:03d}{TAG}{recipe_id(recipe):013d}{seed:010d}'
 return body+f'{98-int(body+"00")%97:02d}'
def decode(code):
 if not isinstance(code,str) or not re.fullmatch(r'[0-9]{32}',code) or code[3:7]!=TAG or int(code)%97!=1:raise ValueError('Invalid v2 seed barcode/checksum')
 result={'version':2,'group':int(code[:3]),'recipe_id':int(code[7:20]),'seed':int(code[20:30])}
 if not 1<=result['group']<=60 or result['recipe_id']>=2**40 or result['seed']>=2**32:raise ValueError('Invalid barcode fields')
 return result

def mixed(q):
 sign='−' if q<0 else '';whole,rem=divmod(abs(q.numerator),q.denominator)
 return sign+(str(whole) if not rem else (f'{whole} {rem}/{q.denominator}' if whole else f'{rem}/{q.denominator}'))
def accepted(q,criteria):
 kind=criteria['answer_kind']
 if kind not in ['integer','proper_fraction','mixed','rational']:raise ValueError('Invalid answer criterion')
 if kind=='integer' and q.denominator!=1:return False
 if kind=='proper_fraction' and not 0<abs(q)<1:return False
 if kind=='mixed' and not (abs(q)>1 and q.denominator>1):return False
 if not Fraction(str(criteria['min_abs']))<=abs(q)<=Fraction(str(criteria['max_abs'])):return False
 if q.denominator>criteria['max_denominator']:return False
 return criteria['sign']=='any' or criteria['sign']=='negative' and q<0 or criteria['sign']=='positive' and q>0

def validate_recipe(recipe):
 if recipe.get('version')!=2 or recipe.get('mode')!='candidate_domains' or type(recipe.get('count')) is not int or not 1<=recipe.get('count',0)<=60:raise ValueError('Invalid v2 recipe')
 ids=recipe.get('document_identities',{})
 if ids:
  identities=[ids['bundle'],ids['key']]+ids['groups'][:recipe['count']]
  if len(ids['groups'])<recipe['count'] or len(set(identities))!=len(identities) or any(not re.fullmatch(r'@\$[0-9A-F]{32}',identity) for identity in identities):raise ValueError('Invalid historical document identities')
 if len(recipe['templates'])!=3:raise ValueError('Exactly three scored tasks required')
 for task in recipe['templates']:
  if task['max_points'] not in [3,4] or not 1<=len(task['parts'])<=2:raise ValueError('Invalid scoring/parts')
  if sum(p['max_points'] for p in task['parts'])!=task['max_points']:raise ValueError('Part maxima do not add up')
  for part in task['parts']:
   if len(part['candidates'])<recipe['count']:raise ValueError('Insufficient unique candidates')
   for tree in part['candidates']:
    validate_template(tree)
    if not accepted(evaluate(tree),part['criteria']):raise ValueError('Candidate violates source criteria')
 return recipe

def groups_from_seed(recipe,seed,through=None):
 validate_recipe(recipe)
 if type(seed) is not int or not 0<=seed<2**32:raise ValueError('Invalid seed')
 through=recipe['count'] if through is None else through
 if not 1<=through<=recipe['count']:raise ValueError('Invalid group')
 seen=set();groups=[]
 for group in range(1,through+1):
  tasks=[]
  for ti,template in enumerate(recipe['templates'],1):
   parts=[]
   for pi,domain in enumerate(template['parts'],1):
    rng=RandomV2(seed,group,ti,pi)
    for _ in range(10000):
     tree=domain['candidates'][rng.below(len(domain['candidates']))];signature=canonical(tree)
     if signature in seen:continue
     seen.add(signature);q=evaluate(tree)
     parts.append({'label':domain.get('label',''),'expression':copy.deepcopy(tree),'expression_text':expression_text(tree),'answer_numerator':q.numerator,'answer_denominator':q.denominator,'answer_mixed':mixed(q),'max_points':domain['max_points'],'division_style':domain.get('division_style','fraction'),'rubric':domain['rubric']});break
    else:raise ValueError('Cannot draw unique task')
   task=copy.deepcopy(parts[0]);task.update(parts=parts,max_points=template['max_points'],rubric=template['rubric'],source_type='seed-v2')
   task['expression_text']='; '.join((p['label']+') ' if p['label'] else '')+p['expression_text'] for p in parts)
   tasks.append(task)
  code=barcode(recipe,seed,group)
  groups.append({'group':group,'barcode_value':code,'submission_id':code,'marker_ids':list(range((group-1)*4,group*4)),'document_identity':recipe.get('document_identities',{}).get('groups',['']*recipe['count'])[group-1],'tasks':tasks})
 return groups

def manifest(recipe,seed):
 return {'schema_version':3,'quiz_id':hashlib.sha256(canonical({'recipe':recipe_hash(recipe),'seed':seed})).hexdigest()[:32],'title':recipe['title'],'created_date':recipe['created_date'],'set_number':1,'class_name':recipe.get('class_name',''),'instruction':recipe['instruction'],'barcode_format':'CODE128','aruco_dictionary':'DICT_5X5_250','document_identities':recipe.get('document_identities',{}),'generation':{'version':2,'recipe_id':recipe_id(recipe),'recipe_sha256':recipe_hash(recipe),'seed':seed,'recipe':recipe},'groups':groups_from_seed(recipe,seed)}
def verify_manifest(meta):
 gen=meta['generation'];recipe=gen['recipe']
 if gen['recipe_sha256']!=recipe_hash(recipe) or gen['recipe_id']!=recipe_id(recipe):raise ValueError('Changed original recipe')
 if meta.get('document_identities',{})!=recipe.get('document_identities',{}):raise ValueError('Changed document identities')
 expected=groups_from_seed(recipe,gen['seed']);by_group={g['group']:g for g in expected}
 for actual in meta['groups']:
  original=by_group[actual['group']]
  if actual['barcode_value']!=original['barcode_value'] or actual['document_identity']!=original['document_identity']:raise ValueError('Changed work identity')
  if len(actual['tasks'])!=3:raise ValueError('Incomplete tasks')
  for task,rebuilt in zip(actual['tasks'],original['tasks']):
   for field in ['parts','max_points','rubric','expression','answer_numerator','answer_denominator']:
    if task[field]!=rebuilt[field]:raise ValueError('Questions/key differ from seed')
def reconstruct(code,recipe):
 fields=decode(code)
 if fields['recipe_id']!=recipe_id(recipe):raise ValueError('Different original source required')
 if fields['group']>recipe['count']:raise ValueError('Group is outside this source recipe')
 result=manifest(recipe,fields['seed']);result['groups']=[result['groups'][fields['group']-1]];return result
