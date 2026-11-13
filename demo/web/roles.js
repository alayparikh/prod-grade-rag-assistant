// Who can open which documents, as the real app would read it from the NAS.
// Its own module (no DOM) so the page and the CI check (demo/check_search.mjs)
// read the same rules: the saved agent runs in agent.json were made
// under these roles, and the check fails if the two ever disagree.
export const isResume = (f) => /_resume\./.test(f);

export const ROLES = [
  { id: "admin", label: "Admin", can: () => true },
  { id: "engineer", label: "Engineer", can: (f) => !isResume(f) },
  { id: "hr", label: "HR", can: (f) => isResume(f) || ["team_roster.md", "company_handbook.md", "onboarding_guide.md", "security_policy.md"].includes(f) },
  // Contractors staff the West warehouse: the order and shipping docs, not HR or engineering.
  { id: "contractor", label: "Contractor", can: (f) => ["company_handbook.md", "onboarding_guide.md", "testing_standards.md",
    "order_lifecycle.md", "shipping_policy.md", "product_catalog.md"].includes(f) },
];
