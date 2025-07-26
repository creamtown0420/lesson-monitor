from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import time
import threading
import smtplib
import requests
import os
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
CORS(app)

# プロキシのサブパス対応
app.config['APPLICATION_ROOT'] = '/scraper'

# グローバル変数で監視状態を管理
monitoring_active = False
monitoring_thread = None
MONITORING_STATE_FILE = 'monitoring_state.json'

def save_monitoring_state(state):
    """監視状態をファイルに保存"""
    try:
        with open(MONITORING_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"[INFO] 監視状態を保存しました: {MONITORING_STATE_FILE}")
    except Exception as e:
        print(f"[ERROR] 監視状態保存失敗: {e}")

def load_monitoring_state():
    """監視状態をファイルから読み込み"""
    try:
        if os.path.exists(MONITORING_STATE_FILE):
            with open(MONITORING_STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            print(f"[INFO] 監視状態を読み込みました: {len(state.get('selected_lessons', []))}件のレッスン")
            return state
    except Exception as e:
        print(f"[ERROR] 監視状態読み込み失敗: {e}")
    return None

def clear_monitoring_state():
    """監視状態ファイルを削除"""
    try:
        if os.path.exists(MONITORING_STATE_FILE):
            os.remove(MONITORING_STATE_FILE)
            print(f"[INFO] 監視状態ファイルを削除しました")
    except Exception as e:
        print(f"[ERROR] 監視状態ファイル削除失敗: {e}")

def restore_monitoring_on_startup():
    """サーバー起動時に監視状態を復旧"""
    global monitoring_active, monitoring_thread
    
    state = load_monitoring_state()
    if not state:
        return
    
    try:
        # 前回の監視が今日の日付かチェック
        target_date = state.get('date')
        today = datetime.now().strftime('%Y-%m-%d')
        
        if target_date != today:
            print(f"[INFO] 前回の監視日付({target_date})と今日({today})が異なるため、監視を復旧しません")
            clear_monitoring_state()
            return
        
        print("[INFO] 前回の監視状態を復旧中...")
        
        monitor = LessonMonitor(
            state['user_id'], state['password'], state['date'],
            state['notify_method'], state['interval'],
            state.get('email'), state.get('line_token'),
            state['selected_lessons']
        )
        
        monitoring_active = True
        monitoring_thread = threading.Thread(target=monitor.start_monitoring)
        monitoring_thread.daemon = False
        monitoring_thread.start()
        
        print(f"[INFO] 監視を復旧しました - 対象: {len(state['selected_lessons'])}件")
        
    except Exception as e:
        print(f"[ERROR] 監視復旧失敗: {e}")
        clear_monitoring_state()

class SeleniumGunzeScraper:
    """スポーツクラブサイトのスクレイパークラス"""
    
    def __init__(self):
        """Chrome WebDriverを初期化"""
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_experimental_option("detach", True)
        
        # ユニークなuser-data-dirを指定して競合を回避
        import tempfile
        import uuid
        temp_dir = tempfile.gettempdir()
        unique_id = str(uuid.uuid4())
        chrome_options.add_argument(f'--user-data-dir={temp_dir}/chrome_profile_{unique_id}')
        
        # 本番環境: ヘッドレスモードで安定動作を優先
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--remote-debugging-port=0')  # ポート競合を回避

        # ChromeDriverのパスを明示的に指定（必要に応じて）
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            print(f"[ERROR] ChromeDriver初期化失敗: {e}")
            # システムのchromedriver-autoinstallerを使用
            import chromedriver_autoinstaller
            chromedriver_autoinstaller.install()
            self.driver = webdriver.Chrome(options=chrome_options)

        # 自動化検出回避のためのステルス設定
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        stealth(
            self.driver,
            languages=["ja-JP", "en-US"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True
        )

        self.logged_in = False

    def login(self, username, password):
        """スポーツクラブサイトにログイン"""
        try:
            self.driver.get("https://www1.nesty-gcloud.net/gunzesports_mypage/")
            
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "会員番号"))
            )
            
            self.driver.find_element(By.NAME, "会員番号").send_keys(username)
            self.driver.find_element(By.NAME, "パスワード").send_keys(password)
            self.driver.find_element(By.ID, "DN10BtnLogin").click()

            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "menuItemAnchorWebPersonal"))
            )

            self.logged_in = True
            print(f"[INFO] ログイン成功: {username}")
            return True
            
        except Exception as e:
            print(f"[ERROR] ログイン失敗: {e}")
            return False

    def go_to_program_page_and_scrape(self, date_str):
        """指定日のレッスン情報を取得（scraper.pyと同じ構造）"""
        if not self.logged_in:
            raise Exception("ログインが必要です")

        try:
            self.driver.find_element(By.ID, "menuItemAnchorWebPersonal").click()
            time.sleep(0.5)

            windows = self.driver.window_handles
            self.driver.switch_to.window(windows[-1])

            prog_anchor = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "menuItemAnchor__sisetu3"))
            )
            prog_anchor.click()
            time.sleep(1)

            print("[INFO] プログラムページに到達 → スクレイピング準備完了")

            lessons = []
            panel_parent = self.driver.find_element(By.ID, f"Q060CalendarDate__{date_str}")
            panels = panel_parent.find_elements(By.CLASS_NAME, "Q060_calendar_panel_yotei")

            print(f"[INFO] 指定日({date_str})のパネル数: {len(panels)}")
            for i, panel in enumerate(panels):
                try:
                    text = panel.text.strip()
                    if len(text) < 5:
                        continue
                    time_part = text[:5]
                    name_part = text[5:].strip()
                    
                    # 括弧内の数字で空き状況を判定
                    status = 'unknown'
                    if '(' in text and ')' in text:
                        # 括弧内は残り枠数 例: 30メガダンス(37) → 37が残り枠数
                        import re
                        match = re.search(r'\((\d+)\)', text)
                        if match:
                            remaining = int(match.group(1))
                            print(f"[DEBUG] テキスト: '{text}' → 残り枠数: {remaining}")
                            if remaining == 0:
                                status = '満員'
                            elif remaining <= 3:
                                status = '残りわずか'
                            else:
                                status = '空きあり'
                            print(f"[DEBUG] ステータス判定: {status}")
                        else:
                            print(f"[DEBUG] 括弧内数字が見つからない - テキスト: '{text}'")
                    
                    lessons.append({
                        'id': f'selenium_{i+1}',
                        'time': time_part,
                        'name': name_part,
                        'status': status
                    })
                except Exception as ex:
                    print(f"[WARN] パネル処理エラー: {ex}")
                    continue

            for lesson in lessons:
                print(f"{lesson['time']} {lesson['name']}")

            return lessons

        except Exception as e:
            print(f"[ERROR] プログラムページ遷移・取得失敗: {e}")
            return []

    def quit(self):
        """WebDriverを終了"""
        try:
            self.driver.quit()
        except:
            pass

