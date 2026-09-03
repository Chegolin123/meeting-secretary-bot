#!/usr/bin/env bash
# Бутстрап деплоя ИИ-секретаря на Коренёво (docs/DEPLOY.md).
# Запуск:  bash bootstrap_korenevo.sh
# Ключи:   экспортируй заранее или впиши в .env вручную:
#   ASSEMBLYAI_API_KEY=...  DEEPSEEK_API_KEY=...  TELEGRAM_BOT_TOKEN=...
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1/4 Туннель к api.telegram.org =="
if curl -x socks5h://127.0.0.1:1082 -s -o /dev/null --max-time 10 https://api.telegram.org; then
  echo "   OK: туннель работает (HTTP через 127.0.0.1:1082)"
else
  echo "   FAIL: туннель не отвечает — проверь: systemctl --user status telegram-tunnel"
  exit 1
fi

echo "== 2/4 .env =="
if [ ! -f .env ]; then
  cp .env.example .env
  echo "   Создан .env из .env.example — заполни ключи, затем запусти снова."
  echo "   Или экспортируй переменные и перезапусти."
  exit 0
fi
echo "   .env на месте"

echo "== 3/4 Сборка и запуск =="
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${ASSEMBLYAI_API_KEY:-}" ] && [ -n "${DEEPSEEK_API_KEY:-}" ]; then
  # ключи переданы через env — синхронизируем в .env
  grep -q "^TELEGRAM_BOT_TOKEN=$\|^TELEGRAM_BOT_TOKEN=$" .env && sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}|" .env
  sed -i "s|^ASSEMBLYAI_API_KEY=.*|ASSEMBLYAI_API_KEY=${ASSEMBLYAI_API_KEY}|" .env
  sed -i "s|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}|" .env
fi
docker compose up -d --build

echo "== 4/4 Smokе =="
sleep 8
docker compose logs bot --tail 5 || true
curl -s http://127.0.0.1:8010/health || echo "   (health недоступен — проверь docker compose ps)"
echo "Готово. Тест: отправь боту voice/аудио."