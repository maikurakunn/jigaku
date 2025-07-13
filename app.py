from flask import Flask, render_template, session, request, redirect, url_for, send_from_directory, abort
import os
import json
import re
import requests
import string
import ssl
from random import choice
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

ARTICLES_DIR = 'articles'
UPLOAD_FOLDER = 'uploads'  # アップロードされたファイルを保存するディレクトリ
USER_FILE = 'users.json'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'py', 'java', "mp3", "mp4", "gif"} # 許可するファイルの拡張子
KANJI_JSON_PATH = 'kanji_data.json'
IP_BLOCKLIST_FILE = 'IP.json'
IP_LOG_FILE = 'IP.json'
FUNCTION_TITLES = [
    "記事", "配布ファイル", "漢字検索", "カラーピッカーを使う",
    "管理者画面へ", "不正アクセス一覧","おみくじ","サーバーコード"
]



#以下関数定義---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


# アップロードフォルダが存在しない場合は作成
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ユーザー読み込み
def load_users():
    if not os.path.exists(USER_FILE):
        return {}
    with open(USER_FILE, 'r') as f:
        return json.load(f)

# ユーザー保存
def save_users(users):
    with open(USER_FILE, 'w') as f:
        json.dump(users, f)


def load_local_kanji_data():
    try:
        with open(KANJI_JSON_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}



