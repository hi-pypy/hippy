# 1. Genel Ayarlar ve Başlangıç
import os
import json
import random
import logging
import time
from datetime import datetime
from instagrapi import Client
from dotenv import load_dotenv
import imaplib
import email
from email.header import decode_header

load_dotenv()

def get_account_credentials(account_number):
    username = os.getenv(f"INSTAGRAM_ACCOUNT{account_number}_USERNAME")
    password = os.getenv(f"INSTAGRAM_ACCOUNT{account_number}_PASSWORD")
    return username, password

print("Program başladı...")  # Başlangıç logu

# Log dosyası ayarı
logging.basicConfig(filename="upload_log.txt", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Hesap listesini yükleme fonksiyonu
def load_accounts(filename="account_list.json"):
    with open(filename, "r") as file:
        accounts = json.load(file)
    return accounts

# JSON dosyasından rastgele veri seçen fonksiyon
def load_random_json_data(filename, key):
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            data = json.load(file)
            if key in data and data[key]:
                return random.choice(data[key])
            else:
                logging.warning(f"{filename} dosyasındaki {key} anahtarı boş veya hatalı.")
                return ""
    except Exception as e:
        logging.error(f"{datetime.now()} - {filename} dosyası okuma hatası: {str(e)}")
        return ""

# 2. Instagram İle Bağlantı ve 2FA
# Instagram'a giriş yapma fonksiyonu
def login_instagram(username, password, email_user=None, email_pass=None, previous_2fa_code=None):
    client = Client()
    try:
        client.login(username, password)

        if client.is_two_factor_required():
            if previous_2fa_code:
                client.two_factor_login(previous_2fa_code)
            elif email_user and email_pass:
                code = get_2fa_code_from_email(email_user, email_pass)
                if code:
                    client.two_factor_login(code)
                    logging.info(f"{username} için 2FA doğrulaması başarılı.")
                else:
                    logging.error(f"{username} için 2FA kodu alınamadı.")
                    return None
            else:
                logging.error(f"{username} için 2FA işlemi yapılmadı.")
                return None

        logging.info(f"{datetime.now()} - {username} başarıyla giriş yaptı")
        return client
    except Exception as e:
        logging.error(f"{datetime.now()} - {username} giriş hatası: {str(e)}")
        return None

# IMAP giriş bilgileri
def get_2fa_code_from_email(email_user, email_pass, imap_server="imap.gmail.com"):
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_user, email_pass)
        
        mail.select("inbox")
        
        result, data = mail.search(None, 'ALL')
        if result != "OK":
            logging.error("E-posta arama hatası.")
            return None
        
        latest_email_id = data[0].split()[-1]
        result, data = mail.fetch(latest_email_id, "(RFC822)")

        code = None
        for response_part in data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8")
                
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        body = part.get_payload(decode=True).decode()
                        if "Your Instagram code is" in body:
                            code = body.split("Your Instagram code is")[1].split()[0]
                            logging.info(f"2FA kodu alındı: {code}")
                            return code
                else:
                    body = msg.get_payload(decode=True).decode()
                    if "Your Instagram code is" in body:
                        code = body.split("Your Instagram code is")[1].split()[0]
                        logging.info(f"2FA kodu alındı: {code}")
                        return code
        
        if code is None:
            logging.error(f"{datetime.now()} - 2FA kodu alınamadı. Hesap: {email_user}")
            return None
            
    except Exception as e:
        logging.error(f"E-posta ile 2FA kodu alma hatası: {str(e)}")
        return None
    finally:
        mail.logout()

# 3. Medya Yükleme İşlemleri (Post ve Story)
# Instagram'a fotoğraf yükleme fonksiyonu (Post için)
def upload_to_instagram(client, file_path, caption, hashtags, username):
    try:
        post_caption = f"{caption}\n\n{hashtags}"
        client.photo_upload(file_path, post_caption)
        logging.info(f"{datetime.now()} - {username} için paylaşım yapıldı: {file_path}")
        return True  # Başarıyla yüklenmişse True döndür
    except Exception as e:
        logging.error(f"{datetime.now()} - {username} paylaşım hatası: {str(e)}")
        return False  # Başarısız yükleme durumunda False döndür

