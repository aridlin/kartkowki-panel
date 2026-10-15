"""Authenticated by the existing SSH transport; no public MCP listener."""
import sys,json,base64
from paper_workflow import db,init,grade_scan,safe_file,clone_quiz,start_author,publish_author,latest_scan,regenerate_work
from paper_authoring import available_models
init()
TOOLS=[{'name':'list_assessments','description':'List stored classroom assessments and their classes.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}}, {'name':'get_coded_work','description':'Read the stored key, assignment, evaluation and latest scan for one full barcode.','inputSchema':{'type':'object','properties':{'barcode':{'type':'string'}},'required':['barcode'],'additionalProperties':False}}, {'name':'grade_scanned_work','description':'Evaluate one cropped scan with the server Codex OAuth account and persist points, grade and description.','inputSchema':{'type':'object','properties':{'scan_id':{'type':'integer'}},'required':['scan_id'],'additionalProperties':False}}]
TOOLS += [
 {'name':'recreate_clean_work','description':'Recreate a clean work from its seed barcode and original source recipe, without a quiz database or model call. Returns the teacher download path.','inputSchema':{'type':'object','properties':{'barcode':{'type':'string'}},'required':['barcode'],'additionalProperties':False}},
 {'name':'list_models','description':'List models available in the server Codex OAuth session.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'get_quiz_manifest','description':'Read exact expressions, keys, point figures and grading policy for one assessment.','inputSchema':{'type':'object','properties':{'quiz_id':{'type':'string'}},'required':['quiz_id'],'additionalProperties':False}},
 {'name':'clone_quiz_for_class','description':'Create a new clean bundle with fresh codes for another class; preserve the source questions.','inputSchema':{'type':'object','properties':{'quiz_id':{'type':'string'},'class_name':{'type':'string'},'profile':{'type':'string','enum':['sp263','zs33-tech','zs33-bs']},'count':{'type':'integer'},'title':{'type':'string'},'students':{'type':'array','items':{'type':'string'}}},'required':['quiz_id','class_name','profile'],'additionalProperties':False}},
 {'name':'propose_quiz','description':'Queue a new or corrected Codex draft. Keys are independently verified and this does not publish student work.','inputSchema':{'type':'object','properties':{'instructions':{'type':'string'},'count':{'type':'integer'},'model':{'type':'string'},'source_quiz_id':{'type':'string'},'source_draft_id':{'type':'string'},'randomize':{'type':'boolean'}},'required':['instructions','count'],'additionalProperties':False}},
 {'name':'get_quiz_draft','description':'Read the status, generated expressions and exact answer key of a queued draft.','inputSchema':{'type':'object','properties':{'job_id':{'type':'string'}},'required':['job_id'],'additionalProperties':False}},
 {'name':'publish_quiz_draft','description':'Publish a verified draft as a new clean bundle for a class, with fresh work codes.','inputSchema':{'type':'object','properties':{'job_id':{'type':'string'},'class_name':{'type':'string'},'profile':{'type':'string','enum':['sp263','zs33-tech','zs33-bs']},'students':{'type':'array','items':{'type':'string'}}},'required':['job_id','class_name','profile'],'additionalProperties':False}},
]
def call(name,args):
 if name=='recreate_clean_work':
  path=regenerate_work(args['barcode']);return [{'type':'text','text':json.dumps({'path':str(path),'teacher_download_path':'papers/recreate/'+args['barcode']+'.pdf','database_required':False,'ai_required':False})}]
 if name=='list_models':return [{'type':'text','text':json.dumps(available_models())}]
 if name=='get_quiz_manifest':
  with db() as c:row=c.execute('SELECT * FROM paper_quizzes WHERE id=?',(args['quiz_id'],)).fetchone()
  if not row:raise ValueError('Unknown assessment')
  return [{'type':'text','text':json.dumps(dict(row),ensure_ascii=False)}]
 if name=='clone_quiz_for_class':return [{'type':'text','text':json.dumps(clone_quiz(args['quiz_id'],args))}]
 if name=='propose_quiz':return [{'type':'text','text':json.dumps(start_author(args))}]
 if name=='get_quiz_draft':
  with db() as c:row=c.execute('SELECT * FROM paper_author_jobs WHERE id=?',(args['job_id'],)).fetchone()
  if not row:raise ValueError('Unknown draft')
  return [{'type':'text','text':json.dumps(dict(row),ensure_ascii=False)}]
 if name=='publish_quiz_draft':return [{'type':'text','text':json.dumps(publish_author(args['job_id'],args))}]

 if name=='list_assessments':
  with db() as c:value=[dict(r) for r in c.execute('SELECT id,title,class_name FROM paper_quizzes')]
  return [{'type':'text','text':json.dumps(value,ensure_ascii=False)}]
 if name=='get_coded_work':
  with db() as c:
   work=c.execute('SELECT * FROM paper_variants WHERE barcode=?',(args['barcode'],)).fetchone()
   if not work:raise ValueError('Unknown barcode')
   assignment=c.execute('SELECT * FROM paper_assignments WHERE barcode=?',(args['barcode'],)).fetchone()
   scan=latest_scan(c,args['barcode'])
   history=[dict(r) for r in c.execute('SELECT id,received_at,status,points,maximum,grade FROM paper_scans WHERE barcode=? ORDER BY received_at DESC,occurrence DESC,id DESC',(args['barcode'],))]
  blocks=[{'type':'text','text':json.dumps({'work':dict(work),'assignment':dict(assignment) if assignment else None,'scan':dict(scan) if scan else None,'scan_history':history},ensure_ascii=False)}]
  if scan:blocks.append({'type':'image','mimeType':'image/png','data':base64.b64encode(safe_file(scan['context_path'] or scan['crop_path']).read_bytes()).decode()})
  return blocks
 if name=='grade_scanned_work':return [{'type':'text','text':json.dumps(grade_scan(int(args['scan_id'])),ensure_ascii=False)}]
 raise ValueError('Unknown tool')
initialized=False
for line in sys.stdin:
 try:
  req=json.loads(line);method=req.get('method');rid=req.get('id');result=None
  if method=='initialize':initialized=True;result={'protocolVersion':req.get('params',{}).get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'kartkowki-prace','version':'1.0.0'}}
  elif rid is None:continue
  elif not initialized:raise ValueError('Initialize first')
  elif method=='tools/list':result={'tools':TOOLS}
  elif method=='tools/call':
   try:result={'content':call(req['params']['name'],req['params'].get('arguments',{}))}
   except Exception as e:result={'isError':True,'content':[{'type':'text','text':str(e)[:400]}]}
  elif method=='ping':result={}
  else:raise ValueError('Unsupported method')
  print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result},ensure_ascii=False),flush=True)
 except Exception as e:print(json.dumps({'jsonrpc':'2.0','id':req.get('id') if 'req' in locals() else None,'error':{'code':-32603,'message':str(e)[:300]}}),flush=True)
