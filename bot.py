#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  Premium Emoji → Video Converter Bot (aiogram 3)
  Всё в одном файле. Токен и ADMIN_IDS — внутри кода.
═══════════════════════════════════════════════════════
  pip install aiogram rlottie-python Pillow
  + ffmpeg должен быть установлен в системе
═══════════════════════════════════════════════════════
"""

import os
import json
import gzip
import uuid
import shutil
import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import (
    Message, CallbackQuery, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ╔══════════════════════════════════════════════════╗
# ║  КОНФИГУРАЦИЯ  —  ЗАПОЛНИ СВОИ ДАННЫЕ ЗДЕСЬ     ║
# ╚══════════════════════════════════════════════════╝

BOT_TOKEN = "8632657131:AAFIwXVbe0EbY7L7MLynLc8z7VFZVGXWTw4"
ADMIN_IDS = [7774179831]            # Telegram ID админов (можно несколько)

TEMP_DIR = "tmp_converter"
DB_FILE  = "bot_database.json"

# ══════════════════════════════════════════
#  ШАБЛОНЫ  /  ПРЕСЕТЫ
# ══════════════════════════════════════════

BG_COLORS = {
    "black":       {"label": "⬛ Чёрный",      "value": "#000000"},
    "white":       {"label": "⬜ Белый",       "value": "#FFFFFF"},
    "red":         {"label": "🟥 Красный",     "value": "#FF0000"},
    "green":       {"label": "🟩 Зелёный",     "value": "#00FF00"},
    "blue":        {"label": "🟦 Синий",       "value": "#0000FF"},
    "yellow":      {"label": "🟨 Жёлтый",     "value": "#FFFF00"},
    "purple":      {"label": "🟪 Фиолетовый", "value": "#9B59B6"},
    "orange":      {"label": "🟧 Оранжевый",  "value": "#FF8C00"},
    "cyan":        {"label": "🩵 Голубой",     "value": "#00CED1"},
    "pink":        {"label": "🩷 Розовый",     "value": "#FF69B4"},
    "transparent": {"label": "🔲 Прозрачный",  "value": "transparent"},
    "gradient1":   {"label": "🌅 Закат",       "value": "gradient:#FF6B6B:#4ECDC4"},
    "gradient2":   {"label": "🌌 Космос",      "value": "gradient:#667eea:#764ba2"},
    "gradient3":   {"label": "🌊 Океан",       "value": "gradient:#0F2027:#2C5364"},
}

RESOLUTIONS = {
    "360":   {"label": "360×360",   "w": 360,  "h": 360},
    "480":   {"label": "480×480",   "w": 480,  "h": 480},
    "512":   {"label": "512×512",   "w": 512,  "h": 512},
    "720":   {"label": "720×720",   "w": 720,  "h": 720},
    "1080":  {"label": "1080×1080", "w": 1080, "h": 1080},
    "1080p": {"label": "1920×1080", "w": 1920, "h": 1080},
}

QUALITY_PRESETS = {
    "best":   {"label": "🏆 Лучшее  (CRF 10)", "crf": 10},
    "high":   {"label": "🔥 Высокое (CRF 18)", "crf": 18},
    "medium": {"label": "👌 Среднее (CRF 26)", "crf": 26},
    "low":    {"label": "📦 Низкое  (CRF 35)", "crf": 35},
}

FPS_PRESETS = {
    "24": {"label": "🎬 24 FPS", "fps": 24},
    "30": {"label": "🎥 30 FPS", "fps": 30},
    "60": {"label": "🚀 60 FPS", "fps": 60},
}


# ══════════════════════════════════════════
#  БАЗА ДАННЫХ  (JSON-файл)
# ══════════════════════════════════════════

class Database:
    def __init__(self, path: str):
        self.path = path
        self.data: dict = {"users": {}, "stats": {"total_conversions": 0}, "bans": []}
        self._load()

    # --- IO ---
    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # --- Users ---
    def get_user(self, uid: int) -> dict:
        k = str(uid)
        if k not in self.data["users"]:
            self.data["users"][k] = {
                "bg": "black", "resolution": "512",
                "quality": "high", "fps": "30",
                "conversions": 0,
                "joined": datetime.now().isoformat(),
                "username": "", "first_name": "",
            }
            self._save()
        return self.data["users"][k]

    def set_user(self, uid: int, **kw):
        u = self.get_user(uid)
        u.update(kw)
        self._save()

    def inc_conversions(self, uid: int):
        self.get_user(uid)["conversions"] += 1
        self.data["stats"]["total_conversions"] += 1
        self._save()

    # --- Bans ---
    def ban(self, uid: int):
        if uid not in self.data["bans"]:
            self.data["bans"].append(uid)
            self._save()

    def unban(self, uid: int):
        if uid in self.data["bans"]:
            self.data["bans"].remove(uid)
            self._save()

    def is_banned(self, uid: int) -> bool:
        return uid in self.data["bans"]

    # --- Stats helpers ---
    def all_uids(self) -> list[int]:
        return [int(x) for x in self.data["users"]]

    @property
    def total_users(self) -> int:
        return len(self.data["users"])

    @property
    def total_conversions(self) -> int:
        return self.data["stats"].get("total_conversions", 0)

    @property
    def total_bans(self) -> int:
        return len(self.data["bans"])


# ══════════════════════════════════════════
#  FSM-СОСТОЯНИЯ
# ══════════════════════════════════════════

class AdminSt(StatesGroup):
    broadcast = State()
    ban_id    = State()
    unban_id  = State()

class UserSt(StatesGroup):
    custom_bg  = State()
    custom_res = State()


# ══════════════════════════════════════════
#  ИНИЦИАЛИЗАЦИЯ
# ══════════════════════════════════════════

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger("bot")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher(storage=MemoryStorage())
r   = Router()
dp.include_router(r)
db  = Database(DB_FILE)

START_TIME = datetime.now()
os.makedirs(TEMP_DIR, exist_ok=True)

is_admin = lambda uid: uid in ADMIN_IDS
even     = lambda n: n if n % 2 == 0 else n + 1   # h264 требует чётные


# ══════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════

def _workdir() -> str:
    d = os.path.join(TEMP_DIR, uuid.uuid4().hex[:10])
    os.makedirs(d, exist_ok=True)
    return d

def _cleanup(d: str):
    try:
        shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass


def _make_gradient_png(c1: str, c2: str, w: int, h: int, path: str):
    """Создаёт PNG-файл с вертикальным градиентом (PIL)."""
    from PIL import Image, ImageDraw
    img  = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    for y in range(h):
        t = y / max(h - 1, 1)
        cr = int(r1 + (r2 - r1) * t)
        cg = int(g1 + (g2 - g1) * t)
        cb = int(b1 + (b2 - b1) * t)
        draw.line([(0, y), (w, y)], fill=(cr, cg, cb))
    img.save(path)


async def _render_tgs(tgs_path: str, frames_dir: str, w: int, h: int):
    """Рендерит TGS (Lottie) в PNG-кадры через rlottie-python.
    Возвращает (количество_кадров, fps_оригинала).
    """
    from rlottie_python import LottieAnimation
    from PIL import Image

    with gzip.open(tgs_path, "rb") as f:
        data = f.read().decode("utf-8")

    anim   = LottieAnimation.from_data(data)
    total  = anim.lottie_animation_get_totalframe()
    fps    = anim.lottie_animation_get_framerate()

    for i in range(total):
        buf = anim.lottie_animation_render(frame_num=i, width=w, height=h)
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
        img.save(os.path.join(frames_dir, f"frame_{i:05d}.png"))

    return total, fps


def _ffprobe_duration(path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15,
        )
        return float(out.stdout.strip())
    except Exception:
        return 3.0


# ══════════════════════════════════════════
#  КОНВЕРТАЦИЯ  СТИКЕРА → ВИДЕО
# ══════════════════════════════════════════

async def convert_to_video(
    sticker_path: str,
    stype: str,          # "tgs" | "webm" | "webp"
    bg: str,             # hex | "transparent" | "gradient:#AAA:#BBB"
    w: int, h: int,
    crf: int,
    fps: int,
    work: str,
) -> str:
    """Возвращает путь к готовому .mp4 / .webm."""

    w, h = even(w), even(h)
    is_transparent = bg == "transparent"
    is_gradient    = bg.startswith("gradient:")
    out = os.path.join(work, "output.webm" if is_transparent else "output.mp4")

    # ─── TGS (Lottie animated) ───────────────────────
    if stype == "tgs":
        fdir = os.path.join(work, "frames")
        os.makedirs(fdir, exist_ok=True)
        total, orig_fps = await _render_tgs(sticker_path, fdir, w, h)
        duration = total / (orig_fps or 30)

        frame_input = ["-framerate", str(int(orig_fps or 30)),
                       "-i", os.path.join(fdir, "frame_%05d.png")]

        if is_transparent:
            cmd = ["ffmpeg", "-y", *frame_input,
                   "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                   "-crf", str(crf), "-b:v", "0", "-r", str(fps), out]

        elif is_gradient:
            c1, c2 = bg.split(":")[1], bg.split(":")[2]
            grad_path = os.path.join(work, "grad.png")
            _make_gradient_png(c1, c2, w, h, grad_path)
            cmd = ["ffmpeg", "-y",
                   "-loop", "1", "-i", grad_path,
                   *frame_input,
                   "-filter_complex",
                   "[0:v]scale={}:{}[bg];[bg][1:v]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p".format(w, h),
                   "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                   "-r", str(fps), "-t", str(duration),
                   "-movflags", "+faststart", out]
        else:
            hex6 = bg.lstrip("#")
            cmd = ["ffmpeg", "-y",
                   "-f", "lavfi", "-i",
                   "color=c=0x{}:s={}x{}:d={}:r={}".format(hex6, w, h, duration, fps),
                   *frame_input,
                   "-filter_complex",
                   "[0:v][1:v]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p",
                   "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                   "-r", str(fps), "-movflags", "+faststart", out]

    # ─── WEBM (video sticker) ────────────────────────
    elif stype == "webm":
        duration = _ffprobe_duration(sticker_path)
        scale_filter = "scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2".format(w, h, w, h)

        if is_transparent:
            cmd = ["ffmpeg", "-y", "-i", sticker_path,
                   "-vf", scale_filter + ":color=0x00000000,format=yuva420p",
                   "-c:v", "libvpx-vp9", "-crf", str(crf), "-b:v", "0",
                   "-r", str(fps), out]
        elif is_gradient:
            c1, c2 = bg.split(":")[1], bg.split(":")[2]
            grad_path = os.path.join(work, "grad.png")
            _make_gradient_png(c1, c2, w, h, grad_path)
            cmd = ["ffmpeg", "-y",
                   "-loop", "1", "-i", grad_path,
                   "-i", sticker_path,
                   "-filter_complex",
                   "[1:v]{}:color=0x00000000,format=yuva420p[fg];"
                   "[0:v]scale={}:{}[bg];[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p".format(scale_filter, w, h),
                   "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                   "-r", str(fps), "-t", str(duration),
                   "-movflags", "+faststart", out]
        else:
            hex6 = bg.lstrip("#")
            cmd = ["ffmpeg", "-y",
                   "-f", "lavfi", "-i",
                   "color=c=0x{}:s={}x{}:d={}:r={}".format(hex6, w, h, duration, fps),
                   "-i", sticker_path,
                   "-filter_complex",
                   "[1:v]{}:color=0x00000000,format=yuva420p[fg];"
                   "[0:v][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p".format(scale_filter),
                   "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                   "-r", str(fps), "-movflags", "+faststart", out]

    # ─── WEBP (static sticker → 3 sec video) ────────
    elif stype == "webp":
        duration = 3.0
        scale_filter = "scale={}:{}:force_original_aspect_ratio=decrease,pad={}:{}:(ow-iw)/2:(oh-ih)/2".format(w, h, w, h)

        if is_transparent:
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", sticker_path,
                   "-t", str(duration),
                   "-vf", scale_filter + ":color=0x00000000,format=yuva420p",
                   "-c:v", "libvpx-vp9", "-crf", str(crf), "-b:v", "0",
                   "-r", str(fps), out]
        elif is_gradient:
            c1, c2 = bg.split(":")[1], bg.split(":")[2]
            grad_path = os.path.join(work, "grad.png")
            _make_gradient_png(c1, c2, w, h, grad_path)
            cmd = ["ffmpeg", "-y",
                   "-loop", "1", "-i", grad_path,
                   "-loop", "1", "-i", sticker_path,
                   "-t", str(duration),
                   "-filter_complex",
                   "[1:v]{}:color=0x00000000,format=yuva420p[fg];"
                   "[0:v]scale={}:{}[bg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p".format(scale_filter, w, h),
                   "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                   "-r", str(fps), "-movflags", "+faststart", out]
        else:
            hex6 = bg.lstrip("#")
            cmd = ["ffmpeg", "-y",
                   "-f", "lavfi", "-i",
                   "color=c=0x{}:s={}x{}:d={}:r={}".format(hex6, w, h, duration, fps),
                   "-loop", "1", "-i", sticker_path,
                   "-t", str(duration),
                   "-filter_complex",
                   "[1:v]{}:color=0x00000000,format=yuva420p[fg];"
                   "[0:v][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p".format(scale_filter),
                   "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                   "-r", str(fps), "-movflags", "+faststart", out]
    else:
        raise ValueError(f"Неизвестный тип: {stype}")

    log.info("ffmpeg cmd: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{proc.stderr[-800:]}")
    if not os.path.exists(out):
        raise RuntimeError("Выходной файл не создан")
    return out


# ══════════════════════════════════════════
#  КЛАВИАТУРЫ
# ══════════════════════════════════════════

def kb_settings(uid: int) -> InlineKeyboardMarkup:
    u = db.get_user(uid)

    def _lbl(mapping: dict, key: str) -> str:
        if key.startswith("custom:"):
            return key.split(":", 1)[1]
        return mapping.get(key, {}).get("label", key)

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎨 Фон: {_lbl(BG_COLORS, u['bg'])}", callback_data="s:bg")],
        [InlineKeyboardButton(text=f"📐 Размер: {_lbl(RESOLUTIONS, u['resolution'])}", callback_data="s:res")],
        [InlineKeyboardButton(text=f"🎬 Качество: {_lbl(QUALITY_PRESETS, u['quality'])}", callback_data="s:q")],
        [InlineKeyboardButton(text=f"🎞 FPS: {_lbl(FPS_PRESETS, u['fps'])}", callback_data="s:fps")],
    ])


def _grid(items: dict, prefix: str, cols: int = 2, extra=None) -> InlineKeyboardMarkup:
    rows, row = [], []
    for k, v in items.items():
        row.append(InlineKeyboardButton(text=v["label"], callback_data=f"{prefix}:{k}"))
        if len(row) == cols:
            rows.append(row); row = []
    if row:
        rows.append(row)
    if extra:
        rows.append(extra)
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="s:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_bg():
    return _grid(BG_COLORS, "bg", 2,
                 [InlineKeyboardButton(text="✏️ Свой HEX", callback_data="bg:custom")])

def kb_res():
    return _grid(RESOLUTIONS, "res", 2,
                 [InlineKeyboardButton(text="✏️ Своё WxH", callback_data="res:custom")])

def kb_quality():
    return _grid(QUALITY_PRESETS, "q", 1)

def kb_fps():
    return _grid(FPS_PRESETS, "fps", 3)


def kb_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика",   callback_data="a:stats")],
        [InlineKeyboardButton(text="📢 Рассылка",     callback_data="a:bc")],
        [InlineKeyboardButton(text="🚫 Бан",  callback_data="a:ban"),
         InlineKeyboardButton(text="✅ Разбан", callback_data="a:unban")],
        [InlineKeyboardButton(text="📋 Бан-лист",     callback_data="a:bans")],
    ])


# ══════════════════════════════════════════
#  ОБРАБОТЧИКИ  —  КОМАНДЫ
# ══════════════════════════════════════════

@r.message(CommandStart())
async def h_start(msg: Message):
    uid = msg.from_user.id
    if db.is_banned(uid):
        return await msg.answer("🚫 Вы заблокированы.")
    u = db.get_user(uid)
    u["username"]   = msg.from_user.username or ""
    u["first_name"] = msg.from_user.first_name or ""
    db._save()

    txt = (
        "👋 <b>Привет! Я конвертер Premium Emoji → Видео</b>\n\n"
        "📩 <b>Отправь мне:</b>\n"
        "  • Premium emoji (в сообщении)\n"
        "  • Custom Emoji ID (число)\n"
        "  • Любой стикер (animated / video / static)\n\n"
        "⚙️ /settings — настройки\n"
        "❓ /help — справка\n"
    )
    if is_admin(uid):
        txt += "🔧 /admin — админ-панель\n"
    await msg.answer(txt)


@r.message(Command("help"))
async def h_help(msg: Message):
    await msg.answer(
        "📖 <b>Инструкция:</b>\n\n"
        "1️⃣ Настрой параметры — /settings\n"
        "2️⃣ Отправь premium emoji / стикер / ID\n"
        "3️⃣ Получи MP4 (или WEBM при прозрачном фоне)\n\n"
        "🎨 Фон — 10 цветов + 3 градиента + прозрачный + свой HEX\n"
        "📐 Размер — 6 пресетов + своё значение\n"
        "🎬 Качество — CRF 10 / 18 / 26 / 35\n"
        "🎞 FPS — 24 / 30 / 60"
    )


@r.message(Command("settings"))
async def h_settings(msg: Message):
    if db.is_banned(msg.from_user.id):
        return
    await msg.answer("⚙️ <b>Настройки конвертации:</b>", reply_markup=kb_settings(msg.from_user.id))


@r.message(Command("admin"))
async def h_admin(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("⛔ Нет доступа.")
    await msg.answer("🔧 <b>Админ-панель:</b>", reply_markup=kb_admin())


@r.message(Command("id"))
async def h_id(msg: Message):
    await msg.answer(f"🆔 Ваш ID: <code>{msg.from_user.id}</code>")


@r.message(Command("cancel"))
async def h_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Отменено.")


# ══════════════════════════════════════════
#  ОБРАБОТЧИКИ  —  НАСТРОЙКИ (callbacks)
# ══════════════════════════════════════════

@r.callback_query(F.data == "s:back")
async def cb_back(cb: CallbackQuery):
    await cb.message.edit_text("⚙️ <b>Настройки конвертации:</b>",
                               reply_markup=kb_settings(cb.from_user.id))

@r.callback_query(F.data == "s:bg")
async def cb_bg(cb: CallbackQuery):
    await cb.message.edit_text("🎨 <b>Выбери фон:</b>", reply_markup=kb_bg())

@r.callback_query(F.data == "s:res")
async def cb_res(cb: CallbackQuery):
    await cb.message.edit_text("📐 <b>Выбери разрешение:</b>", reply_markup=kb_res())

@r.callback_query(F.data == "s:q")
async def cb_q(cb: CallbackQuery):
    await cb.message.edit_text("🎬 <b>Выбери качество:</b>", reply_markup=kb_quality())

@r.callback_query(F.data == "s:fps")
async def cb_fps(cb: CallbackQuery):
    await cb.message.edit_text("🎞 <b>Выбери FPS:</b>", reply_markup=kb_fps())


# --- Установка фона ---
@r.callback_query(F.data.startswith("bg:"))
async def cb_set_bg(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":", 1)[1]
    if key == "custom":
        await state.set_state(UserSt.custom_bg)
        await cb.message.edit_text(
            "✏️ Введи HEX-цвет, например <code>#FF5733</code>:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Отмена", callback_data="s:bg")]
            ]),
        )
        return
    db.set_user(cb.from_user.id, bg=key)
    await cb.answer(f"✅ {BG_COLORS[key]['label']}")
    await cb.message.edit_text("⚙️ <b>Настройки конвертации:</b>",
                               reply_markup=kb_settings(cb.from_user.id))

# --- Установка разрешения ---
@r.callback_query(F.data.startswith("res:"))
async def cb_set_res(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":", 1)[1]
    if key == "custom":
        await state.set_state(UserSt.custom_res)
        await cb.message.edit_text(
            "✏️ Введи разрешение, например <code>800x600</code>  (мин 100, макс 3840):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Отмена", callback_data="s:res")]
            ]),
        )
        return
    db.set_user(cb.from_user.id, resolution=key)
    await cb.answer(f"✅ {RESOLUTIONS[key]['label']}")
    await cb.message.edit_text("⚙️ <b>Настройки конвертации:</b>",
                               reply_markup=kb_settings(cb.from_user.id))

# --- Установка качества ---
@r.callback_query(F.data.startswith("q:"))
async def cb_set_q(cb: CallbackQuery):
    key = cb.data.split(":", 1)[1]
    db.set_user(cb.from_user.id, quality=key)
    await cb.answer(f"✅ {QUALITY_PRESETS[key]['label']}")
    await cb.message.edit_text("⚙️ <b>Настройки конвертации:</b>",
                               reply_markup=kb_settings(cb.from_user.id))

# --- Установка FPS ---
@r.callback_query(F.data.startswith("fps:"))
async def cb_set_fps(cb: CallbackQuery):
    key = cb.data.split(":", 1)[1]
    db.set_user(cb.from_user.id, fps=key)
    await cb.answer(f"✅ {FPS_PRESETS[key]['label']}")
    await cb.message.edit_text("⚙️ <b>Настройки конвертации:</b>",
                               reply_markup=kb_settings(cb.from_user.id))


# ══════════════════════════════════════════
#  ОБРАБОТЧИКИ  —  ПОЛЬЗОВАТЕЛЬСКИЙ ВВОД (FSM)
# ══════════════════════════════════════════

@r.message(UserSt.custom_bg)
async def fsm_custom_bg(msg: Message, state: FSMContext):
    t = msg.text.strip() if msg.text else ""
    if not t.startswith("#") or len(t) not in (4, 7):
        return await msg.answer("❌ Неверный формат. Пример: <code>#FF5733</code>")
    db.set_user(msg.from_user.id, bg=f"custom:{t}")
    await state.clear()
    await msg.answer(f"✅ Цвет фона: {t}", reply_markup=kb_settings(msg.from_user.id))


@r.message(UserSt.custom_res)
async def fsm_custom_res(msg: Message, state: FSMContext):
    t = (msg.text or "").strip().lower()
    try:
        pw, ph = t.split("x")
        pw, ph = int(pw), int(ph)
        assert 100 <= pw <= 3840 and 100 <= ph <= 2160
    except Exception:
        return await msg.answer("❌ Формат: <code>WxH</code>, от 100 до 3840. Пример: <code>800x600</code>")
    db.set_user(msg.from_user.id, resolution=f"custom:{pw}x{ph}")
    await state.clear()
    await msg.answer(f"✅ Разрешение: {pw}×{ph}", reply_markup=kb_settings(msg.from_user.id))


# ══════════════════════════════════════════
#  ОБРАБОТЧИКИ  —  АДМИН (callbacks + FSM)
# ══════════════════════════════════════════

@r.callback_query(F.data == "a:stats")
async def cb_stats(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    dt = datetime.now() - START_TIME
    h, rem = divmod(int(dt.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    await cb.message.edit_text(
        "📊 <b>Статистика:</b>\n\n"
        f"👥 Пользователей: <b>{db.total_users}</b>\n"
        f"🔄 Конвертаций: <b>{db.total_conversions}</b>\n"
        f"🚫 Банов: <b>{db.total_bans}</b>\n"
        f"⏱ Аптайм: <b>{h}ч {m}м {s}с</b>",
        reply_markup=kb_admin(),
    )

@r.callback_query(F.data == "a:bc")
async def cb_broadcast(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AdminSt.broadcast)
    await cb.message.edit_text("📢 Введи текст рассылки (или /cancel):")

@r.callback_query(F.data == "a:ban")
async def cb_ban(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AdminSt.ban_id)
    await cb.message.edit_text("🚫 Введи Telegram ID для бана (или /cancel):")

@r.callback_query(F.data == "a:unban")
async def cb_unban(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AdminSt.unban_id)
    await cb.message.edit_text("✅ Введи Telegram ID для разбана (или /cancel):")

@r.callback_query(F.data == "a:bans")
async def cb_banlist(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    bans = db.data["bans"]
    txt = "📋 <b>Бан-лист пуст.</b>" if not bans else "📋 <b>Бан-лист:</b>\n\n" + "\n".join(f"• <code>{x}</code>" for x in bans)
    await cb.message.edit_text(txt, reply_markup=kb_admin())


@r.message(AdminSt.broadcast)
async def fsm_broadcast(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.clear()
    uids = db.all_uids()
    ok = fail = 0
    st = await msg.answer(f"📢 Рассылка… 0/{len(uids)}")
    for i, uid in enumerate(uids, 1):
        try:
            await bot.send_message(uid, msg.text, parse_mode=ParseMode.HTML)
            ok += 1
        except Exception:
            fail += 1
        if i % 25 == 0:
            try:
                await st.edit_text(f"📢 Рассылка… {i}/{len(uids)}")
            except Exception:
                pass
        await asyncio.sleep(0.04)
    await st.edit_text(
        f"📢 <b>Рассылка завершена</b>\n✅ {ok}  ❌ {fail}",
        reply_markup=kb_admin(),
    )

@r.message(AdminSt.ban_id)
async def fsm_ban(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    try:
        uid = int(msg.text.strip())
    except Exception:
        return await msg.answer("❌ Введи числовой ID.")
    db.ban(uid)
    await state.clear()
    await msg.answer(f"🚫 <code>{uid}</code> забанен.", reply_markup=kb_admin())

@r.message(AdminSt.unban_id)
async def fsm_unban(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    try:
        uid = int(msg.text.strip())
    except Exception:
        return await msg.answer("❌ Введи числовой ID.")
    db.unban(uid)
    await state.clear()
    await msg.answer(f"✅ <code>{uid}</code> разбанен.", reply_markup=kb_admin())


# ══════════════════════════════════════════
#  ПОЛУЧЕНИЕ ПАРАМЕТРОВ ПОЛЬЗОВАТЕЛЯ
# ══════════════════════════════════════════

def user_params(uid: int) -> dict:
    u = db.get_user(uid)

    # фон
    bk = u.get("bg", "black")
    if bk.startswith("custom:"):
        bg_val = bk.split(":", 1)[1]
    elif bk in BG_COLORS:
        bg_val = BG_COLORS[bk]["value"]
    else:
        bg_val = "#000000"

    # разрешение
    rk = u.get("resolution", "512")
    if rk.startswith("custom:"):
        pw, ph = rk.split(":", 1)[1].split("x")
        w, h = int(pw), int(ph)
    elif rk in RESOLUTIONS:
        w, h = RESOLUTIONS[rk]["w"], RESOLUTIONS[rk]["h"]
    else:
        w, h = 512, 512

    qk  = u.get("quality", "high")
    crf = QUALITY_PRESETS.get(qk, QUALITY_PRESETS["high"])["crf"]

    fk  = u.get("fps", "30")
    fps = FPS_PRESETS.get(fk, FPS_PRESETS["30"])["fps"]

    return {"bg": bg_val, "w": w, "h": h, "crf": crf, "fps": fps}


# ══════════════════════════════════════════
#  ОБЩАЯ ФУНКЦИЯ ОБРАБОТКИ СТИКЕРА
# ══════════════════════════════════════════

async def _process(msg: Message, sticker: types.Sticker):
    uid  = msg.from_user.id
    work = _workdir()
    try:
        p   = user_params(uid)
        st  = await msg.answer("⏳ Скачиваю…")

        if sticker.is_animated:
            ext, stype = ".tgs", "tgs"
        elif sticker.is_video:
            ext, stype = ".webm", "webm"
        else:
            ext, stype = ".webp", "webp"

        spath = os.path.join(work, f"sticker{ext}")
        fobj  = await bot.get_file(sticker.file_id)
        await bot.download_file(fobj.file_path, spath)

        await st.edit_text("🔄 Конвертирую…")

        out = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: asyncio.get_event_loop().run_until_complete(
                convert_to_video(spath, stype, p["bg"], p["w"], p["h"], p["crf"], p["fps"], work)
            ),
        ) if False else await convert_to_video(spath, stype, p["bg"], p["w"], p["h"], p["crf"], p["fps"], work)

        await st.edit_text("📤 Отправляю…")

        vf = FSInputFile(out)
        if out.endswith(".webm"):
            await msg.answer_document(vf, caption="✅ Готово! (WEBM с прозрачностью)")
        else:
            await msg.answer_video(vf, caption="✅ Готово!")
        await st.delete()
        db.inc_conversions(uid)

    except Exception as e:
        log.exception("conversion failed")
        await msg.answer(f"❌ Ошибка:\n<pre>{str(e)[:800]}</pre>")
    finally:
        _cleanup(work)


# ══════════════════════════════════════════
#  ОБРАБОТЧИКИ  —  СТИКЕРЫ И ЭМОДЗИ
# ══════════════════════════════════════════

@r.message(F.sticker)
async def h_sticker(msg: Message):
    if db.is_banned(msg.from_user.id):
        return
    db.get_user(msg.from_user.id)
    await _process(msg, msg.sticker)


@r.message(F.entities)
async def h_entities(msg: Message, state: FSMContext):
    # не мешаем FSM
    if await state.get_state() is not None:
        return
    uid = msg.from_user.id
    if db.is_banned(uid):
        return

    ids = [e.custom_emoji_id for e in (msg.entities or []) if e.type == "custom_emoji" and e.custom_emoji_id]
    if not ids:
        return

    db.get_user(uid)
    try:
        stickers = await bot.get_custom_emoji_stickers(ids[:1])
        if stickers:
            await _process(msg, stickers[0])
        else:
            await msg.answer("❌ Не удалось получить эмодзи.")
    except Exception as e:
        log.exception("custom emoji fetch failed")
        await msg.answer(f"❌ Ошибка: <code>{e}</code>")


@r.message(F.text)
async def h_text(msg: Message, state: FSMContext):
    if await state.get_state() is not None:
        return
    uid = msg.from_user.id
    if db.is_banned(uid):
        return

    t = (msg.text or "").strip()
    if not t.isdigit() or len(t) < 6:
        return  # не emoji-id — игнорируем

    db.get_user(uid)
    try:
        stickers = await bot.get_custom_emoji_stickers([t])
        if stickers:
            await _process(msg, stickers[0])
        else:
            await msg.answer("❌ Эмодзи с таким ID не найден.")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: <code>{e}</code>")


# ══════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════

async def main():
    log.info("═══ Bot starting ═══")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
