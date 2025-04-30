# app.py - Ana Flask Uygulaması Dosyası (PDF Veritabanı Entegrasyonu)

from flask import Flask, render_template, request, redirect, url_for, g, flash, abort, make_response, get_flashed_messages # get_flashed_messages eklendi
import sqlite3
import os
from datetime import datetime, timedelta # timedelta eklendi
import io
import random # Örnek veri için eklendi

# PDF Kütüphanesi (Kurulu olduğundan emin olun: pip install reportlab)
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.units import inch, cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    FONT_NAME = 'Helvetica'
    # Proje dizininde bir 'fonts' klasörü ve içinde 'Roboto-Regular.ttf' olduğunu varsayalım
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts', 'Roboto-Regular.ttf')
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('Roboto-Regular', font_path))
        FONT_NAME = 'Roboto-Regular'
        print(f"'{FONT_NAME}' fontu başarıyla yüklendi.")
    else:
         # Font yolu kullanıcıya özel olduğu için uyarıyı daha genel hale getirelim
         print(f"Uyarı: Türkçe karakterler için '{font_path}' yoluyla özel font yüklenemedi. Standart font ({FONT_NAME}) kullanılacak. PDF'te Türkçe karakter sorunları yaşanabilir.")
except ImportError:
    print("HATA: reportlab kütüphanesi bulunamadı. Lütfen 'pip install reportlab' ile kurun.")
    SimpleDocTemplate = None
except Exception as font_error:
    print(f"Uyarı: Font yüklenirken hata oluştu: {font_error}. Standart font ({FONT_NAME}) kullanılacak.")


# --- Uygulama Kurulumu ---
app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'emlak.db')
app.config['SECRET_KEY'] = 'cokgizlibir_anahtar_12345'
# Debug modunu buradan ayarlayabilirsiniz (True ise örnek veri butonu görünür)
# Geliştirme sırasında True, canlıda False yapın
is_debug_mode = True # True veya False olarak ayarlayın
app.config['DEBUG'] = is_debug_mode


