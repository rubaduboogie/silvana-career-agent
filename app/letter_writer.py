import re


PROOFS = {
    'video': (
        'В работе с AI-видео веду полный цикл: идея, визуальная концепция, '
        'раскадровка, генерация, анимация и финальная сборка.',
        ['Невозможный Таиланд', 'CHROME VANITY / Tommy Cash'],
    ),
    'brand': (
        'Умею переводить задачи бренда в цельную визуальную систему, '
        'а не в набор разрозненных генераций.',
        ['Солярис — B2B visual system', 'Farming Utopia'],
    ),
    'social': (
        'Для коротких форматов учитываю хук, удержание, монтажную динамику '
        'и адаптацию идеи под вертикальный экран.',
        ['Невозможный Таиланд', 'Kid Cudi — Ride Ride'],
    ),
    'design': (
        'Опыт в web- и коммуникационном дизайне помогает мне удерживать '
        'типографику, композицию и логику пользовательского восприятия.',
        ['Солярис — B2B visual system'],
    ),
    'art': (
        'Сильная сторона — разработка выразительного художественного мира '
        'с консистентным персонажем, светом и визуальным языком.',
        ['Dreamcore — Are You Experienced?', 'CHROME VANITY / Tommy Cash'],
    ),
}

SIGNALS = {
    'video': (
        'video', 'видео', 'motion', 'ролик', 'reels', 'seedance',
        'veo', 'kling', 'storyboard', 'раскадров'
    ),
    'brand': (
        'brand', 'бренд', 'campaign', 'кампан', 'key visual',
        'visual system', 'коммуникац'
    ),
    'social': (
        'social', 'соцсет', 'reels', 'shorts', 'tiktok',
        'контент', 'viral', 'вертикальн'
    ),
    'design': (
        'design', 'дизайн', 'figma', 'photoshop', 'illustrator',
        'landing', 'web', 'типограф'
    ),
    'art': (
        'art director', 'арт-директор', 'fashion', 'editorial',
        'cinematic', 'кинематограф', 'concept', 'концепт'
    ),
}

TOOL_NAMES = (
    'Midjourney', 'Seedance', 'Veo', 'Kling', 'ChatGPT',
    'Figma', 'Photoshop', 'Illustrator'
)


def _clean(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def _matched_tools(description):
    lower = description.lower()
    return [tool for tool in TOOL_NAMES if tool.lower() in lower]


def _selected_proofs(description):
    lower = description.lower()
    selected = []
    for key, words in SIGNALS.items():
        if any(word in lower for word in words):
            selected.append(key)
    return selected[:2] or ['video', 'brand']


def _responsibility_phrase(description):
    candidates = [
        ('раскадров', 'раскадровкой и визуальным сторителлингом'),
        ('key visual', 'разработкой key visual'),
        ('motion', 'созданием motion- и video-контента'),
        ('reels', 'созданием коротких вертикальных роликов'),
        ('соцсет', 'контентом для социальных сетей'),
        ('бренд', 'развитием визуального языка бренда'),
        ('concept', 'визуальными концепциями'),
        ('концепт', 'визуальными концепциями'),
        ('дизайн', 'дизайном и визуальной коммуникацией'),
    ]
    lower = description.lower()
    for signal, phrase in candidates:
        if signal in lower:
            return phrase
    return 'AI-креативом и визуальным контентом'


def build_cover_letter(vacancy, profile):
    name = _clean(vacancy.get('name')) or 'указанная роль'
    employer = _clean(
        (vacancy.get('employer') or {}).get('name')
        if isinstance(vacancy.get('employer'), dict)
        else vacancy.get('employer')
    ) or 'ваша компания'
    description = _clean(
        vacancy.get('full_description')
        or (vacancy.get('snippet') or {}).get('requirement')
        or ''
    )

    proof_keys = _selected_proofs(description)
    proof_lines = []
    projects = []
    for key in proof_keys:
        line, examples = PROOFS[key]
        proof_lines.append(line)
        projects.extend(examples)

    allowed_projects = set(profile.get('projects') or [])
    projects = [
        project for project in dict.fromkeys(projects)
        if project in allowed_projects
    ][:3]

    tools = _matched_tools(description)
    tools_text = ', '.join(tools[:5]) if tools else (
        'Midjourney, Seedance, Veo, Kling и ChatGPT'
    )
    task = _responsibility_phrase(description)

    paragraphs = [
        (
            f'Здравствуйте! Меня заинтересовала вакансия «{name}» '
            f'в {employer}. Вижу, что в роли важна работа с {task}; '
            'это напрямую совпадает с моей специализацией.'
        ),
        (
            'Я AI-креатор и визуальный дизайнер. '
            + ' '.join(proof_lines)
            + f' В рабочем пайплайне использую {tools_text}.'
        ),
    ]

    if projects:
        paragraphs.append(
            'В качестве релевантных примеров могу показать: '
            + ', '.join(projects)
            + '.'
        )

    paragraphs.append(
        'Не приписываю себе чужой опыт и буду рада предметно обсудить '
        'задачи, формат работы и ожидаемый результат.'
    )
    return '\n\n'.join(paragraphs)
