# gunicorn.conf.py
import threading
import os

def post_fork(server, worker):
    """
    Fires right after a Gunicorn worker process is created. 
    Locks execution specifically to the first worker instance to prevent 409 collisions.
    """
    # 1. Access Gunicorn's internal worker tracking instance index
    # worker.age starts at 1 for the first worker process spawned
    if worker.age > 1:
        server.log.info(f"🛑 Gunicorn Worker {worker.age}: Skipping background threads to prevent token duplicate conflicts.")
        return

    server.log.info(f"🎯 Gunicorn Worker {worker.age} designated as Primary. Spinning up backend configurations...")
    
    # Delayed runtime imports to isolate memory states cleanly
    from app import run_bot, run_reminders, init_db

    # 2. Re-initialize database structures exactly once
    print("♻️ Re-initializing database tables via primary fork...")
    try:
        init_db()
        print("✅ Postgres Database cleanly initialized on Render.")
    except Exception as db_err:
        print(f"❌ Database initialization failed: {db_err}")

    # 3. Spawn the background polling networks exactly once
    print("🚀 Spawning unique single-instance background workers...")
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=run_reminders, daemon=True).start()
