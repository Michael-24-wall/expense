import sqlite3
import os

def migrate_database():
    
    conn = sqlite3.connect('expenses.db')
    c = conn.cursor()
    
    try:
        print("Checking database structure...")
        
        
        c.execute("PRAGMA table_info(expenses)")
        columns = [column[1] for column in c.fetchall()]
        
        if 'user_id' not in columns:
            print("Migrating database: Adding user_id column to expenses table...")
            
            
            c.execute('''CREATE TABLE expenses_new
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL DEFAULT 1,
                         date TEXT NOT NULL,
                         amount REAL NOT NULL,
                         description TEXT NOT NULL,
                         category TEXT NOT NULL)''')
            
        
            c.execute('INSERT INTO expenses_new (date, amount, description, category) SELECT date, amount, description, category FROM expenses')
            
            
            c.execute('DROP TABLE expenses')
            
        
            c.execute('ALTER TABLE expenses_new RENAME TO expenses')
            
            print("Expenses table migration completed successfully!")
        else:
            print("Expenses table already has the user_id column.")
        
        
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not c.fetchone():
            print("Creating users table...")
            c.execute('''CREATE TABLE users
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         username TEXT UNIQUE NOT NULL,
                         email TEXT UNIQUE NOT NULL,
                         password TEXT NOT NULL,
                         created_at TEXT NOT NULL)''')
        
    
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_preferences'")
        if not c.fetchone():
            print("Creating user_preferences table...")
            c.execute('''CREATE TABLE user_preferences
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         currency TEXT DEFAULT '$',
                         monthly_budget REAL DEFAULT 0)''')
            
        print("Database migration completed successfully!")
            
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.commit()
        conn.close()

if __name__ == '__main__':
    migrate_database()
    print("Migration process completed. You can now run your Flask application.")