const $ = id => document.getElementById(id);

const labels = {
  new: 'Новая',
  shortlisted: 'Ручная проверка',
  ready: 'Готова',
  applied: 'Отклик',
  interview: 'Интервью',
  test_task: 'Тестовое',
  offer: 'Оффер',
  rejected: 'Отказ',
  ignored: 'Игнор',
};

const escapeHtml = value => String(value || '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;');

function list(items) {
  return (items && items.length ? items : ['Нет данных'])
    .map(item => `<li>${escapeHtml(item)}</li>`)
    .join('');
}

function salary(vacancy) {
  if (!vacancy.salary_from && !vacancy.salary_to) {
    return 'Зарплата не указана';
  }
  const parts = [];
  if (vacancy.salary_from) {
    parts.push('от ' + vacancy.salary_from.toLocaleString('ru-RU'));
  }
  if (vacancy.salary_to) {
    parts.push('до ' + vacancy.salary_to.toLocaleString('ru-RU'));
  }
  parts.push(vacancy.currency === 'RUR' ? '₽' : (vacancy.currency || ''));
  return parts.join(' ').trim();
}

async function stats() {
  const data = await fetch('/api/stats').then(response => response.json());
  ['total', 'new', 'ready', 'applied', 'interview']
    .forEach(key => $(key).textContent = data[key] || 0);
}

async function change(id, status) {
  await fetch(`/api/vacancies/${id}/status`, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status}),
  });
  await Promise.all([load(), stats()]);
}

async function authStatus() {
  const element = $('browserStatus');
  try {
    const response = await fetch('/api/browser/status');
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Ошибка');
    element.textContent = data.authorized
      ? 'HH: вход выполнен'
      : 'HH: нужно войти через облачный браузер';
    element.className = data.authorized ? 'auth-ok' : 'auth-warn';
  } catch (error) {
    element.textContent = 'Браузерный агент недоступен: ' + error.message;
    element.className = 'auth-warn';
  }
}

async function prepare(id, button) {
  button.disabled = true;
  $('msg').textContent =
    'Читаю полную вакансию, пишу письмо и заполняю форму…';

  try {
    const response = await fetch(`/api/vacancies/${id}/prepare`, {
      method: 'POST',
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Ошибка');

    if (data.status === 'ready_to_review') {
      $('msg').textContent =
        'Форма заполнена. Открой HH-браузер и нажми финальную отправку.';
    } else if (data.status === 'needs_manual') {
      $('msg').textContent =
        'Форма открыта, но HH просит проверить дополнительные поля.';
    } else {
      $('msg').textContent = data.note || 'Подготовка остановлена.';
    }

    await Promise.all([load(), stats()]);
    window.open(
      'https://browser.silvanaxrai.online/vnc.html',
      '_blank'
    );
  } catch (error) {
    $('msg').textContent = 'Ошибка подготовки: ' + error.message;
  } finally {
    button.disabled = false;
  }
}

async function load() {
  const params = new URLSearchParams({min_score: $('score').value});
  if ($('status').value) params.set('status', $('status').value);

  const data = await fetch('/api/vacancies?' + params)
    .then(response => response.json());

  $('list').innerHTML = data.items.length
    ? ''
    : '<div class="card">Вакансий пока нет.</div>';

  data.items.forEach(vacancy => {
    const card = document.createElement('article');
    card.className = 'card';

    const prep = vacancy.preparation_status || 'не подготовлен';
    const letter = vacancy.cover_letter
      ? `<details><summary>Сопроводительное</summary>
         <pre>${escapeHtml(vacancy.cover_letter)}</pre></details>`
      : '';

    card.innerHTML = `
      <div class="head">
        <div>
          <span class="badge">${escapeHtml(labels[vacancy.status] || vacancy.status)}</span>
          <h2>${escapeHtml(vacancy.name)}</h2>
          <p>${escapeHtml(vacancy.employer)} · ${escapeHtml(vacancy.area)}</p>
          <b>${escapeHtml(salary(vacancy))}</b>
          <p>${escapeHtml(vacancy.schedule)}</p>
          <p class="prep">Подготовка: ${escapeHtml(prep)}</p>
        </div>
        <div class="score">${vacancy.match_score}</div>
      </div>

      <div class="cols">
        <div class="panel">
          <h3>Почему подходит</h3>
          <ul>${list(vacancy.match_reasons)}</ul>
        </div>
        <div class="panel">
          <h3>Красные флаги</h3>
          <ul>${list(vacancy.red_flags)}</ul>
        </div>
        <div class="panel">
          <h3>Показать проекты</h3>
          <ul>${list(vacancy.recommended_projects)}</ul>
        </div>
      </div>

      ${letter}

      <div class="actions">
        <select>
          ${Object.entries(labels).map(([key, label]) =>
            `<option value="${key}" ${vacancy.status === key ? 'selected' : ''}>
              ${label}
            </option>`
          ).join('')}
        </select>
        <a href="${escapeHtml(vacancy.url)}" target="_blank">
          Вакансия ↗
        </a>
        <button class="prepare-response">
          ${vacancy.preparation_status === 'ready_to_review'
            ? 'Подготовить заново'
            : 'Подготовить отклик'}
        </button>
        <a class="button secondary"
           href="https://browser.silvanaxrai.online/vnc.html"
           target="_blank">Открыть форму</a>
      </div>
    `;

    card.querySelector('select').onchange = event =>
      change(vacancy.id, event.target.value);

    const prepareButton = card.querySelector('.prepare-response');
    prepareButton.onclick = () => prepare(vacancy.id, prepareButton);

    $('list').appendChild(card);
  });
}

async function run() {
  $('run').disabled = true;
  $('msg').textContent = 'Идёт разовый поиск…';

  try {
    const response = await fetch('/api/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        query: $('query').value.trim() || null,
        area: Number($('area').value),
        per_page: 30,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Ошибка поиска');

    $('msg').textContent =
      `Обработано ${data.processed}, сохранено ${data.saved}. ` +
      'Для полной подготовки нажми кнопку на карточке.';
    await Promise.all([load(), stats()]);
  } catch (error) {
    $('msg').textContent = 'Ошибка поиска: ' + error.message;
  } finally {
    $('run').disabled = false;
  }
}

$('run').onclick = run;
$('checkAuth').onclick = authStatus;
$('status').onchange = load;
$('score').onchange = load;

Promise.all([load(), stats(), authStatus()]);
