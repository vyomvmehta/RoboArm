/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: `npm run build` writes plain HTML/CSS/JS to out/, so it can be hosted anywhere.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
