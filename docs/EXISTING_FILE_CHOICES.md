# Existing-file choices

When an HTTP(S) download's resolved filename already exists in the selected folder, GNS Downloader asks the user what to do:

- **Replace existing file** downloads again and atomically replaces the existing destination when the new file is complete.
- **Save as new file** preserves the existing file and selects the next available numbered filename.
- **Open existing file** opens the existing file and does not start a download.
- **Cancel** abandons the new task.

YouTube downloads perform a metadata-only preflight before starting the transfer. If the predicted final output already exists, the same choices are presented. The replace choice enables yt-dlp overwrite mode; the new-copy choice changes its output template; opening the existing file skips the transfer.

Completed tasks no longer block re-adding the same URL. Active, queued, or paused duplicate tasks are still blocked to avoid concurrent writes to the same output.

This behavior is implemented on the feature branch and is not a release/merge to the official mainline.
