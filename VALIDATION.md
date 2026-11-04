# Native prototype validation — 21 October 2026

The approved fused design is implemented with native Qt Widgets. The main window, photo/video dialogs and tagging controls use the dark palette. The supplied Twisted Imagez logo is included in the UI and executable icon.

Verified on this Windows 10 PC:

- Six catalog tests passed using generated media: original file hashes/timestamps unchanged, persistent tags, filename search, incremental updates, disconnected sources, pause/resume, folder/cache removal, retained labels on re-add, and named-reference matching.
- Native UI exercised against three generated images and one generated two-second video. Tags survived reopening. The generated video decoded and played in the native preview.
- Local quantized CLIP image/text inference and OpenCV YuNet/SFace loaded successfully. One face was detected in a public OpenCV reference fixture. These checks do not establish accuracy on the user's archive or across decades.
- Image plus text inference took about 0.21 seconds in the source-level small-fixture test. Full-library indexing, warm startup and search speed require a representative archive sample; no broad performance guarantee is made.
- The first packaged executable exposed an ICU DLL conflict: packaging collected a versioned ICU library from a build-tool PATH instead of using Windows' ICU API. Build PATH isolation fixed it. The build rejects an unexpected bundled `icuuc.dll` and verifies the executable before producing its installer.
- The corrected setup completed its end-to-end `--verify-setup` check inside `qa-output/verified-installation`: extraction, local test shortcut creation, then bundled-model inference from the installed executable. Exit code 0.
- The installed executable opened its native window through `--smoke`, captured `qa-output/verified-installation/qa-output/native-window.png`, and exited with code 0. No desktop shortcut was created during automated tests; the setup offers that option during ordinary installation.

Current deliverable: `dist/TweestMediaVaultSetup-0.2.9.exe`. Setup is self-contained; no checksum sidecar is required. Internal build checksum evidence is retained in `build/release-checksum.txt`. Personal catalogs and photos are excluded from the installer.

`G:\TK RESTORE\PHOTOS` has not been scanned. Twist MediaBridge has not been modified. First real use should start with a representative sample folder; archive face accuracy, phone-specific codecs, automatic unnamed-face grouping, GPU acceleration and a clean second PC remain outside the verified results. This prototype supports named-face similarity; full unnamed-group merge/split controls are still future work.

## Installer and menu update — version 0.1.1

- Installation always uses a dedicated TweestMediaVault subfolder. Archive paths and write access are checked before extraction.
- Protected locations request Windows elevation. The chosen target and original user desktop shortcut path survive the elevated relaunch. Cancelling approval leaves setup available. Elevated setup finishes without launching the app as administrator.
- Installed cache storage is under LOCALAPPDATA/TweestMediaVault/data; old beside-executable data is copied without deleting it.
- Eight installer/storage/icon regression tests passed. Protected paths and Windows approval/cancellation were simulated; no files were written into Program Files and no live UAC prompt was invoked during testing.
- The packaged app was run with LOCALAPPDATA redirected into QA output. Its catalog was created in that simulated profile, with no data folder created beside the executable.
- The rebuilt versioned setup passed its end-to-end extraction, local test-shortcut and installed-model checks. Its installed executable matches the tested standalone executable, and all five native menu icon assets are present.
- The existing setup window was left running. A separate versioned installer was produced because Windows locked the earlier executable.

## Preview, favourites and offline person search — version 0.1.2, 23 October 2026

- Added Show in Explorer, Save a copy, Share, Favourite and Name a person actions to both preview windows. All six sidebar entries have vector icons, including the new Favourites view.
- Sharing prepares a local file clipboard entry or copies its path; it sends nothing automatically. Explorer arguments and clipboard MIME were tested without sending messages. Export tests confirm byte-identical copies and reject overwriting originals or existing destinations.
- Favourites persist across restarts, incremental rescans and disconnected drives. Folder removal can retain favourites and labels for re-adding later, or forget them.
- Naming a person prepares the selected photo first. Remaining face preparation runs locally in the background. Default name searches find possible matches in other indexed photos even while background indexing is busy. Ordinary photo tags remain separate from confirmed face identities.
- All 22 automated tests passed: six catalog, eight preview/person-search and eight installer/storage/icon checks. The real offline face test used two independent local copies of a public OpenCV reference photo plus a generated scene, with Python network calls blocked. This verifies the workflow, not accuracy across different ages or the user's archive. Multiple-face naming requires choosing a face; cancellation records no identity.
- Native generated-media checks passed, including persistent tags, actual two-second video playback and offline image/text/face inference. The native library screenshot was visually checked for the dark theme, menu icons and preview action layout.
- The versioned installer passed its complete extraction, QA-local shortcut and installed-model checks. The installed executable's SHA-256 matches the standalone packaged executable. All new icon assets are bundled. The installed app then opened, captured its native window and exited successfully through `--smoke`, using isolated QA data; its screenshot was visually checked.
- Setup SHA-256: `754265c308e4c2c1d5adb78f5cd42c12cdc5e496dd961bc861e6ba29a0458488`.
- No user photo library was scanned, no original photo was changed, and no outbound sharing was performed during this validation.

