# app.py - Ana Flask Uygulaması Dosyası (Tüm Modüller Dahil)

from flask import Flask, render_template, request, redirect, url_for, g, flash, abort, make_response, get_flashed_messages
import sqlite3
import os
from datetime import datetime, timedelta, date # date eklendi
import io
import random
import re # Dosya adı temizleme ve not temizleme için eklendi
from werkzeug.utils import secure_filename # PDF indirme için dosya adı güvenliği

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
         print(f"Uyarı: Türkçe karakterler için '{font_path}' yoluyla özel font yüklenemedi. Standart font ({FONT_NAME}) kullanılacak. PDF'te Türkçe karakter sorunları yaşanabilir.")
except ImportError:
    print("HATA: reportlab kütüphanesi bulunamadı. Lütfen 'pip install reportlab' ile kurun.")
    SimpleDocTemplate = None # PDF fonksiyonları kullanılamayacak
except Exception as font_error:
    print(f"Uyarı: Font yüklenirken hata oluştu: {font_error}. Standart font ({FONT_NAME}) kullanılacak.")


# --- Uygulama Kurulumu ---
app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'emlak.db')
app.config['SECRET_KEY'] = 'cokgizlibir_anahtar_12345' # Canlı ortamda değiştirin ve güvenli tutun
# Debug modunu buradan ayarlayabilirsiniz (True ise örnek veri butonu görünür)
# Geliştirme sırasında True, canlıda False yapın
is_debug_mode = True # True veya False olarak ayarlayın
app.config['DEBUG'] = is_debug_mode

# --- YENİ: Prim Oranları (Ayarlanabilir) ---
COMMISSION_RATES = {
    'Satış': 0.02,  # Satış bedelinin %2'si
    'Kira': 0.10,   # İlk ay kira bedelinin %10'u
    'Diğer': 0.01   # Diğer sözleşme bedelinin %1'i
}


# --- Veritabanı İşlemleri ---

def get_db():
    """İstek başına veritabanı bağlantısı alır veya oluşturur."""
    db = getattr(g, '_database', None)
    if db is None:
        try:
            db = g._database = sqlite3.connect(DATABASE)
            db.row_factory = sqlite3.Row # Sonuçları sözlük gibi erişilebilir yapar
            db.execute("PRAGMA foreign_keys = ON") # Yabancı anahtar kısıtlamalarını etkinleştir
            print("Veritabanı bağlantısı başarıyla açıldı.")
        except sqlite3.Error as e:
            print(f"Veritabanı bağlantı hatası: {e}")
            # Hata durumunda None döndürmek yerine uygulamayı durdurmak daha güvenli olabilir
            # veya özel bir hata sayfası gösterilebilir.
            abort(500, description=f"Veritabanına bağlanılamıyor: {e}")
    return db

@app.teardown_appcontext
def close_connection(exception):
    """İstek sonunda veritabanı bağlantısını kapatır."""
    db = getattr(g, '_database', None)
    if db is not None:
        try:
            db.close()
            print("Veritabanı bağlantısı kapatıldı.")
        except sqlite3.Error as e:
            print(f"Veritabanı kapatma hatası: {e}")

def init_db():
    """Veritabanı tablolarını (eğer yoksa) oluşturur veya günceller."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        print("Veritabanı tabloları oluşturuluyor/güncelleniyor...")

        # Danışmanlar Tablosu (agents - Şu an aktif kullanılmıyor ama kalabilir)
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
                status TEXT NOT NULL, -- Satılık, Kiralık, Satıldı, Kiralandı etc.
                price REAL,
                area REAL, -- m²
                rooms TEXT, -- Örn: 3+1, 2+1
                address TEXT,
                city TEXT,
                district TEXT,
                agent_id INTEGER, -- Bu alan kullanılmıyor gibi, kaldırılabilir veya personel_id ile değiştirilebilir
                owner_id INTEGER, -- Emlak sahibine referans
                date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agents (id) ON DELETE SET NULL,
                FOREIGN KEY (owner_id) REFERENCES owners (id) ON DELETE SET NULL -- Sahip silinirse NULL yap
            )
        ''')
        print("- properties tablosu kontrol edildi.")
        # owner_id sütununu eklemeyi dene (zaten varsa hata vermez)
        try:
            cursor.execute("ALTER TABLE properties ADD COLUMN owner_id INTEGER REFERENCES owners(id) ON DELETE SET NULL")
            print("  - 'owner_id' sütunu properties tablosuna eklendi (gerekliyse).")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e) or "already exists" in str(e):
                print("  - 'owner_id' sütunu properties tablosunda zaten mevcut.")
            else:
                # Beklenmedik bir hata varsa yükselt
                raise e

        # Müşteriler Tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT UNIQUE, -- Telefon numarası benzersiz olmalı
                email TEXT UNIQUE, -- E-posta adresi benzersiz olmalı
                customer_type TEXT, -- Alıcı, Satıcı, Kiracı, Potansiyel etc.
                notes TEXT,
                is_archived INTEGER DEFAULT 0, -- 0: Aktif, 1: Arşivlenmiş
                date_registered DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("- customers tablosu kontrol edildi.")
        # is_archived sütununu eklemeyi dene
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
                position TEXT, -- Pozisyonu (Danışman, Yönetici vb.)
                phone TEXT UNIQUE,
                email TEXT UNIQUE,
                hire_date DATE, -- İşe giriş tarihi
                is_active BOOLEAN DEFAULT 1, -- Aktif mi? (0: Pasif, 1: Aktif)
                notes TEXT,
                salary REAL, -- Maaş bilgisi (opsiyonel)
                date_added DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("- personnel tablosu kontrol edildi.")
        # salary sütununu eklemeyi dene
        try:
            cursor.execute("ALTER TABLE personnel ADD COLUMN salary REAL")
            print("  - 'salary' sütunu personnel tablosuna eklendi (gerekliyse).")
        except sqlite3.OperationalError as e:
             if "duplicate column name" in str(e) or "already exists" in str(e):
                 print("  - 'salary' sütunu personnel tablosunda zaten mevcut.")
             elif "no such table: personnel" not in str(e): # Tablo yoksa hata verme
                 pass
             else:
                 raise e

        # Sözleşmeler Tablosu (pdf_filename ve pdf_data eklendi/güncellendi)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_type TEXT NOT NULL, -- Kira, Satış, Diğer
                property_id INTEGER NOT NULL,
                customer_id INTEGER NOT NULL,
                owner_id INTEGER, -- Satış/Kira veren sahip (opsiyonel olabilir)
                personnel_id INTEGER, -- Sözleşmeyi hazırlayan personel
                contract_date DATE NOT NULL, -- Sözleşmenin imzalandığı tarih
                start_date DATE, -- Kira başlangıç tarihi
                end_date DATE, -- Kira bitiş tarihi
                price REAL, -- Satış bedeli veya aylık kira bedeli
                notes TEXT, -- Ek notlar, özel şartlar
                pdf_filename TEXT, -- Oluşturulan PDF dosyasının adı
                pdf_data BLOB,     -- PDF içeriğinin binary verisi
                date_created DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties (id) ON DELETE CASCADE, -- Emlak silinirse sözleşme de silinir
                FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE, -- Müşteri silinirse sözleşme de silinir
                FOREIGN KEY (owner_id) REFERENCES owners (id) ON DELETE SET NULL, -- Sahip silinirse sözleşmedeki sahip null olur
                FOREIGN KEY (personnel_id) REFERENCES personnel (id) ON DELETE SET NULL -- Personel silinirse sorumlu null olur
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
            elif "no such table: contracts" not in str(e): pass # Tablo yoksa hata verme
            else: raise e
        try:
            cursor.execute("ALTER TABLE contracts ADD COLUMN pdf_data BLOB")
            print("  - 'pdf_data' sütunu contracts tablosuna eklendi (gerekliyse).")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e) or "already exists" in str(e):
                print("  - 'pdf_data' sütunu contracts tablosunda zaten mevcut.")
            elif "no such table: contracts" not in str(e): pass # Tablo yoksa hata verme
            else: raise e

        db.commit() # Değişiklikleri kaydet
        print("Veritabanı başarıyla başlatıldı/güncellendi.")


# --- Yardımcı Fonksiyonlar ---
def get_distinct_values(table_name, column_name):
    """Belirtilen tablodaki belirli bir sütunun benzersiz, boş olmayan değerlerini alır."""
    db = get_db()
    cursor = db.cursor()
    try:
        # Güvenlik: Tablo ve sütun adlarını doğrudan SQL'e eklemek yerine kontrol etmek daha iyi olabilir,
        # ancak bu durumda sadece kod içinden çağrıldığı için kabul edilebilir.
        cursor.execute(f"SELECT DISTINCT {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL AND {column_name} != '' ORDER BY {column_name}")
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Hata: get_distinct_values({table_name}, {column_name}) - {e}")
        return [] # Hata durumunda boş liste döndür

def format_datetime(value, format='%d.%m.%Y %H:%M'):
    """SQLite tarih/saat string'ini veya datetime objesini belirtilen formata çevirir."""
    if value is None: return "-"
    try:
        dt_object = None
        if isinstance(value, datetime):
            dt_object = value
        else:
            # Farklı olası veritabanı formatlarını dene
            possible_formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d']
            for fmt in possible_formats:
                try:
                    dt_object = datetime.strptime(str(value), fmt)
                    break # İlk eşleşen formatta döngüden çık
                except ValueError:
                    continue # Eşleşmezse sonraki formatı dene
            if dt_object is None:
                # Hiçbir format uymadıysa, orijinal değeri döndür (veya hata logla)
                print(f"format_datetime: Bilinmeyen format '{value}'")
                return str(value)
        return dt_object.strftime(format)
    except (ValueError, TypeError, AttributeError) as e:
        # Hata durumunda logla ve orijinal değeri döndür
        print(f"format_datetime hatası: {e} - Değer: {value}")
        return str(value)

