/* MarkNest for TOS - translations.

   Three dictionaries live inline; six more are registered on
   window.MARKNEST_I18N by js/i18n/<tag>.js and merged before the supported
   list is built. All nine carry identical key sets. Parity is not a style
   preference: translate() falls back to the default language, so a key present
   in one dictionary and missing in another shows an English sentence inside a
   Chinese interface instead of failing. tools/webui_check.js compares the key
   sets mechanically so that cannot happen quietly.

   Keys are namespaced `area.subject`. `t()` returns the key itself when it is
   missing, which makes an omission show up as `editor.foo` on screen rather
   than as blank space. */

(function (global) {
  'use strict';

  var STRINGS = {
    'zh-cn': {
      'app.name': 'MarkNest',
      'app.subtitle': 'NAS 上的 Markdown 笔记库',
      'app.tagline': '把想法留在自己的硬盘上',

      'common.search': '搜索',
      'common.cancel': '取消',
      'common.confirm': '确定',
      'common.close': '关闭',
      'common.save': '保存',
      'common.saving': '保存中…',
      'common.saved': '已保存',
      'common.delete': '删除',
      'common.rename': '重命名',
      'common.retry': '重试',
      'common.retryAction': '重试',
      'common.loading': '加载中…',
      'common.empty': '暂无内容',
      'common.unknown': '未知',
      'common.back': '返回',
      'common.copy': '复制',
      'common.copied': '已复制',
      'common.download': '下载',
      'common.more': '更多',
      'common.open': '打开',
      'common.create': '创建',
      'common.refresh': '刷新',
      'common.all': '全部',
      'common.optional': '可选',
      'common.browse': '浏览',
      'common.remove': '移除',
      'common.restore': '恢复',
      'common.preview': '预览',
      'common.edit': '编辑',
      'common.export': '导出',
      'common.share': '分享',
      'common.new': '新建',
      'common.add': '添加',
      'common.apply': '应用',
      'common.reset': '重置',
      'common.enabled': '已开启',
      'common.disabled': '已关闭',
      'common.never': '从未',
      'common.none': '无',
      'common.yes': '是',
      'common.no': '否',
      'common.words': '字',
      'common.actions': '操作',
      'common.name': '名称',
      'common.path': '路径',
      'common.size': '大小',
      'common.updated': '更新时间',
      'common.created': '创建时间',
      'common.status': '状态',
      'common.language': '语言',
      'common.settings': '设置',
      'common.version': '版本',
      'common.done': '完成',
      'common.uploading': '上传中…',
      'common.failed': '失败',
      'common.rootFolder': '根目录',
      'common.untitled': '未命名',
      'common.folder': '文件夹',
      'common.note': '笔记',
      'common.notes': '笔记',
      'common.folders': '文件夹',
      'common.menu': '菜单',
      'common.renameAction': '重命名',

      'time.justNow': '刚刚',
      'time.minutesAgo': '{n} 分钟前',
      'time.hoursAgo': '{n} 小时前',
      'time.daysAgo': '{n} 天前',

      'nav.library': '文档库',
      'nav.import': '上传导入',
      'nav.settings': '个人中心',
      'nav.foldersSection': '文件夹',
      'nav.newFolder': '新建文件夹',
      'nav.allNotes': '全部笔记',
      'nav.storage': '存储空间',
      'nav.menu': '打开菜单',
      'nav.collapse': '收起侧栏',
      'nav.resizeSidebar': '拖动调整侧栏宽度',
      'nav.expand': '展开侧栏',
      'nav.quick': '快速开始',
      'nav.libraryHint': '浏览全部笔记',

      'shell.searchPlaceholder': '搜索笔记、标题或正文…',
      'shell.searchHint': '搜索',
      'shell.newNote': '新建笔记',
      'shell.newFolder': '新建文件夹',
      'shell.userFallback': 'TOS 用户',
      'shell.libraryDown': '笔记库不可用',
      'shell.libraryDownHint': '应用自己的共享文件夹缺失或不可读，可在应用中心重新安装。',
      'shell.connectionLost': '无法连接到服务',
      'shell.retry': '重新连接',
      'shell.reindex': '重建索引',
      'shell.reindexed': '索引已重建',
      'shell.reindexRunning': '正在重建索引…',
      'shell.storageUsage': '已使用 {size}',
      'shell.storageFree': '剩余 {free}',
      'shell.footerNote': '文件保存在你的 NAS 上',
      'shell.themeToggle': '切换主题',
      'shell.openShared': '打开共享文件夹设置',

      'library.title': '文档库',
      'library.subtitle': '所有笔记都是普通的 Markdown 文件，放在你自己的共享文件夹里。',
      'library.newNote': '新建笔记',
      'library.import': '上传导入',
      'library.grid': '卡片视图',
      'library.list': '列表视图',
      'library.sortUpdated': '按更新时间',
      'library.sortName': '按名称',
      'library.sortSize': '按大小',
      'library.sortLabel': '排序',
      'library.viewLabel': '视图',
      'library.searchPlaceholder': '在当前范围中筛选…',
      'library.emptyTitle': '这里还没有笔记',
      'library.emptyBody': '新建一篇，或者把已有的 Markdown 文件导入进来。',
      'library.emptyAction': '写第一篇笔记',
      'library.noResults': '没有匹配的笔记',
      'library.noResultsBody': '换一个关键词，或者清除筛选条件。',
      'library.clearFilters': '清除筛选',
      'library.statsNotes': '笔记',
      'library.statsFolders': '文件夹',
      'library.statsSize': '占用空间',
      'library.statsIndexed': '已索引',
      'library.allNotes': '全部笔记',
      'library.openFromNas': '从 NAS 打开',
      'library.openFromNasHint': '浏览笔记库所在的 NAS 文件夹，选择 Markdown 文件直接打开。',
      'library.nasScopeHint': '只能浏览并打开 MarkNest 共享文件夹中的 Markdown 文档；其他目录或 PDF 等格式需先转换并放入该文件夹。',
      'library.nasUp': '上一级',
      'library.nasEmpty': '这个文件夹里没有可打开的文件',
      'library.nasUnsupported': '无法在此打开',
      'library.notesHere': '共 {n} 篇',
      'library.inFolder': '位于「{name}」',
      'library.newFolderTitle': '新建文件夹',
      'library.newFolderLabel': '文件夹路径',
      'library.newFolderPlaceholder': '例如：产品/发布说明',
      'library.newFolderHint': '可以带子目录，路径中的文件夹会一并创建。',
      'library.folderCreated': '已创建文件夹「{name}」',
      'library.deleteFolder': '删除文件夹',
      'library.deleteFolderTitle': '删除文件夹「{name}」？',
      'library.deleteFolderConfirm': '只会删除空文件夹；里面还有笔记时不会执行。',
      'library.folderDeleted': '已删除文件夹「{name}」',
      'library.newNoteTitle': '新建笔记',
      'library.newNoteLabel': '笔记路径',
      'library.newNotePlaceholder': '例如：灵感/标题的写法.md',
      'library.newNoteHint': '省略扩展名时会自动补上 .md；子文件夹会自动创建。',
      'library.noteCreated': '已创建「{name}」',
      'library.renameTitle': '重命名笔记',
      'library.renameLabel': '新的路径',
      'library.renamed': '已重命名',
      'library.deleteTitle': '删除「{name}」？',
      'library.deleteConfirm': '文件会从笔记库中移除，且无法从应用内撤销。',
      'library.deleted': '已删除「{name}」',
      'library.moreActions': '更多操作',
      'library.openReader': '阅读',
      'library.editNote': '编辑',
      'library.copyPath': '复制路径',
      'library.pathCopied': '路径已复制',
      'library.emptyFolder': '这个文件夹还是空的',
      'library.emptyFolderBody': '在「{name}」中新建一篇笔记吧。',
      'library.moveHint': '提示：也可以直接通过 NAS 的共享文件夹管理这些文件。',
      'library.folder': '文件夹',
      'library.note': '笔记',
      'library.indexPending': '索引整理中',

      'reader.edit': '编辑',
      'reader.versions': '版本',
      'reader.export': '导出',
      'reader.share': '分享',
      'reader.toc': '目录',
      'reader.tocEmpty': '这篇笔记没有标题',
      'reader.readingTime': '约 {n} 分钟阅读',
      'reader.words': '{n} 字',
      'reader.updated': '更新于 {time}',
      'reader.back': '返回文档库',
      'reader.more': '更多',
      'reader.deleteTitle': '删除「{name}」？',
      'reader.deleteConfirm': '文件会从笔记库中移除，且无法从应用内撤销。',
      'reader.deleted': '已删除「{name}」',
      'reader.notFound': '找不到这篇笔记',
      'reader.notFoundBody': '它可能已被移动、重命名或删除。',
      'reader.copyLink': '复制链接',
      'reader.linkCopied': '链接已复制',
      'reader.exportMarkdown': '导出 Markdown',
      'reader.exportHtml': '导出 HTML',
      'reader.exportHtmlDone': 'HTML 已导出',
      'reader.shareRich': '复制富文本',
      'reader.shareRichDone': '富文本已复制，可粘贴到邮件或聊天工具',
      'reader.endOfNote': '笔记结束',
      'reader.deleteNote': '删除笔记',
      'reader.allNotes': '全部笔记',
      'reader.print': '打印',

      'editor.title': '编辑',
      'editor.untitled': '未命名',
      'editor.save': '保存',
      'editor.saving': '保存中…',
      'editor.saved': '已保存',
      'editor.savedAt': '已保存 · {time}',
      'editor.unsaved': '有未保存的修改',
      'editor.unsavedShort': '未保存',
      'editor.leaveDiscard': '不保存，直接离开',
      'editor.stayEditing': '继续编辑',
      'editor.preview': '预览',
      'editor.split': '分栏',
      'editor.outline': '大纲',
      'editor.outlineEmpty': '还没有标题',
      'editor.outlineEmptyBody': '用 # 或 ## 标记标题，大纲会自动生成。',
      'editor.versions': '版本记录',
      'editor.versionHistory': '版本记录',
      'editor.versionEmpty': '还没有历史版本',
      'editor.versionEmptyBody': '每次保存前，上一版内容都会记录在这里。',
      'editor.versionRestore': '恢复到这一版',
      'editor.versionRestoreConfirm': '用这一版覆盖当前内容？当前内容会先被记录为一个新版本。',
      'editor.versionRestored': '已恢复到所选版本',
      'editor.versionAt': '{time}',
      'editor.versionSize': '{size}',
      'editor.versionCurrent': '当前',
      'editor.versionLoadFail': '无法载入这个版本',
      'editor.exportShare': '导出与分享',
      'editor.exportMd': '导出 Markdown 文件',
      'editor.exportHtml': '导出为 HTML',
      'editor.copyLink': '复制阅读链接',
      'editor.copyMarkdown': '复制 Markdown',
      'editor.copyRich': '复制为富文本',
      'editor.copied': '已复制',
      'editor.exportHtmlDone': 'HTML 文件已导出',
      'editor.conflictTitle': '这篇笔记已被他人修改',
      'editor.conflictBody': '你的改动没有保存。可以选择覆盖对方的内容，或者保留你的版本另存为副本。',
      'editor.overwrite': '覆盖对方改动',
      'editor.reload': '放弃我的改动并重新载入',
      'editor.saveCopy': '另存为副本',
      'editor.readOnly': '只读',
      'editor.readOnlyHint': '这篇笔记当前不可写入，你仍然可以阅读、导出和复制内容。',
      'editor.toolbar': '格式工具栏',
      'editor.bold': '加粗',
      'editor.italic': '斜体',
      'editor.strike': '删除线',
      'editor.heading': '标题',
      'editor.h1': '一级标题',
      'editor.h2': '二级标题',
      'editor.h3': '三级标题',
      'editor.quote': '引用',
      'editor.code': '代码块',
      'editor.inlineCode': '行内代码',
      'editor.link': '链接',
      'editor.image': '插入图片',
      'editor.ul': '无序列表',
      'editor.ol': '有序列表',
      'editor.task': '任务清单',
      'editor.table': '表格',
      'editor.hr': '分隔线',
      'editor.linkTitle': '插入链接',
      'editor.linkText': '链接文字',
      'editor.linkUrl': '链接地址',
      'editor.imageUploading': '正在上传图片…',
      'editor.imageInserted': '图片已插入',
      'editor.imageFailed': '图片上传失败',
      'editor.dropImage': '松手即可插入图片',
      'editor.pasteImage': '已检测到剪贴板图片，正在上传…',
      'editor.wordCount': '{n} 字',
      'editor.charCount': '{n} 字符',
      'editor.lineCol': '第 {line} 行，第 {col} 列',
      'editor.markdown': 'Markdown',
      'editor.saveHint': 'Ctrl / ⌘ + S 保存',
      'editor.backToLibrary': '返回文档库',
      'editor.imageTooLarge': '图片超过大小限制',
      'editor.unsupportedImage': '只支持 PNG、JPEG、GIF、WebP、BMP 等图片格式',
      'editor.uploadProgress': '上传中 {n}%',
      'editor.autosaved': '已自动保存',
      'editor.focusMode': '专注模式',
      'editor.exitFocus': '退出专注',
      'editor.stats': '{words} 字 · {lines} 行',

      'import.title': '上传与导入',
      'import.subtitle': '把已有的 Markdown、TXT 文件搬进笔记库，或者直接粘贴一段文字开始。',
      'import.dropTitle': '把文件拖到这里',
      'import.dropBody': '支持 .md / .markdown / .mdown / .txt，一次最多 {n} 个文件。',
      'import.browse': '选择文件',
      'import.destination': '导入到',
      'import.rootFolder': '根目录',
      'import.conflict': '同名文件',
      'import.conflictRename': '自动改名保留两份',
      'import.conflictRenameHint': '例如「笔记 (2).md」',
      'import.conflictSkip': '跳过已存在的文件',
      'import.conflictSkipHint': '不覆盖磁盘上已有的内容',
      'import.queue': '待导入文件',
      'import.queueEmpty': '还没有选择文件',
      'import.queueEmptyBody': '拖入文件或点击上方按钮，文件会先列在这里。',
      'import.start': '开始导入',
      'import.uploading': '正在导入…',
      'import.clear': '清空列表',
      'import.statusPending': '等待',
      'import.statusUploading': '导入中',
      'import.statusCreated': '已导入',
      'import.statusSkipped': '已跳过',
      'import.statusFailed': '失败',
      'import.summary': '导入完成：新增 {created} 篇，跳过 {skipped} 篇，失败 {failed} 篇。',
      'import.summaryDone': '已完成',
      'import.goLibrary': '去文档库看看',
      'import.textTitle': '从文本创建',
      'import.textBody': '粘贴一段 Markdown 或纯文本，直接保存成一篇笔记。',
      'import.textName': '笔记路径',
      'import.textNamePlaceholder': '例如：灵感/刚刚的想法.md',
      'import.textPlaceholder': '在这里粘贴或输入内容…',
      'import.textCreate': '创建笔记',
      'import.textCreated': '已创建「{name}」',
      'import.tooMany': '一次最多导入 {n} 个文件',
      'import.accepted': '接受 {exts}',
      'import.fileCount': '已选择 {n} 个文件',
      'import.removeFile': '移除',
      'import.invalidType': '不支持的文件类型',
      'import.noFiles': '请先选择要导入的文件',
      'import.progress': '正在上传 {done}/{total}',
      'import.failedTitle': '部分文件未能导入',
      'import.retryFailed': '重试失败项',
      'import.dragActive': '松手即可添加文件',
      'import.noteHint': '文件内容会按 UTF-8 读取，BOM 会自动处理。',

      'settings.title': '个人中心',
      'settings.subtitle': '账户、外观与数据都集中在这里。',
      'settings.account': '账户与笔记库',
      'settings.accountBody': '每个 TOS 用户都有独立的笔记库，其他账户看不到你的文件。',
      'settings.user': '当前用户',
      'settings.libraryPath': '笔记库位置',
      'settings.libraryStatus': '状态',
      'settings.writable': '可读写',
      'settings.readOnly': '只读',
      'settings.reindex': '重建搜索索引',
      'settings.reindexing': '正在重建…',
      'settings.reindexed': '索引已重建',
      'settings.reindexHint': '索引是缓存，删除或重建都不会影响笔记文件。',
      'settings.openShared': '打开共享文件夹设置',
      'settings.openSharedHint': '在 TOS 控制面板中管理这个共享文件夹的权限。',
      'settings.openSharedUnavailable': '当前不在 TOS 桌面中，无法跳转到控制面板。',
      'settings.appearance': '外观',
      'settings.appearanceBody': '这些设置只保存在当前浏览器中。',
      'settings.theme': '主题',
      'settings.themeSystem': '跟随系统',
      'settings.themeLight': '浅色',
      'settings.themeDark': '深色',
      'settings.accent': '强调色',
      'settings.accentForest': '松林',
      'settings.accentClay': '陶土',
      'settings.accentIndigo': '靛蓝',
      'settings.fontSize': '正文字号',
      'settings.fontSmall': '小',
      'settings.fontMedium': '中',
      'settings.fontLarge': '大',
      'settings.readingWidth': '阅读栏宽',
      'settings.widthNarrow': '窄',
      'settings.widthMedium': '适中',
      'settings.widthWide': '宽',
      'settings.behavior': '使用习惯',
      'settings.behaviorBody': '打开应用时的默认位置与编辑行为。',
      'settings.language': '界面语言',
      'settings.languageHint': '默认跟随 TOS 的界面语言；手动选择后会固定使用该语言。',
      'settings.languageAuto': '跟随 TOS 语言',
      'settings.defaultPage': '默认页面',
      'settings.defaultLibrary': '文档库',
      'settings.defaultImport': '上传导入',
      'settings.autosave': '自动保存',
      'settings.autosaveHint': '编辑停顿后自动保存，冲突检测仍然生效。',
      'settings.data': '数据概览',
      'settings.dataBody': '数字来自当前账户的笔记库与索引。',
      'settings.noteCount': '笔记数量',
      'settings.versionCount': '历史版本',
      'settings.folderCount': '文件夹',
      'settings.storageUsed': '占用空间',
      'settings.indexEngine': '搜索方式',
      'settings.engineFts': '全文索引',
      'settings.engineScan': '逐篇扫描',
      'settings.versionsKept': '版本保留',
      'settings.versionsKeptValue': '每篇 {n} 个',
      'settings.importLimit': '批量导入上限',
      'settings.importLimitValue': '{n} 个文件',
      'settings.about': '关于',
      'settings.aboutBody': 'MarkNest 把笔记保存为普通的 Markdown 文件，没有私有格式，也不依赖云端。',
      'settings.version': '应用版本',
      'settings.reset': '重置外观与习惯设置',
      'settings.resetConfirm': '恢复默认主题、字号、栏宽和语言？笔记文件不会受到影响。',
      'settings.resetDone': '设置已恢复默认',
      'settings.saved': '设置已保存',
      'settings.indexRebuilt': '索引已重建',
      'settings.apiNote': '数据通过 TOS 的会话安全访问，不会离开你的设备。',

      'search.title': '搜索笔记',
      'search.placeholder': '输入关键词…',
      'search.empty': '输入关键词开始搜索',
      'search.emptyBody': '会同时匹配标题、路径和正文。',
      'search.noResults': '没有找到匹配的笔记',
      'search.noResultsBody': '试试更短的关键词，或者换一种说法。',
      'search.hint': '↑ ↓ 选择 · Enter 打开 · Esc 关闭',
      'search.engineFts': '全文索引',
      'search.engineScan': '逐篇扫描',
      'search.results': '找到 {n} 篇',
      'search.close': '关闭搜索',

      'err.unknown': '发生未知错误',
      'err.network': '无法连接到服务，请稍后重试',
      'err.timeout': '请求超时',
      'err.http': '服务返回了错误（HTTP {status}）',
      'err.session': '登录状态已失效，正在返回登录页…',
      'err.upload': '上传失败，请稍后重试',
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
      'err.code3009': '仅支持把 PNG、JPEG、GIF、WebP 等图片作为附件',
      'err.code3010': '附件不存在',
      'err.code3011': '搜索索引不可用，笔记本身不受影响',
      'err.code3012': '该名称不可用（不能含斜杠、不能以点开头、长度不超过 255 字节）',
      'err.code3013': '无法确定你的 TOS 用户身份，请重新登录后重试',
      'err.code3014': '正在建立索引，请稍后重试',
      'err.code3015': '文件夹不为空，无法删除',
      'err.code3016': '该历史版本不存在'
    },

    'zh-hk': {
      'app.name': 'MarkNest',
      'app.subtitle': 'NAS 上的 Markdown 筆記庫',
      'app.tagline': '把想法留在自己的硬碟上',

      'common.search': '搜尋',
      'common.cancel': '取消',
      'common.confirm': '確定',
      'common.close': '關閉',
      'common.save': '儲存',
      'common.saving': '儲存中…',
      'common.saved': '已儲存',
      'common.delete': '刪除',
      'common.rename': '重新命名',
      'common.retry': '重試',
      'common.retryAction': '重試',
      'common.loading': '載入中…',
      'common.empty': '暫無內容',
      'common.unknown': '未知',
      'common.back': '返回',
      'common.copy': '複製',
      'common.copied': '已複製',
      'common.download': '下載',
      'common.more': '更多',
      'common.open': '開啟',
      'common.create': '建立',
      'common.refresh': '重新整理',
      'common.all': '全部',
      'common.optional': '可選',
      'common.browse': '瀏覽',
      'common.remove': '移除',
      'common.restore': '還原',
      'common.preview': '預覽',
      'common.edit': '編輯',
      'common.export': '匯出',
      'common.share': '分享',
      'common.new': '新增',
      'common.add': '新增',
      'common.apply': '套用',
      'common.reset': '重設',
      'common.enabled': '已開啟',
      'common.disabled': '已關閉',
      'common.never': '從未',
      'common.none': '無',
      'common.yes': '是',
      'common.no': '否',
      'common.words': '字',
      'common.actions': '操作',
      'common.name': '名稱',
      'common.path': '路徑',
      'common.size': '大小',
      'common.updated': '更新時間',
      'common.created': '建立時間',
      'common.status': '狀態',
      'common.language': '語言',
      'common.settings': '設定',
      'common.version': '版本',
      'common.done': '完成',
      'common.uploading': '上傳中…',
      'common.failed': '失敗',
      'common.rootFolder': '根目錄',
      'common.untitled': '未命名',
      'common.folder': '資料夾',
      'common.note': '筆記',
      'common.notes': '筆記',
      'common.folders': '資料夾',
      'common.menu': '選單',
      'common.renameAction': '重新命名',

      'time.justNow': '剛剛',
      'time.minutesAgo': '{n} 分鐘前',
      'time.hoursAgo': '{n} 小時前',
      'time.daysAgo': '{n} 天前',

      'nav.library': '文件庫',
      'nav.import': '上傳匯入',
      'nav.settings': '個人中心',
      'nav.foldersSection': '資料夾',
      'nav.newFolder': '新增資料夾',
      'nav.allNotes': '全部筆記',
      'nav.storage': '儲存空間',
      'nav.menu': '開啟選單',
      'nav.collapse': '收起側欄',
      'nav.resizeSidebar': '拖曳調整側欄寬度',
      'nav.expand': '展開側欄',
      'nav.quick': '快速開始',
      'nav.libraryHint': '瀏覽全部筆記',

      'shell.searchPlaceholder': '搜尋筆記、標題或正文…',
      'shell.searchHint': '搜尋',
      'shell.newNote': '新增筆記',
      'shell.newFolder': '新增資料夾',
      'shell.userFallback': 'TOS 使用者',
      'shell.libraryDown': '筆記庫無法使用',
      'shell.libraryDownHint': '應用程式自己的共享資料夾缺失或無法讀取，可在應用中心重新安裝。',
      'shell.connectionLost': '無法連線到服務',
      'shell.retry': '重新連線',
      'shell.reindex': '重建索引',
      'shell.reindexed': '索引已重建',
      'shell.reindexRunning': '正在重建索引…',
      'shell.storageUsage': '已使用 {size}',
      'shell.storageFree': '剩餘 {free}',
      'shell.footerNote': '檔案保存在你的 NAS 上',
      'shell.themeToggle': '切換主題',
      'shell.openShared': '開啟共享資料夾設定',

      'library.title': '文件庫',
      'library.subtitle': '所有筆記都是普通的 Markdown 檔案，放在你自己的共享資料夾裡。',
      'library.newNote': '新增筆記',
      'library.import': '上傳匯入',
      'library.grid': '卡片檢視',
      'library.list': '清單檢視',
      'library.sortUpdated': '按更新時間',
      'library.sortName': '按名稱',
      'library.sortSize': '按大小',
      'library.sortLabel': '排序',
      'library.viewLabel': '檢視',
      'library.searchPlaceholder': '在目前範圍中篩選…',
      'library.emptyTitle': '這裡還沒有筆記',
      'library.emptyBody': '新增一篇，或者把已有的 Markdown 檔案匯入進來。',
      'library.emptyAction': '寫第一篇筆記',
      'library.noResults': '沒有符合的筆記',
      'library.noResultsBody': '換一個關鍵詞，或者清除篩選條件。',
      'library.clearFilters': '清除篩選',
      'library.statsNotes': '筆記',
      'library.statsFolders': '資料夾',
      'library.statsSize': '佔用空間',
      'library.statsIndexed': '已索引',
      'library.allNotes': '全部筆記',
      'library.openFromNas': '從 NAS 開啟',
      'library.openFromNasHint': '瀏覽筆記庫所在的 NAS 資料夾，選擇 Markdown 檔案直接開啟。',
      'library.nasScopeHint': '只能瀏覽並開啟 MarkNest 共享資料夾中的 Markdown 文件；其他資料夾或 PDF 等格式需先轉換並放入該資料夾。',
      'library.nasUp': '上一層',
      'library.nasEmpty': '這個資料夾沒有可開啟的檔案',
      'library.nasUnsupported': '無法在此開啟',
      'library.notesHere': '共 {n} 篇',
      'library.inFolder': '位於「{name}」',
      'library.newFolderTitle': '新增資料夾',
      'library.newFolderLabel': '資料夾路徑',
      'library.newFolderPlaceholder': '例如：產品/發佈說明',
      'library.newFolderHint': '可以帶子目錄，路徑中的資料夾會一併建立。',
      'library.folderCreated': '已建立資料夾「{name}」',
      'library.deleteFolder': '刪除資料夾',
      'library.deleteFolderTitle': '刪除資料夾「{name}」？',
      'library.deleteFolderConfirm': '只會刪除空資料夾；裡面還有筆記時不會執行。',
      'library.folderDeleted': '已刪除資料夾「{name}」',
      'library.newNoteTitle': '新增筆記',
      'library.newNoteLabel': '筆記路徑',
      'library.newNotePlaceholder': '例如：靈感/標題的寫法.md',
      'library.newNoteHint': '省略副檔名時會自動補上 .md；子資料夾會自動建立。',
      'library.noteCreated': '已建立「{name}」',
      'library.renameTitle': '重新命名筆記',
      'library.renameLabel': '新的路徑',
      'library.renamed': '已重新命名',
      'library.deleteTitle': '刪除「{name}」？',
      'library.deleteConfirm': '檔案會從筆記庫中移除，且無法從應用程式內復原。',
      'library.deleted': '已刪除「{name}」',
      'library.moreActions': '更多操作',
      'library.openReader': '閱讀',
      'library.editNote': '編輯',
      'library.copyPath': '複製路徑',
      'library.pathCopied': '路徑已複製',
      'library.emptyFolder': '這個資料夾還是空的',
      'library.emptyFolderBody': '在「{name}」中新增一篇筆記吧。',
      'library.moveHint': '提示：也可以直接透過 NAS 的共享資料夾管理這些檔案。',
      'library.folder': '資料夾',
      'library.note': '筆記',
      'library.indexPending': '索引整理中',

      'reader.edit': '編輯',
      'reader.versions': '版本',
      'reader.export': '匯出',
      'reader.share': '分享',
      'reader.toc': '目錄',
      'reader.tocEmpty': '這篇筆記沒有標題',
      'reader.readingTime': '約 {n} 分鐘閱讀',
      'reader.words': '{n} 字',
      'reader.updated': '更新於 {time}',
      'reader.back': '返回文件庫',
      'reader.more': '更多',
      'reader.deleteTitle': '刪除「{name}」？',
      'reader.deleteConfirm': '檔案會從筆記庫中移除，且無法從應用程式內復原。',
      'reader.deleted': '已刪除「{name}」',
      'reader.notFound': '找不到這篇筆記',
      'reader.notFoundBody': '它可能已被移動、重新命名或刪除。',
      'reader.copyLink': '複製連結',
      'reader.linkCopied': '連結已複製',
      'reader.exportMarkdown': '匯出 Markdown',
      'reader.exportHtml': '匯出 HTML',
      'reader.exportHtmlDone': 'HTML 已匯出',
      'reader.shareRich': '複製富文字',
      'reader.shareRichDone': '富文字已複製，可貼到郵件或聊天工具',
      'reader.endOfNote': '筆記結束',
      'reader.deleteNote': '刪除筆記',
      'reader.allNotes': '全部筆記',
      'reader.print': '列印',

      'editor.title': '編輯',
      'editor.untitled': '未命名',
      'editor.save': '儲存',
      'editor.saving': '儲存中…',
      'editor.saved': '已儲存',
      'editor.savedAt': '已儲存 · {time}',
      'editor.unsaved': '有未儲存的修改',
      'editor.unsavedShort': '未儲存',
      'editor.leaveDiscard': '唔儲存，直接離開',
      'editor.stayEditing': '繼續編輯',
      'editor.preview': '預覽',
      'editor.split': '分欄',
      'editor.outline': '大綱',
      'editor.outlineEmpty': '還沒有標題',
      'editor.outlineEmptyBody': '用 # 或 ## 標記標題，大綱會自動產生。',
      'editor.versions': '版本記錄',
      'editor.versionHistory': '版本記錄',
      'editor.versionEmpty': '還沒有歷史版本',
      'editor.versionEmptyBody': '每次儲存前，上一版內容都會記錄在這裡。',
      'editor.versionRestore': '還原到這一版',
      'editor.versionRestoreConfirm': '用這一版覆蓋目前內容？目前內容會先被記錄為一個新版本。',
      'editor.versionRestored': '已還原到所選版本',
      'editor.versionAt': '{time}',
      'editor.versionSize': '{size}',
      'editor.versionCurrent': '目前',
      'editor.versionLoadFail': '無法載入這個版本',
      'editor.exportShare': '匯出與分享',
      'editor.exportMd': '匯出 Markdown 檔案',
      'editor.exportHtml': '匯出為 HTML',
      'editor.copyLink': '複製閱讀連結',
      'editor.copyMarkdown': '複製 Markdown',
      'editor.copyRich': '複製為富文字',
      'editor.copied': '已複製',
      'editor.exportHtmlDone': 'HTML 檔案已匯出',
      'editor.conflictTitle': '這篇筆記已被他人修改',
      'editor.conflictBody': '你的改動沒有儲存。可以選擇覆蓋對方的內容，或者保留你的版本另存為副本。',
      'editor.overwrite': '覆蓋對方改動',
      'editor.reload': '放棄我的改動並重新載入',
      'editor.saveCopy': '另存為副本',
      'editor.readOnly': '唯讀',
      'editor.readOnlyHint': '這篇筆記目前無法寫入，你仍然可以閱讀、匯出和複製內容。',
      'editor.toolbar': '格式工具列',
      'editor.bold': '粗體',
      'editor.italic': '斜體',
      'editor.strike': '刪除線',
      'editor.heading': '標題',
      'editor.h1': '一級標題',
      'editor.h2': '二級標題',
      'editor.h3': '三級標題',
      'editor.quote': '引用',
      'editor.code': '程式碼區塊',
      'editor.inlineCode': '行內程式碼',
      'editor.link': '連結',
      'editor.image': '插入圖片',
      'editor.ul': '無序清單',
      'editor.ol': '有序清單',
      'editor.task': '任務清單',
      'editor.table': '表格',
      'editor.hr': '分隔線',
      'editor.linkTitle': '插入連結',
      'editor.linkText': '連結文字',
      'editor.linkUrl': '連結網址',
      'editor.imageUploading': '正在上傳圖片…',
      'editor.imageInserted': '圖片已插入',
      'editor.imageFailed': '圖片上傳失敗',
      'editor.dropImage': '放手即可插入圖片',
      'editor.pasteImage': '已偵測到剪貼簿圖片，正在上傳…',
      'editor.wordCount': '{n} 字',
      'editor.charCount': '{n} 字元',
      'editor.lineCol': '第 {line} 行，第 {col} 欄',
      'editor.markdown': 'Markdown',
      'editor.saveHint': 'Ctrl / ⌘ + S 儲存',
      'editor.backToLibrary': '返回文件庫',
      'editor.imageTooLarge': '圖片超過大小限制',
      'editor.unsupportedImage': '只支援 PNG、JPEG、GIF、WebP、BMP 等圖片格式',
      'editor.uploadProgress': '上傳中 {n}%',
      'editor.autosaved': '已自動儲存',
      'editor.focusMode': '專注模式',
      'editor.exitFocus': '退出專注',
      'editor.stats': '{words} 字 · {lines} 行',

      'import.title': '上傳與匯入',
      'import.subtitle': '把已有的 Markdown、TXT 檔案搬進筆記庫，或者直接貼上一段文字開始。',
      'import.dropTitle': '把檔案拖到這裡',
      'import.dropBody': '支援 .md / .markdown / .mdown / .txt，一次最多 {n} 個檔案。',
      'import.browse': '選擇檔案',
      'import.destination': '匯入到',
      'import.rootFolder': '根目錄',
      'import.conflict': '同名檔案',
      'import.conflictRename': '自動改名保留兩份',
      'import.conflictRenameHint': '例如「筆記 (2).md」',
      'import.conflictSkip': '跳過已存在的檔案',
      'import.conflictSkipHint': '不覆蓋磁碟上已有的內容',
      'import.queue': '待匯入檔案',
      'import.queueEmpty': '還沒有選擇檔案',
      'import.queueEmptyBody': '拖入檔案或點擊上方按鈕，檔案會先列在這裡。',
      'import.start': '開始匯入',
      'import.uploading': '正在匯入…',
      'import.clear': '清空清單',
      'import.statusPending': '等待',
      'import.statusUploading': '匯入中',
      'import.statusCreated': '已匯入',
      'import.statusSkipped': '已跳過',
      'import.statusFailed': '失敗',
      'import.summary': '匯入完成：新增 {created} 篇，跳過 {skipped} 篇，失敗 {failed} 篇。',
      'import.summaryDone': '已完成',
      'import.goLibrary': '去文件庫看看',
      'import.textTitle': '從文字建立',
      'import.textBody': '貼上一段 Markdown 或純文字，直接儲存成一篇筆記。',
      'import.textName': '筆記路徑',
      'import.textNamePlaceholder': '例如：靈感/剛剛的想法.md',
      'import.textPlaceholder': '在這裡貼上或輸入內容…',
      'import.textCreate': '建立筆記',
      'import.textCreated': '已建立「{name}」',
      'import.tooMany': '一次最多匯入 {n} 個檔案',
      'import.accepted': '接受 {exts}',
      'import.fileCount': '已選擇 {n} 個檔案',
      'import.removeFile': '移除',
      'import.invalidType': '不支援的檔案類型',
      'import.noFiles': '請先選擇要匯入的檔案',
      'import.progress': '正在上傳 {done}/{total}',
      'import.failedTitle': '部分檔案未能匯入',
      'import.retryFailed': '重試失敗項',
      'import.dragActive': '放手即可加入檔案',
      'import.noteHint': '檔案內容會按 UTF-8 讀取，BOM 會自動處理。',

      'settings.title': '個人中心',
      'settings.subtitle': '帳戶、外觀與資料都集中在這裡。',
      'settings.account': '帳戶與筆記庫',
      'settings.accountBody': '每個 TOS 使用者都有獨立的筆記庫，其他帳戶看不到你的檔案。',
      'settings.user': '目前使用者',
      'settings.libraryPath': '筆記庫位置',
      'settings.libraryStatus': '狀態',
      'settings.writable': '可讀寫',
      'settings.readOnly': '唯讀',
      'settings.reindex': '重建搜尋索引',
      'settings.reindexing': '正在重建…',
      'settings.reindexed': '索引已重建',
      'settings.reindexHint': '索引是快取，刪除或重建都不會影響筆記檔案。',
      'settings.openShared': '開啟共享資料夾設定',
      'settings.openSharedHint': '在 TOS 控制面板中管理這個共享資料夾的權限。',
      'settings.openSharedUnavailable': '目前不在 TOS 桌面中，無法跳轉到控制面板。',
      'settings.appearance': '外觀',
      'settings.appearanceBody': '這些設定只儲存在目前瀏覽器中。',
      'settings.theme': '主題',
      'settings.themeSystem': '跟隨系統',
      'settings.themeLight': '淺色',
      'settings.themeDark': '深色',
      'settings.accent': '強調色',
      'settings.accentForest': '松林',
      'settings.accentClay': '陶土',
      'settings.accentIndigo': '靛藍',
      'settings.fontSize': '正文字號',
      'settings.fontSmall': '小',
      'settings.fontMedium': '中',
      'settings.fontLarge': '大',
      'settings.readingWidth': '閱讀欄寬',
      'settings.widthNarrow': '窄',
      'settings.widthMedium': '適中',
      'settings.widthWide': '寬',
      'settings.behavior': '使用習慣',
      'settings.behaviorBody': '開啟應用程式時的預設位置與編輯行為。',
      'settings.language': '介面語言',
      'settings.languageHint': '預設跟隨 TOS 的介面語言；手動選擇後會固定使用該語言。',
      'settings.languageAuto': '跟隨 TOS 語言',
      'settings.defaultPage': '預設頁面',
      'settings.defaultLibrary': '文件庫',
      'settings.defaultImport': '上傳匯入',
      'settings.autosave': '自動儲存',
      'settings.autosaveHint': '編輯停頓後自動儲存，衝突偵測仍然生效。',
      'settings.data': '資料概覽',
      'settings.dataBody': '數字來自目前帳戶的筆記庫與索引。',
      'settings.noteCount': '筆記數量',
      'settings.versionCount': '歷史版本',
      'settings.folderCount': '資料夾',
      'settings.storageUsed': '佔用空間',
      'settings.indexEngine': '搜尋方式',
      'settings.engineFts': '全文索引',
      'settings.engineScan': '逐篇掃描',
      'settings.versionsKept': '版本保留',
      'settings.versionsKeptValue': '每篇 {n} 個',
      'settings.importLimit': '批次匯入上限',
      'settings.importLimitValue': '{n} 個檔案',
      'settings.about': '關於',
      'settings.aboutBody': 'MarkNest 把筆記儲存為普通的 Markdown 檔案，沒有私有格式，也不依賴雲端。',
      'settings.version': '應用程式版本',
      'settings.reset': '重設外觀與習慣設定',
      'settings.resetConfirm': '恢復預設主題、字號、欄寬和語言？筆記檔案不會受到影響。',
      'settings.resetDone': '設定已恢復預設',
      'settings.saved': '設定已儲存',
      'settings.indexRebuilt': '索引已重建',
      'settings.apiNote': '資料透過 TOS 的工作階段安全存取，不會離開你的裝置。',

      'search.title': '搜尋筆記',
      'search.placeholder': '輸入關鍵詞…',
      'search.empty': '輸入關鍵詞開始搜尋',
      'search.emptyBody': '會同時比對標題、路徑和正文。',
      'search.noResults': '沒有找到符合的筆記',
      'search.noResultsBody': '試試更短的關鍵詞，或者換一種說法。',
      'search.hint': '↑ ↓ 選擇 · Enter 開啟 · Esc 關閉',
      'search.engineFts': '全文索引',
      'search.engineScan': '逐篇掃描',
      'search.results': '找到 {n} 篇',
      'search.close': '關閉搜尋',

      'err.unknown': '發生未知錯誤',
      'err.network': '無法連線到服務，請稍後重試',
      'err.timeout': '請求逾時',
      'err.http': '服務回傳了錯誤（HTTP {status}）',
      'err.session': '登入狀態已失效，正在返回登入頁…',
      'err.upload': '上傳失敗，請稍後重試',
      'err.code1400': '請求參數不合法',
      'err.code1401': '登入狀態已失效，請重新登入',
      'err.code1404': '請求的資源不存在',
      'err.code1405': '請求方法不被允許',
      'err.code1413': '內容超過大小限制',
      'err.code1415': '不支援的內容類型',
      'err.code1503': '服務繁忙，請稍後重試',
      'err.code3001': '筆記庫無法使用：應用程式自己的共享資料夾不存在或無法讀取。請在應用中心重新安裝本應用程式。',
      'err.code3002': '該資料夾無法寫入，因此無法儲存。請檢查共享資料夾的權限。',
      'err.code3003': '該路徑不在你的筆記庫內',
      'err.code3004': '筆記庫拒絕存取該路徑',
      'err.code3005': '這篇筆記不存在，可能已被移動或刪除',
      'err.code3006': '該路徑已存在同名筆記',
      'err.code3007': '這篇筆記已被他人修改',
      'err.code3008': '筆記超過大小限制',
      'err.code3009': '僅支援把 PNG、JPEG、GIF、WebP 等圖片作為附件',
      'err.code3010': '附件不存在',
      'err.code3011': '搜尋索引無法使用，筆記本身不受影響',
      'err.code3012': '該名稱無法使用（不能含斜線、不能以點開頭、長度不超過 255 位元組）',
      'err.code3013': '無法確定你的 TOS 使用者身分，請重新登入後重試',
      'err.code3014': '正在建立索引，請稍後重試',
      'err.code3015': '資料夾不為空，無法刪除',
      'err.code3016': '該歷史版本不存在'
    },

    'en-us': {
      'app.name': 'MarkNest',
      'app.subtitle': 'A Markdown note library on your NAS',
      'app.tagline': 'Keep your thinking on your own disk',

      'common.search': 'Search',
      'common.cancel': 'Cancel',
      'common.confirm': 'OK',
      'common.close': 'Close',
      'common.save': 'Save',
      'common.saving': 'Saving…',
      'common.saved': 'Saved',
      'common.delete': 'Delete',
      'common.rename': 'Rename',
      'common.retry': 'Retry',
      'common.retryAction': 'Retry',
      'common.loading': 'Loading…',
      'common.empty': 'Nothing here yet',
      'common.unknown': 'Unknown',
      'common.back': 'Back',
      'common.copy': 'Copy',
      'common.copied': 'Copied',
      'common.download': 'Download',
      'common.more': 'More',
      'common.open': 'Open',
      'common.create': 'Create',
      'common.refresh': 'Refresh',
      'common.all': 'All',
      'common.optional': 'optional',
      'common.browse': 'Browse',
      'common.remove': 'Remove',
      'common.restore': 'Restore',
      'common.preview': 'Preview',
      'common.edit': 'Edit',
      'common.export': 'Export',
      'common.share': 'Share',
      'common.new': 'New',
      'common.add': 'Add',
      'common.apply': 'Apply',
      'common.reset': 'Reset',
      'common.enabled': 'On',
      'common.disabled': 'Off',
      'common.never': 'Never',
      'common.none': 'None',
      'common.yes': 'Yes',
      'common.no': 'No',
      'common.words': 'words',
      'common.actions': 'Actions',
      'common.name': 'Name',
      'common.path': 'Path',
      'common.size': 'Size',
      'common.updated': 'Updated',
      'common.created': 'Created',
      'common.status': 'Status',
      'common.language': 'Language',
      'common.settings': 'Settings',
      'common.version': 'Version',
      'common.done': 'Done',
      'common.uploading': 'Uploading…',
      'common.failed': 'Failed',
      'common.rootFolder': 'Root folder',
      'common.untitled': 'Untitled',
      'common.folder': 'Folder',
      'common.note': 'Note',
      'common.notes': 'notes',
      'common.folders': 'folders',
      'common.menu': 'Menu',
      'common.renameAction': 'Rename',

      'time.justNow': 'just now',
      'time.minutesAgo': '{n} min ago',
      'time.hoursAgo': '{n} h ago',
      'time.daysAgo': '{n} d ago',

      'nav.library': 'Library',
      'nav.import': 'Import',
      'nav.settings': 'Profile',
      'nav.foldersSection': 'Folders',
      'nav.newFolder': 'New folder',
      'nav.allNotes': 'All notes',
      'nav.storage': 'Storage',
      'nav.menu': 'Open menu',
      'nav.collapse': 'Collapse sidebar',
      'nav.resizeSidebar': 'Resize sidebar',
      'nav.expand': 'Expand sidebar',
      'nav.quick': 'Quick start',
      'nav.libraryHint': 'Browse every note',

      'shell.searchPlaceholder': 'Search titles and note text…',
      'shell.searchHint': 'Search',
      'shell.newNote': 'New note',
      'shell.newFolder': 'New folder',
      'shell.userFallback': 'TOS user',
      'shell.libraryDown': 'Library unavailable',
      'shell.libraryDownHint': 'The shared folder this app owns is missing or unreadable. Reinstall the application from the App Center.',
      'shell.connectionLost': 'Cannot reach the service',
      'shell.retry': 'Reconnect',
      'shell.reindex': 'Rebuild index',
      'shell.reindexed': 'Index rebuilt',
      'shell.reindexRunning': 'Rebuilding the index…',
      'shell.storageUsage': '{size} used',
      'shell.storageFree': '{free} free',
      'shell.footerNote': 'Files stay on your NAS',
      'shell.themeToggle': 'Toggle theme',
      'shell.openShared': 'Open shared folder settings',

      'library.title': 'Library',
      'library.subtitle': 'Every note is a plain Markdown file inside your own shared folder.',
      'library.newNote': 'New note',
      'library.import': 'Import',
      'library.grid': 'Card view',
      'library.list': 'List view',
      'library.sortUpdated': 'Last updated',
      'library.sortName': 'Name',
      'library.sortSize': 'Size',
      'library.sortLabel': 'Sort',
      'library.viewLabel': 'View',
      'library.searchPlaceholder': 'Filter this view…',
      'library.emptyTitle': 'No notes here yet',
      'library.emptyBody': 'Start a new note, or bring in Markdown files you already have.',
      'library.emptyAction': 'Write the first note',
      'library.noResults': 'No notes match',
      'library.noResultsBody': 'Try a shorter keyword, or clear the filters.',
      'library.clearFilters': 'Clear filters',
      'library.statsNotes': 'Notes',
      'library.statsFolders': 'Folders',
      'library.statsSize': 'Space used',
      'library.statsIndexed': 'Indexed',
      'library.allNotes': 'All notes',
      'library.openFromNas': 'Open from NAS',
      'library.openFromNasHint': 'Browse the NAS folder that holds your notes and open a Markdown file directly.',
      'library.nasScopeHint': 'Only Markdown documents inside the MarkNest shared folder can be browsed and opened. Other folders or formats such as PDF must be converted and placed in this folder first.',
      'library.nasUp': 'Up',
      'library.nasEmpty': 'No openable files in this folder',
      'library.nasUnsupported': 'Cannot open here',
      'library.notesHere': '{n} note(s)',
      'library.inFolder': 'In “{name}”',
      'library.newFolderTitle': 'New folder',
      'library.newFolderLabel': 'Folder path',
      'library.newFolderPlaceholder': 'e.g. Product/Release notes',
      'library.newFolderHint': 'Subfolders are created along with the path.',
      'library.folderCreated': 'Created folder “{name}”',
      'library.deleteFolder': 'Delete folder',
      'library.deleteFolderTitle': 'Delete folder “{name}”?',
      'library.deleteFolderConfirm': 'Only an empty folder can be deleted; notes inside it are never removed.',
      'library.folderDeleted': 'Deleted folder “{name}”',
      'library.newNoteTitle': 'New note',
      'library.newNoteLabel': 'Note path',
      'library.newNotePlaceholder': 'e.g. Ideas/How to write a title.md',
      'library.newNoteHint': 'A .md extension is added when omitted; subfolders are created automatically.',
      'library.noteCreated': 'Created “{name}”',
      'library.renameTitle': 'Rename note',
      'library.renameLabel': 'New path',
      'library.renamed': 'Renamed',
      'library.deleteTitle': 'Delete “{name}”?',
      'library.deleteConfirm': 'The file leaves your library and cannot be undone from inside the app.',
      'library.deleted': 'Deleted “{name}”',
      'library.moreActions': 'More actions',
      'library.openReader': 'Read',
      'library.editNote': 'Edit',
      'library.copyPath': 'Copy path',
      'library.pathCopied': 'Path copied',
      'library.emptyFolder': 'This folder is empty',
      'library.emptyFolderBody': 'Start a note inside “{name}”.',
      'library.moveHint': 'Tip: the same files can be managed directly over SMB.',
      'library.folder': 'Folder',
      'library.note': 'Note',
      'library.indexPending': 'Indexing',

      'reader.edit': 'Edit',
      'reader.versions': 'Versions',
      'reader.export': 'Export',
      'reader.share': 'Share',
      'reader.toc': 'Contents',
      'reader.tocEmpty': 'No headings in this note',
      'reader.readingTime': '{n} min read',
      'reader.words': '{n} words',
      'reader.updated': 'Updated {time}',
      'reader.back': 'Back to library',
      'reader.more': 'More',
      'reader.deleteTitle': 'Delete “{name}”?',
      'reader.deleteConfirm': 'The file leaves your library and cannot be undone from inside the app.',
      'reader.deleted': 'Deleted “{name}”',
      'reader.notFound': 'That note could not be found',
      'reader.notFoundBody': 'It may have been moved, renamed or deleted.',
      'reader.copyLink': 'Copy link',
      'reader.linkCopied': 'Link copied',
      'reader.exportMarkdown': 'Export Markdown',
      'reader.exportHtml': 'Export HTML',
      'reader.exportHtmlDone': 'HTML exported',
      'reader.shareRich': 'Copy as rich text',
      'reader.shareRichDone': 'Rich text copied — paste it into mail or chat',
      'reader.endOfNote': 'End of note',
      'reader.deleteNote': 'Delete note',
      'reader.allNotes': 'All notes',
      'reader.print': 'Print',

      'editor.title': 'Editor',
      'editor.untitled': 'Untitled',
      'editor.save': 'Save',
      'editor.saving': 'Saving…',
      'editor.saved': 'Saved',
      'editor.savedAt': 'Saved · {time}',
      'editor.unsaved': 'Unsaved changes',
      'editor.unsavedShort': 'Unsaved',
      'editor.leaveDiscard': 'Leave without saving',
      'editor.stayEditing': 'Keep editing',
      'editor.preview': 'Preview',
      'editor.split': 'Split',
      'editor.outline': 'Outline',
      'editor.outlineEmpty': 'No headings yet',
      'editor.outlineEmptyBody': 'Mark headings with # or ## and the outline builds itself.',
      'editor.versions': 'Version history',
      'editor.versionHistory': 'Version history',
      'editor.versionEmpty': 'No earlier versions',
      'editor.versionEmptyBody': 'The previous content is recorded here before each save.',
      'editor.versionRestore': 'Restore this version',
      'editor.versionRestoreConfirm': 'Replace the current content with this version? The current content is recorded first.',
      'editor.versionRestored': 'Version restored',
      'editor.versionAt': '{time}',
      'editor.versionSize': '{size}',
      'editor.versionCurrent': 'Current',
      'editor.versionLoadFail': 'That version could not be loaded',
      'editor.exportShare': 'Export & share',
      'editor.exportMd': 'Export Markdown file',
      'editor.exportHtml': 'Export as HTML',
      'editor.copyLink': 'Copy reading link',
      'editor.copyMarkdown': 'Copy Markdown',
      'editor.copyRich': 'Copy as rich text',
      'editor.copied': 'Copied',
      'editor.exportHtmlDone': 'HTML file exported',
      'editor.conflictTitle': 'This note was changed elsewhere',
      'editor.conflictBody': 'Your edit was not saved. You can overwrite their change, or keep your version as a copy.',
      'editor.overwrite': 'Overwrite their change',
      'editor.reload': 'Discard mine and reload',
      'editor.saveCopy': 'Save as a copy',
      'editor.readOnly': 'Read-only',
      'editor.readOnlyHint': 'This note cannot be written to, but you can still read, export and copy it.',
      'editor.toolbar': 'Formatting toolbar',
      'editor.bold': 'Bold',
      'editor.italic': 'Italic',
      'editor.strike': 'Strikethrough',
      'editor.heading': 'Heading',
      'editor.h1': 'Heading 1',
      'editor.h2': 'Heading 2',
      'editor.h3': 'Heading 3',
      'editor.quote': 'Quote',
      'editor.code': 'Code block',
      'editor.inlineCode': 'Inline code',
      'editor.link': 'Link',
      'editor.image': 'Insert image',
      'editor.ul': 'Bulleted list',
      'editor.ol': 'Numbered list',
      'editor.task': 'Task list',
      'editor.table': 'Table',
      'editor.hr': 'Divider',
      'editor.linkTitle': 'Insert link',
      'editor.linkText': 'Link text',
      'editor.linkUrl': 'Link URL',
      'editor.imageUploading': 'Uploading image…',
      'editor.imageInserted': 'Image inserted',
      'editor.imageFailed': 'Image upload failed',
      'editor.dropImage': 'Drop to insert the image',
      'editor.pasteImage': 'Clipboard image found, uploading…',
      'editor.wordCount': '{n} words',
      'editor.charCount': '{n} chars',
      'editor.lineCol': 'Line {line}, column {col}',
      'editor.markdown': 'Markdown',
      'editor.saveHint': 'Ctrl / ⌘ + S to save',
      'editor.backToLibrary': 'Back to library',
      'editor.imageTooLarge': 'The image is too large',
      'editor.unsupportedImage': 'Only PNG, JPEG, GIF, WebP and BMP images are supported',
      'editor.uploadProgress': 'Uploading {n}%',
      'editor.autosaved': 'Autosaved',
      'editor.focusMode': 'Focus mode',
      'editor.exitFocus': 'Exit focus',
      'editor.stats': '{words} words · {lines} lines',

      'import.title': 'Upload & import',
      'import.subtitle': 'Bring existing Markdown and TXT files into the library, or paste some text to start.',
      'import.dropTitle': 'Drop files here',
      'import.dropBody': '.md / .markdown / .mdown / .txt, up to {n} files at a time.',
      'import.browse': 'Choose files',
      'import.destination': 'Import into',
      'import.rootFolder': 'Root folder',
      'import.conflict': 'Name conflicts',
      'import.conflictRename': 'Keep both, rename the new one',
      'import.conflictRenameHint': 'For example “Note (2).md”',
      'import.conflictSkip': 'Skip files that already exist',
      'import.conflictSkipHint': 'Never overwrite what is on disk',
      'import.queue': 'Files to import',
      'import.queueEmpty': 'No files chosen yet',
      'import.queueEmptyBody': 'Drop files or use the button above; they are listed here first.',
      'import.start': 'Start import',
      'import.uploading': 'Importing…',
      'import.clear': 'Clear the list',
      'import.statusPending': 'Waiting',
      'import.statusUploading': 'Importing',
      'import.statusCreated': 'Imported',
      'import.statusSkipped': 'Skipped',
      'import.statusFailed': 'Failed',
      'import.summary': 'Import finished: {created} added, {skipped} skipped, {failed} failed.',
      'import.summaryDone': 'Finished',
      'import.goLibrary': 'Open the library',
      'import.textTitle': 'Create from text',
      'import.textBody': 'Paste Markdown or plain text and save it straight as a note.',
      'import.textName': 'Note path',
      'import.textNamePlaceholder': 'e.g. Ideas/A thought from today.md',
      'import.textPlaceholder': 'Paste or type here…',
      'import.textCreate': 'Create note',
      'import.textCreated': 'Created “{name}”',
      'import.tooMany': 'At most {n} files can be imported at once',
      'import.accepted': 'Accepts {exts}',
      'import.fileCount': '{n} file(s) chosen',
      'import.removeFile': 'Remove',
      'import.invalidType': 'Unsupported file type',
      'import.noFiles': 'Choose files to import first',
      'import.progress': 'Uploading {done}/{total}',
      'import.failedTitle': 'Some files could not be imported',
      'import.retryFailed': 'Retry failed files',
      'import.dragActive': 'Release to add the files',
      'import.noteHint': 'Files are read as UTF-8; a BOM is handled automatically.',

      'settings.title': 'Profile',
      'settings.subtitle': 'Account, appearance and data all live here.',
      'settings.account': 'Account & library',
      'settings.accountBody': 'Each TOS user has a private library; other accounts never see your files.',
      'settings.user': 'Signed in as',
      'settings.libraryPath': 'Library location',
      'settings.libraryStatus': 'Status',
      'settings.writable': 'Read & write',
      'settings.readOnly': 'Read-only',
      'settings.reindex': 'Rebuild search index',
      'settings.reindexing': 'Rebuilding…',
      'settings.reindexed': 'Index rebuilt',
      'settings.reindexHint': 'The index is a cache; rebuilding it never touches your notes.',
      'settings.openShared': 'Open shared folder settings',
      'settings.openSharedHint': 'Manage this shared folder from the TOS control panel.',
      'settings.openSharedUnavailable': 'Not running inside the TOS desktop, so the control panel cannot be opened.',
      'settings.appearance': 'Appearance',
      'settings.appearanceBody': 'These preferences are stored in this browser only.',
      'settings.theme': 'Theme',
      'settings.themeSystem': 'System',
      'settings.themeLight': 'Light',
      'settings.themeDark': 'Dark',
      'settings.accent': 'Accent',
      'settings.accentForest': 'Pine',
      'settings.accentClay': 'Clay',
      'settings.accentIndigo': 'Indigo',
      'settings.fontSize': 'Reading size',
      'settings.fontSmall': 'Small',
      'settings.fontMedium': 'Medium',
      'settings.fontLarge': 'Large',
      'settings.readingWidth': 'Reading width',
      'settings.widthNarrow': 'Narrow',
      'settings.widthMedium': 'Medium',
      'settings.widthWide': 'Wide',
      'settings.behavior': 'Habits',
      'settings.behaviorBody': 'Where the app opens and how editing behaves.',
      'settings.language': 'Interface language',
      'settings.languageHint': 'Follows the TOS interface language by default; picking a language here fixes the choice.',
      'settings.languageAuto': 'Follow the TOS language',
      'settings.defaultPage': 'Start page',
      'settings.defaultLibrary': 'Library',
      'settings.defaultImport': 'Import',
      'settings.autosave': 'Autosave',
      'settings.autosaveHint': 'Saves after a pause in typing; conflict detection still applies.',
      'settings.data': 'Data overview',
      'settings.dataBody': 'Numbers come from this account’s library and index.',
      'settings.noteCount': 'Notes',
      'settings.versionCount': 'Versions',
      'settings.folderCount': 'Folders',
      'settings.storageUsed': 'Space used',
      'settings.indexEngine': 'Search engine',
      'settings.engineFts': 'Full-text index',
      'settings.engineScan': 'Per-note scan',
      'settings.versionsKept': 'Versions kept',
      'settings.versionsKeptValue': '{n} per note',
      'settings.importLimit': 'Batch import limit',
      'settings.importLimitValue': '{n} files',
      'settings.about': 'About',
      'settings.aboutBody': 'MarkNest stores notes as ordinary Markdown files — no private format and no cloud dependency.',
      'settings.version': 'Application version',
      'settings.reset': 'Reset appearance and habits',
      'settings.resetConfirm': 'Restore the default theme, size, width and language? Note files are untouched.',
      'settings.resetDone': 'Defaults restored',
      'settings.saved': 'Preference saved',
      'settings.indexRebuilt': 'Index rebuilt',
      'settings.apiNote': 'Data is reached through your TOS session and never leaves the device.',

      'search.title': 'Search notes',
      'search.placeholder': 'Type a keyword…',
      'search.empty': 'Start typing to search',
      'search.emptyBody': 'Titles, paths and note text are all matched.',
      'search.noResults': 'No notes matched',
      'search.noResultsBody': 'Try a shorter keyword or a different phrasing.',
      'search.hint': '↑ ↓ to choose · Enter to open · Esc to close',
      'search.engineFts': 'full-text index',
      'search.engineScan': 'per-note scan',
      'search.results': '{n} note(s) found',
      'search.close': 'Close search',

      'err.unknown': 'Something went wrong',
      'err.network': 'Cannot reach the service, please try again',
      'err.timeout': 'The request timed out',
      'err.http': 'The service answered with an error (HTTP {status})',
      'err.session': 'Your session expired, returning to the sign-in page…',
      'err.upload': 'The upload failed, please try again',
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
      'err.code3009': 'Only PNG, JPEG, GIF and WebP images can be stored as attachments',
      'err.code3010': 'That attachment does not exist',
      'err.code3011': 'The search index is unavailable; your notes are unaffected',
      'err.code3012': 'That name cannot be used (no slashes, no leading dot, at most 255 bytes)',
      'err.code3013': 'Your TOS user could not be determined; sign in again and retry',
      'err.code3014': 'The index is being rebuilt, please try again',
      'err.code3015': 'The folder is not empty and cannot be deleted',
      'err.code3016': 'That earlier version does not exist'
    }
  };

  /* Additional dictionaries are loaded as plain scripts before this file so a
     language can be added without touching the three built-in tables. */
  var EXTRA = global.MARKNEST_I18N || {};
  Object.keys(EXTRA).forEach(function (tag) {
    if (EXTRA[tag]) {
      STRINGS[tag] = EXTRA[tag];
    }
  });

  var SUPPORTED = Object.keys(STRINGS);
  var DEFAULT = 'en-us';
  var STORE_KEY = 'marknest.lang';
  var current = DEFAULT;

  /* TOS keeps the operator's interface language in the desktop document. The
     application is framed under the same origin, so those stores are readable;
     the key has changed between TOS releases, so every plausible spelling is
     probed and the value is validated before it is trusted. */
  var TOS_KEYS = [
    'tos_language', 'tos-lang', 'tosLanguage', 'tos_lang',
    'langModel', 'lang_model',
    'language', 'lang', 'locale', 'ui_language', 'i18n_language'
  ];
  var TOS_PARAMS = ['lang', 'language', 'locale'];

  function normalizeTag(value) {
    var tag = String(value === undefined || value === null ? '' : value)
      .trim().toLowerCase().replace(/_/g, '-');
    if (!tag || tag.length > 20 || !/^[a-z]{2,3}(-[a-z0-9]{1,8})*$/.test(tag)) {
      return null;
    }
    return tag;
  }

  function tagFor(tag) {
    if (!tag) {
      return null;
    }
    if (tag.indexOf('zh') === 0) {
      return /hk|tw|mo|hant/.test(tag) ? 'zh-hk' : 'zh-cn';
    }
    if (tag.indexOf('en') === 0) {
      return 'en-us';
    }
    if (tag.indexOf('ja') === 0) {
      return 'ja-jp';
    }
    if (tag.indexOf('ko') === 0) {
      return 'ko-kr';
    }
    if (tag.indexOf('de') === 0) {
      return 'de-de';
    }
    if (tag.indexOf('fr') === 0) {
      return 'fr-fr';
    }
    if (tag.indexOf('es') === 0) {
      return 'es-es';
    }
    if (tag.indexOf('ru') === 0) {
      return 'ru-ru';
    }
    return null;
  }

  function resolveTag(tag) {
    // A TOS language this build has no dictionary for is rendered in the
    // English base rather than falling back to the browser's preference.
    return tagFor(tag) || DEFAULT;
  }

  function readStore(store) {
    if (!store) {
      return null;
    }
    var i;
    var tag;
    for (i = 0; i < TOS_KEYS.length; i += 1) {
      try {
        tag = normalizeTag(store.getItem(TOS_KEYS[i]));
      } catch (error) {
        return null;
      }
      if (tag) {
        return tag;
      }
    }
    try {
      for (i = 0; i < store.length; i += 1) {
        var key = store.key(i);
        if (!key || key.indexOf('marknest.') === 0 || !/lang|locale/i.test(key)) {
          continue;
        }
        tag = normalizeTag(store.getItem(key));
        if (tag) {
          return tag;
        }
      }
    } catch (error) {
      /* treat as absent */
    }
    return null;
  }

  function readCookie() {
    var text = '';
    try {
      text = global.document.cookie || '';
    } catch (error) {
      return null;
    }
    var parts = text.split(';');
    for (var i = 0; i < parts.length; i += 1) {
      var cut = parts[i].indexOf('=');
      if (cut < 0 || !/lang|locale/i.test(parts[i].slice(0, cut))) {
        continue;
      }
      var raw = parts[i].slice(cut + 1).trim();
      try {
        raw = decodeURIComponent(raw);
      } catch (error) {
        /* keep the raw value */
      }
      var tag = normalizeTag(raw);
      if (tag) {
        return tag;
      }
    }
    return null;
  }

  function readParam() {
    var query = '';
    try {
      query = String(global.location.search || '');
    } catch (error) {
      return null;
    }
    for (var i = 0; i < TOS_PARAMS.length; i += 1) {
      var match = new RegExp('[?&]' + TOS_PARAMS[i] + '=([^&]+)').exec(query);
      if (!match) {
        continue;
      }
      var tag = normalizeTag(decodeURIComponent(match[1]));
      if (tag) {
        return tag;
      }
    }
    return null;
  }

  function readParent() {
    var parentDoc = null;
    var parentWindow = null;
    try {
      parentWindow = global.parent && global.parent !== global ? global.parent : null;
      parentDoc = parentWindow ? parentWindow.document : null;
    } catch (error) {
      return null;
    }
    if (!parentDoc) {
      return null;
    }
    try {
      var html = parentDoc.documentElement;
      var tag = normalizeTag(html && (html.getAttribute('lang') || html.getAttribute('xml:lang')));
      if (tag) {
        return tag;
      }
    } catch (error) {
      /* fall through to the parent's storage */
    }
    try {
      return readStore(parentWindow.localStorage);
    } catch (error) {
      return null;
    }
  }

  /* The raw TOS tag, whether or not this build has a dictionary for it. */
  function tosLanguage() {
    return readParam() || readStore(ownStore()) || readCookie() || readParent();
  }

  function ownStore() {
    try {
      return global.localStorage;
    } catch (error) {
      return null;
    }
  }


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
    var stored = storedLanguage();
    if (stored) {
      return stored;
    }
    return systemLanguage();
  }

  /* Explicit choice, written only when the operator picks a language. */
  function storedLanguage() {
    var stored = null;
    try {
      stored = global.localStorage.getItem(STORE_KEY);
    } catch (error) {
      // Storage can be unavailable inside a sandboxed frame.
      stored = null;
    }
    return STRINGS[stored] ? stored : null;
  }

  /* TOS first, then the browser. A TOS language this build has no dictionary
     for resolves to the English base instead of the browser's preference. */
  function systemLanguage() {
    var tos = tosLanguage();
    if (tos) {
      return resolveTag(tos) || DEFAULT;
    }
    var languages = (global.navigator && (global.navigator.languages ||
      [global.navigator.language])) || [];
    for (var i = 0; i < languages.length; i += 1) {
      var tag = normalizeTag(languages[i]);
      if (!tag) {
        continue;
      }
      var supported = tagFor(tag);
      if (supported) {
        return supported;
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

  function setLanguage(tag, persist) {
    current = STRINGS[tag] ? tag : DEFAULT;
    if (persist !== false) {
      try {
        global.localStorage.setItem(STORE_KEY, current);
      } catch (error) {
        /* not fatal */
      }
    }
    if (global.document && global.document.documentElement) {
      global.document.documentElement.lang = current;
    }
    apply(global.document);
    return current;
  }

  /* Drop the explicit choice and take the language from TOS. */
  function follow() {
    try {
      global.localStorage.removeItem(STORE_KEY);
    } catch (error) {
      /* not fatal */
    }
    return setLanguage(systemLanguage(), false);
  }

  current = detect();

  global.I18N = {
    t: translate,
    errorText: errorText,
    apply: apply,
    setLanguage: setLanguage,
    getLanguage: function () { return current; },
    detect: detect,
    systemLanguage: systemLanguage,
    storedLanguage: storedLanguage,
    tosLanguage: tosLanguage,
    follow: follow,
    supported: SUPPORTED,
    // Exposed so tools/webui_check.js can compare the key sets mechanically.
    tables: STRINGS
  };
})(window);
