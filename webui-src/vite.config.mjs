// Vite configuration for the MarkNest editor bundle.
//
// Three things here are deliberate and load-bearing:
//
//   * IIFE, not ESM. The rest of the WebUI is plain scripts loaded in order and
//     assigning one global each, and the TOS WebView is not a place to discover
//     a module-loading edge case. The bundle exposes `window.MDEditor` and is
//     loaded like any other script.
//
//   * A fixed file name, no content hash. The cache-busting scheme is a `?v=`
//     query string driven by the application version, and tools/bump_version.py
//     asserts that every such tag carries exactly one value. A hashed file name
//     would break that assertion and make the bundle impossible to reference
//     from static markup.
//
//   * No source maps, and no version injected into the bundle. The bundle is a
//     committed artefact: embedding the version would make it stale on every
//     version bump and force a Node build on machines that are meant never to
//     need one.
export default {
  base: './',
  build: {
    outDir: '../webui/js',
    emptyOutDir: false,
    target: 'es2019',
    minify: 'esbuild',
    sourcemap: false,
    lib: {
      entry: 'editor/index.js',
      name: 'MDEditor',
      formats: ['iife'],
      fileName: () => 'vendor.editor.js'
    },
    rollupOptions: {
      output: {
        entryFileNames: 'vendor.editor.js',
        assetFileNames: 'vendor.editor.[ext]'
      }
    }
  }
};