## Default-app preview and single-file setup — version 0.1.3, 25 October 2026

- Both preview surfaces now offer Open in default app with an external-window icon. Windows chooses the registered photo/video application. The original path is passed directly, without command-shell interpolation or an export copy.
- Nine preview regression tests passed, including the original path with spaces, unavailable originals, both preview buttons and a useful error when Windows cannot launch an associated app. Default-app launch is mocked so tests do not open or modify user photos.
- The native generated-media check passed with actual video playback, persistent tags and offline inference. Its screenshot was visually checked for the updated six-action layout.
- Removed the three optional historical setup checksum sidecars from dist. Future builds retain the checksum inside build records rather than beside the installer. Only the setup EXE needs copying.
- The v0.1.3 installer passed extraction and installed offline-model verification. The installed native window then opened and exited successfully with isolated QA data. Its executable matches the standalone packaged build, the new icon is present, and dist contains no checksum sidecars. Setup size: 328,590,329 bytes.

## Video seeking — version 0.1.4, 25 October 2026

- Replaced the generic video slider with a seek control supporting absolute click-to-jump, drag-to-seek on release, and keyboard seeking. Playback position notifications no longer overwrite the playhead during dragging. Seeking is enabled only when the player reports seekable media.
- The real native playback regression passed using a generated 12-second AVI: click to nine seconds while paused, drag back to three seconds during playback, hold the handle despite position updates, and advance one second with the keyboard. Play/pause state was preserved and actual QMediaPlayer positions were checked. This does not establish support for every phone codec.
- All nine existing preview/person-search regressions passed. No user photo or video was opened or modified during testing.
- The single-file installer passed extraction and installed offline-model verification. The installed native window opened and exited successfully using isolated QA data, and its executable matches the standalone packaged build. Setup size: 328,590,969 bytes; checksum is retained in the internal build record.

## Video volume and mute — version 0.1.5, 25 October 2026

- Added a video volume slider, percentage and speaker icon toggle. Muting retains the selected level; clicking the icon again restores sound, including recovery from zero volume. Adjusting above zero unmutes. Controls affect only the player's QAudioOutput.
- The native generated-video regression passed: click to change volume, speaker mute/unmute, preserved level, zero-volume recovery and changing volume while muted. QAudioOutput volume/mute states and UI labels were asserted. Existing real click/drag/keyboard seeking and playback-state checks passed in the same run. This checks backend controls, not subjective speaker loudness.
- Visually checked the video control row at the default preview size. No user library was scanned or opened.
- The single-file v0.1.5 installer passed extraction and installed offline-model verification. The installed native window opened and exited successfully with isolated QA data; the installed executable matches the standalone build and both speaker icons are bundled.

## Month browsing — version 0.1.6, 28 October 2026

- Added All months and January–December beside the year filter, with the choice persisted in view state. Filters combine with media type, folder, year, favourites, text/person and visual search candidates. A month with All years searches across years.
- Month folders are preferred for the month filter; recognised forms include full/abbreviated English names, numbered names, YYYY-MM and numeric month directly beneath a year folder. Unrecognised folder paths fall back to the catalog date. New photos without camera dates use the archive year/month when available.
- Existing catalogs gain a folder_month field from cached path strings only, without opening originals or regenerating thumbnails, embeddings or face names. Existing catalog dates are retained.
- Twenty generated-media regression tests passed: four month tests, six catalog tests, nine preview/person-search tests and the real native video control test. After refining new fallback dates, all ten month/catalog tests passed again. Checks cover empty months, cross-year month browsing, tags/favourites/kind combinations, legacy migration retaining embeddings and named faces, restart persistence, and incremental rescanning retaining analysis.
- Visually checked the native month dropdown beside the year at the default window size. No user library was scanned or modified.
- The v0.1.6 single-file installer passed extraction and installed offline-model verification. The installed native app opened and exited successfully with isolated QA data; its executable matches the standalone packaged build.

