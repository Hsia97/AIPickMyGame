/**
 * Epic Games 内容脚本
 * 
 * 在用户访问 Epic 游戏库页面时自动提取游戏数据
 */

(function() {
  'use strict';
  
  console.log('📖 AIPickMyGame: Epic 内容脚本已注入');
  
  // 等待页面加载完成
  window.addEventListener('load', () => {
    setTimeout(extractLibrary, 3000); // 等待 3 秒确保动态内容加载
  });
  
  /**
   * 从 Epic 游戏库页面提取游戏数据
   */
  async function extractLibrary() {
    try {
      console.log('🔍 开始提取 Epic 游戏库...');
      
      // 方法 1: 拦截网络请求获取 API 数据
      const games = await interceptAPI();
      
      if (games && games.length > 0) {
        console.log(`✅ 成功提取 ${games.length} 款游戏`);
        sendToBackground(games);
        return;
      }
      
      // 方法 2: 从 DOM 提取（备用方案）
      const domGames = extractFromDOM();
      if (domGames.length > 0) {
        console.log(`✅ 从 DOM 提取到 ${domGames.length} 款游戏`);
        sendToBackground(domGames);
      } else {
        console.warn('⚠️ 未找到游戏数据，请确保在正确的页面');
      }
      
    } catch (error) {
      console.error('❌ 提取游戏库失败:', error);
    }
  }
  
  /**
   * 拦截 Epic API 请求获取游戏库
   */
  async function interceptAPI() {
    return new Promise((resolve) => {
      const games = [];
      let requestCount = 0;
      const maxWaitTime = 10000; // 最多等待 10 秒
      
      // 监听 fetch 请求
      const originalFetch = window.fetch;
      window.fetch = async function(...args) {
        const response = await originalFetch.apply(this, args);
        
        // 检查是否是游戏库 API
        if (args[0] && args[0].includes('graphql.epicgames.com')) {
          const clone = response.clone();
          clone.json().then(data => {
            if (data.data?.Catalog?.searchStore?.elements) {
              const elements = data.data.Catalog.searchStore.elements;
              elements.forEach(element => {
                if (isValidGame(element)) {
                  games.push(parseGame(element));
                }
              });
            }
          }).catch(() => {});
        }
        
        return response;
      };
      
      // 触发页面刷新以捕获请求
      setTimeout(() => {
        resolve(games);
      }, maxWaitTime);
    });
  }
  
  /**
   * 从 DOM 提取游戏数据（备用方案）
   */
  function extractFromDOM() {
    const games = [];
    
    // 查找游戏卡片元素
    const gameCards = document.querySelectorAll('[data-testid="titled-card"]');
    
    gameCards.forEach(card => {
      const titleElement = card.querySelector('h3, [class*="title"]');
      const imageElement = card.querySelector('img');
      
      if (titleElement) {
        games.push({
          id: generateId(),
          title: titleElement.textContent.trim(),
          cover_url: imageElement?.src || null,
          platform: 'epic',
          added_at: new Date().toISOString()
        });
      }
    });
    
    return games;
  }
  
  /**
   * 判断是否为有效游戏
   */
  function isValidGame(element) {
    const categories = element.categories || [];
    const categoryPaths = categories.map(cat => cat.path || '');
    
    // 排除非游戏内容
    const excludeKeywords = ['applications', 'dlc', 'mods', 'themes', 'assets'];
    
    for (const keyword of excludeKeywords) {
      if (categoryPaths.some(path => path.toLowerCase().includes(keyword))) {
        return false;
      }
    }
    
    return !!element.title;
  }
  
  /**
   * 解析游戏数据
   */
  function parseGame(element) {
    const keyImages = element.keyImages || [];
    const coverImage = keyImages.find(img => 
      img.type === 'Thumbnail' || img.type === 'DieselStoreFrontWide'
    );
    
    const categories = element.categories || [];
    const genres = categories
      .filter(cat => cat.path && cat.path.startsWith('/public/'))
      .map(cat => cat.path.replace('/public/', '').replace('/', ' ').trim())
      .slice(0, 5);
    
    return {
      id: element.id,
      title: element.title,
      namespace: element.namespace,
      catalog_item_id: element.catalogItemId,
      cover_url: coverImage?.url || null,
      genres: genres,
      release_date: element.releaseDate?.date || null,
      developer: element.developer?.name || null,
      platform: 'epic',
      added_at: new Date().toISOString()
    };
  }
  
  /**
   * 生成唯一 ID
   */
  function generateId() {
    return 'epic_' + Math.random().toString(36).substr(2, 9);
  }
  
  /**
   * 发送数据到后台脚本
   */
  function sendToBackground(games) {
    chrome.runtime.sendMessage({
      type: 'LIBRARY_DATA',
      data: {
        platform: 'epic',
        gameCount: games.length,
        games: games,
        extractedAt: new Date().toISOString()
      }
    });
  }
  
})();
