"""
One-shot script: Reset admin password hash to work with SHA256+bcrypt prehash.
Run inside backend container: python reset_admin_password.py
"""
import asyncio
import hashlib
from passlib.context import CryptContext
import asyncpg


async def main():
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    prehashed = hashlib.sha256("admin123".encode()).hexdigest()
    new_hash = ctx.hash(prehashed)

    # Verify it works
    assert ctx.verify(prehashed, new_hash), "Hash verification failed!"
    print(f"New hash: {new_hash[:30]}...")

    conn = await asyncpg.connect("postgresql://doanbac07:070301@postgres:5432/attendance_db")
    result = await conn.execute("UPDATE admins SET password_hash = $1", new_hash)
    print(f"Updated: {result}")

    rows = await conn.fetch("SELECT email, LEFT(password_hash,20) as h FROM admins")
    for r in rows:
        print(f"  {r['email']} → {r['h']}...")

    await conn.close()
    print("Done. Login with password: admin123")


asyncio.run(main())
