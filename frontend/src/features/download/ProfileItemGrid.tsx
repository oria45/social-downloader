import { useState } from "react";
import formStyles from "./DownloadForm.module.css";
import styles from "./ProfileItemGrid.module.css";
import { BATCH_MAX_ITEMS } from "./types";
import type { ProfileItem } from "./types";

interface ProfileItemGridProps {
  items: ProfileItem[];
  truncated: boolean;
  onDownloadSelected: (urls: string[]) => void;
  onChangeLink: () => void;
  isLoading: boolean;
}

export function ProfileItemGrid({
  items,
  truncated,
  onDownloadSelected,
  onChangeLink,
  isLoading,
}: ProfileItemGridProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  function toggle(url: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(url)) {
        next.delete(url);
      } else if (next.size < BATCH_MAX_ITEMS) {
        next.add(url);
      }
      return next;
    });
  }

  function selectAllVisible() {
    setSelected(new Set(items.slice(0, BATCH_MAX_ITEMS).map((item) => item.url)));
  }

  const atCap = selected.size >= BATCH_MAX_ITEMS;

  return (
    <div>
      <div className={styles.header}>
        <span className={styles.count}>
          {selected.size > 0
            ? `${selected.size} selected`
            : `${items.length} video${items.length === 1 ? "" : "s"} found`}
        </span>
        <button
          className={formStyles.linkButton}
          type="button"
          onClick={selectAllVisible}
          disabled={isLoading}
        >
          Select all visible
        </button>
      </div>

      {truncated && (
        <p className={styles.truncatedNote}>Showing the most recent {items.length} videos.</p>
      )}

      <div className={styles.grid}>
        {items.map((item) => {
          const isSelected = selected.has(item.url);
          return (
            <button
              key={item.id}
              type="button"
              className={`${styles.item} ${isSelected ? styles.itemSelected : ""}`}
              onClick={() => toggle(item.url)}
              disabled={isLoading || (!isSelected && atCap)}
              aria-pressed={isSelected}
            >
              <span className={styles.thumbnailWrap}>
                {item.thumbnail_url && (
                  <img className={styles.thumbnail} src={item.thumbnail_url} alt="" />
                )}
                <input
                  className={styles.checkbox}
                  type="checkbox"
                  checked={isSelected}
                  readOnly
                  tabIndex={-1}
                />
              </span>
              {item.title && <p className={styles.itemTitle}>{item.title}</p>}
            </button>
          );
        })}
      </div>

      <p className={styles.selectionNote}>Select up to {BATCH_MAX_ITEMS} at a time.</p>

      <div className={formStyles.actionRow}>
        <button
          className={formStyles.button}
          type="button"
          onClick={() => onDownloadSelected(Array.from(selected))}
          disabled={isLoading || selected.size === 0}
        >
          {isLoading ? "Downloading…" : `Download selected (${selected.size})`}
        </button>
        <button
          className={formStyles.linkButton}
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
