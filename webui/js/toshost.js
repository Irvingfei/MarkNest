/* MarkNest for TOS - the message channel to the TOS desktop host.

   Used for one thing: when the notes library is unavailable, the operator's
   next move is in the control panel, and a URL cannot take them there. TOS 7
   has no address for a shared folder's permission page - the file manager is a
   single-route SPA whose property sheet is opened by a store commit, and the
   control panel is a component of the desktop shell rather than a page - so a
   link would be a button that goes nowhere.

   What the platform does publish is the channel the desktop uses for the
   applications it embeds. Its own window component accepts, from an embedded
   application, a message it dispatches to a system window:

       { id: <application id>, openId: <system window>, data: <where inside it> }

   The host ignores anything whose origin is not its own, and anything whose id
   is not the application it is hosting, so both are set explicitly rather than
   left to a default that happens to hold.

   Nothing is attempted when there is no host to talk to: a page opened outside
   the desktop reports the jump as unavailable and the interface simply does not
   offer it. */

(function (global) {
  'use strict';

  /* The id the desktop registered this application under. The host matches on
     it before acting, so it is the one value that cannot be guessed. */
  var APP_ID = 'marknest';

  /* "Control" is the desktop's control panel window, and {id:"share", index:2}
     is its Shared Folders section - the same pair the platform's own NFS
     settings page commits when it offers to take the operator there. */
  var CONTROL_PANEL = 'Control';
  var SHARED_FOLDERS = { id: 'share', index: 2 };

  /* Reading a cross-origin parent throws, and that is the honest answer for
     anything that is not the desktop: a page opened directly has
     parent === self, and one framed by a third party is not a host we may
     address. */
  function embedded() {
    try {
      return !!global.parent && global.parent !== global;
    } catch (error) {
      return false;
    }
  }

  function canOpenSharedFolders() {
    return embedded() && typeof global.parent.postMessage === 'function';
  }

  function openSharedFolders() {
    if (!canOpenSharedFolders()) {
      return false;
    }
    try {
      global.parent.postMessage(
        { id: APP_ID, openId: CONTROL_PANEL, data: SHARED_FOLDERS },
        global.location.origin
      );
      return true;
    } catch (error) {
      return false;
    }
  }

  global.TosHost = {
    canOpenSharedFolders: canOpenSharedFolders,
    openSharedFolders: openSharedFolders
  };
})(window);
