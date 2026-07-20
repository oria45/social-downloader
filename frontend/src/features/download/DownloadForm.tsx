import { useState } from "react";
import styles from "./DownloadForm.module.css";
import { previewSrc } from "./apiBase";
import { LinkForm } from "./LinkForm";
import { QualityPicker } from "./QualityPicker";
import { useAnalyze } from "./useAnalyze";
import { useDownload } from "./useDownload";
import type { Selection } from "./types";

const VIDEO_EXTENSIONS = new Set(["mp4", "mov", "webm", "mkv"]);
const AUDIO_EXTENSIONS = new Set(["mp3", "m4a", "wav", "ogg", "opus"]);

type PreviewKind = "video" | "audio" | "image";

function previewKind(filename: string): PreviewKind {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (VIDEO_EXTENSIONS.has(ext)) return "video";
  if (AUDIO_EXTENSIONS.has(ext)) return "audio";
  return "image";
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

  function handleLinkSubmit(submittedUrl: string) {
    setUrl(submittedUrl);
    void analyze(submittedUrl);
  }

  function handleChangeLink() {
    resetAnalyze();
    resetDownload();
    setSelection(null);
  }

  function handleDownload() {
    void download(url, selection ?? undefined);
  }

  const isDownloading = downloadState.status === "loading";

  return (
    <section className={styles.container} aria-labelledby="download-heading">
      <h1 id="download-heading" className={styles.title}>
        Save from TikTok, Instagram, Facebook, or YouTube
      </h1>
      <p className={styles.subtitle}>Paste a link below to download it to this computer.</p>

      {downloadState.status === "idle" || downloadState.status === "error" ? (
        <>
          {analyzeState.status !== "success" && (
            <LinkForm onSubmit={handleLinkSubmit} isLoading={analyzeState.status === "loading"} />
          )}

          {analyzeState.status === "error" && (
            <p className={styles.statusError} role="alert">
              {analyzeState.error.message}
            </p>
          )}

          {analyzeState.status === "success" && analyzeState.result.supports_quality_selection && (
            <div className={styles.panel}>
              <QualityPicker
                title={analyzeState.result.title}
                thumbnail={analyzeState.result.thumbnail}
                videoQualities={analyzeState.result.video_qualities}
                audioQualities={analyzeState.result.audio_qualities}
                selection={
                  selection ??
                  defaultSelection(
                    analyzeState.result.video_qualities,
                    analyzeState.result.audio_qualities,
                  ) ?? { type: "video", height: 0 }
                }
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

          {downloadState.status === "error" && (
            <p className={styles.statusError} role="alert">
              {downloadState.error.message}
            </p>
          )}
        </>
      ) : null}

      {downloadState.status === "loading" && (
        <p className={styles.statusLoading} role="status">
          Downloading — this can take up to a minute…
        </p>
      )}

      {downloadState.status === "success" && (
        <div className={styles.statusSuccess} role="status">
          <p>
            Saved <span className={styles.platformBadge}>{downloadState.result.platform}</span>{" "}
            content to <code>{downloadState.result.filenames.join(", ")}</code>
          </p>
          {downloadState.result.preview_url &&
            downloadState.result.filenames[0] &&
            (() => {
              const kind = previewKind(downloadState.result.filenames[0]);
              const src = previewSrc(downloadState.result.preview_url);
              if (kind === "video") {
                return <video className={styles.preview} src={src} controls />;
              }
              if (kind === "audio") {
                return <audio className={styles.preview} src={src} controls />;
              }
              return (
                <img className={styles.preview} src={src} alt="Downloaded content preview" />
              );
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
