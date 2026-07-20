import styles from "./DownloadForm.module.css";
import type { AudioQuality, Selection, VideoQuality } from "./types";

function encode(selection: Selection): string {
  return selection.type === "video" ? `video:${selection.height}` : `audio:${selection.bitrate}`;
}

function decode(value: string): Selection {
  const [type, amount] = value.split(":");
  return type === "video"
    ? { type: "video", height: Number(amount) }
    : { type: "audio", bitrate: Number(amount) };
}

interface QualityPickerProps {
  title: string | null;
  thumbnail: string | null;
  videoQualities: VideoQuality[];
  audioQualities: AudioQuality[];
  selection: Selection;
  onSelectionChange: (selection: Selection) => void;
  onDownload: () => void;
  onChangeLink: () => void;
  isLoading: boolean;
}

export function QualityPicker({
  title,
  thumbnail,
  videoQualities,
  audioQualities,
  selection,
  onSelectionChange,
  onDownload,
  onChangeLink,
  isLoading,
}: QualityPickerProps) {
  return (
    <div>
      {(title || thumbnail) && (
        <div className={styles.mediaInfo}>
          {thumbnail && <img className={styles.thumbnail} src={thumbnail} alt="" />}
          {title && <p className={styles.mediaTitle}>{title}</p>}
        </div>
      )}

      {videoQualities.length > 0 && (
        <fieldset className={styles.qualityGroup}>
          <legend className={styles.sectionLabel}>Video</legend>
          {videoQualities.map((q) => (
            <label key={encode({ type: "video", height: q.height })} className={styles.radioOption}>
              <input
                type="radio"
                name="quality"
                value={encode({ type: "video", height: q.height })}
                checked={selection.type === "video" && selection.height === q.height}
                onChange={(e) => onSelectionChange(decode(e.target.value))}
                disabled={isLoading}
              />
              {q.label} ({q.ext})
            </label>
          ))}
        </fieldset>
      )}

      {audioQualities.length > 0 && (
        <fieldset className={styles.qualityGroup}>
          <legend className={styles.sectionLabel}>Audio only</legend>
          {audioQualities.map((q) => (
            <label key={encode({ type: "audio", bitrate: q.bitrate })} className={styles.radioOption}>
              <input
                type="radio"
                name="quality"
                value={encode({ type: "audio", bitrate: q.bitrate })}
                checked={selection.type === "audio" && selection.bitrate === q.bitrate}
                onChange={(e) => onSelectionChange(decode(e.target.value))}
                disabled={isLoading}
              />
              {q.label}
            </label>
          ))}
        </fieldset>
      )}

      <div className={styles.actionRow}>
        <button className={styles.button} type="button" onClick={onDownload} disabled={isLoading}>
          {isLoading ? "Downloading…" : "Download"}
        </button>
        <button
          className={styles.linkButton}
          type="button"
          onClick={onChangeLink}
          disabled={isLoading}
        >
          Change link
        </button>
      </div>
    </div>
  );
}
