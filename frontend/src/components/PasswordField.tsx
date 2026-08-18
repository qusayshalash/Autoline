import { useState } from "react";
import { useTranslation } from "react-i18next";

interface Props {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
}

export default function PasswordField({ value, onChange, placeholder, autoFocus }: Props) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);

  return (
    <div style={{ display: "flex", gap: "0.35rem" }}>
      <input
        type={visible ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
      />
      <button type="button" className="btn secondary" onClick={() => setVisible((v) => !v)}>
        {visible ? t("common.hide_password") : t("common.show_password")}
      </button>
    </div>
  );
}