# --- Veritabanı İşlemleri ---

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """Veritabanı tablolarını (eğer yoksa) oluşturur veya günceller."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        print("Veritabanı tabloları oluşturuluyor/güncelleniyor...")

        # Danışmanlar Tablosu (agents - Şu an kullanılmıyor ama kalabilir)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT UNIQUE,
                email TEXT UNIQUE,
                is_active BOOLEAN DEFAULT 1,
                date_joined DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("- agents tablosu kontrol edildi.")

        # Emlak Sahipleri Tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS owners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT UNIQUE,
                email TEXT UNIQUE,
                notes TEXT,
                date_added DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("- owners tablosu kontrol edildi.")

        # Emlaklar Tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                property_type TEXT,
                status TEXT NOT NULL,
                price REAL,
                area REAL,
                rooms TEXT,
                address TEXT,
                city TEXT,
                district TEXT,
                agent_id INTEGER, -- Bu alan kullanılmıyor gibi, kaldırılabilir veya personel_id ile değiştirilebilir
                owner_id INTEGER,
                date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agents (id) ON DELETE SET NULL,
                FOREIGN KEY (owner_id) REFERENCES owners (id) ON DELETE SET NULL
            )
        ''')
        print("- properties tablosu kontrol edildi.")
        try:
            cursor.execute("ALTER TABLE properties ADD COLUMN owner_id INTEGER REFERENCES owners(id) ON DELETE SET NULL")
            print("  - 'owner_id' sütunu properties tablosuna eklendi (gerekliyse).")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e) or "already exists" in str(e):
                print("  - 'owner_id' sütunu properties tablosunda zaten mevcut.")
            else:
                raise e

        # Müşteriler Tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT UNIQUE,
                email TEXT UNIQUE,
                customer_type TEXT,
                notes TEXT,
                is_archived INTEGER DEFAULT 0,
                date_registered DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("- customers tablosu kontrol edildi.")
        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN is_archived INTEGER DEFAULT 0")
            print("  - 'is_archived' sütunu customers tablosuna eklendi (gerekliyse).")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e) or "already exists" in str(e):
                print("  - 'is_archived' sütunu customers tablosunda zaten mevcut.")
            else:
                raise e

        # Personel Tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS personnel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                position TEXT,
                phone TEXT UNIQUE,
                email TEXT UNIQUE,
                hire_date DATE,
                is_active BOOLEAN DEFAULT 1,
                notes TEXT,
                salary REAL,
                date_added DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("- personnel tablosu kontrol edildi.")
        try:
            cursor.execute("ALTER TABLE personnel ADD COLUMN salary REAL")
            print("  - 'salary' sütunu personnel tablosuna eklendi (gerekliyse).")
        except sqlite3.OperationalError as e:
             if "duplicate column name" in str(e) or "already exists" in str(e):
                 print("  - 'salary' sütunu personnel tablosunda zaten mevcut.")
             elif "no such table: personnel" not in str(e):
                 raise e

        # Sözleşmeler Tablosu (pdf_filename ve pdf_data eklendi/güncellendi)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_type TEXT NOT NULL,
                property_id INTEGER NOT NULL,
                customer_id INTEGER NOT NULL,
                owner_id INTEGER,
                personnel_id INTEGER,
                contract_date DATE NOT NULL,
                start_date DATE,
                end_date DATE,
                price REAL,
                notes TEXT,
                pdf_filename TEXT, -- PDF dosya adını saklamak için
                pdf_data BLOB,     -- PDF içeriğini saklamak için (YENİ)
                date_created DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties (id) ON DELETE CASCADE,
                FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE,
                FOREIGN KEY (owner_id) REFERENCES owners (id) ON DELETE SET NULL,
                FOREIGN KEY (personnel_id) REFERENCES personnel (id) ON DELETE SET NULL
            )
        ''')
        print("- contracts tablosu kontrol edildi.")
        # pdf_filename ve pdf_data sütunlarını eklemeyi dene
        try:
            cursor.execute("ALTER TABLE contracts ADD COLUMN pdf_filename TEXT")
            print("  - 'pdf_filename' sütunu contracts tablosuna eklendi (gerekliyse).")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e) or "already exists" in str(e):
                print("  - 'pdf_filename' sütunu contracts tablosunda zaten mevcut.")
            elif "no such table: contracts" not in str(e): raise e
        try:
            cursor.execute("ALTER TABLE contracts ADD COLUMN pdf_data BLOB")
            print("  - 'pdf_data' sütunu contracts tablosuna eklendi (gerekliyse).")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e) or "already exists" in str(e):
                print("  - 'pdf_data' sütunu contracts tablosunda zaten mevcut.")
            elif "no such table: contracts" not in str(e): raise e

        db.commit()
        print("Veritabanı başarıyla başlatıldı/güncellendi.")


# --- Yardımcı Fonksiyonlar ---
def get_distinct_values(table_name, column_name):
    """Belirtilen tablodaki belirli bir sütunun benzersiz değerlerini alır."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(f"SELECT DISTINCT {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL AND {column_name} != '' ORDER BY {column_name}")
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Hata: get_distinct_values({table_name}, {column_name}) - {e}")
        return []

def format_datetime(value, format='%d.%m.%Y %H:%M'):
    """SQLite tarih/saat string'ini belirtilen formata çevirir."""
    if value is None: return "-"
    try:
        if isinstance(value, datetime):
            dt_object = value
        else:
            possible_formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']
            dt_object = None
            for fmt in possible_formats:
                try:
                    dt_object = datetime.strptime(str(value), fmt)
                    break
                except ValueError:
                    continue
            if dt_object is None:
                raise ValueError(f"'{value}' değeri bilinen formatlara uymuyor.")
        return dt_object.strftime(format)
    except (ValueError, TypeError) as e:
        print(f"format_datetime hatası: {e} - Değer: {value}")
        return str(value)

def format_date(value, format='%d.%m.%Y'):
    """SQLite tarih string'ini veya date objesini belirtilen formata çevirir."""
    if value is None: return "-"
    try:
        if isinstance(value, datetime):
             dt_object = value.date()
        elif hasattr(value, 'strftime'):
             dt_object = value
        else:
            possible_formats = ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']
            parsed_date = None
            for fmt in possible_formats:
                try:
                    parsed_date = datetime.strptime(str(value), fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_date is None:
                 raise ValueError(f"'{value}' değeri bilinen tarih formatlarına uymuyor.")
            dt_object = parsed_date

        return dt_object.strftime(format)
    except (ValueError, TypeError) as e:
        print(f"format_date hatası: {e} - Değer: {value}")
        return str(value)

def format_currency(value):
    if value is None:
        return "-"
    try:
        return f"{float(value):,.2f} TL".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return str(value)


app.jinja_env.filters['datetimeformat'] = format_datetime
app.jinja_env.filters['dateformat'] = format_date
app.jinja_env.filters['currencyformat'] = format_currency
@app.context_processor
def inject_now(): return {'now': datetime.now()}

def get_properties_list():
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, title, city, district FROM properties WHERE status NOT IN ('Satıldı', 'Kiralandı') ORDER BY title")
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Hata: get_properties_list - {e}")
        return []

def get_customers_list():
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, name, phone FROM customers WHERE is_archived = 0 ORDER BY name")
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Hata: get_customers_list - {e}")
        return []

def get_owners_list():
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, name FROM owners ORDER BY name")
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Hata: get_owners_list - {e}")
        return []

def get_personnel_list():
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, name, position FROM personnel WHERE is_active = 1 ORDER BY name")
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Hata: get_personnel_list - {e}")
        return []


# --- Genel Route ---
@app.route('/')
def index():
    return render_template('index.html', page_title="Ana Sayfa")

# --- Emlak Modülü Routes ---
@app.route('/properties')
def list_properties():
    db = get_db()
    cursor = db.cursor()
    filters = {
        k: request.args.get(k, default=v[0], type=v[1]) for k, v in {
            'city': ('', str), 'district': ('', str), 'property_type': ('', str),
            'status': ('', str), 'rooms': ('', str), 'min_price': (None, float),
            'max_price': (None, float)
        }.items()
    }
    query = """
        SELECT p.id, p.title, p.property_type, p.status, p.price, p.city, p.district, p.rooms, o.name as owner_name
        FROM properties p
        LEFT JOIN owners o ON p.owner_id = o.id
    """
    where_clauses, params = [], []
    if filters['city']: where_clauses.append("LOWER(p.city) LIKE LOWER(?)"); params.append(f"%{filters['city']}%")
    if filters['district']: where_clauses.append("LOWER(p.district) LIKE LOWER(?)"); params.append(f"%{filters['district']}%")
    if filters['property_type']: where_clauses.append("p.property_type = ?"); params.append(filters['property_type'])
    if filters['status']: where_clauses.append("p.status = ?"); params.append(filters['status'])
    if filters['rooms']: where_clauses.append("p.rooms = ?"); params.append(filters['rooms'])
    if filters['min_price'] is not None: where_clauses.append("p.price >= ?"); params.append(filters['min_price'])
    if filters['max_price'] is not None: where_clauses.append("p.price <= ?"); params.append(filters['max_price'])

    if where_clauses: query += " WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY p.date_added DESC"

    properties = []
    try:
        cursor.execute(query, params)
        properties = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f"Emlakları listelerken veritabanı hatası: {e}", "error")

    distinct_values = {f'distinct_{col}s': get_distinct_values('properties', col)
                       for col in ['city', 'district', 'property_type', 'status', 'rooms']}
    return render_template('properties.html', properties=properties, page_title="Emlaklar",
                           filters=filters, **distinct_values)

@app.route('/add_property', methods=['GET', 'POST'])
def add_property():
     owners = get_owners_list()
     if request.method == 'POST':
         form_data = request.form.to_dict()
         db = get_db()
         cursor = db.cursor()
         try:
            if not form_data.get('title') or not form_data.get('property_type') or not form_data.get('status') or not form_data.get('city') or not form_data.get('district'):
                flash('İlan Başlığı, Emlak Tipi, Durum, Şehir ve İlçe alanları zorunludur.', 'error')
                return render_template('add_property.html', page_title="Yeni Emlak Ekle", form_data=form_data, owners=owners)

            price = float(form_data['price'].replace('.', '').replace(',', '.')) if form_data.get('price') else None
            area = float(form_data['area'].replace(',', '.')) if form_data.get('area') else None
            owner_id = int(form_data['owner_id']) if form_data.get('owner_id') else None

            cursor.execute('''INSERT INTO properties
                              (title, description, property_type, status, price, area, rooms, address, city, district, owner_id)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                           (form_data['title'], form_data.get('description'), form_data['property_type'], form_data['status'],
                            price, area, form_data.get('rooms'), form_data.get('address'),
                            form_data['city'], form_data['district'], owner_id))
            db.commit()
            flash('Emlak başarıyla eklendi!', 'success')
            return redirect(url_for('list_properties'))
         except sqlite3.Error as e:
            db.rollback(); print(f"DB Error (Add Property): {e}")
            flash(f'Emlak eklenirken bir veritabanı hatası oluştu: {e}', 'error')
            return render_template('add_property.html', page_title="Yeni Emlak Ekle", form_data=form_data, owners=owners)
         except ValueError:
            flash('Fiyat ve Alan sayısal değer olmalıdır (örn: 1500.50).', 'error')
            return render_template('add_property.html', page_title="Yeni Emlak Ekle", form_data=form_data, owners=owners)

     return render_template('add_property.html', page_title="Yeni Emlak Ekle", owners=owners)

@app.route('/edit_property/<int:property_id>', methods=['GET', 'POST'])
def edit_property(property_id):
    owners = get_owners_list()
    db = get_db()
    cursor = db.cursor()
    property_data = None
    try:
        cursor.execute("SELECT * FROM properties WHERE id = ?", (property_id,))
        property_data = cursor.fetchone()
    except sqlite3.Error as e:
        flash(f"Emlak bilgileri alınırken hata: {e}", "error")
        return redirect(url_for('list_properties'))

    if property_data is None: abort(404)

    if request.method == 'POST':
        form_data = request.form.to_dict()
        try:
            if not form_data.get('title') or not form_data.get('property_type') or not form_data.get('status') or not form_data.get('city') or not form_data.get('district'):
                flash('İlan Başlığı, Emlak Tipi, Durum, Şehir ve İlçe alanları zorunludur.', 'error')
                current_data = dict(property_data); current_data.update(form_data)
                return render_template('edit_property.html', page_title="Emlak Düzenle", property=current_data, owners=owners)

            price = float(form_data['price'].replace('.', '').replace(',', '.')) if form_data.get('price') else None
            area = float(form_data['area'].replace(',', '.')) if form_data.get('area') else None
            owner_id = int(form_data['owner_id']) if form_data.get('owner_id') else None

            cursor.execute('''UPDATE properties SET
                              title=?, description=?, property_type=?, status=?, price=?, area=?, rooms=?, address=?, city=?, district=?, owner_id=?
                              WHERE id=?''',
                           (form_data['title'], form_data.get('description'), form_data['property_type'], form_data['status'],
                            price, area, form_data.get('rooms'), form_data.get('address'),
                            form_data['city'], form_data['district'], owner_id, property_id))
            db.commit()
            flash('Emlak başarıyla güncellendi!', 'success')
            return redirect(url_for('list_properties'))
        except sqlite3.Error as e:
            db.rollback(); print(f"DB Error (Edit Property): {e}")
            flash(f'Emlak güncellenirken hata: {e}', 'error')
            current_data = dict(property_data); current_data.update(form_data)
            return render_template('edit_property.html', page_title="Emlak Düzenle", property=current_data, owners=owners)
        except ValueError:
            flash('Fiyat ve Alan sayısal değer olmalıdır (örn: 1500.50).', 'error')
            current_data = dict(property_data); current_data.update(form_data)
            return render_template('edit_property.html', page_title="Emlak Düzenle", property=current_data, owners=owners)

    return render_template('edit_property.html', page_title="Emlak Düzenle", property=property_data, owners=owners)

@app.route('/delete_property/<int:property_id>', methods=['POST'])
def delete_property(property_id):
     db = get_db()
     cursor = db.cursor()
     try:
         cursor.execute("DELETE FROM properties WHERE id = ?", (property_id,))
         db.commit()
         flash(f"ID {property_id} olan emlak başarıyla silindi.", "success")
     except sqlite3.Error as e:
         db.rollback()
         print(f"DB Error (Delete Property): {e}")
         flash(f"Emlak silinirken bir hata oluştu: {e}", 'error')
     return redirect(url_for('list_properties'))

# --- Müşteri (CRM) Modülü Routes ---
@app.route('/customers')
def list_customers():
    db = get_db()
    cursor = db.cursor()
    customers = []
    try:
        cursor.execute("SELECT id, name, phone, email, customer_type, notes, date_registered FROM customers WHERE is_archived = 0 ORDER BY date_registered DESC")
        customers = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f"Müşterileri listelerken hata: {e}", "error")
    return render_template('customers.html', customers=customers, page_title="Aktif Müşteriler")

@app.route('/archived_customers')
def list_archived_customers():
    db = get_db()
    cursor = db.cursor()
    customers = []
    try:
        cursor.execute("SELECT id, name, phone, email, customer_type, notes, date_registered FROM customers WHERE is_archived = 1 ORDER BY date_registered DESC")
        customers = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f"Arşivlenmiş müşterileri listelerken hata: {e}", "error")
    return render_template('archived_customers.html', customers=customers, page_title="Arşivlenmiş Müşteriler")

@app.route('/add_customer', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        form_data = request.form.to_dict()
        db = get_db()
        cursor = db.cursor()
        try:
            if not form_data.get('name') or not form_data.get('customer_type'):
                 flash('Ad Soyadı ve Müşteri Tipi alanları zorunludur.', 'error')
                 return render_template('add_customer.html', page_title="Yeni Müşteri Ekle", form_data=form_data)

            phone = form_data.get('phone') or None
            email = form_data.get('email') or None

            cursor.execute('''INSERT INTO customers (name, phone, email, customer_type, notes, is_archived)
                              VALUES (?, ?, ?, ?, ?, 0)''',
                           (form_data['name'], phone, email, form_data['customer_type'], form_data.get('notes')))
            db.commit()
            flash('Müşteri başarıyla eklendi!', 'success')
            return redirect(url_for('list_customers'))
        except sqlite3.IntegrityError as e:
            db.rollback()
            error_msg = "Bu telefon numarası veya e-posta adresi zaten kayıtlı." if "UNIQUE constraint failed" in str(e) else f"Veritabanı bütünlük hatası: {e}"
            flash(error_msg, 'error')
            return render_template('add_customer.html', page_title="Yeni Müşteri Ekle", form_data=form_data)
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Müşteri eklenirken bir veritabanı hatası oluştu: {e}', 'error')
            return render_template('add_customer.html', page_title="Yeni Müşteri Ekle", form_data=form_data)
    return render_template('add_customer.html', page_title="Yeni Müşteri Ekle")

@app.route('/edit_customer/<int:customer_id>', methods=['GET', 'POST'])
def edit_customer(customer_id):
    db = get_db()
    cursor = db.cursor()
    customer_data = None
    try:
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        customer_data = cursor.fetchone()
    except sqlite3.Error as e:
         flash(f"Müşteri bilgileri alınırken hata: {e}", "error")
         redirect_url = url_for('list_customers')
         try:
             cursor.execute("SELECT is_archived FROM customers WHERE id = ?", (customer_id,))
             temp_data = cursor.fetchone()
             if temp_data and temp_data['is_archived']:
                 redirect_url = url_for('list_archived_customers')
         except sqlite3.Error:
             pass
         return redirect(redirect_url)


    if customer_data is None: abort(404)

    if request.method == 'POST':
        form_data = request.form.to_dict()
        try:
            if not form_data.get('name') or not form_data.get('customer_type'):
                 flash('Ad Soyadı ve Müşteri Tipi alanları zorunludur.', 'error')
                 return render_template('edit_customer.html', page_title="Müşteri Düzenle", customer=dict(customer_data, **form_data))

            phone = form_data.get('phone') or None
            email = form_data.get('email') or None

            cursor.execute('''UPDATE customers SET
                              name=?, phone=?, email=?, customer_type=?, notes=?
                              WHERE id=?''',
                           (form_data['name'], phone, email, form_data['customer_type'], form_data.get('notes'), customer_id))
            db.commit()
            flash('Müşteri başarıyla güncellendi!', 'success')
            redirect_url = url_for('list_customers') if not customer_data['is_archived'] else url_for('list_archived_customers')
            return redirect(redirect_url)
        except sqlite3.IntegrityError as e:
            db.rollback()
            error_msg = "Bu telefon numarası veya e-posta adresi zaten başka bir müşteriye ait." if "UNIQUE constraint failed" in str(e) else f"Veritabanı bütünlük hatası: {e}"
            flash(error_msg, 'error')
            return render_template('edit_customer.html', page_title="Müşteri Düzenle", customer=dict(customer_data, **form_data))
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Müşteri güncellenirken bir veritabanı hatası oluştu: {e}', 'error')
            return render_template('edit_customer.html', page_title="Müşteri Düzenle", customer=dict(customer_data, **form_data))
    return render_template('edit_customer.html', page_title="Müşteri Düzenle", customer=customer_data)

@app.route('/delete_customer/<int:customer_id>', methods=['POST'])
def delete_customer(customer_id):
    db = get_db()
    cursor = db.cursor()
    is_archived = 0
    try:
        cursor.execute("SELECT is_archived FROM customers WHERE id = ?", (customer_id,))
        customer = cursor.fetchone()
        if customer:
            is_archived = customer['is_archived']

        cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        db.commit()
        flash(f"ID {customer_id} olan müşteri başarıyla silindi.", "success")
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error (Delete Customer): {e}")
        flash(f"Müşteri silinirken bir hata oluştu: {e}", 'error')

    redirect_url = url_for('list_customers') if not is_archived else url_for('list_archived_customers')
    return redirect(redirect_url)


@app.route('/archive_customer/<int:customer_id>', methods=['POST'])
def archive_customer(customer_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE customers SET is_archived = 1 WHERE id = ?", (customer_id,))
        db.commit()
        flash(f"ID {customer_id} olan müşteri başarıyla arşivlendi.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Müşteri arşivlenirken hata: {e}", "error")
    return redirect(url_for('list_customers'))

@app.route('/unarchive_customer/<int:customer_id>', methods=['POST'])
def unarchive_customer(customer_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE customers SET is_archived = 0 WHERE id = ?", (customer_id,))
        db.commit()
        flash(f"ID {customer_id} olan müşteri başarıyla arşivden çıkarıldı.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Müşteri arşivden çıkarılırken hata: {e}", "error")
    return redirect(url_for('list_archived_customers'))


# --- Emlak Sahibi (Owners) Modülü Routes ---
@app.route('/owners')
def list_owners():
    db = get_db()
    cursor = db.cursor()
    owners = []
    try:
        cursor.execute("SELECT id, name, phone, email FROM owners ORDER BY name")
        owners = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f"Sahipleri listelerken hata: {e}", "error")
    return render_template('owners.html', owners=owners, page_title="Emlak Sahipleri")

@app.route('/add_owner', methods=['GET', 'POST'])
def add_owner():
    if request.method == 'POST':
        form_data = request.form.to_dict()
        db = get_db()
        cursor = db.cursor()
        try:
            if not form_data.get('name'):
                 flash('Ad Soyadı alanı zorunludur.', 'error')
                 return render_template('add_owner.html', page_title="Yeni Emlak Sahibi Ekle", form_data=form_data)

            phone = form_data.get('phone') or None
            email = form_data.get('email') or None

            cursor.execute("INSERT INTO owners (name, phone, email, notes) VALUES (?, ?, ?, ?)",
                           (form_data['name'], phone, email, form_data.get('notes')))
            db.commit()
            flash('Emlak sahibi başarıyla eklendi!', 'success')
            return redirect(url_for('list_owners'))
        except sqlite3.IntegrityError as e:
            db.rollback()
            error_msg = "Bu telefon numarası veya e-posta adresi zaten kayıtlı." if "UNIQUE constraint failed" in str(e) else f"Veritabanı bütünlük hatası: {e}"
            flash(error_msg, 'error')
            return render_template('add_owner.html', page_title="Yeni Emlak Sahibi Ekle", form_data=form_data)
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Emlak sahibi eklenirken bir veritabanı hatası oluştu: {e}', 'error')
            return render_template('add_owner.html', page_title="Yeni Emlak Sahibi Ekle", form_data=form_data)
    return render_template('add_owner.html', page_title="Yeni Emlak Sahibi Ekle")

@app.route('/edit_owner/<int:owner_id>', methods=['GET', 'POST'])
def edit_owner(owner_id):
    db = get_db()
    cursor = db.cursor()
    owner_data = None
    try:
        cursor.execute("SELECT * FROM owners WHERE id = ?", (owner_id,))
        owner_data = cursor.fetchone()
    except sqlite3.Error as e:
        flash(f"Sahip bilgileri alınırken hata: {e}", "error")
        return redirect(url_for('list_owners'))

    if owner_data is None: abort(404)

    if request.method == 'POST':
        form_data = request.form.to_dict()
        try:
            if not form_data.get('name'):
                 flash('Ad Soyadı alanı zorunludur.', 'error')
                 return render_template('edit_owner.html', page_title="Emlak Sahibi Düzenle", owner=dict(owner_data, **form_data))

            phone = form_data.get('phone') or None
            email = form_data.get('email') or None

            cursor.execute("UPDATE owners SET name=?, phone=?, email=?, notes=? WHERE id=?",
                           (form_data['name'], phone, email, form_data.get('notes'), owner_id))
            db.commit()
            flash('Emlak sahibi başarıyla güncellendi!', 'success')
            return redirect(url_for('list_owners'))
        except sqlite3.IntegrityError as e:
            db.rollback()
            error_msg = "Bu telefon numarası veya e-posta adresi zaten başka bir sahibe ait." if "UNIQUE constraint failed" in str(e) else f"Veritabanı bütünlük hatası: {e}"
            flash(error_msg, 'error')
            return render_template('edit_owner.html', page_title="Emlak Sahibi Düzenle", owner=dict(owner_data, **form_data))
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Emlak sahibi güncellenirken bir veritabanı hatası oluştu: {e}', 'error')
            return render_template('edit_owner.html', page_title="Emlak Sahibi Düzenle", owner=dict(owner_data, **form_data))
    return render_template('edit_owner.html', page_title="Emlak Sahibi Düzenle", owner=owner_data)

@app.route('/delete_owner/<int:owner_id>', methods=['POST'])
def delete_owner(owner_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE properties SET owner_id = NULL WHERE owner_id = ?", (owner_id,))
        cursor.execute("UPDATE contracts SET owner_id = NULL WHERE owner_id = ?", (owner_id,))
        cursor.execute("DELETE FROM owners WHERE id = ?", (owner_id,))
        db.commit()
        flash(f"ID {owner_id} olan emlak sahibi başarıyla silindi. İlgili emlakların ve sözleşmelerin sahibi 'Belirsiz' olarak ayarlandı.", "success")
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error (Delete Owner): {e}")
        flash(f"Emlak sahibi silinirken bir hata oluştu: {e}", 'error')
    return redirect(url_for('list_owners'))


# --- Personel Modülü Routes ---
@app.route('/personnel')
def list_personnel():
    db = get_db()
    cursor = db.cursor()
    personnel_list = []
    try:
        cursor.execute("SELECT id, name, position, phone, email, hire_date, is_active FROM personnel ORDER BY name")
        personnel_list = cursor.fetchall()
    except sqlite3.Error as e:
         flash(f"Personel listelenirken hata: {e}", "error")
    return render_template('personnel.html', personnel_list=personnel_list, page_title="Personel Listesi")

@app.route('/add_personnel', methods=['GET', 'POST'])
def add_personnel():
    if request.method == 'POST':
        form_data = request.form.to_dict()
        db = get_db()
        cursor = db.cursor()
        try:
            if not form_data.get('name'):
                 flash('Ad Soyadı alanı zorunludur.', 'error')
                 return render_template('add_personnel.html', page_title="Yeni Personel Ekle", form_data=form_data)

            phone = form_data.get('phone') or None
            email = form_data.get('email') or None
            hire_date_str = form_data.get('hire_date')
            hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d').date() if hire_date_str else None
            is_active = 1 if 'is_active' in form_data else 0

            cursor.execute('''INSERT INTO personnel (name, position, phone, email, hire_date, is_active, notes)
                              VALUES (?, ?, ?, ?, ?, ?, ?)''',
                           (form_data['name'], form_data.get('position'), phone, email, hire_date, is_active, form_data.get('notes')))
            db.commit()
            flash('Personel başarıyla eklendi!', 'success')
            return redirect(url_for('list_personnel'))
        except sqlite3.IntegrityError as e:
            db.rollback()
            error_msg = "Bu telefon numarası veya e-posta adresi zaten kayıtlı." if "UNIQUE constraint failed" in str(e) else f"Veritabanı bütünlük hatası: {e}"
            flash(error_msg, 'error')
            return render_template('add_personnel.html', page_title="Yeni Personel Ekle", form_data=form_data)
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Personel eklenirken bir veritabanı hatası oluştu: {e}', 'error')
            return render_template('add_personnel.html', page_title="Yeni Personel Ekle", form_data=form_data)
        except ValueError:
             flash('İşe giriş tarihi geçersiz formatta (YYYY-AA-GG olmalı).', 'error')
             return render_template('add_personnel.html', page_title="Yeni Personel Ekle", form_data=form_data)
    return render_template('add_personnel.html', page_title="Yeni Personel Ekle")

@app.route('/edit_personnel/<int:personnel_id>', methods=['GET', 'POST'])
def edit_personnel(personnel_id):
    db = get_db()
    cursor = db.cursor()
    personnel_data = None
    try:
        cursor.execute("SELECT * FROM personnel WHERE id = ?", (personnel_id,))
        personnel_data = cursor.fetchone()
    except sqlite3.Error as e:
        flash(f"Personel bilgileri alınırken hata: {e}", "error")
        return redirect(url_for('list_personnel'))

    if personnel_data is None: abort(404)

    if request.method == 'POST':
        form_data = request.form.to_dict()
        try:
            if not form_data.get('name'):
                 flash('Ad Soyadı alanı zorunludur.', 'error')
                 return render_template('edit_personnel.html', page_title="Personel Düzenle", personnel=dict(personnel_data, **form_data))

            phone = form_data.get('phone') or None
            email = form_data.get('email') or None
            hire_date_str = form_data.get('hire_date')
            hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d').date() if hire_date_str else None
            is_active = 1 if 'is_active' in form_data else 0

            cursor.execute('''UPDATE personnel SET
                              name=?, position=?, phone=?, email=?, hire_date=?, is_active=?, notes=?
                              WHERE id=?''',
                           (form_data['name'], form_data.get('position'), phone, email, hire_date, is_active, form_data.get('notes'), personnel_id))
            db.commit()
            flash('Personel bilgileri başarıyla güncellendi!', 'success')
            return redirect(url_for('list_personnel'))
        except sqlite3.IntegrityError as e:
            db.rollback()
            error_msg = "Bu telefon numarası veya e-posta adresi zaten başka bir personele ait." if "UNIQUE constraint failed" in str(e) else f"Veritabanı bütünlük hatası: {e}"
            flash(error_msg, 'error')
            return render_template('edit_personnel.html', page_title="Personel Düzenle", personnel=dict(personnel_data, **form_data))
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Personel güncellenirken bir veritabanı hatası oluştu: {e}', 'error')
            return render_template('edit_personnel.html', page_title="Personel Düzenle", personnel=dict(personnel_data, **form_data))
        except ValueError:
             flash('İşe giriş tarihi geçersiz formatta (YYYY-AA-GG olmalı).', 'error')
             return render_template('edit_personnel.html', page_title="Personel Düzenle", personnel=dict(personnel_data, **form_data))

    personnel_dict = dict(personnel_data)
    if personnel_dict['hire_date']:
        personnel_dict['hire_date'] = format_date(personnel_dict['hire_date'], '%Y-%m-%d')

    return render_template('edit_personnel.html', page_title="Personel Düzenle", personnel=personnel_dict)


@app.route('/delete_personnel/<int:personnel_id>', methods=['POST'])
def delete_personnel(personnel_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE contracts SET personnel_id = NULL WHERE personnel_id = ?", (personnel_id,))
        cursor.execute("DELETE FROM personnel WHERE id = ?", (personnel_id,))
        db.commit()
        flash(f"ID {personnel_id} olan personel başarıyla silindi. İlgili sözleşmelerdeki sorumlu personel 'Belirsiz' olarak ayarlandı.", "success")
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error (Delete Personnel): {e}")
        flash(f"Personel silinirken bir hata oluştu: {e}", 'error')
    return redirect(url_for('list_personnel'))


# --- Sözleşme Modülü ---
def generate_contract_pdf(data):
    """Verilen bilgilere göre PDF sözleşmesi oluşturur."""
    if SimpleDocTemplate is None:
        raise ImportError("PDF oluşturma için reportlab kütüphanesi yüklenemedi.")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    # Özel Stiller (FONT_NAME ile)
    title_style = ParagraphStyle(name='TitleStyle', parent=styles['h1'], alignment=TA_CENTER, fontName=FONT_NAME, fontSize=16, spaceAfter=20)
    heading_style = ParagraphStyle(name='HeadingStyle', parent=styles['h2'], fontName=FONT_NAME, fontSize=12, spaceBefore=12, spaceAfter=6)
    body_style = ParagraphStyle(name='BodyStyle', parent=styles['Normal'], fontName=FONT_NAME, fontSize=10, alignment=TA_JUSTIFY, spaceAfter=6, leading=14)
    info_style = ParagraphStyle(name='InfoStyle', parent=styles['Normal'], fontName=FONT_NAME, fontSize=10, alignment=TA_LEFT, spaceAfter=3, leading=12)
    table_header_style = ParagraphStyle(name='TableHeader', parent=styles['Normal'], fontName=FONT_NAME, fontSize=10, alignment=TA_LEFT)
    table_cell_style = ParagraphStyle(name='TableCell', parent=styles['Normal'], fontName=FONT_NAME, fontSize=10, alignment=TA_LEFT)

    story = []

    # --- Sözleşme Başlığı ---
    contract_title_tr = data['contract_type']
    if contract_title_tr == 'Kira': contract_title_tr = 'KİRA'
    elif contract_title_tr == 'Satış': contract_title_tr = 'SATIŞ'
    story.append(Paragraph(f"<b>{contract_title_tr.upper()} SÖZLEŞMESİ</b>", title_style))
    story.append(Spacer(1, 0.5*cm))

    # --- Taraflar ---
    story.append(Paragraph("<b>Taraflar</b>", heading_style))

    owner_name = data['owner']['name'] if data.get('owner') else '<i>Belirtilmemiş</i>'
    owner_phone = data['owner']['phone'] if data.get('owner') and data['owner'].get('phone') else '-'
    owner_email = data['owner']['email'] if data.get('owner') and data['owner'].get('email') else '-'
    owner_role = "Satıcı" if data['contract_type'] == 'Satış' else "Kiraya Veren"

    owner_info = [
        [Paragraph(f"<b>{owner_role}:</b>", table_header_style), Paragraph(owner_name, table_cell_style)],
        [Paragraph("<b>Telefon:</b>", table_header_style), Paragraph(owner_phone, table_cell_style)],
        [Paragraph("<b>E-posta:</b>", table_header_style), Paragraph(owner_email, table_cell_style)],
    ]
    owner_table = Table(owner_info, colWidths=[4*cm, None])
    owner_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 6)]))
    story.append(owner_table)
    story.append(Spacer(1, 0.2*cm))

    customer_role = 'Alıcı' if data['contract_type'] == 'Satış' else 'Kiracı'
    customer_info = [
        [Paragraph(f"<b>{customer_role}:</b>", table_header_style), Paragraph(data['customer']['name'], table_cell_style)],
        [Paragraph("<b>Telefon:</b>", table_header_style), Paragraph(data['customer']['phone'] or '-', table_cell_style)],
        [Paragraph("<b>E-posta:</b>", table_header_style), Paragraph(data['customer']['email'] or '-', table_cell_style)],
    ]
    customer_table = Table(customer_info, colWidths=[4*cm, None])
    customer_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 6)]))
    story.append(customer_table)
    story.append(Spacer(1, 0.5*cm))

    # --- Sözleşme Konusu Emlak ---
    story.append(Paragraph("<b>Sözleşme Konusu Emlak</b>", heading_style))
    prop_address = f"{data['property'].get('address', '')}, {data['property'].get('district', '')} / {data['property'].get('city', '')}".strip(', ')
    property_info = [
        [Paragraph("<b>İlan Başlığı:</b>", table_header_style), Paragraph(data['property']['title'], table_cell_style)],
        [Paragraph("<b>Emlak Tipi:</b>", table_header_style), Paragraph(data['property'].get('property_type', '-'), table_cell_style)],
        [Paragraph("<b>Adres:</b>", table_header_style), Paragraph(prop_address or '-', table_cell_style)],
        [Paragraph("<b>Alan (m²):</b>", table_header_style), Paragraph(str(data['property']['area']) if data['property'].get('area') else '-', table_cell_style)],
        [Paragraph("<b>Oda Sayısı:</b>", table_header_style), Paragraph(data['property'].get('rooms', '-'), table_cell_style)],
    ]
    property_table = Table(property_info, colWidths=[3*cm, None])
    property_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 6)]))
    story.append(property_table)
    story.append(Spacer(1, 0.5*cm))

    # --- Sözleşme Şartları ---
    story.append(Paragraph("<b>Sözleşme Şartları</b>", heading_style))
    price_formatted = format_currency(data.get('price'))

    if data['contract_type'] == 'Kira':
        story.append(Paragraph(f"İşbu sözleşme, yukarıda bilgileri verilen emlakın <b>{owner_name}</b> tarafından <b>{data['customer']['name']}</b>'a kiralanmasına ilişkindir.", body_style))
        story.append(Paragraph(f"Kira başlangıç tarihi: <b>{format_date(data.get('start_date')) if data.get('start_date') else '-'}</b>", info_style))
        story.append(Paragraph(f"Kira bitiş tarihi: <b>{format_date(data.get('end_date')) if data.get('end_date') else '-'}</b>", info_style))
        story.append(Paragraph(f"Aylık kira bedeli: <b>{price_formatted}</b>", info_style))
        story.append(Paragraph("Kiracı, kira bedelini her ayın ilk 5 (beş) iş günü içinde Kiraya Veren'in belirteceği banka hesabına ödemeyi kabul ve taahhüt eder.", body_style))
        story.append(Paragraph("Kiralanan mülk, sözleşme amacına uygun olarak (mesken/iş yeri) kullanılacaktır. Kiracı, mülke zarar vermemeyi, komşuluk ilişkilerine özen göstermeyi, aidat ve genel giderleri zamanında ödemeyi taahhüt eder.", body_style))
    elif data['contract_type'] == 'Satış':
        story.append(Paragraph(f"İşbu sözleşme, yukarıda bilgileri verilen emlakın <b>{owner_name}</b> (Satıcı) tarafından <b>{data['customer']['name']}</b> (Alıcı)'ya satışına ilişkindir.", body_style))
        story.append(Paragraph(f"Satış bedeli: <b>{price_formatted}</b>", info_style))
        story.append(Paragraph("Satış bedeli, tapu devri sırasında Alıcı tarafından Satıcı'ya nakden ve defaten ödenecektir (veya anlaşılan ödeme planına göre). Tapu harçları ve masrafları yasal oranlarda taraflarca paylaşılacaktır (veya farklı anlaşıldıysa belirtilir).", body_style))
        story.append(Paragraph("Satıcı, emlakın üzerinde herhangi bir takyidat (ipotek, haciz vb.) bulunmadığını beyan ve taahhüt eder.", body_style))
    else:
         story.append(Paragraph("İşbu sözleşme, taraflar arasında aşağıdaki koşullarda anlaşmaya varıldığını belirtir:", body_style))

    if data.get('notes'):
        story.append(Paragraph("<b>Ek Notlar / Özel Şartlar:</b>", heading_style))
        cleaned_notes = data['notes'].replace('<', '&lt;').replace('>', '&gt;')
        story.append(Paragraph(cleaned_notes.replace('\n', '<br/>\n'), body_style))

    story.append(Spacer(1, 1*cm))

    # --- İmzalar ---
    signature_data = [
        [Paragraph(f"<b>{owner_role}</b><br/><br/>{owner_name}", table_cell_style), Paragraph(f"<b>{customer_role}</b><br/><br/>{data['customer']['name']}", table_cell_style)],
        ['', ''],
        [Paragraph('(İmza)', table_cell_style), Paragraph('(İmza)', table_cell_style)],
    ]
    signature_table = Table(signature_data, colWidths=[8*cm, 8*cm])
    signature_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,0), 15),
        ('LINEABOVE', (0,1), (0,1), 1, (0,0,0)),
        ('LINEABOVE', (1,1), (1,1), 1, (0,0,0)),
        ('TOPPADDING', (0,2), (-1,2), 2),
        ('BOTTOMPADDING', (0,2), (-1,-1), 10),
    ]))
    story.append(signature_table)
    story.append(Spacer(1, 0.5*cm))

    # --- Hazırlayan Personel ve Tarih ---
    story.append(Paragraph(f"Sözleşme Tarihi: {format_date(data['contract_date'])}", info_style))
    personnel_name = data['personnel']['name'] if data.get('personnel') else '<i>Belirtilmemiş</i>'
    personnel_title = f" ({data['personnel']['position']})" if data.get('personnel') and data['personnel'].get('position') else ""
    story.append(Paragraph(f"Hazırlayan Yetkili: {personnel_name}{personnel_title}", info_style))

    try:
        doc.build(story)
        buffer.seek(0)
        return buffer
    except Exception as pdf_build_error:
        error_message = f"PDF Oluşturma Hatası (doc.build): {pdf_build_error}"
        print(error_message)
        raise RuntimeError(f"PDF oluşturulamadı: {pdf_build_error}")


@app.route('/create_contract', methods=['GET', 'POST'])
def create_contract():
    """Sözleşme oluşturma formunu gösterir ve PDF üretip veritabanına kaydeder."""
    if SimpleDocTemplate is None:
         flash("PDF oluşturma kütüphanesi (reportlab) yüklenemediği için bu özellik kullanılamıyor. Lütfen 'pip install reportlab' komutu ile kurun.", "error")
         return redirect(url_for('index'))

    properties = get_properties_list()
    customers = get_customers_list()
    personnel = get_personnel_list()
    form_data_on_error = {}

    if request.method == 'POST':
        form_data_on_error = request.form.to_dict()
        try:
            property_id_str = request.form.get('property_id')
            customer_id_str = request.form.get('customer_id')
            personnel_id_str = request.form.get('personnel_id')
            contract_type = request.form.get('contract_type')
            contract_date_str = request.form.get('contract_date') or datetime.now().strftime('%Y-%m-%d')
            start_date_str = request.form.get('start_date') or None
            end_date_str = request.form.get('end_date') or None
            price_str = request.form.get('price', '').strip().replace('.', '').replace(',', '.')
            notes = request.form.get('notes', '').strip()

            if not property_id_str or not customer_id_str or not personnel_id_str or not contract_type:
                flash("Lütfen Emlak, Müşteri, Sorumlu Personel ve Sözleşme Tipi seçin.", "error")
                raise ValueError("Zorunlu alanlar eksik")

            property_id = int(property_id_str)
            customer_id = int(customer_id_str)
            personnel_id = int(personnel_id_str)

            contract_date = datetime.strptime(contract_date_str, '%Y-%m-%d').date()
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None

            if contract_type == 'Kira' and (not start_date or not end_date):
                 flash("Kira sözleşmesi için Başlangıç ve Bitiş Tarihleri gereklidir.", "error")
                 raise ValueError("Kira için tarihler eksik")
            if contract_type == 'Kira' and start_date and end_date and end_date <= start_date:
                flash("Kira bitiş tarihi, başlangıç tarihinden sonra olmalıdır.", "error")
                raise ValueError("Geçersiz kira tarih aralığı")

            price = float(price_str) if price_str else None

            db = get_db()
            cursor = db.cursor()

            cursor.execute("""
                SELECT p.*, o.id as owner_id_from_owner, o.name as owner_name, o.phone as owner_phone, o.email as owner_email
                FROM properties p
                LEFT JOIN owners o ON p.owner_id = o.id
                WHERE p.id = ?""", (property_id,))
            prop = cursor.fetchone()

            cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
            cust = cursor.fetchone()

            cursor.execute("SELECT * FROM personnel WHERE id = ?", (personnel_id,))
            pers = cursor.fetchone()

            if not prop: flash(f"ID'si {property_id} olan emlak bulunamadı veya uygun durumda değil.", "error"); raise ValueError("Emlak bulunamadı")
            if not cust: flash(f"ID'si {customer_id} olan müşteri bulunamadı.", "error"); raise ValueError("Müşteri bulunamadı")
            if not pers: flash(f"ID'si {personnel_id} olan personel bulunamadı.", "error"); raise ValueError("Personel bulunamadı")

            owner = None
            if prop['owner_id_from_owner']:
                 owner = {
                     'id': prop['owner_id_from_owner'],
                     'name': prop['owner_name'],
                     'phone': prop['owner_phone'],
                     'email': prop['owner_email']
                 }

            if contract_type == 'Satış' and not owner:
                flash(f"Seçilen '{prop['title']}' adlı emlak için bir sahip tanımlanmamış. Satış sözleşmesi oluşturulamaz. Lütfen önce emlağı düzenleyip sahibini atayın.", "error")
                raise ValueError("Satış için sahip gerekli")

            pdf_data = {
                'contract_type': contract_type,
                'property': dict(prop),
                'customer': dict(cust),
                'owner': owner,
                'personnel': dict(pers),
                'contract_date': contract_date,
                'start_date': start_date,
                'end_date': end_date,
                'price': price if price is not None else prop['price'],
                'notes': notes
            }

            # PDF oluştur
            pdf_buffer = generate_contract_pdf(pdf_data)
            pdf_bytes = pdf_buffer.getvalue() # PDF içeriğini byte olarak al

            # Dosya adını oluştur
            clean_cust_name = "".join(c for c in cust['name'] if c.isalnum() or c in ['_']).rstrip()
            clean_prop_title = "".join(c for c in prop['title'][:20] if c.isalnum() or c in ['_']).rstrip()
            pdf_filename = f"{contract_type}_{clean_cust_name}_{clean_prop_title}_{prop['id']}.pdf"

            # Sözleşmeyi veritabanına kaydet (PDF verisi ve dosya adı ile birlikte)
            try:
                cursor.execute('''INSERT INTO contracts
                                  (contract_type, property_id, customer_id, owner_id, personnel_id,
                                   contract_date, start_date, end_date, price, notes,
                                   pdf_filename, pdf_data)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', # 12 parametre
                               (contract_type, property_id, customer_id, owner['id'] if owner else None, personnel_id,
                                contract_date, start_date, end_date, pdf_data['price'], notes,
                                pdf_filename, sqlite3.Binary(pdf_bytes))) # pdf_filename ve pdf_data eklendi

                new_status = 'Satıldı' if contract_type == 'Satış' else ('Kiralandı' if contract_type == 'Kira' else prop['status'])
                if new_status != prop['status']:
                     cursor.execute("UPDATE properties SET status = ? WHERE id = ?", (new_status, property_id))
                     print(f"Emlak ID {property_id} durumu '{new_status}' olarak güncellendi.")

                db.commit()
                print("Sözleşme veritabanına başarıyla kaydedildi (PDF dahil).")
                flash(f"{contract_type} sözleşmesi başarıyla oluşturuldu ve veritabanına kaydedildi.", "success")
            except sqlite3.Error as db_err:
                 db.rollback()
                 print(f"DB Error (Save Contract with PDF): {db_err}")
                 flash(f"PDF oluşturuldu ancak sözleşme veritabanına kaydedilirken hata oluştu: {db_err}", "error")
                 # Hata durumunda PDF'i yine de indirme seçeneği sunabiliriz, ancak bu sefer kaydedilmediğini belirtiriz.
                 # Şimdilik hata mesajı yeterli.

            # PDF'i kullanıcıya hemen indirme olarak gönder (isteğe bağlı, artık DB'de kayıtlı)
            response = make_response(pdf_bytes)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
            # PDF gönderildikten sonra sözleşme listesine yönlendir
            # return response # Eğer hemen indirme isteniyorsa bu satır kalır
            return redirect(url_for('list_contracts')) # Kayıttan sonra listeye yönlendir

        # --- Hata Yönetimi ---
        except ValueError as ve:
             if not get_flashed_messages(category_filter=["error"]):
                 flash(f"Form verilerinde hata: {ve}. Lütfen girdileri kontrol edin.", "error")
             print(f"Value Error: {ve}")
        except sqlite3.Error as dbe:
            flash(f"Veritabanı hatası: {dbe}", "error")
            print(f"DB Error: {dbe}")
        except ImportError as ie:
             flash(f"PDF oluşturma hatası: {ie}. 'reportlab' kütüphanesinin kurulu olduğundan emin olun.", "error")
             print(f"Import Error: {ie}")
        except RuntimeError as re:
             flash(f"PDF oluşturulurken hata oluştu: {re}", "error")
             print(f"Runtime Error (PDF Generation): {re}")
        except Exception as e:
            flash(f"Beklenmedik bir hata oluştu: {e}", "error")
            print(f"Unexpected Error: {e}")
            import traceback
            traceback.print_exc()

        # Hata durumunda formu tekrar göster
        return render_template('create_contract.html', page_title="Sözleşme Oluştur",
                               properties=properties, customers=customers, personnel=personnel,
                               form_data=form_data_on_error,
                               today_date=datetime.now().strftime('%Y-%m-%d'))

    # GET isteği
    today_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('create_contract.html', page_title="Sözleşme Oluştur",
                           properties=properties, customers=customers, personnel=personnel,
                           today_date=today_date, form_data=None)


# YENİ: Sözleşme Listeleme Rotası (PDF indirme linki için güncellendi)
@app.route('/contracts')
def list_contracts():
    db = get_db()
    cursor = db.cursor()
    contracts = []
    try:
        # pdf_data'yı listelemeye gerek yok, sadece varlığını kontrol edebiliriz (pdf_filename yeterli)
        query = """
            SELECT
                c.id, c.contract_type, c.contract_date, c.start_date, c.end_date, c.price,
                c.pdf_filename, -- PDF dosya adını al
                p.id as property_id, p.title as property_title,
                cust.id as customer_id, cust.name as customer_name,
                o.id as owner_id, o.name as owner_name,
                pers.id as personnel_id, pers.name as personnel_name
            FROM contracts c
            JOIN properties p ON c.property_id = p.id
            JOIN customers cust ON c.customer_id = cust.id
            LEFT JOIN owners o ON c.owner_id = o.id
            LEFT JOIN personnel pers ON c.personnel_id = pers.id
            ORDER BY c.contract_date DESC, c.id DESC
        """
        cursor.execute(query)
        contracts = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f"Sözleşmeleri listelerken veritabanı hatası: {e}", "error")

    return render_template('contracts.html', contracts=contracts, page_title="Sözleşmeler")

