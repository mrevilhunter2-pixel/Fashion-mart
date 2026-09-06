from flask import Flask, render_template, request, jsonify, session, redirect
import os
import random
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader

# Cloudinary Config
cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key = os.environ.get('CLOUDINARY_API_KEY'),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
)

# Database Selection: Render par Supabase PostgreSQL, Local me SQLite
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.strip()

if DATABASE_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    def get_db():
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    is_postgres = True
else:
    import sqlite3
    DB_NAME = 'fashion.db'
    def get_db():
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn
    is_postgres = False

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'fashion_secret_key_123'
ADMIN_PASSWORD = 'ganesh1234me'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    if is_postgres:
        cur.execute('''CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            image_url TEXT
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT,
            category TEXT,
            mrp INT,
            price INT,
            discount INT,
            images TEXT
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            order_id TEXT,
            user_id TEXT,
            customer_name TEXT,
            phone TEXT,
            address TEXT,
            item_name TEXT,
            price INT,
            payment_method TEXT,
            status TEXT DEFAULT 'Pending',
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
    else:
        cur.execute('''CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            image_url TEXT
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category TEXT,
            mrp INTEGER,
            price INTEGER,
            discount INTEGER,
            images TEXT
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            user_id TEXT,
            customer_name TEXT,
            phone TEXT,
            address TEXT,
            item_name TEXT,
            price INTEGER,
            payment_method TEXT,
            status TEXT DEFAULT 'Pending',
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    cat = request.args.get('cat', 'All')
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM categories ORDER BY id ASC')
    categories = cur.fetchall()
    
    if cat == 'All':
        cur.execute('SELECT * FROM products ORDER BY id DESC')
    else:
        placeholder = '%s' if is_postgres else '?'
        cur.execute(f'SELECT * FROM products WHERE category = {placeholder} ORDER BY id DESC', (cat,))
    products = cur.fetchall()
    conn.close()

    prod_list = []
    for p in products:
        item = dict(p)
        item['img_list'] = [img for img in (item.get('images') or '').split(',') if img]
        item['main_img'] = item['img_list'][0] if item['img_list'] else ''
        prod_list.append(item)

    cart_count = len(session.get('cart', []))
    return render_template('index.html', products=prod_list, categories=categories, selected_cat=cat, cart_count=cart_count)

# --- ADMIN PANEL ROUTES ---
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect('/admin')
        return render_template('admin.html', error='Galat Password!')

    if not session.get('admin_logged_in'):
        return render_template('admin.html', login_required=True)

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM products ORDER BY id DESC')
    products = cur.fetchall()
    cur.execute('SELECT * FROM categories ORDER BY id ASC')
    categories = cur.fetchall()
    cur.execute('SELECT * FROM orders ORDER BY id DESC')
    orders = cur.fetchall()
    conn.close()

    return render_template('admin.html', products=products, categories=categories, orders=orders)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin')

# Category Add (Cloudinary Enabled)
@app.route('/admin/category/add', methods=['POST'])
def add_category():
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    
    name = request.form.get('category_name')
    file = request.files.get('category_image')
    image_url = ""

    if file and file.filename != '':
        upload_res = cloudinary.uploader.upload(file)
        image_url = upload_res.get('secure_url')

    if name:
        conn = get_db()
        cur = conn.cursor()
        placeholder = '%s, %s' if is_postgres else '?, ?'
        try:
            cur.execute(f'INSERT INTO categories (name, image_url) VALUES ({placeholder})', (name, image_url))
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()
        
    return redirect('/admin')

# Category Delete
@app.route('/admin/category/delete/<int:cat_id>')
def delete_category(cat_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    conn = get_db()
    cur = conn.cursor()
    placeholder = '%s' if is_postgres else '?'
    cur.execute(f'DELETE FROM categories WHERE id = {placeholder}', (cat_id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

# Product Add (Cloudinary Enabled)
@app.route('/admin/product/add', methods=['POST'])
def add_product():
    if not session.get('admin_logged_in'):
        return redirect('/admin')

    name = request.form.get('name')
    category = request.form.get('category')
    mrp = int(request.form.get('mrp', 0))
    price = int(request.form.get('price', 0))
    discount = int(((mrp - price) / mrp * 100)) if mrp > price else 0

    uploaded_files = request.files.getlist('images')
    images = []
    for f in uploaded_files[:4]:
        if f and f.filename != '':
            upload_res = cloudinary.uploader.upload(f)
            images.append(upload_res.get('secure_url'))
            
    images_str = ','.join(images)

    conn = get_db()
    cur = conn.cursor()
    placeholder = '%s, %s, %s, %s, %s, %s' if is_postgres else '?, ?, ?, ?, ?, ?'
    cur.execute(f'''INSERT INTO products (name, category, mrp, price, discount, images)
                    VALUES ({placeholder})''', (name, category, mrp, price, discount, images_str))
    conn.commit()
    conn.close()
    return redirect('/admin')

# Product Delete
@app.route('/admin/product/delete/<int:prod_id>')
def delete_product(prod_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    conn = get_db()
    cur = conn.cursor()
    placeholder = '%s' if is_postgres else '?'
    cur.execute(f'DELETE FROM products WHERE id = {placeholder}', (prod_id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

# Order Status Update
@app.route('/admin/order/update/<int:order_id>', methods=['POST'])
def update_order(order_id):
    if not session.get('admin_logged_in'):
        return redirect('/admin')
    new_status = request.form.get('status')
    conn = get_db()
    cur = conn.cursor()
    placeholder = '%s, %s' if is_postgres else '?, ?'
    cur.execute(f'UPDATE orders SET status = {placeholder.split(",")[0]} WHERE id = {placeholder.split(",")[1]}', (new_status, order_id))
    conn.commit()
    conn.close()
    return redirect('/admin')

if __name__ == '__main__':
    app.run(debug=True)
        
