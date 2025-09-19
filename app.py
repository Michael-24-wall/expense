


from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'


def init_db():
    try:
        conn = sqlite3.connect('expenses.db')
        c = conn.cursor()
        

        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     username TEXT UNIQUE NOT NULL,
                     email TEXT UNIQUE NOT NULL,
                     password TEXT NOT NULL,
                     created_at TEXT NOT NULL)''')
        
        
        c.execute('''CREATE TABLE IF NOT EXISTS expenses
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER NOT NULL DEFAULT 1,
                     date TEXT NOT NULL,
                     amount REAL NOT NULL,
                     description TEXT NOT NULL,
                     category TEXT NOT NULL)''')
        
    
        c.execute('''CREATE TABLE IF NOT EXISTS user_preferences
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER NOT NULL,
                     currency TEXT DEFAULT '$',
                     monthly_budget REAL DEFAULT 0)''')
        
    
        c.execute("PRAGMA table_info(expenses)")
        columns = [column[1] for column in c.fetchall()]
        if 'user_id' not in columns:
            c.execute('ALTER TABLE expenses ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1')
        
        conn.commit()
        conn.close()
        print("Database initialized successfully!")
        
    except Exception as e:
        print(f"Error initializing database: {e}")

def get_db_connection():
    conn = sqlite3.connect('expenses.db')
    conn.row_factory = sqlite3.Row
    return conn 
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
@login_required
def index():
    try:
        conn = get_db_connection()
        expenses = conn.execute('SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC', 
                               (session['user_id'],)).fetchall()
        
        
        preferences = conn.execute('SELECT * FROM user_preferences WHERE user_id = ?', 
                                  (session['user_id'],)).fetchone()
        conn.close()
        
    
        total = sum(expense['amount'] for expense in expenses)
        
        currency = preferences['currency'] if preferences else '$'
        
        return render_template('index.html', expenses=expenses, total=total, currency=currency)
    
    except sqlite3.Error as e:
        flash('Database error occurred. Please try again.', 'error')
        return render_template('index.html', expenses=[], total=0, currency='$')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if not username or not email or not password:
            flash('Please fill in all required fields!', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long!', 'error')
            return render_template('register.html')
        
        hashed_password = generate_password_hash(password)
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO users (username, email, password, created_at) VALUES (?, ?, ?, ?)',
                         (username, email, hashed_password, created_at))
            
            
            user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            
            
            conn.execute('INSERT INTO user_preferences (user_id) VALUES (?)', (user['id'],))
            
            conn.commit()
            conn.close()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        
        except sqlite3.IntegrityError:
            flash('Username or email already exists!', 'error')
        except sqlite3.Error as e:
            flash('Database error occurred. Please try again.', 'error')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():

    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db_connection()
    
    if request.method == 'POST':
        currency = request.form['currency']
        monthly_budget = float(request.form['monthly_budget']) if request.form['monthly_budget'] else 0
        
        conn.execute('UPDATE user_preferences SET currency = ?, monthly_budget = ? WHERE user_id = ?',
                     (currency, monthly_budget, session['user_id']))
        conn.commit()
        flash('Preferences updated successfully!', 'success')
    
    
    preferences = conn.execute('SELECT * FROM user_preferences WHERE user_id = ?', 
                              (session['user_id'],)).fetchone()
    conn.close()
    
    return render_template('profile.html', preferences=preferences)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        date = request.form['date']
        amount = float(request.form['amount'])
        description = request.form['description']
        category = request.form['category']
        
        if not date or not amount or not description:
            flash('Please fill in all required fields!', 'error')
            return redirect(url_for('add_expense'))
        
        conn = get_db_connection()
        conn.execute('INSERT INTO expenses (user_id, date, amount, description, category) VALUES (?, ?, ?, ?, ?)',
                     (session['user_id'], date, amount, description, category))
        conn.commit()
        conn.close()
        
        flash('Expense added successfully!', 'success')
        return redirect(url_for('index'))
    
    return render_template('add_expense.html')

# DELETE EXPENSE ROUTE
@app.route('/delete/<int:id>')
@login_required
def delete_expense(id):
    conn = get_db_connection()
    
    # Verify that the expense belongs to the current user
    expense = conn.execute('SELECT * FROM expenses WHERE id = ? AND user_id = ?', 
                          (id, session['user_id'])).fetchone()
    
    if expense:
        conn.execute('DELETE FROM expenses WHERE id = ?', (id,))
        conn.commit()
        flash('Expense deleted successfully!', 'success')
    else:
        flash('Expense not found or you do not have permission to delete it.', 'error')
    
    conn.close()
    return redirect(url_for('index'))

# MONTHLY SUMMARY ROUTE
@app.route('/monthly-summary')
@login_required
def monthly_summary():
    conn = get_db_connection()
    
    # Get user preferences for currency
    preferences = conn.execute('SELECT * FROM user_preferences WHERE user_id = ?', 
                              (session['user_id'],)).fetchone()
    currency = preferences['currency'] if preferences else '$'
    
    # Get expenses by category for the current month
    current_month = datetime.now().strftime('%Y-%m')
    expenses = conn.execute('''
        SELECT category, SUM(amount) as total 
        FROM expenses 
        WHERE user_id = ? AND strftime('%Y-%m', date) = ?
        GROUP BY category
    ''', (session['user_id'], current_month)).fetchall()
    
    # Get all monthly subscriptions
    subscriptions = conn.execute('''
        SELECT DISTINCT description, category 
        FROM expenses 
        WHERE user_id = ? AND category IN ('Netflix', 'Amazon', 'Spotify', 'YouTube Premium', 'Apple Music', 'Disney+', 'HBO Max')
        ORDER BY category
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('monthly_summary.html', 
                          expenses=expenses, 
                          subscriptions=subscriptions,
                          current_month=current_month,
                          currency=currency)

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    init_db()
    app.run(debug=True)