# YENİ: Kayıtlı Sözleşme PDF'ini İndirme Rotası
@app.route('/download_contract_pdf/<int:contract_id>')
def download_contract_pdf(contract_id):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT pdf_data, pdf_filename FROM contracts WHERE id = ?", (contract_id,))
        contract_pdf = cursor.fetchone()

        if contract_pdf and contract_pdf['pdf_data']:
            pdf_data = contract_pdf['pdf_data']
            # Dosya adı veritabanında kayıtlı değilse veya boşsa varsayılan bir ad kullan
            filename = contract_pdf['pdf_filename'] or f"sozlesme_{contract_id}.pdf"

            response = make_response(pdf_data)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        else:
            flash(f"ID {contract_id} olan sözleşme için PDF bulunamadı.", "error")
            # return redirect(url_for('list_contracts')) # Listeye yönlendirme
            abort(404, description="Sözleşme PDF'i bulunamadı.") # Veya 404 hatası ver

    except sqlite3.Error as e:
        flash(f"PDF indirilirken veritabanı hatası oluştu: {e}", "error")
        return redirect(url_for('list_contracts'))
    except Exception as e:
        flash(f"PDF indirilirken beklenmedik bir hata oluştu: {e}", "error")
        return redirect(url_for('list_contracts'))


# YENİ: Sözleşme Silme Rotası
@app.route('/delete_contract/<int:contract_id>', methods=['POST'])
def delete_contract(contract_id):
    db = get_db()
    cursor = db.cursor()
    try:
        # Silmeden önce emlak durumunu geri alma (opsiyonel, önceki kodda yorumluydu)
        # ... (gerekirse buraya eklenebilir)

        cursor.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
        db.commit()
        flash(f"ID {contract_id} olan sözleşme başarıyla silindi.", "success")
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error (Delete Contract): {e}")
        flash(f"Sözleşme silinirken bir hata oluştu: {e}", 'error')
    return redirect(url_for('list_contracts'))


