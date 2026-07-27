import yaml
from pathlib import Path

ROLE={'ai creator':22,'нейрокреатор':22,'generative':18,'ai video':20,'ai content':18,'visual concept':16,'creative producer':14,'content designer':14,'digital designer':12}
TOOLS={'midjourney':6,'seedance':6,'veo':6,'kling':6,'chatgpt':4,'figma':4,'photoshop':4,'illustrator':4,'tilda':3}
TASKS={'storyboard':6,'раскадров':6,'визуальн':6,'video':5,'видео':5,'reels':4,'concept':5,'концепт':5,'prompt':4,'creative':4}
NEG={'обязательный переезд':30,'готовность к переезду':22,'командиров':18,'sales manager':30,'менеджер по продажам':30,'backend':30,'python developer':25,'java developer':25}

def load_profile():
    return yaml.safe_load(Path('config/master_profile.yaml').read_text(encoding='utf-8'))

def score_vacancy(v,p):
    s=' '.join([v.get('name') or '',(v.get('snippet') or {}).get('requirement') or '',(v.get('snippet') or {}).get('responsibility') or '']).lower()
    score=10; reasons=[]; flags=[]
    for term,w in ROLE.items():
        if term in s: score+=w; reasons.append(f'Совпадение по роли: {term}')
    for term,w in TOOLS.items():
        if term in s: score+=w; reasons.append(f'Совпадает инструмент: {term}')
    for term,w in TASKS.items():
        if term in s: score+=w; reasons.append(f'Релевантная задача: {term}')
    for term,w in NEG.items():
        if term in s: score-=w; flags.append(f'Нежелательное требование: {term}')
    sal=v.get('salary') or {}
    if sal.get('from') and sal.get('currency')=='RUR':
        if sal['from']>=int(p.get('minimum_salary_rub',0)): score+=12; reasons.append('Зарплата соответствует цели')
        else: score-=15; flags.append('Зарплата ниже цели')
    elif not sal: flags.append('Зарплата не указана')
    schedule=((v.get('schedule') or {}).get('name') or '').lower()
    if 'удален' in schedule: score+=10; reasons.append('Удалённый формат')
    projects=['Невозможный Таиланд','Farming Utopia','Солярис — B2B visual system']
    return {'score':max(0,min(100,score)),'reasons':list(dict.fromkeys(reasons))[:8],'red_flags':list(dict.fromkeys(flags))[:6],'projects':projects}
