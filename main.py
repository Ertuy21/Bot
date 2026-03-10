import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from functools import wraps

# ========== НАСТРОЙКИ ==========
TOKEN = "8677410719:AAHIa1cG3wTSp0FncCS8MSJGy4-6pJMUQjc"
GROUP_CHAT_ID = -1003771060249  # ID группы
ADMIN_USERNAMES = ["Mts_mtsmtsmts", "GoodGooseGame"]  # Админы
MANAGER_USERNAME = "GoodGooseGame"  # Менеджер для оплаты
# ===============================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния
MAIN_MENU, BUY_MENU, SELL_MENU, ADMIN_MENU = range(4)
WAIT_BUY_SERVICE_REQUEST, WAIT_SELL_SERVICE_RESPONSE = range(4, 6)
WAIT_BLOCK_USER, WAIT_UNBLOCK_USER, WAIT_RESPONSE_FIX = range(6, 9)
WAIT_DELETE_REQUEST_NUMBER = range(9, 10)

# Базы данных
blocked_users = set()
pending_requests = []  # Заявки на модерации
active_requests = []   # Активные заявки (что люди ищут)
pending_responses = []  # Ответы на модерации

# Проверка на админа
def is_admin(username):
    return username and username.lower() in [a.lower() for a in ADMIN_USERNAMES]

