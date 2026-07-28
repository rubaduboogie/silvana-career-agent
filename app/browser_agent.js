const { chromium } = require('playwright');

const CDP_URL =
  process.env.CAREER_BROWSER_CDP || 'http://127.0.0.1:9222';
const clean = value => (value || '').replace(/\s+/g, ' ').trim();

function finish(payload, code = 0) {
  process.stdout.write(JSON.stringify(payload), () => process.exit(code));
}

async function contextOf(browser) {
  const context = browser.contexts()[0];
  if (!context) throw new Error('Нет контекста Chromium');
  return context;
}

async function visible(locator) {
  return locator.isVisible().catch(() => false);
}

async function firstText(root, selectors) {
  for (const selector of selectors) {
    const element = root.locator(selector).first();
    if (await element.count().catch(() => 0)) {
      const value = clean(await element.textContent().catch(() => ''));
      if (value) return value;
    }
  }
  return '';
}

async function firstAttr(root, selectors, attribute) {
  for (const selector of selectors) {
    const element = root.locator(selector).first();
    if (await element.count().catch(() => 0)) {
      const value = await element.getAttribute(attribute).catch(() => null);
      if (value) return value;
    }
  }
  return null;
}

function salary(text) {
  text = clean(text);
  if (!text) return null;

  const nums = [...text.matchAll(/(\d[\d\s]*)/g)]
    .map(match => Number(match[1].replace(/\s/g, '')))
    .filter(Number.isFinite);

  const result = {
    from: null,
    to: null,
    currency: /₽|руб/i.test(text)
      ? 'RUR'
      : (/\$/i.test(text) ? 'USD' : (/€/i.test(text) ? 'EUR' : null)),
  };

  if (/от/i.test(text)) result.from = nums[0] || null;
  else if (/до/i.test(text)) result.to = nums[0] || null;
  else if (nums.length > 1) {
    result.from = nums[0];
    result.to = nums[1];
  } else if (nums[0]) {
    result.from = nums[0];
    result.to = nums[0];
  }
  return result;
}

async function auth(page) {
  await page.goto(
    'https://hh.ru/applicant/resumes',
    { waitUntil: 'domcontentloaded', timeout: 45000 }
  );
  const login = page.locator(
    'input[name="username"],[data-qa="account-login-input"]'
  ).first();

  return {
    authorized: !(await visible(login))
      && !page.url().includes('/account/login'),
    url: page.url(),
    title: await page.title(),
  };
}

async function search(page, payload) {
  const url = new URL('https://hh.ru/search/vacancy');
  url.searchParams.set('text', payload.query || 'AI Creator');
  url.searchParams.set('area', String(payload.area || 1));
  url.searchParams.set('order_by', 'publication_time');
  url.searchParams.set(
    'items_on_page',
    String(Math.min(payload.per_page || 30, 50))
  );

  await page.goto(
    url.toString(),
    { waitUntil: 'domcontentloaded', timeout: 60000 }
  );
  await page.waitForTimeout(1700);

  const captcha = page.locator(
    'text=Подтвердите, что вы не робот,iframe[src*="captcha"]'
  ).first();
  if (await visible(captcha)) {
    throw new Error(
      'HH запросил проверку. Пройди её в облачном браузере.'
    );
  }

  const cards = page.locator(
    '[data-qa="vacancy-serp__vacancy"],' +
    '[data-qa^="vacancy-serp__vacancy"],' +
    'article[data-qa*="vacancy"]'
  );
  const count = Math.min(
    await cards.count(),
    Math.min(payload.per_page || 30, 50)
  );
  const items = [];

  for (let index = 0; index < count; index++) {
    const card = cards.nth(index);
    const name = await firstText(card, [
      '[data-qa="serp-item__title-text"]',
      '[data-qa="vacancy-serp__vacancy-title"]',
      'a[href*="/vacancy/"]',
    ]);
    let href = await firstAttr(card, [
      '[data-qa="serp-item__title"]',
      '[data-qa="vacancy-serp__vacancy-title"]',
      'a[href*="/vacancy/"]',
    ], 'href');

    if (!name || !href) continue;
    if (href.startsWith('/')) href = 'https://hh.ru' + href;

    const employer = await firstText(card, [
      '[data-qa="vacancy-serp__vacancy-employer"]',
      'a[href*="/employer/"]',
    ]);
    const pay = await firstText(card, [
      '[data-qa="vacancy-serp__vacancy-compensation"]',
      '[data-qa*="compensation"]',
    ]);
    const area = await firstText(card, [
      '[data-qa="vacancy-serp__vacancy-address"]',
      '[data-qa*="address"]',
    ]);
    const format = await firstText(card, [
      '[data-qa="vacancy-serp__vacancy-work-format"]',
      '[data-qa*="work-format"]',
    ]);
    const snippet = clean((
      await card.locator(
        '[data-qa*="snippet"],' +
        '[data-qa*="requirement"],' +
        '[data-qa*="responsibility"]'
      ).allTextContents().catch(() => [])
    ).join(' '));
    const match = href.match(/\/vacancy\/(\d+)/);

    items.push({
      id: match
        ? match[1]
        : Buffer.from(href).toString('base64url').slice(0, 32),
      name,
      employer: { name: employer },
      salary: salary(pay),
      area: { name: area },
      schedule: { name: format },
      employment: { name: '' },
      alternate_url: href,
      published_at: '',
      snippet: {
        requirement: snippet,
        responsibility: '',
      },
    });
  }

  return {
    query: payload.query,
    found: items.length,
    items,
    url: page.url(),
  };
}

