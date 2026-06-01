# gunicorn.conf.py
import threading
import os

def post_fork(server, worker):
    """
    This hook runs EXACTLY ONCE on Gunicorn's worker initialization.
    It ensures background threads start safely after the process forks.
    """
    # Prevent running inside auxiliary testing setups
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        return

    server.log.info("🎯 Gunicorn Worker Forked: Starting background tasks...")
    
    # Delay imports until inside the fork context to prevent parent process contamination
    from app import run_bot, run_reminders, init_db

    # 1. Initialize the database exactly once on startup
    print("♻️ Re-initializing database tables via post-fork...")
    try:
        init_db()
        print("✅ Postgres Database cleanly initialized on Render.")
    except Exception as db_err:
        print(f"❌ Database initialization failed: {db_err}")

    # 2. Spawn the background bot and reminder threads safely
    print("🚀 Spawning single-instance production background workers...")
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=run_reminders, daemon=True).start()
