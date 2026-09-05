from flask import Flask, render_template, request, jsonify, session, redirect
import sqlite3
import os
import random
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'fashion_secret_key_123'
DB_NAME = 'fashion.db'
ADMIN_PASSWORD = 'admin123'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category TEXT,
            mrp INTEGER,
            price INTEGER,
            discount INTEGER,
            images TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS orders (
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
init_db()

@app.route('/')
def home():
    cat = request.args.get('cat', 'All')
    with get_db() as conn:
        if cat == 'All':
            products = conn.execute('SELECT * FROM products ORDER BY id DESC').fetchall()
        else:
            products = conn.execute('SELECT * FROM products WHERE category = ? ORDER BY id DESC', (cat,)).fetchall()
    
    # Comma-separated images ko list mein badalna
    prod_list = []
    for p in products:
        item = dict(p)
        item['img_list'] = [img for img in item['images'].split(',') if img]
        item['main_img'] = item['img_list'][0] if item['img_list'] else ''
        prod_list.append(item)

    cart_count = len(session.get('cart', []))
    return render_template('index.html', products=prod_list, selected_cat=cat, cart_count=cart_count)

@app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    total_amount = sum(item['price'] for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total_amount=total_amount)

@app.route('/api/add-to-cart', methods=['POST'])
def add_to_cart():
    if 'cart' not in session:
        session['cart'] = []
    data = request.json
    cart = session['cart']
    cart.append({
        'id': data['id'],
        'name': data['name'],
        'price': int(data['price']),
        'image': data['image']
    })
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

# Admin Panel
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

    with get_db() as conn:
        orders = conn.execute('SELECT * FROM orders ORDER BY id DESC').fetchall()
        products = conn.execute('SELECT * FROM products ORDER BY id DESC').fetchall()
    
    prod_list = []
    for p in products:
        d = dict(p)
        imgs = [i for i in d['images'].split(',') if i]
        d['main_img'] = imgs[0] if imgs else ''
        prod_list.append(d)

    return render_template('admin.html', logged_in=True, orders=orders, products=prod_list)

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect('/')

# Multi-Image Upload (Ek Saath 4 Photos)
@app.route('/api/add-product', methods=['POST'])
def add_product():
    if not session.get('is_admin'): return "Unauthorized", 403
    name = request.form.get('name')
    category = request.form.get('category')
    mrp = int(request.form.get('mrp'))
    price = int(request.form.get('price'))
    discount = int(((mrp - price) / mrp) * 100) if mrp > price else 0

    files = request.files.getlist('product_images')
    saved_images = []
    for f in files[:4]:  # Sirf pehli 4 images tak limit
        if f and f.filename != '':
            filename = f"{random.randint(1000, 9999)}_{secure_filename(f.filename)}"
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            saved_images.append(f"/static/uploads/{filename}")

    images_str = ",".join(saved_images)

    with get_db() as conn:
        conn.execute('INSERT INTO products (name, category, mrp, price, discount, images) VALUES (?, ?, ?, ?, ?, ?)',
                     (name, category, mrp, price, discount, images_str))
    return redirect('/admin')

@app.route('/api/delete-product/<int:p_id>', methods=['POST'])
def delete_product(p_id):
    if not session.get('is_admin'): return "Unauthorized", 403
    with get_db() as conn:
        conn.execute('DELETE FROM products WHERE id=?', (p_id,))
    return redirect('/admin')

@app.route('/api/order', methods=['POST'])
def place_order():
    if 'user_id' not in session:
        session['user_id'] = os.urandom(8).hex()

    data = request.json
    order_id = f"OD{random.randint(10000000, 99999999)}"

    with get_db() as conn:
        conn.execute('''INSERT INTO orders 
            (order_id, user_id, customer_name, phone, address, item_name, price, payment_method) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (order_id, session['user_id'], data['name'], data['phone'], data['address'], data['item'], int(data['price']), data['paymentMethod']))

    if data.get('from_cart'):
        session['cart'] = []
        session.modified = True

    return jsonify({"success": True, "orderId": order_id})

@app.route('/my-orders')
def my_orders():
    user_id = session.get('user_id')
    with get_db() as conn:
        orders = conn.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall() if user_id else []
    return render_template('orders.html', orders=orders)

@app.route('/api/update-status', methods=['POST'])
def update_status():
    if not session.get('is_admin'): return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    with get_db() as conn:
        conn.execute('UPDATE orders SET status = ? WHERE order_id = ?', (data['status'], data['orderId']))
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
