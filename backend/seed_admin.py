import asyncio
import hashlib
import uuid
from passlib.context import CryptContext
import asyncpg

async def main():
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    prehashed = hashlib.sha256("admin123".encode()).hexdigest()
    new_hash = ctx.hash(prehashed)
    
    conn = await asyncpg.connect("postgresql://doanbac07:070301@postgres:5432/attendance_db")
    
    # Check if admin exists
    admin = await conn.fetchrow("SELECT id FROM admins WHERE email = $1", "admin@school.edu.vn")
    
    if not admin:
        print("Admin user not found, inserting...")
        await conn.execute(
            """
            INSERT INTO admins (id, username, email, password_hash, full_name, role, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            str(uuid.uuid4()),
            "admin",
            "admin@school.edu.vn",
            new_hash,
            "System Admin",
            "admin",
            True
        )
        print("Admin user inserted successfully.")
    else:
        print("Admin user already exists, updating password...")
        await conn.execute("UPDATE admins SET password_hash = $1 WHERE email = $2", new_hash, "admin@school.edu.vn")
        print("Admin password updated successfully.")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
