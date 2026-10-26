from aiogram.fsm.state import State, StatesGroup


class ServiceStates(StatesGroup):
    # menyudan xizmat tanlangan, fayl kutilmoqda
    waiting_file = State()


class CollectStates(StatesGroup):
    collecting = State()


class SplitStates(StatesGroup):
    waiting_pages = State()


class AdminStates(StatesGroup):
    broadcast_message = State()
    broadcast_confirm = State()
    channel_add = State()
