const { chromium } = require('playwright');
const CDP_URL = process.env.CAREER_BROWSER_CDP || 'http://127.0.0.1:9222';
const out = x => process.stdout.write(JSON.stringify(x));
const clean = s => (s || '').replace(/\s+/g,' ').trim();

async function pageOf(browser){
  const context = browser.contexts()[0];
  if(!context) throw new Error('Нет контекста Chromium');
  return context.pages()[0] || await context.newPage();
}
async function auth(page){
  await page.goto('https://hh.ru/applicant/resumes',{waitUntil:'domcontentloaded',timeout:45000});
  const login = await page.locator('input[name="username"],[data-qa="account-login-input"]').first().isVisible().catch(()=>false);
  return {authorized:!login && !page.url().includes('/account/login'),url:page.url(),title:await page.title()};
}
function salary(text){
  text=clean(text); if(!text) return null;
  const nums=[...text.matchAll(/(\d[\d\s]*)/g)].map(m=>Number(m[1].replace(/\s/g,''))).filter(Number.isFinite);
  const r={from:null,to:null,currency:/₽|руб/i.test(text)?'RUR':(/\$/i.test(text)?'USD':(/€/i.test(text)?'EUR':null))};
  if(/от/i.test(text)) r.from=nums[0]||null;
  else if(/до/i.test(text)) r.to=nums[0]||null;
  else if(nums.length>1){r.from=nums[0];r.to=nums[1]}
  else if(nums[0]){r.from=nums[0];r.to=nums[0]}
  return r;
}
async function firstText(card, selectors){
  for(const s of selectors){
    const el=card.locator(s).first();
    if(await el.count().catch(()=>0)){
      const t=clean(await el.textContent().catch(()=>'')); if(t) return t;
    }
  } return '';
}
async function firstAttr(card, selectors, attr){
  for(const s of selectors){
    const el=card.locator(s).first();
    if(await el.count().catch(()=>0)){
      const v=await el.getAttribute(attr).catch(()=>null); if(v) return v;
    }
  } return null;
}
async function search(page,p){
  const u=new URL('https://hh.ru/search/vacancy');
  u.searchParams.set('text',p.query||'AI Creator');
  u.searchParams.set('area',String(p.area||1));
  u.searchParams.set('order_by','publication_time');
  u.searchParams.set('items_on_page',String(Math.min(p.per_page||30,50)));
  await page.goto(u.toString(),{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1800);
  const captcha=await page.locator('text=Подтвердите, что вы не робот,iframe[src*="captcha"]').first().isVisible().catch(()=>false);
  if(captcha) throw new Error('HH запросил проверку. Пройди её в облачном браузере.');
  const cards=page.locator('[data-qa="vacancy-serp__vacancy"],[data-qa^="vacancy-serp__vacancy"],article[data-qa*="vacancy"]');
  const count=Math.min(await cards.count(),Math.min(p.per_page||30,50));
  const items=[];
  for(let i=0;i<count;i++){
    const c=cards.nth(i);
    const name=await firstText(c,['[data-qa="serp-item__title-text"]','[data-qa="vacancy-serp__vacancy-title"]','a[href*="/vacancy/"]']);
    let href=await firstAttr(c,['[data-qa="serp-item__title"]','[data-qa="vacancy-serp__vacancy-title"]','a[href*="/vacancy/"]'],'href');
    if(!name||!href) continue;
    if(href.startsWith('/')) href='https://hh.ru'+href;
    const employer=await firstText(c,['[data-qa="vacancy-serp__vacancy-employer"]','a[href*="/employer/"]']);
    const pay=await firstText(c,['[data-qa="vacancy-serp__vacancy-compensation"]','[data-qa*="compensation"]']);
    const area=await firstText(c,['[data-qa="vacancy-serp__vacancy-address"]','[data-qa*="address"]']);
    const format=await firstText(c,['[data-qa="vacancy-serp__vacancy-work-format"]','[data-qa*="work-format"]']);
    const snippet=clean((await c.locator('[data-qa*="snippet"],[data-qa*="requirement"],[data-qa*="responsibility"]').allTextContents().catch(()=>[])).join(' '));
    const m=href.match(/\/vacancy\/(\d+)/);
    items.push({
      id:m?m[1]:Buffer.from(href).toString('base64url').slice(0,32),
      name, employer:{name:employer}, salary:salary(pay),
      area:{name:area}, schedule:{name:format}, employment:{name:''},
      alternate_url:href, published_at:'',
      snippet:{requirement:snippet,responsibility:''}
    });
  }
  return {query:p.query,found:items.length,items,url:page.url()};
}
async function openVacancy(page,url){
  if(!/^https:\/\/([^.]+\.)?hh\.ru\//i.test(url||'')) throw new Error('Разрешены только ссылки HH');
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000}); await page.bringToFront();
  return {url:page.url(),title:await page.title()};
}
async function prepare(page,p){
  await openVacancy(page,p.url);
  const btn=page.locator('[data-qa="vacancy-response-link-top"],[data-qa="vacancy-response-link-bottom"],a[href*="/applicant/vacancy_response"],button:has-text("Откликнуться"),a:has-text("Откликнуться")').first();
  if(!await btn.isVisible().catch(()=>false)) throw new Error('Кнопка «Откликнуться» не найдена или отклик уже отправлен.');
  await btn.click(); await page.waitForTimeout(1500);
  const ta=page.locator('textarea[data-qa*="vacancy-response-letter"],textarea[name*="letter"],textarea').first();
  let letterFilled=false;
  if(p.cover_letter && await ta.isVisible().catch(()=>false)){await ta.fill(p.cover_letter);letterFilled=true}
  await page.bringToFront();
  return {prepared:true,submitted:false,letterFilled,note:'Форма подготовлена. Финальная кнопка не нажата.',url:page.url()};
}
async function main(){
  const action=process.argv[2], payload=process.argv[3]?JSON.parse(process.argv[3]):{};
  const browser=await chromium.connectOverCDP(CDP_URL);
  try{
    const page=await pageOf(browser);
    const result=action==='status'?await auth(page):action==='search'?await search(page,payload):action==='open'?await openVacancy(page,payload.url):action==='prepare'?await prepare(page,payload):(()=>{throw new Error('Неизвестное действие')})();
    out({ok:true,...result});
  } finally {await browser.close()}
}
main().catch(e=>{out({ok:false,error:e.message});process.exitCode=1});
