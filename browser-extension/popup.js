/**
 * 弹出窗口脚本
 */

document.addEventListener('DOMContentLoaded', () => {
  loadSyncStatus();
  
  // 同步按钮
  document.getElementById('syncBtn').addEventListener('click', () => {
    triggerSync();
  });
  
  // 设置按钮
  document.getElementById('settingsBtn').addEventListener('click', () => {
    openSettings();
  });
});

/**
 * 加载同步状态
 */
function loadSyncStatus() {
  chrome.storage.local.get(['lastSync'], (result) => {
    const lastSync = result.lastSync;
    
    if (lastSync) {
      const date = new Date(lastSync);
      const timeStr = formatRelativeTime(date);
      document.getElementById('lastSync').textContent = timeStr;
    } else {
      document.getElementById('lastSync').textContent = '从未';
    }
  });
}

/**
 * 触发同步
 */
function triggerSync() {
  const btn = document.getElementById('syncBtn');
  btn.textContent = '⏳ 同步中...';
  btn.disabled = true;
  
  // 打开 Epic 游戏库页面
  chrome.tabs.create({
    url: 'https://www.epicgames.com/id/library'
  }, (tab) => {
    console.log('已打开 Epic 游戏库页面');
    
    setTimeout(() => {
      btn.textContent = '🔄 立即同步';
      btn.disabled = false;
    }, 2000);
  });
}

/**
 * 打开设置页面
 */
function openSettings() {
  chrome.runtime.openOptionsPage();
}

/**
 * 格式化相对时间
 */
function formatRelativeTime(date) {
  const now = new Date();
  const diff = now - date;
  
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  
  if (minutes < 1) {
    return '刚刚';
  } else if (minutes < 60) {
    return `${minutes} 分钟前`;
  } else if (hours < 24) {
    return `${hours} 小时前`;
  } else {
    return `${days} 天前`;
  }
}
