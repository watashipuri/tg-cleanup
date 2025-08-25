# cleanup_channel.py (устойчивый к пустым секретам)
import os, asyncio
from telethon import TelegramClient, errors
from telethon.tl.types import ChannelParticipantsAdmins

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION  = "cleanup_session"
CHANNEL  = os.getenv("CHANNEL")  # @username или -100...

def getenv_int(name: str, default: int) -> int:
    s = os.getenv(name)
    try:
        return int(s.strip()) if s is not None and s.strip() != "" else default
    except Exception:
        return default

def parse_ids(s: str | None) -> set[int]:
    res: set[int] = set()
    if not s:
        return res
    for part in s.replace(" ", "").split(","):
        if not part:
            continue
        try:
            res.add(int(part))
        except Exception:
            pass
    return res

# безопасные чтения опций
WHITELIST = parse_ids(os.getenv("WHITELIST"))
BATCH     = getenv_int("BATCH", 20)   # сколько киков подряд
SLEEP     = getenv_int("SLEEP", 3)    # пауза между партиями (сек)
DRY_RUN   = getenv_int("DRY_RUN", 1) == 1   # 1 = только вывод без удаления

client = TelegramClient(SESSION, API_ID, API_HASH)

async def main():
    assert CHANNEL, "CHANNEL secret is empty"
    me = await client.get_me()
    if me and me.id:
        WHITELIST.add(me.id)  # самого себя никогда не трогаем

    # соберём админов (их не кикаем)
    admins = {u.id async for u in client.iter_participants(CHANNEL, filter=ChannelParticipantsAdmins())}

    print(f"Channel: {CHANNEL}")
    print(f"Options: DRY_RUN={DRY_RUN}, BATCH={BATCH}, SLEEP={SLEEP}")
    print(f"Admins: {len(admins)} | Whitelist: {len(WHITELIST)}")

    kicked = 0
    batch  = 0
    cand   = 0

    async for u in client.iter_participants(CHANNEL):
        uid = u.id
        if uid in admins or uid in WHITELIST:
            continue

        cand += 1
        uname = f'@{u.username}' if u.username else ''
        if DRY_RUN:
            print(f"[DRY]  uid={uid} {uname}")
            continue

        try:
            await client.kick_participant(CHANNEL, uid)
            kicked += 1
            batch  += 1
            print(f"[KICK] uid={uid} {uname} | total={kicked}")
        except errors.UserAdminInvalidError:
            # попытались кикнуть админа/владельца — пропуск
            continue
        except errors.ChatAdminRequiredError:
            print("❌ Need 'Ban users' admin right in the channel.")
            break
        except errors.FloodWaitError as e:
            wait = int(getattr(e, "seconds", 30))
            print(f"⏳ FLOOD_WAIT {wait}s…")
            await asyncio.sleep(wait)
            continue
        except Exception as e:
            print("Error:", e)
            continue

        if batch >= BATCH:
            batch = 0
            print(f"Pause {SLEEP}s…")
            await asyncio.sleep(SLEEP)

    print(f"Done. Candidates={cand}, Kicked={kicked}, Kept≈{len(admins)+len(WHITELIST)}")

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