## Missing media discovery — version 0.1.7, 28 October 2026

- Read-only filename inventory of the user's specified D:/PHOTOS/Phone Pix 2026 found 2,240 supported media files: 1,725 JPG, 145 PNG, 114 JPEG and 256 MP4. Six RAW files (four DNG, two CR2) are outside current supported formats; PDFs and the Windows shortcut are not library media. No directory errors or junctions were found. The installed catalog was read in SQLite read-only mode: its registered source is D:/PHOTOS, with 8,093 cached items but no items beneath Phone Pix 2026. The saved view was Videos. This establishes missing catalog coverage; it does not establish exactly why the earlier scan stopped or whether those files were added afterward.
- Re-adding an already covered subfolder now starts a targeted incremental scan under its existing parent source ID, instead of rejecting the overlap and falling back to the entire parent. Explicit targeted scans reject folders outside registered sources. Duplicate selected subtrees are removed. Full Rescan remains available.
- Adding folders resets old search, kind, folder, year and month filters. Added Show all media for manual reset. Result counts distinguish loaded and matching media, and Load next 500 reports remaining matches. Incremental model insertion preserves browsing position when loading additional unchanged results. Scan progress also updates while skipping unchanged cached files.
- All 23 regressions passed using generated media: three discovery/pagination, four month, six catalog, nine preview/person-search and one real native video-controls test. Targeted scans skipped unrelated older folders, preserved cached analysis/tags/favourites and thumbnail timestamps, and reused parent ownership. UI tests cover re-adding a child without an overlap warning, clearing hidden filters and loading beyond 1,000 rows without resetting the model. The updated native layout was visually checked.
- Diagnosis did not modify the installed catalog or decode/reindex the user's originals. After installing, re-add the specific 2026 folder to run the targeted scan; existing analysis is retained for unchanged cached media.
- The v0.1.7 single-file installer passed extraction and installed offline-model verification. The installed native app opened and exited successfully with isolated QA data; its executable matches the standalone packaged build.

## Rescan notices, folder dates and duplicate handling — version 0.1.8

- Current installed catalog was inspected read-only: still 8,093 cached media and zero under Phone Pix 2026. Other cached media have 2026 dates, including 341 dated February. The screenshot's February results therefore do not establish that the 2026 archive folder was scanned. The installed cache and originals were not modified by diagnosis.
- Recognised archive folder years now drive year browsing consistently with folder months, falling back to catalog dates only when no year is recognised. Existing paths gain folder_year locally without touching embeddings, face labels, thumbnails or original date fields. Tested a 2026/January archive image with a 2024 camera date and preserved all cached analysis.
- After the installed window opens, a background filename/size/mtime check identifies missing or changed supported media. A Yes/No popup offers a targeted rescan; declining leaves a visible banner. Manual Check for missing media and Open library log actions are in Folders. Unavailable sources are reported separately; no cache is pruned. No automatic decoding or face scan occurs until the user requests a rescan. Pending AI work can yield at its next safe checkpoint.
- Repeated unchanged folder paths are skipped with a local JSONL log entry. Newly added/changed files are accepted. Copied folders are skipped only if their supported relative media paths and sizes match and every media file's SHA-256 agrees with a fully indexed registered/previously scanned folder, or another folder accepted in the same addition. Modified same-size files are not ignored. This is folder-level duplicate handling; differently named/reorganised individual duplicate photos are outside this change. No originals are deleted.
- Twenty-nine regression tests passed, covering six new audit/duplicate/date tests plus existing discovery, month, catalog, preview/person-search and native video checks. After shutdown and same-batch duplicate refinements, ten audit/discovery tests passed again, including the seventh new audit test. Thirty distinct tests were exercised in total. Popup decisions were mocked while native banner visibility, queued rescan routing, QAudioOutput and QMediaPlayer states were checked. The rescan banner was visually inspected.
- New log location for installed apps: LOCALAPPDATA/TweestMediaVault/data/library-log.jsonl. It records folder checks, duplicate decisions, queued paths and rejected folders. It stays on the PC.
- The v0.1.8 single-file installer passed extraction and installed offline-model verification. The installed native app opened and exited successfully with isolated QA data; its executable matches the standalone packaged build. The user's installed cache was left unchanged; their requested rescan is initiated by accepting the new notice after updating.