async function details(page, payload) {
  await page.goto(
    payload.url,
    { waitUntil: 'domcontentloaded', timeout: 60000 }
  );
  await page.waitForTimeout(1000);

  const captcha = page.locator(
    'text=Подтвердите, что вы не робот,iframe[src*="captcha"]'
  ).first();
  if (await visible(captcha)) {
    throw new Error(
      'HH запросил проверку. Пройди её в облачном браузере.'
    );
  }

  const description = await firstText(page, [
    '[data-qa="vacancy-description"]',
    '[data-qa*="vacancy-description"]',
    'main',
  ]);
  const response = page.locator(
    '[data-qa="vacancy-response-link-top"],' +
    '[data-qa="vacancy-response-link-bottom"],' +
    'a[href*="/applicant/vacancy_response"],' +
    'button:has-text("Откликнуться"),' +
    'a:has-text("Откликнуться")'
  ).first();

  const archived = await visible(
    page.locator(
      'text=Вакансия в архиве,text=Вакансия закрыта'
    ).first()
  );

  return {
    description,
    canRespond: await visible(response),
    archived,
    title: await page.title(),
    url: page.url(),
  };
}

async function chooseResume(page, resumeTitle) {
  const radios = page.locator(
    'input[type="radio"][name*="resume"],' +
    'input[type="radio"][data-qa*="resume"]'
  );
  const count = await radios.count().catch(() => 0);

  if (resumeTitle) {
    const label = page.getByText(resumeTitle, { exact: false }).first();
    if (await visible(label)) {
      await label.click().catch(() => {});
      return true;
    }
  }

  if (count === 1) {
    await radios.first().check().catch(async () => {
      await radios.first().click().catch(() => {});
    });
    return true;
  }

  if (count > 1) {
    const checked = page.locator(
      'input[type="radio"][name*="resume"]:checked,' +
      'input[type="radio"][data-qa*="resume"]:checked'
    );
    return (await checked.count().catch(() => 0)) > 0;
  }

  return true;
}

async function fillLetter(page, text) {
  const textarea = page.locator(
    'textarea[data-qa*="vacancy-response-letter"],' +
    'textarea[name*="letter"],textarea'
  ).first();
  if (await visible(textarea)) {
    await textarea.fill(text);
    return true;
  }

  const editor = page.locator(
    '[contenteditable="true"][data-qa*="letter"],' +
    '[contenteditable="true"][role="textbox"]'
  ).first();
  if (await visible(editor)) {
    await editor.fill(text).catch(async () => {
      await editor.click();
      await page.keyboard.type(text);
    });
    return true;
  }
  return false;
}

async function unansweredRequired(page) {
  return page.locator(
    'input[required]:not([type="hidden"]):not([type="checkbox"]),' +
    'textarea[required],' +
    '[aria-required="true"]'
  ).evaluateAll(elements => elements.filter(element => {
    if (element.disabled) return false;
    const value = (element.value || element.textContent || '').trim();
    if (element.type === 'radio') {
      const name = element.name;
      return name && !document.querySelector(
        `input[type="radio"][name="${CSS.escape(name)}"]:checked`
      );
    }
    return !value;
  }).length).catch(() => 0);
}

