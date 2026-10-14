"""Test statute boundaries and school routing using exact rational percentages."""
from grade_rules import school_grade,class_profile
for profile,bands in [('sp263',[(31,'1','2'),(51,'2','3'),(75,'3','4'),(91,'4','5'),(100,'5','6')]),('zs33-tech',[(55,'2','3'),(75,'3','4'),(93,'4','5')]),('zs33-bs',[(55,'2','3'),(75,'3','4'),(93,'4','5')])]:
 for boundary,before,at in bands:
  assert school_grade(str(boundary-.001),100,profile)==before
  assert school_grade(boundary,100,profile)==at
  if boundary<100:assert school_grade(str(boundary+.001),100,profile)==at
for profile in ['zs33-tech','zs33-bs']:
 assert school_grade(34,100,profile)=='1'
 assert school_grade('34.000001',100,profile)=='2'
 assert school_grade('0.34000001',1,profile)=='2'
 assert school_grade(100,100,profile)=='5'
 assert school_grade(100,100,profile,'0.499999',1)=='5'
 assert school_grade(100,100,profile,'0.5',1)=='6'
 assert school_grade('99.999',100,profile,1,1)=='5'
 assert school_grade(100,100,profile,0,0)=='5'
assert class_profile('1dt Tnr6')=='zs33-tech'
assert class_profile('2db2025 BSISnr7')=='zs33-bs'
assert class_profile('6a')=='sp263'
assert class_profile('6a SP263')=='sp263'
assert school_grade(9,9,'sp263')=='6'
assert school_grade(9,9,'zs33-tech')=='5'
assert school_grade(3,9,'sp263')=='2'
assert school_grade(3,9,'zs33-tech')=='1'
try:school_grade(1,9,'');raise AssertionError('Unknown school accepted')
except ValueError:pass
print('PASS: statute bands, exact fractional boundaries, 34% teacher rule, bonus requirements, school routing')