## Preview navigation and zoom — version 0.1.9

- Full preview opens at up to 1280×900, constrained to the available screen, with resizing and maximise support. Previous/Next buttons and a counter follow a snapshot of the filtered browsing order. Ordinary browsing/text results include matches beyond the first 500 loaded tiles; ranked person/scene searches retain their currently loaded result order. Buttons disable at the ends.
- Native QGraphicsView photo canvas supports double-click zoom/Fit, zoom icons, 100% decoded-pixel size, Fit, Ctrl+wheel and drag-to-pan. Resize preserves a manual zoom, while Fit adapts to the viewport. New photos reset to Fit. Decode size is bounded to an 8192-pixel longest edge for very large originals.
- Mixed-media navigation reuses the video player/audio controls and stops/releases the old video source before switching. Photo zoom controls hide for videos. Paths, names, favourites and other actions target the displayed row. Unavailable originals retain navigation and show a cached photo thumbnail when available, with a clear notice.
- Four new preview tests passed using generated landscape/portrait photos and generated videos, including double-click zoom, zoom buttons, fit/resize, scrollable enlarged canvas, photo/video transitions, preserved volume, stopped/released video sources, boundary buttons, unavailable originals and navigation past item 500 under filters. All nine existing preview/person-search regressions and the real native timeline/volume regression passed: 14 tests total. Generated original-file hashes remained unchanged.
- Visually inspected the enlarged native preview and action layout. No user photos or videos were opened, reindexed or modified during this change.
- The v0.1.9 single-file installer passed extraction and installed offline-model verification. The installed native app opened and exited successfully with isolated QA data; its executable matches the standalone packaged build, and the new navigation/zoom icon assets are present.

## Keyboard and wheel preview controls — version 0.1.10

- In a fitted photo preview, Left/Right navigate the current sequence, including when an action button has keyboard focus. Wheel up selects previous; wheel down selects next. Partial wheel movement accumulates to a navigation step rather than skipping on each tiny event, and end-of-list boundaries remain clamped.
- In manual photo zoom, wheel movement only scrolls the vertical image scrollbar. Arrow keys pan the image instead of switching media. Fit/double-click restores navigation. Wheel zoom was removed in favour of the requested context-sensitive scrolling; zoom icons remain available.
- Video Left/Right navigation leaves focused timeline and volume sliders' keyboard behavior intact. Key handling is scoped to the visible preview and does not intercept nested modal dialogs. The preview removes its application event filter when closed.
- Six generated-media tests passed: five native preview tests (including the new focused-button arrow, partial-wheel navigation, list-boundary, zoomed vertical scroll, zoomed arrow-pan and return-to-Fit checks) and the real native video seek/volume regression. Fixed an initial partial-wheel test failure caused by a queued Fit recalculation clearing gesture accumulation. Generated original hashes remained unchanged; no user media was opened or indexed.
- The v0.1.10 single-file installer passed extraction and installed offline-model verification. The installed native app opened and exited successfully with isolated QA data, and its executable matches the standalone packaged build.

## Offline Edit a copy workspace — version 0.2.0

