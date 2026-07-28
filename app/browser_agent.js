const { chromium } = require('playwright');

const CDP_URL = process.env.CAREER_BROWSER_CDP || 'http://127.0.0.1:9222';

function out(payload) {
  process.stdout.write(JSON.stringify(payload));
}

async function getPage(browser) {
  const contexts = browser.contexts();
  if (!contexts.length) throw new Error('В Chromium нет доступного контекста');
  const context = contexts[0];
  const pages = context.pages();
  return pages[0] || await context.newPage();
}

async function isAuthorized(page) {
  await page.goto('https://hh.ru/applicant/resumes', {waitUntil: 'domcontentloaded', timeout: 45000});
  const url = page.url();
  const loginVisible = await page.locator('input[name="username"], [data-qa="account-login-input"]').first().isVisible().catch(() => false);
  const resumeVisible = await page.locator('[data-qa*="resume"], a[href*="/resume/"]').first().isVisible().catch(() => false);
  return {
    authorized: !loginVisible && !url.includes('/account/login') && (resumeVisible || url.includes('/applicant/')),
    url,
    title: await page.title()
  };
}

async function openVacancy(page, url) {
  if (!url || !/^https:\/\/(hh\.ru|[^/]+\.hh\.ru)\//i.test(url)) {
    throw new Error('Разрешены только ссылки HeadHunter');
  }
  await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 45000});
  await page.bringToFront();
  return {url: page.url(), title: await page.title()};
}

async function prepareResponse(page, url, coverLetter) {
  await openVacancy(page, url);
  const respondButton = page.locator(
    '[data-qa="vacancy-response-link-top"], [data-qa="vacancy-response-link-bottom"], a[href*="/applicant/vacancy_response"], button:has-text("Откликнуться")'
  ).first();

  if (!await respondButton.isVisible().catch(() => false)) {
    throw new Error('Кнопка «Откликнуться» не найдена. Возможно, отклик уже отправлен или HH изменил страницу.');
  }

  await respondButton.click();
  await page.waitForTimeout(1500);

  const resumeOptions = page.locator('[data-qa*="resume-title"], [data-qa*="resume-select"], input[type="radio"][name*="resume"]');
  const resumeCount = await resumeOptions.count().catch(() => 0);

  const textArea = page.locator('textarea[data-qa*="vacancy-response-letter"], textarea[name*="letter"], textarea').first();
  let letterFilled = false;
  if (coverLetter && await textArea.isVisible().catch(() => false)) {
    await textArea.fill(coverLetter);
    letterFilled = true;
  }

  const submit = page.locator('[data-qa="vacancy-response-submit-popup"], button[type="submit"]:has-text("Откликнуться"), button:has-text("Отправить")').first();
  const submitVisible = await submit.isVisible().catch(() => false);
  await page.bringToFront();

  return {
    prepared: true,
    submitted: false,
    letterFilled,
    resumeOptions: resumeCount,
    submitVisible,
    url: page.url(),
    note: 'Форма подготовлена. Финальная кнопка не нажата.'
  };
}

async function main() {
  const action = process.argv[2];
  const payload = process.argv[3] ? JSON.parse(process.argv[3]) : {};
  const browser = await chromium.connectOverCDP(CDP_URL);
  try {
    const page = await getPage(browser);
    let result;
    if (action === 'status') result = await isAuthorized(page);
    else if (action === 'open') result = await openVacancy(page, payload.url);
    else if (action === 'prepare') result = await prepareResponse(page, payload.url, payload.cover_letter || '');
    else throw new Error(`Неизвестное действие: ${action}`);
    out({ok: true, ...result});
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  out({ok: false, error: error.message});
  process.exitCode = 1;
});
