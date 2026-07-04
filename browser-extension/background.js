/**
 * 浏览器扩展后台脚本
 * 
 * 负责：
 * 1. 监听 Epic Games 页面访问
 * 2. 提取游戏库数据
 * 3. 通过 Native Messaging 发送到本地 MCP Server
 */

// 监听来自 content script 的消息
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'LIBRARY_DATA') {
    console.log('收到游戏库数据:', message.data.gameCount, '款游戏');
    
    // 保存到本地存储
    chrome.storage.local.set({
      lastSync: new Date().toISOString(),
      libraryData: message.data
    }, () => {
      console.log('✅ 游戏库数据已保存');
      sendResponse({ success: true });
    });
    
    // TODO: 通过 Native Messaging 发送到本地应用
    // sendToNativeApp(message.data);
    
    return true; // 保持消息通道开放
  }
});

// 定期检查同步状态
chrome.alarms?.create('syncCheck', {
  periodInMinutes: 60 // 每小时检查一次
});

chrome.alarms?.onAlarm.addListener((alarm) => {
  if (alarm.name === 'syncCheck') {
    checkSyncStatus();
  }
});

function checkSyncStatus() {
  chrome.storage.local.get(['lastSync'], (result) => {
    const lastSync = result.lastSync ? new Date(result.lastSync) : null;
    const now = new Date();
    
    if (!lastSync || (now - lastSync) > 24 * 60 * 60 * 1000) {
      console.log('⚠️ 超过 24 小时未同步，建议用户访问 Epic 官网');
      showNotification('建议同步游戏库');
    }
  });
}

function showNotification(message) {
  chrome.notifications?.create({
    type: 'basic',
    iconUrl: 'icons/icon48.png',
    title: 'AIPickMyGame Sync',
    message: message
  });
}

console.log('🚀 AIPickMyGame Sync 扩展已加载');
