# Tweest MediaVault — discovery

Updated: 21 October 2026

## Scope and boundaries

A separate native Windows photo-search app, branded **Powered by Tweest**. Work belongs only in this project folder. Do not modify Twist MediaBridge at `D:\CODING WORKS\ChatGPT\MobileTrans App`.

The fused design is approved as the starting direction. Native prototype construction has started inside this project. No personal photo scanning has started; validation uses generated media only.

## Requirements

- Photos date back to 2004, in existing year/month folders across multiple locations.
- Drag folders into the app; index without moving, renaming, writing metadata to, or otherwise changing original photos.
- Persist thumbnails, search data, progress and folder registrations locally across restarts.
- Incremental rescanning, pause/resume, and disconnected-drive support.
- Prioritize natural-language visual search, folder/date filters, and fast square-thumbnail browsing.
- Face grouping is essential to test in the first prototype, including the same person across years.
- Initial source supplied by the user: `G:\TK RESTORE\PHOTOS`. Additional source folders must be supported equally, including folders on other drives. This path has not been scanned.
- Include phone video clips alongside photos, with duration badges, poster thumbnails and local playback. User chose thumbnails and playback only for the initial version; searching scenes within videos is deferred. Photo visual search and photo face grouping remain in the first prototype.
- Reopening must restore the saved library promptly without waiting for source drives, a full rescan or AI model loading. Load only visible thumbnails, restore the previous view and check for changes in the background. Measure time to a usable first screen; never promise loading an entire library into memory instantly.
- Polished dark native interface, offline privacy, and eventual setup executable with desktop shortcut.
- All native window and dialog backgrounds must remain dark; the light surround seen in the chat visualization is not part of the app.
- Remove individual sources or clear the entire registered library/cache to load a different collection. Never delete or rename originals. Offer a clear choice to retain saved annotations and named-face references for later re-adding the same paths.
- Tag the photo being previewed, and name individual detected faces (for example Ivan). Saved names must support later text search and possible face-similarity matches across the photo library, with uncertainty made visible.
- Existing filenames may already contain actual people's names. Index them for text search, while treating filename names as clues rather than automatically assigning a name to an arbitrary face in a group photo.

## Verified PC

Read from Windows system queries and NVIDIA's installed utility on 21 October 2026:

| Component | Specification |
|---|---|
| PC | HP Compaq 8200 Elite CMT PC |
| CPU | Intel Core i5-2400 @ 3.10 GHz, 4 cores / 4 threads |
| RAM | 20 GB |
| GPU | NVIDIA GeForce GTX 1660, 6144 MiB VRAM |
| NVIDIA driver | 610.47 |
| OS | Windows 10 Pro, 64-bit, build 19045 |
| Project drive D: | About 100.6 GB free of 931.5 GB |
| System drive C: | About 345.4 GB free of 476.3 GB |

Windows' video-controller memory field was unreliable; VRAM above comes from `nvidia-smi`. Available space is a point-in-time snapshot. These specifications support attempting a small local trial; they do not establish model compatibility or performance.

## Proposed small read-only prototype

1. Validate a local inference runtime on this CPU/GPU before selecting final models. Test a compact image/text embedding model and a separate face detection/embedding pipeline. Check Windows support, redistribution terms, model download size and memory requirements before implementation. CPU fallback must work.
2. User selects a representative sample of roughly 500–1,000 photos from at least two source locations. Include older and newer photos, varied lighting, groups, repeated people across years, and a removable drive if available. Never start a whole-library scan by default.
3. Build one thin native dark window: folder drop area, search box, folder/date filters, square thumbnail grid, indexing progress and pause/resume. Add a face-group view in this first trial.
4. Keep all generated trial files in a dedicated cache beneath this project folder. Persist a file inventory, thumbnails, visual embeddings, face embeddings, group assignments and durable work checkpoints. The original folders are input-only. Runtime processing is local; initial model installation may need downloads.
5. Track files by source root and relative path, with size and modification time for incremental changes. Read metadata without writing it back. Preserve disconnected roots and cached results, mark originals unavailable, and resume when reconnected. A missing drive must never be treated as mass deletion. Explicitly reconcile missing files only after a successful scan of an available root.
6. Treat face groups as tentative similarities. Allow merging and separating groups, retain corrections, and test whether people stay grouped across years. Include unknown faces and photos with no faces. No automatic naming or outside identity lookup.

## Trial measurements and acceptance checks

