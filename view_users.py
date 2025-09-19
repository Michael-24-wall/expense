import sqlite3

def view_users():
    conn = sqlite3.connect('expenses.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    print("Registered Users:")
    print("-" * 50)
    
    users = c.execute('SELECT id, username, email, created_at FROM users ORDER BY created_at DESC').fetchall()
    
    for user in users:
        print(f"ID: {user['id']}")
        print(f"Username: {user['username']}")
        print(f"Email: {user['email']}")
        print(f"Registered: {user['created_at']}")
        print("-" * 30)
    
    conn.close()

if __name__ == '__main__':
    view_users()