"""Fingerprint storage and command handlers."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from typing import Dict

from telethon import events
from telethon.errors import FileReferenceExpiredError

from utils import send_media_safe

FINGERPRINTS_FILE = "fingerprints.json"
MAX_FINGERPRINTS = 200


@dataclass
class Fingerprint:
    chat: int
    id: int


class FingerprintManager:
    """Handle fingerprint persistence and operations."""

    def __init__(self, path: str = FINGERPRINTS_FILE) -> None:
        self.path = path
        self.data: Dict[str, Fingerprint] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            self.data = {}
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            # migrate old structure {chat_id: {name: id}}
            if raw and all(isinstance(v, dict) for v in raw.values()):
                first = next(iter(raw.values()))
                if first and isinstance(next(iter(first.values()), None), int):
                    migrated = {}
                    for chat, vals in raw.items():
                        for n, i in vals.items():
                            migrated[n] = {"chat": int(chat), "id": i}
                    raw = migrated

            self.data = {
                name: Fingerprint(**vals) for name, vals in raw.items()
            }
        except Exception:
            self.data = {}

    def _save(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
            json.dump(
                {k: asdict(v) for k, v in self.data.items()},
                f,
                ensure_ascii=False,
                indent=2,
            )
            tmp_name = f.name
        os.replace(tmp_name, self.path)

    # public helpers -----------------------------------------------------
    def add(self, name: str, chat_id: int, msg_id: int) -> bool:
        if len(self.data) >= MAX_FINGERPRINTS and name not in self.data:
            return False
        self.data[name] = Fingerprint(chat_id, msg_id)
        self._save()
        return True

    def remove(self, name: str) -> bool:
        if name in self.data:
            del self.data[name]
            self._save()
            return True
        return False

    def list_names(self) -> list[str]:
        return list(self.data.keys())

    def get(self, name: str) -> Fingerprint | None:
        return self.data.get(name)


def register(client):
    manager = FingerprintManager()

    @client.on(events.NewMessage(pattern=r'^\.اضف بصمه (.+)$'))
    async def add_fingerprint(event):
        name = event.pattern_match.group(1).strip()
        reply = await event.get_reply_message()
        if not reply:
            return await event.reply("↯︙رد على الرسالة اللي تريد تحفظها كبصمة.")

        if not manager.add(name, reply.chat_id, reply.id):
            return await event.reply(
                f"↯︙وصلت الحد الأقصى ({MAX_FINGERPRINTS}) من البصمات.")
        await event.reply(f"↯︙تم حفظ البصمة باسم `{name}`.")

    @client.on(events.NewMessage(pattern=r'^\.اسم البصمه (.+)$'))
    async def send_fingerprint(event):
        name = event.pattern_match.group(1).strip()
        fp = manager.get(name)
        if not fp:
            await event.reply(f"↯︙لا توجد بصمة بهذا الاسم: `{name}`.")
            return await event.delete()

        try:
            msg = await client.get_messages(fp.chat, ids=fp.id)
            if msg.media:
                try:
                    await msg.forward_to(event.chat_id)
                except FileReferenceExpiredError:
                    await send_media_safe(client, event.chat_id, msg.media, caption=msg.message or None)
            else:
                await client.send_message(event.chat_id, msg.message or "")
        except Exception:
            await event.reply("↯︙فشل إرسال البصمة. قد تكون محذوفة.")
        await event.delete()

    @client.on(events.NewMessage(pattern=r'^\.(.+)$'))
    async def send_fingerprint_short(event):
        name = event.pattern_match.group(1).strip()
        fp = manager.get(name)
        if not fp:
            return

        try:
            msg = await client.get_messages(fp.chat, ids=fp.id)
            if msg.media:
                try:
                    await msg.forward_to(event.chat_id)
                except FileReferenceExpiredError:
                    await send_media_safe(client, event.chat_id, msg.media, caption=msg.message or None)
            else:
                await client.send_message(event.chat_id, msg.message or "")
        except Exception:
            await event.reply("↯︙فشل إرسال البصمة. قد تكون محذوفة.")
        await event.delete()

    @client.on(events.NewMessage(pattern=r'^\.بصماتي$'))
    async def list_fingerprints(event):
        names = manager.list_names()
        if not names:
            return await event.reply("↯︙لا توجد أي بصمات محفوظة.")
        text = "↯︙قائمة بصماتك:\n" + "\n".join(f"• {n}" for n in names)
        await event.reply(text)

    @client.on(events.NewMessage(pattern=r'^\.احذف بصمه (.+)$'))
    async def delete_fingerprint(event):
        name = event.pattern_match.group(1).strip()
        if manager.remove(name):
            await event.reply(f"↯︙تم حذف البصمة `{name}`.")
        else:
            await event.reply("↯︙لا توجد بصمة بهذا الاسم.")

    @client.on(events.NewMessage(pattern=r'^\.عدد البصمات$'))
    async def fingerprint_count(event):
        count = len(manager.data)
        await event.reply(f"↯︙عدد البصمات المحفوظة: {count}/{MAX_FINGERPRINTS}")

    @client.on(events.NewMessage(pattern=r'^\.بصمات$'))
    async def fingerprints_markdown_help(event):
        text = (
            "🔖 **قائمة أوامر البصمات**\n\n"
            "• `.اضف بصمه [الاسم]`\n"
            "  └─ لحفظ الرسالة اللي رديت عليها باسم.\n\n"
            "• `.اسم البصمه [الاسم]`\n"
            "  └─ إرسال البصمة حسب الاسم.\n"
            "• `.[الاسم]`\n"
            "  └─ إرسال البصمة مباشرة بالاسم.\n\n"
            "• `.بصماتي`\n"
            "  └─ عرض كل البصمات المحفوظة.\n\n"
            "• `.احذف بصمه [الاسم]`\n"
            "  └─ حذف بصمة معينة من التخزين.\n\n"
            "• `.عدد البصمات`\n"
            "  └─ كم بصمة محفوظة حالياً.\n\n"
            "• `.بصمات`\n"
            "  └─ عرض هذه القائمة.\n\n"
            "**• الحد الأقصى:** `200 بصمة محفوظة` ✅"
        )
        await event.reply(text, parse_mode='md')

__all__ = ["register"]