- Added photo-only Edit a copy entry points in the embedded and full previews. The separate native editor opens at up to 1460×940 with scrollable controls and a large image canvas. Geometry covers free/Original/Square/landscape/portrait crop ratios, real drag selection and a thirds grid, ±15° straighten with conservative automatic empty-edge trimming, 90° rotation and both flips.
- Exposure uses an sRGB/linear-light conversion; brightness, contrast and luminance-weighted highlights/shadows are available with debounced background previews. Full-resolution exports use the same edit recipe. Source colour profiles are converted to sRGB when present. Undo/Redo supports branching and groups a slider drag into one step. Reset remains undoable. Hold-original comparison and unsaved-close/Escape protection were checked.
- Save edited copy writes JPEG or PNG exclusively, rejects originals and existing destinations, and removes a newly created partial output if writing fails. JPEG quality is selectable; transparency is preserved for PNG and flattened onto white for JPEG. Orientation is applied once and exports clear camera/location metadata. Original files, cached labels, favourites and faces are not modified. No edit recipe is saved across editor sessions in this version.
- Share edited copy writes a uniquely named file under local data/shared-edits and places that edited file on the clipboard for the user to paste. No outbound sharing or network request occurs. The resulting local share copies remain available rather than being deleted while a clipboard entry may still reference them.
- Eleven generated-photo editor tests passed, covering crop dimensions and actual drag input, quarter rotation/flip, straighten opacity, neutral pixels and tonal changes, region-weighted shadows/highlights, EXIF orientation, PNG alpha/metadata, export overwrite rejection, history branching and slider grouping, native compare/undo/save/share, discard-cancel on Escape, preview entry points and retained catalog labels. Combined with five preview-navigation, nine existing preview/person-search and one native video test, 26 tests passed. Source hashes and modification timestamps were unchanged.
- Visually inspected the editor at its default size. Added native editor preview/export checks to --verify-install so every release verifies the frozen Pillow/Qt path as well as offline AI inference. The source-level combined check passed with exit 0 after explicitly retaining QApplication and disposing the temporary editor before shutdown; an initial verification-harness-only shutdown failure was corrected.
- No user photo or video was edited, indexed, exported or shared during validation; all editing fixtures were generated inside QA output.
- The v0.2.0 single-file installer passed extraction and installed verification, including native photo-editor preview conversion and edited PNG export with original-byte preservation. Both standalone and installed reports confirm photo_editor_export=true. The installed native app opened and exited successfully with isolated QA data; its executable matches the standalone packaged build and the Edit icon is bundled. Setup size: 328,673,861 bytes.

## Save feedback, Color and Before/After — version 0.2.1

- Reproduced the pending-crop failure: export returned after only setting a small status message, leaving the visible selection unsaved. Save/Share now commit a valid pending crop before export. Invalid/unready crops show a message; share-directory access errors also get visible feedback. Normal file-picker saving worked in diagnosis, but lacked a prominent confirmation.
- Added indeterminate progress, Saving button feedback, and a saved-file confirmation panel with Show saved copy (Explorer). Failed exports restore controls and show the error. Originals and existing destinations remain protected.
- Added saturation and vibrance sliders to Color. Saturation −100 yields equal RGB channels (black-and-white). Vibrance weights less-saturated colours more strongly; both use the same preview/export pipeline and existing undo/history.
- Replaced hold-to-compare with a persistent click-toggle Before/After button. Before disables recipe controls and hides crop guides, preserving the edit state. Export returns to After and uses the edited recipe, including a pending crop captured before switching views.
- All 17 editor tests passed with native exit code 0, including a real Save button/file picker and typed destination, Save and Share while cropping, Before-view sharing, export failure recovery/feedback, grayscale and vibrance weighting, toggle state, and existing geometry/metadata/undo/original-hash protections. The first picker-test attempt selected the old default filename via QFileDialog.selectFile; the test was corrected to type into its real filename field. Explicit deferred widget cleanup avoids a test-process shutdown failure after dialog-heavy testing. The production close path also releases the image and ignores late export callbacks.
- Visually inspected the updated editor and saved-copy confirmation. The source combined offline-model/native-editor self-check passed. No user photos were edited, exported or shared during testing.
- The v0.2.1 single-file installer passed extraction and installed offline-model/editor-export verification, confirming photo_editor_export=true. The installed native app opened and exited successfully with isolated QA data and its executable matches the standalone packaged build.

## User-selected export folders — version 0.2.2

- Save edited copy and Share edited copy now use the same destination picker. Users choose any accessible folder and filename. The first default is Windows Downloads; later dialogs start in the last successful export directory. A non-overwriting filename is suggested if the default already exists.
- The last directory is stored in local editor-preferences.json and survives reopening the editor/app. Unavailable or unreadable preferences fall back to Downloads. Failure to save this preference does not undo an otherwise successful image export.
- Sharing puts the chosen exported file on the clipboard rather than silently writing another copy under AppData/shared-edits. Cancelling creates no file. Previously created shared-edits files are retained, with no automatic move or deletion.
- All 19 editor tests passed, including real Save dialog input, chosen share-file clipboard paths, folder persistence across editor recreation, cancel behavior with no worker/file creation, and existing crop/color/export/undo/original-file safety checks. No user media was edited or exported during testing.
- The v0.2.2 single-file installer passed extraction and installed offline-model/editor-export verification. The installed native app opened and exited successfully with isolated QA data; its executable matches the standalone packaged build.

