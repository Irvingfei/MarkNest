/* MarkNest for TOS - translations.

   Three dictionaries with identical key sets. Parity is not a style preference:
   translate() falls back to the default language, so a key present in one
   dictionary and missing in another shows an English sentence inside a Chinese
   interface instead of failing. tools/webui_check.js compares the key sets
   mechanically so that cannot happen quietly.

   Keys are namespaced `area.subject`. `t()` returns the key itself when it is
   missing, which makes an omission show up as `editor.foo` on screen rather
   than as blank space. */

(function (global) {
  'use strict';

  var STRINGS = {
    'zh-cn': {
      'app.name': 'MarkNest 笔记',
      'app.subtitle': 'NAS 上的 Markdown 笔记库',

      'common.language': '语言',
      'common.refresh': '刷新',
      'common.loading': '加载中…',
      'common.empty': '暂无内容',
      'common.unknown': '未知',
      'common.retryAction': '重试',
      'common.close': '关闭',
      'common.cancel': '取消',
      'common.confirm': '确定',

      'home.open': '打开文件',
      'home.new': '新建文件',
      'home.recent': '最近文件',
      'home.noRecent': '还没有笔记',
      'home.timeJustNow': '刚刚',
      'home.timeMinutes': '{n} 分钟前',
      'home.timeHours': '{n} 小时前',
      'home.timeYesterday': '昨天',
      'home.timeDays': '{n} 天前',

      'nav.home': '主页',
      'nav.newNote': '新建文件',
      'nav.openNote': '打开文件',
      'nav.more': '更多',

      'tree.ariaLabel': '笔记目录树',
      'tree.refreshTitle': '刷新目录树',
      'tree.empty': '还没有笔记，点上方「☰」新建一篇',
      'tree.unsupported': '非笔记文件',
      'tree.untitled': '未命名',
      'tree.readOnly': '只读',
      'tree.notWritable': '该文件夹不可写入',
      'tree.newNotePrompt': '新笔记的路径（可含子目录）',
      'tree.newNoteDefault': '未命名.md',
      'tree.renamePrompt': '新的路径',
      'tree.rename': '重命名',
      'tree.delete': '删除',
      'tree.deleteConfirm': '确定删除「{name}」？此操作不可撤销。',
      'tree.created': '已创建 {name}',
      'tree.renamed': '已重命名',
      'tree.deleted': '已删除 {name}',

      'picker.title': '打开文件',
      'picker.library': '笔记库',
      'picker.local': '本机文件',
      'picker.browse': '选择本机文件…',
      'picker.localHint': '选择本机文件后将导入到笔记库，成为一篇普通笔记。',
      'picker.readFailed': '无法读取该文件',
      'picker.badType': '只能选择文本笔记（.md / .markdown / .mdown / .txt）',

      'editor.title': '编辑',
      'editor.ariaLabel': 'Markdown 编辑器',
      'editor.save': '保存',
      'editor.togglePreview': '预览',
      'editor.noNote': '未打开笔记',
      'editor.saved': '已保存',
      'editor.saving': '保存中…',
      'editor.dirty': '有未保存的修改',
      'editor.readOnly': '这篇笔记当前不可写入',
      'editor.conflict': '这篇笔记已被他人修改，你的改动没有保存',
      'editor.overwrite': '覆盖对方改动',
      'editor.reload': '放弃我的改动并重新载入',
      'editor.saveCopy': '另存为副本',
      'editor.loaded': '已打开 {name}',

      'format.ariaLabel': '格式工具栏',
      'format.bold': '加粗',
      'format.italic': '斜体',
      'format.code': '行内代码',
      'format.codeblock': '代码块',
      'format.quote': '引用',
      'format.h1': '一级标题',
      'format.h2': '二级标题',
      'format.h3': '三级标题',
      'format.task': '任务',
      'format.bullet': '无序列表',
      'format.numbered': '有序列表',
      'format.link': '链接',
      'format.table': '表格',
      'format.linkPrompt': '链接地址',
      'format.linkTextPrompt': '显示文字',

      'preview.title': '预览',
      'preview.ariaLabel': 'Markdown 预览',
      'preview.empty': '打开一篇笔记即可预览',

      'search.placeholder': '搜索笔记…',
      'search.results': '找到 {n} 篇',
      'search.none': '没有匹配的笔记',
      'search.clear': '清除搜索',
      'search.engineFts': '全文索引',
      'search.engineScan': '逐篇扫描',

      'status.libraryOk': '笔记库正常',
      'status.libraryDown': '笔记库不可用',
      'status.indexed': '已索引 {n} 篇',
      'status.scanning': '正在建立索引…',

      'err.unknown': '发生未知错误',
      'err.network': '无法连接到服务，请稍后重试',
      'err.timeout': '请求超时',
      'err.http': '服务返回了错误（HTTP {status}）',
      'err.session': '登录状态已失效，正在返回登录页…',
      'err.code1000': '服务内部错误，请稍后重试',
      'err.code1400': '请求参数不合法',
      'err.code1401': '登录状态已失效，请重新登录',
      'err.code1404': '请求的资源不存在',
      'err.code1405': '请求方法不被允许',
      'err.code1413': '内容超过大小限制',
      'err.code1415': '不支持的内容类型',
      'err.code1503': '服务繁忙，请稍后重试',
      'err.code3001': '笔记库不可用：应用自己的共享文件夹不存在或无法读取。请在应用中心重新安装本应用。',
      'err.code3002': '该文件夹不可写入，因此无法保存。请检查共享文件夹的权限。',
      'err.code3003': '该路径不在你的笔记库内',
      'err.code3004': '笔记库拒绝访问该路径',
      'err.code3005': '这篇笔记不存在，可能已被移动或删除',
      'err.code3006': '该路径已存在同名笔记',
      'err.code3007': '这篇笔记已被他人修改',
      'err.code3008': '笔记超过大小限制',
      'err.code3011': '搜索索引不可用，笔记本身不受影响',
      'err.code3012': '该名称不可用（不能含斜杠、不能以点开头、长度不超过 255 字节）',
      'err.code3013': '无法确定你的 TOS 用户身份，请重新登录后重试',
      'err.code3014': '正在建立索引，请稍后重试'
    },

    'zh-hk': {
      'app.name': 'MarkNest 筆記',
      'app.subtitle': 'NAS 上的 Markdown 筆記庫',

      'common.language': '語言',
      'common.refresh': '重新整理',
      'common.loading': '載入中…',
      'common.empty': '暫無內容',
      'common.unknown': '未知',
      'common.retryAction': '重試',
      'common.close': '關閉',
      'common.cancel': '取消',
      'common.confirm': '確定',

      'home.open': '開啟檔案',
      'home.new': '新增檔案',
      'home.recent': '最近檔案',
      'home.noRecent': '還沒有筆記',
      'home.timeJustNow': '剛剛',
      'home.timeMinutes': '{n} 分鐘前',
      'home.timeHours': '{n} 小時前',
      'home.timeYesterday': '昨天',
      'home.timeDays': '{n} 天前',

      'nav.home': '首頁',
      'nav.newNote': '新增檔案',
      'nav.openNote': '開啟檔案',
      'nav.more': '更多',

      'tree.ariaLabel': '筆記目錄樹',
      'tree.refreshTitle': '重新整理目錄樹',
      'tree.empty': '還沒有筆記，點上方「☰」新增一篇',
      'tree.unsupported': '非筆記檔案',
      'tree.untitled': '未命名',
      'tree.readOnly': '唯讀',
      'tree.notWritable': '該資料夾無法寫入',
      'tree.newNotePrompt': '新筆記的路徑（可含子目錄）',
      'tree.newNoteDefault': '未命名.md',
      'tree.renamePrompt': '新的路徑',
      'tree.rename': '重新命名',
      'tree.delete': '刪除',
      'tree.deleteConfirm': '確定刪除「{name}」？此操作無法復原。',
      'tree.created': '已建立 {name}',
      'tree.renamed': '已重新命名',
      'tree.deleted': '已刪除 {name}',

      'picker.title': '開啟檔案',
      'picker.library': '筆記庫',
      'picker.local': '本機檔案',
      'picker.browse': '選擇本機檔案…',
      'picker.localHint': '選擇本機檔案後將匯入筆記庫，成為一篇普通筆記。',
      'picker.readFailed': '無法讀取該檔案',
      'picker.badType': '只能選擇文字筆記（.md / .markdown / .mdown / .txt）',

      'editor.title': '編輯',
      'editor.ariaLabel': 'Markdown 編輯器',
      'editor.save': '儲存',
      'editor.togglePreview': '預覽',
      'editor.noNote': '未開啟筆記',
      'editor.saved': '已儲存',
      'editor.saving': '儲存中…',
      'editor.dirty': '有未儲存的修改',
      'editor.readOnly': '這篇筆記目前無法寫入',
      'editor.conflict': '這篇筆記已被他人修改，你的改動沒有儲存',
      'editor.overwrite': '覆蓋對方改動',
      'editor.reload': '放棄我的改動並重新載入',
      'editor.saveCopy': '另存為副本',
      'editor.loaded': '已開啟 {name}',

      'format.ariaLabel': '格式工具列',
      'format.bold': '粗體',
      'format.italic': '斜體',
      'format.code': '行內程式碼',
      'format.codeblock': '程式碼區塊',
      'format.quote': '引用',
      'format.h1': '一級標題',
      'format.h2': '二級標題',
      'format.h3': '三級標題',
      'format.task': '待辦',
      'format.bullet': '無序清單',
      'format.numbered': '有序清單',
      'format.link': '連結',
      'format.table': '表格',
      'format.linkPrompt': '連結位址',
      'format.linkTextPrompt': '顯示文字',

      'preview.title': '預覽',
      'preview.ariaLabel': 'Markdown 預覽',
      'preview.empty': '開啟一篇筆記即可預覽',

      'search.placeholder': '搜尋筆記…',
      'search.results': '找到 {n} 篇',
      'search.none': '沒有符合的筆記',
      'search.clear': '清除搜尋',
      'search.engineFts': '全文索引',
      'search.engineScan': '逐篇掃描',

      'status.libraryOk': '筆記庫正常',
      'status.libraryDown': '筆記庫無法使用',
      'status.indexed': '已索引 {n} 篇',
      'status.scanning': '正在建立索引…',

      'err.unknown': '發生未知錯誤',
      'err.network': '無法連線到服務，請稍後重試',
      'err.timeout': '請求逾時',
      'err.http': '服務回傳了錯誤（HTTP {status}）',
      'err.session': '登入狀態已失效，正在返回登入頁…',
      'err.code1000': '服務內部錯誤，請稍後重試',
      'err.code1400': '請求參數不合法',
      'err.code1401': '登入狀態已失效，請重新登入',
      'err.code1404': '請求的資源不存在',
      'err.code1405': '請求方法不被允許',
      'err.code1413': '內容超過大小限制',
      'err.code1415': '不支援的內容類型',
      'err.code1503': '服務繁忙，請稍後重試',
      'err.code3001': '筆記庫無法使用：應用自己的共享資料夾不存在或無法讀取。請在應用中心重新安裝本應用。',
      'err.code3002': '該資料夾無法寫入，因此無法儲存。請檢查共享資料夾的權限。',
      'err.code3003': '該路徑不在你的筆記庫內',
      'err.code3004': '筆記庫拒絕存取該路徑',
      'err.code3005': '這篇筆記不存在，可能已被移動或刪除',
      'err.code3006': '該路徑已存在同名筆記',
      'err.code3007': '這篇筆記已被他人修改',
      'err.code3008': '筆記超過大小限制',
      'err.code3011': '搜尋索引無法使用，筆記本身不受影響',
      'err.code3012': '該名稱無法使用（不能含斜線、不能以點開頭、長度不超過 255 位元組）',
      'err.code3013': '無法確定你的 TOS 使用者身分，請重新登入後重試',
      'err.code3014': '正在建立索引，請稍後重試'
    },

    'en-us': {
      'app.name': 'MarkNest',
      'app.subtitle': 'A Markdown note library on your NAS',

      'common.language': 'Language',
      'common.refresh': 'Refresh',
      'common.loading': 'Loading…',
      'common.empty': 'Nothing here yet',
      'common.unknown': 'Unknown',
      'common.retryAction': 'Retry',
      'common.close': 'Close',
      'common.cancel': 'Cancel',
      'common.confirm': 'OK',

      'home.open': 'Open file',
      'home.new': 'New file',
      'home.recent': 'Recent',
      'home.noRecent': 'No notes yet',
      'home.timeJustNow': 'just now',
      'home.timeMinutes': '{n} min ago',
      'home.timeHours': '{n} h ago',
      'home.timeYesterday': 'yesterday',
      'home.timeDays': '{n} d ago',

      'nav.home': 'Home',
      'nav.newNote': 'New file',
      'nav.openNote': 'Open file',
      'nav.more': 'More',

      'tree.ariaLabel': 'Note tree',
      'tree.refreshTitle': 'Refresh the tree',
      'tree.empty': 'No notes yet — use ☰ above to create one',
      'tree.unsupported': 'Not a note',
      'tree.untitled': 'Untitled',
      'tree.readOnly': 'read-only',
      'tree.notWritable': 'That folder cannot be written to',
      'tree.newNotePrompt': 'Path for the new note (subfolders are created)',
      'tree.newNoteDefault': 'untitled.md',
      'tree.renamePrompt': 'New path',
      'tree.rename': 'Rename',
      'tree.delete': 'Delete',
      'tree.deleteConfirm': 'Delete “{name}”? This cannot be undone.',
      'tree.created': 'Created {name}',
      'tree.renamed': 'Renamed',
      'tree.deleted': 'Deleted {name}',

      'picker.title': 'Open a file',
      'picker.library': 'Library',
      'picker.local': 'This computer',
      'picker.browse': 'Choose a file…',
      'picker.localHint': 'A file chosen here is imported into your library, where it becomes an ordinary note.',
      'picker.readFailed': 'That file could not be read',
      'picker.badType': 'Only text notes can be opened (.md, .markdown, .mdown, .txt)',

      'editor.title': 'Editor',
      'editor.ariaLabel': 'Markdown editor',
      'editor.save': 'Save',
      'editor.togglePreview': 'Preview',
      'editor.noNote': 'No note open',
      'editor.saved': 'Saved',
      'editor.saving': 'Saving…',
      'editor.dirty': 'Unsaved changes',
      'editor.readOnly': 'This note cannot be written to',
      'editor.conflict': 'This note was changed by someone else; your edit was not saved',
      'editor.overwrite': 'Overwrite their change',
      'editor.reload': 'Discard mine and reload',
      'editor.saveCopy': 'Save as a copy',
      'editor.loaded': 'Opened {name}',

      'format.ariaLabel': 'Formatting',
      'format.bold': 'Bold',
      'format.italic': 'Italic',
      'format.code': 'Inline code',
      'format.codeblock': 'Code block',
      'format.quote': 'Quote',
      'format.h1': 'Heading 1',
      'format.h2': 'Heading 2',
      'format.h3': 'Heading 3',
      'format.task': 'Task',
      'format.bullet': 'Bullet list',
      'format.numbered': 'Numbered list',
      'format.link': 'Link',
      'format.table': 'Table',
      'format.linkPrompt': 'Link address',
      'format.linkTextPrompt': 'Display text',

      'preview.title': 'Preview',
      'preview.ariaLabel': 'Markdown preview',
      'preview.empty': 'Open a note to see it rendered',

      'search.placeholder': 'Search notes…',
      'search.results': '{n} note(s) found',
      'search.none': 'No note matches',
      'search.clear': 'Clear the search',
      'search.engineFts': 'full-text index',
      'search.engineScan': 'scanning notes',

      'status.libraryOk': 'Library ready',
      'status.libraryDown': 'Library unavailable',
      'status.indexed': '{n} note(s) indexed',
      'status.scanning': 'Building the index…',

      'err.unknown': 'Something went wrong',
      'err.network': 'Cannot reach the service, please try again',
      'err.timeout': 'The request timed out',
      'err.http': 'The service answered with an error (HTTP {status})',
      'err.session': 'Your session expired, returning to the sign-in page…',
      'err.code1000': 'The service hit an internal error, please try again',
      'err.code1400': 'The request was not valid',
      'err.code1401': 'Your session expired, please sign in again',
      'err.code1404': 'That resource does not exist',
      'err.code1405': 'That request method is not allowed',
      'err.code1413': 'The content is too large',
      'err.code1415': 'That content type is not supported',
      'err.code1503': 'The service is busy, please try again',
      'err.code3001': 'The notes library is unavailable: the shared folder this application owns is missing or unreadable. Reinstall the application from the App Center.',
      'err.code3002': 'That folder cannot be written to, so the note was not saved. Check the shared folder permissions.',
      'err.code3003': 'That path is outside your notes library',
      'err.code3004': 'The notes library refused access to that path',
      'err.code3005': 'That note does not exist; it may have been moved or deleted',
      'err.code3006': 'A note already exists at that path',
      'err.code3007': 'This note was changed by someone else',
      'err.code3008': 'The note is too large',
      'err.code3011': 'The search index is unavailable; your notes are unaffected',
      'err.code3012': 'That name cannot be used (no slashes, no leading dot, at most 255 bytes)',
      'err.code3013': 'Your TOS user could not be determined; sign in again and retry',
      'err.code3014': 'The index is being rebuilt, please try again'
    }
  };

  var SUPPORTED = ['zh-cn', 'zh-hk', 'en-us'];
  var DEFAULT = 'en-us';
  var STORE_KEY = 'marknest.lang';
  var current = DEFAULT;

  function table(tag) {
    return STRINGS[tag] || STRINGS[DEFAULT];
  }

  function interpolate(text, params) {
    if (!params) {
      return text;
    }
    Object.keys(params).forEach(function (name) {
      var value = params[name];
      text = text.replace(
        new RegExp('\\{' + name + '\\}', 'g'),
        value === undefined || value === null ? '' : String(value)
      );
    });
    return text;
  }

  function translate(key, params) {
    var value = table(current)[key];
    if (value === undefined) {
      value = table(DEFAULT)[key];
    }
    if (value === undefined) {
      // Returning the key makes a missing string obvious on screen instead of
      // rendering as blank space nobody notices.
      return key;
    }
    return interpolate(value, params);
  }

  function errorText(error, fallbackKey) {
    var code = error && error.code;
    if (code) {
      var byCode = translate('err.code' + code);
      // translate() returns the key itself on a miss, which is how a code this
      // build does not know about is told apart from a real translation.
      if (byCode !== 'err.code' + code) {
        return byCode;
      }
    }
    if (fallbackKey) {
      var byFallback = translate(fallbackKey);
      if (byFallback !== fallbackKey) {
        return byFallback;
      }
    }
    if (error && error.kind === 'timeout') {
      return translate('err.timeout');
    }
    if (error && error.kind === 'network') {
      return translate('err.network');
    }
    if (error && error.message) {
      return error.message;
    }
    return translate('err.unknown');
  }

  function detect() {
    var stored = null;
    try {
      stored = global.localStorage.getItem(STORE_KEY);
    } catch (error) {
      // Storage can be unavailable inside a sandboxed frame; the language then
      // simply falls back to the browser's.
      stored = null;
    }
    if (stored && STRINGS[stored]) {
      return stored;
    }
    var languages = (global.navigator && (global.navigator.languages ||
      [global.navigator.language])) || [];
    for (var i = 0; i < languages.length; i += 1) {
      var tag = String(languages[i] || '').toLowerCase();
      if (!tag) {
        continue;
      }
      if (tag.indexOf('zh') === 0) {
        return /hk|tw|mo|hant/.test(tag) ? 'zh-hk' : 'zh-cn';
      }
      if (tag.indexOf('en') === 0) {
        return 'en-us';
      }
    }
    return DEFAULT;
  }

  function apply(root) {
    var scope = root || global.document;
    if (!scope || !scope.querySelectorAll) {
      return;
    }
    var map = [
      ['data-i18n', 'textContent'],
      ['data-i18n-placeholder', 'placeholder'],
      ['data-i18n-aria-label', 'aria-label'],
      ['data-i18n-title', 'title']
    ];
    map.forEach(function (entry) {
      var attribute = entry[0];
      var property = entry[1];
      Array.prototype.forEach.call(scope.querySelectorAll('[' + attribute + ']'),
        function (node) {
          var key = node.getAttribute(attribute);
          if (!key) {
            return;
          }
          var value = translate(key);
          if (property === 'textContent') {
            node.textContent = value;
          } else {
            node.setAttribute(property, value);
          }
        });
    });
  }

  function setLanguage(tag) {
    current = STRINGS[tag] ? tag : DEFAULT;
    try {
      global.localStorage.setItem(STORE_KEY, current);
    } catch (error) {
      /* not fatal */
    }
    if (global.document && global.document.documentElement) {
      global.document.documentElement.lang = current;
    }
    apply(global.document);
    return current;
  }

  current = detect();

  global.I18N = {
    t: translate,
    errorText: errorText,
    apply: apply,
    setLanguage: setLanguage,
    getLanguage: function () { return current; },
    detect: detect,
    supported: SUPPORTED,
    // Exposed so tools/webui_check.js can compare the key sets mechanically.
    tables: STRINGS
  };
})(window);
