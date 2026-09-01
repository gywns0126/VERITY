import { dirname } from "node:path"
import { fileURLToPath } from "node:url"

const appRoot = dirname(fileURLToPath(import.meta.url))
const workspaceRoot = dirname(appRoot)

/** @type {import('next').NextConfig} */
const nextConfig = {
    turbopack: { root: workspaceRoot },
    // 오퍼레이터 전용(비공개). 검색엔진 색인 방지 헤더.
    async headers() {
        return [
            {
                source: "/:path*",
                headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
            },
        ]
    },
}

export default nextConfig
