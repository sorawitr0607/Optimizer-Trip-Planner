import { copy, type Language } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";

// derives-from: element 36 .currency-info-box as .thinking. The same recessed
// panel Thinking renders, holding the one word every stage route waits under.
export function Loading({ language }: { language?: Language }) {
  // A word alone on an empty page is the picture of a broken site. This is the
  // one loading surface every stage route shares, so a wait never reads as a
  // blank screen; routes.tsx used to own it and seven pages re-invented the
  // bare `<p>` this replaces.
  const { language: context } = useLanguage();
  const active = language ?? context;
  return (
    <p aria-busy="true" aria-live="polite" className="thinking">
      <span className="thinking-dot" />
      <span>{copy("loading", active)}</span>
    </p>
  );
}
