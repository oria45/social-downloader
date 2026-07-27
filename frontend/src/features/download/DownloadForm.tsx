import { useState } from "react";
import styles from "./DownloadForm.module.css";
import { LinkForm } from "./LinkForm";
import { ProfileItemGrid } from "./ProfileItemGrid";
import { QualityPicker } from "./QualityPicker";
import { isProfileUrl } from "./profileDetection";
import { useAnalyze } from "./useAnalyze";
import { useBatchDownload } from "./useBatchDownload";
import { useDownload } from "./useDownload";
import { useListProfile } from "./useListProfile";
import type { Selection } from "./types";

const VIDEO_EXTENSIONS = new Set(["mp4", "mov", "webm", "mkv"]);
const AUDIO_EXTENSIONS = new Set(["mp3", "m4a", "wav", "ogg", "opus"]);
const IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "gif", "webp"]);

type PreviewKind = "video" | "audio" | "image" | "file";

function previewKind(filename: string): PreviewKind {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (VIDEO_EXTENSIONS.has(ext)) return "video";
  if (AUDIO_EXTENSIONS.has(ext)) return "audio";
  if (IMAGE_EXTENSIONS.has(ext)) return "image";
  return "file";
}

function defaultSelection(
  videoQualities: { height: number }[],
  audioQualities: { bitrate: number }[],
): Selection | null {
  if (videoQualities.length > 0) return { type: "video", height: videoQualities[0].height };
  if (audioQualities.length > 0) return { type: "audio", bitrate: audioQualities[0].bitrate };
  return null;
}

export function DownloadForm() {
  const [url, setUrl] = useState("");
  const [selection, setSelection] = useState<Selection | null>(null);
  const { state: analyzeState, analyze, reset: resetAnalyze } = useAnalyze();
  const { state: downloadState, download, reset: resetDownload } = useDownload();
  const { state: listState, listProfile, reset: resetList } = useListProfile();
  const { state: batchDownloadState, downloadBatch, reset: resetBatchDownload } =
    useBatchDownload();

  // A pasted URL is either a single post (existing analyze -> pick quality -> download
  // flow) or a profile/channel (new list -> multi-select -> batch download flow) - never
  // both, so exactly one pair of states is ever active at a time.
  const finalDownloadState = listState.status === "success" ? batchDownloadState : downloadState;
  const isDownloading = finalDownloadState.status === "loading";

  // The picker shows a default quality (first video, else first audio) before the user
  // touches it, so the actual download must use that same default - not just whatever
  // `selection` state holds - or clicking Download without changing the radio silently
  // sends no selection at all (yt-dlp then picks its own best format, which is often a
  // higher-bitrate webm/vp9+opus combo instead of the mp4 quality shown as selected).
  const effectiveSelection =
    selection ??
    (analyzeState.status === "success"
      ? defaultSelection(analyzeState.result.video_qualities, analyzeState.result.audio_qualities)
      : null);

  function handleLinkSubmit(submittedUrl: string) {
    setUrl(submittedUrl);
    if (isProfileUrl(submittedUrl)) {
      void listProfile(submittedUrl);
    } else {
      void analyze(submittedUrl);
    }
  }

  function handleChangeLink() {
    resetAnalyze();
    resetDownload();
    resetList();
    resetBatchDownload();
    setSelection(null);
  }

  function handleDownload() {
    void download(url, effectiveSelection ?? undefined);
  }

  function handleBatchDownload(urls: string[]) {
    void downloadBatch(urls);
  }

  return (
    <section className={styles.container} aria-labelledby="download-heading">
      <h1 id="download-heading" className={styles.title}>
        Save from TikTok, Instagram, Facebook, YouTube, or Twitter/X
      </h1>
      <p className={styles.subtitle}>Paste a link below to download it to this computer.</p>

      {finalDownloadState.status === "idle" || finalDownloadState.status === "error" ? (
        <>
          {analyzeState.status !== "success" && listState.status !== "success" && (
            <LinkForm
              onSubmit={handleLinkSubmit}
              isLoading={analyzeState.status === "loading" || listState.status === "loading"}
            />
          )}

          {analyzeState.status === "error" && (
            <p className={styles.statusError} role="alert">
              {analyzeState.error.message}
            </p>
          )}

          {listState.status === "error" && (
            <p className={styles.statusError} role="alert">
              {listState.error.message}
            </p>
          )}

          {analyzeState.status === "success" && analyzeState.result.supports_quality_selection && (
            <div className={styles.panel}>
              <QualityPicker
                title={analyzeState.result.title}
                thumbnail={analyzeState.result.thumbnail}
                videoQualities={analyzeState.result.video_qualities}
                audioQualities={analyzeState.result.audio_qualities}
                selection={effectiveSelection ?? { type: "video", height: 0 }}
                onSelectionChange={setSelection}
                onDownload={handleDownload}
                onChangeLink={handleChangeLink}
                isLoading={isDownloading}
              />
            </div>
          )}

          {analyzeState.status === "success" && !analyzeState.result.supports_quality_selection && (
            <div className={styles.panel}>
              <p>This link will be downloaded at its original quality.</p>
              <div className={styles.actionRow}>
                <button
                  className={styles.button}
                  type="button"
                  onClick={handleDownload}
                  disabled={isDownloading}
                >
                  {isDownloading ? "Downloading…" : "Download"}
                </button>
                <button
                  className={styles.linkButton}
                  type="button"
                  onClick={handleChangeLink}
                  disabled={isDownloading}
                >
                  Change link
                </button>
              </div>
            </div>
          )}

          {listState.status === "success" && (
            <div className={styles.panel}>
              <ProfileItemGrid
                items={listState.result.items}
                truncated={listState.result.truncated}
                onDownloadSelected={handleBatchDownload}
                onChangeLink={handleChangeLink}
                isLoading={isDownloading}
              />
            </div>
          )}

          {finalDownloadState.status === "error" && (
            <p className={styles.statusError} role="alert">
              {finalDownloadState.error.message}
            </p>
          )}
        </>
      ) : null}

      {finalDownloadState.status === "loading" && (
        <p className={styles.statusLoading} role="status">
          Downloading — this can take up to a minute…
        </p>
      )}

      {finalDownloadState.status === "success" && (
        <div className={styles.statusSuccess} role="status">
          <p>
            Saved{" "}
            <span className={styles.platformBadge}>{finalDownloadState.result.platform}</span>{" "}
            content to your computer as <code>{finalDownloadState.result.filename}</code>
          </p>
          {(() => {
            const kind = previewKind(finalDownloadState.result.filename);
            const src = finalDownloadState.result.blobUrl;
            if (kind === "video") {
              return <video className={styles.preview} src={src} controls />;
            }
            if (kind === "audio") {
              return <audio className={styles.preview} src={src} controls />;
            }
            if (kind === "image") {
              return (
                <img className={styles.preview} src={src} alt="Downloaded content preview" />
              );
            }
            return null;
          })()}
          <div className={styles.actionRow}>
            <button className={styles.linkButton} type="button" onClick={handleChangeLink}>
              Download another link
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
