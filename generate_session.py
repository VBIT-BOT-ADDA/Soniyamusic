import asyncio
import os
import re
from pathlib import Path
from pyrogram import Client


def read_env_value(file_path: Path, key: str):
    if not file_path.exists():
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}="):
                val = line.split("=", 1)[1].strip()
                return val.strip("\"'")
    return None


async def generate():
    print("=" * 60)
    print("AnonXMusic - Pyrogram Session String Generator")
    print("=" * 60)

    base_dir = Path(__file__).resolve().parent
    env_file = base_dir / ".env"
    sample_env = base_dir / "sample.env"

    api_id_str = (
        read_env_value(env_file, "API_ID")
        or read_env_value(sample_env, "API_ID")
        or os.getenv("API_ID")
    )
    api_hash = (
        read_env_value(env_file, "API_HASH")
        or read_env_value(sample_env, "API_HASH")
        or os.getenv("API_HASH")
    )

    if not api_id_str:
        api_id_str = input("Enter API_ID: ").strip()
    else:
        print(f"Using API_ID: {api_id_str}")

    if not api_hash:
        api_hash = input("Enter API_HASH: ").strip()
    else:
        print(f"Using API_HASH: {api_hash}")

    api_id = int(api_id_str)

    print("\nConnecting to Telegram... You will be prompted for your phone number and OTP.")
    async with Client(
        name="anonx_gen", api_id=api_id, api_hash=api_hash, in_memory=True
    ) as app:
        session_string = await app.export_session_string()

        # Send to Telegram Saved Messages
        try:
            await app.send_message(
                "me",
                f"**AnonXMusic Session String:**\n\n`{session_string}`\n\n⚠️ **Keep this string private!**",
            )
            saved_msg_notice = "✓ Sent to your Telegram Saved Messages!"
        except Exception:
            saved_msg_notice = "(Could not send to Saved Messages)"

        print("\n" + "=" * 60)
        print("SUCCESSFULLY GENERATED SESSION STRING!")
        print("=" * 60)
        print(f"\n{session_string}\n")
        print("=" * 60)
        print(saved_msg_notice)

        # Update or create .env from sample.env
        source_file = env_file if env_file.exists() else sample_env
        content = source_file.read_text(encoding="utf-8")
        if re.search(r"^SESSION=.*$", content, flags=re.MULTILINE):
            updated_content = re.sub(
                r"^SESSION=.*$",
                f"SESSION={session_string}",
                content,
                flags=re.MULTILINE,
            )
        else:
            updated_content = content.rstrip() + f"\nSESSION={session_string}\n"

        env_file.write_text(updated_content, encoding="utf-8")
        print(f"✓ Saved session to {env_file.name}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(generate())
