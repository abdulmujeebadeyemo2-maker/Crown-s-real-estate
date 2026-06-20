from dotenv import load_dotenv
load_dotenv()
from flask import( Flask, render_template, request, session, redirect, url_for, flash)
from werkzeug.security import (generate_password_hash, check_password_hash)
from datetime import datetime, timedelta
import bleach
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import uuid
app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER']=os.path.join(BASE_DIR, 'static', 'images')
os.makedirs(app.config['UPLOAD_FOLDER'],exist_ok=True)
app.secret_key = os.environ.get('SECRET_KEY','dev-only-fallback')

DATABASE_URL=os.environ.get('DATABASE_URL')
def get_db():
    conn=psycopg2.connect(DATABASE_URL)
    return conn
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS properties(
        id SERIAL PRIMARY KEY, 
        name TEXT, 
        Price TEXT, 
        Location TEXT, 
        Status TEXT, 
        type TEXT, 
        description TEXT, 
        image TEXT
    )
''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins(
         id SERIAL PRIMARY KEY,
         username TEXT,
        password TEXT
    )
''')
    
    cursor.execute("SELECT COUNT(*) FROM admins")
    if cursor.fetchone()[0]==0:
        admin_username = os.environ.get('ADMIN_USERNAME')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'fallback')
        hashed_password = generate_password_hash(admin_password)
        cursor.execute("INSERT INTO admins(username, password) VALUES(%s,%s)",
               (admin_username, hashed_password))

    cursor.execute('''CREATE TABLE IF NOT EXISTS users
                   (id SERIAL PRIMARY KEY,
                   username TEXT UNIQUE,
                   email TEXT UNIQUE,
                   password TEXT)''')

    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS inquiries(
                    id SERIAL PRIMARY KEY,
                    property_id INTEGER,
                    name TEXT,
                    phone TEXT,
                    email TEXT, 
                    message TEXT
                   )
                   """)
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS sales(
                   id SERIAL PRIMARY KEY,
                   property_id INTEGER,
                   user_id INTEGER,
                   sale_date TEXT DEFAULT NOW(),
                   FOREIGN KEY(property_id)REFERENCES properties(id),
                   FOREIGN KEY(user_id)REFERENCES users(id))''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS leases(
        id SERIAL PRIMARY KEY,
        property_id INTEGER,
        user_id INTEGER,
        start_date TEXT,
        duration_years INTEGER,
        expiry_date TEXT,
        FOREIGN KEY(property_id) REFERENCES properties(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS complaints(
            id SERIAL PRIMARY KEY,
            lease_id INTEGER,
            user_id INTEGER,
            property_id INTEGER,
            message TEXT,
            date_sent TIMESTAMP DEFAULT NOW(),
            sender TEXT,
            FOREIGN KEY(lease_id) REFERENCES leases(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
    ) 
''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS direct_messages(
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            sender TEXT,
            message TEXT,
            date_sent TIMESTAMP DEFAULT NOW(),
            lease_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id)
    )
''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS general_messages(
            id SERIAL PRIMARY KEY,
            message TEXT,
            date_sent TIMESTAMP DEFAULT NOW()
    )
''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS property_images(id SERIAL PRIMARY KEY,
                   property_id INTEGER,
                   image_name TEXT)''')
    conn.commit()
    conn.close()

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''SELECT * FROM admins WHERE 
                       username = %s''',
                       (username,))
        admin = cursor.fetchone()
        conn.close()
        print(admin)
        if admin and check_password_hash(admin[2], password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        else:
           flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('login'))

@app.route('/user/register', methods=['GET', 'POST'])
def user_register():
    if session.get('user_id'):
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed = generate_password_hash(password)
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO users(username, email, password) VALUES(%s,%s,%s)',
                (username, email, hashed)
            )
            conn.commit()
            conn.close()
            flash('Account created! Please log in.')
            return redirect(url_for('user_login'))
        except psycopg2.IntegrityError:
            conn.close()
            flash('Username or email already exists.')
            return redirect(url_for('user_register'))
    return render_template('user_register.html')


@app.route('/user/login', methods=['GET', 'POST'])
def user_login():
    if session.get('user_id'):
        return redirect(url_for('home'))
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        conn.close()
        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            flash(f'Welcome back, {user[1]}!')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password.')
            return redirect(url_for('user_login'))
    return render_template('user_login.html')


@app.route('/user/logout')
def user_logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    return redirect(url_for('home'))

@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor= conn.cursor()
    cursor.execute("SELECT * FROM properties")
    properties=cursor.fetchall()
    cursor.execute("SELECT * FROM inquiries")
    inquiries=cursor.fetchall()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count=cursor.fetchone()[0]
    cursor.execute("""
                   SELECT sales.id, properties.name, users.email, sales.sale_date 
                   FROM sales
                   JOIN properties ON sales.property_id = properties.id
                   JOIN users ON sales.user_id = users.id""")
    sales = cursor.fetchall()
    cursor.execute("""
                   SELECT leases.id, properties.name, users.username, users.email, leases.expiry_date, users.id 
                   FROM leases
                   JOIN properties ON leases.property_id = properties.id
                   JOIN users ON leases.user_id = users.id""")
    leases = cursor.fetchall() 
    cursor.execute('''
        SELECT complaints.id, complaints.lease_id, complaints.property_id,
           complaints.user_id, complaints.message, complaints.date_sent,
           users.username, properties.name
        FROM complaints
        JOIN users ON complaints.user_id = users.id
        JOIN properties ON complaints.property_id = properties.id''')
    complaints = cursor.fetchall()

    cursor.execute('SELECT * FROM direct_messages ORDER BY date_sent DESC')
    all_messages = cursor.fetchall()   
    conn.close()
    return render_template('admin.html',
                            properties=properties,
                            inquiries=inquiries,
                            user_count=user_count,
                            property_count=len(properties),
                            inquiry_count=len(inquiries),
                            sales=sales,
                            leases=leases,
                            all_messages=all_messages,
                            complaints=complaints)

@app.route('/admin/users_list/<int:property_id>/')
def users_list(property_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor=conn.cursor()
    # Only get users who sent an inquiry for this property
    cursor.execute('''
        SELECT DISTINCT users.id, users.username, users.email,
               inquiries.phone, inquiries.message
        FROM users
        JOIN inquiries ON users.email = inquiries.email
        WHERE inquiries.property_id = %s
    ''', (property_id,))
    inquired_users = cursor.fetchall()

    if not inquired_users:
        cursor.execute('''SELECT id, username, email, NULL, NULL FROM users''')
        rows=cursor.fetchall()
        inquired_users=[(r[0], r[1], r[2], ",") for r in rows]

    cursor.execute('SELECT * FROM properties WHERE id = %s', (property_id,))
    property = cursor.fetchone()
    conn.close()
    return render_template('users_list.html',
                           users=inquired_users,
                           property=property)

@app.route('/admin/sell/<int:property_id>/<int:user_id>')
def sell_property(property_id, user_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor= conn.cursor()
    cursor.execute("INSERT INTO sales(property_id, user_id) VALUES(%s,%s)", (property_id, user_id))
    cursor.execute("UPDATE properties SET Status = 'Sold' WHERE id = %s", (property_id,))
    conn.commit()
    conn.close()
    flash('Propery successfully sold.')
    return redirect(url_for('admin'))

# ─── LEASE PROPERTY (updated to accept duration) ───
@app.route('/admin/lease/<int:property_id>/<int:user_id>', methods=['GET', 'POST'])
def lease_property(property_id, user_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        duration_years = int(request.form['duration_years'])
        start_date = datetime.now()
        expiry_date = start_date + timedelta(days=365 * duration_years)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO leases(property_id, user_id, start_date, duration_years, expiry_date)
            VALUES(%s, %s, %s, %s, %s)
        ''', (property_id, user_id,
              start_date.strftime('%Y-%m-%d %H:%M:%S'),
              duration_years,
              expiry_date.strftime('%Y-%m-%d %H:%M:%S')))
        cursor.execute(
            "UPDATE properties SET Status = 'Leased' WHERE id = %s",
            (property_id,)
        )
        conn.commit()
        conn.close()
        flash('Property successfully leased.')
        return redirect(url_for('admin'))
    return render_template('lease_form.html',
                           property_id=property_id,
                           user_id=user_id)

