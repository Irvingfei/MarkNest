/* MarkNest for TOS - personal centre.

   Two kinds of settings meet here and they are kept visibly apart: appearance
   and behaviour live in localStorage and apply immediately, while the account
   and library figures come from the server and are read-only facts about this
   operator's own folder. Nothing on this page edits notes. */

(function (global) {
  'use strict';

  var LANGUAGES = [
    { tag: 'zh-cn', label: '简体中文' },
    { tag: 'zh-hk', label: '繁體中文' },
    { tag: 'en-us', label: 'English' },
    { tag: 'ja-jp', label: '日本語' },
    { tag: 'ko-kr', label: '한국어' },
    { tag: 'de-de', label: 'Deutsch' },
    { tag: 'fr-fr', label: 'Français' },
    { tag: 'es-es', label: 'Español' },
    { tag: 'ru-ru', label: 'Русский' }
  ];

  var nodes = {};
  var mounted = false;

  /* --------------------------------------------------------------- helpers */

  function panel(title, sub, actions, extraClass) {
    var head = UI.el('div', { class: 'panel-head' }, [
      UI.el('div', null, [
        UI.el('h2', { class: 'panel-title', text: title }),
        sub ? UI.el('p', { class: 'panel-sub', text: sub }) : null
      ])
    ]);
    if (actions) {
      head.appendChild(actions);
    }
    return UI.el('section', { class: 'panel' + (extraClass ? ' ' + extraClass : '') }, [head]);
  }

  function settingRow(name, desc, control) {
    return UI.el('div', { class: 'setting-row' }, [
      UI.el('div', { class: 'setting-text' }, [
        UI.el('div', { class: 'setting-name', text: name }),
        desc ? UI.el('div', { class: 'setting-desc', text: desc }) : null
      ]),
      UI.el('div', { class: 'setting-control' }, [control])
    ]);
  }

  function segmented(entries, value, onPick) {
    var group = UI.el('div', { class: 'segmented' });
    entries.forEach(function (entry) {
      var button = UI.el('button', {
        type: 'button',
        class: entry.value === value ? 'is-active' : '',
        text: entry.label,
        onclick: function () {
          Array.prototype.forEach.call(group.children, function (node) {
            node.classList.toggle('is-active', node === button);
          });
          onPick(entry.value);
        }
      });
      group.appendChild(button);
    });
    return group;
  }

  function selectBox(entries, value, onChange) {
    var select = UI.el('select', { class: 'select' });
    entries.forEach(function (entry) {
      select.appendChild(UI.el('option', {
        value: entry.value,
        text: entry.label,
        selected: entry.value === value
      }));
    });
    select.value = value;
    select.addEventListener('change', function () {
      onChange(select.value);
    });
    return select;
  }

  function markSaved() {
    UI.toast(I18N.t('settings.saved'), 'ok', 1800);
  }

  /* ------------------------------------------------------------------ mount */

  function mount(host) {
    mounted = true;

    var page = UI.el('div', { class: 'page page-settings' });
    var scroll = UI.el('div', { class: 'page-scroll' });
    page.appendChild(scroll);
    host.appendChild(page);

    scroll.appendChild(UI.el('div', { class: 'page-head' }, [
      UI.el('div', { class: 'page-head-text' }, [
        UI.el('h1', { class: 'page-title', text: I18N.t('settings.title') }),
        UI.el('p', { class: 'page-sub', text: I18N.t('settings.subtitle') })
      ])
    ]));

    var grid = UI.el('div', { class: 'settings-grid' });
    scroll.appendChild(grid);

    grid.appendChild(buildAccount());
    grid.appendChild(buildAppearance());
    grid.appendChild(buildBehaviour());
    grid.appendChild(buildData());
    grid.appendChild(buildAbout());

    Shell.setCrumb([
      { label: I18N.t('nav.library'), href: Router.href('library', {}) }
    ]);
    Shell.setTitle(I18N.t('settings.title'));
    Shell.setActions([]);

    Store.loadStats().then(function () {
      if (mounted) {
        renderData();
      }
    }).catch(function () {
      /* the stored figures remain displayed */
    });
  }

  function unmount() {
    mounted = false;
    nodes = {};
  }

  /* ---------------------------------------------------------------- account */

  function buildAccount() {
    var me = Store.state.me || {};
    var name = me.user || I18N.t('shell.userFallback');
    var writable = !!me.writable;

    var actions = UI.el('div', { class: 'panel-actions' });
    if (global.TosHost && global.TosHost.canOpenSharedFolders()) {
      actions.appendChild(UI.el('button', {
        type: 'button',
        class: 'btn btn-sm',
        title: I18N.t('settings.openSharedHint'),
        onclick: function () {
          if (!global.TosHost.openSharedFolders()) {
            UI.toast(I18N.t('settings.openSharedUnavailable'), 'warn');
          }
        }
      }, [UI.icon('external'), UI.el('span', { text: I18N.t('settings.openShared') })]));
    }

    var card = panel(I18N.t('settings.account'), I18N.t('settings.accountBody'), actions);

    card.appendChild(UI.el('div', { class: 'account-row' }, [
      UI.el('span', { class: 'avatar avatar-lg', text: initial(name) }),
      UI.el('div', null, [
        UI.el('div', { class: 'account-name', text: name }),
        UI.el('div', { class: 'account-sub', text: I18N.t('settings.user') })
      ])
    ]));

    var statusBadge = me.exists === false
      ? UI.badge('bad', I18N.t('settings.readOnly'))
      : (writable ? UI.badge('ok', I18N.t('settings.writable')) : UI.badge('warn', I18N.t('settings.readOnly')));

    card.appendChild(UI.el('div', { class: 'kv' }, [
      kvRow(I18N.t('settings.libraryPath'), me.library_path || '—', true),
      kvRow(I18N.t('settings.libraryStatus'), statusBadge, false)
    ]));

    if (!me.exists || (!writable && (me.write_reason || me.read_reason))) {
      card.appendChild(UI.el('p', {
        class: 'panel-sub',
        text: me.write_reason || me.read_reason
      }));
    }

    card.appendChild(UI.el('p', { class: 'panel-sub', text: I18N.t('settings.apiNote') }));
    return card;
  }

  function initial(name) {
    var text = String(name || '').trim();
    return text ? text.charAt(0).toUpperCase() : 'M';
  }

  function kvRow(key, value, mono) {
    var valueNode = typeof value === 'string'
      ? UI.el('span', { class: 'kv-value' + (mono ? '' : ' is-text'), text: value })
      : UI.el('span', { class: 'kv-value is-text' }, [value]);
    return UI.el('div', { class: 'kv-row' }, [
      UI.el('span', { class: 'kv-key', text: key }),
      valueNode
    ]);
  }

  /* ------------------------------------------------------------- appearance */

  function buildAppearance() {
    var settings = Store.settings;
    var card = panel(I18N.t('settings.appearance'), I18N.t('settings.appearanceBody'));

    card.appendChild(settingRow(
      I18N.t('settings.theme'),
      '',
      segmented([
        { value: 'system', label: I18N.t('settings.themeSystem') },
        { value: 'light', label: I18N.t('settings.themeLight') },
        { value: 'dark', label: I18N.t('settings.themeDark') }
      ], settings.get('theme'), function (value) {
        settings.set('theme', value);
        syncThemeButton();
        markSaved();
      })
    ));

    var swatches = UI.el('div', { class: 'swatches' });
    [
      { value: 'forest', label: I18N.t('settings.accentForest') },
      { value: 'clay', label: I18N.t('settings.accentClay') },
      { value: 'indigo', label: I18N.t('settings.accentIndigo') }
    ].forEach(function (entry) {
      var swatch = UI.el('button', {
        type: 'button',
        class: 'swatch' + (settings.get('accent') === entry.value ? ' is-active' : ''),
        dataset: { swatch: entry.value },
        title: entry.label,
        'aria-label': entry.label,
        onclick: function () {
          Array.prototype.forEach.call(swatches.children, function (node) {
            node.classList.toggle('is-active', node === swatch);
          });
          settings.set('accent', entry.value);
          markSaved();
        }
      });
      swatches.appendChild(swatch);
    });
    card.appendChild(settingRow(I18N.t('settings.accent'), '', swatches));

    card.appendChild(settingRow(
      I18N.t('settings.fontSize'),
      '',
      segmented([
        { value: 'sm', label: I18N.t('settings.fontSmall') },
        { value: 'md', label: I18N.t('settings.fontMedium') },
        { value: 'lg', label: I18N.t('settings.fontLarge') }
      ], settings.get('fontSize'), function (value) {
        settings.set('fontSize', value);
        markSaved();
      })
    ));

    card.appendChild(settingRow(
      I18N.t('settings.readingWidth'),
      '',
      segmented([
        { value: 'narrow', label: I18N.t('settings.widthNarrow') },
        { value: 'md', label: I18N.t('settings.widthMedium') },
        { value: 'wide', label: I18N.t('settings.widthWide') }
      ], settings.get('readingWidth'), function (value) {
        settings.set('readingWidth', value);
        markSaved();
      })
    ));

    return card;
  }

  /* The topbar button swaps its icon from the data-theme attribute alone, so
     only the attribute need be correct; the wrapper keeps the call site honest. */
  function syncThemeButton() {
    Store.applyAppearance();
  }

  /* -------------------------------------------------------------- behaviour */

  function buildBehaviour() {
    var settings = Store.settings;
    var card = panel(I18N.t('settings.behavior'), I18N.t('settings.behaviorBody'));

    var current = settings.get('language') || '';
    card.appendChild(settingRow(
      I18N.t('settings.language'),
      I18N.t('settings.languageHint'),
      selectBox(
        [{ value: '', label: I18N.t('settings.languageAuto') }].concat(
          LANGUAGES.map(function (entry) {
            return { value: entry.tag, label: entry.label };
          })
        ),
        current,
        function (tag) {
          Shell.applyLanguage(tag);
          Router.refresh();
          UI.toast(I18N.t('settings.saved'), 'ok', 1800);
        }
      )
    ));

    card.appendChild(settingRow(
      I18N.t('settings.defaultPage'),
      '',
      selectBox([
        { value: 'library', label: I18N.t('settings.defaultLibrary') },
        { value: 'import', label: I18N.t('settings.defaultImport') }
      ], settings.get('defaultPage') || 'library', function (value) {
        settings.set('defaultPage', value);
        markSaved();
      })
    ));

    var toggle = UI.el('input', {
      type: 'checkbox',
      checked: !!settings.get('autosave'),
      'aria-label': I18N.t('settings.autosave')
    });
    toggle.addEventListener('change', function () {
      settings.set('autosave', toggle.checked);
      markSaved();
    });

    card.appendChild(settingRow(
      I18N.t('settings.autosave'),
      I18N.t('settings.autosaveHint'),
      UI.el('label', { class: 'switch' }, [
        toggle,
        UI.el('span', { class: 'switch-track' })
      ])
    ));

    return card;
  }

  /* ------------------------------------------------------------------- data */

  function buildData() {
    var reindexBtn = UI.el('button', {
      type: 'button',
      class: 'btn btn-sm',
      onclick: function () { reindex(reindexBtn); }
    }, [UI.icon('refresh'), UI.el('span', { text: I18N.t('settings.reindex') })]);

    var actions = UI.el('div', { class: 'panel-actions' }, [reindexBtn]);
    var card = panel(I18N.t('settings.data'), I18N.t('settings.dataBody'), actions);

    nodes.dataGrid = UI.el('div', { class: 'data-grid' });
    nodes.dataKv = UI.el('div', { class: 'kv' });
    card.appendChild(nodes.dataGrid);
    card.appendChild(nodes.dataKv);

    var hint = UI.el('p', { class: 'panel-sub', text: I18N.t('settings.reindexHint') });
    card.appendChild(hint);

    renderData();
    return card;
  }

  function renderData() {
    if (!nodes.dataGrid) {
      return;
    }
    var stats = Store.state.stats || {};
    var options = Store.state.options || {};

    UI.clear(nodes.dataGrid);
    [
      { value: stats.notes || 0, label: I18N.t('settings.noteCount') },
      { value: stats.versions || 0, label: I18N.t('settings.versionCount') },
      { value: stats.folders || 0, label: I18N.t('settings.folderCount') },
      { value: UI.formatBytes(stats.bytes || 0), label: I18N.t('settings.storageUsed') }
    ].forEach(function (cell) {
      nodes.dataGrid.appendChild(UI.el('div', { class: 'data-cell' }, [
        UI.el('div', { class: 'data-value', text: String(cell.value) }),
        UI.el('div', { class: 'data-label', text: cell.label })
      ]));
    });

    UI.clear(nodes.dataKv);
    nodes.dataKv.appendChild(kvRow(
      I18N.t('settings.indexEngine'),
      stats.engine === 'fts5' ? I18N.t('settings.engineFts') : I18N.t('settings.engineScan'),
      false
    ));
    nodes.dataKv.appendChild(kvRow(
      I18N.t('settings.versionsKept'),
      options.version_keep
        ? I18N.t('settings.versionsKeptValue', { n: options.version_keep })
        : '—',
      false
    ));
    nodes.dataKv.appendChild(kvRow(
      I18N.t('settings.importLimit'),
      I18N.t('settings.importLimitValue', { n: options.max_import_files || 50 }),
      false
    ));
  }

  function reindex(button) {
    button.disabled = true;
    var label = button.querySelector('span');
    var previous = label ? label.textContent : '';
    if (label) {
      label.textContent = I18N.t('settings.reindexing');
    }
    API.indexScan().then(function () {
      return Store.loadStats();
    }).then(function () {
      if (!mounted) {
        return;
      }
      renderData();
      UI.toast(I18N.t('settings.indexRebuilt'), 'ok');
    }).catch(function (error) {
      if (mounted) {
        Shell.reportError(error);
      }
    }).then(function () {
      if (mounted) {
        button.disabled = false;
        if (label) {
          label.textContent = previous || I18N.t('settings.reindex');
        }
      }
    });
  }

  /* ------------------------------------------------------------------ about */

  function buildAbout() {
    var card = panel(I18N.t('settings.about'), I18N.t('settings.aboutBody'));
    var health = Store.state.health || {};
    var version = health.version || '';

    card.appendChild(UI.el('div', { class: 'about-row' }, [
      UI.el('img', {
        class: 'about-mark',
        src: 'icons/marknest.svg',
        alt: '',
        'aria-hidden': 'true'
      }),
      UI.el('div', null, [
        UI.el('div', { class: 'about-name', text: 'MarkNest' }),
        UI.el('div', { class: 'about-version', text: (version ? 'v' + version : '') })
      ])
    ]));

    card.appendChild(UI.el('p', { class: 'about-note', text: I18N.t('settings.aboutBody') }));

    var reset = UI.el('button', {
      type: 'button',
      class: 'btn btn-sm btn-danger',
      onclick: function () { confirmReset(); }
    }, [UI.icon('refresh'), UI.el('span', { text: I18N.t('settings.reset') })]);

    card.appendChild(UI.el('div', { class: 'setting-row' }, [
      UI.el('div', { class: 'setting-text' }, [
        UI.el('div', { class: 'setting-name', text: I18N.t('settings.reset') }),
        UI.el('div', { class: 'setting-desc', text: I18N.t('settings.resetConfirm') })
      ]),
      UI.el('div', { class: 'setting-control' }, [reset])
    ]));

    return card;
  }

  function confirmReset() {
    UI.confirm({
      title: I18N.t('settings.reset'),
      message: I18N.t('settings.resetConfirm'),
      confirmLabel: I18N.t('common.reset'),
      cancelLabel: I18N.t('common.cancel'),
      danger: true
    }).then(function (ok) {
      if (!ok || !mounted) {
        return;
      }
      Store.settings.reset();
      try {
        global.localStorage.removeItem('marknest.lang');
      } catch (error) {
        /* storage disabled: detection still works from the browser language */
      }
      var tag = I18N.detect();
      I18N.setLanguage(tag);
      Store.settings.set('language', '');
      Shell.sync();
      Router.refresh();
      UI.toast(I18N.t('settings.resetDone'), 'ok');
    });
  }

  /* ------------------------------------------------------------- document */

  function setDocumentTitle() {
    Shell.setTitle(I18N.t('settings.title'));
  }

  global.Pages = global.Pages || {};
  global.Pages.settings = {
    mount: mount,
    unmount: unmount,
    setDocumentTitle: setDocumentTitle
  };
})(window);
