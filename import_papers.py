import sys,json,unicodedata,re,secrets
from pathlib import Path
from paper_workflow import init,db,import_bundle
init()
for folder in sys.argv[1:]:print('Imported quiz',import_bundle(folder))
roster=Path(__file__).parent/'rosters-clean.json'
if roster.exists():
 data=json.loads(roster.read_text());updated=added=0
 def norm(s):return ' '.join(sorted(re.findall(r'\w+',unicodedata.normalize('NFKC',s.casefold()))))
 with db() as c:
  for group in data:
   cls=group['class_name'];existing={norm(r['name']):r['librus_id'] for r in c.execute('SELECT * FROM roster WHERE class_name=?',(cls,))}
   for person in group['students']:
    sid=existing.get(norm(person['name']))
    if not sid:
     sid='local:'+secrets.token_hex(8);c.execute('INSERT INTO roster VALUES(?,?,?)',(cls,sid,person['name']));added+=1
    else:updated+=1
    c.execute('INSERT INTO roster_details VALUES(?,?,?,?) ON CONFLICT(class_name,student_id) DO UPDATE SET roll_no=excluded.roll_no,school=excluded.school',(cls,sid,person['roll_no'],group['school']))
 print('Roster matched',updated,'new local records',added)
