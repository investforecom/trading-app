/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    // In dev (no Docker), proxy /api/* to FastAPI on localhost:8000
    if (process.env.NODE_ENV === 'development') {
      return [{ source: '/api/:path*', destination: 'http://localhost:8000/api/:path*' }]
    }
    return []
  },
}
export default nextConfig
