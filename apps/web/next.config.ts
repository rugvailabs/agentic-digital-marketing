import type { NextConfig } from 'next'

const config: NextConfig = {
  reactStrictMode: true,
  typedRoutes: false,
  env: {
    // Server components talk to the API over the docker-published port.
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8020',
  },
}

export default config