# ADMIN DELETE INQUIRY
@app.route('/admin/delete_inquiry/<int:inquiry_id>')
def delete_inquiry(inquiry_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM inquiries WHERE id = %s', (inquiry_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))


# USER DELETE MESSAGE
@app.route('/user/delete_message/<int:message_id>')
def delete_message(message_id):
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    conn = get_db()
    cursor = conn.cursor()
    # Make sure user can only delete their own messages
    cursor.execute(
        'DELETE FROM direct_messages WHERE id = %s AND user_id = %s',
        (message_id, session['user_id'])
    )
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


# ─── USER DASHBOARD ───
@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    user_id = session['user_id']
    now = datetime.now()
    conn = get_db()
    cursor = conn.cursor()

    # Check and expire leases
    cursor.execute('''
        SELECT leases.id FROM leases
        WHERE user_id = %s AND expiry_date <= %s
    ''', (user_id, now.strftime('%Y-%m-%d %H:%M:%S')))
    expired = cursor.fetchall()

    # Get active leases with property info
    cursor.execute('''
        SELECT leases.id, leases.property_id, properties.name,
               properties.location, leases.start_date,
               leases.expiry_date, leases.duration_years
        FROM leases
        JOIN properties ON leases.property_id = properties.id
        WHERE leases.user_id = %s AND leases.expiry_date > %s
    ''', (user_id, now.strftime('%Y-%m-%d %H:%M:%S')))
    active_leases = cursor.fetchall()

    # Get direct messages for this user
    cursor.execute('''
        SELECT * FROM direct_messages
        WHERE user_id = %s
        ORDER BY date_sent DESC
    ''', (user_id,))
    direct_messages = cursor.fetchall()

    # Get general messages
    cursor.execute('''
        SELECT * FROM general_messages
        ORDER BY date_sent DESC
    ''')
    general_messages = cursor.fetchall()

    conn.close()
    return render_template('user_dashboard.html',
                           active_leases=active_leases,
                           expired=expired,
                           direct_messages=direct_messages,
                           general_messages=general_messages,
                           now=now.strftime('%Y-%m-%d %H:%M:%S'))


# ─── USER COMPLAINT ───
@app.route('/complaint/<int:lease_id>', methods=['POST'])
def submit_complaint(lease_id):
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    message = bleach.clean(request.form['message'])
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT property_id FROM leases WHERE id = %s', (lease_id,))
    lease = cursor.fetchone()
    cursor.execute('''
        INSERT INTO complaints(lease_id, user_id, property_id, message, sender)
        VALUES(%s, %s, %s, %s, 'user')
    ''', (lease_id, user_id, lease[0], message))
    conn.commit()
    conn.close()
    flash('Complaint submitted successfully.')
    return redirect(url_for('dashboard'))


# ─── USER SENDS DIRECT MESSAGE ───
@app.route('/message/send/<int:lease_id>', methods=['POST'])
def user_send_message(lease_id):
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    message = bleach.clean(request.form['message'])
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO direct_messages(user_id, sender, message, lease_id)
        VALUES(%s, 'user', %s, %s)
    ''', (user_id, message, lease_id))
    conn.commit()
    conn.close()
    flash('Message sent.')
    return redirect(url_for('dashboard'))


# ─── ADMIN SENDS DIRECT MESSAGE TO USER ───
@app.route('/admin/message/<int:user_id>', methods=['POST'])
def admin_send_message(user_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    message = bleach.clean(request.form['message'])
    lease_id = request.form.get('lease_id', 0)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO direct_messages(user_id, sender, message, lease_id)
        VALUES(%s, 'admin', %s, %s)
    ''', (user_id, message, lease_id))
    conn.commit()
    conn.close()
    flash('Message sent to user.')
    return redirect(url_for('admin'))