class NotificationService:
    """通知サービスクラス"""
    
    @staticmethod
    def send_email(to_email, subject, body):
        """メール通知を送信"""
        try:
            from_email = os.getenv("GMAIL_EMAIL")
            from_password = os.getenv("GMAIL_PASSWORD")
            
            if not from_email or not from_password:
                print("[WARN] メール認証情報が設定されていません")
                return False

            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(from_email, from_password)
            server.send_message(msg)
            server.quit()

            print(f"[INFO] メール通知送信成功: {to_email}")
            return True
            
        except Exception as e:
            print(f"[ERROR] メール送信失敗: {e}")
            return False

    @staticmethod
    def send_line(message, line_token):
        """LINE通知を送信"""
        try:
            if not line_token:
                print("[WARN] LINE Notifyトークンが設定されていません")
                return False

            url = "https://notify-api.line.me/api/notify"
            headers = {"Authorization": f"Bearer {line_token}"}
            data = {"message": message}

            response = requests.post(url, headers=headers, data=data)

            if response.status_code == 200:
                print("[INFO] LINE通知送信成功")
                return True
            else:
                print(f"[ERROR] LINE通知送信失敗: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"[ERROR] LINE通知送信失敗: {e}")
            return False

class LessonMonitor:
    """レッスン監視クラス"""
    
    def __init__(self, user_id, password, date, notify_method, interval_minutes, 
                 email=None, line_token=None, selected_lessons=None):
        self.user_id = user_id
        self.password = password
        self.date = date
        self.notify_method = notify_method
        self.interval_minutes = interval_minutes
        self.email = email
        self.line_token = line_token
        self.selected_lessons = selected_lessons or []
        self.previous_lessons = {}

    def start_monitoring(self):
        """監視を開始"""
        global monitoring_active
        
        print(f"[INFO] 監視開始: {self.date}, 間隔: {self.interval_minutes}分")
        if self.selected_lessons:
            print(f"[INFO] 監視対象レッスン: {len(self.selected_lessons)}件")

        while monitoring_active:
            try:
                # レッスン情報を取得
                lessons = self._get_current_lessons()
                
                # 監視対象レッスンを特定
                target_lessons = self._get_target_lessons(lessons)
                
                # 変化をチェックして通知
                self._check_and_notify(target_lessons)
                
                print(f"[INFO] 監視更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 対象{len(target_lessons)}件を確認")
                
                # 指定間隔で待機
                time.sleep(self.interval_minutes * 60)
                
            except Exception as e:
                print(f"[ERROR] 監視中にエラー: {e}")
                time.sleep(60)

        print("[INFO] 監視終了")

    def _get_current_lessons(self):
        """現在のレッスン情報を取得"""
        scraper = SeleniumGunzeScraper()
        try:
            if not scraper.login(self.user_id, self.password):
                raise Exception("ログイン失敗")
            
            # 日付をYYYYMMDD形式に変換
            date_str = self.date.replace('-', '')  # YYYY-MM-DD → YYYYMMDD
            lessons = scraper.go_to_program_page_and_scrape(date_str)
            return lessons
        finally:
            scraper.quit()

    def _get_target_lessons(self, lessons):
        """監視対象のレッスンを取得"""
        if not self.selected_lessons:
            return lessons
        
        target_lessons = []
        for lesson_index in self.selected_lessons:
            if lesson_index < len(lessons):
                target_lessons.append(lessons[lesson_index])
        
        return target_lessons

    def _check_and_notify(self, target_lessons):
        """レッスンの変化をチェックして通知"""
        for lesson in target_lessons:
            lesson_id = lesson['id']
            current_status = lesson.get('status', 'unknown')
            
            if lesson_id in self.previous_lessons:
                prev_status = self.previous_lessons[lesson_id].get('status', 'unknown')
                
                # 満席・残りわずか → 空き有り の変化を検出
                if (prev_status in ["満席", "残りわずか"]) and current_status == "空き有り":
                    self._send_notification(lesson, prev_status, current_status)
            else:
                # 初回監視時：空きがあるレッスンは即座に通知（オプション）
                if current_status == "空き有り":
                    self._send_initial_notification(lesson)
            
            self.previous_lessons[lesson_id] = lesson

    def _send_initial_notification(self, lesson):
        """初回監視時の通知（空きがあるレッスン）"""
        message = (f"📋【監視開始】📋\n\n"
                  f"📚 レッスン: {lesson['name']}\n"
                  f"🕒 時間: {lesson['time']}\n"
                  f"📊 現在の状況: {lesson['status']}\n\n"
                  f"✅ このレッスンは現在空きがあります\n"
                  f"🔗 https://www1.nesty-gcloud.net/gunzesports_mypage/")
        
        print(f"[INFO] 初回通知: {lesson['name']} (現在{lesson['status']})")
        
        if self.notify_method == "email" and self.email:
            NotificationService.send_email(
                self.email, 
                "📋 スポーツクラブ 監視開始通知", 
                message
            )
        elif self.notify_method == "line" and self.line_token:
            NotificationService.send_line(message, self.line_token)

    def _send_notification(self, lesson, prev_status, current_status):
        """通知を送信"""
        message = (f"🚨【空きが出ました！】🚨\n\n"
                  f"📚 レッスン: {lesson['name']}\n"
                  f"🕒 時間: {lesson['time']}\n"
                  f"📊 状況: {prev_status} → {current_status}\n\n"
                  f"💨 すぐに予約サイトをチェックしてください！\n"
                  f"🔗 https://www1.nesty-gcloud.net/gunzesports_mypage/")
        
        print(f"[ALERT] 空き検出: {lesson['name']} ({prev_status} → {current_status})")
        
        if self.notify_method == "email" and self.email:
            NotificationService.send_email(
                self.email, 
                "🚨 スポーツクラブ レッスン空き通知", 
                message
            )
        elif self.notify_method == "line" and self.line_token:
            NotificationService.send_line(message, self.line_token)

# Flask APIエンドポイント
@app.route('/')
def index():
    """メインページ"""
    try:
        import os
        frontend_path = os.path.join(os.path.dirname(__file__), '../frontend/index.html')
        with open(frontend_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return '''
        <!DOCTYPE html>
        <html><head><title>スポーツクラブ レッスン監視</title></head>
        <body><h1>フロントエンドファイルが見つかりません</h1>
        <p>frontend/index.html を配置してください</p></body></html>
        '''

@app.route('/style.css')
@app.route('/scraper/style.css')
def serve_css():
    """CSSファイルを提供"""
    import os
    try:
        frontend_path = os.path.join(os.path.dirname(__file__), '../frontend')
        print(f"Frontend path: {frontend_path}")
        print(f"Absolute path: {os.path.abspath(frontend_path)}")
        print(f"CSS file exists: {os.path.exists(os.path.join(frontend_path, 'style.css'))}")
        return send_from_directory(frontend_path, 'style.css', mimetype='text/css')
    except Exception as e:
        print(f"Error serving CSS: {e}")
        return str(e), 500

@app.route('/script.js')
@app.route('/scraper/script.js')  
def serve_js():
    """JavaScriptファイルを提供"""
    import os
    return send_from_directory(os.path.join(os.path.dirname(__file__), '../frontend'), 'script.js', mimetype='application/javascript')

@app.route('/api/scrape_lessons', methods=['POST'])
def api_scrape_lessons():
    """レッスン情報取得API（フロントエンド用）"""
    try:
        data = request.get_json()
        user_id = data.get('userId')
        password = data.get('password')
        date = data.get('date')
        
        if not user_id or not password or not date:
            return jsonify({"error": "必要な情報が不足しています"}), 400

        # レッスン情報を取得
        scraper = SeleniumGunzeScraper()
        try:
            if not scraper.login(user_id, password):
                return jsonify({"error": "ログインに失敗しました"}), 401
            
            # 日付をYYYYMMDD形式に変換
            date_str = date.replace('-', '')  # YYYY-MM-DD → YYYYMMDD
            lessons = scraper.go_to_program_page_and_scrape(date_str)
            
            return jsonify({
                "lessons": lessons,
                "message": f"{len(lessons)}件のレッスンを取得しました"
            })
        finally:
            scraper.quit()
        
    except Exception as e:
        print(f"[ERROR] API scrape_lessons エラー: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"エラーが発生しました: {str(e)}"}), 500

@app.route('/api/start_monitoring', methods=['POST'])
def api_start_monitoring():
    """レッスン情報取得・監視開始API"""
    global monitoring_active, monitoring_thread
    
    try:
        data = request.get_json()
        user_id = data.get('userId')
        password = data.get('password')
        date = data.get('date')
        interval = data.get('interval', 5)
        notification = data.get('notification', {})
        selected_lessons = data.get('lessons', [])
        
        if not user_id or not password or not date:
            return jsonify({"error": "必要な情報が不足しています"}), 400
            
        if not selected_lessons:
            return jsonify({"error": "監視対象のレッスンを選択してください"}), 400

        # 既存の監視を停止
        monitoring_active = False
        if monitoring_thread and monitoring_thread.is_alive():
            monitoring_thread.join(timeout=5)

        # 監視開始
        email = notification.get('email')
        line_token = notification.get('lineToken')
        notify_method = notification.get('method', 'none')
        
        monitor = LessonMonitor(
            user_id, password, date, notify_method, interval,
            email, line_token, selected_lessons
        )
        
        monitoring_active = True
        monitoring_thread = threading.Thread(target=monitor.start_monitoring)
        monitoring_thread.daemon = False  # daemonをFalseにして独立したプロセスとして実行
        monitoring_thread.start()
        
        # 監視状態をファイルに保存（サーバー再起動時の復旧用）
        save_monitoring_state({
            'user_id': user_id,
            'password': password,
            'date': date,
            'notify_method': notify_method,
            'interval': interval,
            'email': email,
            'line_token': line_token,
            'selected_lessons': selected_lessons,
            'started_at': datetime.now().isoformat()
        })
        
        message = f"監視を開始しました（間隔: {interval}分）"
        message += f" - 監視対象: {len(selected_lessons)}件のレッスン"
        
        return jsonify({
            "monitoring": True,
            "message": message
        })
        
    except Exception as e:
        print(f"[ERROR] API scrape_lessons エラー: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"エラーが発生しました: {str(e)}"}), 500

@app.route('/api/stop_monitoring', methods=['POST'])
def api_stop_monitoring():
    """監視停止API"""
    global monitoring_active, monitoring_thread
    
    monitoring_active = False
    
    if monitoring_thread and monitoring_thread.is_alive():
        monitoring_thread.join(timeout=5)
    
    # 監視状態ファイルをクリア
    clear_monitoring_state()
    
    return jsonify({"message": "監視を停止しました"})

@app.route('/api/monitoring_status', methods=['GET'])
def api_monitoring_status():
    """監視状態確認API"""
    global monitoring_active, monitoring_thread
    
    is_active = monitoring_active and monitoring_thread and monitoring_thread.is_alive()
    
    return jsonify({
        "monitoring": is_active,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

if __name__ == '__main__':
    print("🚀 スポーツクラブ レッスン監視システム起動中...")
    print("📱 ブラウザで http://127.0.0.1:5000 にアクセスしてください")
    
    # サーバー起動時に前回の監視状態を復旧
    restore_monitoring_on_startup()
    
    app.run(host="0.0.0.0", debug=True, port=5000)