# Клавиатуры
def main_menu_keyboard(username):
    keyboard = [
        [InlineKeyboardButton("🛒 Купить услугу", callback_data="to_buy")],
        [InlineKeyboardButton("💰 Продать услугу", callback_data="to_sell")]
    ]
    if is_admin(username):
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def buy_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔧 Создать заявку", callback_data="create_service_request")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def sell_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔧 Активные заявки", callback_data="show_service_requests")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Заявки на модерации", callback_data="admin_pending_requests")],
        [InlineKeyboardButton("💬 Ответы на модерации", callback_data="admin_pending_responses")],
        [InlineKeyboardButton("🗑 Удалить активную заявку", callback_data="admin_delete_request")],
        [InlineKeyboardButton("🚫 Заблокировать", callback_data="admin_block")],
        [InlineKeyboardButton("✅ Разблокировать", callback_data="admin_unblock")],
        [InlineKeyboardButton("◀️ Выход", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username = update.effective_user.username or "no_username"
    await update.message.reply_text(
        "👋 Привет! Хочешь купить или продать услугу?",
        reply_markup=main_menu_keyboard(username)
    )
    return MAIN_MENU

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    username = update.effective_user.username

    if data == "back_main":
        await query.edit_message_text("Выбери действие:", reply_markup=main_menu_keyboard(username))
        return MAIN_MENU

    # КУПИТЬ
    if data == "to_buy":
        await query.edit_message_text("Что хочешь сделать?", reply_markup=buy_menu_keyboard())
        return BUY_MENU

    # ПРОДАТЬ
    if data == "to_sell":
        await query.edit_message_text("Что хочешь сделать?", reply_markup=sell_menu_keyboard())
        return SELL_MENU

    # Создать заявку
    if data == "create_service_request":
        await query.edit_message_text(
            "🔧 Напиши, какая услуга тебе нужна.\n"
            "Например: нужен репетитор, помощь с переездом, ремонт телефона и т.д.\n\n"
            "После модерации твоя заявка появится у продавцов."
        )
        return WAIT_BUY_SERVICE_REQUEST

    # Показать активные заявки
    if data == "show_service_requests":
        if not active_requests:
            text = "🔧 Пока нет активных заявок."
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="to_sell")]]
        else:
            text = "🔧 Активные заявки:\n\n"
            for i, req in enumerate(active_requests, 1):
                text += f"{i}. {req['text'][:100]}...\n\n"
            
            keyboard = []
            for i, req in enumerate(active_requests):
                keyboard.append([InlineKeyboardButton(
                    f"📌 Заявка #{i+1}", 
                    callback_data=f"respond_{i}"
                )])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="to_sell")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return SELL_MENU

    # Откликнуться на заявку
    if data.startswith("respond_"):
        index = int(data.split("_")[1])
        if 0 <= index < len(active_requests):
            req = active_requests[index]
            context.user_data["current_request"] = req
            context.user_data["current_request_index"] = index
            await query.edit_message_text(
                f"📋 Заявка: {req['text']}\n\n"
                "Напиши своё предложение.\n"
                "❗️ Твой ответ сначала проверит админ."
            )
            return WAIT_SELL_SERVICE_RESPONSE

    # ===== АДМИН-ПАНЕЛЬ =====
    if data == "admin_panel":
        if not is_admin(username):
            await query.answer("Доступ запрещён", show_alert=True)
            return MAIN_MENU
        
        text = f"👑 Админ-панель\n\n"
        text += f"📋 Заявок на модерации: {len(pending_requests)}\n"
        text += f"💬 Ответов на модерации: {len(pending_responses)}\n"
        text += f"📝 Активных заявок: {len(active_requests)}"
        
        await query.edit_message_text(text, reply_markup=admin_menu_keyboard())
        return ADMIN_MENU

    # Модерация заявок
    if data == "admin_pending_requests":
        if not pending_requests:
            await query.edit_message_text("✅ Нет заявок на модерации.", reply_markup=admin_menu_keyboard())
            return ADMIN_MENU
        
        req = pending_requests[0]
        context.user_data["current_req"] = req
        
        text = f"📋 Заявка на модерации\n\n{req['text']}\n\nОт: @{req['user']}"
        keyboard = [
            [InlineKeyboardButton("✅ Одобрить", callback_data="moderate_request_approve")],
            [InlineKeyboardButton("❌ Отклонить", callback_data="moderate_request_reject")],
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_MENU

    if data == "moderate_request_approve":
        req = context.user_data.get("current_req")
        if req and pending_requests and req == pending_requests[0]:
            active_requests.append(req)
            pending_requests.pop(0)
            
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"📝 Новая заявка на услугу\n\n{req['text']}"
            )
            
            await query.edit_message_text("✅ Заявка одобрена!", reply_markup=admin_menu_keyboard())
        return ADMIN_MENU

    if data == "moderate_request_reject":
        if pending_requests:
            pending_requests.pop(0)
            await query.edit_message_text("❌ Заявка отклонена", reply_markup=admin_menu_keyboard())
        return ADMIN_MENU

    # Удаление активной заявки
    if data == "admin_delete_request":
        if not active_requests:
            await query.edit_message_text("✅ Нет активных заявок для удаления.", reply_markup=admin_menu_keyboard())
            return ADMIN_MENU
        
        text = "🗑 Активные заявки:\n\n"
        for i, req in enumerate(active_requests, 1):
            text += f"{i}. {req['text'][:100]}...\n"
        
        text += "\nВведи номер заявки для удаления:"
        
        await query.edit_message_text(text)
        return WAIT_DELETE_REQUEST_NUMBER

    # Модерация ответов
    if data == "admin_pending_responses":
        if not pending_responses:
            await query.edit_message_text("✅ Нет ответов на модерации.", reply_markup=admin_menu_keyboard())
            return ADMIN_MENU
        
        resp = pending_responses[0]
        context.user_data["current_response"] = resp
        
        text = (f"💬 Ответ на модерации\n\n"
                f"Заявка: {resp['request']['text']}\n"
                f"От кого заявка: @{resp['request']['user']}\n\n"
                f"Ответ от: @{resp['seller']}\n"
                f"{resp['response_text']}\n\n"
                f"❗️ Проверь, нет ли контактов")
        
        keyboard = [
            [InlineKeyboardButton("✅ Отправить автору", callback_data="moderate_response_approve")],
            [InlineKeyboardButton("❌ Вернуть на доработку", callback_data="moderate_response_reject")],
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
        ]
        
        try:
            await query.message.delete()
        except:
            pass
        
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_MENU

    if data == "moderate_response_approve":
        resp = context.user_data.get("current_response")
        if resp and pending_responses and resp == pending_responses[0]:
            try:
                # Отправляем автору заявки
                message_to_buyer = (
                    f"📩 Кто-то хочет помочь с твоей заявкой!\n\n"
                    f"Твоя заявка: {resp['request']['text']}\n\n"
                    f"📤 Ответ:\n{resp['response_text']}\n\n"
                    f"❗️ ВАЖНО: Оплата только через менеджера @{MANAGER_USERNAME}"
                )
                
                await context.bot.send_message(
                    chat_id=resp['request']['user_id'],
                    text=message_to_buyer
                )
                
                # Уведомление продавцу
                await context.bot.send_message(
                    chat_id=resp['seller_id'],
                    text=f"✅ Твой ответ отправлен автору заявки!"
                )
                
                # Уведомление в группу
                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"📨 Кто-то откликнулся на заявку"
                )
                
                # Удаляем заявку из активных (на неё уже откликнулись)
                for i, req in enumerate(active_requests):
                    if req['user_id'] == resp['request']['user_id'] and req['text'] == resp['request']['text']:
                        active_requests.pop(i)
                        break
                
                pending_responses.pop(0)
                await query.edit_message_text("✅ Ответ отправлен автору, заявка удалена!", reply_markup=admin_menu_keyboard())
                
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await query.edit_message_text(f"❌ Ошибка: {str(e)}", reply_markup=admin_menu_keyboard())
        
        return ADMIN_MENU

    if data == "moderate_response_reject":
        resp = context.user_data.get("current_response")
        if resp and pending_responses and resp == pending_responses[0]:
            try:
                await context.bot.send_message(
                    chat_id=resp['seller_id'],
                    text=(f"❌ Твой ответ не прошёл модерацию.\n\n"
                          f"Причина: содержит контакты.\n\n"
                          f"Твой ответ:\n{resp['response_text']}\n\n"
                          f"Напиши исправленный ответ:")
                )
                
                pending_responses.pop(0)
                context.user_data["request_for_fix"] = resp['request']
                
                await query.edit_message_text("✅ Ответ отправлен на доработку", reply_markup=admin_menu_keyboard())
                
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await query.edit_message_text(f"❌ Ошибка: {str(e)}", reply_markup=admin_menu_keyboard())
        
        return ADMIN_MENU

    # Блокировка
    if data == "admin_block":
        await query.edit_message_text("🚫 Введите юзернейм для блокировки (без @):")
        return WAIT_BLOCK_USER

    if data == "admin_unblock":
        await query.edit_message_text("✅ Введите юзернейм для разблокировки (без @):")
        return WAIT_UNBLOCK_USER

    return MAIN_MENU