def format_date(value, format='%d.%m.%Y'):
    """SQLite tarih string'ini veya date/datetime objesini belirtilen formata çevirir."""
    if value is None: return "-"
    try:
        dt_object = None
        if isinstance(value, datetime):
             dt_object = value.date() # Sadece tarih kısmını al
        elif isinstance(value, date): # date objesi mi kontrol et (datetime'dan önce)
             dt_object = value
        else:
            # Farklı olası veritabanı formatlarını dene
            possible_formats = ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']
            parsed_date = None
            for fmt in possible_formats:
                try:
                    # Önce datetime olarak parse et, sonra date kısmını al
                    parsed_date = datetime.strptime(str(value), fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_date is None:
                 print(f"format_date: Bilinmeyen format '{value}'")
                 return str(value)
            dt_object = parsed_date

        return dt_object.strftime(format)
    except (ValueError, TypeError, AttributeError) as e:
        print(f"format_date hatası: {e} - Değer: {value}")
        return str(value)

def format_currency(value):
    """Sayısal değeri Türkçe para formatına çevirir."""
    if value is None:
        return "-"
    try:
        # Güvenli float dönüşümü ve Türkçe formatlama
        # Önce string'e çevirip boşlukları temizle
        value_str = str(value).strip()
        # Eğer boşsa 0 kabul et
        if not value_str:
            value_float = 0.0
        else:
             # Binlik ayıracı (nokta) kaldır, ondalık ayıracı (virgül) noktaya çevir
             value_str = value_str.replace('.', '').replace(',', '.')
             value_float = float(value_str)

        # Türkçe format: binlik ayıracı nokta, ondalık ayıracı virgül
        return f"{value_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + " TL"
    except (ValueError, TypeError) as e:
        print(f"format_currency hatası: {e} - Değer: {value}")
        return str(value) # Hata durumunda orijinal değeri döndür


# Jinja filtrelerini ve context işlemcisini ekle
app.jinja_env.filters['datetimeformat'] = format_datetime
app.jinja_env.filters['dateformat'] = format_date
app.jinja_env.filters['currencyformat'] = format_currency
@app.context_processor
def inject_now():
    """Şimdiki zamanı tüm şablonlara gönderir."""
    return {'now': datetime.now()}

# --- Veri Listeleme Fonksiyonları (Select Box'lar için) ---
def get_properties_list():
    """Sözleşme oluşturma formu için uygun emlakları listeler."""
    db = get_db()
    cursor = db.cursor()
    try:
        # Sadece 'Satılık' veya 'Kiralık' durumundaki emlakları getir
        cursor.execute("SELECT id, title, city, district, status FROM properties WHERE status IN ('Satılık', 'Kiralık') ORDER BY title")
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Hata: get_properties_list - {e}")
        flash(f"Emlak listesi alınırken hata: {e}", "error")
        return []

def get_customers_list():
    """Sözleşme oluşturma formu için aktif müşterileri listeler."""
    db = get_db()
    cursor = db.cursor()
    try:
        # Sadece arşivlenmemiş (aktif) müşterileri getir
        cursor.execute("SELECT id, name, phone FROM customers WHERE is_archived = 0 ORDER BY name")
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Hata: get_customers_list - {e}")
        flash(f"Müşteri listesi alınırken hata: {e}", "error")
        return []

def get_owners_list():
    """Emlak ekleme/düzenleme formu için sahipleri listeler."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, name FROM owners ORDER BY name")
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Hata: get_owners_list - {e}")
        flash(f"Sahip listesi alınırken hata: {e}", "error")
        return []

def get_personnel_list():
    """Sözleşme oluşturma formu için aktif personeli listeler."""
    db = get_db()
    cursor = db.cursor()
    try:
        # Sadece aktif personeli getir
        cursor.execute("SELECT id, name, position FROM personnel WHERE is_active = 1 ORDER BY name")
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Hata: get_personnel_list - {e}")
        flash(f"Personel listesi alınırken hata: {e}", "error")
        return []


# --- Genel Route ---
@app.route('/')
def index():
    """Ana sayfayı gösterir."""
    return render_template('index.html', page_title="Ana Sayfa")

# --- Emlak Modülü Routes ---
@app.route('/properties')
def list_properties():
    """Emlakları filtreleme ve listeleme sayfası."""
    db = get_db()
    cursor = db.cursor()

    # Filtre parametrelerini al (varsayılan değerlerle)
    filters = {
        'city': request.args.get('city', default='', type=str),
        'district': request.args.get('district', default='', type=str),
        'property_type': request.args.get('property_type', default='', type=str),
        'status': request.args.get('status', default='', type=str),
        'rooms': request.args.get('rooms', default='', type=str),
        'min_price': request.args.get('min_price', default=None, type=float),
        'max_price': request.args.get('max_price', default=None, type=float),
        'owner_id': request.args.get('owner_id', default=None, type=int) # Sahip filtresi eklendi
    }

    # Temel SQL sorgusu
    query = """
        SELECT p.id, p.title, p.property_type, p.status, p.price, p.city, p.district, p.rooms, o.name as owner_name
        FROM properties p
        LEFT JOIN owners o ON p.owner_id = o.id
    """
    where_clauses = []
    params = []

    # Filtreleri WHERE koşullarına ekle
    if filters['city']:
        where_clauses.append("LOWER(p.city) LIKE LOWER(?)")
        params.append(f"%{filters['city']}%")
    if filters['district']:
        where_clauses.append("LOWER(p.district) LIKE LOWER(?)")
        params.append(f"%{filters['district']}%")
    if filters['property_type']:
        where_clauses.append("p.property_type = ?")
        params.append(filters['property_type'])
    if filters['status']:
        where_clauses.append("p.status = ?")
        params.append(filters['status'])
    if filters['rooms']:
        where_clauses.append("p.rooms = ?")
        params.append(filters['rooms'])
    if filters['min_price'] is not None:
        where_clauses.append("p.price >= ?")
        params.append(filters['min_price'])
    if filters['max_price'] is not None:
        where_clauses.append("p.price <= ?")
        params.append(filters['max_price'])
    if filters['owner_id'] is not None:
        where_clauses.append("p.owner_id = ?")
        params.append(filters['owner_id'])

    # WHERE koşullarını sorguya ekle
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " ORDER BY p.date_added DESC" # En son eklenenler üste gelsin

    properties = []
    try:
        cursor.execute(query, params)
        properties = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f"Emlakları listelerken veritabanı hatası: {e}", "error")

    # Filtreleme seçenekleri için benzersiz değerleri al
    distinct_values = {
        'distinct_citys': get_distinct_values('properties', 'city'),
        'distinct_districts': get_distinct_values('properties', 'district'),
        'distinct_property_types': get_distinct_values('properties', 'property_type'),
        'distinct_statuses': get_distinct_values('properties', 'status'),
        'distinct_rooms': get_distinct_values('properties', 'rooms'),
        'all_owners': get_owners_list() # Sahip filtresi için
    }

    return render_template('properties.html', properties=properties, page_title="Emlaklar",
                           filters=filters, **distinct_values)

@app.route('/add_property', methods=['GET', 'POST'])
def add_property():
     """Yeni emlak ekleme sayfası."""
     owners = get_owners_list() # Sahip seçimi için
     form_data = {} # Hata durumunda formu tekrar doldurmak için

     if request.method == 'POST':
         form_data = request.form.to_dict() # Form verilerini al
         db = get_db()
         cursor = db.cursor()
         try:
            # Zorunlu alan kontrolü
            required_fields = ['title', 'property_type', 'status', 'city', 'district']
            if not all(form_data.get(field) for field in required_fields):
                flash('İlan Başlığı, Emlak Tipi, Durum, Şehir ve İlçe alanları zorunludur.', 'error')
                # Hata durumunda formu tekrar render et, girilen veriler kaybolmasın
                return render_template('add_property.html', page_title="Yeni Emlak Ekle", form_data=form_data, owners=owners)

            # Fiyat ve Alan için güvenli dönüşüm
            price_str = form_data.get('price', '').strip().replace('.', '').replace(',', '.')
            price = float(price_str) if price_str else None
            area_str = form_data.get('area', '').strip().replace(',', '.')
            area = float(area_str) if area_str else None
            owner_id = int(form_data['owner_id']) if form_data.get('owner_id') else None

            # Veritabanına ekle
            cursor.execute('''INSERT INTO properties
                              (title, description, property_type, status, price, area, rooms, address, city, district, owner_id)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                           (form_data['title'], form_data.get('description'), form_data['property_type'], form_data['status'],
                            price, area, form_data.get('rooms'), form_data.get('address'),
                            form_data['city'], form_data['district'], owner_id))
            db.commit()
            flash('Emlak başarıyla eklendi!', 'success')
            return redirect(url_for('list_properties')) # Emlak listesine yönlendir

         except sqlite3.Error as e:
            db.rollback() # Hata olursa işlemi geri al
            print(f"DB Error (Add Property): {e}")
            flash(f'Emlak eklenirken bir veritabanı hatası oluştu: {e}', 'error')
         except ValueError:
            flash('Fiyat ve Alan sayısal değer olmalıdır (örn: 1500,50 veya 1500). Lütfen kontrol edin.', 'error')

         # Hata durumunda formu tekrar render et
         return render_template('add_property.html', page_title="Yeni Emlak Ekle", form_data=form_data, owners=owners)

     # GET isteği için boş formu göster
     return render_template('add_property.html', page_title="Yeni Emlak Ekle", owners=owners, form_data=None)

@app.route('/edit_property/<int:property_id>', methods=['GET', 'POST'])
def edit_property(property_id):
    """Mevcut bir emlağı düzenleme sayfası."""
    owners = get_owners_list() # Sahip seçimi için
    db = get_db()
    cursor = db.cursor()
    property_data = None

    # Önce emlak verisini çek
    try:
        cursor.execute("SELECT * FROM properties WHERE id = ?", (property_id,))
        property_data = cursor.fetchone()
    except sqlite3.Error as e:
        flash(f"Emlak bilgileri alınırken hata: {e}", "error")
        return redirect(url_for('list_properties'))

    # Emlak bulunamazsa 404 hatası ver
    if property_data is None:
        abort(404, description=f"ID {property_id} olan emlak bulunamadı.")

    if request.method == 'POST':
        form_data = request.form.to_dict() # Form verilerini al
        try:
            # Zorunlu alan kontrolü
            required_fields = ['title', 'property_type', 'status', 'city', 'district']
            if not all(form_data.get(field) for field in required_fields):
                flash('İlan Başlığı, Emlak Tipi, Durum, Şehir ve İlçe alanları zorunludur.', 'error')
                # Hata durumunda formu mevcut veriler + form verileriyle tekrar göster
                current_data = dict(property_data)
                current_data.update(form_data)
                return render_template('edit_property.html', page_title="Emlak Düzenle", property=current_data, owners=owners)

            # Fiyat ve Alan için güvenli dönüşüm
            price_str = form_data.get('price', '').strip().replace('.', '').replace(',', '.')
            price = float(price_str) if price_str else None
            area_str = form_data.get('area', '').strip().replace(',', '.')
            area = float(area_str) if area_str else None
            owner_id = int(form_data['owner_id']) if form_data.get('owner_id') else None

            # Veritabanını güncelle
            cursor.execute('''UPDATE properties SET
                              title=?, description=?, property_type=?, status=?, price=?, area=?, rooms=?, address=?, city=?, district=?, owner_id=?
                              WHERE id=?''',
                           (form_data['title'], form_data.get('description'), form_data['property_type'], form_data['status'],
                            price, area, form_data.get('rooms'), form_data.get('address'),
                            form_data['city'], form_data['district'], owner_id, property_id))
            db.commit()
            flash('Emlak başarıyla güncellendi!', 'success')
            return redirect(url_for('list_properties')) # Emlak listesine yönlendir

        except sqlite3.Error as e:
            db.rollback() # Hata olursa işlemi geri al
            print(f"DB Error (Edit Property): {e}")
            flash(f'Emlak güncellenirken hata: {e}', 'error')
        except ValueError:
            flash('Fiyat ve Alan sayısal değer olmalıdır (örn: 1500,50 veya 1500). Lütfen kontrol edin.', 'error')

        # Hata durumunda formu tekrar render et
        current_data = dict(property_data)
        current_data.update(form_data) # Formdaki değişiklikleri uygula
        return render_template('edit_property.html', page_title="Emlak Düzenle", property=current_data, owners=owners)

    # GET isteği için emlak verileriyle dolu formu göster
    return render_template('edit_property.html', page_title="Emlak Düzenle", property=property_data, owners=owners)

@app.route('/delete_property/<int:property_id>', methods=['POST'])
def delete_property(property_id):
     """Bir emlağı siler."""
     db = get_db()
     cursor = db.cursor()
     try:
         # Emlak silinmeden önce ilişkili sözleşmelerin ne olacağına karar verilmeli.
         # Şu anki FOREIGN KEY tanımı (ON DELETE CASCADE) emlak silinince sözleşmeleri de siler.
         # Eğer sözleşmelerin kalması isteniyorsa, FOREIGN KEY tanımı değiştirilmeli
         # veya silmeden önce sözleşmelerdeki property_id null yapılmalı.
         # Şimdilik CASCADE varsayımıyla devam ediyoruz.

         cursor.execute("DELETE FROM properties WHERE id = ?", (property_id,))
         db.commit()
         flash(f"ID {property_id} olan emlak başarıyla silindi.", "success")
     except sqlite3.Error as e:
         db.rollback()
         print(f"DB Error (Delete Property): {e}")
         flash(f"Emlak silinirken bir hata oluştu: {e}", 'error')
     return redirect(url_for('list_properties')) # Emlak listesine yönlendir

# --- Müşteri (CRM) Modülü Routes ---
@app.route('/customers')
def list_customers():
    """Aktif müşterileri listeleme sayfası."""
    db = get_db()
    cursor = db.cursor()
    customers = []
    try:
        # Sadece arşivlenmemiş (is_archived = 0) müşterileri seç
        cursor.execute("SELECT id, name, phone, email, customer_type, notes, date_registered FROM customers WHERE is_archived = 0 ORDER BY date_registered DESC")
        customers = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f"Müşterileri listelerken hata: {e}", "error")
    return render_template('customers.html', customers=customers, page_title="Aktif Müşteriler")

@app.route('/archived_customers')
def list_archived_customers():
    """Arşivlenmiş müşterileri listeleme sayfası."""
    db = get_db()
    cursor = db.cursor()
    customers = []
    try:
        # Sadece arşivlenmiş (is_archived = 1) müşterileri seç
        cursor.execute("SELECT id, name, phone, email, customer_type, notes, date_registered FROM customers WHERE is_archived = 1 ORDER BY date_registered DESC")
        customers = cursor.fetchall()
    except sqlite3.Error as e:
        flash(f"Arşivlenmiş müşterileri listelerken hata: {e}", "error")
    return render_template('archived_customers.html', customers=customers, page_title="Arşivlenmiş Müşteriler")

@app.route('/add_customer', methods=['GET', 'POST'])
def add_customer():
    """Yeni müşteri ekleme sayfası."""
    form_data = {} # Hata durumunda formu doldurmak için
    if request.method == 'POST':
        form_data = request.form.to_dict()
        db = get_db()
        cursor = db.cursor()
        try:
            # Zorunlu alan kontrolü
            if not form_data.get('name') or not form_data.get('customer_type'):
                 flash('Ad Soyadı ve Müşteri Tipi alanları zorunludur.', 'error')
                 return render_template('add_customer.html', page_title="Yeni Müşteri Ekle", form_data=form_data)

            # Boşsa None ata (veritabanında NULL olması için)
            phone = form_data.get('phone').strip() or None
            email = form_data.get('email').strip() or None

            cursor.execute('''INSERT INTO customers (name, phone, email, customer_type, notes, is_archived)
                              VALUES (?, ?, ?, ?, ?, 0)''', # Yeni müşteri her zaman aktif başlar
                           (form_data['name'], phone, email, form_data['customer_type'], form_data.get('notes')))
            db.commit()
            flash('Müşteri başarıyla eklendi!', 'success')
            return redirect(url_for('list_customers')) # Aktif müşteri listesine yönlendir

        except sqlite3.IntegrityError as e:
            db.rollback() # Benzersizlik hatası (UNIQUE constraint)
            error_msg = "Bu telefon numarası veya e-posta adresi zaten kayıtlı." if "UNIQUE constraint failed" in str(e) else f"Veritabanı bütünlük hatası: {e}"
            flash(error_msg, 'error')
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Müşteri eklenirken bir veritabanı hatası oluştu: {e}', 'error')

        # Hata durumunda formu tekrar render et
        return render_template('add_customer.html', page_title="Yeni Müşteri Ekle", form_data=form_data)

    # GET isteği için boş formu göster
    return render_template('add_customer.html', page_title="Yeni Müşteri Ekle", form_data=None)

@app.route('/edit_customer/<int:customer_id>', methods=['GET', 'POST'])
def edit_customer(customer_id):
    """Mevcut bir müşteriyi düzenleme sayfası."""
    db = get_db()
    cursor = db.cursor()
    customer_data = None

    # Müşteri verisini çek
    try:
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        customer_data = cursor.fetchone()
    except sqlite3.Error as e:
         flash(f"Müşteri bilgileri alınırken hata: {e}", "error")
         # Hata durumunda hangi listeye yönlendireceğimizi bilemeyebiliriz, ana sayfaya yönlendirelim
         return redirect(url_for('index'))

    if customer_data is None:
        abort(404, description=f"ID {customer_id} olan müşteri bulunamadı.")

    if request.method == 'POST':
        form_data = request.form.to_dict()
        try:
            # Zorunlu alan kontrolü
            if not form_data.get('name') or not form_data.get('customer_type'):
                 flash('Ad Soyadı ve Müşteri Tipi alanları zorunludur.', 'error')
                 # Mevcut veriler + form verileriyle tekrar göster
                 current_data = dict(customer_data)
                 current_data.update(form_data)
                 return render_template('edit_customer.html', page_title="Müşteri Düzenle", customer=current_data)

            # Boşsa None ata
            phone = form_data.get('phone').strip() or None
            email = form_data.get('email').strip() or None

            cursor.execute('''UPDATE customers SET
                              name=?, phone=?, email=?, customer_type=?, notes=?
                              WHERE id=?''',
                           (form_data['name'], phone, email, form_data['customer_type'], form_data.get('notes'), customer_id))
            db.commit()
            flash('Müşteri başarıyla güncellendi!', 'success')
            # Müşterinin durumuna göre doğru listeye yönlendir
            redirect_url = url_for('list_customers') if not customer_data['is_archived'] else url_for('list_archived_customers')
            return redirect(redirect_url)

        except sqlite3.IntegrityError as e:
            db.rollback()
            error_msg = "Bu telefon numarası veya e-posta adresi zaten başka bir müşteriye ait." if "UNIQUE constraint failed" in str(e) else f"Veritabanı bütünlük hatası: {e}"
            flash(error_msg, 'error')
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Müşteri güncellenirken bir veritabanı hatası oluştu: {e}', 'error')

        # Hata durumunda formu tekrar render et
        current_data = dict(customer_data)
        current_data.update(form_data)
        return render_template('edit_customer.html', page_title="Müşteri Düzenle", customer=current_data)

    # GET isteği için müşteri verileriyle dolu formu göster
    return render_template('edit_customer.html', page_title="Müşteri Düzenle", customer=customer_data)

@app.route('/delete_customer/<int:customer_id>', methods=['POST'])
def delete_customer(customer_id):
    """Bir müşteriyi kalıcı olarak siler."""
    db = get_db()
    cursor = db.cursor()
    is_archived = 0 # Silme sonrası yönlendirme için
    try:
        # Silmeden önce müşterinin arşiv durumunu al
        cursor.execute("SELECT is_archived FROM customers WHERE id = ?", (customer_id,))
        customer = cursor.fetchone()
        if customer:
            is_archived = customer['is_archived']

        # Müşteri silinince ilişkili sözleşmeler de silinir (ON DELETE CASCADE)
        cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        db.commit()
        flash(f"ID {customer_id} olan müşteri başarıyla silindi.", "success")
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error (Delete Customer): {e}")
        flash(f"Müşteri silinirken bir hata oluştu: {e}", 'error')

    # Müşterinin silinmeden önceki durumuna göre doğru listeye yönlendir
    redirect_url = url_for('list_customers') if not is_archived else url_for('list_archived_customers')
    return redirect(redirect_url)


@app.route('/archive_customer/<int:customer_id>', methods=['POST'])
def archive_customer(customer_id):
    """Bir müşteriyi arşivler."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE customers SET is_archived = 1 WHERE id = ?", (customer_id,))
        db.commit()
        flash(f"ID {customer_id} olan müşteri başarıyla arşivlendi.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Müşteri arşivlenirken hata: {e}", "error")
    # Aktif müşteri listesine geri dön
    return redirect(url_for('list_customers'))

