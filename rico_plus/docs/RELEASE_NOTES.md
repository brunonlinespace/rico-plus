# Rico Plus 0.0.3

Rico Plus 0.0.3 is the canonical release that closes the 0.0.3 experimental line.
It preserves the code from the supplied 0.0.4-r1 source while reissuing that
state under the 0.0.3 release identity.

## Workspace commands

- Maps **Refresh Workspace** to **Ctrl+Shift+F5**.
- Renames **Manage Workspaces…** to **Open / Manage Workspaces…** and places it directly below Refresh Workspace.
- Renames **Launch New Window…** to **New Window…**, retaining **Ctrl+Alt+Shift+N**.

## Dashboard touchscreen panning

- Based directly on Suite Pythoine 0.3.4-r2's Dashboard implementation.
- Enables Qt `QScroller` `TouchGesture` on the main Rico Plus Dashboard scroll viewport.
- Stationary taps remain ordinary Dashboard interactions while finger drags pan/scroll the Dashboard kinetically.
- Both Rico Dashboard List and Grid views inherit the behavior because they share the same scroll area.
- The folder tree and Folder Dashboard are deliberately untouched.

No additional functional changes were introduced for the 0.0.3 reissue.
