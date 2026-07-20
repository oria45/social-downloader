import { useId, useState, type FormEvent } from "react";
import styles from "./DownloadForm.module.css";

interface LinkFormProps {
  onSubmit: (url: string) => void;
  isLoading: boolean;
}

export function LinkForm({ onSubmit, isLoading }: LinkFormProps) {
  const [url, setUrl] = useState("");
  const inputId = useId();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!url.trim()) return;
    onSubmit(url.trim());
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <label htmlFor={inputId} className="sr-only">
        Video or post link
      </label>
      <input
        id={inputId}
        className={styles.input}
        type="url"
        inputMode="url"
        placeholder="https://..."
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        disabled={isLoading}
        required
      />
      <button className={styles.button} type="submit" disabled={isLoading}>
        {isLoading ? "Checking…" : "Check link"}
      </button>
    </form>
  );
}