@app.route('/unarchive_customer/<int:customer_id>', methods=['POST'])
def unarchive_customer(customer_id):
    """Bir müşteriyi arşivden çıkarır."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE customers SET is_archived = 0 WHERE id = ?", (customer_id,))
        db.commit()
        flash(f"ID {customer_id} olan müşteri başarıyla arşivden çıkarıldı.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Müşteri arşivden çıkarılırken hata: {e}", "error")
    # Arşivlenmiş müşteri listesine geri dön
    return redirect(url_for('list_archived_customers'))


# --- Emlak Sahibi (Owners) Modülü Routes ---
@app.route('/owners')
def list_owners():
    """Emlak sahiplerini listeleme sayfası."""
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
    """Yeni emlak sahibi ekleme sayfası."""
    form_data = {}
    if request.method == 'POST':
        form_data = request.form.to_dict()
        db = get_db()
        cursor = db.cursor()
        try:
            if not form_data.get('name'):
                 flash('Ad Soyadı alanı zorunludur.', 'error')
                 return render_template('add_owner.html', page_title="Yeni Emlak Sahibi Ekle", form_data=form_data)

            phone = form_data.get('phone').strip() or None
            email = form_data.get('email').strip() or None

            cursor.execute("INSERT INTO owners (name, phone, email, notes) VALUES (?, ?, ?, ?)",
                           (form_data['name'], phone, email, form_data.get('notes')))
            db.commit()
            flash('Emlak sahibi başarıyla eklendi!', 'success')
            return redirect(url_for('list_owners'))
        except sqlite3.IntegrityError as e:
            db.rollback()
            error_msg = "Bu telefon numarası veya e-posta adresi zaten kayıtlı." if "UNIQUE constraint failed" in str(e) else f"Veritabanı bütünlük hatası: {e}"
            flash(error_msg, 'error')
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Emlak sahibi eklenirken bir veritabanı hatası oluştu: {e}', 'error')
        return render_template('add_owner.html', page_title="Yeni Emlak Sahibi Ekle", form_data=form_data)
    return render_template('add_owner.html', page_title="Yeni Emlak Sahibi Ekle", form_data=None)

@app.route('/edit_owner/<int:owner_id>', methods=['GET', 'POST'])
def edit_owner(owner_id):
    """Mevcut bir emlak sahibini düzenleme sayfası."""
    db = get_db()
    cursor = db.cursor()
    owner_data = None
    try:
        cursor.execute("SELECT * FROM owners WHERE id = ?", (owner_id,))
        owner_data = cursor.fetchone()
    except sqlite3.Error as e:
        flash(f"Sahip bilgileri alınırken hata: {e}", "error")
        return redirect(url_for('list_owners'))

    if owner_data is None:
        abort(404, description=f"ID {owner_id} olan emlak sahibi bulunamadı.")

    if request.method == 'POST':
        form_data = request.form.to_dict()
        try:
            if not form_data.get('name'):
                 flash('Ad Soyadı alanı zorunludur.', 'error')
                 current_data = dict(owner_data); current_data.update(form_data)
                 return render_template('edit_owner.html', page_title="Emlak Sahibi Düzenle", owner=current_data)

            phone = form_data.get('phone').strip() or None
            email = form_data.get('email').strip() or None

            cursor.execute("UPDATE owners SET name=?, phone=?, email=?, notes=? WHERE id=?",
                           (form_data['name'], phone, email, form_data.get('notes'), owner_id))
            db.commit()
            flash('Emlak sahibi başarıyla güncellendi!', 'success')
            return redirect(url_for('list_owners'))
        except sqlite3.IntegrityError as e:
            db.rollback()
            error_msg = "Bu telefon numarası veya e-posta adresi zaten başka bir sahibe ait." if "UNIQUE constraint failed" in str(e) else f"Veritabanı bütünlük hatası: {e}"
            flash(error_msg, 'error')
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Emlak sahibi güncellenirken bir veritabanı hatası oluştu: {e}', 'error')

        current_data = dict(owner_data); current_data.update(form_data)
        return render_template('edit_owner.html', page_title="Emlak Sahibi Düzenle", owner=current_data)
    return render_template('edit_owner.html', page_title="Emlak Sahibi Düzenle", owner=owner_data)

@app.route('/delete_owner/<int:owner_id>', methods=['POST'])
def delete_owner(owner_id):
    """Bir emlak sahibini siler."""
    db = get_db()
    cursor = db.cursor()
    try:
        # Sahip silinmeden önce, bu sahibe ait emlakların ve sözleşmelerin
        # owner_id alanlarını NULL yap (FOREIGN KEY tanımı ON DELETE SET NULL)
        # Bu işlem otomatik olarak gerçekleşmeli, ancak emin olmak için manuel de yapılabilir:
        # cursor.execute("UPDATE properties SET owner_id = NULL WHERE owner_id = ?", (owner_id,))
        # cursor.execute("UPDATE contracts SET owner_id = NULL WHERE owner_id = ?", (owner_id,))

        # Sonra sahibi sil
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
    """Personel listeleme sayfası."""
    db = get_db()
    cursor = db.cursor()
    personnel_list = []
    try:
        # Aktiflik durumunu da seç
        cursor.execute("SELECT id, name, position, phone, email, hire_date, is_active FROM personnel ORDER BY name")
        personnel_list = cursor.fetchall()
    except sqlite3.Error as e:
         flash(f"Personel listelenirken hata: {e}", "error")
    return render_template('personnel.html', personnel_list=personnel_list, page_title="Personel Listesi")

@app.route('/add_personnel', methods=['GET', 'POST'])
def add_personnel():
    """Yeni personel ekleme sayfası."""
    form_data = {}
    if request.method == 'POST':
        form_data = request.form.to_dict()
        db = get_db()
        cursor = db.cursor()
        try:
            if not form_data.get('name'):
                 flash('Ad Soyadı alanı zorunludur.', 'error')
                 return render_template('add_personnel.html', page_title="Yeni Personel Ekle", form_data=form_data)

            phone = form_data.get('phone').strip() or None
            email = form_data.get('email').strip() or None
            hire_date_str = form_data.get('hire_date')
            # Tarih formatını doğrula ve parse et
            hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d').date() if hire_date_str else None
            # Checkbox değeri: 'on' ise 1, değilse 0
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
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Personel eklenirken bir veritabanı hatası oluştu: {e}', 'error')
        except ValueError:
             # Tarih parse hatası
             flash('İşe giriş tarihi geçersiz formatta (YYYY-AA-GG olmalı).', 'error')
        return render_template('add_personnel.html', page_title="Yeni Personel Ekle", form_data=form_data)
    return render_template('add_personnel.html', page_title="Yeni Personel Ekle", form_data=None)

@app.route('/edit_personnel/<int:personnel_id>', methods=['GET', 'POST'])
def edit_personnel(personnel_id):
    """Mevcut bir personeli düzenleme sayfası."""
    db = get_db()
    cursor = db.cursor()
    personnel_data = None
    try:
        cursor.execute("SELECT * FROM personnel WHERE id = ?", (personnel_id,))
        personnel_data = cursor.fetchone()
    except sqlite3.Error as e:
        flash(f"Personel bilgileri alınırken hata: {e}", "error")
        return redirect(url_for('list_personnel'))

    if personnel_data is None:
        abort(404, description=f"ID {personnel_id} olan personel bulunamadı.")

    if request.method == 'POST':
        form_data = request.form.to_dict()
        try:
            if not form_data.get('name'):
                 flash('Ad Soyadı alanı zorunludur.', 'error')
                 current_data = dict(personnel_data); current_data.update(form_data)
                 return render_template('edit_personnel.html', page_title="Personel Düzenle", personnel=current_data)

            phone = form_data.get('phone').strip() or None
            email = form_data.get('email').strip() or None
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
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Personel güncellenirken bir veritabanı hatası oluştu: {e}', 'error')
        except ValueError:
             flash('İşe giriş tarihi geçersiz formatta (YYYY-AA-GG olmalı).', 'error')

        current_data = dict(personnel_data); current_data.update(form_data)
        # Tarihi tekrar formatlayıp gönderelim ki inputta doğru görünsün
        if current_data.get('hire_date'):
            try:
                 # Tarih objesini string'e çevir
                 current_data['hire_date'] = format_date(current_data['hire_date'], '%Y-%m-%d')
            except: pass # Formatlama hatası olursa eski değeri kalsın
        return render_template('edit_personnel.html', page_title="Personel Düzenle", personnel=current_data)

    # GET isteği: Tarihi input için doğru formatta gönder
    personnel_dict = dict(personnel_data)
    if personnel_dict.get('hire_date'):
         try:
             # Tarih objesini string'e çevir
             personnel_dict['hire_date'] = format_date(personnel_dict['hire_date'], '%Y-%m-%d')
         except: pass # Hata olursa orijinal kalsın

    return render_template('edit_personnel.html', page_title="Personel Düzenle", personnel=personnel_dict)


@app.route('/delete_personnel/<int:personnel_id>', methods=['POST'])
def delete_personnel(personnel_id):
    """Bir personeli siler."""
    db = get_db()
    cursor = db.cursor()
    try:
        # Personel silinmeden önce, bu personele ait sözleşmelerdeki
        # personnel_id alanlarını NULL yap (FOREIGN KEY tanımı ON DELETE SET NULL)
        # cursor.execute("UPDATE contracts SET personnel_id = NULL WHERE personnel_id = ?", (personnel_id,))

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
    """Verilen bilgilere göre PDF sözleşmesi oluşturur ve BytesIO buffer döndürür."""
    if SimpleDocTemplate is None:
        raise ImportError("PDF oluşturma için reportlab kütüphanesi yüklenemedi.")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    # Özel Stiller (FONT_NAME ile) - Türkçe karakter desteği için
    # Daha fazla stil tanımlanabilir (örn: tablo stilleri)
    title_style = ParagraphStyle(name='TitleStyle', parent=styles['h1'], alignment=TA_CENTER, fontName=FONT_NAME, fontSize=16, spaceAfter=20)
    heading_style = ParagraphStyle(name='HeadingStyle', parent=styles['h2'], fontName=FONT_NAME, fontSize=12, spaceBefore=12, spaceAfter=6, textColor='#333366')
    body_style = ParagraphStyle(name='BodyStyle', parent=styles['Normal'], fontName=FONT_NAME, fontSize=10, alignment=TA_JUSTIFY, spaceAfter=6, leading=14)
    info_style = ParagraphStyle(name='InfoStyle', parent=styles['Normal'], fontName=FONT_NAME, fontSize=10, alignment=TA_LEFT, spaceAfter=3, leading=12)
    table_header_style = ParagraphStyle(name='TableHeader', parent=styles['Normal'], fontName=FONT_NAME, fontSize=10, alignment=TA_LEFT, textColor='#555555') # Bold yerine gri renk
    table_cell_style = ParagraphStyle(name='TableCell', parent=styles['Normal'], fontName=FONT_NAME, fontSize=10, alignment=TA_LEFT)
    signature_label_style = ParagraphStyle(name='SignatureLabel', parent=styles['Normal'], fontName=FONT_NAME, fontSize=9, alignment=TA_CENTER, textColor='#666666')

    story = [] # PDF'e eklenecek akış öğeleri

    # --- Sözleşme Başlığı ---
    contract_title_tr = data.get('contract_type', 'Bilinmeyen').upper()
    if contract_title_tr == 'KIRA': contract_title_tr = 'KİRA' # İ harfi düzeltmesi
    story.append(Paragraph(f"<b>{contract_title_tr} SÖZLEŞMESİ</b>", title_style))
    story.append(Spacer(1, 0.5*cm))

    # --- Taraflar ---
    story.append(Paragraph("Taraflar", heading_style))

    owner = data.get('owner', {}) # Sahip bilgisi yoksa boş dict
    customer = data.get('customer', {}) # Müşteri bilgisi
    property_info_pdf = data.get('property', {}) # Emlak bilgisi
    personnel_info_pdf = data.get('personnel', {}) # Personel bilgisi

    owner_name = owner.get('name', '<i>Belirtilmemiş</i>')
    owner_phone = owner.get('phone', '-')
    owner_email = owner.get('email', '-')
    owner_role = "Satıcı" if data.get('contract_type') == 'Satış' else "Kiraya Veren"

    # Taraflar için tablo kullanmak daha düzenli olabilir
    taraflar_data = [
        [Paragraph(f'<b>{owner_role}</b>', table_header_style), Paragraph(owner_name, table_cell_style)],
        [Paragraph('Telefon:', table_header_style), Paragraph(owner_phone, table_cell_style)],
        [Paragraph('E-posta:', table_header_style), Paragraph(owner_email, table_cell_style)],
        [Spacer(1, 0.2*cm), Spacer(1, 0.2*cm)], # Arada boşluk
        [Paragraph(f'<b>{"Alıcı" if data.get("contract_type") == "Satış" else "Kiracı"}</b>', table_header_style), Paragraph(customer.get('name', '<i>Belirtilmemiş</i>'), table_cell_style)],
        [Paragraph('Telefon:', table_header_style), Paragraph(customer.get('phone', '-'), table_cell_style)],
        [Paragraph('E-posta:', table_header_style), Paragraph(customer.get('email', '-'), table_cell_style)],
    ]
    taraflar_table = Table(taraflar_data, colWidths=[3.5*cm, None])
    taraflar_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW', (0,2), (1,2), 0.5, '#cccccc'), # Sahip sonrası çizgi
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(taraflar_table)
    story.append(Spacer(1, 0.6*cm))

    # --- Sözleşme Konusu Emlak ---
    story.append(Paragraph("Sözleşme Konusu Emlak", heading_style))
    prop_address = f"{property_info_pdf.get('address', '')}, {property_info_pdf.get('district', '')} / {property_info_pdf.get('city', '')}".strip(', ').strip()
    emlak_data = [
        [Paragraph('İlan Başlığı:', table_header_style), Paragraph(property_info_pdf.get('title', '-'), table_cell_style)],
        [Paragraph('Emlak Tipi:', table_header_style), Paragraph(property_info_pdf.get('property_type', '-'), table_cell_style)],
        [Paragraph('Adres:', table_header_style), Paragraph(prop_address or '-', table_cell_style)],
        [Paragraph('Alan (m²):', table_header_style), Paragraph(str(property_info_pdf.get('area')) if property_info_pdf.get('area') else '-', table_cell_style)],
        [Paragraph('Oda Sayısı:', table_header_style), Paragraph(property_info_pdf.get('rooms', '-'), table_cell_style)],
    ]
    emlak_table = Table(emlak_data, colWidths=[3.5*cm, None])
    emlak_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
         ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(emlak_table)
    story.append(Spacer(1, 0.6*cm))

    # --- Sözleşme Şartları ---
    story.append(Paragraph("Sözleşme Şartları", heading_style))
    price_formatted = format_currency(data.get('price')) # Fiyatı formatla

    # Sözleşme tipine göre metinleri ayarla
    if data.get('contract_type') == 'Kira':
        story.append(Paragraph(f"İşbu sözleşme, yukarıda bilgileri verilen emlakın <b>{owner_name}</b> (Kiraya Veren) tarafından <b>{customer.get('name', 'Kiracı')}</b>'a (Kiracı) aşağıda belirtilen şartlarla kiralanmasına ilişkindir:", body_style))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(f"Kira Başlangıç Tarihi: <b>{format_date(data.get('start_date')) if data.get('start_date') else '-'}</b>", info_style))
        story.append(Paragraph(f"Kira Bitiş Tarihi: <b>{format_date(data.get('end_date')) if data.get('end_date') else '-'}</b>", info_style))
        story.append(Paragraph(f"Aylık Kira Bedeli: <b>{price_formatted}</b>", info_style))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("Kiracı, kira bedelini her ayın ilk 5 (beş) iş günü içinde Kiraya Veren'in belirteceği banka hesabına ödemeyi kabul ve taahhüt eder. Kiralanan mülk, sözleşme amacına uygun olarak (mesken/iş yeri) kullanılacaktır. Kiracı, mülke zarar vermemeyi, komşuluk ilişkilerine özen göstermeyi, aidat ve genel giderleri zamanında ödemeyi taahhüt eder.", body_style))
    elif data.get('contract_type') == 'Satış':
        story.append(Paragraph(f"İşbu sözleşme, yukarıda bilgileri verilen emlakın <b>{owner_name}</b> (Satıcı) tarafından <b>{customer.get('name', 'Alıcı')}</b> (Alıcı)'ya aşağıda belirtilen şartlarla satışına ilişkindir:", body_style))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(f"Satış Bedeli: <b>{price_formatted}</b>", info_style))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("Satış bedeli, tapu devri sırasında Alıcı tarafından Satıcı'ya nakden ve defaten ödenecektir (veya taraflarca anlaşılan ödeme planına göre). Tapu harçları ve masrafları yasal oranlarda taraflarca paylaşılacaktır (veya farklı anlaşıldıysa belirtilir). Satıcı, emlakın üzerinde herhangi bir takyidat (ipotek, haciz vb.) bulunmadığını ve emlakın mülkiyetini devretmeye yetkili olduğunu beyan ve taahhüt eder.", body_style))
    else: # Diğer sözleşme tipleri için genel metin
         story.append(Paragraph("İşbu sözleşme, taraflar arasında aşağıdaki koşullarda anlaşmaya varıldığını belirtir:", body_style))
         story.append(Paragraph(f"Sözleşme Bedeli: <b>{price_formatted}</b>", info_style))

    # Ek Notlar / Özel Şartlar
    if data.get('notes'):
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("Ek Notlar / Özel Şartlar", heading_style))
        # HTML etiketlerini temizle (güvenlik için)
        cleaned_notes = re.sub('<[^<]+?>', '', data['notes']) # Basit HTML temizleme
        story.append(Paragraph(cleaned_notes.replace('\n', '<br/>\n'), body_style)) # Satır sonlarını koru

    story.append(Spacer(1, 1.5*cm)) # İmzalardan önce boşluk

    # --- İmzalar ---
    customer_role = 'Alıcı' if data.get('contract_type') == 'Satış' else 'Kiracı'
    signature_data = [
        # İsimler
        [Paragraph(f"<b>{owner_role}</b><br/>{owner_name}", table_cell_style),
         Paragraph(f"<b>{customer_role}</b><br/>{customer.get('name', '-')}", table_cell_style)],
        # İmza Alanları (Çizgi ve yazı)
        [Paragraph("<br/>_________________________<br/>(İmza)", signature_label_style),
         Paragraph("<br/>_________________________<br/>(İmza)", signature_label_style)],
    ]
    signature_table = Table(signature_data, colWidths=[8*cm, 8*cm])
    signature_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'), # Tüm hücreleri ortala
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), # Dikeyde ortala
        ('BOTTOMPADDING', (0,0), (-1,0), 10), # İsimler için alt boşluk
        ('TOPPADDING', (0,1), (-1,1), 10), # İmza alanı için üst boşluk
    ]))
    story.append(signature_table)
    story.append(Spacer(1, 0.8*cm))

    # --- Hazırlayan Personel ve Tarih ---
    story.append(Paragraph(f"Sözleşme Tarihi: {format_date(data.get('contract_date'))}", info_style))
    personnel_name = personnel_info_pdf.get('name', '<i>Belirtilmemiş</i>')
    personnel_title = f" ({personnel_info_pdf.get('position')})" if personnel_info_pdf.get('position') else ""
    story.append(Paragraph(f"Hazırlayan Yetkili: {personnel_name}{personnel_title}", info_style))

    # --- PDF Oluşturma ---
    try:
        doc.build(story)
        buffer.seek(0) # Buffer'ı başa sar
        print("PDF başarıyla oluşturuldu (bellekte).")
        return buffer
    except Exception as pdf_build_error:
        # Hata detayını logla ve hatayı tekrar yükselt
        error_message = f"PDF Oluşturma Hatası (doc.build): {pdf_build_error}"
        print(error_message)
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"PDF oluşturulamadı: {pdf_build_error}")


@app.route('/create_contract', methods=['GET', 'POST'])
def create_contract():
    """Sözleşme oluşturma formunu gösterir ve PDF üretip veritabanına kaydeder."""
    if SimpleDocTemplate is None:
         flash("PDF oluşturma kütüphanesi (reportlab) yüklenemediği için bu özellik kullanılamıyor. Lütfen 'pip install reportlab' komutu ile kurun.", "error")
         return redirect(url_for('index')) # Ana sayfaya yönlendir

    # Form için gerekli listeleri al
    properties = get_properties_list()
    customers = get_customers_list()
    personnel = get_personnel_list()
    form_data_on_error = {} # Hata durumunda formu tekrar doldurmak için

    if request.method == 'POST':
        form_data_on_error = request.form.to_dict() # Hata olursa form verilerini sakla
        db = get_db()
        cursor = db.cursor()
        try:
            # --- Form Verilerini Al ve Doğrula ---
            property_id_str = request.form.get('property_id')
            customer_id_str = request.form.get('customer_id')
            personnel_id_str = request.form.get('personnel_id')
            contract_type = request.form.get('contract_type')
            contract_date_str = request.form.get('contract_date') or datetime.now().strftime('%Y-%m-%d')
            start_date_str = request.form.get('start_date') or None
            end_date_str = request.form.get('end_date') or None
            price_str = request.form.get('price', '').strip().replace('.', '').replace(',', '.')
            notes = request.form.get('notes', '').strip()

            # Zorunlu alan kontrolü
            if not all([property_id_str, customer_id_str, personnel_id_str, contract_type]):
                flash("Lütfen Emlak, Müşteri, Sorumlu Personel ve Sözleşme Tipi seçin.", "error")
                raise ValueError("Zorunlu alanlar eksik")

            property_id = int(property_id_str)
            customer_id = int(customer_id_str)
            personnel_id = int(personnel_id_str)

            # Tarihleri parse et
            try:
                contract_date = datetime.strptime(contract_date_str, '%Y-%m-%d').date()
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
            except ValueError:
                flash("Lütfen geçerli tarihler girin (YYYY-AA-GG formatında).", "error")
                raise ValueError("Geçersiz tarih formatı")

            # Kira sözleşmesi için tarih mantığı kontrolü
            if contract_type == 'Kira':
                if not start_date or not end_date:
                    flash("Kira sözleşmesi için Başlangıç ve Bitiş Tarihleri gereklidir.", "error")
                    raise ValueError("Kira için tarihler eksik")
                if start_date and end_date and end_date <= start_date:
                    flash("Kira bitiş tarihi, başlangıç tarihinden sonra olmalıdır.", "error")
                    raise ValueError("Geçersiz kira tarih aralığı")

            # Fiyatı float'a çevir
            try:
                price = float(price_str) if price_str else None
            except ValueError:
                flash("Sözleşme bedeli geçerli bir sayı olmalıdır.", "error")
                raise ValueError("Geçersiz fiyat formatı")

            # --- Veritabanından İlgili Kayıtları Çek ---
            cursor.execute("""
                SELECT p.*, o.id as owner_id_db, o.name as owner_name, o.phone as owner_phone, o.email as owner_email
                FROM properties p
                LEFT JOIN owners o ON p.owner_id = o.id
                WHERE p.id = ?""", (property_id,))
            prop = cursor.fetchone()

            cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
            cust = cursor.fetchone()

            cursor.execute("SELECT * FROM personnel WHERE id = ?", (personnel_id,))
            pers = cursor.fetchone()

            # Kayıtların varlığını kontrol et
            if not prop: flash(f"ID'si {property_id} olan emlak bulunamadı.", "error"); raise ValueError("Emlak bulunamadı")
            if not cust: flash(f"ID'si {customer_id} olan müşteri bulunamadı.", "error"); raise ValueError("Müşteri bulunamadı")
            if not pers: flash(f"ID'si {personnel_id} olan personel bulunamadı.", "error"); raise ValueError("Personel bulunamadı")

            # Emlak durumu kontrolü (Uyarı ver, işlemi durdurma)
            if contract_type == 'Kira' and prop['status'] != 'Kiralık':
                 flash(f"Uyarı: '{prop['title']}' adlı emlak şu anda '{prop['status']}' durumunda. Kira sözleşmesi oluşturuluyor.", "warning")
            elif contract_type == 'Satış' and prop['status'] != 'Satılık':
                 flash(f"Uyarı: '{prop['title']}' adlı emlak şu anda '{prop['status']}' durumunda. Satış sözleşmesi oluşturuluyor.", "warning")

            # Sahip bilgisini al
            owner = None
            if prop['owner_id_db']:
                 owner = {
                     'id': prop['owner_id_db'],
                     'name': prop['owner_name'],
                     'phone': prop['owner_phone'],
                     'email': prop['owner_email']
                 }
            elif contract_type == 'Satış': # Satışta sahip zorunlu
                flash(f"Seçilen '{prop['title']}' adlı emlak için bir sahip tanımlanmamış. Satış sözleşmesi oluşturulamaz. Lütfen önce emlağı düzenleyip sahibini atayın.", "error")
                raise ValueError("Satış için sahip gerekli")

            # --- PDF Oluşturma ---
            pdf_data_for_generation = {
                'contract_type': contract_type,
                'property': dict(prop),
                'customer': dict(cust),
                'owner': owner,
                'personnel': dict(pers),
                'contract_date': contract_date,
                'start_date': start_date,
                'end_date': end_date,
                'price': price if price is not None else prop['price'], # Formdaki fiyat öncelikli
                'notes': notes
            }

            pdf_buffer = generate_contract_pdf(pdf_data_for_generation)
            pdf_bytes = pdf_buffer.getvalue()

            # --- Dosya Adını Oluştur ---
            def clean_filename(name):
                """Dosya adı için geçersiz karakterleri temizler ve kısaltır."""
                name = str(name) # String olduğundan emin ol
                name = re.sub(r'[\\/*?:"<>|]', "", name) # Geçersiz karakterleri kaldır
                name = re.sub(r'\s+', '_', name) # Boşlukları _ ile değiştir
                # Türkçe karakterleri de değiştirmek isteyebilirsiniz (opsiyonel)
                # name = name.replace('ı', 'i').replace('İ', 'I')...
                return name[:60] # Çok uzamasını engelle

            clean_cust_name = clean_filename(cust['name'])
            clean_prop_title = clean_filename(prop['title'])
            # Daha anlamlı dosya adı
            pdf_filename = f"{contract_type}_{clean_cust_name}_{prop['city']}_{prop['district']}_{prop['id']}.pdf"
            pdf_filename = secure_filename(pdf_filename) # Werkzeug ile son güvenlik kontrolü

            # --- Veritabanına Kaydet ---
            try:
                cursor.execute('''INSERT INTO contracts
                                  (contract_type, property_id, customer_id, owner_id, personnel_id,
                                   contract_date, start_date, end_date, price, notes,
                                   pdf_filename, pdf_data)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (contract_type, property_id, customer_id, owner['id'] if owner else None, personnel_id,
                                contract_date, start_date, end_date, pdf_data_for_generation['price'], notes,
                                pdf_filename, sqlite3.Binary(pdf_bytes))) # PDF verisini BLOB olarak kaydet

                # Emlak durumunu güncelle (Opsiyonel, belki manuel yapılmalı?)
                new_status = 'Satıldı' if contract_type == 'Satış' else ('Kiralandı' if contract_type == 'Kira' else prop['status'])
                if new_status != prop['status']:
                     cursor.execute("UPDATE properties SET status = ? WHERE id = ?", (new_status, property_id))
                     print(f"Emlak ID {property_id} durumu '{new_status}' olarak güncellendi.")

                db.commit()
                print(f"Sözleşme ID {cursor.lastrowid} veritabanına başarıyla kaydedildi (PDF dahil).")
                flash(f"{contract_type} sözleşmesi başarıyla oluşturuldu ve kaydedildi.", "success")

                # Başarılı kayıttan sonra sözleşme listesine yönlendir
                return redirect(url_for('list_contracts'))

            except sqlite3.Error as db_err:
                 db.rollback()
                 print(f"DB Error (Save Contract with PDF): {db_err}")
                 flash(f"PDF oluşturuldu ancak sözleşme veritabanına kaydedilirken hata oluştu: {db_err}", "error")
                 # Hatayı yukarı fırlat ki genel except bloğu yakalasın
                 raise db_err

        # --- Genel Hata Yönetimi (Form validation, DB, PDF generation) ---
        except ValueError as ve:
             # Flash mesajı zaten yukarıda ayarlanmış olabilir
             if not get_flashed_messages(category_filter=["error"]):
                 flash(f"Form verilerinde hata: {ve}. Lütfen girdileri kontrol edin.", "error")
             print(f"Form Değer Hatası: {ve}")
        except sqlite3.Error as dbe:
            if not get_flashed_messages(category_filter=["error"]):
                flash(f"Veritabanı hatası: {dbe}", "error")
            print(f"Veritabanı Hatası: {dbe}")
        except ImportError as ie:
             flash(f"PDF oluşturma hatası: {ie}. 'reportlab' kütüphanesinin kurulu olduğundan emin olun.", "error")
             print(f"Import Hatası: {ie}")
        except RuntimeError as re:
             flash(f"PDF oluşturulurken hata oluştu: {re}", "error")
             print(f"Runtime Hatası (PDF Oluşturma): {re}")
        except Exception as e:
            flash(f"Beklenmedik bir hata oluştu: {e}", "error")
            print(f"Beklenmedik Hata: {e}")
            import traceback
            traceback.print_exc() # Hatanın tam izini konsola yazdır

        # Hata durumunda formu tekrar göster, girilen veriler kaybolmasın
        return render_template('create_contract.html', page_title="Sözleşme Oluştur",
                               properties=properties, customers=customers, personnel=personnel,
                               form_data=form_data_on_error, # Hata anındaki form verileri
                               today_date=datetime.now().strftime('%Y-%m-%d'))

    # GET isteği (Sayfa ilk yüklendiğinde)
    today_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('create_contract.html', page_title="Sözleşme Oluştur",
                           properties=properties, customers=customers, personnel=personnel,
                           today_date=today_date, form_data=None)


# Sözleşme Listeleme Rotası
@app.route('/contracts')
def list_contracts():
    """Oluşturulan sözleşmeleri listeler."""
    db = get_db()
    cursor = db.cursor()
    contracts = []
    try:
        # PDF verisinin varlığını kontrol etmek için CASE kullan
        query = """
            SELECT
                c.id, c.contract_type, c.contract_date, c.start_date, c.end_date, c.price,
                c.pdf_filename, -- PDF dosya adını al
                (CASE WHEN c.pdf_data IS NOT NULL AND LENGTH(c.pdf_data) > 0 THEN 1 ELSE 0 END) as has_pdf_data, -- PDF verisi var mı?
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

