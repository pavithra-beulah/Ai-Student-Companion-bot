# database.py
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(override=True)

# Pull configuration directly from Render's secure environment settings
DB_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DB_URL:
        raise ValueError("CRITICAL ERROR: DATABASE_URL environment variable is missing!")
    conn = psycopg2.connect(DB_URL)
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Refresh tables cleanly inside PostgreSQL schema using proper cascade structures
    cursor.execute("DROP TABLE IF EXISTS submissions CASCADE;")
    cursor.execute("DROP TABLE IF EXISTS assignments CASCADE;")
    cursor.execute("DROP TABLE IF EXISTS users CASCADE;")
    
    # 1. Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_chat_id BIGINT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('teacher', 'student')) NOT NULL,
            associated_teacher_id INTEGER,
            FOREIGN KEY (associated_teacher_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')
    
    # 2. Assignments Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id SERIAL PRIMARY KEY,
            teacher_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            task_description TEXT NOT NULL,
            deadline TEXT NOT NULL,
            status TEXT CHECK(status IN ('Assigned', 'In Progress', 'Stuck', 'Completed')) DEFAULT 'Assigned',
            last_reminder_sent TEXT,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # 3. Submissions Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id SERIAL PRIMARY KEY,
            assignment_id INTEGER UNIQUE NOT NULL,
            submission_text TEXT,
            file_path TEXT,
            feedback_text TEXT,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("✅ Postgres Database cleanly initialized on Render.")
