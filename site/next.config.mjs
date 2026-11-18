/** Static export (out/), so Vercel or any static host can serve it. Root Directory on Vercel = site. */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};
export default nextConfig;