# СОЗДАТЬ ЗАЯВКУ
async def handle_buy_service_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    username = user.username or "нет_юзернейма"
    
    pending_requests.append({
        "text": update.message.text,
        "user": username,
        "user_id": user.id
    })
    
    await update.message.reply_text(
        "📋 Заявка отправлена на модерацию!",
        reply_markup=main_menu_keyboard(username)
    )
    
    for admin in ADMIN_USERNAMES:
        try:
            await context.bot.send_message(
                chat_id=f"@{admin}",
                text=f"📝 Новая заявка на модерацию от @{username}"
            )
        except:
            pass
    
    return MAIN_MENU

# ОТКЛИКНУТЬСЯ НА ЗАЯВКУ
async def handle_sell_service_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    username = user.username or "нет_юзернейма"
    
    req = context.user_data.get("current_request")
    if not req:
        await update.message.reply_text("❌ Ошибка: заявка не найдена")
        return MAIN_MENU
    
    pending_responses.append({
        "response_text": update.message.text,
        "seller": username,
        "seller_id": user.id,
        "request": req
    })
    
    await update.message.reply_text(
        f"📋 Твой ответ отправлен на модерацию!",
        reply_markup=main_menu_keyboard(username)
    )
    
    for admin in ADMIN_USERNAMES:
        try:
            await context.bot.send_message(
                chat_id=f"@{admin}",
                text=f"💬 Новый ответ на модерацию от @{username}"
            )
        except:
            pass
    
    return MAIN_MENU

