# Деплой на Коренёво (дом)

Сервер освобождён 03.09.2026: контент-завод удалён (`docker compose down`), автопилот
выключен — RAM available ~2.16 ГБ, контейнеров 0. Подробности:
`02 — Инциденты и решения/Инцидент — Контент-завод и Freelance Autopilot выключены (03.09.2026)`.

## Порядок запуска

1. **Туннель к Telegram** (обязательно! api.telegram.org из РФ заблокирован):

   ```bash
   sudo cp scripts/telegram-tunnel.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now telegram-tunnel
   ```

   Проверка:
   ```bash
   curl -x socks5h://127.0.0.1:1082 https://api.telegram.org/bot<TOKEN>/getMe
   ```

2. **Ключи:** скопируй `.env.example` → `.env`; заполни
   `TELEGRAM_BOT_TOKEN` (от @BotFather), `ASSEMBLYAI_API_KEY` (регистрация
   https://www.assemblyai.com — грант $50 без карты), `DEEPSEEK_API_KEY`.
   `TELEGRAM_PROXY=socks5://127.0.0.1:1082`.

3. **Запуск:**
   ```bash
   docker compose up -d --build
   docker compose logs -f bot   # смотреть старт
   ```

4. **Проверка E2E:** пришли боту voice/аудио (до 20 МБ) → дождись отчёта
   (HTML + .docx).

## RAM-бюджет Коренёво

| Сервис | ~RAM |
|---|---|
| bot (aiogram + pipeline) | 150–250 МБ |
| api (uvicorn + fastapi) | 100–150 МБ |
| autossh-туннель | <20 МБ |

Итого ~0.5 ГБ из 2.16 доступных — запас под автопилот/другие проекты.

## Ограничения v1.0.0

- Файлы до **20 МБ** (лимит Bot API). Voice-сообщения влезают; длинные записи — в v1.1.0
  через Local Bot API Server (контейнер, лимит 2 ГБ) или ссылку на файл.
- SQLite (одна БД на сервер); PostgreSQL — v1.1.0.
- Файлы хранятся `RETENTION_DAYS` (7), чистка — DELETE в БД, tmp-файлы удаляются сразу.
- Онлайн-STT: данные расшифровки уходят в AssemblyAI — дисклеймер клиенту уже в отчёте;
  для чувствительных записей — v1.3.0 (РФ-провайдер).

## Кабинет (v2.0.0-фундамент)

`http://<server>:8010/` — история заказов (JSON API `/api/orders`). Self-service
оплаты и пакеты — следующий шаг дорожной карты.