"""
Генератор постов для товаров с AI и публикацией ВКонтакте
Для Render: настройте переменные окружения в Dashboard → Environment
"""

from flask import Flask, render_template, request, jsonify
import requests
import json
import random
import os
import threading
import time
from datetime import datetime

app = Flask(__name__)

# ==================== НАСТРОЙКИ PROXYAPI ====================
# На Render: задайте эти переменные в Dashboard → Environment
API_KEY = os.getenv("API_KEY", "")
API_URL = os.getenv("API_URL", "https://api.proxyapi.ru/openai/v1/chat/completions")
MODEL = os.getenv("MODEL", "gpt-5.4-mini")
DEFAULT_TONE = os.getenv("DEFAULT_TONE", "дружелюбный, искренний, с лёгким юмором")
# ==================== КОНЕЦ НАСТРОЕК ====================

# ==================== НАСТРОЙКИ ВКОНТАКТЕ ====================
# Инструкцию по получению этих данных см. в файле vk_setup.md
VK_ACCESS_TOKEN = os.getenv("VK_ACCESS_TOKEN", "")
VK_OWNER_ID = os.getenv("VK_OWNER_ID", "")
# ==================== КОНЕЦ НАСТРОЕК ВК ====================

# Пути к файлам для хранения данных (без базы данных, используем JSON)
# Внимание: на Render (free) файловая система эфемерна — данные исчезают при перезапуске
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
FAVORITES_FILE = os.path.join(DATA_DIR, "favorites.json")
SCHEDULED_FILE = os.path.join(DATA_DIR, "scheduled.json")


def load_json(filepath):
    """Загружает данные из JSON файла"""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_json(filepath, data):
    """Сохраняет данные в JSON файл"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Создаём папку для данных, если её нет
os.makedirs(DATA_DIR, exist_ok=True)


def get_system_prompt(mood):
    """Возвращает системный промпт для нейросети"""

    # #COLOR# НАСТРОЙКА НАСТРОЕНИЙ: можно менять описания эмоций
    mood_descriptions = {
        "профессиональный": "Тон: экспертный, деловой, с фактами. Минимум эмодзи, максимум пользы.",
        "весёлый": "Тон: лёгкий, смешной, с хорошим юмором. Вызови улыбку и расслабь читателя.",
        "доверительный": "Тон: тёплый, мягкий, как совет друга. Вызывай доверие и спокойствие.",
        "срочный": "Тон: энергичный, с чувством срочности. Подчеркни уникальность момента.",
        "интригующий": "Тон: загадочный, с элементом недосказанности. Заставь читателя захотеть узнать больше."
    }

    # #COLOR# СТРУКТУРА ПОСТА: можно менять порядок и содержание блоков
    structure = """
Пост должен содержать:
1. 🔥 Цепляющий заголовок
2. 📝 Основной текст с эмоциями
3. 💡 Польза для покупателя (конкретная)
4. 🏷️ Хэштеги (5-8 штук, релевантные товару)
5. 📢 Призыв к действию (CTA)
"""

    return f"""Ты — профессиональный копирайтер и SMM-специалист.

Твоя задача: создать продающий пост для товара по ссылке.

{structure}

{mood_descriptions.get(mood, mood_descriptions['профессиональный'])}

Правила:
- Пиши на русском языке
- Пост должен быть оригинальным и интересным
- Используй эмодзи умеренно (2-5 штук)
- Не повторяй шаблонные фразы
- Делай пост живым и человечным
- Формат: plain text (без markdown-разметки)

Важно: ответь ТОЛЬКО готовым постом, без комментариев и пояснений."""


def generate_post_with_ai(product_url, additional_info, mood):
    """Генерирует пост с помощью ProxyAPI"""

    # Собираем описание товара для нейросети
    product_description = f"Ссылка на товар: {product_url}"
    if additional_info:
        product_description += f"\nДополнительная информация: {additional_info}"

    # #COLOR# НАСТРОЙКА ПРОМПТА: можно менять запрос к нейросети
    user_prompt = f"""Создай продающий пост для этого товара:

