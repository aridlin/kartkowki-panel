"""Kartkówka thresholds from the supplied school scan; teacher resolved 35% as 2-."""
from decimal import Decimal


def grade(points, maximum, grade_35="2-"):
    points, maximum = Decimal(str(points)), Decimal(str(maximum))
    if maximum <= 0 or points < 0 or points > maximum:
        raise ValueError("Invalid points")
    percent = points * 100 / maximum
    if percent == 35:
        return "2-"
    for lower, label in (
        (97, "5"), (90, "5-"), (87, "4+"), (80, "4"), (75, "4-"),
        (70, "3+"), (60, "3"), (55, "3-"), (50, "2+"), (40, "2"),
        (35, "2-"), (0, "1"),
    ):
        if percent >= lower:
            return label
    raise AssertionError("unreachable")


def percent(points, maximum):
    return round(float(Decimal(str(points)) * 100 / Decimal(str(maximum))), 2)

# Verified statutes, fetched 2026-10-14. ZS 33's 34% gap uses the teacher's
# explicit interpretation: exactly 34% -> 1, anything greater -> at least 2.
PROFILES = {
    'sp263': {'id':'sp263','name':'SP 263 · punktowane prace pisemne',
              'source':'https://www.sp263.waw.pl/images/2026.02.05_STATUT_AKTUALNY.pdf',
              'reference':'Statut 05.02.2026, §60 ust.9, str.43',
              'description':'1: poniżej 31%; 2: od 31%; 3: od 51%; 4: od 75%; 5: od 91%; 6: 100%.',
              'bands':[(0,'1'),(31,'2'),(51,'3'),(75,'4'),(91,'5'),(100,'6')]},
    'zs33-tech': {'id':'zs33-tech','name':'ZS 33 · Technikum nr 6',
                  'source':'https://www.zs33.pl/images/AKTUALNOSCI/2023_2024/PDF/statut%20T%20nr%206.pdf',
                  'reference':'Statut 07.03.2024, §127 ust.5, str.123',
                  'description':'1: do 34% włącznie; 2: powyżej 34%; 3: od 55%; 4: od 75%; 5: od 93%; 6: 100% podstawy i minimum połowa punktów zadania dodatkowego.',
                  'bands':[(0,'1'),(34,'2'),(55,'3'),(75,'4'),(93,'5')]},
    'zs33-bs': {'id':'zs33-bs','name':'ZS 33 · Branżowa Szkoła I stopnia nr 7',
                'source':'https://www.zs33.pl/images/AKTUALNOSCI/2023_2024/PDF/Statut%20BS1S%20nr%207.pdf',
                'reference':'Statut BS I stopnia nr 7, skala punktowanych prac pisemnych',
                'description':'1: do 34% włącznie; 2: powyżej 34%; 3: od 55%; 4: od 75%; 5: od 93%; 6: 100% podstawy i minimum połowa punktów zadania dodatkowego.',
                'bands':[(0,'1'),(34,'2'),(55,'3'),(75,'4'),(93,'5')]},
}

def class_profile(class_name):
    import re
    text=class_name.casefold()
    if 'bsisnr7' in text or 'bsis nr 7' in text:return 'zs33-bs'
    if 'tnr6' in text or 'technikum' in text or 'zs 33' in text or 'zs33' in text:return 'zs33-tech'
    if '263' in text or re.fullmatch(r'[1-8][a-z]',text.strip()):return 'sp263'
    return ''

def school_grade(points, maximum, profile, bonus_points=0, bonus_maximum=0):
    from fractions import Fraction
    if profile not in PROFILES:raise ValueError('Wybierz szkołę / skalę oceniania tej kartkówki')
    p,m,b,bm=[Fraction(str(x)) for x in (points,maximum,bonus_points,bonus_maximum)]
    if m<=0 or not 0<=p<=m or not 0<=b<=bm:raise ValueError('Nieprawidłowa punktacja')
    ratio=p*100/m
    if profile=='sp263':
        return next(label for lower,label in reversed(PROFILES[profile]['bands']) if ratio>=lower)
    if ratio<=34:return '1'
    if p==m and bm>0 and b*2>=bm:return '6'
    return next(label for lower,label in reversed(PROFILES[profile]['bands']) if ratio>=lower)
