from flask import Flask, render_template, request, jsonify, session, redirect
import os
import random
from werkzeug.utils import secure_filename

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
ADMIN_PASSWORD = 'admin123'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # Categories Table
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
    
    # Categories fetch
    cur.execute('SELECT * FROM categories ORDER BY id ASC')
    categories = cur.fetchall()
    
    # Products filter
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

# --- ADMIN ROUTES ---
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect('/admin')
        error = "Galat Password!"

    if not session.get('is_admin'):
        return render_template('admin.html', logged_in=False, error=error)

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM categories ORDER BY id DESC')
    categories = cur.fetchall()
    cur.execute('SELECT * FROM products ORDER BY id DESC')
    products = cur.fetchall()
    cur.execute('SELECT * FROM orders ORDER BY id DESC')
    orders = cur.fetchall()
    conn.close()

    prod_list = []
    for p in products:
        d = dict(p)
        imgs = [i for i in (d.get('images') or '').split(',') if i]
        d['main_img'] = imgs[0] if imgs else ''
        prod_list.append(d)

    return render_template('admin.html', logged_in=True, categories=categories, products=prod_list, orders=orders)

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect('/')

# Category Add API
@app.route('/api/add-category', methods=['POST'])
def add_category():
    if not session.get('is_admin'): return "Unauthorized", 403
    name = request.form.get('name', '').strip()
    file = request.files.get('cat_image')
    image_url = ''

    if file and file.filename != '':
        filename = f"cat_{random.randint(1000, 9999)}_{secure_filename(file.filename)}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_url = f"/static/uploads/{filename}"

    if name:
        conn = get_db()
        cur = conn.cursor()
        placeholder = '%s, %s' if is_postgres else '?, ?'
        try:
            cur.execute(f'INSERT INTO categories (name, image_url) VALUES ({placeholder})', (name, image_url))
            conn.commit()
        except:
            pass
        conn.close()
    return redirect('/admin')

# Category Delete API
@app.route('/api/delete-category/<int:c_id>', methods=['POST'])
def delete_category(c_id):
    if not session.get('is_admin'): return "Unauthorized", 403
    conn = get_db()
    cur = conn.cursor()
    placeholder = '%s' if is_postgres else '?'
    cur.execute(f'DELETE FROM categories WHERE id = {placeholder}', (c_id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

# Product Upload API
@app.route('/api/add-product', methods=['POST'])
def add_product():
    if not session.get('is_admin'): return "Unauthorized", 403
    name = request.form.get('name')
    category = request.form.get('category')
    mrp = int(request.form.get('mrp', 0))
    price = int(request.form.get('price', 0))
    discount = int(((mrp - price) / mrp) * 100) if mrp > price else 0

    files = request.files.getlist('product_images')
    saved_images = []
    for f in files[:4]:
        if f and f.filename != '':
            filename = f"prod_{random.randint(1000, 9999)}_{secure_filename(f.filename)}"
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            saved_images.append(f"/static/uploads/{filename}")

    images_str = ",".join(saved_images)

    conn = get_db()
    cur = conn.cursor()
    placeholder = '%s, %s, %s, %s, %s, %s' if is_postgres else '?, ?, ?, ?, ?, ?'
    cur.execute(f'INSERT INTO products (name, category, mrp, price, discount, images) VALUES ({placeholder})',
                (name, category, mrp, price, discount, images_str))
    conn.commit()
    conn.close()
    return redirect('/admin')

# Product Delete API
@app.route('/api/delete-product/<int:p_id>', methods=['POST'])
def delete_product(p_id):
    if not session.get('is_admin'): return "Unauthorized", 403
    conn = get_db()
    cur = conn.cursor()
    placeholder = '%s' if is_postgres else '?'
    cur.execute(f'DELETE FROM products WHERE id = {placeholder}', (p_id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

# Cart & Orders Routes
@app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    total_amount = sum(item['price'] for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total_amount=total_amount)

@app.route('/api/add-to-cart', methods=['POST'])
def add_to_cart():
    if 'cart' not in session: session['cart'] = []
    data = request.json
    cart = session['cart']
    cart.append({'id': data['id'], 'name': data['name'], 'price': int(data['price']), 'image': data['image']})
    session['cart'] = cart
    session.modified = True
    return jsonify({"success": True, "cart_count": len(session['cart'])})

@app.route('/api/remove-from-cart/<int:index>', methods=['POST'])
def remove_from_cart(index):
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart.pop(index)
        session['cart'] = cart
        session.modified = True
    return redirect('/cart')

@app.route('/api/order', methods=['POST'])
def place_order():
    if 'user_id' not in session: session['user_id'] = os.urandom(8).hex()
    data = request.json
    order_id = f"OD{random.randint(10000000, 99999999)}"

    conn = get_db()
    cur = conn.cursor()
    placeholder = '%s, %s, %s, %s, %s, %s, %s, %s' if is_postgres else '?, ?, ?, ?, ?, ?, ?, ?'
    cur.execute(f'''INSERT INTO orders 
        (order_id, user_id, customer_name, phone, address, item_name, price, payment_method) 
        VALUES ({placeholder})''',
        (order_id, session['user_id'], data['name'], data['phone'], data['address'], data['item'], int(data['price']), data['paymentMethod']))
    conn.commit()
    conn.close()

    if data.get('from_cart'):
        session['cart'] = []
        session.modified = True
    return jsonify({"success": True, "orderId": order_id})

@app.route('/my-orders')
def my_orders():
    user_id = session.get('user_id')
    orders = []
    if user_id:
        conn = get_db()
        cur = conn.cursor()
        placeholder = '%s' if is_postgres else '?'
        cur.execute(f'SELECT * FROM orders WHERE user_id = {placeholder} ORDER BY id DESC', (user_id,))
        orders = cur.fetchall()
        conn.close()
    return render_template('orders.html', orders=orders)

@app.route('/api/update-status', methods=['POST'])
def update_status():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    placeholder = '%s, %s' if is_postgres else '?, ?'
    cur.execute(f'UPDATE orders SET status = {placeholder.split(",")[0]} WHERE order_id = {placeholder.split(",")[1]}', 
                (data['status'], data['orderId']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
