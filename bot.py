# bot.py
import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor
import telebot
import requests
from dotenv import load_dotenv
from database import get_db_connection
from agents.orchestrator import AgentOrchestrator

load_dotenv(override=True)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

print(f"Loading Bot Token: {'Found' if BOT_TOKEN else 'NOT FOUND'}")

DOWNLOAD_DIR = "static/uploads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
orchestrator = AgentOrchestrator()

def sanitize_telegram_html(text: str) -> str:
    text = re.sub(r"```html|```", "", text)
    text = text.replace("<html>", "").replace("</html>", "")
    text = text.replace("<body>", "").replace("</body>", "")
    text = text.replace("<head>", "").replace("</head>", "")
    text = text.replace("<ul>", "").replace("</ul>", "")
    text = text.replace("<ol>", "").replace("</ol>", "")
    text = text.replace("<li>", "• ").replace("</li>", "\n")
    return text.strip()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    print(f"📥 Received /start from chat ID: {message.chat.id}")
    welcome_text = (
        "🤖 <b>Welcome to the SIM Classroom Companion!</b>\n\n"
        "Register your profile to connect with your classroom:\n"
        "👉 <code>/register teacher [Your Name] [Password]</code>\n"
        "👉 <code>/register student [Your Name] [Password] [Teacher Name]</code>\n\n"
        "🔄 <b>Multi-User Sandbox Switching:</b>\n"
        "• To switch to a Teacher role: <code>/switch</code>\n"
        "• To switch to a Student role: <code>/switch [teacher_username]</code>"
    )
    bot.reply_to(message, welcome_text, parse_mode="HTML")

@bot.message_handler(commands=['register'])
def register_user(message):
    print(f"📥 Received registration request: {message.text}")
    parts = message.text.split()
    
    if len(parts) < 4:
        bot.reply_to(
            message, 
            "⚠️ <b>Registration Format:</b>\n\n"
            "🏫 <b>Teachers use:</b>\n<code>/register teacher [Username] [Password]</code>\n\n"
            "🎒 <b>Students use:</b>\n<code>/register student [Username] [Password] [TeacherUsername]</code>",
            parse_mode="HTML"
        )
        return
        
    role = parts[1].lower()
    username = parts[2].strip().lower()
    password = parts[3].strip()
    chat_id = message.chat.id
    
    if role not in ['teacher', 'student']:
        bot.reply_to(message, "⚠️ Role must be either 'teacher' or 'student'.")
        return

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if role == 'student':
            if len(parts) < 5:
                bot.reply_to(message, "⚠️ Students must provide their teacher's username at the end!", parse_mode="HTML")
                cursor.close()
                conn.close()
                return
            teacher_username = parts[4].strip().lower()
            cursor.execute("SELECT id FROM users WHERE role='teacher' AND username = %s", (teacher_username,))
            teacher = cursor.fetchone()
            
            if not teacher:
                bot.reply_to(message, f"❌ Registration failed: Could not find teacher '{teacher_username}'.", parse_mode="HTML")
                cursor.close()
                conn.close()
                return
                
            cursor.execute(
                "INSERT INTO users (telegram_chat_id, username, password, role, associated_teacher_id) VALUES (%s, %s, %s, %s, %s)", 
                (chat_id, username, password, role, teacher['id'])
            )
            bot.reply_to(message, f"✅ <b>Student Registered!</b>\nLinked to Teacher: <code>{teacher_username}</code>", parse_mode="HTML")
        
        elif role == 'teacher':
            cursor.execute(
                "INSERT INTO users (telegram_chat_id, username, password, role) VALUES (%s, %s, %s, %s)", 
                (chat_id, username, password, role)
            )
            bot.reply_to(message, f"✅ <b>Teacher Registered!</b>\nUsername: <code>{username}</code>", parse_mode="HTML")
            
        conn.commit()
    except Exception as e:
        bot.reply_to(message, f"⚠️ Registration roadmap barrier: username taken or collision.")
        print(f"❌ DB Registration Error: {e}")
    finally:
        cursor.close()
        conn.close()

@bot.message_handler(commands=['login'])
def login_as_user(message):
    chat_id = message.chat.id
    parts = message.text.split()
    
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ <b>Login Format:</b> <code>/login [username]</code>", parse_mode="HTML")
        return
        
    target_username = parts[1].strip().lower()
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM users WHERE username = %s", (target_username,))
    account = cursor.fetchone()
    
    if not account:
        bot.reply_to(message, f"❌ <b>Login Failed:</b> The username <code>{target_username}</code> does not exist.", parse_mode="HTML")
        cursor.close()
        conn.close()
        return
        
    cursor.execute("UPDATE users SET telegram_chat_id = %s WHERE username = %s", (chat_id, target_username))
    cursor.execute("UPDATE users SET telegram_chat_id = NULL WHERE username != %s AND telegram_chat_id = %s", (target_username, chat_id))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    role_emoji = "🏫" if account['role'] == 'teacher' else "🎒"
    bot.reply_to(
        message, 
        f"🔓 <b>Session Login Successful!</b>\n"
        f"👤 Identity: <code>{target_username}</code>\n"
        f"{role_emoji} Active Role: <code>{account['role'].upper()}</code>\n\n"
        f"<i>All incoming traffic states are now routed to this profile context.</i>",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['summary'])
