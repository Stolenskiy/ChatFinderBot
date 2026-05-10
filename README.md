# FindChats

Telegram-бот для пошуку публічних Telegram-спільнот за назвою міста.

Проєкт використовує два різні Telegram API:
- `Telegram Bot API` для спілкування з користувачем у боті;
- `MTProto` через `Telethon` для реального пошуку public chats.

## Що вміє бот

- `/groups <city>` - шукає групи та супергрупи;
- `/channels <city>` - шукає канали, у яких є або ймовірно є linked discussion group;
- `/nextpage` - показує наступну сторінку останнього пошуку;
- можна просто надіслати назву міста текстом, і це запустить пошук груп.

Результати:
- сортуються за кількістю учасників за спаданням;
- віддаються сторінками по `100` елементів;
- для каналів показують статус:
  - `підтверджено` - discussion group підтверджена;
  - `можливо` - канал знайдено, але discussion group не вдалося підтвердити через обмеження Telegram.

## Як це працює

1. Користувач пише місто або команду `/groups Київ` / `/channels Київ`.
2. Бот одразу відповідає, що пошук запущено.
3. Фоновий worker через `Telethon` виконує `contacts.search` з кількома варіантами назви міста.
4. Знайдені результати дедуплікуються.
5. Для `/groups` повертаються групи та супергрупи.
6. Для `/channels` повертаються канали з confirmed або possible linked discussion group.
7. Результати сортуються за `members_count` і надсилаються окремим повідомленням, коли пошук завершено.

## Специфіка пошуку

Цей бот шукає спільноти **за текстовими запитами**, а не за геолокацією.

Що це означає:
- у пошук передається назва міста, наприклад `Київ`;
- система генерує кілька текстових варіантів цього слова;
- далі через `Telethon` викликається Telegram client search (`contacts.search`);
- Telegram повертає ті `public` чати, канали і групи, які вважає релевантними для цього тексту.

Пошук **не** працює так:
- не бере координати міста;
- не шукає nearby groups по GPS;
- не обходить весь Telegram глобально;
- не гарантує, що знайде всі існуючі чати міста.

На практиці це означає, що бот найкраще знаходить чати, де назва міста або схожа текстова форма присутня в:
- `title`
- `username`
- інколи в пов'язаних текстових ознаках, які віддає Telegram search

Якщо чат ніяк текстово не пов'язаний із містом або Telegram не повернув його в search, бот його не побачить.

## Обмеження

- знаходяться тільки `public` чати, які Telegram сам повертає в client search;
- приватні групи без публічного `@username` або invite link не знайдуться;
- `Bot API` сам по собі не вміє глобально шукати чати, тому потрібна MTProto-сесія звичайного Telegram-акаунта;
- пагінація зараз `in-memory`, тому після рестарту бота старі `/nextpage` не працюють;
- сортування за кількістю учасників працює тільки для тих результатів, які Telegram уже повернув у пошуку.

## Вимоги

- `Python 3.11+`
- Telegram bot token від `@BotFather`
- `API_ID` і `API_HASH` з `my.telegram.org`
- авторизована MTProto-сесія Telegram-користувача

## Налаштування Telegram

### 1. Створити бота через `@BotFather`

1. Відкрий `@BotFather`.
2. Виконай `/newbot`.
3. Задай `name`.
4. Задай `username`, який закінчується на `bot`.
5. Скопіюй `BOT_TOKEN`.

Рекомендовано також:
1. `/setdescription`
2. `/setabouttext`
3. `/setuserpic`
4. `/setcommands`

Список команд для `BotFather`:

```text
start - start the bot
help - usage help
groups - search groups by city
channels - search channels with linked groups
nextpage - next page of last search
```

### 2. Отримати `API_ID` і `API_HASH`

Це окремі дані для MTProto, не плутати з bot token.

1. Відкрий `https://my.telegram.org`.
2. Увійди своїм Telegram-акаунтом.
3. Перейди в `API development tools`.
4. Створи application.
5. Скопіюй `api_id` і `api_hash`.

## Встановлення і запуск

### 1. Підготувати середовище

