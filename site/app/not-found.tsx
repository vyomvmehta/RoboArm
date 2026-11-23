import { ButtonLink, PageHeader } from "@/components/ui";

export default function NotFound() {
  return (
    <PageHeader title="That page is out of reach" lead="The link is wrong, or the page has not been written yet.">
      <p style={{ marginTop: "var(--space-6)" }}>
        <ButtonLink href="/">
          Go to the home page
        </ButtonLink>
      </p>
    </PageHeader>
  );
}
