// グローバル変数
let selectedLessons = [];
let monitoringInterval = null;
let isMonitoring = false;

document.addEventListener("DOMContentLoaded", function () {
  initializeEventListeners();
  updateUIState();
  setDefaultDate();
});

function initializeEventListeners() {
  // フォーム送信（レッスン検索）
  document.getElementById("lessonForm").addEventListener("submit", handleLessonSearch);
  
  // 通知方法変更
  document.getElementById("notifyMethod").addEventListener("change", handleNotificationMethodChange);
  
  // 監視制御ボタン
  document.getElementById("startMonitoring").addEventListener("click", startMonitoring);
  document.getElementById("stopMonitoring").addEventListener("click", stopMonitoring);
  document.getElementById("clearSelection").addEventListener("click", clearSelection);
  
  // レッスンアイテムクリック（イベント委譲）
  document.getElementById("lessonList").addEventListener("click", handleLessonClick);
}

// レッスンアイテムクリック処理（イベント委譲）
function handleLessonClick(event) {
  const lessonItem = event.target.closest('.lesson-item');
  if (!lessonItem) return;
  
  const id = lessonItem.dataset.lessonId;
  const name = lessonItem.dataset.lessonName;
  const time = lessonItem.dataset.lessonTime;
  const status = lessonItem.dataset.lessonStatus;
  
  console.log("Lesson clicked via event delegation:", { id, name, time, status });
  
  if (id && name && time && status) {
    toggleLessonSelection(id, name, time, status);
  }
}

// デフォルト日付設定（今日）
function setDefaultDate() {
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('date').value = today;
}

// レッスン検索処理
async function handleLessonSearch(e) {
  e.preventDefault();
  
  const formData = new FormData(e.target);
  const searchData = {
    userId: formData.get("userId"),
    password: formData.get("password"),
    date: formData.get("date")
  };

  // ローディング状態
  const submitBtn = e.target.querySelector('button[type="submit"]');
  const originalText = submitBtn.innerHTML;
  submitBtn.innerHTML = '🔄 検索中...';
  submitBtn.disabled = true;
  submitBtn.classList.add('loading');

  try {
    const response = await fetch("/api/scrape_lessons", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(searchData)
    });

    if (!response.ok) {
      throw new Error("レッスン取得に失敗しました");
    }

    const result = await response.json();
    displayLessons(result.lessons || []);
    showToast("レッスン情報を取得しました", "success");
    
  } catch (err) {
    showToast("エラー: " + err.message, "error");
  } finally {
    submitBtn.innerHTML = originalText;
    submitBtn.disabled = false;
    submitBtn.classList.remove('loading');
  }
}

