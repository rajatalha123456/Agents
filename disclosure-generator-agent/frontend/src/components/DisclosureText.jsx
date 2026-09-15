const RTL_LANGUAGES = new Set(["ur", "ar"]);
const FONT_CLASS = { ur: "font-urdu", ar: "font-arabic", en: "font-sans" };

export default function DisclosureText({ text, language }) {
  const isRtl = RTL_LANGUAGES.has(language);

  return (
    <p
      dir={isRtl ? "rtl" : "ltr"}
      lang={language}
      className={
        "leading-relaxed text-slate-800 text-[15px] whitespace-pre-wrap " +
        (FONT_CLASS[language] || "font-sans") +
        (isRtl ? " text-right" : " text-left")
      }
    >
      {text}
    </p>
  );
}