## Minimize controls and Save locations — version 0.2.3

- Enabled Minimize and the Windows system menu on editor and full-preview dialogs, retaining Maximize and removing the unused context-help hint. Native tests confirm the editor's Windows SC_MINIMIZE menu command is enabled (not greyed/disabled), and both windows minimize and restore.
- Added a dark native-widget Save dialog with a prominent Save location dropdown: Last location, Downloads, Documents, Desktop, Pictures, Videos and Home. Paths use Windows QStandardPaths, preserving redirects. Common destinations are also added to the sidebar; unavailable paths are disabled in the dropdown. Normal arbitrary-folder browsing and remembered export locations remain available.
- Selecting a dropdown location updates the real file-picker directory and retains the filename. Both Save and Share use this picker. A real dialog test selected Documents, checked the filename, accepted Save and verified the generated edited file in that directory.
- All 21 editor regressions passed; the strengthened Windows system-menu/minimize test passed again. The new Save dialog layout was visually inspected. No user media was edited or exported; tests used generated photos and temporary destination folders.
- The v0.2.3 single-file installer passed extraction and installed offline-model/editor-export verification. The installed native app opened and exited successfully with isolated QA data and its executable matches the standalone packaged build.

## Close control correction — version 0.2.4

- Reproduced the regression through Windows GetMenuState: SC_CLOSE was greyed after the prior title-bar flags change. Added explicit WindowCloseButtonHint to both the editor and full preview alongside Minimize, Maximize and SystemMenu.
- Native tests now check all three Windows system-menu commands together on both dialogs, rather than only Minimize. All are present and enabled; minimize/restore behavior still passes.
- Posted the real WM_SYSCOMMAND/SC_CLOSE message to the editor. Declining the unsaved-edit prompt kept it open; accepting closed it normally. All 22 editor regressions passed with native exit code 0. No original photo or installed user catalog was modified during testing.
- The v0.2.4 installer passed extraction and installed offline-model/editor-export checks. The installed app opened and exited successfully with isolated QA data and its executable matches the tested standalone build.

## Mixed-media wheel navigation and video posters — version 0.2.5

- Wheel navigation now covers the idle video poster and playing-video display, including their child widgets, with partial-delta accumulation and list-boundary clamping. Navigation stops/releases the old video as before. Wheel events on the timeline and volume controls are not intercepted; zoomed-photo vertical scrolling is unchanged.
- Added a video poster surface using the already cached thumbnail, visible until Play and again when stopped/end-of-playback. Pausing keeps the playback display. Missing originals can still show the cached poster with Play disabled; missing thumbnails use an explanatory placeholder. No new source scanning or automatic playback is required.
- All eight targeted preview/navigation/native-video tests passed. New checks cover photo → video → consecutive video → photo in both directions, partial wheel input on the poster, wheel navigation during real playback, stopped playback and cleared source after switching, non-interception of volume input, and disconnected-original poster visibility. A targeted rerun with a clearly identifiable generated video frame passed and its poster screenshot was visually inspected.
- Generated original hashes remained unchanged. No user photo/video was opened or reindexed during validation.
- The v0.2.5 single-file installer passed extraction and installed offline-model/editor-export verification. The installed app opened and exited successfully with isolated QA data, and its executable matches the tested standalone build.

## Multi-folder selection and pasteable address bar — version 0.2.6

- Replaced the single-folder Add picker with a directory-only native-widget dialog. Its list and details views use ExtendedSelection/SelectRows for Ctrl+click separate selection and Shift+click ranges. Add selected folders submits one path batch to the existing duplicate-check/import workflow; cancellation submits nothing.
- Added a Folder path text field and Go button. Enter in this field navigates rather than triggering the dialog's Add action. Quoted Windows paths and local file:// links are accepted; environment variables and home paths are expanded. Web URLs and unavailable paths get inline feedback without navigating. Old selections and filename text are cleared after Go. Normal folder browsing and current-directory adding remain available.
- Four native picker tests passed with ten existing discovery/audit/duplicate tests (14 total): actual Ctrl/Shift mouse selection, clipboard Ctrl+V then Enter, file-link navigation, invalid path feedback, accepted batch import and cancellation. A targeted repeat confirmed pasted-path navigation clears a prior multi-selection and keeps the dialog open. No user folders were indexed; all fixtures were temporary directories.
- Visually checked the multi-selection highlight, address bar, Go button and Add selected folders action.
- The v0.2.6 single-file installer passed extraction and installed offline-model/editor-export verification. The installed app opened and exited successfully with isolated QA data, and its executable matches the tested standalone build.