# JSONファイルから既存データを読み込み
def load_kanji_data():
    if os.path.exists(KANJI_JSON_PATH):
        with open(KANJI_JSON_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


# JSONファイルに新しい漢字データを保存
def save_kanji_to_local(kanji, data):
    kanji_data = load_local_kanji_data()
    kanji_data[kanji] = data
    with open(KANJI_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(kanji_data, f, ensure_ascii=False, indent=2)


def sanitize_filename(name):
    return re.sub(r'[\\/:"*?<>|]', '_', name)


# IPブロックリストの読み込み
def load_blocked_ips():
    if os.path.exists(IP_BLOCKLIST_FILE):
        with open(IP_BLOCKLIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []





# 不正アクセスIPログを追加
def log_blocked_ip(ip):
    entry = {"ip": ip, "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    logs = []
    if os.path.exists(IP_BLOCKLIST_FILE):
        with open(IP_BLOCKLIST_FILE, 'r', encoding='utf-8') as f:
            try:
                content = f.read().strip()
                if content:  # 空ファイルチェック
                    logs = json.loads(content)
            except json.JSONDecodeError:
                pass  # 壊れたJSONでもスキップ

    # 重複チェック
    if not any(entry['ip'] == log['ip'] for log in logs):
        logs.append(entry)
        with open(IP_BLOCKLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)



def log_server_access():
    log_entry = {
        "ip": request.remote_addr,
        "path": request.path,
        "method": request.method,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    log_file = "access_log.json"
    logs = []
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                pass
    logs.append(log_entry)
    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)


def is_ip_blocked(ip):
    blocked_entries = load_blocked_ips()
    blocked_ip = [entry['ip'] for entry in blocked_entries]
    return ip in blocked_ip


def contains_weird_chars(text):
    for ch in text:
        # ASCIIの制御文字（0x00～0x1Fと0x7F）や、非印刷文字を検出
        if ord(ch) < 32 or ord(ch) == 127:
            return True
    return False


def contains_binary_or_control_chars(s):
    return any(ord(c) < 32 or ord(c) == 127 for c in s)


# JSONファイルをロードする関数
def load_logs():
    try:
        with open(IP_LOG_FILE, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return []



BLOCKED_IPS = load_blocked_ips()


#以下htmlルート----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        
# トップページ

@app.route('/')
def index():
    keyword = request.args.get('q', '').strip().lower()
    cookie_accepted = session.get("cookie_accepted", False)  # ←★ここ追加

    articles = []
    for filename in os.listdir(ARTICLES_DIR):
        if filename.endswith('.html'):
            if keyword:
                filepath = os.path.join(ARTICLES_DIR, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                if keyword in filename.lower() or keyword in content:
                    articles.append(filename)
            else:
                articles.append(filename)

    uploaded_files = os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else []
    return render_template(
        'index.html',
        articles=articles,
        uploaded_files=uploaded_files,
        keyword=keyword,
        cookie_accepted=cookie_accepted  # ←★ここ渡す！
    )



#絞り込み処理
@app.route('/search')
def search():
    query = request.args.get('q', '').lower()
    search_type = request.args.get('type', 'article')

    all_articles = [f for f in os.listdir(ARTICLES_DIR) if f.endswith('.html')]
    all_files = os.listdir(UPLOAD_FOLDER)

    matched_functions = []

    if search_type == 'article':
        articles = [f for f in all_articles if query in f.lower()]
        uploaded_files = all_files
    elif search_type == 'feature':
        # h2 タイトルを小文字で比較
        matched_functions = [title for title in FUNCTION_TITLES if query in title.lower()]
        articles = all_articles
        uploaded_files = all_files
    else:
        articles = []
        uploaded_files = []

    return render_template(
        'index.html',
        articles=articles,
        uploaded_files=uploaded_files,
        matched_functions=matched_functions
    )



# 記事ページ
@app.route('/article/<filename>')
def article(filename):
    filepath = os.path.join(ARTICLES_DIR, filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return render_template('article.html', content=content, filename=filename)
    except FileNotFoundError:
        return "ファイルが見つかりません", 404

# ログインページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_users()
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username] == password:
            session['username'] = username
            return redirect(url_for('admin'))
        return 'ログイン失敗'
    return render_template('login.html')



# ログアウト
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))



# 管理画面
@app.route('/admin')
def admin():
    if 'username' not in session:
        return redirect(url_for('login'))

    articles = []
    for filename in os.listdir(ARTICLES_DIR):
        if filename.endswith('.html'):
            filepath = os.path.join(ARTICLES_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    title = f.readline().strip()
                articles.append({'filename': filename, 'title': title})
            except FileNotFoundError:
                print(f"警告: ファイルが見つかりません: {filename}") # ログ出力

    uploaded_files = os.listdir(UPLOAD_FOLDER)
    return render_template('admin.html', articles=articles, uploaded_files=uploaded_files)

#ユーザー追加
@app.route('/admin_add_user', methods=['GET', 'POST'])
def admin_add_user():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users = load_users()

        if username in users:
            return 'そのユーザー名はすでに存在します。'

        users[username] = password
        save_users(users)
        return redirect(url_for('admin'))

    return render_template('admin_add_user.html')

# 記事作成
@app.route('/create', methods=['GET', 'POST'])
def create():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        body = request.form['body']
        filename_raw = request.form['filename'].strip()
        filename = sanitize_filename(filename_raw)

        if not filename:
            return "ファイル名が無効です", 400

        path = os.path.join(ARTICLES_DIR, filename + '.html')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(title + '\n' + body)

        return redirect(url_for('admin'))

    return render_template('create.html')

# 記事編集
@app.route('/edit/<filename>', methods=['GET', 'POST'])
def edit(filename):
    if 'username' not in session:
        return redirect(url_for('login'))

    old_path = os.path.join(ARTICLES_DIR, filename)
    if not os.path.exists(old_path):
        return "ファイルが見つかりません", 404

    if request.method == 'POST':
        new_filename_raw = request.form['filename'].strip()
        new_filename = sanitize_filename(new_filename_raw) + '.html'

        title = request.form['title']
        body = request.form['body']

        new_path = os.path.join(ARTICLES_DIR, new_filename)

        # ファイル名が変更された場合は旧ファイルを削除
        if new_filename != filename:
            os.remove(old_path)

        with open(new_path, 'w', encoding='utf-8') as f:
            f.write(title + '\n' + body)

        return redirect(url_for('admin'))

    # 読み込み処理
    with open(old_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        title = lines[0].strip()
        body = ''.join(lines[1:])

    return render_template('edit.html', title=title, body=body, filename=filename.replace('.html', ''))

# 記事削除
@app.route('/delete/<filename>')
def delete(filename):
    if 'username' not in session:
        return redirect(url_for('login'))

    path = os.path.join(ARTICLES_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
    return redirect(url_for('admin'))

# アカウント設定画面
@app.route('/admin_settings', methods=['GET', 'POST'])
def admin_settings():
    if 'username' not in session:
        return redirect(url_for('login'))

    users = load_users()
    current_user = session['username']

    if request.method == 'POST':
        new_username = request.form['new_username']
        new_password = request.form['new_password']

        if new_username in users and new_username != current_user:
            return 'そのユーザー名はすでに存在します。'

        users.pop(current_user)
        users[new_username] = new_password
        save_users(users)

        session['username'] = new_username
        return redirect(url_for('admin'))

    return render_template('admin_settings.html', username=current_user)

# ファイルアップロード
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'username' not in session:
        return redirect(url_for('login'))
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return redirect(url_for('admin'))
    return '許可されていないファイル形式です'

# ファイルダウンロード
@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)



# 漢字検索ページ
@app.route('/kanji_lookup', methods=['GET', 'POST'])
def kanji_lookup():
    error = None
    result = None
    kanji = ''

    if request.method == 'POST':
        kanji = request.form.get('kanji', '').strip()

        if len(kanji) != 1:
            error = "1文字だけ入力してください。"
        else:
            kanji_data = load_kanji_data()
            if kanji in kanji_data:
                result = kanji_data[kanji]
            else:
                error = "指定された漢字のデータが見つかりません。"

        return render_template('kanji_result.html', kanji=kanji, data=result, error=error)

    return render_template('kanji_lookup.html')


# アクセス拒否（Forbidden）
@app.before_request
def harden_all_requests():
    ip = request.remote_addr
    path = request.full_path

    # 1. ブロックされたIP
    blocked_ips = [entry['ip'] for entry in load_blocked_ips()]
    if ip in blocked_ips:
        abort(403)




@app.route("/color-picker")
def ColorPicker():
    return render_template("color_picker.html")


@app.route('/omikuji', methods=['GET', 'POST'])
def omikuji():
    result = None
    if request.method == 'POST':
        outcomes = ['大吉', '中吉', '小吉', '末吉', '凶', '大凶']
        result = choice(outcomes)
    return render_template('omikuji.html', result=result) 


@app.route('/blocked_ips')
def blocked_ips():
    # 不正アクセスされたIPアドレスのリストを読み込む
    blocked_ips_list = load_blocked_ips()
    # blocked_ips.htmlというテンプレートにデータを渡して表示する
    return render_template('blocked_ips.html', blocked_ips=blocked_ips_list) 



# Cookie同意の処理
@app.route('/accept_cookies', methods=['POST'])
def accept_cookies():
    session['cookie_accepted'] = True
    return '', 200  # No Content レスポンス



@app.route('/source')
def show_source():
    try:
        with open(__file__, 'r', encoding='utf-8') as f:
            code = f.read()
        return render_template('source.html', code=code)
    except Exception as e:
        return f"読み込み失敗: {e}", 500


@app.route("/server_logs")
def server_logs():
    logs = load_logs()  # ログファイルからデータをロード
    return render_template("server_logs.html", logs=logs)




#以下エラー処理-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------



#400エラー
@app.errorhandler(400)
def add400(e):
    ip = request.remote_addr or '不明'
    now = datetime.now().strftime('%d/%b/%Y %H:%M:%S')

    new_entry = {"ip": ip, "timestamp": now}

    try:
        if os.path.exists(IP_LOG_FILE):
            with open(IP_LOG_FILE, 'r', encoding='utf-8') as f:
                ip_data = json.load(f)
        else:
            ip_data = []
    except Exception as read_error:
        ip_data = []

    ip_data.append(new_entry)

    try:
        with open(IP_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(ip_data, f, ensure_ascii=False, indent=2)
    except Exception as write_error:
        print(f"IPログ書き込みエラー: {write_error}")

    return render_template('error/400.html'), 400





#500エラー
@app.errorhandler(500)
def add500(e):
    ip = request.remote_addr or '不明'
    now = datetime.now().strftime('%d/%b/%Y %H:%M:%S')

    new_entry = {"ip": ip, "timestamp": now}

    try:
        if os.path.exists(IP_LOG_FILE):
            with open(IP_LOG_FILE, 'r', encoding='utf-8') as f:
                ip_data = json.load(f)
        else:
            ip_data = []
    except Exception as read_error:
        ip_data = []

    ip_data.append(new_entry)

    try:
        with open(IP_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(ip_data, f, ensure_ascii=False, indent=2)
    except Exception as write_error:
        print(f"IPログ書き込みエラー: {write_error}")

    return "500 Bad Request", 500







# 実行
if __name__ == '__main__':
    if not os.path.exists(ARTICLES_DIR):
        os.makedirs(ARTICLES_DIR)
    # HTTPでサーバーを起動
    app.run(debug=True, host='0.0.0.0', port=8000)