# ─── ADMIN SENDS GENERAL MESSAGE TO ALL USERS ───
@app.route('/admin/broadcast', methods=['POST'])
def broadcast_message():
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    message = bleach.clean(request.form['message'])
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO general_messages(message) VALUES(%s)', (message,))
    conn.commit()
    conn.close()
    flash('Broadcast message sent to all users.')
    return redirect(url_for('admin'))


# ─── HOMEPAGE NOW PUBLIC ───
@app.route('/')
def home():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM properties')
    properties = cursor.fetchall()
    conn.close()
    return render_template('h.html', properties=properties)


# ─── INQUIRY: redirect to login if not logged in ───
@app.route('/send_inquiry/<int:id>', methods=['POST'])
def send_inquiry(id):
    if not session.get('user_id') and not session.get('admin_logged_in'):
        flash('Please log in to send an inquiry.')
        return redirect(url_for('user_login'))
    name = bleach.clean(request.form['name'])
    phone = bleach.clean(request.form['phone'])
    email = bleach.clean(request.form['email'])
    message = bleach.clean(request.form['message'])
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO inquiries(property_id, name, phone, email, message)
        VALUES(%s, %s, %s, %s, %s)
    ''', (id, name, phone, email, message))
    conn.commit()
    conn.close()
    flash('Inquiry sent successfully.')
    return redirect(url_for('property_details', id=id))

@app.route('/prop_db')
def prop_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM properties')
    rows = cursor.fetchall()
    conn.close()
    return str(rows)

@app.route('/add_property', methods=['POST'])
def add_property():
    print('upload folder:', app.config['UPLOAD_FOLDER'])
    print('Exists:', os.path.exists(app.config['UPLOAD_FOLDER']))
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    name = request.form['name']
    Price = request.form['Price']
    Location = request.form['Location']
    Status = request.form['Status']
    property_type = request.form['type']
    description = request.form['description']

    images = request.files.getlist('images')
    print("Number of images recieved:", len(images))
    for i, img in enumerate(images):
        print(f"image{i}: filename='{img.filename}'")
    cover_image=""
    if images and images[0].filename:
        ext = os.path.splitext(images[0].filename)[1]
        cover_image= str(uuid.uuid4())+ext 
        images[0].save(os.path.join(app.config['UPLOAD_FOLDER'], cover_image))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO properties(name, Price, Location, Status, type, description, image)
                   VALUES(%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id
               ''',(
                   name,
                   Price,
                   Location,
                   Status,
                   property_type,
                   description,
                   cover_image
               ))
    property_id = cursor.fetchone()[0]
    for image in images[1:]:
        if image.filename:
            ext = os.path.splitext(image.filename)[1]
            filename = str(uuid.uuid4())+ext 
            image_path=os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)
            cursor.execute('''INSERT INTO property_images(property_id, image_name)
            VALUES(%s,%s)''',(property_id,
                            filename))
    if cover_image:
        cursor.execute("INSERT INTO property_images(property_id, image_name) VALUES(%s,%s)",(property_id, cover_image))        
    conn.commit()
    conn.close()
    return redirect(url_for('home'))

