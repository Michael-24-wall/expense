import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, redirect, render_template_string, session, flash, url_for
import hashlib
import os
import json
from functools import wraps


try:
    import stripe
except ImportError:
    
    stripe = None
    print("Stripe not installed. Payment features will be disabled.")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key_change_in_production")
app.config['STRIPE_PUBLIC_KEY'] = os.environ.get("STRIPE_PUBLIC_KEY", "pk_test_your_key_here")
app.config['STRIPE_SECRET_KEY'] = os.environ.get("STRIPE_SECRET_KEY", "sk_test_your_key_here")

if stripe:
    stripe.api_key = app.config['STRIPE_SECRET_KEY']

# Database initialization
def init_db():
    """Initialize the database with required tables"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_premium INTEGER DEFAULT 0,
            stripe_customer_id TEXT,
            subscription_id TEXT,
            subscription_status TEXT DEFAULT 'inactive'
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            budget_limit REAL,
            color TEXT DEFAULT '#4361ee',
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id, name)
        )
    ''')
    

    default_categories = [
        ('Food', '#4361ee'),
        ('Transport', '#3a0ca3'),
        ('Entertainment', '#f72585'),
        ('Utilities', '#4cc9f0'),
        ('Rent', '#ffd166'),
        ('Healthcare', '#06d6a0'),
        ('Other', '#6c757d')
    ]
    
    # This will be copied for each user when they register
    c.execute('''
        CREATE TABLE IF NOT EXISTS default_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT NOT NULL
        )
    ''')
    
    
    c.execute('SELECT COUNT(*) FROM default_categories')
    if c.fetchone()[0] == 0:
        for name, color in default_categories:
            c.execute('INSERT INTO default_categories (name, color) VALUES (?, ?)', (name, color))
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Create a database connection"""
    conn = sqlite3.connect('expenses.db')
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    """Decorator to ensure user is logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_categories(user_id):
    """Get categories for a specific user"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM categories WHERE user_id = ? ORDER BY name', (user_id,))
    categories = c.fetchall()
    conn.close()
    return categories

def get_category_totals(user_id, period="all"):
    """Get total expenses by category for a user"""
    conn = get_db_connection()
    c = conn.cursor()
    
    date_condition = ""
    if period == "today":
        date_condition = "AND date(e.date) = date('now')"
    elif period == "week":
        date_condition = "AND date(e.date) >= date('now', '-7 days')"
    elif period == "month":
        date_condition = "AND date(e.date) >= date('now', '-30 days')"
    
    c.execute(f'''
        SELECT c.name, c.color, COALESCE(SUM(e.amount), 0) as total
        FROM categories c
        LEFT JOIN expenses e ON c.name = e.category AND e.user_id = ?
        WHERE c.user_id = ? {date_condition}
        GROUP BY c.name
        ORDER BY total DESC
    ''', (user_id, user_id))
    
    category_totals = {}
    for row in c.fetchall():
        category_totals[row['name']] = {
            'total': row['total'],
            'color': row['color']
        }
    
    conn.close()
    return category_totals

def get_totals(user_id, period="all"):
    """Get total expenses for different periods for a user"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Today's total
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date(date) = ?", (user_id, today))
    daily_total = c.fetchone()[0] or 0
    
    # Weekly total
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    c.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date(date) >= ?", (user_id, week_ago))
    weekly_total = c.fetchone()[0] or 0
    
    # Monthly total
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    c.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date(date) >= ?", (user_id, month_ago))
    monthly_total = c.fetchone()[0] or 0
    
    # All time total
    c.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ?", (user_id,))
    total_expenses = c.fetchone()[0] or 0
    
    conn.close()
    return daily_total, weekly_total, monthly_total, total_expenses

def get_expenses(user_id, period="all", category=None, limit=None):
    """Get expenses for a user with optional filters"""
    conn = get_db_connection()
    c = conn.cursor()
    
    query = '''
        SELECT e.*, c.color 
        FROM expenses e 
        LEFT JOIN categories c ON e.category = c.name AND e.user_id = c.user_id
        WHERE e.user_id = ?
    '''
    params = [user_id]
    
    if period == "today":
        query += " AND date(e.date) = date('now')"
    elif period == "week":
        query += " AND date(e.date) >= date('now', '-7 days')"
    elif period == "month":
        query += " AND date(e.date) >= date('now', '-30 days')"
    
    if category:
        query += " AND e.category = ?"
        params.append(category)
    
    query += " ORDER BY e.date DESC"
    
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    
    c.execute(query, params)
    expenses = c.fetchall()
    conn.close()
    return expenses

def get_user(user_id):
    """Get user by ID"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    return user