// レッスン一覧表示
function displayLessons(lessons) {
  const lessonList = document.getElementById("lessonList");
  
  // デバッグ情報を表示
  console.log("取得したレッスン数:", lessons.length);
  console.log("レッスンデータ:", lessons);
  
  if (lessons.length === 0) {
    lessonList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">❌</div>
        <p>該当するレッスンがありません</p>
        <p style="font-size: 0.8rem; color: #666; margin-top: 10px;">
          デバッグ: レッスン配列の長さ = ${lessons.length}
        </p>
      </div>
    `;
    return;
  }

  // レッスン情報に詳細なデバッグ情報を追加
  lessonList.innerHTML = `
    <div style="background: #f0f8ff; padding: 10px; margin-bottom: 15px; border-radius: 5px; font-size: 0.85rem;">
      <strong>📊 デバッグ情報:</strong><br>
      取得したレッスン数: ${lessons.length}件<br>
      データ例: ${JSON.stringify(lessons[0] || {}, null, 2)}
    </div>
  ` + lessons.map((lesson) => {
    return `
    <div class="lesson-item" 
         data-lesson-id="${lesson.id}" 
         data-lesson-name="${lesson.name}" 
         data-lesson-time="${lesson.time}" 
         data-lesson-status="${lesson.status}"
         style="cursor: pointer; border: 2px solid transparent;" 
         onmouseover="this.style.borderColor='#6366f1'" 
         onmouseout="this.style.borderColor='transparent'">
      <div class="lesson-info">
        <h4>⏰ ${lesson.time || 'N/A'}</h4>
        <p>📚 ${lesson.name || 'N/A'}</p>
        <small style="color: #888;">ID: ${lesson.id}, Status: ${lesson.status}</small>
      </div>
      <div class="lesson-status ${lesson.status === '空きあり' ? 'status-available' : (lesson.status === '残りわずか' ? 'status-warning' : (lesson.status === '満員' ? 'status-full' : 'status-unknown'))}">
        ${lesson.status === '空きあり' ? '✅ 空きあり' : 
          lesson.status === '残りわずか' ? '⚠️ 残りわずか' : 
          lesson.status === '満員' ? '❌ 満員' : '❓ 不明'}
      </div>
    </div>
    `;
  }).join('');
}

// レッスン選択/解除
function toggleLessonSelection(id, name, time, status) {
  console.log("toggleLessonSelection called:", { id, name, time, status });
  
  const existingIndex = selectedLessons.findIndex(lesson => lesson.id === id);
  console.log("existingIndex:", existingIndex);
  console.log("selectedLessons before:", selectedLessons);
  
  if (existingIndex > -1) {
    selectedLessons.splice(existingIndex, 1);
    showToast(`${name} を監視対象から削除しました`, "info");
  } else {
    selectedLessons.push({ id, name, time, status });
    showToast(`${name} を監視対象に追加しました`, "success");
  }
  
  console.log("selectedLessons after:", selectedLessons);
  updateSelectedLessonsDisplay();
  updateUIState();
}

// 選択されたレッスン表示更新
function updateSelectedLessonsDisplay() {
  const container = document.getElementById("selectedLessons");
  
  if (selectedLessons.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📝</div>
        <p>レッスンを選択してください</p>
      </div>
    `;
    return;
  }

  container.innerHTML = selectedLessons.map(lesson => {
    return `
    <div class="selected-lesson">
      <div>
        <div style="font-weight: 600; margin-bottom: 0.25rem;">⏰ ${lesson.time}</div>
        <div style="color: var(--gray-600); font-size: 0.875rem;">📚 ${lesson.name}</div>
      </div>
      <button type="button" class="btn btn-danger remove-lesson-btn" 
              style="padding: 0.5rem; font-size: 0.75rem;" 
              data-lesson-id="${lesson.id}" 
              data-lesson-name="${lesson.name}" 
              data-lesson-time="${lesson.time}" 
              data-lesson-status="${lesson.status}">
        🗑️
      </button>
    </div>
    `;
  }).join('');
  
  // 削除ボタンのイベントリスナーを追加
  container.querySelectorAll('.remove-lesson-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const id = this.dataset.lessonId;
      const name = this.dataset.lessonName;
      const time = this.dataset.lessonTime;
      const status = this.dataset.lessonStatus;
      toggleLessonSelection(id, name, time, status);
    });
  });
}

// 通知方法変更処理
function handleNotificationMethodChange(e) {
  const method = e.target.value;
  const emailSettings = document.getElementById("emailSettings");
  const lineSettings = document.getElementById("lineSettings");
  
  emailSettings.style.display = method === "email" ? "block" : "none";
  lineSettings.style.display = method === "line" ? "block" : "none";
}

// 監視開始
async function startMonitoring() {
  const notifyMethod = document.getElementById("notifyMethod").value;
  const interval = parseInt(document.getElementById("interval").value) || 5;
  
  // 必須パラメータを取得
  const userId = document.getElementById("userId").value;
  const password = document.getElementById("password").value;
  const date = document.getElementById("date").value;
  
  if (!userId || !password || !date) {
    showToast("ユーザーID、パスワード、日付が必要です", "error");
    return;
  }
  
  if (selectedLessons.length === 0) {
    showToast("監視対象のレッスンを選択してください", "error");
    return;
  }
  
  let notificationConfig = {
    method: notifyMethod
  };

  // 通知設定の検証
  if (notifyMethod === "email") {
    const emailAddress = document.getElementById("emailAddress").value;
    if (!emailAddress) {
      showToast("メールアドレスを入力してください", "error");
      return;
    }
    notificationConfig.email = emailAddress;
  } else if (notifyMethod === "line") {
    const lineToken = document.getElementById("lineToken").value;
    if (!lineToken) {
      showToast("LINE Notifyトークンを入力してください", "error");
      return;
    }
    notificationConfig.lineToken = lineToken;
  }

  const startBtn = document.getElementById("startMonitoring");
  startBtn.innerHTML = '🔄 開始中...';
  startBtn.disabled = true;

  try {
    const response = await fetch("/api/start_monitoring", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        userId: userId,
        password: password,
        date: date,
        lessons: selectedLessons,
        notification: notificationConfig,
        interval: interval
      })
    });

    if (!response.ok) {
      throw new Error("監視開始に失敗しました");
    }

    isMonitoring = true;
    updateMonitoringStatus();
    showToast("監視を開始しました", "success");
    
    // 定期的にステータス更新
    monitoringInterval = setInterval(updateMonitoringStatus, 30000);
    
  } catch (err) {
    showToast("エラー: " + err.message, "error");
  } finally {
    startBtn.innerHTML = '🚀 監視開始';
    startBtn.disabled = false;
    updateUIState();
  }
}