У корені проєкту:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
```

Якщо `venv` або `pip` відсутні в системі:

```bash
sudo apt update
sudo apt install python3.12-venv python3-pip
```

### 2. Заповнити `.env`

Приклад:

```env
BOT_TOKEN=123456:replace_me
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace_me
TELEGRAM_SESSION_NAME=findchats_user
SEARCH_LIMIT_PER_QUERY=200
RESULT_LIMIT=100
BOT_LOG_LEVEL=INFO
BOT_LOG_DIR=logs
```

Пояснення:
- `BOT_TOKEN` - токен бота від `@BotFather`
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` - MTProto credentials
- `TELEGRAM_SESSION_NAME` - ім'я файлу сесії `*.session`
- `SEARCH_LIMIT_PER_QUERY` - скільки чатів Telegram може повернути на **кожен окремий внутрішній текстовий search query**. Це не розмір сторінки й не фінальна кількість результатів для користувача.
- `RESULT_LIMIT` - скільки результатів максимум бот залишить **після** дедуплікації, фільтрації й сортування. Саме цей ліміт впливає на загальну довжину списку, доступного для пагінації.
- `BOT_LOG_LEVEL` - рівень логування, наприклад `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `BOT_LOG_DIR` - директорія, куди пишуться лог-файли

### 3. Створити MTProto-сесію

Пошук працює від імені звичайного Telegram-акаунта, тому сесію треба авторизувати один раз.

```bash
python -m findchats.bootstrap_session
```

Далі:
1. введи номер телефону в міжнародному форматі;
2. введи код із Telegram;
3. якщо увімкнено 2FA, введи пароль.

Після цього з'явиться файл на кшталт:

```text
findchats_user.session
```

### 4. Запустити бота

```bash
python -m findchats.main
```

Якщо бот уже запущений і ти хочеш застосувати зміни:

1. зупини його через `Ctrl+C`
2. запусти знову:

```bash
source .venv/bin/activate
python -m findchats.main
```

## Як користуватись

### Пошук груп

```text
/groups Київ
```

або просто:

```text
Київ
```

Бот шукає групи і супергрупи, сортує їх за кількістю учасників і надсилає першу сторінку.

### Пошук каналів з discussion group

```text
/channels Київ
```

Бот шукає канали і намагається визначити, чи є в них linked discussion group.

Можливі стани:
- `підтверджено`
- `можливо`

### Наступна сторінка

```text
/nextpage
```

Показує наступні `100` елементів останнього пошуку цього користувача.

Важливо:
- `/nextpage` працює тільки для останнього пошуку;
- якщо після `Київ` ти шукав `Львів`, то `/nextpage` продовжить уже `Львів`.

## Формат відповіді

### Для груп

```text
1. Назва групи
Посилання на групу: https://t.me/...
Учасників: 12345
```

### Для каналів

```text
1. Назва каналу
Статус: підтверджено
Посилання на канал: https://t.me/...
Група обговорення: Назва linked group
Посилання на групу обговорення: https://t.me/...
Учасників каналу: 54321
```

Для `можливо` discussion link може бути відсутній.

## Логи

Логи пишуться:
- в консоль
- у файл `logs/YYYY-MM-DD.log`

Приклад:

```text
logs/
  2026-05-10.log
```

У логах є:
- запуск і зупинка бота;
- команди `/start`, `/help`, `/nextpage`;
- постановка пошуку в чергу;
- початок і завершення пошуку;
- порожні результати;
- кількість знайдених чатів;
- помилки `Telethon` і runtime-помилки.

## Структура проєкту

```text
src/findchats/
  bot.py
  bootstrap_session.py
  city_variants.py
  config.py
  discovery.py
  logging_setup.py
  main.py
  models.py
```

## Типові проблеми

### `MTProto session is not authorized`

Потрібно ще раз створити сесію:

```bash
python -m findchats.bootstrap_session
```

### `database is locked`

Один і той самий `.session` файл не варто використовувати одночасно з кількох процесів.

Переконайся, що бот запущений лише один раз.

### Бот довго шукає

Це очікувано, бо Telegram може давати `FloodWait` або повільно відповідати на `GetFullChannelRequest`.

Тому бот:
- одразу підтверджує запуск пошуку;
- надсилає результат окремим повідомленням, коли пошук завершено.

## Подальші покращення

1. Зберігати результати пошуку в `SQLite` або `PostgreSQL` замість `in-memory`.
2. Додати `/page <n>` і `/prevpage`.
3. Додати зовнішні джерела discovery.
4. Додати кешування `GetFullChannelRequest`.
5. Розділити в `/channels` секції `підтверджено` і `можливо`.