# Instagram'a fotoğraf yükleme fonksiyonu (Story için)
def upload_to_instagram_story(client, file_path, username):
    try:
        client.photo_upload_to_story(file_path)
        logging.info(f"{datetime.now()} - {username} için story paylaşıldı: {file_path}")
        return True
    except Exception as e:
        logging.error(f"{datetime.now()} - {username} story paylaşım hatası: {str(e)}")
        return False

# 4. Medya Dosyası Seçimi ve Yönetimi
# Kullanılmamış medya dosyasını seçen fonksiyon
def get_unused_media(media_folder="cat", used_file="used_files.txt"):
    media_files = [f for f in os.listdir(media_folder) if f.endswith(('jpg', 'png'))]
    
    used_files = set()
    if os.path.exists(used_file):
        with open(used_file, 'r') as file:
            used_files = set(file.read().splitlines())
    
    available_files = [f for f in media_files if f not in used_files]
    if not available_files:
        logging.warning("Yeterli kullanılabilir dosya yok!")
        return None
    
    selected_file = random.choice(available_files)
    with open(used_file, 'a') as file:
        file.write(f"{selected_file}\n")
    
    return os.path.join(media_folder, selected_file)

# 5. Hesap Yönetimi ve Paylaşım Kontrolleri
def handle_media_for_accounts(media_file_path, accounts):
    account_share_log = {}  # Her hesap için paylaşım durumu
    used_files = {}  # Dosya okuma işlemini optimize et

    for account in accounts:
        account_log_dir = f"logs/{account['username']}"
        if not os.path.exists(account_log_dir):
            os.makedirs(account_log_dir)

        used_log_file = f"{account_log_dir}/used_files.txt"

        if used_log_file not in used_files:
            used_files[used_log_file] = set(line.strip() for line in open(used_log_file, "r"))


        if media_file_path not in used_files[used_log_file]:
            account_share_log[account['username']] = False
        else:
            account_share_log[account['username']] = True
    return account_share_log

# Hesaplar için işlemi başlat
accounts = load_accounts()
media_file_path = get_unused_media()  # Sadece bir medya dosyası seçilecek

if media_file_path:
    account_share_log = handle_media_for_accounts(media_file_path, accounts)
    all_shared = True  # Tüm hesaplarda paylaşım yapılacak mı kontrolü

    for account in accounts:
        if not account_share_log.get(account["username"], False):
            print(f"{datetime.now()} - {account['username']} için giriş yapılıyor...")
            client = login_instagram(account["username"], account["password"])
            
            if client:
                print(f"{datetime.now()} - {account['username']} hesabı için işlem başlıyor...")
                
                caption = load_random_json_data('comment.json', 'comments')
                hashtags = load_random_json_data('hashtag.json', 'hashtags')
                
                if upload_to_instagram(client, media_file_path, caption, hashtags, account["username"]):
                    upload_to_instagram_story(client, media_file_path, account["username"])
                    account_share_log[account["username"]] = True  # Paylaşıldı olarak işaretle
                else:
                    logging.error(f"{datetime.now()} - {account['username']} için paylaşım hatası.")
                    all_shared = False  # Eğer herhangi bir hesap paylaşamazsa, bu işlemi tamamlanmış saymıyoruz
            else:
                logging.error(f"{datetime.now()} - {account['username']} için giriş yapılamadı.")
                print(f"{datetime.now()} - {account['username']} için giriş yapılamadı.")
        
        # Paylaşım sonrası veya işlem arası bekleme
        time.sleep(random.uniform(30, 60))  # Her işlem arası 30-60 saniye bekle

   # Eğer tüm hesaplarda paylaşım başarılıysa, bitiş
   if all_shared:
       logging.info("Tüm hesaplar için medya paylaşımı başarılı.")
   else:
       logging.warning("Bazı hesaplar için medya paylaşımı başarısız oldu.")