async function prepare(context, payload) {
  const page = await context.newPage();
  await page.goto(
    payload.url,
    { waitUntil: 'domcontentloaded', timeout: 60000 }
  );
  await page.waitForTimeout(800);

  const response = page.locator(
    '[data-qa="vacancy-response-link-top"],' +
    '[data-qa="vacancy-response-link-bottom"],' +
    'a[href*="/applicant/vacancy_response"],' +
    'button:has-text("Откликнуться"),' +
    'a:has-text("Откликнуться")'
  ).first();

  if (!(await visible(response))) {
    await page.close().catch(() => {});
    throw new Error(
      'Кнопка «Откликнуться» не найдена или отклик уже отправлен.'
    );
  }

  await response.click();
  await page.waitForTimeout(1400);

  const resumeSelected = await chooseResume(
    page,
    payload.resume_title || ''
  );

  for (let step = 0; step < 2; step++) {
    const textarea = page.locator(
      'textarea[data-qa*="vacancy-response-letter"],' +
      'textarea[name*="letter"],textarea'
    ).first();
    const finalButton = page.locator(
      '[data-qa="vacancy-response-submit-popup"],' +
      '[data-qa="vacancy-response-submit"],' +
      'button:has-text("Отправить отклик"),' +
      'button:has-text("Отправить")'
    ).first();

    if (await visible(textarea) || await visible(finalButton)) break;

    const next = page.locator(
      'button:has-text("Продолжить"),' +
      'button:has-text("Далее"),' +
      '[data-qa*="continue"]'
    ).first();
    if (!(await visible(next))) break;
    await next.click();
    await page.waitForTimeout(900);
  }

  const letterFilled = payload.cover_letter
    ? await fillLetter(page, payload.cover_letter)
    : false;
  const requiredUnanswered = await unansweredRequired(page);
  const finalButton = page.locator(
    '[data-qa="vacancy-response-submit-popup"],' +
    '[data-qa="vacancy-response-submit"],' +
    'button:has-text("Отправить отклик"),' +
    'button:has-text("Отправить")'
  ).first();
  const finalButtonVisible = await visible(finalButton);

  await page.bringToFront();

  const needsManual = (
    !resumeSelected ||
    requiredUnanswered > 0 ||
    !finalButtonVisible
  );

  return {
    prepared: true,
    submitted: false,
    resumeSelected,
    letterFilled,
    requiredUnanswered,
    finalButtonVisible,
    needsManual,
    preparedUrl: page.url(),
    note: needsManual
      ? 'Форма открыта, но требуется ручная проверка полей.'
      : 'Форма заполнена. Осталось проверить и нажать отправку.',
  };
}

async function focus(context, payload) {
  const pages = context.pages();
  const needle = String(payload.vacancy_id || '');
  let page = pages.find(candidate => (
    needle && candidate.url().includes(needle)
  ));

  if (!page && payload.prepared_url) {
    page = pages.find(candidate => (
      candidate.url() === payload.prepared_url
    ));
  }

  if (!page) {
    return { found: false };
  }

  await page.bringToFront();
  return { found: true, url: page.url() };
}

async function main() {
  const action = process.argv[2];
  const payload = process.argv[3]
    ? JSON.parse(process.argv[3])
    : {};
  const browser = await chromium.connectOverCDP(CDP_URL);
  const context = await contextOf(browser);

  let result;

  if (action === 'search' || action === 'details') {
    const page = await context.newPage();
    try {
      result = action === 'search'
        ? await search(page, payload)
        : await details(page, payload);
    } finally {
      await page.close().catch(() => {});
    }
  } else if (action === 'prepare') {
    result = await prepare(context, payload);
  } else if (action === 'focus') {
    result = await focus(context, payload);
  } else {
    const page = context.pages()[0] || await context.newPage();
    result = action === 'status'
      ? await auth(page)
      : (() => { throw new Error('Неизвестное действие'); })();
  }

  finish({ ok: true, ...result });
}

main().catch(error => {
  finish({ ok: false, error: error.message }, 1);
});