def send_progress_summary(message):
    chat_id = message.chat.id
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM users WHERE telegram_chat_id = %s", (chat_id,))
    user = cursor.fetchone()
    if not user or user['role'] != 'teacher':
        bot.reply_to(message, "❌ Access Denied. Only registered teachers can request summaries.")
        cursor.close()
        conn.close()
        return

    parts = message.text.split()
    target_student = None
    
    if len(parts) > 1:
        for word in parts[1:]:
            clean_word = word.strip().lower().replace("?", "")
            if clean_word not in ["how", "is", "doing", "this", "week", "about"]:
                target_student = clean_word
                break

    if target_student:
        bot.reply_to(message, f"📊 <b>[Summariser Agent]</b> Pulling logs for <code>{target_student}</code>...", parse_mode="HTML")
        cursor.execute('''
            SELECT u.username as student_name, a.task_description, a.deadline, a.status
            FROM assignments a
            JOIN users u ON a.student_id = u.id
            WHERE u.username LIKE %s AND a.teacher_id = %s
        ''', (f"%{target_student}%", user['id']))
        active_rows = cursor.fetchall()
        report = orchestrator.summarizer_agent_single(target_student, message.text, active_rows)
    else:
        bot.reply_to(message, "📊 <b>[Summariser Agent]</b> Compiling your classroom summary...", parse_mode="HTML")
        cursor.execute('''
            SELECT u.username as student_name, a.task_description, a.deadline, a.status
            FROM assignments a
            JOIN users u ON a.student_id = u.id
            WHERE a.teacher_id = %s
        ''', (user['id'],))
        active_rows = cursor.fetchall()
        report = orchestrator.summarizer_agent_global(active_rows)
        
    cursor.close()
    conn.close()
    report = sanitize_telegram_html(report)
    bot.send_message(chat_id, report, parse_mode="HTML")

@bot.message_handler(content_types=['photo', 'document'])
def handle_homework_file(message):
    chat_id = message.chat.id
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM users WHERE telegram_chat_id = %s", (chat_id,))
    user = cursor.fetchone()
    if not user or user['role'] != 'student':
        bot.reply_to(message, "❌ Only registered students can turn in file assignments.")
        cursor.close()
        conn.close()
        return
        
    cursor.execute("SELECT * FROM assignments WHERE student_id = %s AND status != 'Completed' ORDER BY id DESC LIMIT 1", (user['id'],))
    active_task = cursor.fetchone()
    if not active_task:
        bot.reply_to(message, "⚠️ You have no active pending tasks to submit files for.")
        cursor.close()
        conn.close()
        return

    bot.reply_to(message, "📥 Downloading your file attachment submission...")

    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
        file_name = f"submission_{active_task['id']}.jpg"
    else:
        file_id = message.document.file_id
        file_name = message.document.file_name

    try:
        file_info = bot.get_file(file_id)
        file_download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        
        file_response = requests.get(file_download_url)
        local_path = os.path.join(DOWNLOAD_DIR, file_name)
        with open(local_path, 'wb') as new_file:
            new_file.write(file_response.content)

        cursor.execute("""
            INSERT INTO submissions (assignment_id, submission_text, file_path) 
            VALUES (%s, %s, %s)
            ON CONFLICT(assignment_id) DO UPDATE SET file_path=EXCLUDED.file_path, submission_text=EXCLUDED.submission_text
        """, (active_task['id'], f"File attachment turned in: {file_name}", local_path))
        
        cursor.execute("UPDATE assignments SET status = 'Completed' WHERE id = %s", (active_task['id'],))
        conn.commit()
        
        bot.reply_to(message, f"🎉 <b>File successfully turned in!</b>", parse_mode="HTML")

        cursor.execute("SELECT * FROM users WHERE id = %s", (active_task['teacher_id'],))
        teacher = cursor.fetchone()
        if teacher and teacher['telegram_chat_id']:
            try:
                prompt_msg = (
                    f"📬 <b>New Submission Received!</b>\n"
                    f"👤 <b>Student:</b> <code>{user['username']}</code>\n"
                    f"📝 <b>Task:</b> {active_task['task_description']}\n\n"
                    f"💬 <b>To leave feedback for this student, reply directly to this message!</b>"
                )
                bot.send_message(teacher['telegram_chat_id'], prompt_msg, parse_mode="HTML")
            except Exception as DM_err:
                print(f"Could not reach teacher via DM: {DM_err}")
                
    except Exception as e:
        bot.reply_to(message, "❌ System failed to download file attachment.")
        print(f"File handling Error: {e}")
    finally:
        cursor.close()
        conn.close()

