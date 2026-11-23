// Facts about the site itself. Arm facts (lengths, limits, speeds) do NOT belong here:
// they come from config/*.yaml through the content loader, so they cannot drift.

export const site = {
  name: "RoboArm",
  tagline: "A 3D-printed robot arm, controlled from a web page",
  repoUrl: "https://github.com/vyomvmehta/RoboArm",
  team: ["Vyom Mehta", "Ishaan", "Siddharth"],
  school: "University of Waterloo",
};

export type NavItem = {
  href: string;
  label: string;
  owner: "Vyom" | "Ishaan";
  /** false = the page is not written yet: shown in the nav as "soon", not as a link. */
  ready: boolean;
};

// One line per page. When your page lands, flip `ready` to true in the same pull request.
export const nav: NavItem[] = [
  { href: "/mechanical/", label: "Mechanical", owner: "Vyom", ready: true },
  { href: "/kinematics/", label: "Kinematics", owner: "Vyom", ready: true },
  { href: "/electronics/", label: "Electronics", owner: "Ishaan", ready: false },
  { href: "/software/", label: "Software", owner: "Ishaan", ready: false },
  { href: "/build-log/", label: "Build log", owner: "Ishaan", ready: false },
];
