# database.py
import sqlite3

DB_NAME = "classroom.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Refresh tables cleanly
    cursor.execute("DROP TABLE IF EXISTS submissions")
    cursor.execute("DROP TABLE IF EXISTS assignments")
    cursor.execute("DROP TABLE IF EXISTS users")
    
    # 1. Users Table (Strict Credentials Blueprint)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_chat_id INTEGER,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('teacher', 'student')) NOT NULL,
            associated_teacher_id INTEGER,
            FOREIGN KEY (associated_teacher_id) REFERENCES users(id)
        )
    ''')
    
    # 2. Assignments Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            task_description TEXT NOT NULL,
            deadline TEXT NOT NULL,
            status TEXT CHECK(status IN ('Assigned', 'In Progress', 'Stuck', 'Completed')) DEFAULT 'Assigned',
            last_reminder_sent TEXT,
            FOREIGN KEY (teacher_id) REFERENCES users(id),
            FOREIGN KEY (student_id) REFERENCES users(id)
        )
    ''')
    
    # 3. Submissions Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER UNIQUE NOT NULL,
            submission_text TEXT,
            file_path TEXT,
            feedback_text TEXT,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id)
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("✅ Database cleanly initialized with strict username/password configuration.")