// 監視停止
async function stopMonitoring() {
  const stopBtn = document.getElementById("stopMonitoring");
  stopBtn.innerHTML = '🔄 停止中...';
  stopBtn.disabled = true;

  try {
    const response = await fetch("/api/stop_monitoring", {
      method: "POST"
    });

    if (!response.ok) {
      throw new Error("監視停止に失敗しました");
    }

    isMonitoring = false;
    if (monitoringInterval) {
      clearInterval(monitoringInterval);
      monitoringInterval = null;
    }
    
    updateMonitoringStatus();
    showToast("監視を停止しました", "info");
    
  } catch (err) {
    showToast("エラー: " + err.message, "error");
  } finally {
    stopBtn.innerHTML = '⏹️ 監視停止';
    stopBtn.disabled = false;
    updateUIState();
  }
}

// 選択クリア
function clearSelection() {
  selectedLessons = [];
  updateSelectedLessonsDisplay();
  updateUIState();
  showToast("選択をクリアしました", "info");
}

// UI状態更新
function updateUIState() {
  const startBtn = document.getElementById("startMonitoring");
  const stopBtn = document.getElementById("stopMonitoring");
  
  if (isMonitoring) {
    startBtn.style.display = "none";
    stopBtn.style.display = "inline-flex";
  } else {
    startBtn.style.display = "inline-flex";
    stopBtn.style.display = "none";
    startBtn.disabled = selectedLessons.length === 0;
  }
}

// 監視ステータス更新
async function updateMonitoringStatus() {
  try {
    const response = await fetch("/api/monitoring_status");
    if (response.ok) {
      const status = await response.json();
      updateMonitoringStatusDisplay(status);
    }
  } catch (err) {
    console.error("ステータス取得エラー:", err);
  }
}

// 監視ステータス表示更新
function updateMonitoringStatusDisplay(status) {
  const statusDiv = document.getElementById("monitoringStatus");
  
  if (status && status.isRunning) {
    statusDiv.className = "status-card status-running";
    statusDiv.innerHTML = `
      <div class="status-title">🔄 監視実行中</div>
      <div class="status-description">
        📊 監視対象: ${status.lessonCount || 0}件<br>
        ⏱️ 次回チェック: ${formatNextCheck(status.nextCheck)}<br>
        📧 最終チェック: ${formatLastCheck(status.lastCheck)}
      </div>
    `;
  } else {
    statusDiv.className = "status-card status-stopped";
    statusDiv.innerHTML = `
      <div class="status-title">⏸️ 監視停止中</div>
      <div class="status-description">レッスンの監視は行われていません</div>
    `;
  }
}

// トースト通知表示
function showToast(message, type = "info") {
  // 既存のトーストを削除
  const existingToast = document.querySelector('.toast');
  if (existingToast) {
    existingToast.remove();
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  let icon = '';
  switch (type) {
    case "success":
      icon = '✅';
      break;
    case "error":
      icon = '❌';
      break;
    case "info":
    default:
      icon = 'ℹ️';
      break;
  }
  
  toast.innerHTML = `${icon} ${message}`;
  document.body.appendChild(toast);
  
  // 4秒後に自動削除
  setTimeout(() => {
    if (toast.parentNode) {
      toast.remove();
    }
  }, 4000);
}

// ユーティリティ関数
function formatNextCheck(timestamp) {
  if (!timestamp) return "未定";
  try {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('ja-JP');
  } catch {
    return "未定";
  }
}

function formatLastCheck(timestamp) {
  if (!timestamp) return "未実行";
  try {
    const date = new Date(timestamp);
    return date.toLocaleString('ja-JP');
  } catch {
    return "未実行";
  }
}

// ページロード時にステータスチェック
window.addEventListener('load', () => {
  updateMonitoringStatus();
});