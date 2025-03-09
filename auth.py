# auth.py - New file to handle authentication
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from pymongo import MongoClient
import os

# Setup MongoDB connection - use the same as in app.py
client = MongoClient("mongodb+srv://adityasharma07327:Aditya%401735@cluster0.erbus.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["pdf_database"]
users_collection = db["users"]

auth = Blueprint('auth', __name__)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access this page", "error")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# User class for Flask-Login
class User:
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.email = user_data['email']
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False
    
    def get_id(self):
        return self.id

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Basic validation
        if not username or not email or not password:
            flash("All fields are required", "error")
            return render_template('register.html')
        
        # Check if username or email already exists
        if users_collection.find_one({"$or": [{"username": username}, {"email": email}]}):
            flash("Username or email already exists", "error")
            return render_template('register.html')
        
        # Create new user
        user_data = {
            "username": username,
            "email": email,
            "password": generate_password_hash(password)
        }
        
        result = users_collection.insert_one(user_data)
        
        if result.inserted_id:
            flash("Registration successful! Please login.", "success")
            return redirect(url_for('auth.login'))
        else:
            flash("Registration failed", "error")
    
    return render_template('register.html')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = users_collection.find_one({"username": username})
        
        if user and check_password_hash(user['password'], password):
            # Store user info in session
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            
            flash("Login successful!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password", "error")
    
    return render_template('login.html')

@auth.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect(url_for('auth.login'))

# Current user helper function
def get_current_user():
    if 'user_id' in session:
        user_data = users_collection.find_one({"_id": session['user_id']})
        if user_data:
            return User(user_data)
    return None