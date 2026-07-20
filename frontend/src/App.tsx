import styles from "./App.module.css";
import { DownloadForm } from "./features/download/DownloadForm";

export function App() {
  return (
    <main>
      <DownloadForm />
      <p className={styles.about}>
        We don't keep a copy — your download streams straight to you and gets deleted from our
        server right after.
      </p>
    </main>
  );
}