- **Visual accuracy:** user supplies 15–20 natural-language queries with known examples; review relevance among the first 20 results. Include scenes, objects and activities, plus folder/date combinations.
- **Face accuracy:** manually review a small set of recurring people across years, recording incorrect merges and missed matches. Start with conservative grouping and expose uncertainty. Face grouping quality must be evaluated separately from visual search.
- **Speed:** measure cold model load, photos indexed per minute, peak RAM/VRAM, thumbnail display time, and search latency after indexing. Initial targets to test: warm searches around one second or less and a responsive grid during indexing; these are targets, not promises.
- **Persistence:** restart the app and verify thumbnails, groups, source registrations and progress survive without rebuilding the entire cache.
- **Incremental behavior:** add and change sample files, then verify only affected items are reprocessed. Pause, close, reopen and resume without losing completed work.
- **Disconnected drive:** disconnect a sample source, browse its cached thumbnails, reconnect it, and confirm recovery without losing records.
- **Read-only behavior:** compare sample-file hashes, sizes and modification timestamps before and after; inspect the app's write paths to ensure all writes remain inside its own cache. Do not rely on access timestamps, which Windows may update on reads.
- **Privacy:** test indexing and search with network access disabled after model installation.

## Decision after the trial

Review visual and face accuracy, measured throughput, memory use and cache bytes per photo. Use those measurements and an eventual library count to estimate full-library time and storage. Choose the production stack and cache location only after this evidence. Finish native UI polish and installer packaging after the core trial passes.

## Design direction

Reference-led deep navy native Windows library, with a slightly lighter sidebar, restrained lavender accents, square thumbnail artwork, captions beneath images and generous space between rows. Keep existing menus and controls. A prominent natural-language search field remains. Left navigation: Library, Photos, Videos, People and Folders. Folder sources remain individually visible, with availability and indexing state. Filters combine media type, source folder and date. Clicking a photo or video opens a large local preview; video tiles show duration and a play indicator. People grouping is a first-prototype feature. This replaces the earlier charcoal and mint styling at the user's request.

Selected branding asset: `Branding\Twisted-logo idea 04.jpg`, supplied and preferred by the user. Use the original Twisted Imagez logo instead of the proposed T icon. Keep Tweest MediaVault as the app name and Powered by Tweest as the signature. Interactive design mockup uses illustrative artwork, not the user's files; it is not the app or an indexing result.

Additional reference liked by the user: Mahdi GZH's YouTube Music redesign, https://dribbble.com/shots/17147578-youtube-music-redesign. Visually inspected: charcoal surfaces with soft tonal depth, rounded outer shell, wide artwork banner, compact left navigation, a secondary video panel and a bottom playback strip. Possible adaptation: retain MediaVault's menus and square grid, borrow restrained surface depth and a large selected-media preview; show playback controls when a video is open. Treat the reference as an additional preference, not a decision to replace the current navy design. Avoid making a large promotional banner consume the default browsing area.

For the first trial, prioritize photo indexing before heavier video work, persist each completed item, and handle unsupported or damaged clips per item without blocking the library. Video indexing throughput and cache storage must be measured separately. Searchable video moments, if chosen, should return a timestamp; frame sampling can miss brief events. Audio transcription is a separate scope decision.

## Fused design for review

The user requested a fusion of both references: retain the navy square-gallery layout, menus and controls; introduce charcoal surface depth, softer framing and a cinematic selected-media preview. Use restrained gold accents from the supplied logo. The selected preview updates on thumbnail selection; video selection exposes a playback-control design. No media is loaded or played in the mockup.

Construction starts after the user is content with the design. Target a native Windows UI, installed through a simple setup executable and launched through a desktop shortcut; no development commands should be needed for everyday use. The browser-based mockup is for design review only and does not change that requirement.

Design approved in the latest user message. Implementation uses native Qt Widgets with a persistent SQLite catalog and a bounded thumbnail memory cache. The first inference backend is CPU-based ONNX for CLIP scene search and OpenCV YuNet/SFace for detected faces and named-reference similarity. GPU performance and across-years face accuracy remain to be measured with a user-selected sample. The prototype does not automatically cluster all unnamed people; its first people workflow is to label a face and find possible matches.

Version 0.1.1 adds native vector icons for all five sidebar menus. Installation uses a dedicated TweestMediaVault subfolder, requests Windows administrator approval for protected locations and defaults to a user-writable installation path. Installed catalog/cache data is stored in the user's LOCALAPPDATA profile so everyday use does not require administrator access. Source-level trial data and automated verification remain inside this project.

Version 0.1.2 adds Show in Explorer, unchanged-original export, clipboard-based sharing, persistent favourites and a Favourites sidebar tab. Icons remain on every menu and are also used for preview actions. Both the embedded and full-size previews expose these controls. Person naming is an explicit offline action; a general photo tag alone is not taken as a face identity. Newly scanned folders automatically enter local visual/face preparation. Person queries can search the completed cache while indexing continues, and selected photos can be prioritised for naming. No internet account or photo upload is needed.