# Kayıtlı Sözleşme PDF'ini İndirme Rotası
@app.route('/download_contract_pdf/<int:contract_id>')
def download_contract_pdf(contract_id):
    """Veritabanında kayıtlı PDF'i indirir."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT pdf_data, pdf_filename FROM contracts WHERE id = ?", (contract_id,))
        contract_pdf = cursor.fetchone()

        if contract_pdf and contract_pdf['pdf_data']:
            pdf_data = contract_pdf['pdf_data']
            filename = contract_pdf['pdf_filename'] or f"sozlesme_{contract_id}.pdf"
            filename = secure_filename(filename) # Güvenlik kontrolü

            response = make_response(pdf_data)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"' # attachment: indir, inline: göster
            print(f"PDF indiriliyor: {filename} (ID: {contract_id}, Boyut: {len(pdf_data)} bytes)")
            return response
        else:
            print(f"Hata: ID {contract_id} için PDF verisi bulunamadı veya boş.")
            flash(f"ID {contract_id} olan sözleşme için indirilecek PDF verisi bulunamadı.", "error")
            # Kullanıcının geldiği sayfaya geri yönlendir
            referer = request.headers.get("Referer")
            return redirect(referer or url_for('list_contracts'))

    except sqlite3.Error as e:
        print(f"DB Hatası (PDF İndirme - ID: {contract_id}): {e}")
        flash(f"PDF indirilirken veritabanı hatası oluştu: {e}", "error")
        return redirect(url_for('list_contracts'))
    except Exception as e:
        print(f"Genel Hata (PDF İndirme - ID: {contract_id}): {e}")
        flash(f"PDF indirilirken beklenmedik bir hata oluştu: {e}", "error")
        import traceback
        traceback.print_exc()
        return redirect(url_for('list_contracts'))


# Sözleşme Silme Rotası
@app.route('/delete_contract/<int:contract_id>', methods=['POST'])
def delete_contract(contract_id):
    """Bir sözleşmeyi siler."""
    db = get_db()
    cursor = db.cursor()
    try:
        # Opsiyonel: Silinen sözleşmeye bağlı emlakın durumunu 'Satılık'/'Kiralık' yap
        # ... (Bu mantık iş akışına göre belirlenmeli) ...

        cursor.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
        db.commit()
        flash(f"ID {contract_id} olan sözleşme başarıyla silindi.", "success")
    except sqlite3.Error as e:
        db.rollback()
        print(f"DB Error (Delete Contract): {e}")
        flash(f"Sözleşme silinirken bir hata oluştu: {e}", 'error')
    return redirect(url_for('list_contracts'))

# --- YENİ: Prim Hesaplama Modülü ---
@app.route('/personnel_commissions', methods=['GET'])
def personnel_commissions():
    """Personel primlerini hesaplar ve gösterir."""
    db = get_db()
    cursor = db.cursor()

    # Tarih filtrelerini al
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')

    # Tarihleri parse et
    start_date = None
    end_date = None
    date_filter_active = False
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            date_filter_active = True
        if end_date_str:
            # Bitiş tarihini dahil etmek için gün sonuna ayarla (eğer saat önemliyse)
            # Şimdilik sadece tarih karşılaştırması yeterli
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            date_filter_active = True
    except ValueError:
        flash("Geçersiz tarih formatı. Lütfen YYYY-AA-GG formatını kullanın.", "error")
        start_date, end_date = None, None # Hatalı formatta filtreyi sıfırla
        date_filter_active = False

    commissions_data = {} # {personnel_id: {'name': '...', 'total_commission': 0.0, 'contracts': []}}

    try:
        # İlgili sözleşmeleri çek
        query = """
            SELECT
                c.id as contract_id, c.contract_type, c.price, c.contract_date,
                p.id as personnel_id, p.name as personnel_name
            FROM contracts c
            JOIN personnel p ON c.personnel_id = p.id
            WHERE p.is_active = 1 -- Sadece aktif personelin primleri
        """
        params = []

        # Tarih filtresini uygula
        if start_date:
            query += " AND c.contract_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND c.contract_date <= ?"
            params.append(end_date)

        query += " ORDER BY p.name, c.contract_date DESC"

        cursor.execute(query, params)
        contracts = cursor.fetchall()

        # Primleri hesapla ve personel bazında grupla
        for contract in contracts:
            personnel_id = contract['personnel_id']
            contract_type = contract['contract_type']
            price = contract['price']

            if personnel_id is None or price is None or price <= 0:
                continue # Geçersiz veri varsa atla

            # Personel verisi yoksa oluştur
            if personnel_id not in commissions_data:
                commissions_data[personnel_id] = {
                    'name': contract['personnel_name'],
                    'total_commission': 0.0,
                    'contracts': [] # Detay için sözleşmeleri tutabiliriz (opsiyonel)
                }

            # Prim oranını al
            rate = COMMISSION_RATES.get(contract_type, 0.0) # Bilinmeyen tip için 0 oran
            commission_amount = price * rate

            # Toplam primi güncelle
            commissions_data[personnel_id]['total_commission'] += commission_amount

            # Sözleşme detayını ekle (opsiyonel)
            commissions_data[personnel_id]['contracts'].append({
                'id': contract['contract_id'],
                'type': contract_type,
                'price': price,
                'date': contract['contract_date'],
                'commission': commission_amount
            })

    except sqlite3.Error as e:
        flash(f"Primler hesaplanırken veritabanı hatası oluştu: {e}", "error")
        print(f"DB Error (Calculate Commissions): {e}")
    except Exception as e:
        flash(f"Primler hesaplanırken beklenmedik bir hata oluştu: {e}", "error")
        print(f"Error (Calculate Commissions): {e}")
        import traceback
        traceback.print_exc()


    # Şablon için veriyi hazırla (sadece toplamları içeren liste)
    commission_summary = []
    for pid, data in commissions_data.items():
        commission_summary.append({
            'personnel_id': pid,
            'personnel_name': data['name'],
            'total_commission': data['total_commission']
        })

    # Toplam prime göre sırala (en yüksekten düşüğe)
    commission_summary.sort(key=lambda x: x['total_commission'], reverse=True)

    return render_template(
        'personnel_commissions.html',
        page_title="Personel Prim Hesaplama",
        commissions=commission_summary,
        start_date=start_date_str, # Filtre alanlarını doldurmak için
        end_date=end_date_str,
        date_filter_active=date_filter_active,
        commission_rates=COMMISSION_RATES # Oranları şablona gönder
    )


# --- Dummy (Örnek) Veri Ekleme Modülü ---
@app.route('/add_dummy_data', methods=['POST'])
def add_dummy_data():
    """Geliştirme/Test amacıyla rastgele örnek veriler ekler."""
    # Sadece debug modunda çalışsın
    if not app.debug:
        flash("Bu işlem sadece geliştirme modunda kullanılabilir.", "error")
        return redirect(url_for('index'))

    db = get_db()
    cursor = db.cursor()
    num_entries = 5 # Her türden kaç tane ekleneceği (yaklaşık)
    added_count = {'owners': 0, 'personnel': 0, 'customers': 0, 'properties': 0, 'contracts': 0}

    try:
        # --- 1. Örnek Sahipler ---
        owners_data = []
        owner_ids = [] # Eklenen veya var olan ID'leri tut
        for i in range(num_entries):
            unique_suffix = random.randint(1000, 9999)
            name = f"Sahip {chr(65+i)}{unique_suffix}"
            phone = f"555000{unique_suffix}"[-10:] # Son 10 hane
            email = f"sahip{unique_suffix}@ornek.com"
            owners_data.append((name, phone, email, f"{name} için notlar."))

        for owner in owners_data:
            try:
                cursor.execute("INSERT INTO owners (name, phone, email, notes) VALUES (?, ?, ?, ?)", owner)
                owner_ids.append(cursor.lastrowid)
                added_count['owners'] += 1
            except sqlite3.IntegrityError: # Telefon veya email zaten varsa
                cursor.execute("SELECT id FROM owners WHERE phone = ? OR email = ?", (owner[1], owner[2]))
                existing_owner = cursor.fetchone()
                if existing_owner: owner_ids.append(existing_owner['id'])
                print(f"Dummy Data: Sahip {owner[1]}/{owner[2]} zaten var, atlandı.")

        # --- 2. Örnek Personel ---
        personnel_data = []
        personnel_ids = []
        positions = ["Emlak Danışmanı", "Yönetici Asistanı", "Pazarlama Uzmanı", "Muhasebe", "Ofis Müdürü"]
        for i in range(num_entries):
             unique_suffix = random.randint(1000, 9999)
             name = f"Personel {chr(70+i)}{unique_suffix}"
             phone = f"555111{unique_suffix}"[-10:]
             email = f"personel{unique_suffix}@sirket.com"
             position = random.choice(positions)
             hire_date = (datetime.now() - timedelta(days=random.randint(30, 1800))).date()
             is_active = random.choice([True, True, False]) # %66 aktif
             salary = random.choice([None, random.randint(15000, 40000)])
             personnel_data.append((name, position, phone, email, hire_date, 1 if is_active else 0, f"{name} hakkında not.", salary))

        for person in personnel_data:
             try:
                 cursor.execute("INSERT INTO personnel (name, position, phone, email, hire_date, is_active, notes, salary) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", person)
                 personnel_ids.append(cursor.lastrowid)
                 added_count['personnel'] += 1
             except sqlite3.IntegrityError:
                 cursor.execute("SELECT id FROM personnel WHERE phone = ? OR email = ?", (person[2], person[3]))
                 existing_personnel = cursor.fetchone()
                 if existing_personnel: personnel_ids.append(existing_personnel['id'])
                 print(f"Dummy Data: Personel {person[2]}/{person[3]} zaten var, atlandı.")

        # --- 3. Örnek Müşteriler ---
        customer_data = []
        customer_ids = []
        types = ["Alıcı", "Kiracı", "Potansiyel", "Satıcı", "Yatırımcı", "Diğer"]
        for i in range(num_entries * 2): # Daha fazla müşteri ekleyelim
             unique_suffix = random.randint(10000, 99999)
             name = f"Müşteri {chr(80+i)}{unique_suffix}"
             phone = f"555222{unique_suffix}"[-10:]
             email = f"musteri{unique_suffix}@mail.net"
             cust_type = random.choice(types)
             is_archived = 1 if random.random() < 0.15 else 0 # %15 arşivli olsun
             customer_data.append((name, phone, email, cust_type, f"{name} için tercihler: {random.choice(['Geniş balkonlu', 'Merkezi konumda', 'Yatırımlık', 'Sessiz muhitte'])}", is_archived))

        for customer in customer_data:
            try:
                cursor.execute("INSERT INTO customers (name, phone, email, customer_type, notes, is_archived) VALUES (?, ?, ?, ?, ?, ?)", customer)
                customer_ids.append(cursor.lastrowid)
                added_count['customers'] += 1
            except sqlite3.IntegrityError:
                cursor.execute("SELECT id FROM customers WHERE phone = ? OR email = ?", (customer[1], customer[2]))
                existing_customer = cursor.fetchone()
                if existing_customer: customer_ids.append(existing_customer['id'])
                print(f"Dummy Data: Müşteri {customer[1]}/{customer[2]} zaten var, atlandı.")

        # --- 4. Örnek Emlaklar ---
        properties_data = []
        property_ids = []
        prop_types = ["Daire", "Villa", "İş Yeri", "Arsa", "Müstakil Ev", "Rezidans", "Yazlık", "Dükkan"]
        statuses = ["Satılık", "Kiralık"] # Başlangıç durumları
        cities = ["Ankara", "İstanbul", "İzmir", "Bursa", "Antalya"]
        districts = {
            "Ankara": ["Çankaya", "Keçiören", "Yenimahalle", "Mamak", "Etimesgut", "Gölbaşı"],
            "İstanbul": ["Kadıköy", "Beşiktaş", "Şişli", "Üsküdar", "Bakırköy", "Sarıyer", "Beylikdüzü", "Fatih"],
            "İzmir": ["Konak", "Bornova", "Karşıyaka", "Buca", "Çiğli", "Narlıdere", "Urla"],
            "Bursa": ["Osmangazi", "Nilüfer", "Yıldırım", "Mudanya", "Gemlik"],
            "Antalya": ["Muratpaşa", "Konyaaltı", "Kepez", "Alanya", "Manavgat", "Kaş", "Kemer"]
        }
        rooms = ["1+1", "2+1", "3+1", "4+1", "4+2", "5+1", "5+2", "Stüdyo", "6+"]

        valid_owner_ids = [oid for oid in owner_ids if oid is not None] # Geçerli sahip ID'leri

        for i in range(num_entries * 4): # Daha fazla emlak ekleyelim
            city = random.choice(cities)
            district = random.choice(districts[city])
            prop_type = random.choice(prop_types)
            status = random.choice(statuses)
            room_count = random.choice(rooms) if prop_type not in ["Arsa", "İş Yeri", "Dükkan"] else None
            title = f"{district.capitalize()} {random.choice(['Merkezde', 'Manzaralı', 'Geniş', 'Yeni'])} {room_count or ''} {prop_type} ({status})"
            price = random.randint(1500000, 15000000) if status == "Satılık" else random.randint(15000, 75000)
            area = random.randint(40, 450) if prop_type != "Arsa" else random.randint(200, 5000)
            address = f"{district.capitalize()} Mahallesi, {random.choice(['Atatürk', 'Cumhuriyet', 'Sevgi', 'Barış'])} Caddesi No:{random.randint(1, 150)}"
            # Rastgele bir sahip ata veya boş bırak
            owner_id = random.choice(valid_owner_ids) if valid_owner_ids and random.random() > 0.2 else None

            prop_data = (
                title, f"{title}. {random.choice(['Şehrin kalbinde', 'Doğa içinde', 'Ulaşımı kolay', 'Yatırıma uygun'])} fırsat! {area} m².",
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
                 # Genelde UNIQUE constraint hatası olmaz ama loglamak iyi olur
                 print(f"Dummy Data: Emlak eklenirken hata: {prop_err} - Veri: {prop_data}")

        # --- 5. Örnek Sözleşmeler (PDF'siz) ---
        # PDF'li dummy data oluşturmak daha karmaşık olurdu, şimdilik PDF'siz ekleyelim.
        valid_property_ids_for_contract = [pid for pid in property_ids if pid is not None]
        valid_customer_ids_for_contract = [cid for cid in customer_ids if cid is not None]
        valid_personnel_ids_for_contract = [pid for pid in personnel_ids if pid is not None]

        if valid_property_ids_for_contract and valid_customer_ids_for_contract and valid_personnel_ids_for_contract:
            num_contracts_to_add = min(len(valid_property_ids_for_contract), len(valid_customer_ids_for_contract), num_entries * 2)

            # Emlakların sahip ve durum bilgilerini çek
            cursor.execute(f"SELECT id, owner_id, status, price FROM properties WHERE id IN ({','.join('?'*len(valid_property_ids_for_contract))})", valid_property_ids_for_contract)
            prop_details_map = {row['id']: {'owner_id': row['owner_id'], 'status': row['status'], 'price': row['price']} for row in cursor.fetchall()}

            # Kullanılacak emlak ID'lerini kopyala, kullandıkça çıkaracağız
            available_prop_ids = list(valid_property_ids_for_contract)
            random.shuffle(available_prop_ids)

            for _ in range(num_contracts_to_add):
                if not available_prop_ids: break # Eklenecek emlak kalmadıysa dur

                prop_id = available_prop_ids.pop() # Listeden bir emlak seç ve çıkar
                prop_details = prop_details_map.get(prop_id)

                if not prop_details or prop_details['status'] not in ['Satılık', 'Kiralık']:
                    continue # Eğer emlak bilgisi yoksa veya durumu uygun değilse atla

                cust_id = random.choice(valid_customer_ids_for_contract)
                pers_id = random.choice(valid_personnel_ids_for_contract)
                owner_id = prop_details['owner_id'] # Emlaktan gelen sahip ID'si

                contract_type = 'Satış' if prop_details['status'] == 'Satılık' else 'Kira'

                # Satış için sahip yoksa ve geçerli sahip listesi boş değilse rastgele ata
                if contract_type == 'Satış' and not owner_id:
                    if valid_owner_ids: owner_id = random.choice(valid_owner_ids)
                    else: continue # Sahip atanamıyorsa bu sözleşmeyi atla

                contract_date = (datetime.now() - timedelta(days=random.randint(1, 730))).date()
                start_date = (contract_date + timedelta(days=random.randint(1, 30))) if contract_type == 'Kira' else None
                end_date = (start_date + timedelta(days=random.randint(300, 730))) if start_date else None
                # Fiyata küçük bir değişiklik yapalım
                price = prop_details['price'] * random.uniform(0.95, 1.05) if prop_details['price'] else (random.randint(15000, 75000) if contract_type == 'Kira' else random.randint(1500000, 15000000))
                notes = f"{contract_type} sözleşmesi için otomatik oluşturulan notlar. Pazarlık yapıldı."
                pdf_filename = f"ornek_{contract_type}_{cust_id}_{prop_id}.pdf" # Örnek dosya adı, veri yok

                contract_data = (
                    contract_type, prop_id, cust_id, owner_id, pers_id,
                    contract_date, start_date, end_date, price, notes,
                    pdf_filename, None # PDF datası None olarak ekleniyor
                )

                try:
                    cursor.execute('''INSERT INTO contracts
                                      (contract_type, property_id, customer_id, owner_id, personnel_id, contract_date, start_date, end_date, price, notes, pdf_filename, pdf_data)
                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', contract_data)

                    # Emlak durumunu güncelle (Satıldı/Kiralandı)
                    new_status = 'Satıldı' if contract_type == 'Satış' else 'Kiralandı'
                    cursor.execute("UPDATE properties SET status = ? WHERE id = ?", (new_status, prop_id))

                    added_count['contracts'] += 1

                except sqlite3.Error as contract_err:
                    # Sözleşme eklenirken hata olursa (örn: foreign key), logla ama devam et
                    print(f"Dummy Data: Sözleşme eklenirken hata: {contract_err} - Veri: {contract_data}")
                    # Başarısız olursa emlak ID'sini tekrar listeye ekle (opsiyonel)
                    # available_prop_ids.append(prop_id)


        db.commit() # Tüm değişiklikleri kaydet
        flash_message = f"Örnek veriler eklendi: {added_count['owners']} Sahip, {added_count['personnel']} Personel, {added_count['customers']} Müşteri, {added_count['properties']} Emlak, {added_count['contracts']} Sözleşme (PDF'siz)."
        flash(flash_message, "success")
        print(flash_message)

    except sqlite3.Error as e:
        db.rollback() # Herhangi bir DB hatasında tüm işlemi geri al
        error_msg = f"Örnek veri eklenirken bir veritabanı hatası oluştu: {e}"
        print(f"Dummy veri eklenirken DB hatası: {e}")
        flash(error_msg, "error")
    except Exception as e:
        db.rollback() # Beklenmedik hatalarda da geri al
        error_msg = f"Örnek veri eklenirken beklenmedik bir hata oluştu: {e}"
        print(f"Dummy veri eklenirken genel hata: {e}")
        import traceback
        traceback.print_exc()
        flash(error_msg, "error")

    return redirect(url_for('index')) # Ana sayfaya yönlendir


# --- Uygulamayı Başlatma ---
if __name__ == '__main__':
    print("Uygulama başlatılıyor...")
    init_db() # Veritabanını kontrol et/oluştur/güncelle
    print(f"Debug modu: {app.debug}")
    # host='0.0.0.0' uygulamanın ağdaki diğer cihazlardan erişilebilir olmasını sağlar.
    # Sadece kendi makinenizde çalıştıracaksanız '127.0.0.1' veya 'localhost' kullanın.
    # port=5000 varsayılan Flask portudur, değiştirebilirsiniz.
    app.run(debug=is_debug_mode, host='0.0.0.0', port=5000)
