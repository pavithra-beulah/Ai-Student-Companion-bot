# app.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, session, url_for
from database import get_db_connection
from dotenv import load_dotenv
import threading
import time

from reminders import send_proactive_escalations
import bot as telegram_bot  

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "sim_interview_secret_key_2026")

@app.route('/')
def index():
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    error = None

    if request.method == 'POST':
        username = request.form.get('username').strip().lower()
        password = request.form.get('password').strip()

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            'SELECT * FROM users WHERE username = %s AND password = %s',
            (username, password)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']

            if user['role'] == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            error = "❌ Invalid username or password credentials."

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/teacher/dashboard')
def teacher_dashboard():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT a.id, u.username as student_name, a.task_description,
               a.deadline, a.status, a.last_reminder_sent,
               s.submission_text, s.feedback_text
        FROM assignments a
        JOIN users u ON a.student_id = u.id
        LEFT JOIN submissions s ON a.id = s.assignment_id
        WHERE a.teacher_id = %s
    ''', (session['user_id'],))
    assignments = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template(
        'teacher.html',
        assignments=assignments,
        username=session['username']
    )

@app.route('/student/dashboard')
def student_dashboard():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT a.id, a.task_description, a.deadline,
               a.status, a.last_reminder_sent,
               s.feedback_text
        FROM assignments a
        LEFT JOIN submissions s ON a.id = s.assignment_id
        WHERE a.student_id = %s
    ''', (session['user_id'],))
    assignments = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template(
        'student.html',
        assignments=assignments,
        username=session['username']
    )

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login_page'))

    assignment_id = request.form.get('assignment_id')
    feedback_text = request.form.get('feedback')

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute('''
        INSERT INTO submissions (assignment_id, feedback_text)
        VALUES (%s, %s)
        ON CONFLICT(assignment_id)
        DO UPDATE SET feedback_text = EXCLUDED.feedback_text
    ''', (assignment_id, feedback_text))

    cursor.execute('''
        SELECT a.task_description, u.telegram_chat_id
        FROM assignments a
        JOIN users u ON a.student_id = u.id
        WHERE a.id = %s
    ''', (assignment_id,))
    assignment = cursor.fetchone()

    conn.commit()
    cursor.close()
    conn.close()

    if assignment and assignment['telegram_chat_id']:
        try:
            telegram_bot.bot.send_message(
                assignment['telegram_chat_id'],
                f"💬 New Feedback from your Teacher!\n\n"
                f"📋 Task: {assignment['task_description']}\n\n"
                f"📝 Feedback: {feedback_text}"
            )
        except Exception as e:
            print(f"Telegram error: {e}")

    return redirect(url_for('teacher_dashboard'))

def run_bot():
    print("🤖 Telegram bot started...")
    # Change infinity_polling() to regular polling with non_stop handling
    try:
        telegram_bot.bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"Bot polling crashed: {e}")

def run_reminders():
    print("⏰ Reminder system started...")
    while True:
        try:
            send_proactive_escalations()
        except Exception as e:
            print(f"Reminder error: {e}")
        time.sleep(30)

if __name__ == "__main__":
    # 1. Intercept the port right away
    bind_port = int(os.getenv("PORT", 5000))
    print(f"🚀 Flask app preparing on port {bind_port}...")
    
    # 2. Start your threads with a slight structural breathing room
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    reminder_thread = threading.Thread(target=run_reminders, daemon=True)
    
    bot_thread.start()
    reminder_thread.start()

    # 3. Hand over control to Flask
    app.run(host="0.0.0.0", port=bind_port)
