import { copy } from "../i18n/copy";
import { useLanguage } from "../i18n/LanguageProvider";

export function StagePage({ stage }: { stage: string }) {
  const { language } = useLanguage();
  return (
    <section className="stage-card">
      <h1 className="text-3xl font-extrabold">{copy(`stage_${stage}`, language)}</h1>
      <p>{copy("stage_stub", language)}</p>
    </section>
  );
}
