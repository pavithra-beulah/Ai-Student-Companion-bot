import os
from flask import Flask, render_template, request, redirect, session, url_for
from database import get_db_connection
from dotenv import load_dotenv
import threading
import time

from reminders import send_proactive_escalations
import bot as telegram_bot  # your bot.py module

# ---------------- ENV ----------------
load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "sim_interview_secret_key_2026")

# ---------------- ROUTES ----------------

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
        user = conn.execute(
            'SELECT * FROM users WHERE username = ? AND password = ?',
            (username, password)
        ).fetchone()
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


# ---------------- TEACHER DASHBOARD ----------------

@app.route('/teacher/dashboard')
def teacher_dashboard():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    assignments = conn.execute('''
        SELECT a.id, u.username as student_name, a.task_description,
               a.deadline, a.status, a.last_reminder_sent,
               s.submission_text, s.feedback_text
        FROM assignments a
        JOIN users u ON a.student_id = u.id
        LEFT JOIN submissions s ON a.id = s.assignment_id
        WHERE a.teacher_id = ?
    ''', (session['user_id'],)).fetchall()
    conn.close()

    return render_template(
        'teacher.html',
        assignments=assignments,
        username=session['username']
    )


# ---------------- STUDENT DASHBOARD ----------------

@app.route('/student/dashboard')
def student_dashboard():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login_page'))

    conn = get_db_connection()
    assignments = conn.execute('''
        SELECT a.id, a.task_description, a.deadline,
               a.status, a.last_reminder_sent,
               s.feedback_text
        FROM assignments a
        LEFT JOIN submissions s ON a.id = s.assignment_id
        WHERE a.student_id = ?
    ''', (session['user_id'],)).fetchall()
    conn.close()

    return render_template(
        'student.html',
        assignments=assignments,
        username=session['username']
    )


# ---------------- FEEDBACK ----------------

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login_page'))

    assignment_id = request.form.get('assignment_id')
    feedback_text = request.form.get('feedback')

    conn = get_db_connection()

    conn.execute('''
        INSERT INTO submissions (assignment_id, feedback_text)
        VALUES (?, ?)
        ON CONFLICT(assignment_id)
        DO UPDATE SET feedback_text = excluded.feedback_text
    ''', (assignment_id, feedback_text))

    assignment = conn.execute('''
        SELECT a.task_description, u.telegram_chat_id
        FROM assignments a
        JOIN users u ON a.student_id = u.id
        WHERE a.id = ?
    ''', (assignment_id,)).fetchone()

    conn.commit()
    conn.close()

    # ---------------- TELEGRAM NOTIFICATION ----------------
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


# ---------------- BACKGROUND THREADS ----------------

def run_bot():
    print("🤖 Telegram bot started...")
    telegram_bot.bot.infinity_polling()


def run_reminders():
    print("⏰ Reminder system started...")
    while True:
        try:
            send_proactive_escalations()
        except Exception as e:
            print(f"Reminder error: {e}")
        time.sleep(30)


# ---------------- MAIN ----------------

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=run_reminders, daemon=True).start()

    print("🚀 Flask app running...")
    app.run(host="0.0.0.0", port=5000)