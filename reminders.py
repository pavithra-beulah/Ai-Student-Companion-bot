# reminders.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import telebot
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DB_URL = os.getenv("DATABASE_URL")
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

def parse_days_left(deadline_str):
    try:
        numbers = [int(s) for s in deadline_str.split() if s.isdigit()]
        return numbers[0] if numbers else 2
    except:
        return 2

def send_proactive_escalations():
    if not bot or not DB_URL:
        print("Bot token or DB link unavailable.")
        return
        
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT a.id as assignment_id, a.task_description, a.deadline, a.status, a.last_reminder_sent, u.telegram_chat_id, u.username
        FROM assignments a
        JOIN users u ON a.student_id = u.id
        WHERE a.status NOT IN ('Completed')
    ''')
    pending = cursor.fetchall()
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for row in pending:
        if row['last_reminder_sent'] == today_str:
            continue
            
        chat_id = row['telegram_chat_id']
        status = row['status']
        task = row['task_description']
        deadline = row['deadline']
        student_display_name = row['username']
        
        days_left = parse_days_left(deadline)
        
        if status == 'Stuck':
            msg = f"🚨 <b>Urgent Blockage Alert, {student_display_name}!</b>\n\nYou flagged your assignment <i>'{task}'</i> as <b>Stuck</b>. Let's get you past this blocker! Reply directly to this message with what's holding you back."
        elif days_left <= 1 or "tomorrow" in deadline.lower():
            msg = f"🔥 <b>Urgent Deadline Approaching, {student_display_name}!</b>\n\nYour assignment <i>'{task}'</i> is due very soon (<b>{deadline}</b>).\n⏱️ Status: <code>{status}</code>\nPlease update your progress or submit your files right here!"
        else:
            msg = f"⏳ <b>Daily Progress Check-In:</b>\n\nHey {student_display_name}, just checking in on your assignment: <i>'{task}'</i>.\nTarget Deadline: <b>{deadline}</b>.\nSimply text me a quick update here!"

        if chat_id:
            try:
                bot.send_message(chat_id, msg, parse_mode="HTML")
                cursor.execute(
                    "UPDATE assignments SET last_reminder_sent = %s WHERE id = %s", 
                    (today_str, row['assignment_id'])
                )
                conn.commit()
                print(f"📊 Fired dynamic nudge to {student_display_name} for task: {task[:15]}...")
            except Exception as e:
                print(f"Could not reach chat profile {chat_id}: {e}")
                
    cursor.close()
    conn.close()

if __name__ == '__main__':
    CHECK_INTERVAL_SECONDS = 30 
    print(f"🚀 Proactive Reminder Daemon running background checks every {CHECK_INTERVAL_SECONDS}s...")
    while True:
        try:
            send_proactive_escalations()
        except Exception as err:
            print(f"Background Loop Error: {err}")
        time.sleep(CHECK_INTERVAL_SECONDS)