# ИСПРАВЛЕННЫЙ ОТВЕТ
async def handle_fixed_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    username = user.username or "нет_юзернейма"
    
    req = context.user_data.get("request_for_fix")
    if not req:
        await update.message.reply_text("❌ Ошибка: заявка не найдена")
        return MAIN_MENU
    
    pending_responses.append({
        "response_text": update.message.text,
        "seller": username,
        "seller_id": user.id,
        "request": req
    })
    
    await update.message.reply_text(
        f"📋 Исправленный ответ отправлен на модерацию!",
        reply_markup=main_menu_keyboard(username)
    )
    
    for admin in ADMIN_USERNAMES:
        try:
            await context.bot.send_message(
                chat_id=f"@{admin}",
                text=f"💬 Исправленный ответ на модерацию от @{username}"
            )
        except:
            pass
    
    return MAIN_MENU

# УДАЛЕНИЕ ЗАЯВКИ АДМИНОМ
async def handle_delete_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        number = int(update.message.text.strip())
        if 1 <= number <= len(active_requests):
            deleted = active_requests.pop(number - 1)
            await update.message.reply_text(
                f"✅ Заявка удалена!",
                reply_markup=admin_menu_keyboard()
            )
            
            # Уведомление в группу
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"🗑 Заявка удалена администратором"
            )
        else:
            await update.message.reply_text(
                "❌ Неверный номер. Попробуй ещё раз.",
                reply_markup=admin_menu_keyboard()
            )
    except:
        await update.message.reply_text(
            "❌ Введи число!",
            reply_markup=admin_menu_keyboard()
        )
    
    return ADMIN_MENU

# Блокировка
async def handle_block_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username = update.message.text.strip().replace("@", "")
    blocked_users.add(username.lower())
    await update.message.reply_text(f"✅ @{username} заблокирован", reply_markup=admin_menu_keyboard())
    return ADMIN_MENU

# Разблокировка
async def handle_unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username = update.message.text.strip().replace("@", "")
    username_lower = username.lower()
    
    found = None
    for u in blocked_users:
        if u.lower() == username_lower:
            found = u
            break
    
    if found:
        blocked_users.remove(found)
        await update.message.reply_text(f"✅ @{username} разблокирован", reply_markup=admin_menu_keyboard())
    else:
        await update.message.reply_text(f"❌ @{username} не в блоке", reply_markup=admin_menu_keyboard())
    return ADMIN_MENU

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username = update.effective_user.username or "no_username"
    await update.message.reply_text("Действие отменено.", reply_markup=main_menu_keyboard(username))
    return MAIN_MENU

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"Юзернейм: @{user.username}\nID: {user.id}")

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("info", info))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [CallbackQueryHandler(button_handler)],
            BUY_MENU: [CallbackQueryHandler(button_handler)],
            SELL_MENU: [CallbackQueryHandler(button_handler)],
            ADMIN_MENU: [CallbackQueryHandler(button_handler)],
            WAIT_BUY_SERVICE_REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buy_service_request)],
            WAIT_SELL_SERVICE_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sell_service_response)],
            WAIT_RESPONSE_FIX: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_fixed_response)],
            WAIT_DELETE_REQUEST_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_request)],
            WAIT_BLOCK_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_block_user)],
            WAIT_UNBLOCK_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unblock_user)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    
    print("✅ Бот запущен")
    print(f"Админы: @{', @'.join(ADMIN_USERNAMES)}")
    print(f"Менеджер: @{MANAGER_USERNAME}")
    application.run_polling()

if __name__ == "__main__":
    main()