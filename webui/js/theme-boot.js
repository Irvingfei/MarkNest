/* Applies the stored theme before the first paint.

   Loaded as a plain blocking script ahead of the stylesheet, because a theme
   applied after load shows one frame of the wrong palette on every navigation. */

(function (global) {
  'use strict';

  var KEY = 'marknest.settings';
  var stored = {};
  try {
    stored = JSON.parse(global.localStorage.getItem(KEY) || '{}') || {};
  } catch (error) {
    stored = {};
  }

  var theme = stored.theme || 'system';
  if (theme === 'system') {
    var dark = !!(global.matchMedia &&
      global.matchMedia('(prefers-color-scheme: dark)').matches);
    theme = dark ? 'dark' : 'light';
  }

  var root = global.document.documentElement;
  root.setAttribute('data-theme', theme === 'dark' ? 'dark' : 'light');
  root.setAttribute('data-accent', stored.accent || 'forest');
  root.setAttribute('data-font', stored.fontSize || 'md');
  root.setAttribute('data-width', stored.readingWidth || 'md');
})(window);