{product_description}

Настроение: {mood}

Сделай пост живым, оригинальным и цепляющим."""

    # Формируем запрос к API
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": get_system_prompt(mood)},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": random.uniform(0.7, 0.9),  # #COLOR# ТЕМПЕРАТУРА: креативность (0.7-0.9)
        "max_completion_tokens": 1000  # #COLOR# ДЛИНА ПОСТА: максимум токенов на выходе
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # Отправляем запрос к ProxyAPI
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        result = response.json()

        # Извлекаем текст из ответа
        post_text = result["choices"][0]["message"]["content"].strip()
        return post_text

    except requests.exceptions.RequestException as e:
        return f"Ошибка при генерации: {str(e)}"
    except (KeyError, IndexError):
        return "Ошибка: неверный формат ответа от AI"


def publish_to_vk(post_text):
    """Публикует пост в сообществе ВКонтакте"""

    if not VK_ACCESS_TOKEN or not VK_OWNER_ID:
        return False, "Не настроены данные ВК. Задайте VK_ACCESS_TOKEN и VK_OWNER_ID в Render Dashboard → Environment"

    url = "https://api.vk.com/method/wall.post"
    params = {
        "owner_id": VK_OWNER_ID,
        "from_group": 1,
        "message": post_text,
        "access_token": VK_ACCESS_TOKEN,
        "v": "5.199"  # Версия API ВК
    }

    try:
        response = requests.post(url, params=params, timeout=30)
        result = response.json()

        if "response" in result:
            post_id = result["response"]["post_id"]
            return True, f"Пост опубликован! ID поста: {post_id}"
        elif "error" in result:
            error_msg = result["error"]["error_msg"]
            return False, f"Ошибка ВК: {error_msg}"
        else:
            return False, f"Неизвестная ошибка: {str(result)}"

    except requests.exceptions.RequestException as e:
        return False, f"Ошибка соединения: {str(e)}"


def publish_scheduled_to_vk(post_text, schedule_time):
    """Создаёт отложенный пост в сообществе ВКонтакте"""

    if not VK_ACCESS_TOKEN or not VK_OWNER_ID:
        return False, "Не настроены данные ВК. Задайте VK_ACCESS_TOKEN и VK_OWNER_ID в Render Dashboard → Environment"

    # Преобразуем время в timestamp
    if isinstance(schedule_time, str):
        dt = datetime.fromisoformat(schedule_time)
    else:
        dt = schedule_time

    publish_date = int(dt.timestamp())

    url = "https://api.vk.com/method/wall.post"
    params = {
        "owner_id": VK_OWNER_ID,
        "from_group": 1,
        "message": post_text,
        "publish_date": publish_date,  # Дата публикации (timestamp)
        "access_token": VK_ACCESS_TOKEN,
        "v": "5.199"
    }

    try:
        response = requests.post(url, params=params, timeout=30)
        result = response.json()

        if "response" in result:
            post_id = result["response"]["post_id"]
            return True, f"Отложенный пост создан! ID: {post_id}, публикация: {dt.strftime('%d.%m.%Y в %H:%M')}"
        elif "error" in result:
            error_msg = result["error"]["error_msg"]
            return False, f"Ошибка ВК: {error_msg}"
        else:
            return False, f"Неизвестная ошибка: {str(result)}"

    except requests.exceptions.RequestException as e:
        return False, f"Ошибка соединения: {str(e)}"


@app.route('/')
def index():
    """Главная страница с формой"""
    return render_template('index.html')


@app.route('/generate', methods=['POST'])
def generate():
    """Обработка запроса на генерацию поста"""
    data = request.get_json()

    product_url = data.get('product_url', '').strip()
    additional_info = data.get('additional_info', '').strip()
    mood = data.get('mood', 'радостный')

    # Проверка на наличие ссылки
    if not product_url:
        return jsonify({'error': 'Добавьте ссылку на товар'})

    # Генерируем пост через AI
    post = generate_post_with_ai(product_url, additional_info, mood)

    if post.startswith("Ошибка"):
        return jsonify({'error': post})

    return jsonify({'post': post})


@app.route('/publish', methods=['POST'])
def publish():
    """Публикует пост в ВК (сейчас или отложенный)"""
    data = request.get_json()

    post_text = data.get('post_text', '').strip()
    publish_type = data.get('publish_type', 'now')  # 'now' или 'scheduled'
    schedule_time = data.get('schedule_time', '')

    if not post_text:
        return jsonify({'error': 'Нет текста для публикации'})

    if publish_type == 'now':
        # Публикуем сразу
        success, message = publish_to_vk(post_text)
    elif publish_type == 'scheduled':
        if not schedule_time:
            return jsonify({'error': 'Укажите время публикации'})

        # Проверяем, что время в будущем
        try:
            scheduled_dt = datetime.fromisoformat(schedule_time)
            if scheduled_dt <= datetime.now():
                return jsonify({'error': 'Время публикации должно быть в будущем'})
        except ValueError:
            return jsonify({'error': 'Неверный формат времени'})

        success, message = publish_scheduled_to_vk(post_text, schedule_time)

        # Сохраняем в список отложенных постов
        if success:
            scheduled_posts = load_json(SCHEDULED_FILE)
            scheduled_posts.append({
                "id": len(scheduled_posts) + 1,
                "text": post_text,
                "scheduled_time": schedule_time,
                "created_at": datetime.now().isoformat(),
                "status": "scheduled"
            })
            save_json(SCHEDULED_FILE, scheduled_posts)
    else:
        return jsonify({'error': 'Неверный тип публикации'})

    return jsonify({'success': success, 'message': message})


@app.route('/favorites', methods=['GET'])
def get_favorites():
    """Возвращает список избранных постов"""
    favorites = load_json(FAVORITES_FILE)
    return jsonify({'favorites': favorites})


@app.route('/favorites', methods=['POST'])
def add_favorite():
    """Добавляет пост в избранное"""
    data = request.get_json()
    post_text = data.get('post_text', '').strip()

    if not post_text:
        return jsonify({'error': 'Нет текста поста'})

    favorites = load_json(FAVORITES_FILE)

    # Создаём запись
    favorite_entry = {
        "id": len(favorites) + 1,
        "text": post_text,
        "saved_at": datetime.now().isoformat()
    }

    favorites.append(favorite_entry)
    save_json(FAVORITES_FILE, favorites)

    return jsonify({'success': True, 'id': favorite_entry['id'], 'message': 'Добавлено в избранное'})


@app.route('/favorites/<int:post_id>', methods=['DELETE'])
def remove_favorite(post_id):
    """Удаляет пост из избранного"""
    favorites = load_json(FAVORITES_FILE)
    favorites = [f for f in favorites if f['id'] != post_id]
    save_json(FAVORITES_FILE, favorites)

    return jsonify({'success': True, 'message': 'Удалено из избранного'})


@app.route('/scheduled', methods=['GET'])
def get_scheduled():
    """Возвращает список отложенных постов"""
    scheduled = load_json(SCHEDULED_FILE)
    return jsonify({'scheduled': scheduled})


@app.route('/scheduled/<int:post_id>', methods=['DELETE'])
def remove_scheduled(post_id):
    """Удаляет отложенный пост"""
    scheduled = load_json(SCHEDULED_FILE)
    scheduled = [s for s in scheduled if s['id'] != post_id]
    save_json(SCHEDULED_FILE, scheduled)

    return jsonify({'success': True, 'message': 'Отложенный пост удалён'})


@app.route('/check-vk')
def check_vk():
    """Проверяет, настроены ли данные ВК"""
    return jsonify({'configured': bool(VK_ACCESS_TOKEN and VK_OWNER_ID)})


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', 3000)))
