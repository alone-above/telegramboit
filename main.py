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

import asyncpg

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

# PostgreSQL URLs (в проде лучше вынести в переменные окружения)
DATABASE_PUBLIC_URL = os.getenv(
    "DATABASE_PUBLIC_URL",
    "postgresql://postgres:mdRdePzUHjPzAtsSNYKbhstWNjrIxktX@centerbeam.proxy.rlwy.net:55351/railway",
)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:mdRdePzUHjPzAtsSNYKbhstWNjrIxktX@postgres.railway.internal:5432/railway",
)

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
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def init(self):
        self.pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=6)
        await self._ensure_schema()

    async def _ensure_schema(self):
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    uid BIGINT PRIMARY KEY,
                    username TEXT NOT NULL DEFAULT '',
                    first_name TEXT NOT NULL DEFAULT '',
                    bg TEXT NOT NULL DEFAULT 'black',
                    resolution TEXT NOT NULL DEFAULT '512',
                    quality TEXT NOT NULL DEFAULT 'high',
                    fps TEXT NOT NULL DEFAULT '30',
                    conversions_count BIGINT NOT NULL DEFAULT 0,
                    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    banned BOOLEAN NOT NULL DEFAULT FALSE
                );

                CREATE TABLE IF NOT EXISTS conversions (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
                    emoji_id TEXT NOT NULL DEFAULT '',
                    bg TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    fps TEXT NOT NULL,
                    success BOOLEAN NOT NULL DEFAULT FALSE,
                    error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_conversions_user_id_created_at
                    ON conversions(user_id, created_at DESC);
                """
            )

    async def get_user(self, uid: int) -> dict:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT uid, username, first_name, bg, resolution, quality, fps,
                       conversions_count, joined_at, banned
                FROM users
                WHERE uid = $1
                """,
                uid,
            )
            if row is None:
                await conn.execute(
                    "INSERT INTO users (uid) VALUES ($1) ON CONFLICT DO NOTHING",
                    uid,
                )
                row = await conn.fetchrow(
                    """
                    SELECT uid, username, first_name, bg, resolution, quality, fps,
                           conversions_count, joined_at, banned
                    FROM users
                    WHERE uid = $1
                    """,
                    uid,
                )
            return dict(row)

    async def set_user(self, uid: int, **kw):
        assert self.pool is not None
        if not kw:
            return

        allowed = {"username", "first_name", "bg", "resolution", "quality", "fps", "banned"}
        cols = [k for k in kw.keys() if k in allowed]
        if not cols:
            return

        values = [kw[c] for c in cols]
        setters = ", ".join(f"{c} = ${i + 2}" for i, c in enumerate(cols))
        sql = f"UPDATE users SET {setters} WHERE uid = $1"

        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO users (uid) VALUES ($1) ON CONFLICT DO NOTHING", uid)
            await conn.execute(sql, uid, *values)

    async def is_banned(self, uid: int) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT banned FROM users WHERE uid = $1", uid)
            if row is None:
                return False
            return bool(row["banned"])

    async def ban(self, uid: int):
        await self.set_user(uid, banned=True)

    async def unban(self, uid: int):
        await self.set_user(uid, banned=False)

    async def get_ban_list(self) -> list[int]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT uid FROM users WHERE banned = TRUE")
        return [int(r["uid"]) for r in rows]

    async def get_stats(self) -> dict:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM users) AS total_users,
                    (SELECT COALESCE(SUM(conversions_count), 0) FROM users) AS total_conversions,
                    (SELECT COUNT(*) FROM users WHERE banned = TRUE) AS total_bans
                """
            )
        return dict(row)

    async def all_uids(self) -> list[int]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT uid FROM users")
        return [int(r["uid"]) for r in rows]

    async def add_conversion(
        self,
        user_id: int,
        emoji_id: str,
        raw_bg: str,
        raw_resolution: str,
        raw_quality: str,
        raw_fps: str,
        success: bool,
        error: str | None = None,
    ):
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO conversions (user_id, emoji_id, bg, resolution, quality, fps, success, error)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    user_id,
                    emoji_id or "",
                    raw_bg,
                    raw_resolution,
                    raw_quality,
                    raw_fps,
                    success,
                    error,
                )
                if success:
                    await conn.execute(
                        "UPDATE users SET conversions_count = conversions_count + 1 WHERE uid = $1",
                        user_id,
                    )


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
db  = Database(DATABASE_URL)

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


def _render_tgs(tgs_path: str, frames_dir: str, w: int, h: int):
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

def convert_to_video(
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
        total, orig_fps = _render_tgs(sticker_path, fdir, w, h)
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

async def kb_settings(uid: int) -> InlineKeyboardMarkup:
    u = await db.get_user(uid)

    import re

    def bg_label(key: str) -> str:
        if key.startswith("custom:"):
            return key.split(":", 1)[1]
        if key in BG_COLORS:
            return BG_COLORS[key]["label"]
        if key.startswith("linear-gradient"):
            colors = re.findall(r"#[0-9A-Fa-f]{6}", key)
            if len(colors) >= 2:
                grad = f"gradient:{colors[0]}:{colors[1]}"
                for k, v in BG_COLORS.items():
                    if v["value"] == grad:
                        return v["label"]
                return "🎨 Градиент (custom)"
        for k, v in BG_COLORS.items():
            if v["value"] == key:
                return v["label"]
        return key

    def res_label(key: str) -> str:
        if key.startswith("custom:"):
            return key.split(":", 1)[1]
        if key in RESOLUTIONS:
            return RESOLUTIONS[key]["label"]
        if "x" in key:
            try:
                pw, ph = key.split("x", 1)
                w, h = int(pw), int(ph)
                for k, v in RESOLUTIONS.items():
                    if v["w"] == w and v["h"] == h:
                        return v["label"]
            except Exception:
                pass
        return key

    def q_label(key: str) -> str:
        if key in QUALITY_PRESETS:
            return QUALITY_PRESETS[key]["label"]
        if str(key).isdigit():
            crf = int(key)
            return f"CRF {crf}"
        return key

    def fps_label(key: str) -> str:
        if key in FPS_PRESETS:
            return FPS_PRESETS[key]["label"]
        if str(key).isdigit():
            fps = int(key)
            return f"{fps} FPS"
        return key

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎨 Фон: {bg_label(str(u['bg']))}", callback_data="s:bg")],
        [InlineKeyboardButton(text=f"📐 Размер: {res_label(str(u['resolution']))}", callback_data="s:res")],
        [InlineKeyboardButton(text=f"🎬 Качество: {q_label(str(u['quality']))}", callback_data="s:q")],
        [InlineKeyboardButton(text=f"🎞 FPS: {fps_label(str(u['fps']))}", callback_data="s:fps")],
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
    if await db.is_banned(uid):
        return await msg.answer("🚫 Вы заблокированы.")
    await db.get_user(uid)
    await db.set_user(
        uid,
        username=msg.from_user.username or "",
        first_name=msg.from_user.first_name or "",
    )

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
    if await db.is_banned(msg.from_user.id):
        return
    await msg.answer(
        "⚙️ <b>Настройки конвертации:</b>",
        reply_markup=await kb_settings(msg.from_user.id),
    )


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
                               reply_markup=await kb_settings(cb.from_user.id))

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
    await db.set_user(cb.from_user.id, bg=key)
    await cb.answer(f"✅ {BG_COLORS[key]['label']}")
    await cb.message.edit_text("⚙️ <b>Настройки конвертации:</b>",
                               reply_markup=await kb_settings(cb.from_user.id))

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
    await db.set_user(cb.from_user.id, resolution=key)
    await cb.answer(f"✅ {RESOLUTIONS[key]['label']}")
    await cb.message.edit_text("⚙️ <b>Настройки конвертации:</b>",
                               reply_markup=await kb_settings(cb.from_user.id))

# --- Установка качества ---
@r.callback_query(F.data.startswith("q:"))
async def cb_set_q(cb: CallbackQuery):
    key = cb.data.split(":", 1)[1]
    await db.set_user(cb.from_user.id, quality=key)
    await cb.answer(f"✅ {QUALITY_PRESETS[key]['label']}")
    await cb.message.edit_text("⚙️ <b>Настройки конвертации:</b>",
                               reply_markup=await kb_settings(cb.from_user.id))

# --- Установка FPS ---
@r.callback_query(F.data.startswith("fps:"))
async def cb_set_fps(cb: CallbackQuery):
    key = cb.data.split(":", 1)[1]
    await db.set_user(cb.from_user.id, fps=key)
    await cb.answer(f"✅ {FPS_PRESETS[key]['label']}")
    await cb.message.edit_text("⚙️ <b>Настройки конвертации:</b>",
                               reply_markup=await kb_settings(cb.from_user.id))


# ══════════════════════════════════════════
#  ОБРАБОТЧИКИ  —  ПОЛЬЗОВАТЕЛЬСКИЙ ВВОД (FSM)
# ══════════════════════════════════════════

@r.message(UserSt.custom_bg)
async def fsm_custom_bg(msg: Message, state: FSMContext):
    t = msg.text.strip() if msg.text else ""
    if not t.startswith("#") or len(t) not in (4, 7):
        return await msg.answer("❌ Неверный формат. Пример: <code>#FF5733</code>")
    await db.set_user(msg.from_user.id, bg=f"custom:{t}")
    await state.clear()
    await msg.answer(
        f"✅ Цвет фона: {t}",
        reply_markup=await kb_settings(msg.from_user.id),
    )


@r.message(UserSt.custom_res)
async def fsm_custom_res(msg: Message, state: FSMContext):
    t = (msg.text or "").strip().lower()
    try:
        pw, ph = t.split("x")
        pw, ph = int(pw), int(ph)
        assert 100 <= pw <= 3840 and 100 <= ph <= 2160
    except Exception:
        return await msg.answer("❌ Формат: <code>WxH</code>, от 100 до 3840. Пример: <code>800x600</code>")
    await db.set_user(msg.from_user.id, resolution=f"custom:{pw}x{ph}")
    await state.clear()
    await msg.answer(
        f"✅ Разрешение: {pw}×{ph}",
        reply_markup=await kb_settings(msg.from_user.id),
    )


# ══════════════════════════════════════════
#  ОБРАБОТЧИКИ  —  АДМИН (callbacks + FSM)
# ══════════════════════════════════════════

@r.callback_query(F.data == "a:stats")
async def cb_stats(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    stats = await db.get_stats()
    dt = datetime.now() - START_TIME
    h, rem = divmod(int(dt.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    await cb.message.edit_text(
        "📊 <b>Статистика:</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"🔄 Конвертаций: <b>{stats['total_conversions']}</b>\n"
        f"🚫 Банов: <b>{stats['total_bans']}</b>\n"
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
    bans = await db.get_ban_list()
    txt = "📋 <b>Бан-лист пуст.</b>" if not bans else "📋 <b>Бан-лист:</b>\n\n" + "\n".join(f"• <code>{x}</code>" for x in bans)
    await cb.message.edit_text(txt, reply_markup=kb_admin())


@r.message(AdminSt.broadcast)
async def fsm_broadcast(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.clear()
    uids = await db.all_uids()
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
    await db.ban(uid)
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
    await db.unban(uid)
    await state.clear()
    await msg.answer(f"✅ <code>{uid}</code> разбанен.", reply_markup=kb_admin())


# ══════════════════════════════════════════
#  ПОЛУЧЕНИЕ ПАРАМЕТРОВ ПОЛЬЗОВАТЕЛЯ
# ══════════════════════════════════════════

async def user_params(uid: int) -> dict:
    import re

    u = await db.get_user(uid)

    # --- фон (примем и "ключи" из бота, и "сырой" формат с web-интерфейса) ---
    bk = str(u.get("bg", "black"))
    if bk.startswith("custom:"):
        bg_val = bk.split(":", 1)[1]
    elif bk == "transparent":
        bg_val = "transparent"
    elif bk.startswith("gradient:"):
        bg_val = bk
    elif bk.startswith("linear-gradient"):
        colors = re.findall(r"#[0-9A-Fa-f]{6}", bk)
        if len(colors) >= 2:
            bg_val = f"gradient:{colors[0]}:{colors[1]}"
        else:
            bg_val = "#000000"
    elif bk.startswith("#"):
        bg_val = bk
    elif bk in BG_COLORS:
        bg_val = BG_COLORS[bk]["value"]
    else:
        bg_val = "#000000"

    # --- разрешение ---
    rk = str(u.get("resolution", "512"))
    if rk.startswith("custom:"):
        pw, ph = rk.split(":", 1)[1].split("x")
        w, h = int(pw), int(ph)
    elif rk in RESOLUTIONS:
        w, h = RESOLUTIONS[rk]["w"], RESOLUTIONS[rk]["h"]
    elif "x" in rk:
        pw, ph = rk.split("x", 1)
        w, h = int(pw), int(ph)
    else:
        w, h = 512, 512

    # --- качество (CRF) ---
    qk = u.get("quality", "high")
    qk_str = str(qk)
    if qk_str.isdigit():
        crf = int(qk_str)
    else:
        crf = QUALITY_PRESETS.get(qk_str, QUALITY_PRESETS["high"])["crf"]

    # --- FPS ---
    fk = u.get("fps", "30")
    fk_str = str(fk)
    if fk_str.isdigit():
        fps = int(fk_str)
    else:
        fps = FPS_PRESETS.get(fk_str, FPS_PRESETS["30"])["fps"]

    return {
        "bg": bg_val,
        "w": w,
        "h": h,
        "crf": crf,
        "fps": fps,
        # для записи в историю
        "raw_bg": bk,
        "raw_resolution": rk,
        "raw_quality": qk_str,
        "raw_fps": fk_str,
    }


# ══════════════════════════════════════════
#  ОБЩАЯ ФУНКЦИЯ ОБРАБОТКИ СТИКЕРА
# ══════════════════════════════════════════

async def _process(msg: Message, sticker: types.Sticker, *, emoji_id: str = ""):
    uid  = msg.from_user.id
    work = _workdir()
    p: dict | None = None
    success = False
    err_txt: str | None = None
    try:
        p   = await user_params(uid)
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

        # ffmpeg/рендеринг может быть долгим и блокирующим — запускаем в отдельном потоке
        out = await asyncio.to_thread(
            convert_to_video,
            spath,
            stype,
            p["bg"],
            p["w"],
            p["h"],
            p["crf"],
            p["fps"],
            work,
        )

        await st.edit_text("📤 Отправляю…")

        vf = FSInputFile(out)
        if out.endswith(".webm"):
            await msg.answer_document(vf, caption="✅ Готово! (WEBM с прозрачностью)")
        else:
            await msg.answer_video(vf, caption="✅ Готово!")
        await st.delete()
        success = True

    except Exception as e:
        log.exception("conversion failed")
        err_txt = str(e)[:2000]
        await msg.answer(f"❌ Ошибка:\n<pre>{str(e)[:800]}</pre>")
    finally:
        if p is not None:
            try:
                await db.add_conversion(
                    user_id=uid,
                    emoji_id=emoji_id,
                    raw_bg=p["raw_bg"],
                    raw_resolution=p["raw_resolution"],
                    raw_quality=p["raw_quality"],
                    raw_fps=p["raw_fps"],
                    success=success,
                    error=err_txt,
                )
            except Exception:
                # Не роняем бота из-за записи истории
                pass
        _cleanup(work)

    return success


# ══════════════════════════════════════════
#  ОБРАБОТЧИКИ  —  СТИКЕРЫ И ЭМОДЗИ
# ══════════════════════════════════════════

@r.message(F.web_app_data)
async def h_webapp_data(msg: Message):
    if not msg.web_app_data or not msg.web_app_data.data:
        return

    uid = msg.from_user.id
    if await db.is_banned(uid):
        return

    try:
        payload = json.loads(msg.web_app_data.data)
    except Exception:
        return

    if payload.get("action") != "convert":
        return

    bg = str(payload.get("bg", "black"))
    resolution = str(payload.get("resolution", "512x512"))
    quality = str(payload.get("quality", "high"))
    fps = str(payload.get("fps", "30"))

    await db.set_user(uid, bg=bg, resolution=resolution, quality=quality, fps=fps)

    emoji_ids = payload.get("emoji_ids") or []
    if not emoji_ids and payload.get("emoji_id"):
        emoji_ids = [payload.get("emoji_id")]

    selected: list[str] = []
    seen: set[str] = set()
    for x in emoji_ids:
        s = str(x).strip()
        if not s.isdigit() or s in seen:
            continue
        seen.add(s)
        selected.append(s)

    if not selected:
        await msg.answer("❌ Не выбрано ни одного эмодзи.")
        return

    p = await user_params(uid)

    st = await msg.answer(f"🔄 Конвертирую {len(selected)} эмодзи…")
    ok = fail = 0

    for i, eid in enumerate(selected, 1):
        try:
            try:
                await st.edit_text(f"🔄 Конвертирую {i}/{len(selected)}…")
            except Exception:
                pass

            stickers = await bot.get_custom_emoji_stickers([eid])
            if stickers:
                res = await _process(msg, stickers[0], emoji_id=eid)
                if res:
                    ok += 1
                else:
                    fail += 1
            else:
                fail += 1
                await db.add_conversion(
                    user_id=uid,
                    emoji_id=eid,
                    raw_bg=p["raw_bg"],
                    raw_resolution=p["raw_resolution"],
                    raw_quality=p["raw_quality"],
                    raw_fps=p["raw_fps"],
                    success=False,
                    error="Not found (no sticker)",
                )
        except Exception as e:
            fail += 1
            await db.add_conversion(
                user_id=uid,
                emoji_id=eid,
                raw_bg=p["raw_bg"],
                raw_resolution=p["raw_resolution"],
                raw_quality=p["raw_quality"],
                raw_fps=p["raw_fps"],
                success=False,
                error=str(e)[:800],
            )

    await st.edit_text(f"✅ Готово: {ok} успешно, {fail} ошибок.")


@r.message(F.sticker)
async def h_sticker(msg: Message):
    if await db.is_banned(msg.from_user.id):
        return
    await db.get_user(msg.from_user.id)
    await _process(msg, msg.sticker)


@r.message(F.entities)
async def h_entities(msg: Message, state: FSMContext):
    # не мешаем FSM
    if await state.get_state() is not None:
        return
    uid = msg.from_user.id
    if await db.is_banned(uid):
        return

    ids = [e.custom_emoji_id for e in (msg.entities or []) if e.type == "custom_emoji" and e.custom_emoji_id]
    if not ids:
        return

    await db.get_user(uid)
    try:
        first_id = ids[0]
        stickers = await bot.get_custom_emoji_stickers([first_id])
        if stickers:
            await _process(msg, stickers[0], emoji_id=first_id)
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
    if await db.is_banned(uid):
        return

    t = (msg.text or "").strip()
    if not t.isdigit() or len(t) < 6:
        return  # не emoji-id — игнорируем

    await db.get_user(uid)
    try:
        stickers = await bot.get_custom_emoji_stickers([t])
        if stickers:
            await _process(msg, stickers[0], emoji_id=t)
        else:
            await msg.answer("❌ Эмодзи с таким ID не найден.")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: <code>{e}</code>")


# ══════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════

async def main():
    log.info("═══ Bot starting ═══")
    await db.init()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