# --- YENİ: Dummy Veri Ekleme Modülü ---
@app.route('/add_dummy_data', methods=['POST'])
def add_dummy_data():
    if not app.debug:
        flash("Bu işlem sadece geliştirme modunda kullanılabilir.", "error")
        return redirect(url_for('index'))

    db = get_db()
    cursor = db.cursor()
    num_entries = 5
    added_count = {'owners': 0, 'personnel': 0, 'customers': 0, 'properties': 0, 'contracts': 0}

    try:
        # 1. Örnek Sahipler
        owners_data = []
        for i in range(num_entries):
            unique_suffix = random.randint(1000, 9999)
            name = f"Sahip {chr(65+i)}{unique_suffix}"
            phone = f"555000{unique_suffix}"
            email = f"sahip{unique_suffix}@ornek.com"
            owners_data.append((name, phone, email, f"{name} için notlar."))

        owner_ids = []
        for owner in owners_data:
            try:
                cursor.execute("INSERT INTO owners (name, phone, email, notes) VALUES (?, ?, ?, ?)", owner)
                owner_ids.append(cursor.lastrowid)
                added_count['owners'] += 1
            except sqlite3.IntegrityError:
                cursor.execute("SELECT id FROM owners WHERE phone = ? OR email = ?", (owner[1], owner[2]))
                existing_owner = cursor.fetchone(); owner_ids.append(existing_owner['id'] if existing_owner else None)

        # 2. Örnek Personel
        personnel_data = []
        positions = ["Emlak Danışmanı", "Yönetici Asistanı", "Pazarlama Uzmanı", "Muhasebe"]
        for i in range(num_entries):
             unique_suffix = random.randint(1000, 9999)
             name = f"Personel {chr(70+i)}{unique_suffix}"
             phone = f"555111{unique_suffix}"
             email = f"personel{unique_suffix}@sirket.com"
             position = random.choice(positions)
             hire_date = (datetime.now() - timedelta(days=random.randint(30, 1800))).date()
             personnel_data.append((name, position, phone, email, hire_date, True, f"{name} hakkında not."))

        personnel_ids = []
        for person in personnel_data:
             try:
                 cursor.execute("INSERT INTO personnel (name, position, phone, email, hire_date, is_active, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", person)
                 personnel_ids.append(cursor.lastrowid)
                 added_count['personnel'] += 1
             except sqlite3.IntegrityError:
                 cursor.execute("SELECT id FROM personnel WHERE phone = ? OR email = ?", (person[2], person[3]))
                 existing_personnel = cursor.fetchone(); personnel_ids.append(existing_personnel['id'] if existing_personnel else None)

        # 3. Örnek Müşteriler
        customer_data = []
        types = ["Alıcı", "Kiracı", "Potansiyel", "Satıcı", "Diğer"]
        for i in range(num_entries * 2):
             unique_suffix = random.randint(10000, 99999)
             name = f"Müşteri {chr(80+i)}{unique_suffix}"
             phone = f"555222{unique_suffix}"
             email = f"musteri{unique_suffix}@mail.net"
             cust_type = random.choice(types)
             is_archived = 1 if random.random() < 0.1 else 0
             customer_data.append((name, phone, email, cust_type, f"{name} için tercihler.", is_archived))

        customer_ids = []
        for customer in customer_data:
            try:
                cursor.execute("INSERT INTO customers (name, phone, email, customer_type, notes, is_archived) VALUES (?, ?, ?, ?, ?, ?)", customer)
                customer_ids.append(cursor.lastrowid)
                added_count['customers'] += 1
            except sqlite3.IntegrityError:
                cursor.execute("SELECT id FROM customers WHERE phone = ? OR email = ?", (customer[1], customer[2]))
                existing_customer = cursor.fetchone(); customer_ids.append(existing_customer['id'] if existing_customer else None)

        # 4. Örnek Emlaklar
        properties_data = []
        prop_types = ["Daire", "Villa", "İş Yeri", "Arsa", "Müstakil Ev", "Rezidans", "Yazlık"]
        statuses = ["Satılık", "Kiralık"]
        cities = ["Ankara", "İstanbul", "İzmir", "Bursa", "Antalya", "Adana", "Konya"]
        districts = {
            "Ankara": ["Çankaya", "Keçiören", "Yenimahalle", "Mamak", "Etimesgut", "Gölbaşı"],
            "İstanbul": ["Kadıköy", "Beşiktaş", "Şişli", "Üsküdar", "Bakırköy", "Sarıyer", "Beylikdüzü"],
            "İzmir": ["Konak", "Bornova", "Karşıyaka", "Buca", "Çiğli", "Narlıdere"],
            "Bursa": ["Osmangazi", "Nilüfer", "Yıldırım", "Mudanya", "Gemlik"],
            "Antalya": ["Muratpaşa", "Konyaaltı", "Kepez", "Alanya", "Manavgat", "Kaş"],
            "Adana": ["Seyhan", "Yüreğir", "Çukurova", "Sarıçam"],
            "Konya": ["Selçuklu", "Meram", "Karatay"]
        }
        rooms = ["1+1", "2+1", "3+1", "4+1", "4+2", "5+1", "5+2", "Stüdyo", "6+"]

        valid_owner_ids = [oid for oid in owner_ids if oid is not None]
        property_ids = []

        for i in range(num_entries * 4):
            city = random.choice(cities)
            district = random.choice(districts[city])
            prop_type = random.choice(prop_types)
            status = random.choice(statuses)
            title = f"{district.capitalize()} Merkezde {rooms[i % len(rooms)]} {prop_type} ({status})"
            price = random.randint(5000, 5000000) if status == "Satılık" else random.randint(1500, 35000)
            area = random.randint(40, 350)
            room_count = random.choice(rooms) if prop_type not in ["Arsa", "İş Yeri"] else None
            address = f"{district.capitalize()} Mahallesi, Atatürk Caddesi No:{random.randint(1, 150)}"
            owner_id = random.choice(valid_owner_ids) if valid_owner_ids and random.random() > 0.15 else None

            prop_data = (
                title, f"{title}. Şehrin kalbinde, ulaşımı kolay, {area} m² genişliğinde fırsat!",
                prop_type, status, price, area,
                room_count, address, city, district, owner_id
            )
            try:
                 cursor.execute("""
                    INSERT INTO properties (title, description, property_type, status, price, area, rooms, address, city, district, owner_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", prop_data)
                 property_ids.append(cursor.lastrowid)
                 added_count['properties'] += 1
            except sqlite3.Error as prop_err:
                 print(f"Emlak eklenirken hata: {prop_err} - Veri: {prop_data}")

        # 5. Örnek Sözleşmeler (PDF olmadan) - PDF'li dummy data daha karmaşık olurdu
        valid_property_ids = [pid for pid in property_ids if pid is not None]
        valid_customer_ids = [cid for cid in customer_ids if cid is not None]
        valid_personnel_ids = [pid for pid in personnel_ids if pid is not None]

        if valid_property_ids and valid_customer_ids and valid_personnel_ids:
            num_contracts = min(len(valid_property_ids), len(valid_customer_ids), num_entries * 3)

            cursor.execute(f"SELECT id, owner_id FROM properties WHERE id IN ({','.join('?'*len(valid_property_ids))})", valid_property_ids)
            prop_owner_map = {row['id']: row['owner_id'] for row in cursor.fetchall()}

            for _ in range(num_contracts):
                prop_id = random.choice(valid_property_ids)
                cust_id = random.choice(valid_customer_ids)
                pers_id = random.choice(valid_personnel_ids)
                owner_id = prop_owner_map.get(prop_id)

                cursor.execute("SELECT status, price FROM properties WHERE id = ?", (prop_id,))
                prop_status_info = cursor.fetchone()
                if not prop_status_info or prop_status_info['status'] not in ['Satılık', 'Kiralık']:
                    continue

                contract_type = 'Satış' if prop_status_info['status'] == 'Satılık' else 'Kira'

                if contract_type == 'Satış' and not owner_id:
                    if valid_owner_ids: owner_id = random.choice(valid_owner_ids)
                    else: continue

                contract_date = (datetime.now() - timedelta(days=random.randint(1, 365))).date()
                start_date = (contract_date + timedelta(days=random.randint(1, 15))) if contract_type == 'Kira' else None
                end_date = (start_date + timedelta(days=random.randint(300, 730))) if start_date else None
                price = prop_status_info['price'] * random.uniform(0.95, 1.05) if prop_status_info['price'] else (random.randint(1000, 20000) if contract_type == 'Kira' else random.randint(100000, 3000000))
                notes = f"{contract_type} sözleşmesi için otomatik oluşturulan notlar."
                pdf_filename = f"ornek_{contract_type}_{cust_id}_{prop_id}.pdf" # Örnek dosya adı

                contract_data = (
                    contract_type, prop_id, cust_id, owner_id, pers_id,
                    contract_date, start_date, end_date, price, notes,
                    pdf_filename, None # PDF datası None olarak ekleniyor
                )

                try:
                    cursor.execute('''INSERT INTO contracts
                                      (contract_type, property_id, customer_id, owner_id, personnel_id, contract_date, start_date, end_date, price, notes, pdf_filename, pdf_data)
                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', contract_data)
                    new_status = 'Satıldı' if contract_type == 'Satış' else 'Kiralandı'
                    cursor.execute("UPDATE properties SET status = ? WHERE id = ?", (new_status, prop_id))

                    added_count['contracts'] += 1
                    valid_property_ids.remove(prop_id)

                except sqlite3.Error as contract_err:
                    print(f"Sözleşme eklenirken hata: {contract_err} - Veri: {contract_data}")


        db.commit()
        flash_message = f"Örnek veriler eklendi: {added_count['owners']} Sahip, {added_count['personnel']} Personel, {added_count['customers']} Müşteri, {added_count['properties']} Emlak, {added_count['contracts']} Sözleşme (PDF'siz)."
        flash(flash_message, "success")
        print(flash_message)

    except sqlite3.Error as e:
        db.rollback()
        error_msg = f"Örnek veri eklenirken bir veritabanı hatası oluştu: {e}"
        print(f"Dummy veri eklenirken DB hatası: {e}")
        flash(error_msg, "error")
    except Exception as e:
        db.rollback()
        error_msg = f"Örnek veri eklenirken beklenmedik bir hata oluştu: {e}"
        print(f"Dummy veri eklenirken genel hata: {e}")
        import traceback
        traceback.print_exc()
        flash(error_msg, "error")

    return redirect(url_for('index'))


# --- Uygulamayı Başlatma ---
if __name__ == '__main__':
    print("Uygulama başlatılıyor...")
    init_db()
    app.run(debug=is_debug_mode, host='0.0.0.0')
