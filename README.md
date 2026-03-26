# Alone Above Shop — Telegram Mini App

Чистый HTML/CSS/JS веб-апп без Node.js и Next.js.
Открывается напрямую через `index.html`.

## Файлы

| Файл | Описание |
|------|----------|
| `index.html` | Главная точка входа (открывать именно его) |
| `style.css` | Все стили — цвета, анимации, компоненты |
| `app.js` | Логика: Telegram API, корзина, каталог, галерея |
| `config.json` | **Настройки для изменения без кода** |
| `assets/logo.svg` | Логотип магазина |

## Настройка через config.json

Все визуальные данные меняются только в `config.json`:

```json
{
  "shop": {
    "name": "Название магазина",
    "logo": "assets/logo.svg"
  },
  "colors": {
    "primary": "#78E700"
  },
  "api": {
    "base_url": "https://ВАШ-API.railway.app"
  },
  "telegram": {
    "channel": "https://t.me/ВАШ_КАНАЛ",
    "support": "https://t.me/ВАШ_ПОДДЕРЖКА"
  }
}
```

## Деплой

### Railway / любой статический хостинг
1. Загрузите папку `webapp/` на хостинг
2. Укажите `index.html` как точку входа
3. В `config.json` → `api.base_url` → укажите URL вашего бота-API

### Локально (для теста)
```bash
# Простой HTTP сервер
python3 -m http.server 8080
# Откройте http://localhost:8080
```

### Подключение к Telegram боту
В боте укажите URL веб-аппа при создании кнопки:
```python
from aiogram.types import WebAppInfo, InlineKeyboardButton
btn = InlineKeyboardButton(text="🛍 Открыть магазин",
      web_app=WebAppInfo(url="https://ВАШ_САЙТ/index.html"))
```