## Direct clipboard Copy — version 0.2.7

- Added an icon-labelled Copy button to both the embedded and full previews. The action copies original-file URLs and, for supported photos, full-resolution orientation-correct image pixels. Videos and unsupported photo decoders retain file-paste support. The action confirms through the main status line without a modal success prompt; unavailable originals report an error without replacing the clipboard.
- Ten focused preview tests passed using generated media, including actual clicks on both Copy buttons and reads from the Windows clipboard, EXIF rotation, file-only video/unsupported-image payloads, missing-file behavior, original-byte preservation, favourites and existing preview actions. The new button layout was visually inspected at 1250 pixels wide.
- Actual WhatsApp pasting was not exercised; receiving-app clipboard support determines which offered format is used. No user media was indexed, edited or uploaded. The separately authorized Twist MediaBridge timeline and album changes are packaged in its own project and executable.
- The v0.2.7 installer passed extraction and installed offline-model/editor-export verification. Installed native smoke exited successfully using isolated QA data; its executable hash matches the standalone packaged app.

## Partial person-name search — version 0.2.8

- Saved-name detection, face-reference selection and preview-result routing now use the same literal substring matching as tags/filenames. Daphine and Aine both find the saved person Daphine Aine and their cached possible face matches. Shared surnames include each matching saved identity without renaming or merging people. Empty input does not activate all people; percent, underscore and backslash remain literal characters.
- Ten tests passed: three new catalog/native UI checks, six catalog regressions and the existing actual offline named-person fixture. Coverage includes full/first/last names, case/whitespace, shared surnames, literal wildcards, favourites/year filters, persistence, possible-match flags, partial searches in both modes and preview sequences that retain possible results. Fixture hashes remained unchanged. No user media or installed catalog was scanned or changed.
- Added a packaged self-check of first/last/full-name lookup using generated photos and synthetic cached face features. No cache migration or rescan is required.
- The v0.2.8 installer passed extraction and installed offline-model/editor-export/partial-name-search verification. Installed native smoke exited successfully with isolated QA data; its executable hash matches the standalone packaged app.

## Missing originals and user-confirmed reconnection — version 0.2.9

- Read-only installed-catalog diagnosis of the screenshot photo found two entries for 20261017_105140.jpg: the old October/0/WhatsApp path is unavailable, while the indexed copy directly in October exists and has the same recorded size. No source file was decoded or moved, and the installed catalog was not changed by diagnosis.
- Removed the blocking preview gate so the existing cached-photo/video-poster preview remains navigable when the original is unavailable. Added Reconnect original to both action panels, enabled for missing originals. It lists only currently available indexed candidates with matching filename/type/recorded size and requires explicit identity confirmation; no automatic name/size identity assumption.
- Reconnection validates the old path is still missing and the chosen file is still available with the recorded type/size. A full SQLite backup includes committed WAL state before changes. One transaction unions tags/favourites, retains cached embeddings/analysis, transfers face references (deduplicating exact compatible detections while retaining conflicting confirmed labels), and removes only the stale catalog entry. No originals or cache-thumbnail files are removed. The dialog and main preview retarget the available row together.
- Four new reconnection/native UI checks and ten existing navigation/partial-name tests passed. A first run's backup-inspection test left its own SQLite handle open during fixture cleanup; the test now closes it explicitly and all four focused checks passed again. Coverage includes backup contents, label/favourite/embedding preservation, conflicting names, restored/mismatched-file guards, cached preview without popup, confirmation cancellation and native reconnect action. Only generated originals were used, and their hashes were retained.
- Packaged self-check also exercises reconnection with generated media and retained labels.
- The v0.2.9 installer passed extraction and installed offline-model/editor-export/partial-name/reconnection verification. Installed native smoke exited successfully with isolated QA data, and its executable hash matches the standalone packaged app.