# HTML Templates
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - ExpenseTracker Pro</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Poppins', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        .auth-container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 15px 50px rgba(0, 0, 0, 0.2);
            width: 100%;
            max-width: 450px;
            overflow: hidden;
            padding: 40px;
        }
        
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .logo i {
            font-size: 3rem;
            color: #4361ee;
            margin-bottom: 15px;
        }
        
        .logo h1 {
            font-size: 2rem;
            color: #333;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #555;
        }
        
        input {
            width: 100%;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s;
        }
        
        input:focus {
            outline: none;
            border-color: #4361ee;
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        button {
            background: #4361ee;
            color: white;
            border: none;
            padding: 15px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            width: 100%;
            transition: all 0.3s;
        }
        
        button:hover {
            background: #3a0ca3;
        }
        
        .auth-footer {
            text-align: center;
            margin-top: 20px;
        }
        
        .auth-footer a {
            color: #4361ee;
            text-decoration: none;
            font-weight: 600;
        }
        
        .auth-footer a:hover {
            text-decoration: underline;
        }
        
        .notification {
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            font-weight: 500;
        }
        
        .notification.error {
            background: #ffebee;
            color: #d32f2f;
            border: 1px solid #ffcdd2;
        }
        
        .notification.success {
            background: #e8f5e9;
            color: #388e3c;
            border: 1px solid #c8e6c9;
        }
    </style>
</head>
<body>
    <div class="auth-container">
        <div class="logo">
            <i class="fas fa-wallet"></i>
            <h1>ExpenseTracker Pro</h1>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="notification {{ category }}">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <form method="POST" action="{{ url_for('login') }}">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required>
            </div>
            
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            
            <button type="submit">Login</button>
        </form>
        
        <div class="auth-footer">
            <p>Don't have an account? <a href="{{ url_for('register') }}">Register</a></p>
        </div>
    </div>
</body>
</html>
"""

REGISTER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register - ExpenseTracker Pro</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Poppins', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        .auth-container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 15px 50px rgba(0, 0, 0, 0.2);
            width: 100%;
            max-width: 450px;
            overflow: hidden;
            padding: 40px;
        }
        
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .logo i {
            font-size: 3rem;
            color: #4361ee;
            margin-bottom: 15px;
        }
        
        .logo h1 {
            font-size: 2rem;
            color: #333;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #555;
        }
        
        input {
            width: 100%;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s;
        }
        
        input:focus {
            outline: none;
            border-color: #4361ee;
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        button {
            background: #4361ee;
            color: white;
            border: none;
            padding: 15px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            width: 100%;
            transition: all 0.3s;
        }
        
        button:hover {
            background: #3a0ca3;
        }
        
        .auth-footer {
            text-align: center;
            margin-top: 20px;
        }
        
        .auth-footer a {
            color: #4361ee;
            text-decoration: none;
            font-weight: 600;
        }
        
        .auth-footer a:hover {
            text-decoration: underline;
        }
        
        .notification {
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            font-weight: 500;
        }
        
        .notification.error {
            background: #ffebee;
            color: #d32f2f;
            border: 1px solid #ffcdd2;
        }
    </style>
</head>
<body>
    <div class="auth-container">
        <div class="logo">
            <i class="fas fa-wallet"></i>
            <h1>ExpenseTracker Pro</h1>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="notification {{ category }}">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <form method="POST" action="{{ url_for('register') }}">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required>
            </div>
            
            <div class="form-group">
                <label for="email">Email</label>
                <input type="email" id="email" name="email" required>
            </div>
            
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            
            <div class="form-group">
                <label for="confirm_password">Confirm Password</label>
                <input type="password" id="confirm_password" name="confirm_password" required>
            </div>
            
            <button type="submit">Register</button>
        </form>
        
        <div class="auth-footer">
            <p>Already have an account? <a href="{{ url_for('login') }}">Login</a></p>
        </div>
    </div>
</body>
</html>
"""

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Expense Tracker Pro</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://js.stripe.com/v3/"></script>
    <style>
        :root {
            --primary: #4361ee;
            --secondary: #3a0ca3;
            --accent: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --success: #4cc9f0;
            --warning: #ffd166;
            --danger: #ef476f;
            --gray: #6c757d;
            --light-gray: #e9ecef;
        }
        
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Poppins', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: var(--dark);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        .app-container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 15px 50px rgba(0, 0, 0, 0.2);
            width: 95%;
            max-width: 1200px;
            overflow: hidden;
            min-height: 90vh;
            display: flex;
            flex-direction: column;
        }
        
        header {
            background: var(--primary);
            color: white;
            padding: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: relative;
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 1.8rem;
            font-weight: 700;
        }
        
        .logo i {
            color: var(--warning);
        }
        
        .nav-container {
            display: flex;
            gap: 5px;
        }
        
        .nav-btn {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 50px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .nav-btn:hover, .nav-btn.active {
            background: white;
            color: var(--primary);
        }
        
        .user-info {
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(255, 255, 255, 0.2);
            padding: 8px 15px;
            border-radius: 50px;
        }
        
        .user-info i {
            color: var(--warning);
        }
        
        .premium-badge {
            background: var(--warning);
            color: var(--dark);
            padding: 4px 10px;
            border-radius: 50px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        
        .content-area {
            flex: 1;
            display: flex;
            overflow: hidden;
        }
        
        .sidebar {
            width: 250px;
            background: var(--light);
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
            border-right: 1px solid var(--light-gray);
        }
        
        .main-content {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            position: relative;
        }
        
        .page {
            display: none;
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.5s ease;
        }
        
        .page.active {
            display: block;
            opacity: 1;
            transform: translateY(0);
        }
        
        .card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
            border: 1px solid var(--light-gray);
            transition: transform 0.3s, box-shadow 0.3s;
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
        }
        
        .card-title {
            font-size: 1.5rem;
            margin-bottom: 15px;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            color: var(--gray);
        }
        
        input, select, textarea {
            width: 100%;
            padding: 12px 15px;
            border: 1px solid var(--light-gray);
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s;
        }
        
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        button {
            background: var(--primary);
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        button:hover {
            background: var(--secondary);
            transform: translateY(-2px);
        }
        
        .btn-danger {
            background: var(--danger);
        }
        
        .btn-danger:hover {
            background: #d5345e;
        }
        
        .btn-success {
            background: var(--success);
        }
        
        .btn-success:hover {
            background: #3ab3d9;
        }
        
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .summary-card {
            background: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
            text-align: center;
            border-left: 4px solid var(--primary);
            transition: transform 0.3s;
        }
        
        .summary-card:hover {
            transform: translateY(-5px);
        }
        
        .summary-card h3 {
            font-size: 1rem;
            color: var(--gray);
            margin-bottom: 10px;
        }
        
        .summary-card .amount {
            font-size: 2rem;
            font-weight: 700;
            color: var(--primary);
        }
        
        .summary-card.today {
            border-left-color: var(--success);
        }
        
        .summary-card.today .amount {
            color: var(--success);
        }
        
        .summary-card.week {
            border-left-color: var(--warning);
        }
        
        .summary-card.week .amount {
            color: var(--warning);
        }
        
        .summary-card.month {
            border-left-color: var(--accent);
        }
        
        .summary-card.month .amount {
            color: var(--accent);
        }
        
        .expense-list {
            max-height: 400px;
            overflow-y: auto;
        }
        
        .expense-item {
            display: flex;
            justify-content: space-between;
            padding: 15px;
            border-bottom: 1px solid var(--light-gray);
            transition: background 0.3s;
            animation: fadeIn 0.5s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .expense-item:hover {
            background: var(--light);
        }
        
        .expense-details {
            flex: 1;
        }
        
        .category {
            font-weight: 600;
            color: var(--primary);
        }
        
        .description {
            color: var(--gray);
            font-size: 0.9rem;
        }
        
        .date {
            font-size: 0.8rem;
            color: var(--gray);
        }
        
        .amount {
            font-weight: 700;
            color: var(--danger);
        }
        
        .chart-container {
            height: 300px;
            margin: 30px 0;
        }
        
        .filter-options {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .filter-btn {
            background: var(--light);
            color: var(--dark);
            border: none;
            padding: 8px 15px;
            border-radius: 50px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.3s;
        }
        
        .filter-btn.active {
            background: var(--primary);
            color: white;
        }
        
        .subscription-plans {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }
        
        .plan-card {
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.1);
            text-align: center;
            border: 2px solid var(--light-gray);
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }
        
        .plan-card.featured {
            border-color: var(--primary);
            transform: scale(1.05);
        }
        
        .plan-card.featured::before {
            content: 'POPULAR';
            position: absolute;
            top: 15px;
            right: -30px;
            background: var(--primary);
            color: white;
            padding: 5px 30px;
            font-size: 0.8rem;
            font-weight: 600;
            transform: rotate(45deg);
        }
        
        .plan-card:hover {
            transform: translateY(-10px);
            box-shadow: 0 15px 30px rgba(0, 0, 0, 0.15);
        }
        
        .plan-name {
            font-size: 1.5rem;
            color: var(--primary);
            margin-bottom: 10px;
        }
        
        .plan-price {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 20px;
            color: var(--dark);
        }
        
        .plan-price span {
            font-size: 1rem;
            color: var(--gray);
        }
        
        .plan-features {
            list-style: none;
            margin-bottom: 25px;
            text-align: left;
        }
        
        .plan-features li {
            padding: 8px 0;
            border-bottom: 1px solid var(--light-gray);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .plan-features li i {
            color: var(--success);
        }
        
        .stats-container {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
        }
        
        @media (max-width: 992px) {
            .content-area {
                flex-direction: column;
            }
            
            .sidebar {
                width: 100%;
                border-right: none;
                border-bottom: 1px solid var(--light-gray);
            }
            
            .stats-container {
                grid-template-columns: 1fr;
            }
        }
        
        @media (max-width: 768px) {
            header {
                flex-direction: column;
                gap: 15px;
            }
            
            .nav-container {
                flex-wrap: wrap;
                justify-content: center;
            }
            
            .subscription-plans {
                grid-template-columns: 1fr;
            }
            
            .plan-card.featured {
                transform: scale(1);
            }
        }
        
        .animation-fade-in {
            animation: fadeIn 0.8s ease;
        }
        
        .animation-slide-in {
            animation: slideIn 0.6s ease;
        }
        
        @keyframes slideIn {
            from { transform: translateX(-20px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        
        .pulse {
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            background: var(--success);
            color: white;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 10px;
            transform: translateX(100%);
            transition: transform 0.5s;
        }
        
        .notification.show {
            transform: translateX(0);
        }
        
        .notification.error {
            background: var(--danger);
        }
        
        .loader {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
            animation: fadeIn 0.5s ease;
        }
        
        .logout-btn {
            background: transparent;
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.3);
            padding: 5px 15px;
            border-radius: 50px;
            font-size: 0.9rem;
            margin-left: 10px;
        }
        
        .logout-btn:hover {
            background: rgba(255, 255, 255, 0.1);
            transform: none;
        }
    </style>
</head>
<body>
    <div class="app-container">
        <header>
            <div class="logo">
                <i class="fas fa-wallet"></i>
                <span>ExpenseTracker Pro</span>
            </div>
            
            <div class="nav-container">
                <button class="nav-btn active" onclick="showPage('dashboard')">
                    <i class="fas fa-home"></i> Dashboard
                </button>
                <button class="nav-btn" onclick="showPage('expenses')">
                    <i class="fas fa-receipt"></i> Expenses
                </button>
                <button class="nav-btn" onclick="showPage('reports')">
                    <i class="fas fa-chart-bar"></i> Reports
                </button>
                <button class="nav-btn" onclick="showPage('subscription')">
                    <i class="fas fa-crown"></i> Premium
                </button>
            </div>
            
            <div class="user-info">
                <i class="fas fa-user-circle"></i>
                <span>{{ user.username }}</span>
                {% if user.is_premium %}
                <span class="premium-badge">Premium</span>
                {% endif %}
                <a href="{{ url_for('logout') }}" class="logout-btn">Logout</a>
            </div>
        </header>
        
        <div class="content-area">
            <div class="sidebar">
                <div class="card animation-slide-in">
                    <h2 class="card-title"><i class="fas fa-plus-circle"></i> Add Expense</h2>
                    <form method="POST" action="{{ url_for('add_expense') }}" onsubmit="return validateExpenseForm()">
                        <div class="form-group">
                            <label for="amount">Amount ($)</label>
                            <input type="number" step="0.01" id="amount" name="amount" required>
                        </div>
                        <div class="form-group">
                            <label for="category">Category</label>
                            <select id="category" name="category" required>
                                {% for category in categories %}
                                <option value="{{ category.name }}" style="color: {{ category.color }}">{{ category.name }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="description">Description</label>
                            <input type="text" id="description" name="description">
                        </div>
                        <div class="form-group">
                            <label for="date">Date</label>
                            <input type="date" id="date" name="date" value="{{ today }}">
                        </div>
                        <button type="submit">
                            <i class="fas fa-plus"></i> Add Expense
                        </button>
                    </form>
                </div>
                
                <div class="card animation-slide-in" style="animation-delay: 0.2s;">
                    <h2 class="card-title"><i class="fas fa-bullseye"></i> Budget</h2>
                    <div class="form-group">
                        <label>Monthly Budget</label>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <input type="range" min="0" max="100" value="75" style="flex: 1;">
                            <span style="font-weight: bold; color: var(--primary);">$750 / $1000</span>
                        </div>
                    </div>
                    <button style="width: 100%;">
                        <i class="fas fa-sliders-h"></i> Set Budget
                    </button>
                </div>
            </div>
            
            <div class="main-content">
                <!-- Dashboard Page -->
                <div id="dashboard-page" class="page active">
                    <h1 class="animation-fade-in">Dashboard</h1>
                    <p class="animation-fade-in" style="animation-delay: 0.2s; color: var(--gray); margin-bottom: 30px;">
                        Welcome back, {{ user.username }}! Here's your financial overview.
                    </p>
                    
                    <div class="summary-grid animation-fade-in" style="animation-delay: 0.4s;">
                        <div class="summary-card today">
                            <h3>Today</h3>
                            <div class="amount">${{ "%.2f"|format(daily_total) }}</div>
                        </div>
                        <div class="summary-card week">
                            <h3>This Week</h3>
                            <div class="amount">${{ "%.2f"|format(weekly_total) }}</div>
                        </div>
                        <div class="summary-card month">
                            <h3>This Month</h3>
                            <div class="amount">${{ "%.2f"|format(monthly_total) }}</div>
                        </div>
                        <div class="summary-card">
                            <h3>Total Expenses</h3>
                            <div class="amount">${{ "%.2f"|format(total_expenses) }}</div>
                        </div>
                    </div>
                    
                    <div class="stats-container">
                        <div class="card animation-fade-in" style="animation-delay: 0.6s;">
                            <h2 class="card-title"><i class="fas fa-chart-pie"></i> Expenses by Category</h2>
                            <div class="chart-container" id="category-chart">
                                <!-- Chart will be rendered here -->
                            </div>
                        </div>
                        
                        <div class="card animation-fade-in" style="animation-delay: 0.8s;">
                            <h2 class="card-title"><i class="fas fa-history"></i> Recent Expenses</h2>
                            <div class="expense-list">
                                {% for expense in recent_expenses %}
                                <div class="expense-item">
                                    <div class="expense-details">
                                        <div class="category" style="color: {{ expense.color }}">{{ expense.category }}</div>
                                        <div class="description">{{ expense.description }}</div>
                                        <div class="date">{{ expense.date }}</div>
                                    </div>
                                    <div class="amount">${{ "%.2f"|format(expense.amount) }}</div>
                                </div>
                                {% endfor %}
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Expenses Page -->
                <div id="expenses-page" class="page">
                    <h1 class="animation-fade-in">All Expenses</h1>
                    <p class="animation-fade-in" style="animation-delay: 0.2s; color: var(--gray); margin-bottom: 30px;">
                        Manage and review your expenses.
                    </p>
                    
                    <div class="filter-options animation-fade-in" style="animation-delay: 0.4s;">
                        <button class="filter-btn active" onclick="filterExpenses('all')">All</button>
                        <button class="filter-btn" onclick="filterExpenses('today')">Today</button>
                        <button class="filter-btn" onclick="filterExpenses('week')">This Week</button>
                        <button class="filter-btn" onclick="filterExpenses('month')">This Month</button>
                        <select onchange="filterByCategory(this.value)" style="width: auto; padding: 8px 15px;">
                            <option value="">All Categories</option>
                            {% for category in categories %}
                            <option value="{{ category.name }}">{{ category.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    
                    <div class="card animation-fade-in" style="animation-delay: 0.6s;">
                        <div class="expense-list" id="expenses-container">
                            {% for expense in all_expenses %}
                            <div class="expense-item">
                                <div class="expense-details">
                                    <div class="category" style="color: {{ expense.color }}">{{ expense.category }}</div>
                                    <div class="description">{{ expense.description }}</div>
                                    <div class="date">{{ expense.date }}</div>
                                </div>
                                <div class="amount">${{ "%.2f"|format(expense.amount) }}</div>
                                <button class="btn-danger" style="padding: 8px 12px;" onclick="deleteExpense({{ expense.id }})">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
                
                <!-- Reports Page -->
                <div id="reports-page" class="page">
                    <h1 class="animation-fade-in">Reports & Analytics</h1>
                    <p class="animation-fade-in" style="animation-delay: 0.2s; color: var(--gray); margin-bottom: 30px;">
                        Analyze your spending patterns.
                    </p>
                    
                    <div class="filter-options animation-fade-in" style="animation-delay: 0.4s;">
                        <button class="filter-btn active" onclick="changeReportPeriod('month')">Monthly</button>
                        <button class="filter-btn" onclick="changeReportPeriod('quarter')">Quarterly</button>
                        <button class="filter-btn" onclick="changeReportPeriod('year')">Yearly</button>
                    </div>
                    
                    <div class="card animation-fade-in" style="animation-delay: 0.6s;">
                        <h2 class="card-title"><i class="fas fa-chart-line"></i> Spending Trends</h2>
                        <div class="chart-container" id="trend-chart">
                            <!-- Trend chart will be rendered here -->
                        </div>
                    </div>
                    
                    <div class="card animation-fade-in" style="animation-delay: 0.8s;">
                        <h2 class="card-title"><i class="fas fa-table"></i> Category Breakdown</h2>
                        <div style="overflow-x: auto;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <thead>
                                    <tr style="border-bottom: 2px solid var(--light-gray);">
                                        <th style="text-align: left; padding: 12px;">Category</th>
                                        <th style="text-align: right; padding: 12px;">Amount</th>
                                        <th style="text-align: right; padding: 12px;">Percentage</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for category, data in category_totals.items() %}
                                    <tr style="border-bottom: 1px solid var(--light-gray);">
                                        <td style="padding: 12px; color: {{ data.color }}">{{ category }}</td>
                                        <td style="text-align: right; padding: 12px; font-weight: bold;">${{ "%.2f"|format(data.total) }}</td>
                                        <td style="text-align: right; padding: 12px;">{{ "%.1f"|format((data.total / total_expenses * 100) if total_expenses > 0 else 0) }}%</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                
                <!-- Subscription Page -->
                <div id="subscription-page" class="page">
                    <h1 class="animation-fade-in">Premium Subscription</h1>
                    <p class="animation-fade-in" style="animation-delay: 0.2s; color: var(--gray); margin-bottom: 30px;">
                        Upgrade to unlock premium features.
                    </p>
                    
                    {% if user.is_premium %}
                    <div class="card animation-fade-in">
                        <h2 class="card-title"><i class="fas fa-crown"></i> You're a Premium Member!</h2>
                        <p>Thank you for subscribing to ExpenseTracker Pro. You have access to all premium features.</p>
                        <p>Your subscription status: <strong>{{ user.subscription_status }}</strong></p>
                    </div>
                    {% else %}
                    <div class="subscription-plans">
                        <div class="plan-card animation-fade-in" style="animation-delay: 0.4s;">
                            <h2 class="plan-name">Basic</h2>
                            <div class="plan-price">$0<span>/month</span></div>
                            <ul class="plan-features">
                                <li><i class="fas fa-check"></i> Expense tracking</li>
                                <li><i class="fas fa-check"></i> Basic reports</li>
                                <li><i class="fas fa-times" style="color: var(--danger);"></i> Advanced analytics</li>
                                <li><i class="fas fa-times" style="color: var(--danger);"></i> Budget alerts</li>
                                <li><i class="fas fa-times" style="color: var(--danger);"></i> Export data</li>
                            </ul>
                            <button>Current Plan</button>
                        </div>
                        
                        <div class="plan-card featured animation-fade-in" style="animation-delay: 0.6s;">
                            <h2 class="plan-name">Premium</h2>
                            <div class="plan-price">$4.99<span>/month</span></div>
                            <ul class="plan-features">
                                <li><i class="fas fa-check"></i> All Basic features</li>
                                <li><i class="fas fa-check"></i> Advanced analytics</li>
                                <li><i class="fas fa-check"></i> Budget alerts</li>
                                <li><i class="fas fa-check"></i> Export data</li>
                                <li><i class="fas fa-check"></i> Priority support</li>
                            </ul>
                            <button class="pulse" onclick="initiateCheckout('premium')">
                                <i class="fas fa-crown"></i> Upgrade Now
                            </button>
                        </div>
                        
                        <div class="plan-card animation-fade-in" style="animation-delay: 0.8s;">
                            <h2 class="plan-name">Family</h2>
                            <div class="plan-price">$7.99<span>/month</span></div>
                            <ul class="plan-features">
                                <li><i class="fas fa-check"></i> All Premium features</li>
                                <li><i class="fas fa-check"></i> Multiple users</li>
                                <li><i class="fas fa-check"></i> Shared budgets</li>
                                <li><i class="fas fa-check"></i> Family analytics</li>
                                <li><i class="fas fa-check"></i> 24/7 support</li>
                            </ul>
                            <button onclick="initiateCheckout('family')">Choose Family</button>
                        </div>
                    </div>
                    
                    <div class="card animation-fade-in" style="animation-delay: 1s; margin-top: 30px;">
                        <h2 class="card-title"><i class="fas fa-gift"></i> Premium Benefits</h2>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px;">
                            <div style="text-align: center;">
                                <i class="fas fa-chart-pie" style="font-size: 2.5rem; color: var(--primary); margin-bottom: 15px;"></i>
                                <h3>Advanced Analytics</h3>
                                <p style="color: var(--gray);">Get detailed insights into your spending habits.</p>
                            </div>
                            <div style="text-align: center;">
                                <i class="fas fa-bell" style="font-size: 2.5rem; color: var(--primary); margin-bottom: 15px;"></i>
                                <h3>Budget Alerts</h3>
                                <p style="color: var(--gray);">Receive notifications when you're approaching budget limits.</p>
                            </div>
                            <div style="text-align: center;">
                                <i class="fas fa-file-export" style="font-size: 2.5rem; color: var(--primary); margin-bottom: 15px;"></i>
                                <h3>Data Export</h3>
                                <p style="color: var(--gray);">Export your data to CSV or Excel for further analysis.</p>
                            </div>
                        </div>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
    
    <div class="notification" id="notification">
        <i class="fas fa-check-circle"></i>
        <span id="notification-text">Expense added successfully!</span>
    </div>

    <script>
        // Show notification function
        function showNotification(message, isError = false) {
            const notification = document.getElementById('notification');
            const notificationText = document.getElementById('notification-text');
            const icon = notification.querySelector('i');
            
            notificationText.textContent = message;
            
            if (isError) {
                notification.classList.add('error');
                icon.className = 'fas fa-exclamation-circle';
            } else {
                notification.classList.remove('error');
                icon.className = 'fas fa-check-circle';
            }
            
            notification.classList.add('show');
            
            setTimeout(() => {
                notification.classList.remove('show');
            }, 3000);
        }
        
        // Page navigation
        function showPage(pageId) {
            // Hide all pages
            document.querySelectorAll('.page').forEach(page => {
                page.classList.remove('active');
            });
            
            // Show selected page
            document.getElementById(`${pageId}-page`).classList.add('active');
            
            // Update active nav button
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            event.currentTarget.classList.add('active');
            
            // Show notification when switching to subscription page
            if (pageId === 'subscription') {
                setTimeout(() => {
                    showNotification('Upgrade to Premium for advanced features!');
                }, 500);
            }
        }
        
        // Form validation
        function validateExpenseForm() {
            const amount = document.getElementById('amount').value;
            if (amount <= 0) {
                showNotification('Please enter a valid amount!', true);
                return false;
            }
            return true;
        }
        
        // Filter buttons
        function filterExpenses(period) {
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.currentTarget.classList.add('active');
            
            // In a real app, this would fetch filtered data from the server
            showNotification(`Showing expenses for ${period}`);
        }
        
        function filterByCategory(category) {
            if (category) {
                showNotification(`Showing expenses for ${category}`);
            } else {
                showNotification('Showing all expenses');
            }
        }
        
        function changeReportPeriod(period) {
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.currentTarget.classList.add('active');
            
            showNotification(`Showing ${period} reports`);
        }
        
        // Delete expense
        function deleteExpense(expenseId) {
            if (confirm('Are you sure you want to delete this expense?')) {
                // In a real app, this would send a request to the server
                showNotification('Expense deleted successfully');
            }
        }
        
        // Stripe checkout
        function initiateCheckout(plan) {
            {% if stripe %}
            showNotification('Redirecting to secure checkout...');
            
            // Create a Stripe checkout session
            fetch('/create-checkout-session', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    plan: plan,
                }),
            })
            .then(response => response.json())
            .then(session => {
                // Redirect to Stripe Checkout
                const stripe = Stripe('{{ app.config["STRIPE_PUBLIC_KEY"] }}');
                stripe.redirectToCheckout({ sessionId: session.id });
            })
            .catch(error => {
                console.error('Error:', error);
                showNotification('Error initiating checkout', true);
            });
            {% else %}
            showNotification('Payment processing is not available in demo mode');
            {% endif %}
        }
        
        // Simulate chart rendering
        function renderCharts() {
            // Simulate category chart
            const categoryChart = document.getElementById('category-chart');
            categoryChart.innerHTML = `
                <div style="display: flex; align-items: flex-end; justify-content: space-around; height: 100%;">
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 40px; background: #4361ee; height: 120px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px;">Food</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 40px; background: #3a0ca3; height: 80px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px;">Transport</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 40px; background: #f72585; height: 60px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px;">Entertainment</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 40px; background: #4cc9f0; height: 100px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px;">Utilities</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 40px; background: #ffd166; height: 70px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px;">Rent</div>
                    </div>
                </div>
            `;
            
            // Simulate trend chart
            const trendChart = document.getElementById('trend-chart');
            trendChart.innerHTML = `
                <div style="display: flex; align-items: flex-end; justify-content: space-around; height: 100%;">
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 20px; background: #4361ee; height: 60px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px; font-size: 12px;">Jan</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 20px; background: #4361ee; height: 80px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px; font-size: 12px;">Feb</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 20px; background: #4361ee; height: 100px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px; font-size: 12px;">Mar</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 20px; background: #4361ee; height: 120px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px; font-size: 12px;">Apr</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 20px; background: #4361ee; height: 140px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px; font-size: 12px;">May</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: center;">
                        <div style="width: 20px; background: #4361ee; height: 160px; border-radius: 5px 5px 0 0;"></div>
                        <div style="margin-top: 10px; font-size: 12px;">Jun</div>
                    </div>
                </div>
            `;
        }
        
        // Initialize the app
        window.onload = function() {
            renderCharts();
            
            // Show welcome notification
            setTimeout(() => {
                showNotification('Welcome to ExpenseTracker Pro!');
            }, 1000);
        };
    </script>
</body>
</html>
"""

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        
        if user and user['password'] == hash_password(password):
            session['user_id'] = user['id']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template_string(REGISTER_TEMPLATE)
        
        conn = get_db_connection()
        c = conn.cursor()
        
        try:
            
            c.execute(
                'INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                (username, hash_password(password), email)
            )
            user_id = c.lastrowid
            
            
            c.execute('SELECT * FROM default_categories')
            default_categories = c.fetchall()
            for category in default_categories:
                c.execute(
                    'INSERT INTO categories (user_id, name, color) VALUES (?, ?, ?)',
                    (user_id, category['name'], category['color'])
                )
            
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists', 'error')
        finally:
            conn.close()
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    user = get_user(user_id)
    categories = get_categories(user_id)
    daily_total, weekly_total, monthly_total, total_expenses = get_totals(user_id)
    category_totals = get_category_totals(user_id)
    recent_expenses = get_expenses(user_id, limit=5)
    all_expenses = get_expenses(user_id)
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    return render_template_string(
        BASE_TEMPLATE,
        user=user,
        categories=categories,
        daily_total=daily_total,
        weekly_total=weekly_total,
        monthly_total=monthly_total,
        total_expenses=total_expenses,
        category_totals=category_totals,
        recent_expenses=recent_expenses,
        all_expenses=all_expenses,
        today=today
    )

@app.route('/add_expense', methods=['POST'])
@login_required
def add_expense():
    user_id = session['user_id']
    amount = float(request.form['amount'])
    category = request.form['category']
    description = request.form.get('description', '')
    date = request.form.get('date', datetime.now().strftime("%Y-%m-%d"))
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        'INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)',
        (user_id, amount, category, description, date)
    )
    conn.commit()
    conn.close()
    
    flash('Expense added successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    if not stripe:
        return {'error': 'Stripe not configured'}, 500
    
    try:
        plan = request.json.get('plan')
        prices = {
            'premium': 'price_1PMyhqFDbldlRgZg8k2fq2K1',  
            'family': 'price_1PMyiFFDbldlRgZgKtQ5f8v3'   
        }
        
        if plan not in prices:
            return {'error': 'Invalid plan'}, 400
        
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': prices[plan],
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=url_for('success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('dashboard', _external=True),
            customer_email=get_user(session['user_id'])['email'],
            client_reference_id=session['user_id'],
        )
        
        return {'id': checkout_session.id}
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/success')
@login_required
def success():
    session_id = request.args.get('session_id')
    
    if session_id:
        try:

            checkout_session = stripe.checkout.Session.retrieve(session_id)
        
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                'UPDATE users SET is_premium = 1, subscription_id = ?, subscription_status = ? WHERE id = ?',
                (checkout_session.subscription, 'active', session['user_id'])
            )
            conn.commit()
            conn.close()
            
            flash('Subscription activated successfully! Thank you for upgrading.', 'success')
        except Exception as e:
            flash('Error verifying subscription. Please contact support.', 'error')
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)