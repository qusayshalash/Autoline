import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

interface Props {
  onFile: (file: File) => void;
  busy: boolean;
  progress: number;
}

export default function UploadDropzone({ onFile, busy, progress }: Props) {
  const { t } = useTranslation();
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      className={`dropzone${dragging ? " dragging" : ""}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.tsv,.txt"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
      {busy ? (
        <div className="dropzone-progress">
          <div className="dropzone-title">{t("datasets.uploading")}</div>
          <div className="progress-bar">
            <div style={{ width: `${progress}%` }} />
          </div>
          <div className="dropzone-progress-label">{progress}%</div>
        </div>
      ) : (
        <>
          <svg className="dropzone-icon" width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <path
              d="M16 20V6M16 6l-5 5M16 6l5 5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M6 22v3a3 3 0 0 0 3 3h14a3 3 0 0 0 3-3v-3"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <div className="dropzone-title">{t("datasets.upload")}</div>
        </>
      )}
    </div>
  );
}
