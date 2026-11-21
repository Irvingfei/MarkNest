/* MarkNest for TOS - reading view.

   A note is read, not inspected: the page is typeset for a measure of about
   740px, the heading outline stays in view beside it, and progress is shown as
   a hairline at the top rather than as a number. Everything else - export,
   share, versions, delete - is one step away in the toolbar and the topbar.

   Attachment images are relative to the note's folder and sit behind the
   authenticated proxy, so the rendered markup is hydrated after insertion:
   Render.hydrateImages swaps the references for object URLs from the Store's
   cache. */

(function (global) {
  'use strict';

  var nodes = {};
  var note = null;
  var tocItems = [];
  var scrollHandler = null;

  function mount(host, params) {
    var path = (params && params.p) || '';
    note = null;
    nodes = {};

    if (!path) {
      Router.navigate('library', {}, { replace: true });
      return;
    }

    var page = UI.el('div', { class: 'page page-reader' });
    var scroll = UI.el('div', { class: 'page-scroll reader-scroll' });
    page.appendChild(scroll);
    host.appendChild(page);
    nodes.scroll = scroll;

    Shell.setTitle(Render.stemOf(path));
    Shell.setCrumb(crumbFor(path));
    Shell.setActions([]);
    loading();

    API.getNote(path).then(function (payload) {
      note = payload;
      Shell.renderFolders();
      render();
    }, function (error) {
      failed(error);
    });
  }

  function unmount() {
    if (scrollHandler && nodes.scroll) {
      nodes.scroll.removeEventListener('scroll', scrollHandler);
    }
    scrollHandler = null;
    nodes = {};
    note = null;
    tocItems = [];
  }

  function setDocumentTitle(params) {
    Shell.setTitle((params && params.p) ? Render.stemOf(params.p) : I18N.t('reader.title'));
  }

  function crumbFor(path) {
    // The article heading is the current note; the trail only carries its
    // folders so the title is not printed twice at the top of the page.
    return Shell.folderCrumb(Render.folderOf(path));
  }

  function loading() {
    var host = nodes.scroll;
    UI.clear(host);
    var shell = UI.el('div', { class: 'reader-shell' }, [
      UI.el('div', { class: 'reader-main' }, [
        UI.el('div', { class: 'skeleton', style: { height: '34px', width: '60%' } }),
        UI.el('div', { class: 'skeleton', style: { height: '13px', width: '36%', marginTop: '18px' } }),
        UI.el('div', { class: 'skeleton', style: { height: '13px', width: '92%', marginTop: '40px' } }),
        UI.el('div', { class: 'skeleton', style: { height: '13px', width: '88%' } }),
        UI.el('div', { class: 'skeleton', style: { height: '13px', width: '90%' } }),
        UI.el('div', { class: 'skeleton', style: { height: '13px', width: '62%' } })
      ]),
      UI.el('div', { class: 'reader-toc' }, [
        UI.el('div', { class: 'reader-toc-title', text: I18N.t('reader.toc') }),
        UI.el('div', { class: 'skeleton', style: { width: '80%' } }),
        UI.el('div', { class: 'skeleton', style: { width: '65%' } })
      ])
    ]);
    host.appendChild(shell);
  }

  function failed(error) {
    UI.clear(nodes.scroll);
    var missing = error && error.code === 3005;
    var box = UI.el('div', { class: 'reader-shell' }, [
      UI.el('article', { class: 'reader-main' }, [
        missing
          ? UI.emptyState({
            icon: 'file',
            title: I18N.t('reader.notFound'),
            body: I18N.t('reader.notFoundBody'),
            actions: [UI.el('button', {
              type: 'button',
              class: 'btn btn-primary',
              text: I18N.t('reader.allNotes'),
              onclick: function () { Router.navigate('library'); }
            })]
          })
          : UI.el('div', { id: 'reader-error' })
      ]),
      UI.el('div', { class: 'reader-toc' })
    ]);
    nodes.scroll.appendChild(box);
    if (!missing) {
      UI.errorBox(box.querySelector('#reader-error'),
        (error && error.message) || I18N.t('err.network'),
        function () { Router.refresh(); },
        '');
    }
    Shell.setActions([]);
  }

  /* ---------------------------------------------------------------- render */

  function render() {
    UI.clear(nodes.scroll);

    var content = note.content || '';
    var title = Render.titleOf(content, note.path);
    var words = Render.countWords(content);
    var outline = Render.outline(content);
    tocItems = outline.filter(function (item) { return item.level <= 4; });

    var progress = UI.el('div', { class: 'reader-progress' }, [
      UI.el('span', { class: 'reader-progress-fill', id: 'reader-progress-fill' })
    ]);
    nodes.progress = progress.firstChild;

    var main = UI.el('article', { class: 'reader-main' });
    main.appendChild(UI.el('nav', { class: 'reader-crumb', 'aria-label': 'breadcrumb' },
      crumbNodes(Render.folderOf(note.path))));

    main.appendChild(UI.el('h1', { class: 'reader-title', text: title }));
    main.appendChild(UI.el('div', { class: 'reader-meta' }, [
      UI.el('span', null, [UI.icon('type'), UI.el('span', { text: I18N.t('reader.words', { n: words }) })]),
      UI.el('span', { class: 'dot' }),
      UI.el('span', null, [UI.icon('clock'), UI.el('span', {
        text: I18N.t('reader.readingTime', { n: Render.readingMinutes(words) })
      })]),
      UI.el('span', { class: 'dot' }),
      UI.el('span', null, [UI.icon('file'), UI.el('span', {
        text: I18N.t('reader.updated', { time: UI.formatTimeAgo(note.mtime_ns) })
      })])
    ]));

    var actions = UI.el('div', { class: 'reader-actions' });
    actions.appendChild(UI.el('button', {
      type: 'button',
      class: 'btn btn-primary',
      onclick: function () { Router.navigate('edit', { p: note.path }); }
    }, [UI.icon('pen'), UI.el('span', { text: I18N.t('reader.edit') })]));
    actions.appendChild(UI.el('button', {
      type: 'button',
      class: 'btn',
      onclick: function () { Pages.doc.versions(note, function (restored) { note = restored; render(); }); }
    }, [UI.icon('clock'), UI.el('span', { text: I18N.t('reader.versions') })]));
    actions.appendChild(UI.el('button', {
      type: 'button',
      class: 'btn',
      onclick: function (event) { Pages.doc.exportMenu(event.currentTarget, note); }
    }, [UI.icon('download'), UI.el('span', { text: I18N.t('reader.export') })]));
    actions.appendChild(UI.el('button', {
      type: 'button',
      class: 'btn',
      onclick: function (event) { Pages.doc.shareMenu(event.currentTarget, note); }
    }, [UI.icon('share'), UI.el('span', { text: I18N.t('reader.share') })]));
    actions.appendChild(UI.el('span', { class: 'spacer' }));
    actions.appendChild(UI.el('button', {
      type: 'button',
      class: 'icon-btn',
      title: I18N.t('reader.deleteNote'),
      'aria-label': I18N.t('reader.deleteNote'),
      onclick: function () { remove(); }
    }, [UI.icon('trash')]));
    main.appendChild(actions);

    var prose = UI.el('div', { class: 'prose' });
    prose.innerHTML = Render.markdown(content);
    main.appendChild(prose);
    nodes.prose = prose;

    main.appendChild(UI.el('footer', { class: 'reader-foot' }, [
      UI.el('span', { text: I18N.t('reader.endOfNote') }),
      UI.el('span', { text: note.path })
    ]));

    var toc = UI.el('aside', { class: 'reader-toc', 'aria-label': I18N.t('reader.toc') });
    var tocInner = UI.el('div', { class: 'reader-toc-inner' }, [
      UI.el('div', { class: 'reader-toc-title', text: I18N.t('reader.toc') })
    ]);
    if (!tocItems.length) {
      tocInner.appendChild(UI.el('div', { class: 'reader-toc-empty', text: I18N.t('reader.tocEmpty') }));
    } else {
      tocItems.forEach(function (item, index) {
        var link = UI.el('a', {
          href: '#',
          text: item.text,
          dataset: { level: String(item.level), index: String(index) },
          onclick: function (event) {
            event.preventDefault();
            jumpTo(item);
          }
        });
        tocInner.appendChild(link);
      });
    }
    toc.appendChild(tocInner);
    nodes.toc = tocInner;

    var shell = UI.el('div', { class: 'reader-shell' }, [main, toc]);
    nodes.scroll.appendChild(progress);
    nodes.scroll.appendChild(shell);

    Shell.setTitle(title);
    Shell.setCrumb(crumbFor(note.path));
    renderTopActions();

    Render.hydrateImages(prose, note.path).then(bindLinks);
    bindScroll();
  }

  function crumbNodes(folder) {
    var parts = Shell.folderCrumb(folder);
    return parts.map(function (part, index) {
      var list = [];
      if (index > 0) {
        list.push(UI.icon('chevron-right'));
      }
      list.push(part.href && index < parts.length - 1
        ? UI.el('a', { href: part.href, text: part.label })
        : UI.el('span', { text: part.label }));
      return list;
    }).reduce(function (all, item) { return all.concat(item); }, []);
  }

  function renderTopActions() {
    Shell.setActions([
      UI.el('button', {
        type: 'button',
        class: 'btn btn-primary',
        onclick: function () { Router.navigate('edit', { p: note.path }); }
      }, [UI.icon('pen'), UI.el('span', { text: I18N.t('reader.edit') })]),
      UI.el('button', {
        type: 'button',
        class: 'icon-btn',
        title: I18N.t('reader.share'),
        'aria-label': I18N.t('reader.share'),
        onclick: function (event) { Pages.doc.shareMenu(event.currentTarget, note); }
      }, [UI.icon('share')]),
      UI.el('button', {
        type: 'button',
        class: 'icon-btn',
        title: I18N.t('reader.more'),
        'aria-label': I18N.t('reader.more'),
        onclick: function (event) {
          UI.menu(event.currentTarget, [
            {
              label: I18N.t('reader.versions'), icon: 'clock',
              onClick: function () { Pages.doc.versions(note, function (restored) { note = restored; render(); }); }
            },
            { label: I18N.t('reader.export'), icon: 'download', onClick: function () { Pages.doc.exportMenu(event.currentTarget, note); } },
            { label: I18N.t('common.copy') + ' · ' + I18N.t('common.path'), icon: 'copy', onClick: function () {
              UI.copyText(note.path).then(function (ok) {
                UI.toast(ok ? I18N.t('library.pathCopied') : I18N.t('err.unknown'), ok ? 'ok' : 'bad');
              });
            } },
            { divider: true },
            { label: I18N.t('reader.deleteNote'), icon: 'trash', danger: true, onClick: remove }
          ]);
        }
      }, [UI.icon('more')])
    ]);
  }

  /* ------------------------------------------------------------ navigation */

  function headingFor(item) {
    if (!nodes.prose) {
      return null;
    }
    var nodesList = nodes.prose.querySelectorAll('[data-line]');
    for (var i = 0; i < nodesList.length; i += 1) {
      if (Number(nodesList[i].getAttribute('data-line')) === item.line) {
        return nodesList[i];
      }
    }
    return null;
  }

  function jumpTo(item) {
    var heading = headingFor(item);
    if (!heading) {
      return;
    }
    var top = heading.getBoundingClientRect().top - nodes.scroll.getBoundingClientRect().top +
      nodes.scroll.scrollTop - 18;
    nodes.scroll.scrollTo({ top: top, behavior: 'smooth' });
  }

  function bindLinks() {
    if (!nodes.prose) {
      return;
    }
    Array.prototype.forEach.call(nodes.prose.querySelectorAll('a'), function (link) {
      link.addEventListener('click', function (event) {
        var href = link.getAttribute('href') || '';
        if (link.classList.contains('wikilink')) {
          event.preventDefault();
          var target = link.getAttribute('data-target') || '';
          if (target) {
            var dir = Render.folderOf(note.path);
            var path = dir ? dir + '/' + target : target;
            Router.navigate('read', { p: /\.(md|markdown|mdown)$/i.test(path) ? path : path + '.md' });
          }
          return;
        }
        if (/^(?:https?:)?\/\//i.test(href)) {
          event.preventDefault();
          global.open(href, '_blank', 'noopener');
        }
      });
    });
  }

  /* -------------------------------------------------------- scroll reading */

  function bindScroll() {
    var scroll = nodes.scroll;
    var fill = nodes.progress;
    var ticking = false;

    scrollHandler = function () {
      if (ticking) {
        return;
      }
      ticking = true;
      global.requestAnimationFrame(function () {
        ticking = false;
        if (!nodes.scroll || !fill) {
          return;
        }
        var max = scroll.scrollHeight - scroll.clientHeight;
        var ratio = max > 0 ? Math.min(1, scroll.scrollTop / max) : 0;
        fill.style.width = (ratio * 100).toFixed(2) + '%';
        highlightToc();
      });
    };
    scroll.addEventListener('scroll', scrollHandler, { passive: true });
    highlightToc();
  }

  function highlightToc() {
    if (!nodes.toc || !nodes.prose) {
      return;
    }
    var links = nodes.toc.querySelectorAll('a');
    if (!links.length) {
      return;
    }
    var line = 68;
    var active = -1;
    for (var i = 0; i < tocItems.length; i += 1) {
      var heading = headingFor(tocItems[i]);
      if (!heading) {
        continue;
      }
      var top = heading.getBoundingClientRect().top - nodes.scroll.getBoundingClientRect().top;
      if (top <= line) {
        active = i;
      }
    }
    Array.prototype.forEach.call(links, function (link, index) {
      link.classList.toggle('is-active', index === active);
    });
  }

  /* --------------------------------------------------------------- actions */

  function remove() {
    UI.confirm({
      title: I18N.t('reader.deleteTitle', { name: note.path }),
      message: I18N.t('reader.deleteConfirm'),
      confirmLabel: I18N.t('common.delete'),
      danger: true
    }).then(function (ok) {
      if (!ok) {
        return;
      }
      API.deleteNote(note.path).then(function () {
        UI.toast(I18N.t('reader.deleted', { name: note.path }), 'ok');
        return Store.loadLibraryAndStats().catch(function () { return null; });
      }).then(function () {
        Shell.renderFolders();
        Shell.renderStorage();
        Router.navigate('library');
      }).catch(Shell.reportError);
    });
  }

  global.Pages = global.Pages || {};
  global.Pages.reader = {
    mount: mount,
    unmount: unmount,
    setDocumentTitle: setDocumentTitle
  };
})(window);