@bot.message_handler(func=lambda message: True)
def handle_conversation(message):
    chat_id = message.chat.id
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM users WHERE telegram_chat_id = %s", (chat_id,))
    user = cursor.fetchone()
    
    if not user:
        bot.reply_to(message, "❌ Please register first by sending `/register [role] [username] [password]`.")
        cursor.close()
        conn.close()
        return

    intent = orchestrator.route_intent(message.text, user['role'])

    if user['role'] == 'teacher':
        if message.reply_to_message and "New Submission Received!" in message.reply_to_message.text:
            try:
                match = re.search(r"Student:\s+([a-zA-Z0-9_]+)", message.reply_to_message.text)
                if match:
                    student_username = match.group(1).strip()
                    cursor.execute("SELECT * FROM users WHERE role='student' AND username = %s", (student_username,))
                    student = cursor.fetchone()
                    
                    if student:
                        feedback_text = message.text
                        student_alert = f"📝 <b>New Feedback from Teacher {user['username']}:</b>\n\n💬 <i>\"{feedback_text}\"</i>"
                        bot.send_message(student['telegram_chat_id'], student_alert, parse_mode="HTML")
                        bot.reply_to(message, f"✅ Feedback successfully delivered to student <code>{student_username}</code>!", parse_mode="HTML")
                        cursor.close()
                        conn.close()
                        return
            except Exception as feedback_err:
                print(f"Failed to route teacher feedback safely: {feedback_err}")

        if intent == "ASSIGNMENT":
            bot.reply_to(message, "🧠 <b>[Teacher Agent]</b> Processing assignment text layout...")
            extracted = orchestrator.teacher_agent_parse(message.text)
            
            student_username = extracted.get('student_name')
            task_desc = extracted.get('task')
            deadline = extracted.get('deadline')
            
            if student_username and student_username.lower() != 'null':
                cursor.execute("""
                    SELECT * FROM users 
                    WHERE role='student' AND username LIKE %s
                """, (f"%{student_username.lower().strip()}%",))
                student = cursor.fetchone()
                
                if student:
                    cursor.execute("""
                        UPDATE users SET associated_teacher_id = %s WHERE id = %s
                    """, (user['id'], student['id']))
                    cursor.execute("""
                        INSERT INTO assignments (teacher_id, student_id, task_description, deadline) 
                        VALUES (%s, %s, %s, %s)
                    """, (user['id'], student['id'], task_desc, deadline))
                    
                    conn.commit()
                    bot.reply_to(message, f"📝 <b>Assignment Logged!</b>\n👤 Student: <code>{student['username']}</code>\n⏳ Deadline: {deadline}", parse_mode="HTML")
                    try:
                        bot.send_message(student['telegram_chat_id'], f"🔔 <b>New Assignment from Teacher {user['username']}:</b>\n\n📝 {task_desc}\n⏳ <b>Due:</b> {deadline}", parse_mode="HTML")
                    except Exception as DM_err:
                        print(f"Couldn't DM student directly: {DM_err}")
                else:
                    bot.reply_to(message, f"🔍 Student username '{student_username}' not found.")
            else:
                bot.reply_to(message, "💡 Couldn't spot a student username identifier.")

        elif intent == "QUERY":
            bot.reply_to(message, "📊 <b>[Summariser Agent]</b> Processing performance records...")
            target_student = None
            for word in message.text.split():
                clean_word = word.strip().lower().replace("?", "")
                if clean_word not in ["how", "is", "doing", "this", "week", "about"]:
                    target_student = clean_word
                    break
                    
            if target_student:
                cursor.execute('''
                    SELECT u.username as student_name, a.task_description, a.deadline, a.status
                    FROM assignments a
                    JOIN users u ON a.student_id = u.id
                    WHERE u.username LIKE %s AND a.teacher_id = %s
                ''', (f"%{target_student}%", user['id']))
                active_rows = cursor.fetchall()
                
                report = orchestrator.summarizer_agent_single(target_student, message.text, active_rows)
                report = sanitize_telegram_html(report)
                bot.send_message(chat_id, report, parse_mode="HTML")
            else:
                bot.reply_to(message, "🔍 Could not isolate the student's username.")
        else:
            bot.reply_to(message, "👋 Welcome! You can assign work naturally or request analytics tracking.")

    elif user['role'] == 'student':
        cursor.execute("SELECT * FROM assignments WHERE student_id = %s AND status != 'Completed' ORDER BY id DESC LIMIT 1", (user['id'],))
        active_task = cursor.fetchone()
        if not active_task:
            bot.reply_to(message, "🌟 You don't have any pending assignments right now.")
            cursor.close()
            conn.close()
            return
            
        bot.reply_to(message, "🤖 <b>[Student Agent]</b> Classifying status metric...")
        new_status = orchestrator.student_agent_classify(message.text)
        
        if new_status == 'Completed':
            bot.reply_to(message, "🎉 <b>Awesome job!</b> Please upload/attach your submission document or photo here to officially complete this task!", parse_mode="HTML")
        else:
            cursor.execute("UPDATE assignments SET status = %s WHERE id = %s", (new_status, active_task['id']))
            bot.reply_to(message, f"👍 <b>Status Updated to:</b> <code>{new_status}</code>", parse_mode="HTML")
            conn.commit()
            
    cursor.close()
    conn.close()

if __name__ == '__main__':
    print("🚀 TeleBot Engine running cleanly.")
    bot.polling(none_stop=True, interval=0, timeout=20)