@app.route('/delete_property/<int:id>')
def delete_property(id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor= conn.cursor()
    cursor.execute("DELETE FROM properties WHERE id=%s",(id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/edit_property/<int:id>', methods=['GET', 'POST'])
def edit_property(id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    conn = get_db()
    cursor=conn.cursor()
    if request.method == 'POST':
        name=request.form['name']
        Price=request.form['Price']
        Location=request.form['Location']
        Status=request.form['Status']
        type=request.form['type']
        description=request.form['description']
        cursor.execute("""
            UPDATE properties 
            SET
                name=%s, 
                Price=%s, 
                Location=%s, 
                Status=%s,
                type=%s, 
                description=%s 
            WHERE id=%s
        """,(
            name,
            Price, 
            Location, 
            Status,
            type,
            description,
            id
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('admin'))
    cursor.execute(
        "SELECT * FROM properties WHERE id=%s",
        (id,)
    )
    property = cursor.fetchone()
    conn.close()
    return render_template('edit_property.html', property=property)

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        min_price = request.form.get('min_price', '')
        max_price = request.form.get('max_price', '')
        property_type = request.form.get('property_type', '')
        city = request.form.get('city', '')
        status = request.form.get('status', '')

        query = "SELECT * FROM properties WHERE 1=1"
        params = []

        if city:
            query += " AND LOWER(location) LIKE %s"
            params.append('%' + city.lower() + '%')

        if status:
            query += " AND status = %s"
            params.append(status)

        if property_type:
            query += " AND type = %s"
            params.append(property_type)

        if min_price:
            query += " AND CAST(price AS INTEGER) >= %s"
            params.append(int(min_price))

        if max_price:
            query += " AND CAST(price AS INTEGER) <= %s"
            params.append(int(max_price))

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()

        return render_template('search_result.html', city=city, results=results)
    return render_template('search.html')

@app.route('/property/<int:id>')
def property_details(id):
    if not session.get('user_id') and not session.get('admin_logged_in'):
        return redirect(url_for('user_login'))
    conn = get_db()
    cursor= conn.cursor()
    cursor.execute("SELECT * FROM properties")
    properties=cursor.fetchall()
    cursor.execute('''SELECT image_name FROM property_images WHERE property_id=%s''',(id,))
    images=cursor.fetchall()
    selected_property = None
    for property in properties:
        if property[0] == id:
            selected_property = property
            break
    conn.close()    
    return render_template('property_details.html', property = selected_property, images=images)

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'),404

@app.route("/about")
def about():
    return render_template('about.html')

@app.route("/contact", methods=['GET', 'POST'])
def contact():
    if not session.get('user_id') and not session.get('admin_logged_in'):
        return redirect(url_for('user_login'))
    if request.method == 'POST':
        name = bleach.clean(request.form['name'])
        phone = bleach.clean(request.form['phone'])
        email = bleach.clean(request.form['email'])
        subject = bleach.clean(request.form['subject'])
        message = bleach.clean(request.form['message'])
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO inquiries(property_id, name, phone, email, message)
            VALUES(%s, %s, %s, %s, %s)
        ''', (0, name, phone, email, subject + ' — ' + message))
        conn.commit()
        conn.close()
        flash('Your message has been sent. We will get back to you shortly.')
        return redirect(url_for('contact'))
    return render_template('contact.html')

init_db()

if __name__=='__main__':
    app.run(debug=False)